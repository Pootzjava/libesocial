# 📋 Especificação de Refatoração - LIBeSocial Premium

## Visão Geral

**Objetivo**: Transformar o LIBeSocial de uma biblioteca funcional para um **produto empresarial Premium** com qualidade de código, confiabilidade, observabilidade e recursos enterprise-grade.

**Status Atual**: Biblioteca funcional com melhorias básicas implementadas (retry, métricas, logging estruturado)

**Meta**: Produto nível enterprise com foco em:
- 🎯 Confiabilidade extrema (99.9% uptime)
- 🔒 Segurança robusta
- 📊 Observabilidade completa
- 🚀 Performance otimizada
- 🧪 Testabilidade
- 📚 Documentação profissional

---

## 📊 Análise SWOT

### Forças (Strengths)
- ✅ API funcional e testada
- ✅ Suporte a certificado A1
- ✅ Validação XSD implementada
- ✅ Estrutura modular básica
- ✅ Melhorias recentes (retry, métricas, logging)

### Fraquezas (Weaknesses)
- ❌ Gestão manual de recursos (del ws)
- ❌ Sem persistência de estado robusta
- ❌ Código com smells (getchildren depreciado)
- ❌ Testes limitados
- ❌ Sem tipagem estática completa
- ❌ Documentação técnica insuficiente

### Oportunidades (Opportunities)
- 📈 Mercado eSocial em crescimento
- 🏢 Demanda por soluções enterprise
- 🔧 Modernização com Python 3.10+
- ☁️ Integração com cloud providers
- 🤖 Automação e IA para validações

### Ameaças (Threats)
- ⚠️ Concorrentes com produtos mais maduros
- ⚠️ Mudanças frequentes no eSocial
- ⚠️ Requisitos de segurança crescentes
- ⚠️ Expectativas enterprise elevadas

---

## 🎯 Roadmap de Refatoração

### **FASE 1: Fundações Sólidas** (Semana 1-2)
Foco: Qualidade de código, type hints, estrutura

#### 1.1 Type Hints Completo
```python
# Antes
def add_event(self, event, gen_event_id=False):
    ...

# Depois
from typing import Optional, Dict, Any, Tuple, List
from lxml import etree

def add_event(
    self, 
    event: etree._ElementTree, 
    gen_event_id: bool = False,
    sign_event: bool = True
) -> Tuple[str, etree._ElementTree]:
    """Adiciona evento ao lote com validação de tipo."""
    ...
```

**Benefícios**:
- IDE support melhor (autocomplete)
- Detecção precoce de erros
- Documentação implícita
- Facilita refatoração

#### 1.2 Pydantic Models para Validação
```python
# esocial/models.py
from pydantic import BaseModel, Field, validator
from typing import Literal

class EmployerID(BaseModel):
    tpInsc: Literal[1, 2] = Field(..., description="1=CNPJ, 2=CPF")
    nrInsc: str = Field(..., min_length=11, max_length=14)
    
    @validator('nrInsc')
    def validate_document(cls, v, values):
        if values['tpInsc'] == 1 and len(v) != 14:
            raise ValueError('CNPJ deve ter 14 dígitos')
        if values['tpInsc'] == 2 and len(v) != 11:
            raise ValueError('CPF deve ter 11 dígitos')
        return v

class WSClientConfig(BaseModel):
    pfx_file: Optional[str] = None
    pfx_passw: Optional[str] = None
    employer_id: EmployerID
    sender_id: Optional[EmployerID] = None
    target: Literal['tests', 'production'] = 'tests'
    enable_persistence: bool = True
    storage_path: str = "./esocial_storage"
    
    class Config:
        arbitrary_types_allowed = True
```

**Benefícios**:
- Validação automática de dados
- Error messages claros
- Self-documenting
- Previne erros em runtime

#### 1.3 Context Managers para Gestão de Recursos
```python
# Antes
ws = WSClient(...)
try:
    result = ws.send()
finally:
    del ws  # Anti-pattern

# Depois
class WSClient(object):
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False  # Propaga exceções
    
    def cleanup(self):
        """Libera recursos (sessões HTTP, cache, etc.)"""
        if hasattr(self, '_session'):
            self._session.close()

# Uso
with WSClient(...) as ws:
    result = ws.send()
# Cleanup automático
```

