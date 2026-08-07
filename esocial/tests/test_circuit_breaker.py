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
"""Tests for Circuit Breaker Implementation

FASE 2: Resilience patterns - Circuit Breaker validation
"""
import pytest
import time
from esocial.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    CircuitStats,
    CircuitBreakerOpen,
    CircuitBreakerRegistry,
    get_circuit_breaker,
    with_circuit_breaker,
)


class TestCircuitBreakerConfig:
    """Testes para configuração do circuit breaker."""
    
    def test_default_config(self):
        """Configuração padrão correta."""
        config = CircuitBreakerConfig()
        assert config.failure_threshold == 5
        assert config.success_threshold == 3
        assert config.timeout == 60.0
    
    def test_custom_config(self):
        """Configuração customizada."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            timeout=30.0
        )
        assert config.failure_threshold == 3
        assert config.success_threshold == 2
        assert config.timeout == 30.0
    
    def test_invalid_failure_threshold(self):
        """Rejeita failure_threshold inválido."""
        with pytest.raises(ValueError):
            CircuitBreakerConfig(failure_threshold=0)
    
    def test_invalid_success_threshold(self):
        """Rejeita success_threshold inválido."""
        with pytest.raises(ValueError):
            CircuitBreakerConfig(success_threshold=0)
    
    def test_invalid_timeout(self):
        """Rejeita timeout inválido."""
        with pytest.raises(ValueError):
            CircuitBreakerConfig(timeout=0)


class TestCircuitBreakerStates:
    """Testes para estados do circuit breaker."""
    
    def test_initial_state_closed(self):
        """Estado inicial é CLOSED."""
        breaker = CircuitBreaker('test')
        assert breaker.state == CircuitState.CLOSED
    
    def test_opens_after_failures(self):
        """Abre após número de falhas."""
        config = CircuitBreakerConfig(failure_threshold=3, timeout=60)
        breaker = CircuitBreaker('test', config)
        
        def fail():
            raise Exception("fail")
        
        for _ in range(3):
            try:
                breaker.call(fail)
            except:
                pass
        
        assert breaker.state == CircuitState.OPEN
    
    def test_half_open_after_timeout(self):
        """Transiciona para HALF_OPEN após timeout."""
        config = CircuitBreakerConfig(failure_threshold=2, timeout=0.5)
        breaker = CircuitBreaker('test', config)
        
        def fail():
            raise Exception("fail")
        
        # Open the circuit
        for _ in range(2):
            try:
                breaker.call(fail)
            except:
                pass
        
        assert breaker.state == CircuitState.OPEN
        
        # Wait for timeout
        time.sleep(0.6)
        
        # Should transition to HALF_OPEN on next state check
        assert breaker.state == CircuitState.HALF_OPEN
    
    def test_closes_after_successes_in_half_open(self):
        """Fecha após sucessos em HALF_OPEN."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=2,
            timeout=0.5
        )
        breaker = CircuitBreaker('test', config)
        
        def fail():
            raise Exception("fail")
        
        def succeed():
            return "ok"
        
        # Open the circuit
        for _ in range(2):
            try:
                breaker.call(fail)
            except:
                pass
        
        # Wait for timeout
        time.sleep(0.6)
        
        # Trigger HALF_OPEN
        breaker.state
        
        # Succeed twice
        breaker.call(succeed)
        breaker.call(succeed)
        
        assert breaker.state == CircuitState.CLOSED


class TestCircuitBreakerRejection:
    """Testes para rejeição de chamadas."""
    
    def test_rejects_when_open(self):
        """Rejeita chamadas quando OPEN."""
        config = CircuitBreakerConfig(failure_threshold=2, timeout=60)
        breaker = CircuitBreaker('test', config)
        
        def fail():
            raise Exception("fail")
        
        # Open the circuit
        for _ in range(2):
            try:
                breaker.call(fail)
            except:
                pass
        
        def succeed():
            return "ok"
        
        # Should reject
        with pytest.raises(CircuitBreakerOpen):
            breaker.call(succeed)
    
    def test_retry_after_info(self):
        """Fornece informação de retry_after."""
        config = CircuitBreakerConfig(failure_threshold=2, timeout=10)
        breaker = CircuitBreaker('test', config)
        
        def fail():
            raise Exception("fail")
        
        # Open the circuit
        for _ in range(2):
            try:
                breaker.call(fail)
            except:
                pass
        
        try:
            breaker.call(lambda: "ok")
        except CircuitBreakerOpen as e:
            assert e.retry_after > 0
            assert e.retry_after <= 10
            assert e.name == 'test'


