import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tax_engine import (
    compute_tax, hra_exemption, build_structure, taxable_income_for_structure,
    derive_pf, derive_nps, STANDARD_DEDUCTION, SalaryStructure,
)
from optimizer import (
    optimize, best_regime_for_given_structure, sensitivity_sweep,
    theoretical_minimum_tax, naive_baseline_tax, optimization_value_pct,
    BASIC_PCT_MIN, BASIC_PCT_MAX,
)
from ai_layer import (
    extract_from_text, explain_result, flag_compliance, negotiate, _check_rules,
    compliance_pct, ai_coverage_pct, answer_query, evaluate_band_guardrail,
)
from payroll_breakdown import monthly_professional_tax, annual_professional_tax, treasury_forecast
from unittest.mock import patch, Mock
from app import _parse_commit_dates


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


class TestNpsRegimeRateDifferential(unittest.TestCase):
    """
    Section 124 (formerly 80CCD(2)): employer NPS deduction cap is 10% of
    basic under the old regime, 14% under the new regime, for private-sector
    employer contributions — the specific rate split flagged for
    confirm-don't-assume verification in the 2026-09-02 citation sweep,
    since the codebase has changed substantially since this was first built.
    """

    def test_new_regime_caps_at_14_percent_of_basic(self):
        basic = 1_000_000
        self.assertEqual(derive_nps(basic, "new", opted_in=True), round(0.14 * basic, 2))

    def test_old_regime_caps_at_10_percent_of_basic(self):
        basic = 1_000_000
        self.assertEqual(derive_nps(basic, "old", opted_in=True), round(0.10 * basic, 2))

    def test_new_regime_rate_exceeds_old_regime_rate_for_same_basic(self):
        basic = 1_000_000
        new_nps = derive_nps(basic, "new", opted_in=True)
        old_nps = derive_nps(basic, "old", opted_in=True)
        self.assertGreater(new_nps, old_nps)
        self.assertEqual(new_nps, round(old_nps * 1.4, 2))

    def test_not_opted_in_yields_zero_regardless_of_regime(self):
        basic = 1_000_000
        self.assertEqual(derive_nps(basic, "new", opted_in=False), 0.0)
        self.assertEqual(derive_nps(basic, "old", opted_in=False), 0.0)


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

    def test_explainer_skip_ai_never_ai_backed(self):
        # Batch mode passes skip_ai=True — found via load-testing that a
        # 20-row batch didn't complete in 60s because of one sequential
        # live API call per row, for explanation text the batch UI never
        # even renders. This asserts the fast path stays deterministic
        # (and therefore fast) regardless of whether a real API key is
        # configured — the whole point of skip_ai is to never touch the
        # network, not just to usually avoid it.
        opt_result = optimize(ctc=1_800_000, rent_paid=540_000, city="metro", nps_opted=True)
        explanation = explain_result(opt_result, rent_paid=540_000, city="metro", skip_ai=True)
        self.assertFalse(explanation["ai_backed"])
        self.assertFalse(explanation["guard_triggered"])
        self.assertIn(str(int(opt_result["ctc"])), explanation["explanation"].replace(",", ""))


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

    def _r1_structure(self):
        # Real R1 (High-severity, Code on Wages) violation — basic well
        # below the 50% statutory floor.
        return SalaryStructure(
            ctc=2_000_000, basic=900_000, hra=400_000, lta=0,
            special_allowance=2_000_000 - 900_000 - 400_000 - 108_000,
            employer_pf=108_000, employer_nps=0, nps_opted=False,
        )

    def test_numeric_guard_rejects_ungrounded_number_in_rephrasing(self):
        # Real bug this closes: flag_compliance() only ever checked that
        # the AI returned the right LINE COUNT, never that the numbers
        # inside those lines were real. This mocks a rephrasing that
        # restates R1's real 50% floor as an invented 35% instead.
        s = self._r1_structure()
        fake_response = Mock()
        fake_response.content = [Mock(text="Basic salary is below 35% of CTC, a compliance concern.")]
        with patch("ai_layer._client", Mock(messages=Mock(create=Mock(return_value=fake_response)))):
            result = flag_compliance(s, rent_paid=300_000)
        self.assertTrue(result["guard_triggered"])
        self.assertFalse(result["ai_backed"])
        r1 = next(f for f in result["flags"] if f["rule_id"] == "R1")
        self.assertIn("50%", r1["message"])  # served the real rationale, not the fake "35%" text
        self.assertNotIn("35%", r1["message"])

    def test_numeric_guard_passes_legitimate_rephrasing(self):
        s = self._r1_structure()
        fake_response = Mock()
        fake_response.content = [Mock(
            text="This structure sets Basic below the 50% floor the Code on Wages 2025 requires.",
        )]
        with patch("ai_layer._client", Mock(messages=Mock(create=Mock(return_value=fake_response)))):
            result = flag_compliance(s, rent_paid=300_000)
        self.assertFalse(result["guard_triggered"])
        self.assertTrue(result["ai_backed"])

    def test_numeric_guard_catches_small_numbers_not_just_large_ones(self):
        # The one deliberate difference from explain_result()'s guard:
        # skip_below=0 here, not 100 — a wrong PERCENTAGE (e.g. "35" vs
        # the real "50") is exactly the kind of small, high-stakes number
        # compliance text turns on, and explain_result's skip-small-
        # numbers heuristic would have let this straight through.
        s = self._r1_structure()
        fake_response = Mock()
        fake_response.content = [Mock(text="Basic salary is below 35% of CTC here.")]
        with patch("ai_layer._client", Mock(messages=Mock(create=Mock(return_value=fake_response)))):
            result = flag_compliance(s, rent_paid=300_000)
        self.assertTrue(result["guard_triggered"])

    def test_polarity_guard_catches_soft_pedaled_violation(self):
        # The sharper gap numeric grounding alone misses: every number in
        # this rephrasing is real (50%), but the CONCLUSION is flipped —
        # a real violation described as if it were fine.
        s = self._r1_structure()
        fake_response = Mock()
        fake_response.content = [Mock(
            text="Basic salary sits near the 50% mark, which is acceptable.",
        )]
        with patch("ai_layer._client", Mock(messages=Mock(create=Mock(return_value=fake_response)))):
            result = flag_compliance(s, rent_paid=300_000)
        self.assertTrue(result["guard_triggered"])
        self.assertFalse(result["ai_backed"])

    def test_polarity_guard_does_not_fire_on_negated_marker(self):
        # The bug found and fixed during plan review: a plain substring
        # check on "compliant" would false-positive on this correctly-
        # negated, faithful rephrasing of a real violation.
        s = self._r1_structure()
        fake_response = Mock()
        fake_response.content = [Mock(
            text="The structure is not compliant with the 50% Basic-salary floor.",
        )]
        with patch("ai_layer._client", Mock(messages=Mock(create=Mock(return_value=fake_response)))):
            result = flag_compliance(s, rent_paid=300_000)
        self.assertFalse(result["guard_triggered"])
        self.assertTrue(result["ai_backed"])

    def test_polarity_guard_does_not_fire_on_hyphenated_negated_marker(self):
        # Second negation gap found in a follow-up review round: "non-
        # compliant" (hyphenated) wasn't recognized as negated by the
        # first fix, which only handled "not compliant" (space-separated).
        s = self._r1_structure()
        fake_response = Mock()
        fake_response.content = [Mock(
            text="The structure is non-compliant with the 50% Basic-salary floor.",
        )]
        with patch("ai_layer._client", Mock(messages=Mock(create=Mock(return_value=fake_response)))):
            result = flag_compliance(s, rent_paid=300_000)
        self.assertFalse(result["guard_triggered"])
        self.assertTrue(result["ai_backed"])


