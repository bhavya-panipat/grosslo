# grosslo — the AI-assisted payroll controller for RazorpayX

Built for the Razorpay AI Buildathon 2026, AI Finance Controller track.

grosslo structures a compensation offer, checks it against a company's approved
band and statutory ceilings, forecasts the capital a treasury team needs to fund
it, and exports a schema-accurate RazorpayX Composite Payout payload — for one
candidate at a time or a whole CSV batch. Every step is logged as a real
execution trace, not a black box: what ran, what it found, and why.

**What grosslo is today, stated precisely:** the decision and compliance
layer a real autonomous controller would need underneath it — not yet the
acting system itself. Every code path here terminates in a recommendation
or a generated payload; nothing in this build calls RazorpayX's real API,
writes to a database, or moves money. That boundary is deliberate (see
"Known limitations" and "Roadmap" below), and it's the honest reason this
is scoped as a controller *in name and direction*, not yet in the sense of
holding write-authority over anything.

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
python3 -m unittest discover -s tests   # 49 tests, all pass with or without an API key
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

- **Persisted employee roster** — a real database so the treasury forecast
  can show a company's steady-state payroll baseline, not just the
  incremental capital for whichever CSV was uploaded in a given session.
- **Live RazorpayX dispatch, gated behind real OAuth and a human-approval
  step** — today the export stops at generating a correct payload on
  purpose; going further requires real credentials and an audit trail
  before any actual payout is safe to trigger automatically.
- **Ecosystem-partner integration** — distributed to companies already on
  RazorpayX rather than as a standalone tool competing for signups.
- **Wider compliance rule coverage** — the current 6 rules and the tax
  engine's scope (no surcharge, single income source, resident individuals
  only) are deliberately narrow; real enterprise payroll needs more edge
  cases covered, ideally reviewed by a practicing CA before being trusted
  at that scale.

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

## Test coverage

49 tests across `tests/test_finos.py`, covering the marginal relief
calculation (validated against the government's own worked example), the
old-vs-new regime crossover, HRA metro vs non-metro, the PF statutory-ceiling
toggle, extraction's mismatch-detection logic, the explainer's numeric guard,
each compliance rule's trigger condition, and the conversational query
layer's hypothetical-recalculation path. All pass with no
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
