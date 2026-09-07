"""
review_queue.py — maker-checker persistence for the HR-submits /
Finance-reviews workflow.

SCOPE, stated plainly (mirrors the discipline everywhere else in this repo):
- Postgres, via psycopg. Ported from SQLite in Roadmap Phase 1.1 step 1
  (MULTI_TENANT_DESIGN.md section 7) — SQLite has no row-level security and no
  per-connection session variables to key a defence-in-depth policy on, both of
  which the tenancy work needs.
- TENANT-SCOPED as of step 3. Every public function takes `tenant_id` as a
  REQUIRED FIRST POSITIONAL ARGUMENT, and every statement carries
  `WHERE tenant_id = %s` unconditionally. tenant_id is deliberately NOT a
  member of any optional filter dict: section 3.1's guarantee is that no
  code path CAN return another tenant's row, not merely that none currently
  does, and an optional filter is one forgetful call site away from failing
  that. A caller that has no tenant_id cannot call these functions at all.
- No real authentication anywhere in this module. "HR" and "Finance" are
  role labels a caller asserts, not identities this module verifies. The
  session carries tenant_id; see auth.require_tenant for the fail-closed gate.
- Zero new tax/compliance logic. Every row this module stores is the
  already-computed output of _build_optimize_response() (app.py) or the
  batch-audit pipeline — this module's only job is persisting it, deciding
  on it, and reading it back. If a function here starts computing a tax
  figure, that's a scope violation, not a feature.

TWO INDEPENDENT ENFORCEMENT LAYERS, on purpose (section 3.1). The first is the
required-argument + unconditional-WHERE discipline above. The second is
row-level security in the database itself, keyed on a transaction-scoped
`app.tenant_id` setting. The second exists precisely because the first is
application code that a future function can forget; "an invariant that held
everywhere it was checked, until a new code path didn't check it" is the exact
bug class this design is written against.

RUNNING THIS REQUIRES A REACHABLE POSTGRES. `brew services start postgresql@16`.
Because app.py calls init_db() at import time, a stopped server fails the test
suite at *collection*, as a wall of connection errors — that is a missing
service, not a bug in whatever you just changed.

IT ALSO REQUIRES THE UNPRIVILEGED grosslo_app ROLE (scripts/setup_app_role.sql).
Superusers and BYPASSRLS roles ignore every RLS policy, so connecting as the
developer's own OS superuser would leave the second layer enforcing nothing
while still appearing to be configured.

A MISSING SCHEMA IS NOT REPAIRED AUTOMATICALLY. init_db() creates it; every
other entry point raises SchemaMissingError if it isn't there. The SQLite
version did the opposite (rebuilt the schema on every connection), which was
right for a local file a stray `rm` could delete and wrong for a database,
where a silent rebuild reports success while the data is gone.

APPROVE DOES NOT DISPATCH ANYTHING. Approving a submission row writes a
status change and an audit-log entry ("Approved — Payout SIMULATED, no
live dispatch"). It never calls RazorpayX, never touches app.py's
export-payload code path unless a human separately, explicitly triggers
that export afterward. This boundary is the same one drawn everywhere else
in this codebase around live execution, and it does not move here either.
"""

from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

import secret_store

# Local dev default targets the Homebrew postgresql@16 cluster over the unix
# socket AS grosslo_app, not as the developer's own OS role. That is not a
# cosmetic choice: see the module docstring and scripts/setup_app_role.sql —
# a superuser connection silently disables every RLS policy below.
DEFAULT_DSN = "postgresql:///grosslo?user=grosslo_app"

# Replaces the old module-level DB_PATH. Tests swapped that file path to get an
# isolated database per test module; Postgres has no file to swap, so the same
# isolation property is provided by giving each test module its own *schema*
# inside one database. Production/dev leaves this at "public".
DB_SCHEMA = "public"

VALID_STATUSES = {"pending", "approved", "rejected"}
VALID_SOURCES = {"single", "batch"}

# Tables that hold tenant-owned rows and therefore carry tenant_id + RLS.
# `tenants` is the registry itself, not tenant-owned data, so it stays out.
#
# tenant_settings joined this list in step 4, when it started holding RazorpayX
# banking credentials — categorically higher-stakes than anything else here
# (3.5). An earlier note here worried that RLS would break login, since login
# must read a tenant's access-code hashes before a session exists. That worry
# was misplaced: 3.3 resolves the tenant from the SUBDOMAIN, before and
# independently of authentication, so a tenant context is available to key the
# policy on by the time the codes are read. Step 5 does exactly that.
#
# users/user_roles joined in Phase 1.2 step 1. They are tenant-owned like any
# other row here, so they get the same two independent enforcement layers
# rather than a third pattern invented for identity (IDENTITY_DESIGN.md 3.6).
# The one deliberate exception is login itself, which must find a user before a
# session exists — it resolves inside the tenant already established from the
# subdomain, exactly as verify_login() reads that tenant's code hashes under
# RLS today, so no new trust boundary appears.
_TENANT_SCOPED_TABLES = ("submissions", "submission_rows", "tenant_settings",
                         "users", "user_roles")


