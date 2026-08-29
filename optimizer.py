"""
FinOS Optimizer — exhaustive grid search over feasible salary structures.

DESIGN DECISIONS (flag these in docs/demo, they are assumptions not statute):
- Basic salary is constrained to [40%, 50%] of CTC. Floor = market convention
  (keeps PF/gratuity/increment math sane). Ceiling = added because an
  unconstrained tax-minimizing search pushes basic upward indefinitely —
  employer PF isn't taxable to the employee and 80CCD(2) NPS deduction scales
  with basic, so more basic mathematically shelters more of the CTC. A
  company would never structure basic at, say, 90% of CTC. The ceiling keeps
  the output realistic, at the cost of not being the true unconstrained
  mathematical optimum. This tradeoff should be stated explicitly if asked.
- New regime: HRA and LTA receive NO exemption at all, so they're taxed
  identically to special allowance. The optimizer therefore does NOT search
  their split under new regime — only basic_pct matters. This is a provable
  simplification (not a shortcut): the tax outcome is mathematically
  invariant to how the non-basic cash component is labeled once you're in
  the new regime.
- Old regime: full grid search over (basic_pct, LTA, HRA-vs-special-allowance
  split), since HRA and LTA both carry old-regime exemptions with different
  formulas.
"""

from __future__ import annotations
from dataclasses import dataclass
from tax_engine import (
    build_structure, taxable_income_for_structure, compute_tax,
    derive_pf, derive_nps, SalaryStructure, Regime, CityTier,
)

BASIC_PCT_MIN = 0.40   # confirmed floor
BASIC_PCT_MAX = 0.50   # ASSUMPTION: added ceiling, see module docstring
BASIC_PCT_STEP = 0.025  # -> 5 points: 40, 42.5, 45, 47.5, 50

HRA_FRACTION_STEP = 0.05   # of "remaining after basic/PF/NPS/LTA" routed to HRA
LTA_MAX_PCT_OF_CTC = 0.10  # ASSUMPTION: realistic company LTA policy ceiling
LTA_STEP_PCT_OF_CTC = 0.02


def evaluate_given_structure(structure: SalaryStructure, regime: Regime,
                              rent_paid: float, city: CityTier) -> dict:
    """
    Evaluate ONE specific, already-known structure (not a search) under a
    given regime. Used to score an offer letter's actual as-extracted split,
    as opposed to optimize_old_regime/optimize_new_regime which search for
    the best split. Returns the same tax_breakdown shape as OptimizationResult.
    """
    taxable = taxable_income_for_structure(structure, regime, rent_paid, city)
    return compute_tax(taxable, regime)


def best_regime_for_given_structure(structure: SalaryStructure, rent_paid: float,
                                     city: CityTier) -> dict:
    """
    Evaluate a fixed structure under both regimes and return whichever is
    lower — the fair "if you keep this exact structure as-is" baseline to
    compare against the optimizer's recommendation.
    """
    old_tax = evaluate_given_structure(structure, "old", rent_paid, city)
    new_tax = evaluate_given_structure(structure, "new", rent_paid, city)
    if old_tax["total_tax"] <= new_tax["total_tax"]:
        return {"regime": "old", "tax_breakdown": old_tax}
    return {"regime": "new", "tax_breakdown": new_tax}



def sensitivity_sweep(rent_paid: float, city: CityTier, nps_opted: bool,
                       ctc_min: float = 400_000, ctc_max: float = 6_000_000,
                       steps: int = 29) -> list[dict]:
    """
    Sweep CTC across a range, holding rent/city/NPS-choice constant, and
    report which regime wins at each point. Reuses optimize() exactly as-is
    — no new tax logic, just repeated calls to the already-validated
    optimizer. This is what surfaces the old-vs-new regime crossover point
    as a visual, rather than a single static answer.

    NOTE: rent_paid is held FIXED across the whole sweep (whatever the user
    entered), not scaled proportionally to CTC. This is a deliberate,
    honestly-scoped choice — the sweep answers "holding your actual rent
    constant, how does the regime recommendation change with CTC," not "how
    would a proportionally-scaled rent change things." State this in the UI.
    """
    step_size = (ctc_max - ctc_min) / (steps - 1) if steps > 1 else 0
    points = []
    for i in range(steps):
        ctc = round(ctc_min + i * step_size, -3)  # round to nearest 1000
        result = optimize(ctc=ctc, rent_paid=rent_paid, city=city, nps_opted=nps_opted)
        points.append({
            "ctc": ctc,
            "old_tax": result["old_regime_best"].tax_breakdown["total_tax"],
            "new_tax": result["new_regime_best"].tax_breakdown["total_tax"],
            "recommended_regime": result["recommended"].regime,
        })
    return points


