"""
FinOS web app. Serves the static UI and exposes the optimize/extract/explain/
compliance endpoints. Run with: python3 app.py [port]
"""

import sys
import subprocess
import uuid
import json
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()  # must run before ai_layer is imported — it reads ANTHROPIC_API_KEY at import time

from flask import Flask, request, jsonify, send_from_directory, send_file
from optimizer import optimize, best_regime_for_given_structure, sensitivity_sweep, optimization_value_pct
from ai_layer import extract_from_text, explain_result, flag_compliance, negotiate, compliance_pct, ai_coverage_pct, answer_query, evaluate_band_guardrail, EPFO_AGGREGATE_CEILING
from tax_engine import SalaryStructure, derive_pf, derive_nps
from payroll_breakdown import treasury_forecast
from penalty_exposure import build_scenario_table
from execution_trace import trace_optimize_stage, trace_guardrail_stage
import io
import review_queue
from diff_view import build_diff
from salary_revision_export import build_salary_revision_workbook, TEMPLATE_HONESTY_LABEL

app = Flask(__name__, static_folder="static", static_url_path="")
review_queue.init_db()

AUDIT_LOG_PATH = "audit_log.jsonl"


def _append_audit_log(route: str, event: dict) -> None:
    """
    Appends one JSON line per money-adjacent decision (structure computed,
    compliance/guardrail verdict, payload generated) to a local, gitignored
    file — a real, inspectable-after-the-fact audit trail, not a claimed
    one. Deliberately narrow: this logs the DECISION (regime, tax figures,
    compliance/guardrail verdicts, whether a payout payload was generated)
    and never employee PII or bank details, so "no bank details are
    persisted anywhere" (see FINOS_PROJECT_BRIEF.md) stays true even though
    a server-side file write now exists. This is a local append-only log
    for this submission, not a production audit system — no rotation, no
    access control, no tamper-evidence. Never let a logging failure break
    the actual response, same degrade-gracefully pattern as
    _get_commit_history().
    """
    try:
        with open(AUDIT_LOG_PATH, "a") as f:
            f.write(json.dumps({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "route": route,
                **event,
            }) + "\n")
    except OSError:
        pass


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


def _build_optimize_response(ctc, rent_paid, city, nps_opted, current_extracted, extraction_ai_backed,
                              skip_explanation_ai=False):
    """
    The full optimize+compliance+negotiation+metrics pipeline for one
    candidate, extracted out of api_optimize() so /api/optimize-batch can
    reuse it per-row without duplicating this logic. Pure extract-function
    refactor — behavior is byte-for-byte identical to what api_optimize()
    used to do inline; only the call site changed.

    skip_explanation_ai=True is passed by the batch route only — see
    explain_result()'s docstring for why (measured, not assumed: this was
    the entire cause of a 500-row batch not completing in 2 minutes).

    Returns (response_dict, raw_result) — raw_result is optimize()'s own
    return value, with real SalaryStructure objects (not yet flattened to
    JSON), so callers that need those objects (guardrail checks, treasury
    forecasts) don't have to recompute optimize() a second time.
    """
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
    current_structure = None
    if isinstance(current_extracted, dict):
        current_structure = _build_current_structure(current_extracted, ctc, result["recommended"].regime)

    # Attach explanation for the recommended structure
    explanation = explain_result(result, rent_paid, city, skip_ai=skip_explanation_ai)
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

    # Radar/ring metrics — reuse data already computed above, no new work.
    extraction_ran = current_structure is not None
    negotiation_ran = current_structure is not None
    negotiation_ai_backed = response["negotiation"]["ai_backed"] if negotiation_ran else False

    response["metrics"] = {
        "optimization_value_pct": optimization_value_pct(ctc, rent_paid, city, nps_opted),
        "compliance_pct": compliance_pct(compliance["flags"]),
        "ai_coverage_pct": ai_coverage_pct(
            extraction_ran=extraction_ran, extraction_ai_backed=extraction_ai_backed,
            explanation_ai_backed=explanation["ai_backed"], compliance_ai_backed=compliance["ai_backed"],
            negotiation_ran=negotiation_ran, negotiation_ai_backed=negotiation_ai_backed,
            compliance_ran=len(compliance["flags"]) > 0,
        ),
    }

    return response, result


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

    current_extracted = data.get("current_structure")
    response, _ = _build_optimize_response(
        ctc, rent_paid, city, nps_opted,
        current_extracted, bool(data.get("extraction_ai_backed", False)),
    )
    response["execution_trace"] = trace_optimize_stage(response, extraction_ran=isinstance(current_extracted, dict))
    _append_audit_log("/api/optimize", {
        "ctc": ctc, "recommended_regime": response["recommended_regime"],
        "annual_saving": response["annual_saving"],
        "compliance_flags": [f["rule_id"] for f in response["compliance"]["flags"]],
    })
    return jsonify(response)


