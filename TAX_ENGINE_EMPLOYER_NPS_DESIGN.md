# Employer NPS in taxable income — fix design

**Status:** D1-1 to D1-4 **approved 2026-09-15** (§6). Before implementation, the
approval asked for a blast-radius check on the payroll-liability and treasury
figures. That check is §8. It found more affected figures than §2 listed, one
claim in §2 that is wrong, and three new decisions for how D1-4 is carried out
(D1-5 to D1-7). *Updated the same day:* D1-5 and D1-6 are approved. The owner
asked whether the error reaches routing, which §8.7 answers: it does, through the
regime, and only toward escalation. §8.7 also found that the recommended
structure changes in 111 of 1,140 cases, contrary to §1.3. That undoes the
reasoning given for approving D1-7, so **D1-7 is reopened (§8.6), and
implementation waits on it.** `tax_engine.py` is not changed.
Decision D1 of `R1_TE4_RECORD_UPDATE_DESIGN.md` approved *opening* this design
ahead of the record updates; the standing rule that a design is approved before
implementation applies here with more force than anywhere else, because this is
the tax math the numeric guard exists to protect.

---

## 1. The defect

### 1.1 The statute — read from the primary source, 2026-09-14

Income-tax Act, 2025, as amended by Finance Act 2026, `incometaxindia.gov.in`:

- **s. 16(k)** — *"salary" includes … "the contribution made by the Central
  Government or any other employer in any tax year, to the account of an
  employee under a pension scheme referred to in section 124"*.
- **s. 124(1)** — that contribution is deductible *"in the computation of his
  total income"* up to 10% of salary; 14% for a Central/State Government
  employer (s. 124(1)(a)); 10% read as 14% under s. 202(1), the new regime
  (s. 124(2)). *Salary* includes DA (s. 124(13)(b)).

**Employer NPS is added to salary, then deducted up to the cap.** Within the cap
the two cancel; above it, the excess stays taxable.

### 1.2 The code

```python
gross_salary = structure.basic + structure.hra + structure.lta + structure.special_allowance
...
taxable = (gross_salary - hra_exempt - lta_exempt - std_deduction - structure.employer_nps)   # old
taxable = gross_salary - std_deduction - structure.employer_nps                                # new
```

Employer NPS is **left out of** `gross_salary` and **subtracted anyway**,
uncapped. The function's docstring states the intended result — within the cap,
*"fully exempt"*, i.e. net zero. The code produces net **minus** the
contribution.

### 1.3 Measured — a read-only prototype, patched in memory, no file changed

**Two structures, same CTC,** ₹80,000 moved from special allowance into employer
NPS (at the old-regime cap for a non-government employer):

| regime | engine: B − A | statute: B − A | under-statement of taxable income |
|---|---|---|---|
| old | −₹1,60,000 | −₹80,000 | ₹80,000 |
| new | −₹1,60,000 | −₹80,000 | ₹80,000 |

**Across the optimizer** — 36 input combinations (6 CTCs × 3 rent/city pairs ×
NPS on/off), current engine against the statute-shaped fix in §3:

| CTC | NPS | recommended structure | regime | recommended tax now | fixed | difference |
|---|---|---|---|---|---|---|
| ₹6L, ₹12L | on | unchanged | unchanged | ₹0 | ₹0 | — |
| ₹18L | on | unchanged | unchanged | ₹76,908 | ₹1,00,495 | **+₹23,587** |
| ₹24L | on | unchanged | unchanged | ₹1,55,792 | ₹1,97,725 | **+₹41,933** |
| ₹36L | on | unchanged | unchanged | ₹3,93,432 | ₹4,87,781 | **+₹94,349** |
| ₹50L | on | unchanged | unchanged | ₹7,25,400 | ₹8,56,440 | **+₹1,31,040** |
| any | **off** | unchanged | unchanged | — | — | **none** |

What the sweep establishes:

