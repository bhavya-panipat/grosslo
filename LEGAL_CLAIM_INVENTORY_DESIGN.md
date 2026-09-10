# Legal claim inventory — design for Roadmap Phase 2.4

Scope: **make every legal claim this codebase makes visible as data, with its
real verification state attached — most of it honestly `unverified` on day one —
and put a small staleness monitor on top of that inventory rather than in place
of it.**

## 1. Why this phase is not called "legal-change monitoring agent"

The roadmap names 2.4 a legal-change monitoring agent, and that name is
retired here deliberately rather than carried forward unexamined.

The phase exists because `optimizer.py:42` carried a wrong Code on Wages floor
until a human happened to go looking. **A change monitor would not have caught
it.** Two independent reasons, both structural:

1. **`BASIC_PCT_MIN` is not a compliance rule.** It is a module constant with no
   `Rule` object, no `source_url`, no `provision`, no `instrument`. A monitor
   scoped to provisions cited in active rules watches R1 and R5 — two claims —
   and never opens `optimizer.py`.
2. **The value was wrong from birth, not changed underneath us.** It was formed
   by a training cutoff predating commencement. A monitor diffs *now* against
   *a recorded earlier state*; started today it has no "before" for any claim,
   so it catches future amendments and nothing else.

A change monitor over an unverified corpus reports "nothing changed" against a
state nobody ever confirmed. That is the same shape as RLS policies present but
silently unenforced in Phase 1.1 — a mechanism that looks like assurance and
supplies none, which is worse than a visible gap because it stops people
looking.

**So the deliverable is the inventory. The monitor is a small thing on top of
it, and is worth roughly a tenth of the phase.**

## 2. Current state — measured, not assumed

### 2.1 Where the legal claims actually are

The rule set is the *smallest* concentration of legal claims in this codebase.

| File | Claims |
|---|---|
| `tax_engine.py` | `NEW_REGIME_SLABS`, `OLD_REGIME_SLABS`, `STANDARD_DEDUCTION`, `NPS_80CCD2_CAP_PCT`, `CESS_RATE`, `EMPLOYER_PF_RATE`, `PF_WAGE_CEILING_BASIC` |
| `payroll_breakdown.py` | `PT_MONTHLY_TABLE` — five separate **state** professional-tax statutes, each independently amendable |
| `penalty_exposure.py` | EPF s. 7Q, s. 14B (plus a 2024 Ministry notification), s. 398(3), and a *reasoned exclusion* of s. 448 |
| `optimizer.py` | `BASIC_PCT_MIN` — the motivating bug |
| `ai_layer.py` | Sections 11 + Sch. II, 392, 124, 17(2)(vii) |
| `execution_trace.py`, `orchestration.py` | Section 124 |
| `compliance_rules.py` | R1, R5 — **the only two with structured provenance** |
| `README.md` | the entire "Regulatory currency" section |

Roughly 25 claims across 8 files. Two carry provenance.

### 2.2 The verification state of what provenance exists

```
statutory rules:            ['R1', 'R5']
with a VERIFIED citation:   []
reviewed by a human:        []
```

`COMPLIANCE_BREADTH_DESIGN.md` §5 promised this phase "a `source_url` and
`citation_checked_on` per rule to re-check on a schedule". That promise was
written before the access wall was found and **did not survive it**: both
statutory rules sit in `unresolved:`, `citation_is_checked` is `False` across
the whole rule set, and "re-verify these provisions" has an empty input set.
§5 should be corrected to say so rather than left as a handoff that did not
arrive.

### 2.3 The access wall, recorded from direct experience

From R5's own `citation_checked_on`: `incometaxindia.gov.in` returned HTTP 403
on the section pages *and* on the official 2025 Act PDF; `indiacode.nic.in`
refused connection, then 403. Two people, independently. Third-party
concordance resources are reachable.

**This is decisive for the monitor's design and is not designed around.** Any
automated poller's only viable input is secondary sources — exactly what
`citation_is_checked` refuses to accept as verification.

### 2.4 No scheduler exists

