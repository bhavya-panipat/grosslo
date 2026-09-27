# One funding figure per submission — fix design (D-S7)

**Status:** design only, **awaiting approval.** No code is changed. Decision D-S7
(§7) is the owner's.

**Why this is ahead of D-S4 in the queue.** The owner moved it there on
2026-09-27, and the reason is that this is the one open item whose failure mode is
**the amount funded not being the amount instructed**. It is also cheapest to fix
now, precisely because nothing is in production yet.

**Found while confirming D-S4's storage question**, not by an incident and not by
a sweep. It was very nearly recorded as a bullet inside D-S4, which would have
lost it once D-S4 closed.

---

## 1. The defect

Two consumers read the same submission's funding figure from two different places.
Verified in the code rather than inferred:

| Consumer | Reads | Where |
|---|---|---|
| The Finance funding gate | the **stored** forecast | `finance-flow.tsx:826` — `totalCapitalOutlay(pendingRows.map(r => r.computed))`, which reduces `r.computed.treasury_forecast.total_capital_outlay` |
| The per-row export | a **freshly recomputed** forecast | `api_export_approved_row` calls `treasury_forecast(...)` and never reads `computed["treasury_forecast"]`, although it exists |

**A stored `treasury_forecast` exists and the export route ignores it.** That is
the whole defect, and it needs no engine change to be true.

### 1.1 The sequencing makes it worse, not better

The two consumers never look at a row at the same moment, which sounds like a
mitigation and is the opposite:

1. While the row is **pending**, the gate sums the **stored** figure and Finance
   funds against it — that is what `canBulkApprove` is decided on.
2. Once **approved**, the export builds a payment instruction from a **fresh**
   figure.

So the same row is seen by both, in sequence, and **the amount funded is the
amount from step 1 while the amount instructed is the amount from step 2.** If
they differ, the difference is a real-money shortfall or surplus, not a display
inconsistency.

### 1.2 Neither figure is wrong in isolation

This is not a repeat of the treasury-NPS bug, where a figure was simply
incomplete. Both values are computed by the same function from the same inputs.
**They are two answers to one question**, and the defect is that the question has
two answers at all. Saying so plainly because "another wrong treasury figure"
would otherwise read as the same severity as D-T1.

## 2. When they actually differ

They agree whenever `optimize()` returns the same recommendation it returned at
submission time. They diverge when it does not, which is **documented, not
hypothetical**: the employer-NPS fix on 2026-09-19 changed the recommendation in
**111 of 1,140** swept cases (≈9.7%).

**Measured on the stored rows that exist:** 0 of 5 have a changed recommendation
today, and none has a stored `treasury_forecast` at all — they predate the field.
Postgres holds 0 rows.

**That zero is not reassurance, and this document will not treat it as such.**
There is no production deployment (no Dockerfile, Procfile or platform config, no
`DATABASE_URL`; `TAX_ENGINE_EMPLOYER_NPS_DESIGN.md` §8), so it means *nothing has
been submitted by a real customer* rather than *nothing diverges under real
volume*. The 9.7% rate is the number that describes the risk; the row count
describes the absence of usage.

## 3. Design

**Pick one source of truth, and enforce it with a test rather than a convention.**

### 3.1 Stored is canonical

- `api_export_approved_row` reads `computed["treasury_forecast"]` instead of
  recomputing it.
- **Three reasons, in order of weight:**
  1. **The funding gate already trusts stored.** Making the export match stored is
     the only option that does not leave two systems permanently disagreeing about
     one submission. Recomputing at export would make the payload internally
     consistent and leave it inconsistent with the gate — moving the disagreement
     rather than removing it.
  2. **It is the figure a human funded against.** A payment instruction should
     name the amount that was approved and funded, not a better one computed later
     by nobody.
  3. **It preserves the maker-checker gate** (the D-S4 argument): recomputing
     silently replaces an approved verdict's basis with one nobody reviewed.

### 3.2 What happens when the stored figure is absent