- **Every structure with employer NPS has its tax under-stated by exactly the tax
  on the full contribution at its marginal rate.** At ₹50L:
  ₹4,20,000 × 30% × 1.04 = ₹1,31,040, to the rupee.
- **Nothing without employer NPS moves.**
- **No recommendation changes** — not the structure (same basic, same NPS) and
  not the regime, in any of the 36 cases. The fix corrects the *figure*, not the
  *advice*.
  **Corrected 2026-09-15 (§8.7): false beyond these 36 cases.** A 1,140-case
  sweep changes the recommended regime or structure in 111 cases. The 36 grid
  points happened to sit where nothing moves. This is the granularity trap
  again: a sample checked at a coarser level than the claim.
- At ₹6L and ₹12L the effect is masked by the rebate, not absent.

**At mid-range CTCs the tool currently shows roughly 15–24% less tax than is
owed** for NPS-opted structures (₹23,587 on ₹1,00,495 is 23.5%; ₹1,31,040 on
₹8,56,440 is 15.3%).

---

## 2. Where the wrong figure goes

Traced, not assumed:

- **`optimizer.py`** calls `taxable_income_for_structure` in four places:
  `evaluate_given_structure` (an as-offered structure), `optimize_new_regime`,
  `optimize_old_regime`, and `naive_baseline_tax`. Everything built on the first
  three inherits the error — recommended tax, the regime comparison, the
  theoretical minimum.
- **`naive_baseline_tax` is unaffected**: it builds its structure with
  `nps_opted=False`. So any saving measured *against that baseline* is
  **over-stated** whenever the recommendation carries employer NPS — the
  recommended side is too low and the baseline side is right.
- **The negotiation view** (`ai_layer.py`) deliberately attributes no rupees to
  any single lever — it names `"NPS enrollment"` as a lever that changed, with no
  amount. What does carry the error is its **total** saving, a plain subtraction
  between the as-extracted and recommended structures: extraction sets employer
  NPS to zero unless stated, so when the recommendation adds NPS the total saving
  is over-stated by the same amount.
- **`/api/batch-audit`** (`app.py`) reads `employer_nps` straight from a CSV
  column. Those are *as-offered* structures and **can exceed the cap** — where
  the engine deducts the uncapped amount, a second error on top of the double
  count.
- **The extraction path** (`app.py`) sets `employer_nps = 0.0` unless stated, so
  structures parsed from offer letters are mostly unaffected.
- **The characterization baseline** — one pinned case, `nps_opted_non_metro`,
  would move.
- **Stored submissions and audit-log entries** computed before a fix carry the
  wrong tax. Whether any user acted on such a figure is **not measured and cannot
  be determined from the code.** It is decision D1-4.
  *(Corrected 2026-09-15, §8.4: the audit-log half is wrong. Neither
  `audit_log.jsonl` nor `process_log.jsonl` records any tax figure. Stored
  submissions do.)*
- *(Added 2026-09-15.)* This list was incomplete. It missed the treasury
  forecast's TDS/take-home split, the penalty scenario, the ring metric, the
  batch "clean" count and the regime-comparison saving. See §8.

---

## 3. Fix options

### Option A — stop subtracting

Remove `- structure.employer_nps`. Net zero, matching the docstring's intent.

**Correct only while the contribution is within the cap.** An as-offered
structure above the cap would have its excess silently exempted, still
under-stating tax. Batch audit reaches exactly that case. **Rejected:** it fixes
the measured case and leaves the adjacent one wrong.

### Option B — model the statute's shape (recommended)

```python
gross_salary = basic + hra + lta + special_allowance + employer_nps        # s. 16(k)
nps_deduction = min(employer_nps, NPS_80CCD2_CAP_PCT[regime] * basic)       # s. 124(1)-(2)
taxable = gross_salary - … - nps_deduction
```

**Correct within the cap and above it**, and its structure mirrors the statute,
so a reader can check it line by line against s. 16(k) and s. 124.

