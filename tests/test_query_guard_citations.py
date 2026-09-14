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

import json
import os
import re
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ai_layer import _numbers_ungrounded, answer_query

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


class TestAnswerQueryServesAnswersThatCiteWhatItSupplied(unittest.TestCase):
    """
    End to end through answer_query(): only the model client is mocked. The
    recompute, the applicable_sections list, the guard and the fallback are all
    real. Each test also reads back what the model was actually SENT, so a pass
    cannot come from a citation that was never supplied.
    """

    CONTEXT = {"recommended_regime": "new", "recommended_tax": 88140.0, "annual_saving": 36972.0}

    def _ask(self, reply, nps_opted=True, context=None):
        response = Mock()
        response.content = [Mock(text=reply)]
        create = Mock(return_value=response)
        with patch("ai_layer._client", Mock(messages=Mock(create=create))):
            result = answer_query("why did the new regime win?", context or self.CONTEXT,
                                  ctc=1_800_000, rent_paid=400_000, city="metro",
                                  nps_opted=nps_opted)
        sent = json.loads(create.call_args.kwargs["messages"][0]["content"])
        return result, sent["context"]["applicable_sections"]

    def test_the_prompts_own_example_wording_is_served_not_replaced(self):
        # Before this change: ai_backed False, guard_triggered True.
        reply = "Salary TDS on your pay is deducted under Section 392 (formerly Section 192)."
        result, supplied = self._ask(reply)
        self.assertIn("Section 392 (formerly Section 192)", supplied)
        self.assertEqual(result, {"answer": reply, "ai_backed": True,
                                  "recalculated": False, "guard_triggered": False})

    def test_a_conditionally_supplied_citation_is_served_when_it_applies(self):
        reply = "Your employer NPS contribution is deductible under Section 124 (formerly Section 80CCD(2))."
        result, supplied = self._ask(reply, nps_opted=True)
        self.assertIn("Section 124 (formerly Section 80CCD(2))", supplied)
        self.assertTrue(result["ai_backed"])
        self.assertFalse(result["guard_triggered"])

    def test_the_same_citation_falls_back_when_it_was_not_supplied_for_this_user(self):
        # Without NPS, no employer NPS in either regime, so Section 124 is not
        # supplied — and the identical reply is an unsupplied reference. This
        # is what ties the exemption to the call, not to a fixed list.
        reply = "Your employer NPS contribution is deductible under Section 124 (formerly Section 80CCD(2))."
        result, supplied = self._ask(reply, nps_opted=False)
        self.assertFalse(any("Section 124" in s for s in supplied))
        self.assertFalse(result["ai_backed"])
        self.assertTrue(result["guard_triggered"])
        self.assertIn("88,140", result["answer"])

    def test_an_invented_section_still_falls_back(self):
        result, _ = self._ask("This is governed by Section 394 of the Act.")
        self.assertFalse(result["ai_backed"])
        self.assertTrue(result["guard_triggered"])

    def test_an_ungrounded_figure_next_to_a_supplied_citation_still_falls_back(self):
        result, _ = self._ask("Under Section 392, your TDS works out to about 4,17,000.")
        self.assertFalse(result["ai_backed"])
        self.assertTrue(result["guard_triggered"])
        self.assertNotIn("4,17,000", result["answer"])

    def test_citations_in_the_request_context_cannot_buy_an_exemption(self):
        # /api/query passes the request body's context straight in. The list
        # the guard exempts against must be the one answer_query built.
        forged = dict(self.CONTEXT, applicable_sections=["Section 555"])
        result, supplied = self._ask("This falls under Section 555.", context=forged)
        self.assertNotIn("Section 555", supplied)
        self.assertFalse(result["ai_backed"])
        self.assertTrue(result["guard_triggered"])


class TestAnswerQueryRejectsSectionsItNeverSupplied(TestAnswerQueryServesAnswersThatCiteWhatItSupplied):
    """
    RATIONALE_GUARD_CITATION_DESIGN.md §8 step 8, and the gap §7 of this
    design left open. Below 100 the figure check skips numbers, so an invented
    low section passed it. Both lines below were served as model text on
    8e7fab0. The prompt already forbids citing anything not in
    applicable_sections; this enforces it.

    Subclasses the class above only to reuse _ask. Its tests also run again
    under this name, so they still hold with the membership check in place.
    """

    def test_low_sections_never_supplied_are_rejected(self):
        for reply, reference in (("You can also claim Section 80C for your PF contributions.", r"\bSection 80C\b"),
                                 ("Your standard deduction falls under Section 16.", r"\bSection 16\b")):
            with self.subTest(reply=reply):
                result, supplied = self._ask(reply)
                # Whole reference, not substring: "80C" is a substring of the
                # supplied "80CCD(2)", which is a different section.
                self.assertFalse(any(re.search(reference, s) for s in supplied), supplied)
                self.assertTrue(result["guard_triggered"])
                self.assertFalse(result["ai_backed"])

    def test_control_every_reference_in_a_supplied_multi_part_citation_is_served(self):
        # "Section 11", "Schedule III" and "Sl. No. 11" are three references in
        # one supplied string. All three must count as supplied.
        reply = ("Your HRA is exempt under Section 11, read with Schedule III, "
                 "Table Sl. No. 11 (formerly Section 10(13A)).")
        result, supplied = self._ask(reply)
        self.assertIn("Section 11, read with Schedule III, Table Sl. No. 11 (formerly Section 10(13A))", supplied)
        self.assertFalse(result["guard_triggered"])
        self.assertTrue(result["ai_backed"])


if __name__ == "__main__":
    unittest.main()
