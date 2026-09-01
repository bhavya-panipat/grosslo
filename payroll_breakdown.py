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

from tax_engine import SalaryStructure, derive_pf

FUNDING_DEADLINE_HOURS_BEFORE_PAYROLL = 48


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


def treasury_forecast(structure: SalaryStructure, tax_breakdown: dict) -> dict:
    """
    Annual capital-outlay forecast for a single employee's structure —
    what the company needs to have funded before payroll runs.
    total_capital_outlay is defined as the sum of the other three figures;
    verification should confirm that identity holds, not just that a number
    is displayed.
    """
    net_take_home_annual = round(
        (structure.basic + structure.hra + structure.lta + structure.special_allowance)
        - derive_pf(structure.basic)
        - tax_breakdown["total_tax"],
        2,
    )
    tds_escrow_annual = round(tax_breakdown["total_tax"], 2)
    epfo_challan_annual = round(structure.employer_pf + derive_pf(structure.basic), 2)
    total_capital_outlay = round(
        net_take_home_annual + tds_escrow_annual + epfo_challan_annual, 2
    )
    return {
        "net_take_home_annual": net_take_home_annual,
        "tds_escrow_annual": tds_escrow_annual,
        "epfo_challan_annual": epfo_challan_annual,
        "total_capital_outlay": total_capital_outlay,
        "funding_deadline_hours_before_payroll": FUNDING_DEADLINE_HOURS_BEFORE_PAYROLL,
    }
