# Query guard: citation tokens are not figures — design

Resolves the defect recorded in `R5_CITATION_PROPAGATION_DESIGN.md` §4.4.1.
That section closed with *"Recorded as its own item, not folded in."* This is
that item.

## 1. The defect, re-measured on this branch

`answer_query()`'s explanatory path hands the model
`grounding["applicable_sections"]`, a list of strings, and then guards the reply
with `_numbers_ungrounded(candidate, allowed)`. `allowed` is built only from the
*numeric* values in `grounding`, and the default `skip_below=100` exempts
nothing above 99. So every section designator of 100 or more that the model
repeats counts as an ungrounded figure.

Guard level, `allowed = {2000000, 600000, 145000}`:

| candidate | extracted | `guard_triggered` |
|---|---|---|
| "…under Section 124." | 124 | **True** |
| "…under Section 392." | 392 | **True** |
| "…under Section 392 (formerly Section 192)." | 392, 192 | **True** |
| "…under Section 124 (formerly Section 80CCD(2))." | 124, 80, 2 | **True** |
| "…Section 11, read with Schedule III, Table Sl. No. 11 (formerly Section 10(13A))." | 11, 11, 10, 13 | False, but only because every token is under 100 |
| "Your total tax is Rs 145000 under the new regime." | 145000 | False |

End to end through `answer_query()`, with the client mocked and everything else
real (CTC 18L, rent 4L, metro, NPS):

| model reply | `ai_backed` | `guard_triggered` |
|---|---|---|
| "…deducted under Section 392 (formerly Section 192)." | **False** | **True** |
| "…deductible under Section 124 (formerly Section 80CCD(2))." | **False** | **True** |
| "…your total tax is 88140." | True | False |

