# Assignment Engine (Phase 9)

Deterministic routing. AI may recommend; business rules control auto-assign.

```text
Request
  → Eligible users (active)
  → Availability filter
  → Branch / Department / Team filter
  → Role filter
  → Skill filter
  → Workload scoring
  → Ranked recommendation
```

## API

- `POST /assignment/recommend` — ranked candidates + `recommended_user_id`
- `POST /assignment/apply` — assign task (`user_id` required unless `ASSIGNMENT_AUTO_ASSIGN_ENABLED=true`)
- `POST /assignment/users/{id}/skills` — attach skill codes

## Scoring (simple)

- Base 100
- + branch/team/dept/role/skill matches
- − 5 × open tasks

## Agent tool

`recommend_assignees` available to CommunicationAgent.

## Config

`ASSIGNMENT_AUTO_ASSIGN_ENABLED=false` by default.
