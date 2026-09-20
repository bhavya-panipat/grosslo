# The payout payload's amount is gross salary — fix design

**Status:** **D-P1 to D-P5 approved 2026-09-21 as recommended; implemented.**
§9 records the runs, including one prediction that was wrong.

**Why now.** Found 2026-09-15 while measuring the employer-NPS blast radius, and
recorded as an open gap with the owner's instruction: *scope it soon, well before
Phase 3's execution capability exists, because it is cheap to fix now and
expensive to discover the day it first matters.*

---

## 1. The defect

`app._build_composite_payout()` fills the RazorpayX Composite Payout `amount`
from the whole monthly cash salary:

```python
net_monthly = round(
    (structure.basic + structure.hra + structure.lta + structure.special_allowance) / 12, 2)
amount_paise = int(round(net_monthly * 100))
```

Nothing is withheld: not TDS, not the employee's PF, not professional tax. The
variable is named `net_monthly` and holds a gross figure.

- **`payroll_breakdown.net_monthly_disbursement()` already computes the right
  shape** — monthly cash minus employee PF minus monthly TDS — and **has no
  callers anywhere in the repository.** The correct function exists, unused,
  beside the wrong inline arithmetic.
- **No test pins the amount.** `test_new_hire_export_returns_razorpayx_payload_with_real_bank_details`
  asserts the bank account and IFSC only.
- **Present since `90e43cc` (2026-08-31),** in both payout-producing routes:
  `/api/export-razorpayx` and `/api/submissions/<id>/rows/<i>/export`.

### 1.1 What it would cost, stated at its real severity

**Nothing dispatches money.** Every route builds a payload; no code path calls
RazorpayX to pay anyone, and that constraint is not being touched here.

**But the payload is built to be used.** The export modal renders it and offers
*Copy*, so the realistic path is a person pasting a schema-accurate payload into
RazorpayX. Measured on the recommended structure at ₹18L CTC, Karnataka:
the payload pays **₹1,39,200 a month** where the employee is owed
**₹1,17,851.47** — an overpayment of **₹21,348.53 a month, ₹2,56,182.36 a year,
per employee**. The difference is exactly what the tool's own forecast says
should have been withheld: employee PF ₹10,800, TDS ₹10,340.20 and professional
tax ₹208.33 a month. So each payment overpays the employee and leaves the TDS and
PF unremitted.

## 2. What "net" has to mean here

`treasury_forecast()` splits the same pool four ways, and its identity is the
place to take the answer from:

```
total_capital_outlay = net_take_home_annual + tds_escrow_annual
                     + epfo_challan_annual + professional_tax_annual
```

`net_take_home_annual` is exactly the amount that reaches the employee's bank
account: cash, minus employee PF, minus total tax, minus professional tax. The
payout `amount` should be one twelfth of it.

**This is not the same as `net_monthly_disbursement()`**, which withholds PF and
TDS but **not** professional tax, because it predates the PT feature. Measured on the same ₹18L structure it returns ₹1,18,059.80 against the correct
₹1,17,851.47, so using it unchanged would still overpay by the professional tax —
₹208.33 a month as the forecast spreads it (₹200 in eleven months, ₹300 in
February).

## 3. Design

- **`amount` becomes `round(forecast["net_take_home_annual"] / 12, 2)`, in
  paise.** Both routes already compute that forecast for their own response, so
  the payout is derived from the same object the caller is shown, not from a
  parallel calculation. One source, and the payload can be checked against the
  forecast beside it.
- **`net_monthly_disbursement()` is deleted.** It has no callers, and after this
  change the live path computes the figure from the forecast. Keeping a second,
  PT-less implementation of "net pay" is exactly the shape this project has
  removed repeatedly, and it is the shape that produced this bug: a correct
  function nobody called, beside wrong inline arithmetic. *(If D-P2 says keep a
  named function instead, it becomes the single implementation and the forecast
  calls it.)*
- **The payload's schema does not change.** RazorpayX's Composite Payout object
  keeps exactly its verified fields. The withholding breakdown goes **beside**
  the payouts array, not inside a payout:

  ```json
  "payout_basis": {
    "gross_monthly_cash": 139200.0,
    "employee_pf_monthly": 10800.0,
    "tds_monthly": 10340.2,
    "professional_tax_monthly": 208.33,
    "net_monthly": 117851.47,
    "note": "amount is net of the withholdings listed; they are remitted separately"
  }
  ```

  (Measured for ₹18L CTC in Karnataka, not illustrative.)

  A reviewer can then see why the figure is what it is, which is the same
  reasoning that made `treasury_forecast` report its components.
- **Professional tax:** the forecast's annual PT already accounts for the
  February bump (11 months plus one), so dividing by 12 spreads it evenly rather
  than reproducing a real February payslip. That is a simplification and is
  recorded as one, in the note and in the README. Making the payload
  month-accurate means passing a month and is **D-P3**.
- **No `work_location`, no PT**, exactly as `treasury_forecast` behaves today.

## 4. Blast radius, traced

