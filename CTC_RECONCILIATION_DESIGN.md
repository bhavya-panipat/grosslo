# Two different amounts of money, subtracted — fix design (D-S2)

**Status:** design only, **awaiting approval.** No code is changed. Decisions
D-S2a to D-S2e (§8) are the owner's.

**Why now.** Found 2026-09-22 by the neighbouring-route sweep
(`NEIGHBOURING_ROUTE_CLAIM_SWEEP.md` §1.1) and recorded as the most severe open
gap. The owner asked for it to be scoped next.

**What scoping changed.** The sweep found one site. **There are three**, and the
worst of them is not the one that was found — it is user-facing negotiating
advice, where the figure can be entirely fabricated.

---

## 1. The defect, stated once

Everything below is the same subtraction:

```
tax on a real structure  −  tax on an optimum built for a different amount of money
```

The difference is then reported as money someone can capture. It is not a saving;
the two terms describe different amounts of pay.

**The root cause is a word.** Nothing in this system agrees on what `ctc` means:

| Meaning | Used by |
|---|---|
| the **stated CTC** — what the offer letter's CTC field says | `optimize()`, the band guardrail, R1's basic-percentage floor |
| the **modelled CTC** — `SalaryStructure.total()`, the five components this tool actually knows about | `treasury_forecast()`, the payout, the EPFO and NPS checks |

The two agree whenever a structure reconciles, which is why this survived four
sweeps. They diverge for ordinary real inputs, and every figure that mixes them
is wrong by the size of the divergence.

**Why real inputs diverge.** A stated CTC routinely contains gratuity, insurance
premiums and bonus provisions. This tool models five components and none of
those. So the stated CTC is legitimately larger than the modelled CTC **for a
correctly entered, entirely valid employee**. This is not malformed input and
must not be designed around as though it were.

## 2. Site A — `/api/batch-audit`, `unclaimed_savings`

```python
current_best = best_regime_for_given_structure(structure, rent_paid, city)   # modelled
optimal      = optimize(ctc=structure.ctc, ...)                              # stated
unclaimed_savings = max(0.0, current_best.total_tax - optimal.total_tax)
```

The route builds `SalaryStructure` straight from the CSV's columns with **no
balancing term**, and validates only `ctc > 0` and `basic > 0`. Nothing
reconciles them.

**Measured, 432-case grid** (CTC ₹6L–₹50L × reconciliation gap −10%…+15% × three
rent levels × metro/non-metro), comparing the figure as shipped against the
like-for-like figure:

| | |
|---|---|
| Cases where `unclaimed_savings` changes | **246 of 432 (56.9%)** |
| Cases where the row flips between clean and flagged | **102 (23.6%)** |
| Cases where `regime_mismatch` flips | **13 (3.0%)** |
| Worst overstatement | **+₹1,44,768** (₹50L, −10% gap: ₹1,93,440 shown vs ₹48,672 real) |
| Worst understatement | **−₹31,824** (₹50L, +5% gap: ₹0 shown vs ₹31,824 real) |

**The common direction is understatement**, because gratuity makes the stated CTC
the larger figure. On the recommended split with a statutory gratuity accrual
inside the stated CTC, the reported saving is **76–79% below** the real one from
₹18L upward.

**The rare direction fabricates.** Where the `ctc` column is *smaller* than the
components, the route reports the whole difference as a saving. On a ₹15,48,000
structure with `ctc` stated as ₹10,00,000: **₹93,756 reported — the employee's
entire tax bill — against a real saving of ₹0.**

`summary.total_unclaimed_savings` sums this across the batch and
`executive-summary-card.tsx` renders it as **"Discovered Annual Tax
Inefficiency"**.

## 3. Site B — `negotiate()`, `total_annual_saving` — the worst one

```python
total_saving = round(current_best["tax_breakdown"]["total_tax"]
                     - recommended_tax["total_tax"], 2)
```

