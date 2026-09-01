"""
Tests for review_queue.py, diff_view.py, salary_revision_export.py, and
the /api/submissions* + /api/export-salary-revision routes in app.py.

Each test class gets its own throwaway SQLite file (never the real
review_queue.db a demo run would create) so tests never see another test's
state and never touch a file a live demo session might be using.
"""

import os
import sys
import unittest
from io import BytesIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import review_queue

# Overridden before `import app` so app.py's module-level review_queue.init_db()
# call (which runs at import time) creates tables in the test DB, not the
# real one a demo session might be using.
review_queue.DB_PATH = "test_review_queue.db"

import app as flask_app
from diff_view import build_diff
from salary_revision_export import build_salary_revision_workbook, TEMPLATE_HONESTY_LABEL

TEST_DB = "test_review_queue.db"


def _optimize_response_for(ctc, rent_paid=0, city="metro", nps_opted=False, current_structure=None):
    """
    Calls the real _build_optimize_response() from app.py — not a
    reimplementation. An earlier version of this helper hand-rolled the
    same logic and silently diverged from the real function (missed that
    negotiate() zeroes changed_levers when total_saving <= 0 unless the
    current_best regime comparison is wired exactly like the real
    function does it), which made a test pass against fake data instead
    of real behavior. Caught by comparing this helper's output against
    the real function's output directly, not by inspection.
    """
    response, _ = flask_app._build_optimize_response(
        ctc, rent_paid, city, nps_opted, current_structure, False, skip_explanation_ai=True,
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


class TestSchemaSelfHeals(ReviewQueueTestCase):
    def test_deleting_db_file_mid_session_does_not_crash_next_call(self):
        # Reproduces a real bug: an earlier version only created tables in
        # init_db() at import time. Deleting the db file while the server
        # was still running (without restarting the process) left every
        # subsequent request hitting "no such table" — sqlite3.connect()
        # silently creates a new, empty, table-less file for a missing
        # path rather than recreating the schema. This asserts the fix:
        # every _conn() ensures the schema exists, so a deleted file
        # self-heals on the very next call instead of 500ing.
        computed = _optimize_response_for(ctc=1_800_000)
        review_queue.create_submission("single", [{
            "employee_name": "Zoe", "ctc": 1_800_000,
            "input": {"ctc": 1_800_000, "rent_paid": 0, "city": "metro", "nps_opted": False, "current_structure": None},
            "computed": computed,
        }])
        os.remove(TEST_DB)  # simulates the exact operational mistake that caused the real bug
        # Must not raise sqlite3.OperationalError — the next call recreates
        # the schema on its own, exactly like a fresh app startup would.
        result = review_queue.create_submission("single", [{
            "employee_name": "Yusuf", "ctc": 2_000_000,
            "input": {"ctc": 2_000_000, "rent_paid": 0, "city": "metro", "nps_opted": False, "current_structure": None},
            "computed": _optimize_response_for(ctc=2_000_000),
        }])
        submission = review_queue.get_submission(result["submission_id"])
        self.assertEqual(submission["rows"][0]["employee_name"], "Yusuf")


class TestMakerChecker(ReviewQueueTestCase):
    def test_submission_persists_and_is_retrievable(self):
        computed = _optimize_response_for(ctc=1_800_000, rent_paid=400_000)
        result = review_queue.create_submission("single", [{
            "employee_name": "Alice", "ctc": 1_800_000,
            "input": {"ctc": 1_800_000, "rent_paid": 400_000, "city": "metro", "nps_opted": False, "current_structure": None},
            "computed": computed,
        }])
        submission = review_queue.get_submission(result["submission_id"])
        self.assertIsNotNone(submission)
        self.assertEqual(submission["rows"][0]["employee_name"], "Alice")
        self.assertEqual(submission["rows"][0]["status"], "pending")

    def test_approve_writes_correct_status_no_dispatch_language(self):
        computed = _optimize_response_for(ctc=1_800_000)
        result = review_queue.create_submission("single", [{
            "employee_name": "Bob", "ctc": 1_800_000,
            "input": {"ctc": 1_800_000, "rent_paid": 0, "city": "metro", "nps_opted": False, "current_structure": None},
            "computed": computed,
        }])
        decision = review_queue.decide_row(result["submission_id"], 0, "approve", None)
        self.assertFalse(decision["already_decided"])
        self.assertEqual(decision["row"]["status"], "approved")


class TestReject(ReviewQueueTestCase):
    def test_reject_requires_a_reason(self):
        with self.assertRaises(ValueError):
            review_queue.decide_row(1, 0, "reject", None)

    def test_rejected_row_visible_with_reason_in_queue(self):
        computed = _optimize_response_for(ctc=1_800_000)
        result = review_queue.create_submission("single", [{
            "employee_name": "Carol", "ctc": 1_800_000,
            "input": {"ctc": 1_800_000, "rent_paid": 0, "city": "metro", "nps_opted": False, "current_structure": None},
            "computed": computed,
        }])
        review_queue.decide_row(result["submission_id"], 0, "reject", "basic looks off")
        rejected = review_queue.list_submissions(status="rejected")
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["rows"][0]["reason"], "basic looks off")
        self.assertEqual(rejected[0]["rows"][0]["status"], "rejected")


