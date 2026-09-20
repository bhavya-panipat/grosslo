"""
The treasury forecast must fund the whole of CTC.
TREASURY_NPS_OUTLAY_DESIGN.md §5, committed failing before the fix.

The employer's NPS contribution is inside CTC by this tool's own definition
(SalaryStructure.total()), and is remitted by the employer like the EPFO
challan. Until this fix it appeared in no component of total_capital_outlay,
so the figure the Finance queue sums against the live bank balance was short
by that contribution — 5.0% at ₹6L CTC, 8.4% from ₹18L up.

Every expected value here is derived from the structure, never copied from a
run: `total() == total_capital_outlay` is arithmetic about what CTC means, and
a test that asserted a remembered number could not tell the two apart.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from optimizer import optimize
from payroll_breakdown import treasury_forecast
from tax_engine import SalaryStructure, compute_tax, derive_pf, taxable_income_for_structure

CTCS = (600_000, 1_200_000, 1_800_000, 3_600_000, 5_000_000)
RENT, CITY, LOCATION = 240_000, "metro", "karnataka"


def _forecast(ctc, nps_opted, work_location=LOCATION):
    """Returns (structure, tax_breakdown, forecast) — the tax comes back too, so
    a test checks the forecast against the very figure it was given, not against
    a tax recomputed by a slightly different route."""
    recommended = optimize(ctc=ctc, rent_paid=RENT, city=CITY, nps_opted=nps_opted)["recommended"]
    return (recommended.structure, recommended.tax_breakdown,
            treasury_forecast(recommended.structure, recommended.tax_breakdown,
                              work_location=work_location))


class TestTheForecastFundsTheWholeCtc(unittest.TestCase):

    def test_the_total_outlay_is_the_ctc_the_structure_describes(self):
        # The whole argument, as one identity: everything the company pays for
        # this employee is what the company committed to pay.
        for ctc in CTCS:
            for nps_opted in (True, False):
                with self.subTest(ctc=ctc, nps_opted=nps_opted):
                    structure, _tax, forecast = _forecast(ctc, nps_opted)
                    self.assertAlmostEqual(forecast["total_capital_outlay"], structure.total(), delta=1.0)

    def test_the_five_components_reconstruct_the_total(self):
        for ctc in CTCS:
            with self.subTest(ctc=ctc):
                _structure, _tax, forecast = _forecast(ctc, nps_opted=True)
                self.assertAlmostEqual(
                    forecast["total_capital_outlay"],
                    forecast["net_take_home_annual"] + forecast["tds_escrow_annual"]
                    + forecast["epfo_challan_annual"] + forecast["professional_tax_annual"]
                    + forecast["nps_remittance_annual"], delta=0.05)

    def test_the_nps_remittance_is_the_employers_contribution(self):
        for ctc in CTCS:
            with self.subTest(ctc=ctc):
                structure, _tax, forecast = _forecast(ctc, nps_opted=True)
                self.assertGreater(structure.employer_nps, 0, "precondition: this structure has NPS")
                self.assertAlmostEqual(forecast["nps_remittance_annual"], structure.employer_nps, delta=0.01)

    def test_a_structure_without_nps_reports_zero_rather_than_omitting_the_field(self):
        # Absent and zero are different things to a consumer: absent means the
        # response predates the field, zero means there is nothing to remit.
        structure, _tax, forecast = _forecast(1_800_000, nps_opted=False)
        self.assertEqual(structure.employer_nps, 0.0)
        self.assertIn("nps_remittance_annual", forecast)
        self.assertEqual(forecast["nps_remittance_annual"], 0.0)

    def test_adding_a_contribution_raises_the_total_by_exactly_that_amount(self):
        # Unlike professional tax, which re-split a fixed pool, this is money
        # the total did not previously contain.
        base = SalaryStructure(
            ctc=2_000_000, basic=1_000_000, hra=400_000, lta=50_000,
            special_allowance=430_000, employer_pf=120_000, employer_nps=0.0, nps_opted=False)
        with_nps = SalaryStructure(
            ctc=2_000_000, basic=1_000_000, hra=400_000, lta=50_000,
            special_allowance=430_000, employer_pf=120_000, employer_nps=140_000.0, nps_opted=True)
        totals = []
        for structure in (base, with_nps):
            tax = compute_tax(taxable_income_for_structure(structure, "new", RENT, CITY), "new")
            totals.append(treasury_forecast(structure, tax, work_location=LOCATION)["total_capital_outlay"])
        self.assertAlmostEqual(totals[1] - totals[0], with_nps.employer_nps, delta=0.01)

    def test_the_other_four_components_keep_their_own_definitions(self):
        # The fix adds a term; it must not quietly redistribute the others.
        # Each is checked against what it is defined to be, not against a
        # remembered number.
        structure, tax_breakdown, forecast = _forecast(1_800_000, nps_opted=True)
        cash = structure.basic + structure.hra + structure.lta + structure.special_allowance
        employee_pf = derive_pf(structure.basic)
        self.assertAlmostEqual(forecast["tds_escrow_annual"], tax_breakdown["total_tax"], delta=0.01)
        self.assertAlmostEqual(forecast["epfo_challan_annual"],
                               structure.employer_pf + employee_pf, delta=0.01)
        self.assertAlmostEqual(
            forecast["net_take_home_annual"],
            cash - employee_pf - forecast["tds_escrow_annual"]
            - forecast["professional_tax_annual"], delta=0.01)
        self.assertGreater(tax_breakdown["total_tax"], 0, "precondition: this structure owes tax")


if __name__ == "__main__":
    unittest.main()
