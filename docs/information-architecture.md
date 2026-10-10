# Information Architecture — CM Ops

## Product lens: collaboration management

Users should experience:

```text
People ↔ Teams ↔ Conversations ↔ Shared goals ↔ Actions ↔ Outcome
```

Not a pile of entities (WorkItem / Case / Task jargon on first paint).

---

## Primary navigation (target: ≤ 8)

```text
خانه / Home          → What’s happening today?
کارهای من / My Work  → On me + shared goals
ارتباطات / Communication → Org inbox (reply / shared / branch / campaign / team)
موجودی / Inventory
مشتریان / Customers
افراد / People
دستیار / AI
تنظیمات / Settings
```

### Shell chrome (not primary nav peers)

- Global search (top bar)
- Notifications bell
- Language switch
- User / role / sign out

نقش‌ها چهار قالب‌اند (ادمین، مدیر، سرپرست، عضو). جزئیات و نگاشت کاربران در `docs/roles-plan.md` است. خانهٔ بخش در `/teams/:teamId` است و گزارش‌ها جدا هستند.

---

## Communication inbox sections

| Section | Question answered |
|---------|-------------------|
| Needs my reply | Who needs me? |
| Shared work | About which shared goal? |
| Conversations | All threads |
| Branch requests | Branch waiting on HQ/manager |
| Campaigns | Marketing pushes + their threads |
| Team activity | Recent chatter across threads |

Each thread should surface: **about what**, **who last spoke**, **linked goal/campaign**, **reply in place**.

---

## Home attention stories

Cards (not raw task rows):

```text
Title of shared goal / request / campaign
  Person → action
  Person → action
  Deadline
```

Click → shared goal detail: people, actions, conversation, **next step**.

---

## Route map

| User concept | Route | Notes |
|--------------|-------|-------|
| Home | `/` | Attention / “what’s happening” |
| My Work | `/my-work` | Actions on me + shared goals |
| Shared goal detail | `/work-items/:id` | Collaboration hub (human copy) |
| Communication | `/communication` | Org inbox + thread |
| Inventory | `/vehicles`, `/vehicles/:id` | Stock + contextual actions |
| Customers | `/customers` | Light CRM |
| People | `/people` | Directory + workload |
| AI | `/agent` | Natural language ops |
| Settings | `/settings` | Teams, branches, knowledge |
| Search | `/search` | Opened from top bar |
| Notifications | `/notifications` | Opened from bell |
| Follow-ups (cases) | `/cases` | Demoted; create from context |
| Knowledge | `/knowledge` | Also via Settings |

---

## Role frames (copy & defaults)

| Role | Home / Comm emphasis |
|------|----------------------|
| Manager | Waiting on me, overdue, branch requests, intervene |
| Seller | Assigned to me, who waits for my reply, customer work |
| Marketing | Campaigns, listing actions, what sales asked |

---

## Work spine

```text
/requests          queue and triage
/projects          list
/projects/:id      overview, tasks, links, chat, costs, activity, type
/my-work           overdue, today, later, waiting
/reports           KPIs plus GET /reports/work
```

Communication campaign labels say «موضوع گفتگو». Performance campaigns stay «کمپین».

---

## Success criteria

1. After login, user can act in ≤ 2 clicks without learning entity names.
2. Opening a shared goal answers: who / what / next / talk.
3. Communication answers: who needs me / about what / for which work.
