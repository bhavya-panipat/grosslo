# Product scope — the decision for Roadmap Phase 2.5

Two questions, asked now because work keeps being built on top of an answer
nobody has written down:

1. **Employees only, or contractors too?**
2. **Single-country (India), or multi-country?**

## 1. Method: what the code can express, before anyone offers a preference

The same approach that settled the audit-sweep question in
`COMPLIANCE_BREADTH_DESIGN.md` §3.5. There, the tempting move was to reason
about how the feature would realistically be used. The answer that actually held
came from asking whether the **inputs required to make the other case possible
exist at all** — they did not, and that could not be defeated by a user behaving
unusually.

The same test applies here, with one difference stated up front in §5, because
it changes what the evidence is allowed to conclude.

## 2. The assumption is pervasive in the code and stated nowhere

Worth recording before the evidence, because it is the reason this document
exists. Searching the repository for a scope statement finds **one**, in
`optimizer.py`, inside a parenthetical about why Dearness Allowance does not
apply:

> "(scoped to private-sector employees, where DA doesn't apply)"

That is the entire written record of who this tool is for. The assumption is
load-bearing in dozens of places and asserted in one, as an aside.

## 3. Evidence — contractors

**The tool's central value proposition is employment-specific, not merely its
implementation.**

| Evidence | Where | Why it is employment-only |
|---|---|---|
| **Salary TDS, Section 392 (formerly 192)** | `payroll_breakdown.py`, `ai_layer.py` | Section 392 *is* the salary-withholding provision. A contractor is withheld under a different provision entirely, at a different rate, with different mechanics. This is not a near-miss; it is a different section of the Act. |
| `"purpose": "salary"` | `app.py` payout payload | The generated RazorpayX instruction declares itself a salary payment. |
| `employer_pf`, `employer_nps` | throughout | Employer contributions exist only inside an employment relationship. There is no employer to contribute for a contractor. |
| **CTC structuring itself** | `optimizer.py`, `tax_engine.py` | The entire product is: take a CTC and split it into basic / HRA / LTA / special allowance to minimise tax. **A contractor has no CTC to structure.** HRA exemption is a salary perquisite; LTA is a salary perquisite; employer PF is an employer cost. Remove employment and there is nothing left to optimise. |
| No contractor concept exists | repository-wide | The only match for "consultant" is in `IDENTITY_DESIGN.md`, about one human holding two tenant *accounts* — a tenancy point, not a payee one. |

**The distinction that matters:** a contractor still pays income tax, and this
tool's slab arithmetic would compute it. But the *optimizer* — the thing that
makes this a product rather than a calculator — has nothing to act on. Serving
contractors would not be an extension of the feature set; it would be a
different product sharing a tax engine.

## 4. Evidence — multi-country

**There is no jurisdiction seam anywhere to widen.**

Every public function in `tax_engine.py`, across all parameters:

```
basic, basic_annual, basic_pct, city, ctc, employer_nps, employer_pf, hra,
hra_paid, hra_pct_of_remaining, lta, nps_opted, opted_in,
pf_voluntary_full_basic, regime, rent_paid, special_allowance, structure,
taxable_income, voluntary_full_basic
```

**Not one country, jurisdiction, locale or currency parameter.** And the two
that look closest are themselves Indian constructs:

- `regime` — the old/new regime choice is a feature of the Indian Income-tax Act.
- `city` — `metro` / `non_metro` are the HRA exemption tiers under Indian law.

Below that, the constants are India's: both slab tables, the standard deduction,
the 87A rebate, the 4% cess, the 12% employer PF rate, the ₹15,000 PF wage
ceiling. All module-level. None parameterised.

Beyond the engine:

- **`"currency": "INR"` and `"mode": "NEFT"`** are hardcoded in the payout
  payload; `ifsc` (10 uses) is Indian bank routing; `PAN` (16 uses) is an Indian
  tax identifier.
- **Five state professional-tax tables** — Indian *state* law, one level below
  national.
- **All 16 legal instruments cited** across every compliance rule and every
  inventoried claim are Indian. Zero exceptions.

Multi-country would not be "add a country parameter". It would be a second tax
engine, a second optimizer search space, a second rule set, a second inventory,
and a second payment rail — sharing approximately the review workflow and the
tenancy model, and nothing else.

## 5. What this evidence does and does not settle — the honest limit

**It settles, beyond argument, what the tool currently is:** single-country
(India), employee-only, and structurally so rather than incidentally.

**It does not by itself settle whether to expand.** This is where the parallel
with the audit-sweep question stops, and the difference is worth being precise
about:

- For audit-sweep, the absence was *dispositive*. The tool could not be told
  which year it was auditing, so reconciling a prior year's filing was not a
  feature to build — it was a thing the tool's own purpose ruled out.
- Here, the absence tells us the **cost** of expanding, not whether expanding is
  worthwhile. "We have not built it" is not an argument against building it.

So the evidence bounds the decision rather than making it. What it establishes
is that neither expansion is incremental: each is a second product's worth of
work, not a widening of this one.

## 6. Recommendation

**Employees only. Single-country: India.** Stated affirmatively in the product's
own documentation rather than left as an unwritten assumption.

The reasoning is not "that is what exists". It is that **both expansions would
dilute the only thing this tool currently does well**, at a moment when its
central weakness is that *15 of 17 of its legal claims are unverified and
nothing has been reviewed by a qualified human*. Adding a second jurisdiction
would multiply an unverified corpus rather than deepen a verified one. That is
the argument, and it is about sequencing rather than about the ideas.

Contractors in particular should be recognised as a **separate product** if ever
pursued, sharing the tax engine and nothing above it.

## 7. What needs an explicit call

- **Confirm or overrule the recommendation.** Recorded either way, with the
  reasoning, so the next person does not re-derive it.
- **A subtlety worth not confusing with the country question:** "single-country"
  means the *tax jurisdiction* is India. An Indian employee of a foreign-domiciled
  company is still Indian payroll law and is **in scope**; the employer's
  domicile is irrelevant. Only the employee's tax jurisdiction decides.
- **Where the scope statement lives.** Recommendation: `README.md`, at the top,
  where a reader meets the product — not only here.

## 8. Named forcing function

**If a second tax jurisdiction is ever added, this decision must be revisited in
the same change** — and the first question then is not "how do we parameterise
the engine" but "does the legal claim inventory work per-jurisdiction", because
every claim, every rule and every instrument currently assumes one.

Same shape as §3.5's return-filing trigger: a condition and an action, not a
reminder to re-read this document.
