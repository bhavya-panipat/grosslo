"""
FinOS AI Layer — LLM-backed extraction, explanation, and compliance flagging.

ARCHITECTURE RULE (do not violate): these functions never compute or invent
tax figures. Extraction pulls numbers out of text the user already gave.
Explanation and compliance flagging only narrate numbers already produced by
tax_engine.py / optimizer.py. If you find yourself having the LLM do
arithmetic on money, that's a bug — route it through the engine instead.

FALLBACK DESIGN: every function tries a real Claude API call first. If the
API key isn't configured, the call fails, or the response doesn't parse, the
function falls back to deterministic logic and marks the result with
"ai_backed": False so the UI can show "rule-based result — AI layer
unavailable" instead of silently pretending the fallback was an LLM.
"""

import json
import os
import re
from typing import Optional
from optimizer import optimize
from tax_engine import SalaryStructure, NPS_80CCD2_CAP_PCT

try:
    import anthropic
    _client = anthropic.Anthropic() if os.environ.get("ANTHROPIC_API_KEY") else None
except Exception:
    _client = None

MODEL = "claude-sonnet-4-5-20250929"


# ---------------------------------------------------------------------------
# Phase 1: Extraction
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = """You extract salary figures from Indian offer \
letters or CTC breakup text. Return ONLY a JSON object, no prose, no markdown \
fences. Schema:
{
  "ctc": <number or null>,
  "basic": <number or null>,
  "hra": <number or null>,
  "lta": <number or null>,
  "special_allowance": <number or null>,
  "employer_pf": <number or null>,
  "currency_note": <string — anything unusual about units, e.g. "figures in lakhs">
}
All figures are ANNUAL rupee amounts. If the text gives monthly figures, \
convert to annual (multiply by 12) and note this in currency_note. If a \
field isn't present in the text, use null. Do not guess or invent a number \
that isn't derivable from the text."""


def _deterministic_extract(text: str) -> dict:
    """
    Fallback: regex-based extraction. Looks for common patterns like
    "CTC: 12,00,000" or "Basic Salary - Rs. 5,40,000". Deliberately
    conservative — returns null for anything it can't confidently match,
    rather than guessing.
    """
    def find_amount(labels: list[str]) -> Optional[float]:
        for label in labels:
            pattern = rf"{label}[:\-\s]*(?:rs\.?|inr|₹)?\s*([\d,]+(?:\.\d+)?)\s*(lakh|lac|l\b)?"
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                num = float(m.group(1).replace(",", ""))
                if m.group(2):
                    num *= 100_000
                return num
        return None

    return {
        "ctc": find_amount(["ctc", "cost to company", "total compensation"]),
        "basic": find_amount(["basic salary", "basic pay", "basic"]),
        "hra": find_amount(["hra", "house rent allowance"]),
        "lta": find_amount(["lta", "leave travel allowance"]),
        "special_allowance": find_amount(["special allowance", "special pay"]),
        "employer_pf": find_amount(["employer pf", "provident fund \\(employer\\)", "epf \\(employer\\)"]),
        "currency_note": "extracted via deterministic pattern match — verify figures manually",
    }


def extract_from_text(text: str) -> dict:
    """
    Extract structured salary fields from messy offer-letter text.
    Returns dict with the extracted fields plus "ai_backed" (bool) and
    "mismatch_warning" (str or None) if extracted total != sum of parts.
    """
    result = None
    ai_backed = False

    if _client is not None:
        try:
            response = _client.messages.create(
                model=MODEL,
                max_tokens=500,
                system=EXTRACTION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": text}],
            )
            raw = response.content[0].text.strip()
            raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
            parsed = json.loads(raw)
            result = {
                "ctc": parsed.get("ctc"),
                "basic": parsed.get("basic"),
                "hra": parsed.get("hra"),
                "lta": parsed.get("lta"),
                "special_allowance": parsed.get("special_allowance"),
                "employer_pf": parsed.get("employer_pf"),
                "currency_note": parsed.get("currency_note", ""),
            }
            ai_backed = True
        except Exception as e:
            result = None  # fall through to deterministic

    if result is None:
        result = _deterministic_extract(text)
        ai_backed = False

    # Mismatch check: only meaningful when we have a near-complete breakdown.
    # A letter that simply doesn't itemize LTA/PF (very common) will always
    # "fail" a naive sum check — that's a false positive, not a real
    # inconsistency, so we require at least 4 of 5 components before judging.
    parts = [result.get(k) for k in ("basic", "hra", "lta", "special_allowance", "employer_pf")]
    known_parts = [p for p in parts if p is not None]
    mismatch_warning = None
    if result.get("ctc") and len(known_parts) >= 4:
        parts_sum = sum(known_parts)
        if abs(parts_sum - result["ctc"]) > 0.05 * result["ctc"]:
            mismatch_warning = (
                f"Extracted components sum to ~{parts_sum:,.0f} but CTC was "
                f"read as {result['ctc']:,.0f} — please verify before proceeding."
            )

    result["ai_backed"] = ai_backed
    result["mismatch_warning"] = mismatch_warning
    return result


