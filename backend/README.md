# CM Backend — Communication & Operations Platform

Phase 0/1 API for organizational communication, WorkItems, Cases, and Tasks.

## Local development

```bash
# From repo root
cp .env.example .env

# Start Postgres + Redis (requires Docker)
docker compose up -d postgres redis

# Backend
cd backend
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

## Tests

Tests use SQLite in-memory by default (no Docker required):

```bash
cd backend
uv run pytest -q
```

## Health

`GET /health` → `{"status":"ok"}`