**The first row is the system prompt's own example wording, quoted exactly.**
`QUERY_EXPLAIN_SYSTEM_PROMPT` tells the model to cite *"using its exact wording
(e.g. "Section 392 (formerly Section 192))"*. A model that follows that
instruction exactly gets rejected. Section 392 goes into `applicable_sections`
unconditionally, so every explanatory answer that cites anything above
Section 99 falls back.

It fails closed, so no wrong figure reaches a user. The cost is quality: the
user quietly gets the thin fallback text.

## 2. The three candidate mechanisms, measured against each other

All three were prototyped against the real `_numbers_ungrounded`, with the same
allow-set and the three strings `answer_query` actually supplies. "Pass" means
the guard lets the reply through.

| candidate | today | (a) strip any citation pattern | (b) whitelist the designators as values | **(c) strip only supplied citation references** |
|---|---|---|---|---|
| "…under Section 392." | reject | pass | pass | **pass** |
| "…Section 392 (formerly Section 192)." | reject | pass | pass | **pass** |
| "…Section 124 (formerly Section 80CCD(2))." | reject | pass | pass | **pass** |
| "section 124 applies." (case) | reject | pass | pass | **pass** |
| "Rs 145000 under the new regime." (grounded) | pass | pass | pass | **pass** |
| "…falls under **Section 394**." (not supplied) | reject | **pass** | reject | **reject** |
| "you save **Rs 392** a year." (a figure) | reject | reject | **pass** | **reject** |
| "Rs 1,24,000 is deductible under Section 124." | reject | reject | reject | **reject** (124000 still checked) |
| "Section 392,000 applies." | reject | **pass**¹ | reject | **reject** |
| "Subsection 392 applies." | reject | reject | **pass** | **reject** |
| "Sections 392 and 192 apply." (plural) | reject | reject | **pass** | reject (see §4) |
| "…Income-tax Act, **2025**." | reject | reject | reject | reject (see §4) |

¹ A pattern with no right-hand boundary. Adding one fixes this row. It does
not fix the row above.

### 2.1 Why not (a)

(a) decides a number is a citation because a keyword **the model wrote** comes
before it. The guard exists so that nothing the model writes can exempt itself.
The measured result: a citation that was never supplied, "Section 394", goes
from rejected to passing. Today, rejecting an invented section number of 100 or
more is the only thing that backs up the prompt's rule to "not cite any section
not present in that list". That backing is accidental, but it is real, and (a)
removes it.

### 2.2 Why not (b)

(b) is the change the task ruled out, only narrower. It still whitelists a
**value**, not a **position**. "Rs 392" is a rupee figure, and under (b) it
passes. Tying the exemption to what was supplied is right. Tying it to a
value is not.

### 2.3 Chosen: (c), which is (b)'s source restriction plus (a)'s positional test

A token is exempt only when both of these hold:

1. **It sits in citation position.** It matches the reference grammar
   (`Section|Schedule|Rule|Form|Sl. No.` followed by a designator such as `392`,
   `80CCD(2)`, `10(13A)` or `III`).
2. **That exact reference was supplied.** The pair (keyword, designator) is one
   of the references parsed out of the `applicable_sections` strings that
   `answer_query` actually sent.

Matching tokens are replaced with a space **before** number extraction.
Everything that remains is checked exactly as it is today, with the same
allow-set, the same `skip_below` and the same tolerance.

It is the same kind of correction as `output_boundary._IDENTIFIER_TOKEN`: it
changes what the extractor is given, not what the checker allows. It is
stricter than that precedent in one respect. `_IDENTIFIER_TOKEN` strips every
identifier-shaped token, while this strips only the ones on a list the
deterministic code wrote.

**The keyword list cannot widen the exemption.** The same grammar parses both
the supplied strings and the candidate, and a candidate reference is stripped
only if it matched a supplied one. Adding a keyword just lets the parser
*recognise* more supplied references. With nothing supplied, nothing is
stripped.

## 3. Design decisions

### 3.1 One grammar, used on both sides

References are parsed out of the supplied strings and out of the candidate with
the **same compiled pattern**. Two parsers would disagree about
"80CCD(2)" versus "80CCD", and that disagreement would be a bug. This is the
same *parsing, not policy* argument as `OUTPUT_BOUNDARY_DESIGN.md` §2.1.

### 3.2 Matching rules, each of which fails closed

- **Keyword** is case-insensitive, and whitespace inside it is ignored
  ("section 124" and "Sl.No. 11" both match). **Designator** is compared
  upper-cased. Neither changes which citation is meant.
- **Right boundary:** the designator cannot be followed by a letter, a digit,
  `(`, or `[.,]digit`. So "Section 392,000" and "Section 392.5" are not
  references and their numbers are checked. A supplied "Section 80CCD" does not
  exempt "Section 80CCD(2)". The longer reference is not stripped at all, so both 80 and 2 are checked.
- **Left boundary:** `\b` before the keyword, so "Subsection 392" is not a
  reference.
- **Only the reference is removed**, never the text around it. So
  "Rs 1,24,000 … Section 124" still checks 124000.

### 3.3 The capability lives in `_numbers_ungrounded`; the wiring stays at the call site

`_numbers_ungrounded(text, allowed_numbers, skip_below=100, citations=())`.
When `citations` is empty, the function takes exactly the code path it takes
today, with no stripping call at all. So the other call sites are unchanged by
construction, not just by testing. Only the one call site that supplies
citations passes them.

**Rejected: stripping inside `answer_query` before the call.** The guard would
then depend on every future citing call site remembering to pre-process its
input. That is failure mode 3 of `OUTPUT_BOUNDARY_DESIGN.md` §2, moved one step
earlier.

### 3.4 The exemption comes from the same list the model was given

`answer_query` passes `grounding["applicable_sections"]`, the same object that
is serialised into the prompt, not a second copy. The exemption can't drift
from what the model saw. If the recompute fails and the list is `[]`, nothing
is exempt.

## 4. Known residual rejections, deliberately kept

- **Plural or abbreviated forms**: "Sections 392 and 192", "s. 392",
  "Sec. 392". They don't match the grammar, so they are still rejected. The
  prompt asks for exact wording, and these forms are not it. Widening the
  grammar to cover them is safe by §2.3's argument, but nothing measured shows
  it is needed.
- **The Act's year**: "Income-tax Act, 2025". 2025 is not a section
  designator, and treating four-digit years as exempt would let a
  ₹2,025 figure through. `applicable_sections` does not contain the year, so
  the prompt does not invite it. If real traffic shows models add it, the fix
  is to supply the year as a reference (for example "Income-tax Act, 2025"
  parsed as its own keyword), **not** a year exemption. Out of scope here.

## 5. Proof requirement

Both directions, plus sabotage:

- supplied references, cited exactly or in part → not rejected, at the guard
  **and** end to end (`ai_backed=True`);
- an unsupplied section, a bare number equal to a supplied designator, a
  designator fused into a larger number, and a figure next to a supplied
  citation → **still rejected**;
- `citations=()` → "Section 392" is still rejected. This pins the claim that
  the other call sites are unchanged;
- **sabotage 1:** make the stripping ignore the supplied set (strip any
  reference, which is option (a)). The "unsupplied section is still rejected"
  tests must fail.
- **sabotage 2:** unwire the call site (stop passing `citations`). The
  end-to-end `ai_backed=True` tests must fail.

## 6. Sequencing

Separate commits, in order:

1. **This document.**
2. **Structural:** add the reference grammar and the `citations` parameter,
   defaulting to empty. No call site passes it, so product behaviour is
   byte-identical. Guard-level unit tests. Expected suite delta: only the new
   tests, each named.
3. **Behavioural:** `answer_query` passes `applicable_sections`. End-to-end
   tests. Expected delta: only the new tests, each named. No existing test
   should change state, because none covers `applicable_sections` (§4.4 of the
   R5 design). If one does change, that is a finding.

Full suite after every step against the 469 baseline, with `python3 -B` and
`~/Library/Caches/com.apple.python` cleared.

## 7. What this does not settle

- **Citation correctness.** This makes the guard stop penalising supplied
  citations. It does not check that the model cited the *right* one for the
  question, and it does not check that the supplied strings are legally correct
  (R5 §4.4: nothing tests that).
- **Unsupplied citations below 100.** "Section 80C" or "Section 16" invented by
  the model passes today and still passes, because `skip_below=100` exempts
  those numbers. Enforcing "cite only listed sections" is a separate check on
  references, not on figures, and it would reuse this grammar.
- **The output-boundary layer does not see `/api/query`.** `test_output_boundary`
  drives `pipeline_baseline.json` and `flag_compliance()`, and nothing else
  (checked: no `answer_query` call, and neither `"answer"` nor
  `applicable_sections` in the fixture). `answer_query`'s response carries
  `ai_backed` but is not in that corpus. If it is added later, the boundary
  check will hit the same false positive, and the response it inspects does not
  include `applicable_sections` to exempt against. Recorded, not fixed.

## 8. Proof, as run

Every run was the full suite with `python3 -B` and the bytecode cache cleared.
Each run was held until no other suite was running against the shared
Postgres; overlap was checked and none occurred. Failures were predicted before
each sabotage run. Every sabotaged file was restored with `git checkout` and
verified against the committed shasum.

| run | result | delta vs 469 |
|---|---|---|
| baseline (worktree off `3046e62`) | 469 OK | — |
| after step 1 (this document) | 469 OK | 0 |
| after step 2 (structural) | 479 OK | +10, all in `test_query_guard_citations.py` |
| after step 3 (behavioural) | 485 OK | +16, all in `test_query_guard_citations.py` |

§5 listed two sabotages. Five were run, because the tests make five separate
claims and each claim should have a run that breaks only that claim:

| sabotage | predicted to fail | failed |
|---|---|---|
| A. strip every reference, ignoring the supplied set (option (a)) | `test_an_unsupplied_section_is_still_rejected`, `test_a_shorter_supplied_reference_does_not_exempt_a_longer_one` | exactly those 2 |
| B. delete the `(?![.,]\d)` right boundary | `test_a_designator_fused_into_a_larger_number_is_not_a_reference`, subtests `392,000` and `392.5` only | exactly those 2 subtests; `Subsection 392` still passed |
| C. unwire the call site (no `citations=`) | `test_the_prompts_own_example_wording_is_served_not_replaced`, `test_a_conditionally_supplied_citation_is_served_when_it_applies` | exactly those 2 |
| D. exempt against a fixed list of all three citations instead of this call's list | `test_the_same_citation_falls_back_when_it_was_not_supplied_for_this_user` | exactly that 1 |
| E. also accept `applicable_sections` from the request's `context` | `test_citations_in_the_request_context_cannot_buy_an_exemption` | exactly that 1 |

No existing test changed state in any run, sabotaged or not. That is expected,
since none of them covers this path.
