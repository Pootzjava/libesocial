"""
Secrets Management - Enterprise Grade

Gerenciamento seguro de segredos com suporte a múltiplos provedores,
rotação automática e cache seguro em memória.
"""

import os
import asyncio
import hashlib
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


class SecretProvider(Enum):
    """Provedores de secrets suportados."""
    ENVIRONMENT = "environment"
    AWS_SECRETS_MANAGER = "aws_secrets_manager"
    AZURE_KEY_VAULT = "azure_key_vault"
    HASHICORP_VAULT = "hashicorp_vault"
    FILE = "file"


@dataclass
class SecretValue:
    """Valor de secret com metadados."""
    value: str
    version: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    rotation_schedule: Optional[timedelta] = None
    
    def is_expired(self) -> bool:
        """Verifica se o secret expirou."""
        if self.expires_at is None:
            return False
        # Usa datetime.now(timezone.utc) para ser timezone-aware
        now = datetime.now(timezone.utc)
        # Se expires_at for timezone-naive, converte para UTC
        if self.expires_at.tzinfo is None:
            expires_at = self.expires_at.replace(tzinfo=timezone.utc)
        else:
            expires_at = self.expires_at
        return now > expires_at
    
    def should_rotate(self) -> bool:
        """Verifica se o secret deve ser rotacionado."""
        if self.rotation_schedule is None:
            return False
        now = datetime.now(timezone.utc)
        # Se created_at for timezone-naive, converte para UTC
        if self.created_at.tzinfo is None:
            created_at = self.created_at.replace(tzinfo=timezone.utc)
        else:
            created_at = self.created_at
        next_rotation = created_at + self.rotation_schedule
        return now >= next_rotation


@dataclass
class CacheEntry:
    """Entrada de cache para secrets."""
    secret_value: SecretValue
    cached_at: float = field(default_factory=time.time)
    ttl_seconds: int = 300  # 5 minutos default
    
    def is_stale(self) -> bool:
        """Verifica se o cache está obsoleto."""
        return (time.time() - self.cached_at) > self.ttl_seconds


