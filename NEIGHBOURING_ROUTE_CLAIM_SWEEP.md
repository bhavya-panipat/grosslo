# The two neighbouring routes — the same sweep

**Why this exists.** `EXPORT_NUMERIC_CLAIM_SWEEP.md` (2026-09-21) closed its §5
by recording what it deliberately did not cover: the per-row export and
`/api/batch-audit`, both of which share the shape that produced four defects in
a week. The owner asked for those two on 2026-09-22. This is that sweep, run
with the same method and the same question.

**The question, unchanged:** does this total actually account for everything it
claims to describe?

**Method.** Every response field enumerated from the code, not from memory. For
each: what it claims, what it sums, and whether the second accounts for the
first. Verified by running where a run settles it — through the real Flask
routes, not the underlying functions, wherever the route adds anything.

**Result: two new defects of the same class, two names that overstate their
content, one inherited gap, and several claims confirmed exact.** One of the two
new defects reaches a headline figure on the batch executive summary. Nothing is
fixed here.

---

## 1. `/api/batch-audit`

### 1.1 B1 — `unclaimed_savings` compares two different amounts of money

**This is the sweep's main finding.**

The route computes, per row:

```python
current_best = best_regime_for_given_structure(structure, rent_paid, city)
optimal      = optimize(ctc=structure.ctc, ...)
unclaimed_savings = max(0.0, current_best.total_tax - optimal.total_tax)
```

`current_best` is the tax on **the components as supplied**. `optimal` is the
tax on a structure built for **the stated `ctc` column**. Nothing anywhere
requires those to describe the same amount of money: the route validates
`ctc > 0` and `basic > 0`, and never checks that the components reconcile to the
CTC. So the subtraction is not a like-for-like comparison, and the difference is
reported as money the company is leaving on the table.

**This is not a malformed-input case.** Real stated CTCs routinely include
gratuity, insurance premiums and bonus provisions that this tool does not model,
so the component columns legitimately sum to less than the `ctc` column for an
ordinary employee. Measured on the recommended split with a statutory gratuity
accrual (4.81% of basic) inside the stated CTC, rent ₹2.4L, metro:

| Stated CTC | Gap (gratuity) | True like-for-like saving | Reported | Understated by |
|---|---|---|---|---|
| ₹6,00,000 | ₹11,544 | ₹0 | ₹0 | — |
| ₹12,00,000 | ₹23,088 | ₹0 | ₹0 | — |
| ₹18,00,000 | ₹34,632 | ₹6,556.55 | ₹1,542.94 | 76% |
| ₹24,00,000 | ₹46,176 | ₹14,111.59 | ₹2,970.24 | 79% |
| ₹36,00,000 | ₹69,264 | ₹25,400.85 | ₹5,346.43 | 79% |
| ₹50,00,000 | ₹96,200 | ₹35,278.96 | ₹7,425.60 | 79% |

**The error runs both ways, and the other direction fabricates.** Where the
`ctc` column is *lower* than the components — a CSV whose CTC field holds fixed
pay while the component columns hold gross, which the required-column check
cannot detect — the route compares a real structure against a cheaper optimal
one and reports the entire difference as a saving. Measured on a ₹15,48,000
structure with `ctc` stated as ₹10,00,000:

| | |
|---|---|
| Current tax on the real structure | ₹93,756.00 |
| "Optimal" tax, for the stated ₹10L | ₹0.00 |
| **`unclaimed_savings` reported** | **₹93,756.00** |

The entire tax bill, reported as discovered savings. There is no saving: the
comparison is against a structure that pays the employee ₹5.48L less.

**Where it surfaces.** `summary.total_unclaimed_savings` is the sum of this
figure across the batch, and `executive-summary-card.tsx` renders it as
**"Discovered Annual Tax Inefficiency"**, detailed as *"Gap between current
structures and the optimal split, summed"*. The optimal split of **what** is the
missing word, and it is the whole defect.

**The frontend does not prevent it.** `csv-upload-card.tsx` requires every
component column to be *present*, which blocks a missing-column path, and does
not check that the values *reconcile* — a different thing. The API checks
neither.

**Nothing enforces reconciliation anywhere.** The first sweep recorded the same
root cause under `band_cost_neutrality`: a structure whose components do not
reconcile is judged on its stated figure, "which is what rule R8 exists to
catch, and R8 is a candidate, so nothing enforces it." B1 is that same
unenforced assumption, surfacing in a currency total rather than a verdict.

### 1.2 B2 — one row, two definitions of CTC

The same response, on the same row, uses both definitions at once. Measured on
the ₹36L gratuity case above:

