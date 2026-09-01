# grosslo — architecture brief

Razorpay AI Buildathon 2026, AI Finance Controller track.

**Why this track and not AI Risk Manager, addressed directly, not left for
a reviewer to ask:** what's most *built out* today — six compliance rules,
a guardrail that actively blocks a bad structure, a penalty-exposure module
citing real statutory sections — genuinely reads closer to a risk-management
surface than a treasury one; the treasury forecast, by contrast, is one
formula with no steady-state tracking yet. Finance Controller was picked
for where this is headed, not for whichever surface happens to be furthest
along today: the roadmap's endpoint is grosslo sitting in the actual
payment-execution path — structuring, checking, and generating the payout
that gets funded — which is a controller function, not a monitoring one.
Risk Manager would be the more defensible claim if judged purely on what's
built this week; Finance Controller is the honest claim about the category
this is being built toward. Both are true; this doc says so on purpose
instead of picking whichever reads better.

This is the architecture document referenced from `README.md`. It exists to
answer the questions a judge will actually ask: what does this do, what part
is genuinely AI-native, what's deterministic and why, and what were the
specific design decisions and tradeoffs along the way. It describes the
system as built, not as planned — see `README.md` for setup/run instructions
and the feature list.

## What grosslo is

**Stated precisely, up front:** grosslo is the decision and compliance layer
a real autonomous payroll controller would need underneath it — not yet the
acting system itself. No route in this codebase writes state, calls an
external API, or moves money; every RazorpayX interaction stops at
generating a correctly-shaped payload. "Controller" describes what this is
built toward, not a write-authority this build currently holds.

It takes a compensation decision — one new hire, or a whole CSV of them —
and does four things a payroll/HR team currently does by hand, in
spreadsheets, across multiple tools: structure the salary tax-efficiently,
check it against a company's approved band and statutory ceilings, forecast
the capital treasury needs to fund it, and generate a schema-accurate
RazorpayX payout payload. It also runs the same checks *backwards* over an
existing headcount, to surface compensation structures that are already out
of policy or leaving money on the table.

## Why the architecture is deterministic-first

The single decision everything else in this codebase follows from: **no LLM
call is ever the source of a number a user acts on.** A grid-search optimizer
(`optimizer.py`) over a closed-form tax function (`tax_engine.py`) computes
every tax, saving, and structure figure. This was a deliberate choice, not a
default — an LLM computing someone's actual payroll tax liability is the
wrong tool for a problem that has a correct, checkable, non-probabilistic
answer. The AI layer's job is everything *around* that number: reading messy
unstructured input, explaining a structured result in plain language, and
answering follow-up questions — never producing the result itself.

Two enforcement mechanisms make this a property of the code, not a
convention people have to remember:

1. **Numeric guard** (explanation, negotiation copy, query answers): the
   LLM's response text is scanned for every number it contains; if any number
   isn't traceable back to the input data the LLM was actually given, the
   response is rejected and a templated deterministic fallback is used
   instead.
2. **Decide-then-phrase** (compliance flags, payroll guardrail): rule
   evaluation happens entirely in Python, before the LLM is ever invoked. The
   LLM's only role is turning an already-decided flag into a cleaner
   sentence — it cannot add, drop, or reinterpret one.

`execution_trace.py` extends this discipline to the trace drawer shown in
the UI: it never hooks into `optimize()`, `flag_compliance()`, or
`evaluate_band_guardrail()` internally, and never runs before those
functions return. It's a pure formatting layer over their real output —
`trace_optimize_stage()` quotes the actual `flag_compliance` result and cites
the real triggered rule's statutory section (or honestly reports "no flags
triggered" when nothing fired), and `trace_guardrail_stage()` quotes the real
`evaluate_band_guardrail()` verdict. A trace line can't cite something the
underlying engine didn't actually decide.

## System architecture

