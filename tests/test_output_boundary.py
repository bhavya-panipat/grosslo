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


# Real requests for the real pipeline (app._build_optimize_response, skip_ai
# False). Measured in OUTPUT_BOUNDARY_GROUNDING_DESIGN.md §1.
R1_ONLY = dict(ctc=2_000_000, rent_paid=300_000, city="metro", nps_opted=False,
               current_extracted={"basic": 900_000, "hra": 400_000, "lta": 0, "employer_pf": 108_000})
R1_R5 = dict(ctc=4_000_000, rent_paid=0, city="metro", nps_opted=True,
             current_extracted={"basic": 1_000_000, "hra": 0, "lta": 0, "employer_pf": 800_000})
NEGOTIATES_NPS = dict(ctc=1_800_000, rent_paid=400_000, city="metro", nps_opted=True,
                      current_extracted={"basic": 720_000, "hra": 288_000, "lta": 0, "employer_pf": 86_400})


def _request_numbers(request):
    return [request["ctc"], request["rent_paid"], *request["current_extracted"].values()]


def _real_response(request, compliance_lines, negotiation=None):
    """
    The real assembled response, with only the model mocked. One reply per call,
    chosen by prompt: each compliance call (one flag per call since
    REPHRASING_ALIGNMENT_DESIGN.md step 2) gets that flag's line, and the
    negotiation call gets negotiation(payload) if given.
    """
    import app as flask_app

    def create(**kwargs):
        system = kwargs.get("system", "")
        payload = json.loads(kwargs["messages"][0]["content"])
        if system == ai_layer.COMPLIANCE_SYSTEM_PROMPT:
            text = "\n".join(compliance_lines[flag["rule_id"]] for flag in payload)
        elif system == ai_layer.EXPLAINER_SYSTEM_PROMPT:
            text = "The recommended regime is cheaper for this structure."
        elif negotiation is not None:
            text = negotiation(payload)
        else:
            text = "You could ask HR whether the structure can be adjusted."
        response = Mock()
        response.content = [Mock(text=text)]
        response.usage = None
        return response

    with patch("ai_layer._client", Mock(messages=Mock(create=Mock(side_effect=create)))):
        response, _ = flask_app._build_optimize_response(
            request["ctc"], request["rent_paid"], request["city"], request["nps_opted"],
            request["current_extracted"], False, skip_ai=False)
    return response


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

    def test_below_100_a_figure_must_match_exactly(self):
        # OUTPUT_BOUNDARY_GROUNDING_DESIGN.md (d). Measured on real output: a
        # basic_pct fraction of 0.6 grounded "1" under +-1. Small counts and
        # percentages are exactly where an unrelated leaf lands within 1 of a
        # fabricated figure.
        payload = {"old_regime_best": {"basic_pct": 0.6},
                   "e": {"ai_backed": True, "t": "There is 1 issue."}}
        self.assertEqual([f.number for f in ob.ungrounded_findings(payload)], [1.0])
        exact = {"metrics": {"rules_triggered": 1},
                 "e": {"ai_backed": True, "t": "There is 1 issue."}}
        self.assertEqual(ob.ungrounded_findings(exact), [])

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
        # OUTPUT_BOUNDARY_GROUNDING_DESIGN.md §3.4. This used to pass only
        # because its payload added "metrics": {"basic_pct": 50, "year": 2025},
        # grounding R1's floor and year by hand. Now it asserts on the real
        # assembled response, where nothing is hand-grounded.
        response = _real_response(R1_ONLY, {"R1": "This structure sets Basic below the 50% "
                                                  "floor the Code on Wages 2025 requires."})
        self.assertTrue(response["compliance"]["ai_backed"])
        self.assertFalse(response["compliance"]["guard_triggered"])
        self.assertEqual(ob.ungrounded_findings(response, extra=_request_numbers(R1_ONLY)), [])

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


