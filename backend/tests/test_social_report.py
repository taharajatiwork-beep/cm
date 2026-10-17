from app.perf.services.social_report import _avg, _parse_day


def test_parse_day():
    assert _parse_day("2026-03-01").isoformat() == "2026-03-01"


def test_avg():
    assert _avg([2, 4]) == 3.0
    assert _avg([]) is None
