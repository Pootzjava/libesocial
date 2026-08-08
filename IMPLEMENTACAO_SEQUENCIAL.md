# 📋 Plano de Implementação Sequencial - LIBeSocial Premium

Este documento fornece instruções **passo a passo** para implementar cada fase da refatoração.

---

## 🎯 Como Usar Este Guia

1. **Siga a ordem**: As fases são sequenciais e cumulativas
2. **Teste cada passo**: Execute os testes após cada mudança
3. **Commit frequente**: Commits pequenos e atômicos
4. **Revise**: Code review obrigatório para cada PR

---

## 📁 Estrutura de Pastas Sugerida

```
/workspace/
├── esocial/
│   ├── __init__.py
│   ├── models.py              # NOVO: Pydantic models
│   ├── client.py              # Refatorar
│   ├── async_client.py        # NOVO: FASE 3
│   ├── xml.py                 # Refatorar
│   ├── utils.py               # Refatorar
│   ├── persistence.py         # Refatorar (FASE 2)
│   ├── metrics.py             # Manter
│   ├── circuit_breaker.py     # NOVO: FASE 2
│   ├── rate_limiter.py        # NOVO: FASE 2
│   ├── cache.py               # NOVO: FASE 3
│   ├── health.py              # NOVO: FASE 4
│   ├── tracing.py             # NOVO: FASE 4
│   ├── alerts.py              # NOVO: FASE 4
│   ├── secrets.py             # NOVO: FASE 5
│   ├── audit.py               # NOVO: FASE 5
│   ├── cli.py                 # NOVO: FASE 6
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_client.py
│   │   ├── test_xml.py
│   │   ├── test_models.py     # NOVO
│   │   ├── test_async.py      # NOVO: FASE 3
│   │   └── ...
│   └── xsd/
├── examples/                   # NOVO: FASE 6
│   ├── basic_usage.py
│   ├── enterprise_usage.py
│   └── async_usage.py
├── docs/                       # NOVO: FASE 6
│   ├── index.md
│   ├── installation.md
│   └── ...
├── tests/
├── setup.py                    # Atualizar
├── requirements-dev.txt        # Atualizar
├── pyproject.toml             # NOVO
├── .pre-commit-config.yaml    # NOVO
├── mypy.ini                   # NOVO
└── README.md                  # Atualizar
```

---

## 🔧 SETUP INICIAL (Semana 0)

### Passo 0.1: Configurar Ambiente de Desenvolvimento

```bash
# Criar virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# ou .venv\Scripts\activate  # Windows

# Instalar dependências de desenvolvimento
pip install -e ".[dev]"

# Instalar ferramentas de qualidade
pip install mypy ruff black isort pytest pytest-cov pre-commit
```

### Passo 0.2: Configurar Pre-commit Hooks

**Arquivo: `.pre-commit-config.yaml`**
```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.6
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]

  - repo: https://github.com/psf/black
    rev: 23.11.0
    hooks:
      - id: black

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.7.1
    hooks:
      - id: mypy
        additional_dependencies: [types-requests, types-lxml]
```

```bash
# Instalar hooks
pre-commit install
```

### Passo 0.3: Configurar Type Checker

**Arquivo: `mypy.ini`**
```ini
[mypy]
python_version = 3.10
warn_return_any = True
warn_unused_configs = True
disallow_untyped_defs = False  # Começa False, mudar para True na FASE 1
ignore_missing_imports = True

[mypy-esocial.*]
disallow_untyped_defs = True

[mypy-setup]
disallow_untyped_defs = False
```

### Passo 0.4: Configurar Linter

**Arquivo: `pyproject.toml`**
```toml
[tool.ruff]
line-length = 88
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "D", "UP"]
ignore = ["D100", "D104"]  # Ignorar docstring em módulos e pacotes

[tool.ruff.lint.per-file-ignores]
"esocial/tests/*" = ["D"]  # Sem exigência de docstring em testes

[tool.black]
line-length = 88
target-version = ['py310']

[tool.isort]
profile = "black"
line_length = 88
```

### Passo 0.5: Setup do GitHub Actions

