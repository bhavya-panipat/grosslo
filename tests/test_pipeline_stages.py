"""
Stage-invocation assertions for Phase 2.1 (ORCHESTRATION_DESIGN.md §3.4).

This file exists because of a specific, measured gap. §2 of the design doc
originally claimed the existing suite would not notice a dropped compliance
stage at all; measuring it showed that was overstated — 5 tests do fail. But
ZERO of them name compliance. They are routing-bucket and diff-view tests,
downstream consumers that happen to depend on flags existing, so the failure
output sends a developer to investigate routing rather than a missing stage.
And that coverage is incidental: it holds for "flags vanish entirely" and thins
out for subtler changes.

So the gap this closes is not "nothing catches it" but "nothing catches it AS
ITSELF". These tests fail by name when a stage stops running, which is the
difference between a suite that detects a problem and one that identifies it.

The other half of the reason is forward-looking: 2.2, 2.3 and 2.4 each add or
extend a stage. Adding one must be a deliberate act that updates the expected
sequence here, not something that quietly slips in — which is why the expected
list is asserted exactly rather than as a subset.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pipeline
import app as flask_app
from tests.pipeline_cases import CASES

# The sequence as of Phase 2.1. Asserted EXACTLY, not as a subset: a new stage
# arriving in 2.2/2.3/2.4 should fail this test and be added here on purpose.
EXPECTED_STAGES = ["optimize", "current_structure", "explain",
                   "compliance", "negotiate", "metrics"]


class TestDeclaredSequence(unittest.TestCase):
    """
    The declaration itself, checked without running anything — so a reordering
    is caught even in a case that happens not to exercise the difference.
    """

    def test_the_declared_stages_are_exactly_the_expected_ones_in_order(self):
        self.assertEqual([name for name, _ in pipeline.STAGES], EXPECTED_STAGES)

    def test_current_structure_is_declared_before_compliance(self):
        """
        The load-bearing constraint (ORCHESTRATION_DESIGN.md §1). Compliance
        checks the AS-OFFERED structure; if it ran before that structure were
        built, it would fall back to the optimizer's own recommendation — which
        the optimizer constrains to a 50-60% basic band by construction, so R1
        (basic < 50% of CTC) could structurally never fire and compliance would
        silently report zero risk on every input.

        Until pipeline.py existed this was enforced by statement order and a
        comment. Asserting the declared order is what turns it into something
        that fails rather than something that is merely written down.
        """
        names = [name for name, _ in pipeline.STAGES]
        self.assertLess(names.index("current_structure"), names.index("compliance"))

    def test_every_declared_stage_is_callable(self):
        for name, fn in pipeline.STAGES:
            with self.subTest(stage=name):
                self.assertTrue(callable(fn), f"{name} is not callable")


class TestEveryStageActuallyRuns(unittest.TestCase):
    """
    The declaration agreeing with itself proves nothing about what executed.
    These drive the real pipeline and assert on what it recorded.
    """

    def _run(self, kwargs):
        response, _ = flask_app._build_optimize_response(
            kwargs["ctc"], kwargs["rent_paid"], kwargs["city"], kwargs["nps_opted"],
            kwargs["current_extracted"], kwargs["extraction_ai_backed"], skip_ai=True,
        )
        return response

    def test_every_case_runs_every_stage_in_order(self):
        for name, kwargs in CASES:
            with self.subTest(case=name):
                response = self._run(kwargs)
                self.assertEqual(
                    response["stages_run"], EXPECTED_STAGES,
                    f"the pipeline did not run the declared sequence for {name}")

    def test_negotiate_is_recorded_even_when_it_declines_to_do_anything(self):
        """
        "Ran and had no work" and "never ran" are different facts. The
        no-extraction case has nothing to negotiate away from, so negotiate()
        returns early and the response has no `negotiation` key — but the stage
        was still invoked, and collapsing those two states would let a stage
        that stopped being called look exactly like one correctly declining.
        """
        case = dict(CASES)["no_extraction_falls_back_to_recommended"]
        response = self._run(case)
        self.assertNotIn("negotiation", response,
                         "this case should have nothing to negotiate")
        self.assertIn("negotiate", response["stages_run"],
                      "the stage still ran; only its work was empty")

    def test_stages_run_reaches_the_http_response_not_just_the_function(self):
        """
        §6 resolved to expose this. A record confirmable only from inside the
        test suite is not an auditable fact — the point is that a caller can
        verify a compliance check executed.
        """
        client = flask_app.app.test_client()
        resp = client.post("/api/optimize", json={
            "ctc": 1_800_000, "rent_paid": 0, "city": "metro", "nps_opted": False})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["stages_run"], EXPECTED_STAGES)


class TestADroppedStageFailsByName(unittest.TestCase):
    """
    The property that makes this file worth having, asserted directly rather
    than trusted: run the orchestrator with a stage removed and confirm the
    absence is detectable from `stages_run` alone — without needing any
    downstream consumer to happen to notice.
    """

    def _context(self):
        return pipeline.PipelineContext(
            ctc=2_000_000, rent_paid=300_000, city="metro", nps_opted=False,
            current_extracted={"basic": 900_000, "hra": 400_000, "lta": 0,
                               "employer_pf": 108_000},
            extraction_ai_backed=False, skip_ai=True,
            build_current_structure=flask_app._build_current_structure,
        )

    def test_removing_a_stage_is_visible_in_stages_run(self):
        original = pipeline.STAGES
        try:
            for dropped in EXPECTED_STAGES[:-1]:   # metrics last; see below
                with self.subTest(dropped=dropped):
                    pipeline.STAGES = tuple((n, f) for n, f in original
                                            if n != dropped)
                    ctx = self._context()
                    try:
                        pipeline.run(ctx)
                    except Exception:
                        # Dropping an upstream stage can break a later one
                        # outright, which is also a detection — the point is
                        # that it cannot pass silently.
                        continue
                    self.assertNotIn(
                        dropped, ctx.response["stages_run"],
                        f"{dropped} was removed but still reported as run")
                    self.assertNotEqual(ctx.response["stages_run"], EXPECTED_STAGES)
        finally:
            pipeline.STAGES = original
        # Asserted HERE rather than as a separate test: a leaked monkeypatch
        # would silently weaken every other test in the suite, and a separate
        # test would only catch it if unittest happened to run it afterwards.
        # Relying on alphabetical ordering for a safety check is the kind of
        # implicit agreement this phase exists to remove.
        self.assertEqual([n for n, _ in pipeline.STAGES], EXPECTED_STAGES,
                         "the monkeypatched sequence leaked out of this test")
