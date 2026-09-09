# Pipeline orchestration — design for Roadmap Phase 2.1

Scope: **turn the implicit computation sequence inside
`_build_optimize_response()` into an explicit orchestrator with typed stage
contracts and one shared execution context, changing no number, flag, verdict
or response field.** This is a structural change only. Everything else in Phase
2 — expanded compliance rules (2.2), adversarial verification (2.3), the
legal-change-monitoring agent (2.4) — builds on the structure this creates.

Phase 1 is merged and pushed (`026243e`, 261 tests). Phase 2 depends on its
exit, which is met.

## 1. Current state — grounded in what the code actually does today

The roadmap describes this phase as rebuilding a pipeline "currently separate
API calls stitched by frontend code". **That premise is substantially wrong,
and correcting it is what determines this phase's real scope.**

- **The pipeline is already server-side and already sequenced.**
  `_build_optimize_response()` (`app.py:375`, 98 lines) runs optimize → explain
  → compliance → negotiate → metrics in order, in one function, with real
  ordering logic — not a thin wrapper over four independent calls.
- **Its ordering encodes a decision that must survive.** Compliance checks the
  AS-OFFERED structure, falling back to the recommendation only when nothing
  was extracted. The comment states why: the optimizer enforces a 50–60% basic
  band by construction, so R1 (basic < 50% of CTC) could structurally never
  fire against its own output. Checking the recommendation would be nearly
  circular and would silently report zero risk. A restructure that loses this
  turns compliance into theatre while every test still passes.
- **The one genuinely frontend-stitched seam is a deliberate human
  checkpoint.** `/api/extract` returns parsed fields plus a
  `mismatch_warning`; the user reviews and corrects them; only then does
  `/api/optimize` run with `current_structure`
  (`offer-letter-card.tsx` → `optimize-flow.tsx`). This is human-in-the-loop on
  the single step where an LLM parses an untrusted document.
- **The numeric guard is the constraint everything here answers to.** No LLM
  call may compute, restate with different rounding, or invent a tax figure.
  Enforced twice: `_numbers_ungrounded()` rejects an explanation containing any
  number not traceable to its inputs (falling back to a deterministic
  template), and compliance rules are matched in Python by `_check_rules()`
  before the LLM sees anything, so the LLM can only rephrase — never add,
  remove or reinterpret a flag.
- **The pipeline has many callers.** `app.py` (17 references),
  `tests/test_finos.py` (22), `tests/test_orchestration.py` (15), and others.
  Any signature change is a wide blast radius.

Net: there is a pipeline. It is correct. What it lacks is a *named* one — a
place where the sequence is declared rather than implied by statement order in
a function that has grown to 98 lines and is about to receive three more
stages.

## 2. The guarantee this design has to produce

**Every stage that runs today still runs, in the same order, on the same
inputs, producing byte-identical outputs — and the sequence itself becomes
something that can be asserted rather than inferred.**

Two clauses, and the second is why this phase exists at all:

- *Byte-identical outputs.* Not "equivalent", not "the tests still pass".
  Pinned before the change and compared after (§3.3).
- *The sequence becomes assertable.* Today, nothing anywhere proves the
  compliance stage was invoked.

  **An earlier draft of this section claimed a dropped compliance stage "would
  not falsify a single existing assertion". That was overstated, and measuring
  it rather than asserting it is what showed so.** Removing the stage from the
  pipeline and running the other 261 tests produces 5 failures — so the suite
  does catch this particular sabotage.

  What it does not do is catch it *as itself*. **Zero of those 5 failures name
  compliance.** They are three routing-bucket tests in
  `test_orchestration.TestSubmissionsRouteIntegration` and two in
  `test_review_workflow.TestDiffView` — downstream consumers that happen to
  depend on flags existing. A developer reading that output would investigate
  routing and diff attribution, not a missing pipeline stage. And the coverage
  is incidental rather than designed: it exists only where flags feed some
  other assertion, so it holds for "flags vanish entirely" and gets thinner for
  subtler changes, such as compliance running against the wrong structure.

  The accurate claim is therefore narrower and still sufficient to justify this
  work: **no test asserts that a stage ran, so stage invocation is protected
  only by whatever happens to consume its output downstream.** That is the same
  shape as the guard-ordering bug Phase 1.2 found — two things assumed to agree
  with nothing forcing them to — and §3.4 is what forces them.

## 3. Design decisions

### 3.1 An explicit orchestrator, not a skipped phase

**Rejected: skip 2.1 and go straight to 2.2's expanded rule set.** The honest
version of this option — least churn on validated code is usually right, and
`_build_optimize_response()` is not broken. It loses because there is not one
hypothetical future consumer of the new structure but three already sequenced
immediately after it (2.2, 2.3, 2.4). Skipping does not avoid the refactor; it
relocates it to the moment 2.3 needs somewhere to attach, entangled with new
logic instead of done as its own attributable step. That is exactly what
porting 1.1's tables before any tenancy logic touched them was for: isolate the
structural change from the behavioural one, or lose the ability to say which
broke something.

