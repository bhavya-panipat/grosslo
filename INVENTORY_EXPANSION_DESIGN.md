# Legal claim inventory — expansion design (Phase 2.4, second batch)

Extends `LEGAL_CLAIM_INVENTORY_DESIGN.md`, which built the mechanism and proved
it on four `tax_engine.py` figures. This batch takes it to `optimizer.py`,
`penalty_exposure.py` and `payroll_breakdown.py`.

**Reading the three files first changed the plan in four material ways.** Each
is recorded below rather than discovered mid-implementation.

## 1. The provenance quality is the OPPOSITE of what §10.1 assumed

§10.1 listed these files as uninventoried territory, with `BASIC_PCT_MIN`
leading because it is the one claim with a documented history of having been
wrong. **That ordering still holds. The assumption underneath it does not.**

Measured by reading the recorded provenance in each file:

| Claim | What the repo records | Strength |
|---|---|---|
| `payroll_breakdown.PT_MONTHLY_TABLE` | *"Every slab re-verified live on 2026-09-03 against a primary source"*. Tamil Nadu verified against **tnswp.com's own government PDF, explicitly not an aggregator's paraphrase** — which, when checked, gave numbers that did not match. Karnataka cites a **named amending Act** (Karnataka Tax on Professions… (Amendment) Act, 2025, eff. 1 Apr 2025). | **Strongest in the codebase** |
| `penalty_exposure.py` | Each rate *"independently verified against current sources"*. Names a **Ministry of Labour notification** (eff. 15 June 2024) and a **Supreme Court judgment with a full citation** (*US Technologies International (P.) Ltd. v. CIT*, [2023] 149 taxmann.com 144 (SC)). | Strong |
| `optimizer.BASIC_PCT_MIN` | *"Verified against multiple independent sources on 2026-09-01"* — that is, **secondary** sources, which this project's own standard (`COMPLIANCE_BREADTH_DESIGN.md` §3.1 step 2) refuses to treat as verification. | Weakest of the three |

**So `BASIC_PCT_MIN` leads on risk, not on neglect** — it is the worst-evidenced
of the three *and* the one with a history of being wrong, which strengthens the
case for it leading rather than weakening it. But the flat picture of "~21
uninventoried claims all in the same unverified state" was wrong. Some of this
territory is better evidenced than anything the first batch touched.

This is the concrete vindication of the correction made to §10.1 on 2026-09-10:
asserting that no other claim could match `BASIC_PCT_MIN` would have been a
statement about territory nobody had examined, and examining it found provenance
that beats it.

**Consequence for this batch: some PT claims may legitimately land `verified`.**
That would be the inventory's first genuine `verified` entries, and it exercises
the state in both directions **without waiting for the browser lookup** — which
§7 of the previous design named as the thing that would prove `verified` means
something. It may arrive from an unexpected direction.

## 2. Four structural problems this batch forces

None of these existed in the first batch. All four are real, not hypothetical.

### 2.1 One symbol, many instruments — the mapping is not 1:1

`PT_MONTHLY_TABLE` is **one Python symbol holding five separate state
statutes**, each independently amendable. Karnataka's Act changing has nothing
to do with Telangana's.

One `Claim` per symbol cannot work: `live_value()` reads the whole dict, so
drift in Karnataka alone is unattributable, and one `citation_checked_on` cannot
describe five separately-verified tables.

**Chosen: a claim addresses a symbol PLUS an optional key path into it.**
`live_value()` walks the path. Five claims over `PT_MONTHLY_TABLE`, one per
state, each with its own instrument and citation state.

**Rejected: split the constant into five module-level constants.** That is a
change to working tax-adjacent code to suit its description — precisely the
inversion §4.2 forbids, where the inventory stops describing reality and starts
reshaping it.

### 2.2 Claims whose instrument is not an Act

`instrument` was designed for Acts (`"Income-tax Act, 2025"`) and its only
statuses are `in_force` / `superseded` / `unknown`. This batch has:

- a **Ministry of Labour notification** (EPF s. 14B's 1%/month, eff. 15 June 2024)
- a **Supreme Court judgment** (*US Technologies*, which decides that s. 448
  does not apply)
- a **constitutional ceiling** (Article 276's Rs 2,500 annual PT cap)

A notification can be superseded by a later notification; a judgment can be
overruled or distinguished. `in_force`/`superseded` still fits — but a reader
seeing `instrument: "Ministry of Labour notification, 15 June 2024"` needs to
know it is not an Act, because what it takes to check it differs.

**Chosen: add `instrument_kind`** — `act` | `subordinate` (rules, notifications)
| `judgment` | `constitution`. Defaults to `act`, so nothing existing changes.
It is descriptive only; no check branches on it in this batch.

### 2.3 A claim with no value — the §10.1 open question, arrived

`penalty_exposure.py` deliberately does **not** model s. 448 (formerly 271C), on
the authority of a named Supreme Court ruling. That is a legal claim, and
arguably the strongest kind in the file: it asserts a provision **does not
apply**.

`asserted_value` assumes a number. There is no number here. §10.1 predicted this
question would arrive with the section-citation claims; it arrives earlier.

**Chosen: `asserted_value` becomes optional, and a claim without one is a
`NON_APPLICABILITY` claim** — it asserts that a provision does not govern this
tool's scenarios, and carries the reasoning. §4.5's drift check does not apply
to it and must not silently pass as though it had been checked.

**Rejected: leave it out of the inventory.** A reasoned exclusion is exactly the
kind of thing that rots invisibly — if that judgment is overruled, nothing in
the codebase notices, and the absence of a penalty model is not visible the way
a wrong number would be. An absent thing is harder to notice than a wrong one,
which is this project's recurring lesson.

### 2.4 A claim that knowingly does NOT match the law

Two in this batch, both documented and both deliberate:

- **Maharashtra PT differentiates by gender** (women exempt to Rs 25,000/month
  vs Rs 7,500 general). Not modeled, because nothing in the intake collects
  gender. The table uses the general slab — a **conservative, higher-PT**
  estimate.
- **Tamil Nadu's is a half-yearly assessment** expressed as a monthly
  equivalent. Flagged as an approximation at the call site.

The citation can be verified *and* the implementation correct-as-designed, and
the implementation still deliberately differs from the statute. Nothing in the
current model records that. Left unrecorded, a future reader either "fixes" a
deliberate divergence or, worse, reads `verified` as meaning the code matches
the law exactly.

**Chosen: add `known_divergence`** — free text, empty when the implementation is
intended to match the instrument exactly. A claim carrying one may still be
`verified`: the citation claim and the fidelity claim are different, exactly as
`citation_checked_on` and `reviewed_by` are different.

**A check falls out of this and is worth having:** a claim whose
`known_divergence` is set but which no human has reviewed is a divergence nobody
signed off on. That is a real finding, and the existing reviewer check does not
express it.

## 3. Delhi's zero is a third kind of empty instrument

`"delhi": [(0, None, 0)]` — *"genuinely levies no Professional Tax; no PT Act
has ever been enacted for the NCT of Delhi (Article 276 permits, but does not
require, a state to legislate one)."*

So an empty `instrument` now has three possible meanings: nobody recorded one,
nobody looked, or **there is genuinely none to record**. The third is a positive,
checked finding and must not read as the first.

**Planned: `instrument_kind = "none_exists"`. SUPERSEDED DURING
IMPLEMENTATION, and the constant was deleted.**

Building it showed the tag does not work: **an absence cannot be cited**, and an
`instrument: none_exists` is indistinguishable from nobody having looked — the
very ambiguity it was invented to resolve, moved one field over.

What shipped is stronger. Delhi cites **Article 276**, the provision that
*permits* a State to levy a professional tax without requiring one. That is a
real, citable instrument, and it is what makes Delhi's zero lawful rather than
an oversight. The operative fact is still an absence — no Delhi PT Act — and
that lives in `threshold_origin`, where prose belongs, rather than being
compressed into an enum value that cannot carry it.

`KIND_NONE_EXISTS` was deleted rather than left unused: zero users is this
repository's "undeleted superseded code" pattern.

## 4. Batch scope and ordering — one mechanism per stage

Deliberately staged so no stage introduces two new things at once, and so a
failure is attributable. Same discipline as the first batch's four figures.

**PLANNED AS THREE STAGES; SHIPPED AS FIVE, and the correction was forced by
this section's own rule.** Stage B as written below adds `instrument_kind` AND
the value-less claim; Stage C adds key paths AND `known_divergence`. Both break
the one-mechanism rule in the heading that governs them — a section stating a
discipline and violating it two paragraphs later.

Each was split before starting, into B1/B2 and C1/C2. The stage descriptions
below are left as first written, with what actually shipped recorded here:

| Shipped | Mechanism | Claims |
|---|---|---|
| A | none — uses the existing model | OP1, OP2 |
| B1 | `instrument_kind` | PE1–PE4 |
| B2 | the value-less claim (`NO_VALUE`, `NON_APPLICABILITY`) | PE5 |
| C1 | key paths | PT1–PT6 |
| C2 | `known_divergence` (+ the citation-state guard tracked from C1) | — |

**Stage A — `optimizer.py`, 2 claims. Discharges the priority; needs no new
mechanism.**
`BASIC_PCT_MIN` (statutory, Code on Wages) and `BASIC_PCT_MAX` (convention — the
docstring is explicit that the ceiling is a search-space decision, not law).
Uses the existing model unchanged. **This stage lands first because it is the
claim this whole phase was named after.**

**Stage B — `penalty_exposure.py`, 5 claims. Adds `instrument_kind` and the
value-less claim.**
`EPF_7Q_MONTHLY_RATE`, `EPF_14B_MONTHLY_RATE`, `EPF_14B_CAP_FRACTION`,
`TDS_201_1A_MONTHLY_RATE`, and the s. 448 non-applicability claim.

**Stage C — `payroll_breakdown.py`, 6 claims. Adds key paths and
`known_divergence`.**
Five state PT tables plus the Article 276 / February-bump cap. The largest and
most frequently amended block, and the one most likely to produce the first
`verified` entries.

Each stage: full suite, sabotage-proof the new mechanism, own commit.

## 5. Decisions needing an explicit call

- **RESOLVED — see §5.1, which states the rule generally rather than deciding
  these six claims.** `verified` only where the citation is specific enough for
  an independent party to re-find the source and redo the check; `unresolved:`
  elsewhere, stating that the check was recorded but the trail was not.
- **OPEN — does `reviewed_by` for a claim with a `known_divergence` mean more
  than for one without?** For Maharashtra a reviewer would be signing off not
  just "the table matches the Act" but "using the general slab for everyone is
  an acceptable conservative simplification". That is a bigger assertion.
  Recommendation: same field, but the review packet must show the divergence
  prominently.
- **OPEN — is `BASIC_PCT_MAX` in scope at all?** It is a convention, not law,
  and this is a *legal* claim inventory. Recommendation: include it — the
  docstring markets the [50%, 60%] band as a unit and a reader checking the
  floor will look at the ceiling; recording that one is statute and one is not
  is the point.


### 5.1 STANDING RULE — what `verified` requires

**A `verified` citation must be sufficient for an independent party to redo the
check. Evidence that a past check occurred is not the same thing, and does not
qualify.**

Written as a general rule, not as a judgement on this batch's six claims, so
the next claim carrying a *"trust me, verified"* comment meets this bar
automatically instead of being relitigated as a fresh question.

What it means in practice:

- A named instrument a reader can look up — *"Karnataka Tax on Professions,
  Trades, Callings and Employments (Amendment) Act, 2025"* — **qualifies**. Its
  specificity is the trail.
- A named, locatable document — Tamil Nadu's government PDF on tnswp.com,
  identified as the government's own rather than an aggregator's —
  **qualifies**.
- *"Verified against multiple independent sources"* with no source named **does
  not**. It records that someone checked; it gives nobody a way to check again.
- A date alone never qualifies. `citation_checked_on` answers *when*; the
  qualifying trail lives in `instrument`, `provision` and `source_url`.

**Corollary, and it is the easy mistake: do NOT retroactively supply a trail
that the original check did not have.** If a past comment is specific enough as
written, record it as found. If it is not, it is `unresolved:` — and going out
today to find a better source, then crediting that evidence to a check made on
an earlier date with different evidence, produces a claim that reads as verified
on a basis nobody actually used. That is the fabricated-citation failure in a
subtler costume: the source may even be correct, but the *record* of how this
codebase came to rely on the value would be false.

Finding better evidence today is worthwhile. It is a **new** check, recorded
with today's date and today's source — never a backdated upgrade of an old one.

## 6. What this batch does NOT ship

Any change to a value; any new statutory compliance rule (2.2 breadth work,
explicitly deferred until the citation loop is proven end-to-end on R5 and the
HRA candidate); `tax_engine.py`'s five remaining figures; the `ai_layer.py` /
`execution_trace.py` / `orchestration.py` section citations; and any claim marked
`verified` without an explicit call on §5's first question.

## 7. Standing note: batch tests that quietly become collection tests

**A test written while a collection holds one batch silently becomes a test
about the whole collection.** It reads correctly, passes, and stays wrong until
the *next* batch arrives — at which point it fails for a reason that has nothing
to do with the change being made.

Four instances so far, in three files:

1. `test_the_same_six_rules_exist_with_the_same_severities_in_order` — compared
   the whole `RULES` tuple, freezing its length, when its claim was about R1–R6
   surviving the migration.
2. `test_there_are_no_candidates_yet` / `test_both_reports_run_clean_over_an_empty_inventory`
   — pinned emptiness rather than the property emptiness was standing in for.
3. `test_the_batch_is_exactly_the_four_named_figures` and
   `test_no_successor_provision_was_invented` — asserted across the whole
   inventory when they meant the first four claims.
4. `test_stage_a_added_exactly_two_claims_after_the_first_batch` — the same
   mistake again, **written one message after the pattern was named as a
   three-instance recurrence and proposed for documentation**. Naming a pattern
   and not writing it down is not the same as having written it down, and this
   section exists because that gap produced a fourth instance immediately.

**The rule: when adding the first batch to a collection, assert on the batch,
not on the container.** Filter by the batch's own id prefix, or slice. If the
container's shape genuinely matters — ordering, or that earlier batches did not
move — assert that separately and say so, rather than getting it as a side
effect of an equality check on the whole thing.

**Refinement, found immediately by Stage B2: an id prefix is a PROXY for a
batch, and proxies break.** §7's fix for the fourth instance was to filter by id
prefix instead of comparing the whole collection. Stage B2 then added `PE5` to
the same file and the same `PE` prefix, and the B1 test failed again — for the
same underlying reason, one level in.

The durable version: **assert on the property that actually distinguishes the
batch, not on a stand-in that happens to correlate with it today.** For B1 that
is "claims in `penalty_exposure` that assert a value", which stays true when a
value-less claim joins the same module. A prefix, a length, and a position are
all the same kind of shortcut.

## 8. Standing principle: assert on structured fields, not on strings

**A test that checks for a substring, or inspects a `repr`, can pass because the
text happened to match for a reason unrelated to what it claims to test.** That
shape of assertion is specifically prone to being green for the wrong reason,
and this project has now produced three instances of it in one session:

1. **R8's call-site claim.** Its basis said `SalaryStructure.total()` has "zero
   call sites" — true when written, false the moment R8's own predicate called
   it. A reader verifying by grep would have found the basis contradicted by
   the rule asserting it.
2. **`classify_row` vs `compliance_ratio`.** A sabotage that made
   `compliance_ratio` raise was expected to be caught by two tests; one passed,
   correctly, because `classify_row` never calls `compliance_ratio`. Only one
   of the two was ever the real guard.
3. **The `karnataka` substring.** Deleting Karnataka's key path left the
   one-state drift test green, because the message then contained the WHOLE
   `PT_MONTHLY_TABLE` dict, whose `repr` includes the string `karnataka`. The
   test asserted on claim ids where the distinguishing content was state names.

**The rule: prefer asserting on structured fields over string containment.**
Compare `claim.instrument_kind == KIND_SUBORDINATE`, not `"notification" in
message`. Where a message genuinely is the thing under test — an error's wording
is a real interface — assert on what must be present *and* on what must be
absent, because a substring check alone cannot distinguish "the right content"
from "a larger blob that contains it".

**And sabotage every such test.** All three instances were found by breaking the
mechanism and watching what happened, never by reading the assertion. A green
test proves nothing about *why* it is green.