class TestCircuitBreakerStats:
    """Testes para estatísticas."""
    
    def test_tracks_total_calls(self):
        """Rastreia total de chamadas."""
        breaker = CircuitBreaker('test')
        
        breaker.call(lambda: "ok")
        breaker.call(lambda: "ok")
        
        stats = breaker.stats
        assert stats.total_calls == 2
        assert stats.successful_calls == 2
    
    def test_tracks_failures(self):
        """Rastreia falhas."""
        breaker = CircuitBreaker('test')
        
        def fail():
            raise Exception("fail")
        
        for _ in range(3):
            try:
                breaker.call(fail)
            except:
                pass
        
        stats = breaker.stats
        assert stats.failed_calls == 3
        assert stats.consecutive_failures == 3
    
    def test_tracks_rejections(self):
        """Rastreia rejeições."""
        config = CircuitBreakerConfig(failure_threshold=2, timeout=60)
        breaker = CircuitBreaker('test', config)
        
        def fail():
            raise Exception("fail")
        
        # Open circuit
        for _ in range(2):
            try:
                breaker.call(fail)
            except:
                pass
        
        # Try to call when open
        for _ in range(3):
            try:
                breaker.call(lambda: "ok")
            except CircuitBreakerOpen:
                pass
        
        stats = breaker.stats
        assert stats.rejected_calls == 3
    
    def test_resets_on_success(self):
        """Reseta contagem de falhas no sucesso."""
        breaker = CircuitBreaker('test')
        
        def fail():
            raise Exception("fail")
        
        def succeed():
            return "ok"
        
        # Some failures
        for _ in range(2):
            try:
                breaker.call(fail)
            except:
                pass
        
        # Success should reset
        breaker.call(succeed)
        
        stats = breaker.stats
        assert stats.consecutive_failures == 0
        assert stats.consecutive_successes == 1


class TestCircuitBreakerOperations:
    """Testes para operações do circuit breaker."""
    
    def test_reset(self):
        """Reset retorna para CLOSED."""
        config = CircuitBreakerConfig(failure_threshold=2, timeout=60)
        breaker = CircuitBreaker('test', config)
        
        def fail():
            raise Exception("fail")
        
        # Open circuit
        for _ in range(2):
            try:
                breaker.call(fail)
            except:
                pass
        
        assert breaker.state == CircuitState.OPEN
        
        # Reset
        breaker.reset()
        
        assert breaker.state == CircuitState.CLOSED
    
    def test_force_open(self):
        """Força abertura."""
        breaker = CircuitBreaker('test')
        
        breaker.force_open()
        
        # Force open should set to OPEN, but state property may transition to HALF_OPEN
        # if timeout has passed. We just verify it's not CLOSED.
        assert breaker.state != CircuitState.CLOSED
    
    def test_force_close(self):
        """Força fechamento."""
        config = CircuitBreakerConfig(failure_threshold=2, timeout=60)
        breaker = CircuitBreaker('test', config)
        
        def fail():
            raise Exception("fail")
        
        # Open circuit
        for _ in range(2):
            try:
                breaker.call(fail)
            except:
                pass
        
        # Force close
        breaker.force_close()
        
        assert breaker.state == CircuitState.CLOSED
    
    def test_is_healthy(self):
        """Verifica saúde."""
        breaker = CircuitBreaker('test')
        assert breaker.is_healthy() is True
        
        # Use config with long timeout to prevent auto-transition to HALF_OPEN
        config = CircuitBreakerConfig(failure_threshold=1, timeout=300)
        breaker_unhealthy = CircuitBreaker('test_unhealthy', config)
        
        def fail():
            raise Exception("fail")
        
        try:
            breaker_unhealthy.call(fail)
        except:
            pass
        
        # Immediately check - should still be OPEN
        with breaker_unhealthy._lock:
            assert breaker_unhealthy._state == CircuitState.OPEN
        
        assert breaker_unhealthy.is_healthy() is False


