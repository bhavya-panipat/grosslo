"""
orchestration.py — routes an already-computed compliance/guardrail result to
a Finance-queue severity tier. Zero new tax/compliance logic: every input
here is a field flag_compliance() or evaluate_band_guardrail() already
computed and already tested. This module only aggregates and labels — it
never re-derives a rule or invents a threshold not already in
compliance_rules.md or ai_layer.py.

Distinct from execution_trace.py's {stage, message} pipeline shape on
purpose: a routing decision is a single aggregation step over existing
signals, not a multi-phase pipeline — forcing it into fabricated "stages"
would invent structure that doesn't exist. The "decision chain" here is the
`reasons` list (what fired, quoting real flag/check text verbatim) plus
`checked` (what was evaluated, including what did NOT fire) — not a fake
staged narrative.

APPROVE STILL HAPPENS ONLY VIA review_queue.decide_row(), by a human click.
Nothing in this module writes state, calls decide_row(), or changes what
/api/submissions/<id>/rows/<i>/decide or /export do. `auto_pass_candidate`
is a routing/presentation recommendation, never an approval.

Four routes, not three — "guardrail never ran" (no compensation band was
supplied for this row) is a distinct, visible state from both "clean" and
"escalated," per the project's own capability-strip precedent of keeping
"not run" separate from "ran, passed." A row with zero compliance flags but
no guardrail run does NOT fast-track — see classify_row()'s priority order.
"""

from __future__ import annotations
from ai_layer import TOTAL_COMPLIANCE_RULES

_SEVERITY_RANK = {"Low": 1, "Medium": 2, "High": 3}
VALID_ROUTES = {"auto_pass_candidate", "needs_review", "guardrail_not_run", "escalate"}


def _aggregate_severity(flags: list[dict]) -> str:
    if not flags:
        return "None"
    return max(flags, key=lambda f: _SEVERITY_RANK[f["severity"]])["severity"]


def classify_row(compliance: dict, guardrail: dict | None) -> dict:
    """
    compliance: flag_compliance()'s {"flags": [...], "ai_backed": bool}.
    guardrail: evaluate_band_guardrail()'s {"verdict", "checks", ...}, or
    None if no band was supplied for this row (guardrail never ran — this
    is a real, distinct state, not "nothing to report").

    Returns {
      "route": "auto_pass_candidate" | "needs_review" | "guardrail_not_run" | "escalate",
      "severity": "None" | "Low" | "Medium" | "High",  # max over triggered flags
      "reasons": [str, ...],   # guardrail failures first, then flags high->low,
                                 # each line quoting the real message verbatim.
                                 # Empty list = nothing fired.
      "checked": {
        "compliance_rules_evaluated": int,       # TOTAL_COMPLIANCE_RULES, always 6
        "compliance_flags_triggered": int,
        "guardrail_evaluated": bool,              # False if guardrail param is None
        "guardrail_checks_failed": int | None,    # None if guardrail_evaluated is False
      },
    }

    Routing rule, in priority order:
      1. Any failing guardrail check, OR max compliance severity "High"
         -> "escalate". The guardrail gates payout-eligibility (band, EPFO
         ceiling, Section 124 NPS cap) with no partial-credit notion — a
         fail is maximally severe, same tier as a High compliance flag.
      2. Else, guardrail wasn't evaluated at all (no band supplied)
         -> "guardrail_not_run". This is checked BEFORE severity tiers
         below it, because "we never checked" must never look like "we
         checked and it's fine" — even a flag-free row stays here.
      3. Else, max compliance severity == "Medium" -> "needs_review".
      4. Else (severity is "None" or "Low", and guardrail ran+passed)
         -> "auto_pass_candidate". A Low-severity flag still fast-tracks
         but is fully preserved in `reasons` — the caller is responsible
         for badging it visibly, not hiding it.
    """
    flags = compliance.get("flags", [])
    severity = _aggregate_severity(flags)

    guardrail_evaluated = guardrail is not None
    failing_checks = [c for c in guardrail["checks"] if not c["passed"]] if guardrail_evaluated else []

    reasons = [f"Guardrail — {c['label']}: {c['message']}" for c in failing_checks]
    for f in sorted(flags, key=lambda f: -_SEVERITY_RANK[f["severity"]]):
        reasons.append(f"{f['rule_id']} ({f['severity']}) — {f['message']}")

    if failing_checks or severity == "High":
        route = "escalate"
    elif not guardrail_evaluated:
        route = "guardrail_not_run"
    elif severity == "Medium":
        route = "needs_review"
    else:
        route = "auto_pass_candidate"

    return {
        "route": route,
        "severity": severity,
        "reasons": reasons,
        "checked": {
            "compliance_rules_evaluated": TOTAL_COMPLIANCE_RULES,
            "compliance_flags_triggered": len(flags),
            "guardrail_evaluated": guardrail_evaluated,
            "guardrail_checks_failed": len(failing_checks) if guardrail_evaluated else None,
        },
    }