Rows predating the field have no stored `treasury_forecast` — all five SQLite rows
are in that state. **The route must not silently fall back to recomputing**, which
would reintroduce the divergence for exactly the oldest rows.

**Recommended: refuse the export with a clear reason**, in the same shape as the
existing missing-bank-details refusal. A row whose funding figure was never
recorded cannot have been funded against a recorded figure, so there is nothing to
honour. The alternative — recompute and label it — is available and is D-S7b
below, because it is a genuine choice and not mine to make.

### 3.3 What this does not change

- **`payouts` and `payout_basis` stay recomputed.** They have no stored form
  (confirmed: `api_create_submission` writes only `treasury_forecast` and
  `guardrail` into `computed`), so making them stored is a **new stored-value
  addition** and therefore a separate decision under `CLAUDE.md`'s stored-value
  rule. **Explicitly out of scope here.** They are derived from the forecast, so
  once the forecast is canonical they inherit it.
- **The guardrail is D-S4's question**, untouched.
- Nothing about who approves a payout, or when bulk-approve blocks.

## 4. The standing test — the part that matters after this closes

A one-off fix here is worth little: the gap reopens the moment someone
recomputes for convenience. So the design's real deliverable is an invariant.

**The test asserts that the funding-gate figure and the export figure are
identical for the same row**, and it is written so that it fails under a future
engine change rather than only today:

- Submit a row, read the figure the gate would sum (`computed.treasury_forecast.
  total_capital_outlay` as the queue API serves it), export the row, and assert
  the payload's `treasury_forecast` is **byte-identical** to the stored one — not
  merely equal in total, since a matching total with different components is the
  same bug wearing a disguise.
- **Then force divergence and assert it still holds.** Mutate the stored forecast
  in the database to a value the engine would never produce, and assert the export
  still serves the stored figure. Without this, the test passes for the wrong
  reason — on an unchanged engine the two paths agree anyway, so a test that only
  compares them would have passed *before* the fix. **This is the step that makes
  it a standing check rather than a coincidence**, and it is the same trap the
  treasury-NPS work hit, where four identity assertions all ran where the missing
  term was zero.
- Assert the absent-stored-figure case behaves as §3.2 decides.

**Sabotage:** restore the recompute at export. The forced-divergence test must
fail; the unchanged-engine comparison will still pass, which is precisely why both
are needed.

**This test is a prerequisite for closing D-S4 cleanly**, because D-S4's answer —
whichever way it goes — only holds if something enforces it going forward.

## 5. What this does not fix, and must not be read as fixing

**The stored figure can itself be stale.** Serving it consistently makes the two
consumers agree; it does not make the figure current. A row submitted before
2026-09-19 stores a forecast computed on the pre-fix engine, and this change means
**both** surfaces now show that figure rather than one showing it and one showing
a fresh one. That is the correct trade — consistency first, and staleness is what
the D-S3 basis warning already exists to say — but it is a trade, and D-S4's
labelling question is what covers the remainder.

## 6. Not in scope

`payouts`/`payout_basis` storage (§3.3); the guardrail (D-S4); D-S1's
primary-source lookup; any change to dispatch, approval, or the bulk-approve rule.

## 7. Decisions for the owner

| | Decision | Recommendation |
|---|---|---|
| **D-S7a** | Which value is canonical for a submission's funding figure? | **Stored.** The funding gate already trusts it, it is the figure a human funded against, and it is the only choice that leaves the two consumers agreeing rather than relocating the disagreement. |
| **D-S7b** | When no stored figure exists (rows predating the field), refuse or recompute-and-label? | **Refuse**, in the shape of the existing missing-bank-details refusal. A row whose funding figure was never recorded cannot have been funded against a recorded one. **Least certain call here** — recompute-and-label is defensible if the owner would rather an old row stayed exportable, and it costs a `funding_figure_recomputed` field to say so. |
| **D-S7c** | Is the standing equality test in scope, or a follow-up? | **In scope, and the point of the exercise.** Without it the gap reopens silently at the next convenient recompute, and D-S4 cannot close cleanly because nothing would enforce its answer either. |
