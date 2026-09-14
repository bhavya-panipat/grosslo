# Rationale guard: citation digits are not grounding — design

Resolves `R5_CITATION_PROPAGATION_DESIGN.md` §4.4.2. That section described a
number that looks like a figure but is part of a citation, **leaking into**
`allowed`. `QUERY_GUARD_CITATION_DESIGN.md` fixed the other half (§4.4.1, a
citation's number wrongly **rejected** in `answer_query`). It was designed
without §4.4.2 in view and left §4.4.2 open. `1dc895c` records that.

**This document is scoped by inventory, not by the section it resolves.** The
last fix went wrong because its scope came from the one call site a finding
named. So this design starts by listing every call site that builds `allowed`
from text, and every string that reaches one.

**Revision 2 (2026-09-14), after review of `54e139f`.** The first version had
three faults, all corrected here:

1. **It filed the cross-flag defect under the wrong severity.** It called it "a
   separate defect" and put it as open decision 2, next to a quality issue. It
   is the failure the numeric guard exists to prevent. §1.1 now says so.
2. **It never ran the test that separates a safe citation exemption from an
   unsafe one:** a fabricated section number that was never supplied. Its
   prototype table had no such case. This revision runs it (§5.1), and that run
   found a gap no variant of the first design closed.
3. **Its year mechanism was not the one described as safe in review.** It took
   the year from the rationale text, not from the structured record. §4.6
   measures three mechanisms.

Measurements are on `1dc895c` unless stated. Revision-2 measurements are on
`0e57895`, which has the same `ai_layer.py`. "Prototype" means the design
applied in a throwaway worktree that was never committed. The patch is kept
out of the repository.

---

## 1. The defects, end to end

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

### 1.1 Severity: the defects here do not share a category

§4.4.1 was accepted as a quality defect **because it fails closed**: a genuine
citation is wrongly rejected, the user gets the fallback, and nothing false
reaches anyone. Most of what this inventory found fails **open**, which is a
different kind of problem. Ranked:

| # | defect | direction | what reaches a user | category |
|---|---|---|---|---|
| 1 | **Cross-flag grounding pool.** `allowed` is the union over every triggered flag, so flag A's line is checked against flag B's figures. | **open** | A **fabricated** figure in flag A that happens to equal a real figure of flag B. Measured: R1 + R4, *"LTA exceeds **50%** of CTC"* (real 10%), served. | **Guard failure.** No figure may escape without a deterministic source, and this one has none. It is the guard's core failure, reopened by the check's **scope**, not by a missing check. |
| 2 | **Swapped lines**, the same pool seen differently. Lines map to flags by index. | **open** | Real figures attached to the **wrong flag**. Measured: R1 → *"LTA exceeds 10% of CTC"*, served and quoted as the reason for a High-severity routing. | **Guard failure** (misattribution). Every number is real; the claim it is attached to is false. |
| 3 | **Citation digits in `allowed`** (§4.4.2), at `flag_compliance` and `evaluate_band_guardrail`. | **open** | A fabricated figure equal to a citation digit: *"1 lakh"*, *"2% of basic"*, *"Rs 124"*. | **Guard failure.** |
| 4 | **Fabricated citation whose digits equal a real figure of the same flag.** | **open** (and pre-existing) | A section never supplied: *"Section 50"* in R1's line, *"Section 14"* in the NPS cap line. Served by every figure-based variant, including `1dc895c` (§5.1). | **Citation fabrication.** A figure check cannot see it by construction (§4.7). |
| 5 | `negotiate` lever citation (§2.3 item 5). | closed | The fallback instead of a correct answer. | Quality: §4.4.1 again. |
| — | §4.4.1 itself, in `answer_query` | closed | fixed at `f6a3394` | Quality. |

**Numbers 1 and 2 are not a wider version of §4.4.1, and this document's
first version was wrong to present them that way.** So was the pointer
`0e57895` added to R5 §4.4.2, which folded them into "the leak is wider than
`flag_compliance`". The correction to that pointer is sequenced in §8.

**Per-line scoping (§4.5) closes 1 and 2 on its own, whatever happens with
citation stripping.** Once each line is checked only against its own flag's
rationale, flag A cannot borrow flag B's figures. Measured in §5.1: both are
rejected under every per-line variant and served under every union variant.
That is why it goes first in §8.

## 2. Inventory

### 2.1 Every call site that builds `allowed` from text

| call site | `allowed` built from | `skip_below` | named in §4.4.2 |
|---|---|---|---|
| `flag_compliance` L592–594 | `_extract_numbers(rationale)`, union over triggered flags | 0 | yes |
| `evaluate_band_guardrail` L734–736 | `_extract_numbers(rationale)`, union over failing checks | 0 | **no** |

No other call site builds `allowed` from text. `explain_result`, `negotiate` and
both `answer_query` paths build it from numeric values (grep of every
`allowed`/`allowed_numbers` construction in `ai_layer.py`).

**Call sites that hand the model citation strings** are a different list, and
decision 4 concerns it: `answer_query` (`applicable_sections`), `negotiate`
(`changed_levers`), and the two rationale sites above.

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
   noted that nothing covers that rationale.
2. **A citation no keyword-anchored grammar can recognise.** `80ccd2_cap` says
   "Section 124 cap **(formerly 80CCD(2))**", with no "Section" keyword. Every
   other citation in the codebase uses "(formerly Section …)". See §4.2.
3. **An Act's year.** R1's "Code on Wages 2025" puts 2025 into `allowed`. R1's
   own `instrument` field says **2019**. That conflict is already an open
   question for the CA: `docs/CA_REVIEW_PACKET.md` L100, deliberately left in
   the emitted text for the CA to rule on. See §4.6.
4. **The cross-flag pool and swapped lines.** Severity 1 and 2 in §1.1.
5. **A third §4.4.1-shaped instance.** `negotiate()` is wired in
   (`pipeline.py` L152). It hands the model the lever text
   `"NPS enrollment (Section 124, formerly 80CCD2)"`, and its prompt says to
   reference levers *"by name"*. Measured: a reply naming that lever is rejected
   at `1dc895c`, and served once `citations=changed_levers` is passed.

### 2.4 The suite cannot see any of this

Three prototype runs of the full suite have now been green: two variants at
`1dc895c` (485 OK) and the revision-2 combination at `0e57895` (491 OK, §5.3).
No existing test covers the leak, the second call site, the cross-flag pool,
swapped lines, or fabricated citations. Nothing would notice any fix here being
reverted. §6 is not optional.

## 3. Why the §4.4.1 mechanism alone does not close this

`citations=` changes the **candidate** side. It stops a supplied reference from
counting as a figure in the model's reply. Here the defect is on the
**`allowed`** side: the allowed set is built by `_extract_numbers` from the same
text that contains the citation. Passing `citations=` without changing how
`allowed` is built changes nothing, because every citation digit is already in
`allowed`.

## 4. Options and mechanism

### 4.1 Rejected: strip citations from the `allowed` side only

Measured: the correct R5 rephrasing *"…taxable under Section 17(1)(h)"* is
**rejected**. That is §4.4.1 recreated at two more call sites.

### 4.2 Rejected: add "formerly" to the reference grammar

Measured: it parses *"14% of basic (formerly **10**% under the old rule)"* as
the reference `formerly 10`, and would exempt a real figure. **Chosen instead:
correct the text** to "(formerly Section 80CCD(2))". That changes emitted text,
so it gets its own commit. Checked: no fixture, CA packet or review queue
contains the old string.

### 4.3 Rejected for now: take citations out of rationale text entirely

`Rule.provision` and `Rule.instrument` already exist. Rationales could hold only
figures, with citations shown from those fields. That is the root fix, recorded
as the long-term direction. It is rejected here because it rewrites
user-facing and reviewer-facing text that is under CA review (§2.3 item 3). The
guard does not need it.

### 4.4 Rejected: declare each rule's allowed figures explicitly

A second source of truth next to the rationale, which would drift on the first
edit.

### 4.5 Chosen: per-flag scope; strip only references that flag supplied

**Which of the two readings this is.** Review drew the line between
**(a)** stripping anything citation-shaped, unconditionally, which would exempt
a hallucinated "Section 999", and **(b)** exempting only citations present in
the real grounding for that flag. **This is (b).** It was not (a) in the first
version either, but the first version was (b) with a batch-wide scope, and
§5.1 shows what that let through.

For each line, and its flag only:

```
allowed(line)   = figures of that flag's rationale, with that rationale's own references removed
candidate(line) = checked with citations=[that flag's rationale]
```

A reference in the reply is removed before figure extraction **only if** it is
in citation position (`Section|Schedule|Rule|Form|Sl. No.` plus a designator)
**and** the same (keyword, designator) pair occurs in **this flag's** rationale.
A reference that was never supplied is not removed, and its digits are checked
as figures.

**Two precisions about "grounding", so this is not read as more than it is:**

1. **For these call sites, the grounding is the flag's rationale string, not a
   structured field.** The rationale is deterministic: `compliance_rules.py` for
   rules, f-strings in `ai_layer.py` for guardrail checks. The model cannot
   write to it, and it is the exact text served as the fallback. The guardrail
   checks have no structured provision record at all. Where rules do have one,
   it can disagree with the rationale (R1). Checking a rationale's citation
   against structured data is citation correctness, which is the CA packet's
   job, not the guard's.
2. **The first version's prototype A scoped "supplied" to the batch.** R5's
   citations were therefore exempt in R1's line. Measured in §5.1: R1's line
   citing *"Section 17(1)(h)"* was served under A, and rejected under per-line
   scoping.

**Guarantee: never accepts a line `1dc895c` rejects.** Proof, for per-line
scope, the membership check (§4.7), and no year mechanism or the "agree" year
mechanism (§4.6):
- A token is removed from a line only if it is a reference in that flag's own
  rationale. Every digit in it was extracted from that rationale, so it is in
  today's union `allowed`.
- Every number that is not removed is checked against that flag's own set,
  which is a subset of today's union.
- The membership check only adds rejections.

**This guarantee fails for the "structured" year mechanism.** It was measured
to accept a line `1dc895c` rejects (§4.6).

### 4.6 Act years: three mechanisms, measured

| mechanism | exempts (name, year) when… | R1: *"…Code on Wages 2025 requires"* (pinned legitimate) | R1: *"Rs 2,025 short"* (fabricated) | R1: *"…Code on Wages 2019 requires"* | guarantee §4.5 |
|---|---|---|---|---|---|
| `1dc895c` (none) | never | served | **served** | rejected | — |
| **text** (first version) | the pair occurs in this flag's rationale text | served | rejected | rejected | holds |
| **structured** (review's safe reading) | the pair matches this rule's `instrument` field | served | **served** | **served** | **fails** |
| **agree** | the pair occurs in the rationale **and** matches `instrument` | served | **served** | rejected | holds |

- **text** takes the year the prose states and never checks it against the
  record. That is pattern-matching standing in for verification, as review
  warned. Not recommended.
- **structured** is the reading review approved conditionally. Measured, it
  does two things review did not intend. It **accepts a line `1dc895c`
  rejects**: "2019" is exempted because a record the model was never shown
  contains it. And it **does not close the "Rs 2,025" leak**, because 2025 is
  not in the record, so it is never stripped from R1's rationale and stays in
  `allowed`.
- **agree** keeps the guarantee, but **exempts nothing today**. The only
  instrument year in any rationale is R1's, and R1's text and record disagree.

**Recommendation (revised from "yes"): build no year mechanism now.** The only
safe form is a no-op until the CA rules on packet question R1. Under per-line
scope, the "Rs 2,025" leak is confined to R1's own line. It is recorded in §9
and tied to that question. If R1's text is corrected to agree with its record,
**agree** becomes the mechanism to build.

### 4.7 Added in revision 2: a supplied-citation check

Stripping supplied references stops correct citations being rejected. It does
nothing about a **fabricated** citation whose digits happen to be grounded.
*"Section 50"* in R1's line survives because 50 is R1's real floor, and
*"Section 14"* in the NPS line survives because 14% is the real cap. A figure
check cannot catch these by construction: the digits are genuinely grounded.
What is false is the citation.

**The check:** reject a line if it contains any reference, in the same grammar,
that is not among that flag's supplied references. It reuses
`_CITATION_REFERENCE` and `_citation_key`.

It enforces what each prompt already demands:
- `QUERY_EXPLAIN_SYSTEM_PROMPT`: *"Do not cite any section not present in that list"*.
- `GUARDRAIL_SYSTEM_PROMPT`: no *"section number that is not already present in
  the rationale"*.
- `COMPLIANCE_SYSTEM_PROMPT`: *"do not add numbers"*, *"do not give legal advice
  beyond what's in the rationale"*.

It also closes the gap `QUERY_GUARD_CITATION_DESIGN.md` §7 left open:
unsupplied citations below 100 in `answer_query`.

**Limit:** a reference the grammar does not parse ("s. 17(1)(h)", "Sec. 124",
plurals) is not membership-checked, and falls back to the figure check. That
fails open only when its digits are grounded, which is the same residual as
today, now confined to unparsed forms.

## 5. Measured

### 5.1 The distinguishing test: fabricated citations never supplied

Driven through the real `flag_compliance` / `evaluate_band_guardrail`, with the
model client mocked. Modes:

- **A**: first version, batch scope, text years.
- **B**: per-line scope, text years.
- **Bs**: per-line, structured years.
- **Bsr**: Bs plus the membership check.
- **Bar**: per-line, agree years, membership check.

**A first run of this table was invalid and was discarded.** zsh did not
word-split the mode variable, every prototype apply failed silently, and all
columns measured unpatched code. The re-run confirms each apply by diff size
before measuring.

| case | `1dc895c` | A | B | Bs | Bsr | Bar |
|---|---|---|---|---|---|---|
| **controls** | | | | | | |
| R5 correct citation (supplied) | served | served | served | served | served | served |
| `80ccd2_cap` correct citation, corrected text | served | served | served | served | served | served |
| R1 pinned legitimate *"Code on Wages 2025 requires"* | served | served | served | served | served | served |
| **fabricated / unsupplied citations** | | | | | | |
| R5: *"Section 999"* | rejected | rejected | rejected | rejected | rejected | rejected |
| R5: unsupplied *"Section 17(1)(i)"* | **served** | rejected | rejected | rejected | rejected | rejected |
| R5: unsupplied *"Section 17(2)(viia)"* | **served** | rejected | rejected | rejected | rejected | rejected |
| R1 + R5: R1's line cites **R5's** *"Section 17(1)(h)"* | **served** | **served** | rejected | rejected | rejected | rejected |
| R1: *"Section 50"* (digits = R1's own real 50) | **served** | **served** | **served** | **served** | rejected | rejected |
| `80ccd2_cap`: *"Section 80CCD(3)"* | rejected | rejected | rejected | rejected | rejected | rejected |
| `80ccd2_cap`: *"Section 125"* | rejected | rejected | rejected | rejected | rejected | rejected |
| `80ccd2_cap`: *"Section 14"* (digits = real 14%) | **served** | **served** | **served** | **served** | rejected | rejected |
| `epfo_ceiling`: unsupplied *"Section 17(1)(i)"* | **served** | rejected | rejected | rejected | rejected | rejected |
| **years** | | | | | | |
| R1: *"Rs 2,025 short"* | **served** | rejected | rejected | **served** | **served** | **served** |
| R1: *"Code on Wages 2019"* | rejected | rejected | rejected | **served** | **served** | rejected |
| R1: *"Code on Wages 2031"* | rejected | rejected | rejected | rejected | rejected | rejected |
| **cross-flag (severity 1, 2)** | | | | | | |
| R1 + R4: R4's line *"50% of CTC"* (real 10%) | **served** | **served** | rejected | rejected | rejected | rejected |
| R1 + R4: lines swapped | **served** | **served** | rejected | rejected | rejected | rejected |

**The answer to the distinguishing question.** The mechanism is (b), never (a),
and *"Section 999"* is rejected everywhere. But a figure-based guard **also**
serves a fabricated section whose digits are grounded, in every mode without
the membership check, `1dc895c` included. A fix that stopped at citation
stripping, even correctly scoped, would have left that gap and passed the
review test as first posed. Only **Bar**'s choices (per-line scope, agree
years, membership check) reject every fabrication in the table while keeping
the §4.5 guarantee. The only thing it still serves is "Rs 2,025" (§4.6).

### 5.2 The other two citing call sites, with the membership check

| call site | reply | `1dc895c` | per-line + membership + `negotiate` wiring |
|---|---|---|---|
| `answer_query` | *"…under Section 392 (formerly Section 192)."* (supplied) | served | served |
| `answer_query` | *"You can also claim Section 80C for your PF."* (unsupplied) | **served** | rejected |
| `answer_query` | *"…falls under Section 16."* (unsupplied) | **served** | rejected |
| `negotiate` | names the lever *"NPS enrollment (Section 124, formerly 80CCD2)"* | **rejected** | served |
| `negotiate` | *"…ask HR about Section 80C investments…"* (unsupplied) | **served** | rejected |

### 5.3 Full suite on the recommended combination

Per-line scope, membership check at all four citing call sites, `negotiate`
passing `citations=`, the `80ccd2_cap` text correction, no year mechanism.
Applied at `0e57895`: **491 OK**, the same count and the same result as that
commit. Every changed behaviour in §5.1 and §5.2 is invisible to the existing
suite.

### 5.4 Residual costs, all fail-closed unless marked

- **A citation copied without its keyword** ("(formerly 80CCD(2))" after the
  text fix) is rejected.
- **The check id `80ccd2_cap` is sent to the model.** If the model repeats
  "80ccd2", the line is rejected. Not measured on live output.
- **A true but unsupplied citation is rejected** by the membership check, for
  example a correct "Section 16" added by the model in `answer_query`. The
  prompts already forbid this.
- **Reordering is caught only when figures differ.** Two figure-free rules (R3
  and R6) swapped still get through. *Fails open.*
- **Unparsed reference forms** ("s. 17(1)(h)", plurals) whose digits are
  grounded still get through. *Fails open.*
- **"Rs 2,025" in R1's line** still gets through (§4.6). *Fails open.*

## 6. Tests required

Every row in §5.1 and §5.2 becomes a test at its real call site, asserting the
**Bar** column, or the right-hand column of §5.2. In addition:

1. **Pin the corrected text:** `80ccd2_cap`'s rationale contains
   "(formerly Section 80CCD(2))".
2. **A data-driven coverage test** over every active rule rationale and every
   rendered guardrail rationale: no parenthesised designator (the `80CCD(2)` /
   `17(1)(h)` shape) may sit outside a recognised reference. It walks
   `active_rules()`, so a new rule is covered automatically.
3. **The §4.5 guarantee as a property:** for each flag, the per-line `allowed`
   is a subset of the old union.
4. **The existing pinned legitimate rephrasing** (*"Code on Wages 2025
   requires"*) stays green without being edited.
5. **The two guardrail rationales** get their first coverage of any kind
   (§4.4.3).

**Sabotage, one run per claim, failures predicted before running:**

| sabotage | should fail |
|---|---|
| go back to the batch-wide union | the cross-flag and swapped-lines tests, and the R1-cites-R5's-citation test |
| build `allowed` from unstripped rationales | the citation-digit leak tests ("1 lakh", "2%", "Rs 124") |
| drop `citations=` at a rationale site | the correct-citation controls at that site |
| remove the membership check | the "Section 50", "Section 14", "Section 80C" and "Section 16" tests |
| make stripping ignore the supplied set (option (a)) | the unsupplied "17(1)(i)" and "17(2)(viia)" tests |
| revert the `80ccd2_cap` text | the pin and the coverage test |
| unwire `negotiate` | the `negotiate` lever test |

## 7. Decisions

Recorded 2026-09-14 from review of `54e139f`:

1. **Per-line grounding: approved.** It closes severity 1 and 2 at their source,
   whatever happens with citation logic.
2. **Include `negotiate`: approved.** The flaw is structural, so it is fixed at
   every call site that has it, found by inventory rather than by report.
3. **Act years: deferred** (decided 2026-09-14, after revision 2). Approved
   first on the condition that the mechanism uses the structured instrument
   data. Revision 2 measured that mechanism (§4.6): it breaks the §4.5
   guarantee and does not close R1's leak. No year mechanism is built. Revisit
   when the CA rules on packet question R1; if R1's text and record then agree,
   **agree** is the mechanism to build. Until then, "Rs 2,025" in R1's own line
   still gets through (§9, and the gap table in `docs/PROJECT_STATUS.md`).
4. **The supplied-citation check (§4.7), at all four citing call sites:
   approved** (2026-09-14). At `answer_query` it changes behaviour shipped at
   `f6a3394`, so it gets its own commit there.

## 8. Sequencing

Ordered by severity. Each commit leaves the suite green. The baseline is
re-measured at the start (491 at `0e57895`; the concurrent R5 steps 7a/7b may
have changed it).

**Corrected 2026-09-14, before implementation started.** Revision 2 put a
structural helper commit (step 2) ahead of per-line scoping. Per-line scoping
needs no helper: it only narrows two existing expressions from the batch union
to each line's own rationale. A helper with no caller at that point would be
surface nobody uses. The helpers now come immediately before the steps that
use them, and step 3 is next after this document. The year mechanism is
removed from the plan (decision 3).

1. **This document**: revision 1 (`54e139f`), revision 2 (`3b1ab62`), and this
   decision record.
2. ~~Structural helpers~~: moved to 4a and 6a.
3. **Behavioural, severity 1–2:** per-line scope at `flag_compliance` and
   `evaluate_band_guardrail`. On its own this closes the cross-flag pool and
   swapped lines. Citation digits still leak within a flag at this step.
4. **Structural (4a):** a per-flag grounded-figures helper that strips that
   flag's own references, with unit tests and the §6 item 3 subset property.
   No call site changes.
   **Behavioural, emitted text (4b):** `80ccd2_cap` → "(formerly Section
   80CCD(2))", plus the pin and the coverage test.
5. **Behavioural, severity 3:** per-flag citation stripping at both rationale
   sites.
6. **Structural (6a):** the membership-check helper, with unit tests.
   **Behavioural, severity 4 (6b):** the membership check at both rationale
   sites.
7. **Behavioural, severity 5:** `negotiate` passes `citations=`, plus the
   membership check.
8. **Behavioural:** the membership check at `answer_query`.
9. ~~Documentation: correct R5 §4.4.2's pointer~~: done in `dec893f`.

Full suite after every step, deltas named test by test, `python3 -B` with the
cache cleared. Runs happen in a worktree, gated by a "request run" / "go"
exchange with the concurrent session over the shared Postgres.

## 9. What this does not settle

- **The R1 year.** Its text/record conflict is CA packet question R1
  (`docs/CA_REVIEW_PACKET.md` L100). Until that is ruled on, "Rs 2,025" in R1's
  own line still gets through (§4.6).
- **The output-boundary layer has the same shared-namespace problem.**
  `output_boundary.figures()` strips identifier tokens, not references.
  `test_a_legitimate_rephrasing_passes_both_layers` passes only because its
  payload adds `"metrics": {"year": 2025}`, which grounds the citation's year by
  hand: made-up grounding inside a test of the grounding checker.
- **Citations inside rationale text** (§4.3): the root fix, deferred.
- **Figure-free reordering and unparsed reference forms** (§5.4).
