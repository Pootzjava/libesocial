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
"""Tests for eSocial Premium Models

FASE 1: Type hints + Pydantic models validation
"""
import pytest
from datetime import datetime
from esocial.models import (
    EmployerIdentification,
    SenderIdentification,
    CertificateConfig,
    BatchConfig,
    EventInfo,
    BatchState,
    DLQEntry,
    ESocialConfig,
    WebServiceURLs,
    SendResult,
    HealthStatus,
    TargetEnum,
    BatchStatusEnum,
)


class TestEmployerIdentification:
    """Testes para modelo EmployerIdentification."""
    
    def test_create_valid_cnpj(self):
        """Cria empregador com CNPJ válido."""
        emp = EmployerIdentification(tpInsc=1, nrInsc='12345678000195')
        assert emp.tpInsc == 1
        assert emp.nrInsc == '12345678000195'
        assert emp.use_full is False
    
    def test_create_valid_cpf(self):
        """Cria empregador com CPF válido."""
        emp = EmployerIdentification(tpInsc=2, nrInsc='12345678901')
        assert emp.tpInsc == 2
        assert emp.nrInsc == '12345678901'
    
    def test_clean_formatting_cnpj(self):
        """Limpa formatação de CNPJ."""
        emp = EmployerIdentification(tpInsc=1, nrInsc='12.345.678/0001-95')
        assert emp.nrInsc == '12345678000195'
    
    def test_clean_formatting_cpf(self):
        """Limpa formatação de CPF."""
        emp = EmployerIdentification(tpInsc=2, nrInsc='123.456.789-01')
        assert emp.nrInsc == '12345678901'
    
    def test_get_nrinsc_short_cnpj(self):
        """Retorna CNPJ curto (8 primeiros dígitos)."""
        emp = EmployerIdentification(tpInsc=1, nrInsc='12345678000195')
        assert emp.get_nrinsc_short() == '12345678'
    
    def test_get_nrinsc_short_cnpj_full(self):
        """Retorna CNPJ completo quando use_full=True."""
        emp = EmployerIdentification(tpInsc=1, nrInsc='12345678000195', use_full=True)
        assert emp.get_nrinsc_short() == '12345678000195'
    
    def test_get_nrinsc_short_cpf(self):
        """Retorna CPF completo sempre."""
        emp = EmployerIdentification(tpInsc=2, nrInsc='12345678901')
        assert emp.get_nrinsc_short() == '12345678901'
    
    def test_invalid_tpinsc(self):
        """Rejeita tpInsc inválido."""
        with pytest.raises(ValueError) as exc_info:
            EmployerIdentification(tpInsc=3, nrInsc='12345678000195')
        assert 'tpInsc deve ser 1 (CNPJ) ou 2 (CPF)' in str(exc_info.value)
    
    def test_invalid_nrinsc_letters(self):
        """Rejeita nrInsc com letras."""
        with pytest.raises(ValueError) as exc_info:
            EmployerIdentification(tpInsc=1, nrInsc='12345678ABCD95')
        assert 'nrInsc deve conter apenas dígitos' in str(exc_info.value)


class TestSenderIdentification:
    """Testes para modelo SenderIdentification."""
    
    def test_create_valid_sender(self):
        """Cria transmissor válido."""
        sender = SenderIdentification(tpInsc=1, nrInsc='98765432000100')
        assert sender.tpInsc == 1
        assert sender.nrInsc == '98765432000100'
    
    def test_invalid_tpinsc(self):
        """Rejeita tpInsc inválido."""
        with pytest.raises(ValueError):
            SenderIdentification(tpInsc=3, nrInsc='98765432000100')


class TestCertificateConfig:
    """Testes para modelo CertificateConfig."""
    
    def test_create_with_pfx_file(self):
        """Cria config com arquivo PFX."""
        cert = CertificateConfig(
            pfx_file='/path/to/cert.pfx',
            pfx_password='senha123'
        )
        assert cert.pfx_file == '/path/to/cert.pfx'
        assert cert.pfx_password == 'senha123'
    
    def test_create_without_pfx_file(self):
        """Cria config sem arquivo PFX (cert_data inline)."""
        cert = CertificateConfig(pfx_password='senha123')
        assert cert.pfx_file is None
        assert cert.pfx_password == 'senha123'


class TestBatchConfig:
    """Testes para modelo BatchConfig."""
    
    def test_default_values(self):
        """Valores padrão corretos."""
        config = BatchConfig()
        assert config.max_batch_size == 50
        assert config.group_id == 1
        assert config.clear_after_send is True
    
    def test_custom_values(self):
        """Valores customizados."""
        config = BatchConfig(max_batch_size=30, group_id=2)
        assert config.max_batch_size == 30
        assert config.group_id == 2
    
    def test_max_batch_size_limit(self):
        """Respeita limite máximo de batch size."""
        with pytest.raises(Exception):  # pydantic ValidationError
            BatchConfig(max_batch_size=51)
    
    def test_min_batch_size_limit(self):
        """Respeita limite mínimo de batch size."""
        with pytest.raises(Exception):
            BatchConfig(max_batch_size=0)


