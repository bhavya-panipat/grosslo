"""
diff_view.py — before/after presentation for Finance's review screen.

Zero new tax computation, by design. Every value here comes from a field
that already exists in _build_optimize_response()'s output (app.py) or
from calling optimizer.py's already-existing, already-tested
best_regime_for_given_structure() — never a new calculation. If a number
shown by this module can't be traced to one of those two sources, that's a
bug, not a feature: the whole point of this file is that a diff is an
explanation over data the system already produced, not a new opinion about
what the offer should be.
"""

from optimizer import best_regime_for_given_structure
from tax_engine import SalaryStructure

# Which compliance rule(s) a given field's change plausibly resolves, so a
# diff line can say *why* a field moved instead of just that it did.
# Sourced from compliance_rules.md's own R1-R6 definitions — not invented
# here.
FIELD_TO_RULES = {
    "basic": ["R1"],
    "hra": ["R3"],
    "lta": ["R4"],
    "employer_pf": ["R2", "R5"],
    "employer_nps": ["R5"],
    "special_allowance": ["R6"],
}

LEVER_TO_FIELD = {
    "basic salary": "basic",
    "HRA": "hra",
    "LTA": "lta",
    "NPS enrollment (80CCD2)": "nps_opted",
}


def build_diff(input_row: dict, computed: dict) -> dict:
    """
    input_row: the raw row input this submission was created from —
    {ctc, rent_paid, city, nps_opted, current_structure?, employee_name?}.
    computed: the full _build_optimize_response() output for that row.

    Returns {"has_prior_offer": bool, "regime_change": {...} | None,
             "field_changes": [{"field", "before", "after", "reason"}]}.
    """
    current_structure = input_row.get("current_structure")
    if not current_structure or "negotiation" not in computed:
        return {
            "has_prior_offer": False,
            "note": "New structure — no prior offer to compare against.",
            "regime_change": None,
            "field_changes": [],
        }

    recommended_regime = computed["recommended_regime"]
    recommended_structure = computed[f"{recommended_regime}_regime_best"]["structure"]
    flags = computed.get("compliance", {}).get("flags", [])
    triggered_rule_ids = {f["rule_id"] for f in flags}
    changed_levers = computed["negotiation"].get("changed_levers", [])

    field_changes = []
    for lever in changed_levers:
        field = LEVER_TO_FIELD.get(lever)
        if field is None or field == "nps_opted":
            continue  # NPS enrollment is a boolean flip, shown separately below, not a before/after number
        before_val = current_structure.get(field)
        after_val = recommended_structure.get(field)
        if before_val is None or after_val is None:
            continue
        matching_rules = [r for r in FIELD_TO_RULES.get(field, []) if r in triggered_rule_ids]
        reason = f"{matching_rules[0]} compliance fix" if matching_rules else "tax optimization"
        field_changes.append({
            "field": field, "before": before_val, "after": after_val, "reason": reason,
        })

    if "NPS enrollment (80CCD2)" in changed_levers:
        field_changes.append({
            "field": "nps_opted",
            "before": bool(current_structure.get("nps_opted", False)),
            "after": bool(recommended_structure.get("nps_opted", False)),
            "reason": "tax optimization",
        })

    # Regime comparison: reuses the existing, already-tested
    # best_regime_for_given_structure() on the as-offered structure — not
    # a new calculation, just a call to a function that already exists for
    # exactly this purpose elsewhere in this codebase.
    regime_change = None
    try:
        as_offered = SalaryStructure(
            ctc=input_row["ctc"],
            basic=current_structure.get("basic", 0), hra=current_structure.get("hra", 0),
            lta=current_structure.get("lta", 0), special_allowance=current_structure.get("special_allowance", 0),
            employer_pf=current_structure.get("employer_pf", 0), employer_nps=current_structure.get("employer_nps", 0),
            nps_opted=bool(current_structure.get("nps_opted", False)),
        )
        current_best = best_regime_for_given_structure(as_offered, input_row.get("rent_paid", 0), input_row.get("city", "metro"))
        if current_best["regime"] != recommended_regime:
            regime_change = {
                "before": current_best["regime"], "after": recommended_regime,
                "reason": "lower total tax",
            }
    except (KeyError, TypeError):
        pass  # malformed current_structure — diff still shows field_changes, just skips the regime note

    return {
        "has_prior_offer": True,
        "note": None,
        "regime_change": regime_change,
        "field_changes": field_changes,
    }
