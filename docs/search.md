# Search

Phase 4 — structured search before RAG.

## Modes

| Mode | Use |
|------|-----|
| Exact | VIN, case number, stock number, email |
| Text | `ilike` on brand/model/subject/title/name (SQLite-safe; Postgres FTS later) |
| Filters | `status`, `branch_id`, `date_from` / `date_to`, entity `types` |

## API

`GET /search`

Query params:

- `q` — free text
- `types` — comma list: `vehicle,case,user,work_item`
- `vin`, `case_number`, `stock_number`, `employee`
- `status`, `branch_id`, `date_from`, `date_to`
- `limit` (1–100)

Requires permission `search.run`.

## Not in this phase

- Vector / semantic search (Phase 5)
- Hybrid fusion / reranking (Phase 6)
- LLM answers (Phase 7+)
