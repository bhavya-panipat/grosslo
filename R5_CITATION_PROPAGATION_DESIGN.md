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

#### 4.4.1 A separate pre-existing defect, found while checking that step 2b was safe

Before changing the emitted string, the question was whether a longer citation
could trip `answer_query`'s numeric guard. It cannot — the added tokens are
`11`, below the `skip_below=100` threshold. **But the check that answered that
question found something else.**

`answer_query` hands the model `grounding["applicable_sections"]`, then guards
the model's reply with `_numbers_ungrounded(candidate, allowed)`, where
`allowed` is built only from *numeric* values in `grounding`.
`applicable_sections` is a list of **strings**, so the section numbers in it
never enter `allowed`. Measured, not reasoned:

| model reply | `guard_triggered` |
|---|---|
| "…under **Section 124**." | **True** |
| "…under **Section 392**." | **True** |
| "…under Section 11, read with Schedule III, Table Sl. No. 11." | False |
| "Your total tax is Rs 145000…" (grounded) | False |

**The product hands the model a citation and then penalises it for using the
citation.** Any answer quoting a section number ≥ 100 — which is most of the
ones this code supplies — trips the guard, sets `ai_backed = False`, and
silently serves the thin deterministic fallback instead.

This **fails closed**, so it is a quality defect rather than a correctness or
safety one: no wrong number reaches a user, the answer just quietly gets worse.
That is precisely why it has gone unnoticed.

Fixing it is out of scope here and is not obvious — adding section numbers to
`allowed` would weaken the guard by whitelisting three-digit values for every
answer, which is the opposite of what the guard exists to do. **Recorded as its
own item, not folded in.**

**Resolved for `answer_query` by `QUERY_GUARD_CITATION_DESIGN.md`** (merged at
`f6a3394`). A reference is blanked out before extraction only when it is written
in citation form *and* that exact reference was in the `applicable_sections`
this call supplied. Nothing is added to `allowed`. An unsupplied "Section 394"
and a bare "Rs 392" are still rejected.

**§4.4.2 below is not closed by that fix.** It was written without §4.4.2 in
view: `citations=` is passed only by `answer_query`, and `flag_compliance`
still builds `allowed` from `_extract_numbers(rationale)`. Re-measured on
`f6a3394`: R5's rationale still yields `{1, 2, 7.5, 17}`, and *"exceed the
limit by 1 lakh"* still passes. The same grammar is the natural starting point
for §4.4.2, but that fix runs in the opposite direction (keeping citation
digits *out* of `allowed`) and needs its own design.

#### 4.4.2 The same defect from the other side — found executing step 5

§4.4.1 is citation digits **missing** from `allowed`, so a valid citation gets
rejected. Step 5 found the mirror image: citation digits **present** in
`allowed`, so an invented figure gets accepted.

`flag_compliance` builds `allowed` from `_extract_numbers(rationale)` with
`skip_below=0`. A rationale's section number is therefore whitelisted as if it
were a figure. Correcting R5's citation changed that set — measured:

| | allowed from R5's rationale |
|---|---|
| before (`17(2)(vii)`) | `{2, 7.5, 17}` |
| after (`17(1)(h) (formerly 17(2)(vii))`) | `{1, 2, 7.5, 17}` |

**The correction widens the guard by exactly one number, `1`.** Both effects,
measured on a model rephrasing:

| rephrasing | before | after |
|---|---|---|
| "The excess is taxable under Section 17(1)(h)." — *correct* | rejected | **passes** ✓ |
| "…exceed the limit by **1 lakh**." — *fabricated* | caught | **passes** ✗ |

**This is disclosed rather than avoided, for two measured reasons:**

1. **It is pre-existing.** The *original* repealed-Act rationale already let
   *"exceed the limit by 2 lakh"* and *"17 thousand rupees over"* through.
   Section digits have leaked into `allowed` since before this propagation.
2. **It is unavoidable at this layer.** Every correct citation of the
   provision contributes `1` — `"Section 17(1)(h)"`, `"s. 17(1)(h)"` and the
   "formerly" form alike. The only way not to add it is to keep citing
   repealed law, which is strictly worse.