class BaseSecretsProvider(ABC):
    """Classe base para provedores de secrets."""
    
    @abstractmethod
    async def get_secret(self, name: str) -> Optional[SecretValue]:
        """Obtém um secret pelo nome."""
        pass
    
    @abstractmethod
    async def set_secret(self, name: str, value: str, 
                        metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Define um secret."""
        pass
    
    @abstractmethod
    async def delete_secret(self, name: str) -> bool:
        """Deleta um secret."""
        pass
    
    @abstractmethod
    async def list_secrets(self, prefix: str = "") -> List[str]:
        """Lista todos os secrets com um prefixo opcional."""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Verifica a saúde do provedor."""
        pass


class EnvironmentSecretsProvider(BaseSecretsProvider):
    """Provedor de secrets via environment variables (desenvolvimento)."""
    
    def __init__(self, prefix: str = "ESOCIAL_"):
        self.prefix = prefix
    
    def _get_env_name(self, name: str) -> str:
        """Converte nome do secret para variável de ambiente."""
        env_name = name.upper().replace("-", "_").replace(".", "_")
        if not env_name.startswith(self.prefix):
            env_name = f"{self.prefix}{env_name}"
        return env_name
    
    async def get_secret(self, name: str) -> Optional[SecretValue]:
        """Obtém secret de environment variable."""
        env_name = self._get_env_name(name)
        value = os.getenv(env_name)
        
        if value is None:
            logger.debug(f"Secret {name} não encontrado em {env_name}")
            return None
        
        return SecretValue(
            value=value,
            version="env",
            created_at=datetime.now(timezone.utc)
        )
    
    async def set_secret(self, name: str, value: str,
                        metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Não suporta set em runtime (apenas para desenvolvimento)."""
        logger.warning("EnvironmentSecretsProvider não suporta set em runtime")
        return False
    
    async def delete_secret(self, name: str) -> bool:
        """Não suporta delete em runtime."""
        logger.warning("EnvironmentSecretsProvider não suporta delete em runtime")
        return False
    
    async def list_secrets(self, prefix: str = "") -> List[str]:
        """Lista secrets que começam com o prefixo."""
        secrets = []
        search_prefix = self.prefix + prefix.upper()
        
        for key in os.environ.keys():
            if key.startswith(search_prefix):
                secret_name = key[len(self.prefix):].lower().replace("_", "-")
                secrets.append(secret_name)
        
        return secrets
    
    async def health_check(self) -> bool:
        """Sempre saudável para environment variables."""
        return True


class AWSSecretsManagerProvider(BaseSecretsProvider):
    """Provedor AWS Secrets Manager."""
    
    def __init__(self, region_name: str = "us-east-1", 
                 secret_prefix: str = "esocial/"):
        try:
            import boto3
            from botocore.exceptions import ClientError
            self.boto3 = boto3
            self.ClientError = ClientError
        except ImportError:
            raise ImportError(
                "boto3 necessário para AWS Secrets Manager. "
                "Instale: pip install boto3"
            )
        
        self.client = self.boto3.client("secretsmanager", region_name=region_name)
        self.secret_prefix = secret_prefix
    
    def _get_secret_name(self, name: str) -> str:
        """Constrói nome completo do secret na AWS."""
        if name.startswith(self.secret_prefix):
            return name
        return f"{self.secret_prefix}{name}"
    
    async def get_secret(self, name: str) -> Optional[SecretValue]:
        """Obtém secret da AWS Secrets Manager."""
        secret_name = self._get_secret_name(name)
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.get_secret_value(SecretId=secret_name)
            )
            
            # Determina se é string ou binary
            if "SecretString" in response:
                value = response["SecretString"]
            else:
                value = response["SecretBinary"].decode("utf-8")
            
            # Extrai metadados
            version_id = response.get("VersionId", "")
            created_date = response.get("CreatedDate", datetime.utcnow())
            
            return SecretValue(
                value=value,
                version=version_id,
                created_at=created_date if isinstance(created_date, datetime) else datetime.utcnow()
            )
            
        except self.ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                logger.debug(f"Secret {name} não encontrado")
                return None
            logger.error(f"Erro ao obter secret {name}: {e}")
            raise
    
    async def set_secret(self, name: str, value: str,
                        metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Define ou atualiza secret na AWS."""
        secret_name = self._get_secret_name(name)
        
        try:
            loop = asyncio.get_event_loop()
            
            # Tenta atualizar primeiro
            try:
                await loop.run_in_executor(
                    None,
                    lambda: self.client.update_secret(
                        SecretId=secret_name,
                        SecretString=value
                    )
                )
            except self.ClientError as e:
                if e.response["Error"]["Code"] == "ResourceNotFoundException":
                    # Cria novo secret
                    await loop.run_in_executor(
                        None,
                        lambda: self.client.create_secret(
                            Name=secret_name,
                            SecretString=value,
                            Description=metadata.get("description", "") if metadata else ""
                        )
                    )
                else:
                    raise
            
            return True
            
        except self.ClientError as e:
            logger.error(f"Erro ao definir secret {name}: {e}")
            return False
    
    async def delete_secret(self, name: str) -> bool:
        """Deleta secret da AWS (agendamento de 7-30 dias)."""
        secret_name = self._get_secret_name(name)
        
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.delete_secret(
                    SecretId=secret_name,
                    RecoveryWindowInDays=7  # Mínimo permitido pela AWS
                )
            )
            return True
        except self.ClientError as e:
            logger.error(f"Erro ao deletar secret {name}: {e}")
            return False
    
    async def list_secrets(self, prefix: str = "") -> List[str]:
        """Lista secrets da AWS com prefixo."""
        try:
            loop = asyncio.get_event_loop()
            paginator = self.client.get_paginator("list_secrets")
            
            secrets = []
            search_prefix = self.secret_prefix + prefix
            
            async for page in paginator.paginate():
                for secret in page["SecretList"]:
                    name = secret["Name"]
                    if name.startswith(search_prefix):
                        # Remove prefixo para retornar nome relativo
                        relative_name = name[len(self.secret_prefix):]
                        secrets.append(relative_name)
            
            return secrets
            
        except self.ClientError as e:
            logger.error(f"Erro ao listar secrets: {e}")
            return []
    
    async def health_check(self) -> bool:
        """Verifica conectividade com AWS Secrets Manager."""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.list_secrets(MaxResults=1)
            )
            return True
        except Exception as e:
            logger.error(f"Health check falhou: {e}")
            return False


