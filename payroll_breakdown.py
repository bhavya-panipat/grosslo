"""
payroll_breakdown.py — monthly payroll cash-flow derivation for the
RazorpayX treasury/export flow.

Read-only on tax_engine.py / optimizer.py: every function here takes an
already-computed SalaryStructure and tax_breakdown dict as input and derives
new numbers from them. Nothing here recomputes or overrides a tax figure —
that boundary (the numeric-guard architecture) is the one rule in this
codebase that doesn't get touched.

SCOPE / KNOWN LIMITATIONS (state these explicitly, same as tax_engine.py does):
- monthly_tds_schedule() distributes the annual tax liability evenly across
  12 months. Real Section 392 withholding (Section 192 under the pre-2026
  Income-tax Act 1961; same mechanism, renumbered under the Income-tax Act
  2025 effective 1 April 2026) involves employer discretion and
  quarter-based re-estimation as the year progresses — this models the
  simplified even-distribution case only.
- Employee-side PF is NOT modeled anywhere in tax_engine.py (SalaryStructure
  only tracks employer_pf/employer_nps, both cost-to-company lines). This
  module introduces employee_pf_monthly() as a new, explicit assumption:
  12% of basic, symmetric with tax_engine.py's own derive_pf() convention
  for the employer side. It reuses derive_pf() directly rather than
  re-deriving the 12% constant, so the two figures can't drift apart.
"""

from __future__ import annotations

from tax_engine import SalaryStructure, derive_pf

FUNDING_DEADLINE_HOURS_BEFORE_PAYROLL = 48

# ---------------------------------------------------------------------------
# State-level Professional Tax (PT)
# ---------------------------------------------------------------------------
# Deliberately here, not in tax_engine.py: PT is payroll/statutory overhead
# on the net-disbursement side, not an income-tax liability the optimizer's
# Basic/HRA/PF search should react to -- same reasoning that already keeps
# employee PF (this module's own employee_pf_monthly) and delayed-
# remittance penalty math (penalty_exposure.py) out of the tax engine.
# tax_engine.py and optimizer.py are never touched by this feature.
#
# Five states for realistic hiring-hub coverage. Every slab re-verified
# live on 2026-09-03 against a primary source, not carried over from the
# figures a first draft of this spec proposed -- which had already gone
# stale or wrong in two places, confirmed live rather than assumed correct:
#
# - Karnataka's exemption threshold moved from Rs 15,000 to Rs 25,000 (and
#   the annual cap from Rs 2,400 to Rs 2,500) under the Karnataka Tax on
#   Professions, Trades, Callings and Employments (Amendment) Act, 2025,
#   effective 1 April 2025 -- already in force for the tax year this build
#   runs in. A hardcoded Rs 15,000 threshold would have been wrong from
#   day one, not just eventually.
# - Tamil Nadu's Greater Chennai Corporation slab is a genuine 6-tier
#   half-yearly table -- verified against tnswp.com's own government PDF
#   directly (not an aggregator's paraphrase, which for this specific
#   table gave numbers that didn't match the primary source when checked),
#   not the simpler 2-tier approximation a first draft proposed. Converted
#   to a monthly-equivalent below and flagged as an approximation in the
#   API response either way, since a monthly-equivalent of a half-yearly
#   assessment is inherently a simplification real payroll practice
#   doesn't literally use.
# - Maharashtra's Act also differentiates by gender (women are exempt up
#   to Rs 25,000/month, versus Rs 7,500 for the general slab below) --
#   not modeled, since nothing in this product's intake collects gender.
#   The table below is the general slab, a conservative (higher-PT)
#   estimate for a category this tool doesn't distinguish, stated here
#   rather than silently assumed.
# - Telangana matched the figures originally proposed exactly, confirmed
#   rather than assumed just because the other two states didn't.
#
# Delhi genuinely levies no Professional Tax -- no PT Act has ever been
# enacted for the NCT of Delhi (Article 276 permits, but does not require,
# a state to legislate one). Modeled as an explicit Rs 0 table, the same
# discipline this codebase uses everywhere else for a real, checked zero
# rather than an omitted case -- see pt_state_recognized below for why
# this is NOT the same kind of zero as an unrecognized work_location.

