# Web Application (Phase 11)

SPA at [`frontend/`](../frontend) — Vite + React + TypeScript.

## Sections

| Area | Notes |
|------|--------|
| Dashboard | Role-specific focus (manager / seller / marketing / viewer) |
| Work Items | Progress, tasks, timeline |
| Cases | Create + timeline / SLA badges |
| Inventory | Vehicle list/detail with linked WorkItems/Cases/history |
| Search | Calls `/search` |
| AI Assistant | Calls `/agent/communication` |
| Notifications | Inbox |

## Auth

JWT via `POST /auth/login`, stored in `localStorage`, sent as Bearer.

## Dev proxy

`/api/*` → backend `:8000`.
