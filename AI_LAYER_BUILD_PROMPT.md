# FinOS — AI-Native Layer: Build Prompt

**Feed this entire document to your coding agent (Claude Code / Codex / Emergent) as
the task specification. It contains the file inventory, what's already validated,
what to build, in what order, and the architectural rules that must not be broken.**

---

## 0. Instructions for the agent executing this

You are extending an existing, working Python project (FinOS) with an AI-native
layer for a hackathon submission. Read Sections 1-2 fully before writing any code.
The tax calculation logic in `tax_engine.py` and `optimizer.py` is already built
and validated against government reference examples — **do not modify the core tax
math in those files.** If you believe a bug exists in them, flag it explicitly to
the user rather than silently changing behavior; that logic was hard-won and
re-verified multiple times.

Build in the exact phase order given in Section 4. Do not start Phase 2 until
Phase 1 is demoable end-to-end. Do not start Phase 3 until Phase 2 is demoable.
If you run out of time, the project must still work with whatever phases are
complete — each phase should degrade gracefully, not leave the app broken.

---

## 1. Existing files (already built, do not rewrite core logic)

| File | Contents | Status |
|---|---|---|
| `tax_engine.py` | Progressive slab tax calculation (old + new regime, FY 2025-26/26-27), Section 87A rebate, marginal relief, HRA exemption formula, LTA exemption (capped at 70% assumed utilization), employer PF (12% of basic), employer NPS/80CCD(2) (10%/14% of basic by regime), 4% cess | Validated against government's own worked marginal-relief example (exact match) |
| `optimizer.py` | Grid-search optimizer: finds tax-minimizing basic/HRA/LTA/special-allowance split for a given CTC, separately under old and new regime, returns both plus the winner and the rupee delta | Basic floor 40% / ceiling 50% of CTC (documented assumptions), sanity-checked across multiple CTC bands |
| `FINOS_PROJECT_BRIEF.md` | Full project brief: scope, assumptions table (9 items), known gaps (notably: aggregate employer PF+NPS+superannuation >₹7.5L/year perquisite tax NOT modeled), open questions | Reference doc — read for context, especially the assumptions table before writing anything that touches tax logic |

**Known unresolved gap (carried over from brief, still open):** the >₹7.5L
aggregate employer contribution perquisite tax rule is not modeled. Decide in
Phase 1 whether to model it or add a hard CTC ceiling to the tool's stated valid
range (e.g., "not validated above ₹40L CTC") — do not leave this silently
unaddressed, since the optimizer's own logic (favoring higher basic) is exactly
what could trigger this edge case.

---

## 2. Non-negotiable architecture rule

**LLM components in this project NEVER compute, restate, or regenerate tax
figures.** Every number shown to the user (tax amount, exemption amount, salary
split figures, rupee delta) must be produced by `tax_engine.py`/`optimizer.py`
and passed to the LLM as already-computed data. LLM components only:
- extract structured input data from unstructured text/documents (Phase 1)
- narrate/explain already-computed results in plain language (Phase 2)
- pattern-match a structure against a fixed, documented rule checklist and
  phrase the findings in plain language (Phase 3)

If any LLM output contains a number that didn't come from the engine, that's a
bug. Test for this explicitly — e.g., assert that numeric values in the
explainer's output match the engine's output to the rupee.

This is the single most important constraint in this document. The entire
credibility argument for this project (verified, auditable tax math) breaks if
the AI layer is allowed to hallucinate figures on top of it.

---

## 3. What to build — three AI-native components