# Karnataka and Maharashtra both cap their annual PT at Rs 2,500 (the
# Article 276 constitutional ceiling) via a one-off Rs 300 February month
# -- 11 months at the base rate + 1 month at Rs 300 lands exactly on
# Rs 2,500. Telangana, Tamil Nadu, and Delhi have no such bump; their own
# flat-rate x12 totals already sit at or under the ceiling.
_FEBRUARY_BUMP_STATES = {"karnataka", "maharashtra"}
_FEBRUARY_BUMP_AMOUNT = 300.0

# {state_key: [(lower_bound, upper_bound_or_None, monthly_pt), ...]}
PT_MONTHLY_TABLE: dict[str, list[tuple[float, float | None, float]]] = {
    "karnataka": [(0, 24_999, 0), (25_000, None, 200)],
    "maharashtra": [(0, 7_500, 0), (7_501, 10_000, 175), (10_001, None, 200)],
    "telangana": [(0, 15_000, 0), (15_001, 20_000, 150), (20_001, None, 200)],
    # Tamil Nadu / Greater Chennai Corporation: real half-yearly slab is
    # Rs 0 / 100 / 235 / 510 / 760 / 1,095 across six average-half-yearly-
    # income bands (verified against tnswp.com's own PDF). Both the income
    # thresholds and the tax amounts are divided by 6 here to express as a
    # monthly-equivalent, so the same gross_monthly-based lookup logic
    # below works unchanged for every state -- this is the one table
    # that's an approximation of a half-yearly assessment, not a literal
    # monthly one, and is flagged as such at the call site.
    "tamil_nadu": [
        (0, 3_500, 0),
        (3_500.01, 5_000, round(100 / 6, 2)),
        (5_000.01, 7_500, round(235 / 6, 2)),
        (7_500.01, 10_000, round(510 / 6, 2)),
        (10_000.01, 12_500, round(760 / 6, 2)),
        (12_500.01, None, round(1_095 / 6, 2)),
    ],
    "delhi": [(0, None, 0)],  # genuinely Rs 0 -- see module docstring above
}


def monthly_professional_tax(work_location: str | None, gross_monthly: float, month: int | None = None) -> dict:
    """
    One month's state Professional Tax for a salaried employee.

    Returns {"amount": float, "pt_state_recognized": bool,
    "is_approximation": bool} -- a dict, not a bare float as an earlier
    draft of this signature specified, so pt_state_recognized travels with
    the amount it actually describes instead of the caller re-deriving it
    from a second, separately-maintained check that could drift out of
    sync with this function's own table.

    pt_state_recognized distinguishes two genuinely different zeros:
    - work_location is None, blank, or not one of the 5 modeled states ->
      amount=0, pt_state_recognized=False. A real "not modeled" gap, not a
      claim about the actual law in that state.
    - work_location == "delhi" -> amount=0, pt_state_recognized=True.
      Delhi genuinely levies no PT; this is a checked, correct zero, not
      an absence of data.

    month (1-12, optional): only changes the result for Karnataka and
    Maharashtra, where a real Rs 300 February month exists. None returns
    the base (non-February) amount -- the right default for a single
    month's quote. See annual_professional_tax() below for the real
    12-month total, which does include the February bump.
    """
    key = (work_location or "").strip().lower().replace(" ", "_")
    table = PT_MONTHLY_TABLE.get(key)
    if table is None:
        return {"amount": 0.0, "pt_state_recognized": False, "is_approximation": False}

    amount = 0.0
    for lower, upper, pt in table:
        if gross_monthly >= lower and (upper is None or gross_monthly <= upper):
            amount = pt
            break

    if month == 2 and key in _FEBRUARY_BUMP_STATES and amount > 0:
        amount = _FEBRUARY_BUMP_AMOUNT

    return {
        "amount": round(amount, 2),
        "pt_state_recognized": True,
        "is_approximation": key == "tamil_nadu",
    }