| Field | Built from | Value |
|---|---|---|
| `treasury_forecast.total_capital_outlay` | the **real components** | ₹35,30,736.00 |
| `unclaimed_savings` | the **stated `ctc`** | ₹5,346.43 |

Each is individually defensible — funding should follow real money, and a band
check follows the stated figure. **What is not defensible is that the response
carries both without saying so.** A reader summing the liability column and the
savings column is combining two different assumptions about what this employee
costs, and nothing in the payload or the card marks the difference.

### 1.3 B3 — `summary.total_rows` is the valid-row count

`total_rows` is `valid_row_count`, which skips malformed rows; those still
appear in `rows[]` carrying an `error`. Measured: three rows submitted, one
malformed, `total_rows: 2` while `len(rows) == 3`.

**Not a live defect, and the reason is worth recording.** Its one consumer reads
it correctly: `batch-flow.tsx` passes it as `processedCount` against the
uploaded row count, and the card shows *"Processed Records: N / M"* with a
throughput percentage — which surfaces the gap rather than hiding it. The API
field name is the only thing that misleads, and only for a future caller.

### 1.4 `penalty_scenario` — inherits D-S1, and one cap that never binds

`build_scenario_table(sum_monthly_epf, sum_monthly_tds)`:

| Claim | Is | Verdict |
|---|---|---|
| EPF arrears base | `Σ epfo_challan_annual / 12` | **Inherits D-S1.** The PF shares only; EDLI and administrative charges are absent, so every 7Q and 14B figure derived from it is proportionally low. |
| TDS arrears base | `Σ total_tax / 12` | **Exact given the engine**, and twelve equal instalments is already a recorded s. 392 simplification. |
| s. 7Q interest, s. 14B damages, s. 398(3) interest | rate × base × months | **Exact arithmetic**, on rates the module documents and dates. |
| `section_14b_cap_applied` | the 100%-of-arrears ceiling | **Correct but unreachable here.** The cap is applied to a *pooled* multi-employee total rather than per employer arrears, which at 1%/month would take ~100 months to bind; the presets stop at 12, so it never fires. Recorded because pooling is a real modelling choice, not because it produces a wrong figure today. |
| `disclaimer` | illustrative, not a finding | **Accurate**, and the module docstring is unusually explicit about what it excludes and why (s. 448 checked and excluded on a cited ruling). |

### 1.5 Confirmed exact — including one I expected to fail

| Claim | Verdict |
|---|---|
| `clean_count` / `flagged_count` | **Exact for what they say.** Audit-optimality, not compliance routing. |
| The docstring's claim that the card's Clean Rate reads `orchestration.route` and never this pair | **True — checked in the file, not taken on the docstring's word.** `executive-summary-card.tsx:24` filters on `route === "auto_pass_candidate"`. |
| Does the tool ever recommend a structure its own R1 rule flags? | **No, tested and it did not reproduce.** Feeding `optimize()`'s own recommendations back through the route at four CTCs: basic lands at 50.0% (₹12L) and 60.0% (above), 4/4 clean, `statutory_violation_count: 0`. The ₹12L case sits exactly on the Code on Wages floor, so the margin is zero but the direction is right. |
| `excess_contribution` | **Exact only where superannuation is zero** — the recorded R5 limitation, unchanged. |
| `regime_mismatch` | **Exact**, and genuinely distinct from `unclaimed_savings > 0`. |
| `statutory_violation_count` | **Exact**, and the docstring correctly declines to claim the three exception counts sum to `flagged_count`. |

## 2. `/api/submissions/<id>/rows/<i>/export`

### 2.1 X1 — the payload mixes two computation bases

Within one payload:

| Field | Computed |
|---|---|
| `treasury_forecast` | **fresh**, at export time (`optimize()` re-run from `input`) |
| `payouts[]`, `payout_basis` | **fresh**, from the same re-run |
| `guardrail` | **stored**, `computed.get("guardrail")` from submission time |

Verified on the live route: the payload's `guardrail` is byte-identical to the
stored one while the forecast beside it was recomputed.

With an unchanged engine the two agree, because `optimize()` is deterministic.
**They diverge exactly when the engine changes** — which it did on 2026-09-19,
when the employer-NPS fix changed the recommended structure in 111 of 1,140
swept cases. Any row submitted before that fix and exported after it carries a
guardrail verdict evaluated against a structure that is not the one being paid.

### 2.2 X2 — the basis flags reach the screen but not the artefact

`review_queue._row_to_dict()` attaches `tax_basis_flag` and
`treasury_basis_flag` to every row it returns, and appends their reasons to
`orchestration.reasons`. This route reads its row through `get_submission()`, so
**it holds both flags.** It reads neither, and `app.py` does not contain the
string `tax_basis` anywhere.