**Arquivo: `.github/workflows/ci.yml`**
```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]

    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -e ".[dev]"
    
    - name: Lint with ruff
      run: ruff check esocial/
    
    - name: Check formatting with black
      run: black --check esocial/
    
    - name: Type check with mypy
      run: mypy esocial/
    
    - name: Test with pytest
      run: pytest --cov=esocial --cov-report=xml
    
    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
```

---

## 🏗️ FASE 1: Fundações Sólidas (Semanas 1-2)

### Passo 1.1: Criar Models com Pydantic

**Arquivo: `esocial/models.py`**
```python
"""Pydantic models for data validation."""
from pydantic import BaseModel, Field, validator
from typing import Optional, Literal
from pathlib import Path


class EmployerID(BaseModel):
    """Identificação do empregador."""
    tpInsc: Literal[1, 2] = Field(
        ..., 
        description="1=CNPJ, 2=CPF"
    )
    nrInsc: str = Field(
        ..., 
        min_length=11, 
        max_length=14,
        description="Número de inscrição (CNPJ ou CPF)"
    )
    use_full: bool = Field(
        default=False,
        description="Usar número completo (sem corte para CNPJ)"
    )

    @validator('nrInsc')
    def validate_document_length(cls, v, values):
        """Valida tamanho do documento."""
        tp_insc = values.get('tpInsc')
        
        if tp_insc == 1 and len(v) != 14:
            raise ValueError(f'CNPJ deve ter 14 dígitos, got {len(v)}')
        if tp_insc == 2 and len(v) != 11:
            raise ValueError(f'CPF deve ter 11 dígitos, got {len(v)}')
        
        # Validação de apenas números
        if not v.isdigit():
            raise ValueError('Documento deve conter apenas números')
        
        return v

    class Config:
        extra = 'forbid'
        schema_extra = {
            "example": {
                "tpInsc": 1,
                "nrInsc": "12345678000199"
            }
        }


class WSClientConfig(BaseModel):
    """Configuração do cliente eSocial."""
    pfx_file: Optional[Path] = Field(
        None, 
        description="Caminho para arquivo de certificado PFX"
    )
    pfx_passw: Optional[str] = Field(
        None, 
        description="Senha do certificado",
        min_length=1
    )
    pkcs12_data_dict: Optional[dict] = Field(
        None, 
        description="Dados do certificado já carregados"
    )
    employer_id: EmployerID
    sender_id: Optional[EmployerID] = None
    ca_file: Optional[Path] = None
    target: Literal['tests', 'production', 1, 2] = 'tests'
    esocial_version: str = 'S-1.0'
    enable_persistence: bool = True
    storage_path: str = "./esocial_storage"

    @validator('pfx_passw')
    def password_not_empty(cls, v):
        if v is not None and not v.strip():
            raise ValueError('Senha não pode ser vazia')
        return v

    class Config:
        arbitrary_types_allowed = True
        extra = 'forbid'
```

**Teste: `esocial/tests/test_models.py`**
```python
"""Tests for Pydantic models."""
import pytest
from pydantic import ValidationError
from esocial.models import EmployerID, WSClientConfig


class TestEmployerID:
    def test_valid_cnpj(self):
        emp = EmployerID(tpInsc=1, nrInsc='12345678000199')
        assert emp.tpInsc == 1
        assert emp.nrInsc == '12345678000199'

    def test_valid_cpf(self):
        emp = EmployerID(tpInsc=2, nrInsc='12345678901')
        assert emp.tpInsc == 2
        assert emp.nrInsc == '12345678901'

    def test_invalid_cnpj_length(self):
        with pytest.raises(ValidationError) as exc_info:
            EmployerID(tpInsc=1, nrInsc='1234567800019')  # 13 digits
        assert 'CNPJ deve ter 14 dígitos' in str(exc_info.value)

    def test_invalid_cpf_length(self):
        with pytest.raises(ValidationError) as exc_info:
            EmployerID(tpInsc=2, nrInsc='1234567890')  # 10 digits
        assert 'CPF deve ter 11 dígitos' in str(exc_info.value)

    def test_non_numeric_document(self):
        with pytest.raises(ValidationError) as exc_info:
            EmployerID(tpInsc=1, nrInsc='1234567800019A')
        assert 'apenas números' in str(exc_info.value)


class TestWSClientConfig:
    def test_minimal_config(self):
        config = WSClientConfig(
            employer_id={'tpInsc': 1, 'nrInsc': '12345678000199'}
        )
        assert config.target == 'tests'
        assert config.enable_persistence is True

    def test_full_config(self):
        config = WSClientConfig(
            pfx_file='/path/to/cert.pfx',
            pfx_passw='secret123',
            employer_id={'tpInsc': 1, 'nrInsc': '12345678000199'},
            target='production'
        )
        assert config.pfx_file.name == 'cert.pfx'
        assert config.target == 'production'

    def test_empty_password_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            WSClientConfig(
                pfx_file='/path/to/cert.pfx',
                pfx_passw='',
                employer_id={'tpInsc': 1, 'nrInsc': '12345678000199'}
            )
        assert 'Senha não pode ser vazia' in str(exc_info.value)
```