`requirements.txt` is `flask, anthropic, python-dotenv, openpyxl,
psycopg[binary]`. No cron, APScheduler, Celery, or worker. And every table runs
under `FORCE ROW LEVEL SECURITY` with transaction-scoped `SET LOCAL
app.tenant_id`, so a background job has no tenant context by default.
"Scheduled" is new infrastructure here, not a configuration choice.

## 3. The non-negotiable boundary

Carried forward verbatim in force from `ORCHESTRATION_DESIGN.md` §3.2:

> an LLM can only *trigger* a re-run or an escalation — never suppress a
> deterministic finding that already fired

Extended for this phase, and binding on every part of it:

**The monitor may notice and flag. It may never decide.** Specifically it does
not deactivate a rule, does not reactivate one, does not edit a citation, does
not change a claim's verification state to verified, and does not mark anything
correct. Every output is a flagged finding for a human. The asymmetry from §3.2
applies unchanged: a wrong flag reaching a person is visible and correctable; a
check silently skipped because software judged it unnecessary is an *absence*,
and absences are what this project keeps failing to notice.

Marking something **verified is a human act**, in the same class as
`reviewed_by`. No automated path writes it.

## 4. Design decisions

### 4.1 Inventory first, monitor second

**Rejected: build the monitor and let the inventory accrete from its findings.**
It inverts the dependency — the monitor's input set is the inventory, and today
that set is empty. It also produces the false-comfort failure in §1: green
results computed against a baseline nobody confirmed.

**Chosen: enumerate the claims first, each with its honest verification state.**
Most start as `unverified`, and that is the phase's actual product. Making the
truth-status of ~25 legal claims *visible* achieves the stated goal — catching
what `optimizer.py` did — by a different and more reliable route than change
detection. Same instinct as porting two tables before any tenancy logic touched
them, and as 2.2's small first batch.

### 4.2 What a claim is

A `Claim` records: an id, the code location it describes, the value asserted,
the legal basis (instrument, provision, source), the verification state, and
who verified it. It does **not** record a predicate, a severity, or user-facing
text — those are rule concepts and do not generalize.

Critically, a `Claim` is *about* a constant; it never becomes the source of that
constant. **No value in `tax_engine.py` moves in this phase.** The
characterization baseline must stay byte-identical, same standard as 2.2 step 1
and 2.1 step 2. This phase is additive metadata over untouched tax math.

### 4.3 Extending R5's mechanism, not paralleling it — the genericity verdict

Checked against the code rather than assumed. **The evidence model is generic;
its container is not.**

Generic already — every one of these reads *only* provenance fields, never
`predicate`, `severity`, `check`, `rationale` or `why`:

- `citation_is_checked`, `cites_superseded_law`, `citation_attempt_unresolved`,
  `implementation_is_reviewed`
- the three-valued `citation_checked_on` convention (never attempted /
  `unresolved:` / a date)
- `instrument` + `instrument_status`, including the rule that a matched text in
  a repealed Act is *not* a checked citation
- `STATUTORY` / `CONVENTION` and the claim-type-dependent evidence requirements
- `threshold_origin`
- 8 of the 10 checks in `protocol_violations()`

Coupled to rule-ness, and these are the only three:

1. **`protocol_violations()` iterates the module-level `RULES` directly** rather
   than taking a collection — it cannot be pointed at anything else.
2. **`rule.is_active` gates two checks** (the reviewer check and the
   superseded-instrument check).
3. **`PRE_PROTOCOL_RULE_IDS`** is a rule-set-specific grandfathering set.

**Chosen: extract the provenance fields and their properties into one shared
structure that both `Rule` and `Claim` carry, and make `protocol_violations()`
take the collection it checks.** R5 stays exactly where it is and keeps
surfacing as it does today — this is a refactor with no behaviour change, held
to the same byte-identical standard, in its own commit before any inventory
entry exists.

**Rejected: a second parallel checker for claims.** It would duplicate the
three-valued citation convention and the superseded-instrument rule, and those
two copies would drift — the exact bug class §3.3 of the 2.2 design exists to
remove, committed knowingly this time.

