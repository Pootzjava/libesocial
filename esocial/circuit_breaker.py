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
"""Circuit Breaker Pattern Implementation

FASE 2: Resilience patterns - Circuit Breaker for external service calls.
Prevents cascading failures when eSocial webservices are unavailable.
"""
import time
import logging
from enum import Enum
from typing import Optional, Callable, Any
from functools import wraps
from threading import Lock
from dataclasses import dataclass, field
import structlog

logger = logging.getLogger(__name__)
struct_logger = structlog.get_logger(__name__)


class CircuitState(Enum):
    """Estados do circuit breaker."""
    CLOSED = 'CLOSED'      # Normal operation, requests allowed
    OPEN = 'OPEN'          # Circuit tripped, requests blocked
    HALF_OPEN = 'HALF_OPEN'  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuração do circuit breaker."""
    failure_threshold: int = 5          # Number of failures before opening
    success_threshold: int = 3          # Number of successes before closing
    timeout: float = 60.0               # Seconds before trying half-open
    expected_exceptions: tuple = (Exception,)  # Exceptions that count as failures
    
    def __post_init__(self):
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if self.success_threshold < 1:
            raise ValueError("success_threshold must be >= 1")
        if self.timeout <= 0:
            raise ValueError("timeout must be > 0")


@dataclass
class CircuitStats:
    """Estatísticas do circuit breaker."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    state_changes: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0


class CircuitBreakerError(Exception):
    """Exceção lançada quando circuit breaker está aberto."""
    pass


class CircuitBreakerOpen(CircuitBreakerError):
    """Exceção específica para circuit breaker aberto."""
    def __init__(self, name: str, retry_after: float):
        self.name = name
        self.retry_after = retry_after
        super().__init__(
            f"Circuit breaker '{name}' is OPEN. Retry after {retry_after:.1f}s"
        )


