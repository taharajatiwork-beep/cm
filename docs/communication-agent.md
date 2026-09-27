# CommunicationAgent (Phase 7)

```text
User message
  → RulesPlanner (deterministic; LLM-swappable later)
  → Tools (RBAC-checked)
  → Domain services
  → DB + AiActionLog
```

## API

`POST /agent/communication`

```json
{ "message": "برای این کمری، رضا مشتری رو پیگیری کنه و سارا تبلیغات رو انجام بده." }
```

Returns: `request_id`, intent, clarification, work_item/tasks, `tool_trace`.

## Tools

Read: `search_inventory`, `get_vehicle`, `find_users`, `find_team`, `find_branch`,
`get_case`, `get_case_history`, `search_messages`, `get_pending_tasks`, `get_user_workload`

Write: `create_work_item`, `create_case`, `create_task`, `assign_task`, `assign_case`,
`send_notification`, `escalate_case`, `summarize_case`

## Rules

- Tools share the same permission model as humans.
- Never invent vehicles or people — clarify on ambiguity.
- Every tool call is written to `ai_action_logs`.
- Planner is rules-based (`rules-v1`); replaceable with LLM planner without changing tools.