### Passo 1.2: Adicionar Type Hints no client.py

**Arquivo: `esocial/client.py`** (trechos principais)
```python
"""eSocial Web Services Client."""
from typing import Optional, Dict, Any, List, Tuple, Union
from pathlib import Path
from lxml import etree
import datetime

from esocial.models import EmployerID, WSClientConfig


class WSClient(object):
    """Cliente para comunicação com webservices do eSocial."""

    def __init__(
        self,
        pkcs12_data_dict: Optional[Dict[str, Any]] = None,
        pfx_file: Optional[Union[str, Path]] = None,
        pfx_passw: Optional[str] = None,
        employer_id: Optional[Dict[str, Any]] = None,
        sender_id: Optional[Dict[str, Any]] = None,
        ca_file: Optional[Union[str, Path]] = None,
        target: str = 'tests',
        esocial_version: str = 'S-1.0',
        enable_persistence: bool = True,
        storage_path: str = "./esocial_storage",
    ):
        """Inicializa o cliente eSocial.
        
        Args:
            pkcs12_data_dict: Dados do certificado já carregados
            pfx_file: Caminho para arquivo de certificado PFX
            pfx_passw: Senha do certificado
            employer_id: Identificação do empregador
            sender_id: Identificação do transmissor (opcional)
            ca_file: Arquivo CA bundle para validação SSL
            target: Ambiente ('tests' ou 'production')
            esocial_version: Versão do layout eSocial
            enable_persistence: Habilitar persistência de estado
            storage_path: Caminho para armazenamento persistente
        """
        # Implementation...
        
    def add_event(
        self, 
        event: etree._ElementTree, 
        gen_event_id: bool = False,
        sign_event: bool = True
    ) -> Tuple[str, etree._ElementTree]:
        """Adiciona evento ao lote.
        
        Args:
            event: Árvore XML do evento
            gen_event_id: Gerar ID automático para o evento
            sign_event: Assinar o evento
            
        Returns:
            Tupla (event_id, evento_assinado)
            
        Raises:
            ValueError: Se event não for ElementTree
            Exception: Se faltar configuração necessária
        """
        if not isinstance(event, etree._ElementTree):
            raise ValueError('Not an ElementTree instance!')
            
        # Implementation...
        
    def send(
        self, 
        group_id: int = 1, 
        clear_batch: bool = True
    ) -> Tuple[Any, etree._Element]:
        """Envia lote de eventos para o eSocial.
        
        Args:
            group_id: ID do grupo de eventos (1-5 conforme eSocial)
            clear_batch: Limpar batch após envio
            
        Returns:
            Tupla (resultado, XML_do_lote)
        """
        # Implementation...
        
    def retrieve(self, protocol_number: str) -> Any:
        """Consulta resultado de processamento de lote.
        
        Args:
            protocol_number: Número do protocolo de envio
            
        Returns:
            Resultado da consulta
        """
        # Implementation...
```

### Passo 1.3: Implementar Context Managers

