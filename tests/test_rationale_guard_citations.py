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
from unittest.mock import Mock, patch

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


class TestCitationsUnsuppliedHelper(unittest.TestCase):
    """
    Step 6a (design §4.7): the membership check, as a unit. It is structural at
    this step, with no call site yet. Every "unsupplied" case has a "supplied"
    partner, because a helper returning True for any citation would pass the
    first half alone.
    """

    R1 = _rule_rationale("R1")
    R5 = _rule_rationale("R5")

    def test_a_supplied_reference_is_not_flagged(self):
        for text in ("It is a perquisite under Section 17(1)(h).",
                     "It is a perquisite under Section 17(1)(h) (formerly Section 17(2)(vii)).",
                     "It is a perquisite under section 17(1)(h)."):
            with self.subTest(text=text):
                self.assertFalse(ai_layer._citations_unsupplied(text, [self.R5]))

    def test_a_reference_never_supplied_is_flagged(self):
        for text in ("It is a perquisite under Section 17(1)(i).",
                     "It is a perquisite under Section 999."):
            with self.subTest(text=text):
                self.assertTrue(ai_layer._citations_unsupplied(text, [self.R5]))

    def test_a_citation_made_of_a_real_figures_digits_is_flagged(self):
        # The case the figure check cannot see: 50 is R1's real floor, so
        # "Section 50" passes the figure check. R1 supplies no reference at all.
        self.assertTrue(ai_layer._citations_unsupplied(
            "Basic salary is below the 50% floor set by Section 50.", [self.R1]))
        self.assertFalse(ai_layer._numbers_ungrounded(
            "Basic salary is below the 50% floor set by Section 50.",
            _grounded_figures(self.R1), skip_below=0, citations=[self.R1]))

    def test_text_with_no_reference_is_not_flagged(self):
        self.assertFalse(ai_layer._citations_unsupplied(
            "Your contributions exceed the limit by 1 lakh.", [self.R5]))

    def test_nothing_supplied_flags_any_reference(self):
        self.assertTrue(ai_layer._citations_unsupplied("Under Section 17(1)(h).", []))
        self.assertFalse(ai_layer._citations_unsupplied("No citation here.", []))

    def test_an_unparsed_form_is_outside_this_check(self):
        # Design §4.7 limit, pinned so a widened grammar is a visible decision.
        self.assertFalse(ai_layer._citations_unsupplied(
            "It is a perquisite under s. 17(1)(i).", [self.R5]))

    def test_a_bare_string_is_rejected_rather_than_silently_supplying_nothing(self):
        with self.assertRaises(TypeError):
            ai_layer._citations_unsupplied("Under Section 17(1)(h).", self.R5)


def _reply(*lines):
    response = Mock()
    response.content = [Mock(text="\n".join(lines))]
    return patch("ai_layer._client", Mock(messages=Mock(create=Mock(return_value=response))))


class _Guards:
    """Single-flag fixtures, so any rejection is about citation digits and
    never about the cross-flag scope fixed in step 3."""

    # PF + NPS Rs 8.4L trips R5 alone: basic 60%, LTA 0, PF present, special > 0.
    R5_ONLY = SalaryStructure(ctc=4_000_000, basic=2_400_000, hra=0, lta=0,
                              special_allowance=760_000, employer_pf=240_000,
                              employer_nps=600_000, nps_opted=True)
    # PF + NPS Rs 8.4L fails epfo_ceiling alone; NPS within 14% of Rs 36L basic.
    EPFO_ONLY = SalaryStructure(ctc=6_000_000, basic=3_600_000, hra=0, lta=0,
                                special_allowance=1_560_000, employer_pf=340_000,
                                employer_nps=500_000, nps_opted=True)
    # Employer NPS Rs 2.5L over the Rs 1.4L cap fails 80ccd2_cap alone.
    NPS_ONLY = SalaryStructure(ctc=2_000_000, basic=1_000_000, hra=0, lta=0,
                               special_allowance=630_000, employer_pf=120_000,
                               employer_nps=250_000, nps_opted=True)
    BAND = ("new", 1_000_000, 9_000_000)

    R5_OK = "The excess over Rs 7.5L is a taxable perquisite under Section 17(1)(h)."
    EPFO_OK = ("Aggregate employer PF + NPS of Rs 840,000 exceeds the Rs 750,000/year "
               "ceiling; the excess is taxable under Section 17(1)(h).")
    NPS_OK = ("Employer NPS of Rs 250,000 exceeds the Section 124 cap (formerly "
              "Section 80CCD(2)) of 14% of basic (Rs 140,000).")

    def compliance(self, line):
        with _reply(line):
            return ai_layer.flag_compliance(self.R5_ONLY, rent_paid=0)

    def guardrail(self, structure, line):
        with _reply(line):
            return ai_layer.evaluate_band_guardrail(structure, *self.BAND)

    def assertServed(self, result):
        self.assertFalse(result["guard_triggered"])
        self.assertTrue(result["ai_backed"])

    def assertRejected(self, result):
        self.assertTrue(result["guard_triggered"])
        self.assertFalse(result["ai_backed"])


