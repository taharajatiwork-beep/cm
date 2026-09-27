# Architecture

## Purpose

Internal AI-native communication and operations platform for a multi-branch automotive company.

**Phase 1 priority:** turn informal communication into structured organizational work (WorkItems, Cases, Tasks) with ownership, history, and next actions.

## Layering

```text
PostgreSQL     = Source of Truth
pgvector       = Semantic retrieval (Phase 5+, not implemented yet)
Web / Telegram = Interfaces (Telegram Phase 3+, Web Phase 11+)
AI Agents      = Understanding + tools (Phase 7+)
Business Rules = Deterministic logic (RBAC, SLA, dependencies)
Audit / Events = Append-only traceability
```

Never use Telegram or a vector store as the primary source of truth.

## Current stack (Phase 0/1)

| Layer | Choice |
|-------|--------|
| API | Python 3.12 + FastAPI |
| ORM | SQLAlchemy 2.0 async |
| Migrations | Alembic |
| DB | PostgreSQL 16 (Docker); SQLite for tests |
| Auth | JWT + local password hashes |
| Cache | Redis in Compose (reserved) |

## Package layout

```text
backend/app/
  api/          # HTTP routers (thin)
  core/         # config, security, permissions, logging
  db/           # engine, session, Base
  models/       # explicit domain tables
  schemas/      # Pydantic request/response
  services/     # domain services + event emission
```

## Request flow

```text
HTTP → Auth (JWT) → Permission check → Domain service → PostgreSQL
                                         ↓
                                      Event (append-only)
                                         ↓
                                      Notification (optional)
```

## What is intentionally not built yet

- Telegram adapter
- Inventory module (only nullable `vehicle_id` stubs)
- RAG / embeddings
- CommunicationAgent / tool calling
- Web UI
- Divar / sales / purchase agents
