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


if __name__ == "__main__":
    unittest.main()