| Consumer | Effect |
|---|---|
| `/api/export-razorpayx` | `payouts[].amount` falls by the withholding. `treasury_forecast` in the same response is unchanged. |
| `/api/submissions/<id>/rows/<i>/export` | Same, plus the placeholder-account warning path, unchanged. |
| `razorpayx-export-modal.tsx` | Renders the payload JSON and offers *Copy*. It displays no amount of its own, so no frontend change is needed; it will show the corrected figure. |
| Audit log | Records `total_capital_outlay`, not the amount. Unchanged. |
| The pipeline baseline fixture | Does not contain payouts. Unchanged. |
| Tests | None pin the amount today. §5 adds them. |

**Not affected:** the maker-checker gate, the tax engine, the treasury totals
(`total_capital_outlay` is unchanged — this moves nothing between the four
components; it corrects which of them the payout pays).

## 5. Tests

**Committed failing first, as in D1:**

- **The identity that makes it checkable:** for a structure with and without a
  `work_location`, `sum(payout amounts) * 12 + tds_escrow_annual +
  epfo_challan_annual + professional_tax_annual == total_capital_outlay`. That
  ties the payout to the forecast rather than to a hand-copied number.
- **The amount is not the gross:** at ₹18L CTC it is strictly less than
  `(basic + hra + lta + special_allowance) / 12`, by exactly employee PF plus
  TDS plus PT for that month.
- **Both routes:** `/api/export-razorpayx` and the per-row export produce the
  same amount for the same input.
- **Paise:** the value is an integer number of paise, and `amount / 100` equals
  the rupee figure to two decimals.
- **A zero-tax structure** (₹6L CTC, tax ₹0) still withholds PF and PT: measured
  gross ₹47,000 a month against a net of ₹43,791.67. Without this case, an
  implementation that withheld only TDS would look correct wherever tax is zero.

**Sabotage:**
- Restore the gross arithmetic: the identity test and the not-gross test fail.
- Withhold TDS but not PT (i.e. the deleted function's behaviour): the identity
  test fails by exactly the PT amount, with a `work_location` supplied.

## 6. Sequence

Separate commits, full suite after each, request/go handshake:

1. The tests above, committed red.
2. `_build_composite_payout()` takes the forecast and uses its net; both call
   sites pass what they already computed. `payout_basis` added beside the
   payouts array.
3. Delete `net_monthly_disbursement()` (D-P2).
4. README and `docs/PROJECT_STATUS.md`: close the gap row, record the even-spread
   PT simplification.

## 7. Decisions for the owner

| | Decision | Recommendation |
|---|---|---|
| **D-P1** | Fix the amount to be net? | **Yes.** The payload is built to be pasted into RazorpayX, and it currently pays gross. |
| **D-P2** | Delete `net_monthly_disbursement()`, or make it the single implementation? | **Delete.** It has no callers and no longer matches what "net" means here. Keeping it is what produced this bug. |
| **D-P3** | Month-accurate professional tax? | **No, spread evenly**, and record it. A month-accurate payload needs a month input and a decision about which month an export is for; neither exists today. |
| **D-P4** | Include `payout_basis` beside the payouts? | **Yes.** It keeps the RazorpayX object schema-exact while showing a reviewer what was withheld. |
| **D-P5** | **Unrelated finding, raised not fixed:** `/api/export-razorpayx` builds every employee's payout from **one** structure computed from a single CTC, so a list of ten employees gets ten payouts with identical amounts and different bank accounts. That is either intended (one offer, several recipients — unlikely to be the real case) or a second defect. | **Not in scope here.** It needs its own design, and it should be answered before Phase 3 for the same reason this one was. |

## 8. Not in scope

Live dispatch of any kind; the treasury total's omission of employer NPS (its own
gap row); the annual-figure-labelled-monthly banner (its own gap row); anything
that changes who approves a payout.


## 9. Implementation record (2026-09-21)

| Step | Commit | Result |
|---|---|---|
| 1 tests, committed red | `5acdbda` | 615 run, 6 failures: 3 assertion failures and 3 errors for the missing `payout_basis`, as predicted. The cross-route test passed, also as predicted — both routes were equally wrong. |
| 2 the fix | `b4bab69` | 615 OK |
| 3 delete `net_monthly_disbursement()` | `c55035c` | 615 OK. Grepped first: no importer anywhere, only prose mentions. |
| Sabotage: restore the gross arithmetic | — | **5 failures, where §5 predicted 2.** The two predicted, plus the whole-paise and below-gross tests, because `payout_basis` keeps reporting the correct net while `amount` goes back to gross, so the payload stops agreeing with itself. The under-prediction is recorded rather than smoothed over: it is real information about how tightly the basis block couples to the amount. |
| Sabotage: withhold TDS but not professional tax | — | Two attempts were discarded for cross-session database contention (see below); the clean run is reported with the docs commit. |

**Two runs were lost to concurrent suites**, not to anything in the tree: two
sessions started runs seconds apart, twice, producing ~100 errors in the
database-backed tests in around half the usual wall time. A pre-flight process
check cannot prevent it, since it only sees runs that have already started. The
sessions have moved to an explicit hold-and-acknowledge handshake, and an atomic
lock directory is proposed so that the exclusion is structural rather than
conventional.
