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
from flask.testing import FlaskClient
from auth import verify_login, hash_access_code

TEST_SCHEMA = "test_auth_queue"


def tearDownModule():
    review_queue._drop_schema(TEST_SCHEMA)


# Every request in these tests arrives on a tenant subdomain, the way a real
# one does (MULTI_TENANT_DESIGN.md 3.3), so tenant resolution runs for real
# rather than being stubbed.
TENANT_HOST = "http://acme.grosslo.app/"


class _TenantTestClient(FlaskClient):
    """
    Sends every request to the tenant subdomain, so tenant resolution runs the
    way it does in production (MULTI_TENANT_DESIGN.md 3.3) instead of being
    stubbed. Set on the client rather than passed per call: a request that
    silently went to a host with no tenant label would 401 in a way that looks
    like a real authorisation bug, and one forgotten base_url= is all it takes.
    A test that deliberately wants a different host still passes base_url.
    """

    def open(self, *args, **kwargs):
        kwargs.setdefault("base_url", TENANT_HOST)
        return super().open(*args, **kwargs)


def _client():
    flask_app.app.test_client_class = _TenantTestClient
    return flask_app.app.test_client()


# Hashed once per module, not once per setUp: pbkdf2 is deliberately slow
# (~0.5s a hash), which is right in production and would add minutes across a
# suite that rebuilds its schema for every test. The value under test is that
# login checks a stored HASH, not how many times this suite recomputes one.
_HR_CODE_HASH = hash_access_code("HR2026")
_FINANCE_CODE_HASH = hash_access_code("FINANCE2026")



def _login_as(client, role, code):
    """
    Logs in for real: the tenant comes from the request's subdomain and the
    code is checked against THAT TENANT's stored hash (step 5).

    This replaces step 3's _grant_tenant() scaffold, which injected tenant_id
    into the session directly because login could not yet resolve a tenant.
    The scaffold is gone; the assertions it supported are unchanged.
    """
    return client.post("/api/auth/login",
                       json={"role": role, "code": code})


class AuthTestCase(unittest.TestCase):
    def setUp(self):
        review_queue.DB_SCHEMA = TEST_SCHEMA
        review_queue._drop_schema(TEST_SCHEMA)
        review_queue.init_db()
        # tenant_id is a NOT NULL FK as of step 2 and a required argument as of
        # step 3, so every tenant-scoped call needs a real tenant to reference.
        self.tenant_id = review_queue.create_tenant("acme", "Acme Corp")["id"]
        review_queue.create_tenant_settings(
            self.tenant_id, _HR_CODE_HASH, _FINANCE_CODE_HASH)
        self.client = _client()
        # POST /api/submissions is now rate-limited per IP (module-level,
        # process-wide state) — reset before every test so unrelated tests
        # in this file don't trip each other's limit via the shared dict.
        flask_app._SUBMISSION_ATTEMPTS.clear()

    def tearDown(self):
        review_queue._drop_schema(TEST_SCHEMA)

    def _login(self, role, code):
        # Real login as of step 5: the tenant comes from the subdomain in
        # base_url and the code is checked against that tenant's stored hash.
        # A failed login leaves the session with no tenant at all, which is one
        # of the three cases require_tenant has to fail closed on — nothing
        # here has to arrange that any more, it just happens.
        return self.client.post("/api/auth/login",
                                json={"role": role, "code": code})


