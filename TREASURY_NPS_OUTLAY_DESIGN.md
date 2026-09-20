# The treasury forecast leaves out employer NPS — fix design

**Status:** **D-T1 to D-T4 approved 2026-09-21 as recommended; implemented.**
§9 records the runs and the one prediction §3 got wrong.

**Why now.** Found 2026-09-15 while measuring the employer-NPS tax blast radius,
recorded as an open gap in `docs/PROJECT_STATUS.md`, and now the oldest live
wrong-figure gap left in the repository after the tax double count and the
payout gross/net fix.

---

## 1. The defect

`payroll_breakdown.treasury_forecast()` reports what the company must have
funded before payroll runs. Its four components are net take-home, TDS escrow,
the EPFO challan and professional tax. **The employer's NPS contribution is in
none of them.**

The algebra reduces to `cash + employer_pf`, and employer NPS is neither.
Measured on the recommended structure, ₹2.4L rent, metro, Karnataka:

| CTC | Reported as required funding | Employer NPS, absent | Short by |
|---|---|---|---|
| ₹6L | ₹5,70,000 | ₹30,000 | 5.0% |
| ₹12L | ₹11,16,000 | ₹84,000 | 7.0% |
| ₹18L | ₹16,48,800 | ₹1,51,200 | 8.4% |
| ₹24L | ₹21,98,400 | ₹2,01,600 | 8.4% |
| ₹36L | ₹32,97,600 | ₹3,02,400 | 8.4% |
| ₹50L | ₹45,80,000 | ₹4,20,000 | 8.4% |

**The identity that settles it:** in every case measured,
`SalaryStructure.total()` — this tool's own definition of CTC — equals
`total_capital_outlay + employer_nps`, to the rupee. The contribution is inside
CTC, so it is company money that leaves the company, and the forecast tells
treasury to fund everything except it.

**It is a real remittance, not an accounting entry.** The tool already treats
the employer's PF the same way: `epfo_challan_annual` is employer PF plus
employee PF, remitted by the employer. Employer NPS is remitted on the same
cadence to a different destination. What the tool does not model is the
employee's own NPS contribution, which stays out of scope here.

### 1.1 What it costs, at its real severity

**This one reaches a gate, not only a banner.** `finance-flow.tsx` computes
`requiredFunding` by summing `total_capital_outlay` over pending rows, compares
it to the live RazorpayX balance, and sets `canBulkApprove = !deficit`. So a
balance that is up to 8.4% short of what payroll actually costs is reported as
sufficient, and bulk-approve stays open.

Nothing dispatches money, so no payment fails today. What is wrong is the
decision support: Finance is told it can fund a payroll run it cannot fully
fund, and the error is systematically one-directional — always short, never
over.

**A second consumer, quieter:** every export writes `total_capital_outlay` into
the audit log, so the compliance trail records the same understated figure.

## 2. Design

- **A fifth component**, `nps_remittance_annual = structure.employer_nps`, added
  to the returned forecast and to `total_capital_outlay`.
- **The defining identity becomes five terms**, and the docstring says so:

  ```
  total_capital_outlay = net_take_home_annual + tds_escrow_annual
                       + epfo_challan_annual + professional_tax_annual
                       + nps_remittance_annual
  ```

- **`total_capital_outlay` rises** by exactly the employer NPS. Unlike the
  professional-tax change that added the fourth term, this is **not** a
  re-split of a fixed pool: it is money the company owes that the total did not
  previously contain. The commit message and the docstring must say that
  plainly, because "another component" reads as harmless and this one is not.
- **Nothing else in the forecast moves.** Net take-home, TDS escrow, the EPFO
  challan and professional tax are unchanged.
- **A structure with no employer NPS is unaffected**, and the new field reads
  ₹0 rather than being absent, so a consumer never has to distinguish "no NPS"
  from "this response predates the field".

## 3. What this breaks, and why that is correct

**Three existing tests assert the incomplete identity.** They are pinning
today's behaviour, which is the defect, so each is retargeted with that said —
not deleted:

| Test | Today | After |
|---|---|---|
| `test_finos`'s PT identity check | four terms reconstruct the total | five terms, and the "total unchanged by PT" assertion stays true, because PT really is a re-split |
| `test_review_workflow`'s live-response identity | three terms (it predates PT) | five terms |
| `test_review_workflow`'s payout identity (`PAYOUT_NET_AMOUNT_DESIGN.md` §5) | `paid × 12 + TDS + EPFO + PT == total` | plus `nps_remittance_annual` |

**That third one is mine, written yesterday, and it would fail.** It should:
it asserts that what is paid out plus what is withheld equals the whole cost,
and the whole cost was wrong. The fix makes it true for the first time.

**The pipeline baseline does not contain a treasury forecast** (it captures
`_build_optimize_response`, which does not call it), so the characterization
fixture is untouched. Verified by reading the fixture, not assumed.

## 4. Stored rows, and the figure Finance already summed

Rows stored before this change keep their old `treasury_forecast`, understated
by that row's employer NPS. The Finance queue sums exactly those stored values
for the funding gate, so a queue of pre-change rows keeps under-reporting until
each is decided.

