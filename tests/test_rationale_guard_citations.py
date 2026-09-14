"""
Citation digits are not grounding (RATIONALE_GUARD_CITATION_DESIGN.md §4.5,
§8 steps 4a onwards).

A rationale is both the source of the figures a rephrasing may restate AND the
source of the citations handed to the model. Built straight from the text, R5's
allowed set was {7.5, 17, 1, 2}. The last three are section digits, and they
let an invented "exceed the limit by 1 lakh" through.

_grounded_figures() removes a rationale's own references before extracting
figures. These tests pin what it keeps as well as what it drops: a helper that
returned an empty set would satisfy every "drops the citation" assertion.
"""

import os
import re
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import ai_layer
import compliance_rules
from ai_layer import _extract_numbers, _grounded_figures
from tax_engine import SalaryStructure


def _rule_rationale(rule_id):
    return next(r.rationale for r in compliance_rules.RULES if r.id == rule_id)


def _guardrail_rationales():
    """Every guardrail rationale branch, rendered by the real function: all
    three checks passing, then all three failing."""
    passing = SalaryStructure(ctc=2_000_000, basic=1_000_000, hra=0, lta=0,
                              special_allowance=780_000, employer_pf=120_000,
                              employer_nps=100_000, nps_opted=True)
    failing = SalaryStructure(ctc=6_000_000, basic=1_000_000, hra=0, lta=0,
                              special_allowance=4_160_000, employer_pf=340_000,
                              employer_nps=500_000, nps_opted=True)
    out = {}
    with patch("ai_layer._client", None):
        for label, structure, band in (("pass", passing, (1_000_000, 3_000_000)),
                                       ("fail", failing, (1_000_000, 2_000_000))):
            result = ai_layer.evaluate_band_guardrail(structure, "new", *band)
            for check in result["checks"]:
                expected = label == "pass"
                assert check["passed"] is expected, (check["id"], label)
                out[f"{check['id']}/{label}"] = check["rationale"]
    return out


class TestGroundedFiguresDropCitationDigits(unittest.TestCase):

    def test_R5_keeps_its_ceiling_and_drops_its_section_digits(self):
        self.assertEqual(_grounded_figures(_rule_rationale("R5")), {7.5})

    def test_the_epfo_guardrail_keeps_its_amounts_and_drops_the_same_citation(self):
        rationale = _guardrail_rationales()["epfo_ceiling/fail"]
        self.assertIn("Section 17(1)(h)", rationale)
        self.assertEqual(_grounded_figures(rationale), {840_000.0, 750_000.0})

    def test_a_keyworded_former_citation_is_dropped(self):
        text = ("Employer NPS of Rs 600,000 exceeds the Section 124 cap (formerly "
                "Section 80CCD(2)) of 14% of basic (Rs 280,000) for the new regime.")
        self.assertEqual(_grounded_figures(text), {600_000.0, 14.0, 280_000.0})

    def test_a_former_citation_without_its_keyword_keeps_its_digits(self):
        # Why step 4b changes the 80ccd2_cap text and does NOT add "formerly"
        # to the grammar (design §4.2). An unrecognised form keeps the old
        # behaviour: its digits stay grounded.
        text = ("Employer NPS of Rs 600,000 exceeds the Section 124 cap (formerly "
                "80CCD(2)) of 14% of basic (Rs 280,000) for the new regime.")
        self.assertEqual(_grounded_figures(text), {600_000.0, 80.0, 2.0, 14.0, 280_000.0})


