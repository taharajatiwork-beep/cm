# InventoryAgent

Tool-only agent that detects inventory opportunities from structured signals.

## Signals

1. **Aging** — vehicle `IN_STOCK` longer than `inventory_aging_days` (default 30)
2. **Branch demand** — open `InventoryRequest`s from ≥ `inventory_min_branch_requests` distinct branches
3. **Customer interest** — open `CUSTOMER_INTEREST` cases on the vehicle

Opportunity = aged **and** (branch demand **or** customer interest). Vehicles with an open `INVENTORY_OPPORTUNITY` case are skipped.

## API

`POST /agent/inventory`

```json
{
  "message": "scan only",
  "min_days": 30,
  "min_branch_requests": 2,
  "auto_create": true
}
```

Requires `agent.run`. Mutating tools still need `inventory.read` / `case.write` / `work_item.write`.

## Tools

- `list_aging_inventory`
- `list_inventory_requests`
- `detect_inventory_opportunities`
- `create_inventory_opportunity` → Case `INVENTORY_OPPORTUNITY` + optional WorkItem

## Config

| Setting | Default |
|---------|---------|
| `inventory_aging_days` | 30 |
| `inventory_min_branch_requests` | 2 |
| `inventory_auto_create_opportunity` | true |