class TestDiffView(ReviewQueueTestCase):
    def test_diff_matches_real_optimizer_output_no_invented_numbers(self):
        current_structure = {
            "basic": 500_000, "hra": 300_000, "lta": 50_000,
            "special_allowance": 750_000, "employer_pf": 60_000, "employer_nps": 0,
        }
        computed = _optimize_response_for(ctc=1_800_000, rent_paid=400_000, current_structure=current_structure)
        input_row = {"ctc": 1_800_000, "rent_paid": 400_000, "city": "metro", "current_structure": current_structure}
        diff = build_diff(input_row, computed)

        self.assertTrue(diff["has_prior_offer"])
        recommended_regime = computed["recommended_regime"]
        recommended_structure = computed[f"{recommended_regime}_regime_best"]["structure"]
        for change in diff["field_changes"]:
            # Every before/after value in the diff must equal the real
            # input / real optimizer output exactly — not a rounded or
            # invented approximation.
            self.assertEqual(change["before"], current_structure[change["field"]])
            self.assertEqual(change["after"], recommended_structure[change["field"]])
        # R1 fired (basic < 35% of CTC) -> the basic change must be
        # attributed to it, not to a generic "tax optimization" catch-all.
        basic_change = next(c for c in diff["field_changes"] if c["field"] == "basic")
        self.assertEqual(basic_change["reason"], "R1 compliance fix")

    def test_no_prior_offer_case_is_explicit_not_a_fake_diff(self):
        computed = _optimize_response_for(ctc=1_800_000)
        diff = build_diff({"ctc": 1_800_000, "current_structure": None}, computed)
        self.assertFalse(diff["has_prior_offer"])
        self.assertEqual(diff["field_changes"], [])

    def test_epfo_ceiling_correction_shows_employer_pf_change(self):
        # Real bug, found live via the audit-mode "Submit correction" flow,
        # not by inspection: build_diff() originally reused
        # ai_layer.py's _diff_levers(), which only checks
        # basic/HRA/LTA/NPS-enrollment because it was built for the
        # negotiation copilot's candidate-facing framing. It never checks
        # employer_pf or employer_nps — so an R5 (EPFO aggregate ceiling)
        # correction, where the actual fix is almost entirely a drop in
        # employer_pf, showed "no meaningful change" and silently missed
        # the one field that mattered. This is that exact scenario.
        current_structure = {
            "basic": 1_800_000, "hra": 900_000, "lta": 100_000,
            "special_allowance": 300_000, "employer_pf": 900_000, "employer_nps": 0,
        }
        computed = _optimize_response_for(ctc=4_000_000, rent_paid=500_000, current_structure=current_structure)
        self.assertTrue(any(f["rule_id"] == "R5" for f in computed["compliance"]["flags"]))

        input_row = {"ctc": 4_000_000, "rent_paid": 500_000, "city": "metro", "current_structure": current_structure}
        diff = build_diff(input_row, computed)

        pf_change = next((c for c in diff["field_changes"] if c["field"] == "employer_pf"), None)
        self.assertIsNotNone(pf_change, "employer_pf change must appear in the diff when R5 fired")
        self.assertEqual(pf_change["before"], 900_000)
        self.assertEqual(pf_change["reason"], "R5 compliance fix")
        self.assertLess(pf_change["after"], 750_000)  # the actual fix: brought back under the EPFO ceiling