**No arquivo `esocial/client.py`:**
```python
class WSClient(object):
    # ... existing code ...
    
    def __enter__(self) -> 'WSClient':
        """Context manager entry."""
        return self
    
    def __exit__(
        self, 
        exc_type: Optional[type], 
        exc_val: Optional[Exception], 
        exc_tb: Optional[Any]
    ) -> bool:
        """Context manager exit with cleanup.
        
        Returns:
            False para propagar exceções
        """
        self.cleanup()
        return False  # Não suprime exceções
    
    def cleanup(self) -> None:
        """Libera recursos (sessões HTTP, cache, etc.)."""
        struct_logger.info("client_cleanup_start")
        
        # Fechar sessões HTTP se existirem
        if hasattr(self, '_session'):
            try:
                self._session.close()
                struct_logger.info("http_session_closed")
            except Exception as e:
                struct_logger.warning("error_closing_session", error=str(e))
        
        # Limpar batch pendente
        if self.batch:
            struct_logger.warning(
                "cleanup_with_pending_batch", 
                batch_size=len(self.batch)
            )
            self.clear_batch()
        
        struct_logger.info("client_cleanup_complete")
```

**Exemplo de uso:**
```python
# Antes (anti-pattern)
ws = WSClient(...)
try:
    result = ws.send()
finally:
    del ws  # Não garante cleanup adequado

# Depois (Pythonic)
with WSClient(...) as ws:
    result = ws.send()
# Cleanup automático e garantido

# Ou com tratamento de erro explícito
with WSClient(...) as ws:
    try:
        result = ws.send()
    except Exception as e:
        logger.error(f"Send failed: {e}")
        # Cleanup ainda será executado
```

### Passo 1.4: Logging com Correlation IDs

**Arquivo: `esocial/logging.py`** (NOVO)
```python
"""Logging utilities with correlation IDs."""
import uuid
from contextvars import ContextVar
from typing import Optional
import structlog

# Context variable for request ID
request_id_var: ContextVar[Optional[str]] = ContextVar(
    'request_id', 
    default=None
)


def generate_request_id() -> str:
    """Gera um ID único para correlacionar logs."""
    return str(uuid.uuid4())[:8]


class RequestContextManager:
    """Gerencia contexto de logging para uma requisição."""
    
    def __init__(self, request_id: Optional[str] = None):
        self.request_id = request_id or generate_request_id()
        self._token = None
        
    def __enter__(self) -> str:
        self._token = request_id_var.set(self.request_id)
        return self.request_id
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._token:
            request_id_var.reset(self._token)


def get_request_id() -> Optional[str]:
    """Retorna o request ID do contexto atual."""
    return request_id_var.get()


# Configurar structlog com correlation ID
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)
```

**Uso no client.py:**
```python
from esocial.logging import RequestContextManager, get_request_id

class WSClient:
    def send(self, group_id: int = 1, clear_batch: bool = True):
        with RequestContextManager() as request_id:
            struct_logger.info(
                "batch_send_start",
                request_id=request_id,
                group_id=group_id,
                batch_size=len(self.batch)
            )
            
            try:
                # ... implementation ...
                
                struct_logger.info(
                    "batch_send_success",
                    request_id=request_id,
                    protocol=result.protocolo
                )
                return result
                
            except Exception as e:
                struct_logger.error(
                    "batch_send_failed",
                    request_id=request_id,
                    error=str(e),
                    exc_info=True
                )
                raise
```

---

## ⚡ FASE 2: Resiliência Enterprise (Semanas 3-4)

### Passo 2.1: Circuit Breaker