@app.route("/api/batch-audit", methods=["POST"])
def api_batch_audit():
    """
    Audits CURRENT (as-offered/as-is) structures — not a CTC to optimize
    from. For each row: best_regime_for_given_structure() gives the real
    tax on the structure as it stands today, optimize() gives the
    theoretical best for the same CTC, the gap between them is
    unclaimed_savings. evaluate_band_guardrail() and treasury_forecast()
    run on the same as-is structure. Every figure traces to an existing,
    already-tested function — no new tax/compliance logic here.
    """
    data = request.get_json(force=True)
    rows = data.get("rows")
    if not isinstance(rows, list) or not rows:
        return jsonify({"error": "rows must be a non-empty list"}), 400

    results = []
    total_excess_contribution = 0.0
    total_unclaimed_savings = 0.0
    sum_monthly_epf = 0.0
    sum_monthly_tds = 0.0

    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            results.append({"row_index": i, "error": "each row must be an object"})
            continue
        try:
            structure = SalaryStructure(
                ctc=float(row["ctc"]),
                basic=float(row["basic"]),
                hra=float(row.get("hra", 0)),
                lta=float(row.get("lta", 0)),
                special_allowance=float(row.get("special_allowance", 0)),
                employer_pf=float(row.get("employer_pf", 0)),
                employer_nps=float(row.get("employer_nps", 0)),
                nps_opted=bool(row.get("nps_opted", False)),
            )
            rent_paid = float(row.get("rent_paid", 0))
            city = row.get("city", "metro")
            band_min = float(row["band_min"])
            band_max = float(row["band_max"])
        except (KeyError, ValueError, TypeError):
            results.append({"row_index": i, "error": "ctc, basic, band_min, and band_max are required and must be numeric"})
            continue
        if structure.ctc <= 0 or structure.basic <= 0:
            results.append({"row_index": i, "error": "ctc and basic must be positive"})
            continue
        if band_min <= 0 or band_max <= 0 or band_min >= band_max:
            results.append({"row_index": i, "error": "band_min and band_max must be positive with band_min < band_max"})
            continue

        current_best = best_regime_for_given_structure(structure, rent_paid, city)
        optimal = optimize(ctc=structure.ctc, rent_paid=rent_paid, city=city, nps_opted=structure.nps_opted)

        unclaimed_savings = round(max(
            0.0,
            current_best["tax_breakdown"]["total_tax"] - optimal["recommended"].tax_breakdown["total_tax"],
        ), 2)
        excess_contribution = round(max(
            0.0,
            (structure.employer_pf + structure.employer_nps) - EPFO_AGGREGATE_CEILING,
        ), 2)
        guardrail = evaluate_band_guardrail(structure, current_best["regime"], band_min, band_max)
        forecast = treasury_forecast(structure, current_best["tax_breakdown"])

        total_excess_contribution += excess_contribution
        total_unclaimed_savings += unclaimed_savings
        sum_monthly_epf += forecast["epfo_challan_annual"] / 12
        sum_monthly_tds += current_best["tax_breakdown"]["total_tax"] / 12

        results.append({
            "row_index": i,
            "name": row.get("name", f"Row {i + 1}"),
            "current_regime": current_best["regime"],
            "current_tax": current_best["tax_breakdown"]["total_tax"],
            "unclaimed_savings": unclaimed_savings,
            "excess_contribution": excess_contribution,
            "guardrail": guardrail,
            "treasury_forecast": forecast,
        })
        _append_audit_log("/api/batch-audit", {
            "row_index": i, "current_regime": current_best["regime"],
            "unclaimed_savings": unclaimed_savings, "excess_contribution": excess_contribution,
            "guardrail_verdict": guardrail.get("verdict"),
        })

    return jsonify({
        "rows": results,
        "summary": {
            "total_excess_contribution": round(total_excess_contribution, 2),
            "total_unclaimed_savings": round(total_unclaimed_savings, 2),
        },
        "penalty_scenario": build_scenario_table(sum_monthly_epf, sum_monthly_tds),
    })


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


