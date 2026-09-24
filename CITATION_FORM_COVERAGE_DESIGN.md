# Citation forms the guard does not parse

**Status: measured, not implemented. Four decisions below are the owner's.**

This is guard-row item (2) in `docs/PROJECT_STATUS.md`, carried since
2026-09-18 as *"an unparsed citation form (`s. 17(1)(h)`, plurals) whose digits
equal a real figure is not checked"*, marked **decide whether to address**.

Measuring it changed what it is. It was recorded as one narrow gap. It is four,
three of them **fail-open**, and one of those is the defect
`RATIONALE_GUARD_CITATION_DESIGN.md` §4.7 was built to close, still open for any
abbreviated form.

## 1. What was measured

Commit `ee76e4d`, clean worktree, `python3 -B`, no database, no model calls —
the functions are pure, so this is measurement rather than inference. Each form
was put through the two checks separately, because they fail in opposite
directions:

- `_strip_supplied_citations` — is the reference blanked, so its digits are not
  read as figures? Blindness here causes **false rejection**.
- `_citations_unsupplied` — is a reference seen at all, so it can be compared
  against what was supplied? Blindness here causes a **fabricated citation to
  be served**.

### 1.1 The rationale sites, verbatim (`skip_below=0`, `citations=[rationale]`)

Rationale: `"Employer NPS exceeds the 14% cap under Section 124 (formerly
Section 80CCD(2))."`, whose only grounded figure is `14.0`.

| model line | figure check | membership | served |
|---|---|---|---|
| `...breaches the 14% cap.` | passes | passes | yes — correct, legitimate |
| `...breaches the cap under Section 14.` | passes | **rejects** | no — correct |
| `...breaches the cap u/s 14.` | passes | blind | **yes — FABRICATED, SERVED** |
| `...breaches the cap under s. 14.` | passes | blind | **yes — FABRICATED, SERVED** |
| `...breaches the cap under Section 124.` | passes | passes | yes — correct, supplied |
| `...breaches the cap u/s 124.` | **rejects** | blind | no — **false rejection** |

Rows 2 and 3 are the same fabrication in two spellings. One is caught; one is
served. There is no Section 14 governing the employer-NPS cap; 14 is a
percentage. A user reads an invented statutory authority as the stated reason
for a compliance flag.

### 1.2 `answer_query` (`skip_below=100`)

Below 100 the figure check skips numbers entirely, so membership is the *only*
thing that can reject a low-numbered citation. Blind to abbreviations, it
rejects nothing:

| model reply | served |
|---|---|
| `You can also claim Section 80C for your PF.` | no — rejected, membership |
| `You can also claim s. 80C for your PF.` | **yes — FABRICATED, SERVED** |
| `Deductible u/s 16.` | **yes — FABRICATED, SERVED** |
| `Your tax is Rs 145000, claimable under s. 16.` | **yes — served, grounded figure carries it** |

This is exactly the §4.4.2 defect. `tests/test_query_guard_citations.py`'s
`test_low_sections_never_supplied_are_rejected` pins both of those sections —
in the parsed spelling only.

### 1.3 `explain_result` — the widest, and previously unnamed

It supplies **no** sections and passes **no** `citations`, so every citation it
writes is unsupplied by construction, and nothing checks for one. Its prompt
(`EXPLAINER_SYSTEM_PROMPT`) forbids introducing a rupee figure or percentage and
says nothing about statutory authority. So "the new regime's standard deduction
under Section 16 is higher" is served in the parsed spelling too: 16 is below
100 and skipped. This site does not need an exotic form to fail.

### 1.4 The fail-closed mirror (quality, not safety)

A **supplied** reference written in any unparsed form is rejected, because its
digits are read as figures: `s. 392`, `sec. 392`, `u/s 392`, `Sections 392 and
124`, and `392 governs salary TDS` all fail where `Section 392` passes. That is
the §4.4.1 defect for abbreviations — it fails closed, so it is a quality
defect, and invisible.

## 2. Cause

One list, used for two purposes:

```python
r"\b(Section|Schedule|Rule|Form|Sl\.\s*No\.)\s+"
```

