# grosslo — the decision and compliance layer for RazorpayX payroll

Built for the Razorpay AI Buildathon 2026, AI Finance Controller track.

**Stated precisely, up front:** grosslo is the decision and compliance layer
a real autonomous payroll controller would need underneath it — not yet the
acting system itself. Nothing in this build calls RazorpayX's real API,
writes to a database, or moves money; every code path terminates in a
recommendation or a generated payload. That boundary is deliberate (see
"Known limitations" and "Roadmap" below), not a gap discovered after the
fact.

grosslo structures a compensation offer, checks it against a company's approved
band and statutory ceilings, forecasts the capital a treasury team needs to fund
it, and exports a schema-accurate RazorpayX Composite Payout payload — for one
candidate at a time or a whole CSV batch. Every step is logged as a real
execution trace, not a black box: what ran, what it found, and why.

## What it actually does

- **Structure**: given a CTC (or a pasted, messy offer letter), computes the
  tax-minimizing salary split under both the old and new Indian tax regimes and
  recommends the better one — the deterministic core this was originally built
  around.
- **Check**: every structure is run against a fixed compliance rule set
  (`compliance_rules.md`, six rules) and a payroll guardrail (approved
  compensation band, the ₹7.5L aggregate EPFO contribution ceiling, the
  regime-specific Section 80CCD(2) employer-NPS cap).
- **Forecast**: net take-home, TDS escrow, and EPFO challan are summed into a
  single capital-outlay number, with a funding lead time — what treasury needs
  to have ready before payroll runs.
