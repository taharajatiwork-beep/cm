# Development Roadmap

Execute in order. Each phase must be working and tested before the next.

| Step | Focus | Status |
|------|--------|--------|
| 0 | Foundation (repo, Docker, Postgres, migrations, logging, tests, docs) | **Done** |
| 1 | Organization + People + Teams + Relationships | **Done** |
| 2 | Communication Core (Conversation / Message) | **Done** |
| 3 | WorkItems + Cases + Tasks + deps + delegation | **Done** |
| 4 | SLA + Notifications + Timeline / Events | **Done** |
| 5 | Inventory core (Vehicle, history, branch links, requests) | **Done** |
| 6 | Telegram adapter | **Done** |
| 7 | Search (exact + FTS + filters) | **Done** |
| 8 | RAG / pgvector memory | **Done** (JSON cosine by default; `embedding_backend=pgvector` uses ANN only on PostgreSQL) |
| 9 | Hybrid RAG | **Done** |
| 10 | CommunicationAgent + tools | **Done** |
| 11 | Assignment engine | **Done** |
| 12 | Web application | **Done** (Vite/React MVP) |
| 13 | Knowledge base | **Done** |
| 14a | InventoryAgent (aging / demand / opportunity) | **Done** |
| 14b | SalesAgent (pipeline / match / follow-up) | **Done** |
| 14c | PurchaseAgent (unmet demand / seller offers) | **Done** |
| 14d | DivarAgent (assisted listing via existing divar pilot) | **Done** |
| 15 | Light CRM + LLM planner (9Router) + pgvector image | **Done** |
| 16 | Enterprise hardening (scope, audit, sessions, worker, deploy, reports, adapters) | **Done** |

## First vertical slice (target after Telegram + light entity resolution)

Manager message → entity resolution → WorkItem + tasks → notifications → SLA → progress → timeline.

Phase 1 delivers the **structured API + tests** for that collaboration model without NL/Telegram.

## Explicit non-goals for early phases

Full ERP, accounting, autonomous purchasing/pricing, multi-agent swarm, full CRM, Divar automation.
