# An annual figure labelled "Monthly", and a gate with no period at all — fix design

**Status:** design only, **awaiting approval.** No code is changed. Decisions
D-M1 to D-M4 (§6) are the owner's.

**Why now.** Recorded as an open gap on 2026-09-15 while measuring the
employer-NPS blast radius, with the owner's note that it errs safe and can queue
behind D1. D1, the payout fix and the treasury fix are done, so this is next.

---

## 1. What is wrong

`treasury_forecast()` is an **annual** forecast. Every field it returns ends in
`_annual`, and its docstring says so. Two surfaces consume it without a period.

### 1.1 The label is simply wrong

`executive-summary-card.tsx` shows the sum of `total_capital_outlay` as:

> **Total Monthly Payroll Liability**
> *Net take-home + TDS escrow + EPFO challan, summed across all processed rows*

Nothing on that path divides by twelve. **The figure is annual and the label
says monthly**, so it reads roughly 12× too small a commitment as a monthly
number — or, put the other way, the number shown is right and its name is wrong.

**The detail line is separately stale**, and now wrong twice over: it names three
components, when the total has five since professional tax (2026-09-03) and the
employer's NPS remittance (2026-09-21). It has been a partial list since PT
shipped.

### 1.2 The gate has no period at all

`treasury-gate.tsx` shows *"Required Treasury Funding (pending rows)"* against
the live RazorpayX balance, and `finance-flow.tsx` blocks bulk-approve when the
balance is lower. The figure is the annual sum. The label names no period, so
nothing is literally false — but the comparison is **a year of payroll against a
bank balance**, which is not the question anyone is asking at a payroll run.

**Its direction is safe.** Comparing an annual requirement to a balance blocks
more often than a monthly comparison would, never less. So this has never let
anyone approve a run they could not fund; it has told them they cannot afford
runs they can.

**That is why this is a label-and-period problem, not a repeat of the treasury
NPS bug**, which was permissive. Stating the difference plainly because "another
wrong treasury figure" would otherwise read as the same severity.

## 2. What a monthly figure would mean, precisely

`total_capital_outlay / 12` is **not** a payroll month, and the design should
not pretend otherwise:

- **Professional tax is not twelve equal instalments.** `annual_professional_tax()`
  is eleven base months plus a higher February (₹200 × 11 + ₹300 in Karnataka).
  A twelfth of the annual figure is the average month, not any actual month.
- **TDS is modelled as twelve equal instalments** (`monthly_tds_schedule()`),
  which is already a documented simplification of real s. 392 withholding.
- **The other three components are twelfths by construction.**

So a monthly figure is an **average month**, correct to within the PT smoothing,
and it must be labelled as such rather than as "this month's payroll".

## 3. Design

**Backend computes it; the frontend does not divide.**

- `treasury_forecast()` gains `average_monthly_outlay`, defined as
  `round(total_capital_outlay / 12, 2)`, alongside the annual fields it already
  returns. One source, and the arithmetic is beside the definition it depends on
  rather than in a component.
- Its docstring records that the twelfth is an average, naming professional tax
  as the reason it is not a real month.

**The Executive Summary card** (D-M1):

- **Recommended: show the annual figure and label it annual.** *"Total Annual
  Payroll Liability"*, with the detail line corrected to name all five
  components. The card's other metrics are annual (*"Discovered Annual Tax
  Inefficiency"*), so this reads consistently and needs no new field.
- The alternative — show `average_monthly_outlay` under the existing label — is
  a bigger change to what the card says, and it makes the two money metrics
  disagree about period.

**The Treasury Gate** (D-M2):

- **Recommended: label the existing figure as annual** — *"Required Treasury
  Funding, annual (pending rows)"* — and leave the comparison alone.
- **Not recommended: switch the gate to the monthly figure.** It would be the
  more meaningful comparison, and it would also make the gate roughly twelve
  times more permissive. That is a product decision about when to block
  bulk-approve, not a labelling fix, and it should not ride along inside one.
  If the owner wants it, it deserves its own design, its own measurement, and
  its own sabotage.

## 4. Tests

- **The new field is a twelfth of the total**, for structures with and without
  employer NPS, and with and without a `work_location`.
- **It is present and zero-safe**: a zero-CTC-ish structure does not produce a
  missing key.
- **The annual fields do not move**, so this is additive: the five-term identity
  and `total_capital_outlay == SalaryStructure.total()` still hold.
- **The average-month caveat is real, and pinned**: with a Karnataka
  `work_location`, `average_monthly_outlay × 12` equals the annual total, while
  `monthly_professional_tax(month=2)` is strictly greater than
  `professional_tax_annual / 12`. That is what makes "average" the honest word.
- **Frontend**: no test runner exists; `tsc --noEmit` plus the screenshot check
  the frontend session has been running.

**Sabotage:** define the new field as `net_take_home_annual / 12` instead of the
total: the twelfth-of-total tests fail while the field-presence test still
passes.

## 5. Sequence

Separate commits, full suite after each, under the lock, pushing the SHA
verified:

1. Tests, committed red.
2. `average_monthly_outlay` in `payroll_breakdown.treasury_forecast()`.
3. Frontend (the frontend session's files, requested not edited): the card's
   label and its corrected five-component detail line; the gate's label;
   `api-types.ts`.
4. README and `docs/PROJECT_STATUS.md`: close the gap row.

## 6. Decisions for the owner

| | Decision | Recommendation |
|---|---|---|
| **D-M1** | Executive Summary: relabel as annual, or show a monthly figure? | **Relabel as annual**, and fix the three-component detail line to five. Least change, consistent with the card's other annual metric, and it makes a true statement immediately. |
| **D-M2** | Treasury Gate: relabel, or compare monthly? | **Relabel only.** Switching to monthly makes the gate ~12× more permissive; that is a product decision, not a labelling one, and must not ride inside this fix. |
| **D-M3** | Add `average_monthly_outlay` at all, given D-M1 and D-M2 both relabel? | **Yes.** The word "monthly" is what people will keep reaching for, and the next person to want it should find a defined field rather than divide by twelve in a component. It is also what any later D-M2 revisit would need. |
| **D-M4** | Name it `average_monthly_outlay` rather than `monthly_outlay`? | **Yes.** It is an average month, not a payroll month, because professional tax is not twelve equal instalments. The name should carry that, since a caller who sees `monthly_outlay` will reasonably assume it is what February costs. |

## 7. Not in scope

The export modal's component grid, which omits professional tax and so does not
reconcile when PT is non-zero — raised by the frontend session on 2026-09-21 and
either fixed there or recorded as its own gap. D-P5, one structure applied to
every employee in an export list. Any change to when bulk-approve blocks.
