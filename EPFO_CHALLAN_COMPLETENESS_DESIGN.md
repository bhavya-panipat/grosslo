# Completing the EPF challan figure (D-S1) — fix design

**Status:** design only. No code is changed. Decisions D-C1 to D-C4 (§8) are the
project owner's. **Implementation is gated on D-C2**, for the reason measured in
§3.

**Rulings already made by the owner, 2026-09-28:**
- D-S1: record now, fix after a primary-source lookup. The lookup is
  `docs/PRIMARY_SOURCE_LOOKUP_TASK.md`, *LOOKUP — D-S1*, and its three readings.
- **EDLI and admin charges go on top of CTC, not inside it.** They are employer
  payments to EPFO for fund administration and insurance, never part of what is
  promised to the employee. `optimize()` already spends the whole CTC on the
  modelled components, and carving room out of it would silently cut someone's
  take-home for a cost they cannot see. So `total_capital_outlay` will
  **deliberately exceed** `SalaryStructure.total()`, because a real employer cost
  was being under-counted.
- This session writes the design. The tenancy session stays on the export and
  funding-gate code, and gets this document before any code, because
  `treasury_forecast()` sits in its treasury area.

---

## 1. What is established, and from where

| Fact | Source | Reads |
|---|---|---|
| EPF admin charges: **0.50% of pay** from 1 June 2018 | S.O. 2011(E), Gazette, 21 May 2018, enclosed in EPFO circular WSU_AdmnCharges_4570 | 1 |
| **Minimum admin charge: ₹500 a month per establishment** with a contributing member; ₹75 with none | Same notification; restated in EPFO's wage-ceiling FAQ, Q13 | 2 (different documents) |
| EDLI admin charges: **nil**, "for the time being", from 1 April 2017 | S.O. 828(E), Gazette, 15 March 2017 | 1 |
| EDLI contribution: **0.5% of wages**, employer only | EPFO's EDLI scheme page (not a notification) | 2 |
| **Statutory wage ceiling: ₹25,000 a month from 17 September 2026**, ₹15,000 before | EPFO wage-ceiling FAQ, citing S.O. 5109(E), which was **not read** | 1 |
| **EDLI and admin charges are computed on wages capped at the ceiling**, in the mandatory case: ₹125 each at PF wages of ₹35,000 | Same FAQ, Q13 table | 1 |

## 2. What the current code computes

`epfo_challan_annual = employer_pf + derive_pf(basic)`: the two PF shares, both
on **full basic**. `derive_pf()` defaults to `voluntary_full_basic=True`,
deliberately, since most employers contribute on full basic rather than the
ceiling. EDLI and admin charges appear nowhere. `PF_WAGE_CEILING_BASIC = 15_000`
is stale since 17 September 2026 (Open gaps row), and inert today.

## 3. The measurement that gates this design

What the fix adds per employee per year (EDLI plus admin, each 0.5%), on the
optimizer's recommended structure. Rent 0, metro, no NPS, at `6087a51`:

| CTC | Basic / month | On the **capped** base (₹25,000) | % of CTC | On **full** basic | % of CTC | Current `epfo_challan_annual` |
|---|---|---|---|---|---|---|
| ₹3,00,000 | ₹12,500 | ₹1,500 | 0.50% | ₹1,500 | 0.50% | ₹36,000 |
| ₹6,00,000 | ₹25,000 | ₹3,000 | 0.50% | ₹3,000 | 0.50% | ₹72,000 |
| ₹12,00,000 | ₹50,000 | ₹3,000 | 0.25% | ₹6,000 | 0.50% | ₹1,44,000 |
| ₹18,00,000 | ₹90,000 | ₹3,000 | 0.17% | ₹10,800 | 0.60% | ₹2,59,200 |
| ₹36,00,000 | ₹1,80,000 | ₹3,000 | 0.08% | ₹21,600 | 0.60% | ₹5,18,400 |
| ₹60,00,000 | ₹3,00,000 | ₹3,000 | 0.05% | ₹36,000 | 0.60% | ₹8,64,000 |

**At or below the ceiling the two bases agree. Above it they diverge by up to
12x** (₹3,000 against ₹36,000 at ₹60L). This tool's default structures pay PF
voluntarily on full basic, and whether EDLI and admin charges then follow the
capped wage or the full contribution base is **not answered by any document
read**. The FAQ shows only capped, mandatory contributions. That is D-C2, and
because the answer moves the figure by an order of magnitude, the fix is not
implemented until it is settled.

This is magnitude, not population. How many real employees sit above the ceiling
depends on a customer's payroll, which no store here holds.

## 4. Design

### 4.1 Two new components, and an honest EPF challan

`treasury_forecast()` gains `edli_contribution_annual` and
`epf_admin_charges_annual`. Each is 0.5% of the monthly PF-wage base, per month,
summed over the months it covers. **`epfo_challan_annual` then includes them**,
because an EPF challan does carry them (EPF, EPS, EDLI and admin accounts; FAQ Q7).
That makes the field's name true, which D-S1's optional rename was reaching for,
without renaming a stored field. `total_capital_outlay` rises by the two
components, on top of CTC.

### 4.2 The PF-wage base

`basic / 12`. Dearness allowance is not modelled anywhere in this tool, which is
an existing, recorded scope limit. The ceiling applies to the base or not
according to D-C2.

### 4.3 A dated ceiling, replacing the constant

`PF_WAGE_CEILING_BASIC` becomes a function of the month:
`pf_wage_ceiling(year, month)`, returning ₹15,000 before September 2026 and
₹25,000 from October 2026. **September 2026 is prorated by days**, 16 at ₹15,000
and 14 at ₹25,000, exactly as the FAQ's Q7 illustration does. The ceiling goes
into the legal-claim inventory as a claim with a citation, so drift is caught.
**Prerequisite:** read S.O. 5109(E) itself. The FAQ is not the notification,
and this becomes load-bearing the moment the fix ships (Open gaps row).

