# FinOS — AI-assisted CTC structuring optimizer

Given a salaried employee's total CTC, rent, city tier, and NPS preference,
FinOS computes the tax-minimizing salary structure under both the old and new
Indian tax regimes, recommends the better one, explains why in plain
language, and flags a fixed checklist of compliance risks — all without ever
letting an LLM invent a tax figure.

Built for the Razorpay AI Buildathon 2026, Open Track.

## Architecture

```
User input (form or pasted offer letter)
        │
        ▼
ai_layer.py — extraction        (LLM, with deterministic regex fallback)
        │
        ▼
optimizer.py + tax_engine.py    (deterministic, validated — sole source of
        │                        every number shown to the user)
        ▼
ai_layer.py — explanation       (LLM narrates the engine's numbers, never
                                  invents its own — see numeric guard below)
        │
ai_layer.py — compliance flags  (rule matching is always deterministic;
                                  LLM only rephrases already-decided flags)
        ▼
Result shown to user
```

**The one rule that matters most in this codebase:** no LLM call in
`ai_layer.py` is ever allowed to compute, restate with different rounding,
or invent a tax/salary figure. Every number the user sees traces back to
`tax_engine.py` / `optimizer.py`. This is enforced two different ways
depending on the function:

- **Explanation** — a numeric guard extracts every number the LLM's response
  contains and rejects the response (falling back to a templated
  deterministic explanation) if any number isn't traceable to the input data
  the LLM was given.
- **Compliance flags** — rule matching against `compliance_rules.md` happens
  entirely in Python before the LLM ever sees anything. The LLM's only job is
  rephrasing already-decided flags into cleaner sentences; it cannot add,
  remove, or reinterpret a flag.

## Running it

```bash
python3 -m unittest discover -s tests   # 23 tests, all pass with or without an API key
python3 app.py 8000                     # serves the UI + API at http://127.0.0.1:8000
```

To enable the real LLM-backed extraction/explanation/compliance-phrasing,
set `ANTHROPIC_API_KEY` before starting the app. **Without a key, the app
still runs correctly** — every AI-layer function has a deterministic
fallback, and `/health` reports `ai_layer_active: false` so this is visible
rather than silent. This was a deliberate design choice, not a fallback
bolted on after the fact: a hackathon demo that hard-crashes without network
access or a valid key is a worse outcome than one that gracefully degrades
and says so.

## What's genuinely AI-native here, and what isn't

Being direct about this because a reviewer will ask: the tax calculation
(`tax_engine.py`, `optimizer.py`) is entirely deterministic, on purpose — a
grid-search optimizer over a well-defined rules problem, chosen specifically
*because* a general-purpose LLM should not be doing arithmetic on someone's
tax liability. The AI-native part is the four `ai_layer.py` functions:
pulling structured numbers out of messy unstructured offer-letter text
(genuinely hard to do reliably with regex alone), turning a table of
optimizer output into a plain-language explanation personalized to the
user's actual numbers, phrasing compliance findings clearly, and — when an
offer letter's actual structure was extracted — drafting negotiation
talking points that compare the as-offered structure against the
recommendation. The negotiation copilot states one number with full
confidence (the total annual rupee saving, a plain subtraction) and
deliberately does NOT attribute a separate rupee figure to each individual
lever that changed (basic, HRA, NPS opt-in, etc.) — when multiple
components move together, the tax function isn't linear across them, so a
clean per-lever rupee split would itself be a false-precision claim rather
than a fact. It only reports which levers changed, not how many rupees
each one is individually "worth." If asked "why isn't the tax math itself
AI-powered," the honest answer is that it shouldn't be — that's the entire
point of the numeric-guard architecture.

## Known limitations (stated explicitly, not left for a reviewer to find)

- **Surcharge** (income above ₹50L) is not modeled. Tool is scoped for the
  salaried CTC ranges typical of early-to-mid career hires.
- **Aggregate employer PF + NPS + superannuation above ₹7.5L/year** is a
  taxable perquisite under Section 17(2)(vii) that `tax_engine.py` does not
  currently calculate into the tax figure. This gap is not silent — rule R5
  in `compliance_rules.md` exists specifically to flag structures that cross
  this threshold, so the user is warned even though the engine doesn't yet
  compute the actual extra liability.
- **LTA exemption** is modeled at a conservative assumed 70% utilization
  rather than the full claimed amount, since real LTA exemption depends on
  actual travel, valid bills, and a twice-per-4-year block limit that a
  structuring tool can't know in advance.
- **Basic salary is constrained to 40–50% of CTC.** The floor is market
  convention; the ceiling was added deliberately after an early build
  iteration showed an unconstrained tax-minimizing search pushes basic
  upward indefinitely (since employer PF/NPS shelter more tax as basic
  grows), which produced structures no real company would implement.
- **Extraction is not guaranteed accurate**, LLM-backed or not — the UI
  always shows extracted values for manual correction before they're used,
  and flags a mismatch warning when extracted components don't sum to the
  extracted CTC (only once at least 4 of 5 components are present, to avoid
  false-positive warnings on offer letters that simply don't itemize
  everything).
- Assumes a resident individual, under 60, salaried, with no other income
  sources or capital gains.

## What broke during development (and what that caught)

- An early draft of the 87A rebate function was left in a broken,
  duplicate state after an editing false-start, before the final version
  replaced it. Caught by code review before it reached production logic.
- A test asserting "salary up to ₹12.75L is tax-free" initially failed —
  not because the engine was wrong, but because the test fed the engine
  *taxable* income where the ₹12.75L figure actually refers to *gross*
  salary before the ₹75,000 standard deduction. The engine was correct; the
  test needed fixing. Worth stating plainly: catching your own test being
  wrong is a different (and arguably stronger) signal than catching a bug
  in the code itself.
- The optimizer's `basic_pct` search initially had no upper bound. Before
  building further on top of it, this was caught and fixed: a pure
  tax-minimizing search with no ceiling pushes basic toward unrealistic
  levels, since more basic mathematically shelters more income via
  employer PF/NPS. A 50% ceiling was added as an explicit, documented
  design tradeoff — not the true unconstrained mathematical optimum, but a
  realistic one.

## Test coverage

23 tests across `tests/test_finos.py`, covering: the marginal relief
calculation validated against the government's own worked example, the
old-vs-new regime crossover (including the case where old regime wins —
high CTC, high rent, NPS not opted), HRA metro vs non-metro, the PF
statutory-ceiling toggle, extraction's mismatch-detection logic (both the
true-positive and false-positive-avoidance cases), the explainer's numeric
guard, and each compliance rule's trigger condition. All 19 pass with no
`ANTHROPIC_API_KEY` set, exercising every deterministic fallback path.

**Not yet tested:** the live LLM-backed path for all four `ai_layer.py`
functions — this requires a real `ANTHROPIC_API_KEY` and hasn't been
exercised end-to-end against the actual Claude API. Test that explicitly
before relying on it in a live demo; don't assume the fallback tests cover
it.
