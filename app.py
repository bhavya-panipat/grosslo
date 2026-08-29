"""
FinOS web app. Serves the static UI and exposes the optimize/extract/explain/
compliance endpoints. Run with: python3 app.py [port]
"""

import sys
from flask import Flask, request, jsonify, send_from_directory
from optimizer import optimize, best_regime_for_given_structure, sensitivity_sweep
from ai_layer import extract_from_text, explain_result, flag_compliance, negotiate
from tax_engine import SalaryStructure, derive_pf, derive_nps

app = Flask(__name__, static_folder="static", static_url_path="")


def _structure_to_dict(s):
    return {
        "ctc": s.ctc, "basic": s.basic, "hra": s.hra, "lta": s.lta,
        "special_allowance": s.special_allowance,
        "employer_pf": s.employer_pf, "employer_nps": s.employer_nps,
        "nps_opted": s.nps_opted,
    }


def _optresult_to_dict(r):
    return {
        "regime": r.regime,
        "structure": _structure_to_dict(r.structure),
        "taxable_income": r.taxable_income,
        "tax_breakdown": r.tax_breakdown,
        "basic_pct": r.basic_pct,
    }


def _build_current_structure(extracted: dict, ctc: float, regime_for_nps: str) -> "SalaryStructure | None":
    """
    Build a concrete SalaryStructure from as-extracted offer-letter data.
    Returns None if there isn't enough information (basic is the minimum
    required field) — negotiation has nothing to compare against otherwise.
    Missing HRA/LTA are treated as 0 (not offered), not guessed at. NPS
    opt-in is assumed False for the as-offered structure unless the
    extraction explicitly found an NPS figure — offer letters rarely state
    this, and assuming an unstated benefit would overstate the "current"
    baseline in the user's favor.
    """
    basic = extracted.get("basic")
    if basic is None or basic <= 0:
        return None
    hra = extracted.get("hra") or 0
    lta = extracted.get("lta") or 0
    employer_pf = extracted.get("employer_pf")
    if employer_pf is None:
        employer_pf = derive_pf(basic)
    employer_nps = 0.0  # see docstring: not assumed unless stated
    special_allowance = max(0.0, ctc - basic - hra - lta - employer_pf - employer_nps)
    return SalaryStructure(
        ctc=ctc, basic=basic, hra=hra, lta=lta,
        special_allowance=special_allowance,
        employer_pf=employer_pf, employer_nps=employer_nps,
        nps_opted=False,
    )


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/README.md")
def readme():
    return send_from_directory(".", "README.md", mimetype="text/markdown")


@app.route("/api/optimize", methods=["POST"])
def api_optimize():
    data = request.get_json(force=True)
    try:
        ctc = float(data["ctc"])
        rent_paid = float(data.get("rent_paid", 0))
        city = data.get("city", "metro")
        nps_opted = bool(data.get("nps_opted", False))
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "ctc is required and must be numeric"}), 400

    if ctc <= 0:
        return jsonify({"error": "ctc must be positive"}), 400
    if ctc > 40_000_000:
        return jsonify({"error": "CTC above Rs 4 crore is outside this tool's validated range (surcharge not modeled)"}), 400

    result = optimize(ctc=ctc, rent_paid=rent_paid, city=city, nps_opted=nps_opted)

    response = {
        "ctc": result["ctc"],
        "old_regime_best": _optresult_to_dict(result["old_regime_best"]),
        "new_regime_best": _optresult_to_dict(result["new_regime_best"]),
        "recommended_regime": result["recommended"].regime,
        "annual_saving": result["annual_tax_saving_vs_other_regime"],
    }

    # Build the as-offered structure (if extraction supplied one) BEFORE
    # compliance checking — compliance must check what was actually offered,
    # not the optimizer's own recommendation. Checking the recommendation
    # is nearly circular: the optimizer enforces a 40-50% basic band by
    # construction, so rules like R1 (basic < 35% of CTC) can structurally
    # never fire against it. Real compliance risk lives in the offer itself.
    current_extracted = data.get("current_structure")
    current_structure = None
    if isinstance(current_extracted, dict):
        current_structure = _build_current_structure(current_extracted, ctc, result["recommended"].regime)

    # Attach explanation for the recommended structure
    explanation = explain_result(result, rent_paid, city)
    response["explanation"] = explanation

    # Compliance checks the AS-OFFERED structure when we have one (the real
    # risk surface); only falls back to the recommended structure when
    # nothing was extracted, so there's still something to check.
    structure_to_check = current_structure if current_structure is not None else result["recommended"].structure
    compliance = flag_compliance(structure_to_check, rent_paid)
    response["compliance"] = compliance
    response["compliance_checked_against"] = "as_offered" if current_structure is not None else "recommended"

    # Negotiation copilot — ONLY when the caller supplied a real extracted
    # current structure (from /api/extract, after the user reviewed/corrected
    # it). A manually-entered CTC-only input has no "offered" structure to
    # negotiate away from, so we don't fabricate one.
    if current_structure is not None:
        current_best = best_regime_for_given_structure(current_structure, rent_paid, city)
        negotiation = negotiate(
            current_structure=current_structure,
            current_best=current_best,
            recommended=result["recommended"].structure,
            recommended_regime=result["recommended"].regime,
            recommended_tax=result["recommended"].tax_breakdown,
            ctc=ctc,
        )
        response["negotiation"] = negotiation

    return jsonify(response)


@app.route("/api/sensitivity", methods=["POST"])
def api_sensitivity():
    data = request.get_json(force=True)
    try:
        rent_paid = float(data.get("rent_paid", 0))
        city = data.get("city", "metro")
        nps_opted = bool(data.get("nps_opted", False))
    except (ValueError, TypeError):
        return jsonify({"error": "rent_paid must be numeric"}), 400

    points = sensitivity_sweep(rent_paid=rent_paid, city=city, nps_opted=nps_opted)
    return jsonify({"points": points, "rent_paid": rent_paid, "city": city, "nps_opted": nps_opted})


@app.route("/api/extract", methods=["POST"])
def api_extract():
    data = request.get_json(force=True)
    text = data.get("text", "")
    if not text.strip():
        return jsonify({"error": "text is required"}), 400
    result = extract_from_text(text)
    return jsonify(result)


@app.route("/health")
def health():
    from ai_layer import _client
    return jsonify({
        "status": "ok",
        "ai_layer_active": _client is not None,
        "note": "ai_layer_active=false means no ANTHROPIC_API_KEY configured; all AI endpoints will use deterministic fallback logic.",
    })


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    app.run(host="0.0.0.0", port=port, debug=False)