class SchemaMissingError(RuntimeError):
    """
    Raised when a query is attempted against a DB_SCHEMA whose tables aren't
    there. Named specifically, rather than surfacing as a bare
    psycopg.errors.UndefinedTable or a generic 500, so this is unmistakable in
    a log instead of blending into every other database error. See
    _require_schema() for why this is not repaired automatically.
    """


class RlsNotEnforceableError(RuntimeError):
    """
    Raised at startup when the configured connection role would IGNORE every
    row-level-security policy — i.e. it is a superuser or holds BYPASSRLS.

    This exists because the failure it prevents is invisible. The policies are
    still created, still show in \\d, and every application-layer test still
    passes, because those exercise the correctly-written path with its explicit
    WHERE tenant_id. What silently disappears is the SECOND enforcement layer —
    the one MULTI_TENANT_DESIGN.md 3.1 added specifically to catch a future
    query that forgets the predicate. There is no error, no log line, and no
    behavioural difference until the day something depends on it.

    It nearly shipped that way during Phase 1.1: the Homebrew default
    connection role is the developer's own OS superuser. Fixing it once by
    adding grosslo_app is not enough, because DATABASE_URL is configuration —
    anyone can point it back at a privileged role and get a working app with
    half its isolation gone. So the invariant is asserted at startup rather
    than documented and hoped about.
    """


class TenantContextMissing(ValueError):
    """
    Raised when a persistence call is made without a usable tenant_id.

    Fails closed and fails loudly, exactly as auth.require_tenant does at the
    HTTP boundary: there is no default tenant, and no query is ever run with a
    NULL or absent tenant. Returning an empty result instead would read to the
    caller as "this tenant has no rows", which is a materially worse and more
    misleading failure than "you did not say which tenant".
    """


def _dsn() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DSN)


def _checked_tenant_id(tenant_id) -> int:
    """
    The single chokepoint every tenant-scoped call passes through. Deliberately
    strict: None, a string, or a bool is rejected outright rather than coerced,
    because every one of those means the caller does not actually know which
    tenant it is acting for, and guessing on their behalf is how a
    cross-tenant write happens.
    """
    if tenant_id is None:
        raise TenantContextMissing(
            "tenant_id is required and was None. There is no default tenant — see "
            "MULTI_TENANT_DESIGN.md 3.1. If this came from a request handler, the "
            "session had no tenant_id and auth.require_tenant should have 401'd first."
        )
    # bool is an int subclass; True would otherwise sail through as tenant 1.
    if isinstance(tenant_id, bool) or not isinstance(tenant_id, int):
        raise TenantContextMissing(
            f"tenant_id must be an int, got {type(tenant_id).__name__}: {tenant_id!r}"
        )
    return tenant_id


# Same window-based idempotency approach used nowhere else in this repo
# because nothing else needed one — deliberately simple, per the brief's
# own instruction not to over-build this into a dedup service. Two
# submissions for the same person at the same CTC on the same calendar day
# are treated as a likely duplicate. A genuinely different offer for the
# same person on the same day (rare, but real) would also get flagged —
# that's a false-positive risk taken on purpose in exchange for a few
# lines of logic instead of a real dedup service.
#
# `email` folds into the key when supplied — flagged in external review:
# name+CTC alone collides for multiple real hires at an identical
# standardized compensation band (common at scale), a false duplicate with
# no code-level fix before this. `email` was already an optional field on
# every submission row (collected for the RazorpayX export payload, see
# app.py's built_rows), so this reuses it rather than adding a column.
#
# tenant_id leads the key as of step 3, per section 4: without it the dedupe
# window is global across tenants, so two different companies hiring two
# different "Anika Verma"s at the same CTC on the same day false-collide and
# the second company's submission is silently rejected as a duplicate of a row
# it is not allowed to see. Adding the column to the table would not have fixed
# that on its own — the hash itself had to change. This does mean dedupe_hash
# values stored before step 3 no longer match freshly computed ones; that is
# harmless here because step 2 truncated both tables, and is noted so it is not
# mistaken later for dedupe silently stopping.
def _dedupe_hash(tenant_id: int, employee_name: str | None, ctc: float,
                 email: str | None = None) -> str:
    tenant_id = _checked_tenant_id(tenant_id)
    window = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    normalized_name = (employee_name or "anon").strip().lower()
    normalized_email = (email or "").strip().lower()
    if normalized_email:
        key = f"{tenant_id}|{normalized_name}|{normalized_email}|{round(ctc)}|{window}"
    else:
        key = f"{tenant_id}|{normalized_name}|{round(ctc)}|{window}"
    return hashlib.sha256(key.encode()).hexdigest()


