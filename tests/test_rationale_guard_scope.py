"""
Per-line grounding for the rationale guards (RATIONALE_GUARD_CITATION_DESIGN.md
§1.1, §8 step 3).

flag_compliance() and evaluate_band_guardrail() ask the model to rephrase
several rationales at once, then assign line i to flag i. Their numeric guard
used to check every line against ONE set pooled from every rationale in the
batch. That failed OPEN, which is a different category from the fail-closed
citation defect in §4.4.1:

  - a fabricated figure in one flag's line passed when it equalled a real
    figure belonging to a different flag;
  - lines returned in swapped order passed, so each flag carried the other's
    reason. orchestration.py quotes that text as the reason for a routing
    decision.

Every rejection test here has a control showing the correct lines, in order,
are still served. A guard that rejected every multi-flag batch would pass the
rejection tests alone.

Only the model client is mocked. Rule matching, the guard and the fallback are
real.
"""

import json
import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import ai_layer
from tax_engine import SalaryStructure


def _reply(*lines):
    response = Mock()
    response.content = [Mock(text="\n".join(lines))]
    return patch("ai_layer._client", Mock(messages=Mock(create=Mock(return_value=response))))


def _replies(*texts):
    """One mocked reply per model call, in call order. Returns (patch, create)
    so a test can read back exactly what each call was sent."""
    responses = []
    for text in texts:
        response = Mock()
        response.content = [Mock(text=text)]
        responses.append(response)
    create = Mock(side_effect=responses)
    return patch("ai_layer._client", Mock(messages=Mock(create=create))), create


class TestComplianceLinesAreGroundedInTheirOwnFlag(unittest.TestCase):
    """
    Since REPHRASING_ALIGNMENT_DESIGN.md step 2, flag_compliance() makes one
    model call per flag, so each test below supplies one reply per call in flag
    order. The assertions are unchanged from the batch version.
    """

    # Basic 40% of CTC trips R1 (50% floor); LTA 15% of CTC trips R4 (10%).
    R1_R4 = SalaryStructure(ctc=2_000_000, basic=800_000, hra=0, lta=300_000,
                            special_allowance=780_000, employer_pf=120_000,
                            employer_nps=0, nps_opted=False)
    # Basic 40% trips R1; PF + NPS of Rs 8.4L trips R5.
    R1_R5 = SalaryStructure(ctc=4_000_000, basic=1_600_000, hra=0, lta=0,
                            special_allowance=1_560_000, employer_pf=240_000,
                            employer_nps=600_000, nps_opted=True)

    def _run(self, structure, *lines):
        patcher, _ = _replies(*lines)
        with patcher:
            return ai_layer.flag_compliance(structure, rent_paid=0)

    def _messages(self, result):
        return {f["rule_id"]: f["message"] for f in result["flags"]}

    def test_the_fixtures_trigger_exactly_the_flags_these_tests_assume(self):
        self.assertEqual([f["rule_id"] for f in ai_layer._check_rules(self.R1_R4, 0)], ["R1", "R4"])
        self.assertEqual([f["rule_id"] for f in ai_layer._check_rules(self.R1_R5, 0)], ["R1", "R5"])

    def test_control_correct_lines_in_order_are_served_to_the_right_flags(self):
        result = self._run(self.R1_R4, "Basic salary is below the 50% floor.",
                           "LTA exceeds 10% of CTC.")
        self.assertTrue(result["ai_backed"])
        self.assertFalse(result["guard_triggered"])
        self.assertEqual(self._messages(result), {
            "R1": "Basic salary is below the 50% floor.",
            "R4": "LTA exceeds 10% of CTC.",
        })

    def test_a_figure_borrowed_from_another_flag_is_rejected(self):
        # 50 is real, but it is R1's figure. R4's is 10.
        result = self._run(self.R1_R4, "Basic salary is below the 50% floor.",
                           "LTA exceeds 50% of CTC.")
        self.assertTrue(result["guard_triggered"])
        self.assertFalse(result["ai_backed"])
        messages = self._messages(result)
        self.assertNotIn("50%", messages["R4"])
        self.assertEqual(messages["R4"], next(
            f["rationale"] for f in ai_layer._check_rules(self.R1_R4, 0) if f["rule_id"] == "R4"))

    def test_lines_returned_in_swapped_order_are_rejected(self):
        # Under one call per flag this means R1's call came back with R4's
        # sentence, and R4's with R1's. The figures still give it away.
        result = self._run(self.R1_R4, "LTA exceeds 10% of CTC.",
                           "Basic salary is below 50% of CTC.")
        self.assertTrue(result["guard_triggered"])
        self.assertFalse(result["ai_backed"])
        self.assertNotIn("LTA", self._messages(result)["R1"],
                         "R1 would be routed with R4's reason")

    def test_a_citation_belonging_to_another_flag_is_rejected(self):
        # "Section 17(1)(h)" is R5's provision. In R1's line its 17 and 1 are
        # not R1's figures. (Citation stripping, a later step, is per-flag for
        # the same reason, so this must stay rejected after it too.)
        result = self._run(self.R1_R5, "Basic salary is below the 50% floor under Section 17(1)(h).",
                           "The excess over Rs 7.5L is a taxable perquisite under Section 17(1)(h).")
        self.assertTrue(result["guard_triggered"])
        self.assertFalse(result["ai_backed"])

    def test_control_the_same_citation_in_its_own_flags_line_is_served(self):
        result = self._run(self.R1_R5, "Basic salary is below the 50% floor.",
                           "The excess over Rs 7.5L is a taxable perquisite under Section 17(1)(h).")
        self.assertTrue(result["ai_backed"])
        self.assertFalse(result["guard_triggered"])


