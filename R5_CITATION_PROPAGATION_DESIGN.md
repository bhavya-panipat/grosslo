# R5 citation propagation — design

**Status:** design, not implemented. Nothing in this document has been built.

The primary-source lookup (`docs/PRIMARY_SOURCE_LOOKUP_TASK.md`, outcome
recorded 2026-09-13, commit `d6cfd90`) resolved both open provisions. This
document designs the propagation of the R5 half into the codebase.

It opens with the two questions raised when the lookup was reported, because
both are load-bearing and both change what gets built.

---

## 1. What the lookup settled, and the one thing it settled *against* us

**Settled:** 1961 s. 17(2)(vii) → 2025 **s. 17(1)(h)**. The Rs 7,50,000
aggregate ceiling and the three-fund composition carried over unchanged, read
side by side in CBDT's own parallel-reading comparison. Companion accretion
provision 17(2)(viia) → 17(1)(i).

**R5's predicate was correct all along. Only its citation was stale.** That is
the good outcome, and it was arrived at rather than assumed.

**Settled against us — and the diagnosis is more useful than the correction.**
`tax_engine.py`'s module docstring says

> Section 17(2)(vii) … was checked and confirmed retained at its original
> number in the new Act — not every section moved.

**That is now known to be false.** The section did move. This claim was already
recorded as disputed in `LEGAL_CLAIM_INVENTORY_DESIGN.md` §10.2 ("the second
`17(2)(vii)`, for the next batch") and in R5's own `citation_checked_on`, which
set the repository's claim against an independent reviewer's and explicitly
declined to pick a winner. **The lookup picks the winner, and the repository
lost.**

This matters beyond one docstring. It is the only surviving instance of a
citation sweep in this project asserting a *positive* verification result that
turned out to be wrong. §4 of this document treats it as its own correction with
its own commit, not as a line swept up in a rename.

### 1.1 The failure mode, named — found while writing the correction

The first draft of this correction said *"every clause of that is wrong"*. That
was an over-claim, and checking it produced the more valuable finding.

**Most of the 2026-09-02 sweep's statement was true.** The 2025 Act's salary
chapter *is* Sections 15–17. Section 17 *is* still headed "Perquisite". It *is*
true that not every section moved. Nothing was invented.

**The sweep checked at section granularity and reported at sub-clause
granularity.** "Section 17 is still perquisites" is true and was genuinely
verified. "Therefore 17(2)(vii) is retained" does not follow from it — the 1961
Act's 17(2) perquisite list was restructured into the 2025 Act's 17(1), so every
sub-clause beneath it moved while the section number above them did not.

**A check one level coarser than the claim it supports will keep returning
confirmations, and they will keep being real confirmations of a different
proposition.** That is a sharper failure than a guess, and more dangerous,
because the verification actually happened and the evidence is genuine.

It is also the same shape as the finding in §3 below: a guard that binds the
*id* while the *claim* is what moved. Both are checks aimed one level off the
thing they are trusted to protect.

---

## 2. Question one — the mechanism loses its only live instance

Fixing R5's citation drives `protocol_violations()` from 1 to 0.

### 2.1 Decision: do not manufacture a violation. Zero is the correct answer.

**Resolved.** A check whose entire job is *"does anything currently cite a
superseded instrument"* reporting zero, because nothing currently does, is the
mechanism working exactly as designed.

This is the same shape as the claim inventory's zero-drift result on day one
(`LEGAL_CLAIM_INVENTORY_DESIGN.md` §4.5): a detector finding nothing is a
finding, not a failure to find something. Keeping R5 mis-cited, or inventing a
carrier rule, to preserve a non-empty list would be optimising the instrument
for its own readings — precisely the "measuring instrument, not a fix" framing
this project has held unrounded.

**What must not happen:** `assertEqual(len(protocol_violations()), 0)` quietly
replacing the current pin, with nothing else changing. That trades a test that
proves *the check fires on a real case* for a test that proves *nothing is
wrong today*. The second is much weaker and looks identical in a green run.

### 2.2 How the check gets proven with nothing live to exercise it

A synthetic carrier, sabotage-style — the pattern already used throughout this
project to prove a check works without a real violation sitting in production.

**This pattern already exists in the file and already covers this exact check.**
`test_an_active_rule_citing_a_superseded_act_is_a_violation` (L541) builds a
synthetic `R81` with `instrument_status=SUPERSEDED` and asserts it is flagged.
`test_a_non_rule_carrier_still_gets_the_superseded_instrument_check` (L1025)
does the same for a non-Rule carrier `C4`. **Both pass today and neither depends
on R5.**

So the coverage is not lost when R5 is fixed — it is already elsewhere. What is
lost is the *demonstration* that the synthetic case matches a real one. That is
the gap this design must close, and it closes it by **retargeting the R5 pins
rather than deleting them**:

- `test_the_rule_set_has_exactly_one_known_open_violation` (L277)
- `test_the_only_open_violation_is_the_known_R5_citation` (L464)
- `test_R5_still_surfaces_exactly_as_before_the_refactor` (L1046)

These three currently assert *"exactly one violation, it is R5, it is
superseded"*. Each becomes a pair:

1. **The rule set is clean** — `assertEqual(protocol_violations(), [])`, with
   the full list in the failure message so a regression names itself.
2. **The check still fires** — the existing synthetic carrier, asserted in the
   same test, so the clean result can never be green for the wrong reason.

The second half is the one that matters. Read `§7` of
`INVENTORY_EXPANSION_DESIGN.md`: a test that asserts only an empty list passes
identically whether the check works or has been deleted. The both-states pairing
is what stops that.

**Sabotage requirement, to be run and named in the commit message:** break
`provenance_violations()`'s superseded branch and confirm the retargeted tests
fail. If deleting the branch leaves a green suite, the retarget is wrong and the
empty-list assertion is doing no work.

### 2.3 One thing this design deliberately does not do

`test_R5_still_surfaces_exactly_as_before_the_refactor` was written to pin a
*refactor's* no-behaviour-change claim, using R5 as the live subject. Retargeted,
its name becomes a lie — it no longer describes a refactor. It gets **renamed**,
not repurposed silently. A test whose name describes work that is three phases
finished is how a suite starts drifting from what it actually checks.

---

## 3. Question two — is the packet generator a third source of truth?

**Yes. Checked, not assumed, and it is worse-shaped than the instances already
caught.**

`scripts/generate_ca_review_packet.py` holds `ACTIVE_RULE_QUESTIONS`, a
hand-written list keyed by rule id. Its R5 entry (L118) asserts:

> Cites Section 17(2)(vii) of the Income-tax Act, **1961**, which the
> Income-tax Act, 2025 replaced … the successor number was NOT guessed.

Every one of those is a restatement of data that lives in `compliance_rules.py`
R5's `instrument`, `instrument_status` and `citation_checked_on`.

The guard that exists — `test_every_active_rule_question_names_a_rule_that_still_exists`
(L833) — **binds the id and nothing else.** It was written against the failure
*"a rule was deleted"* and passes cleanly through the failure *"the rule's facts
changed underneath the question"*.

So after the citation update, the packet keeps telling a CA that R5 cites a
repealed Act, with a green suite, to the one audience whose whole purpose is to
catch exactly that.

**This is the §4.5 pattern with the drift check missing.** §4.5's finding was
that deliberate value duplication is fine *because a drift check watches it*.
Here the duplication is prose rather than values, and nothing watches it at all.
R1's entry has the same shape (it restates the Code on Wages year dispute).

### 3.1 Decision, and its limit

**A prose question cannot be mechanically diffed against a dataclass field, and
this design does not pretend otherwise.** Asserting substring containment
between a question and a citation field is the string-assertion anti-pattern
(`INVENTORY_EXPANSION_DESIGN.md` §8) — it would pass on coincidence and fail on
rewording.

What *is* checkable is the **claim each question depends on**. Each entry gains
a third element: a predicate over the rule it asks about, naming the condition
that must still hold for the question to make sense.

```
("R5", lambda r: r.cites_superseded_law, "Cites Section 17(2)(vii) of …")
```

A test evaluates every predicate against the live rule and fails when one is
false — *"the packet asks about R5 on the basis that it cites superseded law;
it no longer does; the question is stale"*. That binds the question to a
structured field (§8 compliance), not to its own wording.

This is a real change to a generator, with its own tests, and it is **not
folded into the citation commit**. See §5.

**Flagged for decision, not resolved here:** whether R1's and R2's/R4's entries
get predicates in this pass or only R5's. Doing all five is more consistent;
doing one is a smaller diff that proves the mechanism. Recommendation: all five,
because a predicate on one entry and not the others invites the reader to assume
the unguarded ones are guarded.

---

## 4. Blast radius — every site, and what kind of change each is

`17(2)(vii)` appears in 13 files. They are **not** one change.

### 4.1 Citation data (structural — no emitted text changes)

| Site | Change |
|---|---|
| `compliance_rules.py` R5 `instrument` | `Income-tax Act, 1961` → `Income-tax Act, 2025` |
| R5 `instrument_status` | `SUPERSEDED` → `IN_FORCE` |
| R5 `provision` | → `s. 17(1)(h)`, with the three-fund text |
| R5 `source_url` | → the section-17 URL actually used |
| R5 `citation_checked_on` | `unresolved: …` → `2026-09-13` |

**The act number is not written.** `(Act 30 of 2025)` was unverified; see the
lookup outcome. This is a deliberate blank, and a reviewer should see it as one.

### 4.2 Emitted text (behavioural — changes what users and CAs read)

| Site | Note |
|---|---|
| `compliance_rules.py` R5 `rationale`, `why` | Flows into three generated artefacts |
| `ai_layer.py` L649 | Guardrail rationale shown to users |
| `compliance_rules.md`, `docs/CA_REVIEW_PACKET.md`, `docs/LEGAL_REVIEW_QUEUE.md` | Regenerated, `--check` tests enforce sync |

### 4.3 A false claim, not a stale one

| Site | Note |
|---|---|
| `tax_engine.py` L30–32 | Asserts the section was *confirmed retained*. It was not. §1. |
| `README.md` L685–690 | **The same false claim, in a stronger form.** |

**Correction to this document, made while executing step 1.** §4.4 below
originally filed `README.md` L685 under "prose that describes the
investigation". That was wrong. It is not prose about the investigation — it is
the **source instance of the false claim**, filed under the heading *"Checked
and found NOT to need a citation change"*, and asserting the section was
*"verified rather than assumed just because most of its neighbors did move"*.

It is also the instance R5's own `citation_checked_on` quotes by name when it
sets the repository's claim against the independent reviewer's. Missing it
would have left the load-bearing copy standing while correcting the quieter one.

Both are **wrong**, as opposed to out of date. They share step 1's commit.

That this document mis-classified one of the two sites it was written to
enumerate is worth leaving on the record: a blast-radius list assembled by
grepping one phrase will group by *where text matched*, not by *what kind of
claim it is*, and the second grouping is the one that decides sequencing.

### 4.4 Prose that describes the investigation, now finished

`provenance.py` L27 (R5 as a live example of the access wall),
`COMPLIANCE_BREADTH_DESIGN.md` L481, `LEGAL_CLAIM_INVENTORY_DESIGN.md`
§10.2 and L418, `README.md` L449.

(`README.md` L685 was listed here in the first draft and has been moved to
§4.3, where it belongs — see the correction recorded there.)

`README.md` also carries a separate error the lookup surfaced: it records the
HRA exemption as moving to **"Section 11, read with Schedule II"**. The primary
source says **Schedule III [Table: Sl. No. 11]**. Schedule II is the
exempt-income schedule (life insurance, agricultural income). Own commit.

**Correction to this document, made while executing step 2.** The error is not
confined to documentation. `ai_layer.py` L1080 appends
`"Section 11, read with Schedule II (formerly Section 10(13A))"` to
`applicable_sections`, which is **emitted to users**. So step 2 splits:

- **2a — documentation.** `README.md`, this file, `LEGAL_CLAIM_INVENTORY_DESIGN.md`
  (two rows).
- **2b — emitted text.** `ai_layer.py` L1080. Separate commit, per the standing
  rule that behavioural changes are never mixed with structural ones.

**And the reason it survived: nothing tests it.** No test in the suite asserts
on `applicable_sections` or on any string in it. A wrong statutory citation was
being shown to users, and the suite was green the entire time — which is the
same gap the output-boundary check was built for, one field over. The boundary
check verifies that *numbers* in model-facing text are grounded; nothing
verifies that *citations* handed to the model are correct. Noted, not fixed
here; it belongs with the tracked `ai_backed` follow-up rather than inside this
propagation.

---

## 5. Sequencing

Separate commits, in this order. **Do not reorder or combine.**

1. **Correct `tax_engine.py`'s false retention claim.** Standalone, because it
   is the one place the repository asserted a verification result that was
   wrong, and burying it inside a citation update hides that.
2. **Correct the README Schedule II → Schedule III error.** Unrelated to R5;
   found in the same lookup.
3. **R5 citation data** (§4.1). Structural. Emitted text byte-identical —
   asserted, not stated.
4. **Retarget the three violation pins** (§2.2), with the sabotage run named.
5. **R5 emitted text** (§4.2) + regenerate artefacts. Behavioural, separate
   from step 3 by the standing rule.
6. **Packet-generator predicates** (§3.1). Its own mechanism, its own tests.
7. **Investigation prose** (§4.4). Documentation only.

Full suite after every step, reported against the 469 baseline, deltas named
test by test. `python3 -B` with the cache cleared throughout.

---

## 6. Open decisions

1. **Packet predicates: all five entries or only R5?** Recommendation: all five
   (§3.1).
2. **Does R5 keep its pre-protocol grandfathering?** `PRE_PROTOCOL_RULE_IDS`
   exempts R1–R6 from the reviewer requirement. R5 now has a verified citation
   but still no `reviewed_by`. The lookup explicitly does **not** substitute for
   protocol step 5. Recommendation: leave the grandfathering untouched — it
   covers the reviewer gap, which is unchanged, and narrowing it here would
   conflate two different things.
3. **Does `ai_layer.py` L649 adopt the "new, formerly old" form** already used
   elsewhere ("Section 124, formerly 80CCD(2)")? Recommendation: yes —
   17(2)(vii) remains the more recognisable term and the precedent exists.

---

## 7. What this does not settle

- **`reviewed_by`.** Unchanged. The CA gate is exactly where it was.
- **The HRA candidate rule.** Now unblocked — it has a citable provision
  (Schedule III Sl. No. 11, Rule 279, still 50/40). Drafting it is separate
  work under the candidate-rule protocol, not part of this propagation.
- **The DA question.** Rule 279 defines *salary* as including dearness allowance
  where it is a term of employment; `hra_exemption()` uses `basic` and
  `SalaryStructure` has no DA field. That is a correct private-sector
  assumption that has never been written down. It is a CA question and it
  belongs in the packet, not in this change.
- **The metro-selection gap.** A user in Bengaluru, Hyderabad, Pune or
  Ahmedabad who correctly answered `non_metro` under the old law must now
  answer `metro`, and nothing in the product says so. Not a code defect —
  `city` is an abstract flag — but a real user-facing gap. Its own item.
