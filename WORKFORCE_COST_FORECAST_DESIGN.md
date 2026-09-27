# Forward-looking workforce cost forecast (addition spec Tier 2.1) — design

**Status:** design only. No code is written. Decisions D-W1 to D-W4 (§7) are the
project owner's. Held by the owner on 2026-09-26 until the treasury and forecast
code had a quiet stretch (`docs/PROJECT_STATUS.md`, *The addition spec*); started
2026-09-27, when the last defect fix in that code (`6e7427a`, D-S2 Site C) was two
days old and no new gap row had been logged.

**What the spec asked for:** "if we hire N people at CTC X in city Y next quarter,
what's total statutory liability and cash need." Same tax engine, same treasury
math, applied prospectively. **No new computation, no new legal claims, no new
risk surface.**

**Revised twice on 2026-09-27 after the owner's reviews:**
- D-W1: approved, with a day-one "not practitioner-confirmed" condition. B is the
  statutory default on one line of evidence (CBDT); a second source proved to
  derive from CBDT, and India Code does not carry the Act.
- D-W2: ruled no default gratuity rate. "Conservative" was measured on 22,080
  cases and holds only for the total and TDS.
- D-W3: ruled reject crossing 1 April.
- D-W4: approved.
- Rent: required exactly when the engine shows it can change the answer, and
  optional otherwise. A first grid understated its effect; a dense grid showed
  swings up to ₹3,85,008.

Each revised passage says what changed and why.

**What this document finds:** the first half of that holds and the second does
not, quite. §3 measures a case where applying the existing engine prospectively
gives the wrong answer, and it is the component the spec cared about most.

---

## 1. What the answer actually is, stated plainly first

For a hire on the optimizer's recommended structure, `treasury_forecast()`'s
total equals `SalaryStructure.total()`, which equals the CTC (verified for 8
cases in §6, and the identity `treasury_forecast()`'s own docstring and tests
assert). So **the total cash need is the CTC, prorated.** N hires at ₹18L joining
with three months of the year left need N × ₹4,50,000. That is multiplication,
not modelling, and the feature must not present it as more.

**What the engines add is the split:** how much of that cash goes to employees'
bank accounts, how much to the income-tax department as TDS, to EPFO, to the NPS
trustee, and to the state as professional tax, month by month. That split is
the "statutory liability" half of the spec, and it is where §3 applies.

## 2. Existing functions called unchanged

Nothing in `tax_engine.py`, `optimizer.py` or `payroll_breakdown.py` changes. The
implementation's diff must show those three files untouched, and §8 makes that a
checked condition rather than a promise.

| Function | Location at `1aad5a8` | Used for |
|---|---|---|
| `optimize(ctc, rent_paid, city, nps_opted)` | `optimizer.py:257` | The recommended structure and regime per cohort |
| `treasury_forecast(structure, tax_breakdown, work_location)` | `payroll_breakdown.py:193` | The full-year run-rate, and the identity test in §8 |
| `monthly_professional_tax(work_location, gross_monthly, month)` | `payroll_breakdown.py:118` | Per-month PT, including the February month where it differs |
| `employee_pf_monthly(basic_annual)` / `derive_pf` | `payroll_breakdown.py:188`, `tax_engine.py:258` | Employee PF per month |
| `taxable_income_for_structure(structure, regime, rent_paid, city)` | `tax_engine.py:304` | Taxable income for a part-year structure (§3) |
| `compute_tax(taxable_income, regime)` | `tax_engine.py:173` | Tax on that income (§3) |

**New code, all of it outside those files:** grouping hires into cohorts,
multiplying by headcount, iterating months, prorating a structure by months
employed (§3), and summing. No LLM call anywhere: every figure comes from the
functions above, so the architecture rule holds by construction.

## 3. The measurement: prorated annual tax is wrong for mid-year hires

