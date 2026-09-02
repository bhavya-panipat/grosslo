"""
Tests for orchestration.py and its wiring into /api/submissions
(app.py's api_create_submission) and review_queue.py's schema/filtering.

Same discipline as test_review_workflow.py: real functions, real fixtures,
no mocks. Every routing decision here is checked against the actual
flag_compliance()/evaluate_band_guardrail() output, never a hand-written
stand-in for what those functions "should" return.
"""

import os
import sys
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import review_queue

review_queue.DB_PATH = "test_orchestration_queue.db"

import app as flask_app
from ai_layer import flag_compliance, evaluate_band_guardrail
from tax_engine import SalaryStructure
from orchestration import classify_row

TEST_DB = "test_orchestration_queue.db"


def _optimize_response_for(ctc, rent_paid=0, city="metro", nps_opted=False, current_structure=None):
    response, _ = flask_app._build_optimize_response(
        ctc, rent_paid, city, nps_opted, current_structure, False, skip_ai=True,
    )
    return response


class ReviewQueueTestCase(unittest.TestCase):
    def setUp(self):
        review_queue.DB_PATH = TEST_DB
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        review_queue.init_db()

    def tearDown(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)


# ---------------------------------------------------------------------------
# classify_row() — direct unit tests against real flag_compliance()/
# evaluate_band_guardrail() output.
# ---------------------------------------------------------------------------

