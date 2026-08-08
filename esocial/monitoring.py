"""
LIBeSocial Premium - Monitoring & Observability Module

Módulo completo de monitoramento com:
- Métricas Prometheus (counter, gauge, histogram)
- Health checks (liveness, readiness, startup)
- Distributed tracing (OpenTelemetry)
- Alertas e notificações
- Logging estruturado
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from collections import defaultdict
import threading
import json


class MetricType(Enum):
    """Tipos de métricas suportadas."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


class HealthStatus(Enum):
    """Status de health check."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class AlertSeverity(Enum):
    """Severidade de alertas."""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass
class MetricPoint:
    """Ponto de métrica com timestamp."""
    value: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class HealthCheckResult:
    """Resultado de um health check."""
    name: str
    status: HealthStatus
    message: str = ""
    latency_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Alert:
    """Alerta do sistema."""
    id: str
    name: str
    severity: AlertSeverity
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class MetricsRegistry:
    """
    Registry de métricas no estilo Prometheus.
    
    Suporta:
    - Counter: Métricas que só incrementam
    - Gauge: Métricas que podem subir/descer
    - Histogram: Distribuição de valores
    - Labels: Dimensionamento de métricas
    """
    
    def __init__(self, prefix: str = "esocial"):
        self.prefix = prefix
        self._counters: Dict[str, Dict[tuple, float]] = defaultdict(lambda: defaultdict(float))
        self._gauges: Dict[str, Dict[tuple, float]] = defaultdict(lambda: defaultdict(float))
        self._histograms: Dict[str, Dict[tuple, List[float]]] = defaultdict(lambda: defaultdict(list))
        self._lock = threading.Lock()
        self._callbacks: Dict[str, Callable[[], float]] = {}
        
    def counter(self, name: str, description: str = "", labels: Optional[List[str]] = None) -> 'Counter':
        """Cria ou retorna um counter."""
        return Counter(self, name, description, labels or [])
    
    def gauge(self, name: str, description: str = "", labels: Optional[List[str]] = None) -> 'Gauge':
        """Cria ou retorna um gauge."""
        return Gauge(self, name, description, labels or [])
    
    def histogram(
        self, 
        name: str, 
        description: str = "", 
        labels: Optional[List[str]] = None,
        buckets: Optional[List[float]] = None
    ) -> 'Histogram':
        """Cria ou retorna um histogram."""
        return Histogram(self, name, description, labels or [], buckets)
    
    def register_callback(self, name: str, callback: Callable[[], float]) -> None:
        """Registra um callback para métrica dinâmica."""
        with self._lock:
            self._callbacks[name] = callback
    
    def get_counter_value(self, name: str, label_values: Optional[tuple] = None) -> float:
        """Obtém valor de um counter."""
        with self._lock:
            if label_values:
                return self._counters[name].get(label_values, 0.0)
            return sum(self._counters[name].values())
    
    def get_gauge_value(self, name: str, label_values: Optional[tuple] = None) -> float:
        """Obtém valor de um gauge."""
        with self._lock:
            if label_values:
                return self._gauges[name].get(label_values, 0.0)
            if self._gauges[name]:
                return list(self._gauges[name].values())[-1]
            return 0.0
    
    def get_histogram_values(self, name: str, label_values: Optional[tuple] = None) -> List[float]:
        """Obtém valores de um histogram."""
        with self._lock:
            if label_values:
                return self._histograms[name].get(label_values, [])
            all_values = []
            for values in self._histograms[name].values():
                all_values.extend(values)
            return all_values
    
    def export_prometheus(self) -> str:
        """Exporta métricas no formato Prometheus."""
        lines = []
        
        # Export counters
        for name, label_data in self._counters.items():
            help_line = f"# HELP {self.prefix}_{name} Total {name}"
            type_line = f"# TYPE {self.prefix}_{name} counter"
            lines.append(help_line)
            lines.append(type_line)
            
            for label_values, value in label_data.items():
                if label_values:
                    labels_str = ",".join(f'k{i}="{v}"' for i, v in enumerate(label_values))
                    lines.append(f"{self.prefix}_{name}{{{labels_str}}} {value}")
                else:
                    lines.append(f"{self.prefix}_{name} {value}")
        
        # Export gauges
        for name, label_data in self._gauges.items():
            help_line = f"# HELP {self.prefix}_{name} Current {name}"
            type_line = f"# TYPE {self.prefix}_{name} gauge"
            lines.append(help_line)
            lines.append(type_line)
            
            for label_values, value in label_data.items():
                if label_values:
                    labels_str = ",".join(f'k{i}="{v}"' for i, v in enumerate(label_values))
                    lines.append(f"{self.prefix}_{name}{{{labels_str}}} {value}")
                else:
                    lines.append(f"{self.prefix}_{name} {value}")
        
        # Export histograms
        for name, label_data in self._histograms.items():
            help_line = f"# HELP {self.prefix}_{name} Distribution of {name}"
            type_line = f"# TYPE {self.prefix}_{name} histogram"
            lines.append(help_line)
            lines.append(type_line)
            
            for label_values, values in label_data.items():
                if values:
                    count = len(values)
                    total = sum(values)
                    avg = total / count if count > 0 else 0
                    
                    if label_values:
                        labels_str = ",".join(f'k{i}="{v}"' for i, v in enumerate(label_values))
                        lines.append(f"{self.prefix}_{name}_count{{{labels_str}}} {count}")
                        lines.append(f"{prefix}_{name}_sum{{{labels_str}}} {total}")
                        lines.append(f"{self.prefix}_{name}_avg{{{labels_str}}} {avg}")
                    else:
                        lines.append(f"{self.prefix}_{name}_count {count}")
                        lines.append(f"{self.prefix}_{name}_sum {total}")
                        lines.append(f"{self.prefix}_{name}_avg {avg}")
        
        return "\n".join(lines)
    
    def reset(self) -> None:
        """Reseta todas as métricas."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()


