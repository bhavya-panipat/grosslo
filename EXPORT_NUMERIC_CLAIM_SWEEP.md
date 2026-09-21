# Every numeric claim `/api/export-razorpayx` makes — a deliberate sweep

**Why this exists.** Three defects of the same shape were found on this route
family in one week, each while fixing something else: the tax engine's employer
NPS double count, the payout paying gross, and the treasury total omitting the
employer's NPS remittance. Each was **a total that did not account for what it
claimed to describe.**

The owner's instruction, 2026-09-21: sweep every other numeric claim this route
makes, against that same question, rather than waiting for a fourth instance to
surface the same way the first three did.

**Method.** Every field of the response enumerated from the code, not from
memory. For each: what does it claim to describe, what does it actually sum, and
does the second account for the first. Verified by running where a run settles
it.

**Result: two claims are exact, three are exact only under a stated condition,
and one is a name that overstates its content.** No new arithmetic error. The
overstated name is recorded below and is not fixed here.

---

## 1. `treasury_forecast`

| Field | Claims | Is | Verdict |
|---|---|---|---|
| `total_capital_outlay` | what the company must fund | five components summed | **Exact.** Pinned to `SalaryStructure.total()` since `a19d912`. |
| `average_monthly_outlay` | an average month | a twelfth of the total | **Exact, and honestly named.** February is higher; a test pins that. |
| `net_take_home_annual` | reaches the employee's account | cash − employee PF − tax − PT | **Exact** for what this tool models. |
| `tds_escrow_annual` | TDS to escrow | the computed annual tax | **Exact**, given the engine. |
| `nps_remittance_annual` | the employer's NPS remittance | `structure.employer_nps` | **Exact.** |
| `professional_tax_annual` | the year's PT | 11 base months + February | **Exact** where the state is modelled; `pt_state_recognized` reports when it is not, and `pt_is_approximation` flags Tamil Nadu's half-yearly conversion. |
| `funding_deadline_hours_before_payroll` | when to fund | a constant, 48 | Not a total. A policy statement, and the frontend prints it as one. |

### 1.1 `epfo_challan_annual` — the name overstates the content

It is `structure.employer_pf + derive_pf(structure.basic)`: the employer's PF
share plus the employee's. **A real EPF challan is not only those two.** An ECR
also carries EDLI and administrative charges, and the employer's own share is
apportioned between the pension scheme and the provident fund — the split does
not change the total, but the additional charges do.

**What is asserted here and what is not.** That EDLI and administrative charges
exist as challan components is a statement about EPFO's remittance form, and
**this sweep does not assert their rates**: nothing in this repository cites a
primary source for them, and no figure should be written down from memory. What
is established is narrower and sufficient to record the gap:

- the code sums exactly two quantities, both PF shares, verified by reading it;
- nothing anywhere in the repository mentions EDLI, administrative charges or
  the pension-scheme apportionment — `grep -ri` returns nothing;
- so a figure named *"EPFO challan"* is the PF shares only, and a company
  funding exactly this amount would fund less than a real challan.

**This is the same defect class as the three already fixed**, caught by the same
question, and it is **not fixed here** because unlike those three it cannot be
fixed from arithmetic already in the repository: it needs a primary-source rate
for each missing component, which is a person-with-a-browser task of the kind
`docs/PRIMARY_SOURCE_LOOKUP_TASK.md` already describes. Recorded as an open gap
with that as its next action.

## 2. `compliance_metadata` — the guardrail's three checks

| Check | Claims | Is | Verdict |
|---|---|---|---|
| `band_cost_neutrality` | the CTC is within the approved band | compares `structure.ctc`, the **stated** CTC | **Exact on this route**, verified: `optimize()`'s recommended structure has `total() == ctc` to the paisa at every CTC tested. A structure whose components do not reconcile would be judged on its stated figure rather than its real cost — which is what rule R8 exists to catch, and R8 is a candidate, so nothing enforces it. |
| `epfo_ceiling` | aggregate employer contributions are under ₹7.5L | `employer_pf + employer_nps` | **Exact only where superannuation is zero.** The statutory aggregate covers three funds: PF, NPS and an approved superannuation fund. This tool models no superannuation component at all, so the sum is complete for every structure it can produce and incomplete for a real employee who has one. Already recorded — `compliance_rules.py` R5 and the CA packet both say so. |
| `80ccd2_cap` | employer NPS is within the s. 124 cap | `cap_pct × basic` | **Exact only where DA is zero and the employer is non-government.** The statute's base is salary including DA, and a government employer's old-regime rate is 14%. Both are TE4's recorded divergences, and their direction is now known: the tool's cap never exceeds the lawful one, so tax errs high and the guardrail false-flags lawful contributions. |

## 3. `payouts[]` and `payout_basis`

| Field | Claims | Is | Verdict |
|---|---|---|---|
| `payouts[].amount` | what to pay this person | a twelfth of `net_take_home_annual`, in paise | **Exact** since `b4bab69`, and pinned to the forecast in the same response. |
| `payout_basis.*` | what was withheld | gross, employee PF, TDS, PT, net | **Exact**: `net == gross − PF − TDS − PT` is asserted on the live response. |
| `payouts` length | one per employee | — | **Now constrained to one** (`EXPORT_EMPLOYEE_LIST_DESIGN.md`, D-E1): the route refuses a longer list rather than paying N people one person's figure beside a one-person forecast. |

## 4. `execution_trace`

`trace_guardrail_stage()` emits no figures of its own. It quotes the guardrail's
own messages verbatim, so its numbers are the §2 numbers and inherit their
verdicts exactly.

## 5. What this sweep did not cover

- **`/api/submissions/<id>/rows/<i>/export`**, which shares
  `_build_composite_payout` and `treasury_forecast` and therefore inherits §1 and
  §3, but adds the source-account placeholder path. Not swept.
- **`/api/batch-audit`'s** summary totals and penalty scenario. Its
  `unclaimed_savings` and `clean_count` were corrected as part of the tax fix,
  but the route has not had a sweep of this kind.
- **The AI layer's rephrasings**, which are guarded separately by the numeric
  guard and are another session's territory.

Recording these plainly: this sweep is one route, deliberately, and two
neighbours with the same shape have not had one.

## 6. Decision for the owner

| | Decision | Recommendation |
|---|---|---|
| **D-S1** | `epfo_challan_annual` names a challan it does not fully compute. Fix, rename, or record? | **Record now, fix after a primary-source lookup.** The missing components' rates are not in this repository and must not be written from memory. Until then the field is a PF-shares total wearing a challan's name, which is the gap this sweep exists to find. A rename (`pf_contributions_annual`) would make today's content accurate immediately and is the cheaper half, if the owner wants the name honest before the figure is complete. |