def _ensure_schema(conn: psycopg.Connection) -> None:
    """
    Creates the schema, tables, indexes and RLS policies. Called ONLY from
    init_db() — explicit startup and migration — never from _conn().

    This deliberately reverses the SQLite version's behaviour, which ran this
    on every single connection so that a missing schema was silently rebuilt.
    That was the right call when the store was a local file that a stray `rm`
    could remove; it is the wrong call for a database, where "the schema is
    gone" means someone dropped it, a migration half-ran, or the app is
    pointed at the wrong DATABASE_URL. Silently recreating empty tables in
    any of those cases reports success while the data is gone. See
    _require_schema() for what happens instead.

    Column types are chosen to preserve the SQLite behaviour this was ported
    from, not to modernise:
      - ctc is DOUBLE PRECISION, not NUMERIC. SQLite REAL is IEEE-754 binary
        float; NUMERIC is exact decimal and would change comparison and
        rounding behaviour on a money field the tax engine already computed.
      - the timestamp columns stay TEXT. Python writes ISO-8601 strings into
        them today and callers read those strings back; TIMESTAMPTZ would
        change the read-back format, which is a behaviour change rather than
        a port.
      - input_json/computed_json stay TEXT, not JSONB. JSONB normalises key
        order and drops duplicate keys, so _row_to_dict()'s round-trip would
        no longer return what was stored.
      - id is GENERATED BY DEFAULT (not ALWAYS) AS IDENTITY, so the one-off
        SQLite migration can insert explicit ids and preserve the
        submission_rows -> submissions foreign key relationships.
    """
    schema = sql.Identifier(DB_SCHEMA)
    conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(schema))
    conn.execute(sql.SQL("SET LOCAL search_path TO {}").format(schema))

    # tenants / tenant_settings come first: both tenant_id columns below are FKs
    # into tenants(id). Section 4 writes tenants.id as SERIAL; this uses
    # GENERATED BY DEFAULT AS IDENTITY instead, purely so all three tables in
    # this database declare identity the same way rather than mixing the legacy
    # and modern spellings. Functionally equivalent — flagged rather than
    # slipped in, since silently deviating from the schema doc is exactly the
    # habit this project treats as a defect class.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            slug TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tenant_settings (
            tenant_id INTEGER PRIMARY KEY REFERENCES tenants(id),
            hr_access_code_hash TEXT NOT NULL,
            finance_access_code_hash TEXT NOT NULL,
            razorpayx_key_id TEXT,
            razorpayx_key_secret TEXT,
            razorpayx_account_number TEXT
        )
    """)
    # tenant_id is NOT NULL with NO DEFAULT, deliberately. A default would
    # silently satisfy an INSERT that forgot to supply it, which is the exact
    # failure MULTI_TENANT_DESIGN.md 3.1's "required argument, never optional"
    # rule exists to prevent.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id),
            created_at TEXT NOT NULL,
            source TEXT NOT NULL,
            submitted_by TEXT NOT NULL DEFAULT 'hr'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS submission_rows (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id),
            submission_id INTEGER NOT NULL REFERENCES submissions(id),
            row_index INTEGER NOT NULL,
            employee_name TEXT,
            ctc DOUBLE PRECISION NOT NULL,
            dedupe_hash TEXT NOT NULL,
            input_json TEXT NOT NULL,
            computed_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            reason TEXT,
            decided_at TEXT,
            decided_by TEXT
        )
    """)
    # Additive migration for the orchestration columns — CREATE TABLE IF NOT
    # EXISTS above won't add columns to a table that already exists from
    # before this feature shipped, so an existing deployment picks them up on
    # the next init_db(). (SQLite read these from PRAGMA table_info; the
    # Postgres equivalent is information_schema, scoped to DB_SCHEMA so a test
    # module's schema doesn't read another's columns.)
    existing_cols = {
        row["column_name"] for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = 'submission_rows'",
            (DB_SCHEMA,),
        )
    }
    for col, ddl in [
        ("orchestration_json", "ALTER TABLE submission_rows ADD COLUMN orchestration_json TEXT"),
        ("route", "ALTER TABLE submission_rows ADD COLUMN route TEXT"),
        ("severity", "ALTER TABLE submission_rows ADD COLUMN severity TEXT"),
        ("exported_at", "ALTER TABLE submission_rows ADD COLUMN exported_at TEXT"),
        ("dispatched_at", "ALTER TABLE submission_rows ADD COLUMN dispatched_at TEXT"),
    ]:
        if col not in existing_cols:
            conn.execute(ddl)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_tenant ON submissions(tenant_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rows_tenant ON submission_rows(tenant_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rows_submission ON submission_rows(submission_id)")
    # tenant_id is PREPENDED to these two, not merely added alongside: a dedupe
    # or route lookup index spanning tenants is itself a leak surface (section
    # 4). idx_rows_submission is left alone — submission_id is already
    # tenant-scoped transitively through its FK.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rows_dedupe ON submission_rows(tenant_id, dedupe_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rows_route ON submission_rows(tenant_id, route)")

    # ---------------------------------------------------------------------
    # Phase 1.2 (IDENTITY_DESIGN.md §4). Created here, read by nothing yet:
    # step 1 adds the shape, step 4 adds the login that uses it.
    # ---------------------------------------------------------------------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id),
            email TEXT NOT NULL,
            display_name TEXT NOT NULL,
            -- NULLABLE on purpose: an SSO-provisioned user (1.3) has no local
            -- password and must not be able to authenticate with one. §3.2
            -- shapes this now so 1.3 adds idp_subject without reshaping.
            password_hash TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_login_at TIMESTAMPTZ,
            -- Scoped to the tenant, NOT globally unique: one human consulting
            -- for two companies is two accounts. A global constraint would
            -- both forbid that and leak, through a collision, that an address
            -- is already registered somewhere in the system.
            UNIQUE (tenant_id, email)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_roles (
            tenant_id INTEGER NOT NULL REFERENCES tenants(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            role TEXT NOT NULL,
            PRIMARY KEY (user_id, role)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_roles_tenant ON user_roles(tenant_id)")

    # Additive columns, same information_schema pattern as the orchestration
    # columns above. codes_disabled_at records that a tenant's shared access
    # codes were retired (§3.3); decided_by_user_id is the attribution §3.4
    # adds WITHOUT backfilling — historical rows keep decided_by='finance' and
    # a NULL user id, which is the truthful statement that the system did not
    # know who acted.
    for table, col, ddl in [
        ("tenant_settings", "codes_disabled_at",
         "ALTER TABLE tenant_settings ADD COLUMN codes_disabled_at TIMESTAMPTZ"),
        ("submission_rows", "decided_by_user_id",
         "ALTER TABLE submission_rows ADD COLUMN decided_by_user_id INTEGER REFERENCES users(id)"),
    ]:
        present = conn.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s AND column_name = %s",
            (DB_SCHEMA, table, col),
        ).fetchone()
        if not present:
            conn.execute(ddl)

    _ensure_rls(conn)


def _ensure_rls(conn: psycopg.Connection) -> None:
    """
    The SECOND, INDEPENDENT enforcement layer (section 3.1).

    Everything here is redundant with the application layer's mandatory
    `WHERE tenant_id = %s` — and that redundancy is the entire point. The
    application layer is code a future function can forget to write; this one
    holds even for a query with no tenant predicate at all, which is exactly
    what the section 7 step 6 test connects directly to prove.

    FORCE, not merely ENABLE: a table's owner is exempt from its own policies
    unless forced, and grosslo_app owns these tables (it creates them, and owns
    each test schema). ENABLE alone would leave the policy inert for the very
    role the application uses — configured, visible in \\d, and enforcing
    nothing.

    current_setting(..., true) returns NULL rather than raising when the
    setting is absent, so an unset tenant context matches no rows instead of
    matching all of them. Absent context yielding zero rows is the correct
    fail-closed behaviour for a row filter; the loud failure for a missing
    tenant belongs one layer up, where auth.require_tenant 401s and
    _checked_tenant_id raises rather than letting a caller reach here at all.
    """
    for table in _TENANT_SCOPED_TABLES:
        # The policy expression is identical for all three: each carries a
        # tenant_id column (tenant_settings' happens to also be its primary
        # key), so one shape covers them rather than inventing a second.
        ident = sql.Identifier(table)
        conn.execute(sql.SQL("ALTER TABLE {} ENABLE ROW LEVEL SECURITY").format(ident))
        conn.execute(sql.SQL("ALTER TABLE {} FORCE ROW LEVEL SECURITY").format(ident))
        # No CREATE POLICY IF NOT EXISTS in Postgres 16, so drop-then-create
        # keeps init_db() idempotent.
        conn.execute(sql.SQL("DROP POLICY IF EXISTS tenant_isolation ON {}").format(ident))
        conn.execute(sql.SQL(
            "CREATE POLICY tenant_isolation ON {} "
            "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::int) "
            "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::int)"
        ).format(ident))


def _require_schema(conn: psycopg.Connection) -> None:
    """
    Points the connection at DB_SCHEMA and FAILS LOUDLY if the tables aren't
    there, rather than creating them.

    A missing schema is never repaired here on purpose. Recreating it would
    make every subsequent read return zero rows and every write succeed into a
    fresh empty table — the caller gets a 200 and an empty list, which is
    indistinguishable from "this tenant genuinely has no submissions yet" right
    up until somebody notices the history is gone. That is the same failure
    shape MULTI_TENANT_DESIGN.md 3.1 rules out for require_tenant, which 401s
    on a missing tenant_id instead of returning an empty result, and the same
    discipline as classify_row()'s None route defaulting to needs_review rather
    than auto-pass. Data loss must not be reported as success.

    Run init_db() (app.py does, at startup) to create the schema deliberately.
    """
    conn.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(DB_SCHEMA)))
    present = conn.execute(
        "SELECT to_regclass(%s) AS submissions, to_regclass(%s) AS submission_rows",
        (f"{DB_SCHEMA}.submissions", f"{DB_SCHEMA}.submission_rows"),
    ).fetchone()
    missing = [name for name, oid in present.items() if oid is None]
    if missing:
        raise SchemaMissingError(
            f"Postgres schema '{DB_SCHEMA}' is missing table(s): {', '.join(sorted(missing))} "
            f"(connection: {_dsn()}). This is NOT auto-repaired: recreating the tables here "
            f"would silently return empty results for data that may still need recovering. "
            f"If this is a fresh database, run review_queue.init_db(). If it is not, check "
            f"DATABASE_URL points at the right database and that no migration was left half-run."
        )


@contextmanager
def _conn(tenant_id: int):
    """
    The only way into the database for tenant-scoped work, and the reason
    tenant_id is a required argument everywhere above.

    Opens a transaction, pins `app.tenant_id` to it, and hands back a
    connection every subsequent statement runs inside. Section 3.1 makes this
    the module's hard contract: every query runs inside a transaction that
    opened with a transaction-scoped tenant setting, and no query ever runs on
    a connection outside that boundary.

    set_config(..., is_local => true) IS `SET LOCAL`, in a form that takes a
    bound parameter instead of interpolating a value into DDL text. It is
    transaction-scoped and discarded at COMMIT or ROLLBACK regardless of what a
    pool later does with the physical connection.

    DO NOT "SIMPLIFY" THIS TO A SESSION-SCOPED SET. Nothing is pooled today —
    this opens a fresh connection per call — but with any pool in front of it a
    session-scoped `SET app.tenant_id` persists on the physical connection
    after it is returned, so a checkout that is not perfectly reset carries one
    request's tenant into the next. The failure is silent: the second request
    gets a 200 containing the first tenant's data, nothing errors, nothing
    logs. That is a documented category of RLS production bug, not a
    hypothetical, and it is worse than a crash.
    """
    tenant_id = _checked_tenant_id(tenant_id)
    conn = psycopg.connect(_dsn(), row_factory=dict_row)
    try:
        _require_schema(conn)
        conn.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def _admin_conn():
    """
    Connection for work that is genuinely not tenant-scoped: creating the
    schema, and provisioning rows in `tenants` itself. Sets no app.tenant_id,
    and must never be used to read or write submissions/submission_rows — the
    RLS policies would match zero rows there anyway, which is the intended
    outcome rather than something to work around.
    """
    conn = psycopg.connect(_dsn(), row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def assert_rls_enforceable(conn: psycopg.Connection) -> None:
    """
    Refuses to proceed if the connection role would bypass RLS. See
    RlsNotEnforceableError for why this is a hard failure and not a warning:
    a warning scrolls past, and the thing it warns about produces no other
    symptom.
    """
    role = conn.execute(
        "SELECT current_user AS name, rolsuper, rolbypassrls FROM pg_roles "
        "WHERE rolname = current_user"
    ).fetchone()
    if role is None:
        return  # cannot introspect; nothing to assert against
    if role["rolsuper"] or role["rolbypassrls"]:
        why = "a SUPERUSER" if role["rolsuper"] else "BYPASSRLS"
        raise RlsNotEnforceableError(
            f"Refusing to start: the database role {role['name']!r} is {why}, so PostgreSQL "
            f"exempts it from every row-level-security policy. The tenant-isolation policies "
            f"on {', '.join(_TENANT_SCOPED_TABLES)} would exist and enforce NOTHING, silently — "
            f"no error, no log line, and every application-layer test still passing. "
            f"Connect as the unprivileged role instead (scripts/setup_app_role.sql creates "
            f"grosslo_app), or set DATABASE_URL to one. Current DSN: {_dsn()}"
        )


def init_db() -> None:
    """
    Creates the schema if it isn't there. This is now the ONLY place that
    happens — _conn() verifies and raises SchemaMissingError instead of
    creating, so this call is required at startup rather than being the
    convenience it was under SQLite. app.py calls it at import time.

    Also the startup gate for the RLS-bypass invariant (see
    assert_rls_enforceable), because this is the one call guaranteed to run
    before anything else touches the database.
    """
    with _admin_conn() as conn:
        assert_rls_enforceable(conn)
        _ensure_schema(conn)


def _drop_schema(schema: str | None = None) -> None:
    """
    DESTRUCTIVE: drops `schema` (default: DB_SCHEMA) and everything in it.

    This is the replacement for what the test suite used to do by deleting the
    SQLite file — each test module points DB_SCHEMA at its own schema and calls
    this to get a clean namespace between tests. There is no file to delete
    under Postgres, and dropping a whole database per test module would be far
    slower and would need a separate connection to `postgres` to do it.

    Callers should pass the schema name EXPLICITLY rather than relying on the
    DB_SCHEMA default, because DB_SCHEMA is process-global mutable state and
    the whole suite runs in one process: a module-level teardown that reads it
    gets whatever the last-executed test happened to leave there, which is not
    necessarily that module's own schema. The SQLite version was immune to this
    by construction — it passed its own TEST_DB constant to os.remove() — so
    passing the name here keeps a property that already existed rather than
    adding a new requirement.

    Deliberately underscore-prefixed and never called from application code.
    """
    target = schema or DB_SCHEMA
    with _admin_conn() as conn:
        conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(target)))


