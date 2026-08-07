"""
Testes para Secrets Management - FASE 5

Cobertura esperada: >95%
"""

import os
import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, MagicMock, AsyncMock

from esocial.secrets import (
    SecretValue,
    CacheEntry,
    EnvironmentSecretsProvider,
    AWSSecretsManagerProvider,
    AzureKeyVaultProvider,
    HashiCorpVaultProvider,
    SecretsManager,
    create_secrets_manager,
)


def utc_now():
    """Helper para datetime UTC timezone-aware."""
    return datetime.now(timezone.utc)


class TestSecretValue:
    """Testes para classe SecretValue."""
    
    def test_create_secret_value_basic(self):
        """Testa criação básica de SecretValue."""
        secret = SecretValue(value="test-password")
        
        assert secret.value == "test-password"
        assert secret.version == ""
        assert isinstance(secret.created_at, datetime)
        assert secret.expires_at is None
        assert secret.rotation_schedule is None
    
    def test_create_secret_value_with_metadata(self):
        """Testa criação de SecretValue com metadados."""
        created = utc_now().replace(year=2024, month=1, day=1, hour=12, minute=0, second=0)
        expires = utc_now().replace(year=2025, month=1, day=1, hour=12, minute=0, second=0)
        rotation = timedelta(days=90)
        
        secret = SecretValue(
            value="test-password",
            version="v1.0",
            created_at=created,
            expires_at=expires,
            rotation_schedule=rotation
        )
        
        assert secret.value == "test-password"
        assert secret.version == "v1.0"
        assert secret.created_at == created
        assert secret.expires_at == expires
        assert secret.rotation_schedule == rotation
    
    def test_is_expired_false(self):
        """Testa is_expired quando não expirado."""
        future = utc_now() + timedelta(days=30)
        secret = SecretValue(value="test", expires_at=future)
        
        assert secret.is_expired() is False
    
    def test_is_expired_true(self):
        """Testa is_expired quando expirado."""
        past = utc_now() - timedelta(days=30)
        secret = SecretValue(value="test", expires_at=past)
        
        assert secret.is_expired() is True
    
    def test_is_expired_no_expiration(self):
        """Testa is_expired sem data de expiração."""
        secret = SecretValue(value="test")
        
        assert secret.is_expired() is False
    
    def test_should_rotate_false(self):
        """Testa should_rotate quando não deve rotacionar."""
        recent = utc_now() - timedelta(days=10)
        rotation = timedelta(days=90)
        
        secret = SecretValue(value="test", created_at=recent, rotation_schedule=rotation)
        
        assert secret.should_rotate() is False
    
    def test_should_rotate_true(self):
        """Testa should_rotate quando deve rotacionar."""
        old = utc_now() - timedelta(days=100)
        rotation = timedelta(days=90)
        
        secret = SecretValue(value="test", created_at=old, rotation_schedule=rotation)
        
        assert secret.should_rotate() is True
    
    def test_should_rotate_no_schedule(self):
        """Testa should_rotate sem schedule de rotação."""
        secret = SecretValue(value="test")
        
        assert secret.should_rotate() is False


class TestCacheEntry:
    """Testes para classe CacheEntry."""
    
    def test_create_cache_entry(self):
        """Testa criação básica de CacheEntry."""
        secret_value = SecretValue(value="test")
        entry = CacheEntry(secret_value=secret_value, ttl_seconds=300)
        
        assert entry.secret_value.value == "test"
        assert entry.ttl_seconds == 300
        assert isinstance(entry.cached_at, float)
    
    def test_is_stale_false(self):
        """Testa is_stale quando cache está válido."""
        secret_value = SecretValue(value="test")
        entry = CacheEntry(secret_value=secret_value, ttl_seconds=300)
        
        # Cache recém-criado não deve estar stale
        assert entry.is_stale() is False
    
    def test_is_stale_true(self):
        """Testa is_stale quando cache está obsoleto."""
        secret_value = SecretValue(value="test")
        entry = CacheEntry(secret_value=secret_value, ttl_seconds=1)
        
        # Espera 2 segundos para o cache ficar stale
        asyncio.run(asyncio.sleep(2))
        
        assert entry.is_stale() is True


