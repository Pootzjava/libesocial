# ==============================================================================
# Copyright 2018, Qualita Seguranca e Saude Ocupacional. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""eSocial Premium Models

Pydantic models for data validation and serialization.
FASE 1: Type hints + Pydantic models
"""
from datetime import datetime, date
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict
from pydantic_settings import BaseSettings


class TargetEnum(str, Enum):
    """Ambiente de destino do eSocial."""
    TESTS = 'tests'
    PRODUCTION = 'production'


class BatchStatusEnum(str, Enum):
    """Status de um lote de eventos."""
    PENDING = "PENDENTE"
    PROCESSING = "PROCESSANDO"
    SENT = "ENVIADO"
    SUCCESS = "SUCESSO"
    FAILED = "FALHA"
    ERROR = "ERRO"
    CANCELLED = "CANCELADO"


# ============================================================================
# Enums for Returns Module (Compatibility)
# ============================================================================

class EventStatus(str, Enum):
    """Status for eSocial events (alias for BatchStatusEnum)."""
    PENDING = "PENDENTE"
    PROCESSING = "PROCESSANDO"
    SENT = "ENVIADO"
    SUCCESS = "SUCESSO"
    ERROR = "ERRO"
    CANCELLED = "CANCELADO"


class EventType(str, Enum):
    """Types of eSocial events."""
    S1000 = "S-1000"  # Informações do Empregador
    S1010 = "S-1010"  # Tabela de Rubricas
    S1020 = "S-1020"  # Tabela de Lotações Tributárias
    S1030 = "S-1030"  # Tabela de Cargos/Empregos
    S1040 = "S-1040"  # Tabela de Ambientes de Trabalho
    S1050 = "S-1050"  # Tabela de Horários/Turnos de Trabalho
    S1060 = "S-1060"  # Tabela de Processos Administrativos/Judiciais
    S1070 = "S-1070"  # Tabela de Processos com Suspensão de Contribuições
    S1080 = "S-1080"  # Tabela de Operadores do Sistema
    S1200 = "S-1200"  # Remuneração de Servidor Público
    S1210 = "S-1210"  # Pagamentos de Rendimentos do Trabalho
    S1260 = "S-1260"  # Comercialização da Produção Rural Pessoa Física
    S1270 = "S-1270"  # Contratação de Trabalhador Avulso Não Portuário
    S1280 = "S-1280"  # Contribuição Previdenciária do Empregador
    S1295 = "S-1295"  # Solicitação de Totalizador para Recálculo
    S1298 = "S-1298"  # Reabertura dos Periódicos
    S1299 = "S-1299"  # Fechamento dos Periódicos
    S2200 = "S-2200"  # Admissão/Ingresso de Trabalhador
    S2205 = "S-2205"  # Alteração de Dados Cadastrais do Trabalhador
    S2206 = "S-2206"  # Alteração de Contrato de Trabalho
    S2210 = "S-2210"  # Comunicação de Acidente de Trabalho (CAT)
    S2220 = "S-2220"  # Monitoramento da Saúde do Trabalhador
    S2221 = "S-2221"  # Afastamento Temporário
    S2230 = "S-2230"  # Desligamento
    S2240 = "S-2240"  # Condições Ambientais do Trabalho - Fatores de Risco
    S2298 = "S-2298"  # Reintegração
    S2299 = "S-2299"  # Readmissão
    S2300 = "S-2300"  # Início de Prestação de Serviços sem Vínculo
    S2306 = "S-2306"  # Alteração de Dados sem Vínculo Empregatício
    S2399 = "S-2399"  # Término sem Vínculo Empregatício
    S2400 = "S-2400"  # Cadastro de Beneficiário Entes Públicos
    S2405 = "S-2405"  # Alteração de Dados Cadastrais de Beneficiário
    S2410 = "S-2410"  # Benefício - RPPS
    S2416 = "S-2416"  # Atualização de Valores de Benefícios
    S2418 = "S-2418"  # Encerramento de Benefício - RPPS
    S2500 = "S-2500"  # Progressão e Promoção Funcional
    S2501 = "S-2501"  # Informação de Período de Trabalho
    S3000 = "S-3000"  # Exclusão de Informações
    S3500 = "S-3500"  # Pedido de Clearance Internacional
    S5001 = "S-5001"  # Evento de Exposição a Agentes Nocivos
    S5002 = "S-5002"  # Registro de Eventos de Proteção Previdenciária
    S5003 = "S-5003"  # Monitoramento da Saúde do Trabalhador
    PENDING = 'PENDING'
    SUCCESS = 'SUCCESS'
    FAILED = 'FAILED'
    PROCESSING = 'PROCESSING'


class EmployerIdentification(BaseModel):
    """Identificação do empregador."""
    tpInsc: int = Field(..., description="Tipo de inscrição (1-CNPJ, 2-CPF)")
    nrInsc: str = Field(..., description="Número de inscrição")
    use_full: bool = Field(default=False, description="Usar número completo")
    
    @field_validator('nrInsc')
    @classmethod
    def validate_nrinsc(cls, v: str) -> str:
        """Valida formato do número de inscrição."""
        cleaned = v.strip().replace('.', '').replace('-', '').replace('/', '')
        if not cleaned.isdigit():
            raise ValueError('nrInsc deve conter apenas dígitos')
        return cleaned
    
    @field_validator('tpInsc')
    @classmethod
    def validate_tpinsc(cls, v: int) -> int:
        """Valida tipo de inscrição."""
        if v not in [1, 2]:
            raise ValueError('tpInsc deve ser 1 (CNPJ) ou 2 (CPF)')
        return v
    
    def get_nrinsc_short(self) -> str:
        """Retorna número de inscrição curto (8 primeiros dígitos para CNPJ)."""
        if self.use_full or self.tpInsc == 2:
            return self.nrInsc
        return self.nrInsc[:8]
    
    model_config = ConfigDict(json_schema_extra={
        'example': {
            'tpInsc': 1,
            'nrInsc': '12345678000195',
            'use_full': False
        }
    })


class SenderIdentification(BaseModel):
    """Identificação do transmissor."""
    tpInsc: int = Field(..., description="Tipo de inscrição")
    nrInsc: str = Field(..., description="Número de inscrição")
    
    @field_validator('tpInsc')
    @classmethod
    def validate_tpinsc(cls, v: int) -> int:
        """Valida tipo de inscrição."""
        if v not in [1, 2]:
            raise ValueError('tpInsc deve ser 1 (CNPJ) ou 2 (CPF)')
        return v


class CertificateConfig(BaseModel):
    """Configuração de certificado digital."""
    pfx_file: Optional[str] = Field(None, description="Caminho para arquivo .pfx")
    pfx_password: str = Field(..., description="Senha do certificado")
    ca_file: Optional[str] = Field(None, description="Caminho para CA bundle")
    
    model_config = ConfigDict(json_schema_extra={
        'example': {
            'pfx_file': '/path/to/cert.pfx',
            'pfx_password': 'senha123',
            'ca_file': '/path/to/ca.pem'
        }
    })


class BatchConfig(BaseModel):
    """Configuração de lote de eventos."""
    max_batch_size: int = Field(default=50, ge=1, le=50)
    group_id: int = Field(default=1, ge=1)
    clear_after_send: bool = Field(default=True)
    
    model_config = ConfigDict(json_schema_extra={
        'example': {
            'max_batch_size': 50,
            'group_id': 1,
            'clear_after_send': True
        }
    })


class EventInfo(BaseModel):
    """Informações de um evento."""
    event_id: str
    event_type: str
    status: str = 'PENDING'
    created_at: datetime = Field(default_factory=datetime.now)
    sent_at: Optional[datetime] = None
    response: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class BatchState(BaseModel):
    """Estado de um lote de eventos."""
    batch_id: str
    events: List[EventInfo] = Field(default_factory=list)
    status: BatchStatusEnum = BatchStatusEnum.PENDING
    created_at: datetime = Field(default_factory=datetime.now)
    sent_at: Optional[datetime] = None
    protocol: Optional[str] = None
    last_error: Optional[str] = None
    retry_count: int = Field(default=0)
    
    def add_event(self, event_info: EventInfo) -> None:
        """Adiciona evento ao lote."""
        self.events.append(event_info)
    
    def mark_success(self, protocol: Optional[str] = None) -> None:
        """Marca lote como sucesso."""
        self.status = BatchStatusEnum.SUCCESS
        self.sent_at = datetime.now()
        self.protocol = protocol
    
    def mark_failed(self, error: str) -> None:
        """Marca lote como falho."""
        self.status = BatchStatusEnum.FAILED
        self.last_error = error
    
    model_config = ConfigDict(json_schema_extra={
        'example': {
            'batch_id': 'batch_1_1234567890',
            'events': [],
            'status': 'PENDING',
            'retry_count': 0
        }
    })


class DLQEntry(BaseModel):
    """Entrada na Dead Letter Queue."""
    event_id: str
    event_type: str
    error_message: str
    context: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    retry_count: int = Field(default=0)
    last_retry_at: Optional[datetime] = None


class ESocialConfig(BaseSettings):
    """Configurações principais do eSocial."""
    target: TargetEnum = TargetEnum.TESTS
    esocial_version: str = 'S-1.0'
    employer_id: Optional[EmployerIdentification] = None
    sender_id: Optional[SenderIdentification] = None
    certificate: Optional[CertificateConfig] = None
    batch_config: BatchConfig = Field(default_factory=BatchConfig)
    enable_persistence: bool = True
    storage_path: str = './esocial_storage'
    timeout_seconds: int = 30
    max_retries: int = 3
    
    model_config = ConfigDict(
        env_prefix='ESOCIAL_',
        env_file='.env',
        json_schema_extra={
            'example': {
                'target': 'tests',
                'esocial_version': 'S-1.0',
                'enable_persistence': True,
                'storage_path': './esocial_storage',
                'timeout_seconds': 30,
                'max_retries': 3
            }
        }
    )
    
    @property
    def is_production(self) -> bool:
        """Verifica se está em produção."""
        return self.target == TargetEnum.PRODUCTION
    
    @property
    def is_tests(self) -> bool:
        """Verifica se está em ambiente de testes."""
        return self.target == TargetEnum.TESTS
    
    @classmethod
    def from_env(cls) -> 'ESocialConfig':
        """Cria configuração a partir de variáveis de ambiente."""
        return cls()


class WebServiceURLs(BaseModel):
    """URLs dos web services do eSocial."""
    send: str
    retrieve: str
    download_identifiers: Optional[str] = None
    download_events: Optional[str] = None
    
    @classmethod
    def get_urls(cls, target: TargetEnum) -> 'WebServiceURLs':
        """Retorna URLs baseadas no ambiente."""
        if target == TargetEnum.TESTS:
            return cls(
                send='https://webservices.producaorestrita.esocial.gov.br/servicos/empregador/enviarloteeventos/WsEnviarLoteEventos.svc?wsdl',
                retrieve='https://webservices.producaorestrita.esocial.gov.br/servicos/empregador/consultarloteeventos/WsConsultarLoteEventos.svc?wsdl',
                download_identifiers='https://webservices.producaorestrita.esocial.gov.br/servicos/empregador/dwlcirurgico/WsConsultarIdentificadoresEventos.svc?wsdl',
                download_events='https://webservices.producaorestrita.esocial.gov.br/servicos/empregador/dwlcirurgico/WsSolicitarDownloadEventos.svc?wsdl'
            )
        else:
            return cls(
                send='https://webservices.envio.esocial.gov.br/servicos/empregador/enviarloteeventos/WsEnviarLoteEventos.svc?wsdl',
                retrieve='https://webservices.consulta.esocial.gov.br/servicos/empregador/consultarloteeventos/WsConsultarLoteEventos.svc?wsdl',
                download_identifiers='https://webservices.download.esocial.gov.br/servicos/empregador/dwlcirurgico/WsConsultarIdentificadoresEventos.svc?wsdl',
                download_events='https://webservices.download.esocial.gov.br/servicos/empregador/dwlcirurgico/WsSolicitarDownloadEventos.svc?wsdl'
            )


class SendResult(BaseModel):
    """Resultado de envio de lote."""
    success: bool
    batch_id: str
    protocol: Optional[str] = Field(None, alias='protocolo', description="Protocolo de recebimento")
    response_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration_seconds: float = 0.0
    events_sent: int = 0
    
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            'example': {
                'success': True,
                'batch_id': 'batch_1_1234567890',
                'protocol': '1.2.3.4.5.6.7.8.9',
                'duration_seconds': 2.5,
                'events_sent': 10
            }
        }
    )


class HealthStatus(BaseModel):
    """Status de saúde do sistema."""
    healthy: bool
    timestamp: datetime = Field(default_factory=datetime.now)
    version: str = ''
    target: str = ''
    persistence_enabled: bool = False
    circuit_breaker_state: str = 'CLOSED'
    last_check: Optional[datetime] = None
    errors: List[str] = Field(default_factory=list)


# =============================================================================
# Rate Limiter Models (FASE 2)
# =============================================================================

class RateLimitAlgorithm(str, Enum):
    """Algoritmos de rate limiting suportados."""
    TOKEN_BUCKET = 'token_bucket'
    SLIDING_WINDOW_LOG = 'sliding_window_log'
    FIXED_WINDOW_COUNTER = 'fixed_window_counter'


class RateLimiterConfig(BaseSettings):
    """Configuração do rate limiter."""
    algorithm: RateLimitAlgorithm = RateLimitAlgorithm.TOKEN_BUCKET
    max_requests: int = Field(default=100, ge=1)
    window_size: float = Field(default=60.0, gt=0)  # seconds
    refill_rate: Optional[float] = Field(None, gt=0)  # tokens per second (for token bucket)
    
    model_config = ConfigDict(
        env_prefix='ESOCIAL_RATE_LIMIT_',
        json_schema_extra={
            'example': {
                'algorithm': 'token_bucket',
                'max_requests': 100,
                'window_size': 60.0,
                'refill_rate': 1.67  # 100 requests per minute
            }
        }
    )
    
    @field_validator('refill_rate')
    @classmethod
    def calculate_default_refill_rate(cls, v: Optional[float], info) -> Optional[float]:
        """Calcula refill rate padrão baseado em max_requests e window_size."""
        if v is None:
            # Access data from values or use default calculation
            return None  # Will be calculated in rate_limiter.py
        return v


class RateLimitResult(BaseModel):
    """Resultado de uma tentativa de rate limiting."""
    allowed: bool
    remaining_tokens: int = Field(..., ge=0)
    retry_after: Optional[float] = Field(None, ge=0)  # seconds
    reset_time: datetime
    algorithm: RateLimitAlgorithm
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    model_config = ConfigDict(json_schema_extra={
        'example': {
            'allowed': True,
            'remaining_tokens': 95,
            'retry_after': None,
            'reset_time': '2024-01-01T12:00:00Z',
            'algorithm': 'token_bucket',
            'metadata': {'capacity': 100, 'refill_rate': 1.67}
        }
    })
