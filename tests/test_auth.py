"""
Tests for auth.py and the /api/auth/* routes, plus @require_permission coverage
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
from auth import verify_login, hash_access_code, hash_password

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



# --- Phase 1.2 step 4: real users replace the shared-code login ------------
# The access codes no longer produce a usable session; they bootstrap a
# tenant's first owner once and then retire (IDENTITY_DESIGN.md 3.3). Tests
# therefore provision actual accounts.
#
# The hash is computed ONCE per module for the same reason the code hashes
# above are: pbkdf2 is deliberately ~0.5s, which is correct in production and
# would add minutes across a suite that rebuilds its schema for every test.
# The user is inserted with that pre-computed hash rather than through
# create_user(password=...), which would re-hash per test.
_TEST_PASSWORD = "test-user-password"
_TEST_PASSWORD_HASH = hash_password(_TEST_PASSWORD)


def _ensure_user(tenant_id, role):
    """Creates (once per schema) a user holding `role`, and returns its email."""
    email = f"{role}@acme.test"
    if review_queue.get_user_by_email(tenant_id, email) is None:
        user = review_queue.create_user(tenant_id, email, role.title(), [role])
        with review_queue._conn(tenant_id) as conn:
            conn.execute(
                "UPDATE users SET password_hash = %s WHERE tenant_id = %s AND id = %s",
                (_TEST_PASSWORD_HASH, tenant_id, user["id"]),
            )
    return email


def _login_as(client, role, code=None):
    """
    Logs in as a REAL USER holding `role` (step 4). `code` is accepted and
    ignored so call sites read unchanged; the shared codes it used to pass no
    longer produce a session.
    """
    tenant = review_queue.get_tenant_by_slug("acme")
    email = _ensure_user(tenant["id"], role)
    return client.post("/api/auth/login",
                       json={"email": email, "password": _TEST_PASSWORD})


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

    def _login(self, role, code=None):
        """
        Logs in as a REAL USER holding `role` (step 4). The tenant still comes
        from the subdomain in base_url; what changed is that the credential is
        now a person's password rather than a shared code. `code` is accepted
        and ignored so call sites read unchanged.

        A failed login still leaves the session with no tenant at all, which is
        one of the three cases require_tenant fails closed on.
        """
        email = _ensure_user(self.tenant_id, role)
        return self.client.post("/api/auth/login",
                                json={"email": email, "password": _TEST_PASSWORD})


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
    def test_correct_login_returns_the_user_and_their_roles(self):
        # Step 4: login answers with a PERSON, not a role string. This is the
        # visible half of IDENTITY_DESIGN.md §2 — an action is now traceable to
        # someone who can be asked why.
        resp = self._login("hr", "HR2026")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["user"]["roles"], ["hr"])
        self.assertEqual(body["user"]["email"], "hr@acme.test")
        self.assertNotIn("role", body, "the shared-role response shape is gone")

    def test_incorrect_login_returns_401_and_no_session(self):
        _ensure_user(self.tenant_id, "hr")
        resp = self.client.post("/api/auth/login",
                                json={"email": "hr@acme.test", "password": "WRONG"})
        self.assertEqual(resp.status_code, 401)
        # No session established — a follow-up protected call still fails.
        follow_up = self.client.get("/api/submissions")
        self.assertEqual(follow_up.status_code, 401)

    def test_session_endpoint_reflects_login_state(self):
        before = self.client.get("/api/auth/session")
        self.assertIsNone(before.get_json()["user_id"])
        self.assertEqual(before.get_json()["roles"], [])

        self._login("finance", "FINANCE2026")
        after = self.client.get("/api/auth/session")
        self.assertEqual(after.get_json()["roles"], ["finance"])
        self.assertIsNotNone(after.get_json()["user_id"])

    def test_logout_clears_session(self):
        self._login("finance", "FINANCE2026")
        self.assertEqual(self.client.get("/api/auth/session").get_json()["roles"], ["finance"])

        logout = self.client.post("/api/auth/logout")
        self.assertEqual(logout.status_code, 200)
        self.assertIsNone(self.client.get("/api/auth/session").get_json()["user_id"])
        self.assertEqual(self.client.get("/api/auth/session").get_json()["roles"], [])

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


# ---------------------------------------------------------------------------
# Phase 1.2 step 2 — permission-based enforcement (IDENTITY_DESIGN.md 3.1).
# ---------------------------------------------------------------------------

class TestPermissionCatalogue(unittest.TestCase):
    """
    The catalogue and mapping, tested directly rather than only through routes,
    because their whole purpose is to be the one place a reviewer can read to
    know who may do what.
    """

    def test_every_role_grants_only_defined_permissions(self):
        from auth import PERMISSIONS, ROLE_PERMISSIONS
        for role, granted in ROLE_PERMISSIONS.items():
            unknown = set(granted) - set(PERMISSIONS)
            self.assertEqual(unknown, set(), f"{role} grants undefined permission(s) {unknown}")

    def test_unknown_permission_raises_rather_than_denying_quietly(self):
        # A typo must not read as a plain 403/401. Returning False would make a
        # misspelled guard look like a working one that simply refuses.
        from auth import has_permission, require_permission
        with self.assertRaises(ValueError):
            has_permission("veiw_queue")
        with self.assertRaises(ValueError):
            require_permission("not_a_real_permission")

    def test_submit_row_is_deliberately_not_a_permission(self):
        # POST /api/submissions is unauthenticated by design (1.1 §3.3). A
        # permission for it would imply an enforcement point that does not
        # exist.
        from auth import PERMISSIONS
        self.assertNotIn("submit_row", PERMISSIONS)

    def test_owner_holds_every_permission(self):
        from auth import PERMISSIONS, ROLE_PERMISSIONS
        self.assertEqual(set(ROLE_PERMISSIONS["owner"]), set(PERMISSIONS))

    def test_mapping_preserves_exactly_todays_access(self):
        # The property that makes step 2 safe: hr and finance keep precisely
        # what the routes enforced before the swap. hr holds view_audit_log
        # because /api/audit-log was guarded by @require_tenant alone and both
        # roles could already read it.
        from auth import ROLE_PERMISSIONS
        self.assertEqual(set(ROLE_PERMISSIONS["hr"]), {"view_queue", "view_audit_log"})
        self.assertEqual(set(ROLE_PERMISSIONS["finance"]),
                         {"view_queue", "decide_row", "export_row",
                          "view_audit_log", "view_bank_balance"})

    def test_require_role_is_gone_not_merely_unused(self):
        # Superseded enforcement must not remain reachable, or a future route
        # gets written against the mechanism this phase replaced.
        import auth
        self.assertFalse(hasattr(auth, "require_role"))


class TestPermissionSessionBridge(unittest.TestCase):
    """
    current_roles() spans two session shapes: the shared `role` string that
    exists until step 4, and the per-user `roles` list that replaces it. Step 4
    must be additive, so both are asserted now.
    """

    def test_reads_the_legacy_single_role(self):
        with flask_app.app.test_request_context():
            from flask import session
            session["role"] = "finance"
            from auth import current_roles, has_permission
            self.assertEqual(current_roles(), ["finance"])
            self.assertTrue(has_permission("decide_row"))

    def test_prefers_the_per_user_roles_list_when_present(self):
        with flask_app.app.test_request_context():
            from flask import session
            session["role"] = "hr"
            session["roles"] = ["finance"]
            from auth import current_roles, has_permission
            self.assertEqual(current_roles(), ["finance"])
            self.assertTrue(has_permission("decide_row"),
                            "the per-user list must win once step 4 sets it")

    def test_no_session_grants_nothing(self):
        with flask_app.app.test_request_context():
            from auth import current_roles, has_permission
            self.assertEqual(current_roles(), [])
            for perm in ("view_queue", "decide_row", "manage_users"):
                self.assertFalse(has_permission(perm))


class TestBootstrapRetiresSharedCodes(AuthTestCase):
    """
    IDENTITY_DESIGN.md §3.3. The shared access code's only remaining power is
    to create exactly one named account, once, and then stop existing — which
    is what makes §2's second clause ("no state-changing action can be
    performed by a principal the system cannot name") true rather than
    aspirational.
    """

    def _code_login(self):
        return self.client.post("/api/auth/login",
                                json={"role": "finance", "code": "FINANCE2026"})

    def test_code_login_yields_a_session_that_can_do_nothing_else(self):
        resp = self._code_login()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["bootstrap_required"])
        # No tenant_id in the session, so every guarded route refuses it. A
        # session minted from a shared secret never gets to act as a person.
        self.assertEqual(self.client.get("/api/submissions").status_code, 401)
        self.assertEqual(self.client.get("/api/users").status_code, 401)
        self.assertIsNone(self.client.get("/api/auth/session").get_json()["user_id"])

    def test_bootstrap_creates_an_owner_and_retires_the_codes(self):
        self._code_login()
        resp = self.client.post("/api/auth/bootstrap", json={
            "email": "ada@acme.test", "display_name": "Ada", "password": "S3cretPassw0rd"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["user"]["roles"], ["owner"])
        self.assertTrue(resp.get_json()["shared_codes_retired"])
        # The session is now a real person's and works everywhere owner does.
        self.assertEqual(self.client.get("/api/submissions").status_code, 200)
        self.assertEqual(self.client.get("/api/users").status_code, 200)

    def test_the_code_works_exactly_once(self):
        self._code_login()
        self.client.post("/api/auth/bootstrap", json={
            "email": "ada@acme.test", "display_name": "Ada", "password": "S3cretPassw0rd"})
        again = _client().post("/api/auth/login",
                               json={"role": "finance", "code": "FINANCE2026"})
        self.assertEqual(again.status_code, 401)
        self.assertIn("no longer used", again.get_json()["error"])

    def test_codes_are_dead_once_any_user_exists_even_before_bootstrap(self):
        # BOTH conditions, not either (§3.3): a tenant provisioned by the admin
        # CLI never had a bootstrap, and must not still have an open back door.
        review_queue.create_user(self.tenant_id, "cli@acme.test", "CLI", ["owner"])
        resp = self._code_login()
        self.assertEqual(resp.status_code, 401)

    def test_retired_hashes_are_kept_as_a_record_not_nulled(self):
        # §6's resolved decision: nulling would destroy the evidence that a
        # shared secret existed and was correctly retired.
        self._code_login()
        self.client.post("/api/auth/bootstrap", json={
            "email": "ada@acme.test", "display_name": "Ada", "password": "S3cretPassw0rd"})
        hashes = review_queue.get_tenant_access_code_hashes(self.tenant_id)
        self.assertIsNotNone(hashes["hr"])
        self.assertIsNotNone(hashes["finance"])
        self.assertIsNotNone(
            review_queue.get_tenant_bootstrap_state(self.tenant_id)["codes_disabled_at"])

    def test_bootstrap_rechecks_rather_than_trusting_its_own_session(self):
        # The session was minted earlier; another request or the admin CLI may
        # have created the first user in between. This is what makes the code
        # single-use under a replayed or concurrent request.
        self._code_login()
        review_queue.create_user(self.tenant_id, "race@acme.test", "Race", ["owner"])
        resp = self.client.post("/api/auth/bootstrap", json={
            "email": "ada@acme.test", "display_name": "Ada", "password": "S3cretPassw0rd"})
        self.assertEqual(resp.status_code, 409)
        self.assertIsNone(review_queue.get_user_by_email(self.tenant_id, "ada@acme.test"))

    def test_bootstrap_requires_a_bootstrap_session(self):
        self.assertEqual(
            _client().post("/api/auth/bootstrap", json={
                "email": "x@acme.test", "display_name": "X", "password": "S3cretPassw0rd"}).status_code,
            401)

    def test_bootstrap_refuses_a_weak_password(self):
        self._code_login()
        resp = self.client.post("/api/auth/bootstrap", json={
            "email": "ada@acme.test", "display_name": "Ada", "password": "short"})
        self.assertEqual(resp.status_code, 400)
        self.assertIsNone(review_queue.get_user_by_email(self.tenant_id, "ada@acme.test"))
        self.assertIsNone(
            review_queue.get_tenant_bootstrap_state(self.tenant_id)["codes_disabled_at"],
            "a rejected bootstrap must not retire the codes")


class TestLoginIsNotAnEnumerationOracle(AuthTestCase):
    """
    §3.5. Named accounts are enumerable in a way one shared code was not, so
    login must not confirm which addresses exist.
    """

    def test_unknown_email_and_wrong_password_are_indistinguishable(self):
        _ensure_user(self.tenant_id, "finance")
        unknown = self.client.post("/api/auth/login",
                                   json={"email": "ghost@acme.test", "password": _TEST_PASSWORD})
        wrong = self.client.post("/api/auth/login",
                                 json={"email": "finance@acme.test", "password": "nope"})
        self.assertEqual(unknown.status_code, wrong.status_code)
        self.assertEqual(unknown.get_json(), wrong.get_json())

    def test_a_disabled_user_cannot_log_in_and_looks_the_same(self):
        _ensure_user(self.tenant_id, "finance")
        user = review_queue.get_user_by_email(self.tenant_id, "finance@acme.test")
        review_queue.set_user_status(self.tenant_id, user["id"], "disabled")
        resp = self.client.post("/api/auth/login",
                                json={"email": "finance@acme.test", "password": _TEST_PASSWORD})
        self.assertEqual(resp.status_code, 401)
        self.assertIn("don't match", resp.get_json()["error"])

    def test_a_user_with_no_password_cannot_log_in(self):
        # The state an SSO-provisioned user will be in from 1.3, and the state
        # create_owner.py leaves an account provisioned ahead of its person.
        review_queue.create_user(self.tenant_id, "nopw@acme.test", "No Password", ["finance"])
        resp = self.client.post("/api/auth/login",
                                json={"email": "nopw@acme.test", "password": ""})
        self.assertEqual(resp.status_code, 401)

    def test_a_user_of_another_tenant_cannot_log_in_here(self):
        other = review_queue.create_tenant("globex", "Globex")["id"]
        review_queue.create_tenant_settings(other, _HR_CODE_HASH, _FINANCE_CODE_HASH)
        _ensure_user(other, "finance")
        # Same email, but this client is on acme's subdomain.
        resp = self.client.post("/api/auth/login",
                                json={"email": "finance@acme.test", "password": _TEST_PASSWORD})
        self.assertEqual(resp.status_code, 401)