# ---------------------------------------------------------------------------
# Phase 2: Explainer
# ---------------------------------------------------------------------------

EXPLAINER_SYSTEM_PROMPT = """You explain Indian salary tax optimization \
results in plain language for someone who isn't a tax expert. You are given \
a JSON object with already-computed results — old regime best, new regime \
best, the recommendation, and the rupee delta. Write 2-4 sentences \
explaining WHY the recommended option wins for this specific person, \
referencing their actual numbers (CTC, rent, basic split). \

CRITICAL RULE: you must not introduce any rupee figure, percentage, or tax \
amount that is not already present in the JSON you're given. If you want to \
state a number, copy it exactly from the input. Do not compute anything. Do \
not round differently than the input. Return plain text only, no markdown."""


def _extract_numbers(text: str) -> list[float]:
    """Pull out numeric tokens from text for the numeric-guard check."""
    # Match numbers with optional commas/decimals, ignore standalone small
    # integers that are almost certainly not rupee figures (e.g. "2-4 sentences")
    raw = re.findall(r"[\d,]+\.?\d*", text)
    nums = []
    for r in raw:
        cleaned = r.replace(",", "")
        try:
            nums.append(float(cleaned))
        except ValueError:
            continue
    return nums


def _deterministic_explain(optimizer_result: dict, rent_paid: float, city: str) -> str:
    rec = optimizer_result["recommended"]
    delta = optimizer_result["annual_tax_saving_vs_other_regime"]
    ctc = optimizer_result["ctc"]
    return (
        f"For a CTC of Rs {ctc:,.0f}, the {rec.regime} regime gives the lower "
        f"tax outcome, saving Rs {delta:,.0f} per year compared to the other "
        f"regime. This is based on a basic salary of {rec.basic_pct:.0%} of "
        f"CTC and rent paid of Rs {rent_paid:,.0f} in a {city.replace('_', '-')} "
        f"city — see the full breakdown table for exact component amounts."
    )


def explain_result(optimizer_result: dict, rent_paid: float, city: str, skip_ai: bool = False) -> dict:
    """
    Generate a plain-language explanation of the optimizer's recommendation.
    Returns {"explanation": str, "ai_backed": bool, "guard_triggered": bool}.
    guard_triggered=True means the LLM output contained a number not present
    in the input data, and we fell back to the deterministic explanation.

    skip_ai=True goes straight to the deterministic explanation without
    ever calling the live API — for batch mode, where per-row prose is
    generated but never rendered anywhere in the batch UI (checked:
    batch-results-table.tsx shows only CTC/regime/saving/guardrail columns).
    Measured live: with skip_ai unset, a 20-row batch took over 60 seconds
    because of one sequential blocking API call per row; with it set, the
    same batch completed in ~0.1s. Not a design tradeoff — the explanation
    text this was generating was pure waste, computed and then discarded.
    """
    if skip_ai:
        return {
            "explanation": _deterministic_explain(optimizer_result, rent_paid, city),
            "ai_backed": False,
            "guard_triggered": False,
        }
    rec = optimizer_result["recommended"]
    payload = {
        "ctc": optimizer_result["ctc"],
        "rent_paid": rent_paid,
        "city": city,
        "recommended_regime": rec.regime,
        "recommended_basic_pct": rec.basic_pct,
        "recommended_total_tax": rec.tax_breakdown["total_tax"],
        "annual_saving_vs_other_regime": optimizer_result["annual_tax_saving_vs_other_regime"],
        "old_regime_tax": optimizer_result["old_regime_best"].tax_breakdown["total_tax"],
        "new_regime_tax": optimizer_result["new_regime_best"].tax_breakdown["total_tax"],
    }
    allowed_numbers = set(round(v, 2) for v in payload.values() if isinstance(v, (int, float)))
    # also allow the same numbers formatted without decimals / as ints
    allowed_numbers |= set(round(v) for v in allowed_numbers)

    explanation = None
    ai_backed = False
    guard_triggered = False

    if _client is not None:
        try:
            response = _client.messages.create(
                model=MODEL,
                max_tokens=300,
                system=EXPLAINER_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": json.dumps(payload)}],
            )
            candidate = response.content[0].text.strip()
            found_numbers = _extract_numbers(candidate)
            # numeric guard: every number mentioned must be traceable to input
            for n in found_numbers:
                if n < 100:
                    continue  # skip small numbers like "2-4 sentences", percentages read separately
                if not any(abs(n - allowed) < 1 for allowed in allowed_numbers):
                    guard_triggered = True
                    break
            if not guard_triggered:
                explanation = candidate
                ai_backed = True
        except Exception:
            pass

    if explanation is None:
        explanation = _deterministic_explain(optimizer_result, rent_paid, city)
        ai_backed = False

    return {
        "explanation": explanation,
        "ai_backed": ai_backed,
        "guard_triggered": guard_triggered,
    }