### 4.4 Which month an annual forecast uses

`treasury_forecast()` is annual and undated. `workforce_forecast.py` already
works month by month, so it can use the dated ceiling per month directly. For
`treasury_forecast()`, see D-C1.

### 4.5 The establishment minimum: where it can and cannot be applied

The ₹500 minimum attaches to the **whole establishment**, and this tool never
sees a whole establishment's payroll. It sees the rows someone submitted.

- **Per row, per hire, per funding decision:** the **marginal** admin charge is
  the percentage. An employer already paying at least ₹500 a month owes exactly
  0.5% more for each added employee, so the per-employee figure is correct as the
  *extra* cost. This covers `treasury_forecast()`, the funding gate, the payout
  export and the workforce forecast, which forecasts *additional* hires.
- **Only where a whole payroll is uploaded** (a batch audit of the full
  establishment) can the minimum be applied: `max(sum of admin charges, ₹500)`,
  or ₹75 with no contributing member. Even there the tool cannot know the upload
  is the whole establishment, so D-C3 decides whether it is applied or only
  noted.
- Everywhere the minimum is not applied, the output says so: "excludes EPFO's
  ₹500 monthly minimum admin charge per establishment".

### 4.6 Stored rows (`CLAUDE.md`, *Fixing a stored computed value*)

Submission rows store `treasury_forecast`. After the fix, a stored forecast
without `edli_contribution_annual` predates it, and is identified by the missing
key, exactly as `_pre_nps_remittance_flag()` identifies a pre-NPS forecast. **The
population, measured at `6087a51`:** Postgres holds 0 submission rows in either
tenant. None of the 5 SQLite rows stores a `treasury_forecast` at all. So the
affected population is 0. **Unlike D-S6's, the set is not closed until the fix
ships:** every row submitted between now and then will store a pre-fix forecast.
So D-C4 is decided on the population at ship time, re-measured then, not on
today's zero.

With D-S7 (the stored figure is canonical, approved), a stored pre-fix forecast
would be what the export serves, which is what makes D-C4 matter.

## 5. What changes, deliberately

Every `total_capital_outlay` rises. Consumers: the Finance funding gate
(`frontend/lib/treasury.ts`), the Executive Summary's annual liability, the export
modal's funding grid, the batch audit's liability total, the workforce forecast's
total cash need, and `penalty_scenario`'s arrears base (which inherits
`epfo_challan_annual`). The identity every treasury test asserts,
`total_capital_outlay == SalaryStructure.total()`, becomes
`== SalaryStructure.total() + edli + admin`. That is the ruling taking effect,
not a regression, and each retargeted assertion must say so. The workforce
forecast's identity test (`tests/test_workforce_forecast.py`) moves with it.

## 6. Tests, including the ones that make the claims checkable

- **The new identity:** total = CTC-modelled + EDLI + admin, for every case the
  existing identity tests cover.
- **The cap binds:** PF wages ₹35,000 a month gives ₹125 each per month under the
  capped base (the FAQ's own row), and ₹20,000 gives ₹100 (under the cap, the
  bases agree).
- **September 2026:** prorated by days, reproducing the FAQ's Q7 Scenario B
  figures (EDLI ₹100, admin ₹100 on ₹20,000).
- **Dated ceiling:** ₹15,000 for August 2026, ₹25,000 for October 2026.
- **The minimum:** applied only where D-C3 says, and labelled everywhere else.
- **Pre-fix rows:** a stored forecast without the new key is identified, per
  D-C4.
- **Sabotage:** drop EDLI from the total, and the identity tests fail; use the
  stale ₹15,000 ceiling for October 2026, and the dated-ceiling test fails.
- Suite before and after under the lock, with the delta named test by test, and
  test-file descriptions for the count generator.

## 7. Not in scope

EPS versus EPF account split (the total is unaffected); DA; any change to what
`optimize()` recommends; payouts' own net amounts (EDLI and admin are employer
costs, not deductions from pay); the ungated re-export the tenancy session found
(a separate candidate gap).

## 8. Decisions for the owner

| | Decision | Recommendation |
|---|---|---|
| **D-C1** | Which ceiling does an undated annual `treasury_forecast()` use? | **The ceiling in force on the date it is computed, recorded in the forecast** (`pf_wage_ceiling_applied`), so a stored forecast says which law it used. A forecast is forward-looking payroll, and every date since 17 September 2026 gives ₹25,000. |
| **D-C2** | When PF is paid voluntarily on full basic (this tool's default), are EDLI and admin charges on the capped wage or the full base? | **Do not implement until answered.** Up to 12x apart (§3). The FAQ covers only the mandatory, capped case, and the answer must not come from memory. Route: read S.O. 5109(E) and the EPF Scheme's paragraphs 26 and 30 on India Code, and add the question to `docs/CA_REVIEW_PACKET.md`. If the owner prefers to ship first: the **full base**, labelled, because it over-funds rather than under-funds. But that is an assumption shown as a figure, which the owner rejected on D-W3. |
| **D-C3** | The ₹500 establishment minimum. | **Label it everywhere; apply it nowhere in the first version.** Per-row and per-hire figures are correct as marginal costs, and no upload can be known to be a whole establishment. Applying the minimum to a partial upload would overstate. |
| **D-C4** | Pre-fix stored forecasts. | **Decide at ship time on the re-measured population.** Today it is 0 in both stores, but the set stays open until the fix ships. If still 0 then, no flag, with its trigger conditions recorded (D-S6's shape); if not, the absence-of-key flag, which needs no column. |
