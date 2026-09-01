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

**Isn't this what RazorpayX Payroll already does?** RazorpayX Payroll is a
real, shipped product with CTC structuring, statutory filing, and direct
disbursement already built. grosslo doesn't re-implement that — it's
narrower and more forensic: per-hire tax-optimization modeling, a
maker-checker governance layer with a real audit trail, and an audit-sweep
mode that runs the same checks *backwards* over payroll a company already
runs elsewhere, which a payroll-execution product has no reason to build.
See "Isn't this what RazorpayX Payroll already does?" in
`FINOS_PROJECT_BRIEF.md` for the full answer, not just the summary.

## What it actually does

- **Structure**: given a CTC (or a pasted, messy offer letter), computes the
  tax-minimizing salary split under both the old and new Indian tax regimes and
  recommends the better one — the deterministic core this was originally built
  around.
- **Check**: every structure is run against a fixed compliance rule set
  (`compliance_rules.md`, six rules) and a payroll guardrail (approved
  compensation band, the ₹7.5L aggregate EPFO contribution ceiling, the
  regime-specific Section 124 employer-NPS cap, formerly Section 80CCD(2)
  under the 1961 Act — see "Regulatory currency" below).
- **Forecast**: net take-home, TDS escrow, and EPFO challan are summed into a
  single capital-outlay number, with a funding lead time — what treasury needs
  to have ready before payroll runs.
