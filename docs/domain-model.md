# Domain Model

## Organization

```text
Organization
 ├── Branches
 ├── Departments
 │    └── Teams
 ├── Roles → Permissions + DataScope
 └── Users
      ├── role, branch, department, team
      └── manager_id
```

## Relationships

Explicit graph edges (not roles alone):

- `MANAGES`
- `REPORTS_TO`
- `WORKS_WITH`
- `COLLABORATES_WITH`
- `MEMBER_OF`
- `DELEGATES_TO`

Supports queries: who manages X, who collaborates with X, team members, eligible assignees.

## Inventory (Phase 2)

```text
Vehicle
 ├── status (IN_STOCK | RESERVED | SOLD | …)
 ├── branch_id + VehicleBranch links
 ├── VehicleHistory (append-only status changes)
 └── InventoryRequest (branch interest / transfer / availability)

WorkItem / Case / Conversation.vehicle_id → vehicles.id
```

## Communication

```text
Conversation
 ├── channel (TELEGRAM | WEB | SYSTEM | …)
 ├── participants
 ├── optional links: branch, team, work_item, case, vehicle
 └── Messages (TEXT first; VOICE/IMAGE/DOCUMENT/SYSTEM/AI reserved)
```

## Collaboration

```text
WorkItem  (shared business goal)
 ├── Cases (CommunicationCase)
 ├── Tasks
 │    ├── TaskAssignee (OWNER | ASSIGNEE | REVIEWER | APPROVER | FOLLOWER)
 │    ├── TaskParticipant
 │    └── TaskDependency
 └── Participants
```

Tasks may assign to a **User** and/or a **Team / Department / Branch** target (`assignment_target_type` + `assignment_target_id`).

## SLA / Ops

- `SlaPolicy` — response + warning windows by priority
- `Notification` — WEB / SYSTEM / TELEGRAM channel types
- `Event` — append-only log (timeline source)
- `AuditLog` — sensitive actions (e.g. delegation)

## Stubs remaining

- Multi-team membership (user currently has a single `team_id` / `department_id` / `branch_id`)
- Hard enforcement of DataScope on every list query (scope levels are stored on roles)

See also: [collaboration.md](./collaboration.md)
