"""
Phase 1.2's exit criteria, as tests (IDENTITY_DESIGN.md §7 step 7).

Four claims, kept in separate classes because they are separate claims and one
cannot stand in for another:

  1. TestPermissionMatrix — every permission-guarded route is driven by every
     role, and refuses with 403 exactly when that role lacks the permission.
     Asserted by MAKING THE REQUESTS, never by reading decorators: a decorator
     can be present and mis-ordered (it was — see the 403 commit), or present
     and guarding the wrong permission, and inspection catches neither.

  2. TestStateChangingRoutesRecordAUser — §2's guarantee, that every
     state-changing action is attributable to exactly one identified human.

  3. TestUserCrossTenantIsolation — extends 1.1's suite to the identity tables:
     a user of tenant A cannot be listed, edited or authenticated into tenant
     B, at the application layer and again with the query wrapper bypassed.

  4. TestSharedCodeRetirementIsComplete — the code works exactly once and never
     again, including once the account it created is gone.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import review_queue

review_queue.DB_SCHEMA = "test_identity"

import psycopg
from psycopg.rows import dict_row
from flask.testing import FlaskClient

import app as flask_app
from auth import hash_access_code, hash_password, ROLE_PERMISSIONS

TEST_SCHEMA = "test_identity"
ALPHA_HOST = "http://alpha.grosslo.app/"
BETA_HOST = "http://beta.grosslo.app/"

_HR_HASH = hash_access_code("HR2026")
_FIN_HASH = hash_access_code("FINANCE2026")
_PASSWORD = "test-user-password"
_PASSWORD_HASH = hash_password(_PASSWORD)


def _client_for(host):
    class _HostClient(FlaskClient):
        def open(self, *args, **kwargs):
            kwargs.setdefault("base_url", host)
            return super().open(*args, **kwargs)
    flask_app.app.test_client_class = _HostClient
    return flask_app.app.test_client()


class IdentityTestCase(unittest.TestCase):
    def setUp(self):
        review_queue.DB_SCHEMA = TEST_SCHEMA
        review_queue._drop_schema(TEST_SCHEMA)
        review_queue.init_db()
        flask_app._SUBMISSION_ATTEMPTS.clear()
        flask_app._LOGIN_ATTEMPTS.clear()
        self.alpha = review_queue.create_tenant("alpha", "Alpha Ltd")["id"]
        self.beta = review_queue.create_tenant("beta", "Beta Ltd")["id"]
        review_queue.create_tenant_settings(self.alpha, _HR_HASH, _FIN_HASH)
        review_queue.create_tenant_settings(self.beta, _HR_HASH, _FIN_HASH)

    def tearDown(self):
        review_queue._drop_schema(TEST_SCHEMA)
        flask_app._LOGIN_ATTEMPTS.clear()

    def _user(self, tenant_id, role, email=None):
        email = email or f"{role}@t{tenant_id}.test"
        existing = review_queue.get_user_by_email(tenant_id, email)
        if existing:
            return existing
        user = review_queue.create_user(tenant_id, email, role.title(), [role])
        with review_queue._conn(tenant_id) as conn:
            conn.execute("UPDATE users SET password_hash = %s WHERE tenant_id = %s AND id = %s",
                         (_PASSWORD_HASH, tenant_id, user["id"]))
        return user

    def _as(self, host, tenant_id, role):
        user = self._user(tenant_id, role)
        client = _client_for(host)
        resp = client.post("/api/auth/login",
                           json={"email": user["email"], "password": _PASSWORD})
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        return client, user


# ---------------------------------------------------------------------------
# 1. Authorisation
# ---------------------------------------------------------------------------

# (permission, method, concrete URL). Ids that do not exist are fine: the
# assertion is only ever "was this refused for lack of permission", so a
# permitted role reaching a 404 still proves the guard let it through.
GUARDED_ROUTES = [
    ("view_queue",        "GET",  "/api/submissions"),
    ("view_queue",        "GET",  "/api/submissions/1"),
    ("decide_row",        "POST", "/api/submissions/1/rows/0/decide"),
    ("export_row",        "POST", "/api/submissions/1/rows/0/export"),
    ("export_row",        "POST", "/api/submissions/1/rows/0/complete"),
    ("view_audit_log",    "GET",  "/api/audit-log"),
    ("manage_users",      "GET",  "/api/users"),
    ("manage_users",      "POST", "/api/users"),
    ("manage_users",      "PUT",  "/api/users/1/roles"),
    ("manage_users",      "PUT",  "/api/users/1/status"),
    ("view_bank_balance", "GET",  "/api/razorpayx/balance"),
]


class TestPermissionMatrix(IdentityTestCase):

    def test_the_matrix_covers_every_permission_guarded_route(self):
        """
        Guards against the table above going stale. A route added later with a
        permission guard and no case here would otherwise be silently
        untested — the coverage gap looks identical to full coverage.
        """
        import re
        src = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "app.py")).read()
        found = set()
        for deco, _fn in re.findall(r'((?:@app\.route\([^\n]*\)\n)(?:@[^\n]+\n)*)def (\w+)', src):
            perms = re.findall(r'@require_permission\("(\w+)"\)', deco)
            for route in re.findall(r'@app\.route\("([^"]+)"', deco):
                if perms:
                    found.add((perms[0], route))
        covered = {(p, re.sub(r"/\d+", "/<int>", u)) for p, _m, u in GUARDED_ROUTES}
        missing = {(p, r) for p, r in found
                   if (p, re.sub(r"<[^>]+>", "<int>", r)) not in covered}
        self.assertEqual(missing, set(),
                         f"permission-guarded routes with no matrix case: {missing}")

    def test_every_role_is_refused_exactly_where_it_lacks_the_permission(self):
        for role in ("hr", "finance", "owner"):
            client, _ = self._as(ALPHA_HOST, self.alpha, role)
            granted = ROLE_PERMISSIONS[role]
            for permission, method, url in GUARDED_ROUTES:
                with self.subTest(role=role, permission=permission, url=url):
                    resp = client.open(url, method=method, json={})
                    if permission in granted:
                        self.assertNotEqual(
                            resp.status_code, 403,
                            f"{role} holds {permission} but was refused at {method} {url}")
                    else:
                        self.assertEqual(
                            resp.status_code, 403,
                            f"{role} lacks {permission} and was NOT refused at "
                            f"{method} {url} (got {resp.status_code})")

    def test_an_unidentified_caller_gets_401_not_403_everywhere(self):
        # The distinction the 403 commit established: 401 answers "who are
        # you?", 403 answers "you may not". A guard order that evaluates
        # permission first would leak a judgement about an unidentified caller.
        client = _client_for(ALPHA_HOST)
        for _permission, method, url in GUARDED_ROUTES:
            with self.subTest(url=url):
                self.assertEqual(client.open(url, method=method, json={}).status_code, 401)

    def test_a_user_with_no_roles_can_authenticate_and_do_nothing(self):
        # A coherent state (an invited account awaiting assignment), and the
        # cleanest proof that permissions and not sessions are what authorise.
        user = review_queue.create_user(self.alpha, "noroles@alpha.test", "No Roles", [])
        with review_queue._conn(self.alpha) as conn:
            conn.execute("UPDATE users SET password_hash = %s WHERE tenant_id = %s AND id = %s",
                         (_PASSWORD_HASH, self.alpha, user["id"]))
        client = _client_for(ALPHA_HOST)
        self.assertEqual(client.post("/api/auth/login", json={
            "email": "noroles@alpha.test", "password": _PASSWORD}).status_code, 200)
        for _permission, method, url in GUARDED_ROUTES:
            with self.subTest(url=url):
                self.assertEqual(client.open(url, method=method, json={}).status_code, 403)


# ---------------------------------------------------------------------------
# 2. Attribution
# ---------------------------------------------------------------------------

class TestStateChangingRoutesRecordAUser(IdentityTestCase):

    def setUp(self):
        super().setUp()
        self._orig_audit = flask_app.AUDIT_LOG_PATH
        flask_app.AUDIT_LOG_PATH = "test_identity_audit.jsonl"
        if os.path.exists(flask_app.AUDIT_LOG_PATH):
            os.remove(flask_app.AUDIT_LOG_PATH)

    def tearDown(self):
        if os.path.exists(flask_app.AUDIT_LOG_PATH):
            os.remove(flask_app.AUDIT_LOG_PATH)
        flask_app.AUDIT_LOG_PATH = self._orig_audit
        super().tearDown()

    def _lines(self):
        if not os.path.exists(flask_app.AUDIT_LOG_PATH):
            return []
        with open(flask_app.AUDIT_LOG_PATH) as f:
            return [json.loads(l) for l in f if l.strip()]

    def test_every_authenticated_state_change_names_its_actor(self):
        client, actor = self._as(ALPHA_HOST, self.alpha, "owner")
        sub = review_queue.create_submission(self.alpha, "single", [{
            "employee_name": "E", "ctc": 1_800_000,
            "input": {"ctc": 1_800_000, "rent_paid": 0, "city": "metro",
                      "nps_opted": False, "current_structure": None},
            "computed": flask_app._build_optimize_response(
                1_800_000, 0, "metro", False, None, False, skip_ai=True)[0],
        }])["submission_id"]
        client.post(f"/api/submissions/{sub}/rows/0/decide", json={"decision": "approve"})
        client.post("/api/users", json={"email": "new@alpha.test",
                                        "display_name": "New", "roles": ["hr"]})
        lines = [e for e in self._lines() if e["route"] != "/api/submissions"]
        self.assertTrue(lines)
        for entry in lines:
            self.assertEqual(entry["user_id"], actor["id"],
                             f"{entry['route']} did not record who acted")
            self.assertEqual(entry["tenant_id"], self.alpha)

    def test_a_decision_by_one_user_is_never_attributed_to_another(self):
        rows = []
        # Two different people decide two different rows. The rows differ
        # because IDENTICAL rows in one tenant are a genuine duplicate and
        # _dedupe_hash correctly drops the second, leaving nothing to decide.
        computed = flask_app._build_optimize_response(
            1_800_000, 0, "metro", False, None, False, skip_ai=True)[0]
        for who, email in (("finance", None), ("owner", "second@alpha.test")):
            user = self._user(self.alpha, who, email=email)
            client = _client_for(ALPHA_HOST)
            client.post("/api/auth/login", json={"email": user["email"], "password": _PASSWORD})
            sub = review_queue.create_submission(self.alpha, "single", [{
                "employee_name": user["display_name"], "ctc": 1_800_000,
                "input": {"ctc": 1_800_000, "rent_paid": 0, "city": "metro",
                          "nps_opted": False, "current_structure": None,
                          "email": user["email"]},
                "computed": computed,
            }])["submission_id"]
            client.post(f"/api/submissions/{sub}/rows/0/decide", json={"decision": "approve"})
            rows.append((user, review_queue.get_submission(self.alpha, sub)["rows"][0]))
        (u1, r1), (u2, r2) = rows
        self.assertNotEqual(u1["id"], u2["id"])
        self.assertEqual(r1["decided_by_user_id"], u1["id"])
        self.assertEqual(r2["decided_by_user_id"], u2["id"])

    def test_the_public_submission_route_records_no_actor_rather_than_a_wrong_one(self):
        # It is deliberately unauthenticated, so None is the truthful answer —
        # the same honesty as a NULL decided_by_user_id on a pre-1.2 row.
        anon = _client_for(ALPHA_HOST)
        anon.post("/api/submissions", json={"source": "single", "row": {"ctc": 1_800_000}})
        lines = [e for e in self._lines() if e["route"] == "/api/submissions"]
        self.assertTrue(lines)
        self.assertIsNone(lines[0]["user_id"])
        self.assertEqual(lines[0]["tenant_id"], self.alpha)


# ---------------------------------------------------------------------------
# 3. Cross-tenant isolation of the identity tables
# ---------------------------------------------------------------------------

class TestUserCrossTenantIsolation(IdentityTestCase):

    def test_a_users_list_never_includes_another_tenants_people(self):
        self._user(self.alpha, "owner")
        self._user(self.beta, "owner", email="beta-owner@beta.test")
        client, _ = self._as(ALPHA_HOST, self.alpha, "owner")
        emails = [u["email"] for u in client.get("/api/users").get_json()["users"]]
        self.assertNotIn("beta-owner@beta.test", emails)

    def test_another_tenants_user_cannot_be_edited(self):
        beta_user = self._user(self.beta, "hr", email="victim@beta.test")
        client, _ = self._as(ALPHA_HOST, self.alpha, "owner")
        self.assertEqual(client.put(f"/api/users/{beta_user['id']}/roles",
                                    json={"roles": ["owner"]}).status_code, 404)
        self.assertEqual(client.put(f"/api/users/{beta_user['id']}/status",
                                    json={"status": "disabled"}).status_code, 404)
        after = review_queue.get_user(self.beta, beta_user["id"])
        self.assertEqual(after["roles"], ["hr"])
        self.assertEqual(after["status"], "active")

    def test_credentials_do_not_work_on_another_tenants_subdomain(self):
        user = self._user(self.alpha, "finance")
        resp = _client_for(BETA_HOST).post("/api/auth/login",
                                           json={"email": user["email"], "password": _PASSWORD})
        self.assertEqual(resp.status_code, 401)

    def test_rls_blocks_identity_reads_with_the_query_wrapper_bypassed(self):
        # The independent layer, per 1.1 §3.1: no application code, no WHERE
        # tenant_id, deliberately simulating a future function that forgets it.
        self._user(self.alpha, "owner")
        self._user(self.beta, "owner", email="beta-owner@beta.test")
        raw = psycopg.connect(review_queue._dsn(), row_factory=dict_row)
        try:
            raw.execute(f"SET search_path TO {TEST_SCHEMA}")
            self.assertEqual(raw.execute("SELECT COUNT(*) n FROM users").fetchone()["n"], 0,
                             "no tenant context must see no users")
            raw.execute("SELECT set_config('app.tenant_id', %s, false)", (str(self.alpha),))
            rows = raw.execute("SELECT tenant_id, email FROM users").fetchall()
            self.assertTrue(rows)
            self.assertTrue(all(r["tenant_id"] == self.alpha for r in rows), rows)
            roles = raw.execute("SELECT tenant_id FROM user_roles").fetchall()
            self.assertTrue(all(r["tenant_id"] == self.alpha for r in roles), roles)
        finally:
            raw.close()

    def test_rls_blocks_writing_a_user_into_another_tenant(self):
        raw = psycopg.connect(review_queue._dsn(), row_factory=dict_row)
        try:
            raw.execute(f"SET search_path TO {TEST_SCHEMA}")
            raw.execute("SELECT set_config('app.tenant_id', %s, false)", (str(self.alpha),))
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                raw.execute("INSERT INTO users (tenant_id, email, display_name) "
                            "VALUES (%s, 'smuggled@beta.test', 'Smuggled')", (self.beta,))
        finally:
            raw.close()


# ---------------------------------------------------------------------------
# 4. Shared-code retirement
# ---------------------------------------------------------------------------

class TestSharedCodeRetirementIsComplete(IdentityTestCase):

    def _bootstrap(self, host=ALPHA_HOST):
        client = _client_for(host)
        client.post("/api/auth/login", json={"role": "finance", "code": "FINANCE2026"})
        resp = client.post("/api/auth/bootstrap", json={
            "email": "owner@alpha.test", "display_name": "Owner", "password": "S3cretPassw0rd"})
        self.assertEqual(resp.status_code, 200)
        return client, resp.get_json()["user"]

    def test_exactly_one_owner_is_created(self):
        self._bootstrap()
        users = review_queue.list_users(self.alpha)
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["roles"], ["owner"])

    def test_the_code_stays_dead_after_the_owner_it_created_is_disabled(self):
        # The §7 case. Users are disabled rather than deleted (attribution must
        # survive), so "the owner is gone" means disabled — and the door must
        # not reopen, or disabling the only owner would hand the tenant back to
        # anyone holding an old shared secret.
        _client, owner = self._bootstrap()
        review_queue.set_user_status(self.alpha, owner["id"], "disabled")
        resp = _client_for(ALPHA_HOST).post("/api/auth/login",
                                            json={"role": "finance", "code": "FINANCE2026"})
        self.assertEqual(resp.status_code, 401)
        self.assertIn("no longer used", resp.get_json()["error"])

    def test_retiring_one_tenants_codes_does_not_retire_anothers(self):
        self._bootstrap(ALPHA_HOST)
        self.assertIsNotNone(
            review_queue.get_tenant_bootstrap_state(self.alpha)["codes_disabled_at"])
        self.assertIsNone(
            review_queue.get_tenant_bootstrap_state(self.beta)["codes_disabled_at"])
        beta = _client_for(BETA_HOST).post("/api/auth/login",
                                           json={"role": "finance", "code": "FINANCE2026"})
        self.assertTrue(beta.get_json()["bootstrap_required"])

    def test_the_bootstrap_owner_can_immediately_administer_the_tenant(self):
        # Otherwise the tenant is bootstrapped into a state nobody can manage.
        client, _owner = self._bootstrap()
        created = client.post("/api/users", json={
            "email": "second@alpha.test", "display_name": "Second", "roles": ["finance"]})
        self.assertEqual(created.status_code, 201)
