# AI Architecture

## Separation

| Concern | Owner |
|---------|--------|
| Permissions, SLA, approvals, hard workflow | Business rules (deterministic) |
| Intent, entity resolution, summarization, recommendation | AI (Phase 7+) |
| Structured truth (price, VIN, status, ids) | PostgreSQL + `/search` |
| Semantic memory | `embeddings` table + `/rag` (Phase 5) |

Never use an LLM where deterministic logic is required.  
AI must call the same authorization layer as humans.

## Phase 5 — Semantic memory (implemented)

```text
Content (message / case / vehicle narrative / work item)
  → chunk
  → EmbeddingProvider (hash | openai)
  → embeddings table (JSON vector; pgvector-ready shape)
  → cosine retrieval via POST /rag/query
```

### Table shape

`embeddings`: organization_id, entity_type, entity_id, chunk_id, content, content_hash,
embedding, embedding_model, embedding_version, metadata_json, timestamps.

Metadata may include `branch_id`, `vehicle_id`, `case_id`, `visibility_scope`.

### Rules

- Do **not** use vectors as primary source for VIN, price, status, branch_id, user_id.
- Default provider is deterministic `hash` for local/dev/tests.
- Set `EMBEDDING_PROVIDER=openai` + `EMBEDDING_API_KEY` for real embeddings.
- Production Postgres can swap storage to **pgvector** without changing the domain API.

### API

- `POST /rag/index` — index message | case | vehicle | work_item | custom
- `POST /rag/query` — semantic retrieval (`top_k`, filters, `request_id` in metadata)

Permissions: `rag.index`, `rag.read`.

## Future agent shape

```text
User message
  → CommunicationAgent
  → Tools (search_*, get_*, create_*, assign_*, notify_*, escalate_*)
  → Domain services
  → DB + Events + Audit
```

Sensitive tools (`reserve_vehicle`, price changes) will require stronger approval.

## Not yet

CommunicationAgent tool loop (Phase 7), LLM-generated answers with citations.