The precedent is D1-4: **a figure someone may have acted on is not silently
recomputed.** The mechanism already exists — `review_queue._row_to_dict()`
flags rows whose `tax_basis` is not current, at read time, without rewriting
anything. **Decision D-T3** is whether to extend it here, and the recommendation
is yes: unlike the tax figures, this one feeds a gate that is about to be used,
and a row that under-reports its own funding requirement should say so where
the approver reads.

## 5. Tests

**Committed failing first:**

- **The CTC identity, which is the whole argument:** for structures with and
  without employer NPS, across several CTCs, `total_capital_outlay ==
  structure.total()`. That is checkable arithmetic about this tool's own
  definition of CTC, not a figure copied from a run.
- **The five-term identity** holds, and each term is the expected one.
- **The total rises by exactly the employer NPS**: same structure, forecast
  before and after, difference equals `structure.employer_nps`. (Expressed as:
  a no-NPS structure's total is unchanged, an NPS structure's total is higher by
  its contribution.)
- **`nps_remittance_annual` is ₹0, not missing**, when there is no employer NPS.
- **Through the real routes**, not only the function: a submission's stored
  `computed.treasury_forecast` and the export response both carry the fifth
  term.

**Sabotage:**
- Remove the fifth term from the total but keep the field: the CTC identity and
  the five-term identity fail; the field-presence test still passes, proving the
  identity tests and not merely the field's existence are what catch it.
- Set `nps_remittance_annual` from employer PF instead of employer NPS: the CTC
  identity fails on any structure where the two differ.

## 6. Sequence

Separate commits, full suite after each, under the lock
(`docs/SUITE_LOCK_PROTOCOL.md`), pushing the SHA that was verified:

1. The tests above, committed red.
2. The fifth component in `payroll_breakdown.treasury_forecast()`, with its
   docstring.
3. The three retargeted identity tests, each named and explained.
4. `api-types.ts`: `nps_remittance_annual` on `TreasuryForecast`. Frontend, and
   the export modal's component list gains a row. Coordinate with the frontend
   session rather than editing its files unannounced.
5. The read-time flag for pre-change stored rows, if D-T3 says yes.
6. README and `docs/PROJECT_STATUS.md`: close the gap row, record that the
   funding total moved and why.

## 7. Decisions for the owner

| | Decision | Recommendation |
|---|---|---|
| **D-T1** | Add employer NPS to the treasury total? | **Yes.** It is inside CTC by this tool's own definition, it is a real remittance, and its absence makes the funding gate systematically permissive by up to 8.4%. |
| **D-T2** | A fifth component, or fold it into the EPFO challan? | **A fifth component.** The EPFO challan is one remittance to one destination; NPS is another. Folding them would make a single figure that reconciles to no real payment instruction. |
| **D-T3** | Flag stored rows whose forecast predates this? | **Yes**, reusing the read-time mechanism from D1-4 rather than recomputing. This figure gates an approval decision that is still pending, which is a stronger case than the tax figures had. |
| **D-T4** | Does the funding gate's behaviour change beyond the number? | **No.** `canBulkApprove` keeps its current rule against a corrected figure. Changing what the gate does with a deficit is a separate product decision and is not proposed here. |

## 8. Not in scope

The employee's own NPS contribution (not modelled anywhere); the
annual-figure-labelled-"Monthly" banner (its own gap row); D-P5, one structure
applied to every employee in an export list; anything that changes who approves
a payout, or that dispatches money.


## 9. Implementation record (2026-09-21)

| Step | Commit | Result |
|---|---|---|
| 1 tests, committed red | `4060a37` | 621 run, 17 assertions failing across all 6 new tests, as designed |
| 2 the fifth component | `a19d912` | 621 run, **2 failures** |
| 3 retargeted identity tests | `83895ae` | 621 OK |
| 5 read-time flag for stored rows (D-T3) | `9bdb1b2` | 625 OK (+4) |
| Sabotage: term present but out of the total | — | 14 assertions fail; **the field-presence test still passes**, which is the point: the identities catch it, not the field's existence |
| Sabotage: term sourced from employer PF | — | 20 assertions fail, including the no-NPS case, where PF is non-zero and the term should be zero |
| Sabotage: stored-row flag never fires | — | exactly its 2 tests fail |

**§3 predicted three tests would break. Two of the three did not.** The
`test_finos` professional-tax identity and the `test_review_workflow` live-response
identity both kept passing, because the structures they run on carry no employer
NPS — so the term this fix adds is zero there. Only
`test_employer_nps_statute`'s tax-independence invariant failed, being the one
identity assertion in the suite written on a structure that actually has a
contribution.

**That is the finding, not a footnote.** The suite asserted this total's identity
in four places and still shipped a total that omitted a whole remittance, because
every assertion but one was made where the omission is invisible. The prediction
was wrong in the direction that matters: I expected the existing tests to be
sensitive, and they were not. They are retargeted to five terms anyway, and the
payout identity test now carries an `nps_opted=True` case with a precondition
asserting the contribution is non-zero, so the coverage gap cannot reopen
silently.
