# Collaboration Core

This phase makes **organized communication and collaboration** the product foundation.

## What already existed (reused)

- Organization → Branch / Department / Team / User / Role / Permissions
- `relationships` table (`MANAGES`, `REPORTS_TO`, `WORKS_WITH`, `COLLABORATES_WITH`, …)
- WorkItem as shared goal + participants
- Case + Task + TaskAssignee / TaskParticipant / TaskDependency
- Team / Department / Branch assignment targets on Task
- Delegation (audit + notify)
- SLA evaluate + escalation events
- Conversation / Message linked to WorkItem / Case / Vehicle
- Timeline Events + Notifications + AuditLog
- AssignmentEngine (role, skill, branch, team, workload)
- Telegram adapter as channel (not source of truth)
- Communication agent creating WorkItem + multi-person tasks

## What this phase completed

### APIs

| Endpoint | Purpose |
|----------|---------|
| `GET /people`, `/people/{id}`, `/people/{id}/reports` | People directory |
| `GET /teams`, `/departments`, `/branches`, `/relationships` | Org structure |
| `GET /work-items` | List collaboration hubs |
| `POST /work-items/{id}/participants` | Add collaborators |
| `GET /tasks`, `POST /tasks/{id}/assign`, `POST /tasks/{id}/participants` | Task collaboration |
| `GET /tasks/{id}/timeline`, `GET /cases/{id}/timeline` | Per-entity history |
| `GET /conversations?work_item_id=` | Communication linked to work |
| `GET /users/{id}/workload` | Open / overdue load |

### AI tools

- `create_task` / `assign_task` now accept team / department / branch targets.

### AssignmentEngine

- Optional `related_user_id` boosts collaborators from the org relationship graph.

### Frontend

Nav exposes: Communication, Work Items, Cases, Tasks, People, Teams, Branches (+ existing Inventory / Customers / AI).

Work Item detail shows participants, assignees, team targets, linked conversations, timeline.

### Tests

- Existing Phase 1 Camry Reza/Sara acceptance, deps, delegation, SLA, permissions
- Existing Phase 3 Telegram → WorkItem flow
- New `test_collaboration_core.py` for list APIs, team task, participants, workload, assign

## Definition of done (manager path)

```text
Manager creates WorkItem
  → assigns Reza (seller) + Sara/Marketing (team target)
  → both under one WorkItem
  → notifications fire
  → progress / timeline visible
  → overdue / SLA surface without WhatsApp chasing
```

## Intentionally deferred

- Multi-team membership (M2M) — user still has single `team_id`
- Hard DataScope query filtering beyond permission codes
- Graph database
- Autonomous sales / purchase / Divar automation