# ---------------------------------------------------------------------------
# Tenant provisioning. Admin-created only, per section 6's resolved decision —
# there is no self-serve signup endpoint in 1.1, and nothing here is reachable
# from a route. scripts/create_tenant.py is the CLI wrapper.
# ---------------------------------------------------------------------------

def create_tenant(slug: str, display_name: str) -> dict:
    """
    Creates a tenant and returns it. Does NOT create its tenant_settings row:
    that holds the per-tenant access-code hashes the login flow needs, and
    wiring login up is step 5's job, not step 3's.
    """
    if not slug or not slug.strip():
        raise ValueError("slug is required")
    if not display_name or not display_name.strip():
        raise ValueError("display_name is required")
    with _admin_conn() as conn:
        _require_schema(conn)
        return conn.execute(
            "INSERT INTO tenants (slug, display_name) VALUES (%s, %s) "
            "RETURNING id, slug, display_name, created_at",
            (slug.strip().lower(), display_name.strip()),
        ).fetchone()


def get_tenant_by_slug(slug: str) -> dict | None:
    """Resolves a subdomain slug to a tenant row, or None (section 3.3)."""
    with _admin_conn() as conn:
        _require_schema(conn)
        return conn.execute(
            "SELECT id, slug, display_name, created_at FROM tenants WHERE slug = %s",
            ((slug or "").strip().lower(),),
        ).fetchone()