Identical subtraction, reached through `/api/optimize` and `/api/submissions`
whenever an extracted structure is present.

**These routes were expected to be immune, and they are not.**
`_build_current_structure()` makes special allowance the balancing figure —

```python
special_allowance = max(0.0, ctc - basic - hra - lta - employer_pf - employer_nps)
```

— so the as-offered structure normally *does* reconcile to the stated CTC. **The
`max(0.0, …)` clamp is the hole.** When the extracted components already exceed
the stated CTC, special allowance is pinned at zero and the structure
over-reconciles, without limit and without a warning.

**Measured, rent ₹2.4L, metro:**

| Stated CTC | Structure really totals | Overstated by | Saving shown to the user | Like-for-like |
|---|---|---|---|---|
| ₹36,00,000 | ₹36,00,000 | ₹0 | ₹5,990.40 | ₹5,990.40 |
| ₹18,00,000 | ₹22,68,000 | ₹4,68,000 | **₹90,417.60** | **₹0.00** |
| ₹24,00,000 | ₹25,92,000 | ₹1,92,000 | **₹44,928.00** | **₹0.00** |
| ₹36,00,000 | ₹48,60,000 | ₹12,60,000 | **₹3,61,670.40** | **₹0.00** |

**Every rupee of those figures is an artefact.** The structures are already
optimal for the money they contain; the saving exists only because the optimum
was built for a smaller CTC.

**This is worse than Site A in kind, not just in size.** Site A is a dashboard
total. This is `negotiation.points` — advice telling a candidate what to ask
their employer for. Someone acts on it, in a conversation, against a number that
is not real.

### 3.1 The numeric guard does not catch it, and is not failing

`total_annual_saving` is formatted into `NEGOTIATION_SYSTEM_PROMPT` and the
guard grounds the model's output against it. So the guard sees ₹3,61,670 as a
**supplied, grounded** figure and passes prose asserting it.

**The guard is working exactly as designed.** It guarantees that no figure is
invented by the model. It cannot guarantee that a figure handed to it is true.
Worth stating plainly in the design, because "the numeric guard covers the AI
surface" is otherwise a reasonable thing to believe and is not protection here.

## 4. Site C — the correction flow silently converts the gap into taxable pay

`batch-flow.tsx`'s `buildCorrectionRow` posts the audited row's components,
including its `special_allowance`, to `/api/submissions`.
`_build_current_structure()` **ignores the supplied `special_allowance` and
recomputes it** as the balancing figure.

Measured on the ₹36L gratuity row:

| | |
|---|---|
| Components the audit displayed | ₹35,30,736.00 |
| Components the correction rebuilt | ₹36,00,000.00 |
| Special allowance silently raised by | **₹69,264.00** — exactly the gratuity |

So the gratuity, which is not special allowance and is not taxable as salary in
the year it accrues, is absorbed into special allowance, which is. The
correction flow then computes tax on a structure the audit never showed, and its
benefit figure inherits that.

**Consequence for the fix:** correcting Site A alone leaves the audit and the
correction on different structures, which is a new disagreement introduced by a
fix meant to remove one. Sites A and C are one decision, not two.

## 5. What this does **not** reach

Stated as flatly as the D1 §8.7 answer, and checked rather than assumed:

| Surface | Reached? | Why |
|---|---|---|
| `orchestration.route` / `severity` | **No.** | `classify_row(compliance, guardrail)` takes only those two arguments. Neither carries the subtraction. Verified by reading the signature and both call sites. |
| The Compliance Clean Rate metric | **No.** | It reads `orchestration.route`, verified in `executive-summary-card.tsx:24`. |
| `treasury_forecast` and everything under it | **No.** | Built from `structure` and the current tax breakdown; `optimal` is not an input. The funding gate is unaffected. |
| The payout amount and `payout_basis` | **No.** | Derived from the forecast. |
| `excess_contribution`, the EPFO ceiling check | **No.** | Structure-only. |
| The maker-checker gate | **No.** | Nothing here changes who approves anything. |