class CircuitBreaker:
    """
    Circuit Breaker pattern implementation.
    
    Prevents cascading failures by stopping requests to failing services.
    
    States:
    - CLOSED: Normal operation, all requests allowed
    - OPEN: Service failing, requests blocked immediately
    - HALF_OPEN: Testing recovery, limited requests allowed
    
    Usage:
        breaker = CircuitBreaker('esocial_api', failure_threshold=5, timeout=60)
        
        @breaker
        def send_to_esocial(data):
            # ... implementation ...
            
        # Or manually:
        with breaker.track():
            send_to_esocial(data)
    """
    
    def __init__(
        self,
        name: str = 'default',
        config: Optional[CircuitBreakerConfig] = None,
    ):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._stats = CircuitStats()
        self._lock = Lock()
        self._last_failure_time: Optional[float] = None
        self._consecutive_failures: int = 0
        self._consecutive_successes: int = 0
        
        struct_logger.info(
            "circuit_breaker_initialized",
            name=name,
            failure_threshold=self.config.failure_threshold,
            timeout=self.config.timeout
        )
    
    @property
    def state(self) -> CircuitState:
        """Retorna estado atual, verificando timeout se OPEN."""
        with self._lock:
            if self._state == CircuitState.OPEN:
                if self._should_try_half_open():
                    self._transition_to(CircuitState.HALF_OPEN)
            return self._state
    
    @property
    def stats(self) -> CircuitStats:
        """Retorna estatísticas do circuit breaker."""
        with self._lock:
            return CircuitStats(
                total_calls=self._stats.total_calls,
                successful_calls=self._stats.successful_calls,
                failed_calls=self._stats.failed_calls,
                rejected_calls=self._stats.rejected_calls,
                last_failure_time=self._stats.last_failure_time,
                last_success_time=self._stats.last_success_time,
                state_changes=self._stats.state_changes,
                consecutive_failures=self._consecutive_failures,
                consecutive_successes=self._consecutive_successes,
            )
    
    def _should_try_half_open(self) -> bool:
        """Verifica se passou tempo suficiente para tentar recuperação."""
        if self._last_failure_time is None:
            return True
        elapsed = time.time() - self._last_failure_time
        return elapsed >= self.config.timeout
    
    def _transition_to(self, new_state: CircuitState) -> None:
        """Transiciona para novo estado."""
        old_state = self._state
        if old_state != new_state:
            self._state = new_state
            self._stats.state_changes += 1
            
            struct_logger.info(
                "circuit_breaker_state_change",
                name=self.name,
                old_state=old_state.value,
                new_state=new_state.value
            )
            
            # Reset counters on state change
            if new_state == CircuitState.HALF_OPEN:
                self._consecutive_successes = 0
            elif new_state == CircuitState.CLOSED:
                self._consecutive_failures = 0
                self._consecutive_successes = 0
            elif new_state == CircuitState.OPEN:
                self._consecutive_successes = 0
    
    def _record_success(self) -> None:
        """Registra sucesso de chamada."""
        with self._lock:
            self._stats.successful_calls += 1
            self._stats.last_success_time = time.time()
            self._consecutive_successes += 1
            self._consecutive_failures = 0
            
            current_state = self._state
            
            if current_state == CircuitState.HALF_OPEN:
                if self._consecutive_successes >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
            elif current_state == CircuitState.CLOSED:
                # Reset failure counter on success
                self._consecutive_failures = 0
    
    def _record_failure(self) -> None:
        """Registra falha de chamada."""
        with self._lock:
            self._stats.failed_calls += 1
            self._stats.last_failure_time = time.time()
            self._last_failure_time = time.time()
            self._consecutive_failures += 1
            self._consecutive_successes = 0
            
            current_state = self._state
            
            if current_state == CircuitState.HALF_OPEN:
                # Immediately open on any failure in half-open
                self._transition_to(CircuitState.OPEN)
            elif current_state == CircuitState.CLOSED:
                if self._consecutive_failures >= self.config.failure_threshold:
                    self._transition_to(CircuitState.OPEN)
    
    def _record_rejection(self) -> None:
        """Registra chamada rejeitada (circuit open)."""
        with self._lock:
            self._stats.rejected_calls += 1
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Executa função com proteção do circuit breaker.
        
        Args:
            func: Função a ser executada
            *args: Argumentos posicionais
            **kwargs: Argumentos nomeados
            
        Returns:
            Resultado da função
            
        Raises:
            CircuitBreakerOpen: Se circuit breaker estiver aberto
        """
        current_state = self.state
        self._stats.total_calls += 1
        
        if current_state == CircuitState.OPEN:
            self._record_rejection()
            retry_after = self.config.timeout - (time.time() - self._last_failure_time)
            raise CircuitBreakerOpen(self.name, max(0, retry_after))
        
        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result
        except self.config.expected_exceptions as e:
            self._record_failure()
            struct_logger.warning(
                "circuit_breaker_function_failed",
                name=self.name,
                error=str(e),
                consecutive_failures=self._consecutive_failures,
                state=self.state.value
            )
            raise
    
    def __call__(self, func: Callable) -> Callable:
        """Decorator para proteger funções."""
        @wraps(func)
        def wrapper(*args, **kwargs):
            return self.call(func, *args, **kwargs)
        return wrapper
    
    def track(self):
        """Context manager para rastrear operações."""
        return CircuitBreakerContext(self)
    
    def reset(self) -> None:
        """Reseta circuit breaker para estado inicial."""
        with self._lock:
            old_state = self._state
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._consecutive_successes = 0
            self._last_failure_time = None
            
            if old_state != CircuitState.CLOSED:
                self._stats.state_changes += 1
                
                struct_logger.info(
                    "circuit_breaker_reset",
                    name=self.name,
                    old_state=old_state.value
                )
    
    def force_open(self) -> None:
        """Força abertura do circuit breaker (manutenção)."""
        with self._lock:
            if self._state != CircuitState.OPEN:
                self._transition_to(CircuitState.OPEN)
    
    def force_close(self) -> None:
        """Força fechamento do circuit breaker (teste)."""
        with self._lock:
            if self._state != CircuitState.CLOSED:
                self._transition_to(CircuitState.CLOSED)
    
    def is_healthy(self) -> bool:
        """Verifica se circuit breaker está saudável."""
        return self.state != CircuitState.OPEN
    
    def get_retry_after(self) -> Optional[float]:
        """Retorna tempo até próxima tentativa (se OPEN)."""
        if self.state != CircuitState.OPEN or self._last_failure_time is None:
            return None
        elapsed = time.time() - self._last_failure_time
        return max(0, self.config.timeout - elapsed)


class CircuitBreakerContext:
    """Context manager para circuit breaker."""
    
    def __init__(self, breaker: CircuitBreaker):
        self.breaker = breaker
        self._exc_type = None
        self._exc_value = None
    
    def __enter__(self):
        if self.breaker.state == CircuitState.OPEN:
            self.breaker._record_rejection()
            retry_after = self.breaker.get_retry_after()
            raise CircuitBreakerOpen(self.breaker.name, retry_after or 0)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.breaker._record_success()
        elif issubclass(exc_type, self.breaker.config.expected_exceptions):
            self.breaker._record_failure()
            # Don't suppress exception
            return False
        return False


class CircuitBreakerRegistry:
    """Registro de circuit breakers por nome."""
    
    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = Lock()
    
    def get_or_create(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
    ) -> CircuitBreaker:
        """Obtém ou cria circuit breaker."""
        with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(name, config)
            return self._breakers[name]
    
    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Obtém circuit breaker por nome."""
        with self._lock:
            return self._breakers.get(name)
    
    def all_healthy(self) -> bool:
        """Verifica se todos circuit breakers estão saudáveis."""
        with self._lock:
            return all(b.is_healthy() for b in self._breakers.values())
    
    def get_stats(self) -> dict[str, CircuitStats]:
        """Retorna estatísticas de todos circuit breakers."""
        with self._lock:
            return {name: b.stats for name, b in self._breakers.items()}
    
    def reset_all(self) -> None:
        """Reseta todos circuit breakers."""
        with self._lock:
            for breaker in self._breakers.values():
                breaker.reset()


# Global registry for application-wide circuit breakers
global_registry = CircuitBreakerRegistry()


def get_circuit_breaker(
    name: str,
    config: Optional[CircuitBreakerConfig] = None,
) -> CircuitBreaker:
    """Obtém circuit breaker do registro global."""
    return global_registry.get_or_create(name, config)


def with_circuit_breaker(
    name: str = 'default',
    failure_threshold: int = 5,
    success_threshold: int = 3,
    timeout: float = 60.0,
    expected_exceptions: tuple = (Exception,),
):
    """
    Decorator factory para circuit breaker.
    
    Usage:
        @with_circuit_breaker('esocial_send', failure_threshold=3)
        def send_to_esocial(data):
            ...
    """
    config = CircuitBreakerConfig(
        failure_threshold=failure_threshold,
        success_threshold=success_threshold,
        timeout=timeout,
        expected_exceptions=expected_exceptions,
    )
    breaker = get_circuit_breaker(name, config)
    return breaker
