# Hybrid RAG (Phase 6)

```text
User Query
  → QueryAnalyzer (deterministic)
  → Permission check
  → SQL/Exact/Text (/search)  +  Vector (/rag)
  → Reciprocal Rank Fusion
  → Rerank (exact / multi-source boosts)
  → Context Builder (char-capped)
  → Extractive answer stub (LLM later)
```

## API

`POST /rag/hybrid`

```json
{
  "query": "Find silver Camry stock #666",
  "entity_types": ["vehicle", "work_item"],
  "top_k": 8,
  "context_char_limit": 4000
}
```

Returns: `request_id`, analyzed fields, fused hits with `sources`, `context`, grounded `answer`.

## Rules

- Never dump the whole DB into context.
- VIN / status / price remain SQL-primary (`exact` channel wins via rerank boosts).
- Answer is extractive stub until CommunicationAgent (Phase 7).
