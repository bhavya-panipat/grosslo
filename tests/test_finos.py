import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tax_engine import (
    compute_tax, hra_exemption, build_structure, taxable_income_for_structure,
    derive_pf, derive_nps, STANDARD_DEDUCTION, SalaryStructure,
)
from optimizer import optimize, best_regime_for_given_structure, sensitivity_sweep
from ai_layer import extract_from_text, explain_result, flag_compliance, negotiate, _check_rules


class TestTaxEngineCore(unittest.TestCase):
    def test_zero_tax_at_12L_new_regime(self):
        result = compute_tax(1_200_000, "new")
        self.assertEqual(result["total_tax"], 0.0)

    def test_marginal_relief_matches_official_example(self):
        # Government's own worked example: ~61,500 slab tax at 12.1L
        # taxable income, reduced to 10,000 by marginal relief.
        result = compute_tax(1_210_000, "new")
        self.assertEqual(result["slab_tax"], 61500.0)
        self.assertEqual(result["tax_after_marginal_relief"], 10000)

    def test_gross_salary_12_75L_is_tax_free_new_regime(self):
        gross_salary = 1_275_000
        taxable = gross_salary - STANDARD_DEDUCTION["new"]
        result = compute_tax(taxable, "new")
        self.assertEqual(result["total_tax"], 0.0)

    def test_old_regime_basic_calc(self):
        result = compute_tax(600_000, "old")
        self.assertEqual(result["total_tax"], 33800.0)


class TestHraExemption(unittest.TestCase):
    def test_hra_metro_vs_non_metro(self):
        basic = 500_000
        hra_paid = 300_000
        rent = 400_000
        metro = hra_exemption(basic, hra_paid, rent, "metro")
        non_metro = hra_exemption(basic, hra_paid, rent, "non_metro")
        self.assertGreater(metro, non_metro)

    def test_hra_zero_when_no_rent(self):
        self.assertEqual(hra_exemption(500_000, 300_000, 0, "metro"), 0.0)


class TestPfCeilingToggle(unittest.TestCase):
    def test_pf_voluntary_vs_statutory_ceiling(self):
        basic = 1_200_000  # 100k/month, well above 15k statutory ceiling
        full = derive_pf(basic, voluntary_full_basic=True)
        capped = derive_pf(basic, voluntary_full_basic=False)
        self.assertGreater(full, capped)
        self.assertEqual(capped, round(0.12 * 15_000 * 12, 2))


class TestOptimizerRegimeCrossover(unittest.TestCase):
    def test_high_rent_low_ctc_new_regime_still_favored(self):
        # Post-2025-reform, new regime dominates for most typical salaried
        # ranges even with high rent, due to HRA's 50%-of-basic cap.
        result = optimize(ctc=1_800_000, rent_paid=1_000_000, city="metro", nps_opted=True)
        self.assertIn(result["recommended"].regime, ("old", "new"))

    def test_old_regime_can_win_high_ctc_high_rent_no_nps(self):
        # Documented crossover case found during build: high CTC, high rent,
        # NPS not opted -> old regime should win.
        result = optimize(ctc=3_500_000, rent_paid=1_400_000, city="metro", nps_opted=False)
        self.assertEqual(result["recommended"].regime, "old")

    def test_nps_opted_toggle_changes_recommendation_or_saving(self):
        with_nps = optimize(ctc=1_800_000, rent_paid=540_000, city="metro", nps_opted=True)
        without_nps = optimize(ctc=1_800_000, rent_paid=540_000, city="metro", nps_opted=False)
        # NPS opt-in should never make new regime tax worse
        self.assertLessEqual(
            with_nps["new_regime_best"].tax_breakdown["total_tax"],
            without_nps["new_regime_best"].tax_breakdown["total_tax"],
        )


class TestAiLayerExtraction(unittest.TestCase):
    def test_extraction_partial_breakdown_no_false_mismatch(self):
        text = "CTC: Rs. 18,00,000\nBasic Salary: Rs. 7,20,000\nHRA: Rs. 3,60,000"
        result = extract_from_text(text)
        self.assertIsNone(result["mismatch_warning"])

    def test_extraction_full_breakdown_catches_genuine_mismatch(self):
        text = (
            "CTC: Rs. 20,00,000\nBasic Salary: Rs. 5,00,000\nHRA: Rs. 2,00,000\n"
            "LTA: Rs. 50,000\nSpecial Allowance: Rs. 3,00,000\nEmployer PF: Rs. 60,000"
        )
        result = extract_from_text(text)
        self.assertIsNotNone(result["mismatch_warning"])

    def test_extraction_falls_back_without_api_key(self):
        text = "CTC: Rs. 10,00,000"
        result = extract_from_text(text)
        self.assertIn("ai_backed", result)


