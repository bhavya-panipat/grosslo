"""
The characterization baseline for Phase 2.1 (ORCHESTRATION_DESIGN.md §3.3).

This asserts the pipeline's exact output against a COMMITTED fixture captured
before the restructure began. It exists because the other 261 tests cannot
catch what this phase risks: they call flag_compliance(), negotiate() and the
rest DIRECTLY and assert on their return values, so a restructure that dropped
a stage from the pipeline entirely would not falsify a single one of them. A
missing stage and a correct one look identical to a suite that checks outputs
at known entry points rather than confirming entry happened.

The fixture is never regenerated to make this pass. A diff here is either a bug
or a deliberate change someone has to justify — that is the property that makes
it a checkpoint rather than a restatement of whatever the code currently does.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as flask_app
from tests.pipeline_cases import CASES

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "fixtures", "pipeline_baseline.json")


def _run(kwargs):
    response, _result = flask_app._build_optimize_response(
        kwargs["ctc"], kwargs["rent_paid"], kwargs["city"], kwargs["nps_opted"],
        kwargs["current_extracted"], kwargs["extraction_ai_backed"], skip_ai=True,
    )
    return response


class TestPipelineBaselineExists(unittest.TestCase):
    """
    The baseline's own preconditions. Without these, a deleted or truncated
    fixture would make every comparison below vacuously pass — the test would
    go green precisely when it had stopped testing anything.
    """

    def test_the_fixture_is_committed_and_covers_every_case(self):
        self.assertTrue(os.path.exists(FIXTURE),
                        f"no committed baseline at {FIXTURE}; it must not be "
                        f"regenerated on demand (ORCHESTRATION_DESIGN.md §6)")
        with open(FIXTURE) as f:
            baseline = json.load(f)
        self.assertEqual(sorted(baseline), sorted(name for name, _ in CASES),
                         "the fixture and the case list have drifted apart")

    def test_the_baseline_pins_real_output_not_empty_shapes(self):
        # A fixture of empty dicts would compare equal to a pipeline that had
        # stopped computing anything at all.
        with open(FIXTURE) as f:
            baseline = json.load(f)
        for name, response in baseline.items():
            with self.subTest(case=name):
                for key in ("recommended_regime", "annual_saving", "compliance",
                            "explanation", "metrics", "old_regime_best",
                            "new_regime_best", "compliance_checked_against"):
                    self.assertIn(key, response, f"{name} is missing {key}")
                self.assertIn(response["recommended_regime"], ("old", "new"))


class TestPipelineOutputIsUnchanged(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(FIXTURE) as f:
            cls.baseline = json.load(f)

    def test_every_case_matches_the_baseline_byte_for_byte(self):
        for name, kwargs in CASES:
            with self.subTest(case=name):
                expected = self.baseline[name]
                actual = _run(kwargs)
                self.assertEqual(
                    json.dumps(actual, sort_keys=True, indent=2),
                    json.dumps(expected, sort_keys=True, indent=2),
                    f"pipeline output changed for {name}. If this was "
                    f"deliberate, justify it — do NOT re-run the capture "
                    f"script to make it pass.")


class TestBaselineCoversTheBoundariesItClaimsTo(unittest.TestCase):
    """
    The spread is only worth having if it actually exercises the branches it
    was chosen for. A characterization suite whose cases all landed on the same
    path would pass every restructure and prove nothing — so what each case
    triggers is asserted, not assumed.
    """

    @classmethod
    def setUpClass(cls):
        with open(FIXTURE) as f:
            cls.baseline = json.load(f)

    def _flags(self, name):
        return [f["rule_id"] for f in self.baseline[name]["compliance"]["flags"]]

    def test_the_code_on_wages_floor_is_pinned_on_both_sides(self):
        # Below the 50% floor fires R1; exactly at it does not. A comparison
        # flipped from < to <= would move only the second.
        self.assertIn("R1", self._flags("code_on_wages_floor_breach"))
        self.assertNotIn("R1", self._flags("code_on_wages_floor_exactly_at_50pct"))

    def test_the_epfo_ceiling_case_actually_breaches_it(self):
        self.assertIn("R5", self._flags("epfo_aggregate_ceiling_breach"))

    def test_a_clean_pass_is_pinned_so_silence_is_distinguishable(self):
        # Without this, a pipeline that stopped running compliance would look
        # correct — every case would simply report no flags.
        self.assertEqual(self._flags("clean_pass_no_flags"), [])
        self.assertNotEqual(self._flags("code_on_wages_floor_breach"), [],
                            "at least one case must fire, or empty proves nothing")

    def test_the_as_offered_ordering_decision_is_pinned(self):
        # ORCHESTRATION_DESIGN.md §1: compliance checks the AS-OFFERED
        # structure, falling back to the recommendation only when nothing was
        # extracted. If a restructure inverted this, R1 could structurally
        # never fire — the optimizer enforces the 50-60% band by construction —
        # and compliance would silently become theatre.
        self.assertEqual(
            self.baseline["code_on_wages_floor_breach"]["compliance_checked_against"],
            "as_offered")
        self.assertEqual(
            self.baseline["no_extraction_falls_back_to_recommended"]["compliance_checked_against"],
            "recommended")

    def test_negotiation_is_present_only_when_there_is_an_offer_to_negotiate_from(self):
        self.assertIn("negotiation", self.baseline["code_on_wages_floor_breach"])
        self.assertNotIn("negotiation",
                         self.baseline["no_extraction_falls_back_to_recommended"])

    def test_the_zero_saving_case_really_has_nothing_to_gain(self):
        # The naive-baseline branch: negotiate() zeroes changed_levers when
        # total_saving <= 0.
        negotiation = self.baseline["already_optimal_zero_saving"]["negotiation"]
        self.assertLessEqual(negotiation["total_annual_saving"], 0)
        self.assertEqual(negotiation["changed_levers"], [])
        # Contrasted against a case that DOES have levers to pull, so "empty"
        # is pinned as a real outcome rather than as the only outcome the
        # pipeline can produce.
        self.assertNotEqual(
            self.baseline["code_on_wages_floor_breach"]["negotiation"]["changed_levers"], [])