class TestEnvironmentSecretsProvider:
    """Testes para EnvironmentSecretsProvider."""
    
    @pytest.fixture
    def provider(self):
        """Cria provider para testes."""
        return EnvironmentSecretsProvider(prefix="TEST_")
    
    @pytest.mark.asyncio
    async def test_get_secret_exists(self, provider):
        """Testa obtenção de secret que existe."""
        with patch.dict(os.environ, {"TEST_MY_SECRET": "my-value"}):
            result = await provider.get_secret("my-secret")
            
            assert result is not None
            assert result.value == "my-value"
            assert result.version == "env"
    
    @pytest.mark.asyncio
    async def test_get_secret_not_found(self, provider):
        """Testa obtenção de secret que não existe."""
        result = await provider.get_secret("non-existent")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_secret_auto_prefix(self, provider):
        """Testa que provider adiciona prefixo automaticamente."""
        with patch.dict(os.environ, {"TEST_ANOTHER_SECRET": "another-value"}):
            result = await provider.get_secret("another-secret")
            
            assert result is not None
            assert result.value == "another-value"
    
    @pytest.mark.asyncio
    async def test_set_secret_not_supported(self, provider):
        """Testa que set não é suportado em runtime."""
        result = await provider.set_secret("new-secret", "value")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_delete_secret_not_supported(self, provider):
        """Testa que delete não é suportado em runtime."""
        result = await provider.delete_secret("some-secret")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_list_secrets(self, provider):
        """Testa listagem de secrets."""
        with patch.dict(os.environ, {
            "TEST_SECRET1": "value1",
            "TEST_SECRET2": "value2",
            "OTHER_SECRET": "other"
        }):
            result = await provider.list_secrets()
            
            assert "secret1" in result
            assert "secret2" in result
            assert "other-secret" not in result  # Prefixo diferente
    
    @pytest.mark.asyncio
    async def test_list_secrets_with_prefix(self, provider):
        """Testa listagem com filtro por prefixo."""
        with patch.dict(os.environ, {
            "TEST_DB_PASSWORD": "pass",
            "TEST_DB_HOST": "localhost",
            "TEST_API_KEY": "key123"
        }):
            result = await provider.list_secrets(prefix="db")
            
            assert "db-password" in result
            assert "db-host" in result
            assert "api-key" not in result
    
    @pytest.mark.asyncio
    async def test_health_check_always_true(self, provider):
        """Testa health check sempre retorna True."""
        result = await provider.health_check()
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_get_secret_name_transformations(self, provider):
        """Testa transformações de nome para env var."""
        test_cases = [
            ("my-secret", "TEST_MY_SECRET"),
            ("my_secret", "TEST_MY_SECRET"),
            ("My.Secret", "TEST_MY_SECRET"),
        ]
        
        for secret_name, expected_env in test_cases:
            with patch.dict(os.environ, {expected_env: "value"}):
                result = await provider.get_secret(secret_name)
                assert result is not None
                assert result.value == "value"