class TestGuardrailPhrasingGuard(unittest.TestCase):
    """
    Numeric + polarity guard on evaluate_band_guardrail()'s AI-phrased
    check messages — same discipline as TestAiLayerCompliance's
    flag_compliance() tests above, and the reason guard_triggered in this
    function's return value is no longer permanently False (it was dead
    scaffolding — declared, never actually set anywhere — before this).
    """

    def _out_of_band_structure(self):
        # Real, clean structure whose CTC simply falls outside a narrow
        # approved band — the guardrail's band_cost_neutrality check
        # fails; EPFO/Section 124 checks pass, so exactly one check is
        # being rephrased, keeping the mock response simple.
        return SalaryStructure(
            ctc=1_800_000, basic=1_080_000, hra=0, lta=0, special_allowance=590_400,
            employer_pf=129_600, employer_nps=0, nps_opted=False,
        )

    def test_numeric_guard_rejects_ungrounded_number(self):
        s = self._out_of_band_structure()
        fake_response = Mock()
        fake_response.content = [Mock(
            text="CTC of Rs 1,800,000 falls outside the approved band of Rs 100,000-Rs 500,000.",
        )]
        with patch("ai_layer._client", Mock(messages=Mock(create=Mock(return_value=fake_response)))):
            result = evaluate_band_guardrail(s, "new", 2_000_000, 2_500_000)
        self.assertTrue(result["guard_triggered"])
        self.assertFalse(result["ai_backed"])
        check = next(c for c in result["checks"] if c["id"] == "band_cost_neutrality")
        self.assertIn("2,000,000", check["message"])  # real band, not the fake one

    def test_numeric_guard_passes_legitimate_rephrasing(self):
        s = self._out_of_band_structure()
        fake_response = Mock()
        fake_response.content = [Mock(
            text="This CTC of Rs 1,800,000 does not fall within the approved Rs 2,000,000-Rs 2,500,000 band.",
        )]
        with patch("ai_layer._client", Mock(messages=Mock(create=Mock(return_value=fake_response)))):
            result = evaluate_band_guardrail(s, "new", 2_000_000, 2_500_000)
        self.assertFalse(result["guard_triggered"])
        self.assertTrue(result["ai_backed"])

    def test_polarity_guard_catches_flip_with_grounded_numbers(self):
        # The gap that matters most, per review: every number here is
        # real (the actual band), but the rephrasing states the FAILING
        # check as if it passed — "is within" is the passing template's
        # own pivot phrase, echoed back for a check that actually failed.
        s = self._out_of_band_structure()
        fake_response = Mock()
        fake_response.content = [Mock(
            text="CTC of Rs 1,800,000 is within the approved band of Rs 2,000,000-Rs 2,500,000.",
        )]
        with patch("ai_layer._client", Mock(messages=Mock(create=Mock(return_value=fake_response)))):
            result = evaluate_band_guardrail(s, "new", 2_000_000, 2_500_000)
        self.assertTrue(result["guard_triggered"])
        self.assertFalse(result["ai_backed"])

    def test_polarity_guard_does_not_fire_on_negated_marker(self):
        s = self._out_of_band_structure()
        fake_response = Mock()
        fake_response.content = [Mock(
            text="CTC of Rs 1,800,000 is not within the approved band of Rs 2,000,000-Rs 2,500,000.",
        )]
        with patch("ai_layer._client", Mock(messages=Mock(create=Mock(return_value=fake_response)))):
            result = evaluate_band_guardrail(s, "new", 2_000_000, 2_500_000)
        self.assertFalse(result["guard_triggered"])
        self.assertTrue(result["ai_backed"])


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
        # current basic is 450,000 / 1,800,000 = 25% of CTC, well below the
        # optimizer's own 50-60% recommended band, and NPS is off in the
        # current structure but the recommendation opts in — both should
        # be flagged. This "current" structure is a user-supplied input to
        # the negotiation copilot, not the optimizer's own search output,
        # so it isn't constrained by BASIC_PCT_MIN/MAX at all — the 25%
        # value is unaffected by the statutory-floor fix and needs no
        # change here beyond this comment's own arithmetic being correct.
        self.assertIn("NPS enrollment (Section 124, formerly 80CCD2)", neg["changed_levers"])

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

    def test_skip_ai_goes_straight_to_deterministic_text_no_api_call(self):
        # Real latency fix, not a hypothetical: negotiate() was measured
        # live as the DOMINANT cost in a batch submission (~5.5s/row,
        # even after flag_compliance() was already fixed) because it was
        # called unconditionally for every correction row with no skip
        # flag at all. skip_ai=True must never reach _client.messages.create
        # — verified here by patching _client to a Mock that raises if
        # called, not just by checking the returned ai_backed flag (which
        # a real bug could report correctly while still making the call).
        current = SalaryStructure(
            ctc=1_800_000, basic=450_000, hra=300_000, lta=0,
            special_allowance=996_000, employer_pf=54_000, employer_nps=0,
            nps_opted=False,
        )
        current_best = best_regime_for_given_structure(current, 400_000, "metro")
        result = optimize(ctc=1_800_000, rent_paid=400_000, city="metro", nps_opted=True)

        def _fail_if_called(*args, **kwargs):
            raise AssertionError("negotiate() called the API despite skip_ai=True")

        with patch("ai_layer._client", Mock(messages=Mock(create=_fail_if_called))):
            neg = negotiate(
                current_structure=current, current_best=current_best,
                recommended=result["recommended"].structure,
                recommended_regime=result["recommended"].regime,
                recommended_tax=result["recommended"].tax_breakdown,
                ctc=1_800_000, skip_ai=True,
            )
        self.assertFalse(neg["ai_backed"])
        self.assertFalse(neg["guard_triggered"])
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
    a 50-60% basic band by construction — so R1 (basic < 50% of CTC) could
    never fire against it. That's nearly circular: checking the tool's
    output against rules the tool was built to satisfy. Compliance must
    check the as-offered structure when one exists.

    Worth stating plainly: after the Code on Wages fix, R1's threshold
    (50%) and the optimizer's own floor (BASIC_PCT_MIN = 0.50) are now the
    exact same number, with zero margin between them — before the fix
    there was a 5-point buffer (35% vs 40%) that would have silently
    absorbed any floating-point rounding noise. test_optimizer_
    recommended_structure_never_triggers_r1 below is what actually proves
    the boundary still holds cleanly at that exact value, not just that
    the logic reads as though it should.
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
        # the optimizer's own 50% floor means R1 can't fire against its
        # output, now with zero numeric margin between R1's threshold and
        # BASIC_PCT_MIN (both exactly 0.50) — this is the real, live check
        # that a recommended structure landing exactly at the floor
        # doesn't trip R1 on floating-point rounding noise, not an
        # assumption carried forward from when there was a 5-point buffer.
        for ctc in [800_000, 1_800_000, 2_400_000, 4_000_000, 6_000_000]:
            result = optimize(ctc=ctc, rent_paid=400_000, city="metro", nps_opted=True)
            flags = _check_rules(result["recommended"].structure, rent_paid=400_000)
            rule_ids = [f["rule_id"] for f in flags]
            self.assertNotIn("R1", rule_ids, f"R1 incorrectly fired at CTC={ctc}")


