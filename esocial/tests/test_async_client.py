"""
Testes para o AsyncESocialClient.

Cobre:
- Inicialização e conexão
- Envio de lotes (mock)
- Circuit breaker integration
- Rate limiting
- Retry com backoff
- Persistência
- Health checks
- Context manager
"""
import asyncio
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from esocial.async_client import (
    AsyncESocialClient,
    AsyncSendError,
    create_async_client,
)
from esocial.models import ESocialConfig, SendResult, EmployerIdentification, TargetEnum


class TestAsyncClientInitialization:
    """Testes de inicialização do cliente."""
    
    def test_create_client_basic(self):
        """Cria cliente com configuração mínima."""
        config = ESocialConfig(target=TargetEnum.TESTS)
        client = AsyncESocialClient(config=config)
        
        assert client.config == config
        assert client.max_connections == 10
        assert client.timeout == 30.0
        assert client.http2 is True
        assert client._connected is False
        assert client._client is None
    
    def test_create_client_custom_config(self):
        """Cria cliente com configurações customizadas."""
        config = ESocialConfig(target=TargetEnum.PRODUCTION)
        client = AsyncESocialClient(
            config=config,
            max_connections=20,
            max_keepalive_connections=10,
            timeout=60.0,
            http2=False,
            enable_persistence=False
        )
        
        assert client.max_connections == 20
        assert client.max_keepalive_connections == 10
        assert client.timeout == 60.0
        assert client.http2 is False
        assert client.enable_persistence is False
        assert client._persistence is None
    
    def test_create_client_with_persistence(self, tmp_path):
        """Cria cliente com persistência habilitada."""
        config = ESocialConfig(target=TargetEnum.TESTS)
        storage_path = str(tmp_path / "storage")
        
        client = AsyncESocialClient(
            config=config,
            enable_persistence=True,
            storage_path=storage_path
        )
        
        assert client._persistence is not None
        assert client._persistence.storage_path.name == "storage"


@pytest.mark.asyncio
class TestAsyncClientConnection:
    """Testes de conexão e desconexão."""
    
    async def test_connect(self):
        """Testa conexão inicial."""
        config = ESocialConfig(target=TargetEnum.TESTS)
        client = AsyncESocialClient(config=config)
        
        assert client._connected is False
        
        await client.connect()
        
        assert client._connected is True
        assert client._client is not None
        assert isinstance(client._client, httpx.AsyncClient)
        
        await client.disconnect()
    
    async def test_connect_idempotent(self):
        """Conectar múltiplas vezes não cria múltiplos clientes."""
        config = ESocialConfig(target=TargetEnum.TESTS)
        client = AsyncESocialClient(config=config)
        
        await client.connect()
        first_client = client._client
        
        await client.connect()
        second_client = client._client
        
        assert first_client is second_client
        
        await client.disconnect()
    
    async def test_disconnect(self):
        """Testa desconexão."""
        config = ESocialConfig(target=TargetEnum.TESTS)
        client = AsyncESocialClient(config=config)
        
        await client.connect()
        assert client._connected is True
        
        await client.disconnect()
        assert client._connected is False
        assert client._client is None
    
    async def test_context_manager(self):
        """Testa uso como context manager."""
        config = ESocialConfig(target=TargetEnum.TESTS)
        client = AsyncESocialClient(config=config)
        
        async with client as c:
            assert c._connected is True
            assert c._client is not None
        
        assert client._connected is False
        assert client._client is None


