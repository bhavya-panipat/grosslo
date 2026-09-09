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

**The candidate-rule protocol, in five steps:**

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

**This does not change R5.** R5 remains active, honestly labelled, and a
known-open violation citing the superseded 1961 Act. The scope decision says
which law the rule *should* describe; it does not supply the successor provision
number, which remains unidentified because no primary source was reachable. Two
independent attempts — mine and a reviewer's — hit the same wall, which is
evidence of a genuine access problem for this phase rather than grounds for
lowering the bar on the next citation.

## 4. Concrete shape

```python
# compliance_rules.py
@dataclass(frozen=True)
class Rule:
    id: str
    severity: str            # High | Medium | Low
    rationale: str
    predicate: Callable      # (structure, rent_paid) -> bool
    status: str              # "active" | "candidate"
    source_url: str          # captured, live-verified primary source
    provision: str           # the specific section/rule cited
    verified_on: str         # ISO date the citation was checked
    reviewed_by: str | None  # None until a human signs off
```

`_check_rules()` iterates `RULES`, evaluating only `status == "active"`.
R1–R6 migrate as active with their existing text preserved byte-for-byte, so the
migration itself changes no output.

## 5. What 2.2 hands to 2.3 and 2.4

2.3's adversarial verification argues over a rule set that is now data, so it can
name which rule it disagrees about. 2.4's citation-verification skill has a
`source_url` and `verified_on` per rule to re-check on a schedule — the standing
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

### 6.1 OPEN — a convention rule whose threshold is a statutory number

**Not resolved. Raised here rather than decided, because deciding it silently
is exactly the failure the claim-type split exists to prevent.**

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