**What it does reach:** `unclaimed_savings`, `total_unclaimed_savings`,
`clean_count`, `flagged_count`, `regime_mismatch`, `regime_mismatch_count`,
`negotiation.total_annual_saving`, `negotiation.points`, and the correction
flow's rebuilt structure.

## 6. Design

**The principle: never subtract across two different amounts of money. Optimise
from the money that is actually there, and report the difference rather than
absorbing it.**

### 6.1 One definition, named

Add `SalaryStructure.modelled_total()` as the existing `total()` — no new
arithmetic — and a single helper:

```python
def reconciliation_gap(structure) -> float:
    """stated CTC minus the money this tool models. Positive = the stated
    figure contains something we do not model (gratuity, insurance).
    Negative = the components exceed the stated CTC, which is an input error."""
    return round(structure.ctc - structure.total(), 2)
```

One definition, beside the structure it describes. **Not a second source of
truth:** it is the difference between two quantities that both already exist.

### 6.2 Site A

- `optimize(ctc=structure.total())`, so both sides of the subtraction describe
  the same money.
- The row gains `reconciliation_gap` and `ctc_basis: "modelled"`, so the figure
  says what it was computed against instead of leaving it to be inferred.
- `summary` gains `rows_not_reconciling`, a count — because a batch where most
  rows carry a gap is a fact about the upload that the person reading the total
  should know.

### 6.3 Site B

- **The clamp stays.** *(Corrected during implementation: this bullet first said
  the clamp should stop hiding the overflow, which misdescribed it. A negative
  special allowance is nonsense, so `max(0.0, …)` is the right arithmetic — and
  the components are not lost either, since only special allowance is affected.
  What was actually missing is that **nobody was told it had fired**.)* So the
  clamp is kept and the response records the negative gap instead.
- `negotiate()` receives `ctc=structure.total()`, so its subtraction is
  like-for-like.
- **When the gap is negative, the response says the input disagrees with itself**
  — this is the one place the tool should be loud, because an offer letter whose
  components exceed its stated CTC has been misread, by the extractor or by a
  person, and no downstream figure is trustworthy until that is resolved.

### 6.4 Site C

- `_build_current_structure()` honours a supplied `special_allowance` when there
  is one, and balances only when there is not. The audit and the correction then
  work on the same structure.
- **This changes nothing for the extraction path**, which supplies no special
  allowance and continues to balance exactly as today.

### 6.5 What is deliberately not done

- **No refusal.** A reconciliation gap is the normal state of a valid employee,
  and D-E1's refusal precedent does not transfer: there the input was
  meaningless, here it is ordinary.
- **No change to the band guardrail.** It judges the stated CTC on purpose — an
  approved band is a band on what the company says it is paying. That it cannot
  see a structure that does not reconcile is R8's territory, already recorded,
  and must not be folded in here.
- **No change to R1's basic-percentage floor**, which is a statutory test whose
  base is a legal question, not an arithmetic one. Recorded as a follow-up
  question rather than assumed either way.

## 7. Tests

**Committed failing first**, every expected value derived from the structure in
the same response rather than copied from a run:

- **The identity that is the whole argument:** for any structure, the optimum
  the audit compares against has `total() == structure.total()`. Today it equals
  `structure.ctc`, so this fails wherever they differ.
- **A reconciling row is unchanged**, at several CTCs — the both-states pair, so
  the fix cannot be satisfied by breaking the case that already worked.
- **The gratuity row**: a positive gap produces the like-for-like saving, and
  `reconciliation_gap` equals the gratuity to the paisa.
- **The inverted row**: components exceeding the stated CTC report a negative
  gap and **do not** report a saving that the structure cannot deliver.
- **Site B, the fabrication case**: the ₹18L/₹22.68L structure's
  `total_annual_saving` is ₹0, not ₹90,417.60.