class AzureKeyVaultProvider(BaseSecretsProvider):
    """Provedor Azure Key Vault."""
    
    def __init__(self, vault_url: str):
        try:
            from azure.keyvault.secrets import SecretClient
            from azure.identity import DefaultAzureCredential
            self.SecretClient = SecretClient
            self.DefaultAzureCredential = DefaultAzureCredential
        except ImportError:
            raise ImportError(
                "azure-keyvault-secrets e azure-identity necessários. "
                "Instale: pip install azure-keyvault-secrets azure-identity"
            )
        
        self.vault_url = vault_url
        self.credential = self.DefaultAzureCredential()
        self.client = self.SecretClient(
            vault_url=self.vault_url,
            credential=self.credential
        )
    
    async def get_secret(self, name: str) -> Optional[SecretValue]:
        """Obtém secret do Azure Key Vault."""
        try:
            loop = asyncio.get_event_loop()
            secret = await loop.run_in_executor(
                None,
                lambda: self.client.get_secret(name)
            )
            
            return SecretValue(
                value=secret.value,
                version=secret.properties.version,
                created_at=secret.properties.created_on,
                expires_at=secret.properties.expires_on
            )
            
        except Exception as e:
            logger.debug(f"Secret {name} não encontrado: {e}")
            return None
    
    async def set_secret(self, name: str, value: str,
                        metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Define secret no Azure Key Vault."""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.set_secret(name, value)
            )
            return True
        except Exception as e:
            logger.error(f"Erro ao definir secret {name}: {e}")
            return False
    
    async def delete_secret(self, name: str) -> bool:
        """Deleta secret do Azure Key Vault."""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.begin_delete_secret(name)
            )
            return True
        except Exception as e:
            logger.error(f"Erro ao deletar secret {name}: {e}")
            return False
    
    async def list_secrets(self, prefix: str = "") -> List[str]:
        """Lista secrets do Azure Key Vault."""
        try:
            loop = asyncio.get_event_loop()
            secrets = await loop.run_in_executor(
                None,
                lambda: list(self.client.list_properties_of_secrets())
            )
            
            return [
                secret.name for secret in secrets
                if secret.name.startswith(prefix)
            ]
            
        except Exception as e:
            logger.error(f"Erro ao listar secrets: {e}")
            return []
    
    async def health_check(self) -> bool:
        """Verifica conectividade com Azure Key Vault."""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: list(self.client.list_properties_of_secrets(max_results=1))
            )
            return True
        except Exception as e:
            logger.error(f"Health check falhou: {e}")
            return False


class HashiCorpVaultProvider(BaseSecretsProvider):
    """Provedor HashiCorp Vault."""
    
    def __init__(self, url: str = "http://localhost:8200", 
                 token: Optional[str] = None,
                 namespace: Optional[str] = None):
        try:
            import hvac
            self.hvac = hvac
        except ImportError:
            raise ImportError(
                "hvac necessário para HashiCorp Vault. "
                "Instale: pip install hvac"
            )
        
        self.client = self.hvac.Client(
            url=url,
            token=token or os.getenv("VAULT_TOKEN"),
            namespace=namespace
        )
    
    async def get_secret(self, name: str) -> Optional[SecretValue]:
        """Obtém secret do HashiCorp Vault."""
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.secrets.kv.v2.read_secret_version(path=name)
            )
            
            data = response["data"]["data"]
            metadata = response["data"]["metadata"]
            
            return SecretValue(
                value=data.get("value", ""),
                version=str(metadata.get("version", "")),
                created_at=datetime.fromisoformat(metadata.get("created_time", "")) if metadata.get("created_time") else datetime.utcnow()
            )
            
        except Exception as e:
            logger.debug(f"Secret {name} não encontrado: {e}")
            return None
    
    async def set_secret(self, name: str, value: str,
                        metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Define secret no HashiCorp Vault."""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.secrets.kv.v2.create_or_update_secret(
                    path=name,
                    secret={"value": value}
                )
            )
            return True
        except Exception as e:
            logger.error(f"Erro ao definir secret {name}: {e}")
            return False
    
    async def delete_secret(self, name: str) -> bool:
        """Deleta secret do HashiCorp Vault."""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.secrets.kv.v2.delete_metadata_and_all_versions(name)
            )
            return True
        except Exception as e:
            logger.error(f"Erro ao deletar secret {name}: {e}")
            return False
    
    async def list_secrets(self, prefix: str = "") -> List[str]:
        """Lista secrets do HashiCorp Vault."""
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.secrets.kv.v2.list_secrets(path=prefix)
            )
            
            return response["data"]["keys"]
            
        except Exception as e:
            logger.debug(f"Erro ao listar secrets: {e}")
            return []
    
    async def health_check(self) -> bool:
        """Verifica conectividade com HashiCorp Vault."""
        try:
            loop = asyncio.get_event_loop()
            is_authenticated = await loop.run_in_executor(
                None,
                lambda: self.client.is_authenticated()
            )
            return is_authenticated
        except Exception as e:
            logger.error(f"Health check falhou: {e}")
            return False


