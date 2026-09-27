"""
Forward-looking workforce cost forecast (addition spec Tier 2.1).

Design: WORKFORCE_COST_FORECAST_DESIGN.md. Read it before changing anything here;
every rule below is a decision recorded there, most of them measured.

What this module is: grouping hires into cohorts, multiplying by headcount,
iterating months, prorating a structure by months employed, and summing. What it
is NOT: a second tax engine. Every figure comes from functions that stay
unchanged (§2): optimize(), taxable_income_for_structure(), compute_tax(),
derive_pf(), monthly_professional_tax(). No LLM call anywhere, so the one
architecture rule holds by construction.

The four things a reader must know, each from the design:

- The total cash need is the CTC, prorated (§1). N hires need N x CTC x
  months/12. That is multiplication; what the engines add is the SPLIT.
- TDS is the tax on the part-year pay, never the annual tax prorated (§3). For a
  mid-year hire, proration is wrong by up to 100% of the figure, always too
  high, because the tax is not linear in pay. The primary figure assumes the
  hire declares no earlier salary (s. 392(4)(a)(i) of the Income-tax Act, 2025,
  read from CBDT only, NOT practitioner-confirmed; D-W1). The "if declared"
  line is the prorated annual figure, right only when earlier pay was at the
  same rate.
- Rent is required exactly when it can change the answer (§4), decided per
  request by comparing rent 0 against rent at the HRA exemption's ceiling. No
  threshold is hard-coded; the observed ones move whenever the engine does.
- The whole entered CTC (less any stated provision) is treated as cash (D-W2).
  If it includes gratuity or insurance, only the total and TDS are overstated
  in a known direction; EPFO, NPS and take-home can move either way (§7,
  22,080 comparisons).
"""
from __future__ import annotations

from dataclasses import dataclass

from optimizer import optimize
from payroll_breakdown import monthly_professional_tax
from tax_engine import SalaryStructure, compute_tax, derive_pf, taxable_income_for_structure

# The one financial year whose rates tax_engine.py holds for a forward forecast.
# Its module header reads "FY 2025-26 / FY 2026-27"; a test pins that this
# constant and that header agree, so a rate update that moves the year fails
# loudly here instead of silently forecasting on the wrong law (D-W3).
FORECAST_FY_LABEL = "FY 2026-27"
FY_FIRST_MONTH = (2026, 4)   # April 2026
FY_LAST_MONTH = (2027, 3)    # March 2027

# Same ceiling /api/optimize enforces: surcharge is not modelled above it.
MAX_CTC = 40_000_000

CITY_TIERS = ("metro", "non_metro")

TDS_BASIS_NOTE = (
    "TDS assumes the hire declares no salary from an earlier employer this year, "
    "so tax is withheld on this employment alone. \"If earlier salary is declared\" "
    "assumes it was paid at the same rate all year. This reading of the "
    "Income-tax Act, 2025, s. 392(4)(a)(i) is not practitioner-confirmed."
)
RENT_ASSUMED_ZERO_NOTE = (
    "Assumes no rent claimed. Rent cannot change the tax for this cohort, so "
    "this does not affect any figure shown."
)
CTC_BASIS_NOTE = (
    "The whole CTC entered, less any provision you excluded, is treated as cash "
    "pay. If it still includes gratuity or insurance, the total cash need and "
    "TDS are overstated; EPFO, NPS and take-home can be off in either direction."
)
RATES_NOTE = (
    f"{FORECAST_FY_LABEL} rates. Periods after March 2027 are refused until the "
    "next year's rates are enacted."
)
NOT_MODELLED = (
    "Gratuity, insurance and bonus provisions",
    "EDLI and EPFO administrative charges",
    "ESI, labour welfare fund, and the employee's own NPS contribution",
    "Professional tax outside Karnataka, Maharashtra, Telangana, Tamil Nadu and Delhi",
    "Whether the standard deduction applies in full to a part-year salary (unverified)",
)


class ForecastError(ValueError):
    """A request the forecast refuses, with a reason a user can act on."""


@dataclass(frozen=True)
class Cohort:
    headcount: int
    ctc: float
    city: str
    nps_opted: bool
    join_month: tuple[int, int]
    rent_paid: float | None = None
    work_location: str | None = None
    provision_excluded: float = 0.0
    label: str | None = None


def parse_month(value: str, field: str) -> tuple[int, int]:
    try:
        year_s, month_s = str(value).split("-")
        year, month = int(year_s), int(month_s)
    except (ValueError, AttributeError):
        raise ForecastError(f"{field} must be a month like 2026-10, got {value!r}")
    if not 1 <= month <= 12:
        raise ForecastError(f"{field} must be a month like 2026-10, got {value!r}")
    return (year, month)


