"""
Testes do Plugin System - LIBeSocial Premium
Cobertura completa do sistema de plugins.

Copyright (c) 2024 LIBeSocial Premium Enterprise
License: MIT
"""

import pytest
from pathlib import Path
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock

from esocial.plugin_manager import (
    PluginManager, 
    IPlugin, 
    BasePlugin,
    PluginMetadata,
    PluginLifecycle,
    PluginInfo
)


class TestPluginMetadata:
    """Testes para PluginMetadata."""

    def test_create_metadata(self):
        metadata = PluginMetadata(
            name="test-plugin",
            version="1.0.0",
            description="Plugin de teste",
            author="Dev Team",
            email="dev@test.com",
            homepage="https://test.com"
        )
        assert metadata.name == "test-plugin"
        assert metadata.version == "1.0.0"
        assert metadata.license == "MIT"
        assert metadata.tags == []
        assert metadata.dependencies == []

    def test_metadata_with_optional_fields(self):
        metadata = PluginMetadata(
            name="advanced-plugin",
            version="2.0.0",
            description="Plugin avançado",
            author="Senior Dev",
            email="senior@test.com",
            homepage="https://advanced.com",
            license="Apache-2.0",
            tags=["validation", "transform"],
            dependencies=["requests", "pydantic"],
            min_python_version="3.9",
            max_python_version="3.12"
        )
        assert metadata.license == "Apache-2.0"
        assert "validation" in metadata.tags
        assert len(metadata.dependencies) == 2


class TestPluginLifecycle:
    """Testes para enum PluginLifecycle."""

    def test_lifecycle_states(self):
        assert PluginLifecycle.DISCOVERED.value == "discovered"
        assert PluginLifecycle.LOADED.value == "loaded"
        assert PluginLifecycle.INITIALIZED.value == "initialized"
        assert PluginLifecycle.ACTIVE.value == "active"
        assert PluginLifecycle.DISABLED.value == "disabled"
        assert PluginLifecycle.ERROR.value == "error"


class TestBasePlugin:
    """Testes para BasePlugin."""

    def test_base_plugin_metadata(self):
        plugin = BasePlugin()
        metadata = plugin.metadata
        assert metadata.name == "base"
        assert metadata.version == "1.0.0"
        assert metadata.author == "LIBeSocial Team"

    def test_base_plugin_initialize(self):
        plugin = BasePlugin()
        config = {"key": "value"}
        result = plugin.initialize(config)
        assert result is True
        assert plugin._config == config
        assert plugin._initialized is True

    def test_base_plugin_shutdown(self):
        plugin = BasePlugin()
        plugin.initialize({"key": "value"})
        plugin.shutdown()
        assert plugin._initialized is False
        assert plugin._config == {}

    def test_base_plugin_default_methods(self):
        plugin = BasePlugin()
        plugin.initialize({})
        
        # Test default implementations
        assert plugin.validate("data") == (True, None)
        assert plugin.transform("data") == "data"
        assert plugin.on_event("event", "data") is None
        assert plugin.is_validator() is False
        assert plugin.is_transformer() is False
        assert plugin.get_event_handlers() == []


class SampleValidatorPlugin(BasePlugin):
    """Plugin de exemplo para validação."""

    @property
    def metadata(self):
        return PluginMetadata(
            name="validator",
            version="1.0.0",
            description="Validador de CPF/CNPJ",
            author="Test Team",
            email="test@example.com",
            homepage="https://example.com"
        )

    def is_validator(self) -> bool:
        return True

    def validate(self, event_data: any) -> tuple[bool, str]:
        if isinstance(event_data, dict) and "cpf" in event_data:
            cpf = event_data["cpf"]
            if len(cpf) != 11:
                return False, "CPF inválido"
        return True, None


class SampleTransformerPlugin(BasePlugin):
    """Plugin de exemplo para transformação."""

    @property
    def metadata(self):
        return PluginMetadata(
            name="transformer",
            version="1.0.0",
            description="Transformador de dados",
            author="Test Team",
            email="test@example.com",
            homepage="https://example.com"
        )

    def is_transformer(self) -> bool:
        return True

    def transform(self, event_data: any) -> any:
        if isinstance(event_data, dict):
            event_data["transformed"] = True
        return event_data

    def get_event_handlers(self) -> list[str]:
        return ["S-1000", "S-1010"]