`_supplied_references`, `_strip_supplied_citations` and `_citations_unsupplied`
all derive from `_CITATION_REFERENCE`, deliberately, so stripping and membership
can never disagree about what was supplied. The consequence was not thought
through: they also cannot disagree about what a *citation* is. A form outside the
keyword list is not "a citation we can't match" — it is not a citation at all, so
the membership check has nothing to test.

## 3. The asymmetry that makes this fixable

Recognising more forms is **safe in both directions**, for different reasons:

- **Membership.** Recognising more forms can only reject more. A form that is
  recognised and supplied is accepted exactly as before; a form recognised and
  not supplied is now rejected instead of served. It cannot widen anything.
- **Stripping.** Recognition alone exempts nothing: a reference is blanked only
  if its `(keyword, designator)` key is among those actually supplied, and the
  key normalises the keyword. So adding `u/s` as a keyword lets `u/s 124` be
  exempted **only when Section 124 was supplied for that call**.

So one grammar extension closes the fail-open and the false rejection together,
and neither can widen the exemption past what was supplied. That is worth
stating explicitly because the obvious fear — "a longer keyword list is a bigger
loophole" — is the opposite of what the code does.

**What cannot be fixed this way:** a bare designator (`392 governs salary TDS`)
is indistinguishable from a figure without treating every number as a possible
citation. It stays a figure, and stays rejected. That residual is deliberate and
should remain recorded rather than quietly widened.

## 4. Decisions for the owner

| | Decision | Recommendation |
|---|---|---|
| **D-C1** | Add abbreviated keywords (`s.`, `ss.`, `sec.`, `u/s`, `under s.`) to the grammar? | **Yes.** It closes §1.1 and §1.2 and the §1.4 mirror in one change. Risk to weigh: `sec.` also abbreviates *seconds*, and a bare `s.` is common in ordinary prose. Mitigation: require a designator token immediately after, which `14`/`80C` satisfies and `"in 30 sec. the page loads"` does not — but this needs its own test either way. |
| **D-C2** | Parse plural forms (`Sections 392 and 124`)? | **Yes, but second.** It is the same class and a narrower grammar change (keyword plural, then a designator list). It is currently pinned as a deliberate residual in `test_the_named_residual_rejections_are_kept`, so closing it means changing a test that exists to catch exactly this widening — which is the test doing its job, and the change has to be explicit. |
| **D-C3** | `explain_result`: forbid citations in the prompt and guard for them, or supply sections and check membership? | **Forbid and guard.** It explains arithmetic, not law; it has no reason to cite. Supplying sections there would widen the surface for no product gain. This is a prompt change plus one guard call, and it is the only site whose fix is not the grammar. |
| **D-C4** | Keep bare designators out of scope? | **Yes**, and keep the test that pins their rejection, so the boundary stays a decision rather than an omission. |

## 5. Sequencing, if approved

Per this project's convention, each step is its own commit, with the full suite
after it and a sabotage run whose failures are predicted beforehand.

1. Tests for every row in §1.1–§1.4, committed **knowingly red** — the served
   fabrications first, since those are the fail-open.
2. Grammar: abbreviations (D-C1). Expect §1.1 rows 3–4, §1.2 rows 2–4 and the
   §1.4 mirror to go green together.
3. Plurals (D-C2), including the deliberate rewrite of
   `test_the_named_residual_rejections_are_kept`.
4. `explain_result` (D-C3): prompt sentence plus the guard call.
5. Update `docs/PROJECT_STATUS.md` item (2) and this file's record.

Sabotage, one per mechanism: revert the keyword list and confirm the served-
fabrication tests fail; drop the designator-adjacency requirement and confirm
the `"30 sec."` test fails; remove the `explain_result` guard call and confirm
its own test fails.

## 6. What this does not settle

- **Whether the model ever writes these forms.** Everything above is measured on
  the guard, not on model output. The guard's job is to hold regardless, and a
  fabrication served in one spelling and caught in another is a defect whether or
  not today's model happens to prefer the caught spelling. But no claim is made
  here about frequency, and none should be made without measuring real replies.
- **Act years** (`Rs 2,025`) — still deferred, decision 3, untouched.
- **The (C) off-topic detector** — still deliberately not built.
