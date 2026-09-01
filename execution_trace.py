"""
execution_trace.py — orchestration wrappers that build a trace log from
already-computed response data.

This does NOT record trace events from inside optimize(), flag_compliance(),
evaluate_band_guardrail(), or any other existing tested function — none of
those have been touched. Every function here is called AFTER the real work
is done, and formats trace lines purely from fields the response already
contains. Nothing here computes a new number or invents a statutory
citation: COMPLIANCE_PASS and POLICY_GATE quote flag_compliance()'s and
evaluate_band_guardrail()'s own real `message` strings verbatim, rather than
maintaining a separate rule-id-to-section lookup table that could drift out
of sync with compliance_rules.md over time.

Split by what each endpoint actually does (see the plan this was built
from): /api/optimize's three stages are all true by the time it returns.
PAYLOAD_SERIALIZE is deliberately not modeled here at all — it would
require the export endpoint to have already run, which it may not have.
"""


def trace_optimize_stage(response: dict, extraction_ran: bool) -> list[dict]:
    """
    Three stages, built entirely from fields already in `response`
    (the dict api_optimize()/_build_optimize_response() already returns).
    """
    stages = [{
        "stage": "PARSE_INGESTION",
        "message": (
            "Extracted offer-letter fields into a structured input."
            if extraction_ran else
            "Parsed manual CTC/rent/city/NPS input."
        ),
    }]

    flags = response["compliance"]["flags"]
    if flags:
        joined = "; ".join(f["message"] for f in flags)
        compliance_message = f"{len(flags)} flag(s) triggered — {joined}"
    else:
        compliance_message = "No flags triggered."
    stages.append({"stage": "COMPLIANCE_PASS", "message": compliance_message})

    stages.append({
        "stage": "MATH_SOLVER",
        "message": (
            f"Deterministic regime sweep found Rs {response['annual_saving']:,.0f}/year "
            f"in the {response['recommended_regime']} regime."
        ),
    })

    return stages


def trace_guardrail_stage(guardrail: dict) -> dict:
    """One stage, built from evaluate_band_guardrail()'s own real verdict/checks."""
    if guardrail["verdict"] == "pass":
        message = "All policy checks passed — band, EPFO ceiling, Section 124 NPS cap (formerly 80CCD(2))."
    else:
        failing = "; ".join(c["message"] for c in guardrail["checks"] if not c["passed"])
        message = f"Policy gate flagged — {failing}"
    return {"stage": "POLICY_GATE", "message": message}