### 4.4 The asymmetry that does not transfer: a rule can be inert, a constant cannot

**This is not a smaller version of 2.2's candidate gate. It is a fundamentally
different problem, and it has no available safe state.** That is the most
important finding in this phase and it is stated first, plainly, because every
instinct carried over from 2.2 will be wrong about it.

2.2's central mechanism is the candidate gate: an unreviewed rule ships
**inert** and cannot fire. That works because a compliance rule is optional —
the system computes correctly without it. An unreviewed rule costs nothing
while it waits.

**A load-bearing constant runs in production regardless of its verification
status.** `STANDARD_DEDUCTION` is read on every tax computation. There is no
version of this system that runs while it is "awaiting review", no inert state
to park it in, and no way to make it cost nothing while it waits. So:

- A claim's verification state describes **how well we know the value is
  right**, not **whether it is in use**. Everything in the inventory is in use.
- `unverified` is therefore not a safe holding state the way `candidate` is. It
  is a live risk, recorded.
- The gate 2.2 relied on is unavailable here, and no substitute is invented.
  What replaces it is **visibility plus §4.5's internal check** — which is
  weaker, and is stated as weaker rather than dressed up.

### 4.5 The first monitor that works watches the code, not the gazette

The external monitor is blocked by §2.3. An internal one is not, and is
available immediately.

Each `Claim` records the value that was verified. A test compares it against the
live constant. **If `STANDARD_DEDUCTION` changes and its claim's verification
state does not, that is caught in the same commit, locally, with no fetching.**

**The limit, stated as plainly as the capability, because a check whose scope is
overstated is worse than no check.** This catches exactly one thing: **a value
silently changed without its citation being re-verified.** It catches nothing
else. In particular it CANNOT catch the law moving while the code sits still —
which is the failure mode the phase's original name promised and the one that
remains unaddressed by anything automated here. It needs no network, is
unaffected by the access wall, and is a genuine change-detector within that one
scope. Outside it, §4.6's monitor and a human re-verification cadence are the
only answers, and both are weaker than this one.

**Rejected: have the `Claim` read the live constant instead of recording a
copy.** It cannot drift, but it also cannot detect anything — the claim would
agree with the code by construction, which is the `TOTAL_COMPLIANCE_RULES`
derived-once mistake in a new costume. A deliberate second copy plus a test that
compares them is the point, not an oversight.

### 4.6 What the monitor is, once the inventory exists

Small, on-demand first, and constrained by §3. It takes claims whose citation is
`unresolved` or whose instrument is not `in_force`, checks reachable secondary
sources, and **emits a finding for a human**. It never writes a verification
state.

Because its only reachable inputs are secondary (§2.3), a finding it produces is
explicitly *not* evidence — it is a prompt to run the browser lookup. That must
be visible in the finding itself, or the project quietly lowers the bar it
raised in 2.2.

### 4.7 Type A and Type B findings

- **Type B — "an obligation exists that no rule covers."** This *is* a candidate
  rule. It routes through the existing candidate-rule protocol unchanged,
  `threshold_origin` included. No new mechanism.
- **Type A — "this claim's cited provision may have moved."** It creates no rule
  and has no threshold, so `threshold_origin` has nothing to answer. It is a
  change to an existing claim's provenance, and it surfaces exactly the way R5
  does today: by setting `instrument_status` / `citation_checked_on` so the
  shared checker reports it.

**R5 is already a live Type A finding surfaced by an existing check.** That is
the proof the mechanism exists; §4.3 makes it reusable.

## 5. First batch — `tax_engine.py`'s core figures only

Four claims, chosen because they are the highest-stakes numbers in the system
and every tax figure the tool produces depends on them:

- `NEW_REGIME_SLABS`
- `OLD_REGIME_SLABS`
- `STANDARD_DEDUCTION` — `{"new": 75_000, "old": 50_000}`
- `NPS_80CCD2_CAP_PCT` — `{"new": 0.14, "old": 0.10}`

