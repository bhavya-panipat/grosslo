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
import secrets
from functools import wraps

from flask import session, jsonify, request, g
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


def hash_password(password: str) -> str:
    """
    Hashes a USER's password (Phase 1.2). Distinct from hash_access_code()
    above, and the difference is not stylistic.

    hash_access_code() runs normalize_access_code(), which upper-cases and
    strips. That is correct for the shared demo codes, which were compared
    case-insensitively client-side long before they were hashed. Applying it to
    a password would silently make every password case-insensitive and discard
    leading and trailing characters — collapsing the search space an attacker
    has to cover, on the credential that actually identifies a person. So
    passwords are hashed verbatim, with no normalisation whatsoever.

    Same pbkdf2:sha256 pinning as hash_access_code, for the same reason:
    werkzeug's default is scrypt, and hashlib.scrypt is absent on this repo's
    interpreter.
    """
    if not isinstance(password, str) or not password:
        raise ValueError("password must be a non-empty string")
    return generate_password_hash(password, method="pbkdf2:sha256")


# A real hash of a value nobody knows, verified against whenever there is no
# stored hash to verify against. See verify_password() for why this exists.
# Computed once at import: it costs one pbkdf2 (~0.5s) at startup, not per
# request.
_DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_hex(32), method="pbkdf2:sha256")


def verify_password(password_hash: str | None, password: str) -> bool:
    """
    Checks a password against a stored hash. False — never an exception — when
    the user has no local password at all, which is the state an SSO-provisioned
    user will be in from 1.3 (users.password_hash is nullable, IDENTITY_DESIGN.md
    3.2). Such a user must fail local login cleanly rather than crash it.

    WHEN THERE IS NO HASH, IT STILL DOES THE WORK. Returning False immediately
    would be correct and would leak: pbkdf2 is deliberately ~0.5s, so an
    absent hash answers in single-digit milliseconds while a present one takes
    half a second. Measured on this machine before this mitigation: 511.6ms for
    an account that exists against 6.6ms for one that does not — a 77x
    difference, distinguishable in ONE request, with no statistics needed.

    That made login an account-enumeration oracle even though every response
    body was byte-identical. Content symmetry and timing symmetry are different
    guarantees, and step 4 only established the first. Verifying against a
    fixed dummy hash spends comparable work on both paths so the two are no
    longer separable by clock.

    Note this is a mitigation, not a proof of constant time: hash comparison
    cost still varies slightly, and network jitter dwarfs the remainder. It
    removes an oracle that was usable with a single sample; it does not claim
    immunity to arbitrarily-many-sample statistical attacks.
    """
    if not isinstance(password, str):
        password = ""
    if not password_hash:
        check_password_hash(_DUMMY_PASSWORD_HASH, password)
        return False
    return check_password_hash(password_hash, password)


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
    """
    Resolves the request's tenant from its subdomain, or None.

    Cached on flask.g for the life of the request: this hits the database, and
    a single submission would otherwise resolve the same slug three times
    (the decorator, the write, and the audit-log line).
    """
    if "_resolved_tenant" in g:
        return g._resolved_tenant
    slug = tenant_slug_from_host(request.host)
    tenant = review_queue.get_tenant_by_slug(slug) if slug else None
    g._resolved_tenant = tenant
    return tenant


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


# ---------------------------------------------------------------------------
# Permissions (Phase 1.2, IDENTITY_DESIGN.md 3.1)
#
# Routes are guarded by what they DO, not by who is allowed to do it. The
# alternative — an allow-list of role names at each route — is correct for the
# roles that exist when it is written and one forgetful edit away from wrong
# when a role is added, which is the same shape as the "add WHERE tenant_id to
# the queries we have today" approach 1.1 rejected.
#
# The catalogue and the role mapping live in code rather than in a table: they
# are system-defined in 1.2, and a constant shipping alongside the routes it
# guards cannot drift from them the way a seeded table can.
#
# NOT DEFINED, deliberately: a `submit_row` permission. POST /api/submissions
# is unauthenticated by design (see its docstring and require_resolved_tenant)
# so there is no session to hold such a permission. Defining one would imply an
# enforcement point that does not exist.
# ---------------------------------------------------------------------------
PERMISSIONS = (
    "view_queue",         # GET /api/submissions, GET /api/submissions/<id>
    "decide_row",         # POST .../decide
    "export_row",         # POST .../export, POST .../complete
    "view_audit_log",     # GET /api/audit-log
    "view_bank_balance",  # GET /api/razorpayx/balance
    "manage_users",       # the 1.2 user-admin routes
)

# Derived from what the routes ENFORCE today, not from what the names suggest,
# so this swap changes no tenant's effective access. In particular `hr` holds
# view_audit_log because /api/audit-log is guarded by @require_tenant alone
# today and both roles can already read it — restricting a compliance surface
# is a product decision, not a side effect of refactoring enforcement.
ROLE_PERMISSIONS = {
    "hr": frozenset({"view_queue", "view_audit_log"}),
    "finance": frozenset({"view_queue", "decide_row", "export_row",
                          "view_audit_log", "view_bank_balance"}),
    "owner": frozenset(PERMISSIONS),
}


def current_roles() -> list:
    """
    The roles this session holds.

    Bridges two session shapes on purpose. Until step 4 a session carries one
    shared string, `role`; afterwards it carries a real per-user list, `roles`.
    Reading the list first and falling back means step 2 can swap every route's
    guard without also changing the session, keeping the two changes separately
    reviewable — and step 4 becomes additive rather than a second sweep.
    """
    roles = session.get("roles")
    if roles is not None:
        return list(roles)
    role = session.get("role")
    return [role] if role else []


def has_permission(permission: str) -> bool:
    if permission not in PERMISSIONS:
        # A typo'd permission must never silently authorise. Raising beats
        # returning False, which would look like a plain 403 and hide the bug.
        raise ValueError(
            f"unknown permission {permission!r} — must be one of {PERMISSIONS}"
        )
    return any(permission in ROLE_PERMISSIONS.get(r, frozenset())
               for r in current_roles())


def require_permission(permission: str):
    """
    Route decorator: refuses unless the session's roles grant `permission`.

    RETURNS 401, BYTE-IDENTICAL TO require_role, ON PURPOSE. This decorator
    replaces require_role at every route in one step, and that step's entire
    value is that it provably changes no observable behaviour — so it does not
    also change a status code. 403 is the semantically correct answer here (401
    means "I do not know who you are", which is the wrong thing to tell a
    caller who IS identified and simply may not do this, and a client that
    reacts to 401 by re-authenticating would loop). Changing it is a real,
    separate decision about the HTTP contract, not a side effect of moving the
    enforcement point — so it is flagged rather than folded in here.
    """
    if permission not in PERMISSIONS:
        raise ValueError(f"unknown permission {permission!r}")  # at import, not per-request

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not has_permission(permission):
                return jsonify({"error": "Not authenticated for this action."}), 401
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# require_role() lived here until Phase 1.2 step 2 and is deliberately GONE,
# not kept alongside require_permission as a still-working alternative. Every
# route it guarded now checks a permission instead, and leaving a second,
# role-name-based enforcement path in the module is how a future route ends up
# guarded by the mechanism this phase replaced — the "undeleted superseded
# code" failure this repo has hit before. Its behaviour is preserved exactly
# inside require_permission (same 401, same body); what is gone is the ability
# to write a new route against role names.


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