class TestPartialApproval(ReviewQueueTestCase):
    def test_mixed_batch_rows_decided_independently(self):
        rows = []
        for name, ctc in [("Dave", 1_800_000), ("Eve", 2_500_000), ("Frank", 1_200_000)]:
            computed = _optimize_response_for(ctc=ctc)
            rows.append({
                "employee_name": name, "ctc": ctc,
                "input": {"ctc": ctc, "rent_paid": 0, "city": "metro", "nps_opted": False, "current_structure": None},
                "computed": computed,
            })
        result = review_queue.create_submission("batch", rows)
        sid = result["submission_id"]

        review_queue.decide_row(sid, 0, "approve", None)
        review_queue.decide_row(sid, 1, "reject", "over budget")
        # row 2 (Frank) left pending on purpose

        submission = review_queue.get_submission(sid)
        statuses = {r["row_index"]: r["status"] for r in submission["rows"]}
        self.assertEqual(statuses, {0: "approved", 1: "rejected", 2: "pending"})


class TestIdempotency(ReviewQueueTestCase):
    def test_duplicate_row_is_flagged_not_silently_reprocessed(self):
        computed = _optimize_response_for(ctc=1_800_000)
        row = {
            "employee_name": "Grace", "ctc": 1_800_000,
            "input": {"ctc": 1_800_000, "rent_paid": 0, "city": "metro", "nps_opted": False, "current_structure": None},
            "computed": computed,
        }
        first = review_queue.create_submission("single", [row])
        self.assertEqual(len(first["duplicates"]), 0)

        second = review_queue.create_submission("single", [row])
        self.assertEqual(len(second["duplicates"]), 1)
        self.assertEqual(len(second["inserted_row_ids"]), 0)

    def test_double_approve_does_not_double_write(self):
        computed = _optimize_response_for(ctc=1_800_000)
        result = review_queue.create_submission("single", [{
            "employee_name": "Heidi", "ctc": 1_800_000,
            "input": {"ctc": 1_800_000, "rent_paid": 0, "city": "metro", "nps_opted": False, "current_structure": None},
            "computed": computed,
        }])
        sid = result["submission_id"]
        first = review_queue.decide_row(sid, 0, "approve", None)
        second = review_queue.decide_row(sid, 0, "approve", None)
        self.assertFalse(first["already_decided"])
        self.assertTrue(second["already_decided"])
        self.assertEqual(second["current_status"], "approved")


class TestSalaryRevisionExport(unittest.TestCase):
    def test_xlsx_contains_real_corrected_values_and_honesty_label(self):
        employees = [{
            "employee_name": "Ivan", "ctc": 4_000_000,
            "current": {"basic": 1_800_000, "hra": 900_000, "lta": 100_000,
                        "special_allowance": 300_000, "employer_pf": 900_000, "employer_nps": 0},
            "corrected": {"basic": 2_000_000, "hra": 0, "lta": 0,
                          "special_allowance": 1_520_000, "employer_pf": 240_000, "employer_nps": 280_000},
        }]
        wb = build_salary_revision_workbook(employees)
        self.assertEqual(wb.sheetnames, ["Read Me", "Default Structure", "Custom Structure"])

        readme_text = " ".join(str(wb["Read Me"][f"A{i}"].value) for i in range(1, 9))
        self.assertIn(TEMPLATE_HONESTY_LABEL, readme_text)

        custom = wb["Custom Structure"]
        header = [c.value for c in custom[1]]
        row = [c.value for c in custom[2]]
        as_dict = dict(zip(header, row))
        self.assertEqual(as_dict["Employee Name"], "Ivan")
        self.assertEqual(as_dict["Basic"], employees[0]["corrected"]["basic"])
        self.assertEqual(as_dict["Employer NPS"], employees[0]["corrected"]["employer_nps"])

        default = wb["Default Structure"]
        self.assertEqual([c.value for c in default[2]], ["Ivan", 4_000_000])