class TestClassifyRow(unittest.TestCase):
    def _clean_structure(self):
        # basic 60% of ctc — within the statutory 50-60% band, no flags.
        return SalaryStructure(
            ctc=1_800_000, basic=1_080_000, hra=0, lta=0, special_allowance=590_400,
            employer_pf=129_600, employer_nps=0, nps_opted=False,
        )

    def test_zero_flags_no_guardrail_run_routes_guardrail_not_run(self):
        structure = self._clean_structure()
        compliance = flag_compliance(structure, rent_paid=0)
        result = classify_row(compliance, None)
        self.assertEqual(result["route"], "guardrail_not_run")
        self.assertEqual(result["severity"], "None")
        self.assertFalse(result["checked"]["guardrail_evaluated"])
        self.assertIsNone(result["checked"]["guardrail_checks_failed"])

    def test_zero_flags_guardrail_passing_routes_auto_pass_candidate(self):
        structure = self._clean_structure()
        compliance = flag_compliance(structure, rent_paid=0)
        guardrail = evaluate_band_guardrail(structure, "new", 1_700_000, 1_900_000)
        self.assertEqual(guardrail["verdict"], "pass")
        result = classify_row(compliance, guardrail)
        self.assertEqual(result["route"], "auto_pass_candidate")
        self.assertEqual(result["severity"], "None")
        self.assertEqual(result["reasons"], [])

    def test_r4_only_low_severity_routes_auto_pass_candidate_but_is_surfaced(self):
        # LTA > 10% of CTC fires R4 (Low) without touching basic_pct.
        structure = SalaryStructure(
            ctc=1_800_000, basic=1_080_000, hra=0, lta=200_000, special_allowance=390_400,
            employer_pf=129_600, employer_nps=0, nps_opted=False,
        )
        compliance = flag_compliance(structure, rent_paid=0)
        self.assertTrue(any(f["rule_id"] == "R4" for f in compliance["flags"]))
        guardrail = evaluate_band_guardrail(structure, "new", 1_700_000, 1_900_000)
        result = classify_row(compliance, guardrail)
        self.assertEqual(result["route"], "auto_pass_candidate")
        self.assertEqual(result["severity"], "Low")
        # Still fast-tracks, but must not be silently dropped — the caller
        # (finance-flow.tsx) badges the row using this list.
        self.assertEqual(len(result["reasons"]), 1)
        self.assertIn("R4", result["reasons"][0])
        self.assertTrue(result["reasons"][0].strip())  # real, non-empty text

    def test_r2_only_medium_with_no_band_routes_guardrail_not_run(self):
        # guardrail_not_run outranks needs_review in the priority order —
        # "never checked" must never look like "checked, just needs review."
        structure = SalaryStructure(
            ctc=1_800_000, basic=1_080_000, hra=0, lta=0, special_allowance=720_000,
            employer_pf=0, employer_nps=0, nps_opted=False,
        )
        compliance = flag_compliance(structure, rent_paid=0)
        self.assertTrue(any(f["rule_id"] == "R2" for f in compliance["flags"]))
        result = classify_row(compliance, None)
        self.assertEqual(result["route"], "guardrail_not_run")

    def test_r2_only_medium_with_passing_band_routes_needs_review(self):
        structure = SalaryStructure(
            ctc=1_800_000, basic=1_080_000, hra=0, lta=0, special_allowance=720_000,
            employer_pf=0, employer_nps=0, nps_opted=False,
        )
        compliance = flag_compliance(structure, rent_paid=0)
        guardrail = evaluate_band_guardrail(structure, "new", 1_700_000, 1_900_000)
        result = classify_row(compliance, guardrail)
        self.assertEqual(result["route"], "needs_review")
        self.assertEqual(result["severity"], "Medium")
        self.assertIn("R2", result["reasons"][0])

    def test_r1_high_severity_routes_escalate(self):
        structure = SalaryStructure(
            ctc=2_000_000, basic=900_000, hra=400_000, lta=0,
            special_allowance=2_000_000 - 900_000 - 400_000 - 108_000,
            employer_pf=108_000, employer_nps=0, nps_opted=False,
        )
        compliance = flag_compliance(structure, rent_paid=300_000)
        self.assertTrue(any(f["rule_id"] == "R1" for f in compliance["flags"]))
        result = classify_row(compliance, None)
        self.assertEqual(result["route"], "escalate")
        self.assertEqual(result["severity"], "High")
        self.assertIn("R1", result["reasons"][0])
        self.assertIn("Code on Wages", result["reasons"][0])

    def test_r5_epfo_ceiling_high_severity_routes_escalate(self):
        # Same fixture as test_review_workflow.py's
        # test_epfo_ceiling_correction_shows_employer_pf_change — reused
        # rather than inventing a new R5-triggering structure.
        structure = SalaryStructure(
            ctc=4_000_000, basic=1_800_000, hra=900_000, lta=100_000,
            special_allowance=300_000, employer_pf=900_000, employer_nps=0, nps_opted=False,
        )
        compliance = flag_compliance(structure, rent_paid=500_000)
        self.assertTrue(any(f["rule_id"] == "R5" for f in compliance["flags"]))
        result = classify_row(compliance, None)
        self.assertEqual(result["route"], "escalate")
        self.assertEqual(result["severity"], "High")

    def test_failing_guardrail_forces_escalate_even_with_zero_compliance_flags(self):
        structure = self._clean_structure()
        compliance = flag_compliance(structure, rent_paid=0)
        self.assertEqual(compliance["flags"], [])
        guardrail = evaluate_band_guardrail(structure, "new", 100_000, 500_000)  # CTC well outside this band
        self.assertEqual(guardrail["verdict"], "flag")
        result = classify_row(compliance, guardrail)
        self.assertEqual(result["route"], "escalate")
        self.assertEqual(result["severity"], "None")  # the guardrail, not compliance, is what escalated this
        self.assertEqual(len(result["reasons"]), 1)
        self.assertIn("band", result["reasons"][0].lower())

    def test_reasons_trace_to_real_flag_and_guardrail_text_no_invented_strings(self):
        structure = SalaryStructure(
            ctc=2_000_000, basic=900_000, hra=400_000, lta=0,
            special_allowance=2_000_000 - 900_000 - 400_000 - 108_000,
            employer_pf=108_000, employer_nps=0, nps_opted=False,
        )
        compliance = flag_compliance(structure, rent_paid=300_000)
        guardrail = evaluate_band_guardrail(structure, "new", 100_000, 500_000)  # also fails, on purpose
        result = classify_row(compliance, guardrail)
        failing_checks = [c for c in guardrail["checks"] if not c["passed"]]
        for check in failing_checks:
            self.assertTrue(any(check["message"] in r for r in result["reasons"]))
        for flag in compliance["flags"]:
            self.assertTrue(any(flag["message"] in r for r in result["reasons"]))

    def test_combined_high_flag_and_failing_guardrail_reasons_ordering(self):
        # Gap flagged during plan review: both independently route to
        # escalate, so the route isn't in question — this confirms the
        # documented `reasons` ordering (guardrail failures first, then
        # flags high->low) actually holds when both fire on the same row,
        # not just when observed separately.
        structure = SalaryStructure(
            ctc=2_000_000, basic=900_000, hra=400_000, lta=0,
            special_allowance=2_000_000 - 900_000 - 400_000 - 108_000,
            employer_pf=108_000, employer_nps=0, nps_opted=False,
        )
        compliance = flag_compliance(structure, rent_paid=300_000)
        self.assertTrue(any(f["rule_id"] == "R1" for f in compliance["flags"]))
        guardrail = evaluate_band_guardrail(structure, "new", 100_000, 500_000)  # CTC outside band -> fails
        self.assertEqual(guardrail["verdict"], "flag")
        result = classify_row(compliance, guardrail)
        self.assertEqual(result["route"], "escalate")
        self.assertGreaterEqual(len(result["reasons"]), 2)
        self.assertTrue(result["reasons"][0].startswith("Guardrail —"), result["reasons"])
        self.assertIn("R1", result["reasons"][1])

    def test_two_flags_different_severities_aggregate_to_the_higher_one(self):
        # Gap flagged during plan review: _aggregate_severity's max() logic
        # was never observed picking the higher of two real, simultaneously
        # triggered severities. R2 (Medium, no employer PF) + R6 (Low,
        # special_allowance == 0) on the same structure.
        structure = SalaryStructure(
            ctc=1_800_000, basic=1_080_000, hra=0, lta=0, special_allowance=0,
            employer_pf=0, employer_nps=0, nps_opted=False,
        )
        compliance = flag_compliance(structure, rent_paid=0)
        triggered_ids = {f["rule_id"] for f in compliance["flags"]}
        self.assertIn("R2", triggered_ids)
        self.assertIn("R6", triggered_ids)
        guardrail = evaluate_band_guardrail(structure, "new", 1_700_000, 1_900_000)
        result = classify_row(compliance, guardrail)
        self.assertEqual(result["severity"], "Medium")  # not "Low" — max() must pick the higher severity
        self.assertEqual(result["route"], "needs_review")
        # severity-descending order: Medium (R2) reported before Low (R6)
        r2_index = next(i for i, r in enumerate(result["reasons"]) if "R2" in r)
        r6_index = next(i for i, r in enumerate(result["reasons"]) if "R6" in r)
        self.assertLess(r2_index, r6_index)