# ---------------------------------------------------------------------------
# Phase 3: Compliance-risk flagging
# ---------------------------------------------------------------------------
# Rules are defined in compliance_rules.md (R1-R6). This module checks a
# given structure against those exact rules — it does not invent new checks.

COMPLIANCE_SYSTEM_PROMPT = """You phrase compliance-flag results in plain \
language for a non-technical user. You are given a JSON list of rule IDs \
that were triggered, each with its rationale and severity, already computed \
by fixed rule-matching code — you do NOT decide which rules trigger. Your \
only job is to phrase each triggered rule's rationale clearly and briefly \
(1 sentence each). Do not add rules, do not add numbers, do not give legal \
advice beyond what's in the rationale text provided. Return plain text, one \
line per flag, no markdown."""


def _check_rules(structure, rent_paid: float) -> list[dict]:
    """
    Deterministic rule-matching against compliance_rules.md's R1-R6. This
    part is NOT an LLM call by design — matching numeric thresholds against
    fixed rules is exactly the kind of deterministic logic that should never
    be delegated to an LLM. Only the phrasing (below) is LLM territory.
    """
    flags = []
    ctc = structure.ctc
    basic_pct = structure.basic / ctc if ctc else 0

    if basic_pct < 0.35:
        flags.append({
            "rule_id": "R1", "severity": "Medium",
            "rationale": "Basic salary is below common market convention (under 35% of CTC), which may indicate an attempt to minimize statutory PF/gratuity obligations.",
        })
    if ctc > 600_000 and structure.employer_pf == 0:
        flags.append({
            "rule_id": "R2", "severity": "Medium",
            "rationale": "No employer PF component despite CTC above Rs 6L/year — PF is near-universal at this level; confirm this isn't an oversight.",
        })
    if structure.hra > 0 and rent_paid <= 0:
        flags.append({
            "rule_id": "R3", "severity": "Low",
            "rationale": "HRA is structured into the salary but no rent payment was provided — the HRA exemption requires actual rent with documentation.",
        })
    if ctc and structure.lta > 0.10 * ctc:
        flags.append({
            "rule_id": "R4", "severity": "Low",
            "rationale": "LTA exceeds 10% of CTC, above typical company policy ceilings, and may not be realizable given actual travel requirements.",
        })
    if (structure.employer_pf + structure.employer_nps) > 750_000:
        flags.append({
            "rule_id": "R5", "severity": "High",
            "rationale": "Aggregate employer PF + NPS exceeds Rs 7.5L/year — the excess is a taxable perquisite under Section 17(2)(vii), which this tool's tax engine does not currently model.",
        })
    if structure.special_allowance == 0:
        flags.append({
            "rule_id": "R6", "severity": "Low",
            "rationale": "Special allowance is zero, leaving no flexible cash component — check this wasn't an input error.",
        })
    return flags


# ---------------------------------------------------------------------------
# Radar/ring metrics: Compliance % and AI Coverage %
# ---------------------------------------------------------------------------

TOTAL_COMPLIANCE_RULES = 6  # R1-R6, defined above


def compliance_pct(flags: list) -> float:
    """(total rules - flags triggered) / total rules, as a percentage."""
    triggered = len(flags)
    return round((TOTAL_COMPLIANCE_RULES - triggered) / TOTAL_COMPLIANCE_RULES * 100, 1)


