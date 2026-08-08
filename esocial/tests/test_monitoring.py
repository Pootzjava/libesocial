"""
Tests for LIBeSocial Premium Monitoring Module

Cobertura:
- MetricsRegistry (Counter, Gauge, Histogram)
- HealthChecker
- TracingManager
- AlertManager
- Global instances
"""

import pytest
import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from esocial.monitoring import (
    MetricsRegistry,
    Counter,
    Gauge,
    Histogram,
    HealthChecker,
    HealthStatus,
    HealthCheckResult,
    TracingManager,
    Span,
    AlertManager,
    AlertSeverity,
    Alert,
    get_metrics_registry,
    get_health_checker,
    get_tracing_manager,
    get_alert_manager,
    reset_globals,
)


class TestMetricsRegistry:
    """Testes para MetricsRegistry."""

    def test_create_registry(self):
        """Testa criação de registry."""
        registry = MetricsRegistry(prefix="test")
        assert registry.prefix == "test"

    def test_counter_increment(self):
        """Testa incremento de counter."""
        registry = MetricsRegistry()
        counter = registry.counter("requests_total", "Total requests")
        
        counter.inc()
        assert registry.get_counter_value("requests_total") == 1.0
        
        counter.inc(5.0)
        assert registry.get_counter_value("requests_total") == 6.0

    def test_counter_with_labels(self):
        """Testa counter com labels."""
        registry = MetricsRegistry()
        counter = registry.counter("requests", "Requests", ["method", "status"])
        
        counter.with_labels(method="GET", status="200").inc()
        counter.with_labels(method="POST", status="200").inc()
        counter.with_labels(method="GET", status="200").inc()
        
        # Total should be sum of all label combinations
        assert registry.get_counter_value("requests") == 3.0

    def test_gauge_set(self):
        """Testa set de gauge."""
        registry = MetricsRegistry()
        gauge = registry.gauge("active_connections", "Active connections")
        
        gauge.set(10.0)
        assert registry.get_gauge_value("active_connections") == 10.0
        
        gauge.set(5.0)
        assert registry.get_gauge_value("active_connections") == 5.0

    def test_gauge_inc_dec(self):
        """Testa incremento e decremento de gauge."""
        registry = MetricsRegistry()
        gauge = registry.gauge("temperature", "Temperature")
        
        gauge.set(20.0)
        gauge.inc(5.0)
        assert registry.get_gauge_value("temperature") == 25.0
        
        gauge.dec(10.0)
        assert registry.get_gauge_value("temperature") == 15.0

    def test_histogram_observe(self):
        """Testa observação no histogram."""
        registry = MetricsRegistry()
        histogram = registry.histogram("request_duration", "Request duration")
        
        histogram.observe(0.1)
        histogram.observe(0.2)
        histogram.observe(0.3)
        
        values = registry.get_histogram_values("request_duration")
        assert len(values) == 3
        assert values == [0.1, 0.2, 0.3]

    def test_histogram_time_context_manager(self):
        """Testa context manager de timing do histogram."""
        registry = MetricsRegistry()
        histogram = registry.histogram("operation_time", "Operation time")
        
        with histogram.time():
            time.sleep(0.01)  # Sleep 10ms
        
        values = registry.get_histogram_values("operation_time")
        assert len(values) == 1
        assert values[0] >= 0.01

    def test_export_prometheus_format(self):
        """Testa export no formato Prometheus."""
        registry = MetricsRegistry(prefix="myapp")
        counter = registry.counter("errors", "Errors")
        counter.inc(5.0)
        
        output = registry.export_prometheus()
        
        assert "# HELP myapp_errors Total errors" in output
        assert "# TYPE myapp_errors counter" in output
        assert "myapp_errors 5.0" in output

    def test_reset_metrics(self):
        """Testa reset de métricas."""
        registry = MetricsRegistry()
        counter = registry.counter("test_counter", "Test")
        counter.inc(10.0)
        
        registry.reset()
        
        assert registry.get_counter_value("test_counter") == 0.0