# ---------------------------------------------------------------------------
# review_queue.py — schema migration, orchestration plumbing, route filter.
# ---------------------------------------------------------------------------

class TestSchemaAndPersistence(ReviewQueueTestCase):
    def test_create_submission_without_orchestration_key_does_not_raise(self):
        # Every fixture in test_review_workflow.py omits "orchestration"
        # entirely — this must keep working unchanged (backward compatible).
        row = {
            "employee_name": "No Orchestration Row", "ctc": 1_800_000,
            "input": {"ctc": 1_800_000, "rent_paid": 0, "city": "metro"},
            "computed": {"compliance": {"flags": []}},
        }
        result = review_queue.create_submission("single", [row])
        submission = review_queue.get_submission(result["submission_id"])
        self.assertIsNone(submission["rows"][0]["orchestration"])

    def test_create_submission_with_orchestration_persists_and_reads_back(self):
        row = {
            "employee_name": "Escalated Row", "ctc": 2_000_000,
            "input": {"ctc": 2_000_000, "rent_paid": 300_000, "city": "metro"},
            "computed": {"compliance": {"flags": []}},
            "orchestration": {
                "route": "escalate", "severity": "High",
                "reasons": ["R1 (High) — test rationale"],
                "checked": {
                    "compliance_rules_evaluated": 6, "compliance_flags_triggered": 1,
                    "guardrail_evaluated": False, "guardrail_checks_failed": None,
                },
            },
        }
        result = review_queue.create_submission("single", [row])
        submission = review_queue.get_submission(result["submission_id"])
        orchestration = submission["rows"][0]["orchestration"]
        self.assertEqual(orchestration["route"], "escalate")
        self.assertEqual(orchestration["severity"], "High")

    def test_list_submissions_route_filter(self):
        clean_row = {
            "employee_name": "Clean", "ctc": 1_800_000,
            "input": {"ctc": 1_800_000}, "computed": {"compliance": {"flags": []}},
            "orchestration": {"route": "auto_pass_candidate", "severity": "None", "reasons": [],
                               "checked": {"compliance_rules_evaluated": 6, "compliance_flags_triggered": 0,
                                           "guardrail_evaluated": True, "guardrail_checks_failed": 0}},
        }
        escalated_row = {
            "employee_name": "Escalated", "ctc": 2_000_000,
            "input": {"ctc": 2_000_000}, "computed": {"compliance": {"flags": []}},
            "orchestration": {"route": "escalate", "severity": "High", "reasons": ["x"],
                               "checked": {"compliance_rules_evaluated": 6, "compliance_flags_triggered": 1,
                                           "guardrail_evaluated": False, "guardrail_checks_failed": None}},
        }
        review_queue.create_submission("batch", [clean_row, escalated_row])

        escalated_only = review_queue.list_submissions(route="escalate")
        self.assertEqual(len(escalated_only), 1)
        self.assertEqual(len(escalated_only[0]["rows"]), 1)
        self.assertEqual(escalated_only[0]["rows"][0]["employee_name"], "Escalated")

        clean_only = review_queue.list_submissions(route="auto_pass_candidate")
        self.assertEqual(len(clean_only), 1)
        self.assertEqual(clean_only[0]["rows"][0]["employee_name"], "Clean")