`treasury_forecast()` is annual throughout, and `monthly_tds_schedule()` spreads
the annual tax over twelve equal months. The obvious prospective use is to take
that annual TDS and prorate it by the months a hire works. **For anyone joining
mid-year, that overstates TDS, sometimes by all of it.** Income tax falls on
income earned in the financial year, the slabs are progressive, and the rebate
cuts off at a threshold, so a part-year salary is not taxed at a proportional
share of the full-year tax.

Measured at `1aad5a8`, `python3 -B`, rent ₹3,00,000, metro, no NPS, recommended
regime. **A** is the annual tax prorated by months employed. **B** is `compute_tax`
on a structure scaled to the months employed, for a hire with no other income in
the year:

| CTC | Regime | Annual tax | 3 months: A | B | 6 months: A | B | 9 months: A | B |
|---|---|---|---|---|---|---|---|---|
| ₹6,00,000 | old | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ₹12,00,000 | new | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ₹18,00,000 | new | 1,24,082 | 31,021 | **0** | 62,041 | **0** | 93,062 | **0** |
| ₹24,00,000 | new | 2,47,572 | 61,893 | **0** | 1,23,786 | **0** | 1,85,679 | 1,24,082 |
| ₹36,00,000 | new | 5,82,130 | 1,45,532 | **0** | 2,91,065 | 1,24,082 | 4,36,597 | 3,21,547 |
| ₹60,00,000 | new | 12,77,016 | 3,19,254 | 80,652 | 6,38,508 | 4,08,408 | 9,57,762 | 8,42,712 |

At 12 months A and B coincide for every case measured (§6), which is what makes
this a proration effect rather than a disagreement between two methods.

**B is the statutory default, and A is the exception.** *(Corrected after review.
The first draft treated A and B as symmetric unknowns. The owner pointed out that
the law decides which one applies, and the primary source confirms it.)*

Income-tax Act, 2025, **s. 392(4)(a)(i)**, the successor to the 1961 Act's s.
192(2) per CBDT's own concordance utility. The employer "shall take into account
the following particulars furnished by the assessee, **at his option**",
including "any income under the head 'Salaries' due or received by the assessee,
from any other employer or employers during the tax year". Read on 2026-09-27 in
CBDT's parallel-reading view on `incometaxindia.gov.in`, alongside the 1961 text,
which says the same: "he may furnish". So:

- **Without a declaration, the employer withholds on this employment's income
  alone. That is B**, whatever the hire earned before.
- **A applies only if the hire declares earlier income**, and then only roughly: it
  is exact when the earlier pay was at the same rate, and the real figure can
  exceed A if it was higher.

**Text dual-sourced, mapping single-sourced pending India Code; not signed
off.** *(Wording sharpened after implementation, at the tenancy session's
suggestion: the two halves of this claim have different evidence, and saying
"one line of evidence" blurred which half.)* On the owner's instruction the
reading was checked a second way. `itact2025.org/tds-tcs/s392-salary-tds`, a
knowledge base maintained by a practising chartered accountant, carries the same
**text** word for word. **The mapping from 1961 s. 192 to 2025 s. 392 is not
independently confirmed**, and the owner's third review asked exactly that:
itact2025.org's own mapping page names its source as "CBDT Navigator
(new-bill-2025-navigator.pdf)" and labels itself "DRAFT — verify against enacted
PDF". So the mapping, which is the part doing the work, is CBDT read twice. An independent line was tried: **India Code
does not carry the Income-tax Act, 2025.** Its Acts collection, searched newest
first on 2026-09-27, lists other 2025 Acts but not this one, and its income-tax
link points to CBDT. That is consistent with the open gap *`(Act 30 of 2025)` is
still unverified* in `docs/PROJECT_STATUS.md`. The remaining independent routes
are the Gazette (`egazette.gov.in`) or a practitioner.

**Ruled by the owner 2026-09-27, as a condition, not a recommendation:** the UI
copy ships from day one with "not practitioner-confirmed" wording on the B/A
distinction, and never states it as law. Its unconfirmed status must not become
confirmed by omission. Recommended: add it to `docs/CA_REVIEW_PACKET.md` as a
question, so the confirmation has a place to arrive.

