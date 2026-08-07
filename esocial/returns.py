"""
eSocial Returns Module - S-500X Series (Occupational Health & Safety)

Specialized module for handling eSocial returns related to occupational health 
and safety events (S-5001, S-5002, S-5003). Provides parsing, validation, 
tracking and compliance features for SST (Saúde e Segurança no Trabalho) events.

Author: LIBeSocial Premium Team
Version: 1.0.0
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, ValidationError, validator

from .models import EventStatus, EventType


logger = logging.getLogger(__name__)


class SSTEventType(str, Enum):
    """Enum for S-500X series event types."""
    
    S5001 = "S-5001"  # Evento de Exposição a Agentes Nocivos
    S5002 = "S-5002"  # Registro de Eventos de Proteção Previdenciária
    S5003 = "S-5003"  # Monitoramento da Saúde do Trabalhador
    
    @property
    def xml_tag(self) -> str:
        """Return the XML tag name for this event type."""
        mapping = {
            self.S5001: "evtExpRisco",
            self.S5002: "evtBenPrRP",
            self.S5003: "evtMonit",
        }
        return mapping.get(self, "")
    
    @property
    def description(self) -> str:
        """Return human-readable description."""
        mapping = {
            self.S5001: "Evento de Exposição a Agentes Nocivos",
            self.S5002: "Registro de Eventos de Proteção Previdenciária",
            self.S5003: "Monitoramento da Saúde do Trabalhador",
        }
        return mapping.get(self, "Evento SST Desconhecido")
    
    @classmethod
    def from_xml_tag(cls, xml_tag: str) -> Optional["SSTEventType"]:
        """Get event type from XML tag."""
        reverse_mapping = {
            "evtExpRisco": cls.S5001,
            "evtBenPrRP": cls.S5002,
            "evtMonit": cls.S5003,
        }
        return reverse_mapping.get(xml_tag)
    
    @classmethod
    def from_event_id(cls, event_id: str) -> Optional["SSTEventType"]:
        """Get event type from event ID (e.g., 'S-5001.01.00')."""
        if event_id.startswith("S-5001"):
            return cls.S5001
        elif event_id.startswith("S-5002"):
            return cls.S5002
        elif event_id.startswith("S-5003"):
            return cls.S5003
        return None


class ReturnStatus(str, Enum):
    """Status of eSocial return processing."""
    
    SUCCESS = "SUCESSO"
    ERROR = "ERRO"
    WARNING = "ADVERTENCIA"
    PENDING = "PENDENTE"
    PROCESSING = "EM_PROCESSAMENTO"
    
    @property
    def is_final(self) -> bool:
        """Check if status is final (no further processing expected)."""
        return self in [self.SUCCESS, self.ERROR]
    
    @property
    def color_code(self) -> str:
        """Return ANSI color code for terminal display."""
        mapping = {
            self.SUCCESS: "\033[92m",  # Green
            self.ERROR: "\033[91m",    # Red
            self.WARNING: "\033[93m",  # Yellow
            self.PENDING: "\033[94m",  # Blue
            self.PROCESSING: "\033[96m",  # Cyan
        }
        return mapping.get(self, "\033[0m")


class ErrorCode(str, Enum):
    """Common error codes for eSocial returns."""
    
    # Validation Errors (5xx)
    VALIDATION_CPF_INVALID = "501"
    VALIDATION_CNPJ_INVALID = "502"
    VALIDATION_DATE_FORMAT = "503"
    VALIDATION_MISSING_FIELD = "504"
    VALIDATION_DUPLICATE_EVENT = "505"
    
    # Processing Errors (6xx)
    PROCESSING_TIMEOUT = "601"
    PROCESSING_SYSTEM_ERROR = "602"
    PROCESSING_DATABASE_ERROR = "603"
    
    # Authorization Errors (7xx)
    AUTH_CERTIFICATE_EXPIRED = "701"
    AUTH_CERTIFICATE_REVOKED = "702"
    AUTH_PERMISSION_DENIED = "703"
    AUTH_SIGNATURE_INVALID = "704"
    
    # Business Rule Errors (8xx)
    BUSINESS_RULE_VIOLATION = "801"
    BUSINESS_INCONSISTENT_DATA = "802"
    BUSINESS_DEADLINE_EXCEEDED = "803"
    
    @property
    def category(self) -> str:
        """Return error category based on code prefix."""
        if self.value.startswith("5"):
            return "Validação"
        elif self.value.startswith("6"):
            return "Processamento"
        elif self.value.startswith("7"):
            return "Autorização"
        elif self.value.startswith("8"):
            return "Regra de Negócio"
        return "Desconhecido"
    
    @property
    def severity(self) -> str:
        """Return error severity level."""
        if self.value.startswith("7"):
            return "CRÍTICO"
        elif self.value.startswith("5") or self.value.startswith("8"):
            return "ALTO"
        return "MÉDIO"


# ============================================================================
# Pydantic Models for S-500X Returns
# ============================================================================

class ErrorInfo(BaseModel):
    """Information about a specific error in return."""
    
    code: str = Field(..., description="Error code")
    description: str = Field(..., description="Error description")
    location: Optional[str] = Field(None, description="XML location of error")
    severity: str = Field(default="MÉDIO", description="Error severity")
    category: Optional[str] = Field(None, description="Error category")
    
    class Config:
        use_enum_values = True
    
    @validator("severity", pre=True, always=True)
    def validate_severity(cls, v: Any) -> str:
        """Validate and normalize severity."""
        if isinstance(v, str):
            return v.upper()
        return "MÉDIO"


class ProcessingInfo(BaseModel):
    """Processing information from return."""
    
    status: ReturnStatus = Field(..., description="Processing status")
    protocol: Optional[str] = Field(None, description="Protocol number")
    receipt_number: Optional[str] = Field(None, description="Receipt number")
    processing_date: Optional[datetime] = Field(None, description="Processing date")
    hash_return: Optional[str] = Field(None, description="Hash of return")
    
    @validator("status", pre=True)
    def validate_status(cls, v: Any) -> ReturnStatus:
        """Validate and normalize status."""
        if isinstance(v, ReturnStatus):
            return v
        if isinstance(v, str):
            v = v.upper()
            # Handle common variations
            v = v.replace("Ç", "C").replace("Ã", "A")
            for status in ReturnStatus:
                if status.value == v or status.name == v:
                    return status
        raise ValueError(f"Invalid status: {v}")


class SSTEventReturn(BaseModel):
    """Return model for S-500X series events."""
    
    event_type: SSTEventType = Field(..., description="Event type (S-5001, S-5002, S-5003)")
    event_id: str = Field(..., description="Event ID (e.g., S-5001.01.00)")
    event_version: str = Field(..., description="Event version")
    worker_cpf: str = Field(..., description="Worker CPF")
    employer_cnpj: str = Field(..., description="Employer CNPJ")
    submission_date: datetime = Field(..., description="Submission date")
    
    processing: ProcessingInfo = Field(..., description="Processing information")
    errors: List[ErrorInfo] = Field(default_factory=list, description="List of errors")
    warnings: List[ErrorInfo] = Field(default_factory=list, description="List of warnings")
    
    xml_content: Optional[str] = Field(None, description="Original XML content")
    xml_hash: Optional[str] = Field(None, description="SHA256 hash of XML")
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.now, description="Record creation time")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update time")
    
    class Config:
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            SSTEventType: lambda v: v.value,
            ReturnStatus: lambda v: v.value,
        }
    
    @validator("worker_cpf")
    def validate_cpf(cls, v: str) -> str:
        """Validate CPF format."""
        v = v.strip().replace(".", "").replace("-", "")
        if len(v) != 11 or not v.isdigit():
            raise ValueError("CPF inválido: deve conter 11 dígitos")
        return v
    
    @validator("employer_cnpj")
    def validate_cnpj(cls, v: str) -> str:
        """Validate CNPJ format."""
        v = v.strip().replace(".", "").replace("/", "").replace("-", "")
        if len(v) != 14 or not v.isdigit():
            raise ValueError("CNPJ inválido: deve conter 14 dígitos")
        return v
    
    @validator("xml_hash", pre=True, always=True)
    def compute_xml_hash(cls, v: Any, values: Dict[str, Any]) -> Optional[str]:
        """Compute SHA256 hash of XML content if provided."""
        if v:
            return v
        xml_content = values.get("xml_content")
        if xml_content:
            return hashlib.sha256(xml_content.encode()).hexdigest()
        return None
    
    @property
    def is_success(self) -> bool:
        """Check if processing was successful."""
        return self.processing.status == ReturnStatus.SUCCESS
    
    @property
    def has_errors(self) -> bool:
        """Check if return has errors."""
        return len(self.errors) > 0
    
    @property
    def has_warnings(self) -> bool:
        """Check if return has warnings."""
        return len(self.warnings) > 0
    
    @property
    def status_display(self) -> str:
        """Return formatted status for display."""
        color = self.processing.status.color_code
        reset = "\033[0m"
        return f"{color}{self.processing.status.value}{reset}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return self.dict()
    
    def summary(self) -> str:
        """Return human-readable summary."""
        status_icon = "✅" if self.is_success else "❌" if self.has_errors else "⚠️"
        return (
            f"{status_icon} {self.event_type.value} - {self.event_id}\n"
            f"   CPF: {self.worker_cpf}\n"
            f"   CNPJ: {self.employer_cnpj}\n"
            f"   Status: {self.processing.status.value}\n"
            f"   Erros: {len(self.errors)}\n"
            f"   Alertas: {len(self.warnings)}"
        )


class BatchReturn(BaseModel):
    """Return model for batch processing of S-500X events."""
    
    batch_id: str = Field(..., description="Batch identifier")
    submission_date: datetime = Field(..., description="Batch submission date")
    total_events: int = Field(..., description="Total events in batch")
    
    returns: List[SSTEventReturn] = Field(default_factory=list, description="Individual returns")
    
    processing_status: ReturnStatus = Field(ReturnStatus.PENDING, description="Overall batch status")
    protocol: Optional[str] = Field(None, description="Batch protocol number")
    
    class Config:
        use_enum_values = True
    
    @property
    def success_count(self) -> int:
        """Count successful returns."""
        return sum(1 for r in self.returns if r.is_success)
    
    @property
    def error_count(self) -> int:
        """Count returns with errors."""
        return sum(1 for r in self.returns if r.has_errors)
    
    @property
    def warning_count(self) -> int:
        """Count returns with warnings only."""
        return sum(1 for r in self.returns if r.has_warnings and not r.has_errors)
    
    @property
    def pending_count(self) -> int:
        """Count pending returns."""
        return sum(
            1 for r in self.returns 
            if r.processing.status in [ReturnStatus.PENDING, ReturnStatus.PROCESSING]
        )
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_events == 0:
            return 0.0
        return (self.success_count / self.total_events) * 100
    
    def summary(self) -> str:
        """Return batch summary."""
        return (
            f"📦 Lote: {self.batch_id}\n"
            f"   Total: {self.total_events}\n"
            f"   ✅ Sucesso: {self.success_count}\n"
            f"   ❌ Erros: {self.error_count}\n"
            f"   ⚠️ Alertas: {self.warning_count}\n"
            f"   ⏳ Pendentes: {self.pending_count}\n"
            f"   📊 Taxa de Sucesso: {self.success_rate:.1f}%"
        )


# ============================================================================
# Return Parser
# ============================================================================

class ReturnParser:
    """Parser for eSocial XML returns, specialized for S-500X events."""
    
    def __init__(self, xml_content: str):
        self.xml_content = xml_content
        self.root = None
        self._parse_xml()
    
    def _parse_xml(self) -> None:
        """Parse XML content."""
        try:
            import xml.etree.ElementTree as ET
            self.root = ET.fromstring(self.xml_content)
        except ET.ParseError as e:
            logger.error(f"Failed to parse XML: {e}")
            raise ValueError(f"XML inválido: {e}")
    
    def _find_element(self, path: str, namespace: Optional[Dict[str, str]] = None) -> Optional[Any]:
        """Find XML element by path."""
        if self.root is None:
            return None
        
        # Default namespaces for eSocial returns
        ns = namespace or {
            "ns": "http://www.esocial.gov.br/schema/retornos",
        }
        
        try:
            # Try with namespace first
            element = self.root.find(path, namespaces=ns)
            if element is not None:
                return element
            
            # Try without namespace (some returns may not use it)
            element = self.root.find(path.replace("{http://www.esocial.gov.br/schema/retornos}", ""))
            return element
        except Exception as e:
            logger.debug(f"Error finding element {path}: {e}")
            return None
    
    def _get_text(self, element: Any, path: str, default: str = "") -> str:
        """Get text content of child element."""
        if element is None:
            return default
        
        # Try with namespace
        ns = {"ns": "http://www.esocial.gov.br/schema/retornos"}
        child = element.find(f"ns:{path}" if not path.startswith("ns:") else path, namespaces=ns)
        
        # Try without namespace if not found
        if child is None:
            child = element.find(path)
        
        # Try direct tag match
        if child is None:
            for elem in element:
                tag_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                if tag_name == path:
                    child = elem
                    break
        
        if child is not None and child.text:
            return child.text.strip()
        return default
    
    def parse_sst_return(self) -> SSTEventReturn:
        """Parse S-500X return from XML."""
        # Extract basic info - try multiple namespace approaches
        event_type_elem = None
        
        # Try with default namespace
        for tag in ["evtExpRisco", "evtBenPrRP", "evtMonit"]:
            event_type_elem = self._find_element(f".//{tag}")
            if event_type_elem is not None:
                break
            
            # Try without namespace prefix
            event_type_elem = self._find_element(f".//{{http://www.esocial.gov.br/schema/retornos}}{tag}")
            if event_type_elem is not None:
                break
        
        if event_type_elem is None:
            # Last resort: search by tag name only
            for elem in self.root.iter():
                tag_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                if tag_name in ["evtExpRisco", "evtBenPrRP", "evtMonit"]:
                    event_type_elem = elem
                    break
        
        if event_type_elem is None:
            raise ValueError("Não foi possível identificar o tipo de evento SST no XML")
        
        xml_tag = event_type_elem.tag.split("}")[-1] if "}" in event_type_elem.tag else event_type_elem.tag
        event_type = SSTEventType.from_xml_tag(xml_tag)
        
        if event_type is None:
            raise ValueError(f"Tipo de evento SST não suportado: {xml_tag}")
        
        # Extract event ID and version
        ide_evento = self._find_element(".//ideEvento")
        if ide_evento is None:
            # Search by iterating
            for elem in self.root.iter():
                tag_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                if tag_name == "ideEvento":
                    ide_evento = elem
                    break
        
        event_id = self._get_text(ide_evento, "tpEvt", "S-5000") if ide_evento is not None else "S-5000"
        event_version = self._get_text(ide_evento, "verProc", "1.0") if ide_evento is not None else "1.0"
        
        # Extract employer info
        ide_empregador = self._find_element(".//ideEmpregador")
        if ide_empregador is None:
            for elem in self.root.iter():
                tag_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                if tag_name == "ideEmpregador":
                    ide_empregador = elem
                    break
        
        employer_cnpj = self._get_text(ide_empregador, "nrInsc", "") if ide_empregador is not None else ""
        
        # Try different paths for CPF
        worker_cpf = ""
        for cpf_path in ["cpfTrab", "cpfBenef"]:
            worker_cpf = self._get_text(self.root, cpf_path)
            if worker_cpf:
                break
        
        # If still not found, search iteratively
        if not worker_cpf:
            for elem in self.root.iter():
                tag_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                if tag_name in ["cpfTrab", "cpfBenef"] and elem.text:
                    worker_cpf = elem.text.strip()
                    break
        
        # Extract processing info
        proc_info = self._find_element(".//procEvento")
        if proc_info is None:
            for elem in self.root.iter():
                tag_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                if tag_name == "procEvento":
                    proc_info = elem
                    break
        
        status_text = self._get_text(proc_info, "codResp", "PENDENTE") if proc_info is not None else "PENDENTE"
        status = ReturnStatus.SUCCESS if status_text == "0" else ReturnStatus.ERROR
        
        protocol = self._get_text(proc_info, "nrRecibo", "") if proc_info is not None else ""
        receipt = self._get_text(proc_info, "hashRetorno", "") if proc_info is not None else ""
        
        processing_date_str = self._get_text(proc_info, "dhProcessamento", "") if proc_info is not None else ""
        processing_date = None
        if processing_date_str:
            try:
                processing_date = datetime.fromisoformat(processing_date_str.replace("Z", "+00:00"))
            except ValueError:
                pass
        
        # Extract errors
        errors = []
        error_elems = self.root.findall(".//{http://www.esocial.gov.br/schema/retornos}erro")
        if not error_elems:
            error_elems = self.root.findall(".//erro")
        if not error_elems:
            # Search iteratively
            for elem in self.root.iter():
                tag_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                if tag_name == "erro":
                    error_elems.append(elem)
        
        for err_elem in error_elems:
            code = self._get_text(err_elem, "codigo", "DESCONHECIDO")
            desc = self._get_text(err_elem, "descricao", "Erro sem descrição")
            loc = self._get_text(err_elem, "localizacao", None)
            
            error = ErrorInfo(
                code=code,
                description=desc,
                location=loc,
            )
            errors.append(error)
        
        # Create return object
        return SSTEventReturn(
            event_type=event_type,
            event_id=event_id,
            event_version=event_version,
            worker_cpf=worker_cpf,
            employer_cnpj=employer_cnpj,
            submission_date=datetime.now(),
            processing=ProcessingInfo(
                status=status,
                protocol=protocol if protocol else None,
                receipt_number=receipt if receipt else None,
                processing_date=processing_date,
            ),
            errors=errors,
            xml_content=self.xml_content,
        )
    
    @classmethod
    def from_file(cls, file_path: Union[str, Path]) -> "ReturnParser":
        """Create parser from XML file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {path}")
        
        xml_content = path.read_text(encoding="utf-8")
        return cls(xml_content)


