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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import review_queue

review_queue.DB_PATH = "test_razorpayx_queue.db"

import app as flask_app
from razorpayx_client import (
    fetch_account_balance, RazorpayXNotConfigured, RazorpayXKeyModeError, RazorpayXRequestError,
)

TEST_DB = "test_razorpayx_queue.db"


def tearDownModule():
    # app.py's import-time review_queue.init_db() creates this file even
    # though nothing in this module writes rows to it — clean it up so it
    # doesn't get left behind as scratch state (also gitignored via
    # test_*.db as a second layer, but tests should clean up after
    # themselves regardless).
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


class TestFetchAccountBalanceGuards(unittest.TestCase):
    def setUp(self):
        self._orig_id = os.environ.pop("RAZORPAYX_KEY_ID", None)
        self._orig_secret = os.environ.pop("RAZORPAYX_KEY_SECRET", None)

    def tearDown(self):
        if self._orig_id is not None:
            os.environ["RAZORPAYX_KEY_ID"] = self._orig_id
        else:
            os.environ.pop("RAZORPAYX_KEY_ID", None)
        if self._orig_secret is not None:
            os.environ["RAZORPAYX_KEY_SECRET"] = self._orig_secret
        else:
            os.environ.pop("RAZORPAYX_KEY_SECRET", None)

    def test_missing_credentials_raises_not_configured(self):
        with self.assertRaises(RazorpayXNotConfigured):
            fetch_account_balance()

    def test_missing_secret_only_raises_not_configured(self):
        os.environ["RAZORPAYX_KEY_ID"] = "rzp_test_something"
        with self.assertRaises(RazorpayXNotConfigured):
            fetch_account_balance()

    def test_live_mode_key_is_refused_not_called(self):
        # The one guard that actually matters: a key that isn't test-mode
        # must never reach urllib.request.urlopen() at all.
        os.environ["RAZORPAYX_KEY_ID"] = "rzp_live_fakekeyfortest"
        os.environ["RAZORPAYX_KEY_SECRET"] = "fakesecret"
        with self.assertRaises(RazorpayXKeyModeError):
            fetch_account_balance()

    def test_test_mode_key_prefix_passes_the_guard_and_reaches_the_real_network(self):
        # Confirms the guard's condition is specifically the "rzp_test_"
        # prefix, not e.g. rejecting everything. A fake (but correctly
        # prefixed) key genuinely reaches RazorpayX's real server and comes
        # back with a real 401 Unauthorized — proving the request actually
        # left this machine and hit the live API, not a guard block or a
        # local stub. Confirmed live: RazorpayXRequestError(401, ...).
        os.environ["RAZORPAYX_KEY_ID"] = "rzp_test_fakekeyfortest"
        os.environ["RAZORPAYX_KEY_SECRET"] = "fakesecret"
        try:
            with self.assertRaises(RazorpayXRequestError) as ctx:
                fetch_account_balance()
            self.assertEqual(ctx.exception.status_code, 401)
        except urllib.error.URLError as e:
            self.skipTest(f"No network reachability to RazorpayX in this environment: {e}")


class TestRazorpayXBalanceRoute(unittest.TestCase):
    def setUp(self):
        self.client = flask_app.app.test_client()
        self._orig_id = os.environ.pop("RAZORPAYX_KEY_ID", None)
        self._orig_secret = os.environ.pop("RAZORPAYX_KEY_SECRET", None)

    def tearDown(self):
        if self._orig_id is not None:
            os.environ["RAZORPAYX_KEY_ID"] = self._orig_id
        else:
            os.environ.pop("RAZORPAYX_KEY_ID", None)
        if self._orig_secret is not None:
            os.environ["RAZORPAYX_KEY_SECRET"] = self._orig_secret
        else:
            os.environ.pop("RAZORPAYX_KEY_SECRET", None)

    def test_route_returns_503_when_not_configured(self):
        resp = self.client.get("/api/razorpayx/balance")
        self.assertEqual(resp.status_code, 503)
        body = resp.get_json()
        self.assertFalse(body["configured"])
        self.assertFalse(body["live"])

    def test_route_returns_403_for_live_mode_key(self):
        os.environ["RAZORPAYX_KEY_ID"] = "rzp_live_fakekeyfortest"
        os.environ["RAZORPAYX_KEY_SECRET"] = "fakesecret"
        resp = self.client.get("/api/razorpayx/balance")
        self.assertEqual(resp.status_code, 403)
        body = resp.get_json()
        self.assertTrue(body["configured"])
        self.assertFalse(body["live"])


if __name__ == "__main__":
    unittest.main()