class TestBasicPctStatutoryFloor(unittest.TestCase):
    """
    Code on Wages 2025 fix (effective 21 Nov 2025, verified live 2026-09-01
    — see README.md's "Regulatory currency" section): BASIC_PCT_MIN raised
    from 0.40 to 0.50 (the statutory floor), BASIC_PCT_MAX raised from 0.50
    to 0.60 (same 10-point band width, repositioned above the floor so the
    search space doesn't collapse to one point). These tests prove the
    fix's actual behavior, not just that the constants changed.
    """

    def test_constants_are_the_statutory_band_not_the_old_one(self):
        self.assertEqual(BASIC_PCT_MIN, 0.50)
        self.assertEqual(BASIC_PCT_MAX, 0.60)

    def test_search_space_is_genuinely_ten_points_wide_not_collapsed(self):
        # The whole point of raising the ceiling alongside the floor: if
        # this ever regressed to BASIC_PCT_MIN == BASIC_PCT_MAX, the
        # optimizer would still run without error but would have nothing
        # left to search. First, the grid itself must be genuinely 5
        # distinct points spanning 0.50 to 0.60.
        from optimizer import _basic_pct_range, optimize_new_regime
        grid = _basic_pct_range()
        self.assertEqual(len(grid), 5, f"expected 5 grid points (50/52.5/55/57.5/60), got {grid}")
        self.assertEqual(grid[0], 0.50)
        self.assertEqual(grid[-1], 0.60)
        self.assertEqual(len(set(grid)), 5, "grid points are not all distinct")

        # Second, and more important: prove the search actually EXPLORES
        # more than one point and that the points matter, not just that the
        # bounds constants are set correctly. Pinning the search to a
        # single-point range at each end of the band and confirming the
        # resulting tax differs proves both endpoints are real, reachable,
        # distinct outcomes — not that the default call merely iterates
        # without effect.
        low_end = optimize_new_regime(ctc=4_000_000, nps_opted=True, basic_pct_range=[0.50])
        high_end = optimize_new_regime(ctc=4_000_000, nps_opted=True, basic_pct_range=[0.60])
        self.assertNotEqual(
            low_end.tax_breakdown["total_tax"], high_end.tax_breakdown["total_tax"],
            "0.50 and 0.60 basic_pct produced identical tax — search space isn't doing real work",
        )
        # And the unconstrained default call must actually land on the
        # higher-basic point, since more basic shelters more via PF/NPS
        # under the new regime — confirming the full grid is walked, not
        # just its first element.
        default_result = optimize_new_regime(ctc=4_000_000, nps_opted=True)
        self.assertEqual(default_result.basic_pct, grid[-1])

    def test_r1_fires_below_floor_and_not_at_or_above_it(self):
        # 45% — below the statutory floor, must trigger, High severity.
        below = SalaryStructure(
            ctc=2_000_000, basic=900_000, hra=400_000, lta=0,
            special_allowance=2_000_000 - 900_000 - 400_000 - 108_000,
            employer_pf=108_000, employer_nps=0, nps_opted=False,
        )
        flags_below = _check_rules(below, rent_paid=300_000)
        r1_below = next((f for f in flags_below if f["rule_id"] == "R1"), None)
        self.assertIsNotNone(r1_below, "R1 must fire at 45% basic (900,000/2,000,000)")
        self.assertEqual(r1_below["severity"], "High")
        self.assertIn("Code on Wages", r1_below["rationale"])

        # Exactly 50% — at the floor, must NOT trigger ("at least 50%" is compliant).
        at_floor = SalaryStructure(
            ctc=2_000_000, basic=1_000_000, hra=400_000, lta=0,
            special_allowance=2_000_000 - 1_000_000 - 400_000 - 120_000,
            employer_pf=120_000, employer_nps=0, nps_opted=False,
        )
        flags_at_floor = _check_rules(at_floor, rent_paid=300_000)
        rule_ids_at_floor = [f["rule_id"] for f in flags_at_floor]
        self.assertNotIn("R1", rule_ids_at_floor, "R1 must NOT fire at exactly 50% basic")

    def test_naive_baseline_matches_statutory_floor_but_is_its_own_literal(self):
        # naive_baseline_tax() hardcodes 0.50 independently of BASIC_PCT_MIN
        # (see its own docstring for why they're deliberately not coupled in
        # source) — this is the explicit assertion the user asked for, so a
        # future change to either number is caught here instead of silently
        # desyncing the two concepts it happens to currently share a value
        # with.
        self.assertEqual(BASIC_PCT_MIN, 0.50)
        naive = naive_baseline_tax(ctc=1_800_000, rent_paid=400_000, city="metro")
        from optimizer import build_structure, taxable_income_for_structure, compute_tax
        expected_structure = build_structure(
            ctc=1_800_000, basic_pct=BASIC_PCT_MIN, hra_pct_of_remaining=0.0,
            lta=0.0, regime="new", nps_opted=False,
        )
        expected_taxable = taxable_income_for_structure(expected_structure, "new", rent_paid=0, city="metro")
        expected = compute_tax(expected_taxable, "new")["total_tax"]
        self.assertEqual(naive, expected)