**One cause, two symptoms.** Citations and figures share a single namespace in
`_extract_numbers`. §4.4.1 and §4.4.2 are the same defect observed in opposite
directions, and a fix that strips citation tokens before extracting figures —
the direction already recorded for §4.4.1, analogous to `output_boundary.py`'s
`_IDENTIFIER_TOKEN` — closes both at once. That work is running as a separate
task; **this finding belongs in its scope**, because a fix for §4.4.1 alone
could be written that leaves §4.4.2 standing.

**Designed in `RATIONALE_GUARD_CITATION_DESIGN.md` (`54e139f`). Not yet
implemented. Three decisions are open (its §7).** The §4.4.1 fix did turn out
to leave this standing (see the correction under §4.4.1). Two statements above
are overtaken by that design:

- *"That work is running as a separate task"* no longer holds. It ended
  without this, and this now has its own design.
- *"It is unavoidable at this layer"* holds only while `allowed` is built from
  unstripped text. If references are stripped from the rationale **and** from
  the rephrasing, both of the rows above come out right: the correct citation
  passes and the fabricated "1 lakh" is rejected. That was measured on a
  prototype in the design's §5, not merely argued.

The design's inventory also found this is wider than `flag_compliance`.
`evaluate_band_guardrail` has the same leak (`epfo_ceiling`, `80ccd2_cap`),
and the union across flags lets one flag's figures ground another's text,
including lines returned in swapped order. See its §2.3.

#### 4.4.3 Two user-facing citations with no coverage of any kind

Recapturing the pipeline baseline for step 5 showed its fixture contains R5's
compliance `rationale` but **not** `ai_layer.py`'s `epfo_ceiling` guardrail
rationale, which step 5 also changed. With `applicable_sections` (§4.4), that
makes two user-facing statutory citations that no unit test, no fixture and no
characterization baseline would notice changing.

---

## 4.5 What step 3 revealed when run on its own

Recorded as corrections to this design, made while executing step 3. Every one
of them was found by running the step in isolation and reading the actual
failures — none by re-reading the plan.

### 4.5.1 The citation data is not artefact-neutral

§4.1 called the five citation fields *"no emitted text changes"* and §5 put all
artefact regeneration in step 5. **Wrong.** `provision`, `instrument` and
`citation_checked_on` are rendered into `docs/CA_REVIEW_PACKET.md` and
`docs/LEGAL_REVIEW_QUEUE.md`. Predicted 4 failures; got **7**:

| Failure | Actual cause, from the failure line |
|---|---|
| `test_the_committed_packet_matches_what_the_generator_produces` | `CA_REVIEW_PACKET.md is stale.` |
| `test_the_committed_queue_matches_the_generator` | `queue is stale.` |
| `test_a_mislabelled_worked_example_fails_generation` | Fails at **L831**, its closing `--check`. It *reached* 831, so every assertion about mislabelled examples passed — a downstream symptom of the stale packet, not a broken mechanism. |

The distinction §4.1 needed was not *emitted vs structural* but **user-facing
vs reviewer-facing**. R5's `rationale` — what a user sees on a flag — is still
byte-identical. The reviewer artefacts are not, and cannot be, because they
exist to render exactly this data. **They are regenerated in step 3**, since a
data commit with knowingly stale artefacts would fail its sync tests for
reasons unrelated to the pins.

### 4.5.2 A fifth pin, in a different file

Regenerating cleared those three and **unmasked** a failure that had been
hidden: `test_legal_claims.py::test_the_worst_item_is_first_not_the_easiest`,
five subtests. It hardcodes `queue.index("### R5")` as the worst item.

§2.2 listed three pins and §4 one more, all in `test_compliance_rules.py`. The
blast radius was mapped by grepping that file. **The fifth pin lives in
`test_legal_claims.py`**, which is why it was never seen.

**It was green for the wrong reason until regeneration.** It reads the
*committed* queue. While that artefact was stale it still listed R5 first, so
the ordering test kept passing against current data that no longer supported
it. What made that safe is that the sync test fails *first* — the ordering
assertion is only trustworthy because a separate test guarantees the artefact
it reads is current. Neither test is sufficient alone.