class TestHealthChecker:
    """Testes para HealthChecker."""

    @pytest.mark.asyncio
    async def test_register_and_run_check(self):
        """Testa registro e execução de health check."""
        checker = HealthChecker(service_name="test-service")
        
        def healthy_check():
            return HealthCheckResult(
                name="database",
                status=HealthStatus.HEALTHY,
                message="DB connected"
            )
        
        checker.register("database", healthy_check)
        result = await checker.run_check("database")
        
        assert result.name == "database"
        assert result.status == HealthStatus.HEALTHY
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_check_failure(self):
        """Testa falha em health check."""
        checker = HealthChecker()
        
        def failing_check():
            raise Exception("Connection timeout")
        
        checker.register("cache", failing_check)
        result = await checker.run_check("cache")
        
        assert result.status == HealthStatus.UNHEALTHY
        assert "Connection timeout" in result.message

    @pytest.mark.asyncio
    async def test_run_all_checks(self):
        """Testa execução de todos os checks."""
        checker = HealthChecker()
        
        checker.register("db", lambda: HealthCheckResult("db", HealthStatus.HEALTHY))
        checker.register("cache", lambda: HealthCheckResult("cache", HealthStatus.HEALTHY))
        
        results = await checker.run_all_checks()
        
        assert len(results) == 2
        assert all(r.status == HealthStatus.HEALTHY for r in results.values())

    def test_get_overall_status_healthy(self):
        """Testa status geral saudável."""
        checker = HealthChecker()
        checker._last_results = {
            "db": HealthCheckResult("db", HealthStatus.HEALTHY),
            "cache": HealthCheckResult("cache", HealthStatus.HEALTHY)
        }
        
        status = checker.get_overall_status()
        assert status == HealthStatus.HEALTHY

    def test_get_overall_status_unhealthy(self):
        """Testa status geral não saudável."""
        checker = HealthChecker()
        checker._last_results = {
            "db": HealthCheckResult("db", HealthStatus.HEALTHY),
            "cache": HealthCheckResult("cache", HealthStatus.UNHEALTHY)
        }
        
        status = checker.get_overall_status()
        assert status == HealthStatus.UNHEALTHY

    def test_to_dict(self):
        """Testa conversão para dict."""
        checker = HealthChecker(service_name="api")
        checker._last_results = {
            "db": HealthCheckResult(
                "db", 
                HealthStatus.HEALTHY, 
                "OK", 
                latency_ms=5.2
            )
        }
        
        result = checker.to_dict()
        
        assert result["service"] == "api"
        assert result["status"] == "healthy"
        assert "checks" in result
        assert "db" in result["checks"]


class TestTracingManager:
    """Testes para TracingManager."""

    def test_start_span(self):
        """Testa início de span."""
        tracer = TracingManager(service_name="test")
        span = tracer.start_span("operation")
        
        assert span.operation_name == "operation"
        assert span.manager == tracer

    def test_span_set_tag(self):
        """Testa adição de tags no span."""
        tracer = TracingManager()
        span = tracer.start_span("db_query")
        span.set_tag("db.type", "postgresql")
        span.set_tag("db.statement", "SELECT * FROM users")
        
        assert span.span_data["tags"]["db.type"] == "postgresql"
        assert span.span_data["tags"]["db.statement"] == "SELECT * FROM users"

    def test_span_log(self):
        """Testa adição de logs no span."""
        tracer = TracingManager()
        span = tracer.start_span("request")
        span.log("Processing started", "INFO")
        span.log("Error occurred", "ERROR")
        
        assert len(span.span_data["logs"]) == 2
        assert span.span_data["logs"][0]["message"] == "Processing started"

    def test_span_finish(self):
        """Testa finalização de span."""
        tracer = TracingManager()
        span = tracer.start_span("task")
        
        assert not span._finished
        span.finish()
        assert span._finished
        assert "end_time" in span.span_data

    def test_trace_context_manager(self):
        """Testa context manager de trace."""
        tracer = TracingManager()
        
        with tracer.trace("operation") as span:
            span.set_tag("key", "value")
        
        assert span._finished
        assert span.span_data["tags"]["key"] == "value"

    def test_trace_context_manager_with_error(self):
        """Testa context manager com erro."""
        tracer = TracingManager()
        
        try:
            with tracer.trace("failing_operation") as span:
                raise ValueError("Something went wrong")
        except ValueError:
            pass
        
        assert span.span_data["status"] == "ERROR"
        assert "Something went wrong" in span.span_data["tags"]["error"]

    def test_get_spans(self):
        """Testa obtenção de spans."""
        tracer = TracingManager()
        
        tracer.start_span("span1")
        tracer.start_span("span2")
        
        spans = tracer.get_spans()
        assert len(spans) == 2

    def test_clear_spans(self):
        """Testa limpeza de spans."""
        tracer = TracingManager()
        tracer.start_span("span1")
        tracer.start_span("span2")
        
        tracer.clear()
        
        assert len(tracer.get_spans()) == 0

    def test_export_json(self):
        """Testa export JSON."""
        tracer = TracingManager()
        span = tracer.start_span("test_op")
        span.set_tag("key", "value")
        span.finish()
        
        json_output = tracer.export_json()
        
        assert "test_op" in json_output
        assert "key" in json_output

    def test_disable_enable(self):
        """Testa desabilitar/habilitar tracing."""
        tracer = TracingManager()
        tracer.disable()
        
        span = tracer.start_span("disabled_op")
        assert span.span_data is None
        
        tracer.enable()
        span2 = tracer.start_span("enabled_op")
        assert span2.span_data is not None


