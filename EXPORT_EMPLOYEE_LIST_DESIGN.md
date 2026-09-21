# One structure, many employees — fix design

**Status:** design only, **awaiting approval.** No code is changed. Decisions
D-E1 to D-E3 (§6) are the owner's.

**Why now.** Raised as D-P5 while fixing the payout gross/net bug on
2026-09-21, recorded unfixed with the note that it needs its own design before
Phase 3. This is that design.

---

## 1. What the route does

`POST /api/export-razorpayx` takes **one** compensation input — `ctc`,
`rent_paid`, `city`, `nps_opted` — and **a list** of employees, each with a name
and bank details. It computes one recommended structure from that single input
and then builds one payout per employee from it:

```python
result = optimize(ctc=ctc, rent_paid=rent_paid, city=city, nps_opted=nps_opted)
recommended = result["recommended"]
...
response["payouts"] = [
    _build_composite_payout(recommended.structure, employee, account_number, forecast)
    for employee in employees
]
```

So a list of ten employees yields **ten payouts with identical amounts** and ten
different bank accounts. Every person named is paid the same figure, derived
from one CTC that at most one of them actually has.

### 1.1 The response contradicts itself when the list is longer than one

`treasury_forecast` in the same response is computed **once, for that single
structure**. The modal renders it under *"Capital required for these
employees"*, above a payload that pays N people:

| N | Payouts issued | Funding reported |
|---|---|---|
| 1 | one person's net pay | that person's outlay |
| 10 | ten identical net payments | **one** person's outlay |

At N = 10 the funding figure is a tenth of what the payload disburses, and the
modal's own words claim it covers *"the 10 employees shown here"*. Either half
is defensible alone; together they cannot both be true.

This is the same defect class as the two fixed this week — a total that does not
account for what it claims to — and it is the reason to treat the list as the
problem rather than only the amounts.

### 1.2 Nothing sends more than one today

Traced, not assumed:

- **The only frontend caller** is `razorpayx-export-modal.tsx`, which posts
  `employees: [employee]` — a single-element list, built from one form.
- **The only test caller** posts a one-element list.
- **The per-row export** (`/api/submissions/<id>/rows/<i>/export`) builds its
  employee from one submission row and is unaffected.

So the broken case is **reachable but unreached**: the API accepts it, no caller
produces it, and the moment anything does — a batch export, a script, a demo
against the documented shape — it produces N wrong payment instructions and a
funding figure off by a factor of N.

## 2. Design

**Refuse the case rather than implement it.**

- `POST /api/export-razorpayx` answers **400** when `employees` has more than one
  entry, with a message that says why and what to do: one structure describes
  one person, so a second employee needs a second call with their own CTC.
- Everything else is unchanged: the single-employee path, the per-row export,
  the treasury forecast, the payout amount.

**Why refuse rather than support it.** Supporting N employees properly means
accepting N compensation inputs — each with its own CTC, rent, city and NPS
choice — computing N structures and N forecasts, and summing them. That is a
batch export, and one already exists in a different shape:
`/api/batch-audit` takes per-row structures. Building a second batch path inside
a route whose whole premise is "one structure" would give two ways to do the
same thing, and the version being fixed here is the one that silently produced
identical amounts.

**Why not leave it documented.** The route's shape invites the mistake: a
parameter named `employees`, plural, that is correct only at length one. A
comment cannot make a request return the right thing. The owner asked for this
scoped *before* Phase 3 precisely because the day it first matters is the day
money moves.

## 3. What this changes for callers

| Caller | Effect |
|---|---|
| `razorpayx-export-modal.tsx` | None. It sends one. |
| The per-row export | None. Different route. |
| Tests | None existing. §4 adds new ones. |
| A hypothetical batch caller | Now gets a 400 explaining the constraint, instead of N wrong payloads |

**The field keeps its name and its list shape.** Renaming it to `employee` or
taking an object would be a breaking change to the request for every caller, to
fix a case none of them send. A 400 is the smaller correction, and the list
shape is what a future real batch export would use.

## 4. Tests

- **Two employees are refused**, with a 400 and a message naming the reason.
- **One employee still succeeds**, and its payout and forecast are unchanged —
  the both-states pair, so the refusal cannot be satisfied by breaking the
  working case.
- **Zero employees keeps its current behaviour** (already a 400; pinned so this
  change does not alter it).
- **`employees` omitted entirely keeps its current behaviour**: the route
  returns the guardrail and forecast with no payouts, which is the deliberate
  "check before bank details exist" path and must survive.

**Sabotage:** raise the limit to two — the refusal test fails while the
single-employee test still passes, showing the boundary is where the test says.

## 5. Sequence

Separate commits, full suite after each, under the lock, pushing the SHA
verified:

1. Tests, committed red.
2. The 400 in `app.api_export_razorpayx`, with a comment recording why the
   route refuses rather than supports the case.
3. The modal's *"these employees"* copy, which is written for a list it can no
   longer receive — the frontend session's file, requested not edited.
4. `docs/PROJECT_STATUS.md`: close D-P5.

## 6. Decisions for the owner

| | Decision | Recommendation |
|---|---|---|
| **D-E1** | Refuse a multi-employee list, or implement real per-employee batch export? | **Refuse, with a 400.** Real batch export needs per-employee compensation inputs, which is a second batch path beside `/api/batch-audit`. Nothing asks for it today, and the current behaviour is silently wrong rather than merely missing. |
| **D-E2** | Keep the field named `employees` and list-shaped? | **Yes.** Renaming breaks every caller's request shape to fix a case none of them send, and a future real batch export would want the list back. |
| **D-E3** | Should the single-employee forecast be labelled more precisely in the response? | **No, not here.** The modal already says the figure covers only the employee shown. Once the list cannot exceed one, the singular is accurate, and adding a field to restate it would be noise. If the copy is reworded at all, it is the frontend session's `"these employees"` line. |

## 7. Not in scope

Real batch payout export; any change to `/api/batch-audit`; anything that
dispatches a payout; the summary-card and treasury-gate labels still outstanding
from `TREASURY_PERIOD_LABEL_DESIGN.md` D-M1/D-M2.