- **Site C**: a supplied `special_allowance` survives `_build_current_structure`;
  an absent one is still balanced.
- **Containment, pinned so it cannot silently break:** `orchestration.route`,
  `treasury_forecast.total_capital_outlay` and the payout amount are byte-identical
  before and after, on a row with a non-zero gap.

**Sabotage:**
- Restore `optimize(ctc=structure.ctc)` at Site A: the identity test and the
  gratuity test fail; the reconciling-row test still passes, proving the tests
  are sensitive to the basis and not merely to the field's existence.
- Restore the `max(0.0, …)` clamp: the Site B fabrication test fails alone.
- Honour `special_allowance` but stop balancing when it is absent: the
  extraction-path test fails, proving both halves of §6.4 are pinned.

**The characterization baseline will move.** `pipeline_baseline.json` captures
`_build_optimize_response`, which contains `negotiation`. Any baseline case with
an over-reconciling structure changes. **It is regenerated only after the
changed cases are enumerated and each one explained in the commit message** —
never to make a test pass.

## 8. Decisions for the owner

| | Decision | Recommendation |
|---|---|---|
| **D-S2a** | Optimise from `structure.total()` rather than the stated `ctc`? | **Yes.** It is the only change that makes the subtraction mean anything. Money this tool does not model cannot be re-split into basic and HRA, so it must not be in the optimiser's budget. |
| **D-S2b** | Fix all three sites, or Site A alone? | **All three, in one sequence, separate commits.** Site C is not optional: fixing A alone puts the audit and the correction on different structures, which introduces a disagreement in the act of removing one. Site B is the most severe and would be strange to leave. |
| **D-S2c** | When components exceed the stated CTC, keep them or keep the clamp? | **Keep them and say so.** The clamp converts a detectable input error into a silent, unbounded overstatement of negotiating leverage. Loudness is correct here precisely because it is not the normal case, unlike a positive gap. |
| **D-S2d** | Report `reconciliation_gap` on the row and `rows_not_reconciling` in the summary? | **Yes.** The gap is real information about the offer letter — for most rows it is roughly the gratuity, and a row where it is not is worth a look. It also stops the next person inferring which CTC a figure used. |
| **D-S2e** | Does R1's 50%-of-CTC floor use the stated or the modelled CTC? | **No change, and I am flagging this rather than deciding it.** R1 implements a statutory test whose base is a legal question — whether the Code on Wages' "wages" is measured against the stated CTC or against modelled pay. It belongs with the CA packet's existing R1 question, not in an arithmetic fix. Changing it silently here would be the worst option. |

## 9. Sequence

Separate commits, full suite after each, under the lock, pushing the SHA
verified:

1. Tests for all three sites, committed red.
2. `reconciliation_gap()` and the Site A basis change.
3. Site B: the clamp, and `negotiate()`'s basis.
4. Site C: honour a supplied `special_allowance`.
5. The baseline regeneration, if §7 shows it moves — changed cases enumerated
   and explained in the commit message.
6. `api-types.ts` and the frontend surfaces: the new fields, and the copy on
   "Discovered Annual Tax Inefficiency". The frontend session's files,
   requested rather than edited.
7. README and `docs/PROJECT_STATUS.md`: close the D-S2 row, record that a
   headline figure moved and in which direction.

## 10. Implementation record (2026-09-25)

Commits are the cherry-picked range on `origin/main`; the shared-tree SHAs they
were authored at differ and are not cited here for that reason.

| Step | Commit | Result |
|---|---|---|
| 1 tests, all three sites, committed red | `bddf3bd` | ERROR — the module failed to import, hiding every assertion. A weak red, so step 2 was split out to expose it |
| 2 `reconciliation_gap()` alone, no caller | `6afb81e` | assertion-level red across Sites A and C, as intended |
| — Site B tests corrected | `64c9dbf` | **they had asserted nothing** (below) |
| 3 Site A, the batch-audit basis | `939e3f7` | every Site A test passes, containment pins hold |
| 4 Site B, the negotiation comparison | `e521d5b` | Site B passes; the baseline moved on one case |
| 5 Site C, the supplied special allowance | `6e7427a` | all three sites pass |
| 6 docs | `8afe5cd`, `d4d1cdf`, `44c8f62`, `cdf5db7` | — |