**Arquivo: `esocial/circuit_breaker.py`** (NOVO)
```python
"""Circuit Breaker pattern implementation."""
from enum import Enum
from datetime import datetime, timedelta
from typing import Callable, Any, Optional
import logging
import structlog

logger = logging.getLogger(__name__)
struct_logger = structlog.get_logger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"      # Operação normal
    OPEN = "open"          # Falhando, não tentar
    HALF_OPEN = "half_open"  # Testando recuperação


class CircuitBreakerError(Exception):
    """Erro quando circuit breaker está aberto."""
    pass


class CircuitBreaker:
    """Implementa padrão Circuit Breaker."""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 3,
    ):
        """
        Args:
            failure_threshold: Falhas antes de abrir o circuito
            recovery_timeout: Segundos antes de tentar recuperação
            half_open_max_calls: Máximo de tentativas em half-open
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.half_open_calls = 0
        
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Executa função com proteção do circuit breaker."""
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._enter_half_open()
            else:
                struct_logger.warning(
                    "circuit_breaker_open",
                    service="esocial_webservice",
                    retry_after=self._time_until_retry()
                )
                raise CircuitBreakerError(
                    "Circuit breaker is OPEN. Service unavailable."
                )
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _should_attempt_reset(self) -> bool:
        """Verifica se já passou o timeout de recuperação."""
        if not self.last_failure_time:
            return True
            
        elapsed = datetime.now() - self.last_failure_time
        return elapsed.total_seconds() >= self.recovery_timeout
    
    def _time_until_retry(self) -> float:
        """Segundos restantes até próxima tentativa."""
        if not self.last_failure_time:
            return 0
            
        elapsed = (datetime.now() - self.last_failure_time).total_seconds()
        return max(0, self.recovery_timeout - elapsed)
    
    def _enter_half_open(self) -> None:
        """Transita para estado half-open."""
        self.state = CircuitState.HALF_OPEN
        self.half_open_calls = 0
        struct_logger.info("circuit_breaker_half_open")
    
    def _on_success(self) -> None:
        """Trata chamada bem-sucedida."""
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_calls += 1
            if self.half_open_calls >= self.half_open_max_calls:
                self._reset()
        else:
            self.failure_count = 0
    
    def _on_failure(self) -> None:
        """Trata chamada falha."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.state == CircuitState.HALF_OPEN:
            self._enter_open()
        elif self.failure_count >= self.failure_threshold:
            self._enter_open()
    
    def _enter_open(self) -> None:
        """Transita para estado open."""
        self.state = CircuitState.OPEN
        struct_logger.warning(
            "circuit_breaker_opened",
            failure_count=self.failure_count,
            recovery_timeout=self.recovery_timeout
        )
    
    def _reset(self) -> None:
        """Reseta para estado closed."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        struct_logger.info("circuit_breaker_reset")


# Decorator para fácil aplicação
def circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: int = 60
):
    """Decorator para aplicar circuit breaker."""
    breaker = CircuitBreaker(failure_threshold, recovery_timeout)
    
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            return breaker.call(func, *args, **kwargs)
        return wrapper
    return decorator
```

**Uso no client.py:**
```python
from esocial.circuit_breaker import CircuitBreaker

class WSClient:
    def __init__(self, ...):
        # ... existing init ...
        
        # Inicializa circuit breaker para operações críticas
        self._send_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60
        )
        self._retrieve_breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=30
        )
    
    def send(self, group_id: int = 1, clear_batch: bool = True):
        """Envia lote com circuit breaker."""
        return self._send_breaker.call(
            self._send_internal, 
            group_id, 
            clear_batch
        )
    
    def _send_internal(self, group_id: int, clear_batch: bool):
        """Implementação interna do send (sem circuit breaker)."""
        # ... existing implementation ...
    
    def retrieve(self, protocol_number: str):
        """Consulta com circuit breaker."""
        return self._retrieve_breaker.call(
            self._retrieve_internal,
            protocol_number
        )
    
    def _retrieve_internal(self, protocol_number: str):
        """Implementação interna do retrieve."""
        # ... existing implementation ...
```

### Passo 2.2: Rate Limiting