def list_tenants() -> list[dict]:
    """Cross-tenant by definition — admin/ops listing of the registry itself."""
    with _admin_conn() as conn:
        _require_schema(conn)
        return conn.execute(
            "SELECT id, slug, display_name, created_at FROM tenants ORDER BY id"
        ).fetchall()


# ---------------------------------------------------------------------------
# Per-tenant RazorpayX credentials (step 4, section 3.5). These replace the
# process-wide RAZORPAYX_KEY_ID / RAZORPAYX_KEY_SECRET environment variables,
# which meant every company would have been paying out of — and reading the
# balance of — one shared bank account.
#
# Ciphertext in, ciphertext out at the storage boundary: secret_store owns the
# envelope format, and refuses outright to store anything but a test-mode key
# until a real KMS exists (3.5). tenant_settings is RLS-protected, so these go
# through _conn(tenant_id) like any other tenant-owned row.
# ---------------------------------------------------------------------------

def set_tenant_razorpayx_credentials(tenant_id: int, key_id: str | None,
                                     key_secret: str | None,
                                     account_number: str | None = None) -> None:
    """
    Stores (or clears) a tenant's RazorpayX credentials.

    Requires the tenant_settings row to exist — created alongside the tenant's
    access codes. Raises secret_store.LiveCredentialRefused for a non-test-mode
    key; that refusal is deliberate and has no override.
    """
    tenant_id = _checked_tenant_id(tenant_id)
    stored_id = secret_store.encrypt(key_id) if key_id else None
    stored_secret = secret_store.encrypt(key_secret, is_credential=False) if key_secret else None
    with _conn(tenant_id) as conn:
        cur = conn.execute(
            "UPDATE tenant_settings SET razorpayx_key_id = %s, razorpayx_key_secret = %s, "
            "razorpayx_account_number = %s WHERE tenant_id = %s",
            (stored_id, stored_secret, account_number, tenant_id),
        )
        if cur.rowcount == 0:
            raise ValueError(
                f"no tenant_settings row for tenant {tenant_id} — create the tenant's "
                f"settings (access codes) before attaching RazorpayX credentials"
            )


