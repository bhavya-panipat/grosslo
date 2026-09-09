# Compliance rule breadth — design for Roadmap Phase 2.2

Scope: **make the compliance rule set expandable without the drift its current
shape guarantees, and stage new rules through a protocol that ends in human
sign-off rather than in my confidence.** The roadmap calls this "compliance rule
breadth (real CA review)". The second half of that phrase names a step I cannot
perform, and this document is written around that fact rather than past it.

Phase 2.1 is merged (`b5ddd2f`, 277 tests). The compliance stage now has a
declared place in `pipeline.STAGES`, which is what this phase extends.

## 1. Current state — grounded in what the code actually does today

- **Six rules, R1–R6**, matched deterministically in `_check_rules()`
  (`ai_layer.py:330`). That determinism is deliberate and stays: threshold
  matching is never delegated to an LLM, which may only rephrase what Python
  already decided.
- **A rule lives in THREE places, and they have already drifted.** The table in
  `compliance_rules.md`, the `if` chain in `_check_rules()`, and
  `TOTAL_COMPLIANCE_RULES = 6` (`ai_layer.py:378`). R1's rationale is 481
  characters in the table and 375 in the code; the table says the breach carries
  "real penalty exposure" and the code's text does not. Nothing detects that.
  This is the "three separate hiding places" bug class this repo has already
  logged, and going from 6 rules to N is exactly the change that makes it bite.
- **`compliance_pct` divides by a hardcoded 6.** Its consumers are
  `pipeline.metrics_stage`, `ring-metric.tsx` (a bare percentage on a ring),
  `api-types.ts`, and three tests in `test_finos.py` that assert against sixths.
- **Regulatory claims here are verified live, not recalled.** README's
  "Regulatory currency" section records what was checked on 2026-09-01 against
  primary sources, including citation renumbering under the Income-tax Act 2025.
  That standard exists because recall already failed once — see §2.

## 2. The constraint this phase is built around

**I cannot validate Indian tax or labour law from my own knowledge, and this
project has already been burned by exactly that.**

`optimizer.py:42` carries `BASIC_PCT_MIN = 0.50`, labelled STATUTORY FLOOR —
Code on Wages 2025. That value is correct *now* because it was checked against a
live source. The failure mode it corrects is precise: a training cutoff that
predates a law change produces a confidently-worded rule that looks right until
someone happens to check. My cutoff is May 2026; the Income-tax Act 2025 took
effect 1 April 2026. A rule I draft from recall in this domain carries the
identical risk in the identical domain.

A confidently-worded wrong compliance rule is worse than an absent one, because
an absent rule is visibly absent. This phase therefore ships no rule that my
recall is the authority for.

## 3. Design decisions

### 3.1 The candidate-rule protocol

This is the second time this shape has been the right answer. The Code on Wages
fix went: draft → verify against a live primary source → explicit human sign-off
before it touched the codebase. That was a one-off response to a bug report.
Naming it here makes it repeatable, so the next place breadth needs to grow does
not rediscover it.

**The candidate-rule protocol, in six steps:**

0. **Answer the threshold-origin question in writing, before drafting
   proceeds:** *is this threshold's specific number derived from a statute, and
   how do you know?* Recorded in the rule's `threshold_origin` field. Numbered
   zero because it gates drafting rather than following it. A rule with no
   numeric threshold says so — that is a complete answer.
1. **Draft** the rule as a threshold check, in the same deterministic form R1–R6
   already take.
2. **Cite a live-verified primary source** — captured URL, the specific
   provision, and the date verification was performed. Not a recalled section
   number.
3. **Ship INACTIVE.** The rule exists in the rule set with `status: candidate`
   and cannot produce a flag on any structure.
4. **Require an explicit status change to activate**, recording who reviewed it
   and when.
5. **Never let citation-checking substitute for the interpretation step.**
   Verifying that a provision exists and says what is quoted is a different act
   from judging that a given threshold correctly implements it. The first I can
   do; the second is the CA's.

What this buys: the CA reviews *interpretation*, with the citation work already
done and independently checkable, instead of starting from a blank page or
chasing references.

### 3.2 A candidate rule cannot fire, at all

