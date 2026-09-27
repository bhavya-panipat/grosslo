# Completing the EPF challan figure (D-S1) — fix design

**Status:** design only. No code is changed. **D-C1, D-C3 and D-C4 approved by
the owner, 2026-09-28. D-C2 resolved from the primary source the same day, and
it split** (§3.1). **Implementation waits on D-C5, ruled "wait"**: the rate notifications under the 2026 schemes, not yet located (§8).

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
- **D-C2 is to be answered per component, not as one binary** (owner's review).
  EDLI and admin charges fall under different schemes and may have different
  bases. The "ship first on the full base" fallback was **removed**, not
  footnoted, because it would put an assumption on screen as a figure, which
  D-W3 already rejected.

---

## 1. What is established, and from where

| Fact | Source | Reads |
|---|---|---|
| EPF admin charges: **0.50% of pay** from 1 June 2018 | S.O. 2011(E), Gazette, 21 May 2018, enclosed in EPFO circular WSU_AdmnCharges_4570 | 1 |
| **Minimum admin charge: ₹500 a month per establishment** with a contributing member; ₹75 with none | Same notification; restated in EPFO's wage-ceiling FAQ, Q13 | 2 (different documents) |
| EDLI admin charges: **nil**, "for the time being", from 1 April 2017 | S.O. 828(E), Gazette, 15 March 2017 | 1 |
| EDLI contribution: **0.5% of wages**, employer only | EPFO's EDLI scheme page (not a notification) | 2 |
| **Statutory wage ceiling: ₹25,000 a month from 17 September 2026**, "for the purposes of Chapter III" of the Code on Social Security, 2020, under s. 2(89) | **S.O. 5109(E)**, Gazette of India No. 4918, 17 September 2026 (`CG-DL-E-17092026-276299`), **read**. It supersedes S.O. 2702(E) of 29 May 2026, which was **not read**; the ₹15,000 before 17 September rests on the FAQ | 1 |
| **For contributions, the schemes now in force are the EPF Scheme, 2026** (s. 15(1)(a) of the Code on Social Security, 2020) **and a separate EDLI Scheme, 2026** (s. 15(1)(c)), both applicable from 29 June 2026. **Not established:** that the 1952 Act is repealed for other provisions. A 9 September 2026 notification was still issued under its s. 17(3)(a) | Gazette, Ministry of Labour, 29 June 2026 (`CG-DL-E-01072026-273957`, `CG-DL-E-30062026-273942`), **read** | 1 |
| **EPF admin charges follow voluntary higher wages:** *"The employer shall be liable to pay additional administrative charges on such wages, on which voluntary contributions are paid"* | **EPF Scheme, 2026, para 19(3)**; the charge is a "percentage of wages" (para 28(2)), fixed by separate notification (para 29(1)) | 1 |
| **The EDLI contribution is capped:** *"calculated on the basis of the wages as defined in clause (88) of section 2 of the Code, subject to the wage ceiling specified in clause (89)"*. The scheme has no voluntary-contribution provision | **EDLI Scheme, 2026, para 5(1)**; the rate is fixed by separate notification (para 5(2)) | 1 |
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

### 3.1 Resolved from the primary source, and neither column above is right

Read per component, as the owner directed, each against its own clause:

- **EPF admin charges: the full base** when PF is paid above the ceiling, which is
  this tool's default. EPF Scheme, 2026, para 19(3).
- **EDLI contribution: the capped base**, always. EDLI Scheme, 2026, para 5(1).

So the table's "capped" column understates, and its "full" column overstates.
What the fix actually adds, measured at `6087a51` (same structures):

| CTC | Basic / month | Admin (full base) | EDLI (capped at ₹25,000) | Per year | % of CTC |
|---|---|---|---|---|---|
| ₹3,00,000 | ₹12,500 | ₹750 | ₹750 | ₹1,500 | 0.50% |
| ₹6,00,000 | ₹25,000 | ₹1,500 | ₹1,500 | ₹3,000 | 0.50% |
| ₹12,00,000 | ₹50,000 | ₹3,000 | ₹1,500 | ₹4,500 | 0.38% |
| ₹18,00,000 | ₹90,000 | ₹5,400 | ₹1,500 | ₹6,900 | 0.38% |
| ₹36,00,000 | ₹1,80,000 | ₹10,800 | ₹1,500 | ₹12,300 | 0.34% |
| ₹60,00,000 | ₹3,00,000 | ₹18,000 | ₹1,500 | ₹19,500 | 0.33% |

At ₹60L the answer is ₹19,500 a year. A single-binary D-C2 would have given
₹3,000 or ₹36,000, and been wrong either way.

## 4. Design

### 4.1 Two new components, and an honest EPF challan

`treasury_forecast()` gains `edli_contribution_annual` and
`epf_admin_charges_annual`. Each is 0.5% of the monthly PF-wage base, per month,
summed over the months it covers. **`epfo_challan_annual` then includes them**,
because an EPF challan does carry them (EPF, EPS, EDLI and admin accounts; FAQ Q7).
That makes the field's name true, which D-S1's optional rename was reaching for,
without renaming a stored field. `total_capital_outlay` rises by the two
components, on top of CTC.

**The two are also reported together as `statutory_overheads_annual`**, so the
identity can be **retargeted rather than deleted** (§5). A total that could
exceed `total()` with nothing to check the excess against would be unconstrained.
That is how the employer-NPS omission survived until D-T1: four identity tests
passed because nothing constrained the total. *(Raised by the tenancy session,
which built the identity pin.)*

**Direction: this makes the funding gate more conservative, never less.** It
adds real employer costs the gate was not funding. The treasury-NPS bug (D-T1)
was the opposite: a missing component made the gate permissive. So this is not
another treasury total change of the same severity.

### 4.2 The PF-wage base

`basic / 12`. Dearness allowance is not modelled anywhere in this tool, which is
an existing, recorded scope limit. The Code defines "wages" in s. 2(88), which is
the same kind of definition R1's open question turns on. Basic-only is carried
into the CA question (§8, D-C5), not settled here.

- **Admin charges:** 0.5% (D-C5) of `basic / 12`, **uncapped when PF is paid on
  full basic** (`derive_pf(voluntary_full_basic=True)`, the default, para 19(3)),
  and capped at the dated ceiling when it is not.
- **EDLI:** 0.5% (D-C5) of `min(basic / 12, ceiling for the month)`, always
  (para 5(1)).

### 4.3 A dated ceiling, replacing the constant

`PF_WAGE_CEILING_BASIC` becomes a function of the month:
`pf_wage_ceiling(year, month)`, returning ₹15,000 before September 2026 and
₹25,000 from October 2026. **September 2026 is prorated by days**, 16 at ₹15,000
and 14 at ₹25,000, exactly as the FAQ's Q7 illustration does. The ceiling goes
into the legal-claim inventory as a claim with a citation, so drift is caught.
**S.O. 5109(E) was read from the Gazette on 2026-09-28** and confirms ₹25,000
from 17 September 2026. The ₹15,000 before it rests on the FAQ, because the
superseded S.O. 2702(E) was not read.
**This design and the stale-ceiling Open gaps row are the same piece of work**,
not cross-references: the fix cannot ship with the ceiling unsettled, and the
ceiling's only live consequence is this fix.

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

**The D-S7 interaction is not symmetric** (tenancy session). With D-S7a
approved, the stored figure is canonical. For rows computed **after** this fix,
both the funding gate and the export see the overheads and agree. For rows
stored **before** it, both agree on the **old, understated** figure. That is
consistent, but low by the overheads. It is the trade `FUNDING_FIGURE_SOURCE_OF_TRUTH_DESIGN.md`
§5 already names, and the D-S3 basis-warning channel is how such a row would say
so if D-C4 flags it.

## 5. What changes, deliberately

Every `total_capital_outlay` rises. Consumers: the Finance funding gate
(`frontend/lib/treasury.ts`), the Executive Summary's annual liability, the export
modal's funding grid, the batch audit's liability total, the workforce forecast's
total cash need, and `penalty_scenario`'s arrears base (which inherits
`epfo_challan_annual`). The identity every treasury test asserts,
`total_capital_outlay == SalaryStructure.total()`, becomes
`== SalaryStructure.total() + statutory_overheads_annual`. That is the ruling
taking effect, not a regression, and each retargeted assertion must say so.

