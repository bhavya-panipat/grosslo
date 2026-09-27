# Carrying the basis flags into the exported payload — design (D-S3)

**Status:** design and measurement complete, **awaiting approval.** No code is
changed. Decision D-S3 (§6) is the owner's.

**Why now.** Found 2026-09-22 by the neighbouring-route sweep
(`NEIGHBOURING_ROUTE_CLAIM_SWEEP.md` §2.2). The owner asked for it next on
2026-09-26.

**Read §2 before §3.** The measurement changes this decision's justification,
though not — in my reading — its answer. It would be easy to implement this on
the strength of the sweep's recommendation alone and never notice that the
population is empty.

---

## 1. The defect

`review_queue._row_to_dict()` attaches `tax_basis_flag` and
`treasury_basis_flag` to every row it returns, and appends their reasons to
`orchestration.reasons`. `/api/submissions/<id>/rows/<i>/export` reads its row
through `get_submission()`, so **it holds both flags and reads neither.**
`app.py` does not contain the string `tax_basis` anywhere.

Verified end to end on 2026-09-22: a row forced to the pre-fix basis exports
`200` with a payload containing no trace of the flag.

**The flag reaches the Finance screen and not the payment instruction.** D1-4 and
D-T3 built the read-time mechanism so that a figure someone may act on says when
its basis is superseded. A payout payload is the document that gets acted on, and
it is the one surface the mechanism does not reach.

## 2. The measurement

Per `CLAUDE.md`'s *Measure the population before ranking severity*, which this
project adopted after D-S6 — and which applies to its own recommendations.

### 2.1 Which rows could be exported carrying a flag

Export requires `status == "approved"` **and** either bank details (the new-hire
path) or a `current_structure` (the correction path). A flag requires a pre-fix
basis.

| Store | Rows | Would carry `tax_basis_flag` | Would carry `treasury_basis_flag` | **Exportable and flagged** |
|---|---|---|---|---|
| Postgres (all tenants) | **0** | 0 | 0 | **0** |
| Pre-port SQLite `review_queue.db` | 5 | **2** | **0** | **0** |

The two flagged SQLite rows are `sub3 row0` (pending, employer NPS ₹2,01,600) and
`sub4 row1` (rejected, ₹2,56,200). **Neither is approved, and neither has bank
details or a `current_structure`**, so neither can reach the export route at all.
The one approved row has no employer NPS, so it would not be flagged.

**`treasury_basis_flag` fires on none of them, and the reason is worth stating
because I expected otherwise:** those rows predate the treasury forecast
entirely, so `_forecasts()` finds nothing, `stale` is empty, and the function
returns `None`. There is no stale forecast to detect — not a forecast that
happens to be current. Measured, not reasoned from the fix dates.

### 2.2 The flagged set is closed

`tax_basis` is written at insert as `nps-as-salary-capped`, which is the only
member of `_NPS_CORRECT_TAX_BASES`. **So a row created today is never flagged,
and the flagged set cannot grow.** Same shape as D-S6.

### 2.3 What this means

**The population this change would serve is empty today and cannot grow from
here.** Anything below is defense-in-depth against §5's trigger conditions, not
a repair of something currently wrong. Stating it plainly because the sweep's
recommendation reads as though it were fixing a live exposure, and it is not.

## 3. Why I still recommend implementing it, unlike D-S6

D-S6 measured zero and the recommendation was **don't build**. This measures zero
and the recommendation is **build**. The difference has to be stated, or the two
decisions look inconsistent and the measurement looks decorative.

| | D-S6 | D-S3 |
|---|---|---|
| Mechanism | would need a **new** one — flag derivation, a response field, a frontend badge | **already exists**; the flags are on the row object the route holds |
| Cost | a column-or-derivation decision plus frontend work | roughly three lines, no new derivation, no new state |
| Cost when inactive | **a badge beside two working ones that can never fire**, which teaches people to discount all three | **an absent key**. Nothing renders, nothing is shown, no one is trained to ignore anything |
| Nature of the gap | a consequence nobody had decided about | **an existing mechanism left incomplete by oversight**, whose own stated purpose is not served until it reaches the artefact that gets acted on |
| Flagged population | 0 rows, in any store | **2 rows exist and carry a flag** — they are merely not exportable |

**The last two rows carry the argument.** D1-4 and D-T3 decided that a figure
someone may act on should say when its basis is superseded. That decision is
already taken; this route simply does not implement it. And the noise objection
that killed D-S6 — a signal that can never fire degrades the ones that can —
does not apply to a key that is absent when there is nothing to say.

**The honest counter-argument**, recorded rather than argued away: this project
has just established that a measured zero is a legitimate reason not to build,
and building anyway on a zero population risks making that principle look
selectively applied. If the owner reads it that way, **record-and-defer is a
defensible answer** and §5's triggers make it recoverable. I do not think the two
are the same case, for the reasons above, but the objection is real.