#### 1.4 Logging Estruturado Aprimorado
```python
# Implementar correlation IDs
import uuid
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar('request_id', default='')

def generate_request_id() -> str:
    return str(uuid.uuid4())[:8]

# No client
async def send(self, ...):
    request_id = generate_request_id()
    token = request_id_var.set(request_id)
    
    struct_logger.info("batch_send_start", 
                      request_id=request_id,
                      batch_size=len(self.batch))
    try:
        ...
    finally:
        request_id_var.reset(token)
```

---

### **FASE 2: Resiliência Enterprise** (Semana 3-4)
Foco: Tolerância a falhas, recovery, DLQ

#### 2.1 Circuit Breaker Pattern
```python
# esocial/circuit_breaker.py
from circuitbreaker import circuit
import time

class ESocialCircuitBreaker:
    def __init__(
        self,
        failure_threshold=5,
        recovery_timeout=60,
        expected_exception=(
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        )
    ):
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
        
    @circuit(failure_threshold=5, recovery_timeout=60)
    def send_with_circuit(self, batch_xml):
        """Protege contra cascata de falhas"""
        ...
```

**Benefícios**:
- Previne overload do servidor eSocial
- Fail fast quando serviço indisponível
- Recovery automático gradual

#### 2.2 Rate Limiting Inteligente
```python
# esocial/rate_limiter.py
from datetime import datetime, timedelta
from collections import deque

class TokenBucketRateLimiter:
    """Implementa rate limiting baseado no Token Bucket"""
    
    def __init__(
        self,
        max_requests: int = 100,
        time_window: int = 60,  # segundos
    ):
        self.max_requests = max_requests
        self.time_window = time_window
        self.tokens = deque()
        
    async def acquire(self):
        now = datetime.now()
        
        # Remove tokens expirados
        while self.tokens and now - self.tokens[0] > timedelta(seconds=self.time_window):
            self.tokens.popleft()
        
        if len(self.tokens) >= self.max_requests:
            # Espera até próximo token disponível
            wait_time = self.time_window - (now - self.tokens[0]).seconds
            await asyncio.sleep(wait_time)
        
        self.tokens.append(now)
```

#### 2.3 Dead Letter Queue Aprimorada
```python
# esocial/dlq.py
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any
import json

class FailureReason(Enum):
    VALIDATION_ERROR = "validation_error"
    NETWORK_ERROR = "network_error"
    SCHEMA_ERROR = "schema_error"
    CERTIFICATE_ERROR = "certificate_error"
    RATE_LIMITED = "rate_limited"
    UNKNOWN = "unknown"

@dataclass
class DLQEntry:
    event_id: str
    event_type: str
    event_xml: str
    failure_reason: FailureReason
    error_message: str
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_attempt: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries
    
    def to_dict(self) -> dict:
        return {
            'event_id': self.event_id,
            'event_type': self.event_type,
            'failure_reason': self.failure_reason.value,
            'retry_count': self.retry_count,
            ...
        }

class AdvancedDLQ:
    """DLQ com suporte a prioridade e agendamento"""
    
    def __init__(self, storage_path: str):
        self.storage_path = Path(storage_path) / "dlq_advanced"
        self.high_priority_queue = []
        self.normal_queue = []
        
    def enqueue(
        self, 
        entry: DLQEntry, 
        priority: str = 'normal'
    ):
        """Adiciona evento à fila com prioridade"""
        queue = self.high_priority_queue if priority == 'high' else self.normal_queue
        queue.append(entry)
        self._persist()
        
    def get_retryable_events(self) -> List[DLQEntry]:
        """Retorna eventos prontos para retry"""
        now = datetime.utcnow()
        retryable = []
        
        for queue in [self.high_priority_queue, self.normal_queue]:
            for entry in queue:
                if entry.can_retry():
                    if entry.last_attempt is None:
                        retryable.append(entry)
                    elif now - entry.last_attempt > timedelta(hours=1):
                        retryable.append(entry)
                        
        return sorted(retryable, key=lambda x: x.created_at)
```

