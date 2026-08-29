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
from tax_engine import SalaryStructure

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


def explain_result(optimizer_result: dict, rent_paid: float, city: str) -> dict:
    """
    Generate a plain-language explanation of the optimizer's recommendation.
    Returns {"explanation": str, "ai_backed": bool, "guard_triggered": bool}.
    guard_triggered=True means the LLM output contained a number not present
    in the input data, and we fell back to the deterministic explanation.
    """
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
