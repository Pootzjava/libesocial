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
"""eSocial Premium Models

Pydantic models for data validation and serialization.
FASE 1: Type hints + Pydantic models
"""
from datetime import datetime, date
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict
from pydantic_settings import BaseSettings


class TargetEnum(str, Enum):
    """Ambiente de destino do eSocial."""
    TESTS = 'tests'
    PRODUCTION = 'production'


class BatchStatusEnum(str, Enum):
    """Status de um lote de eventos."""
    PENDING = 'PENDING'
    SUCCESS = 'SUCCESS'
    FAILED = 'FAILED'
    PROCESSING = 'PROCESSING'


class EmployerIdentification(BaseModel):
    """Identificação do empregador."""
    tpInsc: int = Field(..., description="Tipo de inscrição (1-CNPJ, 2-CPF)")
    nrInsc: str = Field(..., description="Número de inscrição")
    use_full: bool = Field(default=False, description="Usar número completo")
    
    @field_validator('nrInsc')
    @classmethod
    def validate_nrinsc(cls, v: str) -> str:
        """Valida formato do número de inscrição."""
        cleaned = v.strip().replace('.', '').replace('-', '').replace('/', '')
        if not cleaned.isdigit():
            raise ValueError('nrInsc deve conter apenas dígitos')
        return cleaned
    
    @field_validator('tpInsc')
    @classmethod
    def validate_tpinsc(cls, v: int) -> int:
        """Valida tipo de inscrição."""
        if v not in [1, 2]:
            raise ValueError('tpInsc deve ser 1 (CNPJ) ou 2 (CPF)')
        return v
    
    def get_nrinsc_short(self) -> str:
        """Retorna número de inscrição curto (8 primeiros dígitos para CNPJ)."""
        if self.use_full or self.tpInsc == 2:
            return self.nrInsc
        return self.nrInsc[:8]
    
    model_config = ConfigDict(json_schema_extra={
        'example': {
            'tpInsc': 1,
            'nrInsc': '12345678000195',
            'use_full': False
        }
    })


class SenderIdentification(BaseModel):
    """Identificação do transmissor."""
    tpInsc: int = Field(..., description="Tipo de inscrição")
    nrInsc: str = Field(..., description="Número de inscrição")
    
    @field_validator('tpInsc')
    @classmethod
    def validate_tpinsc(cls, v: int) -> int:
        """Valida tipo de inscrição."""
        if v not in [1, 2]:
            raise ValueError('tpInsc deve ser 1 (CNPJ) ou 2 (CPF)')
        return v


class CertificateConfig(BaseModel):
    """Configuração de certificado digital."""
    pfx_file: Optional[str] = Field(None, description="Caminho para arquivo .pfx")
    pfx_password: str = Field(..., description="Senha do certificado")
    ca_file: Optional[str] = Field(None, description="Caminho para CA bundle")
    
    model_config = ConfigDict(json_schema_extra={
        'example': {
            'pfx_file': '/path/to/cert.pfx',
            'pfx_password': 'senha123',
            'ca_file': '/path/to/ca.pem'
        }
    })


class BatchConfig(BaseModel):
    """Configuração de lote de eventos."""
    max_batch_size: int = Field(default=50, ge=1, le=50)
    group_id: int = Field(default=1, ge=1)
    clear_after_send: bool = Field(default=True)
    
    model_config = ConfigDict(json_schema_extra={
        'example': {
            'max_batch_size': 50,
            'group_id': 1,
            'clear_after_send': True
        }
    })


class EventInfo(BaseModel):
    """Informações de um evento."""
    event_id: str
    event_type: str
    status: str = 'PENDING'
    created_at: datetime = Field(default_factory=datetime.now)
    sent_at: Optional[datetime] = None
    response: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class BatchState(BaseModel):
    """Estado de um lote de eventos."""
    batch_id: str
    events: List[EventInfo] = Field(default_factory=list)
    status: BatchStatusEnum = BatchStatusEnum.PENDING
    created_at: datetime = Field(default_factory=datetime.now)
    sent_at: Optional[datetime] = None
    protocol: Optional[str] = None
    last_error: Optional[str] = None
    retry_count: int = Field(default=0)
    
    def add_event(self, event_info: EventInfo) -> None:
        """Adiciona evento ao lote."""
        self.events.append(event_info)
    
    def mark_success(self, protocol: Optional[str] = None) -> None:
        """Marca lote como sucesso."""
        self.status = BatchStatusEnum.SUCCESS
        self.sent_at = datetime.now()
        self.protocol = protocol
    
    def mark_failed(self, error: str) -> None:
        """Marca lote como falho."""
        self.status = BatchStatusEnum.FAILED
        self.last_error = error
    
    model_config = ConfigDict(json_schema_extra={
        'example': {
            'batch_id': 'batch_1_1234567890',
            'events': [],
            'status': 'PENDING',
            'retry_count': 0
        }
    })


