# Knowledge Base (Phase 12)

```text
Upload
  → Parse (text/markdown; PDF text-extracted by client for now)
  → Clean
  → Chunk
  → Metadata
  → Embedding (via RagService)
  → Retrieve (POST /knowledge/search)
```

## Categories

`COMPANY_KNOWLEDGE`, `POLICY`, `SOP`, `BRANCH_RULES`, `SALES_RULES`, `PURCHASE_RULES`, `COMMUNICATION_RULES`, `OTHER`

## API

- `POST /knowledge/documents` — upload (+ optional auto index)
- `GET /knowledge/documents`
- `GET /knowledge/documents/{id}`
- `POST /knowledge/documents/{id}/index`
- `POST /knowledge/search`

Permissions: `kb.read`, `kb.write` (+ `rag.index` / `rag.read` for embed/retrieve).

## Tables

`documents`, `document_chunks` — structured truth for KB; vectors live in `embeddings` with `entity_type=document`.