# ---------------------------------------------------------------------------
# Integration: real HTTP through app.py's /api/submissions.
# ---------------------------------------------------------------------------

class TestSubmissionsRouteIntegration(ReviewQueueTestCase):
    def setUp(self):
        super().setUp()
        self.client = flask_app.app.test_client()
        # GET /api/submissions/<id> now requires a real hr/finance session
        # (see auth.py) — POST (create) deliberately stays open, unaffected.
        self.client.post("/api/auth/login", json={"role": "finance", "code": "FINANCE2026"})

    def test_submitting_r1_row_persists_and_returns_escalate_route(self):
        row = {
            "employee_name": "Escalates On Submit", "ctc": 2_000_000, "rent_paid": 300_000, "city": "metro",
            "current_structure": {
                "basic": 900_000, "hra": 400_000, "lta": 0,
                "special_allowance": 2_000_000 - 900_000 - 400_000 - 108_000,
                "employer_pf": 108_000, "employer_nps": 0,
            },
        }
        post_resp = self.client.post("/api/submissions", json={"source": "single", "row": row})
        self.assertEqual(post_resp.status_code, 200)
        submission_id = post_resp.get_json()["submission_id"]

        get_resp = self.client.get(f"/api/submissions/{submission_id}")
        self.assertEqual(get_resp.status_code, 200)
        orchestration = get_resp.get_json()["rows"][0]["orchestration"]
        self.assertIsNotNone(orchestration)
        self.assertEqual(orchestration["route"], "escalate")
        self.assertEqual(orchestration["severity"], "High")

    def test_reasons_surfaced_are_the_safe_fallback_when_upstream_guard_fires(self):
        # The actual claim this whole guard extension is justified by:
        # orchestration.py surfaces flag_compliance()'s "message" text as
        # the stated reason for a routing decision — this test trips the
        # numeric guard upstream (a fabricated rephrasing with a wrong
        # percentage) through the REAL /api/submissions route, exactly
        # the path a live panel re-run would take, and confirms the
        # `reasons` text that actually reaches the response is the safe
        # deterministic rationale, not the bad AI text, and not silently
        # missing. Proves the guarantee end to end rather than assuming
        # it from reading ai_layer.py and orchestration.py separately.
        row = {
            "employee_name": "Guard Fires On Submit", "ctc": 2_000_000, "rent_paid": 300_000, "city": "metro",
            "current_structure": {
                "basic": 900_000, "hra": 400_000, "lta": 0,
                "special_allowance": 2_000_000 - 900_000 - 400_000 - 108_000,
                "employer_pf": 108_000, "employer_nps": 0,
            },
        }
        fake_response = Mock()
        fake_response.content = [Mock(text="Basic salary is below 35% of CTC, a compliance concern.")]
        with patch("ai_layer._client", Mock(messages=Mock(create=Mock(return_value=fake_response)))):
            post_resp = self.client.post("/api/submissions", json={"source": "single", "row": row})
        self.assertEqual(post_resp.status_code, 200)
        submission_id = post_resp.get_json()["submission_id"]

        get_resp = self.client.get(f"/api/submissions/{submission_id}")
        row_data = get_resp.get_json()["rows"][0]
        orchestration = row_data["orchestration"]
        self.assertEqual(orchestration["route"], "escalate")  # R1 is High severity regardless of phrasing
        reasons_text = " ".join(orchestration["reasons"])
        self.assertIn("50%", reasons_text)  # the real, guard-verified rationale
        self.assertNotIn("35%", reasons_text)  # never the fabricated AI text
        # Same guarantee visible on the raw compliance flags this was built
        # from — ai_backed is False specifically because the guard rejected
        # the fabricated rephrasing, not because no client was configured.
        self.assertFalse(row_data["computed"]["compliance"]["ai_backed"])

    def test_submitting_clean_row_with_band_returns_auto_pass_candidate(self):
        row = {
            "employee_name": "Clean On Submit", "ctc": 1_800_000, "rent_paid": 0, "city": "metro",
            "band_min": 1_700_000, "band_max": 1_900_000,
        }
        post_resp = self.client.post("/api/submissions", json={"source": "single", "row": row})
        submission_id = post_resp.get_json()["submission_id"]
        get_resp = self.client.get(f"/api/submissions/{submission_id}")
        orchestration = get_resp.get_json()["rows"][0]["orchestration"]
        self.assertEqual(orchestration["route"], "auto_pass_candidate")

    def test_submitting_clean_row_without_band_returns_guardrail_not_run(self):
        row = {"employee_name": "No Band On Submit", "ctc": 1_800_000, "rent_paid": 0, "city": "metro"}
        post_resp = self.client.post("/api/submissions", json={"source": "single", "row": row})
        submission_id = post_resp.get_json()["submission_id"]
        get_resp = self.client.get(f"/api/submissions/{submission_id}")
        orchestration = get_resp.get_json()["rows"][0]["orchestration"]
        self.assertEqual(orchestration["route"], "guardrail_not_run")

    def test_end_to_end_mixed_batch_lands_in_correct_buckets(self):
        rows = [
            {  # clean, band supplied+passing -> auto_pass_candidate
                "employee_name": "Clean", "ctc": 1_800_000, "rent_paid": 0, "city": "metro",
                "band_min": 1_700_000, "band_max": 1_900_000,
            },
            {  # R4-only (Low), band passing -> auto_pass_candidate, badged
                "employee_name": "LowOnly", "ctc": 1_800_000, "rent_paid": 0, "city": "metro",
                "band_min": 1_700_000, "band_max": 1_900_000,
                "current_structure": {
                    "basic": 1_080_000, "hra": 0, "lta": 200_000, "special_allowance": 390_400,
                    "employer_pf": 129_600, "employer_nps": 0,
                },
            },
            {  # R1 (High) -> escalate
                "employee_name": "HighSeverity", "ctc": 2_000_000, "rent_paid": 300_000, "city": "metro",
                "current_structure": {
                    "basic": 900_000, "hra": 400_000, "lta": 0,
                    "special_allowance": 2_000_000 - 900_000 - 400_000 - 108_000,
                    "employer_pf": 108_000, "employer_nps": 0,
                },
            },
            {  # zero flags, no band -> guardrail_not_run
                "employee_name": "NoBand", "ctc": 1_800_000, "rent_paid": 0, "city": "metro",
            },
        ]
        post_resp = self.client.post("/api/submissions", json={"source": "batch", "rows": rows})
        self.assertEqual(post_resp.status_code, 200)
        submission_id = post_resp.get_json()["submission_id"]

        get_resp = self.client.get(f"/api/submissions/{submission_id}")
        by_name = {r["employee_name"]: r for r in get_resp.get_json()["rows"]}

        self.assertEqual(by_name["Clean"]["orchestration"]["route"], "auto_pass_candidate")
        self.assertEqual(by_name["LowOnly"]["orchestration"]["route"], "auto_pass_candidate")
        self.assertEqual(by_name["LowOnly"]["orchestration"]["severity"], "Low")
        self.assertEqual(by_name["HighSeverity"]["orchestration"]["route"], "escalate")
        self.assertEqual(by_name["NoBand"]["orchestration"]["route"], "guardrail_not_run")

        # A client-side "bulk-approve eligible" filter (mirroring
        # finance-flow.tsx's routeOf()) must only ever include the clean +
        # Low-only rows.
        bulk_eligible = {
            name for name, r in by_name.items() if r["orchestration"]["route"] == "auto_pass_candidate"
        }
        self.assertEqual(bulk_eligible, {"Clean", "LowOnly"})


if __name__ == "__main__":
    unittest.main()