- **Export**: a real RazorpayX Composite Payout payload (verified against
  RazorpayX's own API docs, not guessed) — nested `fund_account`/`contact`,
  amount in paise. No live call is ever made; this generates the payload only.
- **Batch**: the same flow over a CSV — either a New Hire Batch (structure +
  export a set of new offers in one pass) or a Compliance & Savings Audit
  (point the same guardrail checks at *existing* employee structures, surface
  unclaimed regime-switch savings and excess EPFO contributions across the
  whole set).
- **Trace**: a live-looking execution log on every result — parse → compliance
  pass → math solver → policy gate — where every line is built from a field
  the underlying computation actually returned, never a scripted placeholder.

## Maker-checker review (demo-scoped, stated explicitly)

Closes a real gap the earlier build had: Compliance & Savings Audit could
detect a problem, but there was no path from "here's an issue" to an
actual decision being made and recorded. This adds that loop, scoped
honestly for a demo rather than dressed up as production workflow
infrastructure:

- **HR submits** (`POST /api/submissions`) — a single offer or a CSV
  batch, computed through the exact same `_build_optimize_response()`
  every other route uses. Nothing new is computed here; this only decides
  whether a result gets persisted for review.
- **Finance reviews** (`GET /api/submissions`, `/hr` and `/finance` as two
  separate frontend pages) — inspects the real execution trace, the real
  compliance flags, and a before/after diff (below), then approves or
  rejects **per row**, not only per whole submission — a 50-row batch
  where 2 rows have flags doesn't require an all-or-nothing decision.
- **Approving never dispatches anything.** It writes a status change and
  an audit-log entry that says exactly that: *"Approved — Payout
  SIMULATED, no live dispatch."* This is the same live-execution boundary
  drawn everywhere else in this codebase, in button copy this time instead
  of pitch copy, and it doesn't move here either.
- **Rejecting requires a reason** (free text, mandatory) — a review
  process that can't say no isn't a review process. The rejected row
  returns to HR's queue with that reason visible, and the rejection is
  logged exactly like an approval — a decision either way belongs in the
  trail.
- **A before/after diff, not just a raw trace.** For every offer with a
  prior structure to compare against, Finance sees exactly which fields
  changed and *why* — attributed to the specific compliance rule it
  resolves (e.g. "Basic: ₹5,00,000 → ₹9,00,000 — R1 compliance fix") or to
  "tax optimization" when no rule is involved. Zero new computation: this
  reads the same `negotiation`/`compliance` data every other route already
  produces (`diff_view.py`).
- **Duplicate submissions are flagged, not silently reprocessed.** The
  same employee at the same CTC submitted twice in the same day is
  detected and blocked before it's inserted (`review_queue.py`). A
  double-click on Approve doesn't write a second audit-log entry either —
  the status transition only fires once, by construction, not because of
  a special case bolted on for double-clicks.
- **Bulk Salary Revision export** (`POST /api/export-salary-revision`)
  closes the audit loop the rest of the way: takes a flagged employee's
  current + corrected structure (already computed by the audit, invented
  nowhere here) and generates a real multi-sheet XLSX — modeled on
  RazorpayX Payroll's own documented two-sheet Salary Revision format
  (Default Structure, Custom Structure), plus a Read Me sheet. **The exact
  column headers were not verified against a live RazorpayX account** —
  the file says so explicitly, in its own Read Me sheet and in the API
  response's `X-Template-Honesty-Label` header, so this is never mistaken
  for a confirmed, ready-to-upload template.

**What this deliberately is not:** real authentication (`/hr` and
`/finance` are a role toggle, not identity verification — anyone who can
reach the app can reach both), a production database (SQLite, a single
gitignored file, explicitly not the "real database" the roadmap describes
for a steady-state company roster), a second-approver escalation tier, or
a notification system for pending reviews. All four are reasonable ideas
in isolation; none of them belong on top of an approval layer already
honestly labeled as a demo simplification — making that layer *look* more
sophisticated than the authentication underneath it can actually support
would undermine the exact honesty this section is trying to model.

## Architecture — the one rule that matters most

```
Input (CTC form, or a pasted offer letter, or a CSV batch)
        │
        ▼
ai_layer.py — extraction          (LLM, with a deterministic regex fallback)
        │
        ▼
optimizer.py + tax_engine.py      (deterministic, unit-tested — sole source of
        │                          every tax figure shown to the user)
        ▼
ai_layer.py — explanation          (LLM narrates the engine's numbers, never
        │                           invents its own — see the numeric guard below)
        ▼
ai_layer.py — compliance flags     (rule matching is always deterministic;
        │                           LLM only rephrases already-decided flags)
        ▼
ai_layer.py — payroll guardrail    (band / EPFO ceiling / 80CCD(2) — same
        │                           deterministic-first pattern as compliance)
        ▼
payroll_breakdown.py — treasury forecast, penalty_exposure.py — delay scenario
        │
        ▼
app.py — RazorpayX Composite Payout payload (schema only, no live dispatch)
```

**No LLM call anywhere in this codebase is ever allowed to compute, restate
with different rounding, or invent a tax/salary/compliance figure.** Every
number the user sees traces back to `tax_engine.py` / `optimizer.py` /
`payroll_breakdown.py` / `penalty_exposure.py`. Enforced two ways:

- **Explanation and negotiation-adjacent text** — a numeric guard extracts
  every number the LLM's response contains and rejects the response (falling
  back to a templated deterministic version) if any number isn't traceable to
  the input data the LLM was given.
- **Compliance and guardrail flags** — rule matching happens entirely in
  Python before the LLM ever sees anything. The LLM's only job is rephrasing
  already-decided flags into cleaner sentences; it cannot add, remove, or
  reinterpret one.

The execution trace (`execution_trace.py`) follows the same discipline from a
different angle: it never hooks into `optimize()`, `flag_compliance()`, or
`evaluate_band_guardrail()` internally. It's a thin wrapper that runs *after*
those functions return, and formats trace lines by quoting their real output
verbatim — so a trace line citing a compliance section is never a citation
grosslo invented, only one the compliance engine already decided.

## Running it

Backend:
```bash
python3 -m unittest discover -s tests   # 61 tests, all pass with or without an API key
python3 app.py 8000                     # serves the API at http://127.0.0.1:8000
```