def month_str(ym: tuple[int, int]) -> str:
    return f"{ym[0]:04d}-{ym[1]:02d}"


def months_between(first: tuple[int, int], last: tuple[int, int]) -> list[tuple[int, int]]:
    out, (y, m) = [], first
    while (y, m) <= last:
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _in_fy(ym: tuple[int, int]) -> bool:
    return FY_FIRST_MONTH <= ym <= FY_LAST_MONTH


def _scaled(s: SalaryStructure, k: float) -> SalaryStructure:
    return SalaryStructure(
        ctc=s.ctc * k, basic=s.basic * k, hra=s.hra * k, lta=s.lta * k,
        special_allowance=s.special_allowance * k, employer_pf=s.employer_pf * k,
        employer_nps=s.employer_nps * k, nps_opted=s.nps_opted,
    )


def rent_can_matter(cash_ctc: float, city: str, nps_opted: bool) -> bool:
    """
    True when rent can change this cohort's tax (design §4). The HRA exemption
    is capped at the smaller of HRA received and 50% of basic (40% outside
    metros), so rent equal to the CTC always reaches the cap: if the tax at that
    rent equals the tax at rent 0, no rent can change it.
    """
    at_zero = optimize(ctc=cash_ctc, rent_paid=0, city=city, nps_opted=nps_opted)
    at_cap = optimize(ctc=cash_ctc, rent_paid=cash_ctc, city=city, nps_opted=nps_opted)
    return abs(at_zero["recommended"].tax_breakdown["total_tax"]
               - at_cap["recommended"].tax_breakdown["total_tax"]) >= 0.01


def _validate_cohort(raw: dict, index: int) -> Cohort:
    where = f"Hiring group {index + 1}"
    if not isinstance(raw, dict):
        raise ForecastError(f"{where} must be an object")
    try:
        headcount = int(raw["headcount"])
        ctc = float(raw["ctc"])
    except (KeyError, TypeError, ValueError):
        raise ForecastError(f"{where}: headcount and ctc are required and must be numeric")
    if headcount < 1:
        raise ForecastError(f"{where}: headcount must be at least 1")
    if ctc <= 0:
        raise ForecastError(f"{where}: ctc must be positive")
    if ctc > MAX_CTC:
        raise ForecastError(f"{where}: CTC above Rs 4 crore is outside this tool's validated range (surcharge not modelled)")
    city = raw.get("city", "metro")
    if city not in CITY_TIERS:
        raise ForecastError(f"{where}: city must be one of {', '.join(CITY_TIERS)}")
    try:
        provision = float(raw.get("provision_excluded") or 0)
        rent = raw.get("rent_paid")
        rent = None if rent in (None, "") else float(rent)
    except (TypeError, ValueError):
        raise ForecastError(f"{where}: rent_paid and provision_excluded must be numeric")
    if provision < 0 or provision >= ctc:
        raise ForecastError(f"{where}: provision_excluded must be at least 0 and less than the CTC")
    if rent is not None and rent < 0:
        raise ForecastError(f"{where}: rent_paid cannot be negative")
    join = parse_month(raw.get("join_month"), f"{where} join_month")
    if not _in_fy(join):
        raise ForecastError(f"{where}: join_month must fall within {FORECAST_FY_LABEL} (2026-04 to 2027-03)")
    return Cohort(
        headcount=headcount, ctc=ctc, city=city, nps_opted=bool(raw.get("nps_opted", False)),
        join_month=join, rent_paid=rent, work_location=raw.get("work_location") or None,
        provision_excluded=provision, label=raw.get("label") or None,
    )


LINES = ("net_take_home", "tds", "epfo_challan", "nps_remittance", "professional_tax",
         "total", "tds_if_declared", "net_take_home_if_declared")


