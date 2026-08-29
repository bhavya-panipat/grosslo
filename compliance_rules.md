# FinOS Compliance Rules Checklist (v1)

This is a fixed, documented set of pattern checks — not legal advice, not a
substitute for a tax professional. The compliance-flagging agent checks a
given salary structure against these rules ONLY. It does not free-associate
additional advice.

| Rule ID | Check | Rationale | Severity |
|---|---|---|---|
| R1 | Basic salary < 35% of CTC | Below common market convention (40% floor used elsewhere in this tool); may indicate an attempt to minimize statutory PF/gratuity obligations, which can create future disputes over retirement benefits and loan-eligibility calculations that reference basic pay | Medium |
| R2 | CTC > Rs 6L/year but employer PF = 0 | PF is near-universal for salaried employees above minimum wage thresholds; a missing PF component at this CTC level is unusual and worth confirming isn't an oversight | Medium |
| R3 | HRA claimed but rent_paid = 0 or not provided | HRA exemption requires actual rent payment with supporting documentation; claiming HRA structure without a rent input suggests the exemption may not be realizable | Low |
| R4 | LTA > 10% of CTC | Exceeds typical company LTA policy ceilings; may not be realizable given actual travel-and-bills requirements | Low |
| R5 | Aggregate employer PF + NPS > Rs 7.5L/year | The excess over Rs 7.5L is a taxable perquisite under Section 17(2)(vii) — NOT currently modeled in tax_engine.py's tax calculation, so any structure crossing this threshold has an unmodeled tax liability the tool doesn't account for | High |
| R6 | Special allowance = 0 | Leaves no flexible cash component; unusual structure that may indicate an input error rather than a deliberate choice | Low |

**How this list is used:** the flagging agent checks a given structure's
numbers against each rule above and reports which rules triggered, using the
severity and rationale text already written here — it does not generate new
rules or reasoning outside this table.

**Known gap this table surfaces:** Rule R5 exists specifically because
`tax_engine.py` does not yet model the >Rs 7.5L aggregate perquisite rule
(see FINOS_PROJECT_BRIEF.md, assumption #7). Until that's modeled in the
engine itself, this flag is the only place that gap is visible to the user —
don't remove R5 without first resolving the underlying engine gap.
