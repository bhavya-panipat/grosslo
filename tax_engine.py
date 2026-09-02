"""
FinOS Tax Engine — FY 2025-26 / FY 2026-27 (AY 2026-27 / AY 2027-28)

SCOPE / KNOWN LIMITATIONS (state these explicitly in any demo/docs):
- Surcharge (applicable above Rs 50L taxable income) is NOT modeled.
  Tool is scoped for salaried CTC ranges typical of early-to-mid career hires.
- Assumes salaried individual, resident, below 60 years of age.
- Does not model capital gains, other-source income, or non-salary deductions
  beyond what's listed below.
- Basic salary floor is a market-convention assumption (40% of CTC), NOT a
  statutory requirement. Configurable.

Sources checked live on 2026-08-24 (see chat for citations):
- New regime slabs unchanged from FY25-26 into FY26-27 (Budget 2026 made no changes)
- New regime: nil up to 4L, 5/10/15/20/25/30% in 4L bands up to 24L
- New regime standard deduction: Rs 75,000
- New regime Section 156 (formerly 87A) rebate: taxable income up to Rs
  12,00,000 -> zero tax (with marginal relief above)
- Old regime: nil up to 2.5L, then 5% (2.5-5L), 20% (5-10L), 30% (>10L)
- Old regime standard deduction: Rs 50,000
- Old regime Section 156 (formerly 87A) rebate: taxable income up to Rs
  5,00,000 -> zero tax
- Section 124 (formerly 80CCD(2)) employer NPS cap: 10% of basic (old regime),
  14% of basic (new regime)
- Cess: 4% flat on (tax - rebate + surcharge) in both regimes, surcharge = 0 here

Citation sweep re-verified live 2026-09-02 against the Income Tax Act 2025
(in force 1 April 2026, current for this tax year): Section 87A -> Section
156, Section 80CCD(2) -> Section 124, Section 201(1A) -> Section 398(3),
Section 271C -> Section 448. Section 17(2)(vii) (the >Rs 7.5L PF+NPS
perquisite rule referenced in ai_layer.py/compliance_rules.md) was checked
and confirmed retained at its original number in the new Act — not every
section moved. Internal Python names below (REBATE_87A_THRESHOLD,
NPS_80CCD2_CAP_PCT, etc.) keep their old-Act-numbered names deliberately,
same precedent as NPS_80CCD2_CAP_PCT elsewhere in this codebase — renaming
constants is a bigger diff for zero behavioral gain; only citation TEXT
shown to a user or judge needed the sweep.
"""

from dataclasses import dataclass, field
from typing import Literal

Regime = Literal["old", "new"]
CityTier = Literal["metro", "non_metro"]


# ---------------------------------------------------------------------------
# Slab definitions
# ---------------------------------------------------------------------------

NEW_REGIME_SLABS = [
    (400_000, 0.00),
    (800_000, 0.05),
    (1_200_000, 0.10),
    (1_600_000, 0.15),
    (2_000_000, 0.20),
    (2_400_000, 0.25),
    (float("inf"), 0.30),
]

OLD_REGIME_SLABS = [
    (250_000, 0.00),
    (500_000, 0.05),
    (1_000_000, 0.20),
    (float("inf"), 0.30),
]

STANDARD_DEDUCTION = {"new": 75_000, "old": 50_000}
REBATE_87A_THRESHOLD = {"new": 1_200_000, "old": 500_000}
REBATE_87A_MAX = {"new": 60_000, "old": 12_500}
NPS_80CCD2_CAP_PCT = {"new": 0.14, "old": 0.10}
CESS_RATE = 0.04

LTA_ASSUMED_UTILIZATION_PCT_DEFAULT = 0.70
# ASSUMPTION, not statutory: LTA exemption in reality requires (a) actual travel
# undertaken, (b) valid bills, (c) is capped at economy airfare for the shortest
# route to the destination, and (d) can only be claimed twice in a rolling
# 4-year block (currently 2022-25 block, next block 2026-29). A salary
# structuring tool CANNOT know in advance whether an employee will travel or
# keep bills. Defaulting to 70% assumed utilization is a conservative
# approximation, not a guarantee — flag this explicitly in any tool output
# and let the user override it.

EMPLOYER_PF_RATE = 0.12
PF_WAGE_CEILING_BASIC = 15_000  # monthly; statutory mandatory PF base ceiling


def _slab_tax(taxable_income: float, slabs: list[tuple[float, float]]) -> float:
    """Progressive slab tax, no rebate/cess applied."""
    tax = 0.0
    lower = 0.0
    for upper, rate in slabs:
        if taxable_income <= lower:
            break
        band = min(taxable_income, upper) - lower
        tax += band * rate
        lower = upper
    return tax


def _apply_87a_rebate(slab_tax: float, taxable_income: float, regime: Regime) -> float:
    """Apply Section 156 (formerly Section 87A) rebate. Returns tax after rebate (before cess)."""
    threshold = REBATE_87A_THRESHOLD[regime]
    max_rebate = REBATE_87A_MAX[regime]
    if taxable_income <= threshold:
        rebate = min(slab_tax, max_rebate)
        return slab_tax - rebate
    return slab_tax


def _apply_marginal_relief(tax_after_rebate: float, taxable_income: float, regime: Regime) -> float:
    """
    Marginal relief: tax payable on income just above the rebate threshold
    should not exceed (income - threshold) + tax that would've applied at threshold.
    In practice for Section 156 (formerly 87A): if income is slightly above threshold, tax payable is
    capped at (taxable_income - threshold), so post-threshold earners aren't
    worse off than someone right at the threshold (who pays ~0 due to rebate).
    """
    threshold = REBATE_87A_THRESHOLD[regime]
    if taxable_income <= threshold:
        return tax_after_rebate  # already 0 via rebate
    excess = taxable_income - threshold
    if tax_after_rebate > excess:
        return excess
    return tax_after_rebate


