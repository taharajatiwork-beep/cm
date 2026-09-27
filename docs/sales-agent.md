# SalesAgent

Tool-only agent for sales pipeline on Core cases (no separate CRM yet).

## Capabilities

1. **Pipeline** — list open `BUYER_REQUEST` / `CUSTOMER_INTEREST` / `FOLLOW_UP`
2. **Match** — map case subject hints (کمری/Camry, stock #) → in-stock vehicles
3. **Stale follow-up** — buyer/interest cases older than `sales_stale_days` without an open follow-up
4. **Create** — `FOLLOW_UP` case + WorkItem + seller task via AssignmentEngine

## API

`POST /agent/sales`

```json
{
  "message": "scan only",
  "stale_days": 3,
  "auto_create": true,
  "case_id": null
}
```

Message hints: `pipeline` / `list`, `match`, `scan`, `follow` / `پیگیری` / `create`.

Requires `agent.run`. Mutating tools need `case.write` / `work_item.write` / `task.write` / `task.assign`.

## Tools

- `list_sales_pipeline`
- `match_buyer_to_inventory`
- `detect_sales_follow_ups`
- `create_sales_follow_up`

## Config

| Setting | Default |
|---------|---------|
| `sales_stale_days` | 3 |
| `sales_auto_create_follow_up` | true |