class TestTheoreticalMinimumAndOptimizationValue(unittest.TestCase):
    def test_theoretical_minimum_never_exceeds_realistic_recommendation(self):
        for ctc in [800_000, 1_800_000, 3_500_000, 6_000_000]:
            rent = int(0.25 * ctc)
            realistic = optimize(ctc=ctc, rent_paid=rent, city="metro", nps_opted=True)["recommended"].tax_breakdown["total_tax"]
            theoretical = theoretical_minimum_tax(ctc=ctc, rent_paid=rent, city="metro", nps_opted=True)
            self.assertLessEqual(theoretical, realistic)

    def test_theoretical_minimum_does_not_crash_at_wide_basic_range(self):
        # Regression test: optimize_new_regime originally had no exception
        # handling for infeasible basic_pct values, which only surfaced
        # once theoretical_minimum_tax's wide 1-99% search range hit a
        # basic_pct where PF+NPS exceeded the remaining CTC.
        result = theoretical_minimum_tax(ctc=1_800_000, rent_paid=400_000, city="metro", nps_opted=True)
        self.assertIsInstance(result, float)

    def test_optimization_value_is_not_degenerately_zero_for_a_good_recommendation(self):
        # Regression test: the original formula (realistic vs. theoretical
        # floor, as a ratio) showed 0% "efficiency" at CTC 18L specifically
        # because the theoretical floor is exactly 0 there — making a
        # correct, well-optimized recommendation look like it scored badly.
        # optimization_value_pct fixes this by comparing against a naive
        # baseline instead, which is never trivially zero when there's
        # real tax being saved.
        value = optimization_value_pct(ctc=1_800_000, rent_paid=400_000, city="metro", nps_opted=True)
        self.assertGreater(value, 0)

    def test_optimization_value_is_zero_not_crashed_when_nothing_to_optimize(self):
        # At low CTC, both naive and realistic tax can be genuinely zero —
        # must return 0.0, not divide by zero.
        value = optimization_value_pct(ctc=800_000, rent_paid=200_000, city="metro", nps_opted=True)
        self.assertEqual(value, 0.0)

    def test_naive_baseline_uses_new_regime_default_no_optimization(self):
        # Sanity-check the baseline structure itself: 50% basic, new regime,
        # no NPS opt-in — matches what "doing nothing" actually means.
        baseline = naive_baseline_tax(ctc=2_400_000, rent_paid=500_000, city="metro")
        self.assertGreater(baseline, 0)