class TestTheGuardsNoLongerGroundFiguresInCitationDigits(_Guards, unittest.TestCase):
    """Step 5, severity 3 (design §1.1): each guard grounds a line in
    _grounded_figures(its rationale) and exempts that rationale's references."""

    def test_the_fixtures_fail_exactly_one_flag_each(self):
        self.assertEqual([f["rule_id"] for f in ai_layer._check_rules(self.R5_ONLY, 0)], ["R5"])
        with patch("ai_layer._client", None):
            for structure, check_id in ((self.EPFO_ONLY, "epfo_ceiling"), (self.NPS_ONLY, "80ccd2_cap")):
                checks = ai_layer.evaluate_band_guardrail(structure, *self.BAND)["checks"]
                self.assertEqual([c["id"] for c in checks if not c["passed"]], [check_id])

    def test_R5_quoting_its_citation_is_served(self):
        self.assertServed(self.compliance(self.R5_OK))

    def test_R5_quoting_its_citation_and_the_former_one_is_served(self):
        self.assertServed(self.compliance(
            "The excess over Rs 7.5L is a taxable perquisite under Section 17(1)(h) "
            "(formerly Section 17(2)(vii))."))

    def test_R5_figures_made_of_its_section_digits_are_rejected(self):
        for line in ("Your contributions exceed the limit by 1 lakh.",
                     "Your contributions exceed the limit by 2 lakh.",
                     "You are 17 thousand rupees over the ceiling."):
            with self.subTest(line=line):
                self.assertRejected(self.compliance(line))

    def test_epfo_quoting_its_citation_is_served(self):
        self.assertServed(self.guardrail(self.EPFO_ONLY, self.EPFO_OK))

    def test_epfo_figure_made_of_its_section_digits_is_rejected(self):
        self.assertRejected(self.guardrail(
            self.EPFO_ONLY, "Aggregate employer PF + NPS exceeds the ceiling by 1 lakh."))

    def test_nps_cap_quoting_its_citations_is_served(self):
        self.assertServed(self.guardrail(self.NPS_ONLY, self.NPS_OK))

    def test_nps_cap_figures_made_of_its_section_digits_are_rejected(self):
        for line in ("Employer NPS of Rs 250,000 exceeds the cap of 2% of basic.",
                     "Employer NPS is Rs 124 over the cap."):
            with self.subTest(line=line):
                self.assertRejected(self.guardrail(self.NPS_ONLY, line))


class TestSectionsNeverSuppliedAreStillChecked(_Guards, unittest.TestCase):
    """
    The distinguishing test from review (design §4.5, §5.1). The exemption is
    for references present in THIS flag's rationale, never for anything shaped
    like a citation. An unconditional strip would pass every line here.
    """

    def test_R5_sections_it_never_supplied_are_rejected(self):
        for section in ("Section 17(1)(i)", "Section 17(2)(viia)", "Section 999"):
            with self.subTest(section=section):
                self.assertRejected(self.compliance(
                    f"The excess over Rs 7.5L is a taxable perquisite under {section}."))

    def test_epfo_section_it_never_supplied_is_rejected(self):
        self.assertRejected(self.guardrail(
            self.EPFO_ONLY,
            "Aggregate employer PF + NPS of Rs 840,000 exceeds the Rs 750,000/year "
            "ceiling; the excess is taxable under Section 17(1)(i)."))

    def test_an_abbreviated_citation_the_grammar_cannot_parse_fails_closed(self):
        # Design §5.4, a cost accepted on purpose: "s. 17(1)(h)" is not a
        # recognised reference, so its 17 and 1 are checked, and they are no
        # longer grounded. If this starts passing, the grammar widened; that
        # should be a decision, not a side effect.
        self.assertRejected(self.compliance(
            "The excess over Rs 7.5L is a taxable perquisite under s. 17(1)(h)."))


class TestAFabricatedCitationIsRejectedEvenWhenItsDigitsAreReal(_Guards, unittest.TestCase):
    """
    Step 6b, severity 4 (design §1.1, §4.7). Both guards now also reject a line
    that cites a reference its own rationale does not. On a743339 each line
    below was served: its digits are real figures of the same flag, so the
    figure check alone could not see the fabrication.
    """

    # Basic 45% of CTC trips R1 alone (rent is supplied, so R3 does not fire).
    R1_ONLY = SalaryStructure(ctc=2_000_000, basic=900_000, hra=400_000, lta=0,
                              special_allowance=592_000, employer_pf=108_000,
                              employer_nps=0, nps_opted=False)

    def r1(self, line):
        with _reply(line):
            return ai_layer.flag_compliance(self.R1_ONLY, rent_paid=300_000)

    def test_the_R1_fixture_triggers_R1_alone(self):
        self.assertEqual([f["rule_id"] for f in ai_layer._check_rules(self.R1_ONLY, 300_000)], ["R1"])

    def test_R1_citing_a_section_built_from_its_own_floor_is_rejected(self):
        self.assertRejected(self.r1("Basic salary is below the 50% floor set by Section 50."))

    def test_control_R1_restating_its_floor_without_a_citation_is_served(self):
        self.assertServed(self.r1("This structure sets Basic below the 50% floor the Code on Wages 2025 requires."))

    def test_nps_cap_citing_a_section_built_from_its_own_rate_is_rejected(self):
        self.assertRejected(self.guardrail(
            self.NPS_ONLY, "Employer NPS of Rs 250,000 exceeds the Section 14 cap of 14% of basic."))

    def test_control_a_supplied_citation_in_other_case_is_served(self):
        self.assertServed(self.compliance(
            "The excess over Rs 7.5L is a taxable perquisite under section 17(1)(h)."))


if __name__ == "__main__":
    unittest.main()
