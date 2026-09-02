"""
razorpayx_client.py — thin, read-only HTTP client for RazorpayX's real API.

This is the ONLY file in this codebase that makes a live network call to
RazorpayX. Everything else (app.py's Composite Payout payload builder, the
export modal, the "Simulate dispatch"/"Simulate upload" buttons) constructs
a payload and stops there, deliberately, per this project's own
no-live-dispatch discipline (see review_queue.py's and app.py's export
routes' own docstrings).

Scope, kept deliberately narrow: ONE read-only endpoint (fetch account
balance), GET only, zero side effects, zero money movement. This exists
specifically to prove the RazorpayX integration is real and reachable, not
simulated — not to expand the live-call surface. Do not add a write
endpoint (payout creation, fund account creation, contact creation) to this
file without the same explicit, deliberate confirmation this file itself
required before being written.

Uses stdlib only (urllib.request + base64) — no new dependency justified
for one GET request.
"""

import base64
import json
import os
import urllib.error
import urllib.request

# Verified against RazorpayX's own docs (razorpay.com/docs/api/x/
# account-validation/balance-fetch/) on 2026-09-02, not recalled from
# training data: the endpoint is NOT /v1/accounts/balance (an earlier,
# wrong assumption caught before writing this file) — it's
# /v1/banking_balances.
RAZORPAYX_BALANCE_URL = "https://api.razorpay.com/v1/banking_balances"


class RazorpayXNotConfigured(Exception):
    """RAZORPAYX_KEY_ID / RAZORPAYX_KEY_SECRET aren't set in the environment."""


class RazorpayXKeyModeError(Exception):
    """The configured key is not a test-mode key — see fetch_account_balance()."""


class RazorpayXRequestError(Exception):
    """RazorpayX's API responded with a non-2xx status."""

    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"RazorpayX returned HTTP {status_code}: {body}")


def fetch_account_balance() -> dict:
    """
    GET /v1/banking_balances — RazorpayX's real Fetch Account Balances API.
    Basic Auth over Key ID : Key Secret, per RazorpayX's documented auth
    scheme (same key pair as the Payment Gateway, per their own docs).

    Refuses to run against a live-mode key (Key ID not starting with
    "rzp_test_") — this project's whole pitch rests on never touching real
    money without an explicit, deliberate decision, and a live key used by
    accident in a demo context is exactly the kind of mistake that boundary
    exists to prevent. Raises RazorpayXKeyModeError rather than silently
    proceeding; there is no override flag, on purpose.
    """
    key_id = os.environ.get("RAZORPAYX_KEY_ID")
    key_secret = os.environ.get("RAZORPAYX_KEY_SECRET")
    if not key_id or not key_secret:
        raise RazorpayXNotConfigured(
            "RAZORPAYX_KEY_ID / RAZORPAYX_KEY_SECRET are not set in the environment. "
            "Generate a test-mode key pair from the RazorpayX Dashboard "
            "(Test Mode on -> Account & Settings -> API Keys) and add both to .env."
        )
    if not key_id.startswith("rzp_test_"):
        raise RazorpayXKeyModeError(
            "Refusing to call RazorpayX: RAZORPAYX_KEY_ID does not start with "
            "'rzp_test_'. This project never calls RazorpayX with a live-mode key."
        )

    credentials = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
    request = urllib.request.Request(
        RAZORPAYX_BALANCE_URL,
        headers={"Authorization": f"Basic {credentials}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        raise RazorpayXRequestError(e.code, e.read().decode()) from e
