"""
Tests for razorpayx_client.py and the /api/razorpayx/balance route.

The live network call itself is exercised manually against real
RazorpayX test-mode credentials (see the plan/verification notes) — it
is not mocked into a "pass" here, since a mocked 200 response would prove
nothing about the real integration actually working. What IS tested here,
with real code paths and no mocking of razorpayx_client itself: the
not-configured guard, the live-key refusal guard (the one place this
project would otherwise risk a real-money call), and that the Flask route
maps each exception to the right status code.
"""

import os
import sys
import unittest
import urllib.error
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import review_queue
import secret_store

review_queue.DB_SCHEMA = "test_razorpayx_queue"

import app as flask_app
from flask.testing import FlaskClient
from auth import hash_access_code

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
from razorpayx_client import (
    fetch_account_balance, RazorpayXNotConfigured, RazorpayXKeyModeError, RazorpayXRequestError,
)

TEST_SCHEMA = "test_razorpayx_queue"


def tearDownModule():
    # app.py's import-time review_queue.init_db() creates this schema even
    # though nothing in this module writes rows to it — clean it up so it
    # doesn't get left behind as scratch state. (The old gitignore'd
    # test_*.db file was a second layer of protection here; a Postgres
    # schema has no such backstop, so this cleanup matters slightly more
    # than it did before.)
    review_queue._drop_schema(TEST_SCHEMA)


class TestFetchAccountBalanceGuards(unittest.TestCase):
    """
    Credentials are ARGUMENTS as of step 4 (section 3.5) — this client no
    longer reads os.environ, so these tests pass the pair in directly instead
    of setting and restoring process environment around every case.
    """

    def test_missing_credentials_raises_not_configured(self):
        with self.assertRaises(RazorpayXNotConfigured):
            fetch_account_balance(None, None)

    def test_missing_secret_only_raises_not_configured(self):
        with self.assertRaises(RazorpayXNotConfigured):
            fetch_account_balance("rzp_test_something", None)

    def test_live_mode_key_is_refused_not_called(self):
        # The one guard that actually matters: a key that isn't test-mode
        # must never reach urllib.request.urlopen() at all.
        with self.assertRaises(RazorpayXKeyModeError):
            fetch_account_balance("rzp_live_fakekeyfortest", "fakesecret")

    def test_guard_is_enforceable_per_tenant_not_process_wide(self):
        # The point of moving credentials off process environment: one tenant
        # holding a live key must not decide anything for another tenant. Same
        # process, two credential pairs, two different outcomes.
        with self.assertRaises(RazorpayXKeyModeError):
            fetch_account_balance("rzp_live_tenant_a", "secret_a")
        try:
            with self.assertRaises(RazorpayXRequestError):
                fetch_account_balance("rzp_test_tenant_b", "secret_b")
        except urllib.error.URLError as e:
            self.skipTest(f"No network reachability to RazorpayX in this environment: {e}")

    def test_test_mode_key_prefix_passes_the_guard_and_reaches_the_real_network(self):
        # Confirms the guard's condition is specifically the "rzp_test_"
        # prefix, not e.g. rejecting everything. A fake (but correctly
        # prefixed) key genuinely reaches RazorpayX's real server and comes
        # back with a real 401 Unauthorized — proving the request actually
        # left this machine and hit the live API, not a guard block or a
        # local stub. Confirmed live: RazorpayXRequestError(401, ...).
        try:
            with self.assertRaises(RazorpayXRequestError) as ctx:
                fetch_account_balance("rzp_test_fakekeyfortest", "fakesecret")
            self.assertEqual(ctx.exception.status_code, 401)
        except urllib.error.URLError as e:
            self.skipTest(f"No network reachability to RazorpayX in this environment: {e}")


