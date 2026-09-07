"""
auth.py — server-side session verification for the HR/Finance role gate.

Replaces role-gate.tsx's previous client-side-only check (a hardcoded code
compared in the browser, stored in sessionStorage, readable by anyone who
opens devtools). This is still deliberately scoped to two SHARED role-codes
(HR, Finance) — not a per-person account system. See the plan this was
built from for the full reasoning on what stays gated vs. open.

Session state is Flask's built-in signed cookie session (itsdangerous,
already a Flask dependency — no new package), holding only
{"role": "hr" | "finance"}. Signed with app.secret_key, HttpOnly, so it
can't be forged without the key and can't be read by JS — a real
improvement over the previous sessionStorage approach even though the
underlying codes are still shared secrets, not per-person credentials.
"""

import os
from functools import wraps
from flask import session, jsonify

ROLES = ("hr", "finance")

_DEFAULT_CODES = {"hr": "HR2026", "finance": "FINANCE2026"}
_ENV_VARS = {"hr": "HR_ACCESS_CODE", "finance": "FINANCE_ACCESS_CODE"}


def _code_for(role: str) -> str:
    return os.environ.get(_ENV_VARS[role], _DEFAULT_CODES[role])


def verify_login(role: str, code: str) -> bool:
    """
    True if `code` matches the configured secret for `role`. Case- and
    whitespace-insensitive, matching role-gate.tsx's previous client-side
    comparison exactly, so existing demo codes keep working unchanged.
    """
    if role not in ROLES or not isinstance(code, str):
        return False
    return code.strip().upper() == _code_for(role)


def require_role(*allowed_roles: str):
    """
    Route decorator: 401s unless the current session's role is one of
    `allowed_roles`. Use @require_role("finance") for finance-only routes,
    @require_role("hr", "finance") for routes either role may read.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if session.get("role") not in allowed_roles:
                return jsonify({"error": "Not authenticated for this action."}), 401
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def current_tenant_id():
    """
    The ONLY sanctioned way for a route to learn which tenant it is acting for:
    the signed session cookie, never the request body or query string.

    MULTI_TENANT_DESIGN.md 3.3 rejects trusting a client-supplied tenant id
    outright — it is an unverified value, so any authenticated session could
    name a different tenant and read its data. That is the isolation guarantee
    failing at the very first hop rather than a hardening gap to find later.
    """
    return session.get("tenant_id")


def require_tenant(fn):
    """
    Route decorator: 401s immediately unless the session carries a tenant_id.
    Same shape and same failure mode as require_role above, deliberately —
    MULTI_TENANT_DESIGN.md 3.1 asks for this to be stated as explicitly as
    require_role rather than left implicit.

    Fails closed on all three of: a stale session, a bug in the login flow that
    never set tenant_id, and a request that skipped login entirely. All three
    get an identical hard 401, BEFORE any query runs and before a tenant
    context is established on a connection.

    What it must never do:
      - compute or fall back to a default tenant, and
      - treat a missing tenant_id as "act on nothing" and return an empty list.
        An empty list reads to the caller as "you have zero rows", which is a
        materially different and worse failure than "you are not authorised" —
        the same reasoning as classify_row()'s None route defaulting to
        needs_review rather than auto-pass.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("tenant_id") is None:
            return jsonify({"error": "No tenant context for this session."}), 401
        return fn(*args, **kwargs)
    return wrapper
