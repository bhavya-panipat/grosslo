"""
review_queue.py — maker-checker persistence for the HR-submits /
Finance-reviews workflow.

SCOPE, stated plainly (mirrors the discipline everywhere else in this repo):
- Postgres, via psycopg. Ported from SQLite in Roadmap Phase 1.1 step 1
  (MULTI_TENANT_DESIGN.md section 7) — SQLite has no row-level security and no
  per-connection session variables to key a defence-in-depth policy on, both of
  which step 3 needs. This module is STILL single-tenant: there is no tenant_id
  column here yet, deliberately. Step 1 proves the database migration works in
  isolation from the tenancy change, so a bug afterwards is attributable to one
  or the other rather than both at once. Do not add tenant_id here ahead of
  step 2.
- No real authentication anywhere in this module. "HR" and "Finance" are
  role labels a caller asserts, not identities this module verifies. See
  app.py's /hr and /finance routes for how that's surfaced (or not) in the
  UI — this module just records whatever role string it's given.
- Zero new tax/compliance logic. Every row this module stores is the
  already-computed output of _build_optimize_response() (app.py) or the
  batch-audit pipeline — this module's only job is persisting it, deciding
  on it, and reading it back. If a function here starts computing a tax
  figure, that's a scope violation, not a feature.

RUNNING THIS REQUIRES A REACHABLE POSTGRES. `brew services start postgresql@16`.
Because app.py calls init_db() at import time, a stopped server fails the test
suite at *collection*, as a wall of connection errors — that is a missing
service, not a bug in whatever you just changed.

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

# Local dev default targets the Homebrew postgresql@16 cluster over the unix
# socket as the current OS user. DATABASE_URL overrides it (.env), which is how
# a managed provider would be pointed at — MULTI_TENANT_DESIGN.md section 6
# leaves the hosting choice open on purpose.
DEFAULT_DSN = "postgresql:///grosslo"

# Replaces the old module-level DB_PATH. Tests swapped that file path to get an
# isolated database per test module; Postgres has no file to swap, so the same
# isolation property is provided by giving each test module its own *schema*
# inside one database. Production/dev leaves this at "public".
DB_SCHEMA = "public"

VALID_STATUSES = {"pending", "approved", "rejected"}
VALID_SOURCES = {"single", "batch"}


class SchemaMissingError(RuntimeError):
    """
    Raised when a query is attempted against a DB_SCHEMA whose tables aren't
    there. Named specifically, rather than surfacing as a bare
    psycopg.errors.UndefinedTable or a generic 500, so this is unmistakable in
    a log instead of blending into every other database error. See
    _require_schema() for why this is not repaired automatically.
    """


def _dsn() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DSN)


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
# When email IS supplied, two candidates with the same name+CTC now hash
# differently as long as their emails differ, while a same-candidate
# same-day revised offer (same email) still collides as intended. When
# email is absent, the key is deliberately built with the exact old
# name+ctc+window shape (no empty email segment) — not just a lower bar,
# but bit-for-bit the previous formula — so dedupe_hash values already
# stored for existing emailless rows keep matching fresh lookups instead
# of silently stopping mid-flight.
#
# NOTE for step 2/3: this key is global across tenants today. Section 4 of
# MULTI_TENANT_DESIGN.md requires tenant_id folded in here, not just added to
# the table — two companies hiring two different people of the same name at the
# same CTC on the same day would otherwise false-collide. Not done in step 1.
def _dedupe_hash(employee_name: str | None, ctc: float, email: str | None = None) -> str:
    window = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    normalized_name = (employee_name or "anon").strip().lower()
    normalized_email = (email or "").strip().lower()
    if normalized_email:
        key = f"{normalized_name}|{normalized_email}|{round(ctc)}|{window}"
    else:
        key = f"{normalized_name}|{round(ctc)}|{window}"
    return hashlib.sha256(key.encode()).hexdigest()


def _ensure_schema(conn: psycopg.Connection) -> None:
    """
    Creates the schema, tables and indexes. Called ONLY from init_db() —
    explicit startup and migration — never from _conn().

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
    # SET LOCAL, not SET: transaction-scoped, discarded at COMMIT/ROLLBACK.
    # Nothing is pooled yet (a fresh connection per _conn()), so plain SET
    # would also work today — but MULTI_TENANT_DESIGN.md 3.1 makes
    # transaction-scoped the hard rule for connection state once pooling
    # arrives in step 3, and there is no reason to establish the other habit
    # here first and have to find every instance of it later.
    conn.execute(sql.SQL("SET LOCAL search_path TO {}").format(schema))

    conn.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            created_at TEXT NOT NULL,
            source TEXT NOT NULL,
            submitted_by TEXT NOT NULL DEFAULT 'hr'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS submission_rows (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
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

    conn.execute("CREATE INDEX IF NOT EXISTS idx_rows_submission ON submission_rows(submission_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rows_dedupe ON submission_rows(dedupe_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rows_route ON submission_rows(route)")


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
    schema = sql.Identifier(DB_SCHEMA)
    # SET LOCAL, not SET: transaction-scoped, discarded at COMMIT/ROLLBACK.
    # Nothing is pooled yet (a fresh connection per _conn()), so plain SET
    # would also work today — but MULTI_TENANT_DESIGN.md 3.1 makes
    # transaction-scoped the hard rule for connection state once pooling
    # arrives in step 3, and there is no reason to establish the other habit
    # here first and have to find every instance of it later.
    conn.execute(sql.SQL("SET LOCAL search_path TO {}").format(schema))
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
def _conn():
    conn = psycopg.connect(_dsn(), row_factory=dict_row)
    try:
        _require_schema(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """
    Creates the schema if it isn't there. This is now the ONLY place that
    happens — _conn() verifies and raises SchemaMissingError instead of
    creating, so this call is required at startup rather than being the
    convenience it was under SQLite. app.py calls it at import time.
    """
    conn = psycopg.connect(_dsn(), row_factory=dict_row)
    try:
        _ensure_schema(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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
    with psycopg.connect(_dsn()) as conn:
        conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(target)))
        conn.commit()


def _row_to_dict(row: dict) -> dict:
    d = dict(row)
    d["input"] = json.loads(d.pop("input_json"))
    d["computed"] = json.loads(d.pop("computed_json"))
    # None for rows created before this feature shipped — callers (the
    # frontend, tests) must handle this, not assume every row has one.
    raw_orchestration = d.pop("orchestration_json", None)
    d["orchestration"] = json.loads(raw_orchestration) if raw_orchestration else None
    return d


def check_duplicate(employee_name: str | None, ctc: float, email: str | None = None) -> dict | None:
    """
    Returns the existing pending/approved row this would duplicate, or
    None. Callers decide what to do with a duplicate (block, per the
    brief's "flag or block, don't silently reprocess") — this function
    only detects.
    """
    dedupe_hash = _dedupe_hash(employee_name, ctc, email)
    with _conn() as conn:
        existing = conn.execute(
            "SELECT * FROM submission_rows WHERE dedupe_hash = %s AND status != 'rejected' ORDER BY id DESC LIMIT 1",
            (dedupe_hash,),
        ).fetchone()
        return _row_to_dict(existing) if existing else None


def create_submission(source: str, rows: list[dict], submitted_by: str = "hr") -> dict:
    """
    rows: list of {employee_name, ctc, input: {...raw row input...},
    computed: {...full _build_optimize_response() output...}}. Each row is
    checked for a duplicate before insert; duplicates are skipped (not
    inserted) and reported back, not silently merged into the submission.

    Returns {"submission_id": int, "rows": [...inserted rows...],
             "duplicates": [...skipped rows, with the existing row they matched...]}.
    """
    if source not in VALID_SOURCES:
        raise ValueError(f"source must be one of {VALID_SOURCES}")

    inserted, duplicates = [], []
    with _conn() as conn:
        # RETURNING id replaces SQLite's cur.lastrowid, which psycopg has no
        # equivalent for.
        submission_id = conn.execute(
            "INSERT INTO submissions (created_at, source, submitted_by) VALUES (%s, %s, %s) RETURNING id",
            (datetime.now(timezone.utc).isoformat(), source, submitted_by),
        ).fetchone()["id"]

        for i, row in enumerate(rows):
            name = row.get("employee_name")
            ctc = row["ctc"]
            email = row.get("input", {}).get("email")
            dedupe_hash = _dedupe_hash(name, ctc, email)
            existing = conn.execute(
                "SELECT * FROM submission_rows WHERE dedupe_hash = %s AND status != 'rejected' LIMIT 1",
                (dedupe_hash,),
            ).fetchone()
            if existing is not None:
                duplicates.append({"row_index": i, "matches_existing_row_id": existing["id"]})
                continue
            orchestration = row.get("orchestration")  # optional — omitted by fixtures/callers predating this feature
            row_id = conn.execute(
                """INSERT INTO submission_rows
                   (submission_id, row_index, employee_name, ctc, dedupe_hash, input_json, computed_json,
                    orchestration_json, route, severity, status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
                   RETURNING id""",
                (submission_id, i, name, ctc, dedupe_hash,
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


def list_submissions(status: str | None = None, route: str | None = None) -> list[dict]:
    with _conn() as conn:
        submissions = conn.execute("SELECT * FROM submissions ORDER BY id DESC").fetchall()
        result = []
        for s in submissions:
            row_query = "SELECT * FROM submission_rows WHERE submission_id = %s"
            params = [s["id"]]
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


def get_submission(submission_id: int) -> dict | None:
    with _conn() as conn:
        s = conn.execute("SELECT * FROM submissions WHERE id = %s", (submission_id,)).fetchone()
        if s is None:
            return None
        rows = conn.execute(
            "SELECT * FROM submission_rows WHERE submission_id = %s ORDER BY row_index", (submission_id,)
        ).fetchall()
        return {
            "id": s["id"], "created_at": s["created_at"], "source": s["source"],
            "submitted_by": s["submitted_by"], "rows": [_row_to_dict(r) for r in rows],
        }


def decide_row(submission_id: int, row_index: int, decision: str, reason: str | None,
                decided_by: str = "finance") -> dict:
    """
    Approve or reject exactly one row. Idempotent by construction: the
    UPDATE only matches rows still 'pending', using the database's own
    atomicity rather than a separate idempotency-key mechanism — a
    double-click that fires this twice finds zero matching rows on the second
    call and returns already_decided=True instead of writing a second audit
    entry. (cur.rowcount means the same thing in psycopg as it did in
    sqlite3 for an UPDATE, so this survived the port unchanged.)
    """
    if decision not in ("approve", "reject"):
        raise ValueError("decision must be 'approve' or 'reject'")
    if decision == "reject" and not reason:
        raise ValueError("a rejection requires a reason")

    new_status = "approved" if decision == "approve" else "rejected"
    with _conn() as conn:
        cur = conn.execute(
            """UPDATE submission_rows
               SET status = %s, reason = %s, decided_at = %s, decided_by = %s
               WHERE submission_id = %s AND row_index = %s AND status = 'pending'""",
            (new_status, reason, datetime.now(timezone.utc).isoformat(), decided_by,
             submission_id, row_index),
        )
        if cur.rowcount == 0:
            existing = conn.execute(
                "SELECT status FROM submission_rows WHERE submission_id = %s AND row_index = %s",
                (submission_id, row_index),
            ).fetchone()
            return {
                "already_decided": True,
                "current_status": existing["status"] if existing else None,
            }
        row = conn.execute(
            "SELECT * FROM submission_rows WHERE submission_id = %s AND row_index = %s",
            (submission_id, row_index),
        ).fetchone()
        return {"already_decided": False, "row": _row_to_dict(row)}


def mark_exported(submission_id: int, row_index: int) -> None:
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
    with _conn() as conn:
        conn.execute(
            "UPDATE submission_rows SET exported_at = %s WHERE submission_id = %s AND row_index = %s",
            (datetime.now(timezone.utc).isoformat(), submission_id, row_index),
        )


def mark_dispatched(submission_id: int, row_index: int) -> None:
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
    with _conn() as conn:
        conn.execute(
            "UPDATE submission_rows SET dispatched_at = %s WHERE submission_id = %s AND row_index = %s",
            (datetime.now(timezone.utc).isoformat(), submission_id, row_index),
        )