How often hires actually declare is not measured here, and no store holds it. It
does not need to be: the default follows from the statute, not from frequency.
Two points are **not** verified and are not claimed: the name and number of the
prescribed form under the Income-tax Rules, 2026, and the hire's final liability
at filing, which can differ from what was withheld. The second is the employee's
cash, not the employer's.

**Magnitude, not population.** The table shows how wrong prorating can be. It does
not say how many real hires are affected, because that depends on a customer's
hiring mix, which no store here holds. Stated separately, per `CLAUDE.md`.

**Why this matters less than it looks, and more than it looks.** Less, because
TDS and net pay are two slices of the same cash (§1): the total need is
unaffected, and only the split between the tax department and the employees'
bank accounts moves. More, because the split is exactly what the spec asked for,
and a single confident TDS figure would be wrong in one direction or the other
for most mid-year hires. That is D-W1.

## 4. Inputs

Per cohort: headcount, CTC, city tier, rent paid, NPS opted, work location,
joining month. Per forecast: the period (§7, D-W3).

- **Rent paid is not known for a hire who has not joined.** *(Revised after review.
  The first draft required it with no default, which pushes an unanswerable
  question onto the user.)* **Required where it can change the answer, optional
  where it cannot** (rule below). Where optional and omitted, it **defaults to
  zero, labelled as an upper bound**: "assumes no rent claimed; TDS may be lower and take-home
  higher if the hire claims HRA". Zero is used rather than a percentage-of-CTC
  estimate, because any such percentage would be a number with nothing behind it,
  which the addition spec's exclusion list rules out.

  **Measured at `1aad5a8`, and corrected once.** A first 30-case grid (CTC ₹6L, 9L,
  12L, 18L, 36L × metro/non-metro × rent ₹0/₹3L/₹6L, even and unweighted) found
  rent changing the tax in 1 case of 30, and this document briefly called the
  default "nearly costless". The owner questioned the grid. A dense one (CTC ₹5L–₹60L
  in ₹1L steps × metro/non-metro × rent at 10/20/30/40% of CTC, 448 cases, still
  unweighted, since no customer hiring distribution exists here to weight by)
  reversed that: **rent changed the tax in 43% of cases and the recommended regime
  in 203**, and the largest difference was **₹3,85,008 a year** (₹60L, metro, 40%
  rent). The small grid's rents were too low in rupees for the salaries where they
  matter. **What held in all 448: rent never increased the tax.** So the zero
  default is a reliable *upper bound* on TDS and a lower bound on take-home, in a
  known direction. It is not a small error, and the label must not imply one. Rent
  never changes the total cash need (§1).

  **Honest about the direction is not the same as usable as a forecast** (the
  owner's second review), so **rent is required exactly when it can change the
  answer.** The rule comes from the engine, not from a chosen cut-off. The HRA
  exemption is capped at the smaller of HRA received and 50% of basic (40%
  outside metros), `tax_engine.py:196`, so a rent equal to the CTC always reaches
  the cap. For each cohort, the route runs `optimize()` at rent ₹0 and at rent =
  CTC. If the recommended tax differs, rent is required, and the route refuses to
  forecast without it and says why. If it does not, rent cannot matter and stays
  optional. Measured at `1aad5a8` (CTC ₹3L–₹60L in ₹25,000 steps, no NPS): rent
  can change the tax from **₹16,00,000 upward in metros and ₹27,00,000 upward
  outside**, at every step above those points, by up to ₹3,85,008 and ₹3,08,256.
  Below them it never does. **Those two figures are observations, not constants
  to hard-code.** They move whenever slabs or the optimizer change, which is why
  the rule is computed per request.
- **The regime is the optimizer's recommendation.** The employee chooses in
  reality. The output must label the regime it assumed.

## 5. What is not modelled, stated where the figures are shown

Each of these is already a known gap. The forecast inherits them, and must say so
next to the figures rather than in this document only:

- **Gratuity, insurance and bonus provisions.** An offered CTC usually carries
  them (`CTC_RECONCILIATION_DESIGN.md`), and `optimize()` spends the whole CTC on
  the five modelled components. So an offer-letter CTC entered as-is overstates
  monthly cash pay by those amounts and shows no gratuity liability at all. That
  is D-W2.
- **EDLI and EPFO administrative charges.** `epfo_challan_annual` omits them
  (open gap D-S1), so the EPFO line understates a real challan.
- **ESI, labour welfare fund, the employee's own NPS contribution.** Not modelled
  anywhere in this codebase.
- **Professional tax outside five states.** An unrecognised `work_location` gives
  PT "not modelled", not zero, as today.
- **One legal claim this feature leans on, not verified here.** The engine applies
  `STANDARD_DEDUCTION` as a flat amount, and B in §3 inherits that for a part-year
  salary. It goes to the claim inventory as unverified, rather than being asserted
  in the feature's output. (The second claim in the first draft, how earlier
  income reaches the new employer's withholding, is now verified: s. 392(4)(a)(i),
  §3.)