**It still carries the tool's two recorded assumptions, and does not fix them:**
the cap is applied to *basic* rather than salary-including-DA, and at the
non-government rate. Those are TE4's `known_divergence` items, and they stay
divergences. Option B is what makes their *direction* statable for the first
time — §4.3.

---

## 4. Consequences of Option B

### 4.1 Candidate R7 loses most of its reason to exist

R7 flags employer NPS present without an NPS opt-in, because *"the tax
computation deducts the employer NPS contribution regardless of the opt-in flag,
so the tax figure shown for this structure may be understated"*. That
consequence **is the double count.** Under Option B the pair nets to zero within
the cap, and the tax figure is not under-stated.

- `test_R7_claim_1_tax_ignores_nps_opted_entirely` **still passes** — the engine
  still ignores `nps_opted`.
- **R7's `rationale` and `basis` become false** within the cap. Its basis quotes
  the `- structure.employer_nps` expression verbatim.

R7 is a CANDIDATE, inert by construction, so nothing a user sees changes. But its
recorded reasoning would be wrong. **Decision D1-3:** redraft R7 for the
above-cap residue, or retire it.

### 4.2 The docstring stops contradicting its code

*"Employer NPS beyond the cap would be taxable but we assume contribution == cap,
so fully exempt"* — Option B makes the first half true without the assumption.
Rewritten in the same commit.

### 4.3 TE4's divergence direction becomes statable

With the double count gone, applying the cap to basic at the non-government rate
gives a deduction **no larger** than the statute allows. Where the tool's cap is
lower than the lawful one — a government employer under the old regime, or an
employer paying DA — **taxable income is over-stated, never under-stated.** The
direction is conservative for tax. It is not conservative for the guardrail,
which false-flags lawful contributions (`R1_TE4_RECORD_UPDATE_DESIGN.md` §3.4).

**This paragraph is a prediction about Option B,** and it goes into TE4's
divergence only once Option B is implemented and the direction is measured. Until
then, TE4's record says *pending D1*.

---

## 5. Implementation plan, if approved

Separate commits, full suite after each, request/go handshake.

1. **A test that pins the statute, first, and fails today.** Moving X from special
   allowance into employer NPS lowers taxable income by exactly X within the cap,
   and by exactly the cap above it — in both regimes. Committed red, as step 3 of
   the R5 propagation was, so the failure is on record before the fix.
2. **Option B** in `taxable_income_for_structure`, plus its docstring. Behavioural.
3. **Recapture the characterization baseline, deliberately.** Its policy — *"a
   diff here is either a bug or a deliberate change someone has to justify"* —
   applies in full. Justification: `--check` must drift **only**
   `nps_opted_non_metro`, and within it only tax-derived figures, each by the tax
   on that case's employer NPS.
4. **Every other test that moves**, named test by test. Each is either pinning
   the double count, and retargeted with that said, or it is a regression.
5. **R7's record** (D1-3).
6. **TE4's divergence direction** — measured on the fixed engine, then written.

**Sabotage:** restore the uncapped subtraction and confirm the statute test fails.
Remove the `min()` cap and confirm the above-cap half fails on its own.

---

## 6. Decisions needed

**D1-1 to D1-4 approved 2026-09-15 by the project owner, as recommended:** fix it,
Option B, redraft R7, record the cut-over and visibly flag affected submissions.
The owner's reasoning on D1-4: *make the compromised state visibly different, not
silently different*, as with `PLACEHOLDER-DO-NOT-UPLOAD` and `guardrail_not_run`.
The approval added a condition: measure the liability and treasury figures
before this is called done. That measurement is §8. D1-5 to D1-7 are in §8.6.

