# Employer NPS in taxable income — fix design

**Status:** design only, **awaiting approval.** `tax_engine.py` is not changed.
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

| | Decision | Recommendation |
|---|---|---|
| **D1-1** | Approve fixing the tax engine? | **Yes.** Tax is under-stated by the full contribution's tax for every NPS-opted structure, 15–24% at mid-range CTCs. |
| **D1-2** | Option A or Option B? | **B** — A leaves above-cap batch-audit structures wrong. |
| **D1-3** | Candidate R7: redraft for the above-cap residue, or retire? | **Redraft** — above the cap, opt-in genuinely matters again. |
| **D1-4** | Stored submissions and audit-log entries computed before the fix: flag them, recompute them, or record the cut-over date only? | **Record the cut-over date and flag affected submissions visibly; do not silently recompute.** A figure someone may have acted on should not change underneath them without notice. This one needs the project owner, not a default. |

## 7. Not in scope

- **The two carried assumptions** — basic rather than salary-including-DA, and
  the non-government rate. They are TE4 divergences; modelling them is a scope
  decision about what the tool represents.
- **Employer PF.** Left out of `gross_salary` and not subtracted: net zero, which
  matches its treatment within limits. The unmodelled s. 17(1)(h) excess above
  ₹7.5L aggregate is R5's recorded gap, and separate.
- **The `80ccd2_cap` guardrail's wording** — active work in another session.