- **Export**: a real RazorpayX Composite Payout payload (verified against
  RazorpayX's own API docs, not guessed) — nested `fund_account`/`contact`,
  amount in paise. No live call is ever made; this generates the payload only.
- **Batch**: `/hr`'s CSV upload structures a set of new offers in one pass —
  the single path for this now, single or batch, so every new hire goes
  through the same Finance review an individual offer does (see "Redundancy
  fix" below). `/optimize/batch` is a separate, audit-only CSV flow: point
  the same guardrail checks at *existing* employee structures, surface
  unclaimed regime-switch savings and excess EPFO contributions across the
  whole set, and send any flagged row to Finance the same way. The summary
  isn't just two currency totals — it reports clean vs. flagged counts and
  a real exception breakdown (over the EPFO cap vs. filed under the wrong
  regime entirely for that structure, a genuinely different signal from
  "unclaimed savings"), so a batch narration has actual on-screen counts to
  point at instead of a number nobody watching can verify.
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
- **Bulk actions batch the click, never the judgment.** A "Submit all N
  for review" button on the audit page sends every flagged row in one
  `/api/submissions` batch call instead of N separate ones — the endpoint
  already accepted a batch array, this just uses it. On `/finance`, row
  checkboxes plus "select all pending" open a bulk action bar that
  approves or rejects every selected row in one click; rejection still
  requires a reason, one shared reason applied to the whole selection,
  with the UI saying plainly to reject rows individually if they need
  different explanations. There's no bulk-decide endpoint and no need for
  one — this fires the same idempotent per-row `/decide` call once per
  selected row, in parallel, so every row still gets its own individually
  logged decision. Nothing here lets anything but a person decide.
- **Bulk Salary Revision export** (`POST
  /api/submissions/<id>/rows/<row_index>/export`, approved rows only)
  closes the audit loop the rest of the way: takes a flagged employee's
  current + corrected structure (already computed by the audit, invented
  nowhere here) and generates a real multi-sheet XLSX — modeled on
  RazorpayX Payroll's own documented two-sheet Salary Revision format
  (Default Structure, Custom Structure), plus a Read Me sheet. **The exact
  column headers were not verified against a live RazorpayX account** —
  the file says so explicitly, in its own Read Me sheet and in the
  response's `X-Template-Honesty-Label` header, so this is never mistaken
  for a confirmed, ready-to-upload template. After download, `/finance`
  shows a **"Simulate upload to RazorpayX Payroll"** confirmation
  button — deliberately *not* a fake API-call preview like new hire's
  Composite Payout payload gets: Bulk Salary Revision is a RazorpayX
  Payroll dashboard file-upload feature, not a documented JSON API, so
  simulating an API call for it would mean inventing a schema nothing
  has verified. The confirmation step mirrors new hire's "review, then
  confirm" UX without pretending an API call happened where only a file
  upload actually would.

**What this deliberately is not:** real authentication. `/hr` and
`/finance` each sit behind their own simulated access-code gate
(`role-gate.tsx`) — `HR2026` and `FINANCE2026`, unlocking one has no
effect on the other — but it's a client-only UX gate, not identity
verification: there's no server-side session or account behind it, the
code ships in the same client bundle anyone downloads, and it's shown on
the gate screen itself rather than hidden, on purpose, so it's never
mistaken for something it isn't. Anyone who reaches the app can reach both
roles the moment they read the code shown on screen — this simulates what
role-gated access would *feel* like from inside the demo, it doesn't
provide it. Also deliberately absent: a production database (SQLite, a
single gitignored file, explicitly not the "real database" the roadmap
describes for a steady-state company roster), a second-approver escalation
tier, or a notification system for pending reviews. All three are
reasonable ideas in isolation; none of them belong on top of an approval
layer already honestly labeled as a demo simplification — making that
layer *look* more sophisticated than the authentication underneath it can
actually support would undermine the exact honesty this section is trying
to model.

### Redundancy fix: one path for structuring a new hire, not two

`/optimize/batch` used to have a "New Hire Batch" mode alongside
"Compliance & Savings Audit" — it computed a structure via
`/api/optimize-batch` and offered a direct "Export N to RazorpayX" button
with **no Finance review step at all**, while `/hr`'s batch upload went
through the exact same computation and then queued it for approval. Same
underlying pipeline, two different governance outcomes depending on which
page happened to be open — a real workflow gap, not a cosmetic one.

Fixed by removing the redundant path entirely, not just hiding it in the
UI: `/api/optimize-batch` no longer exists, `/optimize/batch`'s mode
toggle is gone, and it's audit-only now. `/hr` is the sole path for
structuring a new hire, single offer or CSV batch, and it always goes
through Finance.

That fix surfaced three more gaps behind the same redundancy, closed
together rather than one at a time:

- **`/api/submissions` never ran the payroll guardrail at all.** Only the
  standalone `/api/optimize-batch`/`/api/export-razorpayx` paths checked
  a compensation band; an offer submitted through `/hr` could be approved
  with zero guardrail signal anywhere in the review queue. Fixed —
  `/api/submissions` now runs `evaluate_band_guardrail()` whenever
  `band_min`/`band_max` are supplied, the same function every other route
  uses.
- **No path from an approved row to a real export.** Approving in
  `/finance` only ever wrote a status change; there was no way to turn
  that decision into an actual RazorpayX payload or Salary Revision file
  without leaving the review queue and re-entering everything by hand in
  a separate modal. Fixed with `POST
  /api/submissions/<id>/rows/<row_index>/export` — approved-only, and it
  branches on what the row actually was: a correction (has a prior
  `current_structure`) generates the Salary Revision XLSX, a new hire
  generates a RazorpayX Composite Payout payload from the bank details
  supplied at submission time. `/hr` now also collects `band_min`/
  `band_max`/`bank_account_number`/`ifsc`/`email` (all optional) for
  exactly this reason — see the persistence note above for what that
  means for stored data.
- **The Bulk Salary Revision export had zero frontend wiring.**
  `/api/export-salary-revision` (the original standalone endpoint) is
  still never called from any page — it remains a real, tested capability
  with no UI path to it, which is itself a known gap rather than
  something newly introduced here. The new per-row export above reuses
  the same `build_salary_revision_workbook()` function directly instead
  of routing through that standalone endpoint, so a correction row's
  export works today even though the standalone route's own UI gap is
  unresolved.

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
python3 -m unittest discover -s tests   # 73 tests, all pass with or without an API key
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
  - **No real access control — `/hr` and `/finance`'s access-code gate is
    a UX simulation, not authentication.** Each page checks a hardcoded
    demo code against `sessionStorage`, client-side only; there's no
    server-side session, no account, and the code itself is shown on the
    gate screen rather than hidden. See "Maker-checker review, demo-scoped"
    below. Anyone who reaches the app can reach both roles the moment they
    read the code shown on screen.
  - **The review queue does store employee PII, including bank details —
    named explicitly, not glossed over.** Employee name and CTC were
    always stored (needed for the dedupe check); as of the redundancy fix
    that unified new-hire structuring onto `/hr`, an offer's `band_min`/
    `band_max`/`bank_account_number`/`ifsc`/`email` are stored too, when
    HR supplies them — this is what lets an approved row generate a real
    RazorpayX payout payload later, rather than requiring the export
    modal's separate manual re-entry. It sits in the same unencrypted,
    access-control-free SQLite file as everything else here, so this is
    exactly the kind of data the "no encryption at rest" and "no access
    control" gaps above are about — real production use needs those
    closed before real bank details go anywhere near this schema. The
    audit log remains the one exception: it excludes names/bank
    details/emails by construction (see its own section below), and that
    claim is unaffected by this change.

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

## Regulatory currency — verified live on 2026-09-01, not assumed

India's payroll law changed substantially for FY 2026-27, and a codebase
that hardcodes statutory citations doesn't stay current on its own. This
section states exactly what was checked, against what, and what's still
open — the same "verify the source, don't trust recall" discipline that
caught the 271C citation error elsewhere in this document, applied to law
that changed after this build's own knowledge was formed, not just to a
citation that was wrong from the start.

**Confirmed current via live search, sources checked, not recalled:**
- The Income-tax Act 2025 replaced the Income-tax Act 1961 effective
  1 April 2026. Salary TDS moved from **Section 192 to Section 392**; the
  annual TDS certificate moved from **Form 16 to Form 130**.
- HRA's 50%-exemption metro-city list expanded from 4 cities to
  **8 — Delhi, Mumbai, Kolkata, Chennai, plus Bengaluru, Hyderabad, Pune,
  and Ahmedabad** — effective 1 April 2026. This build never hardcoded a
  city-name list anywhere (`city` is an abstract `"metro"`/`"non_metro"`
  flag the user selects) — so this law change doesn't correspond to a code
  defect here, only to a stale section citation (below).
- Section 10(13A) (HRA exemption) moved to **Section 11, read with
  Schedule II**. Section 80CCD(2) (employer NPS deduction) moved to
  **Section 124, read with Schedule XV** — the 10%/14% old-vs-new-regime
  rate split itself is unchanged and was already correct in
  `tax_engine.py`'s `NPS_80CCD2_CAP_PCT`.
- **Fixed in code**: every user-facing citation of the old section numbers
  (392/11+Schedule II/124) across `ai_layer.py`, `execution_trace.py`,
  `payroll_breakdown.py`, and this document — the old number is kept
  alongside the new one ("Section 124, formerly 80CCD(2)") since it's
  still the more recognizable, more-searched-for term, not because the old
  number is still correct on its own.

**Checked and found NOT to need a citation change:**
- Sections 7Q and 14B (`penalty_exposure.py`'s EPF interest/damages) are
  under the EPF & Miscellaneous Provisions Act 1952 — a different statute
  from the Income-tax Act entirely, unaffected by this renumbering.

**Checked, and genuinely unresolved — not silently left looking as current
as the citations above:**
- **Section 17(2)(vii)** (the >₹7.5L aggregate PF+NPS perquisite rule
  behind Rule R5 and the payroll guardrail) and **Section 201(1A)** (TDS
  late-deposit interest, in `penalty_exposure.py`) are both still cited
  under their 1961-Act numbers. Two real search attempts each found no
  confirmed 2025-Act mapping for either — the underlying provisions and
  rates are real and current, only the exact new section/schedule number
  is unverified. Left as the 1961-Act citation rather than guessing a
  replacement, since a fabricated new number would be a worse error than
  an old-but-real one.

**Flagged, not fixed — a real decision, not a citation:**
- **The Code on Wages 2025** (one of the four labour codes, effective
  21 November 2025, no grace period) requires basic pay + dearness
  allowance to be **at least 50%** of total remuneration; falling short
  triggers automatic reclassification of the excess allowances as "wages"
  for PF and gratuity purposes. `optimizer.py`'s `BASIC_PCT_MIN = 0.40`
  currently lets the search space recommend structures as low as 40%
  basic — below that new legal floor. This is a real, verified
  correctness gap, not a stale citation, and it lives in a file this
  project has treated as protected all along. It's named here rather than
  silently patched, because raising the floor to 50% would collapse the
  new-regime optimizer's entire search space to a single point (there's
  nothing left to search once `BASIC_PCT_MIN == BASIC_PCT_MAX`), which
  changes what "optimization" means for that regime and needs a real
  decision, not a one-line constant edit.

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
- A second, different bug in the same numeric guard, found while wiring
  its rejection state into the UI for the first time, not by inspection:
  in both branches of `answer_query()`, `guard_triggered` was computed
  correctly inside the try block, but the fallback return two lines down
  always hardcoded `"guard_triggered": False` — discarding the real
  computed value whenever the guard had actually just fired. A genuine
  live rejection would have silently reported itself as "nothing
  happened." `explain_result()` and `negotiate()` never had this bug, only
  the query layer's two paths did. Fixed by declaring `guard_triggered`
  outside the try block in both places. New tests mock only the external
  Claude call (a fabricated response stating an untraceable number) — the
  guard logic, the fallback text, and the True/False it reports are all
  real; this is the guard's rejection branch getting automated coverage
  for the first time, not just the pass-through branch.
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
  seconds (~69ms/row) instead of not completing at all. `/api/optimize-batch`
  itself no longer exists — it was the "New Hire Batch" mode's route,
  removed as part of the redundancy fix below; the `skip_explanation_ai`
  fix it originated carried forward into `/api/submissions` (batch source)
  and `/api/batch-audit`, which is what this same measurement still
  protects.
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

73 tests total — 54 in `tests/test_finos.py` covering the marginal relief
calculation (validated against the government's own worked example), the
old-vs-new regime crossover, HRA metro vs non-metro, the PF statutory-ceiling
toggle, extraction's mismatch-detection logic, the explainer's numeric guard
(including that batch mode's `skip_ai` path stays deterministic and that the
conversational query layer's guard genuinely rejects an untraceable number
and reports that it did, not just that it passes a traceable one), each
compliance rule's trigger condition, and the conversational query layer's
hypothetical-recalculation path; plus 19 in `tests/test_review_workflow.py`
covering the maker-checker flow end to end — submission persistence,
approval writes the correct simulated-not-dispatched status, rejection
requires and stores a reason, the diff view's before/after values match a
real optimizer run exactly (no invented attribution text), mixed-batch
rows are decided independently, duplicate submissions are flagged rather
than reprocessed, a double-approve doesn't double-write, the salary-
revision export's XLSX contains the real corrected values with the
honesty label present, an approved row's export is actually gated on
approval, a new-hire export contains the real bank details supplied at
submission (and fails clearly without them), a correction export returns a
real XLSX, the guardrail actually runs when a submission carries a band,
`/api/optimize-batch` is verifiably gone from the route map, and the batch
audit's clean/flagged/exception counts match a hand-verified mix of rows
(including a real regime-mismatch case found by brute-force search over
the optimizer, not asserted from assumption). All pass with no
`ANTHROPIC_API_KEY` set, exercising every deterministic fallback.

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