def get_tenant_razorpayx_credentials(tenant_id: int) -> dict | None:
    """
    Returns {"key_id", "key_secret", "account_number"} in PLAINTEXT for the
    caller to use immediately, or None if this tenant has no credentials
    configured. Never log or persist the returned values.

    None here means "no API access for this tenant", NOT "no source account".
    The two are separate: API keys authorise live calls (the balance route),
    while the account number is just which account a generated payout names,
    and a tenant can reasonably configure the second without handing over the
    first. Callers that only need the account number must use
    get_tenant_source_account() — routing them through here imports a gate that
    has nothing to do with what they are asking for.
    """
    tenant_id = _checked_tenant_id(tenant_id)
    with _conn(tenant_id) as conn:
        row = conn.execute(
            "SELECT razorpayx_key_id, razorpayx_key_secret, razorpayx_account_number "
            "FROM tenant_settings WHERE tenant_id = %s",
            (tenant_id,),
        ).fetchone()
    if row is None or not row["razorpayx_key_id"]:
        return None
    return {
        "key_id": secret_store.decrypt(row["razorpayx_key_id"]),
        "key_secret": secret_store.decrypt(row["razorpayx_key_secret"]),
        "account_number": row["razorpayx_account_number"],
    }


def get_tenant_source_account(tenant_id: int) -> str | None:
    """
    The account number a generated payout should name as its SOURCE, or None if
    this tenant has not configured one.

    Deliberately separate from get_tenant_razorpayx_credentials(), which
    returns None whenever there is no API key. The export path needs only this
    one value and makes no live call, so gating it on the presence of API keys
    would tell a tenant that has configured an account that it has not — which
    is exactly what happened before this existed: the export emitted its
    "DO NOT UPLOAD" placeholder for tenants whose account number was sitting
    right there in the row.

    Not a credential and not enveloped: an account number identifies where
    money comes from, it does not authorise moving it, so it is stored and read
    in the clear like any other tenant setting.
    """
    tenant_id = _checked_tenant_id(tenant_id)
    with _conn(tenant_id) as conn:
        row = conn.execute(
            "SELECT razorpayx_account_number FROM tenant_settings WHERE tenant_id = %s",
            (tenant_id,),
        ).fetchone()
    return row["razorpayx_account_number"] if row else None


def create_tenant_settings(tenant_id: int, hr_access_code_hash: str,
                           finance_access_code_hash: str) -> None:
    """
    Creates the tenant's settings row. Separate from create_tenant() because
    the access-code hashes are step 5's concern (3.3's interim shared-code
    model, now scoped per tenant) while the tenant registry entry itself is
    not.
    """
    tenant_id = _checked_tenant_id(tenant_id)
    with _conn(tenant_id) as conn:
        conn.execute(
            "INSERT INTO tenant_settings (tenant_id, hr_access_code_hash, finance_access_code_hash) "
            "VALUES (%s, %s, %s) ON CONFLICT (tenant_id) DO UPDATE SET "
            "hr_access_code_hash = EXCLUDED.hr_access_code_hash, "
            "finance_access_code_hash = EXCLUDED.finance_access_code_hash",
            (tenant_id, hr_access_code_hash, finance_access_code_hash),
        )