@pytest.mark.asyncio
class TestAsyncClientSendBatch:
    """Testes de envio de lotes."""
    
    @patch('esocial.async_client.httpx.AsyncClient.post')
    async def test_send_batch_success(self, mock_post):
        """Testa envio bem-sucedido."""
        # Mock da resposta
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = """<?xml version="1.0"?>
        <soap:Envelope>
            <soap:Body>
                <EnviarLoteEventosResponse>
                    <protocolo>1234567890</protocolo>
                </EnviarLoteEventosResponse>
            </soap:Body>
        </soap:Envelope>
        """
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response
        
        config = ESocialConfig(target=TargetEnum.TESTS)
        client = AsyncESocialClient(config=config, enable_persistence=False)
        
        await client.connect()
        
        events = [{'id': 'evt1', 'tipo': 'S-2200'}]
        xml_content = "<lote>...</lote>"
        
        result = await client.send_batch("batch_1", events, xml_content)
        
        assert result.success is True
        assert result.protocol == "1234567890"  # Usar 'protocol' em vez de 'protocolo'
        assert result.batch_id == "batch_1"
        
        await client.disconnect()
    
    @patch('esocial.async_client.httpx.AsyncClient.post')
    async def test_send_batch_http_error(self, mock_post):
        """Testa envio com erro HTTP."""
        # Mock do erro
        mock_post.side_effect = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=MagicMock(),
            response=MagicMock(status_code=500, text="Erro interno")
        )
        
        config = ESocialConfig(target=TargetEnum.TESTS)
        client = AsyncESocialClient(config=config, enable_persistence=False)
        
        await client.connect()
        
        events = [{'id': 'evt1', 'tipo': 'S-2200'}]
        xml_content = "<lote>...</lote>"
        
        with pytest.raises(AsyncSendError) as exc_info:
            await client.send_batch("batch_1", events, xml_content)
        
        assert exc_info.value.batch_id == "batch_1"
        assert "HTTP 500" in str(exc_info.value)
        
        await client.disconnect()
    
    @patch('esocial.async_client.httpx.AsyncClient.post')
    async def test_send_batch_with_persistence(self, mock_post, tmp_path):
        """Testa envio com persistência."""
        # Mock da resposta
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = """<?xml version="1.0"?>
        <soap:Envelope>
            <soap:Body>
                <EnviarLoteEventosResponse>
                    <protocolo>1234567890</protocolo>
                </EnviarLoteEventosResponse>
            </soap:Body>
        </soap:Envelope>
        """
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response
        
        config = ESocialConfig(target=TargetEnum.TESTS)
        storage_path = str(tmp_path / "storage")
        client = AsyncESocialClient(
            config=config,
            enable_persistence=True,
            storage_path=storage_path
        )
        
        await client.connect()
        
        events = [{'id': 'evt1', 'tipo': 'S-2200'}]
        xml_content = "<lote>...</lote>"
        
        result = await client.send_batch("batch_1", events, xml_content)
        
        assert result.success is True
        
        # Verificar persistência
        batch_state = client._persistence.load_batch("batch_1")
        assert batch_state is not None
        assert batch_state.status == 'SUCCESS'
        assert batch_state.response_data['protocolo'] == "1234567890"
        
        await client.disconnect()


@pytest.mark.asyncio
class TestAsyncClientMultipleBatches:
    """Testes de envio múltiplo concorrente."""
    
    @patch('esocial.async_client.httpx.AsyncClient.post')
    async def test_send_multiple_batches(self, mock_post):
        """Testa envio de múltiplos lotes concorrentemente."""
        # Mock da resposta
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = """<?xml version="1.0"?>
        <soap:Envelope>
            <soap:Body>
                <EnviarLoteEventosResponse>
                    <protocolo>{proto}</protocolo>
                </EnviarLoteEventosResponse>
            </soap:Body>
        </soap:Envelope>
        """
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response
        
        config = ESocialConfig(target=TargetEnum.TESTS)
        client = AsyncESocialClient(config=config, enable_persistence=False)
        
        await client.connect()
        
        batches = [
            ("batch_1", [{'id': 'evt1'}], "<lote1>"),
            ("batch_2", [{'id': 'evt2'}], "<lote2>"),
            ("batch_3", [{'id': 'evt3'}], "<lote3>"),
        ]
        
        results = await client.send_multiple_batches(batches)
        
        assert len(results) == 3
        assert all(r.success for r in results)
        
        await client.disconnect()
    
    @patch('esocial.async_client.httpx.AsyncClient.post')
    async def test_send_multiple_batches_partial_failure(self, mock_post):
        """Testa envio com falhas parciais."""
        call_count = [0]
        
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise httpx.HTTPStatusError(
                    "500 Error",
                    request=MagicMock(),
                    response=MagicMock(status_code=500)
                )
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = """<?xml version="1.0"?>
            <soap:Envelope>
                <soap:Body>
                    <EnviarLoteEventosResponse>
                        <protocolo>PROTO{}</protocolo>
                    </EnviarLoteEventosResponse>
                </soap:Body>
            </soap:Envelope>
            """.format(call_count[0])
            mock_response.raise_for_status = MagicMock()
            return mock_response
        
        mock_post.side_effect = side_effect
        
        config = ESocialConfig(target=TargetEnum.TESTS)
        client = AsyncESocialClient(config=config, enable_persistence=False)
        
        await client.connect()
        
        batches = [
            ("batch_1", [{'id': 'evt1'}], "<lote1>"),
            ("batch_2", [{'id': 'evt2'}], "<lote2>"),
            ("batch_3", [{'id': 'evt3'}], "<lote3>"),
        ]
        
        results = await client.send_multiple_batches(batches)
        
        # 2 sucessos, 1 falha
        assert len(results) == 2
        
        await client.disconnect()