class TestVerifyLogin(AuthTestCase):
    """
    Access codes are PER TENANT as of step 5 (3.3's interim model), so
    verify_login takes a tenant_id and checks a stored hash rather than
    comparing against one process-wide pair of plaintext constants.
    """

    def test_correct_codes_verify(self):
        self.assertTrue(verify_login(self.tenant_id, "hr", "HR2026"))
        self.assertTrue(verify_login(self.tenant_id, "finance", "FINANCE2026"))

    def test_case_and_whitespace_insensitive(self):
        self.assertTrue(verify_login(self.tenant_id, "hr", "  hr2026  "))

    def test_wrong_code_fails(self):
        self.assertFalse(verify_login(self.tenant_id, "hr", "FINANCE2026"))
        self.assertFalse(verify_login(self.tenant_id, "finance", "wrong"))

    def test_unknown_role_fails(self):
        self.assertFalse(verify_login(self.tenant_id, "admin", "HR2026"))

    def test_a_tenants_code_does_not_unlock_another_tenant(self):
        """
        The reason the global _DEFAULT_CODES pair had to go. With one HR code
        for the whole process, the same shared secret opened every company's
        queue — which is not a hardening gap, it is the isolation guarantee
        failing at the login screen.
        """
        other = review_queue.create_tenant("globex", "Globex")["id"]
        review_queue.create_tenant_settings(
            other, hash_access_code("GLOBEX-HR"), hash_access_code("GLOBEX-FIN"))

        self.assertTrue(verify_login(other, "hr", "GLOBEX-HR"))
        self.assertFalse(verify_login(other, "hr", "HR2026"))
        self.assertFalse(verify_login(self.tenant_id, "hr", "GLOBEX-HR"))

    def test_tenant_with_no_settings_cannot_be_logged_into(self):
        # Fails closed rather than falling back to something that would work.
        bare = review_queue.create_tenant("bare", "Bare Co")["id"]
        self.assertFalse(verify_login(bare, "hr", "HR2026"))


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

    def test_create_submission_is_public_again_via_subdomain_resolution(self):
        """
        FLAG 1, RESOLVED IN STEP 5 — and this test has now been written three
        ways, which is the honest record of what happened.

        Originally it asserted the route stays reachable with no session at
        all, guarding a deliberate product decision: /optimize/batch's public
        "Submit correction" flow posts here without logging in.

        Step 3 broke that. Rows need a tenant_id, nothing supplied one for an
        anonymous request, and inventing a default or trusting a body field is
        what 3.3 rejects outright. So the route was closed and this test was
        reversed to record the closure rather than pretend it hadn't happened.
        It stayed closed for two commits, logged as a known regression, and was
        deliberately NOT patched early — collapsing step 5's work into step 3
        would have destroyed the per-step attributability the sequencing exists
        for.

        Step 5 repairs it properly: the tenant comes from the SUBDOMAIN
        (3.3), which needs no login, so the public flow works again and no
        client-supplied tenant value is ever trusted.
        """
        resp = self.client.post("/api/submissions", json={
            "source": "single", "row": {"ctc": 1_800_000},
        })
        self.assertEqual(resp.status_code, 200, "public submission must work on a tenant subdomain")
        self.assertEqual(
            review_queue.get_submission(self.tenant_id, resp.get_json()["submission_id"])["rows"][0]["ctc"],
            1_800_000,
            "the row must land in the subdomain's tenant",
        )

    def test_create_submission_still_fails_closed_on_a_host_with_no_tenant(self):
        # The repair must not have turned into "anyone, anywhere". A host that
        # names no tenant gets the same hard 401 — never a default tenant, and
        # never a silent success that writes nowhere.
        resp = self.client.post("/api/submissions", base_url="http://localhost/", json={
            "source": "single", "row": {"ctc": 1_800_000},
        })
        self.assertEqual(resp.status_code, 401)
        self.assertIn("error", resp.get_json())

    def test_submission_subdomain_grants_write_only_never_read(self):
        # The Host header is client-supplied, so subdomain resolution is
        # deliberately confined to this one already-public write. Reads take
        # their tenant from the signed session, so arriving on a tenant's
        # subdomain with no session must not read that tenant's queue.
        self.client.post("/api/submissions", json={
            "source": "single", "row": {"ctc": 1_800_000},
        })
        self.assertEqual(self.client.get("/api/submissions").status_code, 401)

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