def ai_coverage_pct(extraction_ran: bool, extraction_ai_backed: bool,
                     explanation_ai_backed: bool, compliance_ai_backed: bool,
                     negotiation_ran: bool, negotiation_ai_backed: bool,
                     compliance_ran: bool = True) -> float:
    """
    % of the capabilities that actually ran THIS PASS that were genuinely
    AI-backed (not fallback). A capability not running (e.g. no offer
    letter pasted, so extraction/negotiation are not applicable) is
    excluded from the denominator entirely — it's neutral, not a failure.
    Penalizing a valid manual-CTC-only run for something that was never
    applicable would be its own kind of misleading number.

    Compliance rule-matching always *executes*, but there's nothing for the
    LLM to do when zero rules fire — no flags to rephrase into plain
    language. That's the same "not applicable" case extraction/negotiation
    already get excluded for, so compliance is excluded from the
    denominator too when compliance_ran is False (i.e. zero flags),
    instead of counting as a fallback data point that silently caps this
    metric near 50% on the most common, cleanest-structure path. Caller
    passes compliance_ran=len(flags) > 0. Defaults to True so existing
    call sites that always had flags aren't forced to pass it.
    """
    ran = [explanation_ai_backed]
    if compliance_ran:
        ran.append(compliance_ai_backed)
    if extraction_ran:
        ran.append(extraction_ai_backed)
    if negotiation_ran:
        ran.append(negotiation_ai_backed)
    if not ran:
        return 0.0
    return round(sum(1 for x in ran if x) / len(ran) * 100, 1)


def flag_compliance(structure, rent_paid: float) -> dict:
    """
    Check a salary structure against the fixed compliance_rules.md checklist.
    Rule matching is always deterministic (see _check_rules). The LLM, when
    available, only rephrases the already-determined flags into cleaner
    prose — it cannot add or remove flags.
    Returns {"flags": [...], "ai_backed": bool}.
    """
    triggered = _check_rules(structure, rent_paid)
    if not triggered:
        return {"flags": [], "ai_backed": False}

    if _client is not None:
        try:
            response = _client.messages.create(
                model=MODEL,
                max_tokens=400,
                system=COMPLIANCE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": json.dumps(triggered)}],
            )
            phrased = response.content[0].text.strip().split("\n")
            phrased = [p.strip("- ").strip() for p in phrased if p.strip()]
            if len(phrased) == len(triggered):
                for i, flag in enumerate(triggered):
                    flag["message"] = phrased[i]
                return {"flags": triggered, "ai_backed": True}
        except Exception:
            pass

    # Fallback: use the rationale text directly as the message
    for flag in triggered:
        flag["message"] = flag["rationale"]
    return {"flags": triggered, "ai_backed": False}


# ---------------------------------------------------------------------------
# RazorpayX pivot: band guardrail agent (replaces negotiate() in the UI —
# negotiate() itself stays defined/tested above, just unwired from the new
# flow, which is a B2B payroll-controller context rather than a candidate
# negotiating their own offer).
# ---------------------------------------------------------------------------

GUARDRAIL_SYSTEM_PROMPT = """You rephrase already-decided payroll guardrail \
check results into clear, professional sentences for a founder/HR/treasury \
audience. You are given a JSON list of checks, each with an id, label, a \
boolean "passed", and a rationale. Rephrase ONLY the rationale text for \
checks where passed is false — return exactly one rephrased sentence per \
failing check, one per line, in the same order they appear in the input, \
nothing else. Do not invent a rupee figure, percentage, or section number \
that is not already present in the rationale you were given. Do not add \
commentary about checks that passed."""

EPFO_AGGREGATE_CEILING = 750_000  # same threshold as compliance_rules.md Rule R5