def get_tenant_access_code_hashes(tenant_id: int) -> dict | None:
    """Returns {"hr": hash, "finance": hash} for the tenant, or None."""
    tenant_id = _checked_tenant_id(tenant_id)
    with _conn(tenant_id) as conn:
        row = conn.execute(
            "SELECT hr_access_code_hash, finance_access_code_hash FROM tenant_settings "
            "WHERE tenant_id = %s",
            (tenant_id,),
        ).fetchone()
    if row is None:
        return None
    return {"hr": row["hr_access_code_hash"], "finance": row["finance_access_code_hash"]}


# ---------------------------------------------------------------------------
# Tenant-scoped persistence. tenant_id is the required first argument on every
# one of these, and every statement filters on it unconditionally.
# ---------------------------------------------------------------------------

def _row_to_dict(row: dict) -> dict:
    d = dict(row)
    d["input"] = json.loads(d.pop("input_json"))
    d["computed"] = json.loads(d.pop("computed_json"))
    # None for rows created before this feature shipped — callers (the
    # frontend, tests) must handle this, not assume every row has one.
    raw_orchestration = d.pop("orchestration_json", None)
    d["orchestration"] = json.loads(raw_orchestration) if raw_orchestration else None
    return d


def check_duplicate(tenant_id: int, employee_name: str | None, ctc: float,
                    email: str | None = None) -> dict | None:
    """
    Returns the existing pending/approved row this would duplicate, or
    None. Callers decide what to do with a duplicate (block, per the
    brief's "flag or block, don't silently reprocess") — this function
    only detects.
    """
    dedupe_hash = _dedupe_hash(tenant_id, employee_name, ctc, email)
    with _conn(tenant_id) as conn:
        existing = conn.execute(
            "SELECT * FROM submission_rows WHERE tenant_id = %s AND dedupe_hash = %s "
            "AND status != 'rejected' ORDER BY id DESC LIMIT 1",
            (tenant_id, dedupe_hash),
        ).fetchone()
        return _row_to_dict(existing) if existing else None


def create_submission(tenant_id: int, source: str, rows: list[dict],
                      submitted_by: str = "hr") -> dict:
    """
    rows: list of {employee_name, ctc, input: {...raw row input...},
    computed: {...full _build_optimize_response() output...}}. Each row is
    checked for a duplicate before insert; duplicates are skipped (not
    inserted) and reported back, not silently merged into the submission.

    Returns {"submission_id": int, "rows": [...inserted rows...],
             "duplicates": [...skipped rows, with the existing row they matched...]}.
    """
    tenant_id = _checked_tenant_id(tenant_id)
    if source not in VALID_SOURCES:
        raise ValueError(f"source must be one of {VALID_SOURCES}")

    inserted, duplicates = [], []
    with _conn(tenant_id) as conn:
        # RETURNING id replaces SQLite's cur.lastrowid, which psycopg has no
        # equivalent for.
        submission_id = conn.execute(
            "INSERT INTO submissions (tenant_id, created_at, source, submitted_by) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (tenant_id, datetime.now(timezone.utc).isoformat(), source, submitted_by),
        ).fetchone()["id"]

        for i, row in enumerate(rows):
            name = row.get("employee_name")
            ctc = row["ctc"]
            email = row.get("input", {}).get("email")
            dedupe_hash = _dedupe_hash(tenant_id, name, ctc, email)
            existing = conn.execute(
                "SELECT * FROM submission_rows WHERE tenant_id = %s AND dedupe_hash = %s "
                "AND status != 'rejected' LIMIT 1",
                (tenant_id, dedupe_hash),
            ).fetchone()
            if existing is not None:
                duplicates.append({"row_index": i, "matches_existing_row_id": existing["id"]})
                continue
            orchestration = row.get("orchestration")  # optional — omitted by fixtures/callers predating this feature
            row_id = conn.execute(
                """INSERT INTO submission_rows
                   (tenant_id, submission_id, row_index, employee_name, ctc, dedupe_hash,
                    input_json, computed_json, orchestration_json, route, severity, status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
                   RETURNING id""",
                (tenant_id, submission_id, i, name, ctc, dedupe_hash,
                 json.dumps(row["input"]), json.dumps(row["computed"]),
                 json.dumps(orchestration) if orchestration else None,
                 orchestration.get("route") if orchestration else None,
                 orchestration.get("severity") if orchestration else None),
            ).fetchone()["id"]
            inserted.append(row_id)

    return {
        "submission_id": submission_id,
        "inserted_row_ids": inserted,
        "duplicates": duplicates,
    }


def list_submissions(tenant_id: int, status: str | None = None,
                     route: str | None = None) -> list[dict]:
    tenant_id = _checked_tenant_id(tenant_id)
    with _conn(tenant_id) as conn:
        submissions = conn.execute(
            "SELECT * FROM submissions WHERE tenant_id = %s ORDER BY id DESC", (tenant_id,)
        ).fetchall()
        result = []
        for s in submissions:
            row_query = "SELECT * FROM submission_rows WHERE tenant_id = %s AND submission_id = %s"
            params = [tenant_id, s["id"]]
            if status:
                row_query += " AND status = %s"
                params.append(status)
            if route:
                row_query += " AND route = %s"
                params.append(route)
            row_query += " ORDER BY row_index"
            rows = conn.execute(row_query, params).fetchall()
            if (status or route) and not rows:
                continue  # submission has no rows matching the filter(s) — omit it, don't show an empty shell
            result.append({
                "id": s["id"],
                "created_at": s["created_at"],
                "source": s["source"],
                "submitted_by": s["submitted_by"],
                "rows": [_row_to_dict(r) for r in rows],
            })
        return result