class TestAiFieldDeclarations(unittest.TestCase):
    """OUTPUT_BOUNDARY_GROUNDING_DESIGN.md §5 step 3, structural: sections
    declare which fields the model wrote, and the boundary resolves those
    paths. Nothing here imports app, so nothing touches the shared database."""

    def test_the_resolver_follows_every_element_and_indexed_paths(self):
        section = {"ai_fields": ["flags[].message", "checks[1].message", "points"],
                   "flags": [{"message": "a"}, {"message": "b"}],
                   "checks": [{"message": "p"}, {"message": "f"}], "points": "x"}
        self.assertEqual(ob.declared_ai_fields(section, "s"), [
            ("s.flags[0].message", "a"), ("s.flags[1].message", "b"),
            ("s.checks[1].message", "f"), ("s.points", "x")])

    def test_a_declaration_that_resolves_to_nothing_raises(self):
        with self.assertRaises(ValueError):
            ob.declared_ai_fields({"ai_fields": ["flags[].mesage"], "flags": [{"message": "a"}]})

    def test_a_fallback_section_declares_nothing(self):
        # On the fallback path the model wrote nothing, so nothing is declared.
        structure = SalaryStructure(ctc=2_000_000, basic=800_000, hra=0, lta=300_000,
                                    special_allowance=780_000, employer_pf=120_000,
                                    employer_nps=0, nps_opted=False)
        with patch("ai_layer._client", None):
            result = ai_layer.flag_compliance(structure, rent_paid=0)
        self.assertFalse(result["ai_backed"])
        self.assertNotIn("ai_fields", result)

    def test_the_guardrail_declares_only_the_failing_checks_messages(self):
        structure = SalaryStructure(ctc=2_000_000, basic=1_000_000, hra=0, lta=0,
                                    special_allowance=630_000, employer_pf=120_000,
                                    employer_nps=250_000, nps_opted=True)
        replies = []
        for text in ("CTC is outside the approved band.", "Employer NPS is over its cap."):
            response = Mock()
            response.content = [Mock(text=text)]
            replies.append(response)
        with patch("ai_layer._client", Mock(messages=Mock(create=Mock(side_effect=replies)))):
            result = ai_layer.evaluate_band_guardrail(structure, "new", 1_000_000, 1_500_000)
        self.assertTrue(result["ai_backed"])
        failing = [i for i, c in enumerate(result["checks"]) if not c["passed"]]
        self.assertEqual(result["ai_fields"], [f"checks[{i}].message" for i in failing])
        self.assertEqual(len(failing), 2)