def evaluate_band_guardrail(structure: SalaryStructure, regime: str,
                             band_min: float, band_max: float) -> dict:
    """
    Deterministic pass/flag checks on a structure before it's cleared for
    RazorpayX payout export: is the CTC within the approved compensation
    band, is the aggregate employer PF+NPS under the same Rs 7.5L ceiling
    Rule R5 already flags, and is employer NPS within the regime-specific
    Section 124 cap — formerly Section 80CCD(2) under the 1961 Act, renamed
    under the Income-tax Act 2025 effective 1 April 2026, rate unchanged
    (14% of basic under the new regime, 10% under the old — NOT a flat 10%,
    per tax_engine.py's own NPS_80CCD2_CAP_PCT, whose name is kept as-is
    since it's an internal constant, not user-facing text).

    Same pattern as flag_compliance: rule matching is always deterministic;
    the LLM, when available, only rephrases already-failing checks into
    cleaner prose. It cannot flip a pass into a fail or vice versa.
    Returns {"verdict": "pass"|"flag", "checks": [...], "ai_backed": bool,
             "guard_triggered": bool}.
    """
    ctc = structure.ctc

    band_ok = band_min <= ctc <= band_max
    checks = [{
        "id": "band_cost_neutrality",
        "label": "Within approved compensation band",
        "passed": band_ok,
        "rationale": (
            f"CTC of Rs {ctc:,.0f} is within the approved band of "
            f"Rs {band_min:,.0f}-Rs {band_max:,.0f}."
            if band_ok else
            f"CTC of Rs {ctc:,.0f} falls outside the approved band of "
            f"Rs {band_min:,.0f}-Rs {band_max:,.0f}."
        ),
    }]

    epfo_total = structure.employer_pf + structure.employer_nps
    epfo_ok = epfo_total <= EPFO_AGGREGATE_CEILING
    checks.append({
        "id": "epfo_ceiling",
        "label": "EPFO aggregate contribution ceiling",
        "passed": epfo_ok,
        "rationale": (
            f"Aggregate employer PF + NPS of Rs {epfo_total:,.0f} is within the "
            f"Rs {EPFO_AGGREGATE_CEILING:,.0f}/year ceiling."
            if epfo_ok else
            f"Aggregate employer PF + NPS of Rs {epfo_total:,.0f} exceeds the "
            f"Rs {EPFO_AGGREGATE_CEILING:,.0f}/year ceiling — the excess is a "
            "taxable perquisite under Section 17(2)(vii), not currently "
            "modeled in the tax engine."
        ),
    })

    cap_pct = NPS_80CCD2_CAP_PCT.get(regime, NPS_80CCD2_CAP_PCT["old"])
    nps_cap = cap_pct * structure.basic
    nps_ok = structure.employer_nps <= nps_cap
    checks.append({
        "id": "80ccd2_cap",
        "label": f"Section 124 employer NPS cap ({regime} regime, {cap_pct:.0%} of basic)",
        "passed": nps_ok,
        "rationale": (
            f"Employer NPS of Rs {structure.employer_nps:,.0f} is within the "
            f"Section 124 cap (formerly 80CCD(2)) of {cap_pct:.0%} of basic (Rs {nps_cap:,.0f}) "
            f"for the {regime} regime."
            if nps_ok else
            f"Employer NPS of Rs {structure.employer_nps:,.0f} exceeds the "
            f"Section 124 cap (formerly 80CCD(2)) of {cap_pct:.0%} of basic "
            f"(Rs {nps_cap:,.0f}) for the {regime} regime."
        ),
    })

    failing = [c for c in checks if not c["passed"]]
    verdict = "pass" if not failing else "flag"

    if not failing:
        for c in checks:
            c["message"] = c["rationale"]
        return {"verdict": verdict, "checks": checks, "ai_backed": False, "guard_triggered": False}

    ai_backed = False
    guard_triggered = False
    if _client is not None:
        try:
            response = _client.messages.create(
                model=MODEL,
                max_tokens=400,
                system=GUARDRAIL_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": json.dumps(failing)}],
            )
            phrased = response.content[0].text.strip().split("\n")
            phrased = [p.strip("- ").strip() for p in phrased if p.strip()]
            if len(phrased) == len(failing):
                for flag, message in zip(failing, phrased):
                    flag["message"] = message
                ai_backed = True
        except Exception:
            pass

    if not ai_backed:
        for flag in failing:
            flag["message"] = flag["rationale"]

    for c in checks:
        if c["passed"]:
            c["message"] = c["rationale"]

    return {"verdict": verdict, "checks": checks, "ai_backed": ai_backed, "guard_triggered": guard_triggered}


# ---------------------------------------------------------------------------
# Phase 4: Negotiation copilot
# ---------------------------------------------------------------------------
# Compares the offer letter's AS-EXTRACTED structure against the optimizer's
# recommended structure. The rupee TOTAL saving is a plain subtraction and is
# always trustworthy. Per-lever rupee attribution is deliberately NOT
# computed or claimed — when basic/HRA/LTA/NPS move together the tax
# function isn't linear across them, so a clean per-lever rupee split would
# itself be a false-precision claim. We only report WHICH structural levers
# changed, not how many rupees each one is individually "worth."

NEGOTIATION_SYSTEM_PROMPT = """You draft negotiation talking points for an \
employee to raise with HR/recruiting about their salary structure — NOT the \
total offer amount, only how the same CTC is split into components. You are \
given a JSON object with: the current (as-offered) structure's total tax, \
the recommended structure's total tax, the total annual rupee saving \
(already computed — trustworthy), and a list of which structural levers \
changed (e.g. "basic salary", "NPS enrollment") with NO rupee amount \
attached to each individual lever.

CRITICAL RULES:
1. You must not introduce any rupee figure that is not the exact \
   total_annual_saving value given to you. Do not invent, estimate, or \
   split that figure across the individual levers — the input deliberately \
   gives you no per-lever amounts, so do not manufacture any.
2. Do not give generic negotiation coaching (tone, timing, leverage, how to \
   ask for a raise). Stay strictly to: "you could ask to restructure X, \
   which is part of how this recommendation reaches Rs {total_annual_saving} \
   in annual savings."
3. Write 2-3 short, professional talking points the user could literally \
   send to HR, referencing the specific levers by name. Return plain text, \
   one point per line, no markdown, no preamble."""