def get_submission(tenant_id: int, submission_id: int) -> dict | None:
    tenant_id = _checked_tenant_id(tenant_id)
    with _conn(tenant_id) as conn:
        s = conn.execute(
            "SELECT * FROM submissions WHERE tenant_id = %s AND id = %s",
            (tenant_id, submission_id),
        ).fetchone()
        if s is None:
            return None
        rows = conn.execute(
            "SELECT * FROM submission_rows WHERE tenant_id = %s AND submission_id = %s "
            "ORDER BY row_index",
            (tenant_id, submission_id),
        ).fetchall()
        return {
            "id": s["id"], "created_at": s["created_at"], "source": s["source"],
            "submitted_by": s["submitted_by"], "rows": [_row_to_dict(r) for r in rows],
        }


def decide_row(tenant_id: int, submission_id: int, row_index: int, decision: str,
               reason: str | None, decided_by: str = "finance") -> dict:
    """
    Approve or reject exactly one row. Idempotent by construction: the
    UPDATE only matches rows still 'pending', using the database's own
    atomicity rather than a separate idempotency-key mechanism — a
    double-click that fires this twice finds zero matching rows on the second
    call and returns already_decided=True instead of writing a second audit
    entry. (cur.rowcount means the same thing in psycopg as it did in
    sqlite3 for an UPDATE, so this survived the port unchanged.)
    """
    tenant_id = _checked_tenant_id(tenant_id)
    if decision not in ("approve", "reject"):
        raise ValueError("decision must be 'approve' or 'reject'")
    if decision == "reject" and not reason:
        raise ValueError("a rejection requires a reason")

    new_status = "approved" if decision == "approve" else "rejected"
    with _conn(tenant_id) as conn:
        cur = conn.execute(
            """UPDATE submission_rows
               SET status = %s, reason = %s, decided_at = %s, decided_by = %s
               WHERE tenant_id = %s AND submission_id = %s AND row_index = %s
                 AND status = 'pending'""",
            (new_status, reason, datetime.now(timezone.utc).isoformat(), decided_by,
             tenant_id, submission_id, row_index),
        )
        if cur.rowcount == 0:
            existing = conn.execute(
                "SELECT status FROM submission_rows "
                "WHERE tenant_id = %s AND submission_id = %s AND row_index = %s",
                (tenant_id, submission_id, row_index),
            ).fetchone()
            return {
                "already_decided": True,
                "current_status": existing["status"] if existing else None,
            }
        row = conn.execute(
            "SELECT * FROM submission_rows "
            "WHERE tenant_id = %s AND submission_id = %s AND row_index = %s",
            (tenant_id, submission_id, row_index),
        ).fetchone()
        return {"already_decided": False, "row": _row_to_dict(row)}


def mark_exported(tenant_id: int, submission_id: int, row_index: int) -> None:
    """
    Records that /rows/<i>/export has actually generated output for this
    row at least once, so the frontend can tell "never exported yet" from
    "already have this" on a fresh page load instead of re-showing the
    same first-time export button forever. Unconditional UPDATE, not
    gated on current status — export re-runs are allowed (re-downloading
    a file you already have is normal), so this just records the latest
    timestamp, overwriting any prior one rather than refusing a second
    write.
    """
    tenant_id = _checked_tenant_id(tenant_id)
    with _conn(tenant_id) as conn:
        conn.execute(
            "UPDATE submission_rows SET exported_at = %s "
            "WHERE tenant_id = %s AND submission_id = %s AND row_index = %s",
            (datetime.now(timezone.utc).isoformat(), tenant_id, submission_id, row_index),
        )


def mark_dispatched(tenant_id: int, submission_id: int, row_index: int) -> None:
    """
    Records that Finance clicked through this row's final confirmation —
    "Simulate upload to RazorpayX Payroll," "Simulate dispatch," or
    "Acknowledge — nothing to export yet." Previously this was tracked only
    in FinanceFlow's own completedKeys useState, which reset on every page
    load — a real bug, not the documented tradeoff its own comment claimed
    ("consistent with every other 'simulated' state in this app"): unlike
    a real RazorpayX call (which genuinely doesn't happen and shouldn't be
    faked), this is just remembering a click Finance already made, the same
    class of gap exported_at already fixed for the export step. Same
    unconditional-UPDATE shape as mark_exported() — re-confirming isn't an
    error, it just refreshes the timestamp.
    """
    tenant_id = _checked_tenant_id(tenant_id)
    with _conn(tenant_id) as conn:
        conn.execute(
            "UPDATE submission_rows SET dispatched_at = %s "
            "WHERE tenant_id = %s AND submission_id = %s AND row_index = %s",
            (datetime.now(timezone.utc).isoformat(), tenant_id, submission_id, row_index),
        )