**Blast radius, counted at `6087a51`:** five assertions of the identity in four
files. They are `tests/test_treasury_outlay.py:49` and `:149` (whose docstring
explains why the pin is arithmetic about what CTC means),
`tests/test_ctc_reconciliation.py:202`, `tests/test_employer_nps_statute.py:130`,
and `tests/test_workforce_forecast.py:65`, which compares the forecast to
`treasury_forecast()` and must move in step with it. Two other sites read the
field without asserting the identity and do not change:
`tests/test_finos.py:963` (with PT against without) and
`tests/test_review_workflow.py:1013` (positive). D-T1's argument, that
`total()` equalling the outlay proves a component is inside CTC, still holds
for the five CTC components. The retargeted identity keeps it true for them,
and makes the two overheads the only named exception.

## 6. Tests, including the ones that make the claims checkable

- **The new identity:** total = CTC-modelled + EDLI + admin, for every case the
  existing identity tests cover.
- **Each component on its own base (§3.1):** at basic ₹35,000 a month, EDLI is
  ₹125 (capped, para 5(1)) and admin charges are ₹175 under full-basic PF (para
  19(3)), or ₹125 when PF is not paid above the ceiling (the FAQ's own row). At
  ₹20,000 both are ₹100, because under the cap the bases agree.
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
| **D-C1** | Which ceiling does an undated annual `treasury_forecast()` use? | **APPROVED 2026-09-28.** The ceiling in force on the date it is computed, recorded in the forecast (`pf_wage_ceiling_applied`). |
| **D-C2a** | EPF admin charges under voluntary full-basic PF: capped or full? | **RESOLVED from the primary source 2026-09-28: full.** EPF Scheme, 2026, para 19(3). |
| **D-C2b** | EDLI contribution: capped or full? | **RESOLVED from the primary source 2026-09-28: capped**, always. EDLI Scheme, 2026, para 5(1). |
| **D-C3** | The ₹500 establishment minimum. | **APPROVED 2026-09-28.** Label it everywhere; apply it nowhere in the first version. |
| **D-C4** | Pre-fix stored forecasts. | **APPROVED 2026-09-28.** Decide at ship time on the re-measured population. |
| **D-C5** | **The rates.** Both 2026 schemes fix their percentage by separate notification (EPF para 29(1); EDLI para 5(2)), and neither notification was located. The admin charge's 0.50% and ₹500 minimum rest on S.O. 2011(E), made under the **1952** scheme. The EDLI 0.5% rests on EPFO's scheme page and its September 2026 FAQ. | **RULED by the owner 2026-09-28: wait for the notifications.** A figure cited to the FAQ would be a labelled but unconfirmed legal figure, the pattern rejected on D-W3 and in D-C2's removed fallback. The wait covers **both** rates: the admin charge's Gazette grounding is under the old scheme, so under the 2026 scheme it is in the same position as EDLI's. Next action: find the notifications under EPF Scheme 2026 para 29(1) and EDLI Scheme 2026 para 5(2) (Gazette, Ministry of Labour, from June 2026). The CA packet §4 asks the same question. |