#### 2.4 Persistência com Transações
```python
# esocial/persistence_v2.py
import sqlite3
from contextlib import contextmanager

class TransactionalPersistence:
    """Persistência com suporte transacional"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
        
    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS batches (
                    batch_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP,
                    events_json JSON,
                    response_json JSON,
                    error_message TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dlq (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE,
                    event_type TEXT,
                    event_xml TEXT,
                    failure_reason TEXT,
                    retry_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
    
    @contextmanager
    def transaction(self):
        """Gerencia transações automaticamente"""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def save_batch_atomic(self, batch_state: BatchState):
        """Salva batch atomicamente"""
        with self.transaction() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO batches 
                (batch_id, status, updated_at, events_json, response_json, error_message)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                batch_state.batch_id,
                batch_state.status,
                datetime.utcnow(),
                json.dumps(batch_state.events),
                json.dumps(batch_state.response_data),
                batch_state.last_error
            ))
```

---

### **FASE 3: Performance & Escalabilidade** (Semana 5-6)
Foco: Async, caching, pooling

#### 3.1 Cliente Assíncrono
```python
# esocial/async_client.py
import asyncio
import httpx
from typing import AsyncIterator

class AsyncWSClient:
    """Cliente assíncrono para alto throughput"""
    
    def __init__(
        self,
        cert_data: Dict[str, Any],
        employer_id: Dict[str, str],
        max_concurrent: int = 10,
        timeout: float = 30.0,
    ):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.timeout = httpx.Timeout(timeout)
        self.cert_data = cert_data
        self.employer_id = employer_id
        self._client: Optional[httpx.AsyncClient] = None
        
    async def __aenter__(self):
        await self._initialize()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        
    async def _initialize(self):
        """Inicializa cliente HTTP com pool de conexões"""
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)
        self._client = httpx.AsyncClient(
            cert=(self.cert_data['cert_str'], self.cert_data['key_str']),
            verify=self.ca_bundle,
            timeout=self.timeout,
            limits=limits,
        )
        
    async def send_batch(
        self, 
        events: List[etree._ElementTree],
        group_id: int = 1
    ) -> Dict[str, Any]:
        """Envia lote assincronamente"""
        async with self.semaphore:
            batch_xml = self._make_send_envelop(group_id, events)
            
            response = await self._client.post(
                self.esocial_send_url(),
                content=etree.tostring(batch_xml),
                headers={'Content-Type': 'application/xml'}
            )
            
            response.raise_for_status()
            return self._parse_response(response.content)
            
    async def send_parallel(
        self,
        batches: List[Tuple[List[etree._ElementTree], int]]
    ) -> AsyncIterator[Dict[str, Any]]:
        """Envia múltiplos lotes em paralelo"""
        tasks = [
            self.send_batch(events, group_id) 
            for events, group_id in batches
        ]
        
        for coro in asyncio.as_completed(tasks):
            try:
                result = await coro
                yield {'status': 'success', 'result': result}
            except Exception as e:
                yield {'status': 'error', 'error': str(e)}
                
    async def close(self):
        if self._client:
            await self._client.aclose()
```

#### 3.2 Cache de Certificados e Schemas
```python
# esocial/cache.py
from functools import lru_cache
import hashlib
from datetime import datetime, timedelta

class CertificateCache:
    """Cache de certificados com invalidação por tempo"""
    
    def __init__(self, ttl_seconds: int = 3600):
        self.ttl = timedelta(seconds=ttl_seconds)
        self._cache = {}
        
    def get_or_load(
        self, 
        cert_path: str, 
        password: str,
        loader_func
    ) -> Dict[str, Any]:
        cache_key = f"{cert_path}:{hashlib.sha256(password.encode()).hexdigest()}"
        
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if datetime.now() - cached['loaded_at'] < self.ttl:
                return cached['data']
                
        # Load and cache
        data = loader_func(cert_path, password)
        self._cache[cache_key] = {
            'data': data,
            'loaded_at': datetime.now()
        }
        return data
        
    def invalidate(self, cert_path: str):
        """Invalida cache para um certificado específico"""
        keys_to_remove = [k for k in self._cache if k.startswith(cert_path)]
        for key in keys_to_remove:
            del self._cache[key]

# Uso com decorator
@lru_cache(maxsize=100)
def load_xsd_schema(schema_name: str, version: str) -> etree.XMLSchema:
    """Carrega e cached schema XSD"""
    ...
```

#### 3.3 Connection Pooling
```python
# Já implementado parcialmente no async_client
# Melhorar no cliente síncrono

class PooledWSClient(WSClient):
    """WSClient com connection pooling"""
    
    _pool: Optional[requests.Session] = None
    _pool_lock = threading.Lock()
    
    @classmethod
    def get_shared_session(cls) -> requests.Session:
        """Retorna sessão compartilhada thread-safe"""
        if cls._pool is None:
            with cls._pool_lock:
                if cls._pool is None:
                    adapter = CustomHTTPSAdapter(
                        pool_connections=10,
                        pool_maxsize=20,
                        pool_block=True,
                    )
                    cls._pool = requests.Session()
                    cls._pool.mount('https://', adapter)
        return cls._pool
```