@dataclass
class OptimizationResult:
    regime: Regime
    structure: SalaryStructure
    taxable_income: float
    tax_breakdown: dict
    basic_pct: float
    hra_fraction: float | None
    lta: float


def _basic_pct_range():
    vals = []
    v = BASIC_PCT_MIN
    while v <= BASIC_PCT_MAX + 1e-9:
        vals.append(round(v, 4))
        v += BASIC_PCT_STEP
    return vals


def optimize_new_regime(ctc: float, nps_opted: bool) -> OptimizationResult:
    """
    New regime: HRA/LTA/special-allowance are tax-identical, so we don't
    search their split. Only basic_pct affects tax (via PF/NPS deduction).
    We still need a concrete structure to display, so once basic_pct is
    chosen, remaining CTC (after basic/PF/NPS) is put entirely into
    special allowance for the canonical structure (equivalent tax outcome
    to any other split).
    """
    best = None
    for basic_pct in _basic_pct_range():
        structure = build_structure(
            ctc=ctc, basic_pct=basic_pct, hra_pct_of_remaining=0.0,
            lta=0.0, regime="new", nps_opted=nps_opted,
        )
        taxable = taxable_income_for_structure(structure, "new", rent_paid=0, city="metro")
        tax = compute_tax(taxable, "new")
        if best is None or tax["total_tax"] < best.tax_breakdown["total_tax"]:
            best = OptimizationResult(
                regime="new", structure=structure, taxable_income=taxable,
                tax_breakdown=tax, basic_pct=basic_pct, hra_fraction=None, lta=0.0,
            )
    return best


def optimize_old_regime(ctc: float, rent_paid: float, city: CityTier,
                         nps_opted: bool) -> OptimizationResult:
    best = None
    lta_max = LTA_MAX_PCT_OF_CTC * ctc
    lta_values = []
    v = 0.0
    while v <= lta_max + 1e-6:
        lta_values.append(round(v, 2))
        v += LTA_STEP_PCT_OF_CTC * ctc

    for basic_pct in _basic_pct_range():
        for lta in lta_values:
            hra_frac = 0.0
            while hra_frac <= 1.0 + 1e-9:
                try:
                    structure = build_structure(
                        ctc=ctc, basic_pct=basic_pct, hra_pct_of_remaining=hra_frac,
                        lta=lta, regime="old", nps_opted=nps_opted,
                    )
                except ValueError:
                    hra_frac += HRA_FRACTION_STEP
                    continue
                taxable = taxable_income_for_structure(structure, "old", rent_paid, city)
                tax = compute_tax(taxable, "old")
                if best is None or tax["total_tax"] < best.tax_breakdown["total_tax"]:
                    best = OptimizationResult(
                        regime="old", structure=structure, taxable_income=taxable,
                        tax_breakdown=tax, basic_pct=basic_pct,
                        hra_fraction=round(hra_frac, 4), lta=lta,
                    )
                hra_frac += HRA_FRACTION_STEP
    return best


def optimize(ctc: float, rent_paid: float, city: CityTier, nps_opted: bool) -> dict:
    """
    Full optimization: best structure under old regime, best under new
    regime, and the winner. Returns all three for the '3 scenarios + delta'
    output format.
    """
    old_best = optimize_old_regime(ctc, rent_paid, city, nps_opted)
    new_best = optimize_new_regime(ctc, nps_opted)

    if old_best.tax_breakdown["total_tax"] <= new_best.tax_breakdown["total_tax"]:
        winner, loser = old_best, new_best
    else:
        winner, loser = new_best, old_best

    delta = loser.tax_breakdown["total_tax"] - winner.tax_breakdown["total_tax"]

    return {
        "ctc": ctc,
        "old_regime_best": old_best,
        "new_regime_best": new_best,
        "recommended": winner,
        "annual_tax_saving_vs_other_regime": round(delta, 2),
    }