# ============================================================================
# Return Handler with Audit Integration
# ============================================================================

@dataclass
class ReturnHandlerConfig:
    """Configuration for return handler."""
    
    enable_audit: bool = True
    audit_log_path: Optional[Path] = None
    enable_notifications: bool = False
    notification_webhook: Optional[str] = None
    persistence_enabled: bool = True
    persistence_path: Optional[Path] = None


class ReturnHandler:
    """Handler for processing and managing S-500X returns."""
    
    def __init__(self, config: Optional[ReturnHandlerConfig] = None):
        self.config = config or ReturnHandlerConfig()
        self.processed_returns: Dict[str, SSTEventReturn] = {}
        self.batch_returns: Dict[str, BatchReturn] = {}
        
        # Initialize audit logger if enabled
        self.audit_logger = None
        if self.config.enable_audit:
            try:
                from .audit import AuditLogger, AuditConfig
                log_path = str(self.config.audit_log_path) if self.config.audit_log_path else "/tmp/esocial_audit"
                audit_config = AuditConfig(
                    enabled=True,
                    log_path=log_path,
                )
                self.audit_logger = AuditLogger(config=audit_config)
                logger.info("Audit logging enabled for returns")
            except ImportError:
                logger.warning("Audit module not available, audit logging disabled")
            except Exception as e:
                logger.warning(f"Failed to initialize audit logger: {e}, continuing without audit")
    
    def process_return(self, xml_content: str) -> SSTEventReturn:
        """Process a single return XML."""
        try:
            parser = ReturnParser(xml_content)
            return_obj = parser.parse_sst_return()
            
            # Store return
            key = f"{return_obj.event_type if isinstance(return_obj.event_type, str) else return_obj.event_type.value}:{return_obj.event_id}:{return_obj.worker_cpf}"
            self.processed_returns[key] = return_obj
            
            # Log to audit if enabled
            if self.audit_logger:
                self._log_audit_event(return_obj)
            
            # Send notification if enabled
            if self.config.enable_notifications and self.config.notification_webhook:
                self._send_notification(return_obj)
            
            logger.info(f"Processed return: {return_obj.event_type.value} - {return_obj.status_display}")
            return return_obj
            
        except Exception as e:
            logger.error(f"Failed to process return: {e}")
            raise
    
    def process_batch_return(self, batch_id: str, xml_contents: List[str]) -> BatchReturn:
        """Process batch of returns."""
        returns = []
        for xml_content in xml_contents:
            try:
                return_obj = self.process_return(xml_content)
                returns.append(return_obj)
            except Exception as e:
                logger.error(f"Failed to process individual return in batch: {e}")
                # Create error return
                error_return = SSTEventReturn(
                    event_type=SSTEventType.S5001,  # Default
                    event_id="ERROR",
                    event_version="1.0",
                    worker_cpf="00000000000",
                    employer_cnpj="00000000000000",
                    submission_date=datetime.now(),
                    processing=ProcessingInfo(
                        status=ReturnStatus.ERROR,
                    ),
                    errors=[ErrorInfo(
                        code="PROCESSING_ERROR",
                        description=str(e),
                        severity="CRÍTICO",
                    )],
                )
                returns.append(error_return)
        
        # Determine overall status
        if all(r.is_success for r in returns):
            overall_status = ReturnStatus.SUCCESS
        elif any(r.has_errors for r in returns):
            overall_status = ReturnStatus.ERROR
        else:
            overall_status = ReturnStatus.WARNING
        
        batch_return = BatchReturn(
            batch_id=batch_id,
            submission_date=datetime.now(),
            total_events=len(returns),
            returns=returns,
            processing_status=overall_status,
        )
        
        self.batch_returns[batch_id] = batch_return
        logger.info(f"Processed batch {batch_id}: {batch_return.summary()}")
        
        return batch_return
    
    def _log_audit_event(self, return_obj: SSTEventReturn) -> None:
        """Log return processing to audit system."""
        if not self.audit_logger:
            return
        
        event_data = {
            "event_type": return_obj.event_type.value,
            "event_id": return_obj.event_id,
            "worker_cpf": return_obj.worker_cpf,
            "employer_cnpj": return_obj.employer_cnpj,
            "status": return_obj.processing.status.value,
            "has_errors": return_obj.has_errors,
            "error_count": len(return_obj.errors),
            "protocol": return_obj.processing.protocol,
        }
        
        self.audit_logger.log(
            event_type="SST_RETURN_PROCESSED",
            action="PROCESS_RETURN",
            resource_type="SSTEventReturn",
            resource_id=f"{return_obj.event_type.value}:{return_obj.event_id}",
            details=event_data,
            metadata={
                "xml_hash": return_obj.xml_hash,
                "processing_date": return_obj.processing.processing_date.isoformat() if return_obj.processing.processing_date else None,
            },
        )
    
    def _send_notification(self, return_obj: SSTEventReturn) -> None:
        """Send notification for return processing."""
        if not self.config.notification_webhook:
            return
        
        # In a real implementation, this would send HTTP request to webhook
        logger.info(f"Notification would be sent to {self.config.notification_webhook}")
        logger.info(f"Return status: {return_obj.status_display}")
    
    def get_return(self, key: str) -> Optional[SSTEventReturn]:
        """Get processed return by key."""
        return self.processed_returns.get(key)
    
    def get_batch(self, batch_id: str) -> Optional[BatchReturn]:
        """Get batch return by ID."""
        return self.batch_returns.get(batch_id)
    
    def query_returns(
        self,
        event_type: Optional[SSTEventType] = None,
        status: Optional[ReturnStatus] = None,
        worker_cpf: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> List[SSTEventReturn]:
        """Query processed returns with filters."""
        results = list(self.processed_returns.values())
        
        if event_type:
            results = [r for r in results if r.event_type == event_type]
        
        if status:
            results = [r for r in results if r.processing.status == status]
        
        if worker_cpf:
            worker_cpf = worker_cpf.replace(".", "").replace("-", "")
            results = [r for r in results if r.worker_cpf == worker_cpf]
        
        if date_from:
            results = [r for r in results if r.submission_date >= date_from]
        
        if date_to:
            results = [r for r in results if r.submission_date <= date_to]
        
        return results
    
    def export_to_json(self, output_path: Union[str, Path]) -> None:
        """Export all returns to JSON file."""
        import json
        
        path = Path(output_path)
        data = {
            "export_date": datetime.now().isoformat(),
            "total_returns": len(self.processed_returns),
            "returns": [r.to_dict() for r in self.processed_returns.values()],
        }
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Exported {len(self.processed_returns)} returns to {path}")


# ============================================================================
# Convenience Functions
# ============================================================================

def parse_sst_return(xml_content: str) -> SSTEventReturn:
    """Convenience function to parse S-500X return."""
    parser = ReturnParser(xml_content)
    return parser.parse_sst_return()


def parse_sst_return_file(file_path: Union[str, Path]) -> SSTEventReturn:
    """Convenience function to parse S-500X return from file."""
    parser = ReturnParser.from_file(file_path)
    return parser.parse_sst_return()


def process_sst_returns(xml_contents: List[str], batch_id: Optional[str] = None) -> BatchReturn:
    """Convenience function to process multiple S-500X returns."""
    handler = ReturnHandler()
    batch_id = batch_id or f"batch_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    return handler.process_batch_return(batch_id, xml_contents)


__all__ = [
    # Enums
    "SSTEventType",
    "ReturnStatus",
    "ErrorCode",
    
    # Models
    "ErrorInfo",
    "ProcessingInfo",
    "SSTEventReturn",
    "BatchReturn",
    
    # Parser & Handler
    "ReturnParser",
    "ReturnHandler",
    "ReturnHandlerConfig",
    
    # Convenience functions
    "parse_sst_return",
    "parse_sst_return_file",
    "process_sst_returns",
]
