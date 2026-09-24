"""
Citation forms the grammar does not parse (CITATION_FORM_COVERAGE_DESIGN.md).

Guard-row item (2) was carried as one narrow gap. Measuring it at `ee76e4d`
found four defects, three of them fail-open, and every row in the design's §1
tables is pinned here.

The defect in one line: `_CITATION_REFERENCE` is the single definition of what a
citation IS, so a form outside its keyword list is not "a citation we cannot
match" — it is not a citation at all, and `_citations_unsupplied` has nothing to
test. `under Section 14` is rejected as fabricated; `u/s 14` is served.

Committed knowingly RED. Every test named below_is_red fails against the
grammar as it stands; that is the defect, not a broken test. The controls beside
them pass now and must keep passing, because a grammar that recognised
everything would satisfy the red ones and break these.
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import ai_layer
from ai_layer import (_citations_unsupplied, _grounded_figures,
                      _numbers_ungrounded, answer_query, explain_result)
from optimizer import optimize

# A rationale whose ONLY grounded figure is 14.0 — the employer-NPS cap
# percentage. There is no Section 14 governing that cap, so "u/s 14" is a
# fabricated authority whose digits coincide with a real figure. That
# coincidence is the whole point: the figure check cannot see it, so only the
# membership check can.
NPS_RATIONALE = ("Employer NPS exceeds the 14% cap under Section 124 "
                 "(formerly Section 80CCD(2)).")

# Verbatim what answer_query() supplies when HRA and employer NPS both apply.
SUPPLIED = [
    "Section 11, read with Schedule III, Table Sl. No. 11 (formerly Section 10(13A))",
    "Section 392 (formerly Section 192)",
    "Section 124 (formerly Section 80CCD(2))",
]
ALLOWED = {2000000.0, 600000.0, 145000.0}


def _rationale_site_serves(line):
    """
    The rationale/guardrail/negotiate call sites, exactly: skip_below=0, the
    rationale as both grounding and citations, and the two checks OR-ed the way
    flag_compliance ORs them.
    """
    grounded = _grounded_figures(NPS_RATIONALE)
    return not (_numbers_ungrounded(line, grounded, skip_below=0,
                                    citations=[NPS_RATIONALE])
                or _citations_unsupplied(line, [NPS_RATIONALE]))


def _query_site_serves(reply):
    """answer_query's guard, exactly: the default skip_below=100 plus membership."""
    return not (_numbers_ungrounded(reply, ALLOWED, citations=SUPPLIED)
                or _citations_unsupplied(reply, SUPPLIED))


class TestTheGrammarSeesOnlyOneSpelling(unittest.TestCase):
    """Design §1.1. The same fabrication, caught in one spelling and served in
    another, is the defect in its clearest form."""

    def test_control_the_parsed_spelling_is_caught(self):
        self.assertFalse(_rationale_site_serves(
            "Your NPS breaches the cap under Section 14."))

    def test_control_a_legitimate_line_is_still_served(self):
        # If this ever fails, a widened grammar has started rejecting real
        # output, which is the §4.4.1 defect coming back by the front door.
        self.assertTrue(_rationale_site_serves(
            "Your employer NPS breaches the 14% cap."))

    def test_control_the_supplied_section_is_still_served(self):
        self.assertTrue(_rationale_site_serves(
            "Your NPS breaches the cap under Section 124."))

    def test_an_abbreviated_fabrication_is_caught_red(self):
        for line in ("Your NPS breaches the cap u/s 14.",
                     "Your NPS breaches the cap under s. 14.",
                     "Your NPS breaches the cap under sec. 14.",
                     "Your NPS breaches the cap under ss. 14."):
            with self.subTest(line=line):
                self.assertFalse(_rationale_site_serves(line))

    def test_an_abbreviated_supplied_reference_is_served_red(self):
        # The fail-closed mirror: 124 is read as a figure, so a correct answer
        # citing what it was given is thrown away. Invisible, because the
        # fallback looks like a normal answer.
        for line in ("Your NPS breaches the cap u/s 124.",
                     "Your NPS breaches the cap under s. 124."):
            with self.subTest(line=line):
                self.assertTrue(_rationale_site_serves(line))


class TestBelowOneHundredMembershipIsTheOnlyProtection(unittest.TestCase):
    """
    Design §1.2. At answer_query skip_below=100, so the figure check skips
    small numbers entirely. A low-numbered citation can therefore only be
    rejected by membership, and membership cannot see an abbreviation.
    """

    def test_control_the_parsed_spelling_is_caught(self):
        self.assertFalse(_query_site_serves("You can also claim Section 80C for your PF."))
        self.assertFalse(_query_site_serves("Your standard deduction falls under Section 16."))

    def test_an_abbreviated_low_section_is_caught_red(self):
        for reply in ("You can also claim s. 80C for your PF.",
                      "Deductible u/s 16.",
                      "Your standard deduction falls under sec. 16."):
            with self.subTest(reply=reply):
                self.assertFalse(_query_site_serves(reply))

    def test_a_grounded_figure_does_not_carry_a_fabricated_citation_red(self):
        # The figure is real and the citation is invented. Rs 145000 is
        # traceable; s. 16 is not, and nothing checks it.
        self.assertFalse(_query_site_serves(
            "Your tax is Rs 145000, claimable under s. 16."))


