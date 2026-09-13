"""
The numeric guard's citation-token exemption (QUERY_GUARD_CITATION_DESIGN.md).

answer_query() hands the model statutory references, then guards its reply with
_numbers_ungrounded(). Before this, the guard read "Section 392" as the figure
392 and rejected every answer that cited what it had been given — failing
closed, so invisibly.

Every test that shows a reference is exempt has a partner showing that
something which only LOOKS like it is not. An exemption proven in one direction
only is exactly what a guard that exempts everything would also pass.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ai_layer import _numbers_ungrounded

# Verbatim what answer_query() supplies when HRA and employer NPS both apply.
SUPPLIED = [
    "Section 11, read with Schedule III, Table Sl. No. 11 (formerly Section 10(13A))",
    "Section 392 (formerly Section 192)",
    "Section 124 (formerly Section 80CCD(2))",
]
ALLOWED = {2000000.0, 600000.0, 145000.0}


class TestTheDefaultIsUnchanged(unittest.TestCase):
    """Design §3.3: every call site that passes no citations behaves as before."""

    def test_without_citations_a_section_number_is_still_a_figure(self):
        text = "Salary TDS is deducted under Section 392."
        self.assertTrue(_numbers_ungrounded(text, ALLOWED))
        self.assertTrue(_numbers_ungrounded(text, ALLOWED, citations=()))
        self.assertTrue(_numbers_ungrounded(text, ALLOWED, citations=[]))


class TestSuppliedReferencesAreNotFigures(unittest.TestCase):

    def test_a_reply_citing_supplied_sections_passes(self):
        for text in (
            "Salary TDS is deducted under Section 392.",
            # The system prompt's own example wording, exactly.
            "Salary TDS is deducted under Section 392 (formerly Section 192).",
            "Your employer NPS falls under Section 124 (formerly Section 80CCD(2)).",
            "Your employer NPS deduction falls under Section 124.",
            "section 124 applies.",
        ):
            with self.subTest(text=text):
                self.assertFalse(_numbers_ungrounded(text, ALLOWED, citations=SUPPLIED))

    def test_a_grounded_figure_beside_a_supplied_reference_passes(self):
        text = "Your total tax is Rs 145000, with TDS under Section 392."
        self.assertFalse(_numbers_ungrounded(text, ALLOWED, citations=SUPPLIED))


class TestWhatOnlyLooksLikeASuppliedReferenceIsStillChecked(unittest.TestCase):

    def test_an_unsupplied_section_is_still_rejected(self):
        # The case option (a), strip-every-citation, gets wrong (design §2.1).
        self.assertTrue(_numbers_ungrounded(
            "This falls under Section 394.", ALLOWED, citations=SUPPLIED))

    def test_a_bare_number_equal_to_a_supplied_designator_is_still_a_figure(self):
        # The case option (b), whitelist-the-values, gets wrong (design §2.2).
        self.assertTrue(_numbers_ungrounded(
            "You save Rs 392 a year.", ALLOWED, citations=SUPPLIED))

    def test_an_ungrounded_figure_beside_a_supplied_reference_is_still_rejected(self):
        # Only the reference is removed, never its neighbours.
        self.assertTrue(_numbers_ungrounded(
            "Rs 1,24,000 is deductible under Section 124.", ALLOWED, citations=SUPPLIED))

    def test_a_designator_fused_into_a_larger_number_is_not_a_reference(self):
        for text in ("Section 392,000 applies.", "Section 392.5 applies.",
                     "Subsection 392 applies."):
            with self.subTest(text=text):
                self.assertTrue(_numbers_ungrounded(text, ALLOWED, citations=SUPPLIED))

    def test_a_shorter_supplied_reference_does_not_exempt_a_longer_one(self):
        # skip_below=0 so the small tokens are observable. "Section 80CCD" was
        # supplied; "Section 80CCD(2)" was not, so its 80 and 2 are checked.
        text = "Under Section 80CCD(2)."
        self.assertTrue(_numbers_ungrounded(
            text, set(), skip_below=0, citations=["Section 80CCD"]))
        self.assertFalse(_numbers_ungrounded(
            text, set(), skip_below=0, citations=["Section 80CCD(2)"]))

    def test_the_named_residual_rejections_are_kept(self):
        # Design §4: kept on purpose. If either starts passing, the grammar
        # widened, and that is a decision to make explicitly.
        for text in ("Sections 392 and 192 apply.",
                     "Under Section 392 of the Income-tax Act, 2025."):
            with self.subTest(text=text):
                self.assertTrue(_numbers_ungrounded(text, ALLOWED, citations=SUPPLIED))

    def test_a_bare_string_is_rejected_rather_than_silently_exempting_nothing(self):
        with self.assertRaises(TypeError):
            _numbers_ungrounded("Under Section 392.", ALLOWED,
                                citations="Section 392 (formerly Section 192)")


if __name__ == "__main__":
    unittest.main()
