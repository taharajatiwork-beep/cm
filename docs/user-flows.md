# User Flows — CM Ops

## Flow A — Morning open (any role)

```text
Login → Home (“الان چه خبر است؟”)
  → story card: goal + who does what + deadline
  → open → people / actions / conversation / next step
```

Success: user acts within 2 clicks of login without learning Work Item / Case names.

---

## Flow B — Manager assigns Camry work

```text
Inventory → Camry #124
  → assign shared goal
  → action for رضا (customer)
  → action for سارا / Marketing (listing)
  → same page: checklist + next step + conversation link
```

Success: no need to visit Cases / Tasks as separate nav destinations.

---

## Flow C — Seller does today’s work

```text
Home or My Work (“روی من”)
  → open action / complete
  → optional open parent shared goal for context
```

---

## Flow D — Communication (org inbox)

```text
Communication
  → Needs my reply | Shared goals | Branch requests | Campaigns | Team activity
  → open thread: about what + who spoke + reply
  → jump to related shared goal if linked
```

---

## Flow E — Find anything

```text
Top bar search → type “Camry” / “رضا” / “مشهد”
  → open vehicle / person / shared goal
```

---

## Flow F — Ask AI

```text
My Work / Vehicle / Home
  → “از دستیار بپرس”
  → AI with implied context
```

Standalone `/agent` remains for power users.

---

## Flow H — Request to project to report

```text
Manager → /requests → new request (ads / price / general)
  → marketing triage
      → project (one or more, team + kind) → /projects/:id
      → or one operational task (price)
  → tasks, thread, cost (manager then finance)
  → /reports?scope=me|team|team_tree|org
```

Success: the requester reads the project and writes in its thread. Payment and price confirmation stay on their own pages.

---

## First-time user checklist

1. Find what’s happening — Home story cards  
2. See who needs my reply — Communication  
3. Find a vehicle — Inventory or search  
4. See who is responsible — Shared goal detail  
5. Assign Sales + Marketing — two actions on one goal  
6. See next step — same detail page  
7. Talk in context — Communication linked to goal / campaign  