class TestExportApprovedRow(ReviewQueueTestCase):
    """
    Covers the redundancy fix: New Hire Batch (which bypassed Finance
    review entirely) was removed, and /hr became the sole path for
    structuring new hires — which only works end-to-end if an approved
    row can actually be exported afterward. Exercises the real Flask
    routes, not review_queue.py directly, since this is HTTP-shaped
    behavior (status codes, response shape) that unit-level calls can't
    verify.
    """

    def setUp(self):
        super().setUp()
        self.client = flask_app.app.test_client()

    def _submit_and_approve(self, row):
        resp = self.client.post("/api/submissions", json={"source": "single", "row": row})
        self.assertEqual(resp.status_code, 200)
        submission_id = resp.get_json()["submission_id"]
        decide = self.client.post(f"/api/submissions/{submission_id}/rows/0/decide", json={"decision": "approve"})
        self.assertEqual(decide.status_code, 200)
        return submission_id

    def test_export_requires_approval_first(self):
        resp = self.client.post("/api/submissions", json={
            "source": "single",
            "row": {"employee_name": "Pending Export", "ctc": 1_800_000, "rent_paid": 0, "city": "metro", "nps_opted": False},
        })
        submission_id = resp.get_json()["submission_id"]
        export = self.client.post(f"/api/submissions/{submission_id}/rows/0/export")
        self.assertEqual(export.status_code, 400)
        self.assertIn("not approved", export.get_json()["error"])

    def test_new_hire_export_returns_razorpayx_payload_with_real_bank_details(self):
        submission_id = self._submit_and_approve({
            "employee_name": "Export Test", "ctc": 1_800_000, "rent_paid": 0, "city": "metro", "nps_opted": False,
            "band_min": 1_700_000, "band_max": 1_900_000,
            "bank_account_number": "1234567890", "ifsc": "HDFC0000001", "email": "export@test.com",
        })
        export = self.client.post(f"/api/submissions/{submission_id}/rows/0/export")
        self.assertEqual(export.status_code, 200)
        payout = export.get_json()["payouts"][0]
        self.assertEqual(payout["fund_account"]["bank_account"]["account_number"], "1234567890")
        self.assertEqual(payout["fund_account"]["bank_account"]["ifsc"], "HDFC0000001")

    def test_new_hire_export_without_bank_details_errors_clearly(self):
        # No bank_account_number/ifsc supplied at submission time — the
        # export must fail with a clear reason, not a generated payload
        # with fabricated or empty bank fields.
        submission_id = self._submit_and_approve({
            "employee_name": "No Bank", "ctc": 1_800_000, "rent_paid": 0, "city": "metro", "nps_opted": False,
        })
        export = self.client.post(f"/api/submissions/{submission_id}/rows/0/export")
        self.assertEqual(export.status_code, 400)
        self.assertIn("bank_account_number", export.get_json()["error"])

    def test_correction_export_returns_salary_revision_xlsx(self):
        submission_id = self._submit_and_approve({
            "employee_name": "Correction Export", "ctc": 4_000_000, "rent_paid": 500_000, "city": "metro", "nps_opted": False,
            "current_structure": {
                "basic": 1_800_000, "hra": 900_000, "lta": 100_000,
                "special_allowance": 300_000, "employer_pf": 900_000, "employer_nps": 0,
            },
        })
        export = self.client.post(f"/api/submissions/{submission_id}/rows/0/export")
        self.assertEqual(export.status_code, 200)
        self.assertIn("spreadsheet", export.content_type)

    def test_guardrail_runs_on_submission_when_band_supplied(self):
        # Real gap this closed: /api/submissions never ran
        # evaluate_band_guardrail() at all before the redundancy fix, so
        # an out-of-band offer could be approved with no guardrail signal
        # anywhere in the review queue.
        resp = self.client.post("/api/submissions", json={
            "source": "single",
            "row": {
                "employee_name": "Guardrail Check", "ctc": 5_000_000, "rent_paid": 0, "city": "metro", "nps_opted": False,
                "band_min": 1_000_000, "band_max": 2_000_000,  # CTC is well outside this band
            },
        })
        submission_id = resp.get_json()["submission_id"]
        submission = self.client.get(f"/api/submissions/{submission_id}").get_json()
        guardrail = submission["rows"][0]["computed"].get("guardrail")
        self.assertIsNotNone(guardrail)
        self.assertEqual(guardrail["verdict"], "flag")


