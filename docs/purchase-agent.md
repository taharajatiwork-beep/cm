# PurchaseAgent

Tool-only agent for purchase signals on Core cases + inventory demand.

## Capabilities

1. **Pipeline** — list open `SELLER_REQUEST` cases
2. **Unmet demand** — buyer/interest / inventory requests for models with **zero** in-stock
3. **Stale seller offers** — open `SELLER_REQUEST` older than `purchase_stale_days`
4. **Create** — Case + WorkItem + task (`Purchase opportunity:` / `Purchase follow-up:`)

## API

`POST /agent/purchase`

```json
{
  "message": "scan only",
  "stale_days": 3,
  "auto_create": true
}
```

Requires `agent.run`.

## Tools

- `list_purchase_pipeline`
- `detect_purchase_opportunities`
- `create_purchase_opportunity`

## Config

| Setting | Default |
|---------|---------|
| `purchase_stale_days` | 3 |
| `purchase_auto_create_opportunity` | true |