## 4. Design

**Carry the flags. Do not refuse the export.**

- The payload gains `tax_basis_flag` and `treasury_basis_flag` **only when the
  row carries them** — absent otherwise, so a consumer never has to distinguish
  "no flag" from "this response predates the field" by reading a `null`.
- When either is present, the payload also gains
  `WARNING_BASIS_SUPERSEDED`, carrying the same reason text the queue shows —
  **the same two-surface treatment `WARNING_DO_NOT_UPLOAD` already gets in this
  route**, and for the same reason: a warning must survive the payload being
  piped, saved or handed on.
- **Not** an HTTP header. `X-Source-Account-Placeholder` exists because that
  warning concerns the whole response; a basis flag concerns the figures, and
  headers get dropped by every tool that reformats a body. The body is where a
  payment instruction's caveats belong. *(Stated because the precedent invites
  copying the header too, and I do not think it should be copied.)*
- **Nothing is recomputed and nothing stored is rewritten**, exactly as D1-4 and
  D-T3 settled. The payout amount, the forecast and the guardrail are untouched.

### 4.1 Why not refuse

D1-7(b) already settled that a pre-fix row's reasons say so rather than the route
blocking. A refusal would be a **new gate on work a human has already approved**,
which is a product decision about the maker-checker flow and not a completion of
a flagging mechanism. It also fails closed on rows whose figures may well be
right — the flag says *may be wrong*, not *is wrong*.

### 4.2 Not in scope

D-S4, the mixed computation bases in the same payload — separate decision, still
open. The per-row export's other fields. Any change to who approves a payout, or
to what the Finance queue displays.

### What a measured zero does and does not establish

**The count is not informative on its own, and it should not be read as
reassurance.** There is no production deployment: no Dockerfile, Procfile or
platform config, no `DATABASE_URL` in `.env`, and only local databases on this
machine (`TAX_ENGINE_EMPLOYER_NPS_DESIGN.md` §8). The five SQLite rows are
development data from 2026-09-07. So "0 affected rows" here means **0 because
nothing has been submitted by a real customer**, not 0 despite real volume. Those
are very different levels of assurance, and this document let them look the same.

**What carries the decision is the CLOSED-SET property, which is independent of
deployment.** Every row written after the fix is computed on the corrected basis,
so the affected set cannot grow *whatever the volume*. That argument would hold
identically with a million rows in Postgres. The count only says nothing is owed
retroactively today; the closed set says nothing will be owed tomorrow.

*(Added 2026-09-27, at the owner's challenge. The two were run together as one
reason and only one of them is load-bearing. If this is ever revisited, revisit
it on the closed-set property — and note that a restored pre-fix store breaks
that property, which is what the trigger conditions exist to catch.)*

## 5. What would make this live

The same triggers as `STORED_ROW_BASIS_FLAG_DESIGN.md` §4, and they are why
record-and-defer would be recoverable rather than final:

- a pre-fix backup is restored, or any database predating 2026-09-19 is attached;
- `scripts/migrate_sqlite_to_postgres.py` is run — **note that this alone is not
  enough**: the two flagged rows still could not be exported, because neither is
  approved and neither has bank details or a `current_structure`;
- another deployment exists. No deploy configuration is evidenced in the
  repository (`TAX_ENGINE_EMPLOYER_NPS_DESIGN.md` §8), which is evidence about
  this machine, not proof.

## 6. Decision for the owner

| | Decision | Recommendation |
|---|---|---|
| **D-S3** | Carry the basis flags into the exported payload, refuse the export, or record and defer? | **Carry them.** An existing mechanism is incomplete by oversight, at a cost of about three lines and no new state, and it adds an absent key rather than a signal that can never fire. **But the population is measured at zero and closed (§2), so this is defense-in-depth, not a repair** — and *record-and-defer* is defensible on the same principle that settled D-S6, if the owner prefers consistency there. **Not** a refusal: D1-7(b) already ruled that reasons say so rather than the route blocking, and a new gate on approved work is a product decision. |

## 7. Tests, if approved

- **A flagged row's export carries the flag and the warning**, with the same
  reason text the queue shows — asserted against `review_queue`'s constant, not a
  copied string.
- **An unflagged row's export carries neither key** — the both-states pair, so the
  feature cannot be satisfied by always emitting it.
- **Both flags independently**: a tax-basis-flagged row and a
  treasury-basis-flagged row each produce their own key.
- **Nothing else moves**: on a flagged row, the payout amount, `payout_basis` and
  `treasury_forecast` are byte-identical to the unflagged case with the same
  input.
- **The correction path too** — the XLSX branch returns a file, not JSON, so the
  flag cannot ride in a body. **This is an open question in the design, not a
  solved one:** the workbook's honesty label uses a header
  (`X-Template-Honesty-Label`), so that branch may have to use one despite §4's
  argument against headers. Flagged rather than decided.