**Rejected: fire but label provisional.** Its own risk is disqualifying rather
than a caveat beside a benefit. Requiring a provisional marker to survive every
downstream consumer — export payload, audit log, routing buckets, the review
queue — is a standing tax on every future piece of code touching compliance
findings, in perpetuity, to preserve a distinction that a firing gate makes
unnecessary. And the moment any flag can originate from an unreviewed candidate,
*every* flag requires the reader to check provenance before trusting it. That
degrades a mechanism that already works, to gain early visibility into rules
nobody has confirmed.

**Rejected: keep candidates outside the rule set, as prose only.** Then approval
is of an idea rather than of a rule, and nothing forces the eventually-coded
version to match what was approved. It is mechanism-only with an extra step.

**Chosen: `status: candidate` rules are inert.** Present in the rule set,
visible to a reviewer, executable in shape, producing nothing. This is
continuous with §3.1 rather than a separate decision: candidates were worth
having *because* they carry zero live risk while giving a CA something real to
act on. Letting one fire reintroduces precisely the risk the gate removes.

**Proof requirement, both states shown rather than only the safe one asserted:**
a test constructs a structure that *would* trip a candidate rule if it were
active, confirms zero flags fire while `status == "candidate"`, then flips the
status to reviewed and confirms the identical structure now fires. Same pattern
as the placeholder source-account marker and the audit-log split — demonstrate
the mechanism in both directions, because a gate asserted only in its closed
state might be closed for the wrong reason.

### 3.3 One source of truth for a rule

**Chosen: rules become data**, each carrying id, predicate, severity,
rationale, status, and provenance (source URL, provision, verified-on date,
reviewed-by). `compliance_rules.md` is generated from that data rather than
maintained beside it, and `TOTAL_COMPLIANCE_RULES` is derived, not declared.

The drift already present between the table and the code (§1) is the argument:
two hand-maintained copies of the same rationale diverged without anything
noticing, and a third copy is about to be added for every new rule.

### 3.3.1 Standing principle: writing a claim down does not verify it

**A falsifiable basis is only better than prose if the claims in it were
actually checked. Writing them down is not checking them — grepping is.**

This is stated as a standing principle rather than as a note about one rule,
because both instances of it in this phase were caught by accident, on the way
to doing something else.

R7's basis named `compute_tax()` as the function that deducts employer NPS. That
function exists — it takes an already-computed taxable income and never touches
`employer_nps`. The claim read as specific and verifiable and would have sent a
reviewer to the wrong function. It was found by grepping for the function name,
not by re-reading the sentence.

**The self-referential trap, which is the generalizable half.** R8's basis
claimed `SalaryStructure.total()` has "zero call sites anywhere in the
repository". That was true when written and **false the instant R8 shipped**,
because R8's own predicate calls it. A reviewer verifying the claim by grepping
would have found it contradicted by the rule asserting it.

The category: **a rule whose basis describes the absence of something can create
that something by existing.** It cannot be caught by checking the claim before
writing the rule, because the rule is what falsifies it. Any future
falsifiable-basis rule that says "nothing does X" or "there are no Y" needs the
check re-run *after* the rule exists, and needs its wording scoped to what stays
true — for R8, that no **production** path enforces the invariant.

Practical rule for drafting: after writing a basis, grep every factual claim in
it, then grep them again with the new rule in place.

### 3.4 `compliance_pct` reports its denominator

**Rejected: freeze the denominator at 6.** Its own framing names the failure
this project keeps finding — a metric that silently stops meaning what its name
says while still returning a plausible number, with nothing forcing a re-check.
Structurally identical to `decided_by` quietly meaning a role string instead of
a person for a whole phase.

**Chosen: the percentage still moves as the rule set grows — that is the
truthful computation — and `rules_triggered` / `rules_total` are reported
alongside it.** The live denominator alone is honest locally and deceptive in
aggregate: two equal-looking percentages from different points in time are not
the same claim, and nothing in a bare number says so. Exposing the ratio lets a
reader reconstruct why, instead of having to already know.

Only ACTIVE reviewed rules count toward the denominator. A candidate that cannot
fire must not make the score look better by inflating the total.

