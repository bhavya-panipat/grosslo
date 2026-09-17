# Rephrasing alignment: a line must belong to the flag it is served for — design

**Status: design approved 2026-09-16, being implemented (§7).** Approved to be written by the user on
2026-09-15. It closes the residual that `RATIONALE_GUARD_CITATION_DESIGN.md`
§5.4 left open, as corrected in `21c42ee`.

Measurements are on `21c42ee`, with only the model client mocked. Prototypes
ran in a throwaway worktree and were never committed.

---

## 1. The defect, measured

`flag_compliance()` and `evaluate_band_guardrail()` send every failing rationale
to the model in **one** call and assign reply line *i* to flag *i*. After step 3
of the rationale-guard plan, each line's figures are checked against its own
flag's rationale. That check sees a swap only when the swapped lines carry
*differing figures*.

| batch | model's lines, in returned order | served? | what users see |
|---|---|---|---|
| R1 + R4, lines with figures, swapped | "LTA exceeds 10% of CTC." / "Basic salary is below the 50% floor." | rejected | fallback text |
| R1 + R4, **figure-free** lines, swapped | "LTA is higher than company policy usually allows." / "Basic salary is too low for this CTC." | **served** | R1 → the LTA reason; R4 → the Basic reason |
| R3 + R6, swapped | "Special allowance is zero." / "HRA is included but no rent was provided." | **served** | R3 → the special-allowance reason |
| guardrail band + `80ccd2_cap`, figure-free, swapped | "Employer NPS is over its cap." / "CTC is outside the approved band." | **served** | `band_cost_neutrality` → the NPS reason |
| R1 + R4, one line with a figure, swapped | "LTA is higher than policy allows." / "Basic salary is below the 50% floor." | rejected | fallback text |

This **fails open**, in the category of `RATIONALE_GUARD_CITATION_DESIGN.md`
§1.1 severity 2 (misattribution). Every word may be true, but it is attached to
the wrong flag, and `orchestration.py` L99–101 quotes it as that flag's routing
reason.

**How often multi-flag batches occur.** Unknown in production. In
`tests/fixtures/pipeline_baseline.json`, 8 cases carry {0 flags: 5, 1 flag: 2,
2 flags: 1}, and no guardrail section at all. That is a characterization corpus,
not traffic, and it is recorded only to show that multi-flag batches are
ordinary inputs, not contrived ones.

## 2. Why no figure check can close this

The per-line figure check asks "are this line's numbers grounded in this flag's
rationale?". A line with no numbers passes that question for every flag. The
defect is about **which flag a sentence belongs to**, and a sentence with no
numbers carries no figure that could answer it. Any fix is either structural
(make misassignment impossible) or semantic (detect that the sentence is about
something else).

## 3. Options, measured

### 3.1 (A) One model call per flag — structural

Each call is sent exactly one rationale, and its reply becomes that flag's
message. The pairing is set by the code; the model never chooses it.

Prototyped at both call sites, keeping today's all-or-nothing rule (any
rejected line sends the whole batch to fallback) and requiring exactly one line
per reply:

- **Measured:** for R1 + R4, the model is sent `[['R1'], ['R4']]`, two calls,
  and `usage_totals()['calls'] == 2`. Token accounting still sees every call
  because each goes through `_create()`. Correct figure-free lines land on the
  right flags.
- **What it removes:** positional misalignment entirely. A line cannot land on
  the wrong flag by order, because there is no order to get wrong.
- **What it does NOT catch (measured):** an **off-topic line within its own
  call**. If R1's call returns "LTA is higher than company policy usually
  allows.", it is served as R1's message. The model was never shown R4's
  rationale, so this is invention, not a swap. It is the same class as any
  figure-free hallucinated rephrasing of a single flag, which the guards do not
  catch today either.