class TestGroundedFiguresKeepRealFigures(unittest.TestCase):

    def test_rules_without_citations_are_unchanged(self):
        for rule_id, expected in (("R2", {6.0}), ("R3", set()), ("R4", {10.0}), ("R6", set())):
            with self.subTest(rule=rule_id):
                self.assertEqual(_grounded_figures(_rule_rationale(rule_id)), expected)

    def test_R1_keeps_2025_because_years_are_deferred(self):
        # Decision 3 (design §7): no year mechanism. R1's text says 2025 and its
        # instrument record says 2019, and the only safe mechanism is a no-op
        # until the CA rules. If this starts dropping 2025, a year mechanism
        # was built without that decision.
        self.assertEqual(_grounded_figures(_rule_rationale("R1")), {50.0, 2025.0})

    def test_a_figure_sharing_a_citations_digits_is_kept(self):
        self.assertEqual(_grounded_figures("Rs 17 is taxable under Section 17(1)(h)."), {17.0})

    def test_the_band_guardrail_keeps_every_amount(self):
        rationale = _guardrail_rationales()["band_cost_neutrality/fail"]
        self.assertEqual(_grounded_figures(rationale), set(_extract_numbers(rationale)))
        self.assertTrue(_grounded_figures(rationale))


class TestTheNpsCapRationaleCitesItsFormerSectionWithAKeyword(unittest.TestCase):
    """
    Step 4b (design §4.2). The rationale said "(formerly 80CCD(2))". Without a
    keyword no grammar can recognise it, so 80 and 2 stayed grounded, and a
    fabricated "cap of 2% of basic" passed. Adding "formerly" as a keyword was
    measured to also parse "(formerly 10% ...)" and exempt a real figure. So
    the TEXT changed to the form every other citation here already uses.
    """

    BRANCHES = ("80ccd2_cap/pass", "80ccd2_cap/fail")

    def test_both_branches_use_the_keyworded_form(self):
        rationales = _guardrail_rationales()
        for branch in self.BRANCHES:
            with self.subTest(branch=branch):
                self.assertIn("(formerly Section 80CCD(2))", rationales[branch])
                self.assertNotIn("(formerly 80CCD(2))", rationales[branch])

    def test_both_branches_ground_only_their_amounts_and_rate(self):
        # Rendered from the fixtures in _guardrail_rationales(): basic Rs 10L,
        # a 14% new-regime cap of Rs 1.4L, employer NPS Rs 1L (pass) and
        # Rs 5L (fail). No 124, 80 or 2.
        rationales = _guardrail_rationales()
        for branch, nps in (("80ccd2_cap/pass", 100_000.0), ("80ccd2_cap/fail", 500_000.0)):
            with self.subTest(branch=branch):
                self.assertEqual(_grounded_figures(rationales[branch]), {nps, 14.0, 140_000.0})

    def test_no_rationale_carries_a_designator_the_grammar_cannot_see(self):
        # Data-driven (design §6 item 2), so a new rule is covered without
        # anyone remembering to add it. Walks every rule, candidates included,
        # so a bare designator is caught before a candidate can be activated.
        # Shape: digits, optional letters, one or more parenthesised parts,
        # e.g. 80CCD(2), 17(1)(h), 10(13A).
        designator = re.compile(r"\b\d+[A-Za-z]*(?:\([0-9A-Za-z]+\))+")
        rationales = {f"rule {r.id}": r.rationale for r in compliance_rules.RULES}
        rationales.update({f"guardrail {k}": v for k, v in _guardrail_rationales().items()})
        for name, text in rationales.items():
            with self.subTest(source=name):
                outside = ai_layer._CITATION_REFERENCE.sub(" ", text)
                self.assertEqual(designator.findall(outside), [],
                                 f"a citation the grammar does not recognise keeps its "
                                 f"digits grounded as figures: {text!r}")


class TestGroundingCanOnlyNarrow(unittest.TestCase):
    """Design §6 item 3, the property behind the §4.5 guarantee."""

    def test_every_rationale_grounds_a_subset_of_its_raw_numbers(self):
        rationales = {f"rule {r.id}": r.rationale for r in compliance_rules.RULES}
        rationales.update({f"guardrail {k}": v for k, v in _guardrail_rationales().items()})
        self.assertEqual(len(rationales), len(compliance_rules.RULES) + 6)
        for name, text in rationales.items():
            with self.subTest(source=name):
                self.assertLessEqual(_grounded_figures(text), set(_extract_numbers(text)))


if __name__ == "__main__":
    unittest.main()