class DLQEntry(BaseModel):
    """Entrada na Dead Letter Queue."""
    event_id: str
    event_type: str
    error_message: str
    context: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    retry_count: int = Field(default=0)
    last_retry_at: Optional[datetime] = None


class ESocialConfig(BaseSettings):
    """Configurações principais do eSocial."""
    target: TargetEnum = TargetEnum.TESTS
    esocial_version: str = 'S-1.0'
    employer_id: Optional[EmployerIdentification] = None
    sender_id: Optional[SenderIdentification] = None
    certificate: Optional[CertificateConfig] = None
    batch_config: BatchConfig = Field(default_factory=BatchConfig)
    enable_persistence: bool = True
    storage_path: str = './esocial_storage'
    timeout_seconds: int = 30
    max_retries: int = 3
    
    model_config = ConfigDict(
        env_prefix='ESOCIAL_',
        env_file='.env',
        json_schema_extra={
            'example': {
                'target': 'tests',
                'esocial_version': 'S-1.0',
                'enable_persistence': True,
                'storage_path': './esocial_storage',
                'timeout_seconds': 30,
                'max_retries': 3
            }
        }
    )
    
    @property
    def is_production(self) -> bool:
        """Verifica se está em produção."""
        return self.target == TargetEnum.PRODUCTION
    
    @property
    def is_tests(self) -> bool:
        """Verifica se está em ambiente de testes."""
        return self.target == TargetEnum.TESTS


class WebServiceURLs(BaseModel):
    """URLs dos web services do eSocial."""
    send: str
    retrieve: str
    download_identifiers: Optional[str] = None
    download_events: Optional[str] = None
    
    @classmethod
    def get_urls(cls, target: TargetEnum) -> 'WebServiceURLs':
        """Retorna URLs baseadas no ambiente."""
        if target == TargetEnum.TESTS:
            return cls(
                send='https://webservices.producaorestrita.esocial.gov.br/servicos/empregador/enviarloteeventos/WsEnviarLoteEventos.svc?wsdl',
                retrieve='https://webservices.producaorestrita.esocial.gov.br/servicos/empregador/consultarloteeventos/WsConsultarLoteEventos.svc?wsdl',
                download_identifiers='https://webservices.producaorestrita.esocial.gov.br/servicos/empregador/dwlcirurgico/WsConsultarIdentificadoresEventos.svc?wsdl',
                download_events='https://webservices.producaorestrita.esocial.gov.br/servicos/empregador/dwlcirurgico/WsSolicitarDownloadEventos.svc?wsdl'
            )
        else:
            return cls(
                send='https://webservices.envio.esocial.gov.br/servicos/empregador/enviarloteeventos/WsEnviarLoteEventos.svc?wsdl',
                retrieve='https://webservices.consulta.esocial.gov.br/servicos/empregador/consultarloteeventos/WsConsultarLoteEventos.svc?wsdl',
                download_identifiers='https://webservices.download.esocial.gov.br/servicos/empregador/dwlcirurgico/WsConsultarIdentificadoresEventos.svc?wsdl',
                download_events='https://webservices.download.esocial.gov.br/servicos/empregador/dwlcirurgico/WsSolicitarDownloadEventos.svc?wsdl'
            )


class SendResult(BaseModel):
    """Resultado de envio de lote."""
    success: bool
    batch_id: str
    protocol: Optional[str] = None
    response_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration_seconds: float = 0.0
    events_sent: int = 0
    
    model_config = ConfigDict(json_schema_extra={
        'example': {
            'success': True,
            'batch_id': 'batch_1_1234567890',
            'protocol': '1.2.3.4.5.6.7.8.9',
            'duration_seconds': 2.5,
            'events_sent': 10
        }
    })


class HealthStatus(BaseModel):
    """Status de saúde do sistema."""
    healthy: bool
    timestamp: datetime = Field(default_factory=datetime.now)
    version: str = ''
    target: str = ''
    persistence_enabled: bool = False
    circuit_breaker_state: str = 'CLOSED'
    last_check: Optional[datetime] = None
    errors: List[str] = Field(default_factory=list)