Frontend (Next.js — Node isn't bundled with this repo, install it separately):
```bash
cd frontend
npm install
npm run dev                             # http://localhost:3000, proxies /api/* to Flask on :8000
```

To enable the real LLM-backed extraction/explanation/compliance-phrasing/query
answering, put `ANTHROPIC_API_KEY=sk-...` in a `.env` file in the project root
(gitignored, loaded automatically via `python-dotenv` at startup — no manual
`export` needed) or set it in your shell before starting the backend.
**Without a key, every AI-layer function still works correctly** via its
deterministic fallback, and `/health` reports `ai_layer_active: false` so
this is visible rather than silent — a deliberate design choice, not a
bolted-on fallback.

## What's genuinely AI-native, and what isn't

Being direct about this, because a reviewer will ask: the tax calculation
(`tax_engine.py`, `optimizer.py`) is entirely deterministic, on purpose — a
grid-search optimizer over a well-defined rules problem, chosen specifically
*because* a general-purpose LLM should not be doing arithmetic on someone's
tax or payroll liability. The AI-native surface is `ai_layer.py`'s functions:
pulling structured numbers out of messy unstructured offer-letter text
(genuinely hard to do reliably with regex alone), turning a table of optimizer
output into a plain-language explanation personalized to the actual numbers,
phrasing compliance and guardrail findings clearly, and answering natural-
language follow-up questions — including "what if" questions that trigger a
real re-run of the deterministic engine with the changed input, not an LLM
guess at what the new number would be.

## Known limitations (stated explicitly, not left for a reviewer to find)

- **Surcharge** (income above ₹50L) is not modeled. Scoped for the salaried
  CTC ranges typical of early-to-mid career hires.
- **Aggregate employer PF + NPS above ₹7.5L/year** is a taxable perquisite
  under Section 17(2)(vii) that the tax engine does not compute into the tax
  figure itself — the guardrail's EPFO ceiling check exists specifically so
  this is flagged rather than silently absent.
- **LTA exemption** is modeled at a conservative assumed 70% utilization
  rather than the full claimed amount, since real LTA exemption depends on
  actual travel, valid bills, and a twice-per-4-year block limit this tool
  can't know in advance.
- **Basic salary is constrained to 40–50% of CTC.** The floor is market
  convention; the ceiling stops an unconstrained tax-minimizing search from
  pushing basic upward indefinitely, which produced structures no real
  company would implement in early testing.
- **Employee-side PF is not modeled in `tax_engine.py`** (only the
  employer's cost-to-company contribution is). `payroll_breakdown.py`
  introduces employee PF as a new, explicit assumption (12% of basic,
  symmetric with the engine's own employer-PF convention) purely for
  net-disbursement and treasury math — it never feeds back into the tax
  calculation itself.
- **The delayed-remittance penalty scenario (`penalty_exposure.py`) models
  Section 7Q interest and Section 14B damages (EPF) and Section 201(1A)
  interest (TDS) — deliberately not Section 271C.** The Supreme Court held
  in *US Technologies International (P.) Ltd. v. CIT* (2023) that 271C
  applies only to failure to *deduct* TDS, not to late remittance after
  deduction — the exact scenario this feature models. Including a 271C
  figure here would have been a real citation error, not a rounding one, so
  it's excluded on purpose. Professional tax (state-variable) and ESI
  (wage ceiling below this tool's target salary bracket) are excluded for
  similar scope reasons.
- **Extraction is not guaranteed accurate**, LLM-backed or not — extracted
  values are always shown for manual correction before use, with a mismatch
  warning when extracted components don't sum to the extracted CTC.
- Assumes a resident individual, under 60, salaried, with no other income
  sources or capital gains.
- The RazorpayX export generates a schema-verified payload only — no live
  call to RazorpayX is made anywhere in this codebase.
- **Security and privacy posture, stated plainly rather than left silent —
  this matters more than most limitations here, because this tool handles
  real compensation data.** Persistence is now limited to two things: the
  local `review_queue.db` (SQLite) that lets an HR submission survive
  until Finance reviews it, and the local `audit_log.jsonl` decision
  trail — nothing else. Specifically:
  - **No encryption at rest.** Both files are plain SQLite/JSONL on disk.
  - **No data-retention or deletion policy.** Data lives as long as the
    demo session/database file does, with no expiry or purge mechanism.
  - **No access control beyond the demo role-toggle** on `/hr` and
    `/finance` — see "Maker-checker review, demo-scoped" below. It is a
    UI convenience, not authentication; anyone who can reach the app can
    reach both roles.
  - **No employee PII or bank details in either persisted store** — the
    review queue stores computed structures and decisions, the audit log
    excludes names/bank details/emails by construction (see its own
    section below). This limits exposure; it does not substitute for the
    four gaps above.

  Named explicitly as a pre-production gap, not an oversight — the same
  discipline already applied to the LTA-utilization estimate, the 40%
  basic floor, and the no-live-dispatch boundary elsewhere in this
  document. **Real security infrastructure was deliberately not built for
  this submission** — the honest statement is the correct move here; a
  rushed implementation before Sept 5 would be worse than admitting the
  gap plainly.
- **The treasury forecast (`payroll_breakdown.treasury_forecast`) has no
  concept of history or an existing payroll baseline** — there's no database
  anywhere in this app, so the "capital required" figure is a literal sum
  over whatever structure(s) are in the current request, not a delta against
  a company's actual recurring payroll. The UI label says this explicitly
  ("capital required for these employees... not your full existing
  payroll") so it isn't mistaken for more than it is. See Roadmap below for
  what closing this gap actually requires.

## Roadmap toward a real product (explicitly out of scope for this submission)

This was built to demonstrate the core mechanism correctly, not to be
production-complete — these are the specific, known next steps, not vague
future plans:

- **Persistence — and the decisions that come bundled with it, not
  sequentially after it.** Going from this build's fully stateless
  request/response model to one that remembers a company's roster over
  time is a genuine re-architecture, not an incremental feature. Three
  things have to be designed together, not added one at a time: a real
  database so the treasury forecast can show a company's steady-state
  payroll baseline (not just the incremental capital for whichever CSV was
  uploaded); **multi-tenant isolation**, so company A's payroll data is
  never reachable from company B's request the moment more than one
  company's data exists in the same system; and a **system-of-record
  decision** — does grosslo become the source of truth for a company's
  compensation data, or does it ingest from and stay in sync with
  RazorpayX Payroll or whatever HRIS a company already runs. None of these
  three is answered yet, and none of them can be answered independently of
  the other two.
- **Live RazorpayX dispatch, gated behind real OAuth and a human-approval
  step** — today the export stops at generating a correct payload on
  purpose; going further requires real credentials and an audit trail
  before any actual payout is safe to trigger automatically.
- **Ecosystem-partner integration** — distributed to companies already on
  RazorpayX rather than as a standalone tool competing for signups.
- **Wider compliance and tax coverage, named specifically rather than left
  as a direction.** The current 6 rules and the tax engine's scope (no
  surcharge, single income source, resident individuals only) don't yet
  cover the messier reality of real payroll: mid-year joiners and leavers
  with pro-rated CTC, multiple income sources, prior-employer TDS
  certificates, bonuses and variable pay, and ESOP taxation. Each of these
  needs its own scoping work, ideally reviewed by a practicing CA before
  being trusted at real enterprise scale — the same discipline that caught
  the 271C citation error above.
- **Closing the audit-mode loop further — this is now partially built, not
  fully.** The maker-checker review flow and the Bulk Salary Revision
  export (see the dedicated section above) take a flagged employee from
  "here's an issue" to a real, reviewable, approved correction and a
  downloadable revision file. What's still roadmap, not built: any actual
  RazorpayX-side application of that correction — the export produces a
  file for manual upload, it doesn't touch RazorpayX at all, matching the
  no-live-dispatch boundary drawn everywhere else in this project.
- **Who actually operates this, day to day — an open product question,
  not yet a design decision.** HR, a payroll admin, an individual employee,
  or an API Razorpay's own systems call internally are all plausible, and
  each implies a different permission model and a different UI. This
  build doesn't answer it yet.

## What broke during development (and what that caught)

- An early draft of the 87A rebate function was left in a broken, duplicate
  state after an editing false-start, before the final version replaced it.
  Caught by review before it reached production logic.
- A test asserting "salary up to ₹12.75L is tax-free" initially failed — not
  because the engine was wrong, but because the test fed the engine *taxable*
  income where the ₹12.75L figure actually refers to *gross* salary before
  the ₹75,000 standard deduction. The engine was correct; the test needed
  fixing — catching your own test being wrong is a stronger signal than
  catching a bug in the code itself.
- The optimizer's `basic_pct` search initially had no upper bound. A pure
  tax-minimizing search with no ceiling pushes basic toward unrealistic
  levels, since more basic mathematically shelters more income via employer
  PF/NPS. A 50% ceiling was added as an explicit, documented tradeoff.
- While building the delayed-remittance penalty scenario, an initial draft
  included a Section 271C figure paired with the deposit-delay case this
  feature models. Independent verification against the actual Supreme Court
  ruling (not just training-data recall) caught that 271C legally cannot
  apply to that scenario, and it was removed before shipping rather than
  left in — the exact kind of citation error a feature built around "real
  citations, not hallucinated" can't afford to make.
- The hypothetical-recalc query path (`/api/query`, "what if my rent were
  X") had never been run against the real Claude API before a live test
  pass caught that its numeric guard was silently rejecting almost every
  real answer: the guard's allow-list checked the recalculated tax figures
  but not the changed parameter's own new value, which any natural-language
  answer restates as a matter of course ("if your rent were ₹2,00,000..."),
  so the feature was quietly always falling back to its templated response.
  The deterministic-fallback test suite couldn't have caught this — it
  exercises the fallback path directly, not the guard logic that sits in
  front of a real LLM response. Fixed by adding the changed value to the
  guard's allow-list when it's numeric.
- `/api/optimize-batch` had never been load-tested. With a live API key, a
  20-row batch didn't complete inside 60 seconds, and a 500-row batch
  didn't complete inside 2 minutes. Measured, not assumed: isolating the
  same 20-row batch with the AI layer off completed in 0.11 seconds — the
  entire cost was one sequential, blocking Claude API call per row to
  generate that row's prose explanation. Checked whether that explanation
  was actually used anywhere: `batch-results-table.tsx` renders only
  row/CTC/regime/saving/guardrail columns — the explanation text was
  computed and then discarded on every single row, in every batch, before
  this was found. Fixed by skipping that AI call in batch mode specifically
  (`explain_result(..., skip_ai=True)`); the single-candidate flow, where
  the explanation is actually shown, is untouched. The same 20-row batch
  now completes in under 4 seconds; a 500-row batch completes in ~34
  seconds (~69ms/row) instead of not completing at all.
- The salary-revision export's honesty-label header hung the dev server
  on the first real request against it, not in testing against mocked
  data. `X-Template-Honesty-Label` carried the label text verbatim,
  including an em dash — HTTP header values have to be Latin-1-encodable,
  and the em dash isn't, so werkzeug threw a `UnicodeEncodeError` mid
  response and the client hung waiting for a response that never
  finished. The file's own Read Me sheet keeps the original Unicode text
  fine (a spreadsheet cell has no such constraint); only the header copy
  needed sanitizing. Caught by actually calling the endpoint over real
  HTTP with a timeout, not by reading the code — this is exactly the kind
  of bug that inspection alone doesn't surface.

## Test coverage

61 tests total — 51 in `tests/test_finos.py` covering the marginal relief
calculation (validated against the government's own worked example), the
old-vs-new regime crossover, HRA metro vs non-metro, the PF statutory-ceiling
toggle, extraction's mismatch-detection logic, the explainer's numeric guard
(including that batch mode's `skip_ai` path stays deterministic), each
compliance rule's trigger condition, and the conversational query layer's
hypothetical-recalculation path; plus 10 in `tests/test_review_workflow.py`
covering the maker-checker flow end to end — submission persistence,
approval writes the correct simulated-not-dispatched status, rejection
requires and stores a reason, the diff view's before/after values match a
real optimizer run exactly (no invented attribution text), mixed-batch
rows are decided independently, duplicate submissions are flagged rather
than reprocessed, a double-approve doesn't double-write, and the salary-
revision export's XLSX contains the real corrected values with the
honesty label present. All pass with no `ANTHROPIC_API_KEY` set,
exercising every deterministic fallback.

**The live LLM-backed path has been tested end-to-end against the real
Claude API**, not just its deterministic fallback: extraction, explanation,
compliance-flag phrasing, query classification, and the hypothetical-recalc
query path were each exercised with a real `ANTHROPIC_API_KEY` and their
output checked against the deterministic figures they're supposed to be
grounded in. This testing caught one real bug — the hypothetical-recalc
numeric guard's `allowed` set was missing the changed parameter's own new
value (e.g. a restated rent figure), so any live answer that naturally
repeated the number from the question (nearly all of them) was spuriously
guard-rejected and silently fell back to the templated response, even though
nothing was actually wrong with the answer. Fixed in `ai_layer.py` by adding
the new numeric value to the guard's allow-list when the changed parameter
is itself a number (`rent_paid`/`ctc`); all 49 tests still pass.