**RESOLVED at the close of the phase — what happens when the denominator is
zero.** Found by the whole-diff read, not by any test. The denominator used to
be the constant `TOTAL_COMPLIANCE_RULES = 6`, so it could never be zero; making
it live rule data introduced the case. It is not reachable from user input — it
needs every rule moved to `candidate` — but that is a real workflow this phase
built, not a hypothetical: a reviewer pulling the whole set for re-review
produces exactly it.

**Rejected: return `100.0`.** It claims full compliance when *nothing was
checked*. That is this project's signature failure — a plausible-looking number
with nothing forcing a re-check — relocated from a stale citation to a
degenerate metric. **Rejected: return `0.0`**, arbitrary in the other direction
and reading as total non-compliance.

**Chosen: raise `NoActiveRulesError`, naming the business event rather than the
arithmetic.** A bare `ZeroDivisionError` surfaces as an unexplained 500 and
tells an operator nothing about why. The message states that every rule is
currently candidate/under review, names which ones, says this is a legitimate
state rather than a bug, and says how to resolve it — the standard
`SchemaMissingError` set, where the message carries both the fault and the fix.

`compliance_ratio()` deliberately does **not** raise: reporting 0 of 0 is
truthful and complete, and a caller that wants to render the state rather than
fail needs it. `classify_row()` likewise keeps routing, reporting zero rules
evaluated, because a row must not become unroutable because the rule set is
under review.

**Every consumer changes in the same pass** — a shape change that leaves one
display showing an ambiguous bare number recreates the problem being solved:

- `pipeline.metrics_stage` — emits the new fields
- `frontend/components/ring-metric.tsx` — shows the ratio, not just the ring
- `frontend/lib/api-types.ts` — declares the new fields
- `tests/test_finos.py` — three tests asserting against hardcoded sixths

### 3.5 Which law the rules describe: forward-looking, the Income-tax Act, 2025

**Decided, with the audit-sweep question resolved from the code rather than
from preference.**

**On what the basis for this is, because the first answer was weaker and is
superseded rather than merely supplemented.** The question was first approached
by reasoning about how audit-sweep would realistically be used — whether anyone
would plausibly point it at a prior year. That argument is defeasible by a
single user doing the unexpected thing, and it would have left the decision
resting on a prediction about behaviour. The argument recorded below is
different in kind: it asks whether the *inputs required to make the transitional
case possible exist at all*. They do not. That cannot be defeated by a user
behaving unusually — only by a code change that adds a period input, which is
precisely what the forcing function at the end of this section catches. The
capability check is therefore the basis for this decision, and the
realistic-usage argument is not a supporting reason for it; it is the weaker
answer it replaced.

Today is inside FY2026-27, which the Income-tax Act, 2025 (Act 30 of 2025)
governs. That is not a future state to prepare for; it is the current one, for
both of this tool's flows.

The one case that could have justified a second, transitional rule set is
return-filing reconciliation: auditing compensation actually paid, or a return
actually filed, for a period before 1 April 2026 would fall under the 1961 Act.
**The code says that capability does not exist.** `/api/batch-audit`'s own
docstring describes auditing "CURRENT (as-offered/as-is) structures ... the real
tax on the structure as it stands today", and more decisively:

- **No route accepts a fiscal or assessment period.** There is no
  `assessment_year`, `financial_year`, or equivalent input anywhere in the
  application.
- **The batch CSV carries only structure components** — basic, hra, lta,
  special_allowance, employer_pf, employer_nps, nps_opted, rent_paid, city.
  Nothing identifies which year a row belongs to.
- The single `FY` reference in the codebase is a comment in `tax_engine.py`
  about slab continuity, not a period parameter.

A tool that cannot be told which year it is auditing cannot reconcile a prior
year's filing. So audit-sweep is current-payroll-health only, "both" is ruled
out on evidence, and **single scope — the 2025 Act — is correct and complete.**

**Named forcing function, so this does not silently become wrong:** if
return-filing reconciliation is ever added — any input that identifies a past
assessment period — this decision must be revisited in the same change. At that
point the tool would genuinely span two statutes, and a single-instrument rule
set would start giving the wrong answer for the older one. That is the trigger
to split, and it should be reconsidered then rather than inherited.

