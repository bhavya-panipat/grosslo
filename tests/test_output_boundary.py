"""
The output-boundary numeric assertion (OUTPUT_BOUNDARY_DESIGN.md).

The second enforcement layer for the numeric guard. The first layer,
ai_layer._numbers_ungrounded(), is called BY each LLM call site with an
allow-set that call site supplies. This one trusts no call site to have done
anything: it inspects an assembled response and asks whether every number in
model-authored text is traceable to a deterministic field of that response.

The case it exists for — and the one sabotage-proven first — is a NEW AI-backed
section whose text never went through the inline guard at all.
"""

import json
import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_layer
import output_boundary as ob
from tax_engine import SalaryStructure

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _mock_llm(text):
    """Patch the Anthropic client so a call site receives exactly `text`."""
    response = Mock()
    response.content = [Mock(text=text)]
    return patch("ai_layer._client",
                 Mock(messages=Mock(create=Mock(return_value=response))))


class TestTheCheckIsNotVacuousOverTheBaseline(unittest.TestCase):
    """
    The characterization baseline has ai_backed False throughout — it is the
    deterministic fallback path, because no API key is present when it is
    generated. Running the check over it and reporting success would be
    reporting success having checked nothing (design §3.5).

    So the clean result is asserted TOGETHER with the reason it is clean.
    """

    def _cases(self):
        with open(os.path.join(ROOT, "tests", "fixtures",
                               "pipeline_baseline.json")) as f:
            data = json.load(f)
        return data if isinstance(data, list) else list(data.values())

    def test_the_baseline_is_clean(self):
        for i, case in enumerate(self._cases()):
            with self.subTest(case=i):
                self.assertEqual(ob.ungrounded_findings(case), [])

    def test_and_it_is_clean_because_it_contains_no_model_text_at_all(self):
        # Without this, the test above would pass identically if the checker
        # were `return []`.
        for i, case in enumerate(self._cases()):
            with self.subTest(case=i):
                self.assertEqual(ob._ai_section_paths(case), [],
                                 "the baseline now has AI-backed sections; the "
                                 "clean result above is no longer explained by "
                                 "their absence")


class TestTheCaseThisExistsFor(unittest.TestCase):
    """
    A new AI-backed section whose text never went through the inline guard.
    Design §2: the analogue of a query that forgets to filter, and the one
    failure the inline guard structurally cannot catch.
    """

    def test_model_text_that_never_met_the_inline_guard_is_still_caught(self):
        # No call to _numbers_ungrounded anywhere in producing this. It is what
        # a seventh messages.create() dropped straight into a response looks
        # like.
        payload = {
            "metrics": {"total_tax": 120_000, "compliance_pct": 83.3},
            "forecast": {
                "ai_backed": True,
                "narrative": "Treasury should hold Rs 450,000 for this hire.",
            },
        }
        findings = ob.ungrounded_findings(payload)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].number, 450_000)
        self.assertEqual(findings[0].path, "forecast.narrative")

    def test_the_finding_names_the_number_and_where_it_appeared(self):
        payload = {"metrics": {"total_tax": 120_000},
                   "x": {"ai_backed": True, "note": "It is Rs 999,999."}}
        message = str(ob.ungrounded_findings(payload)[0])
        self.assertIn("999999", message)
        self.assertIn("x.note", message)
        self.assertIn("Rs 999,999", message)


