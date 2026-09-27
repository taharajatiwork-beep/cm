# CRM (light)

`customers` table linked to Cases / WorkItems / Conversations via `customer_id`.

## API

- `POST /customers`
- `GET /customers?q=`
- `GET /customers/{id}`
- `PATCH /customers/{id}`

Permissions: `customer.read`, `customer.write`.

## Agent tool

`find_customers` — search by name/phone (never invent IDs).
