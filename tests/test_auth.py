"""
Tests for auth.py and the /api/auth/* routes, plus @require_role coverage
on the submissions read/decide/export/razorpayx-balance routes.

Real Flask test client throughout — a single client instance persists
cookies across calls within a test (Werkzeug's test client behaves like a
real browser session that way), so login -> protected call -> logout
sequences are exercised for real, not mocked.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import review_queue

review_queue.DB_PATH = "test_auth_queue.db"

import app as flask_app
from auth import verify_login

TEST_DB = "test_auth_queue.db"


def tearDownModule():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


class AuthTestCase(unittest.TestCase):
    def setUp(self):
        review_queue.DB_PATH = TEST_DB
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        review_queue.init_db()
        self.client = flask_app.app.test_client()
        # POST /api/submissions is now rate-limited per IP (module-level,
        # process-wide state) — reset before every test so unrelated tests
        # in this file don't trip each other's limit via the shared dict.
        flask_app._SUBMISSION_ATTEMPTS.clear()

    def tearDown(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)

    def _login(self, role, code):
        return self.client.post("/api/auth/login", json={"role": role, "code": code})


class TestVerifyLogin(unittest.TestCase):
    def test_correct_codes_verify(self):
        self.assertTrue(verify_login("hr", "HR2026"))
        self.assertTrue(verify_login("finance", "FINANCE2026"))

    def test_case_and_whitespace_insensitive(self):
        self.assertTrue(verify_login("hr", "  hr2026  "))

    def test_wrong_code_fails(self):
        self.assertFalse(verify_login("hr", "FINANCE2026"))
        self.assertFalse(verify_login("finance", "wrong"))

    def test_unknown_role_fails(self):
        self.assertFalse(verify_login("admin", "HR2026"))


class TestLoginLogoutSession(AuthTestCase):
    def test_correct_login_sets_session_and_returns_role(self):
        resp = self._login("hr", "HR2026")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["role"], "hr")

    def test_incorrect_login_returns_401_and_no_session(self):
        resp = self._login("hr", "WRONG")
        self.assertEqual(resp.status_code, 401)
        # No session established — a follow-up protected call still fails.
        follow_up = self.client.get("/api/submissions")
        self.assertEqual(follow_up.status_code, 401)

    def test_session_endpoint_reflects_login_state(self):
        before = self.client.get("/api/auth/session")
        self.assertIsNone(before.get_json()["role"])

        self._login("finance", "FINANCE2026")
        after = self.client.get("/api/auth/session")
        self.assertEqual(after.get_json()["role"], "finance")

    def test_logout_clears_session(self):
        self._login("finance", "FINANCE2026")
        self.assertEqual(self.client.get("/api/auth/session").get_json()["role"], "finance")

        logout = self.client.post("/api/auth/logout")
        self.assertEqual(logout.status_code, 200)
        self.assertIsNone(self.client.get("/api/auth/session").get_json()["role"])

        # A previously-working protected call now fails again.
        follow_up = self.client.get("/api/submissions")
        self.assertEqual(follow_up.status_code, 401)


class TestRouteProtection(AuthTestCase):
    def test_get_submissions_requires_a_session(self):
        self.assertEqual(self.client.get("/api/submissions").status_code, 401)

    def test_get_submissions_succeeds_for_either_role(self):
        self._login("hr", "HR2026")
        self.assertEqual(self.client.get("/api/submissions").status_code, 200)

        self.client.post("/api/auth/logout")
        self._login("finance", "FINANCE2026")
        self.assertEqual(self.client.get("/api/submissions").status_code, 200)

    def test_decide_requires_finance_specifically_not_just_any_login(self):
        # Create a row to decide on first (unauthenticated — create stays open).
        create = self.client.post("/api/submissions", json={
            "source": "single", "row": {"ctc": 1_800_000},
        })
        submission_id = create.get_json()["submission_id"]

        # HR session (wrong role) is rejected.
        self._login("hr", "HR2026")
        wrong_role = self.client.post(
            f"/api/submissions/{submission_id}/rows/0/decide",
            json={"decision": "approve"},
        )
        self.assertEqual(wrong_role.status_code, 401)

        # Finance session succeeds.
        self.client.post("/api/auth/logout")
        self._login("finance", "FINANCE2026")
        right_role = self.client.post(
            f"/api/submissions/{submission_id}/rows/0/decide",
            json={"decision": "approve"},
        )
        self.assertEqual(right_role.status_code, 200)

    def test_export_requires_finance_session(self):
        self.assertEqual(
            self.client.post("/api/submissions/1/rows/0/export").status_code, 401,
        )

    def test_create_submission_stays_open_with_no_session(self):
        # The deliberate non-gating decision — this is the regression
        # guard: a future "fix" that adds @require_role here would break
        # /optimize/batch's public audit-correction flow, and this test
        # would catch it.
        resp = self.client.post("/api/submissions", json={
            "source": "single", "row": {"ctc": 1_800_000},
        })
        self.assertEqual(resp.status_code, 200)

    def test_razorpayx_balance_requires_finance_session_before_anything_else(self):
        # Auth is checked before the not-configured/live-key checks
        # already covered in test_razorpayx_client.py.
        resp = self.client.get("/api/razorpayx/balance")
        self.assertEqual(resp.status_code, 401)

    def test_decided_by_comes_from_session_not_client_input(self):
        create = self.client.post("/api/submissions", json={
            "source": "single", "row": {"ctc": 1_800_000},
        })
        submission_id = create.get_json()["submission_id"]

        self._login("finance", "FINANCE2026")
        self.client.post(
            f"/api/submissions/{submission_id}/rows/0/decide",
            # A client-supplied decided_by must be ignored, not trusted.
            json={"decision": "approve", "decided_by": "someone-else"},
        )

        submission = self.client.get(f"/api/submissions/{submission_id}").get_json()
        self.assertEqual(submission["rows"][0]["decided_by"], "finance")


if __name__ == "__main__":
    unittest.main()
