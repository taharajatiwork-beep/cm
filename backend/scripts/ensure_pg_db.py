"""Create the PostgreSQL database named in DATABASE_URL if it does not exist.

Usage:
  DATABASE_URL=postgresql+asyncpg://cm:cm@localhost:5432/cm_e2e python -m scripts.ensure_pg_db
"""

from __future__ import annotations

import asyncio
import os
import sys

import asyncpg
from sqlalchemy.engine.url import make_url


def _dsn(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


async def _ensure(url: str) -> None:
    parsed = make_url(_dsn(url))
    name = parsed.database
    if not name:
        raise SystemExit("DATABASE_URL has no database name")
    conn = None
    last_error: Exception | None = None
    for admin_db in ("postgres", "cm", parsed.database):
        if not admin_db:
            continue
        try:
            admin = parsed.set(database=admin_db)
            conn = await asyncpg.connect(admin.render_as_string(hide_password=False))
            break
        except Exception as exc:  # noqa: BLE001 — try the next maintenance database
            last_error = exc
    if conn is None:
        raise SystemExit(f"Could not connect to PostgreSQL: {last_error}")
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{name}"')
            print(f"created database {name}")
        else:
            print(f"database {name} exists")
    finally:
        await conn.close()


def ensure_database(url: str | None = None) -> None:
    url = url or os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_TEST_URL") or ""
    if not url:
        raise SystemExit("Set DATABASE_URL (PostgreSQL).")
    if url.startswith("sqlite"):
        raise SystemExit("SQLite is not supported. Use PostgreSQL DATABASE_URL.")
    asyncio.run(_ensure(url))


def main() -> None:
    ensure_database()


if __name__ == "__main__":
    sys.exit(main() or 0)