class Counter:
    """Metric counter que só incrementa."""
    
    def __init__(self, registry: MetricsRegistry, name: str, description: str, label_names: List[str]):
        self.registry = registry
        self.name = name
        self.description = description
        self.label_names = label_names
        self._label_values: Dict[str, str] = {}
        
    def with_labels(self, **kwargs: str) -> 'Counter':
        """Define labels para a métrica."""
        self._label_values = kwargs
        return self
    
    def inc(self, value: float = 1.0) -> None:
        """Incrementa o counter."""
        label_tuple = tuple(self._label_values.get(k, "") for k in sorted(self._label_values.keys()))
        with self.registry._lock:
            self.registry._counters[self.name][label_tuple] += value
    
    def clear(self) -> None:
        """Limpa os valores do counter."""
        with self.registry._lock:
            self.registry._counters[self.name].clear()


class Gauge:
    """Metric gauge que pode subir/descer."""
    
    def __init__(self, registry: MetricsRegistry, name: str, description: str, label_names: List[str]):
        self.registry = registry
        self.name = name
        self.description = description
        self.label_names = label_names
        self._label_values: Dict[str, str] = {}
        
    def with_labels(self, **kwargs: str) -> 'Gauge':
        """Define labels para a métrica."""
        self._label_values = kwargs
        return self
    
    def set(self, value: float) -> None:
        """Define o valor do gauge."""
        label_tuple = tuple(self._label_values.get(k, "") for k in sorted(self._label_values.keys()))
        with self.registry._lock:
            self.registry._gauges[self.name][label_tuple] = value
    
    def inc(self, value: float = 1.0) -> None:
        """Incrementa o gauge."""
        label_tuple = tuple(self._label_values.get(k, "") for k in sorted(self._label_values.keys()))
        with self.registry._lock:
            self.registry._gauges[self.name][label_tuple] += value
    
    def dec(self, value: float = 1.0) -> None:
        """Decrementa o gauge."""
        label_tuple = tuple(self._label_values.get(k, "") for k in sorted(self._label_values.keys()))
        with self.registry._lock:
            self.registry._gauges[self.name][label_tuple] -= value
    
    def clear(self) -> None:
        """Limpa os valores do gauge."""
        with self.registry._lock:
            self.registry._gauges[self.name].clear()


