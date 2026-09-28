"""Helpers so later migrations no-op when 0001 already created the current schema."""

from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.engine import Connection


def table_exists(bind: Connection, name: str) -> bool:
    return name in inspect(bind).get_table_names()


def column_exists(bind: Connection, table: str, column: str) -> bool:
    if not table_exists(bind, table):
        return False
    return any(col["name"] == column for col in inspect(bind).get_columns(table))