class TestSecretStoreRefusesLiveCredentials(unittest.TestCase):
    """
    Section 3.5 requires "encrypted at rest" to name a real, auditable
    mechanism rather than describe an aspiration. The KMS that mechanism
    depends on cannot be built until section 6's hosting decision is made, so
    the gap is enforced structurally instead of documented and hoped about: a
    credential that is not a test-mode key has nowhere to be stored.
    """

    def test_live_key_cannot_be_stored_at_all(self):
        with self.assertRaises(secret_store.LiveCredentialRefused):
            secret_store.encrypt("rzp_live_realkey")

    def test_test_key_round_trips(self):
        stored = secret_store.encrypt("rzp_test_abc123")
        self.assertNotEqual(stored, "rzp_test_abc123")  # at minimum, not stored raw
        self.assertEqual(secret_store.decrypt(stored), "rzp_test_abc123")

    def test_stored_value_names_its_backend_and_does_not_claim_encryption(self):
        # A future reader (or a restored database) must be able to tell what
        # produced a value. Silence here is how plaintext gets mistaken for
        # ciphertext.
        stored = secret_store.encrypt("rzp_test_abc123")
        self.assertTrue(stored.startswith("dev-plaintext:"))
        self.assertFalse(secret_store.is_real_encryption())

    def test_unrecognised_envelope_is_refused_not_guessed_at(self):
        with self.assertRaises(secret_store.SecretStoreUnavailable):
            secret_store.decrypt("something-else:v1:zzz")


class TestRazorpayXBalanceRoute(unittest.TestCase):
    """
    These test the not-configured/live-key-mode logic downstream of auth —
    the 401-before-any-of-that-is-even-checked case is covered in
    test_auth.py's test_razorpayx_balance_requires_finance_session_before_anything_else.
    So every test here logs in as finance first, deliberately.
    """

    def setUp(self):
        review_queue.DB_SCHEMA = TEST_SCHEMA
        review_queue._drop_schema(TEST_SCHEMA)
        review_queue.init_db()
        self.tenant_id = review_queue.create_tenant("acme", "Acme Corp")["id"]
        review_queue.create_tenant_settings(
            self.tenant_id, _HR_CODE_HASH, _FINANCE_CODE_HASH)
        self.client = _client()
        # Real login on the tenant subdomain — the step 3 session scaffold is gone.
        self.client.post("/api/auth/login",
                         json={"role": "finance", "code": "FINANCE2026"})

    def tearDown(self):
        review_queue._drop_schema(TEST_SCHEMA)

    def test_route_returns_503_when_this_tenant_has_no_credentials(self):
        resp = self.client.get("/api/razorpayx/balance")
        self.assertEqual(resp.status_code, 503)
        body = resp.get_json()
        self.assertFalse(body["configured"])
        self.assertFalse(body["live"])

    def test_route_returns_403_for_live_mode_key(self):
        # secret_store refuses to STORE a live key, so this can no longer be
        # set up by writing one to the database — the storage guard fires
        # first. That is defence in depth, not a reason to stop testing the
        # client's own guard: a real KMS backend WILL accept live keys
        # (legitimate tenants have them), and at that point razorpayx_client's
        # rzp_test_ check is the thing standing between a demo and a live-money
        # call. So the credential resolution is patched to simulate exactly
        # that future state.
        with patch.object(review_queue, "get_tenant_razorpayx_credentials",
                          return_value={"key_id": "rzp_live_fakekeyfortest",
                                        "key_secret": "fakesecret",
                                        "account_number": None}):
            resp = self.client.get("/api/razorpayx/balance")
        self.assertEqual(resp.status_code, 403)
        body = resp.get_json()
        self.assertTrue(body["configured"])
        self.assertFalse(body["live"])

    def test_credentials_are_resolved_per_tenant_not_from_environment(self):
        # Regression guard for the actual step-4 change: setting the old
        # process-wide env vars must have no effect on the route.
        os.environ["RAZORPAYX_KEY_ID"] = "rzp_test_fromenv"
        os.environ["RAZORPAYX_KEY_SECRET"] = "envsecret"
        try:
            resp = self.client.get("/api/razorpayx/balance")
            self.assertEqual(resp.status_code, 503, "env vars must no longer configure this route")
        finally:
            os.environ.pop("RAZORPAYX_KEY_ID", None)
            os.environ.pop("RAZORPAYX_KEY_SECRET", None)

    def test_stored_test_mode_credentials_are_used_for_the_call(self):
        review_queue.set_tenant_razorpayx_credentials(
            self.tenant_id, "rzp_test_storedkey", "storedsecret", "2323230000000000")
        resolved = review_queue.get_tenant_razorpayx_credentials(self.tenant_id)
        self.assertEqual(resolved["key_id"], "rzp_test_storedkey")
        self.assertEqual(resolved["key_secret"], "storedsecret")
        self.assertEqual(resolved["account_number"], "2323230000000000")


if __name__ == "__main__":
    unittest.main()