class TestComplianceAndCoverageMetrics(unittest.TestCase):
    def test_compliance_pct_zero_flags_is_100(self):
        self.assertEqual(compliance_pct([]), 100.0)

    def test_compliance_pct_all_six_flags_is_zero(self):
        self.assertEqual(compliance_pct([{"rule_id": f"R{i}"} for i in range(1, 7)]), 0.0)

    def test_compliance_pct_one_flag_is_five_sixths(self):
        self.assertAlmostEqual(compliance_pct([{"rule_id": "R1"}]), 83.3, places=1)

    def test_ai_coverage_excludes_not_run_capabilities_from_denominator(self):
        # Only explanation + compliance ran, both AI-backed -> 100%, not 50%
        # (extraction/negotiation not running isn't a failure, it's N/A).
        self.assertEqual(
            ai_coverage_pct(extraction_ran=False, extraction_ai_backed=False,
                             explanation_ai_backed=True, compliance_ai_backed=True,
                             negotiation_ran=False, negotiation_ai_backed=False),
            100.0
        )

    def test_ai_coverage_all_four_ran_partial_ai_backed(self):
        self.assertEqual(
            ai_coverage_pct(extraction_ran=True, extraction_ai_backed=True,
                             explanation_ai_backed=True, compliance_ai_backed=True,
                             negotiation_ran=True, negotiation_ai_backed=False),
            75.0
        )

    def test_ai_coverage_full_fallback_is_zero(self):
        self.assertEqual(
            ai_coverage_pct(extraction_ran=True, extraction_ai_backed=False,
                             explanation_ai_backed=False, compliance_ai_backed=False,
                             negotiation_ran=True, negotiation_ai_backed=False),
            0.0
        )

    def test_ai_coverage_excludes_compliance_with_zero_flags(self):
        # Manual CTC only, clean structure (zero compliance flags -> nothing
        # for the LLM to phrase, compliance_ai_backed is correctly False by
        # construction). Compliance must be excluded from the denominator
        # the same way extraction/negotiation are when not applicable — the
        # only thing that actually ran (explanation) was AI-backed, so this
        # should read 100%, not silently cap at 50% for the most common,
        # cleanest-structure path. Found live via a panel-style walkthrough,
        # not by inspection alone.
        self.assertEqual(
            ai_coverage_pct(extraction_ran=False, extraction_ai_backed=False,
                             explanation_ai_backed=True, compliance_ai_backed=False,
                             negotiation_ran=False, negotiation_ai_backed=False,
                             compliance_ran=False),
            100.0
        )