## 6. Checks run for this design, at `1aad5a8`

For CTC ₹6L, ₹18L, ₹36L and ₹60L, each with and without NPS (8 cases), all held:
the recommended structure's `total()` equals the CTC; `treasury_forecast()`'s total
equals `total()`; and at 12 months, B equals the engine's annual tax. The script
is in the appendix.

## 7. Decisions for the owner

| | Decision | Recommendation |
|---|---|---|
| **D-W1** | TDS for mid-year hires. | **Approved by the owner 2026-09-27, with the day-one "not practitioner-confirmed" condition in §3.** *(Revised after review.)* **B is the figure, because it is the statutory default** (s. 392(4)(a)(i), §3, CBDT only): what the employer withholds unless the hire declares earlier income. A is shown as a secondary line, "if the hire declares earlier salary at this rate", never side by side as an equal. The total cash need is shown once, because it does not depend on either. |
| **D-W2** | A stated CTC usually carries gratuity and insurance the engine does not model. | *(Revised after review.)* The first draft asked for "CTC excluding gratuity and insurance". The review is right that a hiring manager forecasting before any offer exists cannot supply that split. **Accept the CTC the user has, treat all of it as cash, and say so beside the figures:** "if this CTC includes gratuity or insurance, the cash need is overstated by that amount". Offer an **optional** field to subtract a known provision. **Ruled by the owner 2026-09-27: no default gratuity percentage.** A statutory rate is a new legal claim, and it faces the same in-force question R1 has (Payment of Gratuity Act, 1972 or Code on Social Security, 2020). It must not be added while s. 392 has not been signed off, whatever the 2026-12-09 date.<br><br>**"Conservative" was asserted in the first revision, then measured on the owner's instruction.** At `1aad5a8`: cash CTC ₹5L–₹60L in ₹1L steps; an unmodelled provision p of 2/4/6% of the entered CTC (sensitivity values, not a legal rate); NPS on and off; metro; rent ₹0; 336 comparisons. That grid found no regime flips and one take-home exception (₹14,00,000 entered as ₹14,28,571, crossing the new-regime rebate zone). **The owner asked whether that exception was singular. It is not, and that first grid was too narrow**: metro only, rent ₹0, so the old regime was barely exercised. **Re-measured at `1aad5a8`:** CTC ₹3L–₹60L in ₹50,000 steps × metro/non-metro × NPS on/off × rent 0/20/40% of CTC × p from 0.5% to 8% in 0.5% steps, **22,080 comparisons**. **Regime flipped in 253.** Lines lower than the truth: **total cash need 0, TDS 0, EPFO 114, NPS 79, take-home 249.** Exceptions spanned both regimes and both flip directions, at true taxable incomes from ₹4,94,050 to ₹25,41,400, with take-home understated by up to ₹19,553. **Conclusion: with an inflated CTC, only the total cash need and TDS keep a guaranteed direction** (overstated, the safe way for funding). EPFO, NPS and take-home do not, because the inflated base can move the optimizer to a different structure or regime. So the label may promise a direction for those two lines only. The optional provision field is the only way to make the rest of the split exact, and the output must say that too. |
| **D-W3** | Periods that cross 1 April. | **Ruled by the owner 2026-09-27: reject.** A figure labelled "at FY 2026-27 rates, not yet enacted for FY 2027-28" still gets copied into a spreadsheet without its label, the same lesson as R5's citation and as A/B. `tax_engine.py` holds only FY 2025-26 / FY 2026-27 rates (header, checked at `1aad5a8`), so a period past 31 March 2027 is refused, with the reason given. Crossing is a real product need, deferred until FY 2027-28 rates exist and both years can be computed on enacted law, not solved with a caveat now. |
| **D-W4** | Where it lives. | **Approved by the owner 2026-09-27.** **A stateless compute route,** like `/api/optimize` and `/api/batch-audit`. Nothing is stored, so there are no pre-fix rows to decide about under `CLAUDE.md`'s stored-value rule. The answer is recorded here, not skipped. A saved-scenarios feature later would bring that rule back. |

