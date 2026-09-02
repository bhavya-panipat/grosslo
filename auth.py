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
