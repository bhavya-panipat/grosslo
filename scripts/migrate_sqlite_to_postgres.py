"""
One-off migration for MULTI_TENANT_DESIGN.md section 7 step 1: copy the two
existing tables out of the old SQLite review_queue.db into Postgres, verbatim.

Verbatim means verbatim: no tenant_id (that is step 2), no type "improvements",
no re-serialising of the JSON blobs. Row ids are preserved explicitly so the
submission_rows -> submissions foreign key still points where it did, and the
identity sequences are then advanced past the highest id so the next INSERT
from the application doesn't collide with a migrated row.

Idempotent enough to re-run during development: it refuses to write into
non-empty destination tables rather than silently duplicating rows.

Usage:
    python3 scripts/migrate_sqlite_to_postgres.py [--sqlite review_queue.db]
                                                  [--schema public] [--force]
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

import review_queue

SUBMISSION_COLS = ["id", "created_at", "source", "submitted_by"]
ROW_COLS = [
    "id", "submission_id", "row_index", "employee_name", "ctc", "dedupe_hash",
    "input_json", "computed_json", "status", "reason", "decided_at", "decided_by",
    "orchestration_json", "route", "severity", "exported_at", "dispatched_at",
]


def _copy(pg, table: str, cols: list[str], rows: list[sqlite3.Row]) -> int:
    if not rows:
        return 0
    stmt = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
        sql.Identifier(table),
        sql.SQL(", ").join(sql.Identifier(c) for c in cols),
        sql.SQL(", ").join(sql.Placeholder() * len(cols)),
    )
    for r in rows:
        pg.execute(stmt, tuple(r[c] for c in cols))
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", default="review_queue.db")
    ap.add_argument("--schema", default="public")
    ap.add_argument("--force", action="store_true",
                    help="truncate the destination tables first instead of refusing to write into non-empty ones")
    args = ap.parse_args()

    if not os.path.exists(args.sqlite):
        print(f"error: {args.sqlite} not found", file=sys.stderr)
        return 1

    review_queue.DB_SCHEMA = args.schema
    review_queue.init_db()  # creates the destination schema/tables if absent

    lite = sqlite3.connect(f"file:{args.sqlite}?mode=ro", uri=True)
    lite.row_factory = sqlite3.Row
    submissions = lite.execute("SELECT * FROM submissions ORDER BY id").fetchall()
    rows = lite.execute("SELECT * FROM submission_rows ORDER BY id").fetchall()
    print(f"source {args.sqlite}: {len(submissions)} submissions, {len(rows)} submission_rows")

    with psycopg.connect(review_queue._dsn(), row_factory=dict_row) as pg:
        pg.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(args.schema)))

        existing = {
            t: pg.execute(sql.SQL("SELECT COUNT(*) AS n FROM {}").format(sql.Identifier(t))).fetchone()["n"]
            for t in ("submissions", "submission_rows")
        }
        if any(existing.values()):
            if not args.force:
                print(f"error: destination not empty ({existing}); re-run with --force to truncate first",
                      file=sys.stderr)
                return 1
            pg.execute("TRUNCATE submission_rows, submissions RESTART IDENTITY")
            print(f"--force: truncated destination (was {existing})")

        n_sub = _copy(pg, "submissions", SUBMISSION_COLS, submissions)
        n_row = _copy(pg, "submission_rows", ROW_COLS, rows)

        # Explicit ids above bypass the identity sequences, which would
        # otherwise still be at 1 and collide on the next application INSERT.
        for table in ("submissions", "submission_rows"):
            pg.execute(
                "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
                "COALESCE((SELECT MAX(id) FROM " + table + "), 0) + 1, false)",
                (f"{args.schema}.{table}",),
            )
        pg.commit()

    print(f"copied: {n_sub} submissions, {n_row} submission_rows -> postgres schema '{args.schema}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