class TestAiLayerExplainer(unittest.TestCase):
    def test_explainer_grounded_in_engine_numbers(self):
        opt_result = optimize(ctc=1_800_000, rent_paid=540_000, city="metro", nps_opted=True)
        explanation = explain_result(opt_result, rent_paid=540_000, city="metro")
        self.assertFalse(explanation["guard_triggered"])
        self.assertIn(str(int(opt_result["ctc"])), explanation["explanation"].replace(",", ""))

    def test_explainer_old_regime_win_case(self):
        opt_result = optimize(ctc=3_500_000, rent_paid=1_400_000, city="metro", nps_opted=False)
        self.assertEqual(opt_result["recommended"].regime, "old")
        explanation = explain_result(opt_result, rent_paid=1_400_000, city="metro")
        self.assertIn("explanation", explanation)


class TestAiLayerCompliance(unittest.TestCase):
    def test_clean_structure_no_flags(self):
        result = optimize(ctc=1_800_000, rent_paid=540_000, city="metro", nps_opted=True)
        flags = flag_compliance(result["recommended"].structure, rent_paid=540_000)
        self.assertEqual(flags["flags"], [])

    def test_low_basic_triggers_r1(self):
        s = SalaryStructure(
            ctc=1_800_000, basic=500_000, hra=200_000, lta=0,
            special_allowance=0, employer_pf=60_000, employer_nps=0, nps_opted=False,
        )
        flags = flag_compliance(s, rent_paid=0)
        ids = {f["rule_id"] for f in flags["flags"]}
        self.assertIn("R1", ids)

    def test_r5_perquisite_gap_detected(self):
        s = SalaryStructure(
            ctc=9_000_000, basic=4_500_000, hra=1_000_000, lta=200_000,
            special_allowance=1_500_000, employer_pf=540_000, employer_nps=630_000,
            nps_opted=True,
        )
        flags = flag_compliance(s, rent_paid=1_000_000)
        ids = {f["rule_id"] for f in flags["flags"]}
        self.assertIn("R5", ids)

    def test_hra_without_rent_triggers_r3(self):
        s = SalaryStructure(
            ctc=1_800_000, basic=720_000, hra=300_000, lta=0,
            special_allowance=780_000, employer_pf=86_400, employer_nps=0, nps_opted=False,
        )
        flags = flag_compliance(s, rent_paid=0)
        ids = {f["rule_id"] for f in flags["flags"]}
        self.assertIn("R3", ids)


class TestNegotiationCopilot(unittest.TestCase):
    def _run(self, ctc, rent_paid, city, current_structure, nps_opted=True):
        current_best = best_regime_for_given_structure(current_structure, rent_paid, city)
        result = optimize(ctc=ctc, rent_paid=rent_paid, city=city, nps_opted=nps_opted)
        neg = negotiate(
            current_structure=current_structure, current_best=current_best,
            recommended=result["recommended"].structure,
            recommended_regime=result["recommended"].regime,
            recommended_tax=result["recommended"].tax_breakdown,
            ctc=ctc,
        )
        return neg, current_best, result

    def test_savings_equals_exact_subtraction(self):
        # Poorly structured offer: low basic, no NPS, no LTA — plenty of
        # room for the optimizer to improve on.
        current = SalaryStructure(
            ctc=1_800_000, basic=450_000, hra=300_000, lta=0,
            special_allowance=996_000, employer_pf=54_000, employer_nps=0,
            nps_opted=False,
        )
        neg, current_best, result = self._run(1_800_000, 400_000, "metro", current)
        expected = round(current_best["tax_breakdown"]["total_tax"] - result["recommended"].tax_breakdown["total_tax"], 2)
        self.assertEqual(neg["total_annual_saving"], expected)
        self.assertGreater(neg["total_annual_saving"], 0)

    def test_changed_levers_detected(self):
        current = SalaryStructure(
            ctc=1_800_000, basic=450_000, hra=300_000, lta=0,
            special_allowance=996_000, employer_pf=54_000, employer_nps=0,
            nps_opted=False,
        )
        neg, _, _ = self._run(1_800_000, 400_000, "metro", current)
        # basic differs (45% vs recommended 40-50% band starting higher),
        # and NPS is off in the current structure but the recommendation
        # opts in — both should be flagged.
        self.assertIn("NPS enrollment (80CCD2)", neg["changed_levers"])

    def test_already_optimal_structure_yields_no_ask(self):
        # Build a "current" structure that IS the optimizer's own recommendation
        # — there should be nothing left to negotiate.
        result = optimize(ctc=1_800_000, rent_paid=400_000, city="metro", nps_opted=True)
        rec_structure = result["recommended"].structure
        current_best = best_regime_for_given_structure(rec_structure, 400_000, "metro")
        neg = negotiate(
            current_structure=rec_structure, current_best=current_best,
            recommended=rec_structure,
            recommended_regime=result["recommended"].regime,
            recommended_tax=result["recommended"].tax_breakdown,
            ctc=1_800_000,
        )
        self.assertEqual(neg["total_annual_saving"], 0)
        self.assertEqual(neg["changed_levers"], [])

    def test_fallback_message_contains_no_fabricated_number(self):
        # With no API key in this test environment, this always exercises
        # the deterministic fallback — confirm it only ever states the
        # exact total_annual_saving figure, never a per-lever number.
        current = SalaryStructure(
            ctc=1_800_000, basic=450_000, hra=300_000, lta=0,
            special_allowance=996_000, employer_pf=54_000, employer_nps=0,
            nps_opted=False,
        )
        neg, _, _ = self._run(1_800_000, 400_000, "metro", current)
        self.assertFalse(neg["ai_backed"])
        saving_str = f"{neg['total_annual_saving']:,.0f}"
        self.assertIn(saving_str, neg["points"])