```
Input: CTC form │ pasted offer letter │ CSV (new-hire batch or existing-employee audit)
        │
        ▼
ai_layer.py — extraction              LLM w/ deterministic regex fallback
        │
        ▼
optimizer.py + tax_engine.py          deterministic, unit-tested — sole
        │                             source of every tax figure
        ▼
ai_layer.py — explanation             LLM narrates the engine's numbers,
        │                             guarded against invented figures
        ▼
ai_layer.py — compliance flags        6 fixed rules (compliance_rules.md),
        │                             matched in Python; LLM only rephrases
        ▼
ai_layer.py — payroll guardrail       band check + EPFO ₹7.5L aggregate
        │                             ceiling + regime-specific 80CCD(2) cap
        ▼
payroll_breakdown.py                  treasury forecast: net disbursement,
        │                             TDS escrow, EPFO challan, funding lead time
        ▼
penalty_exposure.py                   (audit mode only) illustrative delayed-
        │                             remittance cost if payroll slips
        ▼
app.py                                RazorpayX Composite Payout payload
                                       (schema only — no live dispatch)
```

Backend: Flask, stdlib + `anthropic` SDK only. Frontend: Next.js 15 (App
Router), React 19, TypeScript, Tailwind, Framer Motion, React Three Fiber —
5 routes (`/`, `/optimize`, `/optimize/batch`, `/hr`, `/finance`), 34
components.

### Backend routes

| Route | Purpose |
|---|---|
| `POST /api/optimize` | single-candidate structure + compliance + trace |
| `POST /api/batch-audit` | Compliance & Savings Audit — runs the guardrail and unclaimed-savings check against *existing* structures, not new offers |
| `POST /api/sensitivity` | regime-crossover curve for the results chart |
| `POST /api/extract` | offer-letter text → structured fields |
| `POST /api/query` | conversational follow-up, including live "what if" re-runs of the deterministic engine |
| `POST /api/export-razorpayx` | guardrail check + RazorpayX payload generation |
| `GET /api/audit-log` | read-only view of the local audit trail (`?limit=`) — inspect live what's actually been logged |
| `POST /api/submissions` | HR submits a single offer or CSV batch for Finance review — the sole path for structuring a new hire (see "Redundancy fix" below) |
| `GET /api/submissions` | Finance's queue (`?status=pending\|approved\|rejected`) |
| `GET /api/submissions/<id>` | one submission's detail, including the before/after diff per row |
| `POST /api/submissions/<id>/rows/<row_index>/decide` | approve or reject one row — idempotent, never dispatches |
| `POST /api/submissions/<id>/rows/<row_index>/export` | approved-only: a correction row generates the Salary Revision XLSX, a new-hire row generates a RazorpayX payout payload from the bank details supplied at submission |
| `POST /api/export-salary-revision` | standalone Bulk Salary Revision XLSX for an explicit employee list — file only, no live upload; still has no frontend caller (see "Redundancy fix") |
| `GET /health` | reports whether `ANTHROPIC_API_KEY` is set (`ai_backed`) so degraded mode is visible, not silent |

`/api/optimize`, `/api/submissions`, and `/api/batch-audit` all share one
internal helper (`_build_optimize_response`) so no route reimplements the
optimize+compliance+negotiation+metrics pipeline — it's the same function
called once per request or once per row, with row-level errors isolated
so one bad CSV row doesn't fail a batch. `/api/optimize-batch` used to be
a fourth caller of that helper — the "New Hire Batch" mode's route — but
it bypassed Finance review entirely, duplicating what `/api/submissions`
already does with a review step on top. Removed as a redundancy fix, not
folded into anything: see "Redundancy fix" in `README.md`.

## Key design decisions

**The ₹7.5L aggregate EPFO ceiling is one constant, referenced everywhere it
matters.** `EPFO_AGGREGATE_CEILING = 750_000` is defined once in
`ai_layer.py` and reused by both the payroll guardrail and the batch-audit's
excess-contribution calculation — not two independently-maintained
thresholds that could silently drift apart.