class TestAlertManager:
    """Testes para AlertManager."""

    def test_create_alert(self):
        """Testa criação de alerta."""
        manager = AlertManager(service_name="test")
        alert = manager.create_alert(
            name="high_cpu",
            severity=AlertSeverity.WARNING,
            message="CPU usage above 80%"
        )
        
        assert alert is not None
        assert alert.name == "high_cpu"
        assert alert.severity == AlertSeverity.WARNING
        assert not alert.resolved

    def test_create_critical_alert(self):
        """Testa criação de alerta crítico."""
        manager = AlertManager()
        alert = manager.create_alert(
            name="service_down",
            severity=AlertSeverity.CRITICAL,
            message="Service is down"
        )
        
        assert alert.severity == AlertSeverity.CRITICAL

    def test_resolve_alert(self):
        """Testa resolução de alerta."""
        manager = AlertManager()
        alert = manager.create_alert(
            name="test",
            severity=AlertSeverity.INFO,
            message="Test alert"
        )
        
        resolved = manager.resolve_alert(alert.id, "Issue fixed")
        
        assert resolved
        assert alert.resolved
        assert alert.resolved_at is not None
        assert alert.metadata["resolution_message"] == "Issue fixed"

    def test_get_active_alerts(self):
        """Testa obtenção de alertas ativos."""
        manager = AlertManager()
        alert1 = manager.create_alert("alert1", AlertSeverity.INFO, "Message 1")
        alert2 = manager.create_alert("alert2", AlertSeverity.WARNING, "Message 2")
        manager.resolve_alert(alert1.id)
        
        active = manager.get_active_alerts()
        
        assert len(active) == 1
        assert active[0].id == alert2.id

    def test_get_alert_history(self):
        """Testa obtenção de histórico de alertas."""
        manager = AlertManager()
        
        for i in range(5):
            manager.create_alert(f"alert{i}", AlertSeverity.INFO, f"Message {i}")
        
        history = manager.get_alert_history()
        
        assert len(history) == 5

    def test_alert_cooldown(self):
        """Testa cooldown de alertas."""
        manager = AlertManager()
        manager._cooldown_period = timedelta(minutes=5)
        
        alert1 = manager.create_alert("duplicate", AlertSeverity.INFO, "First")
        alert2 = manager.create_alert("duplicate", AlertSeverity.INFO, "Second")
        
        # Second alert should be None due to cooldown
        assert alert1 is not None
        assert alert2 is None

    def test_notification_callback(self):
        """Testa callback de notificação."""
        manager = AlertManager()
        callback_called = []
        
        def notify(alert: Alert):
            callback_called.append(alert)
        
        manager.register_notification(notify)
        manager.create_alert("test", AlertSeverity.INFO, "Test")
        
        assert len(callback_called) == 1
        assert callback_called[0].name == "test"

    def test_clear_alerts(self):
        """Testa limpeza de alertas."""
        manager = AlertManager()
        manager.create_alert("alert1", AlertSeverity.INFO, "Message 1")
        manager.create_alert("alert2", AlertSeverity.WARNING, "Message 2")
        
        manager.clear()
        
        assert len(manager.get_active_alerts()) == 0
        assert len(manager.get_alert_history()) == 0