**Sabotage:** emit the flag unconditionally — the unflagged-row test fails alone,
proving the pair distinguishes "carried when present" from "always present".

## 8. Implementation record (2026-09-27)

| Step | Commit | Result |
|---|---|---|
| Tests, committed failing | `f6180a4` | 8 run, **4 failures** — the four needing the feature. The other four assert that nothing changes, and had to pass from the start |
| Both branches | `319c02c` | **696 tests OK** |
| Sabotage: emit the payload flag unconditionally | — | **exactly the 1 predicted failure**, the unflagged-row test. The only thing in 693 tests that tells "carried when present" from "always present" |

**Verified: 696 tests OK at `319c02c`, no failures, no skips**, in a worktree
outside the shared tree. Counts in `README.md` and `FINOS_PROJECT_BRIEF.md`
regenerated with `scripts/generate_test_counts_md.py`, not hand-edited.

**The run above is the second one, and the first did not carry over.** This range
was rebased twice. The first rebase crossed documentation only, so the earlier
result still applied. The second crossed `output_boundary.py` — the census fix
that lets a declaration alone make a section visible — so **the suite was re-run
from scratch rather than the 693 figure being carried forward with new SHAs**.
Every SHA cited here was rewritten to its post-rebase identity for the same
reason, which is the third time in this work that a rebase has silently
invalidated a document's own citations. The rule that follows: after a rebase,
check whether anything the range crossed was code, and re-measure if it was.

### 8.1 §7's open question, decided

The correction path returns an XLSX, so the flag cannot ride in a JSON body.
**Decided as the workbook itself plus a header, not a header alone.** A saved file
outlives its response headers, which is the same reasoning that put the JSON
caveat in the body rather than only on the response. `basis_warnings` is an
optional argument to `build_salary_revision_workbook()`, so every existing caller
is unaffected, and the rows are absent when there is nothing to say — an
always-present warning row would train people to skip the sheet, which is
D1-4 §8.2's argument against flagging unaffected rows, applied to a spreadsheet.

**The template honesty label and the basis warning coexist, and a test pins it.**
One is about the *file shape* and has been there since the workbook shipped; the
other is about the *figures*. Neither replaces the other, and it would be easy to
write the second in a way that overwrote the first.

### 8.2 Two things the tests do that are worth copying

- **Every reason string is asserted against `review_queue`'s own constant**, never
  a copied literal. A copied string passes while the route emits stale text —
  the same defect class as a figure copied out of a run.
- **Each flagged-row test asserts the fixture actually produced a flag** before
  asserting anything about the route. Without that precondition a fixture that
  quietly stopped flagging would make them pass vacuously, which is exactly the
  trap the treasury work hit: four identity assertions, all running where the
  missing term was zero.

### 8.3 A mistake, and why the conformance is safe

The new annotation broke at import on Python 3.9 (3.9.6 here), because
`salary_revision_export.py` lacked `from __future__ import annotations`. **The new
tests caught it on their first run, before any suite.**

**"Twelve other modules do it" is a pattern, not a reason, so the absence was
checked rather than assumed.** It is not a deliberate exemption, and it is not
quite an oversight either:

- **The module never had an annotation that needed it.** Its only annotated
  signature was `rows: list[dict]) -> Workbook`. `list[dict]` is a builtin
  generic subscript (PEP 585) and evaluates fine on 3.9 — confirmed by running
  it. What fails on 3.9 is the `X | None` union syntax (PEP 604, 3.10+), and
  `basis_warnings: list[str] | None` is **the first union this file has ever
  had**.
- **The import was never present and never removed.**
  `git log -S "from __future__ import annotations" -- salary_revision_export.py`
  returns only the commit that adds it.
- **Nothing inspects this module's annotations at runtime**, so PEP 563's
  stringification cannot change behaviour: the file itself uses no
  `get_type_hints`, `__annotations__`, `dataclass`, `inspect` or `typing`, its
  consumers only import and call it, and **no file in the repository uses
  `get_type_hints` or `__annotations__` at all**.
- **It simply predates the convention** — created 2026-09-01, where
  `pipeline.py` (which has the import) arrived 2026-09-08.

So conforming is safe, and the reason is the absence of any runtime annotation
consumer, not the popularity of the pattern.

### 8.4 The count generator caught this change too

`tests/test_doc_test_counts.py` — landed by another session while this work was in
progress — failed on the new test file and **demanded a descriptive line, not just
a refreshed number**: *"these test files have no entry in README.md or
FINOS_PROJECT_BRIEF.md, so the total would count files the reader is never
shown."* That is stronger than the hand-checked sum this project relied on until
2026-09-26, and it earned its place on first contact with an unrelated change.
