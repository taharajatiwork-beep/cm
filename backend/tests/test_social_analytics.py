"""Unit tests for social rollup helpers."""

from app.perf.services.social_analytics import _open_count, _redact_sample, _status_open


def test_status_open_closed_numeric():
    assert _status_open(2) is False
    assert _status_open("closed") is False
    assert _status_open(1) is True
    assert _status_open(None) is True


def test_open_count():
    items = [{"status": 1}, {"status": 2}, {"status": "open"}]
    assert _open_count(items) == 2


def test_redact_sample():
    text = "@user123 call 09123456789 please"
    out = _redact_sample(text)
    assert "@…" in out
    assert "09123456789" not in out