def _cohort_months(c: Cohort, period: list[tuple[int, int]], index: int) -> dict:
    cash_ctc = c.ctc - c.provision_excluded
    required = rent_can_matter(cash_ctc, c.city, c.nps_opted)
    if required and c.rent_paid is None:
        raise ForecastError(
            f"Hiring group {index + 1}: rent paid is required at this CTC and city, because "
            "it changes the tax. Enter the rent you expect these hires to pay, even as an estimate."
        )
    rent = c.rent_paid if c.rent_paid is not None else 0.0

    rec = optimize(ctc=cash_ctc, rent_paid=rent, city=c.city, nps_opted=c.nps_opted)["recommended"]
    s, regime = rec.structure, rec.regime
    annual_tax = rec.tax_breakdown["total_tax"]

    # Months employed in the financial year, joining month to March inclusive.
    employed = months_between(c.join_month, FY_LAST_MONTH)
    k = len(employed) / 12
    part_year_taxable = max(0.0, taxable_income_for_structure(_scaled(s, k), regime, rent * k, c.city))
    part_year_tax = compute_tax(part_year_taxable, regime)["total_tax"]

    gross_monthly = (s.basic + s.hra + s.lta + s.special_allowance) / 12
    employee_pf = derive_pf(s.basic) / 12
    employer_pf = s.employer_pf / 12
    nps = s.employer_nps / 12
    tds_primary = part_year_tax / len(employed)   # tax on the part-year pay (design §3, B)
    tds_declared = annual_tax / 12                # prorated annual (design §3, A)

    rows, totals = [], {line: 0.0 for line in LINES}
    for ym in period:
        active = c.headcount if ym >= c.join_month else 0
        pt_info = monthly_professional_tax(c.work_location, gross_monthly, month=ym[1])
        pt = pt_info["amount"]
        one = {
            "net_take_home": gross_monthly - employee_pf - tds_primary - pt,
            "tds": tds_primary,
            "epfo_challan": employer_pf + employee_pf,
            "nps_remittance": nps,
            "professional_tax": pt,
            "tds_if_declared": tds_declared,
            "net_take_home_if_declared": gross_monthly - employee_pf - tds_declared - pt,
        }
        one["total"] = (one["net_take_home"] + one["tds"] + one["epfo_challan"]
                        + one["nps_remittance"] + one["professional_tax"])
        scaled = {line: one[line] * active for line in LINES}
        for line in LINES:
            totals[line] += scaled[line]
        rows.append({"month": month_str(ym), "headcount": active,
                     **{line: round(v, 2) for line, v in scaled.items()}})

    return {
        "label": c.label,
        "headcount": c.headcount,
        "ctc_entered": c.ctc,
        "provision_excluded": c.provision_excluded,
        "cash_ctc": cash_ctc,
        "city": c.city,
        "nps_opted": c.nps_opted,
        "join_month": month_str(c.join_month),
        "months_employed_in_fy": len(employed),
        "regime_assumed": regime,
        "rent_used": rent,
        "rent_required": required,
        "rent_assumed_zero": c.rent_paid is None,
        "pt_state_recognized": monthly_professional_tax(c.work_location, gross_monthly)["pt_state_recognized"],
        "months": rows,
        "totals": {line: round(v, 2) for line, v in totals.items()},
        "_raw_totals": totals,
    }


def forecast(payload: dict) -> dict:
    """Compute a forecast from a request body. Raises ForecastError on anything it refuses."""
    if not isinstance(payload, dict):
        raise ForecastError("Request body must be a JSON object")
    period_raw = payload.get("period") or {}
    start = parse_month(period_raw.get("start"), "period.start")
    end = parse_month(period_raw.get("end"), "period.end")
    if end < start:
        raise ForecastError("period.end is before period.start")
    if not (_in_fy(start) and _in_fy(end)):
        raise ForecastError(
            f"The period must fall within {FORECAST_FY_LABEL} (2026-04 to 2027-03). "
            "The engine holds only this year's rates, and next year's are not yet enacted."
        )
    cohorts_raw = payload.get("cohorts")
    if not isinstance(cohorts_raw, list) or not cohorts_raw:
        raise ForecastError("At least one cohort is required")
    if len(cohorts_raw) > 50:
        raise ForecastError("At most 50 cohorts per forecast")

    period = months_between(start, end)
    cohorts = [_validate_cohort(raw, i) for i, raw in enumerate(cohorts_raw)]
    results = [_cohort_months(c, period, i) for i, c in enumerate(cohorts)]

    by_month = []
    for idx, ym in enumerate(period):
        by_month.append({
            "month": month_str(ym),
            **{line: round(sum(r["months"][idx][line] for r in results), 2) for line in LINES},
        })
    grand = {line: round(sum(r["_raw_totals"][line] for r in results), 2) for line in LINES}
    for r in results:
        del r["_raw_totals"]

    return {
        "fy": FORECAST_FY_LABEL,
        "period": {"start": month_str(start), "end": month_str(end)},
        "cohorts": results,
        "months": by_month,
        "totals": grand,
        "notes": {
            "tds_basis": TDS_BASIS_NOTE,
            "ctc_basis": CTC_BASIS_NOTE,
            "rent_assumed_zero": RENT_ASSUMED_ZERO_NOTE,
            "rates": RATES_NOTE,
            "not_modelled": list(NOT_MODELLED),
        },
    }