class TestRealAiBackedResponses(unittest.TestCase):
    """
    OUTPUT_BOUNDARY_GROUNDING_DESIGN.md §3.4, committed knowingly red (§5 step 2)
    before the boundary changes. Driven with the real assembled response. Before
    this, the layer was only ever driven with an all-fallback baseline or
    hand-built payloads, and on real AI-backed output it was wrong both ways
    (§1): false findings on Python-written fields, and fabricated figures
    grounded by unrelated metrics.

    Where a test needs a fabrication to reach the boundary, the inline guard is
    switched off, as in test_the_boundary_catches_it_when_the_inline_guard_is_disabled:
    the second layer is only worth anything if it holds on its own.
    """

    R1_LINE = "This structure sets Basic below the 50% floor the Code on Wages 2025 requires."
    R5_LINE = "The excess over Rs 7.5L is a taxable perquisite under Section 17(1)(h)."

    def _without_inline_guard(self):
        return patch.multiple(ai_layer, _numbers_ungrounded=lambda *a, **k: False,
                              _citations_unsupplied=lambda *a, **k: False)

    def test_the_fixtures_reach_ai_backed_sections(self):
        # Without this, every "no findings" test below would pass vacuously.
        both = _real_response(R1_R5, {"R1": self.R1_LINE, "R5": self.R5_LINE})
        self.assertEqual([f["rule_id"] for f in both["compliance"]["flags"]], ["R1", "R5"])
        self.assertTrue(both["compliance"]["ai_backed"])
        nps = _real_response(NEGOTIATES_NPS, {}, negotiation=lambda p: (
            f"You could ask HR to restructure your {p['changed_levers'][-1]}, part of how this "
            f"recommendation reaches Rs {p['total_annual_saving']:,.0f} in annual savings."))
        self.assertTrue(nps["negotiation"]["ai_backed"])
        self.assertIn("NPS enrollment (Section 124, formerly 80CCD2)", nps["negotiation"]["changed_levers"])

    def test_legitimate_compliance_rephrasings_have_no_findings(self):
        response = _real_response(R1_R5, {"R1": self.R1_LINE, "R5": self.R5_LINE})
        self.assertEqual(ob.ungrounded_findings(response, extra=_request_numbers(R1_R5)), [])

    def test_a_negotiation_point_naming_a_real_lever_and_the_real_saving_has_no_findings(self):
        response = _real_response(NEGOTIATES_NPS, {}, negotiation=lambda p: (
            f"You could ask HR to restructure your {p['changed_levers'][-1]}, part of how this "
            f"recommendation reaches Rs {p['total_annual_saving']:,.0f} in annual savings."))
        self.assertEqual(ob.ungrounded_findings(response, extra=_request_numbers(NEGOTIATES_NPS)), [])

    def test_python_written_fields_inside_ai_sections_are_never_findings(self):
        response = _real_response(R1_R5, {"R1": self.R1_LINE, "R5": self.R5_LINE})
        paths = [f.path for f in ob.ungrounded_findings(response, extra=_request_numbers(R1_R5))]
        self.assertEqual([p for p in paths if p.endswith((".rationale", ".rule_id", ".severity"))
                          or ".changed_levers" in p], [])

    def test_a_fabricated_figure_equal_to_an_unrelated_metric_is_found(self):
        # §1.2: 2 equals metrics.rules_triggered and 1 is within +-1 of
        # basic_pct. Neither has anything to do with R5's ceiling.
        for fabricated, number in (("Your contributions exceed the limit by 2 lakh.", 2.0),
                                   ("Your contributions exceed the limit by 1 lakh.", 1.0)):
            with self.subTest(number=number), self._without_inline_guard():
                response = _real_response(R1_R5, {"R1": self.R1_LINE, "R5": fabricated})
                self.assertTrue(response["compliance"]["ai_backed"], "the inline guard was not bypassed")
                findings = ob.ungrounded_findings(response, extra=_request_numbers(R1_R5))
                self.assertTrue(any(f.path == "compliance.flags[1].message" and f.number == number
                                    for f in findings), f"not found: {findings}")

    def test_a_fabricated_section_whose_digits_are_grounded_is_found(self):
        # 50 is R1's real floor; "Section 50" was never supplied.
        with self._without_inline_guard():
            response = _real_response(R1_R5, {"R1": "Basic salary is below the 50% floor set by Section 50.",
                                              "R5": self.R5_LINE})
        findings = ob.ungrounded_findings(response, extra=_request_numbers(R1_R5))
        self.assertTrue(any(f.path == "compliance.flags[0].message" for f in findings),
                        f"the fabricated citation was not found: {findings}")

    def test_every_ai_backed_section_in_real_output_declares_its_model_authored_fields(self):
        # §3.1 (b). Walks the real response, so a new AI-backed section that
        # forgets to declare is caught here without anyone updating a list.
        responses = [_real_response(R1_R5, {"R1": self.R1_LINE, "R5": self.R5_LINE}),
                     _real_response(NEGOTIATES_NPS, {}, negotiation=lambda p: "You could ask HR.")]
        for response in responses:
            for path in ob._ai_section_paths(response):
                section = response
                for part in path.replace("]", "").replace("[", ".").split("."):
                    section = section[int(part)] if part.isdigit() else section[part]
                with self.subTest(section=path):
                    self.assertIn("ai_fields", section)
                    self.assertTrue(section["ai_fields"])
                    # Paths are relative ("flags[].message"), resolved by the
                    # boundary's own resolver, which raises if a declared path
                    # resolves to nothing.
                    resolved = ob.declared_ai_fields(section, path)
                    self.assertTrue(resolved)
                    self.assertTrue(all(isinstance(value, str) for _, value in resolved))


if __name__ == "__main__":
    unittest.main()