Verified end to end — a row forced to the pre-fix basis, then exported:

| | |
|---|---|
| `tax_basis_flag` on the row the route reads | **True** |
| the warning present in `orchestration.reasons` | **True** |
| export status | **200** |
| payload keys | `WARNING_DO_NOT_UPLOAD`, `guardrail`, `idempotency_key_hint`, `payout_basis`, `payouts`, `source_account_is_placeholder`, `treasury_forecast` |
| payload mentions the flag or its reason | **False** |

**The flag stops at the queue screen.** D1-4 and D-T3 built the read-time
mechanism so that a figure someone may act on says when its basis is superseded.
The payment instruction is the document that gets acted on, and it is the one
surface the flag does not reach. The route already knows how to put a warning in
both a payload and a header — `WARNING_DO_NOT_UPLOAD` and
`X-Source-Account-Placeholder` do exactly that for the placeholder account — so
the mechanism to carry it is present and unused.

### 2.3 X3 — "current vs. corrected" describes a file with no current column

The route's docstring says the correction path yields *"a Bulk Salary Revision
XLSX, current vs. corrected, via salary_revision_export.py"*. The caller duly
passes `"current": inp["current_structure"]`.

**`build_salary_revision_workbook()` never reads it.** The string `current`
appears in that module exactly once, in the docstring describing the parameter
shape. Verified by generating a workbook:

- **Default Structure:** `Employee Name`, `Revised CTC`
- **Custom Structure:** `Employee Name`, `CTC`, `Basic`, `HRA`, `LTA`, `Special Allowance`, `Employer PF`, `Employer NPS` — **corrected values only**

There is no current-versus-corrected comparison in the file. **The file itself is
honest** — its Read Me sheet says it "contains corrected structures". The route
docstring is what overstates, and the passed-in `current` is dead data.

### 2.4 Confirmed exact

| Claim | Verdict |
|---|---|
| Custom Structure components vs. stated CTC | **Exact to the rupee** (₹40,00,000 case reconciles). |
| `payouts[]`, `payout_basis`, `treasury_forecast` | **Inherit §1 and §3 of the first sweep**, including D-S1, and are recomputed rather than stale. |
| Placeholder source account | **Exact and loud**, in body and header both. |
| Export refused unless the row is `approved` | **Exact**, and separately tested. |
| Bank details absent | **Refused**, rather than fabricated. |

## 3. What this sweep did not cover

- **`/api/optimize` and `/api/sensitivity`**, the remaining compute routes.
- **The audit-log entries** both routes write, beyond noting that the per-row
  export records `total_capital_outlay` and the placeholder flag.
- **The AI layer's rephrasings**, guarded separately.

## 4. Decisions for the owner

| | Decision | Recommendation |
|---|---|---|
| **D-S2** | `unclaimed_savings` compares tax across two different amounts of money (B1). Fix, or constrain the input? | **Constrain the input, and say what the figure means.** Compute the optimum from `structure.total()` rather than the stated `ctc`, so both sides describe the same money — and report the reconciliation gap on the row instead of silently absorbing it, since a gap is real information about the offer letter. Changing the comparison moves a headline figure in both directions, so it needs its own design, its own before/after measurement across the CTC range, and its own sabotage. **Not to be folded into anything else.** |
| **D-S3** | The basis flags don't reach the exported payload (X2). Carry them, or refuse the export? | **Carry them, don't refuse.** A pre-fix row is not unexportable — its figure may well be right, and D1-7(b) already settled that the reasons say so rather than the route blocking. The payload should carry `tax_basis_flag` and the same reason text the queue shows, by the `WARNING_DO_NOT_UPLOAD` precedent already in this route. Refusing would be a new gate on approved work, which is a product decision and not this one. |
| **D-S4** | X1's mixed bases: recompute the guardrail at export, or serve the stored one and label it? | **Label, don't recompute — and this is the one I am least sure of.** Recomputing makes the payload internally consistent but silently replaces the verdict a human approved with one nobody reviewed, which is the maker-checker gate eroding by a side effect. Labelling keeps the approved verdict and says when it was computed. If the owner reads the gate differently, this flips. |
| **D-S5** | The two overstating names (B3 `total_rows`, X3 "current vs. corrected"). | **Correct both, and they are the cheap half of this sweep.** The docstring is a one-line correction to match the file. `total_rows` has one consumer that already uses it correctly, so renaming it to `valid_row_count` is safe today and gets cheaper never. |

## 5. Not in scope

Any code change; any change to what the guardrail does, to who approves a
payout, or to when bulk-approve blocks; the D-S1 primary-source lookup.