**Independently corroborated after the decision was made.** A reviewer's search
found that FY2025-26 returns still use 1961 numbering and the 2025 Act's
numbering applies from Tax Year 2026-27. That is consistent with this section's
conclusion and arrived from a different direction — a timing fact about the
changeover rather than an argument about this tool's inputs. Recorded as
corroboration, not as the basis: the basis is the capability check above.

**This does not change R5.** R5 remains active, honestly labelled, and a
known-open violation citing the superseded 1961 Act. The scope decision says
which law the rule *should* describe; it does not supply the successor provision
number, which remains unidentified because no primary source was reachable. Two
independent attempts — mine and a reviewer's — hit the same wall, which is
evidence of a genuine access problem for this phase rather than grounds for
lowering the bar on the next citation.

## 4. Concrete shape

**The authoritative field list is the `Rule` dataclass in
`compliance_rules.py`. This section deliberately does not reproduce it.**

It used to. The sketch written before implementation had `verified_on` and
`reviewed_by: str | None`; what shipped has `citation_checked_on` and
`reviewed_by: str = ""`, and gained `check`, `why`, `claim_type`, `instrument`,
`instrument_status`, `basis` and `threshold_origin` as the phase went on. The
sketch was never updated, and **the whole-diff read caught it — a stale
hand-maintained copy of the rule shape, in the design document whose §3.3
argues that a second hand-maintained copy always drifts.** Reproducing the list
here again, correctly, would only reset the clock on the same failure.

So what this section records is the *shape decisions*, which are stable, rather
than the field names, which are not:

- **A rule is one frozen object.** Predicate, both text registers, severity,
  status and provenance travel together, so a rule's justification cannot
  change in one file and not another. Frozen because activating a candidate
  must be a source change visible in a diff, not something application code can
  do at runtime.
- **Evidence is typed by the KIND of claim**, because demanding the wrong kind
  is actively harmful — a convention rule pressured into attaching a provision
  produces a citation that does not say what the rule claims, which is worse
  than no citation because it looks like evidence.
- **The two claims stay separate.** "The cited provision exists and says this"
  and "this predicate correctly implements it" are different assertions, and
  only the first can be established by fetching a document.
- **Citation state is three-valued, not two** — never attempted, attempted and
  unresolved, verified — because "uncheckable from here" is worse than
  "unchecked" and collapsing them loses what a reviewer needs.
- **The instrument is tracked separately from the text**, since a citation can
  match its source perfectly and still point at a repealed Act.

`_check_rules()` iterates `active_rules()`. R1–R6 migrated as active with their
existing text preserved byte-for-byte, so the migration itself changed no
output.

## 5. What 2.2 hands to 2.3 and 2.4

2.3's adversarial verification argues over a rule set that is now data, so it can
name which rule it disagrees about. 2.4's citation-verification skill has a
`source_url` and `citation_checked_on` per rule to re-check on a schedule — the standing
legal-change monitor becomes "re-verify these provisions", not "re-read the
codebase".

2.2 explicitly does NOT ship: any active rule beyond R1–R6, any LLM involvement
in rule matching, or a CA's approval.

## 6. Decisions needing an explicit call, not a silent default

All three resolved before implementation. Recorded rather than deleted, so the
reasoning behind §3 and §7 stays legible.

- **RESOLVED — draft a SMALL first batch, 2–3 candidates, not a comprehensive
  set.** This is the first end-to-end run of the candidate-rule protocol, and
  what is being tested is the process itself: whether the citation format is
  usable, what "reviewed" turns out to require in practice, and how much
  friction the status flip carries. A small batch surfaces that before a CA's
  attention is committed at scale — the same instinct as porting two tables
  before any tenancy logic touched them.
- **RESOLVED — `compliance_rules.md` is GENERATED, not replaced.** The
  human-readable artefact is the property worth preserving, not merely its
  content: it is the file a reviewer, a CA, or a future contributor opens first.
  It becomes derived output from the single source of truth rather than a
  hand-maintained second copy that can drift from the code again.
- **RESOLVED — `reviewed_by` lives in code beside the rule, and the diff is the
  audit trail.** A separate signed-record system is stronger but would be
  infrastructure invented speculatively, before anything needs it.

  **Named forcing function, so this does not become permanent by default:
  revisit the moment a SECOND reviewing party exists.** One reviewer's sign-off
  in a commit is attributable because the commit is attributable. Two make
  "who approved this rule" ambiguous in exactly the way a git blame cannot
  settle — that is the trigger to build the stronger record, and it should be
  reconsidered then rather than inherited quietly.