class TestPlurals(unittest.TestCase):
    """
    Design §1.2 and D-C2. "Sections 392 and 124" names two supplied references
    and is currently parsed as neither.
    """

    def test_a_supplied_plural_is_served_red(self):
        self.assertTrue(_query_site_serves("Sections 392 and 124 apply to your pay."))

    def test_a_fabricated_plural_is_seen_as_citing_something_red(self):
        # Today this returns False for the WRONG reason — no reference is seen
        # at all. The figure check happens to reject the line because 394 and
        # 395 are ungrounded, so the reply is refused; that is the right outcome
        # from the wrong mechanism, and it disappears the moment the digits are
        # grounded. Assert the mechanism, not just the outcome.
        self.assertTrue(_citations_unsupplied("Sections 394 and 395 apply.", SUPPLIED))


class TestWhatMustNotBecomeACitation(unittest.TestCase):
    """
    D-C1's risk and D-C4's boundary. A wider keyword list must not turn
    ordinary prose into an exemption, and a bare number must stay a figure.
    These pass today and must still pass after the grammar widens — they are
    the reason the widening cannot be done by loosening the pattern.
    """

    def test_seconds_are_not_a_section(self):
        # "sec." abbreviates seconds. Nothing here was supplied, so if this
        # parsed as a reference the line would be reported as citing something
        # unsupplied — a new false rejection introduced by the fix.
        self.assertFalse(_citations_unsupplied(
            "The page loads in 30 sec. 5 at most.", SUPPLIED))

    def test_plural_expansion_does_not_swallow_the_words_after_it(self):
        # "[0-9A-Z]+" under IGNORECASE matches ordinary words, so an unguarded
        # plural expansion reads "Sections 392 and the rest" as citing Section
        # THE and rejects the line — the fix introducing a new false rejection.
        # Measured while writing step 3; pinned here because a measurement in a
        # commit message does not survive the next edit.
        self.assertFalse(_citations_unsupplied(
            "Sections 392 and 192 are the ones that matter.", SUPPLIED))
        self.assertFalse(_citations_unsupplied(
            "Sections 392 and the rest are irrelevant.", SUPPLIED))

    def test_a_bare_designator_stays_a_figure(self):
        # D-C4, deliberate: recognising this would mean treating every number
        # as a possible citation.
        self.assertTrue(_numbers_ungrounded("392 governs salary TDS.", ALLOWED,
                                            citations=SUPPLIED))

    def test_a_designator_fused_into_a_number_is_not_a_reference(self):
        for text in ("Under s. 392,000.", "Under u/s 392.5."):
            with self.subTest(text=text):
                self.assertTrue(_numbers_ungrounded(text, ALLOWED, citations=SUPPLIED))


class TestAnswerQueryEndToEnd(unittest.TestCase):
    """The unit assertions above, through the real answer_query: recompute,
    applicable_sections, guard and fallback all real, only the client mocked."""

    CONTEXT = {"recommended_regime": "new", "recommended_tax": 88140.0,
               "annual_saving": 36972.0}

    def _ask(self, reply):
        response = Mock()
        response.content = [Mock(text=reply)]
        with patch("ai_layer._client", Mock(messages=Mock(create=Mock(return_value=response)))):
            return answer_query("why did the new regime win?", self.CONTEXT,
                                ctc=1_800_000, rent_paid=400_000, city="metro",
                                nps_opted=True)

    def test_control_a_parsed_fabrication_falls_back(self):
        result = self._ask("You can also claim Section 80C for your PF contributions.")
        self.assertTrue(result["guard_triggered"])
        self.assertFalse(result["ai_backed"])

    def test_an_abbreviated_fabrication_falls_back_red(self):
        result = self._ask("You can also claim s. 80C for your PF contributions.")
        self.assertTrue(result["guard_triggered"])
        self.assertFalse(result["ai_backed"])

    def test_control_a_supplied_citation_is_still_served(self):
        reply = "Salary TDS on your pay is deducted under Section 392 (formerly Section 192)."
        result = self._ask(reply)
        self.assertFalse(result["guard_triggered"])
        self.assertEqual(result["answer"], reply)


class TestExplainResultCitesLawWithNothingCheckingIt(unittest.TestCase):
    """
    Design §1.3, D-C3. explain_result supplies no sections and passes no
    citations, so every citation it writes is unsupplied by construction — and
    nothing looks for one. Its prompt forbids new figures and says nothing
    about statutory authority. This site does not need an exotic form to fail:
    the ordinary spelling is served, because 16 is below 100.
    """

    @classmethod
    def setUpClass(cls):
        cls.opt = optimize(ctc=1_800_000, rent_paid=540_000, city="metro",
                           nps_opted=True)

    def _explain(self, text):
        response = Mock()
        response.content = [Mock(text=text)]
        with patch("ai_layer._client", Mock(messages=Mock(create=Mock(return_value=response)))):
            return explain_result(self.opt, rent_paid=540_000, city="metro")

    def test_control_a_citation_free_explanation_is_served(self):
        result = self._explain(
            "The new regime wins because your deductions are smaller than the "
            "rate cut is worth.")
        self.assertTrue(result["ai_backed"])
        self.assertFalse(result["guard_triggered"])

    def test_an_explanation_that_cites_a_section_is_refused_red(self):
        for text in ("The new regime wins because the standard deduction under "
                     "Section 16 is higher.",
                     "The new regime wins; see s. 16 for the deduction."):
            with self.subTest(text=text):
                result = self._explain(text)
                self.assertTrue(result["guard_triggered"], result)
                self.assertFalse(result["ai_backed"])

    def test_the_prompt_forbids_citing_statute_red(self):
        # The guard is the enforcement; the prompt is what stops the model
        # producing it in the first place. Both, or the fallback becomes the
        # normal path for a question the model answers well.
        prompt = ai_layer.EXPLAINER_SYSTEM_PROMPT.lower()
        self.assertTrue("section" in prompt or "statut" in prompt, prompt)


if __name__ == "__main__":
    unittest.main()
