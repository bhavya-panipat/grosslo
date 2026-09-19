# Output-boundary grounding: make the second layer check real output — design

**Status: implemented and verified 2026-09-20 (`bada9d4`, `8e47e5e`, `866176e`; record in §7).** Approved to be written by the user on
2026-09-15, framed as "output_boundary treats citation digits as figures, and
its test grounds a year by hand". Measuring that turned up a larger problem,
recorded first.

Measurements drive the real `app._build_optimize_response()` with
`skip_ai=False` and only the model client mocked, one reply per prompt. Nothing
was committed from them.

**Correction to this document, made 2026-09-16 just after `93318cd`.** Its first
version said every measurement was on `7c08da4`. That was false. They ran in
the shared working tree while the concurrent session had uncommitted
`tax_engine.py` changes there (since committed as `02d05a8`, employer-NPS
Option B). Everything was re-measured in clean worktrees at **both** commits.
The tables below now show what holds at each. The kind of failure is the same
at both. Which numbers coincide depends on the response's values, which the tax
fix changes.

---

## 1. What was measured

`output_boundary.ungrounded_findings(response)` is `OUTPUT_BOUNDARY_DESIGN.md`'s
second enforcement layer. It treats every string inside a section marked
`ai_backed: True` as model-authored. It builds the allowed set from every
numeric leaf **outside** those sections, plus the request's numbers, and matches
within an absolute tolerance of 1.

Its tests drive it two ways. One is the characterization baseline, where
`ai_backed` is False throughout, so nothing is checked. The other is
hand-built payloads: `test_a_legitimate_rephrasing_passes_both_layers` adds
`"metrics": {"basic_pct": 50, "year": 2025}` to make the R1 rephrasing pass.
**Neither drives it with a real AI-backed response.** Doing so:

### 1.1 False findings on legitimate output

| response | finding | why |
|---|---|---|
| R1 fires, pinned legitimate rephrasing ("…the 50% floor the Code on Wages 2025 requires.") | `compliance.flags[0].rationale`: 50, 2025, 50 | `rationale` is written by Python (`compliance_rules.py`), but it sits in an `ai_backed` section, so it is treated as model text |
| same | `compliance.flags[0].message`: 50, 2025 | 50 and 2025 are stated only in R1's rationale *string*, never as a numeric leaf, so nothing can ground them |
| R1 + R5 fire | `compliance.flags[1].rationale` and `.message`: 7.5 | same: R5's Rs 7.5L exists only in its rationale text |
| any row where the NPS lever changes | `negotiation.changed_levers[0]`: 124, 80, 2 | `changed_levers` is computed by `_diff_levers()`, deterministic, and it sits in the `ai_backed` negotiation section; the digits are "Section 124, formerly 80CCD2" |
| R1 + R5 fire, negotiation AI-backed, point restating the saving (at `7c08da4`) | `negotiation.points`: 49920 | the real saving is `negotiation.total_annual_saving`, a numeric leaf **inside** the `ai_backed` section, so it is excluded from grounding |

All rows reproduce in clean worktrees at both `7c08da4` and `02d05a8`, except
the last. At `02d05a8` that response's negotiation was not AI-backed, so it was
not inspected.

`output_boundary.py` already met this once, with `rule_id` "R1", and fixed it
by stripping identifier tokens. The comment there states the lesson: *"a section
is NOT uniformly model-authored"*. The identifier fix handled the one field that
showed up. It did not address the assumption itself.

### 1.2 Coincidental passes

In the R1 + R5 response, R5's message and rationale contain the citation digits
17, 1 and 2, and R1's contain 50. Whether each was flagged depended on unrelated
fields that happened to hold the same value:

| number in text | grounded by | at `7c08da4` | at `02d05a8` | relationship to the text |
|---|---|---|---|---|
| 1 | `old_regime_best.basic_pct`, `new_regime_best.basic_pct` (fractions such as 0.6, within ±1) | grounded | grounded | none |
| 2 | `metrics.rules_triggered` | grounded | grounded | none |
| 17 | `metrics.optimization_value_pct` | not equal: **17 flagged** | grounded | none |
| 50 | `metrics.ai_coverage_pct` | not equal: **50 flagged** | grounded | none: R1's 50 is a statutory floor, this 50 is AI coverage |

Whether a figure passes the boundary thus depends on an unrelated metric's
value in that particular response. With `02d05a8`'s numbers, a fabricated
"17 thousand rupees over" in R5's message would be grounded by an optimization
percentage. With `7c08da4`'s numbers, the legitimate citation digit 17 is
flagged. OUTPUT_BOUNDARY_DESIGN §3.4
removed `skip_below` so that small numbers would be checked. An absolute ±1
tolerance, matched against response-wide small-valued leaves, gives much of
that back.