**Arquivo: `esocial/rate_limiter.py`** (NOVO)
```python
"""Rate limiting implementations."""
import asyncio
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)


class TokenBucketLimiter:
    """Rate limiter baseado em Token Bucket algorithm."""
    
    def __init__(
        self,
        max_requests: int = 100,
        time_window: int = 60,  # segundos
    ):
        """
        Args:
            max_requests: Máximo de requisições por janela
            time_window: Janela de tempo em segundos
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.tokens: deque = deque()
        
    async def acquire(self, blocking: bool = True) -> bool:
        """
        Adquire permissão para fazer requisição.
        
        Args:
            blocking: Se True, espera até conseguir token
            
        Returns:
            True se conseguiu token, False se non-blocking e sem tokens
        """
        while True:
            now = datetime.now()
            
            # Remove tokens expirados
            while (
                self.tokens and 
                now - self.tokens[0] > timedelta(seconds=self.time_window)
            ):
                self.tokens.popleft()
            
            if len(self.tokens) < self.max_requests:
                # Token disponível
                self.tokens.append(now)
                logger.debug(
                    "rate_limit_token_acquired",
                    tokens_used=len(self.tokens),
                    tokens_available=self.max_requests - len(self.tokens)
                )
                return True
            
            if not blocking:
                logger.warning("rate_limit_exceeded_non_blocking")
                return False
            
            # Calcula tempo de espera
            oldest_token = self.tokens[0]
            wait_time = (
                oldest_token + timedelta(seconds=self.time_window) - now
            ).total_seconds()
            
            if wait_time > 0:
                logger.info(
                    "rate_limit_waiting",
                    wait_seconds=wait_time
                )
                await asyncio.sleep(wait_time)
    
    def acquire_sync(self, blocking: bool = True) -> bool:
        """Versão síncrona do acquire."""
        # Implementação similar mas sem asyncio
        # Para uso em código síncrono
        now = datetime.now()
        
        while self.tokens and now - self.tokens[0] > timedelta(seconds=self.time_window):
            self.tokens.popleft()
        
        if len(self.tokens) < self.max_requests:
            self.tokens.append(now)
            return True
        
        return False
    
    def get_status(self) -> dict:
        """Retorna status atual do rate limiter."""
        now = datetime.now()
        active_tokens = sum(
            1 for t in self.tokens 
            if now - t <= timedelta(seconds=self.time_window)
        )
        
        return {
            'tokens_used': active_tokens,
            'tokens_available': self.max_requests - active_tokens,
            'max_requests': self.max_requests,
            'time_window': self.time_window,
        }
```

**Uso no client.py:**
```python
from esocial.rate_limiter import TokenBucketLimiter

class WSClient:
    def __init__(self, ...):
        # ... existing init ...
        
        # Rate limiting para evitar bloqueios do eSocial
        self._rate_limiter = TokenBucketLimiter(
            max_requests=100,  # Ajustar conforme limites do eSocial
            time_window=60     # 100 requisições por minuto
        )
    
    async def send_async(self, group_id: int = 1, clear_batch: bool = True):
        """Envio assíncrono com rate limiting."""
        await self._rate_limiter.acquire()
        
        struct_logger.info(
            "rate_limit_passed",
            status=self._rate_limiter.get_status()
        )
        
        # Proceed with send...
        return await self._send_internal(group_id, clear_batch)
```

### Passo 2.3: DLQ Avançada

(Similar ao que já existe, mas com melhorias de prioridade e agendamento)

### Passo 2.4: Persistência Transacional

(Migrar de JSON files para SQLite com transações)

---

## 🚀 FASE 3: Performance & Escalabilidade (Semanas 5-6)

### Passo 3.1: Cliente Assíncrono

**Arquivo: `esocial/async_client.py`** (NOVO)
```python
"""Async client for high-throughput operations."""
import asyncio
import httpx
from typing import Optional, List, Dict, Any, AsyncIterator
from lxml import etree
import structlog

from esocial.client import WSClient
from esocial import xml

logger = structlog.get_logger(__name__)


class AsyncWSClient:
    """Cliente assíncrono para operações de alto volume."""
    
    def __init__(
        self,
        cert_data: Dict[str, Any],
        employer_id: Dict[str, Any],
        sender_id: Optional[Dict[str, Any]] = None,
        max_concurrent: int = 10,
        timeout: float = 30.0,
        target: str = 'tests',
        **kwargs
    ):
        """
        Args:
            cert_data: Dados do certificado
            employer_id: Identificação do empregador
            sender_id: Identificação do transmissor
            max_concurrent: Máximo de requisições concorrentes
            timeout: Timeout em segundos
            target: Ambiente (tests/production)
        """
        self.cert_data = cert_data
        self.employer_id = employer_id
        self.sender_id = sender_id or employer_id
        self.target = target
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.timeout = httpx.Timeout(timeout)
        self._client: Optional[httpx.AsyncClient] = None
        
    async def __aenter__(self) -> 'AsyncWSClient':
        await self._initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
    
    async def _initialize(self) -> None:
        """Inicializa cliente HTTP com pooling."""
        limits = httpx.Limits(
            max_keepalive_connections=20,
            max_connections=50
        )
        
        self._client = httpx.AsyncClient(
            cert=(
                self.cert_data['cert_str'], 
                self.cert_data['key_str']
            ),
            verify=self.ca_bundle,
            timeout=self.timeout,
            limits=limits,
        )
        
        logger.info(
            "async_client_initialized",
            max_connections=limits.max_connections
        )
    
    async def close(self) -> None:
        """Fecha conexões HTTP."""
        if self._client:
            await self._client.aclose()
            logger.info("async_client_closed")
    
    async def send_batch(
        self,
        events: List[etree._ElementTree],
        group_id: int = 1
    ) -> Dict[str, Any]:
        """Envia lote de eventos."""
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
        batches: List[tuple]
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Envia múltiplos lotes em paralelo.
        
        Args:
            batches: Lista de tuplas (events, group_id)
            
        Yields:
            Resultados na ordem de conclusão
        """
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
    
    def _make_send_envelop(
        self, 
        group_id: int, 
        events: List[etree._ElementTree]
    ) -> etree._Element:
        """Cria envelope de envio de lote."""
        # Similar ao método do WSClient síncrono
        pass
    
    def _parse_response(self, content: bytes) -> Dict[str, Any]:
        """Parse da resposta XML."""
        # Implementação de parse
        pass
```

