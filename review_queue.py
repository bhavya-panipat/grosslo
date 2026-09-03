"""
review_queue.py — maker-checker persistence for the HR-submits /
Finance-reviews workflow.

SCOPE, stated plainly (mirrors the discipline everywhere else in this repo):
- SQLite, not a production database. A single file (`review_queue.db`,
  gitignored), created on first use. This is demo-scale persistence for a
  submission to survive between HR's screen and Finance's screen — not a
  multi-tenant company roster, and not the "real database" the README's
  roadmap describes for a steady-state treasury baseline. That's a
  separate, much larger piece of work and this doesn't pretend to be it.
- No real authentication anywhere in this module. "HR" and "Finance" are
  role labels a caller asserts, not identities this module verifies. See
  app.py's /hr and /finance routes for how that's surfaced (or not) in the
  UI — this module just records whatever role string it's given.
- Zero new tax/compliance logic. Every row this module stores is the
  already-computed output of _build_optimize_response() (app.py) or the
  batch-audit pipeline — this module's only job is persisting it, deciding
  on it, and reading it back. If a function here starts computing a tax
  figure, that's a scope violation, not a feature.

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
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = "review_queue.db"

VALID_STATUSES = {"pending", "approved", "rejected"}
VALID_SOURCES = {"single", "batch"}

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
def _dedupe_hash(employee_name: str | None, ctc: float, email: str | None = None) -> str:
    window = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    normalized_name = (employee_name or "anon").strip().lower()
    normalized_email = (email or "").strip().lower()
    if normalized_email:
        key = f"{normalized_name}|{normalized_email}|{round(ctc)}|{window}"
    else:
        key = f"{normalized_name}|{round(ctc)}|{window}"
    return hashlib.sha256(key.encode()).hexdigest()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """
    CREATE TABLE IF NOT EXISTS is cheap and idempotent — called on every
    connection, not just once at app startup. Found the hard way: an
    earlier version only ran this from init_db() at import time, so
    deleting DB_PATH out from under a still-running server (a cleanup
    command run without restarting the process) left every subsequent
    request hitting "no such table" — sqlite3.connect() happily creates a
    new, empty, table-less file for a missing path, it doesn't recreate
    the schema. Self-healing on every connection means a missing or
    externally-deleted db file is never a hard crash, here or in whatever
    happens to this file after this submission.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            source TEXT NOT NULL,
            submitted_by TEXT NOT NULL DEFAULT 'hr'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS submission_rows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER NOT NULL REFERENCES submissions(id),
            row_index INTEGER NOT NULL,
            employee_name TEXT,
            ctc REAL NOT NULL,
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
    # before this feature shipped, so this self-heals the same way the rest
    # of this function already does. Verified against a copy of this
    # project's real (non-empty) review_queue.db before shipping: existing
    # rows survive unchanged, new columns come back NULL, and running this
    # twice on an already-migrated table is a no-op, not an error.
    existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(submission_rows)")}
    for col, ddl in [
        ("orchestration_json", "ALTER TABLE submission_rows ADD COLUMN orchestration_json TEXT"),
        ("route", "ALTER TABLE submission_rows ADD COLUMN route TEXT"),
        ("severity", "ALTER TABLE submission_rows ADD COLUMN severity TEXT"),
        ("exported_at", "ALTER TABLE submission_rows ADD COLUMN exported_at TEXT"),
    ]:
        if col not in existing_cols:
            conn.execute(ddl)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_rows_submission ON submission_rows(submission_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rows_dedupe ON submission_rows(dedupe_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rows_route ON submission_rows(route)")


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _ensure_schema(conn)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """
    Kept as an explicit, named call for app.py's startup and for tests
    that want the schema to exist before doing anything else — but every
    _conn() now ensures the schema itself too, so this is a convenience,
    not the only place it happens.
    """
    with _conn():
        pass


def _row_to_dict(row: sqlite3.Row) -> dict:
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
            "SELECT * FROM submission_rows WHERE dedupe_hash = ? AND status != 'rejected' ORDER BY id DESC LIMIT 1",
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
        cur = conn.execute(
            "INSERT INTO submissions (created_at, source, submitted_by) VALUES (?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), source, submitted_by),
        )
        submission_id = cur.lastrowid

        for i, row in enumerate(rows):
            name = row.get("employee_name")
            ctc = row["ctc"]
            email = row.get("input", {}).get("email")
            dedupe_hash = _dedupe_hash(name, ctc, email)
            existing = conn.execute(
                "SELECT * FROM submission_rows WHERE dedupe_hash = ? AND status != 'rejected' LIMIT 1",
                (dedupe_hash,),
            ).fetchone()
            if existing is not None:
                duplicates.append({"row_index": i, "matches_existing_row_id": existing["id"]})
                continue
            orchestration = row.get("orchestration")  # optional — omitted by fixtures/callers predating this feature
            row_cur = conn.execute(
                """INSERT INTO submission_rows
                   (submission_id, row_index, employee_name, ctc, dedupe_hash, input_json, computed_json,
                    orchestration_json, route, severity, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
                (submission_id, i, name, ctc, dedupe_hash,
                 json.dumps(row["input"]), json.dumps(row["computed"]),
                 json.dumps(orchestration) if orchestration else None,
                 orchestration.get("route") if orchestration else None,
                 orchestration.get("severity") if orchestration else None),
            )
            inserted.append(row_cur.lastrowid)

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
            row_query = "SELECT * FROM submission_rows WHERE submission_id = ?"
            params = [s["id"]]
            if status:
                row_query += " AND status = ?"
                params.append(status)
            if route:
                row_query += " AND route = ?"
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
        s = conn.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,)).fetchone()
        if s is None:
            return None
        rows = conn.execute(
            "SELECT * FROM submission_rows WHERE submission_id = ? ORDER BY row_index", (submission_id,)
        ).fetchall()
        return {
            "id": s["id"], "created_at": s["created_at"], "source": s["source"],
            "submitted_by": s["submitted_by"], "rows": [_row_to_dict(r) for r in rows],
        }


def decide_row(submission_id: int, row_index: int, decision: str, reason: str | None,
                decided_by: str = "finance") -> dict:
    """
    Approve or reject exactly one row. Idempotent by construction: the
    UPDATE only matches rows still 'pending', using SQLite's own atomicity
    rather than a separate idempotency-key mechanism — a double-click that
    fires this twice finds zero matching rows on the second call and
    returns already_decided=True instead of writing a second audit entry.
    """
    if decision not in ("approve", "reject"):
        raise ValueError("decision must be 'approve' or 'reject'")
    if decision == "reject" and not reason:
        raise ValueError("a rejection requires a reason")

    new_status = "approved" if decision == "approve" else "rejected"
    with _conn() as conn:
        cur = conn.execute(
            """UPDATE submission_rows
               SET status = ?, reason = ?, decided_at = ?, decided_by = ?
               WHERE submission_id = ? AND row_index = ? AND status = 'pending'""",
            (new_status, reason, datetime.now(timezone.utc).isoformat(), decided_by,
             submission_id, row_index),
        )
        if cur.rowcount == 0:
            existing = conn.execute(
                "SELECT status FROM submission_rows WHERE submission_id = ? AND row_index = ?",
                (submission_id, row_index),
            ).fetchone()
            return {
                "already_decided": True,
                "current_status": existing["status"] if existing else None,
            }
        row = conn.execute(
            "SELECT * FROM submission_rows WHERE submission_id = ? AND row_index = ?",
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
            "UPDATE submission_rows SET exported_at = ? WHERE submission_id = ? AND row_index = ?",
            (datetime.now(timezone.utc).isoformat(), submission_id, row_index),
        )