### 1.3 What this means

The layer is **not live**: it runs only in tests, by design (§3.1 of its
design). No user sees its findings. But on real AI-backed output it is wrong
both ways at once: it reports legitimate text and passes fabricated text by
coincidence. Its tests are green because they never give it real AI-backed
input. The claim that it is a working second layer is not supported by what it
does on real output.

The original framing (citation digits, a hand-grounded year) describes two
symptoms of §1.1. Fixing only those would leave §1.1's rationale and lever
findings and all of §1.2.

## 2. Causes

1. **"Model-authored" is decided per section, but it varies per field.** Inside
   `compliance.flags[]` only `message` is model text. `rule_id`, `severity`
   and `rationale` are Python's. Inside `negotiation`, only `points` is model
   text; `changed_levers` and `total_annual_saving` are Python's.
2. **Deterministic strings are never grounding sources.** A figure stated
   only in rationale text, which is exactly what the inline guard grounds
   against, is invisible to the boundary.
3. **Grounding is response-wide, with absolute ±1.** Any small leaf anywhere
   grounds any small number anywhere.
4. **Citation digits count as figures.** This is the problem originally framed
   for this design, and one instance of cause 2.

## 3. Options

### 3.1 Which fields are model-authored

- **(a) A central list of field paths in `output_boundary.py`.** Rejected, for
  the reason OUTPUT_BOUNDARY_DESIGN §3.2 already gives: it is a second source of
  truth that drifts when a field is added.
- **(b) Each section declares its model-authored keys where it is built**, next
  to `ai_backed`: for example `"ai_fields": ["message"]` on a compliance flag,
  and `"ai_fields": ["points"]` on negotiation. It is self-declaring like
  `ai_backed` and kept next to the code that writes the field. **Cost: it
  changes the API payload shape.** The characterization baseline fixture changes
  (the concurrent D1 work is also changing that fixture), and the frontend
  receives a new key it ignores.
- **(c) Declare them in code, keyed by section, next to each builder in
  `ai_layer.py`**, without adding them to the payload. The payload is
  unchanged, but it is a list again. It lives beside the builder rather than in
  the checker, which reduces drift but doesn't remove it.

**Recommendation: (b).** The layer's whole premise (§3.2 of its design) is that
sections declare themselves. A field-level declaration is that premise applied
one level down, which is where the measurement shows it is needed.

### 3.2 What grounds model text

For each model-authored field, allow the figures of the **deterministic strings
in the same object** (a flag's `rationale`, negotiation's `changed_levers`),
taken through the inline guard's `_grounded_figures()` so citation digits are
excluded. Add the object's own numeric leaves, then the response-wide numeric
leaves.

Also apply the membership check (`_citations_unsupplied`) against those same
deterministic strings. This reuses the inline helpers, which is parsing, not
policy, the same argument OUTPUT_BOUNDARY_DESIGN §2.1 makes for
`_extract_numbers`.

### 3.3 Coincidental grounding

- **(d) Keep response-wide grounding, but match small values exactly** (values
  below 100 must be equal; ±1 applies only above). Closes the 0.6-grounds-1
  case. Does not close 17 ↔ `optimization_value_pct` if the values happen to
  be equal.
- **(e) Ground per object first:** a flag's message may use its own flag's
  rationale figures and the request's numbers, and response-wide leaves only for
  sections with no deterministic source of their own (the explanation). This
  closes the metrics cases in §1.2. It moves the boundary's policy closer to the
  inline guard's, which reduces the independence the second layer exists to
  provide. That trade-off is stated, not argued away.

**Recommendation: (d) and (e) together**, with the independence cost written
into `output_boundary.py`'s docstring next to the existing "where the
independence is real and where it is not" paragraph. A layer that grounds a
fabricated figure against an unrelated optimisation percentage offers
independence in name only.

### 3.4 Tests

Replace the hand-built payloads with real `_build_optimize_response()` output,
driven through a mocked client, one reply per prompt:

- legitimate rephrasings (R1's pinned wording, R5's citation, a lever-naming
  point) → **no findings**;
