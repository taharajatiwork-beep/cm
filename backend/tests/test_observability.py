"""Tests for observability: metrics, health endpoints, structured logging."""

import pytest
from httpx import AsyncClient

from app.core.metrics import (
    record_request,
    record_latency,
    render_metrics,
    async_timed_request,
)


class TestMetrics:
    """Test Prometheus metrics collection and rendering."""

    def setup_method(self):
        """Reset metrics before each test."""
        import app.core.metrics as metrics
        metrics._requests.clear()
        metrics._request_latency.clear()

    def test_record_request_increments_counter(self):
        record_request("GET", "200")
        record_request("GET", "200")
        record_request("POST", "201")
        output = render_metrics()
        assert 'cm_http_requests_total{method="GET",status="200"} 2' in output
        assert 'cm_http_requests_total{method="POST",status="201"} 1' in output

    def test_record_latency_buckets(self):
        record_latency("GET", "/api/test", 0.005)  # < 0.01
        record_latency("GET", "/api/test", 0.03)   # 0.05 bucket
        record_latency("POST", "/api/other", 0.15) # 0.25 bucket
        
        output = render_metrics()
        assert 'cm_http_request_duration_seconds_bucket{method="GET",path="/api/test",le="0.01"} 1' in output
        assert 'cm_http_request_duration_seconds_bucket{method="GET",path="/api/test",le="0.05"} 1' in output
        assert 'cm_http_request_duration_seconds_bucket{method="POST",path="/api/other",le="0.25"} 1' in output

    def test_render_metrics_format(self):
        record_request("GET", "200")
        record_latency("GET", "/api/test", 0.05)
        output = render_metrics()
        assert output.startswith("# HELP cm_http_requests_total")
        assert "# TYPE cm_http_requests_total counter" in output
        assert "cm_http_request_duration_seconds_bucket" in output


class TestHealthEndpoints:
    """Test health check endpoints."""

    @pytest.mark.asyncio
    async def test_health_live(self, client: AsyncClient):
        r = await client.get("/health/live")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_health_ready(self, client: AsyncClient):
        r = await client.get("/health/ready")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ready"

    @pytest.mark.asyncio
    async def test_metrics_endpoint(self, client: AsyncClient):
        r = await client.get("/metrics")
        assert r.status_code == 200
        assert "text/plain" in r.headers.get("content-type", "")
        text = r.text
        assert "cm_http_requests_total" in text


class TestStructuredLogging:
    """Test JSON log formatting and secret masking."""

    def test_json_formatter_masks_secrets(self):
        from app.core.logging import _SECRET
        
        test_str = "token=abc123 secret=xyz password=12345 api_key=key123"
        masked = _SECRET.sub(r"\1\2 ***", test_str)
        assert "abc123" not in masked
        assert "xyz" not in masked
        assert "12345" not in masked
        assert "key123" not in masked
        assert "***" in masked


class TestRequestTiming:
    """Test async request timing context manager."""

    @pytest.mark.asyncio
    async def test_async_timed_request_records_latency(self):
        import app.core.metrics as metrics
        metrics._request_latency.clear()
        
        async with async_timed_request("GET", "/test"):
            pass  # minimal work
        
        output = render_metrics()
        assert "cm_http_request_duration_seconds_bucket" in output
        assert 'method="GET"' in output
        assert 'path="/test"' in output


class TestHealthDetailed:
    """Test detailed health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_detailed_returns_info(self, client: AsyncClient):
        r = await client.get("/health/detailed")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert "database" in data
        assert "service" in data


# CI: run with pytest -q --tb=short