class TestOptimizeBatchRouteRemoved(unittest.TestCase):
    def test_route_no_longer_exists(self):
        # The New Hire Batch mode this route powered bypassed Finance
        # review entirely, duplicating what /hr + /api/submissions already
        # do with a review step. Removed as part of the redundancy fix;
        # this guards against it quietly coming back.
        # static_url_path="" means Flask's own static-file catch-all still
        # matches this path for GET (and reports it as a 405 on POST,
        # since the catch-all only registers GET/HEAD/OPTIONS) — asserting
        # on the url_map directly is the actual signal that the route
        # itself is gone, not a specific status code that catch-all
        # routing happens to produce.
        rules = [r.rule for r in flask_app.app.url_map.iter_rules() if r.rule == "/api/optimize-batch"]
        self.assertEqual(rules, [])


class TestBatchAuditExceptionBreakdown(unittest.TestCase):
    """
    /api/batch-audit's summary used to report only two currency totals —
    no count of clean vs. flagged rows, and no breakdown by exception type.
    That meant a batch-demo narration like "54 clean, 6 flagged — 4 over
    the EPFO cap, 2 in the wrong regime" cited numbers nothing on screen
    could back up. These are real, verified rows: the regime-mismatch case
    was found by brute-force search over random structures and its exact
    current-vs-optimal regimes double-checked directly against
    optimizer.py before being hardcoded here.
    """

    def setUp(self):
        self.client = flask_app.app.test_client()

    def test_clean_flagged_and_exception_counts(self):
        rows = [
            {  # clean: this is optimize()'s own recommended structure for this
               # exact CTC/rent, so it's within the EPFO cap, in the right
               # regime, and has zero unclaimed savings by construction.
                "name": "Clean Row", "ctc": 1_800_000, "basic": 900_000, "hra": 0, "lta": 0,
                "special_allowance": 792_000, "employer_pf": 108_000, "employer_nps": 0,
                "nps_opted": False, "rent_paid": 0, "city": "metro",
                "band_min": 1_700_000, "band_max": 1_900_000,
            },
            {  # excess EPFO contribution: employer_pf + employer_nps > 750,000 ceiling
                "name": "Over EPFO Cap", "ctc": 4_000_000, "basic": 1_800_000, "hra": 900_000,
                "lta": 100_000, "special_allowance": 300_000, "employer_pf": 900_000,
                "employer_nps": 0, "nps_opted": False, "rent_paid": 500_000, "city": "metro",
                "band_min": 3_800_000, "band_max": 4_200_000,
            },
            {  # regime mismatch: current structure is best off under 'new', true optimum for this CTC is 'old'
                "name": "Wrong Regime", "ctc": 6_000_000, "basic": 1_600_000, "hra": 1_000_000,
                "lta": 50_000, "special_allowance": 3_310_000, "employer_pf": 40_000,
                "employer_nps": 0, "nps_opted": False, "rent_paid": 800_000, "city": "metro",
                "band_min": 5_800_000, "band_max": 6_200_000,
            },
        ]
        resp = self.client.post("/api/batch-audit", json={"rows": rows})
        self.assertEqual(resp.status_code, 200)
        summary = resp.get_json()["summary"]

        self.assertEqual(summary["total_rows"], 3)
        self.assertEqual(summary["clean_count"], 1)
        self.assertEqual(summary["flagged_count"], 2)
        self.assertEqual(summary["epfo_cap_exceeded_count"], 1)
        self.assertEqual(summary["regime_mismatch_count"], 1)

        result_rows = resp.get_json()["rows"]
        wrong_regime_row = next(r for r in result_rows if r["name"] == "Wrong Regime")
        self.assertTrue(wrong_regime_row["regime_mismatch"])
        self.assertEqual(wrong_regime_row["current_regime"], "new")

        over_cap_row = next(r for r in result_rows if r["name"] == "Over EPFO Cap")
        self.assertGreater(over_cap_row["excess_contribution"], 0)
        self.assertFalse(over_cap_row["regime_mismatch"])

        clean_row = next(r for r in result_rows if r["name"] == "Clean Row")
        self.assertEqual(clean_row["excess_contribution"], 0)
        self.assertFalse(clean_row["regime_mismatch"])


if __name__ == "__main__":
    unittest.main()
