"""
LIBeSocial Premium - Plugin System
Arquitetura extensível para carregamento dinâmico de módulos e handlers.

Copyright (c) 2024 LIBeSocial Premium Enterprise
License: MIT
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type, Callable
from pathlib import Path
import importlib
import importlib.util
import logging
from dataclasses import dataclass, field
from enum import Enum
import json

logger = logging.getLogger(__name__)


class PluginLifecycle(Enum):
    """Estados do ciclo de vida do plugin."""
    DISCOVERED = "discovered"
    LOADED = "loaded"
    INITIALIZED = "initialized"
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"


@dataclass
class PluginMetadata:
    """Metadados do plugin."""
    name: str
    version: str
    description: str
    author: str
    email: str
    homepage: str
    license: str = "MIT"
    tags: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    min_python_version: str = "3.8"
    max_python_version: str = "3.12"


@dataclass
class PluginInfo:
    """Informações completas do plugin."""
    metadata: PluginMetadata
    module_path: Path
    lifecycle: PluginLifecycle
    error_message: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)


class IPlugin(ABC):
    """Interface base para todos os plugins."""

    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        """Retorna metadados do plugin."""
        pass

    @abstractmethod
    def initialize(self, config: Dict[str, Any]) -> bool:
        """Inicializa o plugin com configuração."""
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Finaliza o plugin liberando recursos."""
        pass

    def on_event(self, event_type: str, data: Any) -> Optional[Any]:
        """Hook chamado quando um evento ocorre."""
        return None

    def validate(self, event_data: Any) -> tuple[bool, Optional[str]]:
        """Valida dados de evento antes do processamento."""
        return True, None

    def transform(self, event_data: Any) -> Any:
        """Transforma dados de evento antes do envio."""
        return event_data

    def post_send(self, response: Any, event_data: Any) -> None:
        """Hook chamado após envio bem-sucedido."""
        pass

    def on_error(self, error: Exception, event_data: Any) -> None:
        """Hook chamado quando ocorre um erro."""
        pass