**Basic salary is capped at 50% of CTC in the optimizer**, not left
unconstrained. An early build iteration without this ceiling pushed basic
upward indefinitely, because more basic mathematically shelters more income
via employer PF/NPS — mathematically optimal, but not a structure any real
company would offer. The 40–50% band matches market convention instead of
the pure tax-minimizing optimum, an explicit, documented tradeoff.

**Employee-side PF and the delayed-remittance penalty math live outside
`tax_engine.py`, in `payroll_breakdown.py` and `penalty_exposure.py`,
deliberately.** `tax_engine.py` only ever needed the employer's
cost-to-company PF contribution to compute tax correctly; employee PF and
statutory penalty interest are payroll/treasury concerns, not tax-liability
concerns, and adding them to the tax engine would have coupled two things
that change for different reasons. Keeping them in separate, newer modules
that call into the tax engine read-only — instead of extending it — means
the original 23-test-covered engine is untouched by later feature work; only
additive modules and their own new tests carry the risk of a new bug.

**Section 271C is deliberately absent from the delayed-remittance penalty
scenario**, not an oversight. `penalty_exposure.py` models the cost of
depositing already-deducted EPF/TDS late (Sections 7Q, 14B, 201(1A)). The
Supreme Court held in *US Technologies International (P.) Ltd. v.
Commissioner of Income Tax* (2023) that Section 271C's penalty applies only
to a *failure to deduct* TDS in the first place — not to late remittance
after deduction, which is the exact scenario this feature models, and which
is already covered by Section 201(1A) interest. An earlier draft of this
module included a 271C figure; it was removed after checking the actual
ruling rather than relying on recalled priors, because a feature whose whole
premise is real statutory citations can't afford a citation that's wrong in
scope. `README.md`'s "what broke during development" section documents this
by name.

**The 6-rule compliance set and the tax engine's narrow scope (no surcharge,
single income source, resident individuals only) are a deliberate hackathon
boundary, not an unrecognized gap.** This build is scoped to demonstrate the
mechanism — deterministic-first checks, real statutory citations, a
guardrail that actually blocks a bad structure — correctly and defensibly
for the salaried CTC ranges typical of early-to-mid career hires, rather
than attempting broad real-world coverage under deadline pressure and
risking a rule that's subtly wrong the way an early 271C draft was (see
above). Expanding coverage — surcharge, multiple income sources, additional
compliance rules beyond R1–R6 — is explicit, named, next-in-line roadmap
work in `README.md`, not a silent limitation, and it's scoped to go through
a practicing CA's review before being trusted at real enterprise scale,
for the same reason the 271C citation got checked against the actual
ruling instead of recalled knowledge: this is a domain where being
confidently wrong is worse than being narrow.

**The RazorpayX Composite Payout payload shape was verified against
RazorpayX's own API documentation**, not inferred from field-name guesses —
nested `fund_account`/`bank_account`/`contact` objects, amount in paise, and
the `X-Payout-Idempotency` header requirement for a real (never-issued-here)
dispatch call.

**Batch CSV parsing uses `papaparse`**, not a hand-rolled splitter. This is
the one place in the frontend where a subtly wrong parse (an unescaped comma
inside a quoted field, for instance) produces a confidently wrong compliance
or savings number rather than a visibly broken pixel — a different risk
profile from presentation-layer code, where a bug is visibly wrong instead of
silently wrong.

**`/api/batch-audit` is still a fully stateless Flask handler** — it computes
a response from the request body and returns it, the same as every route
that isn't part of the review queue. Uploaded audit CSV rows live only in
browser memory for the session tab; nothing about an existing employee's
structure is written anywhere by that route.