@app.route("/api/query", methods=["POST"])
def api_query():
    data = request.get_json(force=True)
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400

    try:
        ctc = float(data["ctc"])
        rent_paid = float(data.get("rent_paid", 0))
        city = data.get("city", "metro")
        nps_opted = bool(data.get("nps_opted", False))
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "ctc is required and must be numeric — pass the same values used for the last /api/optimize call"}), 400

    context = data.get("context", {})
    if not isinstance(context, dict):
        context = {}

    result = answer_query(question, context, ctc, rent_paid, city, nps_opted)
    return jsonify(result)


DEFAULT_RAZORPAYX_ACCOUNT_NUMBER = "7878780080316316"  # demo placeholder, RazorpayX docs' own example account


def _build_composite_payout(structure, employee: dict, account_number: str) -> dict:
    """
    Builds one payout object matching RazorpayX's real Composite Payout API
    schema (verified against https://razorpay.com/docs/api/x/payout-composite/
    create/bank-account/ — not guessed): nested fund_account.bank_account and
    fund_account.contact, amount in paise. This is schema construction only —
    no live call to RazorpayX is made anywhere in this route.
    """
    net_monthly = round(
        (structure.basic + structure.hra + structure.lta + structure.special_allowance) / 12,
        2,
    )
    amount_paise = int(round(net_monthly * 100))
    return {
        "account_number": account_number,
        "amount": amount_paise,
        "currency": "INR",
        "mode": "NEFT",
        "purpose": "salary",
        "fund_account": {
            "account_type": "bank_account",
            "bank_account": {
                "name": employee["name"],
                "ifsc": employee["ifsc"],
                "account_number": employee["bank_account_number"],
            },
            "contact": {
                "name": employee["name"],
                "email": employee.get("email"),
                "contact": employee.get("phone"),
                "type": "employee",
                "reference_id": employee.get("reference_id", employee["name"]),
            },
        },
        "queue_if_low_balance": True,
        "reference_id": employee.get("reference_id", employee["name"]),
        "narration": "grosslo payroll disbursement"[:30],
    }


@app.route("/api/export-razorpayx", methods=["POST"])
def api_export_razorpayx():
    data = request.get_json(force=True)
    try:
        ctc = float(data["ctc"])
        rent_paid = float(data.get("rent_paid", 0))
        city = data.get("city", "metro")
        nps_opted = bool(data.get("nps_opted", False))
        band_min = float(data["band_min"])
        band_max = float(data["band_max"])
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "ctc, band_min, and band_max are required and must be numeric"}), 400

    if band_min <= 0 or band_max <= 0:
        return jsonify({"error": "band_min and band_max must be positive"}), 400
    if band_min >= band_max:
        return jsonify({"error": "band_min must be less than band_max"}), 400

    # employees is OPTIONAL: the guardrail/treasury check needs to be
    # runnable as soon as a structure exists, before anyone has entered
    # payroll bank details. When omitted, this returns everything except
    # the actual payout payloads — the same endpoint, called again later
    # once employees are supplied, additionally returns those.
    employees = data.get("employees")
    if employees is not None:
        if not isinstance(employees, list) or not employees:
            return jsonify({"error": "employees, if supplied, must be a non-empty list of {name, bank_account_number, ifsc, ...}"}), 400
        for e in employees:
            if not isinstance(e, dict) or not e.get("name") or not e.get("bank_account_number") or not e.get("ifsc"):
                return jsonify({"error": "each employee requires name, bank_account_number, and ifsc"}), 400

    account_number = data.get("account_number", DEFAULT_RAZORPAYX_ACCOUNT_NUMBER)

    # Server recomputes the structure deterministically from ctc/rent/city/nps
    # rather than trusting client-supplied numbers — same principle as every
    # other route here: the client never gets to hand back its own tax figures.
    result = optimize(ctc=ctc, rent_paid=rent_paid, city=city, nps_opted=nps_opted)
    recommended = result["recommended"]

    guardrail = evaluate_band_guardrail(recommended.structure, recommended.regime, band_min, band_max)
    forecast = treasury_forecast(recommended.structure, recommended.tax_breakdown)

    response = {
        "treasury_forecast": forecast,
        "compliance_metadata": guardrail,
        "idempotency_key_hint": str(uuid.uuid4()),
        "execution_trace": [trace_guardrail_stage(guardrail)],
    }
    if employees is not None:
        response["payouts"] = [
            _build_composite_payout(recommended.structure, employee, account_number)
            for employee in employees
        ]

    _append_audit_log("/api/export-razorpayx", {
        "ctc": ctc, "band_min": band_min, "band_max": band_max,
        "guardrail_verdict": guardrail.get("verdict"),
        "payout_payloads_generated": len(employees) if employees is not None else 0,
        "total_capital_outlay": forecast["total_capital_outlay"],
    })
    return jsonify(response)


