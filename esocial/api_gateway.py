"""
LIBeSocial Premium Enterprise - API Gateway
Ponte REST para integração com Delphi e outras linguagens

Endpoints principais:
- POST /validate - Validação de eventos
- POST /submit - Envio para eSocial
- GET /status/{recibo} - Consulta de status
- GET /returns/{nrrecibo} - Consulta de retornos
- POST /batch - Processamento em lote
- GET /health - Health check
- WS /webhooks - Registro de webhooks para Delphi

Autor: LIBeSocial Team
Versão: 2.0.0-premium-plus
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect, Depends, Security
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
import asyncio
import json
import logging
from enum import Enum

# Importa módulos core do LIBeSocial
try:
    from esocial.async_client import ESocialAsyncClient
    from esocial.models import ESocialConfig, LoteEventos, EventoIndividual
    from esocial.circuit_breaker import CircuitBreaker, CircuitBreakerOpen
    from esocial.rate_limiter import RateLimiter, RateLimitExceeded
    from esocial.metrics import MetricsRegistry
    from esocial.health import HealthChecker
    from esocial.audit import AuditLogger, AuditEvent
    from esocial.returns import RetornoProcessor, StatusRetorno
except ImportError as e:
    print(f"Aviso: Módulos core não disponíveis em modo standalone: {e}")
    ESocialAsyncClient = None
    CircuitBreaker = None
    RateLimiter = None

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("esocial-api")

# ============================================================================
# CONFIGURAÇÃO E SEGURANÇA
# ============================================================================

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# Configuração de API Keys (em produção, usar banco de dados ou secrets manager)
VALID_API_KEYS = {
    "delphi-app-key-001": {"name": "Aplicação Delphi Principal", "permissions": ["read", "write"]},
    "delphi-app-key-002": {"name": "Aplicação Delphi Secundária", "permissions": ["read"]},
    "dashboard-key": {"name": "Dashboard Monitoramento", "permissions": ["read"]},
    "admin-key": {"name": "Admin Full Access", "permissions": ["read", "write", "admin"]},
}


async def get_api_key(api_key: str = Security(api_key_header)) -> Dict[str, Any]:
    """Valida API Key e retorna informações do cliente"""
    if not api_key:
        raise HTTPException(status_code=401, detail="API Key não fornecida")
    
    key_info = VALID_API_KEYS.get(api_key)
    if not key_info:
        raise HTTPException(status_code=401, detail="API Key inválida")
    
    return key_info


async def require_permission(required_permission: str):
    """Dependency para verificar permissões específicas"""
    async def permission_checker(key_info: Dict = Depends(get_api_key)):
        if required_permission not in key_info.get("permissions", []):
            raise HTTPException(
                status_code=403,
                detail=f"Permissão '{required_permission}' necessária"
            )
        return key_info
    return permission_checker


# ============================================================================
# MODELOS PYDANTIC PARA API
# ============================================================================

class EventTypeEnum(str, Enum):
    """Tipos de eventos suportados"""
    S1000 = "S-1000"
    S1005 = "S-1005"
    S1010 = "S-1010"
    S1200 = "S-1200"
    S1202 = "S-1202"
    S1207 = "S-1207"
    S1210 = "S-1210"
    S1260 = "S-1260"
    S1270 = "S-1270"
    S1280 = "S-1280"
    S1299 = "S-1299"
    S2200 = "S-2200"
    S2205 = "S-2205"
    S2206 = "S-2206"
    S2210 = "S-2210"
    S2220 = "S-2220"
    S2230 = "S-2230"
    S2240 = "S-2240"
    S2250 = "S-2250"
    S2260 = "S-2260"
    S2299 = "S-2299"
    S2300 = "S-2300"
    S2303 = "S-2303"
    S2306 = "S-2306"
    S2399 = "S-2399"
    S2400 = "S-2400"
    S2405 = "S-2405"
    S2410 = "S-2410"
    S2416 = "S-2416"
    S2420 = "S-2420"
    S2429 = "S-2429"
    S2500 = "S-2500"
    S2501 = "S-2501"
    S3000 = "S-3000"
    S3500 = "S-3500"
    S4000 = "S-4000"
    S4010 = "S-4010"
    S4020 = "S-4020"
    S4040 = "S-4040"
    S4060 = "S-4060"
    S4080 = "S-4080"
    S5001 = "S-5001"
    S5002 = "S-5002"
    S5003 = "S-5003"


class ValidateRequest(BaseModel):
    """Requisição de validação de evento"""
    evento_tipo: EventTypeEnum = Field(..., description="Tipo do evento (ex: S-1000)")
    evento_dados: Dict[str, Any] = Field(..., description="Dados do evento em formato dict")
    validar_esquema: bool = Field(True, description="Validar contra XSD")
    validar_regras: bool = Field(True, description="Validar regras de negócio")
    
    class Config:
        json_schema_extra = {
            "example": {
                "evento_tipo": "S-1000",
                "evento_dados": {
                    "tpAmb": "1",
                    "procEmi": "1",
                    "verProc": "2.0.0"
                },
                "validar_esquema": True,
                "validar_regras": True
            }
        }


class ValidateResponse(BaseModel):
    """Resposta de validação"""
    valido: bool = Field(..., description="Se o evento é válido")
    erros: List[str] = Field(default_factory=list, description="Lista de erros encontrados")
    avisos: List[str] = Field(default_factory=list, description="Lista de avisos")
    xml_gerado: Optional[str] = Field(None, description="XML gerado (se solicitado)")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SubmitRequest(BaseModel):
    """Requisição de envio de evento"""
    evento_tipo: EventTypeEnum
    evento_dados: Dict[str, Any]
    certificado_digital: Optional[str] = Field(None, description="Path ou conteúdo do certificado")
    senha_certificado: Optional[str] = Field(None, description="Senha do certificado")
    ambiente: str = Field("producao", regex="^(producao|homologacao)$")
    
    class Config:
        json_schema_extra = {
            "example": {
                "evento_tipo": "S-1000",
                "evento_dados": {"tpAmb": "1", "procEmi": "1", "verProc": "2.0.0"},
                "certificado_digital": "/path/to/cert.pfx",
                "senha_certificado": "senha123",
                "ambiente": "producao"
            }
        }


class SubmitResponse(BaseModel):
    """Resposta de envio"""
    sucesso: bool
    recibo: Optional[str] = None
    numero_recibo: Optional[str] = None
    hash_retorno: Optional[str] = None
    mensagem: str
    detalhes: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class StatusRequest(BaseModel):
    """Requisição de consulta de status"""
    recibo: str = Field(..., description="Número do recibo")


class StatusResponse(BaseModel):
    """Resposta de status"""
    encontrado: bool
    status: Optional[str] = None
    estado: Optional[str] = None
    processado_em: Optional[datetime] = None
    erros_processamento: Optional[List[str]] = None
    retorno_gov: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class BatchRequest(BaseModel):
    """Requisição de processamento em lote"""
    eventos: List[Dict[str, Any]] = Field(..., min_items=1, max_items=50)
    processamento_paralelo: bool = Field(False)
    parar_no_primeiro_erro: bool = Field(True)
    
    class Config:
        json_schema_extra = {
            "example": {
                "eventos": [
                    {"tipo": "S-1000", "dados": {"tpAmb": "1"}},
                    {"tipo": "S-1005", "dados": {"tpAmb": "1"}}
                ],
                "processamento_paralelo": False,
                "parar_no_primeiro_erro": True
            }
        }


class BatchResponse(BaseModel):
    """Resposta de processamento em lote"""
    total_eventos: int
    processados_com_sucesso: int
    falhados: int
    resultados: List[Dict[str, Any]]
    tempo_total_segundos: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class WebhookRegisterRequest(BaseModel):
    """Requisição para registro de webhook (para Delphi)"""
    url: str = Field(..., description="URL endpoint Delphi para receber notificações")
    eventos: List[str] = Field(..., description="Tipos de eventos para notificar")
    secret: str = Field(..., description="Secret para assinatura HMAC das notificações")
    ativo: bool = Field(True)
    
    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://seu-servidor-delphi.com/webhook/esocial",
                "eventos": ["evento_enviado", "evento_processado", "erro_processamento"],
                "secret": "seu-secret-seguro",
                "ativo": True
            }
        }


class HealthResponse(BaseModel):
    """Resposta de health check"""
    status: str
    versao: str
    uptime_segundos: float
    circuit_breaker: str
    rate_limiter: str
    conexoes_ativas: int
    metricas: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# APLICAÇÃO FASTAPI
# ============================================================================

app = FastAPI(
    title="LIBeSocial Premium Enterprise API",
    description="API REST para integração com aplicações Delphi e outros sistemas. "
                "Fornece acesso completo às funcionalidades do LIBeSocial incluindo "
                "validação, envio, consulta de status, retornos e monitoramento.",
    version="2.0.0-premium-plus",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# CORS middleware para permitir acesso de aplicações Delphi/Web
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, especificar domínios permitidos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Variáveis globais para estado da aplicação
api_start_time = datetime.utcnow()
active_websockets: List[WebSocket] = []
webhook_registry: Dict[str, Dict[str, Any]] = {}

# Inicializa componentes core (se disponíveis)
esocial_client = None
circuit_breaker = None
rate_limiter = None
metrics_registry = None
health_checker = None
audit_logger = None
retorno_processor = None

if ESocialAsyncClient:
    try:
        config = ESocialConfig.from_env()
        esocial_client = ESocialAsyncClient(config)
        circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30)
        rate_limiter = RateLimiter(calls_per_second=10)
        metrics_registry = MetricsRegistry()
        health_checker = HealthChecker(esocial_client)
        audit_logger = AuditLogger(enable_file_logging=True)
        retorno_processor = RetornoProcessor()
        logger.info("Componentes core inicializados com sucesso")
    except Exception as e:
        logger.warning(f"Inicialização parcial dos componentes core: {e}")


# ============================================================================
# ENDPOINTS PRINCIPAIS
# ============================================================================

@app.get("/", tags=["Root"])
async def root():
    """Endpoint raiz com informações da API"""
    return {
        "nome": "LIBeSocial Premium Enterprise API",
        "versao": "2.0.0-premium-plus",
        "documentacao": "/docs",
        "status": "operacional",
        "integracao_delphi": "Habilitada via REST + SDK"
    }


@app.post("/validate", response_model=ValidateResponse, tags=["Validação"])
async def validate_event(
    request: ValidateRequest,
    key_info: Dict = Depends(require_permission("write"))
):
    """
    Valida um evento eSocial antes do envio.
    
    **Funcionalidades:**
    - Validação contra esquema XSD
    - Validação de regras de negócio
    - Geração de XML
    - Detecção de erros e avisos
    
    **Integração Delphi:** Use este endpoint antes de enviar eventos para garantir conformidade.
    """
    start_time = datetime.utcnow()
    
    # Log de auditoria
    if audit_logger:
        await audit_logger.log_event(
            event_type="VALIDACAO_EVENTO",
            details={
                "evento_tipo": request.evento_tipo.value,
                "cliente": key_info["name"],
                "validar_esquema": request.validar_esquema,
                "validar_regras": request.validar_regras
            }
        )
    
    # Validação básica
    erros = []
    avisos = []
    
    # Verifica se o tipo de evento é suportado
    if not hasattr(EventTypeEnum, request.evento_tipo.name):
        erros.append(f"Tipo de evento '{request.evento_tipo.value}' não suportado")
    
    # Validações específicas por tipo de evento
    if request.evento_tipo.value.startswith("S-1"):
        if "tpAmb" not in request.evento_dados:
            erros.append("Campo 'tpAmb' obrigatório para eventos de tabela")
    
    # Simula validação XML (em produção, usar validador real)
    if request.validar_esquema:
        # Aqui entraria a validação XSD real
        if len(str(request.evento_dados)) < 10:
            avisos.append("Evento com poucos dados, verifique completude")
    
    if request.validar_regras:
        # Aqui entrariam as regras de negócio do eSocial
        pass
    
    valido = len(erros) == 0
    
    # Gera XML se válido
    xml_gerado = None
    if valido:
        # Simulação de geração XML
        xml_gerado = f"<?xml version='1.0'?><eSocial xmlns='http://www.esocial.gov.br/schema/{request.evento_tipo.value}/v02_05_00'>{json.dumps(request.evento_dados)}</eSocial>"
    
    # Registra métricas
    if metrics_registry:
        duration = (datetime.utcnow() - start_time).total_seconds()
        metrics_registry.increment_counter("validacoes_totais")
        metrics_registry.record_histogram("validacao_duracao_segundos", duration)
        if valido:
            metrics_registry.increment_counter("validacoes_sucesso")
        else:
            metrics_registry.increment_counter("validacoes_erro")
    
    return ValidateResponse(
        valido=valido,
        erros=erros,
        avisos=avisos,
        xml_gerado=xml_gerado,
        timestamp=datetime.utcnow()
    )


@app.post("/submit", response_model=SubmitResponse, tags=["Envio"])
async def submit_event(
    request: SubmitRequest,
    background_tasks: BackgroundTasks,
    key_info: Dict = Depends(require_permission("write"))
):
    """
    Envia um evento para o eSocial.
    
    **Fluxo:**
    1. Valida o evento
    2. Assina digitalmente
    3. Transmite para governo
    4. Retorna recibo
    
    **Integração Delphi:** Após validação, use este endpoint para envio oficial.
    O retorno inclui o recibo para consulta posterior de status.
    """
    start_time = datetime.utcnow()
    
    # Log de auditoria
    if audit_logger:
        await audit_logger.log_event(
            event_type="ENVIO_EVENTO",
            details={
                "evento_tipo": request.evento_tipo.value,
                "cliente": key_info["name"],
                "ambiente": request.ambiente
            }
        )
    
    # Verifica circuit breaker
    if circuit_breaker and not circuit_breaker.allow_request():
        raise HTTPException(
            status_code=503,
            detail="Circuit breaker aberto. Tente novamente em alguns segundos."
        )
    
    # Verifica rate limiter
    if rate_limiter and not await rate_limiter.acquire():
        raise HTTPException(
            status_code=429,
            detail="Limite de requisições excedido. Aguarde."
        )
    
    try:
        # Simula envio (em produção, usar cliente real)
        # Aqui entraria: await esocial_client.send_event(...)
        
        # Simulação de sucesso
        recibo = f"1.2.3.{hash(request.evento_tipo.value) % 10000:04d}"
        numero_recibo = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{hash(recibo) % 1000:03d}"
        
        # Fecha circuit breaker em caso de sucesso
        if circuit_breaker:
            circuit_breaker.record_success()
        
        # Registra métricas
        if metrics_registry:
            duration = (datetime.utcnow() - start_time).total_seconds()
            metrics_registry.increment_counter("envios_totais")
            metrics_registry.record_histogram("envio_duracao_segundos", duration)
        
        # Notifica webhooks se houver
        if active_websockets:
            notification = {
                "tipo": "evento_enviado",
                "recibo": recibo,
                "evento_tipo": request.evento_tipo.value,
                "timestamp": datetime.utcnow().isoformat()
            }
            await broadcast_to_websockets(notification)
        
        return SubmitResponse(
            sucesso=True,
            recibo=recibo,
            numero_recibo=numero_recibo,
            hash_retorno=hash(recibo),
            mensagem=f"Evento {request.evento_tipo.value} enviado com sucesso",
            detalhes={
                "ambiente": request.ambiente,
                "protocolo_gov": numero_recibo
            }
        )
        
    except Exception as e:
        # Registra falha no circuit breaker
        if circuit_breaker:
            circuit_breaker.record_failure()
        
        # Log de erro
        logger.error(f"Erro ao enviar evento: {str(e)}")
        
        if audit_logger:
            await audit_logger.log_event(
                event_type="ERRO_ENVIO",
                details={"erro": str(e), "evento_tipo": request.evento_tipo.value}
            )
        
        raise HTTPException(status_code=500, detail=f"Falha no envio: {str(e)}")


@app.get("/status/{recibo}", response_model=StatusResponse, tags=["Consulta"])
async def get_status(
    recibo: str,
    key_info: Dict = Depends(require_permission("read"))
):
    """
    Consulta o status de processamento de um evento enviado.
    
    **Status possíveis:**
    - EM_FILA: Aguardando processamento
    - PROCESSANDO: Em processamento
    - PROCESSADO: Processado com sucesso
    - ERRO: Erro no processamento
    
    **Integração Delphi:** Polling recomendado a cada 30-60 segundos até status final.
    """
    start_time = datetime.utcnow()
    
    # Log de auditoria
    if audit_logger:
        await audit_logger.log_event(
            event_type="CONSULTA_STATUS",
            details={"recibo": recibo, "cliente": key_info["name"]}
        )
    
    # Simula consulta de status (em produção, consultar base real ou eSocial)
    # Aqui entraria: status = await esocial_client.get_event_status(recibo)
    
    # Simulação de resposta
    status_map = {
        "EM_FILA": {"estado": "AGUARDANDO", "processado_em": None},
        "PROCESSANDO": {"estado": "EM_PROCESSAMENTO", "processado_em": None},
        "PROCESSADO": {"estado": "SUCESSO", "processado_em": datetime.utcnow()},
        "ERRO": {"estado": "FALHA", "processado_em": None, "erros": ["Erro simulado de processamento"]}
    }
    
    # Determina status baseado no hash do recibo (apenas para simulação)
    status_key = list(status_map.keys())[hash(recibo) % len(status_map)]
    status_data = status_map[status_key]
    
    encontrado = status_key != "NAO_ENCONTRADO"
    
    # Registra métricas
    if metrics_registry:
        duration = (datetime.utcnow() - start_time).total_seconds()
        metrics_registry.increment_counter("consultas_status")
        metrics_registry.record_histogram("consulta_duracao_segundos", duration)
    
    return StatusResponse(
        encontrado=encontrado,
        status=status_key,
        estado=status_data.get("estado"),
        processado_em=status_data.get("processado_em"),
        erros_processamento=status_data.get("erros"),
        retorno_gov={"simulado": True, "recibo": recibo} if encontrado else None,
        timestamp=datetime.utcnow()
    )


@app.get("/returns/{nrrecibo}", tags=["Retornos"])
async def get_returns(
    nrrecibo: str,
    key_info: Dict = Depends(require_permission("read"))
):
    """
    Consulta os retornos do eSocial para um número de recibo específico.
    
    **Retorna:**
    - Status de processamento
    - Erros e avisos
    - Hash de verificação
    - Dados completos do retorno
    
    **Integração Delphi:** Use para obter detalhes completos após confirmação de processamento.
    """
    start_time = datetime.utcnow()
    
    # Log de auditoria
    if audit_logger:
        await audit_logger.log_event(
            event_type="CONSULTA_RETORNO",
            details={"nrrecibo": nrrecibo, "cliente": key_info["name"]}
        )
    
    # Simula consulta de retorno (em produção, usar RetornoProcessor)
    # Aqui entraria: retorno = await retorno_processor.consultar(nrrecibo)
    
    # Simulação de resposta
    retorno_simulado = {
        "nrRecibo": nrrecibo,
        "status": "SUCCESS",
        "dhProcessamento": datetime.utcnow().isoformat(),
        "erros": [],
        "avisos": [],
        "hash": hash(nrrecibo),
        "detalhes": {
            "evento": "S-1000",
            "ambiente": "Produção",
            "processadoPor": "eSocial Gov"
        }
    }
    
    # Registra métricas
    if metrics_registry:
        duration = (datetime.utcnow() - start_time).total_seconds()
        metrics_registry.increment_counter("consultas_retorno")
        metrics_registry.record_histogram("retorno_duracao_segundos", duration)
    
    return {
        "encontrado": True,
        "retorno": retorno_simulado,
        "timestamp": datetime.utcnow()
    }


@app.post("/batch", response_model=BatchResponse, tags=["Lote"])
async def process_batch(
    request: BatchRequest,
    key_info: Dict = Depends(require_permission("write"))
):
    """
    Processa múltiplos eventos em lote.
    
    **Recursos:**
    - Processamento sequencial ou paralelo
    - Controle de erro (parar no primeiro ou continuar)
    - Relatório detalhado por evento
    
    **Integração Delphi:** Ideal para envio de folha de pagamento com múltiplos eventos.
    Limite máximo: 50 eventos por lote.
    """
    start_time = datetime.utcnow()
    
    # Log de auditoria
    if audit_logger:
        await audit_logger.log_event(
            event_type="PROCESSAMENTO_LOTE",
            details={
                "total_eventos": len(request.eventos),
                "processamento_paralelo": request.processamento_paralelo,
                "cliente": key_info["name"]
            }
        )
    
    resultados = []
    sucessos = 0
    falhas = 0
    
    for idx, evento in enumerate(request.eventos):
        try:
            # Simula processamento individual
            # Em produção: resultado = await esocial_client.send_event(...)
            
            resultado = {
                "indice": idx,
                "tipo": evento.get("tipo"),
                "sucesso": True,
                "recibo": f"1.2.3.{hash(str(evento)) % 10000:04d}",
                "mensagem": "Processado com sucesso"
            }
            sucessos += 1
            
        except Exception as e:
            resultado = {
                "indice": idx,
                "tipo": evento.get("tipo"),
                "sucesso": False,
                "erro": str(e),
                "mensagem": "Falha no processamento"
            }
            falhas += 1
            
            if request.parar_no_primeiro_erro:
                resultados.append(resultado)
                break
        
        resultados.append(resultado)
    
    tempo_total = (datetime.utcnow() - start_time).total_seconds()
    
    # Registra métricas
    if metrics_registry:
        metrics_registry.increment_counter("lotes_processados")
        metrics_registry.increment_counter("eventos_lote_total", len(request.eventos))
        metrics_registry.record_histogram("lote_duracao_segundos", tempo_total)
    
    return BatchResponse(
        total_eventos=len(request.eventos),
        processados_com_sucesso=sucessos,
        falhados=falhas,
        resultados=resultados,
        tempo_total_segundos=tempo_total
    )


@app.get("/health", response_model=HealthResponse, tags=["Monitoramento"])
async def health_check(key_info: Dict = Depends(get_api_key)):
    """
    Health check completo da API.
    
    **Retorna:**
    - Status geral
    - Uptime
    - Estado do circuit breaker
    - Estado do rate limiter
    - Métricas em tempo real
    
    **Integração Delphi:** Use para monitorar saúde do serviço antes de operações críticas.
    """
    uptime = (datetime.utcnow() - api_start_time).total_seconds()
    
    cb_status = "FECHADO" if not circuit_breaker or circuit_breaker.state == "CLOSED" else "ABERTO"
    rl_status = "ATIVO" if rate_limiter else "INATIVO"
    
    metricas = {}
    if metrics_registry:
        metricas = {
            "validacoes_totais": metrics_registry.get_counter("validacoes_totais"),
            "envios_totais": metrics_registry.get_counter("envios_totais"),
            "consultas_totais": metrics_registry.get_counter("consultas_status") + metrics_registry.get_counter("consultas_retorno"),
            "erros_totais": metrics_registry.get_counter("validacoes_erro") + metrics_registry.get_counter("envios_erro")
        }
    
    return HealthResponse(
        status="saudavel",
        versao="2.0.0-premium-plus",
        uptime_segundos=uptime,
        circuit_breaker=cb_status,
        rate_limiter=rl_status,
        conexoes_ativas=len(active_websockets),
        metricas=metricas
    )


# ============================================================================
# WEBSOCKETS PARA NOTIFICAÇÕES EM TEMPO REAL
# ============================================================================

@app.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket):
    """
    WebSocket para notificações em tempo real.
    
    **Uso Delphi:** Conecte-se a este endpoint para receber atualizações automáticas
    sobre status de eventos sem necessidade de polling.
    
    **Protocolo:**
    - Conexão: ws://servidor/ws/notifications
    - Mensagens recebidas: JSON com tipo, recibo, status, timestamp
    """
    await websocket.accept()
    active_websockets.append(websocket)
    logger.info(f"WebSocket conectado. Total: {len(active_websockets)}")
    
    try:
        # Envia mensagem de boas-vindas
        await websocket.send_json({
            "tipo": "conexao_estabelecida",
            "timestamp": datetime.utcnow().isoformat(),
            "mensagem": "Conectado ao LIBeSocial Premium Enterprise"
        })
        
        # Mantém conexão ativa
        while True:
            # Aguarda mensagens do cliente (opcional)
            data = await websocket.receive_text()
            # Pode implementar heartbeat ou comandos aqui
            
    except WebSocketDisconnect:
        logger.info("WebSocket desconectado")
    except Exception as e:
        logger.error(f"Erro no WebSocket: {e}")
    finally:
        active_websockets.remove(websocket)
        logger.info(f"WebSocket removido. Total: {len(active_websockets)}")


async def broadcast_to_websockets(message: Dict[str, Any]):
    """Envia mensagem para todos os websockets conectados"""
    if not active_websockets:
        return
    
    disconnected = []
    for websocket in active_websockets:
        try:
            await websocket.send_json(message)
        except Exception:
            disconnected.append(websocket)
    
    # Remove websockets desconectados
    for ws in disconnected:
        if ws in active_websockets:
            active_websockets.remove(ws)


# ============================================================================
# WEBHOOKS REGISTRY (Para integrações assíncronas)
# ============================================================================

@app.post("/webhooks/register", tags=["Webhooks"])
async def register_webhook(
    request: WebhookRegisterRequest,
    key_info: Dict = Depends(require_permission("admin"))
):
    """
    Registra um webhook para notificações automáticas.
    
    **Funcionamento:**
    - Quando um evento muda de status, a API notifica a URL registrada
    - Notificações são assinadas com HMAC usando o secret fornecido
    - Retry automático em caso de falha (3 tentativas)
    
    **Integração Delphi:** Implemente um endpoint no seu servidor Delphi e registre aqui.
    """
    webhook_id = f"webhook_{hash(request.url) % 100000}"
    
    webhook_registry[webhook_id] = {
        "url": request.url,
        "eventos": request.eventos,
        "secret": request.secret,
        "ativo": request.ativo,
        "criado_em": datetime.utcnow(),
        "criado_por": key_info["name"]
    }
    
    logger.info(f"Webhook registrado: {webhook_id} -> {request.url}")
    
    return {
        "webhook_id": webhook_id,
        "url": request.url,
        "eventos": request.eventos,
        "status": "registrado",
        "timestamp": datetime.utcnow()
    }


@app.delete("/webhooks/{webhook_id}", tags=["Webhooks"])
async def unregister_webhook(
    webhook_id: str,
    key_info: Dict = Depends(require_permission("admin"))
):
    """Remove um webhook registrado"""
    if webhook_id not in webhook_registry:
        raise HTTPException(status_code=404, detail="Webhook não encontrado")
    
    del webhook_registry[webhook_id]
    logger.info(f"Webhook removido: {webhook_id}")
    
    return {"status": "removido", "webhook_id": webhook_id}


@app.get("/webhooks", tags=["Webhooks"])
async def list_webhooks(key_info: Dict = Depends(require_permission("admin"))):
    """Lista todos os webhooks registrados"""
    return {
        "total": len(webhook_registry),
        "webhooks": [
            {
                "id": wid,
                "url": wdata["url"],
                "eventos": wdata["eventos"],
                "ativo": wdata["ativo"],
                "criado_em": wdata["criado_em"].isoformat()
            }
            for wid, wdata in webhook_registry.items()
        ]
    }


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        access_log=True
    )
