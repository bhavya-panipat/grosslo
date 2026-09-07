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

review_queue.DB_SCHEMA = "test_auth_queue"

import app as flask_app
from auth import verify_login

TEST_SCHEMA = "test_auth_queue"


def tearDownModule():
    review_queue._drop_schema(TEST_SCHEMA)


def _grant_tenant(client, tenant_id):
    """
    Puts tenant_id into the signed session directly.

    SCAFFOLD — STEP 5 DELETES THIS. /api/auth/login does not resolve a tenant
    yet; that is section 7 step 5's job. Without this, every route test would
    401 at require_tenant with no legitimate way to obtain a tenant context,
    and step 3's actual subject — required tenant_id, unconditional
    WHERE tenant_id, and the RLS policies — would go unexercised until step 5.
    Injecting the session value here tests step 3 now. When login resolves the
    tenant for real, these calls are removed and the assertions around them
    stay exactly as they are.
    """
    with client.session_transaction() as sess:
        sess["tenant_id"] = tenant_id


class AuthTestCase(unittest.TestCase):
    def setUp(self):
        review_queue.DB_SCHEMA = TEST_SCHEMA
        review_queue._drop_schema(TEST_SCHEMA)
        review_queue.init_db()
        # tenant_id is a NOT NULL FK as of step 2 and a required argument as of
        # step 3, so every tenant-scoped call needs a real tenant to reference.
        self.tenant_id = review_queue.create_tenant("acme", "Acme Corp")["id"]
        self.client = flask_app.app.test_client()
        # POST /api/submissions is now rate-limited per IP (module-level,
        # process-wide state) — reset before every test so unrelated tests
        # in this file don't trip each other's limit via the shared dict.
        flask_app._SUBMISSION_ATTEMPTS.clear()

    def tearDown(self):
        review_queue._drop_schema(TEST_SCHEMA)

    def _login(self, role, code):
        resp = self.client.post("/api/auth/login", json={"role": role, "code": code})
        # Only on success: a failed login must leave the session with no tenant,
        # which is one of the three cases require_tenant has to fail closed on.
        if resp.status_code == 200:
            _grant_tenant(self.client, self.tenant_id)
        return resp


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
        # Create a row to decide on first. Tenant-scoped since step 3, so the
        # client needs a tenant context; the point of this test is the ROLE
        # check on /decide, not who may create. (The logout below clears
        # tenant_id along with role, and _login re-grants it on success —
        # which is exactly what step 5 will do for real.)
        _grant_tenant(self.client, self.tenant_id)
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

    def test_create_submission_now_requires_a_tenant_context(self):
        """
        REVERSED IN STEP 3, and this is the most consequential behaviour change
        in the tenancy work so far — flagged rather than quietly patched.

        This test used to assert the opposite: that POST /api/submissions stays
        reachable with no session at all. That was a deliberate product
        decision with its own regression guard, because /optimize/batch's
        public "Submit correction" flow posts here without logging in, and
        api_create_submission's docstring still says in as many words: do not
        "fix" this route into requiring auth.

        Tenancy makes that position unholdable as written. The route WRITES
        rows, every row now needs a tenant_id, and there is no honest tenant to
        attribute an anonymous submission to. Inventing one (a default tenant,
        or trusting a tenant field in the body) is precisely what
        MULTI_TENANT_DESIGN.md 3.3 rejects — a client-supplied tenant id is
        unverified, and that is the isolation guarantee failing at the first
        hop. So section 7 step 3's "require_tenant on every tenant-scoped
        route" wins over the older comment, and the public flow is broken until
        something legitimately supplies a tenant.

        The intended repair is section 3.3's subdomain resolution:
        {tenant-slug}.grosslo.app identifies the tenant from the host, with no
        login required, which would restore the public flow WITHOUT trusting
        the request body. That is not built yet — it belongs with step 5's
        tenant resolution work — so this test records the current, deliberately
        closed state rather than pretending the old behaviour survives.
        """
        resp = self.client.post("/api/submissions", json={
            "source": "single", "row": {"ctc": 1_800_000},
        })
        self.assertEqual(resp.status_code, 401)
        # Never an empty-but-successful response: a caller must be able to tell
        # "not authorised" from "submitted, nothing happened" (3.1).
        self.assertIn("error", resp.get_json())

    def test_razorpayx_balance_requires_finance_session_before_anything_else(self):
        # Auth is checked before the not-configured/live-key checks
        # already covered in test_razorpayx_client.py.
        resp = self.client.get("/api/razorpayx/balance")
        self.assertEqual(resp.status_code, 401)

    def test_decided_by_comes_from_session_not_client_input(self):
        _grant_tenant(self.client, self.tenant_id)  # tenant-scoped since step 3
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
