# DivarAgent

Assisted Divar listing agent wired to the existing pilot at `C:\taha\projects\divar`.

## Principle

Divar is an **adapter**, never source of truth. Inventory + WorkItems stay in CM Postgres.

**Never** auto-login, solve captcha, or click final Divar submit. Human operator submits.

## Flow

```text
Vehicle (IN_STOCK)
  → map to Divar product (category=vehicles)
  → POST /api/products (+ optional /api/tasks) on Divar pilot
  → DivarListing row in CM
  → WorkItem + Case + review task
```

## API

`POST /agent/divar`

```json
{
  "message": "list candidates",
  "vehicle_id": null,
  "auto_create": true,
  "limit": 5
}
```

## Config

| Env / setting | Default | Notes |
|---------------|---------|--------|
| `divar_mode` | `fake` | `fake` for tests; `http` to call real pilot |
| `divar_api_base` | `http://localhost:3000` | Divar `npm start` |
| `divar_api_token` | `tok-admin-xyz` | From divar `auth.js` manager token |
| `divar_auto_prepare` | `true` | |

Run Divar pilot: `cd C:\taha\projects\divar && npm start`

## Tools

- `list_divar_candidates`
- `list_divar_listings`
- `prepare_divar_listing`
