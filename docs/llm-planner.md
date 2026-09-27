# LLM Planner (9Router)

CommunicationAgent uses `LLMPlanner` when `LLM_PROVIDER` is set to `9router` / `openai`.

Falls back to deterministic `RulesPlanner` on any failure.

## Config (`.env`)

```text
LLM_PROVIDER=9router
LLM_API_BASE=http://localhost:20128/v1
LLM_API_KEY=...
LLM_MODEL=taha
```

Start [9Router](https://9router.com/) locally so `localhost:20128` is up (same setup as OpenCode).

Use the **combo name** from `http://localhost:20128/dashboard/combos` as `LLM_MODEL` (e.g. `taha`).

## Safety

- Planner may only propose allow-listed tools
- Search tools strip invented `id` / `vehicle_id` / `user_id` args
- Entity resolution ambiguity still forces clarification before mutations
- Tests force `LLM_PROVIDER=rules`