**Rejected: the full rebuild the roadmap literally describes**, collapsing
extract → optimize into one server-side flow. It removes the human review of
LLM-parsed offer-letter fields. That seam is structurally the same kind of
checkpoint as the maker-checker gate — a human confirming a machine's reading
before it has consequences — and it postdates the roadmap sentence that
describes it as stitching. Optimising for consistency with a stale plan over
consistency with what the system has since proven it needs would be the wrong
trade.

**Chosen: name the sequence, change nothing it computes.** A `pipeline.py`
declaring the stages, their contracts and their order, with
`_build_optimize_response()` becoming a thin caller.

### 3.2 Deterministic control flow only, in this phase

**Rejected: LLM-chosen control flow** (an LLM deciding "this extraction looks
unreliable, re-run it" or "this needs escalation"). The idea is not wrong, it
is early. 2.1 has already promised a pure structural move proven
behaviour-identical; introducing new LLM decision authority in the same change
mixes a structural change with a behavioural one — the precise thing 1.1 step 1
and 1.2 step 2 were built to avoid, applied to control flow instead of a
database or a permission model.

**Rejected outright, not merely deprioritised: deciding per stage, case by
case.** "Each stage argues its own case" is the condition that produced the
guard-ordering bug — no stated principle forcing two independent decisions to
agree, until one silently disagreed for a whole phase. That shape is not worth
repeating at the control-flow level.

**Chosen: Python decides what runs next, from values the deterministic engines
already produced.** LLMs stay exactly where they are — phrasing explanations,
parsing text — behind the guards that already contain them. "Multi-agent" here
means separable, individually-testable stages, not stages that choose their own
path.

**Recorded now for 2.3's design doc, while the reasoning is fresh: control flow
needs a guard with the same seriousness as numbers, not a lesser one.** When
2.3 gives a second opinion influence over escalation, it must be scoped so an
LLM can only *trigger* a re-run or an escalation — never suppress a
deterministic finding that already fired — and must be labelled `ai_backed`
like everything else here. The reason is asymmetric visibility: a wrong number
reaching a human is visible and correctable, whereas a compliance check
silently skipped because an LLM judged it unnecessary is an *absence*, which is
harder to notice and potentially worse.

### 3.3 Characterization tests come first, and this is a stronger bar than 1.1's

**Rejected: rely on the existing 261 tests.** They cover tax math and
compliance rules heavily, and per §2's correction they are not blind to a
dropped stage — but their coverage of it is incidental, arrives as failures
that name the wrong subsystem, and thins out for subtler restructures than
"delete the stage". They assert properties at known call sites and have never
had to prove the sequence runs intact, because before 2.1 there was no
separable orchestration layer capable of dropping a stage.

Measured, both ways: with compliance removed from the pipeline, the
characterization baseline fails 8 of 8 cases and names each one; with the
as-offered ordering inverted — the §1 failure that turns compliance into
theatre — it fails the 3 cases that have flags to lose. Both are caught
immediately and both point at the actual change.

**Chosen: pin the full pipeline's exact output before touching anything**, then
prove the migration output-identical against that captured baseline rather than
arguing it. This is a stronger requirement than 1.1 step 1's precedent, not an
equivalent one: that step ported inert rows with no behaviour change intended,
so the existing suite was already adequate. This one restructures the sequence
of computation itself.

**The input spread is deliberately not happy-path**, because a characterization
suite built from typical inputs misses exactly the boundary conditions most
likely to shift during a restructure. It must include, at minimum:

- the **Code on Wages** statutory-floor boundary (the gap this project already
  found once, by luck rather than process)
- an **EPFO aggregate-ceiling violation** (R5)
- a **zero-flag clean pass**, so "nothing fired" is pinned as an outcome too
- an **extraction-mismatch** case, exercising `mismatch_warning`
- the **naive-baseline zero-optimization** case, where `total_saving <= 0` and
  `negotiate()` zeroes `changed_levers`

### 3.4 Stage invocation is observable, not inferred

Each stage records that it ran, into the shared context — so "the compliance
stage executed" becomes an assertable fact rather than something inferred from
a field being present. This is what makes §2's second clause testable, and it
is the direct answer to the failure mode in §2: a dropped stage must break a
test.

**`stages_run` IS exposed in the API response** (§6's resolved decision, which
reverses an earlier draft of this section that kept it internal). The reasoning
that changed it: a hidden, test-only assertion that a stage ran is verifiable
only by the test suite — nobody outside the code can confirm it. A visible
field makes "the compliance stage executed" a checkable fact for the frontend
and for any future audit trail, which is the same reasoning behind
`orchestration.py`'s `checked` field recording what was evaluated including
what did NOT fire.

It does not duplicate or replace `execution_trace.py`, which builds the
human-readable narrative the UI shows. This is the machine-checkable list of
what ran.

## 4. Concrete shape

```python
# pipeline.py
@dataclass
class PipelineContext:
    ctc: float; rent_paid: float; city: str; nps_opted: bool
    current_extracted: dict | None
    extraction_ai_backed: bool
    skip_ai: bool
    result: dict | None = None            # optimizer output
    current_structure: SalaryStructure | None = None
    response: dict = field(default_factory=dict)
    stages_run: list[str] = field(default_factory=list)

STAGES = (optimize_stage, current_structure_stage, explain_stage,
          compliance_stage, negotiate_stage, metrics_stage)

def run(context) -> PipelineContext:   # calls each stage in order, records it
```

`_build_optimize_response()` keeps its exact signature and return shape
(`(response, result)`) and becomes a caller of `run()`. That is deliberate: 54
call sites across `app.py` and four test modules reference this pipeline, and a
signature change would make the diff impossible to review as a pure
restructure.

Stage order is declared in `STAGES` — including the §1 constraint that
`current_structure_stage` precedes `compliance_stage`, which today is enforced
only by statement order and a comment.

## 5. What 2.1 hands to 2.2, 2.3 and 2.4

A named place to attach, and a contract to attach with. 2.2's expanded rules
extend `compliance_stage`'s rule set without touching the sequence. 2.3's
adversarial verification becomes a stage after compliance, reading its output
from the context — with the control-flow guard from §3.2 as its explicit
starting principle. 2.4's legal-change monitoring runs outside this pipeline
entirely but writes the rule set 2.2's stage reads.

2.1 explicitly does NOT ship: any new rule, any new LLM call, any change to
what a stage computes, any change to the extract → optimize human checkpoint,
or the batch path sharing the orchestrator (§6). The single deliberate addition
to the response is `stages_run` (§3.4), named here because everything else
about this phase claims to change nothing.

**And that addition PERSISTS, which this document did not originally say.**
`POST /api/submissions` stores the pipeline's response verbatim into
`submission_rows.computed_json`, so every row created from now on carries the
stage list. Found by reading the assembled diff, not by a failing test — the
characterization baseline pins the function's return value, not what a route
does with it.

Kept rather than suppressed, because it makes §3.4's argument stronger rather
than weaker: the auditable claim becomes "the compliance stage ran for THIS
stored row", checkable long after the request is gone, instead of only "the API
said so at the time". It is additive, and rows stored before 2.1 simply lack
the field — which is why `stages_run` is optional in the TypeScript type. But
a data-shape change in a phase whose whole claim is that it changes nothing has
to be stated, not left for someone to discover in a database.

## 6. Decisions needing an explicit call, not a silent default

All three resolved before implementation. Recorded rather than deleted, so the
reasoning that produced §3.4 and §7 stays legible.

- **RESOLVED — the characterization baseline is a COMMITTED FIXTURE**, not
  regenerated at test time. A regenerated baseline only proves the code agrees
  with itself, and cannot catch a pre-existing regression. It has to be a fixed
  point that requires a deliberate change to move — the same property that
  makes a commit a real checkpoint rather than a description of the present.
- **RESOLVED — `stages_run` IS exposed in the API response.** This reverses the
  earlier draft (§3.4 updated accordingly): a test-only assertion that a stage
  ran is confirmable only from inside the test suite, and the fact that a
  compliance check executed is exactly the kind of thing an audit trail should
  be able to state. Same reasoning as `orchestration.py`'s `checked` field.
  It is a new public field, which this phase otherwise avoids — called out
  rather than slipped in, since the phase's whole claim is that it changes
  nothing.
- **RESOLVED — `/api/batch-audit` stays separate for this change.** 2.1's
  justification rests on being a narrow, provably behaviour-identical move, and
  folding in a second, differently-shaped endpoint makes "same test count
  before and after" harder to trust cleanly. It shares the orchestrator later,
  as its own small follow-up with its own before/after, once this proves out.

## 7. Suggested internal sequencing for 2.1

1. **Characterization tests first, before any restructure** (§3.3), including
   the five boundary cases named there. Establish the baseline against the
   CURRENT code and confirm it passes against the current code — a baseline
   that has never gone green proves nothing.
2. Add `pipeline.py` with the context and stages, and make
   `_build_optimize_response()` call it. No behaviour change.
3. Add the stage-invocation assertions (§3.4): a test that fails if a stage
   stops running, which today no test would.
4. Verify: **the same test count before and after, with any delta named
   test-by-test rather than asserted as design intent** — the standard 1.1
   step 1 and 1.2 step 2 both held to, plus the characterization baseline
   matching byte-for-byte.
