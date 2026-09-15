"""
Employer NPS in taxable income, pinned to the statute rather than to the engine.
TAX_ENGINE_EMPLOYER_NPS_DESIGN.md §5 step 1 and §8.5.

Income-tax Act, 2025: s. 16(k) makes the employer's contribution part of
salary; s. 124(1)-(2) deducts it up to a cap (here, as the engine models it,
10% of basic in the old regime and 14% in the new). So within the cap the two
cancel, and above it the excess stays taxable.

Every expected value below is derived in this file from that rule, by
arithmetic, not read back from taxable_income_for_structure(). A test that asked
the engine what the answer is could not catch the engine being wrong, which is
how the double count survived: the old tests pinned what the code did.

These were committed failing, before the fix, so the failure is on record.
The routing and recommendation cases at the bottom are named cases from the
§8.7 sweep; their expected values were measured on an in-memory prototype of
the fix, and each one is the fixed engine disagreeing with the current one.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tax_engine import (
    SalaryStructure, compute_tax, hra_exemption, taxable_income_for_structure,
    NPS_80CCD2_CAP_PCT, STANDARD_DEDUCTION, LTA_ASSUMED_UTILIZATION_PCT_DEFAULT, derive_pf,
)
from optimizer import optimize
from payroll_breakdown import treasury_forecast
from ai_layer import evaluate_band_guardrail, flag_compliance
from orchestration import classify_row

RENT, CITY = 240_000, "metro"


def _structure(employer_nps=0.0, special_allowance=500_000.0):
    return SalaryStructure(
        ctc=0.0,  # not read by the taxable-income computation
        basic=1_000_000.0, hra=400_000.0, lta=50_000.0,
        special_allowance=special_allowance,
        employer_pf=120_000.0, employer_nps=employer_nps, nps_opted=employer_nps > 0,
    )


def _statute_taxable(s, regime):
    """s. 16(k): the contribution is salary. s. 124: deduct it, up to the cap."""
    salary = s.basic + s.hra + s.lta + s.special_allowance + s.employer_nps
    deduction = min(s.employer_nps, NPS_80CCD2_CAP_PCT[regime] * s.basic)
    exemptions = 0.0
    if regime == "old":
        exemptions = hra_exemption(s.basic, s.hra, RENT, CITY) + s.lta * LTA_ASSUMED_UTILIZATION_PCT_DEFAULT
    return salary - exemptions - STANDARD_DEDUCTION[regime] - deduction


class TestTaxableIncomeFollowsTheStatute(unittest.TestCase):

    def _taxable(self, s, regime):
        return taxable_income_for_structure(s, regime, RENT, CITY)

    def test_a_contribution_within_the_cap_adds_nothing_to_taxable_income(self):
        # Same salary, plus a contribution on top: salary rises by X, the
        # deduction removes X. Net zero. The double count gives minus X.
        for regime in ("old", "new"):
            with self.subTest(regime=regime):
                x = 0.5 * NPS_80CCD2_CAP_PCT[regime] * 1_000_000
                self.assertAlmostEqual(
                    self._taxable(_structure(employer_nps=x), regime),
                    self._taxable(_structure(), regime), delta=0.01)

    def test_moving_x_into_nps_within_the_cap_lowers_taxable_income_by_exactly_x(self):
        for regime in ("old", "new"):
            cap = NPS_80CCD2_CAP_PCT[regime] * 1_000_000
            for x in (0.5 * cap, cap):
                with self.subTest(regime=regime, x=x):
                    before = self._taxable(_structure(), regime)
                    after = self._taxable(_structure(employer_nps=x, special_allowance=500_000 - x), regime)
                    self.assertAlmostEqual(before - after, x, delta=0.01)

    def test_moving_x_into_nps_above_the_cap_lowers_taxable_income_by_exactly_the_cap(self):
        for regime in ("old", "new"):
            cap = NPS_80CCD2_CAP_PCT[regime] * 1_000_000
            x = cap + 50_000
            with self.subTest(regime=regime):
                before = self._taxable(_structure(), regime)
                after = self._taxable(_structure(employer_nps=x, special_allowance=500_000 - x), regime)
                self.assertAlmostEqual(before - after, cap, delta=0.01)

    def test_taxable_income_equals_the_statutes_on_either_side_of_the_cap(self):
        for regime in ("old", "new"):
            cap = NPS_80CCD2_CAP_PCT[regime] * 1_000_000
            for nps in (0.0, 0.5 * cap, cap, cap + 50_000):
                with self.subTest(regime=regime, nps=nps):
                    s = _structure(employer_nps=nps)
                    self.assertAlmostEqual(self._taxable(s, regime), _statute_taxable(s, regime), delta=0.01)


class TestTheTreasurySplitFollowsTheCorrectedTax(unittest.TestCase):
    """
    The owner's blast-radius question (§8.1). The total cannot move; the TDS it
    contains and the take-home beside it must follow the corrected tax.
    """

    def _forecast(self, s, regime):
        tax = compute_tax(taxable_income_for_structure(s, regime, RENT, CITY), regime)
        return treasury_forecast(s, tax)

    def test_tds_escrow_is_the_tax_on_the_statutes_taxable_income(self):
        s = _structure(employer_nps=140_000.0)
        expected_tax = compute_tax(_statute_taxable(s, "new"), "new")["total_tax"]
        forecast = self._forecast(s, "new")
        self.assertAlmostEqual(forecast["tds_escrow_annual"], expected_tax, delta=0.01)
        cash = s.basic + s.hra + s.lta + s.special_allowance
        self.assertAlmostEqual(forecast["net_take_home_annual"],
                               cash - derive_pf(s.basic) - expected_tax, delta=0.01)

    def test_the_total_outlay_does_not_depend_on_tax_at_all(self):
        # The invariant, and the one assertion here that passes before the fix
        # as well as after: cash + employer PF, whatever the tax is.
        for nps in (0.0, 140_000.0, 250_000.0):
            with self.subTest(nps=nps):
                s = _structure(employer_nps=nps)
                cash = s.basic + s.hra + s.lta + s.special_allowance
                self.assertAlmostEqual(self._forecast(s, "new")["total_capital_outlay"],
                                       cash + s.employer_pf, delta=0.01)


class TestNamedCasesWhereTheFixChangesTheAdvice(unittest.TestCase):
    """
    §8.7: the error reaches the recommendation and, through the regime, routing.
    Measured over 1,140 submissions and 8,424 batch rows, every route change
    went escalate -> auto_pass_candidate, never the other way. These pin one
    named case of each mechanism. They mirror /api/submissions: optimize(),
    then the guardrail on the recommended structure and regime.
    """

    def _submission(self, ctc, rent):
        rec = optimize(ctc=ctc, rent_paid=rent, city="metro", nps_opted=True)["recommended"]
        guardrail = evaluate_band_guardrail(rec.structure, rec.regime, 0.8 * ctc, 1.2 * ctc)
        route = classify_row(flag_compliance(rec.structure, rent, skip_ai=True), guardrail)["route"]
        return rec, route

    def test_49L_with_high_rent_recommends_the_old_regime_and_stays_under_the_epfo_ceiling(self):
        # Under the double count, the new regime with 14% NPS looked cheapest;
        # its PF + NPS crossed the Rs 7.5L ceiling and the row escalated.
        rec, route = self._submission(4_900_000, 900_000)
        self.assertEqual(rec.regime, "old")
        self.assertAlmostEqual(rec.structure.employer_nps, 0.10 * rec.structure.basic, delta=0.01)
        self.assertEqual(route, "auto_pass_candidate")

    def test_15L_recommends_a_different_basic(self):
        # Measured: 50% basic under the double count, 60% after.
        rec, _ = self._submission(1_500_000, 0)
        self.assertEqual(rec.regime, "new")
        self.assertEqual(rec.structure.basic, 900_000)


if __name__ == "__main__":
    unittest.main()
