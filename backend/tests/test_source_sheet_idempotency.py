from types import SimpleNamespace

from app.perf.services.source_sheets import pending_source_export, register_rows


def test_register_skips_exported_campaigns():
    exported = SimpleNamespace(code="S99", title="x", starts_on=None, created_at=None, source_sheet_exported_at=object())
    fresh = SimpleNamespace(code="S100", title="y", starts_on=None, created_at=None, source_sheet_exported_at=None)
    rows = register_rows(pending_source_export([exported, fresh]), set())
    assert len(rows) == 1 and rows[0][2] == "S100"
