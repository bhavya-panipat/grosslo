"""
auth.py — server-side session verification for the HR/Finance role gate, and
tenant resolution.

Replaces role-gate.tsx's previous client-side-only check (a hardcoded code
compared in the browser, stored in sessionStorage, readable by anyone who
opens devtools). This is still deliberately scoped to two SHARED role-codes
(HR, Finance) — not a per-person account system — but as of Phase 1.1 step 5
those codes are PER TENANT rather than one global pair (MULTI_TENANT_DESIGN.md
3.3's interim model). Real per-user accounts, SSO and RBAC are 1.2; 1.1's only
job on that seam is getting tenant_id into the session correctly, so that 1.2
can replace `role` with real per-user role data without re-deriving the tenant
boundary.

Session state is Flask's built-in signed cookie session (itsdangerous,
already a Flask dependency — no new package), holding
{"role": "hr" | "finance", "tenant_id": int}. Signed with app.secret_key,
HttpOnly, so it can't be forged without the key and can't be read by JS.

TENANT RESOLUTION IS FROM THE SUBDOMAIN, NOT THE REQUEST BODY (3.3). A
tenant_id in a JSON payload is a client-supplied value with zero verification —
any authenticated session could name a different tenant and read its data,
which is the isolation guarantee failing at the very first hop rather than a
hardening gap found later. So it is never read from there.
"""

from __future__ import annotations

import os
from functools import wraps

from flask import session, jsonify, request
from werkzeug.security import generate_password_hash, check_password_hash

import review_queue

ROLES = ("hr", "finance")

# {slug}.grosslo.app — the host suffix under which a leading label identifies a
# tenant. Overridable so a deployment on another domain doesn't have to patch
# code.
TENANT_DOMAIN_SUFFIX = os.environ.get("TENANT_DOMAIN_SUFFIX", "grosslo.app")


def normalize_access_code(code: str) -> str:
    """
    Case- and whitespace-insensitive, matching role-gate.tsx's original
    client-side comparison exactly, so existing demo codes keep working
    unchanged. Applied identically when hashing and when checking — if these
    ever diverge, every login fails.
    """
    return (code or "").strip().upper()


def hash_access_code(code: str) -> str:
    """
    Hashes a tenant's HR/Finance access code for storage in
    tenant_settings.hr_access_code_hash / finance_access_code_hash.

    3.3 flags this as a genuine improvement BEYOND what tenant-scoping
    required, called out rather than folded in silently: the previous
    _DEFAULT_CODES compared plaintext directly, so anything that could read the
    configuration learned the login code outright. Storing per-tenant plaintext
    would have satisfied the tenancy scope just as well; hashing is extra, and
    saying so is the same standard this repo applies to unstated scope
    expansion elsewhere.
    """
    # Method pinned explicitly rather than left to werkzeug's default, which is
    # scrypt: hashlib.scrypt is absent unless Python was built against an
    # OpenSSL that provides it, and it is absent on this repo's interpreter
    # (macOS Command Line Tools 3.9), where the default raises AttributeError
    # at hash time. pbkdf2:sha256 is available everywhere Python is.
    return generate_password_hash(normalize_access_code(code), method="pbkdf2:sha256")


def tenant_slug_from_host(host: str | None) -> str | None:
    """
    Extracts the tenant slug from a Host header: 'acme.grosslo.app' -> 'acme'.
    Returns None when the host carries no tenant label.

    TRUST BOUNDARY, stated because it is easy to miss: Host is client-supplied.
    In production the reverse proxy that terminates TLS is what makes this
    trustworthy — it must set or validate Host rather than passing through
    whatever arrived. Nothing here can verify that, and the only thing this
    resolution is allowed to authorise is the already-public submission route
    (see require_resolved_tenant). Every route that READS tenant data takes its
    tenant from the signed session instead, so a forged Host cannot reach one
    tenant's data from another's subdomain.
    """
    if not host:
        return None
    hostname = host.split(":")[0].strip().lower()  # strip any :port
    suffix = "." + TENANT_DOMAIN_SUFFIX.lower()
    if not hostname.endswith(suffix):
        return None
    label = hostname[: -len(suffix)]
    # Only a single leading label identifies a tenant; 'a.b.grosslo.app' is not
    # tenant 'a.b', it is a host this application does not recognise.
    if not label or "." in label:
        return None
    return label


def tenant_from_request():
    """Resolves the request's tenant from its subdomain, or None."""
    slug = tenant_slug_from_host(request.host)
    if slug is None:
        return None
    return review_queue.get_tenant_by_slug(slug)


def verify_login(tenant_id: int, role: str, code: str) -> bool:
    """
    True if `code` matches the configured secret for `role` WITHIN THIS TENANT.

    There is no global fallback pair any more. The previous _DEFAULT_CODES /
    _ENV_VARS module constants were one HR code and one Finance code for the
    whole process; with two tenants that is the same shared secret unlocking
    both companies' queues. A tenant with no settings row cannot be logged into
    at all, rather than falling back to something that would work.
    """
    if role not in ROLES or not isinstance(code, str):
        return False
    hashes = review_queue.get_tenant_access_code_hashes(tenant_id)
    if hashes is None or not hashes.get(role):
        return False
    return check_password_hash(hashes[role], normalize_access_code(code))


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
    The tenant this request is AUTHENTICATED for, from the signed session only.

    Deliberately does not consult the subdomain. Every route that reads or
    mutates tenant-owned data uses this, so a forged Host header cannot widen
    what an authenticated session can reach (3.3).
    """
    return session.get("tenant_id")


def resolved_tenant_id():
    """
    Session tenant if there is one, otherwise the subdomain's tenant.

    ONLY for the public submission route, which by design has no session (see
    api_create_submission's docstring). Do not use this for anything that
    returns tenant data — see current_tenant_id() for why.
    """
    from_session = session.get("tenant_id")
    if from_session is not None:
        return from_session
    tenant = tenant_from_request()
    return tenant["id"] if tenant else None


def require_tenant(fn):
    """
    Route decorator: 401s immediately unless the SESSION carries a tenant_id.
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


def require_resolved_tenant(fn):
    """
    Like require_tenant, but accepts a tenant resolved from the SUBDOMAIN when
    there is no session.

    Exists for exactly one route: POST /api/submissions, which is deliberately
    unauthenticated so /optimize/batch's public "Submit correction" flow keeps
    working. Step 3 had to close that route outright — a row needs a tenant_id
    and there was no honest way to get one without a session — and this is what
    reopens it, using 3.3's actual resolution mechanism rather than trusting a
    tenant field in the body.

    Still fails closed: a request to a host with no tenant label gets the same
    hard 401, never a default tenant and never a silent no-op. What it grants
    is narrow — the ability to submit a row into a named tenant's review queue,
    which is what this route already allowed anyone to do — and it grants no
    read access whatsoever.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if resolved_tenant_id() is None:
            return jsonify({
                "error": "No tenant for this request. Submissions must be made on a "
                         "tenant subdomain (e.g. acme." + TENANT_DOMAIN_SUFFIX + ").",
            }), 401
        return fn(*args, **kwargs)
    return wrapper
