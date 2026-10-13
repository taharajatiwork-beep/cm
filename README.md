# CM — Automotive Communication & Operations Platform

AI-native internal platform for a multi-branch automotive company.

**توضیح کامل فارسی:** [docs/project-overview.md](docs/project-overview.md)

**Current milestone:** Phase 0–15 — Core, Agents, light CRM, LLM planner, Campaigns.

## Quick start

```bash
cp .env.example .env

# API
cd backend
uv sync --extra dev
uv run uvicorn app.main:app --reload --port 8000

# Demo data (optional)
uv run python -m scripts.seed_demo

# Web UI (another terminal)
cd frontend
npm install
npm run dev
```

- API docs: http://localhost:8000/docs  
- Web app: http://localhost:5173  
- Health: http://localhost:8000/health  
- Readiness (checks DB): http://localhost:8000/health/ready  
- Metrics: http://localhost:8000/metrics  

Demo login: org `autoco` · `ali@autoco.example` / `password`

## Tests

```bash
cd backend
uv sync --extra dev
uv run pytest -q
```

Tests and the API use PostgreSQL (`docker compose up postgres`). Pytest uses `cm_test` so demo data on `cm` is left alone. `tests/test_deploy_secrets.py` and
`tests/test_production_guard.py` read the deployment files directly, so they
catch a hardcoded secret or an unsafe production default before it ships.

```bash
cd frontend
npx tsc -b && npm run lint && npm test && npm run build
npm run e2e        # starts its own API + web server
```

### Load test

`backend/scripts/loadtest.py` drives the busiest endpoints with N concurrent
users and fails if any p95 exceeds its budget. No extra dependency — stdlib
only, in-process ASGI.

```bash
cd backend
uv run python -m scripts.loadtest --users 20 --rounds 3
uv run python -m scripts.loadtest --print-only   # baseline, budgets not enforced
```

Budgets come from a real 20-user run on SQLite (WAL on): `login` is the slowest
at ~1.5s p50 because bcrypt is intentionally expensive. Rerun with
`--print-only` after schema or query changes and update `BUDGETS_MS` if a
regression is expected.

By default the script uses a throwaway SQLite file. Point it at a real
PostgreSQL to measure production-like numbers:

```bash
LOADTEST_DATABASE_URL=postgresql+asyncpg://cm:cm@localhost:5432/cm \
  uv run python -m scripts.loadtest --users 20 --rounds 3
```

CI runs the load test against PostgreSQL, so the budgets are checked against
the real engine rather than SQLite.

### Verifying the audit hash chain

Audit rows are append-only at the API level, but direct database access could
still edit or delete them. Since migration `0011` every row carries a
`row_hash` built from its own contents plus the previous row's hash, so any
tampering is detectable.

```bash
cd backend
uv run python -m scripts.verify_audit_chain            # all orgs
uv run python -m scripts.verify_audit_chain --org autoco
uv run python -m scripts.verify_audit_chain --json     # for monitoring
```

Exit code is `1` if any organization has a broken chain, and the output names
the first broken row. CI runs this too.

## Production deployment

1. **Generate the secrets.** Do not hand-write passwords — the script makes
   five distinct random values and embeds the database password into
   `DATABASE_URL` correctly (URL-escaped, host `postgres`, not `localhost`):

   ```bash
   sh deploy/make-secrets.sh      # writes .env.prod.local, mode 600
   # edit CORS_ORIGINS to your real https host, then:
   cp .env.prod.local .env
   ```

   Re-running refuses to overwrite the existing file. Keep
   `BACKUP_PASSPHRASE` in a password manager as well — losing it means losing
   every backup.

   For local development only, `cp .env.example .env` still works.

2. **Put a TLS certificate in `deploy/certs/`** — `tls.crt` and `tls.key`.

3. **Start everything:**

   ```bash
   docker compose -f docker-compose.prod.yml up -d --build
   ```

The API refuses to boot in production when any of these is unsafe: `DEBUG=true`,
a placeholder or short `SECRET_KEY`, `COOKIE_SECURE=false`, an `http://` CORS origin,
`WORKER_MODE=embedded`, or a SQLite `DATABASE_URL`. All problems are reported at
once so you do not fix them one restart at a time.

Runbooks: [deploy](docs/runbooks/deploy.md) · [backup & restore](docs/runbooks/backup.md)

## Architecture at a glance

```
frontend (React + Vite, RTL Persian)  ──HTTPS──▶  nginx  ──▶  api (FastAPI)
                                                                  │
                                              ┌───────────────────┴──────────┐
                                          Postgres + pgvector          Redis
                                              │                             │
                                          worker (outbox, SLA,          rate limit,
                                          Telegram polling, KPIs)      leader lock
```

- **Backend:** `backend/app` — `api/routes` (HTTP), `services` (business logic),
  `models` (SQLAlchemy), `core` (config, security, scope, locks, metrics), `ai`,
  `integrations` (Telegram, channels).
- **Frontend:** `frontend/src` — `pages`, `components`, `lib`. All copy is Persian
  and RTL; enums have Persian labels in `src/labels.ts` and `src/ux.tsx`.
- **Data scoping:** every query is filtered by `core/scope.py` (org → branch → self).

Full details: [architecture](docs/architecture.md) · [domain model](docs/domain-model.md)

## Docs

- **[Project overview (FA)](docs/project-overview.md)** — توضیح کامل فارسی
- [Security & audit](docs/security-and-audit.md) — کنترل‌های امنیتی، زنجیرهٔ هش ممیزی، واکنش به حادثه
- [Architecture](docs/architecture.md)
- [Domain model](docs/domain-model.md)
- [Collaboration](docs/collaboration.md)
- [Information architecture](docs/information-architecture.md)
- [Communication](docs/communication.md)
- [CRM](docs/crm.md)
- [Search](docs/search.md)
- [Hybrid RAG](docs/hybrid-rag.md)
- [Communication Agent](docs/communication-agent.md)
- [Assignment Engine](docs/assignment-engine.md)
- [Web App](docs/web-app.md)
- [Knowledge Base](docs/knowledge-base.md)
- [AI architecture](docs/ai-architecture.md)
- [Development roadmap](docs/development-roadmap.md)

## Bootstrap a demo org

```http
POST /auth/bootstrap
{
  "organization_name": "AutoCo",
  "organization_slug": "autoco",
  "admin_email": "admin@autoco.test",
  "admin_name": "Admin",
  "admin_password": "secret12"
}
```