---

### **FASE 4: Observabilidade Avançada** (Semana 7-8)
Foco: Métricas, tracing, alertas

#### 4.1 Distributed Tracing (OpenTelemetry)
```python
# esocial/tracing.py
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

def setup_tracing(service_name: str = "libesocial"):
    """Configura tracing distribuído"""
    provider = TracerProvider()
    processor = BatchSpanProcessor(
        JaegerExporter(
            agent_host_name="localhost",
            agent_port=6831,
        )
    )
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    
def traced_operation(operation_name: str):
    """Decorator para tracing automático"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span(operation_name) as span:
                span.set_attribute("component", "libesocial")
                span.set_attribute("operation", operation_name)
                
                try:
                    result = func(*args, **kwargs)
                    span.set_attribute("status", "success")
                    return result
                except Exception as e:
                    span.set_attribute("status", "error")
                    span.record_exception(e)
                    raise
        return wrapper
    return decorator
```

#### 4.2 Health Checks
```python
# esocial/health.py
from enum import Enum
from dataclasses import dataclass
from typing import List, Dict

class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

@dataclass
class HealthCheckResult:
    name: str
    status: HealthStatus
    message: str
    latency_ms: float
    details: Dict[str, Any] = None

class HealthChecker:
    """Verifica saúde do sistema e dependências"""
    
    def __init__(self, ws_client: WSClient):
        self.ws_client = ws_client
        self.checks = [
            self._check_esocial_connectivity,
            self._check_certificate_validity,
            self._check_storage_health,
        ]
        
    async def check_all(self) -> List[HealthCheckResult]:
        results = []
        for check in self.checks:
            try:
                result = await check()
                results.append(result)
            except Exception as e:
                results.append(HealthCheckResult(
                    name=check.__name__,
                    status=HealthStatus.UNHEALTHY,
                    message=str(e),
                    latency_ms=0
                ))
        return results
        
    async def _check_esocial_connectivity(self) -> HealthCheckResult:
        start = time.time()
        try:
            # Ping ao webservice
            url = self.ws_client.esocial_send_url()
            # Implementar health endpoint ou tentativa leve
            latency = (time.time() - start) * 1000
            
            return HealthCheckResult(
                name="esocial_webservice",
                status=HealthStatus.HEALTHY,
                message="Conexão bem-sucedida",
                latency_ms=latency
            )
        except Exception as e:
            return HealthCheckResult(
                name="esocial_webservice",
                status=HealthStatus.UNHEALTHY,
                message=f"Falha na conexão: {str(e)}",
                latency_ms=0
            )
```

#### 4.3 Alertas e Notificações
```python
# esocial/alerts.py
from typing import Callable, List
import smtplib
from email.mime.text import MIMEText

class AlertManager:
    """Gerencia alertas e notificações"""
    
    def __init__(self):
        self.alert_handlers: List[Callable] = []
        self.thresholds = {
            'error_rate': 0.05,  # 5%
            'latency_p99': 30.0,  # 30 segundos
            'dlq_size': 100,  # 100 eventos
        }
        
    def register_handler(self, handler: Callable):
        self.alert_handlers.append(handler)
        
    def check_and_alert(self, metrics: Dict[str, Any]):
        """Verifica métricas contra thresholds e dispara alertas"""
        alerts = []
        
        if metrics.get('error_rate', 0) > self.thresholds['error_rate']:
            alerts.append(Alert(
                severity='critical',
                title='Alta taxa de erro no eSocial',
                message=f"Error rate: {metrics['error_rate']:.2%}"
            ))
            
        if metrics.get('dlq_size', 0) > self.thresholds['dlq_size']:
            alerts.append(Alert(
                severity='warning',
                title='DLQ acima do limite',
                message=f"Eventos na DLQ: {metrics['dlq_size']}"
            ))
            
        for alert in alerts:
            for handler in self.alert_handlers:
                handler(alert)
                
    def email_handler(self, alert: Alert):
        """Envia alerta por email"""
        msg = MIMEText(alert.message)
        msg['Subject'] = f"[LIBeSocial] {alert.severity.upper()}: {alert.title}"
        msg['From'] = 'alerts@company.com'
        msg['To'] = 'team@company.com'
        
        with smtplib.SMTP('smtp.company.com') as server:
            server.send_message(msg)
```