**Deliberately deferred, and named so the boundary is explicit rather than an
oversight:** `CESS_RATE`, `EMPLOYER_PF_RATE` and `PF_WAGE_CEILING_BASIC` are
equally statutory and in the same file; `payroll_breakdown.py`'s five state PT
tables and the scattered section references elsewhere follow after the mechanism
is proven. Same discipline as 2.2's small first batch — prove the shape on a
few before committing to ~25.

**All four will land as `unverified`, and that is the batch working.** Recorded
that way rather than defensively: the purpose of this phase is to make the
truth-status of these numbers visible, and the visible truth is that four of the
system's most load-bearing figures currently rest on nothing recorded. An
inventory that reported anything else on its first pass would be describing a
verification effort nobody performed.

## 6. Decisions needing an explicit call, not a silent default

All four resolved before implementation. Recorded rather than deleted, so the
reasoning behind §4 and §7 stays legible.

- **RESOLVED — verification state is GLOBAL, not per-tenant.** A statutory
  number is true or false independently of which company is asking. The RLS
  machinery being available is not a reason to tenant-scope a fact that is not
  tenant-specific; doing so would imply the answer could legitimately differ
  per tenant, which for a tax slab it cannot. This is a deliberate, named
  exception to the system's RLS posture rather than an absence of one — and it
  is safe precisely because nothing here is tenant data.
- **RESOLVED — the inventory lives in CODE**, matching where the claims it
  describes already live. The diff is the audit trail, same as `reviewed_by`
  in 2.2 §6. A database would enable a cadence and per-tenant state; neither is
  wanted (see above and below).
- **RESOLVED — NO SCHEDULER. It runs in the existing test suite, on every
  run.** §4.5's mechanism is local and network-independent, so CI-on-every-run
  already delivers the real value without inventing infrastructure this
  codebase does not have (§2.4). This is strictly better than a nightly job for
  the failure it actually catches: a value changed without re-verification is
  caught *in the commit that changes it*, not up to a day later.
- **RESOLVED — an aged `unverified` claim WILL fail the build, but not today.**
  Blocking immediately would fail on all four claims on day one, which turns
  the signal into an obstacle to be silenced rather than acted on. It ships as
  a **visible, non-blocking report** first.

  **Named forcing function, with a date, so "not today" does not become
  "never": on 2026-12-09 an `unverified` claim becomes build-blocking.** Chosen
  as ~90 days, deliberately after the CA packet's 2026-10-10 escalation trigger
  (`COMPLIANCE_BREADTH_DESIGN.md` §8.2), so the reviewer conversation has had
  its own deadline first. Same shape as `reviewed_by`'s trigger and §8's dates:
  a condition and an action, not a reminder to re-read this document.

## 7. Sequencing

0. **§8.1 of `COMPLIANCE_BREADTH_DESIGN.md`** — the browser lookup resolving
   R5's citation, due 2026-09-13. It supplies the inventory's **first genuinely
   verified real entry**.

   **It gates the first real `verified` entry; it does not gate steps 1–5.**
   The distinction the lookup would demonstrate — that `verified` means
   something rather than merely existing — is proven in both directions with a
   **probe claim** in the tests, the same way 2.2 proved the candidate gate
   with `R99` while zero candidates existed. Waiting for a human task to
   prove a mechanism that can be proven without one would be the mistake 2.2
   §3.2 already rejected.
1. Extract the shared provenance structure and make `protocol_violations()` take
   its collection (§4.3). **No behaviour change**, byte-identical, own commit,
   R5 still surfacing exactly as today.
2. Add the `Claim` record and the checker over an **empty** inventory — the
   mechanism testable before anything depends on it, same as 2.2 step 4.
3. Add the four `tax_engine.py` claims (§5), all `unverified`, plus §4.5's
   drift test. The characterization baseline must not move.
4. Sabotage-prove §4.5: change a constant without touching its claim, confirm
   the test fails and names the claim.
5. The on-demand monitor (§4.6), emitting findings that state plainly they are
   not evidence.

## 8. What this phase does NOT ship

Any change to a tax value; any scheduled job; any automated write of a
verification state; any claim marked verified without a human; the remaining ~21
claims outside §5's batch; and a CA's approval.