- each §1.2 coincidence as a fabricated figure (e.g. "17 thousand rupees over"
  in R5's message) → **a finding**, naming the path;
- the existing "inline guard disabled, boundary still catches it" test, kept
  as it is, but on real output;
- a data-driven test: every `ai_backed` section in real output declares
  `ai_fields`, so a new section cannot skip the declaration;
- `"metrics": {"basic_pct": 50, "year": 2025}` removed from the test payload.
  The year question stays decision 3 of `RATIONALE_GUARD_CITATION_DESIGN.md`:
  R1's text says 2025 and its record says 2019.

**Sabotage:** drop `ai_fields` handling (the rationale findings come back);
ground response-wide only (the 17 coincidence passes); match small values within
±1 again (the 0.6 → 1 case passes); drop the membership check at the boundary
(a fabricated section passes).

## 4. Decisions

**Decided by the user, 2026-09-16:** (b) and (d) + (e). Decision 3 follows the standing OUTPUT_BOUNDARY_DESIGN §5 recommendation: a finding fails the build once the tests run on real output.

1. **How fields declare authorship:** (b) payload `ai_fields` (recommended),
   (c) a code-side declaration, or (a) a central list. **Decided: (b).**
2. **Coincidental grounding:** (d) + (e) (recommended), (d) only, or leave it. **Decided: (d) + (e).**
3. **Does a finding fail the build?** Today it fails its own tests only. The
   recommendation stays as OUTPUT_BOUNDARY_DESIGN §5 has it: yes, once the
   tests run on real output.

## 5. Sequencing, if approved

1. This document.
2. **Tests first, knowingly red:** real-output tests that currently fail with
   the §1 findings. Committed red and named. This follows the R5 propagation's
   precedent for a knowingly red commit.
3. **Structural:** `ai_fields` declarations at each `ai_backed` builder
   (payload shape, plus fixture regeneration, coordinated with the concurrent D1
   work on the same fixture).
4. **Behavioural (boundary):** field-scoped inspection, per-object grounding
   with `_grounded_figures`, membership check, exact small-value matching. The
   real-output tests go green, and the sabotage runs are named.
5. **Documentation:** OUTPUT_BOUNDARY_DESIGN.md gets a correction note, and the
   gap row in `docs/PROJECT_STATUS.md` is updated.

## 6. What this does not settle

- **The inline guard's own ±1 tolerance** with `skip_below=0` at the rationale
  sites. It is per flag since step 3, so a response-wide coincidence like §1.2
  cannot happen there, but "49.5%" for a 50% floor still passes. Out of scope;
  noted.
- **The year** (decision 3 in the rationale-guard design).
- **Whether the boundary should ever run at runtime.** Unchanged: tests only.

## 7. Implementation record

Full suite with `python3 -B` and the cache cleared, in a clean worktree at each
commit, under the "request run" / "go" handshake. Every run: zero sleep/wake
events, `OVERLAP=0`, worktree clean after.

| step | commit | suite (vs parent, by test-ID diff) |
|---|---|---|
| 2, real-output tests, knowingly red | `bada9d4` | 588: +7; **exactly 11 failures**, all in `test_output_boundary`, each for a reason §1 names |
| 3, `ai_fields` declared (payload shape) | `8e47e5e` | 592: +4; **exactly 7 failures**; the declaration test went green. The concurrent session measured the same 7 independently |
| 4, per-object grounding, (d), membership | `866176e` | **594 OK**: +1 (`test_below_100_a_figure_must_match_exactly`) |

| sabotage on `866176e` | predicted to fail | failed |
|---|---|---|
| B1: +-1 at every size (undo d) | `test_below_100_a_figure_must_match_exactly` | exactly that |
| B2: no membership check | `test_a_fabricated_section_whose_digits_are_grounded_is_found` | exactly that |
| B3: ignore `ai_fields` | at least: the 4 legitimate-output tests, the "2" coincidence subtest and the fabricated-section test; the "1" subtest uncertain | those 6; the "1" subtest passed |
| B4: response-wide grounding only | at least: 3 legitimate-output tests and the "2" subtest | exactly those 4 |

**One thing the prediction had to leave open, stated rather than rounded:**
under B3 the old code path reported the fabricated "1 lakh" anyway, so that
subtest did not separate B3. B1 is the test that pins exact small-value
matching.

**Residual, by construction, not measured on live output:** negotiate's lever
text is "NPS enrollment (Section 124, formerly 80CCD2)". The unkeyworded
"80CCD2" is not a recognised reference, so `_grounded_figures` keeps its 80 and
2 as figures of the negotiation object, and a fabricated "2" in a point would
be grounded. It is the same shape as the `80ccd2_cap` text fixed in `5060498`.
The fix is the same: emit "(formerly Section 80CCD(2))". That is emitted text
pinned by `test_finos` and the characterization fixture, so it is left for a
decision.
