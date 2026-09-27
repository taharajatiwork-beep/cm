# CM Ops Web App

Vite + React + TypeScript UI for the Communication & Operations platform.

## Run

```bash
# Terminal 1 — API
cd backend
uv run uvicorn app.main:app --reload --port 8000

# Terminal 2 — UI
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — Vite proxies `/api` → `http://127.0.0.1:8000`.

## Features

- Role-aware dashboard (manager / seller / marketing / viewer)
- Work Items (list, progress, task complete, timeline)
- Cases (create + timeline)
- Inventory (list/create/detail with linked work + history)
- Search, CommunicationAgent, Notifications

## Design

Internal ops chrome: charcoal nav, steel-teal accent, Sora + IBM Plex Sans.