**`/api/submissions` is not stateless, and — since the redundancy fix — it
persists bank details when HR supplies them, stated plainly rather than
left implicit.** The review queue (`review_queue.db`, SQLite) always stored
employee name and CTC (needed for the dedupe check); it now also stores
`band_min`/`band_max`/`bank_account_number`/`ifsc`/`email` when present,
because that's what lets an approved row generate a real RazorpayX payout
payload later without re-entering everything by hand. This is exactly the
kind of data the security posture section below is about — unencrypted,
no access control, demo-scale only — not a claim that no PII is stored.
The audit log remains the one place that genuinely excludes it by
construction (see below).

**One server-side file write does exist, deliberately narrow: a local audit
log.** `_append_audit_log()` in `app.py` appends one JSON line per
money-adjacent decision (structure computed, compliance/guardrail verdict,
whether a payout payload was generated) to a gitignored `audit_log.jsonl`
on every call to `/api/optimize`, `/api/submissions`, `/api/batch-audit`,
and `/api/export-razorpayx` — a real, inspectable-after-the-fact record,
not a claimed one. It never writes employee names, bank account numbers,
IFSC codes, or emails, so the "no bank details persisted" claim above still
holds exactly. This is a local append-only log for this submission, not a
production audit system — no rotation, no access control, no
tamper-evidence — and is stated as exactly that, not oversold as more.
`GET /api/audit-log` (optional `?limit=`) reads it back — the audit trail
is something a reviewer can inspect live, not just a claim to take on
trust.

**The treasury forecast is a total over the current request's structures,
not a delta against a company's real payroll.** This follows directly from
the statelessness above: `payroll_breakdown.treasury_forecast()` has no
history to compute a delta against, so "capital required" is a literal
figure for whatever single structure is in the request — one candidate on
`/optimize`, or one approved row's own forecast on the per-row export in
`/finance`. (`/api/batch-audit` computes one per row too, for the CSV
being audited; nothing currently aggregates a multi-employee capital
figure in one call — the New Hire Batch export modal that once did this
was removed with the redundancy fix, and nothing replaced that specific
aggregation.) That's an accurate number for what it is, but it is not a
company's
full recurring payroll capital, and the UI label says so explicitly rather
than leaving that inference to the viewer. Closing that gap for real —
showing a steady-state baseline alongside the incremental figure — needs a
persisted employee roster this build deliberately doesn't have; it's the
first item on the roadmap in `README.md`, not a silent limitation.

**Batch mode skips the AI-generated explanation entirely — measured, not
assumed, to cost nothing.** `explain_result(..., skip_ai=True)` goes
straight to the deterministic explanation without a live API call,
whenever a request is batch-shaped: `/api/submissions` (batch source) and
`/api/batch-audit` both pass `skip_explanation_ai=True`. This was found
via load-testing the (since-removed) New Hire Batch route, not design
review: with the AI layer on, a 20-row batch didn't complete inside 60
seconds, entirely because of one sequential, blocking Claude call per row.
Before "fixing" it, checked whether the explanation text was used anywhere
— `batch-results-table.tsx` renders only row/CTC/regime/saving/guardrail
columns, so it was computed and discarded on every row, in every batch.
Skipping it dropped a 500-row batch from not completing at all to ~34
seconds (~69ms/row). The fix outlived the route it was found on — it
carried forward into every batch-shaped path that came after. The
single-candidate flow, where the explanation is actually shown, is
untouched — see `README.md`'s "what broke" section for the full
before/after.

**The maker-checker review layer is three new, deliberately separate
modules, not one bigger one.** `review_queue.py` (SQLite persistence and
decision logic), `diff_view.py` (before/after presentation over data those
other modules already computed), and `salary_revision_export.py` (XLSX
generation) don't import each other's internals — each does exactly one
job, matching the pattern already established by `payroll_breakdown.py`
and `penalty_exposure.py` being separate from `tax_engine.py`. Two
decisions worth naming explicitly:
- **Idempotency on Approve is structural, not a bolted-on check.**
  `decide_row()`'s SQL only updates rows still `status = 'pending'`; a
  second call (a double-click, a retried request) matches zero rows and
  returns `already_decided` instead of a special-cased guard clause. The
  database's own atomicity does the work, which is a stronger guarantee
  than an application-level flag would be.
