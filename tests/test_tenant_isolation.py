"""
The Phase 1.1 exit criterion, as tests: two companies can use grosslo
simultaneously with zero data leakage.

MULTI_TENANT_DESIGN.md §7 step 6 asks for TWO separate tests, because they
prove two separate claims and the first cannot stand in for the second:

  1. TestApplicationLayerIsolation — every read and write endpoint returns and
     mutates only the requesting tenant's rows, and a request with no tenant
     context gets a hard 401 rather than an empty result.

  2. TestRlsAsIndependentLayer — connecting DIRECTLY to Postgres with the
     application's query wrapper bypassed entirely, and no WHERE tenant_id in
     the query at all, the database itself still returns zero cross-tenant
     rows. §3.1's "belt and suspenders" claim is only proven once this exists:
     the first class exercises the correctly-written path and would pass
     unchanged even if RLS were silently misconfigured or missing.

  3. TestAuditLogIsolation — §3.4. NOT sequenced anywhere in §7, which is
     exactly why it is here. The audit log was tenant-scoped in the schema and
     the query layer while /api/audit-log still returned every tenant's lines,
     and a gap that lives only in a report gets closed by nobody. It is a
     compliance and trust surface, so a reader has no way to tell they are
     looking at another company's decisions.

Two tenants with DELIBERATELY IDENTICAL data throughout — same employee name,
same CTC, same day. That is the exact case §4 says _dedupe_hash() must
tenant-scope: with a global hash the second company's submission is silently
rejected as a duplicate of a row it is not allowed to see.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import review_queue

review_queue.DB_SCHEMA = "test_tenant_isolation"

import psycopg
from psycopg.rows import dict_row
from flask.testing import FlaskClient

import app as flask_app
from auth import hash_access_code

TEST_SCHEMA = "test_tenant_isolation"

ALPHA_HOST = "http://alpha.grosslo.app/"
BETA_HOST = "http://beta.grosslo.app/"
NO_TENANT_HOST = "http://localhost/"

_HR_HASH = hash_access_code("HR2026")
_FIN_HASH = hash_access_code("FINANCE2026")

# Byte-for-byte identical across both tenants, on purpose.
IDENTICAL_ROW = {
    "employee_name": "Anika Verma",
    "ctc": 1_800_000,
    "input": {"ctc": 1_800_000, "rent_paid": 0, "city": "metro",
              "nps_opted": False, "current_structure": None},
}


def _client_for(host):
    class _HostClient(FlaskClient):
        def open(self, *args, **kwargs):
            kwargs.setdefault("base_url", host)
            return super().open(*args, **kwargs)
    flask_app.app.test_client_class = _HostClient
    return flask_app.app.test_client()


class TenantIsolationTestCase(unittest.TestCase):
    def setUp(self):
        review_queue.DB_SCHEMA = TEST_SCHEMA
        review_queue._drop_schema(TEST_SCHEMA)
        review_queue.init_db()
        flask_app._SUBMISSION_ATTEMPTS.clear()

        self.alpha = review_queue.create_tenant("alpha", "Alpha Ltd")["id"]
        self.beta = review_queue.create_tenant("beta", "Beta Ltd")["id"]
        review_queue.create_tenant_settings(self.alpha, _HR_HASH, _FIN_HASH)
        review_queue.create_tenant_settings(self.beta, _HR_HASH, _FIN_HASH)

        self.computed = flask_app._build_optimize_response(
            1_800_000, 0, "metro", False, None, False, skip_ai=True)[0]

    def tearDown(self):
        review_queue._drop_schema(TEST_SCHEMA)

    def _row(self):
        return {**IDENTICAL_ROW, "computed": self.computed}

    def _seed_both(self):
        a = review_queue.create_submission(self.alpha, "single", [self._row()])
        b = review_queue.create_submission(self.beta, "single", [self._row()])
        return a, b

    def _logged_in(self, host, role="finance", code="FINANCE2026"):
        client = _client_for(host)
        resp = client.post("/api/auth/login", json={"role": role, "code": code})
        self.assertEqual(resp.status_code, 200, f"login failed on {host}: {resp.get_data(as_text=True)}")
        return client


class TestApplicationLayerIsolation(TenantIsolationTestCase):

    def test_identical_data_in_both_tenants_does_not_false_deduplicate(self):
        # The §4 case: same name, same CTC, same day. A global dedupe key would
        # reject Beta's row as a duplicate of Alpha's — a row Beta cannot see.
        a, b = self._seed_both()
        self.assertEqual(a["duplicates"], [])
        self.assertEqual(b["duplicates"], [], "Beta's row was rejected as a duplicate of Alpha's")
        self.assertEqual(len(a["inserted_row_ids"]), 1)
        self.assertEqual(len(b["inserted_row_ids"]), 1)
        self.assertNotEqual(
            review_queue._dedupe_hash(self.alpha, "Anika Verma", 1_800_000),
            review_queue._dedupe_hash(self.beta, "Anika Verma", 1_800_000),
        )

    def test_reads_return_only_the_requesting_tenants_rows(self):
        self._seed_both()
        for tenant, other in ((self.alpha, self.beta), (self.beta, self.alpha)):
            subs = review_queue.list_submissions(tenant)
            self.assertEqual(len(subs), 1)
            for s in subs:
                for row in s["rows"]:
                    self.assertEqual(row["tenant_id"], tenant)

    def test_get_submission_cannot_reach_another_tenants_id(self):
        a, b = self._seed_both()
        self.assertIsNone(review_queue.get_submission(self.alpha, b["submission_id"]))
        self.assertIsNone(review_queue.get_submission(self.beta, a["submission_id"]))
        # ...and it is not simply returning None for everything.
        self.assertIsNotNone(review_queue.get_submission(self.alpha, a["submission_id"]))

    def test_writes_cannot_mutate_another_tenants_row(self):
        a, b = self._seed_both()
        # Alpha tries to approve Beta's row by id. Must be a no-op, not a
        # cross-tenant write, and must not report success.
        result = review_queue.decide_row(self.alpha, b["submission_id"], 0, "approve", None)
        self.assertTrue(result["already_decided"])
        self.assertIsNone(result["current_status"], "Alpha saw the status of Beta's row")
        self.assertEqual(
            review_queue.get_submission(self.beta, b["submission_id"])["rows"][0]["status"],
            "pending",
            "Beta's row was mutated by Alpha",
        )

    def test_mark_exported_and_dispatched_are_tenant_scoped_too(self):
        a, b = self._seed_both()
        review_queue.mark_exported(self.alpha, b["submission_id"], 0)
        review_queue.mark_dispatched(self.alpha, b["submission_id"], 0)
        beta_row = review_queue.get_submission(self.beta, b["submission_id"])["rows"][0]
        self.assertIsNone(beta_row["exported_at"])
        self.assertIsNone(beta_row["dispatched_at"])

    def test_check_duplicate_does_not_disclose_another_tenants_row(self):
        self._seed_both()
        # Alpha asks about a candidate Beta also has. It must find ALPHA's row,
        # never Beta's — the leak here would be a bare existence disclosure.
        found = review_queue.check_duplicate(self.alpha, "Anika Verma", 1_800_000)
        self.assertIsNotNone(found)
        self.assertEqual(found["tenant_id"], self.alpha)

    def test_http_reads_are_scoped_to_the_session_tenant(self):
        a, b = self._seed_both()
        alpha_client = self._logged_in(ALPHA_HOST)
        listed = alpha_client.get("/api/submissions").get_json()["submissions"]
        self.assertEqual([s["id"] for s in listed], [a["submission_id"]])
        self.assertEqual(alpha_client.get(f"/api/submissions/{b['submission_id']}").status_code, 404)

    def test_a_session_is_not_sent_to_another_tenants_subdomain_at_all(self):
        # First line of defence, and it is the cookie's, not ours: a session
        # issued on alpha.grosslo.app is simply not presented to
        # beta.grosslo.app, so the request arrives unauthenticated.
        self._seed_both()
        alpha_client = self._logged_in(ALPHA_HOST)
        self.assertEqual(alpha_client.get("/api/submissions", base_url=BETA_HOST).status_code, 401)

    def test_the_host_never_overrides_the_session_tenant_on_a_read(self):
        """
        The assertion that matters if a cookie ever DOES reach another
        subdomain (a wildcard cookie domain, a proxy, a future SSO flow):
        reads take their tenant from the signed session, never from the host,
        so the answer is Alpha's data — not Beta's, and not an error that might
        later be "helpfully" resolved by falling back to the host (3.3).
        """
        a, b = self._seed_both()
        client = _client_for(BETA_HOST)
        with client.session_transaction(base_url=BETA_HOST) as sess:
            sess["role"] = "finance"
            sess["tenant_id"] = self.alpha  # an Alpha session, on Beta's host

        listed = client.get("/api/submissions").get_json()["submissions"]
        self.assertEqual([s["id"] for s in listed], [a["submission_id"]],
                         "the host, not the session, decided which tenant was read")
        self.assertEqual(client.get(f"/api/submissions/{b['submission_id']}").status_code, 404)

    def test_missing_tenant_context_is_401_never_an_empty_list(self):
        """
        §3.1's specific requirement: an empty list reads to a caller as "you
        have zero rows", which is a materially different and worse failure than
        "you are not authorised". All three fail-closed cases produce 401.
        """
        self._seed_both()

        # 1. a request that skipped login entirely
        no_session = _client_for(ALPHA_HOST)
        resp = no_session.get("/api/submissions")
        self.assertEqual(resp.status_code, 401)
        self.assertNotIn("submissions", resp.get_json())

        # 2. a stale session: role survives, tenant_id does not
        stale = self._logged_in(ALPHA_HOST)
        with stale.session_transaction(base_url=ALPHA_HOST) as sess:
            del sess["tenant_id"]
        resp = stale.get("/api/submissions")
        self.assertEqual(resp.status_code, 401)
        self.assertNotIn("submissions", resp.get_json())

        # 3. a login-flow bug: a session built without a tenant at all
        buggy = _client_for(ALPHA_HOST)
        with buggy.session_transaction(base_url=ALPHA_HOST) as sess:
            sess["role"] = "finance"
        resp = buggy.get("/api/submissions")
        self.assertEqual(resp.status_code, 401)
        self.assertNotIn("submissions", resp.get_json())

    def test_persistence_layer_refuses_a_missing_tenant_rather_than_defaulting(self):
        for bad in (None, "1", True):
            with self.assertRaises(review_queue.TenantContextMissing):
                review_queue.list_submissions(bad)


class TestRlsAsIndependentLayer(TenantIsolationTestCase):
    """
    Bypasses the application's query wrapper ENTIRELY. Every query below is
    written with no tenant predicate at all, deliberately simulating "a
    reviewer forgot the WHERE clause in a new function" — the exact bug class
    §3.1 says the second layer exists for.

    TestApplicationLayerIsolation above would pass unchanged if these policies
    were dropped tomorrow, which is precisely why this cannot be folded into
    it.
    """

    def _raw(self):
        conn = psycopg.connect(review_queue._dsn(), row_factory=dict_row)
        conn.execute(f"SET search_path TO {TEST_SCHEMA}")
        return conn

    def test_the_app_role_cannot_bypass_rls_in_the_first_place(self):
        """
        Guards the assumption everything else in this class rests on.
        Superusers and BYPASSRLS roles ignore every policy, so if the
        application ever connects as one, every other test here passes while
        proving nothing.
        """
        conn = self._raw()
        who = conn.execute(
            "SELECT current_user AS u, rolsuper, rolbypassrls FROM pg_roles "
            "WHERE rolname = current_user").fetchone()
        conn.close()
        self.assertFalse(who["rolsuper"], f"{who['u']} is a superuser; RLS would be inert")
        self.assertFalse(who["rolbypassrls"], f"{who['u']} has BYPASSRLS; RLS would be inert")

    def test_startup_refuses_a_role_that_would_bypass_rls(self):
        """
        The near-miss, made unrepeatable. grosslo_app was added because the
        default Homebrew role is a superuser and RLS was therefore inert — but
        that fix lives in configuration, and DATABASE_URL can be pointed back
        at a privileged role by anyone, producing a working app with half its
        isolation silently gone. So the invariant is asserted at startup.
        """
        import os
        original = os.environ.get("DATABASE_URL")
        # The developer's own OS role: superuser + BYPASSRLS on a stock
        # Homebrew cluster, which is exactly how this nearly shipped.
        os.environ["DATABASE_URL"] = "postgresql:///grosslo"
        try:
            conn = psycopg.connect(review_queue._dsn(), row_factory=dict_row)
            privileged = conn.execute(
                "SELECT rolsuper OR rolbypassrls AS bypasses FROM pg_roles "
                "WHERE rolname = current_user").fetchone()["bypasses"]
            conn.close()
            if not privileged:
                self.skipTest("default connection role is not privileged here; "
                              "nothing to assert against")
            with self.assertRaises(review_queue.RlsNotEnforceableError) as ctx:
                review_queue.init_db()
            message = str(ctx.exception)
            self.assertIn("row-level-security", message)
            self.assertIn("grosslo_app", message, "the error must name the fix, not just the fault")
        finally:
            if original is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original

    def test_policies_are_forced_not_merely_enabled(self):
        # A table's OWNER is exempt from its own policies unless FORCE is set,
        # and this role owns these tables.
        conn = self._raw()
        rows = conn.execute(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = %s AND relname IN "
            "('submissions','submission_rows','tenant_settings')", (TEST_SCHEMA,)).fetchall()
        conn.close()
        self.assertEqual(len(rows), 3)
        for r in rows:
            self.assertTrue(r["relrowsecurity"], f"{r['relname']}: RLS not enabled")
            self.assertTrue(r["relforcerowsecurity"], f"{r['relname']}: RLS enabled but not FORCEd")

    def test_no_tenant_context_returns_zero_rows_not_every_row(self):
        self._seed_both()
        conn = self._raw()
        for table in ("submissions", "submission_rows", "tenant_settings"):
            n = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            self.assertEqual(n, 0, f"{table} returned {n} rows with no app.tenant_id set")
        conn.close()

    def test_query_with_no_where_clause_still_returns_only_one_tenant(self):
        self._seed_both()
        conn = self._raw()
        conn.execute("SELECT set_config('app.tenant_id', %s, false)", (str(self.alpha),))
        rows = conn.execute("SELECT id, tenant_id FROM submission_rows").fetchall()
        conn.close()
        self.assertEqual(len(rows), 1)
        self.assertTrue(all(r["tenant_id"] == self.alpha for r in rows))

    def test_write_into_another_tenant_is_blocked_by_with_check(self):
        self._seed_both()
        conn = self._raw()
        conn.execute("SELECT set_config('app.tenant_id', %s, false)", (str(self.alpha),))
        with self.assertRaises(psycopg.errors.Error):
            conn.execute(
                "INSERT INTO submissions (tenant_id, created_at, source) VALUES (%s, 'x', 'single')",
                (self.beta,))
        conn.rollback()
        conn.close()

    def test_update_cannot_reach_across_tenants_without_a_where_clause(self):
        # The dangerous shape: a blanket UPDATE with no tenant predicate.
        _, b = self._seed_both()
        conn = self._raw()
        conn.execute("SELECT set_config('app.tenant_id', %s, false)", (str(self.alpha),))
        cur = conn.execute("UPDATE submission_rows SET status = 'approved'")
        conn.commit()
        self.assertEqual(cur.rowcount, 1, "a WHERE-less UPDATE touched more than one tenant's rows")
        conn.close()
        self.assertEqual(
            review_queue.get_submission(self.beta, b["submission_id"])["rows"][0]["status"],
            "pending")

    def test_tenant_context_is_transaction_scoped_not_session_scoped(self):
        """
        §3.1's SET LOCAL rule, verified rather than assumed. The application
        sets app.tenant_id with set_config(..., is_local => true); after the
        transaction ends the setting must be gone, so a pooled connection
        handed to the next request carries no tenant with it.
        """
        self._seed_both()
        conn = psycopg.connect(review_queue._dsn(), row_factory=dict_row)
        conn.execute(f"SET search_path TO {TEST_SCHEMA}")
        conn.execute("SELECT set_config('app.tenant_id', %s, true)", (str(self.alpha),))
        self.assertEqual(
            conn.execute("SELECT COUNT(*) AS n FROM submission_rows").fetchone()["n"], 1)
        conn.commit()  # what returning a connection to a pool would do
        leaked = conn.execute(
            "SELECT current_setting('app.tenant_id', true) AS t").fetchone()["t"]
        self.assertIn(leaked, (None, ""), f"tenant context survived COMMIT: {leaked!r}")
        self.assertEqual(
            conn.execute("SELECT COUNT(*) AS n FROM submission_rows").fetchone()["n"], 0,
            "a connection with no tenant context could still read rows after COMMIT")
        conn.close()


class TestPayoutSourceAccountIsPerTenant(TenantIsolationTestCase):
    """
    The source account a payout DEBITS must be the exporting tenant's own.

    This was missed when step 4 moved RazorpayX credentials per-tenant: key_id
    and key_secret reached the balance route, but tenant_settings.
    razorpayx_account_number was written, read back, and consumed by nobody —
    so every tenant's export payload named one hardcoded account. Neither
    step's own tests could catch it, because step 4 tested the balance route
    and the export path was step 3's, already green. It surfaced only on a read
    of the assembled diff.
    """

    def _approved_row_for(self, slug, tenant_id):
        client = _client_for(f"http://{slug}.grosslo.app/")
        client.post("/api/submissions", json={"source": "single", "row": {
            "ctc": 1_800_000, "rent_paid": 0, "city": "metro", "nps_opted": False,
            "employee_name": "E", "bank_account_number": "9999", "ifsc": "HDFC0001",
            "email": "e@example.com",
        }})
        client.post("/api/auth/login", json={"role": "finance", "code": "FINANCE2026"})
        sub = review_queue.list_submissions(tenant_id)[0]["id"]
        client.post(f"/api/submissions/{sub}/rows/0/decide", json={"decision": "approve"})
        return client.post(f"/api/submissions/{sub}/rows/0/export")

    def test_each_tenant_payload_names_its_own_configured_source_account(self):
        review_queue.set_tenant_razorpayx_credentials(
            self.alpha, "rzp_test_A", "secretA", "1111111111111111")
        review_queue.set_tenant_razorpayx_credentials(
            self.beta, "rzp_test_B", "secretB", "2222222222222222")

        a = self._approved_row_for("alpha", self.alpha).get_json()
        b = self._approved_row_for("beta", self.beta).get_json()
        self.assertEqual(a["payouts"][0]["account_number"], "1111111111111111")
        self.assertEqual(b["payouts"][0]["account_number"], "2222222222222222")
        self.assertNotEqual(a["payouts"][0]["account_number"],
                            b["payouts"][0]["account_number"],
                            "two tenants must not share one source account")
        for payload in (a, b):
            self.assertNotIn("WARNING_DO_NOT_UPLOAD", payload)
            self.assertFalse(payload.get("source_account_is_placeholder", False))

    def test_unconfigured_tenant_still_exports_but_is_loudly_marked(self):
        """
        An unconfigured tenant has not finished onboarding — that is not the
        same category as a missing tenant_id or a forged Host, which are a bug
        or an attacker and get refused. So the export still works, and the
        placeholder is impossible to mistake for a real account.
        """
        response = self._approved_row_for("alpha", self.alpha)  # no credentials set
        self.assertEqual(response.status_code, 200, "incomplete setup must not block the export")
        payload = response.get_json()

        account = payload["payouts"][0]["account_number"]
        self.assertIn("DO-NOT-UPLOAD", account)
        # Not a bare 16-digit string: a plausible-looking one is exactly what
        # gets pasted into RazorpayX without a second look.
        self.assertFalse(account.isdigit(), f"placeholder must not look like an account: {account!r}")
        self.assertNotEqual(account, flask_app.DEFAULT_RAZORPAYX_ACCOUNT_NUMBER)

        self.assertTrue(payload["source_account_is_placeholder"])
        self.assertIn("DO NOT UPLOAD", payload["WARNING_DO_NOT_UPLOAD"])
        # Second surface, so the warning survives the payload being piped,
        # saved, or handed on.
        self.assertIn("DO NOT UPLOAD", response.headers.get("X-Source-Account-Placeholder", ""))

    def test_source_account_is_not_gated_behind_having_api_keys(self):
        """
        A tenant may configure which account its payouts name without handing
        the app live API keys — the keys authorise live calls (the balance
        route), the account number does not. Reading the account through
        get_tenant_razorpayx_credentials(), which returns None whenever there
        is no key_id, told such a tenant it had no account and emitted the
        DO-NOT-UPLOAD placeholder over a value sitting right there in the row.
        """
        review_queue.set_tenant_razorpayx_credentials(
            self.alpha, None, None, "3333333333333333")
        self.assertIsNone(
            review_queue.get_tenant_razorpayx_credentials(self.alpha),
            "no API key still means no API access — that part was correct")
        self.assertEqual(
            review_queue.get_tenant_source_account(self.alpha), "3333333333333333",
            "but the source account must be readable independently of the keys")

        payload = self._approved_row_for("alpha", self.alpha).get_json()
        self.assertEqual(payload["payouts"][0]["account_number"], "3333333333333333")
        self.assertNotIn("WARNING_DO_NOT_UPLOAD", payload,
                         "a configured account must not be reported as a placeholder")

    def test_audit_trail_records_which_exports_used_a_placeholder(self):
        orig = flask_app.AUDIT_LOG_PATH
        flask_app.AUDIT_LOG_PATH = "test_source_account_audit.jsonl"
        if os.path.exists(flask_app.AUDIT_LOG_PATH):
            os.remove(flask_app.AUDIT_LOG_PATH)
        try:
            self._approved_row_for("alpha", self.alpha)
            with open(flask_app.AUDIT_LOG_PATH) as f:
                exports = [json.loads(l) for l in f
                           if l.strip() and json.loads(l).get("export_type") == "razorpayx_payout"]
            self.assertTrue(exports)
            self.assertTrue(exports[-1]["source_account_is_placeholder"])
        finally:
            if os.path.exists(flask_app.AUDIT_LOG_PATH):
                os.remove(flask_app.AUDIT_LOG_PATH)
            flask_app.AUDIT_LOG_PATH = orig


class TestAuditLogIsolation(TenantIsolationTestCase):
    """
    §3.4, which §7 never sequenced into any step — that omission is the reason
    this class exists rather than a note in a report. /api/audit-log is
    explicitly a compliance and trust surface, so a silent leak here is worse
    than most: a reviewer reading another company's decisions has no way to
    tell.
    """

    def setUp(self):
        super().setUp()
        # Point the audit log at a scratch file: the real one is a live demo
        # artifact, and this class writes to it.
        self._orig_path = flask_app.AUDIT_LOG_PATH
        self._orig_process_path = flask_app.PROCESS_LOG_PATH
        flask_app.AUDIT_LOG_PATH = "test_audit_log_isolation.jsonl"
        flask_app.PROCESS_LOG_PATH = "test_process_log_isolation.jsonl"
        for path in (flask_app.AUDIT_LOG_PATH, flask_app.PROCESS_LOG_PATH):
            if os.path.exists(path):
                os.remove(path)

    def tearDown(self):
        for path in (flask_app.AUDIT_LOG_PATH, flask_app.PROCESS_LOG_PATH):
            if os.path.exists(path):
                os.remove(path)
        flask_app.AUDIT_LOG_PATH = self._orig_path
        flask_app.PROCESS_LOG_PATH = self._orig_process_path
        super().tearDown()

    def _lines(self, path):
        if not os.path.exists(path):
            return []
        with open(path) as f:
            return [json.loads(l) for l in f if l.strip()]

    def _submit_on(self, host):
        return _client_for(host).post("/api/submissions", json={
            "source": "single", "row": {"ctc": 1_800_000},
        })

    def test_every_written_line_carries_a_tenant_id(self):
        self._submit_on(ALPHA_HOST)
        lines = self._lines(flask_app.AUDIT_LOG_PATH)
        self.assertTrue(lines)
        for entry in lines:
            self.assertIn("tenant_id", entry)
            # Not merely present: an OWNER. Asserting key presence alone was
            # what let "required" quietly mean "required but nullable".
            self.assertIsNotNone(entry["tenant_id"])
            self.assertEqual(entry["tenant_id"], self.alpha)

    def test_audit_log_writer_rejects_a_null_tenant_outright(self):
        """
        The invariant is enforced where the line is WRITTEN, not patched over
        where it is read. A read-side filter alone leaves the compliance file
        itself containing unowned lines, and makes "every line has an owner"
        a property of the reader rather than of the data.
        """
        with self.assertRaises(ValueError) as ctx:
            flask_app._append_audit_log(None, "/api/optimize", {"ctc": 1})
        self.assertIn("_append_process_log", str(ctx.exception),
                      "the error must name the correct alternative, not just refuse")
        self.assertEqual(self._lines(flask_app.AUDIT_LOG_PATH), [],
                         "a rejected write must not land in the file anyway")

    def test_anonymous_compute_goes_to_the_process_log_not_the_audit_log(self):
        # No session, and a host that names no tenant at all.
        anon = flask_app.app.test_client()
        r = anon.post("/api/optimize", json={"ctc": 1_800_000}, headers={"Host": "localhost"})
        self.assertEqual(r.status_code, 200, "stateless compute must stay reachable anonymously")
        self.assertEqual(self._lines(flask_app.AUDIT_LOG_PATH), [],
                         "an unowned event must never reach the tenant compliance trail")
        process = self._lines(flask_app.PROCESS_LOG_PATH)
        self.assertTrue(process, "it must still be recorded somewhere, not dropped")
        self.assertEqual(process[0]["route"], "/api/optimize")
        self.assertIsNone(process[0]["tenant_id"])

    def test_authenticated_compute_still_lands_in_that_tenants_audit_trail(self):
        """
        The split must not quietly reduce audit coverage. A logged-in user's
        computation belonged to their trail before the split and still does —
        only anonymous lines moved.
        """
        client = self._logged_in(ALPHA_HOST, role="hr", code="HR2026")
        r = client.post("/api/optimize", json={"ctc": 1_800_000})
        self.assertEqual(r.status_code, 200)
        audit = self._lines(flask_app.AUDIT_LOG_PATH)
        self.assertTrue(any(e["route"] == "/api/optimize" and e["tenant_id"] == self.alpha
                            for e in audit),
                        "an authenticated computation must stay in that tenant's trail")
        self.assertEqual(self._lines(flask_app.PROCESS_LOG_PATH), [],
                         "an owned event must not be diverted to the unowned sink")

    def test_audit_log_returns_zero_foreign_tenant_lines(self):
        """
        THE ASSERTION THIS CLASS EXISTS FOR. Both tenants act; each must see
        only its own decisions.
        """
        self._submit_on(ALPHA_HOST)
        self._submit_on(BETA_HOST)

        for tenant, host in ((self.alpha, ALPHA_HOST), (self.beta, BETA_HOST)):
            body = self._logged_in(host).get("/api/audit-log").get_json()
            self.assertTrue(body["entries"], f"tenant {tenant} saw no entries of its own")
            foreign = [e for e in body["entries"] if e.get("tenant_id") != tenant]
            self.assertEqual(foreign, [], f"tenant {tenant} was shown {len(foreign)} foreign lines")

    def test_total_logged_does_not_disclose_other_tenants_volume(self):
        # A count over the whole file would leak how much another company is
        # doing, even with the entries themselves filtered out.
        self._submit_on(ALPHA_HOST)
        for _ in range(3):
            self._submit_on(BETA_HOST)
        body = self._logged_in(ALPHA_HOST).get("/api/audit-log").get_json()
        self.assertEqual(body["total_logged"], len(body["entries"]))
        self.assertEqual(body["total_logged"], 1)

    def test_untenanted_legacy_lines_are_shown_to_nobody(self):
        # Lines written before §3.4 shipped have no tenant_id at all. They are
        # not this tenant's data, so they fail closed rather than defaulting
        # into whoever asks first.
        with open(flask_app.AUDIT_LOG_PATH, "a") as f:
            f.write(json.dumps({"timestamp": "2026-01-01T00:00:00+00:00",
                                "route": "/api/optimize", "legacy": True}) + "\n")
            f.write(json.dumps({"timestamp": "2026-01-01T00:00:00+00:00",
                                "tenant_id": None, "route": "/api/optimize"}) + "\n")
        self._submit_on(ALPHA_HOST)
        body = self._logged_in(ALPHA_HOST).get("/api/audit-log").get_json()
        self.assertTrue(all(e.get("tenant_id") == self.alpha for e in body["entries"]))
        self.assertEqual(body["total_logged"], 1)

    def test_audit_log_requires_a_tenant_context(self):
        self._submit_on(ALPHA_HOST)
        resp = _client_for(ALPHA_HOST).get("/api/audit-log")
        self.assertEqual(resp.status_code, 401)
        self.assertNotIn("entries", resp.get_json())


if __name__ == "__main__":
    unittest.main()


class TestUserAdministration(TenantIsolationTestCase):
    """
    Phase 1.2 step 3. Sessions are injected directly here because no owner can
    LOG IN until step 4 — the shared-code login only mints hr/finance. That is
    the correct state for this step, not a gap: step 3 adds the capability,
    step 4 adds the door.
    """

    def _owner_client(self, host, tenant_id, user_id=None):
        client = _client_for(host)
        # base_url must be passed explicitly: session_transaction() does not go
        # through _HostClient.open(), so without it the cookie is set for the
        # default host and never sent to the tenant subdomain.
        with client.session_transaction(base_url=host) as sess:
            sess["tenant_id"] = tenant_id
            sess["roles"] = ["owner"]
            if user_id is not None:
                sess["user_id"] = user_id
        return client

    def test_owner_can_create_list_and_scope_users_to_their_tenant(self):
        client = self._owner_client(ALPHA_HOST, self.alpha)
        created = client.post("/api/users", json={
            "email": "Ada@Alpha.test", "display_name": "Ada", "roles": ["finance"],
            "password": "pw",
        })
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.get_json()["email"], "ada@alpha.test", "email is normalised")
        self.assertNotIn("password_hash", created.get_json(), "the hash must never leave the server")

        review_queue.create_user(self.beta, "bob@beta.test", "Bob", ["hr"])
        listed = client.get("/api/users").get_json()["users"]
        self.assertEqual([u["email"] for u in listed], ["ada@alpha.test"],
                         "Alpha's owner must not see Beta's users")

    def test_a_role_lacking_manage_users_is_refused(self):
        client = _client_for(ALPHA_HOST)
        with client.session_transaction(base_url=ALPHA_HOST) as sess:
            sess["tenant_id"] = self.alpha
            sess["roles"] = ["finance"]      # finance holds no manage_users
        self.assertEqual(client.get("/api/users").status_code, 401)
        self.assertEqual(client.post("/api/users", json={}).status_code, 401)

    def test_unknown_roles_are_refused_not_silently_stored(self):
        # A stored role nobody grants permissions for would look assigned and
        # do nothing — worse than a clear rejection.
        client = self._owner_client(ALPHA_HOST, self.alpha)
        resp = client.post("/api/users", json={
            "email": "x@alpha.test", "display_name": "X", "roles": ["superuser"],
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn("superuser", resp.get_json()["error"])
        self.assertEqual(review_queue.list_users(self.alpha), [])

    def test_users_are_disabled_never_deleted(self):
        # decided_by_user_id references users(id); deleting a person would break
        # or orphan the attribution on every decision they made.
        user = review_queue.create_user(self.alpha, "z@alpha.test", "Z", ["finance"])
        client = self._owner_client(ALPHA_HOST, self.alpha)
        resp = client.put(f"/api/users/{user['id']}/status", json={"status": "disabled"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "disabled")
        self.assertIsNotNone(review_queue.get_user(self.alpha, user["id"]),
                             "the row must survive so attribution survives")

    def test_owner_cannot_reach_another_tenants_user_by_id(self):
        beta_user = review_queue.create_user(self.beta, "bob@beta.test", "Bob", ["hr"])
        client = self._owner_client(ALPHA_HOST, self.alpha)
        self.assertEqual(
            client.put(f"/api/users/{beta_user['id']}/roles", json={"roles": ["owner"]}).status_code,
            404, "Beta's user must be invisible, not editable, from Alpha")
        self.assertEqual(review_queue.get_user(self.beta, beta_user["id"])["roles"], ["hr"],
                         "Beta's user must be unchanged")

    def test_user_administration_is_written_to_the_audit_trail(self):
        orig = flask_app.AUDIT_LOG_PATH
        flask_app.AUDIT_LOG_PATH = "test_user_admin_audit.jsonl"
        if os.path.exists(flask_app.AUDIT_LOG_PATH):
            os.remove(flask_app.AUDIT_LOG_PATH)
        try:
            client = self._owner_client(ALPHA_HOST, self.alpha, user_id=99)
            client.post("/api/users", json={
                "email": "n@alpha.test", "display_name": "N", "roles": ["hr"]})
            with open(flask_app.AUDIT_LOG_PATH) as f:
                entries = [json.loads(l) for l in f if l.strip()]
            created = [e for e in entries if e.get("action") == "create_user"]
            self.assertEqual(len(created), 1)
            self.assertEqual(created[0]["tenant_id"], self.alpha)
            self.assertEqual(created[0]["actor_user_id"], 99,
                             "who created the account must be recorded, not just that it happened")
        finally:
            if os.path.exists(flask_app.AUDIT_LOG_PATH):
                os.remove(flask_app.AUDIT_LOG_PATH)
            flask_app.AUDIT_LOG_PATH = orig