### 3.1 Document extraction agent (Phase 1)
**Input:** a messy offer letter or existing CTC breakup, as PDF or image upload.
**Output:** structured JSON matching the input shape `optimizer.py` already
expects (total CTC, and if present, existing basic/HRA/LTA/special allowance
breakdown).
**Approach:** LLM with vision/document input (Claude API — use PDF/image input
per the product's document-handling capability) prompted to extract specific
named fields, returning strict JSON only. Validate the extracted total against
the sum of extracted components where both are present, and flag a mismatch to
the user rather than silently picking one number.
**Failure mode to design for:** offer letters vary wildly in format. The
extraction should have a manual-correction step in the UI (show extracted
values, let user fix before proceeding) rather than trusting extraction blindly
and feeding bad data straight into the optimizer.

### 3.2 Explainer agent (Phase 2)
**Input:** the optimizer's full output object (old regime best, new regime
best, recommended winner, delta, and the underlying structure numbers).
**Output:** a plain-language explanation of why the recommended structure is
optimal for this specific user's numbers — not a generic explanation of how
Indian tax law works.
**Approach:** LLM prompted with the structured result object and instructed to
narrate it, explicitly forbidden from introducing new figures. Good explanation
should reference the user's actual rent/CTC/city inputs to make clear it's
personalized, not templated (e.g., "because your rent is high relative to your
CTC, your HRA exemption is close to the legal cap of 50% of basic, which is
why old regime still edges out new regime here" — reasoning grounded in the
engine's actual numbers, not invented).

### 3.3 Edge-case / compliance-risk flagging agent (Phase 3)
**Input:** a proposed salary structure (either the optimizer's output, or a
structure the user/extraction agent provided that wasn't optimized).
**Output:** a list of flagged risks or red flags, each tied to a specific,
documented rule — not freeform legal opinion.
**Approach:** maintain an explicit, versioned checklist file (e.g.,
`compliance_rules.md`) of known red-flag patterns — e.g., basic below common
market floor, missing PF where CTC size suggests it should apply, LTA claimed
at a level inconsistent with the stated city/role, HRA claimed with no rent
input. The LLM's job is to check the given structure against this fixed
checklist and phrase findings clearly — it should not be free-associating
compliance advice outside the checklist. This keeps the "compliance" framing
honest: it's a documented-pattern checker, not a legal opinion generator, and
that distinction should be stated explicitly in the demo (a fintech engineer
will ask, and "we check against a fixed documented ruleset, we don't fake being
a tax lawyer" is a strong, credible answer).

---

## 4. Build phase order (do not skip ahead)

**Phase 1 — Document extraction, wired to existing optimizer.**
Deliverable: user uploads an offer letter, sees extracted (and correctable)
CTC, clicks through to the existing optimizer output. This alone is a complete,
demoable product even if Phases 2-3 don't ship — it's a real AI-native feature
(unstructured → structured) sitting on top of validated tax logic.

**Phase 2 — Explainer agent.**
Deliverable: the optimizer's output is now accompanied by a personalized
plain-language explanation. Test explicitly that no invented numbers appear.

**Phase 3 — Compliance-risk flagging.**
Deliverable: a documented checklist file plus an agent that checks structures
against it and reports findings. Lowest priority of the three — cut first if
time runs short.

**MVP cutline: if only Phase 1 ships, that is still a complete, coherent,
demoable submission.** Do not leave Phase 1 half-done in order to start Phase 2.

---

## 5. Decisions still needed from the user before/during build (do not assume)

- **LLM provider/API for the agent layers** — confirm which API key/setup is
  available (Claude API is the natural fit given the project's origin, but
  confirm before hardcoding).
- **Interface shape** — web app, CLI, or notebook? This determines how the PDF
  upload (Phase 1) and chat-style explanation (Phase 2) actually get built.
  Not yet decided in the project brief — resolve before starting Phase 1's UI.
- **Sample offer letters for testing extraction** — Phase 1 needs real (or
  realistic synthetic) varied-format sample documents to test against; without
  these, extraction accuracy can't actually be validated before the demo.
- **compliance_rules.md content** — the actual checklist for Phase 3 needs to
  be drafted and sourced (market convention + the same public tax rules already
  cited in `FINOS_PROJECT_BRIEF.md`) before that agent can be built at all.

---

## 6. Testing expectations for new code

- Phase 1: test extraction against at least 3-4 differently-formatted sample
  documents; test the mismatch-detection logic (extracted total vs sum of
  components) with a deliberately inconsistent sample.
- Phase 2: assert numeric values in explainer output match engine output
  exactly; test with at least one old-regime-wins case and one new-regime-wins
  case, since the explanation logic differs meaningfully between them.
- Phase 3: test the checklist-matching logic against at least one structure
  that should trigger each rule, and one clean structure that should trigger
  none.
