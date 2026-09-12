"""
Model token accounting (ADDITION_SPEC_BATCH1.md, Tier 3.1's plumbing-only half).

Tier 3.1 as proposed also covered multi-turn session management and tool
permissions. Neither applies: answer_query is stateless and single-turn, and
there are no tools. Those would be capability changes and are flagged back, not
decided here. This is the part that is genuinely additive.
"""

import os
import re
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_layer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestEveryModelCallIsAccounted(unittest.TestCase):
    """
    The structural half. Adding a recording line to each call site would have
    worked today and failed the first time another was added — the same
    forgotten-call-site failure the output-boundary check exists to catch,
    reintroduced one layer over.

    Routing every call through one wrapper found EIGHT sites, where counting
    max_tokens by hand had suggested six. That gap is the argument.
    """

    def test_there_is_exactly_one_direct_call_to_the_client(self):
        with open(os.path.join(ROOT, "ai_layer.py")) as f:
            source = f.read()
        # Strip comments so the prose describing this rule does not count as a
        # violation of it.
        code = "\n".join(line for line in source.splitlines()
                         if not line.lstrip().startswith("#"))
        direct = code.count("_client.messages.create(")
        self.assertEqual(direct, 1,
                         "a model call bypasses _create() and is unaccounted; "
                         "route it through the wrapper")

    def test_that_one_call_is_inside_the_wrapper(self):
        with open(os.path.join(ROOT, "ai_layer.py")) as f:
            source = f.read()
        wrapper = re.search(r"def _create\(\*\*kwargs\):.*?\n    return response",
                            source, re.S)
        self.assertIsNotNone(wrapper, "_create() is gone or was renamed")
        self.assertIn("_client.messages.create(", wrapper.group(0))

    def test_the_call_sites_actually_use_it(self):
        with open(os.path.join(ROOT, "ai_layer.py")) as f:
            source = f.read()
        self.assertGreaterEqual(source.count("response = _create("), 8,
                                "call sites stopped routing through the wrapper")


class TestUsageIsRecorded(unittest.TestCase):

    def setUp(self):
        self._saved = ai_layer.usage_totals()
        ai_layer.reset_usage()

    def tearDown(self):
        ai_layer._USAGE.update(self._saved)

    def _client_returning(self, text, usage=None):
        response = Mock()
        response.content = [Mock(text=text)]
        response.usage = usage
        return Mock(messages=Mock(create=Mock(return_value=response)))

    def test_a_call_increments_the_counters(self):
        usage = Mock(input_tokens=120, output_tokens=45)
        with patch.object(ai_layer, "_client",
                          self._client_returning("Some explanation.", usage)):
            ai_layer._create(model="m", max_tokens=10, messages=[])
        self.assertEqual(ai_layer.usage_totals(),
                         {"calls": 1, "input_tokens": 120, "output_tokens": 45})

    def test_counters_accumulate_across_calls(self):
        usage = Mock(input_tokens=10, output_tokens=5)
        with patch.object(ai_layer, "_client",
                          self._client_returning("x", usage)):
            ai_layer._create(model="m", max_tokens=10, messages=[])
            ai_layer._create(model="m", max_tokens=10, messages=[])
        self.assertEqual(ai_layer.usage_totals()["calls"], 2)
        self.assertEqual(ai_layer.usage_totals()["input_tokens"], 20)

    def test_a_bare_mock_response_does_not_break_the_call(self):
        # THE CASE THE FIRST VERSION MISSED. A Mock auto-creates attributes, so
        # getattr(usage, "input_tokens", 0) returns a truthy Mock — `or 0` never
        # fires and int() raises. My own test set response.usage = None
        # explicitly and passed; thirteen existing guard tests did not.
        response = Mock()
        response.content = [Mock(text="x")]
        client = Mock(messages=Mock(create=Mock(return_value=response)))
        with patch.object(ai_layer, "_client", client):
            returned = ai_layer._create(model="m", max_tokens=10, messages=[])
        self.assertIs(returned, response)
        self.assertEqual(ai_layer.usage_totals()["calls"], 1,
                         "a call that happened was not counted")

    def test_a_response_without_usage_does_not_break_the_call(self):
        # A mocked client in tests has no real usage object, and accounting must
        # never be the reason a response fails to be returned.
        with patch.object(ai_layer, "_client",
                          self._client_returning("x", usage=None)):
            response = ai_layer._create(model="m", max_tokens=10, messages=[])
        self.assertEqual(response.content[0].text, "x")
        self.assertEqual(ai_layer.usage_totals()["calls"], 1)
        self.assertEqual(ai_layer.usage_totals()["input_tokens"], 0)

    def test_reset_clears_everything(self):
        usage = Mock(input_tokens=7, output_tokens=3)
        with patch.object(ai_layer, "_client",
                          self._client_returning("x", usage)):
            ai_layer._create(model="m", max_tokens=10, messages=[])
        ai_layer.reset_usage()
        self.assertEqual(ai_layer.usage_totals(),
                         {"calls": 0, "input_tokens": 0, "output_tokens": 0})

    def test_totals_are_a_copy_not_the_live_dict(self):
        totals = ai_layer.usage_totals()
        totals["calls"] = 999
        self.assertEqual(ai_layer.usage_totals()["calls"], 0,
                         "usage_totals() handed out the mutable internal dict")


class TestNoBehaviourChanged(unittest.TestCase):
    """Tier 3.1's plumbing-only claim, asserted rather than stated."""

    def test_a_real_call_site_still_returns_model_text_and_still_guards(self):
        from tax_engine import SalaryStructure
        structure = SalaryStructure(
            ctc=2_000_000, basic=600_000, hra=500_000, lta=100_000,
            special_allowance=560_000, employer_pf=240_000,
            employer_nps=0, nps_opted=False)

        response = Mock()
        response.content = [Mock(text="This structure sets Basic below the 50% "
                                      "floor the Code on Wages 2025 requires.")]
        response.usage = Mock(input_tokens=1, output_tokens=1)
        with patch.object(ai_layer, "_client",
                          Mock(messages=Mock(create=Mock(return_value=response)))):
            ok = ai_layer.flag_compliance(structure, rent_paid=300_000)

        response.content = [Mock(text="Basic salary is below 35% of CTC.")]
        with patch.object(ai_layer, "_client",
                          Mock(messages=Mock(create=Mock(return_value=response)))):
            guarded = ai_layer.flag_compliance(structure, rent_paid=300_000)

        self.assertTrue(ok["ai_backed"])
        self.assertFalse(ok["guard_triggered"])
        self.assertTrue(guarded["guard_triggered"])
        self.assertFalse(guarded["ai_backed"])


if __name__ == "__main__":
    unittest.main()