class SampleEventHandlerPlugin(BasePlugin):
    """Plugin de exemplo para handler de eventos."""

    def __init__(self):
        super().__init__()
        self.events_received = []

    @property
    def metadata(self):
        return PluginMetadata(
            name="event_handler",
            version="1.0.0",
            description="Handler de eventos",
            author="Test Team",
            email="test@example.com",
            homepage="https://example.com"
        )

    def get_event_handlers(self) -> list[str]:
        return ["S-1000", "S-1020"]

    def on_event(self, event_type: str, data: any) -> any:
        self.events_received.append((event_type, data))
        return data


class TestPluginManager:
    """Testes para PluginManager."""

    @pytest.fixture
    def plugin_manager(self):
        return PluginManager()

    @pytest.fixture
    def temp_plugins_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_init_default(self, plugin_manager):
        assert plugin_manager.plugins_dir == Path.cwd() / "plugins"
        assert len(plugin_manager._plugins) == 0
        assert len(plugin_manager._instances) == 0

    def test_init_custom_dir(self, temp_plugins_dir):
        manager = PluginManager(plugins_dir=temp_plugins_dir)
        assert manager.plugins_dir == temp_plugins_dir

    def test_discover_no_directory(self, plugin_manager):
        discovered = plugin_manager.discover()
        assert discovered == []

    def test_discover_empty_directory(self, temp_plugins_dir, plugin_manager):
        plugin_manager.plugins_dir = temp_plugins_dir
        discovered = plugin_manager.discover()
        assert discovered == []

    def test_load_nonexistent_plugin(self, plugin_manager):
        result = plugin_manager.load("nonexistent")
        assert result is False

    def test_get_active_plugins_empty(self, plugin_manager):
        active = plugin_manager.get_active_plugins()
        assert active == []

    def test_get_stats_empty(self, plugin_manager):
        stats = plugin_manager.get_stats()
        assert stats["total_discovered"] == 0
        assert stats["total_loaded"] == 0
        assert stats["active_count"] == 0

    def test_manual_plugin_registration_and_lifecycle(self, plugin_manager):
        # Simular registro manual de plugin
        metadata = PluginMetadata(
            name="manual_plugin",
            version="1.0.0",
            description="Plugin manual",
            author="Test",
            email="test@test.com",
            homepage="https://test.com"
        )
        
        info = PluginInfo(
            metadata=metadata,
            module_path=Path("/fake/path.py"),
            lifecycle=PluginLifecycle.DISCOVERED
        )
        
        plugin_manager._plugins["manual_plugin"] = info
        plugin_manager._instances["manual_plugin"] = BasePlugin()
        
        # Testar descoberta
        assert "manual_plugin" in plugin_manager._plugins
        
        # Simular load
        info.lifecycle = PluginLifecycle.LOADED
        
        # Inicializar
        initialized = plugin_manager.initialize_all()
        assert initialized == 1
        assert info.lifecycle == PluginLifecycle.INITIALIZED
        
        # Ativar
        result = plugin_manager.activate("manual_plugin")
        assert result is True
        assert info.lifecycle == PluginLifecycle.ACTIVE
        
        # Desativar
        result = plugin_manager.disable("manual_plugin")
        assert result is True
        assert info.lifecycle == PluginLifecycle.DISABLED

    def test_process_event_with_validators(self, plugin_manager):
        validator = SampleValidatorPlugin()
        plugin_manager._instances["validator"] = validator
        plugin_manager._validators = ["validator"]
        
        # Dados válidos
        result = plugin_manager.process_event("S-1000", {"cpf": "12345678901"})
        assert result == {"cpf": "12345678901"}
        
        # Dados inválidos
        with pytest.raises(ValueError) as exc_info:
            plugin_manager.process_event("S-1000", {"cpf": "123"})
        assert "CPF inválido" in str(exc_info.value)

    def test_process_event_with_transformers(self, plugin_manager):
        transformer = SampleTransformerPlugin()
        plugin_manager._instances["transformer"] = transformer
        plugin_manager._transformers = ["transformer"]
        
        result = plugin_manager.process_event("S-1000", {"name": "Test"})
        assert result == {"name": "Test", "transformed": True}

    def test_process_event_with_handlers(self, plugin_manager):
        handler = SampleEventHandlerPlugin()
        plugin_manager._instances["event_handler"] = handler
        plugin_manager._event_handlers = {
            "S-1000": ["event_handler"],
            "S-1020": ["event_handler"]
        }
        
        data = {"id": "123"}
        result = plugin_manager.process_event("S-1000", data)
        
        assert result == data
        assert len(handler.events_received) == 1
        assert handler.events_received[0] == ("S-1000", data)

    def test_notify_post_send(self, plugin_manager):
        plugin1 = Mock(spec=BasePlugin)
        plugin2 = Mock(spec=BasePlugin)
        
        plugin_manager._instances = {
            "plugin1": plugin1,
            "plugin2": plugin2
        }
        
        response = {"status": "success"}
        event_data = {"event": "S-1000"}
        
        plugin_manager.notify_post_send(response, event_data)
        
        plugin1.post_send.assert_called_once_with(response, event_data)
        plugin2.post_send.assert_called_once_with(response, event_data)

    def test_notify_error(self, plugin_manager):
        plugin1 = Mock(spec=BasePlugin)
        plugin2 = Mock(spec=BasePlugin)
        
        plugin_manager._instances = {
            "plugin1": plugin1,
            "plugin2": plugin2
        }
        
        error = ValueError("Test error")
        event_data = {"event": "S-1000"}
        
        plugin_manager.notify_error(error, event_data)
        
        plugin1.on_error.assert_called_once_with(error, event_data)
        plugin2.on_error.assert_called_once_with(error, event_data)

    def test_notify_error_handles_exceptions(self, plugin_manager, caplog):
        plugin = Mock(spec=BasePlugin)
        plugin.on_error.side_effect = Exception("Plugin error")
        
        plugin_manager._instances = {"failing_plugin": plugin}
        
        error = ValueError("Original error")
        plugin_manager.notify_error(error, {})
        
        assert "Erro no on_error" in caplog.text

    def test_get_stats_with_plugins(self, plugin_manager):
        metadata = PluginMetadata(
            name="stats_plugin",
            version="2.0.0",
            description="Stats",
            author="Test",
            email="test@test.com",
            homepage="https://test.com"
        )
        
        info = PluginInfo(
            metadata=metadata,
            module_path=Path("/fake.py"),
            lifecycle=PluginLifecycle.ACTIVE
        )
        
        plugin_manager._plugins["stats_plugin"] = info
        plugin_manager._instances["stats_plugin"] = BasePlugin()
        plugin_manager._validators = ["stats_plugin"]
        plugin_manager._event_handlers = {"S-1000": ["stats_plugin"]}
        
        stats = plugin_manager.get_stats()
        
        assert stats["total_discovered"] == 1
        assert stats["total_loaded"] == 1
        assert stats["active_count"] == 1
        assert stats["validators_count"] == 1
        assert stats["transformers_count"] == 0
        assert stats["event_handlers"] == 1
        assert "stats_plugin" in stats["plugins"]


class TestPluginIntegration:
    """Testes de integração com múltiplos plugins."""

    def test_chain_validator_transformer_handler(self):
        manager = PluginManager()
        
        validator = SampleValidatorPlugin()
        transformer = SampleTransformerPlugin()
        handler = SampleEventHandlerPlugin()
        
        manager._instances = {
            "validator": validator,
            "transformer": transformer,
            "handler": handler
        }
        
        manager._validators = ["validator"]
        manager._transformers = ["transformer"]
        manager._event_handlers = {"S-1000": ["handler"]}
        
        data = {"cpf": "12345678901", "name": "Test"}
        result = manager.process_event("S-1000", data)
        
        # Validado (não levantou exceção)
        # Transformado
        assert result["transformed"] is True
        # Handler chamado
        assert len(handler.events_received) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