class TestGroundingRules(unittest.TestCase):

    def test_a_figure_present_deterministically_is_allowed(self):
        payload = {"metrics": {"total_tax": 120_000},
                   "e": {"ai_backed": True, "t": "Your tax is Rs 120,000."}}
        self.assertEqual(ob.ungrounded_findings(payload), [])

    def test_request_numbers_may_be_restated(self):
        # An explanation may legitimately restate the CTC it was asked about
        # even when the response does not echo it back as its own field.
        payload = {"metrics": {"total_tax": 120_000},
                   "e": {"ai_backed": True, "t": "On a CTC of Rs 900,000..."}}
        self.assertTrue(ob.ungrounded_findings(payload))
        self.assertEqual(ob.ungrounded_findings(payload, extra=[900_000]), [])

    def test_a_section_marked_not_ai_backed_is_not_checked(self):
        # Its text is the deterministic fallback by definition — the
        # Python-authored rationale from compliance_rules.py, whose figures are
        # grounded in the rule rather than in the response. Checking it would
        # report findings against text no model ever touched.
        payload = {"metrics": {"total_tax": 120_000},
                   "c": {"ai_backed": False,
                         "rationale": "Basic is below the 50% floor."}}
        self.assertEqual(ob.ungrounded_findings(payload), [])

    def test_booleans_do_not_enter_the_allow_set(self):
        # bool is a subclass of int, so a True anywhere deterministic would
        # otherwise ground every stray "1" in model text.
        #
        # THE BOOL MUST SIT OUTSIDE THE AI SECTION. The first version of this
        # test put ai_backed itself forward as the offender — but that lives
        # INSIDE the section, so section-exclusion already removed it and the
        # bool check was never exercised. The test passed with the bool
        # exclusion deleted. Caught by sabotage, not by reading it.
        payload = {"meta": {"guardrail_ran": True},
                   "e": {"ai_backed": True, "t": "There is 1 issue."}}
        self.assertNotIn(1.0, ob.grounded_numbers(payload),
                         "a boolean entered the allow-set as the number 1")
        self.assertTrue(ob.ungrounded_findings(payload),
                        "a boolean grounded a number in model text")

    def test_numbers_inside_an_ai_section_do_not_ground_its_own_text(self):
        # Otherwise a model could invent a figure, have it echoed into a
        # sibling field of the same section, and thereby ground itself.
        payload = {"e": {"ai_backed": True, "amount": 777_000,
                         "t": "The amount is Rs 777,000."}}
        self.assertTrue(ob.ungrounded_findings(payload),
                        "an AI section grounded its own text")

    def test_there_is_no_skip_below_unlike_the_inline_guard(self):
        # The inline guard skips numbers under 100 in explanation text. This is
        # the backstop, and a backstop that exempts a range is not a backstop
        # over that range — the safety-critical figures live exactly there.
        payload = {"metrics": {"total_tax": 120_000},
                   "e": {"ai_backed": True, "t": "Basic sits at 35% of CTC."}}
        findings = ob.ungrounded_findings(payload)
        self.assertEqual([f.number for f in findings], [35.0])

    def test_tolerance_matches_the_inline_guard(self):
        payload = {"metrics": {"total_tax": 120_000},
                   "e": {"ai_backed": True, "t": "Tax of Rs 120,000.4"}}
        self.assertEqual(ob.ungrounded_findings(payload), [])


class TestAgainstRealPipelineOutputWithAModel(unittest.TestCase):
    """
    Design §3.5: the check proves nothing unless it is driven with model text.
    These run the real compliance path with the LLM mocked.
    """

    def _structure(self):
        # Basic below 50% of CTC — trips R1.
        return SalaryStructure(
            ctc=2_000_000, basic=600_000, hra=500_000, lta=100_000,
            special_allowance=560_000, employer_pf=240_000,
            employer_nps=0, nps_opted=False)

    def test_a_legitimate_rephrasing_passes_both_layers(self):
        with _mock_llm("This structure sets Basic below the 50% floor the "
                       "Code on Wages 2025 requires."):
            result = ai_layer.flag_compliance(self._structure(), rent_paid=300_000)
        self.assertTrue(result["ai_backed"])
        self.assertFalse(result["guard_triggered"])
        payload = {"compliance": result,
                   "metrics": {"basic_pct": 50, "year": 2025}}
        self.assertEqual(ob.ungrounded_findings(payload), [])

    def test_an_invented_figure_is_caught_by_the_inline_guard_first(self):
        # Defence in depth working as designed: the inline guard rejects the
        # rephrasing and serves the deterministic text, so nothing ungrounded
        # ever reaches the boundary. The boundary check then sees a section
        # correctly marked ai_backed False.
        with _mock_llm("Basic salary is below 35% of CTC, a compliance concern."):
            result = ai_layer.flag_compliance(self._structure(), rent_paid=300_000)
        self.assertTrue(result["guard_triggered"])
        self.assertFalse(result["ai_backed"])
        payload = {"compliance": result, "metrics": {"basic_pct": 50}}
        self.assertEqual(ob.ungrounded_findings(payload), [],
                         "the inline guard already replaced the invented text")

    def test_the_boundary_catches_it_when_the_inline_guard_is_disabled(self):
        # The real test of the second layer: neutralise the first and confirm
        # the second still holds. This is what a forgotten guard call looks like
        # from the outside.
        with patch.object(ai_layer, "_numbers_ungrounded", lambda *a, **k: False):
            with _mock_llm("Basic salary is below 35% of CTC, a compliance concern."):
                result = ai_layer.flag_compliance(self._structure(), rent_paid=300_000)
        self.assertTrue(result["ai_backed"], "the inline guard was not actually bypassed")
        payload = {"compliance": result, "metrics": {"basic_pct": 50}}
        findings = ob.ungrounded_findings(payload)
        self.assertTrue(any(f.number == 35.0 for f in findings),
                        f"the boundary missed the invented figure: {findings}")


if __name__ == "__main__":
    unittest.main()