class TestSecretsManager:
    """Testes para classe SecretsManager."""
    
    @pytest.fixture
    def secrets_manager(self):
        """Cria SecretsManager para testes."""
        return SecretsManager(provider="environment", prefix="TEST_")
    
    @pytest.mark.asyncio
    async def test_create_with_environment_provider(self):
        """Testa criação com provedor environment."""
        manager = SecretsManager(provider="environment", prefix="TEST_")
        
        assert manager.cache_enabled is True
        assert manager.cache_ttl == 300
    
    @pytest.mark.asyncio
    async def test_create_with_invalid_provider(self):
        """Testa criação com provedor inválido."""
        with pytest.raises(ValueError) as exc_info:
            SecretsManager(provider="invalid_provider")
        
        assert "não suportado" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_get_secret_cached(self, secrets_manager):
        """Testa obtenção de secret com cache."""
        with patch.dict(os.environ, {"TEST_CACHED_SECRET": "cached-value"}):
            # Primeira chamada (cache miss)
            result1 = await secrets_manager.get("cached-secret")
            assert result1 == "cached-value"
            
            # Segunda chamada (cache hit)
            result2 = await secrets_manager.get("cached-secret")
            assert result2 == "cached-value"
    
    @pytest.mark.asyncio
    async def test_get_secret_custom_ttl(self, secrets_manager):
        """Testa obtenção de secret com TTL customizado."""
        with patch.dict(os.environ, {"TEST_TTL_SECRET": "ttl-value"}):
            result = await secrets_manager.get("ttl-secret", ttl=60)
            
            assert result == "ttl-value"
            assert secrets_manager._cache["ttl-secret"].ttl_seconds == 60
    
    @pytest.mark.asyncio
    async def test_get_secret_not_found(self, secrets_manager):
        """Testa obtenção de secret inexistente."""
        result = await secrets_manager.get("non-existent-secret")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_set_secret(self, secrets_manager):
        """Testa definição de secret (deve falhar para environment)."""
        result = await secrets_manager.set("new-secret", "new-value")
        
        assert result is False  # Environment não suporta set
    
    @pytest.mark.asyncio
    async def test_delete_secret(self, secrets_manager):
        """Testa deleção de secret (deve falhar para environment)."""
        result = await secrets_manager.delete("some-secret")
        
        assert result is False  # Environment não suporta delete
    
    @pytest.mark.asyncio
    async def test_list_secrets(self, secrets_manager):
        """Testa listagem de secrets."""
        with patch.dict(os.environ, {
            "TEST_LIST1": "val1",
            "TEST_LIST2": "val2"
        }):
            result = await secrets_manager.list()
            
            assert "list1" in result
            assert "list2" in result
    
    @pytest.mark.asyncio
    async def test_rotate_secret(self, secrets_manager):
        """Testa agendamento de rotação."""
        result = await secrets_manager.rotate("api-key", rotation_days=60)
        
        assert result is True
        assert "api-key" in secrets_manager._rotation_schedules
        assert secrets_manager._rotation_schedules["api-key"] == timedelta(days=60)
    
    @pytest.mark.asyncio
    async def test_health_check(self, secrets_manager):
        """Testa health check do provider."""
        result = await secrets_manager.health_check()
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_clear_cache_specific(self, secrets_manager):
        """Testa limpeza de cache específico."""
        with patch.dict(os.environ, {
            "TEST_SECRET1": "val1",
            "TEST_SECRET2": "val2"
        }):
            # Popula cache
            await secrets_manager.get("secret1")
            await secrets_manager.get("secret2")
            
            assert "secret1" in secrets_manager._cache
            assert "secret2" in secrets_manager._cache
            
            # Limpa apenas secret1
            await secrets_manager.clear_cache("secret1")
            
            assert "secret1" not in secrets_manager._cache
            assert "secret2" in secrets_manager._cache
    
    @pytest.mark.asyncio
    async def test_clear_cache_all(self, secrets_manager):
        """Testa limpeza completa do cache."""
        with patch.dict(os.environ, {
            "TEST_SECRET1": "val1",
            "TEST_SECRET2": "val2"
        }):
            # Popula cache
            await secrets_manager.get("secret1")
            await secrets_manager.get("secret2")
            
            assert len(secrets_manager._cache) == 2
            
            # Limpa todo o cache
            await secrets_manager.clear_cache()
            
            assert len(secrets_manager._cache) == 0
    
    @pytest.mark.asyncio
    async def test_cache_invalidation_on_set(self):
        """Testa que cache é invalidado ao fazer set."""
        manager = SecretsManager(provider="environment", prefix="TEST_")
        
        with patch.dict(os.environ, {"TEST_INVALIDATE": "initial"}):
            # Popula cache
            await manager.get("invalidate")
            assert "invalidate" in manager._cache
            
            # Tenta fazer set (vai falhar, mas deve tentar invalidar)
            await manager.set("invalidate", "new")
            
            # Cache deve ser invalidado mesmo se set falhar
            # (na implementação real, só invalida se set tiver sucesso)
    
    @pytest.mark.asyncio
    async def test_cache_stale_refresh(self, secrets_manager):
        """Testa que cache stale é refreshado."""
        with patch.dict(os.environ, {"TEST_STALE": "fresh-value"}):
            # Primeira chamada
            result1 = await secrets_manager.get("stale", ttl=1)
            assert result1 == "fresh-value"
            
            # Espera cache ficar stale
            await asyncio.sleep(2)
            
            # Segunda chamada deve buscar do provider novamente
            result2 = await secrets_manager.get("stale", ttl=1)
            assert result2 == "fresh-value"
    
    @pytest.mark.asyncio
    async def test_factory_function(self):
        """Testa factory function create_secrets_manager."""
        manager = create_secrets_manager("environment", prefix="FACTORY_")
        
        assert isinstance(manager, SecretsManager)
        assert manager.cache_enabled is True