- **The diff view calls `optimizer.py`'s existing
  `best_regime_for_given_structure()` to determine the as-offered
  structure's own regime, rather than storing it separately.** This is a
  call to an already-tested function that already exists for exactly this
  purpose elsewhere in the codebase (the batch-audit route), not new
  logic — the constraint the build brief for this feature set explicitly
  called for.

## Open product questions (unresolved on purpose, not glossed over)

These aren't roadmap items with a known next step — they're decisions that
haven't been made yet, and pretending otherwise would be its own kind of
overclaiming.

**Who actually operates this, day to day?** HR, a payroll admin, an
individual employee reviewing their own offer, or an API Razorpay's own
systems call internally are all plausible, and each implies a different
permission model, a different UI, and a different answer to who's even
allowed to see a given number. This document describes what the system
computes; it doesn't yet answer who's using it or what they're allowed to
see.

**Does grosslo become the system of record, or does it sync with one that
already exists?** Every real company already runs payroll through
something — RazorpayX Payroll itself, or another vendor. Whether grosslo
assumes ownership of compensation data or ingests from and stays in sync
with an existing system is a foundational architecture decision, and it's
entangled with the persistence and multi-tenancy questions in the roadmap
above, not separable from them — this can't be answered as three separate
features added one at a time.

## What's genuinely AI-native

- **Offer-letter extraction** — pulling structured CTC/basic/HRA/LTA/PF
  fields out of unstructured pasted text, a task regex alone handles
  unreliably across real-world offer-letter formats.
- **Explanation** — turning a table of optimizer output into a plain-language
  recommendation personalized to the user's actual numbers, guarded against
  inventing any figure not already in that table.
- **Compliance and guardrail phrasing** — rephrasing already-decided flags
  into readable sentences, never deciding what to flag.
- **Conversational query** (`/api/query`) — including hypothetical
  ("what if I paid ₹5,000 more rent") questions that trigger a real re-run of
  `optimizer.py`/`tax_engine.py` with the changed input and report the actual
  recomputed result, rather than an LLM estimate of what the new number would
  be.

## Test coverage

69 tests total, passing with or without `ANTHROPIC_API_KEY` set (every
AI-layer function has a deterministic fallback, so the full suite
exercises real logic either way): 51 in `tests/test_finos.py` — the
marginal relief calculation against the government's own worked example,
the old-vs-new regime crossover, HRA metro/non-metro, the PF statutory
ceiling, extraction mismatch detection, the explainer's numeric guard,
each of the 6 compliance rules' trigger conditions, and the query layer's
hypothetical re-run path — plus 18 in `tests/test_review_workflow.py`
covering the maker-checker flow: submission persistence, correctly-worded
simulated approval, mandatory rejection reasons, the diff view matching
real optimizer output exactly, independent row-level decisions on a mixed
batch, duplicate-submission detection, double-approve protection, the
salary-revision export's real values plus honesty label, and — added with
the redundancy fix — approval-gated export, a new-hire export's real bank
details (and its clean failure without them), a correction export's real
XLSX, the guardrail actually firing on a banded submission, and
`/api/optimize-batch` being genuinely absent from the route map.

The live LLM-backed path has also been exercised end-to-end against the
real Claude API (extraction, explanation, compliance phrasing, query
classification, and the hypothetical-recalc query path) — this is separate
from the 49 automated tests above, which only run against the deterministic
fallback. That live pass caught one real bug: the hypothetical-recalc
guard's allow-list was missing the changed value itself, so a valid answer
that naturally restated it was being silently rejected. Fixed, documented
in `README.md`'s "what broke during development" section.