---

### **FASE 5: Segurança Hardening** (Semana 9-10)
Foco: Secrets management, auditoria, compliance

#### 5.1 Secrets Management Integration
```python
# esocial/secrets.py
from abc import ABC, abstractmethod
from typing import Optional

class SecretsBackend(ABC):
    """Interface para backends de secrets"""
    
    @abstractmethod
    def get_secret(self, name: str) -> str:
        pass
        
    @abstractmethod
    def get_certificate(self, name: str) -> Dict[str, Any]:
        pass

class AWSSecretsManager(SecretsBackend):
    """Integração com AWS Secrets Manager"""
    
    def __init__(self, region: str = 'us-east-1'):
        import boto3
        self.client = boto3.client('secretsmanager', region_name=region)
        
    def get_secret(self, name: str) -> str:
        response = self.client.get_secret_value(SecretId=name)
        return response['SecretString']
        
    def get_certificate(self, name: str) -> Dict[str, Any]:
        secret = self.get_secret(name)
        # Parse JSON secret contendo cert e key
        ...

class VaultSecretsManager(SecretsBackend):
    """Integração com HashiCorp Vault"""
    ...

# Factory
def get_secrets_backend(backend_type: str, **kwargs) -> SecretsBackend:
    backends = {
        'aws': AWSSecretsManager,
        'vault': VaultSecretsManager,
        'local': LocalSecretsManager,
    }
    return backends[backend_type](**kwargs)

# Uso no WSClient
class SecureWSClient(WSClient):
    def __init__(
        self,
        cert_secret_name: Optional[str] = None,
        secrets_backend: Optional[SecretsBackend] = None,
        **kwargs
    ):
        if cert_secret_name and secrets_backend:
            # Carrega certificado do secrets manager
            cert_data = secrets_backend.get_certificate(cert_secret_name)
            kwargs['pkcs12_data_dict'] = cert_data
            
        super().__init__(**kwargs)
```

#### 5.2 Audit Logging
```python
# esocial/audit.py
import json
from datetime import datetime
from typing import Dict, Any

class AuditLogger:
    """Logger de auditoria para compliance"""
    
    def __init__(self, output_path: str = "./audit_logs"):
        self.output_path = Path(output_path)
        self.output_path.mkdir(parents=True, exist_ok=True)
        
    def log_event(
        self,
        action: str,
        resource_type: str,
        resource_id: str,
        user_id: str,
        details: Dict[str, Any],
        success: bool
    ):
        """Registra ação de auditoria"""
        audit_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'action': action,
            'resource_type': resource_type,
            'resource_id': resource_id,
            'user_id': user_id,
            'details': details,
            'success': success,
            'ip_address': self._get_client_ip(),
        }
        
        # Write to dated file
        date_file = f"audit_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        with open(self.output_path / date_file, 'a') as f:
            f.write(json.dumps(audit_entry) + '\n')
            
    def log_send(
        self,
        batch_id: str,
        event_count: int,
        employer_id: str,
        success: bool,
        error: Optional[str] = None
    ):
        self.log_event(
            action='BATCH_SEND',
            resource_type='esocial_batch',
            resource_id=batch_id,
            user_id=employer_id,
            details={
                'event_count': event_count,
                'error': error
            },
            success=success
        )
```