def _parse_commit_dates(git_log_output: str) -> dict:
    """
    Pure function: takes raw 'one date per line, YYYY-MM-DD' text (as
    produced by `git log --format=%ad --date=short`) and returns a
    {date: count} dict. Kept separate from the subprocess call so this
    logic is testable without needing a real git repo in the test run.
    """
    counts = {}
    for line in git_log_output.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        counts[line] = counts.get(line, 0) + 1
    return counts


def _get_commit_history() -> dict:
    """
    Runs `git log` in the current working directory and returns real
    commit-activity data for the calendar/commit-grid widget. Degrades
    gracefully (empty result, not a crash) if git isn't available or this
    isn't a git repo — matches the deterministic-fallback pattern used
    throughout ai_layer.py: never let an optional feature take down a
    request over something that isn't core to the tax calculation.
    """
    try:
        result = subprocess.run(
            ["git", "log", "--format=%ad", "--date=short"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return {"commits": {}, "total_commits": 0, "available": False}
        commits = _parse_commit_dates(result.stdout)
        return {"commits": commits, "total_commits": sum(commits.values()), "available": True}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"commits": {}, "total_commits": 0, "available": False}


@app.route("/api/submissions", methods=["POST"])
def api_create_submission():
    """
    HR's "Submit to Finance for Review" action — the sole path for
    structuring both new hires and corrections, single or batch. Computes
    each row via the same _build_optimize_response() every other route uses
    (zero new tax logic), then persists it to the review queue as 'pending'.
    Batch submissions skip the per-row AI explanation (skip_explanation_ai)
    for the same measured reason /api/batch-audit's docstring describes —
    a live API call per row doesn't scale.
    """
    data = request.get_json(force=True)
    source = data.get("source")
    if source not in ("single", "batch"):
        return jsonify({"error": "source must be 'single' or 'batch'"}), 400

    raw_rows = data.get("rows") if source == "batch" else [data.get("row")]
    if not isinstance(raw_rows, list) or not raw_rows or any(not isinstance(r, dict) for r in raw_rows):
        return jsonify({"error": "rows must be a non-empty list of row objects"}), 400

    built_rows, row_errors = [], []
    for i, row in enumerate(raw_rows):
        try:
            ctc = float(row["ctc"])
            rent_paid = float(row.get("rent_paid", 0))
            city = row.get("city", "metro")
            nps_opted = bool(row.get("nps_opted", False))
        except (KeyError, ValueError, TypeError):
            row_errors.append({"row_index": i, "error": "ctc is required and must be numeric"})
            continue
        if ctc <= 0:
            row_errors.append({"row_index": i, "error": "ctc must be positive"})
            continue

        current_structure = row.get("current_structure")
        response, raw_result = _build_optimize_response(
            ctc, rent_paid, city, nps_opted,
            current_structure, bool(row.get("extraction_ai_backed", False)),
            skip_explanation_ai=(source == "batch"),
        )

        # Band is optional (same convention as /api/optimize's own
        # bandMissing handling on the frontend) — but when supplied, the
        # guardrail actually runs here, in the review queue itself. It
        # previously didn't: Finance could approve an offer with zero
        # visibility into whether it was even within the approved
        # compensation band, which defeats a real part of the point of
        # having a review step at all.
        band_min, band_max = row.get("band_min"), row.get("band_max")
        if band_min is not None and band_max is not None:
            try:
                band_min, band_max = float(band_min), float(band_max)
                if band_min > 0 and band_max > 0 and band_min < band_max:
                    response["guardrail"] = evaluate_band_guardrail(
                        raw_result["recommended"].structure, raw_result["recommended"].regime, band_min, band_max,
                    )
            except (ValueError, TypeError):
                pass  # malformed band just skips the guardrail check, doesn't fail the row

        built_rows.append({
            "employee_name": row.get("employee_name"),
            "ctc": ctc,
            "input": {
                "ctc": ctc, "rent_paid": rent_paid, "city": city, "nps_opted": nps_opted,
                "current_structure": current_structure, "employee_name": row.get("employee_name"),
                "band_min": band_min if isinstance(band_min, float) else None,
                "band_max": band_max if isinstance(band_max, float) else None,
                # Bank details are stored here ONLY for eventual RazorpayX
                # export after Finance approves — never logged to
                # audit_log.jsonl (see _append_audit_log's own docstring),
                # and only ever read back by /rows/<i>/export below.
                "bank_account_number": row.get("bank_account_number"),
                "ifsc": row.get("ifsc"),
                "email": row.get("email"),
            },
            "computed": response,
        })

    if not built_rows:
        return jsonify({"error": "no valid rows to submit", "row_errors": row_errors}), 400

    result = review_queue.create_submission(source, built_rows, submitted_by=data.get("submitted_by", "hr"))
    _append_audit_log("/api/submissions", {
        "submission_id": result["submission_id"], "source": source,
        "rows_submitted": len(built_rows), "duplicates_skipped": len(result["duplicates"]),
    })
    return jsonify({**result, "row_errors": row_errors})


@app.route("/api/submissions", methods=["GET"])
def api_list_submissions():
    status = request.args.get("status")
    return jsonify({"submissions": review_queue.list_submissions(status)})


@app.route("/api/submissions/<int:submission_id>", methods=["GET"])
def api_get_submission(submission_id):
    """Finance's detail view — includes the before/after diff per row, built over already-computed data only."""
    submission = review_queue.get_submission(submission_id)
    if submission is None:
        return jsonify({"error": "submission not found"}), 404
    for row in submission["rows"]:
        row["diff"] = build_diff(row["input"], row["computed"])
    return jsonify(submission)


@app.route("/api/submissions/<int:submission_id>/rows/<int:row_index>/decide", methods=["POST"])
def api_decide_row(submission_id, row_index):
    """
    Finance's approve/reject action on one row. Idempotent: a second call
    on an already-decided row (a double-click, a retried request) writes
    nothing and returns already_decided=True — see review_queue.decide_row.
    Approving NEVER calls RazorpayX or dispatches anything; the response
    and audit-log entry say so explicitly, on purpose, matching the same
    boundary drawn everywhere else in this codebase around live execution.
    """
    data = request.get_json(force=True)
    decision = data.get("decision")
    reason = data.get("reason")
    if decision not in ("approve", "reject"):
        return jsonify({"error": "decision must be 'approve' or 'reject'"}), 400
    if decision == "reject" and not reason:
        return jsonify({"error": "a rejection requires a reason"}), 400

    try:
        result = review_queue.decide_row(submission_id, row_index, decision, reason,
                                          decided_by=data.get("decided_by", "finance"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if result["already_decided"]:
        return jsonify({
            "already_decided": True,
            "current_status": result["current_status"],
            "message": f"This row was already {result['current_status']} — no second decision was recorded.",
        }), 409

    _append_audit_log("/api/submissions/decide", {
        "submission_id": submission_id, "row_index": row_index, "decision": decision, "reason": reason,
    })
    return jsonify({
        "already_decided": False,
        "status": result["row"]["status"],
        "message": "Approved — Payout SIMULATED, no live dispatch." if decision == "approve"
                    else f"Rejected: {reason}",
    })


@app.route("/api/submissions/<int:submission_id>/rows/<int:row_index>/export", methods=["POST"])
def api_export_approved_row(submission_id, row_index):
    """
    Closes the loop after Finance approves: generates the correct kind of
    output for that specific row, without requiring HR or Finance to
    re-enter anything. Which kind depends on what the row actually is,
    not on which page it happened to be submitted from:
    - A row with a current_structure is a correction (came from the audit
      mode's "Submit correction") -> a Bulk Salary Revision XLSX, current
      vs. corrected, via salary_revision_export.py.
    - A row with no current_structure is a new hire -> a RazorpayX
      Composite Payout payload, via the same _build_composite_payout()
      /api/export-razorpayx already uses. Requires bank_account_number
      and ifsc to have been supplied at submission time; if they weren't,
      this says so rather than generating a payload with fabricated
      bank details.
    Only ever runs on a row that's actually 'approved' — exporting a
    pending or rejected row is refused, not just discouraged.
    """
    submission = review_queue.get_submission(submission_id)
    if submission is None:
        return jsonify({"error": "submission not found"}), 404
    row = next((r for r in submission["rows"] if r["row_index"] == row_index), None)
    if row is None:
        return jsonify({"error": "row not found"}), 404
    if row["status"] != "approved":
        return jsonify({"error": f"row is '{row['status']}', not approved — export requires approval first"}), 400

    inp = row["input"]
    computed = row["computed"]
    recommended_regime = computed["recommended_regime"]
    recommended_structure_dict = computed[f"{recommended_regime}_regime_best"]["structure"]

    if inp.get("current_structure"):
        # Correction path -> Salary Revision XLSX.
        wb = build_salary_revision_workbook([{
            "employee_name": row.get("employee_name") or f"Row {row_index + 1}",
            "ctc": inp["ctc"],
            "current": inp["current_structure"],
            "corrected": recommended_structure_dict,
        }])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        _append_audit_log("/api/submissions/export", {
            "submission_id": submission_id, "row_index": row_index, "export_type": "salary_revision",
        })
        response = send_file(
            buf, as_attachment=True, download_name="grosslo_salary_revision.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response.headers["X-Template-Honesty-Label"] = TEMPLATE_HONESTY_LABEL.replace("—", "-")
        return response

    # New-hire path -> RazorpayX Composite Payout payload.
    if not inp.get("bank_account_number") or not inp.get("ifsc"):
        return jsonify({
            "error": "bank_account_number and ifsc were not supplied for this submission — "
                     "can't generate a real payout payload without them",
        }), 400

    result = optimize(ctc=inp["ctc"], rent_paid=inp["rent_paid"], city=inp["city"], nps_opted=inp["nps_opted"])
    recommended = result["recommended"]
    forecast = treasury_forecast(recommended.structure, recommended.tax_breakdown)
    employee = {
        "name": row.get("employee_name") or f"Row {row_index + 1}",
        "bank_account_number": inp["bank_account_number"],
        "ifsc": inp["ifsc"],
        "email": inp.get("email"),
    }
    payload = {
        "treasury_forecast": forecast,
        "guardrail": computed.get("guardrail"),
        "idempotency_key_hint": str(uuid.uuid4()),
        "payouts": [_build_composite_payout(recommended.structure, employee, DEFAULT_RAZORPAYX_ACCOUNT_NUMBER)],
    }
    _append_audit_log("/api/submissions/export", {
        "submission_id": submission_id, "row_index": row_index, "export_type": "razorpayx_payout",
        "total_capital_outlay": forecast["total_capital_outlay"],
    })
    return jsonify(payload)


@app.route("/api/export-salary-revision", methods=["POST"])
def api_export_salary_revision():
    """
    Generates a Bulk Salary Revision XLSX for already-flagged employees —
    see salary_revision_export.py for the honesty label on the template
    shape and why this is a separate module from the RazorpayX payout
    payload generator. No live upload occurs; this returns a file only.
    """
    data = request.get_json(force=True)
    employees = data.get("employees")
    if not isinstance(employees, list) or not employees:
        return jsonify({"error": "employees must be a non-empty list of {employee_name, ctc, current, corrected}"}), 400
    for i, e in enumerate(employees):
        if not isinstance(e, dict) or not e.get("employee_name") or "ctc" not in e or "current" not in e or "corrected" not in e:
            return jsonify({"error": f"employee at index {i} requires employee_name, ctc, current, and corrected"}), 400

    wb = build_salary_revision_workbook(employees)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    _append_audit_log("/api/export-salary-revision", {"employee_count": len(employees)})

    response = send_file(
        buf, as_attachment=True, download_name="grosslo_salary_revision.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    # HTTP header values must be Latin-1-encodable — the em-dash in
    # TEMPLATE_HONESTY_LABEL isn't, and setting it directly hung the dev
    # server on a real request (caught live, not by inspection). The file's
    # own Read Me sheet keeps the original Unicode; only the header copy is
    # ASCII-sanitized, since that's the only one with an encoding constraint.
    response.headers["X-Template-Honesty-Label"] = TEMPLATE_HONESTY_LABEL.replace("—", "-")
    return response


@app.route("/api/commit-history")
def api_commit_history():
    return jsonify(_get_commit_history())


@app.route("/api/audit-log")
def api_audit_log():
    """
    Read-only view of the local audit trail _append_audit_log() writes on
    every money-adjacent decision. Exists so the audit trail is something a
    reviewer can actually inspect live (curl this route, or GET it in a
    browser), not just a claim about a file on disk. Same degrade-gracefully
    pattern as _get_commit_history(): an empty/missing log file is a valid,
    non-error state (nothing has run yet), not a crash.
    """
    limit = min(int(request.args.get("limit", 50)), 500)
    entries = []
    try:
        with open(AUDIT_LOG_PATH) as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
    except (OSError, json.JSONDecodeError):
        pass
    return jsonify({"entries": entries[-limit:], "total_logged": len(entries)})


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
