"""
Tests for eSocial Returns Module - S-500X Series

Comprehensive test suite for SST (Saúde e Segurança no Trabalho) return processing.
Covers parsing, validation, batch processing and audit integration.

Author: LIBeSocial Premium Team
Version: 1.0.0
"""

import pytest
from datetime import datetime
from pathlib import Path
import json
import xml.etree.ElementTree as ET

from esocial.returns import (
    SSTEventType,
    ReturnStatus,
    ErrorCode,
    ErrorInfo,
    ProcessingInfo,
    SSTEventReturn,
    BatchReturn,
    ReturnParser,
    ReturnHandler,
    ReturnHandlerConfig,
    parse_sst_return,
    parse_sst_return_file,
    process_sst_returns,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_xml_s5001() -> str:
    """Sample XML for S-5001 event return."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<retornoEvento xmlns="http://www.esocial.gov.br/schema/retornos">
    <evtExpRisco>
        <ideEvento>
            <tpEvt>S-5001</tpEvt>
            <verProc>1.0</verProc>
        </ideEvento>
        <ideEmpregador>
            <nrInsc>12345678000199</nrInsc>
        </ideEmpregador>
        <trabalhador>
            <cpfTrab>12345678901</cpfTrab>
        </trabalhador>
    </evtExpRisco>
    <procEvento>
        <codResp>0</codResp>
        <nrRecibo>12345678901234567890</nrRecibo>
        <hashRetorno>abc123def456</hashRetorno>
        <dhProcessamento>2024-01-15T10:30:00Z</dhProcessamento>
    </procEvento>
</retornoEvento>
"""


@pytest.fixture
def sample_xml_s5002() -> str:
    """Sample XML for S-5002 event return."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<retornoEvento xmlns="http://www.esocial.gov.br/schema/retornos">
    <evtBenPrRP>
        <ideEvento>
            <tpEvt>S-5002</tpEvt>
            <verProc>1.1</verProc>
        </ideEvento>
        <ideEmpregador>
            <nrInsc>98765432000188</nrInsc>
        </ideEmpregador>
        <cpfBenef>98765432109</cpfBenef>
    </evtBenPrRP>
    <procEvento>
        <codResp>0</codResp>
        <nrRecibo>98765432109876543210</nrRecibo>
        <hashRetorno>xyz789ghi012</hashRetorno>
        <dhProcessamento>2024-01-16T14:45:00Z</dhProcessamento>
    </procEvento>
</retornoEvento>
"""


@pytest.fixture
def sample_xml_s5003() -> str:
    """Sample XML for S-5003 event return."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<retornoEvento xmlns="http://www.esocial.gov.br/schema/retornos">
    <evtMonit>
        <ideEvento>
            <tpEvt>S-5003</tpEvt>
            <verProc>1.0</verProc>
        </ideEvento>
        <ideEmpregador>
            <nrInsc>11223344000155</nrInsc>
        </ideEmpregador>
        <cpfTrab>11223344556</cpfTrab>
    </evtMonit>
    <procEvento>
        <codResp>1</codResp>
        <nrRecibo></nrRecibo>
        <hashRetorno></hashRetorno>
        <dhProcessamento>2024-01-17T09:15:00Z</dhProcessamento>
    </procEvento>
    <erro>
        <codigo>504</codigo>
        <descricao>Campo obrigatório não preenchido</descricao>
        <localizacao>//trabalhador/nascto</localizacao>
    </erro>
</retornoEvento>
"""


@pytest.fixture
def sample_xml_with_errors() -> str:
    """Sample XML with multiple errors."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<retornoEvento xmlns="http://www.esocial.gov.br/schema/retornos">
    <evtExpRisco>
        <ideEvento>
            <tpEvt>S-5001</tpEvt>
            <verProc>1.0</verProc>
        </ideEvento>
        <ideEmpregador>
            <nrInsc>12345678000199</nrInsc>
        </ideEmpregador>
        <trabalhador>
            <cpfTrab>12345678901</cpfTrab>
        </trabalhador>
    </evtExpRisco>
    <procEvento>
        <codResp>1</codResp>
    </procEvento>
    <erro>
        <codigo>501</codigo>
        <descricao>CPF inválido</descricao>
    </erro>
    <erro>
        <codigo>802</codigo>
        <descricao>Dados inconsistentes</descricao>
        <localizacao>//expRisco/agenteNocivo</localizacao>
    </erro>
</retornoEvento>
"""


@pytest.fixture
def handler_config(tmp_path: Path) -> ReturnHandlerConfig:
    """Create handler config for tests."""
    audit_path = tmp_path / "audit_logs"
    audit_path.mkdir()
    
    return ReturnHandlerConfig(
        enable_audit=True,
        audit_log_path=audit_path,
        enable_notifications=False,
        persistence_enabled=True,
        persistence_path=tmp_path / "persistence",
    )


@pytest.fixture
def return_handler(handler_config: ReturnHandlerConfig) -> ReturnHandler:
    """Create return handler instance."""
    return ReturnHandler(config=handler_config)


# ============================================================================
# Tests for SSTEventType Enum
# ============================================================================

class TestSSTEventType:
    """Test SSTEventType enum functionality."""
    
    def test_event_type_values(self):
        """Test event type values."""
        assert SSTEventType.S5001.value == "S-5001"
        assert SSTEventType.S5002.value == "S-5002"
        assert SSTEventType.S5003.value == "S-5003"
    
    def test_xml_tag_mapping(self):
        """Test XML tag mapping."""
        assert SSTEventType.S5001.xml_tag == "evtExpRisco"
        assert SSTEventType.S5002.xml_tag == "evtBenPrRP"
        assert SSTEventType.S5003.xml_tag == "evtMonit"
    
    def test_description_mapping(self):
        """Test description mapping."""
        assert "Exposição" in SSTEventType.S5001.description
        assert "Proteção Previdenciária" in SSTEventType.S5002.description
        assert "Monitoramento" in SSTEventType.S5003.description
    
    def test_from_xml_tag(self):
        """Test creating event type from XML tag."""
        assert SSTEventType.from_xml_tag("evtExpRisco") == SSTEventType.S5001
        assert SSTEventType.from_xml_tag("evtBenPrRP") == SSTEventType.S5002
        assert SSTEventType.from_xml_tag("evtMonit") == SSTEventType.S5003
        assert SSTEventType.from_xml_tag("unknown") is None
    
    def test_from_event_id(self):
        """Test creating event type from event ID."""
        assert SSTEventType.from_event_id("S-5001.01.00") == SSTEventType.S5001
        assert SSTEventType.from_event_id("S-5002.02.01") == SSTEventType.S5002
        assert SSTEventType.from_event_id("S-5003.01.00") == SSTEventType.S5003
        assert SSTEventType.from_event_id("S-1000") is None


# ============================================================================
# Tests for ReturnStatus Enum
# ============================================================================

class TestReturnStatus:
    """Test ReturnStatus enum functionality."""
    
    def test_status_values(self):
        """Test status values."""
        assert ReturnStatus.SUCCESS.value == "SUCESSO"
        assert ReturnStatus.ERROR.value == "ERRO"
        assert ReturnStatus.PENDING.value == "PENDENTE"
    
    def test_is_final_property(self):
        """Test is_final property."""
        assert ReturnStatus.SUCCESS.is_final is True
        assert ReturnStatus.ERROR.is_final is True
        assert ReturnStatus.PENDING.is_final is False
        assert ReturnStatus.PROCESSING.is_final is False
    
    def test_color_code(self):
        """Test color codes for terminal display."""
        assert "\033[92m" in ReturnStatus.SUCCESS.color_code  # Green
        assert "\033[91m" in ReturnStatus.ERROR.color_code    # Red
        assert "\033[93m" in ReturnStatus.WARNING.color_code  # Yellow


# ============================================================================
# Tests for ErrorCode Enum
# ============================================================================

class TestErrorCode:
    """Test ErrorCode enum functionality."""
    
    def test_error_categories(self):
        """Test error category classification."""
        assert ErrorCode.VALIDATION_CPF_INVALID.category == "Validação"
        assert ErrorCode.PROCESSING_TIMEOUT.category == "Processamento"
        assert ErrorCode.AUTH_CERTIFICATE_EXPIRED.category == "Autorização"
        assert ErrorCode.BUSINESS_RULE_VIOLATION.category == "Regra de Negócio"
    
    def test_error_severity(self):
        """Test error severity levels."""
        assert ErrorCode.AUTH_CERTIFICATE_EXPIRED.severity == "CRÍTICO"
        assert ErrorCode.VALIDATION_CPF_INVALID.severity == "ALTO"
        assert ErrorCode.PROCESSING_TIMEOUT.severity == "MÉDIO"


# ============================================================================
# Tests for ErrorInfo Model
# ============================================================================

class TestErrorInfo:
    """Test ErrorInfo Pydantic model."""
    
    def test_create_error_info(self):
        """Test creating ErrorInfo instance."""
        error = ErrorInfo(
            code="501",
            description="CPF inválido",
            location="//trabalhador/cpfTrab",
            severity="ALTO",
        )
        assert error.code == "501"
        assert error.description == "CPF inválido"
        assert error.location == "//trabalhador/cpfTrab"
        assert error.severity == "ALTO"
    
    def test_default_severity(self):
        """Test default severity value."""
        error = ErrorInfo(code="500", description="Erro genérico")
        assert error.severity == "MÉDIO"
    
    def test_severity_normalization(self):
        """Test severity normalization to uppercase."""
        error = ErrorInfo(code="500", description="Erro", severity="baixo")
        assert error.severity == "BAIXO"


# ============================================================================
# Tests for ProcessingInfo Model
# ============================================================================

class TestProcessingInfo:
    """Test ProcessingInfo Pydantic model."""
    
    def test_create_processing_info(self):
        """Test creating ProcessingInfo instance."""
        info = ProcessingInfo(
            status=ReturnStatus.SUCCESS,
            protocol="12345678901234567890",
            receipt_number="abc123",
            processing_date=datetime(2024, 1, 15, 10, 30, 0),
        )
        assert info.status == ReturnStatus.SUCCESS
        assert info.protocol == "12345678901234567890"
        assert info.receipt_number == "abc123"
    
    def test_status_validation_from_string(self):
        """Test status validation from string."""
        info = ProcessingInfo(status="SUCESSO")
        assert info.status == ReturnStatus.SUCCESS
        
        info = ProcessingInfo(status="ERRO")
        assert info.status == ReturnStatus.ERROR
    
    def test_invalid_status_raises_error(self):
        """Test that invalid status raises ValueError."""
        with pytest.raises(ValueError, match="Invalid status"):
            ProcessingInfo(status="INVALIDO")


# ============================================================================
# Tests for SSTEventReturn Model
# ============================================================================

class TestSSTEventReturn:
    """Test SSTEventReturn Pydantic model."""
    
    def test_create_success_return(self, sample_xml_s5001: str):
        """Test creating successful return."""
        parser = ReturnParser(sample_xml_s5001)
        ret = parser.parse_sst_return()
        
        assert ret.event_type == SSTEventType.S5001
        assert ret.event_id == "S-5001"
        assert ret.worker_cpf == "12345678901"
        assert ret.employer_cnpj == "12345678000199"
        assert ret.is_success is True
        assert ret.has_errors is False
        assert ret.xml_hash is not None
    
    def test_cpf_validation(self):
        """Test CPF validation."""
        with pytest.raises(ValueError, match="CPF inválido"):
            SSTEventReturn(
                event_type=SSTEventType.S5001,
                event_id="S-5001.01.00",
                event_version="1.0",
                worker_cpf="123",  # Invalid CPF
                employer_cnpj="12345678000199",
                submission_date=datetime.now(),
                processing=ProcessingInfo(status=ReturnStatus.SUCCESS),
            )
    
    def test_cnpj_validation(self):
        """Test CNPJ validation."""
        with pytest.raises(ValueError, match="CNPJ inválido"):
            SSTEventReturn(
                event_type=SSTEventType.S5001,
                event_id="S-5001.01.00",
                event_version="1.0",
                worker_cpf="12345678901",
                employer_cnpj="12345",  # Invalid CNPJ
                submission_date=datetime.now(),
                processing=ProcessingInfo(status=ReturnStatus.SUCCESS),
            )
    
    def test_xml_hash_computation(self, sample_xml_s5001: str):
        """Test automatic XML hash computation."""
        parser = ReturnParser(sample_xml_s5001)
        ret = parser.parse_sst_return()
        
        assert ret.xml_hash is not None
        assert len(ret.xml_hash) == 64  # SHA256 hex length
    
    def test_status_display(self, sample_xml_s5001: str):
        """Test status display with color codes."""
        parser = ReturnParser(sample_xml_s5001)
        ret = parser.parse_sst_return()
        
        display = ret.status_display
        assert "SUCESSO" in display
        assert "\033[92m" in display  # Green color code
    
    def test_summary_output(self, sample_xml_s5001: str):
        """Test summary method output."""
        parser = ReturnParser(sample_xml_s5001)
        ret = parser.parse_sst_return()
        
        summary = ret.summary()
        assert "S-5001" in summary
        assert "12345678901" in summary
        assert "✅" in summary
    
    def test_to_dict(self, sample_xml_s5001: str):
        """Test conversion to dictionary."""
        parser = ReturnParser(sample_xml_s5001)
        ret = parser.parse_sst_return()
        
        data = ret.to_dict()
        assert isinstance(data, dict)
        assert "event_type" in data
        assert "worker_cpf" in data
        assert "processing" in data


# ============================================================================
# Tests for BatchReturn Model
# ============================================================================

class TestBatchReturn:
    """Test BatchReturn Pydantic model."""
    
    def test_create_batch_return(self, sample_xml_s5001: str, sample_xml_s5002: str):
        """Test creating batch return."""
        parser1 = ReturnParser(sample_xml_s5001)
        parser2 = ReturnParser(sample_xml_s5002)
        
        ret1 = parser1.parse_sst_return()
        ret2 = parser2.parse_sst_return()
        
        batch = BatchReturn(
            batch_id="batch_001",
            submission_date=datetime.now(),
            total_events=2,
            returns=[ret1, ret2],
            processing_status=ReturnStatus.SUCCESS,
        )
        
        assert batch.batch_id == "batch_001"
        assert batch.total_events == 2
        assert batch.success_count == 2
        assert batch.error_count == 0
        assert batch.success_rate == 100.0
    
    def test_mixed_status_batch(self, sample_xml_s5001: str, sample_xml_s5003: str):
        """Test batch with mixed success/error returns."""
        parser1 = ReturnParser(sample_xml_s5001)
        parser3 = ReturnParser(sample_xml_s5003)
        
        ret1 = parser1.parse_sst_return()
        ret3 = parser3.parse_sst_return()
        
        batch = BatchReturn(
            batch_id="batch_002",
            submission_date=datetime.now(),
            total_events=2,
            returns=[ret1, ret3],
        )
        
        assert batch.success_count == 1
        assert batch.error_count == 1
        assert batch.success_rate == 50.0
    
    def test_batch_summary(self, sample_xml_s5001: str):
        """Test batch summary output."""
        parser = ReturnParser(sample_xml_s5001)
        ret = parser.parse_sst_return()
        
        batch = BatchReturn(
            batch_id="batch_test",
            submission_date=datetime.now(),
            total_events=1,
            returns=[ret],
        )
        
        summary = batch.summary()
        assert "batch_test" in summary
        assert "✅ Sucesso: 1" in summary
        assert "Taxa de Sucesso: 100.0%" in summary


# ============================================================================
# Tests for ReturnParser
# ============================================================================

class TestReturnParser:
    """Test ReturnParser functionality."""
    
    def test_parse_s5001_return(self, sample_xml_s5001: str):
        """Test parsing S-5001 return."""
        parser = ReturnParser(sample_xml_s5001)
        ret = parser.parse_sst_return()
        
        assert ret.event_type == SSTEventType.S5001
        assert ret.event_id == "S-5001"
        assert ret.event_version == "1.0"
        assert ret.worker_cpf == "12345678901"
        assert ret.employer_cnpj == "12345678000199"
        assert ret.is_success is True
        assert ret.processing.protocol == "12345678901234567890"
    
    def test_parse_s5002_return(self, sample_xml_s5002: str):
        """Test parsing S-5002 return."""
        parser = ReturnParser(sample_xml_s5002)
        ret = parser.parse_sst_return()
        
        assert ret.event_type == SSTEventType.S5002
        assert ret.worker_cpf == "98765432109"
        assert ret.employer_cnpj == "98765432000188"
    
    def test_parse_s5003_return_with_errors(self, sample_xml_s5003: str):
        """Test parsing S-5003 return with errors."""
        parser = ReturnParser(sample_xml_s5003)
        ret = parser.parse_sst_return()
        
        assert ret.event_type == SSTEventType.S5003
        assert ret.is_success is False
        assert ret.has_errors is True
        assert len(ret.errors) == 1
        assert ret.errors[0].code == "504"
    
    def test_parse_return_with_multiple_errors(self, sample_xml_with_errors: str):
        """Test parsing return with multiple errors."""
        parser = ReturnParser(sample_xml_with_errors)
        ret = parser.parse_sst_return()
        
        assert len(ret.errors) == 2
        assert ret.errors[0].code == "501"
        assert ret.errors[1].code == "802"
        assert ret.errors[1].location == "//expRisco/agenteNocivo"
    
    def test_parse_invalid_xml(self):
        """Test parsing invalid XML raises error."""
        with pytest.raises(ValueError, match="XML inválido"):
            parser = ReturnParser("<xml>invalid</xml>")
            parser.parse_sst_return()
    
    def test_parse_unsupported_event_type(self):
        """Test parsing unsupported event type raises error."""
        xml = """<?xml version="1.0"?>
        <retornoEvento>
            <evtUnknown>
                <ideEvento><tpEvt>S-9999</tpEvt></ideEvento>
            </evtUnknown>
        </retornoEvento>
        """
        with pytest.raises(ValueError, match="não suportado"):
            parser = ReturnParser(xml)
            parser.parse_sst_return()
    
    def test_from_file(self, sample_xml_s5001: str, tmp_path: Path):
        """Test parsing from file."""
        xml_file = tmp_path / "return.xml"
        xml_file.write_text(sample_xml_s5001)
        
        parser = ReturnParser.from_file(xml_file)
        ret = parser.parse_sst_return()
        
        assert ret.event_type == SSTEventType.S5001
    
    def test_from_nonexistent_file(self, tmp_path: Path):
        """Test parsing from nonexistent file raises error."""
        nonexistent = tmp_path / "nonexistent.xml"
        
        with pytest.raises(FileNotFoundError):
            ReturnParser.from_file(nonexistent)


# ============================================================================
# Tests for ReturnHandler
# ============================================================================

class TestReturnHandler:
    """Test ReturnHandler functionality."""
    
    def test_process_single_return(self, return_handler: ReturnHandler, sample_xml_s5001: str):
        """Test processing single return."""
        ret = return_handler.process_return(sample_xml_s5001)
        
        assert ret.event_type == SSTEventType.S5001
        assert ret.is_success is True
        
        # Check stored in handler
        key = f"{ret.event_type.value}:{ret.event_id}:{ret.worker_cpf}"
        assert key in return_handler.processed_returns
    
    def test_process_batch_return(self, return_handler: ReturnHandler, sample_xml_s5001: str, sample_xml_s5002: str):
        """Test processing batch of returns."""
        batch = return_handler.process_batch_return(
            batch_id="test_batch",
            xml_contents=[sample_xml_s5001, sample_xml_s5002],
        )
        
        assert batch.batch_id == "test_batch"
        assert batch.total_events == 2
        assert batch.success_count == 2
        assert batch.processing_status == ReturnStatus.SUCCESS
        
        # Check stored in handler
        assert "test_batch" in return_handler.batch_returns
    
    def test_query_returns_by_event_type(self, return_handler: ReturnHandler, sample_xml_s5001: str, sample_xml_s5002: str):
        """Test querying returns by event type."""
        return_handler.process_return(sample_xml_s5001)
        return_handler.process_return(sample_xml_s5002)
        
        s5001_returns = return_handler.query_returns(event_type=SSTEventType.S5001)
        assert len(s5001_returns) == 1
        assert s5001_returns[0].event_type == SSTEventType.S5001
    
    def test_query_returns_by_status(self, return_handler: ReturnHandler, sample_xml_s5001: str, sample_xml_s5003: str):
        """Test querying returns by status."""
        return_handler.process_return(sample_xml_s5001)
        return_handler.process_return(sample_xml_s5003)
        
        success_returns = return_handler.query_returns(status=ReturnStatus.SUCCESS)
        error_returns = return_handler.query_returns(status=ReturnStatus.ERROR)
        
        assert len(success_returns) == 1
        assert len(error_returns) == 1
    
    def test_query_returns_by_cpf(self, return_handler: ReturnHandler, sample_xml_s5001: str):
        """Test querying returns by CPF."""
        return_handler.process_return(sample_xml_s5001)
        
        returns = return_handler.query_returns(worker_cpf="123.456.789-01")
        assert len(returns) == 1
        
        # Test with formatted CPF
        returns = return_handler.query_returns(worker_cpf="12345678901")
        assert len(returns) == 1
    
    def test_query_returns_by_date_range(self, return_handler: ReturnHandler, sample_xml_s5001: str):
        """Test querying returns by date range."""
        return_handler.process_return(sample_xml_s5001)
        
        now = datetime.now()
        returns = return_handler.query_returns(
            date_from=now.replace(hour=0, minute=0, second=0),
            date_to=now.replace(hour=23, minute=59, second=59),
        )
        assert len(returns) >= 1
    
    def test_export_to_json(self, return_handler: ReturnHandler, sample_xml_s5001: str, tmp_path: Path):
        """Test exporting returns to JSON."""
        return_handler.process_return(sample_xml_s5001)
        
        output_file = tmp_path / "returns.json"
        return_handler.export_to_json(output_file)
        
        assert output_file.exists()
        
        with open(output_file, "r") as f:
            data = json.load(f)
        
        assert "export_date" in data
        assert "total_returns" in data
        assert "returns" in data
        assert data["total_returns"] == 1
    
    def test_get_return_by_key(self, return_handler: ReturnHandler, sample_xml_s5001: str):
        """Test getting return by key."""
        ret = return_handler.process_return(sample_xml_s5001)
        
        key = f"{ret.event_type.value}:{ret.event_id}:{ret.worker_cpf}"
        retrieved = return_handler.get_return(key)
        
        assert retrieved is not None
        assert retrieved.worker_cpf == ret.worker_cpf
    
    def test_get_batch_by_id(self, return_handler: ReturnHandler, sample_xml_s5001: str):
        """Test getting batch by ID."""
        return_handler.process_batch_return("test_batch", [sample_xml_s5001])
        
        batch = return_handler.get_batch("test_batch")
        
        assert batch is not None
        assert batch.batch_id == "test_batch"


# ============================================================================
# Tests for Convenience Functions
# ============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_parse_sst_return(self, sample_xml_s5001: str):
        """Test parse_sst_return function."""
        ret = parse_sst_return(sample_xml_s5001)
        
        assert isinstance(ret, SSTEventReturn)
        assert ret.event_type == SSTEventType.S5001
    
    def test_parse_sst_return_file(self, sample_xml_s5001: str, tmp_path: Path):
        """Test parse_sst_return_file function."""
        xml_file = tmp_path / "return.xml"
        xml_file.write_text(sample_xml_s5001)
        
        ret = parse_sst_return_file(xml_file)
        
        assert isinstance(ret, SSTEventReturn)
        assert ret.event_type == SSTEventType.S5001
    
    def test_process_sst_returns(self, sample_xml_s5001: str, sample_xml_s5002: str):
        """Test process_sst_returns function."""
        batch = process_sst_returns(
            xml_contents=[sample_xml_s5001, sample_xml_s5002],
            batch_id="func_test_batch",
        )
        
        assert isinstance(batch, BatchReturn)
        assert batch.batch_id == "func_test_batch"
        assert batch.total_events == 2


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for returns module."""
    
    def test_full_workflow(self, return_handler: ReturnHandler, sample_xml_s5001: str, sample_xml_s5002: str, sample_xml_s5003: str):
        """Test complete workflow: parse, process, query, export."""
        # Process returns
        ret1 = return_handler.process_return(sample_xml_s5001)
        ret2 = return_handler.process_return(sample_xml_s5002)
        ret3 = return_handler.process_return(sample_xml_s5003)
        
        # Query by status
        success_returns = return_handler.query_returns(status=ReturnStatus.SUCCESS)
        error_returns = return_handler.query_returns(status=ReturnStatus.ERROR)
        
        assert len(success_returns) == 2
        assert len(error_returns) == 1
        
        # Export to JSON
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            output_path = Path(f.name)
        
        return_handler.export_to_json(output_path)
        
        assert output_path.exists()
        assert output_path.stat().st_size > 0
        
        # Cleanup
        output_path.unlink()
    
    def test_error_handling_in_batch(self, return_handler: ReturnHandler):
        """Test error handling when processing batch with invalid XML."""
        valid_xml = """<?xml version="1.0"?>
        <retornoEvento xmlns="http://www.esocial.gov.br/schema/retornos">
            <evtExpRisco>
                <ideEvento><tpEvt>S-5001</tpEvt><verProc>1.0</verProc></ideEvento>
                <ideEmpregador><nrInsc>12345678000199</nrInsc></ideEmpregador>
                <trabalhador><cpfTrab>12345678901</cpfTrab></trabalhador>
            </evtExpRisco>
            <procEvento><codResp>0</codResp></procEvento>
        </retornoEvento>
        """
        
        invalid_xml = "<xml>totally invalid</xml>"
        
        batch = return_handler.process_batch_return(
            batch_id="error_test",
            xml_contents=[valid_xml, invalid_xml],
        )
        
        assert batch.total_events == 2
        assert batch.success_count == 1
        assert batch.error_count == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