### 6.1 A convention rule whose threshold is a statutory number

**RESOLVED for every FUTURE rule, by adding step 0 to the protocol (§3.1).
NOT resolved for the specific HRA candidate, which stays held back.**

The claim-type split was introduced to route around the primary-source access
problem: a convention rule needs a stated basis, not a citation, so it could be
drafted without reaching a blocked government site. Drafting the first batch
showed the split **relocated the dishonesty risk rather than removing it.** A
convention rule whose threshold is really a statutory figure ships a statutory
number with no citation, wearing convention clothing — and "typical market
practice" turns out to need the same verification rigour as a citation, against
sources that are equally unreachable.

**The resolution is a process gate, not a code gate, and the distinction is
exact.** `protocol_violations()` now requires every post-protocol rule to carry
a non-empty `threshold_origin`. What the code enforces is *that the question was
answered*. Whether the answer is TRUE is a human judgement and cannot be checked
here — a check would have to know which numbers are statutory, which is the
interpretation step this project refuses to fake. The value is that no candidate
advances while the question sits unanswered, so the next rule cannot slide into
this gap **by omission**, which is how this one nearly arrived.

This does **not** retroactively revisit R1–R8. The pre-protocol set stays closed
and named; R7 and R8 answered the question as part of adding it.

**Still open, and deliberately narrow:** the held-back HRA candidate (*HRA above
50% of basic*). Its threshold is a statutory figure, so as CONVENTION it ships a
statutory number with no citation, and as STATUTORY it needs a provision and
source. Its citation need is folded into the same human-browser lookup task as
R5's successor provision — same tools, same session, two lookups. See
`docs/PRIMARY_SOURCE_LOOKUP_TASK.md`.

A third candidate was drafted for the first batch and then held back: *HRA
structured above 50% of basic*, on the ground that `hra_exemption()` caps the
exemption at 50% of basic (metro) or 40% (non-metro) regardless of rent, so the
excess can never be exempted and is dead weight in the structure.

It is a genuinely useful rule and its basis is internal — it is derived from
this tool's own exemption formula. But **the 50% figure in that formula is a
statutory number**, and that creates a problem the protocol does not currently
catch:

- Labelled CONVENTION, it ships with a `basis` and no citation. That is a
  statutory threshold travelling without a citation, wearing convention
  clothing.
- Labelled STATUTORY, it needs a provision and a source — and those are exactly
  what is unreachable from this environment (§3.5, R1, R5).

`protocol_violations()` detects the reverse error — a convention rule that
*carries* a provision — but nothing detects a statutory number with no
provision attached, and nothing mechanically can: the check would have to know
which numbers are statutory, which is the interpretation step.

**Why this matters beyond one rule:** it shows the access problem is not
confined to the statutory side of the rule set. It reaches any convention rule
whose threshold happens to originate in a statute, which is a large fraction of
plausible payroll rules. That is a narrowing of what can be drafted from here,
and it should be an explicit decision rather than something absorbed silently.

Three ways this could go, none of them taken yet: ship it as CONVENTION with the
tension recorded in its `basis`; hold it until a primary source is reachable and
ship it as STATUTORY; or add a fourth claim type for "derived from a statutory
figure this tool already implements", whose evidence is the implementing code
rather than the statute.

## 7. Suggested internal sequencing for 2.2

1. Migrate R1–R6 to the data structure with no behaviour change — the
   characterization baseline must be byte-identical, same standard as 2.1 step 2.
2. Generate `compliance_rules.md` from the data; delete the hand-maintained
   table so the drift cannot recur.
3. Change `compliance_pct` to report its denominator, updating every consumer in
   §3.4 in the same pass.
4. Add the candidate mechanism and its both-states proof test (§3.2), with zero
   candidates present — the gate is testable before anything depends on it.
5. Draft candidate rules under the §3.1 protocol, each with a live-verified
   citation, all INACTIVE.
6. Produce the CA review packet: each candidate's draft text, its cited
   provision, the captured source, and the structures it would flag.