#### 5.3 Certificate Rotation
```python
# esocial/cert_rotation.py
from datetime import datetime, timedelta
from cryptography.x509 import load_pem_x509_certificate

class CertificateMonitor:
    """Monitora validade de certificados e alerta sobre expiração"""
    
    def __init__(self, warning_days: int = 30):
        self.warning_days = warning_days
        
    def check_expiration(self, cert_pem: bytes) -> Dict[str, Any]:
        cert = load_pem_x509_certificate(cert_pem)
        expiry_date = cert.not_valid_after
        days_remaining = (expiry_date - datetime.now()).days
        
        return {
            'subject': cert.subject.rfc4514_string(),
            'issuer': cert.issuer.rfc4514_string(),
            'valid_from': cert.not_valid_before.isoformat(),
            'valid_until': expiry_date.isoformat(),
            'days_remaining': days_remaining,
            'status': self._get_status(days_remaining)
        }
        
    def _get_status(self, days_remaining: int) -> str:
        if days_remaining < 0:
            return 'EXPIRED'
        elif days_remaining < self.warning_days:
            return 'EXPIRING_SOON'
        else:
            return 'VALID'
            
    def auto_rotate(
        self,
        cert_path: str,
        renewal_service_url: str
    ):
        """Automatiza renovação de certificado"""
        with open(cert_path, 'rb') as f:
            cert_data = f.read()
            
        status = self.check_expiration(cert_data)
        
        if status['status'] == 'EXPIRING_SOON':
            # Chama serviço de renovação
            response = requests.post(
                renewal_service_url,
                json={'cert_path': cert_path}
            )
            response.raise_for_status()
            
            # Backup do certificado antigo
            backup_path = f"{cert_path}.backup.{datetime.now().strftime('%Y%m%d')}"
            shutil.copy(cert_path, backup_path)
            
            # Salva novo certificado
            new_cert = response.json()['certificate']
            with open(cert_path, 'wb') as f:
                f.write(new_cert)
```

---

### **FASE 6: DX & Documentação** (Semana 11-12)
Foco: Developer experience, docs, exemplos

#### 6.1 Documentação com Sphinx/MkDocs
```yaml
# mkdocs.yml
site_name: LIBeSocial Documentation
theme:
  name: material
  palette:
    primary: blue
    
nav:
  - Home: index.md
  - Installation: installation.md
  - Quick Start: quickstart.md
  - Core Concepts:
    - Client Configuration: client.md
    - Events: events.md
    - Batches: batches.md
  - Advanced:
    - Async Client: async.md
    - Error Handling: errors.md
    - Monitoring: monitoring.md
  - API Reference: api.md
  - Examples: examples.md
  
plugins:
  - search
  - mkdocstrings
```

#### 6.2 Exemplos Completos
```python
# examples/enterprise_usage.py
"""
Exemplo completo de uso enterprise do LIBeSocial
"""
import asyncio
from esocial import AsyncWSClient, CertificateCache, AlertManager
from esocial.models import EmployerID, WSClientConfig

async def main():
    # Configuração typed
    config = WSClientConfig(
        employer_id=EmployerID(tpInsc=1, nrInsc='12345678000199'),
        target='production',
        enable_persistence=True
    )
    
    # Setup de alertas
    alerts = AlertManager()
    alerts.register_handler(alerts.email_handler)
    
    # Cache de certificados
    cert_cache = CertificateCache(ttl_seconds=3600)
    
    # Cliente assíncrono com pooling
    async with AsyncWSClient(
        cert_data=cert_cache.get_or_load(...),
        employer_id=config.employer_id.dict(),
        max_concurrent=10
    ) as client:
        
        # Envio paralelo de múltiplos lotes
        batches = [
            (events_batch_1, 1),
            (events_batch_2, 2),
            (events_batch_3, 3),
        ]
        
        async for result in client.send_parallel(batches):
            if result['status'] == 'success':
                print(f"Lote enviado: {result['result']['protocol']}")
            else:
                print(f"Falha: {result['error']}")
                # Adiciona à DLQ automaticamente
                
        # Health check
        health = await HealthChecker(client).check_all()
        for check in health:
            print(f"{check.name}: {check.status.value}")

if __name__ == '__main__':
    asyncio.run(main())
```

#### 6.3 CLI para Operações
```python
# esocial/cli.py
import click
import json

@click.group()
@click.option('--config', default='esocial_config.json')
@click.pass_context
def cli(ctx, config):
    """LIBeSocial Command Line Interface"""
    ctx.ensure_object(dict)
    ctx.obj['CONFIG'] = load_config(config)

@cli.command()
@click.argument('xml_files', nargs=-1)
@click.option('--group-id', default=1)
@click.pass_context
def send(ctx, xml_files, group_id):
    """Envia lote de eventos XML"""
    config = ctx.obj['CONFIG']
    
    with WSClient(**config) as client:
        for xml_file in xml_files:
            event = load_fromfile(xml_file)
            client.add_event(event)
            
        result, batch = client.send(group_id=group_id)
        click.echo(f"Protocolo: {result.protocolo}")

@cli.command()
@click.argument('protocol_number')
@click.pass_context
def retrieve(ctx, protocol_number):
    """Consulta resultado de lote"""
    config = ctx.obj['CONFIG']
    
    with WSClient(**config) as client:
        result = client.retrieve(protocol_number)
        decoded = decode_response(result)
        click.echo(json.dumps(decoded.toDict(), indent=2))

@cli.command()
@click.option('--format', type=click.Choice(['json', 'table']), default='table')
@click.pass_context
def dlq(ctx, format):
    """Lista eventos na Dead Letter Queue"""
    config = ctx.obj['CONFIG']
    
    with WSClient(**config) as client:
        events = client.get_dlq_events()
        
        if format == 'json':
            click.echo(json.dumps(events, indent=2))
        else:
            # Format as table
            ...

if __name__ == '__main__':
    cli(obj={})
```

