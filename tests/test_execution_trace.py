"""
trace_guardrail_stage() (execution_trace.py): the POLICY_GATE stage that
/api/guardrail returns to users. Nothing tested it before this file.

Its passing message was the last user-visible text still citing the NPS cap's
former section without a keyword, "(formerly 80CCD(2))", after the guardrail's
own rationale moved to "(formerly Section 80CCD(2))" in 5060498
(RATIONALE_GUARD_CITATION_DESIGN.md §4.2). The two described the same check
differently.
"""

import os
import re
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import ai_layer
from execution_trace import trace_guardrail_stage
from tax_engine import SalaryStructure


def _guardrail(structure, band):
    with patch("ai_layer._client", None):
        return ai_layer.evaluate_band_guardrail(structure, "new", *band)


PASSING = SalaryStructure(ctc=2_000_000, basic=1_000_000, hra=0, lta=0,
                          special_allowance=780_000, employer_pf=120_000,
                          employer_nps=100_000, nps_opted=True)
FAILING = SalaryStructure(ctc=2_000_000, basic=1_000_000, hra=0, lta=0,
                          special_allowance=630_000, employer_pf=120_000,
                          employer_nps=250_000, nps_opted=True)


class TestPolicyGateTrace(unittest.TestCase):

    def test_the_passing_message_cites_the_former_section_with_its_keyword(self):
        guardrail = _guardrail(PASSING, (1_000_000, 3_000_000))
        self.assertEqual(guardrail["verdict"], "pass")
        stage = trace_guardrail_stage(guardrail)
        self.assertEqual(stage["stage"], "POLICY_GATE")
        self.assertIn("(formerly Section 80CCD(2))", stage["message"])
        self.assertNotIn("(formerly 80CCD(2))", stage["message"])

    def test_the_passing_message_has_no_designator_the_citation_grammar_cannot_see(self):
        # Same shape check as the rationale coverage test in
        # test_rationale_guard_citations.py, applied to this message.
        message = trace_guardrail_stage(_guardrail(PASSING, (1_000_000, 3_000_000)))["message"]
        outside = ai_layer._CITATION_REFERENCE.sub(" ", message)
        self.assertEqual(re.findall(r"\b\d+[A-Za-z]*(?:\([0-9A-Za-z]+\))+", outside), [])

    def test_the_flagged_message_is_built_from_the_failing_checks_own_messages(self):
        guardrail = _guardrail(FAILING, (1_000_000, 3_000_000))
        self.assertEqual(guardrail["verdict"], "flag")
        message = trace_guardrail_stage(guardrail)["message"]
        failing = [c for c in guardrail["checks"] if not c["passed"]]
        self.assertEqual([c["id"] for c in failing], ["80ccd2_cap"])
        self.assertEqual(message, f"Policy gate flagged — {failing[0]['message']}")


if __name__ == "__main__":
    unittest.main()
