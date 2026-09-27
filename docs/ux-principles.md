# UX Principles — CM Ops

## North star

```text
Open → see what needs me → understand why → act in place
```

The product teaches itself. Documentation is backup, not the path.

---

## Principles

### 1. Goals over entities
Navigation and labels follow user goals (My Work, Communication, Inventory), not database tables.

### 2. Attention first
Critical > needs attention > important > informational. Never give all buttons primary weight.

### 3. One obvious next action
Every major object answers: **حالا باید چه کار کنم؟ / What’s next?**

### 4. Human language
Speak as employees speak. Keep Case/WorkItem/Task in the backend; explain them in UI copy and hints.

### 5. Context stays with the user
Don’t send people to another menu to finish the thought. Prefill what the system already knows.

### 6. Simple by default
Advanced fields (SLA, dependencies, metadata) live under “More options”.

### 7. Remove before add
If a control doesn’t help a frequent job, demote or delete it from primary UI.

### 8. Empty states teach
Explain what will appear and offer the first safe action.

### 9. Errors are coaching
What happened, why, what to do — never raw `403 AuthorizationError`.

### 10. Persian-first clarity
FA labels must not collide. Prefer **کار مشترک** / **وظایف** / **پیگیری** over ambiguous **کارها** alone.

---

## Visual rules

- One primary action per view  
- Status uses semantic color (ok / warn / danger), not decoration  
- Prefer list + detail over walls of cards  
- Generous spacing; restrained borders  
- Icons only when they add meaning  

---

## Glossary (user-facing)

| Concept | EN | FA | One-line meaning |
|---------|----|----|------------------|
| Shared work | Shared work | کار مشترک | A goal several people push together |
| Follow-up | Follow-up | پیگیری | A tracked subject that needs ownership |
| Task | Task | وظیفه | One concrete action for someone |
| Conversation | Conversation | گفتگو | Messages about that work |
| My Work | My Work | کارهای من | Everything I personally owe |