## 8. How correctness is proven

- **The identity test, and the strongest one:** one hire, joining in April, over
  the whole financial year, must reproduce `treasury_forecast()` for the same
  inputs exactly, component by component. Both TDS cases must equal its
  `tds_escrow_annual`. Any proration or aggregation bug breaks this.
- **Linearity:** N identical hires equal N × one hire, for every component.
- **Totals:** for every cohort and month, the components sum to the prorated
  `total()`, and the TDS case chosen changes net pay and TDS by equal and opposite
  amounts, never the total.
- **PT timing:** a period containing February shows that month's PT from
  `monthly_professional_tax(..., month=2)`, not the base amount.
- **§3's table** becomes a test, so the A/B divergence stays pinned.
- **The measured directions become tests,** so a later engine change that breaks
  them fails loudly rather than silently falsifying a label:
  - rent never increases tax, across the §4 dense grid;
  - the rent-required rule: rent is demanded exactly when tax at rent ₹0 differs
    from tax at rent = CTC, and is refused-without for such a cohort;
  - an inflated CTC never lowers the total cash need or TDS (§7, D-W2). This is the
    only direction claim the design makes, and the test must not be widened to
    EPFO, NPS or take-home, which measurably go both ways.
- **D-W3's refusal:** a period ending after 31 March 2027 is rejected with its
  reason, not computed.
- **Engines untouched:** the implementation's diff shows no change to
  `tax_engine.py`, `optimizer.py` or `payroll_breakdown.py`.
- **Suite before and after,** under the lock, `python3 -B`, with the delta named
  test by test. The new test file needs a description for
  `scripts/generate_test_counts_md.py`, which refuses to run without one.
- **The frontend surface,** if one is built, goes into README's *Known unverified
  surfaces* table until it has been seen rendering.

## 9. Out of scope

Anything past a forecast: no payout, no remittance, no scheduling of payments, no
statutory due dates (Tier 2.2 was removed because the inventory holds none). No
change to the maker-checker gate. No cross-tenant anything. Crossing into a
second financial year is decided by D-W3. Beyond that, nothing: no rates for any
year the engine does not hold.

---

## Appendix: the measurement script (§3, §6)

```python
from optimizer import optimize
from tax_engine import compute_tax, taxable_income_for_structure, SalaryStructure

rent, city = 300000, "metro"
for ctc in (600000, 1200000, 1800000, 2400000, 3600000, 6000000):
    r = optimize(ctc=ctc, rent_paid=rent, city=city, nps_opted=False)["recommended"]
    s, reg, annual = r.structure, r.regime, r.tax_breakdown["total_tax"]
    for m in (3, 6, 9):
        k = m / 12
        scaled = SalaryStructure(ctc=s.ctc*k, basic=s.basic*k, hra=s.hra*k, lta=s.lta*k,
                                 special_allowance=s.special_allowance*k,
                                 employer_pf=s.employer_pf*k,
                                 employer_nps=s.employer_nps*k, nps_opted=s.nps_opted)
        A = annual * k
        B = compute_tax(max(0.0, taxable_income_for_structure(scaled, reg, rent*k, city)),
                        reg)["total_tax"]
```
