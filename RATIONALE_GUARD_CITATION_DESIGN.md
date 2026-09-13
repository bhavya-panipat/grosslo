# Rationale guard: citation digits are not grounding — design

Resolves `R5_CITATION_PROPAGATION_DESIGN.md` §4.4.2. That section described a
number that looks like a figure but is part of a citation, **leaking into**
`allowed`. `QUERY_GUARD_CITATION_DESIGN.md` fixed the other half (§4.4.1, a
citation's number wrongly **rejected** in `answer_query`). It was designed
without §4.4.2 in view and left §4.4.2 open. `1dc895c` records that.

**This document is scoped by inventory, not by the section it resolves.** The
last fix went wrong because its scope came from the one call site a finding
named. So this design starts by listing every call site that builds `allowed`
from text, and every string that reaches one. The list is longer than §4.4.2,
and §2 says which findings this design takes on and which it doesn't.

All measurements are on `1dc895c` unless stated. "Prototype" means the design
below, applied in a throwaway worktree that was never committed.

---

## 1. The defect, end to end

The model client is mocked; everything else is real code.

| call site | model's rephrasing | `1dc895c` | prototype |
|---|---|---|---|
| `flag_compliance`, R5 fires | "The excess over Rs 7.5L is a taxable perquisite under Section 17(1)(h)." (correct) | served | served |
| `flag_compliance`, R5 fires | "Your contributions exceed the limit by **1 lakh**." (fabricated) | **served** | rejected |
| `evaluate_band_guardrail`, `80ccd2_cap` fails | "…exceeds the Section 124 cap (formerly Section 80CCD(2)) of 14% of basic." (correct) | served | served |
| `evaluate_band_guardrail`, `80ccd2_cap` fails | "Employer NPS exceeds the cap of **2%** of basic." (fabricated; real is 14%) | **served** | rejected |
| `evaluate_band_guardrail`, `80ccd2_cap` fails | "Employer NPS is **Rs 124** over the cap." (fabricated) | **served** | rejected |

"Served" means `ai_backed=True`, and the text becomes `flag["message"]` or
`check["message"]`. `orchestration.py` L99–101 quotes that text verbatim as the
stated reason for a routing decision.

**This is the direction that matters.** §4.4.1 failed closed: answers got worse,
but no wrong number reached anyone. §4.4.2 fails **open**: a fabricated figure
reaches a user and a routing reason.

## 2. Inventory

### 2.1 Every call site that builds `allowed` from text

| call site | `allowed` built from | `skip_below` | named in §4.4.2 |
|---|---|---|---|
| `flag_compliance` L592–594 | `_extract_numbers(rationale)`, union over triggered flags | 0 | yes |
| `evaluate_band_guardrail` L734–736 | `_extract_numbers(rationale)`, union over failing checks | 0 | **no** |

No other call site builds `allowed` from text. `explain_result`, `negotiate` and
both `answer_query` paths build it from numeric values.

### 2.2 Every rationale that reaches those two sites, and what it adds

For each rationale: the numbers it adds to `allowed` today, the citation
references the existing `_CITATION_REFERENCE` grammar recognises in it, and
what is left after stripping those references.

| source | adds to `allowed` today | recognised references | left after stripping | citation digits leaking |
|---|---|---|---|---|
| R1 | 50, **2025**, 50 | none | 50, 2025, 50 | **2025** ("Code on Wages 2025") |
| R2 | 6 | none | 6 | none |
| R3 | none | none | none | none |
| R4 | 10 | none | 10 | none |
| R5 | 7.5, **17, 1, 17, 2** | Section 17(1)(h), Section 17(2)(vii) | 7.5 | 17, 1, 2 |
| R6 | none | none | none | none |
| R7, R8 (candidate; not active) | none | none | none | none |
| guardrail `band_cost_neutrality` | CTC and band limits | none | same | none |
| guardrail `epfo_ceiling` | total, 750000, **17, 1, 17, 2** | Section 17(1)(h), Section 17(2)(vii) | total, 750000 | 17, 1, 2 |
| guardrail `80ccd2_cap` | NPS, **124, 80, 2**, 14, cap | Section 124 only | NPS, **80, 2**, 14, cap | 124, 80, 2 |

### 2.3 What the inventory found beyond §4.4.2

1. **A second call site.** `evaluate_band_guardrail` has the same pattern, and
   its `epfo_ceiling` text carries the same citation as R5. §4.4.3 already
   noted that nothing covers that rationale. *In scope.*
2. **A citation no keyword-anchored grammar can recognise.** `80ccd2_cap` says
   "Section 124 cap **(formerly 80CCD(2))**", with no "Section" keyword. Even
   after stripping, 80 and 2 stay in `allowed`, and "cap of 2% of basic" still
   passes. Every other citation in the codebase uses
   "(formerly Section …)". *In scope* (§4.2).
3. **An Act's year.** R1's "Code on Wages 2025" puts 2025 into `allowed`. The
   repository also **contradicts itself** here: R1's own `instrument` field is
   `Code on Wages, 2019 (Act 29 of 2019)`, and its `provision` says *"In force
   21 Nov 2025"*. That is a legal-claim question, not a guard question.
   *The guard half is open decision 1; the claim half is out of scope* (§7).
4. **The union across flags, which is a separate defect.** `allowed` is the union
   of every triggered rationale. A real figure from one flag therefore grounds a
   fabricated figure in another, with no citation involved:

   | fired | rephrasing | `1dc895c` | citation fix only | + per-line grounding |
   |---|---|---|---|---|
   | R1 + R5 | "Basic salary is below **17%** of CTC." | served | rejected | rejected |
   | R1 + R5 | "Basic salary is below **7.5%** of CTC." | served | **served** | rejected |
   | R1 + R4 | "LTA exceeds **50%** of CTC." (real: 10%) | served | **served** | rejected |

   **And it hides reordered lines.** Lines map to flags by index. With R1 + R4
   firing and the model returning the two lines in swapped order, `1dc895c`
   serves both, measured:

   ```
   R1 -> LTA exceeds 10% of CTC.
   R4 -> Basic salary is below 50% of CTC.
   ```

   `orchestration.py` would then give *"R1 (High) — LTA exceeds 10% of CTC."* as
   the reason for a High-severity routing decision. Grounding each line against
   its own rationale rejects this, because 10 is not in R1's figures. *Open
   decision 2.*
5. **A third §4.4.1-shaped instance.** `negotiate()` is wired in
   (`pipeline.py` L152). It hands the model the lever text
   `"NPS enrollment (Section 124, formerly 80CCD2)"`, and its prompt says to
   reference levers *"by name"*. Its guard uses the default `skip_below=100`, so
   a reply naming that lever trips on 124 and falls back. Passing
   `citations=changed_levers` fixes it (measured: True → False). Fails closed.
   *Open decision 3.*

### 2.4 The suite cannot see any of this

Both prototype variants in §5 ran the full suite at **485 OK**: the same count
and the same result as `1dc895c`. So no existing test covers the leak, the
second call site, the cross-flag case or the reordered lines. Nothing would
notice the fix if it were reverted. §6 is not optional.

## 3. Why the §4.4.1 mechanism alone does not close this

`citations=` changes the **candidate** side. It stops a supplied reference from
counting as a figure in the model's reply. Here the defect is on the
**`allowed`** side: the allowed set is built by `_extract_numbers` from the same
text that contains the citation. Passing `citations=` to these two sites
without changing how `allowed` is built changes nothing, because every
citation digit is already in `allowed`.

## 4. Options, measured

### 4.1 Rejected: strip citations from the `allowed` side only

This keeps citation digits out of `allowed` but still checks them in the reply.
Measured: the correct R5 rephrasing *"…taxable under Section 17(1)(h)"* is
**rejected**. It trades a fail-open defect for a fail-closed one on every
correct citation. That is §4.4.1 recreated at two more call sites.

### 4.2 Rejected: add "formerly" to the reference grammar

This would recognise "(formerly 80CCD(2))" as it stands. Measured: it also
parses *"14% of basic (formerly **10**% under the old rule)"* as the reference
`formerly 10`, and would exempt a real figure. Every existing keyword names
a kind of legal provision; "formerly" doesn't, and can come before anything.

**Chosen instead: correct the text** to "(formerly Section 80CCD(2))", the form
`applicable_sections`, R5 and the `epfo_ceiling` rationale already use. That
changes emitted text, so it gets its own commit (§8). Checked: no fixture, CA
packet or review queue contains that string. `FINOS_PROJECT_BRIEF.md` L157 and
L327 mention 80CCD(2) in prose but don't quote this rationale.

### 4.3 Rejected for now: take citations out of rationale text entirely

`Rule` already has `provision` and `instrument` fields. The rationale could hold
only figures, with citations shown from those fields. That is the root fix, and
it is recorded as the long-term direction. It is rejected **here** because it
rewrites user-facing and reviewer-facing text, regenerates both reviewer
artefacts, and lands in the middle of the R5 propagation, which is changing
that same text right now. The guard does not need it.

### 4.4 Rejected: declare each rule's allowed figures explicitly

For example `Rule.figures = {7.5}`. That is a second source of truth next to
the rationale, and it would drift the first time someone edits a rationale.
That is the failure this repository keeps finding.

### 4.5 Chosen: strip on both sides, using the rationales as the supplied citations

For the rationales that reach a call site:

```
allowed   = figures of each rationale, with the references in those rationales removed
candidate = checked with citations=those same rationales
```

It needs no new list: the rationale is already both the source of figures and
the source of citations. It reuses `_strip_supplied_citations` and
`_CITATION_REFERENCE` unchanged. Instrument years (decision 1) extend what that
function recognises.

**It can never accept a line that `1dc895c` rejects.** Proof:
- A token is stripped from the candidate only if it is a reference found in a
  supplied rationale. Every digit in such a reference was extracted from that
  rationale, so it is already in today's `allowed`.
- Every number that is *not* stripped is checked against the new `allowed`,
  which is a subset of today's.
- So every accepted line was also accepted on `1dc895c`.

The change can only remove false acceptances. Any new rejection is a
fail-closed quality cost, and §5 lists the ones that were measured.

For a citation form the grammar does not recognise, the digits stay in both
`allowed` and the candidate. That is exactly today's behaviour, so an
unrecognised form means a leak that isn't closed, never a new false rejection.
§6 adds a test that makes such forms visible instead of silent.

## 5. Measured costs and residuals

Prototype A is the citation fix with the text correction and instrument years,
keeping the union. Prototype B is A plus per-line grounding. Both: **485 OK**.

| case | `1dc895c` | A | B |
|---|---|---|---|
| R5: "1 lakh", "2 lakh", "17 thousand rupees" (fabricated) | served | rejected | rejected |
| R1: "Rs 2,025 short of the floor" (fabricated) | served | rejected | rejected |
| R1: *"…the 50% floor the Code on Wages 2025 requires"* (pinned as legitimate by `test_finos` and `test_output_boundary`) | served | served | served |
| R1: "below 35% of CTC" (existing test) | rejected | rejected | rejected |
| cross-flag and reordered lines (§2.3 item 4) | served | **served** | rejected |
| `80ccd2_cap`: model drops the keyword, "(formerly 80CCD(2))", after the text fix | served | **rejected** | **rejected** |

**Residual costs, all fail-closed:**

- **A citation copied without its keyword** is rejected, as in the last row.
  The model is given the corrected text, so copying it exactly passes.
- **The check id `80ccd2_cap` is sent to the model** inside the JSON. If the
  model repeats "80ccd2", 80 and 2 are checked and the line is rejected. Today
  that passes. Not measured on live output.
- **Reordering is caught only when figures differ.** Two figure-free rules (R3
  and R6) swapped still go through under B.
- The residuals from `QUERY_GUARD_CITATION_DESIGN.md` §4 still apply: plural
  and abbreviated forms of a reference are not recognised.

## 6. Tests required

Both directions for every case, per the project's standing pattern:

1. **One test per leak** in §2.2: a fabricated figure equal to a citation digit
   is rejected, and the correct citation next to it is served. Covers R5,
   `epfo_ceiling`, `80ccd2_cap` and R1's year. The two guardrail rationales get
   their first coverage of any kind (§4.4.3).
2. **Pin the corrected text:** `80ccd2_cap`'s rationale contains
   "(formerly Section 80CCD(2))".
3. **A data-driven coverage test** over every active rule rationale and every
   rendered guardrail rationale. No parenthesised designator (the
   `80CCD(2)` / `17(1)(h)` shape) may sit outside a recognised reference. This
   is the test that would have caught §2.3 item 2. Because it walks
   `active_rules()`, it covers a new rule automatically, the same way
   `ai_backed` works for the boundary check.
4. **The subset property of §4.5**, asserted over the same inputs: the new
   `allowed` is a subset of the old.
5. **If decision 2 is yes:** the cross-flag case and the reordered-lines case,
   each rejected.
6. **If decision 3 is yes:** `negotiate` serves a reply that names the NPS lever.
7. **The existing pinned legitimate rephrasing** (*"Code on Wages 2025
   requires"*) must stay green without being edited.

**Sabotage, one run per claim, predicted before running:**

| sabotage | should fail |
|---|---|
| build `allowed` from unstripped rationales | tests in item 1 (fabricated figures) |
| drop `citations=` at either call site | tests in item 1 (correct citations), at that call site |
| revert the `80ccd2_cap` text | items 2 and 3 |
| go back to the union | item 5 |
| unwire `negotiate` | item 6 |

## 7. Open decisions

1. **Instrument years:** strip "Code on Wages 2025"-style references too?
   **Recommendation: yes.** Instrument names would come from the rules'
   `instrument` fields (currently `Code on Wages`, `Income-tax Act`), not a
   hand-written list. Prototype A does this and stays at 485 OK. Leaving it out
   would make this fix knowingly partial, which is the mistake `1dc895c` had to
   record. **This is not an endorsement of the year.** The R1 rationale's 2025
   against its `instrument` field's 2019 goes to the legal-claim inventory and
   the CA packet, not here.
2. **Per-line grounding:** include it in this series? **Recommendation: yes, as
   its own behavioural commit after the citation fix.** It is a different cause
   (real figures, not citations) in the same two loops. Its strongest
   justification is the reordered-lines case, which is a correctness defect in
   routing reasons, not just a looser guard. Prototype B passes the suite.
3. **`negotiate`:** include the one-line `citations=changed_levers` in this
   series? **Recommendation: yes, as its own commit.** It is the §4.4.1 defect
   again, found by this inventory. Leaving a known instance for a third pass is
   how the last one happened.

## 8. Sequencing

Separate commits, in order. The baseline is re-measured when implementation
starts: `485` now, and the concurrent R5 step 6 may change it.

1. **This document.**
2. **Structural:** a `_grounded_figures(rationales)` helper, and instrument-year
   references in `_strip_supplied_citations` (decision 1). No call site changes.
   `answer_query` is unaffected because its supplied list contains no instrument
   names, so the stripping is a no-op there; a test pins that. Unit tests for
   both.
3. **Behavioural, emitted text:** `80ccd2_cap` → "(formerly Section 80CCD(2))",
   plus tests 2 and 3.
4. **Behavioural:** both call sites build `allowed` with `_grounded_figures` and
   pass `citations=`. Tests 1, 4 and 7.
5. **Behavioural** (decision 2): per-line grounding. Test 5.
6. **Behavioural** (decision 3): `negotiate` passes `citations=`. Test 6.
7. **Documentation:** a back-pointer in R5 §4.4.2. **Written only after the
   concurrent step-6 commit lands**, as agreed with that session, since both
   write that file.

Full suite after every step, deltas named test by test, `python3 -B` with the
cache cleared. Suite runs happen in a worktree, and each one is announced to the
concurrent session first because the Postgres database is shared.

## 9. What this does not settle

- **The R1 year conflict** (§2.3 item 3). A citation-correctness question.
- **The output-boundary layer has the same shared-namespace problem.**
  `output_boundary.figures()` strips identifier tokens, not references.
  `test_a_legitimate_rephrasing_passes_both_layers` passes only because its
  payload adds `"metrics": {"year": 2025}`, which grounds the citation's year by
  hand. That is made-up grounding inside a test of the grounding checker.
  Recorded, not fixed.
- **Citations inside rationale text** (§4.3): the root fix, deferred.
- **Reordering figure-free flags** (§5): still undetected.