@pytest.mark.asyncio
class TestAsyncClientHealthCheck:
    """Testes de health check."""
    
    async def test_health_check_disconnected(self):
        """Health check quando desconectado."""
        config = ESocialConfig(target=TargetEnum.TESTS)
        client = AsyncESocialClient(config=config)
        
        health = await client.health_check()
        
        assert health['connected'] is False
        assert health['circuit_breaker'] == 'CLOSED'
    
    async def test_health_check_connected(self):
        """Health check quando conectado."""
        config = ESocialConfig(target=TargetEnum.TESTS)
        client = AsyncESocialClient(config=config)
        
        await client.connect()
        
        health = await client.health_check()
        
        assert health['connected'] is True
        assert health['circuit_breaker'] == 'CLOSED'
        assert 'available_tokens' in health
        
        await client.disconnect()


@pytest.mark.asyncio
class TestAsyncClientFactory:
    """Testes da factory function."""
    
    @patch('esocial.async_client.open', new_callable=MagicMock)
    async def test_create_async_client(self, mock_open):
        """Testa criação via factory."""
        mock_open.return_value.__enter__.return_value.read.return_value = b'fake_pfx_data'
        
        employer = {
            'tpInsc': 1,
            'nrInsc': '12345678000199'
        }
        
        client = await create_async_client(
            pfx_file='/fake/cert.pfx',
            pfx_passw='senha',
            environment='TEST',
            employer_id=employer,
            max_connections=5
        )
        
        assert isinstance(client, AsyncESocialClient)
        assert client._connected is True
        assert client.config.is_production is False
        
        await client.disconnect()


@pytest.mark.asyncio
class TestAsyncClientRetry:
    """Testes de retry automático."""
    
    @patch('esocial.async_client.httpx.AsyncClient.post')
    async def test_retry_on_network_error(self, mock_post):
        """Testa retry em erro de rede."""
        call_count = [0]
        
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise httpx.NetworkError("Connection lost")
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = """<?xml version="1.0"?>
            <soap:Envelope>
                <soap:Body>
                    <EnviarLoteEventosResponse>
                        <protocolo>1234567890</protocolo>
                    </EnviarLoteEventosResponse>
                </soap:Body>
            </soap:Envelope>
            """
            mock_response.raise_for_status = MagicMock()
            return mock_response
        
        mock_post.side_effect = side_effect
        
        config = ESocialConfig(target=TargetEnum.TESTS)
        client = AsyncESocialClient(config=config, enable_persistence=False)
        
        await client.connect()
        
        events = [{'id': 'evt1'}]
        xml_content = "<lote>"
        
        result = await client.send_batch("batch_1", events, xml_content)
        
        # Deve ter tentado 3 vezes (2 falhas + 1 sucesso)
        assert call_count[0] == 3
        assert result.success is True
        
        await client.disconnect()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
