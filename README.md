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

Demo login: org `autoco` · `ali@autoco.example` / `password`

## Tests

```bash
cd backend
uv sync --extra dev
uv run pytest -q
```

Tests use in-memory SQLite (no Docker required).

## Docs

- **[Project overview (FA)](docs/project-overview.md)** — توضیح کامل فارسی
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