class PluginManager:
    """Gerenciador de plugins com descoberta automática e lifecycle."""

    def __init__(self, plugins_dir: Optional[Path] = None):
        self.plugins_dir = plugins_dir or Path.cwd() / "plugins"
        self._plugins: Dict[str, PluginInfo] = {}
        self._instances: Dict[str, IPlugin] = {}
        self._event_handlers: Dict[str, List[str]] = {}
        self._validators: List[str] = []
        self._transformers: List[str] = []

    def discover(self) -> List[str]:
        """Descobre plugins disponíveis no diretório."""
        discovered = []
        
        if not self.plugins_dir.exists():
            logger.info(f"Diretório de plugins não existe: {self.plugins_dir}")
            return discovered

        for plugin_file in self.plugins_dir.glob("plugin_*.py"):
            try:
                plugin_name = plugin_file.stem.replace("plugin_", "")
                spec = importlib.util.spec_from_file_location(
                    f"esocial.plugins.{plugin_name}", 
                    plugin_file
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    if hasattr(module, "PLUGIN_CLASS"):
                        plugin_class = module.PLUGIN_CLASS
                        info = PluginInfo(
                            metadata=plugin_class.metadata,
                            module_path=plugin_file,
                            lifecycle=PluginLifecycle.DISCOVERED
                        )
                        self._plugins[plugin_name] = info
                        discovered.append(plugin_name)
                        logger.info(f"Plugin descoberto: {plugin_name} v{info.metadata.version}")
            except Exception as e:
                logger.error(f"Erro ao descobrir plugin {plugin_file}: {e}")

        return discovered

    def load(self, plugin_name: str) -> bool:
        """Carrega um plugin específico."""
        if plugin_name not in self._plugins:
            logger.error(f"Plugin não encontrado: {plugin_name}")
            return False

        info = self._plugins[plugin_name]
        try:
            spec = importlib.util.spec_from_file_location(
                f"esocial.plugins.{plugin_name}",
                info.module_path
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                if hasattr(module, "PLUGIN_CLASS"):
                    plugin_class = module.PLUGIN_CLASS
                    instance = plugin_class()
                    self._instances[plugin_name] = instance
                    info.lifecycle = PluginLifecycle.LOADED
                    logger.info(f"Plugin carregado: {plugin_name}")
                    return True
                    
        except Exception as e:
            info.lifecycle = PluginLifecycle.ERROR
            info.error_message = str(e)
            logger.error(f"Erro ao carregar plugin {plugin_name}: {e}")
            return False

        return False

    def initialize_all(self, global_config: Optional[Dict[str, Any]] = None) -> int:
        """Inicializa todos os plugins carregados."""
        initialized = 0
        global_config = global_config or {}

        for name, info in self._plugins.items():
            if info.lifecycle == PluginLifecycle.LOADED:
                instance = self._instances.get(name)
                if instance:
                    config = global_config.get(name, {})
                    if instance.initialize(config):
                        info.lifecycle = PluginLifecycle.INITIALIZED
                        
                        # Registrar handlers de eventos
                        if hasattr(instance, 'get_event_handlers'):
                            handlers = instance.get_event_handlers()
                            for event_type in handlers:
                                if event_type not in self._event_handlers:
                                    self._event_handlers[event_type] = []
                                self._event_handlers[event_type].append(name)
                        
                        # Registrar validadores
                        if hasattr(instance, 'is_validator') and instance.is_validator():
                            self._validators.append(name)
                            
                        # Registrar transformadores
                        if hasattr(instance, 'is_transformer') and instance.is_transformer():
                            self._transformers.append(name)
                        
                        initialized += 1
                        logger.info(f"Plugin inicializado: {name}")

        return initialized

    def activate(self, plugin_name: str) -> bool:
        """Ativa um plugin inicializado."""
        if plugin_name not in self._plugins:
            return False
            
        info = self._plugins[plugin_name]
        if info.lifecycle == PluginLifecycle.INITIALIZED:
            info.lifecycle = PluginLifecycle.ACTIVE
            logger.info(f"Plugin ativado: {plugin_name}")
            return True
        return False

    def disable(self, plugin_name: str) -> bool:
        """Desativa um plugin."""
        if plugin_name not in self._plugins:
            return False
            
        info = self._plugins[plugin_name]
        if info.lifecycle in [PluginLifecycle.ACTIVE, PluginLifecycle.INITIALIZED]:
            instance = self._instances.get(plugin_name)
            if instance:
                instance.shutdown()
            info.lifecycle = PluginLifecycle.DISABLED
            logger.info(f"Plugin desativado: {plugin_name}")
            return True
        return False

    def get_plugin(self, name: str) -> Optional[IPlugin]:
        """Retorna instância de um plugin."""
        return self._instances.get(name)

    def get_active_plugins(self) -> List[str]:
        """Lista plugins ativos."""
        return [
            name for name, info in self._plugins.items()
            if info.lifecycle == PluginLifecycle.ACTIVE
        ]

    def process_event(self, event_type: str, data: Any) -> Any:
        """Processa evento através dos plugins registrados."""
        result = data
        
        # Executar validadores
        for validator_name in self._validators:
            if validator_name in self._instances:
                validator = self._instances[validator_name]
                is_valid, error_msg = validator.validate(result)
                if not is_valid:
                    raise ValueError(f"Validação falhou ({validator_name}): {error_msg}")

        # Executar transformadores
        for transformer_name in self._transformers:
            if transformer_name in self._instances:
                transformer = self._instances[transformer_name]
                result = transformer.transform(result)

        # Executar handlers específicos do evento
        handlers = self._event_handlers.get(event_type, [])
        for handler_name in handlers:
            if handler_name in self._instances:
                handler = self._instances[handler_name]
                handler_result = handler.on_event(event_type, result)
                if handler_result is not None:
                    result = handler_result

        return result

    def notify_post_send(self, response: Any, event_data: Any) -> None:
        """Notifica plugins após envio bem-sucedido."""
        for name, instance in self._instances.items():
            try:
                instance.post_send(response, event_data)
            except Exception as e:
                logger.error(f"Erro no post_send do plugin {name}: {e}")

    def notify_error(self, error: Exception, event_data: Any) -> None:
        """Notifica plugins sobre erro."""
        for name, instance in self._instances.items():
            try:
                instance.on_error(error, event_data)
            except Exception as e:
                logger.error(f"Erro no on_error do plugin {name}: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas dos plugins."""
        return {
            "total_discovered": len(self._plugins),
            "total_loaded": len(self._instances),
            "active_count": len(self.get_active_plugins()),
            "validators_count": len(self._validators),
            "transformers_count": len(self._transformers),
            "event_handlers": len(self._event_handlers),
            "plugins": {
                name: {
                    "version": info.metadata.version,
                    "lifecycle": info.lifecycle.value,
                    "error": info.error_message
                }
                for name, info in self._plugins.items()
            }
        }


# Exemplo de Plugin Base para extensão
class BasePlugin(IPlugin):
    """Classe base conveniente para criar plugins."""

    def __init__(self):
        self._config: Dict[str, Any] = {}
        self._initialized = False

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="base",
            version="1.0.0",
            description="Plugin base",
            author="LIBeSocial Team",
            email="team@libesocial.com",
            homepage="https://libesocial.com"
        )

    def initialize(self, config: Dict[str, Any]) -> bool:
        self._config = config
        self._initialized = True
        return True

    def shutdown(self) -> None:
        self._initialized = False
        self._config = {}

    def is_validator(self) -> bool:
        return False

    def is_transformer(self) -> bool:
        return False

    def get_event_handlers(self) -> List[str]:
        return []