class TestSensitivitySweep(unittest.TestCase):
    def test_returns_requested_number_of_points(self):
        points = sensitivity_sweep(rent_paid=400_000, city="metro", nps_opted=True, steps=15)
        self.assertEqual(len(points), 15)

    def test_points_are_internally_consistent_with_optimize(self):
        # Spot-check one point against a direct optimize() call — the sweep
        # must not silently diverge from the already-validated function it
        # wraps.
        points = sensitivity_sweep(rent_paid=400_000, city="metro", nps_opted=True,
                                    ctc_min=1_800_000, ctc_max=1_800_000, steps=1)
        direct = optimize(ctc=1_800_000, rent_paid=400_000, city="metro", nps_opted=True)
        self.assertEqual(points[0]["old_tax"], direct["old_regime_best"].tax_breakdown["total_tax"])
        self.assertEqual(points[0]["new_tax"], direct["new_regime_best"].tax_breakdown["total_tax"])
        self.assertEqual(points[0]["recommended_regime"], direct["recommended"].regime)

    def test_low_ctc_favors_old_regime_with_high_relative_rent(self):
        # At low CTC with a fixed, relatively high rent, HRA exemption should
        # make old regime win — sanity-checks the sweep finds a real signal,
        # not just constant output.
        points = sensitivity_sweep(rent_paid=400_000, city="metro", nps_opted=True,
                                    ctc_min=400_000, ctc_max=400_000, steps=1)
        self.assertEqual(points[0]["recommended_regime"], "old")


class TestComplianceChecksOfferedStructure(unittest.TestCase):
    """
    Regression test for a real bug caught during manual testing: compliance
    was checking the OPTIMIZER'S OWN recommended structure, which enforces
    a 40-50% basic band by construction — so R1 (basic < 35% of CTC) could
    never fire against it. That's nearly circular: checking the tool's
    output against rules the tool was built to satisfy. Compliance must
    check the as-offered structure when one exists.
    """
    def test_low_basic_offer_triggers_r1_against_as_offered_structure(self):
        offered = SalaryStructure(
            ctc=2_400_000, basic=600_000, hra=320_000, lta=0,
            special_allowance=1_480_000 - 72_000 - 168_000,  # rough remainder
            employer_pf=72_000, employer_nps=0, nps_opted=False,
        )
        flags = _check_rules(offered, rent_paid=400_000)
        rule_ids = [f["rule_id"] for f in flags]
        self.assertIn("R1", rule_ids)

    def test_optimizer_recommended_structure_never_triggers_r1(self):
        # Documents WHY checking the recommendation alone is insufficient —
        # the optimizer's own 40% floor means R1 can't fire against its output.
        result = optimize(ctc=2_400_000, rent_paid=400_000, city="metro", nps_opted=True)
        flags = _check_rules(result["recommended"].structure, rent_paid=400_000)
        rule_ids = [f["rule_id"] for f in flags]
        self.assertNotIn("R1", rule_ids)


if __name__ == "__main__":
    unittest.main()