def compute_tax(taxable_income: float, regime: Regime) -> dict:
    """Full tax computation: slab tax -> Section 156 (formerly 87A) rebate -> marginal relief -> cess."""
    slabs = NEW_REGIME_SLABS if regime == "new" else OLD_REGIME_SLABS
    raw_slab_tax = _slab_tax(taxable_income, slabs)
    after_rebate = _apply_87a_rebate(raw_slab_tax, taxable_income, regime)
    after_relief = _apply_marginal_relief(after_rebate, taxable_income, regime)
    cess = after_relief * CESS_RATE
    total_tax = after_relief + cess

    return {
        "taxable_income": round(taxable_income, 2),
        "slab_tax": round(raw_slab_tax, 2),
        "tax_after_rebate": round(after_rebate, 2),
        "tax_after_marginal_relief": round(after_relief, 2),
        "cess": round(cess, 2),
        "total_tax": round(total_tax, 2),
    }


# ---------------------------------------------------------------------------
# HRA exemption (old regime only)
# ---------------------------------------------------------------------------

def hra_exemption(basic: float, hra_paid: float, rent_paid: float, city: CityTier) -> float:
    """
    HRA exemption = min(
        actual HRA received,
        rent paid - 10% of basic,
        50% of basic (metro) or 40% of basic (non-metro)
    )
    Only valid for old regime. Assumes annual figures.
    """
    if rent_paid <= 0 or hra_paid <= 0:
        return 0.0
    city_pct = 0.50 if city == "metro" else 0.40
    option_a = hra_paid
    option_b = max(0.0, rent_paid - 0.10 * basic)
    option_c = city_pct * basic
    return max(0.0, min(option_a, option_b, option_c))


# ---------------------------------------------------------------------------
# CTC component structuring
# ---------------------------------------------------------------------------

@dataclass
class SalaryStructure:
    ctc: float
    basic: float
    hra: float
    lta: float
    special_allowance: float
    employer_pf: float
    employer_nps: float
    nps_opted: bool

    def total(self) -> float:
        return (self.basic + self.hra + self.lta + self.special_allowance
                + self.employer_pf + self.employer_nps)


def derive_pf(basic_annual: float, voluntary_full_basic: bool = True) -> float:
    """
    Employer PF = 12% of basic.
    Statutory mandatory base is capped at Rs 15,000/month basic ceiling,
    but most private employers (and this tool, by default) apply 12% on
    actual basic ('voluntary' higher PF) rather than restricting to the
    statutory minimum wage ceiling. Toggle if you need the strict statutory
    minimum instead.
    """
    if voluntary_full_basic:
        return round(EMPLOYER_PF_RATE * basic_annual, 2)
    monthly_basic_capped = min(basic_annual / 12, PF_WAGE_CEILING_BASIC)
    return round(EMPLOYER_PF_RATE * monthly_basic_capped * 12, 2)


def derive_nps(basic_annual: float, regime: Regime, opted_in: bool) -> float:
    if not opted_in:
        return 0.0
    return round(NPS_80CCD2_CAP_PCT[regime] * basic_annual, 2)


def build_structure(ctc: float, basic_pct: float, hra_pct_of_remaining: float,
                     lta: float, regime: Regime, nps_opted: bool,
                     pf_voluntary_full_basic: bool = True) -> SalaryStructure:
    """
    Build a structure given basic as % of CTC, then split the remainder
    (after basic, PF, NPS) between HRA and special allowance, with LTA fixed.

    hra_pct_of_remaining: fraction of (CTC - basic - PF - NPS - LTA) routed to HRA;
                           rest goes to special allowance.
    """
    basic = basic_pct * ctc
    pf = derive_pf(basic, pf_voluntary_full_basic)
    nps = derive_nps(basic, regime, nps_opted)
    remaining = ctc - basic - pf - nps - lta
    if remaining < 0:
        raise ValueError("CTC too low for given basic%, PF, NPS, and LTA combination")
    hra = hra_pct_of_remaining * remaining
    special_allowance = remaining - hra
    return SalaryStructure(
        ctc=ctc, basic=basic, hra=hra, lta=lta,
        special_allowance=special_allowance,
        employer_pf=pf, employer_nps=nps, nps_opted=nps_opted,
    )


def taxable_income_for_structure(structure: SalaryStructure, regime: Regime,
                                  rent_paid: float, city: CityTier) -> float:
    """
    Gross salary income (excluding employer PF, which is not part of taxable
    salary; employer NPS beyond the Section 124 (formerly 80CCD(2)) cap would
    be taxable but we assume contribution == cap, so fully exempt) minus
    applicable exemptions/deductions.
    """
    gross_salary = structure.basic + structure.hra + structure.lta + structure.special_allowance
    # employer NPS under Section 124 (formerly 80CCD(2)) is deductible from gross total income (both regimes)
    # LTA exemption (old regime only) is capped to a conservative assumed
    # utilization fraction — see LTA_ASSUMED_UTILIZATION_PCT_DEFAULT above.
    std_deduction = STANDARD_DEDUCTION[regime]

    if regime == "old":
        hra_exempt = hra_exemption(structure.basic, structure.hra, rent_paid, city)
        lta_exempt = structure.lta * LTA_ASSUMED_UTILIZATION_PCT_DEFAULT
        taxable = (gross_salary - hra_exempt - lta_exempt - std_deduction
                   - structure.employer_nps)
    else:
        # new regime: no HRA/LTA exemption at all
        taxable = gross_salary - std_deduction - structure.employer_nps

    return max(0.0, taxable)