| | Decision | Recommendation |
|---|---|---|
| **D1-1** | Approve fixing the tax engine? | **Yes.** Tax is under-stated by the full contribution's tax for every NPS-opted structure, 15–24% at mid-range CTCs. |
| **D1-2** | Option A or Option B? | **B** — A leaves above-cap batch-audit structures wrong. |
| **D1-3** | Candidate R7: redraft for the above-cap residue, or retire? | **Redraft** — above the cap, opt-in genuinely matters again. *(Corrected 2026-09-15, before approval: that reason was too thin. After Option B, the contradiction has no tax effect within the cap. Above the cap, if the not-opted flag is the true input, the phantom contribution's excess is taxed and tax is **over**-stated, not under-stated. The redraft says that, and keeps the opt-in question for the CA. Approved on the corrected reasoning.)* |
| **D1-4** | Stored submissions and audit-log entries computed before the fix: flag them, recompute them, or record the cut-over date only? | **Record the cut-over date and flag affected submissions visibly; do not silently recompute.** A figure someone may have acted on should not change underneath them without notice. This one needs the project owner, not a default. |

## 7. Not in scope

- **The two carried assumptions** — basic rather than salary-including-DA, and
  the non-government rate. They are TE4 divergences; modelling them is a scope
  decision about what the tool represents.
- **Employer PF.** Left out of `gross_salary` and not subtracted: net zero, which
  matches its treatment within limits. The unmodelled s. 17(1)(h) excess above
  ₹7.5L aggregate is R5's recorded gap, and separate.
- **The `80ccd2_cap` guardrail's wording** — active work in another session.

---

## 8. Blast radius beyond the tax figure (added 2026-09-15)

The approval asked for this before implementation. Its question: if tax was
under-stated, then TDS was too. Do the Executive Summary's "Total Monthly Payroll
Liability" and the Treasury Gate's "Required Treasury Funding" go wrong for the
same structures?

**Method.** Read-only, same as §1.3. Option B was patched in memory into both
`tax_engine` and `optimizer`, since `optimizer` imports the function by name. No
repository file was changed. The AI client was asserted absent before running.

- **Consumers:** the real product functions (`best_regime_for_given_structure`,
  `optimize`, `optimization_value_pct`, `treasury_forecast`,
  `evaluate_band_guardrail`, `build_scenario_table`).
- **Batch-audit loop:** `/api/batch-audit`'s loop body was replayed with those
  functions. Importing `app.py` needs Postgres and appends to `audit_log.jsonl`.
- **Inputs:** 15 as-offered batch rows (₹18L, ₹36L and ₹50L CTC). Each CTC was
  run with no NPS, NPS at 10% of basic, at 14%, at 20%, and at 14% with
  `nps_opted` false (the R7 case). The 36-case optimizer sweep from §1.3 was
  re-run through `treasury_forecast`.

### 8.1 The two liability totals do not move, and cannot

**Both totals are unchanged in every case measured:** 15 batch rows, 36 sweep
cases, and a batch total of ₹4,89,84,000 before and after. This follows from the
code, not only from the sample. From `payroll_breakdown.treasury_forecast()`:

```
net_take_home       = cash − employee_pf − total_tax − PT
total_capital_outlay = net_take_home + total_tax + epfo_challan + PT
                     = cash − employee_pf + (employer_pf + employee_pf)
                     = cash + employer_pf
```

`total_tax` enters once with each sign and cancels. Both banners sum
`total_capital_outlay` through the shared `frontend/lib/treasury.ts`, so
**neither total depends on tax at all.** This holds for this bug and for any
other tax error.

**The concern is right about its components.** Inside that unchanged total:

- `tds_escrow_annual` is **under-stated**.
- `net_take_home_annual` is **over-stated** by the same amount.

Both move by exactly the §1.3 tax difference: ₹23,587 at ₹18L to ₹1,31,040 at
₹50L, in all 12 NPS-on sweep cases. The totals are right. The split is not.
Where the split is displayed (the RazorpayX export modal's "Net take-home" and
"TDS escrow" lines, and any stored row's `treasury_forecast`), it over-states
take-home pay and under-states the TDS to escrow. The Executive Summary card
shows only the total, and names the components in its detail text without their
values.

### 8.2 Other figures that do move

| Figure | Where it shows | Current engine error |
|---|---|---|
| **Penalty scenario, s. 398(3) interest** | `/api/batch-audit` `penalty_scenario` | **Under-stated.** Sums `total_tax / 12`. For the 15-row sample: ₹8,645 → ₹9,846 at one month, ₹1,03,741 → ₹1,18,148 at twelve. The EPF columns do not move. |
| **`optimization_value_pct`** (ring metric) | every optimize response | **Over-stated, by roughly half** with NPS on (rent ₹2.4L, metro): 40.1% → 21.7% at ₹18L; 38.9% → 22.5% at ₹24L; 33.9% → 18.1% at ₹36L; 27.9% → 14.9% at ₹50L. Same cause as §2's naive-baseline point. |
| **`annual_saving`** (regime comparison) | optimize response; `MATH_SOLVER` trace message | **Wrong in both directions**, because the old- and new-regime caps differ: ₹47,861 → ₹62,837 at ₹12L (under-stated); ₹2,17,402 → ₹1,90,445 at ₹36L and ₹2,15,280 → ₹1,77,840 at ₹50L (over-stated). The recommended regime does not change. |
| **Batch `unclaimed_savings`** → "Discovered Annual Tax Inefficiency" | Executive Summary card | **Wrong in both directions.** NPS at the cap: over-stated (₹22,464 → ₹12,917 at ₹18L). NPS above the cap: **reported as ₹0 when it is not** (₹0 → ₹7,301 at ₹18L; ₹0 → ₹29,203 at ₹36L). The uncapped deduction makes an over-cap offer look optimal. |
| **Batch `clean_count` / `flagged_count`** | batch summary | Above-cap rows with no EPFO excess count as **clean when they are not** (18L and 36L, 20% rows: `clean` true → false). The Executive Summary's *Compliance Clean Rate* reads `orchestration.route`, and route does not read `unclaimed_savings` or `clean`. *(Corrected 2026-09-15, §8.7: "does not move" was measured on 15 rows only. Route **does** read a tax-derived value, the regime, and changes on a wider sweep.)* |
| **Salary Revision export row selection** | who gets exported | Selection includes unclaimed-savings rows, so an above-cap employee can be left out. The file's contents are optimizer output and inherit the fix. |

**Measured as unchanged:** the guardrail verdict and failing checks (15/15), the
current regime (15/15), `regime_mismatch` (15/15), the recommended structure and
regime (36/36), and every figure on a structure with no employer NPS.
*(Corrected 2026-09-15: every "unchanged" in that sentence except the last was a
small sample. §8.7 re-measures them wider, and three of them do move.)*

**R7's case behaves like the opted-in case.** An NPS-at-14%, not-opted row moves
by the same ₹19,656 at ₹18L as the opted row. The engine never reads
`nps_opted`, before or after. §4.1 stands.

### 8.3 Three pre-existing gaps found on the way, not caused by this bug

They are recorded here so that "checked, doesn't affect my change" is not the
last anyone hears of them.

1. **The treasury total leaves out employer NPS.** The algebra above gives
   `total_capital_outlay = cash + employer_pf`. The employer's NPS remittance is a
   real outflow, but it appears in no component. Measured: an ₹18L structure
   with 14% NPS reports ₹16,74,000, which is CTC less the ₹1,26,000 contribution.
   Required Treasury Funding is under-stated by the employer NPS of every pending
   row that has it.
2. **The payout payload's amount is gross, not net.** `_build_composite_payout()`
   in `app.py` sets `amount` from `(basic + hra + lta + special_allowance) / 12`,
   in a variable named `net_monthly`. No TDS, employee PF or PT is withheld.
   `payroll_breakdown.net_monthly_disbursement()`, which does withhold them, has
   **no callers anywhere in the repository**. No test pins the payout amount.
   This is present since `90e43cc` (2026-08-31). Payloads are schema-only, and no
   dispatch exists.
3. **Both banners display an annual figure without saying so, and one calls it
   monthly.** `treasury_forecast()` is an *"Annual capital-outlay forecast"*, and
   every field in it is `_annual`.
   - `executive-summary-card.tsx` labels the sum of `total_capital_outlay`
     **"Total Monthly Payroll Liability"**, with no division by 12 anywhere on
     that path.
   - `finance-flow.tsx` compares the same annual sum to the live RazorpayX
     balance as "Required Treasury Funding". The deficit that blocks
     bulk-approve is therefore tested against a year of payroll. That is
     conservative (it blocks more often, never less) but is not what the label
     implies.

   Read from the code and not run, since there is no `node` here.

None of the three changes with the fix, so none is part of D1. All three touch
the treasury and payout path, which carries this project's hard constraints.
Each needs its own design, and none is proposed here.

### 8.4 What D1-4 actually has to flag

- **Stored submission rows: yes.** `submission_rows.computed_json` stores the full
  optimize response: tax breakdowns, `treasury_forecast`, `annual_saving`,
  `metrics`. The Finance detail view and `build_diff` read it back as stored.
- **Audit and process logs: no.** Neither `audit_log.jsonl` (16,848 lines) nor
  `process_log.jsonl` contains a tax figure or `employer_nps`; both hold ids,
  routes and verdicts. §2's "audit-log entries" was wrong and is corrected there.
- **This machine's data:** the `public` schema holds 0 submission rows today.
  Nothing here says what any other deployment holds, so the mechanism is built for
  the general case.
- *(Added 2026-09-15.)* **Where else stored rows could be.**
  - **No other deployment is evidenced in the repository.** It has no deploy
    configuration: no Dockerfile, Procfile, or fly/render/vercel/railway file.
    `.env` sets no `DATABASE_URL`, so the app uses `DEFAULT_DSN` on this machine.
    The only Postgres databases here are `postgres` and `grosslo`. That is
    evidence about this repository and this machine, not proof that nobody ever
    ran a copy elsewhere, which the code cannot know.
  - **One real store was found, not in Postgres.** The pre-port SQLite file
    `review_queue.db` (git-ignored, last written 2026-09-07) still holds 5
    submission rows, 2 of them with employer NPS (₹1,44,000 and ₹1,83,000). The
    app no longer reads it. `scripts/migrate_sqlite_to_postgres.py` copies it
    verbatim, so if it is ever run, those rows arrive with no `tax_basis`.
  - **Consequence for D1-5:** a missing or NULL `tax_basis` must read as **pre-fix**,
    never as current. Pinned by a test in the flag-on-read step.
- **Out of reach:** anything already exported (Salary Revision XLSX files) is
  outside the system and cannot be flagged. Recorded as a limit.

**Affected rows.** A row is affected when it was computed on the pre-fix basis
**and** any structure in it has `employer_nps > 0`: `current`,
`old_regime_best`, `new_regime_best`, or the recommended one. §8.2 measured that
rows with no employer NPS anywhere do not move, so flagging them would be noise.

### 8.7 Does the error reach routing? (added 2026-09-15)

The owner's question: does an above-cap offer that reads ₹0 and "clean" also get
routed `auto_pass_candidate`, and so become eligible for bulk-approve? If it
does, that is a routing failure, and it jumps the sequence.

**Answer: `clean` and `unclaimed_savings` do not reach routing. The error does
reach routing by a second path, the regime. In every case measured it errs
toward escalation, never toward auto-pass.**

**How route is built.** `orchestration.classify_row()` takes exactly two inputs.

- **Compliance flags:** every rule predicate reads only the structure and rent,
  with no tax figure (`compliance_rules.py`, all eight predicates).
- **The guardrail:** band, EPFO ceiling, and the Section 124 cap. The cap check
  uses `NPS_80CCD2_CAP_PCT[regime]`, and **the regime is chosen by tax**, so it
  is tax-derived. It reaches route in two ways:
  - **Batch audit:** the guardrail receives `current_best["regime"]`.
  - **`/api/submissions`:** the guardrail receives the *recommended* structure and
    regime, both outputs of the tax search.

`unclaimed_savings` and the batch `clean` flag feed only the batch summary
counts and the "Tax Inefficiency" figure. **That half of the finding is display
only.**

**Measured, read-only, in-memory Option B:**

| Path | Cases | Route changed | Direction |
|---|---|---|---|
| Batch audit, as-offered structures (6 CTCs × 3 basic % × 3 HRA × 2 LTA × 3 rent × 2 cities × 7 NPS % × opted/not) | 8,424 | **52** | all `escalate` → `auto_pass_candidate` |
| Submissions, recommended structure (CTC ₹4L–₹60L in ₹1L steps × 5 rents × 2 cities × NPS on/off) | 1,140 | **16** | all `escalate` → `auto_pass_candidate` |

**No case went from `auto_pass_candidate` to `escalate` or `needs_review`.** The
bug has not been letting rows through that the fixed engine would stop. It has
been stopping rows the fixed engine would let through.

- **Batch mechanism:** under the bug, an old-regime offer with NPS above 10% of
  basic looks cheapest in the old regime. The guardrail then applies the 10% cap
  and fails the row. Fixed, the same offer is cheaper in the new regime, the
  14% cap applies, and it passes. The regime flipped in 236 of the 8,424 cases,
  always old → new.
- **Submissions mechanism:** at high CTC and high rent, the bug makes the
  new-regime structure with 14% NPS look best. Its PF plus NPS exceeds the ₹7.5L
  EPFO ceiling, so it escalates. Fixed, the old-regime structure with 10% NPS
  wins and stays under the ceiling. Example: ₹49L CTC, ₹9L rent.

**This is measured, not proved.** Both mechanisms point the same way: the fix
raises old-regime taxable income by at least as much as new-regime, because the
old cap is lower. Tax is not linear in taxable income, though, so this is a
strong expectation over the measured grid, not a theorem. The step-1 test pins
both directions on named cases.

**Sequencing:** no routing failure toward auto-pass was found, so nothing jumps
ahead. What does change the plan is the next finding.

**The recommended structure itself changes.** In the 1,140-case sweep, 111
NPS-on cases change the recommended regime or structure:

| Change | Cases |
|---|---|
| new → old, same basic | 44 |
| new → new, different basic (e.g. ₹15L: 50% → 60% basic) | 20 |
| new → old, different basic | 19 |
| old → old, same basic, different HRA | 17 |
| old → new | 8 |
| old → old, different basic | 3 |

75 of the 111 are at the ₹9L rent level, which the 36-case grid never sampled.
§1.3's "no recommendation changes" is corrected above. Consequences:

- **The advice changes, not only the figure.** A pending pre-fix row may
  recommend a structure the fixed engine would not. Its Salary Revision export
  carries that structure, and its payout amount is derived from it.
- **§5 step 3's baseline justification still holds**, checked:
  `nps_opted_non_metro` (₹24L, ₹2.4L rent, non-metro) is not among the 111. Step 3
  still has to confirm this on the real `--check`.
- **D1-7's reasoning has to change** (§8.6).

### 8.5 Revised implementation plan

§5 stands, with these changes. Each is its own commit, with the full suite after
each and the request/go handshake.

- **0. (new, before §5 step 1) Record the computation basis on stored rows.**
  - Add a `tax_basis` column to `submission_rows` using the existing additive
    migration pattern.
  - Write it on every insert from one constant, set here to the **pre-fix**
    value.
  - No figure changes. The characterization baseline is untouched, because the
    column is on storage and not in the response.
- **§5 step 1** also pins, on the fixed engine:
  - the TDS escrow and take-home move by equal and opposite amounts;
  - `total_capital_outlay` does not move;
  - `penalty_scenario` follows `total_tax`;
  - an above-cap batch row reports non-zero `unclaimed_savings`.
  
  Each assertion must fail today, except the one that documents the invariant.
- **§5 step 2** also bumps the `tax_basis` constant to the fixed value, in the
  same commit. The bump lands atomically with the fix, so no correct row is ever
  stored under the old basis.
- **§5 step 3's** baseline justification is unchanged: only
  `nps_opted_non_metro` drifts. This is the reason the basis lives in a column
  and not in the response.
- **New step, after §5 step 4: flag on read.**
  - A structured field on each affected row, returned by the submissions API.
  - Asserted on structured fields (§8 of the inventory design), including
    both-states tests: an affected row is flagged, and an unaffected pre-fix row
    and a post-fix row are not.
- **New step: show it in the Finance queue.** A frontend change. With no `node`
  here it is uncompiled, and it is recorded in README's *Known unverified
  surfaces* table as the fourth instance.
- **Sabotage, added:**
  - Leave the constant un-bumped in step 2 and confirm post-fix rows flag.
  - Drop the `employer_nps > 0` condition and confirm the unaffected-row test
    fails.

### 8.6 Decisions needed before implementation

| | Decision | Recommendation |
|---|---|---|
| **D1-5** | How is a pre-fix row identified: by `created_at` against a cut-over date, or by a recorded basis? | **A `tax_basis` column written at insert (step 0).** A cut-over date differs per deployment, the code cannot know it, and `created_at` is TEXT from the app clock. A recorded basis says what the row was computed with, on the row. The cut-over commit is still recorded in this document, as D1-4 requires. |
| **D1-6** | Does the flag show the corrected figure alongside the stored one? | **No. Flag only.** Showing a recomputed figure is a different decision from D1-4's "do not silently recompute", and it puts a second figure on the row. If wanted later, it is its own design. |
| **D1-7** | Does a flagged row change approve or export? | **No. Informational only.** Blocking approval of a flagged row would change the maker-checker gate, which is a standing hard constraint. If the owner wants flagged rows blocked, that means lifting the constraint for this case, and it is not assumed here. **Approved 2026-09-15 — reopened the same day, see below.** |

**D1-5 and D1-6 approved 2026-09-15 as recommended.** D1-5 adds one requirement
(§8.4): a missing or NULL `tax_basis` reads as pre-fix.

**D1-7 is reopened: the reasoning given for approving it does not hold.**

- **The reasoning offered at approval:** no *pending* row can sit in pre-fix
  state at decision time, because every computation after the fix uses corrected
  logic.
- **Why it fails:** rows are computed at submission and stored, and `status`
  stays `pending` until a human decides. A row submitted before the fix and
  still pending when the fix ships is exactly that: a live, undecided row
  carrying pre-fix figures. §8.7 adds that it may also carry a different
  recommended structure. Nothing recomputes it (D1-4).

**What still holds from the original recommendation:**

- The maker-checker constraint.
- §8.7's measurement that pre-fix routing erred toward escalation, so no pending
  pre-fix row was fast-tracked by the bug.

**What no longer holds:** "informational only" rested partly on the flag being
about figures. For a pending row it can be about the structure a human is about
to approve.

**Options for the owner. These are not decided here.**

- **(a) Informational only.** As originally recommended. The human sees the flag
  and decides.
- **(b) Informational, plus the flag reason in `orchestration.reasons`.** It is
  shown with every other reason, and no route or status changes.
- **(c) Require resubmission of pending affected rows.** Blocks their approval.
  That changes the maker-checker gate and needs the constraint lifted for this
  case.

**Recommendation: (b).** It puts the flag where the approver already reads, and
it does not touch the gate.
