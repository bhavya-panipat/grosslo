# FinOS — Prompt for Emergent

**Paste this whole document as the task brief. Attach the files listed in
Section 1 to the same conversation before sending.**

---

## 0. The one rule that overrides everything else in this brief

Do NOT regenerate the tax calculation logic from a description. Port it
verbatim from the attached files. This logic has been validated against the
Indian government's own worked example for marginal relief (exact match:
₹61,500 slab tax → ₹10,000 payable at ₹12.1L taxable income) and has 23
passing tests covering regime crossover cases, HRA/PF edge cases, and the
AI-layer numeric-guard architecture. If you rewrite it from scratch based on
your own understanding of Indian tax law instead of porting the attached
code, you will silently reintroduce bugs that already got caught and fixed
once. Re-implement the same 23 tests in whatever stack you use, and do not
report the build as complete until they pass against your ported version.

If you genuinely believe something in the attached logic is wrong, say so
explicitly and ask — do not silently "fix" it.

---

## 1. Files attached — what's already validated, don't rebuild these from scratch

- `tax_engine.py` — progressive slab tax (old + new regime), Section 87A
  rebate, marginal relief, HRA exemption, LTA exemption (capped at 70%
  assumed utilization — a documented conservative assumption, not statute),
  employer PF/NPS.
- `optimizer.py` — grid-search optimizer over feasible salary structures
  (basic constrained to 40-50% of CTC — also a documented assumption, not
  statute), plus `evaluate_given_structure` / `best_regime_for_given_structure`
  for scoring one specific structure (used by the negotiation feature).
- `ai_layer.py` — four LLM-backed functions (extraction, explanation,
  compliance flagging, negotiation copilot), each with a deterministic
  fallback and a numeric guard that rejects any LLM output containing a
  rupee figure not traceable to already-computed engine output.
- `compliance_rules.md` — the fixed rule checklist `ai_layer.py` checks
  structures against.
- `tests/test_finos.py` — 23 tests. Port these to your stack's test
  framework and confirm they pass.
- `README.md` — full context: architecture rationale, known limitations
  (notably: aggregate employer PF+NPS above ₹7.5L/year isn't modeled as a
  taxable perquisite yet), and the three real "what broke during
  development" stories from building this.

---

## 2. The non-negotiable architecture rule (carries over from the attached code)

LLM calls in this project never compute, restate, or invent a tax/rupee
figure. They extract structured data from unstructured text, explain
already-computed results in plain language, phrase already-decided
compliance flags, and draft negotiation talking points — always citing
numbers that trace back exactly to `tax_engine.py` / `optimizer.py` output.
Preserve the numeric-guard pattern from `ai_layer.py` in whatever language
you rebuild the API layer in. This is the actual brand of the product:
**"the AI that explains your money but never invents it."** It is not a
disclaimer to bury — it's the differentiator.

One specific rule to preserve exactly: the negotiation feature states a
total rupee saving with full confidence (a plain subtraction) but
deliberately does NOT split that figure across individual structural
levers (basic, HRA, NPS, etc.) — when multiple components change together,
the tax function isn't linear across them, so a per-lever rupee split would
be a false-precision claim. Keep this constraint; don't "improve" it by
adding per-lever numbers.

---

## 3. What to build — the frontend and experience layer

This is the part that's actually open for you to design. Build:

1. **A real landing/hero section** — not a generic SaaS hero. The subject
   is auditability: every number the user sees can be traced back to
   something checkable. Design around that, not around generic AI
   aesthetics. Avoid the reflexive AI-generated defaults: cream-background
   serif-with-terracotta-accent, near-black-with-neon-accent, or
   broadsheet-hairline-newspaper layouts — pick a direction that's actually
   grounded in "ledger / audited / verifiable," not decoration for its own
   sake.
2. **Animated, sophisticated dashboards for the result** — the current
   reference build (also attached, in `static/`) uses a staggered
   card-reveal, a count-up animation on the headline saving figure, and a
   small "verified" stamp beside any AI-touched output. You are free to go
   further (e.g. a real chart comparing old vs new regime, an animated
   breakdown of where the CTC goes) but keep the verified/rule-based
   distinction visually present everywhere an AI-touched number appears —
   do not let a slicker UI quietly erase the honesty signal that's the
   actual point of this project.
3. **Smooth transitions** between the offer-letter extraction step, the
   details form, and the result — this should feel like one coherent flow,
   not three disconnected pages.
4. **Mobile-responsive, with visible keyboard focus states and
   `prefers-reduced-motion` respected** — don't skip this for a demo; a
   judge may view this on a phone.

---

## 4. What NOT to do

- Don't invent new tax rules, new regime logic, or new exemption formulas —
  everything tax-related is in the attached files already.
- Don't remove or soften the "rule-based fallback" / "AI-generated" tags in
  the UI — they're load-bearing for the project's actual credibility story,
  not just debug info.
- Don't silently drop the numeric guard to make the UI simpler. If the
  guard rejects an LLM response, the UI must show the fallback, clearly
  labeled, not hide the failure.
- Don't add a live database, user accounts, or persistent storage unless
  explicitly asked — this is a stateless calculator, keep it that way
  unless the brief changes.

---

## 5. Deliverable

A working app (your choice of stack) that:
- Reproduces the exact same tax outputs as the attached Python files for
  the same inputs (spot-check against the reference case: ₹18,00,000 CTC,
  ₹4,00,000 rent, metro, NPS opted → new regime, ₹88,140 tax, ₹36,972
  annual saving vs old regime — these exact figures should reproduce
  precisely)
- Passes a ported version of the 23 tests in `tests/test_finos.py`
- Has the landing page, animated dashboard, and smooth transitions
  described in Section 3
- Preserves the numeric-guard architecture and the visible AI-backed /
  rule-based labeling throughout

If anything in this brief is ambiguous, ask before building — don't guess
and build the wrong thing, especially on the tax logic.