def _deterministic_negotiate(total_saving: float, changed_levers: list[str],
                              recommended_regime: str) -> str:
    if not changed_levers:
        return (
            "Your offered structure already matches FinOS's recommended "
            "split closely — no structural changes to negotiate here."
        )
    levers_text = ", ".join(changed_levers)
    return (
        f"Your current structure and the recommended structure differ on: "
        f"{levers_text}. Restructuring along these lines (staying on the "
        f"{recommended_regime} regime) is projected to save Rs "
        f"{total_saving:,.0f} per year in tax, with your total CTC "
        f"unchanged. Consider asking HR whether these components can be "
        f"adjusted within their existing payroll policy."
    )


def _diff_levers(current: SalaryStructure, recommended: SalaryStructure,
                  ctc: float) -> list[str]:
    """
    Deterministic comparison — which components differ meaningfully
    (>1% of CTC, or a true/false flip for NPS) between the as-offered and
    recommended structures. This list, not any LLM, decides what counts as
    'changed.'
    """
    threshold = 0.01 * ctc
    levers = []
    if abs(current.basic - recommended.basic) > threshold:
        levers.append("basic salary")
    if abs(current.hra - recommended.hra) > threshold:
        levers.append("HRA")
    if abs(current.lta - recommended.lta) > threshold:
        levers.append("LTA")
    if bool(current.nps_opted) != bool(recommended.nps_opted):
        levers.append("NPS enrollment (80CCD2)")
    return levers


def negotiate(current_structure: SalaryStructure, current_best: dict,
              recommended: SalaryStructure, recommended_regime: str,
              recommended_tax: dict, ctc: float) -> dict:
    """
    Compare the offer letter's as-extracted structure against the
    optimizer's recommendation and produce negotiation talking points.
    Returns {"points": str, "total_annual_saving": float,
             "changed_levers": [...], "ai_backed": bool,
             "guard_triggered": bool}.
    Caller must only invoke this when a real extracted current_structure
    exists — there is nothing to negotiate away from a manually-entered
    CTC-only input with no offered breakdown.
    """
    total_saving = round(current_best["tax_breakdown"]["total_tax"] - recommended_tax["total_tax"], 2)
    changed_levers = _diff_levers(current_structure, recommended, ctc)

    if total_saving <= 0:
        return {
            "points": "Your offered structure is already at or near the tax-optimal split — nothing to negotiate here.",
            "total_annual_saving": max(total_saving, 0),
            "changed_levers": [],
            "ai_backed": False,
            "guard_triggered": False,
        }

    payload = {
        "total_annual_saving": total_saving,
        "changed_levers": changed_levers,
        "recommended_regime": recommended_regime,
    }
    allowed_numbers = {round(total_saving, 2), round(total_saving)}

    points = None
    ai_backed = False
    guard_triggered = False

    if _client is not None:
        try:
            response = _client.messages.create(
                model=MODEL,
                max_tokens=350,
                system=NEGOTIATION_SYSTEM_PROMPT.format(total_annual_saving=f"{total_saving:,.0f}"),
                messages=[{"role": "user", "content": json.dumps(payload)}],
            )
            candidate = response.content[0].text.strip()
            found_numbers = _extract_numbers(candidate)
            for n in found_numbers:
                if n < 100:
                    continue
                if not any(abs(n - allowed) < 1 for allowed in allowed_numbers):
                    guard_triggered = True
                    break
            if not guard_triggered:
                points = candidate
                ai_backed = True
        except Exception:
            pass

    if points is None:
        points = _deterministic_negotiate(total_saving, changed_levers, recommended_regime)
        ai_backed = False

    return {
        "points": points,
        "total_annual_saving": total_saving,
        "changed_levers": changed_levers,
        "ai_backed": ai_backed,
        "guard_triggered": guard_triggered,
    }


# ---------------------------------------------------------------------------
# Conversational query layer
# ---------------------------------------------------------------------------
# Two distinct question types, handled differently:
#   1. Explanatory ("why did old regime lose") - LLM narrates the EXISTING
#      already-computed result, numeric-guarded like explain_result.
#   2. Hypothetical ("what if my rent were higher") - the LLM's job is to
#      identify WHICH input changed, never to guess the answer. Python then
#      re-runs the real optimizer with the new value and the LLM narrates
#      that real, freshly-computed result. Skipping this and letting the
#      LLM estimate a plausible-sounding hypothetical would be exactly the
#      kind of fabricated number this whole architecture exists to prevent.