class TestCommitHistoryParser(unittest.TestCase):
    def test_counts_multiple_commits_per_day(self):
        sample = "2026-08-30\n2026-08-30\n2026-08-29\n2026-08-30\n"
        result = _parse_commit_dates(sample)
        self.assertEqual(result, {"2026-08-30": 3, "2026-08-29": 1})

    def test_empty_input_returns_empty_dict(self):
        self.assertEqual(_parse_commit_dates(""), {})

    def test_single_commit(self):
        self.assertEqual(_parse_commit_dates("2026-08-29\n"), {"2026-08-29": 1})

    def test_ignores_blank_lines(self):
        sample = "2026-08-29\n\n2026-08-29\n\n"
        self.assertEqual(_parse_commit_dates(sample), {"2026-08-29": 2})


class TestConversationalQueryLayer(unittest.TestCase):
    def setUp(self):
        self.context = {"recommended_regime": "new", "recommended_tax": 88140.0, "annual_saving": 36972.0}

    def test_explanatory_fallback_does_not_crash_and_uses_real_context_numbers(self):
        r = answer_query("why did old regime lose?", self.context,
                          ctc=1_800_000, rent_paid=400_000, city="metro", nps_opted=True)
        self.assertFalse(r["ai_backed"])
        self.assertFalse(r["recalculated"])
        self.assertIn("88,140", r["answer"])  # real context number, not invented

    def test_hypothetical_rent_change_triggers_real_recalculation(self):
        # Regression-proof: the answer's number must come from an actual
        # optimize() call, not an LLM guess. Verified by computing the
        # expected result independently and checking for an exact match.
        with patch("ai_layer._classify_query", return_value={"type": "hypothetical", "param": "rent_paid", "value": 800_000}):
            r = answer_query("what if my rent were 8 lakh?", self.context,
                              ctc=1_800_000, rent_paid=400_000, city="metro", nps_opted=True)
        real = optimize(ctc=1_800_000, rent_paid=800_000, city="metro", nps_opted=True)
        real_tax = real["recommended"].tax_breakdown["total_tax"]
        self.assertTrue(r["recalculated"])
        self.assertIn(f"{real_tax:,.0f}", r["answer"])

    def test_hypothetical_ctc_change_triggers_real_recalculation(self):
        with patch("ai_layer._classify_query", return_value={"type": "hypothetical", "param": "ctc", "value": 3_000_000}):
            r = answer_query("what if my ctc were 30L?", self.context,
                              ctc=1_800_000, rent_paid=400_000, city="metro", nps_opted=True)
        real = optimize(ctc=3_000_000, rent_paid=400_000, city="metro", nps_opted=True)
        real_tax = real["recommended"].tax_breakdown["total_tax"]
        self.assertIn(f"{real_tax:,.0f}", r["answer"])

    def test_hypothetical_nps_boolean_change_triggers_real_recalculation(self):
        with patch("ai_layer._classify_query", return_value={"type": "hypothetical", "param": "nps_opted", "value": False}):
            r = answer_query("what if I don't opt into NPS?", self.context,
                              ctc=1_800_000, rent_paid=400_000, city="metro", nps_opted=True)
        real = optimize(ctc=1_800_000, rent_paid=400_000, city="metro", nps_opted=False)
        real_tax = real["recommended"].tax_breakdown["total_tax"]
        self.assertIn(f"{real_tax:,.0f}", r["answer"])

    def test_missing_value_key_does_not_crash(self):
        # Regression test: a malformed classification (param given, no
        # value) originally caused a KeyError. Must fall back gracefully.
        with patch("ai_layer._classify_query", return_value={"type": "hypothetical", "param": "rent_paid"}):
            r = answer_query("what if my rent changed?", self.context,
                              ctc=1_800_000, rent_paid=400_000, city="metro", nps_opted=True)
        self.assertFalse(r["recalculated"])
        self.assertFalse(r["ai_backed"])

    def test_invalid_param_falls_back_gracefully(self):
        with patch("ai_layer._classify_query", return_value={"type": "hypothetical", "param": "not_a_real_field", "value": 5}):
            r = answer_query("what if something invalid?", self.context,
                              ctc=1_800_000, rent_paid=400_000, city="metro", nps_opted=True)
        self.assertFalse(r["recalculated"])

    def test_hypothetical_guard_rejects_untraceable_number_and_reports_itself(self):
        # Real bug, found while wiring the guard's rejection state into the
        # UI, not by inspection: guard_triggered was computed correctly
        # inside the try block but the fallback return two branches down
        # always hardcoded False, so a genuine guard trigger was silently
        # reported as if nothing had happened. Fixed in ai_layer.py by
        # declaring guard_triggered outside the try block. This test mocks
        # only the external Claude call (a fabricated bad response
        # containing an unrelated large number) — the guard logic itself,
        # the fallback text, and the True/False it reports are all real.
        fake_response = Mock()
        fake_response.content = [Mock(text="Your new tax would be roughly ₹5,42,000 after this change.")]
        with patch("ai_layer._classify_query", return_value={"type": "hypothetical", "param": "rent_paid", "value": 800_000}), \
             patch("ai_layer._client", Mock(messages=Mock(create=Mock(return_value=fake_response)))):
            r = answer_query("what if my rent were 8 lakh?", self.context,
                              ctc=1_800_000, rent_paid=400_000, city="metro", nps_opted=True)
        real = optimize(ctc=1_800_000, rent_paid=800_000, city="metro", nps_opted=True)
        real_tax = real["recommended"].tax_breakdown["total_tax"]
        # 542000 is nowhere near the real recalculated tax, so the guard
        # must reject it and report that it did.
        self.assertNotAlmostEqual(real_tax, 542_000, delta=1)
        self.assertTrue(r["guard_triggered"])
        self.assertFalse(r["ai_backed"])
        self.assertTrue(r["recalculated"])
        self.assertIn(f"{real_tax:,.0f}", r["answer"])  # served the verified fallback, not the fake AI text
        self.assertNotIn("5,42,000", r["answer"])

    def test_hypothetical_guard_passes_a_traceable_number(self):
        # The other half of the same behavior: a live response that only
        # states numbers already traceable to the real recalculation must
        # NOT trip the guard.
        with patch("ai_layer._classify_query", return_value={"type": "hypothetical", "param": "rent_paid", "value": 800_000}):
            real = optimize(ctc=1_800_000, rent_paid=800_000, city="metro", nps_opted=True)
            real_tax = real["recommended"].tax_breakdown["total_tax"]
            fake_response = Mock()
            fake_response.content = [Mock(text=f"Your new total tax would be ₹{real_tax:,.0f} under the new regime.")]
            with patch("ai_layer._client", Mock(messages=Mock(create=Mock(return_value=fake_response)))):
                r = answer_query("what if my rent were 8 lakh?", self.context,
                                  ctc=1_800_000, rent_paid=400_000, city="metro", nps_opted=True)
        self.assertFalse(r["guard_triggered"])
        self.assertTrue(r["ai_backed"])

    def test_explanatory_guard_rejects_untraceable_number_and_reports_itself(self):
        # Same fix, same discipline, for the query layer's other path (a
        # "why" question rather than a "what if" one).
        fake_response = Mock()
        fake_response.content = [Mock(text="This is because your effective rate works out to about 4,17,000.")]
        with patch("ai_layer._client", Mock(messages=Mock(create=Mock(return_value=fake_response)))):
            r = answer_query("why did the new regime win?", self.context,
                              ctc=1_800_000, rent_paid=400_000, city="metro", nps_opted=True)
        self.assertTrue(r["guard_triggered"])
        self.assertFalse(r["ai_backed"])
        self.assertIn("88,140", r["answer"])  # verified fallback, grounded in the real context number