class TestEventInfo:
    """Testes para modelo EventInfo."""
    
    def test_create_event_info(self):
        """Cria informações de evento."""
        event = EventInfo(event_id='ID123', event_type='S-1000')
        assert event.event_id == 'ID123'
        assert event.event_type == 'S-1000'
        assert event.status == 'PENDING'
        assert isinstance(event.created_at, datetime)
        assert event.sent_at is None
        assert event.error is None


class TestBatchState:
    """Testes para modelo BatchState."""
    
    def test_create_batch_state(self):
        """Cria estado de lote."""
        batch = BatchState(batch_id='batch_1_123')
        assert batch.batch_id == 'batch_1_123'
        assert batch.status == BatchStatusEnum.PENDING
        assert batch.events == []
        assert batch.retry_count == 0
    
    def test_add_event(self):
        """Adiciona evento ao lote."""
        batch = BatchState(batch_id='batch_1_123')
        event = EventInfo(event_id='ID123', event_type='S-1000')
        batch.add_event(event)
        assert len(batch.events) == 1
        assert batch.events[0].event_id == 'ID123'
    
    def test_mark_success(self):
        """Marca lote como sucesso."""
        batch = BatchState(batch_id='batch_1_123')
        batch.mark_success(protocol='1.2.3.4.5')
        assert batch.status == BatchStatusEnum.SUCCESS
        assert batch.protocol == '1.2.3.4.5'
        assert batch.sent_at is not None
    
    def test_mark_failed(self):
        """Marca lote como falho."""
        batch = BatchState(batch_id='batch_1_123')
        batch.mark_failed(error='Connection timeout')
        assert batch.status == BatchStatusEnum.FAILED
        assert batch.last_error == 'Connection timeout'


class TestDLQEntry:
    """Testes para modelo Dead Letter Queue Entry."""
    
    def test_create_dlq_entry(self):
        """Cria entrada na DLQ."""
        entry = DLQEntry(
            event_id='ID123',
            event_type='S-1000',
            error_message='Validation failed'
        )
        assert entry.event_id == 'ID123'
        assert entry.event_type == 'S-1000'
        assert entry.error_message == 'Validation failed'
        assert entry.retry_count == 0
        assert entry.context == {}


class TestESocialConfig:
    """Testes para modelo ESocialConfig."""
    
    def test_default_config(self):
        """Configuração padrão."""
        cfg = ESocialConfig()
        assert cfg.target == TargetEnum.TESTS
        assert cfg.esocial_version == 'S-1.0'
        assert cfg.enable_persistence is True
        assert cfg.storage_path == './esocial_storage'
        assert cfg.timeout_seconds == 30
        assert cfg.max_retries == 3
    
    def test_is_production(self):
        """Verifica se é produção."""
        cfg_test = ESocialConfig()
        assert cfg_test.is_tests is True
        assert cfg_test.is_production is False
        
        cfg_prod = ESocialConfig(target=TargetEnum.PRODUCTION)
        assert cfg_prod.is_production is True
        assert cfg_prod.is_tests is False
    
    def test_config_with_employer(self):
        """Configuração com empregador."""
        employer = EmployerIdentification(tpInsc=1, nrInsc='12345678000195')
        cfg = ESocialConfig(employer_id=employer)
        assert cfg.employer_id is not None
        assert cfg.employer_id.tpInsc == 1


class TestWebServiceURLs:
    """Testes para modelo WebServiceURLs."""
    
    def test_get_test_urls(self):
        """Obtém URLs de teste."""
        urls = WebServiceURLs.get_urls(TargetEnum.TESTS)
        assert 'producaorestrita' in urls.send
        assert 'producaorestrita' in urls.retrieve
    
    def test_get_production_urls(self):
        """Obtém URLs de produção."""
        urls = WebServiceURLs.get_urls(TargetEnum.PRODUCTION)
        assert 'envio' in urls.send or 'consulta' in urls.retrieve


class TestSendResult:
    """Testes para modelo SendResult."""
    
    def test_create_success_result(self):
        """Cria resultado de envio bem-sucedido."""
        result = SendResult(
            success=True,
            batch_id='batch_1_123',
            protocol='1.2.3.4.5',
            duration_seconds=2.5,
            events_sent=10
        )
        assert result.success is True
        assert result.protocol == '1.2.3.4.5'
        assert result.duration_seconds == 2.5
        assert result.events_sent == 10
        assert result.error is None
    
    def test_create_failed_result(self):
        """Cria resultado de envio falho."""
        result = SendResult(
            success=False,
            batch_id='batch_1_123',
            error='Connection timeout',
            events_sent=0
        )
        assert result.success is False
        assert result.error == 'Connection timeout'
        assert result.protocol is None


class TestHealthStatus:
    """Testes para modelo HealthStatus."""
    
    def test_create_healthy_status(self):
        """Cria status saudável."""
        health = HealthStatus(
            healthy=True,
            version='1.0.0',
            target='tests'
        )
        assert health.healthy is True
        assert health.version == '1.0.0'
        assert health.target == 'tests'
        assert health.errors == []
    
    def test_create_unhealthy_status(self):
        """Cria status não saudável."""
        health = HealthStatus(
            healthy=False,
            errors=['Database connection failed', 'API timeout']
        )
        assert health.healthy is False
        assert len(health.errors) == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