def annual_professional_tax(work_location: str | None, gross_monthly: float) -> dict:
    """
    The real annual PT total: 11 base months + 1 February month, not a
    naive monthly x 12 -- a flat x12 of Karnataka's/Maharashtra's Rs 200
    gives Rs 2,400, not the real Rs 2,500 the February bump produces, an
    error worth exactly the gap this whole feature exists to close.
    This is what treasury_forecast() below actually integrates, since it
    reports annual figures throughout.
    """
    base = monthly_professional_tax(work_location, gross_monthly, month=1)
    february = monthly_professional_tax(work_location, gross_monthly, month=2)
    return {
        "amount": round(base["amount"] * 11 + february["amount"], 2),
        "pt_state_recognized": base["pt_state_recognized"],
        "is_approximation": base["is_approximation"],
    }


def monthly_tds_schedule(tax_breakdown: dict) -> list[float]:
    """12 equal installments of the annual total_tax."""
    monthly = round(tax_breakdown["total_tax"] / 12, 2)
    return [monthly] * 12


def employee_pf_monthly(basic_annual: float) -> float:
    """Employee PF deduction — 12% of basic, monthly. See module docstring."""
    return round(derive_pf(basic_annual) / 12, 2)


def net_monthly_disbursement(structure: SalaryStructure, tax_breakdown: dict) -> float:
    """
    Net cash hitting the employee's bank account per month.
    Only the cash components of the structure (basic/HRA/LTA/special
    allowance) are payslip cash — employer_pf/employer_nps are
    cost-to-company retiral contributions, not cash to the employee.
    """
    monthly_cash = (structure.basic + structure.hra + structure.lta
                     + structure.special_allowance) / 12
    monthly_tds = tax_breakdown["total_tax"] / 12
    return round(monthly_cash - employee_pf_monthly(structure.basic) - monthly_tds, 2)


def treasury_forecast(structure: SalaryStructure, tax_breakdown: dict, work_location: str | None = None) -> dict:
    """
    Annual capital-outlay forecast for a single employee's structure —
    what the company needs to have funded before payroll runs.
    total_capital_outlay is defined as the sum of net_take_home_annual,
    tds_escrow_annual, epfo_challan_annual, AND professional_tax_annual;
    verification should confirm that identity holds, not just that a number
    is displayed.

    work_location is optional and additive: PT doesn't change the total
    cash the company needs (that pool was already fixed by basic + hra +
    lta + special_allowance), it just splits it a fourth way — net take-
    home goes down by the PT amount, and that amount is now remitted to
    the state instead of reaching the employee's bank account, the same
    relationship employee PF already has to net_take_home_annual. Omitting
    work_location (None) reproduces this function's exact pre-PT behavior
    — every existing caller that doesn't pass it stays byte-for-byte
    unaffected, which is what let this ship without touching tax_engine.py
    or optimizer.py at all.
    """
    gross_monthly = (structure.basic + structure.hra + structure.lta + structure.special_allowance) / 12
    pt = annual_professional_tax(work_location, gross_monthly)
    professional_tax_annual = pt["amount"]

    net_take_home_annual = round(
        (structure.basic + structure.hra + structure.lta + structure.special_allowance)
        - derive_pf(structure.basic)
        - tax_breakdown["total_tax"]
        - professional_tax_annual,
        2,
    )
    tds_escrow_annual = round(tax_breakdown["total_tax"], 2)
    epfo_challan_annual = round(structure.employer_pf + derive_pf(structure.basic), 2)
    total_capital_outlay = round(
        net_take_home_annual + tds_escrow_annual + epfo_challan_annual + professional_tax_annual, 2
    )
    return {
        "net_take_home_annual": net_take_home_annual,
        "tds_escrow_annual": tds_escrow_annual,
        "epfo_challan_annual": epfo_challan_annual,
        "professional_tax_annual": professional_tax_annual,
        "pt_state_recognized": pt["pt_state_recognized"],
        "pt_is_approximation": pt["is_approximation"],
        "total_capital_outlay": total_capital_outlay,
        "funding_deadline_hours_before_payroll": FUNDING_DEADLINE_HOURS_BEFORE_PAYROLL,
    }