**Verified: 651 tests OK, no failures, no skips, at `cdf5db7`.** 158.18s of test
time against 171s of wall clock. Static count is 645 `def test_` methods; the
six-test difference is the deliberate subclassing in
`tests/test_query_guard_citations.py`, already documented in the README.

### 10.1 The intermediate test counts in the commit messages are not anchored

Steps 3 to 6 cite "672 tests" (and step 3 "651"). **Those runs happened in the
shared working tree while a concurrent session had uncommitted test files in it,
so the totals correspond to no commit anyone can check out** — the exact fault
the *Claims in documentation must be checkable* rule in `CLAUDE.md` exists to
prevent, committed while quoting that rule elsewhere. The failure *attribution*
in those messages was correct: every failure named belonged to the other
session's knowingly-red step-1 tests. The count was not.

**The one anchored number is the 651 above.** Corrected here rather than by
amending the commits, so the record shows the mistake and its correction rather
than only the corrected state.

### 10.2 The baseline was regenerated in that window, and is re-verified

`tests/fixtures/pipeline_baseline.json` was regenerated against that same
unanchorable tree. Re-verified at a real commit with
`python3 scripts/capture_pipeline_baseline.py --check` at `cdf5db7`: **8 cases,
no drift, nothing missing, nothing added.** The fixture was also hand-written
with `json.dump(..., indent=2, sort_keys=True)` plus a trailing newline, which is
byte-for-byte what that script produces — checked after the fact, having not
noticed the script existed at the time.

### 10.3 Sabotages

| Sabotage | Predicted | Actual |
|---|---|---|
| Site A: restore `optimize(ctc=structure.ctc)` | 4 | **4** — three gratuity subtests and the inverted case. The gap field, `ctc_basis`, the summary count and the containment test all still passed |
| Site B: revert `negotiate_stage` to the stated CTC | 4 | **4** — three fabrication subtests and the baseline case |
| Site C: `or`-style defaulting instead of `is None` | 1 | **1** — the explicit-zero test alone |
| Site C: honour supplied but never balance | 9 | **8** — see below |

**The Site C miss is the informative one.** I expected all seven
extraction-bearing baseline cases to fail; six did.
`extraction_mismatch_components_exceed_ctc` did not, because its components
already exceed the stated CTC, so the clamp had already forced special allowance
to zero and the sabotage is a no-op there. **The over-reconciling case is
invisible to a sabotage of the balancing logic precisely because balancing never
had anything to do there** — which is also why that case sat in the fixture
pinning a fabricated figure for as long as it did.

### 10.4 Two tests of mine that asserted nothing

Both are recorded because the suite's own reds are what caught them, not review.

- **The Site B tests as first committed** called `negotiate()` directly with
  `ctc=structure.total()` and a recommendation built from the same figure — the
  corrected arguments, supplied by hand. They passed with the defect fully
  present. The red run showing them green is what exposed it. Rewritten to go
  through `_build_optimize_response()`, where the wrong argument is actually
  chosen.
- **`test_the_optimum_is_built_from_the_money_that_is_actually_there`** asserts a
  property of `optimize()` itself, so it survives the Site A sabotage. Kept as a
  statement that `optimize()` reconciles exactly, but it is not what catches this
  defect, and the commit message says so.

## 11. Not in scope

R8 and band cost neutrality; the s. 124 cap's DA base and government-employer
rate (TE4's recorded divergences); D-S1's EDLI and administrative charges; D-S3
and D-S4 from the same sweep; anything that dispatches money or changes who
approves it.