- **Cost:** N calls instead of 1 for a batch of N. Latency was **not measured**:
  there is no API key in this environment, so no real call can be timed. The
  batch submission route already passes `skip_ai=True` (measured at ~7.9 s/row
  in `flag_compliance`'s docstring), so batch throughput is unaffected. Only
  interactive multi-flag rows pay the extra calls.
- **Blast radius (measured):** across 179 guard-related tests
  (`test_rationale_guard_scope`, `test_rationale_guard_citations`,
  `test_finos`, `test_orchestration`, `test_output_boundary`,
  `test_usage_tracking`, `test_execution_trace`), exactly **8 fail**, all
  multi-flag tests in `tests/test_rationale_guard_scope.py`. They mock one
  multi-line reply, which every per-flag call now receives, so each reply
  has 2 lines and falls back. They need one mocked reply per call; their
  assertions stand.
  `test_usage_tracking`'s source-shape assertions still pass.

### 3.2 (C) Wording-overlap detector — semantic heuristic

Reject a line unless it shares more content words with its own rationale than
with any other rationale in the batch, and at least one.

Measured on 18 cases (a case is one reply, one or two lines): 14 legitimate,
4 that should be caught (3 swaps and 1 off-topic single-flag reply).

| outcome | count |
|---|---|
| legitimate cases served | 13 |
| **legitimate cases rejected** | **1**: R1 "The fixed pay portion of this package is too small." (no shared word with R1's rationale) |
| swaps / off-topic caught | 4 of 4, including the off-topic single-flag case (A) misses |

**The corpus is the weak point, and it is stated rather than hidden.** All 18
cases were written by the author of this document, not sampled from a model.
13 of 14 is not a false-rejection *rate*. It shows the mechanism works on
sentences that echo their rationale's vocabulary, and fails closed on one that
doesn't. A model paraphrasing freely ("fixed pay" for "Basic") would hit that
failure more often, by an unmeasured amount. It is pattern-matching on words,
not verification of meaning. Its failure mode is fail-closed (a good sentence
served as the fallback text), not fail-open.

### 3.3 (B) Keyed reply (JSON by rule id) — rejected, not measured

Ask for `{"R1": "...", "R4": "..."}` and assign by key. This moves the pairing
from a position the model chooses to a key the model chooses. The model still
decides which sentence goes under which key. An offline mock cannot represent
whether a model keys honestly, so there is nothing meaningful to measure here.
(A) removes the choice instead of relocating it.

### 3.4 (D) Ask the model to classify its own lines back — rejected

A second model call to check the first grades model output with model output.
The guards exist precisely so that no model judgement is the last line of
defence.

## 4. Recommendation

**(A), one call per flag, at both call sites.** It is the same principle as
per-line grounding: shrink the unit of trust to one flag, so nothing can borrow
another flag's identity. It closes the measured defect by construction, not by
detection.

**(C) is not recommended as the mechanism**, for the reason above: a heuristic
detector would stand in for a structural guarantee. It is offered as an
**optional second layer** for the one thing (A) leaves open, off-topic
invention within a flag's own call. Decision 2.

## 5. Decisions

**Decided by the user, 2026-09-16:** (A) adopted at both call sites; (C) not built now; all-or-nothing fallback kept. The recommendations below are kept as written.

1. **Adopt (A)?** Recommendation: yes. **Decided: yes.** It costs N model calls for an N-flag
   interactive row; latency is unmeasured here.
2. **Add (C) on top, for off-topic lines?** Recommendation: not now. Measure it
   first on real model rephrasings once an API key is available. The
   self-authored corpus above cannot size its false-rejection cost. **Decided: not now.**
3. **Keep all-or-nothing fallback under (A)?** Recommendation: yes, unchanged.
   Per-flag fallback (serve the flags whose lines passed) is a separate
   behavioural change with its own trade-off: a batch in which the model got one
   flag wrong may have got the others subtly wrong too. **Decided: kept.**

## 6. Tests and sabotage, if (A) is adopted

- The 8 multi-flag tests move to one mocked reply per call, with the same
  assertions.
- New: every model call is sent exactly one rationale, and the call count
  equals the flag count, at both call sites.
- New: a reply with more than one line for a single flag falls back.
- The figure-free swapped cases in §1 become "the model is never shown another
  flag's rationale", asserted from the calls' payloads, because a swap by
  position can no longer be constructed.
- **Sabotage:** send the whole batch in one call again → the one-rationale
  payload test and the call-count test fail. Accept multi-line replies again →
  the multi-line fallback test fails.

## 7. Sequencing, if approved

1. This document.
2. **Behavioural:** (A) at `flag_compliance`, with its tests (including the
   moved multi-flag tests for that function). Full suite, test-ID diff,
   sabotage.
3. **Behavioural:** (A) at `evaluate_band_guardrail`, likewise.
4. **Documentation:** close item (1) of the rationale-guard row in
   `docs/PROJECT_STATUS.md`, recording the off-topic residual (decision 2) in
   its place.

## 8. What this does not settle

- **Off-topic invention within one flag's call** (decision 2).
- **Latency of (A)** on a real model.
- **`negotiate` and `answer_query`** each already make a single call producing
  one answer, so they have no alignment to get wrong. Not affected.

## 9. Implementation record

Full suite with `python3 -B` and the cache cleared, in a worktree at the
commit, under a "request run" / "go" handshake with the concurrent session over
the shared Postgres. Every run below was checked for machine sleep during it
(zero events) and for a clean worktree afterwards.

Each run at these commits also shows `test_theoretical_minimum_never_exceeds_realistic_recommendation`,
which belongs to the concurrent session's tax-engine work and is fixed in its
later `ef85fd4`. It is excluded from the counts below.

| step | commit | suite (vs parent) |
|---|---|---|
| 2, `flag_compliance` | `9fd7bbf` | **571**, +3 by test-ID diff |
| 3, `evaluate_band_guardrail` | `84c8173` | **574**, +3 |

| sabotage | predicted to fail | failed |
|---|---|---|
| 2-1: whole batch sent in each compliance call | `test_each_call_is_sent_exactly_one_rationale_in_flag_order` | exactly that |
| 2-2: compliance accepts multi-line replies | `test_a_reply_that_is_not_exactly_one_line_falls_back_for_every_flag` | exactly that |
| 3-1: whole batch sent in each guardrail call | `test_each_call_is_sent_exactly_one_failing_check_in_order` | exactly that |
| 3-2: guardrail accepts multi-line replies | `test_a_reply_that_is_not_exactly_one_line_falls_back_for_every_check` | exactly that |

**Three runs were discarded, and why.**

1. **Overlap.** The step-3 suite ran while the concurrent session's suite was
   running: 55s instead of ~145s, 112 errors across the Postgres-backed
   `test_auth` / `test_identity` / `test_tenant_isolation` / `test_review_workflow`
   tests. The runner's own `OVERLAP=1` flag caught it. Re-run alone: clean.
2. **Sleep.** An earlier set of step-3 runs spanned machine sleep (12 sleep/wake
   events in one) and picked up a spurious `test_auth` throttling failure, the
   same signature recorded in `RATIONALE_GUARD_CITATION_DESIGN.md` §10. Re-run
   with keep-awake held.
3. **A broken runner, found by reading the output rather than the summary.**
   Widening the overlap-detection pattern with
   `sed s/unittest discover -s tests/-m unittest/g` also rewrote the runner's
   own command into `python3 -B -m -m unittest -q`. Two "runs" exited in three
   seconds with `No module named -m`. The summary line showed no failures. A
   `pgrep` pattern beginning with `-` is also parsed as an option and needs
   `[-]m unittest`. Both fixed, and the pattern was then verified against a
   process whose command line spells `-s` with an absolute path.

**Still open, as designed:** an off-topic line inside a flag's own call
(decision 2, the (C) detector, not built).
