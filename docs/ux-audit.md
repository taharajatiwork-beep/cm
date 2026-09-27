# UX Audit — CM Ops

**Date:** 2026-09-27  
**Scope:** `frontend/src` as a first-time user (manager, seller, marketing)  
**Default locale:** Persian (FA)

---

## 1. What is confusing?

| Problem | Evidence |
|---------|----------|
| 14 equally weighted nav items | `Shell.tsx` flat list |
| Work Items FA = **کارها** vs Tasks = **تسک‌ها** | Users think کارها = their tasks |
| Case / Work Item / Task / Communication overlap | Four “work thread” metaphors |
| Home does not answer “what do I do now?” | Stats + static tips, not my queue |
| Cases page has no inbox | Create-only; demo empty copy |
| UUID slices instead of titles | Tasks, Communication, People |
| Search / Notifications / Knowledge as peers | Should be chrome or Settings |
| Agent “Communication” mode vs Communication page | Same word, different worlds |
| Raw enums | `IN_PROGRESS`, `HIGH`, SLA codes |
| Org structure (Teams/Branches) in daily nav | Reference data, not daily work |

---

## 2. Why is it confusing?

The UI mirrors **backend entities**, not **user goals**.

```text
Developer mental model: Case → WorkItem → Task → Event → SLA
Employee mental model:  What do I owe? Who waits on me? What’s overdue?
```

Labels were translated literally without resolving collisions (especially FA **کارها**).

---

## 3. What does the user actually need?

1. See **attention items** on open  
2. Open **one place for my responsibilities**  
3. Talk / message in context of a goal  
4. Find a **vehicle / customer / person** without knowing tables  
5. Assign work to people/teams without 5 screens  
6. Understand progress of shared goals at a glance  
7. Ask AI in context when stuck  

---

## 4. What should be removed (from primary UI)?

- Top-level: Cases, Tasks, Work Items (as peers), Branches, Teams, Search, Knowledge, Notifications  
- Dashboard vanity tiles without action  
- Demo defaults (`Camry` search, prefilled agent English scans) from production UX  
- Cases empty-state “create to inspect fields” lab copy  
- Always-expanded create forms where list is the primary job  

*(Routes can remain for deep links.)*

---

## 5. What should be renamed?

| Old EN / FA | New EN / FA |
|-------------|-------------|
| Dashboard / داشبورد | **Home** / **خانه** |
| Work Items / کارها | **Shared work** / **کار مشترک** |
| Tasks / تسک‌ها | **Tasks** / **وظایف** (inside My Work) |
| Cases / پرونده‌ها | **Follow-ups** / **پیگیری‌ها** (contextual) |
| Create case | **New follow-up** / **پیگیری جدید** |
| Assignee | **Owner** / **مسئول انجام** |
| AI Assistant modes jargon | Soften “Intent” → **Result** / **نتیجه** |

---

## 6. What should be combined?

- **My Work** = my tasks + overdue + shared work I’m on + actionable alerts  
- **People** = directory + team membership context  
- **Settings** = branches, teams, knowledge, language prefs  
- Notifications → shell bell + Home attention list  

---

## 7. What should become contextual?

- Case create → from Vehicle / Customer / Shared work  
- Assign / add participant → on Shared work detail  
- AI → “Ask about this…” on Vehicle / Shared work / My Work  
- Conversation → embedded on Shared work, not only a separate inbox  

---

## 8. What should be shown automatically?

- On Home: overdue, due soon, waiting response, unread alerts  
- On Shared work: participants, task checklist with owners, next action, progress  
- On Vehicle: open shared work, responsible people, recent messages  
- Prefill vehicle/branch/customer when creating work from that page  

---

## Severity ranking

1. **P0** — Navigation & Home attention model  
2. **P0** — Terminology (FA کارها collision)  
3. **P1** — My Work hub  
4. **P1** — Shared work detail as collaboration screen  
5. **P2** — Settings demotion, empty states, onboarding  
6. **P2** — Global search chrome, AI context chips  