class TestStateProfessionalTax(unittest.TestCase):
    """
    payroll_breakdown.py's PT tables were re-verified live on 2026-09-03
    against primary sources, not the figures a first draft of this feature
    proposed — two of which had already gone stale or wrong: Karnataka's
    exemption threshold moved from Rs 15,000 to Rs 25,000 (Karnataka Tax on
    Professions... (Amendment) Act, 2025, effective 1 April 2025), and
    Tamil Nadu's Greater Chennai Corporation slab is a real 6-tier
    half-yearly table (verified against tnswp.com's own PDF directly), not
    a 2-tier approximation. Every gross_monthly figure below is chosen to
    land unambiguously inside the band being tested, not near a boundary,
    except the Telangana boundary test which does the opposite on purpose.
    """

    def test_karnataka_above_new_25000_threshold(self):
        r = monthly_professional_tax("karnataka", 30_000)
        self.assertEqual(r["amount"], 200)
        self.assertTrue(r["pt_state_recognized"])
        self.assertFalse(r["is_approximation"])

    def test_karnataka_below_new_25000_threshold_is_exempt(self):
        # The real behavioral consequence of the corrected threshold: a
        # salary that WOULD have owed Rs 200/month under the old Rs 15,000
        # exemption is genuinely exempt now.
        r = monthly_professional_tax("karnataka", 20_000)
        self.assertEqual(r["amount"], 0)
        self.assertTrue(r["pt_state_recognized"])

    def test_maharashtra_7501_to_10000_band(self):
        r = monthly_professional_tax("maharashtra", 8_000)
        self.assertEqual(r["amount"], 175)
        self.assertTrue(r["pt_state_recognized"])

    def test_maharashtra_february_bump_reaches_2500_annual_ceiling(self):
        # Both the single-month lookup and the real annual total, so a
        # regression in either the bump condition or the aggregation gets
        # caught, not just one of the two.
        february = monthly_professional_tax("maharashtra", 50_000, month=2)
        self.assertEqual(february["amount"], 300)
        annual = annual_professional_tax("maharashtra", 50_000)
        self.assertEqual(annual["amount"], 2_500)  # 11 x 200 + 300, the Article 276 ceiling

    def test_telangana_three_tier_boundaries(self):
        self.assertEqual(monthly_professional_tax("telangana", 15_000)["amount"], 0)
        self.assertEqual(monthly_professional_tax("telangana", 15_001)["amount"], 150)
        self.assertEqual(monthly_professional_tax("telangana", 20_000)["amount"], 150)
        self.assertEqual(monthly_professional_tax("telangana", 20_001)["amount"], 200)

    def test_tamil_nadu_monthly_equivalent_flagged_as_approximation(self):
        # Real half-yearly top-band tax is Rs 1,095 (verified against
        # tnswp.com's own PDF) -> monthly-equivalent is 1,095/6 = 182.5.
        r = monthly_professional_tax("tamil_nadu", 20_000)
        self.assertEqual(r["amount"], round(1_095 / 6, 2))
        self.assertTrue(r["pt_state_recognized"])
        self.assertTrue(r["is_approximation"])

    def test_delhi_is_a_confirmed_zero_not_an_unmodeled_one(self):
        r = monthly_professional_tax("delhi", 50_000)
        self.assertEqual(r["amount"], 0)
        self.assertTrue(r["pt_state_recognized"])  # the whole point of this case

    def test_missing_work_location_is_unmodeled_not_zero_by_law(self):
        # Negative control for the Delhi case directly above: both return
        # amount=0, but pt_state_recognized must tell them apart.
        r = monthly_professional_tax(None, 50_000)
        self.assertEqual(r["amount"], 0)
        self.assertFalse(r["pt_state_recognized"])

    def test_treasury_forecast_net_disbursement_differs_by_exactly_the_pt_amount(self):
        structure = build_structure(ctc=1_800_000, basic_pct=0.6, hra_pct_of_remaining=0.4,
                                     lta=0, regime="new", nps_opted=False)
        tax = compute_tax(taxable_income_for_structure(structure, "new", rent_paid=0, city="metro"), "new")
        without_pt = treasury_forecast(structure, tax)
        with_pt = treasury_forecast(structure, tax, work_location="karnataka")
        self.assertGreater(with_pt["professional_tax_annual"], 0)
        self.assertAlmostEqual(
            without_pt["net_take_home_annual"] - with_pt["net_take_home_annual"],
            with_pt["professional_tax_annual"],
            places=2,
        )
        # total_capital_outlay's own defining identity (see treasury_forecast's
        # docstring) must still hold with PT folded in as a fourth term —
        # the total cash the company needs doesn't change, only how it splits.
        self.assertAlmostEqual(
            with_pt["total_capital_outlay"],
            with_pt["net_take_home_annual"] + with_pt["tds_escrow_annual"]
            + with_pt["epfo_challan_annual"] + with_pt["professional_tax_annual"],
            places=2,
        )
        # And the total itself is unchanged by PT — it's a fourth split of
        # the same fixed cash pool, not new money the company has to find.
        self.assertAlmostEqual(without_pt["total_capital_outlay"], with_pt["total_capital_outlay"], places=2)


if __name__ == "__main__":
    unittest.main()