### Passo 3.2: Cache de Certificados e Schemas

**Arquivo: `esocial/cache.py`** (NOVO)

### Passo 3.3: Connection Pooling Aprimorado

---

## 📊 FASE 4: Observabilidade Avançada (Semanas 7-8)

### Passo 4.1: Distributed Tracing

**Arquivo: `esocial/tracing.py`** (NOVO)

### Passo 4.2: Health Checks

**Arquivo: `esocial/health.py`** (NOVO)

### Passo 4.3: Sistema de Alertas

**Arquivo: `esocial/alerts.py`** (NOVO)

---

## 🔒 FASE 5: Segurança Hardening (Semanas 9-10)

### Passo 5.1: Secrets Management

**Arquivo: `esocial/secrets.py`** (NOVO)

### Passo 5.2: Audit Logging

**Arquivo: `esocial/audit.py`** (NOVO)

### Passo 5.3: Certificate Rotation

**Arquivo: `esocial/cert_rotation.py`** (NOVO)

---

## 📚 FASE 6: Developer Experience (Semanas 11-12)

### Passo 6.1: Documentação Completa

**Setup do MkDocs:**
```bash
pip install mkdocs mkdocs-material mkdocstrings
mkdocs new docs/
```

### Passo 6.2: CLI

**Arquivo: `esocial/cli.py`** (NOVO)

### Passo 6.3: Exemplos Enterprise

**Pasta: `examples/`** (NOVA)

---

## ✅ Checklist de Conclusão

### Fase 1
- [ ] Models Pydantic criados e testados
- [ ] Type hints em todo código público
- [ ] Context managers implementados
- [ ] Logging com correlation IDs
- [ ] mypy configurado e passando

### Fase 2
- [ ] Circuit breaker implementado
- [ ] Rate limiting funcional
- [ ] DLQ avançada com prioridades
- [ ] Persistência transacional

### Fase 3
- [ ] AsyncWSClient operacional
- [ ] Cache de certificados
- [ ] Connection pooling otimizado

### Fase 4
- [ ] Tracing distribuído configurado
- [ ] Health checks implementados
- [ ] Sistema de alertas funcional

### Fase 5
- [ ] Integração com Secrets Manager
- [ ] Audit logging ativo
- [ ] Certificate rotation automático

### Fase 6
- [ ] Documentação completa publicada
- [ ] CLI funcional
- [ ] Exemplos enterprise disponíveis

---

## 🎯 Próximos Passos

1. **Comece pela Semana 0**: Setup do ambiente
2. **Execute testes frequentemente**: `pytest -xvs`
3. **Mantenha compatibilidade**: Não quebre a API existente
4. **Documente mudanças**: Atualize CHANGELOG.md
5. **Versionamento semântico**: Siga semver.org

**Boa implementação! 🚀**