class TestGlobalInstances:
    """Testes para instâncias globais."""

    def test_get_metrics_registry_singleton(self):
        """Testa singleton do metrics registry."""
        reset_globals()
        
        registry1 = get_metrics_registry()
        registry2 = get_metrics_registry()
        
        assert registry1 is registry2

    def test_get_health_checker_singleton(self):
        """Testa singleton do health checker."""
        reset_globals()
        
        checker1 = get_health_checker()
        checker2 = get_health_checker()
        
        assert checker1 is checker2

    def test_get_tracing_manager_singleton(self):
        """Testa singleton do tracing manager."""
        reset_globals()
        
        tracer1 = get_tracing_manager()
        tracer2 = get_tracing_manager()
        
        assert tracer1 is tracer2

    def test_get_alert_manager_singleton(self):
        """Testa singleton do alert manager."""
        reset_globals()
        
        manager1 = get_alert_manager()
        manager2 = get_alert_manager()
        
        assert manager1 is manager2

    def test_reset_globals(self):
        """Testa reset de globals."""
        # Initialize globals
        get_metrics_registry()
        get_health_checker()
        get_tracing_manager()
        get_alert_manager()
        
        reset_globals()
        
        # Should create new instances
        registry = get_metrics_registry()
        assert registry is not None


class TestIntegration:
    """Testes de integração entre componentes."""

    @pytest.mark.asyncio
    async def test_full_monitoring_workflow(self):
        """Testa workflow completo de monitoramento."""
        reset_globals()
        
        # Setup
        metrics = get_metrics_registry()
        health = get_health_checker("integration-test")
        tracer = get_tracing_manager()
        alerts = get_alert_manager()
        
        # Register health check
        health.register("api", lambda: HealthCheckResult("api", HealthStatus.HEALTHY))
        
        # Start trace
        with tracer.trace("send_event") as span:
            span.set_tag("event_type", "S-1000")
            
            # Record metrics
            request_counter = metrics.counter("events_sent", "Events sent")
            request_counter.inc()
            
            duration_histogram = metrics.histogram("send_duration", "Send duration")
            with duration_histogram.time():
                await asyncio.sleep(0.01)
            
            # Check health
            results = await health.run_all_checks()
            assert results["api"].status == HealthStatus.HEALTHY
        
        # Verify metrics
        assert metrics.get_counter_value("events_sent") == 1.0
        assert len(metrics.get_histogram_values("send_duration")) == 1
        
        # Verify trace
        spans = tracer.get_spans()
        assert len(spans) == 1
        assert spans[0]["operation_name"] == "send_event"
        
        # Create alert if needed
        if len(spans) > 100:
            alerts.create_alert("too_many_spans", AlertSeverity.WARNING, "High trace volume")
        
        active_alerts = alerts.get_active_alerts()
        assert len(active_alerts) == 0

    def test_metrics_with_health_integration(self):
        """Testa integração entre métricas e health."""
        metrics = MetricsRegistry()
        health = HealthChecker()
        
        # Track health check executions
        check_counter = metrics.counter("health_checks_total", "Health checks")
        health_gauge = metrics.gauge("health_status", "Health status")
        
        def tracked_check():
            check_counter.inc()
            health_gauge.set(1.0)
            return HealthCheckResult("db", HealthStatus.HEALTHY)
        
        health.register("db", tracked_check)
        
        # Run check
        asyncio.run(health.run_check("db"))
        
        assert metrics.get_counter_value("health_checks_total") == 1.0
        assert metrics.get_gauge_value("health_status") == 1.0

    def test_tracing_with_alerts(self):
        """Testa integração entre tracing e alertas."""
        tracer = TracingManager()
        alerts = AlertManager()
        
        error_count = 0
        
        def detect_errors(span_data):
            nonlocal error_count
            if span_data.get("status") == "ERROR":
                error_count += 1
                if error_count >= 3:
                    alerts.create_alert(
                        "high_error_rate",
                        AlertSeverity.CRITICAL,
                        "High error rate detected"
                    )
        
        # Simulate errors
        for i in range(3):
            with tracer.trace(f"op_{i}") as span:
                span.set_status("ERROR")
                detect_errors(span.span_data)
        
        active_alerts = alerts.get_active_alerts()
        assert len(active_alerts) == 1
        assert active_alerts[0].name == "high_error_rate"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
