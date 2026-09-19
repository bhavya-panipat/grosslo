# FinOS Compliance Rules Checklist (v1)

This is a fixed, documented set of pattern checks — not legal advice, not a
substitute for a tax professional. The compliance-flagging agent checks a
given salary structure against these rules ONLY. It does not free-associate
additional advice.

<!-- BEGIN GENERATED RULES TABLE — edit compliance_rules.py, not this -->

| Rule ID | Check | Rationale | Severity | Status |
|---|---|---|---|---|
| R1 | Basic salary < 50% of CTC | Statutory violation, not a soft convention: the Code on Wages 2025 requires Basic + DA to be at least 50% of total remuneration — this tool has no separate DA field (scoped to private-sector employees, where DA doesn't apply), so Basic alone is the relevant component. Falling below this line triggers automatic reclassification of the excess allowances as "wages" for PF and gratuity purposes, with real penalty exposure — not just a market-convention miss | High | active |
| R2 | CTC > Rs 6L/year but employer PF = 0 | PF is near-universal for salaried employees above minimum wage thresholds; a missing PF component at this CTC level is unusual and worth confirming isn't an oversight | Medium | active |
| R3 | HRA claimed but rent_paid = 0 or not provided | HRA exemption requires actual rent payment with supporting documentation; claiming HRA structure without a rent input suggests the exemption may not be realizable | Low | active |
| R4 | LTA > 10% of CTC | Exceeds typical company LTA policy ceilings; may not be realizable given actual travel-and-bills requirements | Low | active |
| R5 | Aggregate employer PF + NPS > Rs 7.5L/year | The excess over Rs 7.5L is a taxable perquisite under Section 17(1)(h) (formerly Section 17(2)(vii)) — NOT currently modeled in tax_engine.py's tax calculation, so any structure crossing this threshold has an unmodeled tax liability the tool doesn't account for | High | active |
| R6 | Special allowance = 0 | Leaves no flexible cash component; unusual structure that may indicate an input error rather than a deliberate choice | Low | active |
| R7 | Employer NPS contribution present but nps_opted is false | The two inputs contradict each other. REDRAFTED 2026-09-19 with the employer-NPS tax fix (TAX_ENGINE_EMPLOYER_NPS_DESIGN.md D1-3); the original draft said the contradiction produced a lower tax number, which was the double count itself and is no longer true. tax_engine.taxable_income_for_structure() now adds structure.employer_nps to salary (Income-tax Act, 2025 s. 16(k)) and deducts it up to the cap (s. 124), in both regimes, without ever reading nps_opted. So within the cap the pair has no effect on tax at all. Above the cap the excess is taxed; if the not-opted flag is the true input, that contribution does not exist and the tax is over-stated, never under-stated. The rule flags the inconsistency for confirmation and does not assert which of the two inputs is wrong. Its severity (High) was set when the stated consequence was an under-stated tax; the consequence is now narrower and conservative, and whether High still fits is left to the reviewer rather than changed here | High | **CANDIDATE — cannot fire, awaiting review** |
| R8 | Salary components do not sum to the stated CTC | A meta-rule: it does not describe a defect in the compensation structure but tells the reader that other rules' output cannot be trusted for this row. SalaryStructure.total() exists in tax_engine.py to express exactly this reconciliation, and before this rule was drafted it had no call sites anywhere in the repository — the invariant was written down and never checked | High | **CANDIDATE — cannot fire, awaiting review** |

<!-- END GENERATED RULES TABLE -->

**This table is generated** from `compliance_rules.py`, which is the single
source of truth for every rule's predicate, text, severity and provenance. Edit
the rules there and re-run `scripts/generate_compliance_rules_md.py`; edits made
directly to the table above will be overwritten, and a test fails if the two
fall out of sync. The prose in this document is hand-written and is not
generated.

**How this list is used:** the flagging agent checks a given structure's
numbers against each rule above and reports which rules triggered, using the
severity and rationale text already written here — it does not generate new
rules or reasoning outside this table.

**Known gap this table surfaces:** Rule R5 exists specifically because
`tax_engine.py` does not yet model the >Rs 7.5L aggregate perquisite rule
(see FINOS_PROJECT_BRIEF.md, assumption #7). Until that's modeled in the
engine itself, this flag is the only place that gap is visible to the user —
don't remove R5 without first resolving the underlying engine gap.