---

## 📈 Métricas de Sucesso

### Qualidade de Código
- [ ] Coverage de testes > 90%
- [ ] Type hints em 100% das funções públicas
- [ ] Zero warnings do mypy
- [ ] Code climate maintainability > A
- [ ] Cyclomatic complexity média < 10

### Confiabilidade
- [ ] Uptime > 99.9%
- [ ] MTTR (Mean Time To Recovery) < 5 minutos
- [ ] Auto-recovery em 95% das falhas transitórias
- [ ] DLQ processada diariamente

### Performance
- [ ] Latência p99 < 30 segundos
- [ ] Throughput > 1000 eventos/hora
- [ ] Memory footprint < 256MB
- [ ] Cold start < 2 segundos

### Developer Experience
- [ ] Time to first successful send < 10 minutos
- [ ] Documentação completa com exemplos
- [ ] CLI funcional para operações comuns
- [ ] Error messages claras e acionáveis

---

## 🛠️ Ferramentas Recomendadas

### Desenvolvimento
- **Type Checking**: mypy
- **Linting**: ruff, flake8
- **Formatting**: black, isort
- **Testing**: pytest, pytest-asyncio
- **Coverage**: coverage.py, codecov

### CI/CD
- **GitHub Actions** para automação
- **Pre-commit hooks** para qualidade
- **Semantic Release** para versionamento

### Monitoramento
- **Prometheus** + **Grafana** para métricas
- **Jaeger** para tracing
- **Sentry** para error tracking

### Documentação
- **MkDocs** com tema Material
- **mkdocstrings** para API docs
- **Examples** directory com casos reais

---

## 📅 Cronograma Estimado

| Fase | Duração | Entregáveis |
|------|---------|-------------|
| 1. Fundações | 2 semanas | Type hints, Pydantic models, Context managers |
| 2. Resiliência | 2 semanas | Circuit breaker, Rate limiting, DLQ v2 |
| 3. Performance | 2 semanas | Async client, Caching, Connection pooling |
| 4. Observabilidade | 2 semanas | Tracing, Health checks, Alerts |
| 5. Segurança | 2 semanas | Secrets mgmt, Audit logs, Cert rotation |
| 6. DX | 2 semanas | Docs, CLI, Examples |

**Total**: 12 semanas (3 meses)

---

## 🎯 Critérios de Aceite "Premium"

Um produto é considerado **Premium** quando:

1. ✅ **Documentação**: Qualquer desenvolvedor consegue usar em < 15 minutos
2. ✅ **Erros**: Mensagens de erro claras indicam como resolver
3. ✅ **Resiliência**: Recupera-se automaticamente de falhas comuns
4. ✅ **Monitoramento**: É possível saber o que está acontecendo em tempo real
5. ✅ **Performance**: Atende requisitos de volume enterprise
6. ✅ **Segurança**: Segue best practices de segurança da indústria
7. ✅ **Testes**: Cobertura > 90%, testes rodam em < 5 minutos
8. ✅ **Código**: Limpo, tipado, fácil de manter e estender

---

## 🚀 Próximos Passos Imediatos

1. **Priorizar FASE 1** (Type hints + Pydantic) - Maior ROI imediato
2. **Setup de CI/CD** com GitHub Actions
3. **Criar issue templates** no GitHub para cada fase
4. **Estabelecer métricas baseline** antes de começar
5. **Comunicar roadmap** para stakeholders

---

## 📞 Contato e Contribuição

Este spec é um documento vivo. Contribuições são bem-vindas!

**Maintainer**: Lab TI Qualitá  
**License**: Apache 2.0  
**Repository**: github.com/qualitaocupacional/libesocial