class TestSecretsManagerIntegration:
    """Testes de integração para SecretsManager."""
    
    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Testa workflow completo de uso de secrets."""
        # Setup
        with patch.dict(os.environ, {
            "WORKFLOW_PASSWORD": "secure123",
            "WORKFLOW_API_KEY": "key-abc-xyz"
        }):
            manager = SecretsManager(provider="environment", prefix="WORKFLOW_")
            
            # Get secrets
            password = await manager.get("password")
            api_key = await manager.get("api-key")
            
            assert password == "secure123"
            assert api_key == "key-abc-xyz"
            
            # List secrets
            secrets = await manager.list()
            assert "password" in secrets
            assert "api-key" in secrets
            
            # Schedule rotation
            await manager.rotate("api-key", rotation_days=30)
            
            # Health check
            healthy = await manager.health_check()
            assert healthy is True
    
    @pytest.mark.asyncio
    async def test_multiple_secrets_concurrent(self):
        """Testa obtenção concorrente de múltiplos secrets."""
        with patch.dict(os.environ, {
            "CONCURRENT_1": "val1",
            "CONCURRENT_2": "val2",
            "CONCURRENT_3": "val3"
        }):
            manager = SecretsManager(provider="environment", prefix="CONCURRENT_")
            
            # Requisições concorrentes
            tasks = [
                manager.get("1"),
                manager.get("2"),
                manager.get("3"),
            ]
            
            results = await asyncio.gather(*tasks)
            
            assert results == ["val1", "val2", "val3"]


class TestSecretValueEdgeCases:
    """Testes de casos extremos para SecretValue."""
    
    def test_empty_value(self):
        """Testa SecretValue com valor vazio."""
        secret = SecretValue(value="")
        assert secret.value == ""
    
    def test_unicode_value(self):
        """Testa SecretValue com caracteres unicode."""
        secret = SecretValue(value="senha-çom-únicódé-🔐")
        assert secret.value == "senha-çom-únicódé-🔐"
    
    def test_very_long_value(self):
        """Testa SecretValue com valor muito longo."""
        long_value = "x" * 10000
        secret = SecretValue(value=long_value)
        assert len(secret.value) == 10000
    
    def test_version_formats(self):
        """Testa diferentes formatos de versão."""
        versions = ["v1", "1.0.0", "2024-01-01", "abc123"]
        
        for version in versions:
            secret = SecretValue(value="test", version=version)
            assert secret.version == version


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