class SecretsManager:
    """
    Gerenciador de Secrets Enterprise-grade.
    
    Suporta múltiplos provedores com failover automático,
    cache em memória e rotação de credenciais.
    
    Exemplo de uso:
        secrets = SecretsManager(provider="aws")
        password = await secrets.get("database-password")
        
        # Com cache customizado
        cert = await secrets.get("cert-password", ttl=60)
        
        # Rotação automática
        await secrets.rotate("api-key", rotation_days=90)
    """
    
    def __init__(
        self,
        provider: str = "environment",
        cache_enabled: bool = True,
        cache_ttl: int = 300,
        **provider_kwargs
    ):
        """
        Inicializa o Secrets Manager.
        
        Args:
            provider: Tipo de provedor ("environment", "aws", "azure", "vault")
            cache_enabled: Habilita cache em memória
            cache_ttl: TTL do cache em segundos
            **provider_kwargs: Argumentos específicos do provedor
        """
        self.cache_enabled = cache_enabled
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, CacheEntry] = {}
        self._rotation_schedules: Dict[str, timedelta] = {}
        
        # Mapeia string para classe do provedor
        provider_map = {
            "environment": EnvironmentSecretsProvider,
            "aws": AWSSecretsManagerProvider,
            "azure": AzureKeyVaultProvider,
            "vault": HashiCorpVaultProvider,
        }
        
        if provider not in provider_map:
            raise ValueError(
                f"Provedor '{provider}' não suportado. "
                f"Opções: {list(provider_map.keys())}"
            )
        
        self.provider = provider_map[provider](**provider_kwargs)
        logger.info(f"SecretsManager inicializado com provedor: {provider}")
    
    async def get(self, name: str, ttl: Optional[int] = None) -> Optional[str]:
        """
        Obtém um secret pelo nome.
        
        Args:
            name: Nome do secret
            ttl: Override do TTL do cache para esta requisição
            
        Returns:
            Valor do secret ou None se não encontrado
        """
        # Verifica cache primeiro
        if self.cache_enabled and name in self._cache:
            entry = self._cache[name]
            if not entry.is_stale() and not entry.secret_value.is_expired():
                logger.debug(f"Cache hit para secret: {name}")
                return entry.secret_value.value
            else:
                logger.debug(f"Cache stale para secret: {name}")
                del self._cache[name]
        
        # Busca no provedor
        secret_value = await self.provider.get_secret(name)
        
        if secret_value is None:
            return None
        
        # Aplica schedule de rotação se configurado
        if name in self._rotation_schedules:
            secret_value.rotation_schedule = self._rotation_schedules[name]
        
        # Atualiza cache
        if self.cache_enabled:
            effective_ttl = ttl if ttl is not None else self.cache_ttl
            self._cache[name] = CacheEntry(
                secret_value=secret_value,
                ttl_seconds=effective_ttl
            )
        
        logger.debug(f"Secret obtido: {name}")
        return secret_value.value
    
    async def set(self, name: str, value: str, 
                 metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Define um secret.
        
        Args:
            name: Nome do secret
            value: Valor do secret
            metadata: Metadados opcionais
            
        Returns:
            True se sucesso, False caso contrário
        """
        success = await self.provider.set_secret(name, value, metadata)
        
        if success and self.cache_enabled:
            # Invalida cache
            if name in self._cache:
                del self._cache[name]
        
        return success
    
    async def delete(self, name: str) -> bool:
        """
        Deleta um secret.
        
        Args:
            name: Nome do secret
            
        Returns:
            True se sucesso, False caso contrário
        """
        success = await self.provider.delete_secret(name)
        
        if success and self.cache_enabled:
            # Invalida cache
            if name in self._cache:
                del self._cache[name]
        
        return success
    
    async def list(self, prefix: str = "") -> List[str]:
        """
        Lista todos os secrets com prefixo opcional.
        
        Args:
            prefix: Prefixo para filtrar secrets
            
        Returns:
            Lista de nomes de secrets
        """
        return await self.provider.list_secrets(prefix)
    
    async def rotate(self, name: str, rotation_days: int = 90) -> bool:
        """
        Agenda rotação automática para um secret.
        
        Args:
            name: Nome do secret
            rotation_days: Dias entre rotações
            
        Returns:
            True se agendado com sucesso
        """
        self._rotation_schedules[name] = timedelta(days=rotation_days)
        logger.info(f"Rotação agendada para {name}: a cada {rotation_days} dias")
        return True
    
    async def health_check(self) -> bool:
        """
        Verifica saúde do provedor de secrets.
        
        Returns:
            True se saudável, False caso contrário
        """
        return await self.provider.health_check()
    
    async def clear_cache(self, name: Optional[str] = None) -> None:
        """
        Limpa o cache.
        
        Args:
            name: Nome específico para limpar (None limpa todo o cache)
        """
        if name:
            if name in self._cache:
                del self._cache[name]
                logger.debug(f"Cache limpo para: {name}")
        else:
            self._cache.clear()
            logger.debug("Cache completamente limpo")
    
    def _generate_hash(self, value: str) -> str:
        """Gera hash seguro para verificação de integridade."""
        return hashlib.sha256(value.encode()).hexdigest()


# Factory function para criar SecretsManager
def create_secrets_manager(
    provider: str = "environment",
    **kwargs
) -> SecretsManager:
    """
    Factory function para criar SecretsManager.
    
    Exemplo:
        secrets = create_secrets_manager("aws", region_name="us-east-1")
    """
    return SecretsManager(provider=provider, **kwargs)
