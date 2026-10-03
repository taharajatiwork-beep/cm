"""Observability: Prometheus metrics, structured JSON logging, request timing."""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from contextlib import asynccontextmanager, contextmanager
from typing import Any

from sqlalchemy import text

# Prometheus metrics (no external dependency)
_requests: Counter[tuple[str, str]] = Counter()
_request_latency: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
_histogram_buckets = [0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]


def record_request(method: str, status: str) -> None:
    _requests[(method, status)] += 1


def record_latency(method: str, path: str, duration_seconds: float) -> None:
    """Record request latency into histogram buckets."""
    bucket = "+Inf"
    for b in _histogram_buckets:
        if duration_seconds <= b:
            bucket = str(b)
            break
    _request_latency[(method, path)][bucket] += 1


def render_metrics() -> str:
    lines = [
        "# HELP cm_http_requests_total HTTP requests",
        "# TYPE cm_http_requests_total counter",
    ]
    for (method, status), count in sorted(_requests.items()):
        lines.append(f'cm_http_requests_total{{method="{method}",status="{status}"}} {count}')
    if len(lines) == 2:
        lines.append('cm_http_requests_total{method="GET",status="0"} 0')

    # Latency histogram
    lines.append("")
    lines.append("# HELP cm_http_request_duration_seconds HTTP request latency")
    lines.append("# TYPE cm_http_request_duration_seconds histogram")
    for (method, path), buckets in sorted(_request_latency.items()):
        for bucket, count in sorted(buckets.items()):
            lines.append(f'cm_http_request_duration_seconds_bucket{{method="{method}",path="{path}",le="{bucket}"}} {count}')
    return "\n".join(lines) + "\n"


# ============================================================
# Structured JSON Logging
# ============================================================

class JsonFormatter:
    """Format log records as JSON lines for ELK/Loki ingestion."""

    def __init__(self, service: str = "cm"):
        self.service = service

    def format(self, level: str, message: str, **fields: Any) -> str:
        record = {
            "timestamp": time.time(),
            "level": level.upper(),
            "service": self.service,
            "message": message,
            **fields,
        }
        return json.dumps(record, ensure_ascii=False)


json_formatter = JsonFormatter()


def get_json_logger(service: str = "cm"):
    """Return a callable that logs JSON to stdout."""
    formatter = JsonFormatter(service)

    def log(level: str, message: str, **fields: Any):
        print(formatter.format(level, message, **fields), flush=True)

    return log


# Convenience loggers for common modules
log = get_json_logger("cm")
db_log = get_json_logger("cm.db")
http_log = get_json_logger("cm.http")
ai_log = get_json_logger("cm.ai")
telegram_log = get_json_logger("cm.telegram")


# ============================================================
# Request timing context managers
# ============================================================

@contextmanager
def timed_request(method: str, path: str):
    """Synchronous context manager to time a request and record metrics."""
    start = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start
        record_latency(method, path, duration)


@asynccontextmanager
async def async_timed_request(method: str, path: str):
    """Asynchronous context manager to time a request and record metrics."""
    start = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start
        record_latency(method, path, duration)


# ============================================================
# Health check endpoint data
# ============================================================

async def health_check_data() -> dict[str, Any]:
    """Aggregate health information for /health endpoint."""
    from app.core.config import get_settings
    from app.db.session import WorkerSessionLocal

    settings = get_settings()
    db_ok = False
    try:
        # probe فقط می‌خواند — انجین ورکر (deferred) تا قفل نوشتن نگیرد
        async with WorkerSessionLocal() as db:
            await db.execute(text("SELECT 1"))
            db_ok = True
    except Exception as exc:  # noqa: BLE001 - readiness probe: any failure means "db down"
        # get_json_logger returns a callable(level, message, **fields), not a Logger
        log("warning", "readiness_db_check_failed", error=str(exc))

    return {
        "status": "ok" if db_ok else "degraded",
        "service": "cm",
        "version": "0.1.0",
        "environment": settings.app_env,
        "database": "connected" if db_ok else "disconnected",
        "workers": "embedded",  # could read from worker status
    }