QUERY_CLASSIFY_PROMPT = """Classify the user's question about their tax \
optimization result into exactly one JSON object, nothing else:

{"type": "hypothetical", "param": "rent_paid", "value": 600000}
or
{"type": "hypothetical", "param": "nps_opted", "value": true}
or
{"type": "explanatory"}

"hypothetical" means the user is asking "what if X were different" about \
one of: rent_paid (number, rupees/year), ctc (number, rupees/year), \
nps_opted (true/false), city ("metro" or "non_metro"). Extract the single \
changed parameter and its new value. If the question doesn't clearly \
specify both a parameter and a new value, return {"type": "explanatory"} \
instead of guessing.

"explanatory" means any other question about the existing result (why a \
regime won, what a compliance flag means, what a number represents, etc).

Return ONLY the JSON object, no other text."""

QUERY_EXPLAIN_SYSTEM_PROMPT = """Answer the user's question about their \
already-computed tax optimization result, using ONLY the numbers given to \
you in the context JSON. Do not introduce any rupee figure, percentage, or \
number that is not already present in that context. If the question asks \
about something not covered by the given context, say so plainly rather \
than guessing. Keep the answer to 2-4 sentences, plain language, no \
markdown.

If you reference a specific statutory basis, cite ONLY a section listed in \
the context's "applicable_sections" array, using its exact wording (e.g. \
"Section 392 (formerly Section 192)"), and only when it's actually relevant \
to the question. Do not cite any section not present in that list, and do \
not cite one at all if the list is empty or none apply."""

QUERY_HYPOTHETICAL_SYSTEM_PROMPT = """Answer the user's 'what if' question \
using ONLY the before/after numbers given to you in the context JSON — \
these were computed by re-running the real tax optimizer with the changed \
input, not estimated. State the new result and the difference from the \
original clearly. Do not introduce any number not present in the context. \
Keep the answer to 2-4 sentences, plain language, no markdown."""


def _classify_query(question: str) -> dict:
    if _client is None:
        return {"type": "explanatory"}
    try:
        response = _client.messages.create(
            model=MODEL, max_tokens=150,
            system=QUERY_CLASSIFY_PROMPT,
            messages=[{"role": "user", "content": question}],
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r"^```(json)?|```$", "", raw.strip()).strip()
        parsed = json.loads(raw)
        if parsed.get("type") not in ("hypothetical", "explanatory"):
            return {"type": "explanatory"}
        return parsed
    except Exception:
        return {"type": "explanatory"}


def _deterministic_query_fallback(question: str, context: dict) -> str:
    rec = context.get("recommended_regime", "the recommended regime")
    tax = context.get("recommended_tax")
    saving = context.get("annual_saving")
    tax_str = f"₹{tax:,.0f}" if tax is not None else "the computed figure"
    saving_str = f"₹{saving:,.0f}" if saving is not None else "the computed amount"
    return (
        f"I can't process that specific question right now (AI layer "
        f"unavailable). Here's what's already computed: the recommended "
        f"structure is under the {rec} regime, with total tax of {tax_str}, "
        f"saving {saving_str}/year versus the other regime. See the sections "
        f"above for the full breakdown."
    )