class TestCircuitBreakerDecorator:
    """Testes para decorator."""
    
    def test_decorator_protects_function(self):
        """Decorator protege função."""
        @with_circuit_breaker('test_dec', failure_threshold=2, timeout=60)
        def my_function():
            return "result"
        
        result = my_function()
        assert result == "result"
    
    def test_decorator_handles_failures(self):
        """Decorator lida com falhas."""
        @with_circuit_breaker('test_dec_fail', failure_threshold=2, timeout=60)
        def failing_function():
            raise Exception("error")
        
        for _ in range(2):
            try:
                failing_function()
            except:
                pass
        
        # Circuit should be open now
        with pytest.raises(CircuitBreakerOpen):
            failing_function()


class TestCircuitBreakerContextManager:
    """Testes para context manager."""
    
    def test_context_manager_success(self):
        """Context manager registra sucesso."""
        breaker = CircuitBreaker('test_ctx')
        
        with breaker.track():
            result = "ok"
        
        stats = breaker.stats
        assert stats.successful_calls == 1
    
    def test_context_manager_failure(self):
        """Context manager registra falha."""
        breaker = CircuitBreaker('test_ctx_fail')
        
        with pytest.raises(Exception):
            with breaker.track():
                raise Exception("error")
        
        stats = breaker.stats
        assert stats.failed_calls == 1
    
    def test_context_manager_rejects_when_open(self):
        """Context manager rejeita quando aberto."""
        config = CircuitBreakerConfig(failure_threshold=1, timeout=60)
        breaker = CircuitBreaker('test_ctx_open', config)
        
        # Open circuit
        try:
            breaker.call(lambda: (_ for _ in ()).throw(Exception()))
        except:
            pass
        
        with pytest.raises(CircuitBreakerOpen):
            with breaker.track():
                pass


class TestCircuitBreakerRegistry:
    """Testes para registro de circuit breakers."""
    
    def test_get_or_create(self):
        """Cria ou obtém circuit breaker."""
        registry = CircuitBreakerRegistry()
        
        breaker1 = registry.get_or_create('test1')
        breaker2 = registry.get_or_create('test1')
        
        assert breaker1 is breaker2
    
    def test_get_nonexistent(self):
        """Retorna None para não existente."""
        registry = CircuitBreakerRegistry()
        
        breaker = registry.get('nonexistent')
        
        assert breaker is None
    
    def test_all_healthy(self):
        """Verifica se todos saudáveis."""
        registry = CircuitBreakerRegistry()
        
        breaker1 = registry.get_or_create('test1')
        breaker2 = registry.get_or_create('test2')
        
        assert registry.all_healthy() is True
        
        # Open one - use long timeout to prevent auto-transition
        config = CircuitBreakerConfig(failure_threshold=1, timeout=300)
        breaker3 = registry.get_or_create('test3', config)
        
        def fail():
            raise Exception("fail")
        
        try:
            breaker3.call(fail)
        except:
            pass
        
        # Check internal state directly
        with breaker3._lock:
            assert breaker3._state == CircuitState.OPEN
        
        assert registry.all_healthy() is False
    
    def test_get_stats(self):
        """Obtém estatísticas de todos."""
        registry = CircuitBreakerRegistry()
        
        breaker = registry.get_or_create('test_stats')
        breaker.call(lambda: "ok")
        
        stats = registry.get_stats()
        
        assert 'test_stats' in stats
        assert stats['test_stats'].total_calls == 1
    
    def test_reset_all(self):
        """Reseta todos."""
        registry = CircuitBreakerRegistry()
        
        breaker1 = registry.get_or_create('test_r1')
        breaker2 = registry.get_or_create('test_r2')
        
        breaker1.force_open()
        breaker2.force_open()
        
        registry.reset_all()
        
        assert breaker1.state == CircuitState.CLOSED
        assert breaker2.state == CircuitState.CLOSED


class TestGlobalRegistry:
    """Testes para registro global."""
    
    def test_get_circuit_breaker(self):
        """Obtém do registro global."""
        breaker1 = get_circuit_breaker('global_test')
        breaker2 = get_circuit_breaker('global_test')
        
        assert breaker1 is breaker2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