class TestComplianceMakesOneCallPerFlag(unittest.TestCase):
    """
    REPHRASING_ALIGNMENT_DESIGN.md §3.1, step 2. With every flag in one call,
    two FIGURE-FREE lines returned in swapped order passed every check (measured:
    R1 served with R4's reason). No figure check can see that. So the pairing is
    now structural: each call is sent one rationale, and its one-line reply
    becomes that flag's message.
    """

    R1_R4 = TestComplianceLinesAreGroundedInTheirOwnFlag.R1_R4

    def test_each_call_is_sent_exactly_one_rationale_in_flag_order(self):
        patcher, create = _replies("Basic salary is too low for this CTC.",
                                   "LTA is higher than company policy usually allows.")
        with patcher:
            ai_layer.flag_compliance(self.R1_R4, rent_paid=0)
        sent = [json.loads(call.kwargs["messages"][0]["content"]) for call in create.call_args_list]
        self.assertEqual([[flag["rule_id"] for flag in payload] for payload in sent], [["R1"], ["R4"]])

    def test_figure_free_lines_land_on_the_flag_whose_call_produced_them(self):
        patcher, _ = _replies("Basic salary is too low for this CTC.",
                              "LTA is higher than company policy usually allows.")
        with patcher:
            result = ai_layer.flag_compliance(self.R1_R4, rent_paid=0)
        self.assertTrue(result["ai_backed"])
        self.assertEqual({f["rule_id"]: f["message"] for f in result["flags"]}, {
            "R1": "Basic salary is too low for this CTC.",
            "R4": "LTA is higher than company policy usually allows.",
        })

    def test_a_reply_that_is_not_exactly_one_line_falls_back_for_every_flag(self):
        # All-or-nothing, as before (design §5 decision 3): R1's call returns two
        # lines, so no message is assigned and no further call is made.
        patcher, create = _replies("Basic salary is too low.\nLTA is too high.",
                                   "LTA is higher than company policy usually allows.")
        with patcher:
            result = ai_layer.flag_compliance(self.R1_R4, rent_paid=0)
        self.assertFalse(result["ai_backed"])
        self.assertEqual(create.call_count, 1)
        for flag in result["flags"]:
            self.assertEqual(flag["message"], flag["rationale"])


class TestGuardrailMessagesAreGroundedInTheirOwnCheck(unittest.TestCase):

    # CTC Rs 20L outside a Rs 10L-15L band; employer NPS Rs 2.5L over the 14%
    # new-regime cap on Rs 10L basic (Rs 1.4L). EPFO aggregate Rs 3.7L passes.
    STRUCTURE = SalaryStructure(ctc=2_000_000, basic=1_000_000, hra=0, lta=0,
                                special_allowance=630_000, employer_pf=120_000,
                                employer_nps=250_000, nps_opted=True)
    BAND = ("new", 1_000_000, 1_500_000)

    BAND_LINE = "CTC of Rs 2,000,000 falls outside the approved band of Rs 1,000,000-Rs 1,500,000."
    NPS_LINE = "Employer NPS of Rs 250,000 exceeds the 14% of basic cap of Rs 140,000."

    def _run(self, *lines):
        with _reply(*lines):
            return ai_layer.evaluate_band_guardrail(self.STRUCTURE, *self.BAND)

    def test_the_fixture_fails_exactly_the_checks_these_tests_assume(self):
        with patch("ai_layer._client", None):
            result = ai_layer.evaluate_band_guardrail(self.STRUCTURE, *self.BAND)
        self.assertEqual([c["id"] for c in result["checks"] if not c["passed"]],
                         ["band_cost_neutrality", "80ccd2_cap"])

    def test_control_correct_messages_in_order_are_served_to_the_right_checks(self):
        result = self._run(self.BAND_LINE, self.NPS_LINE)
        self.assertTrue(result["ai_backed"])
        self.assertFalse(result["guard_triggered"])
        messages = {c["id"]: c["message"] for c in result["checks"]}
        self.assertEqual(messages["band_cost_neutrality"], self.BAND_LINE)
        self.assertEqual(messages["80ccd2_cap"], self.NPS_LINE)

    def test_a_figure_borrowed_from_another_check_is_rejected(self):
        # The CTC is Rs 5,00,000 over the band ceiling. Rs 2,50,000 is the
        # NPS check's figure, not the band's.
        result = self._run("CTC of Rs 2,000,000 exceeds the Rs 1,500,000 band ceiling by Rs 250,000.",
                           self.NPS_LINE)
        self.assertTrue(result["guard_triggered"])
        self.assertFalse(result["ai_backed"])

    def test_messages_returned_in_swapped_order_are_rejected(self):
        result = self._run(self.NPS_LINE, self.BAND_LINE)
        self.assertTrue(result["guard_triggered"])
        self.assertFalse(result["ai_backed"])
        band = next(c for c in result["checks"] if c["id"] == "band_cost_neutrality")
        self.assertNotIn("NPS", band["message"])


if __name__ == "__main__":
    unittest.main()