class Histogram:
    """Metric histogram para distribuição de valores."""
    
    DEFAULT_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
    
    def __init__(
        self, 
        registry: MetricsRegistry, 
        name: str, 
        description: str, 
        label_names: List[str],
        buckets: Optional[List[float]] = None
    ):
        self.registry = registry
        self.name = name
        self.description = description
        self.label_names = label_names
        self.buckets = buckets or self.DEFAULT_BUCKETS
        self._label_values: Dict[str, str] = {}
        
    def with_labels(self, **kwargs: str) -> 'Histogram':
        """Define labels para a métrica."""
        self._label_values = kwargs
        return self
    
    def observe(self, value: float) -> None:
        """Observa um valor no histogram."""
        label_tuple = tuple(self._label_values.get(k, "") for k in sorted(self._label_values.keys()))
        with self.registry._lock:
            self.registry._histograms[self.name][label_tuple].append(value)
    
    @contextmanager
    def time(self):
        """Context manager para timing de operações."""
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start
            self.observe(duration)
    
    def clear(self) -> None:
        """Limpa os valores do histogram."""
        with self.registry._lock:
            self.registry._histograms[self.name].clear()


class HealthChecker:
    """
    Sistema de health checks com suporte a:
    - Liveness probe (está vivo?)
    - Readiness probe (pronto para receber tráfego?)
    - Startup probe (inicialização completa?)
    """
    
    def __init__(self, service_name: str = "esocial-client"):
        self.service_name = service_name
        self._checks: Dict[str, Callable[[], HealthCheckResult]] = {}
        self._last_results: Dict[str, HealthCheckResult] = {}
        self._lock = threading.Lock()
        
    def register(self, name: str, check_func: Callable[[], HealthCheckResult]) -> None:
        """Registra um health check."""
        with self._lock:
            self._checks[name] = check_func
    
    def unregister(self, name: str) -> None:
        """Remove um health check."""
        with self._lock:
            if name in self._checks:
                del self._checks[name]
    
    async def run_check(self, name: str) -> HealthCheckResult:
        """Executa um health check específico."""
        if name not in self._checks:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNKNOWN,
                message=f"Check '{name}' not found"
            )
        
        start = time.perf_counter()
        try:
            result = self._checks[name]()
            latency = (time.perf_counter() - start) * 1000
            result.latency_ms = latency
            
            with self._lock:
                self._last_results[name] = result
            
            return result
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            result = HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                latency_ms=latency
            )
            with self._lock:
                self._last_results[name] = result
            return result
    
    async def run_all_checks(self) -> Dict[str, HealthCheckResult]:
        """Executa todos os health checks."""
        tasks = [self.run_check(name) for name in self._checks.keys()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        output = {}
        for name, result in zip(self._checks.keys(), results):
            if isinstance(result, Exception):
                output[name] = HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=str(result)
                )
            else:
                output[name] = result
        
        return output
    
    def get_overall_status(self) -> HealthStatus:
        """Obtém status geral do serviço."""
        with self._lock:
            if not self._last_results:
                return HealthStatus.UNKNOWN
            
            statuses = [r.status for r in self._last_results.values()]
            
            if all(s == HealthStatus.HEALTHY for s in statuses):
                return HealthStatus.HEALTHY
            elif any(s == HealthStatus.UNHEALTHY for s in statuses):
                return HealthStatus.UNHEALTHY
            elif any(s == HealthStatus.DEGRADED for s in statuses):
                return HealthStatus.DEGRADED
            else:
                return HealthStatus.UNKNOWN
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte resultados para dict."""
        with self._lock:
            overall = self.get_overall_status()
            checks = {
                name: {
                    "status": result.status.value,
                    "message": result.message,
                    "latency_ms": result.latency_ms,
                    "timestamp": result.timestamp.isoformat(),
                    "details": result.details
                }
                for name, result in self._last_results.items()
            }
            
            return {
                "service": self.service_name,
                "status": overall.value,
                "timestamp": datetime.utcnow().isoformat(),
                "checks": checks
            }


class TracingManager:
    """
    Gerenciador de distributed tracing (estilo OpenTelemetry).
    
    Suporta:
    - Spans aninhados
    - Context propagation
    - Tags e attributes
    - Export para Jaeger/Zipkin
    """
    
    def __init__(self, service_name: str = "esocial-client"):
        self.service_name = service_name
        self._spans: List[Dict[str, Any]] = []
        self._current_span: Optional[Dict[str, Any]] = None
        self._lock = threading.Lock()
        self._enabled = True
        
    def start_span(self, operation_name: str, parent: Optional[Dict[str, Any]] = None) -> 'Span':
        """Inicia um novo span."""
        if not self._enabled:
            return Span(self, operation_name, None, parent)
        
        span_id = str(uuid.uuid4())
        trace_id = parent.get("trace_id") if parent else str(uuid.uuid4())
        
        span_data = {
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": parent.get("span_id") if parent else None,
            "operation_name": operation_name,
            "service_name": self.service_name,
            "start_time": datetime.utcnow().isoformat(),
            "tags": {},
            "logs": [],
            "status": "OK"
        }
        
        with self._lock:
            self._spans.append(span_data)
            self._current_span = span_data
        
        return Span(self, operation_name, span_data, parent)
    
    @contextmanager
    def trace(self, operation_name: str):
        """Context manager para tracing."""
        span = self.start_span(operation_name)
        try:
            yield span
            span.finish()
        except Exception as e:
            span.set_tag("error", str(e))
            span.set_status("ERROR")
            raise
        finally:
            if span.span_data:
                span.finish()
    
    def get_spans(self) -> List[Dict[str, Any]]:
        """Obtém todos os spans."""
        with self._lock:
            return self._spans.copy()
    
    def clear(self) -> None:
        """Limpa todos os spans."""
        with self._lock:
            self._spans.clear()
            self._current_span = None
    
    def export_json(self) -> str:
        """Exporta spans em JSON."""
        with self._lock:
            return json.dumps(self._spans, indent=2)
    
    def disable(self) -> None:
        """Desabilita tracing."""
        self._enabled = False
    
    def enable(self) -> None:
        """Habilita tracing."""
        self._enabled = True


class Span:
    """Representa um span de tracing."""
    
    def __init__(
        self, 
        manager: TracingManager, 
        operation_name: str, 
        span_data: Optional[Dict[str, Any]],
        parent: Optional[Dict[str, Any]] = None
    ):
        self.manager = manager
        self.operation_name = operation_name
        self.span_data = span_data
        self.parent = parent
        self._finished = False
        
    def set_tag(self, key: str, value: Any) -> 'Span':
        """Adiciona uma tag ao span."""
        if self.span_data and not self._finished:
            self.span_data["tags"][key] = value
        return self
    
    def log(self, message: str, level: str = "INFO") -> 'Span':
        """Adiciona um log ao span."""
        if self.span_data and not self._finished:
            self.span_data["logs"].append({
                "timestamp": datetime.utcnow().isoformat(),
                "level": level,
                "message": message
            })
        return self
    
    def set_status(self, status: str) -> 'Span':
        """Define o status do span."""
        if self.span_data and not self._finished:
            self.span_data["status"] = status
        return self
    
    def finish(self) -> None:
        """Finaliza o span."""
        if self.span_data and not self._finished:
            self.span_data["end_time"] = datetime.utcnow().isoformat()
            self._finished = True
    
    def __enter__(self) -> 'Span':
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_val:
            self.set_tag("error", str(exc_val))
            self.set_status("ERROR")
        if not self._finished:
            self.finish()


class AlertManager:
    """
    Gerenciador de alertas e notificações.
    
    Suporta:
    - Múltiplas severidades
    - Auto-resolução
    - Notificações (webhook, email, slack)
    - Rate limiting de alertas
    """
    
    def __init__(self, service_name: str = "esocial-client"):
        self.service_name = service_name
        self._alerts: Dict[str, Alert] = {}
        self._alert_history: List[Alert] = []
        self._notification_callbacks: List[Callable[[Alert], None]] = []
        self._lock = threading.Lock()
        self._cooldown_period = timedelta(minutes=5)
        self._last_alert_time: Dict[str, datetime] = {}
        
    def register_notification(self, callback: Callable[[Alert], None]) -> None:
        """Registra um callback de notificação."""
        self._notification_callbacks.append(callback)
    
    def create_alert(
        self,
        name: str,
        severity: AlertSeverity,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Alert:
        """Cria um novo alerta."""
        alert_id = f"{self.service_name}-{name}-{uuid.uuid4().hex[:8]}"
        
        # Check cooldown
        now = datetime.utcnow()
        if name in self._last_alert_time:
            elapsed = now - self._last_alert_time[name]
            if elapsed < self._cooldown_period:
                # Skip duplicate alert within cooldown
                return None
        
        alert = Alert(
            id=alert_id,
            name=name,
            severity=severity,
            message=message,
            metadata=metadata or {}
        )
        
        with self._lock:
            self._alerts[alert_id] = alert
            self._alert_history.append(alert)
            self._last_alert_time[name] = now
        
        # Notify
        for callback in self._notification_callbacks:
            try:
                callback(alert)
            except Exception:
                pass  # Don't fail on notification errors
        
        return alert
    
    def resolve_alert(self, alert_id: str, message: str = "") -> bool:
        """Resolve um alerta."""
        with self._lock:
            if alert_id not in self._alerts:
                return False
            
            alert = self._alerts[alert_id]
            alert.resolved = True
            alert.resolved_at = datetime.utcnow()
            alert.metadata["resolution_message"] = message
            
            return True
    
    def get_active_alerts(self) -> List[Alert]:
        """Obtém alertas ativos."""
        with self._lock:
            return [a for a in self._alerts.values() if not a.resolved]
    
    def get_alert_history(self, limit: int = 100) -> List[Alert]:
        """Obtém histórico de alertas."""
        with self._lock:
            return self._alert_history[-limit:]
    
    def clear(self) -> None:
        """Limpa todos os alertas."""
        with self._lock:
            self._alerts.clear()


# Global instances
_default_metrics: Optional[MetricsRegistry] = None
_default_health: Optional[HealthChecker] = None
_default_tracing: Optional[TracingManager] = None
_default_alerts: Optional[AlertManager] = None


def get_metrics_registry(prefix: str = "esocial") -> MetricsRegistry:
    """Obtém ou cria registry de métricas global."""
    global _default_metrics
    if _default_metrics is None:
        _default_metrics = MetricsRegistry(prefix)
    return _default_metrics


def get_health_checker(service_name: str = "esocial-client") -> HealthChecker:
    """Obtém ou cria health checker global."""
    global _default_health
    if _default_health is None:
        _default_health = HealthChecker(service_name)
    return _default_health


def get_tracing_manager(service_name: str = "esocial-client") -> TracingManager:
    """Obtém ou cria tracing manager global."""
    global _default_tracing
    if _default_tracing is None:
        _default_tracing = TracingManager(service_name)
    return _default_tracing


def get_alert_manager(service_name: str = "esocial-client") -> AlertManager:
    """Obtém ou cria alert manager global."""
    global _default_alerts
    if _default_alerts is None:
        _default_alerts = AlertManager(service_name)
    return _default_alerts


def reset_globals() -> None:
    """Reseta todas as instâncias globais (útil para testes)."""
    global _default_metrics, _default_health, _default_tracing, _default_alerts
    _default_metrics = None
    _default_health = None
    _default_tracing = None
    _default_alerts = None