def answer_query(question: str, context: dict, ctc: float, rent_paid: float,
                  city: str, nps_opted: bool) -> dict:
    """
    context: dict with at least recommended_regime, recommended_tax,
    annual_saving — the already-computed result, used for explanatory
    answers and as the fallback baseline.

    Returns {"answer": str, "ai_backed": bool, "recalculated": bool,
             "guard_triggered": bool}.
    """
    classification = _classify_query(question)

    if classification.get("type") == "hypothetical" and classification.get("param") in {"rent_paid", "ctc", "nps_opted", "city"}:
        new_kwargs = {"ctc": ctc, "rent_paid": rent_paid, "city": city, "nps_opted": nps_opted}
        param, value = classification["param"], classification.get("value")
        if value is None:
            return {
                "answer": _deterministic_query_fallback(question, context),
                "ai_backed": False, "recalculated": False, "guard_triggered": False,
            }
        try:
            if param == "rent_paid":
                new_kwargs["rent_paid"] = float(value)
            elif param == "ctc":
                new_kwargs["ctc"] = float(value)
            elif param == "nps_opted":
                new_kwargs["nps_opted"] = bool(value)
            elif param == "city":
                new_kwargs["city"] = "metro" if str(value).lower() == "metro" else "non_metro"
        except (TypeError, ValueError):
            return {
                "answer": _deterministic_query_fallback(question, context),
                "ai_backed": False, "recalculated": False, "guard_triggered": False,
            }

        new_result = optimize(**new_kwargs)
        new_tax = new_result["recommended"].tax_breakdown["total_tax"]
        old_tax = context.get("recommended_tax", new_tax)
        payload = {
            "changed_param": param, "new_value": new_kwargs[param],
            "original_tax": old_tax, "new_tax": new_tax,
            "difference": round(new_tax - old_tax, 2),
            "new_recommended_regime": new_result["recommended"].regime,
        }
        allowed = {round(old_tax, 2), round(new_tax, 2), round(new_tax - old_tax, 2), round(abs(new_tax - old_tax), 2)}
        if isinstance(new_kwargs[param], (int, float)) and not isinstance(new_kwargs[param], bool):
            allowed.add(round(new_kwargs[param], 2))

        # Declared here, not inside the try block, so the real computed
        # value survives into the fallback return below — a real bug this
        # exact structure: without this, guard_triggered was computed
        # correctly but then discarded, and the fallback path always
        # reported False even when the guard had genuinely just fired.
        guard_triggered = False
        if _client is not None:
            try:
                response = _client.messages.create(
                    model=MODEL, max_tokens=250,
                    system=QUERY_HYPOTHETICAL_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": json.dumps(payload)}],
                )
                candidate = response.content[0].text.strip()
                nums = _extract_numbers(candidate)
                guard_triggered = any(n >= 100 and not any(abs(n - a) < 1 for a in allowed) for n in nums)
                if not guard_triggered:
                    return {"answer": candidate, "ai_backed": True, "recalculated": True, "guard_triggered": False}
            except Exception:
                pass

        diff = payload["difference"]
        direction = "more" if diff > 0 else "less"
        fallback = (
            f"Recalculated with {param.replace('_', ' ')} = {value}: total tax "
            f"would be ₹{new_tax:,.0f} ({new_result['recommended'].regime} regime), "
            f"₹{abs(diff):,.0f} {direction} than the original ₹{old_tax:,.0f}."
        )
        return {"answer": fallback, "ai_backed": False, "recalculated": True, "guard_triggered": guard_triggered}

    # Explanatory path — ground the answer in a real recomputed old-vs-new
    # diff rather than just the thin {recommended_regime, recommended_tax,
    # annual_saving} the caller supplied, and attach a data-driven citation
    # whitelist so "why" questions have real section references to draw on
    # instead of the LLM inferring one from the regime name alone.
    grounding = dict(context)
    try:
        full = optimize(ctc=ctc, rent_paid=rent_paid, city=city, nps_opted=nps_opted)
        old_best, new_best = full["old_regime_best"], full["new_regime_best"]
        grounding["old_regime_total_tax"] = old_best.tax_breakdown["total_tax"]
        grounding["new_regime_total_tax"] = new_best.tax_breakdown["total_tax"]
        grounding["tax_difference"] = round(
            old_best.tax_breakdown["total_tax"] - new_best.tax_breakdown["total_tax"], 2
        )
        # Citations verified against the Income-tax Act 2025 (effective
        # 1 April 2026) via live research, not recalled from training data —
        # the 1961-Act numbers are kept alongside the new ones since they're
        # still the recognizable, searched-for terms. Section 17(2)(vii)
        # elsewhere in this codebase (the >Rs 7.5L perquisite rule) is NOT
        # included in that verification: no confirmed 2025-Act mapping was
        # found for it, so it's left as the 1961-Act citation with the gap
        # noted, not silently treated as equally current.
        applicable_sections = []
        if old_best.structure.hra > 0 or new_best.structure.hra > 0:
            applicable_sections.append("Section 11, read with Schedule II (formerly Section 10(13A))")
        applicable_sections.append("Section 392 (formerly Section 192)")
        if old_best.structure.employer_nps > 0 or new_best.structure.employer_nps > 0:
            applicable_sections.append("Section 124 (formerly Section 80CCD(2))")
        grounding["applicable_sections"] = applicable_sections
    except Exception:
        grounding["applicable_sections"] = []  # fall back to the thin context if recompute fails

    allowed = set()
    for v in grounding.values():
        if isinstance(v, (int, float)):
            allowed.add(round(v, 2))
    # Same fix as the hypothetical-recalc branch above: declared outside the
    # try block so a genuine guard trigger survives into the fallback return
    # instead of being silently discarded as False.
    guard_triggered = False
    if _client is not None:
        try:
            response = _client.messages.create(
                model=MODEL, max_tokens=250,
                system=QUERY_EXPLAIN_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": json.dumps({"question": question, "context": grounding})}],
            )
            candidate = response.content[0].text.strip()
            nums = _extract_numbers(candidate)
            guard_triggered = any(n >= 100 and not any(abs(n - a) < 1 for a in allowed) for n in nums)
            if not guard_triggered:
                return {"answer": candidate, "ai_backed": True, "recalculated": False, "guard_triggered": False}
        except Exception:
            pass

    return {
        "answer": _deterministic_query_fallback(question, context),
        "ai_backed": False, "recalculated": False, "guard_triggered": guard_triggered,
    }