Its failure is correct. R5 now has a verified citation and ranks 21st of 23.
Retarget in step 4 by the same both-states pattern as §2.2: assert the real
queue has **no** tier-1 item, and inject a synthetic superseded item to prove
it still outranks TE1/TE2/TE3/R1/TE4.

### 4.5.3 The queue renders an empty tier as silence

The ranking is four tiers; R5 was the **only** tier-1 item ("cites law that has
been superseded"). The regenerated queue's headers are now:

```
## 2. Asserts law with no citation recorded anywhere
## 3. Citation attempted, no primary source reached
## 4. No human has signed off
```

`render_document()` only emits a header when a row arrives, so **tier 1 simply
disappears** and the list opens at "2.". That is §2.1 violated at the rendering
layer: "none cite dead law, checked" becomes indistinguishable from "that check
did not run", and a numbered list starting at 2 reads as a deletion.

The CA packet already does this correctly — *"**0 rule(s) cite an instrument
that has been superseded:** none."* — so the fix has a precedent in the same
repository. **Not fixed in step 3**: it is a generator mechanism change and
belongs with step 6.

### 4.5.4 The stale 403 claim is hardcoded in two generators

The CA packet's *"Official government sites returned HTTP 403 or refused
connections across repeated attempts"* and the queue's *"Primary legal sources
return HTTP 403 from the environment this was built in, confirmed
independently by two people"* are both now known false — the sites were
reachable by browser throughout. The queue's version also justifies a design
choice (*"It does not fetch anything, on purpose"*) on that premise.

Same class as §3: hand-written prose restating a fact, with nothing binding it
to reality. Two instances. Step 6/7.

**The step-3 packet is knowingly self-contradictory** until step 6: L124's
hardcoded question says R5 *"cites Section 17(2)(vii) of the Income-tax Act,
1961"* while L134, derived from data, says *"0 rule(s) cite an instrument that
has been superseded: none."* That is §3's prediction, now demonstrated.

**Resolved in step 6.** The regenerated packet contains no `17(2)(vii)` and no
`1961`; only the derived *"0 rule(s)… none"* line remains.

## 4.6 What step 6 found

### 4.6.1 The mechanism's first catch was the real stale question

Order was deliberate. R5's **old** question was given its honest predicate
(`cites_superseded_law`) and the refusal wired in **before** the question was
rewritten, then the generator was run:

```
error: the packet would ask a CA a question whose premise is no longer true.
  R5: asked on the basis that R5 cites superseded law — that no longer holds.
  Rewrite or remove the question — do NOT loosen its condition to match.
```

Exit 1, R5 alone named, R1–R4 not flagged, and the packet on disk
byte-identical — the refused run wrote nothing. A synthetic test proves a check
*can* fire; this proves it fires on the case it was built for.

### 4.6.2 Four of five questions bind to a structured field; one cannot, and is justified

| Q | Condition | Kind |
|---|---|---|
| R2, R4 | `not threshold_origin` | structured — the field that exists to answer "where did this number come from" |
| R3 | `claim_type == CONVENTION` | structured, exact |
| R5 | `citation_is_checked and not implementation_is_reviewed` | structured |
| R1 | `"Code on Wages 2025" in rationale and not implementation_is_reviewed` | **free text, deliberately** |

R1's is the one containment check, and it is not the §8 anti-pattern: that
question's *subject* is a phrase in R1's emitted text, so checking for the exact
phrase checks the thing asked about rather than inferring meaning from wording.

**Refinement over §3.1:** each entry also carries `depends_on`, the condition
in words. §3.1 proposed a bare lambda, whose failure message would be a lambda's
repr. A stale question now says *what changed*.

### 4.6.3 R5's rewritten question surfaces the superannuation gap to the CA

The citation half is gone because it is answered. The implementation half
remains and is sharper: s. 17(1)(h) aggregates **three** funds, the rule sums
two, and the tool models no superannuation — exact under an assumption nobody
signed off. That is now *asked* in the packet. It is **not** recorded as a
`known_divergence`, which remains an open decision (step 5's report).

The rewritten question deliberately does not restate R5's section number,
instrument or check date. Those are structured fields; retyping them into prose
is how this list became a second source of truth.

### 4.6.4 Sabotage — three runs, one of them initially invalid

| Sabotage | Failed | Stayed green, correctly |
|---|---|---|
| **C** — `stale_active_rule_questions()` returns `[]` | caught_and_named, refuses_to_write | **true_premise** — the empty-list test, green against a broken check, which is why the other two exist |
| **D** — restore the silent skip of empty tiers | rendered_in_order (tier=1), empty_tier_says_so | worst_tier (reads rows, not rendering) |
| **E** — empty marker under every tier | empty_tier_says_so: *"an occupied tier claims to be empty"* | rendered_in_order, worst_tier |

**The first run of C tested nothing.** It reported `Ran 1 test … _FailedTest`:
the three test names were held in an unquoted shell variable, and zsh — unlike
bash — does not word-split one, so unittest received them as a single argument
and failed to load it. That output was a loader error, not a result, and was
discarded rather than counted. Re-run with the names written out: `Ran 3 tests`.

**D first went red as an ERROR, not a FAIL.** The section-slicing helper raised a
bare `ValueError: substring not found` when tier 1's header was missing — a
detection, but one that named nothing. The helper now asserts with a message and
D re-runs as two clean FAILs.

### 4.6.5 A §8 slip caught before running

The empty-tier marker was first `"None."`. A two-word marker can occur by
coincidence inside an item's own provision or description text, and then *"an
occupied tier does not carry the marker"* fails for a reason unrelated to
rendering. It is now a distinctive sentence, bound by name (`EMPTY_TIER`).

### 4.6.6 Found outside step 6's scope: the unverified act number is already in five claims

The sabotage-D failure output dumped the whole rendered queue, and it shows
**TE1, TE2, TE3, TE4 and PE4** in `legal_claims.py` all recording their
instrument as **`Income-tax Act, 2025 (Act 30 of 2025)`**.

That is exactly the act number deliberately *not* written into R5, because it
was never verified. So the repository now spells one instrument two ways, and
the more authoritative-looking spelling carries the number nobody checked.
**Not changed here** — it is `legal_claims.py` data, outside this propagation —
but it undercuts the R5 decision unless it is resolved one way or the other:
verify the number, or remove it from all five.

### 4.6.7 Two sessions shared one Postgres, and one suite run was invalid

A second session was working in this repository during step 6. Our full-suite
runs overlapped once. Mine reported **491 run, 1 failure + 38 errors**, every
one in `test_auth` / `test_identity` (Postgres-backed), in **74s** against a
normal ~175s. The other session's overlapping run failed identically.

"Probably interference" was treated as a hypothesis, not a finding: after
confirming no `unittest` process was alive, a clean re-run gave **491 OK in
178s**. The two sessions now use an explicit request/go handshake before any
suite run.

---

## 5. Sequencing

Separate commits, in this order. **Do not reorder or combine.**

1. **Correct `tax_engine.py`'s false retention claim.** Standalone, because it
   is the one place the repository asserted a verification result that was
   wrong, and burying it inside a citation update hides that.
2. **Correct the README Schedule II → Schedule III error.** Unrelated to R5;
   found in the same lookup.
3. **R5 citation data** (§4.1) **+ regenerate the two reviewer artefacts**
   (§4.5.1). User-facing emitted text byte-identical. Commits **knowingly red**
   at exactly the five pins of step 4 — reported, not hidden in a combined
   commit.
4. **Retarget the ~~three~~ five pins** (§2.2, §4.5.2), with the sabotage run
   named. Four in `test_compliance_rules.py`, one in `test_legal_claims.py`.
5. **R5 emitted text** (§4.2) + regenerate artefacts. Behavioural, separate
   from step 3 by the standing rule.
6. **Packet-generator predicates** (§3.1), **plus the queue's empty-tier
   rendering (§4.5.3)**. Generator mechanisms, their own tests.
7. **Investigation prose** (§4.4) **and the hardcoded 403 claims in both
   generators (§4.5.4).** The generator prose changes regenerate artefacts, so
   that half is not documentation-only and gets its own commit.

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
