# Multi-tenant architecture — design for Roadmap Phase 1.1

Scope: **only** "two companies can use grosslo simultaneously with zero
data leakage" (the Phase 1 exit criterion). Real per-user accounts, SSO,
and RBAC are 1.2 — deliberately out of scope here except for the one
seam 1.2 needs from this doc (see "What 1.1 hands to 1.2" below). Building
identity now would mean re-deriving the tenant boundary a second time
once real accounts exist; building tenancy now gives 1.2 a boundary to
scope roles inside of, which is the dependency the roadmap states.

## 1. Current state — grounded in what the code actually does today

Every one of these is a genuine single-tenant assumption, not a
simplification with a tenant concept nearby to extend:

- **Persistence is one global SQLite file.** `review_queue.py:38`:
  `DB_PATH = "review_queue.db"` — one file, no company column anywhere
  in `submissions` or `submission_rows` (`review_queue.py:91-113`). Every
  HR submission and every Finance decision from every user, ever, lands
  in the same two tables.
- **Auth is two shared secrets, not accounts.** `auth.py:22-24`: `ROLES =
  ("hr", "finance")`, one password per role, sourced from `.env` or a
  hardcoded fallback (`_DEFAULT_CODES`). The session
  (`app.py:1065`) stores exactly `{"role": "hr" | "finance"}` — no user
  id, no company id, nothing to scope a query by even if we wanted to.
- **RazorpayX credentials are one process-wide key pair.**
  `razorpayx_client.py:67-68`: `os.environ.get("RAZORPAYX_KEY_ID")` /
  `RAZORPAYX_KEY_SECRET`. One bank account for the entire running
  process — every company would be paying out of (or reading the
  balance of) the same RazorpayX account.
- **The audit log is one global file.** `app.py:60`: `AUDIT_LOG_PATH =
  "audit_log.jsonl"`. Every event from every company interleaved in one
  append-only file, no partition key.
- **The Flask session-signing key is process-wide** (`app.py:43-52`) —
  this one is fine to stay global; it signs cookies, it doesn't scope
  data, so it's not part of the isolation problem below.

Net: there is currently no code path anywhere that could even express
"give me only Company A's rows" — not a filter that's missing a
`WHERE` clause, but a schema that has nothing to filter on.

## 2. The isolation guarantee this design has to produce

Restating the roadmap's own exit criterion precisely, because "multi-
tenant" is vague until it's a testable claim: **for any two tenants A
and B, every read and write in the system — HTTP API, background job,
export payload, audit log query — is scoped to exactly one tenant's
data, and there is no code path (not just no *current* path — no
possible path given the schema and query layer) that can return or
mutate a row belonging to a tenant other than the one the request is
authenticated for.**

That last clause is the one that rules out the cheapest possible
approach (see 3.1 below).

## 3. Design decisions

Each decision below is stated with its real alternative and why the
other one loses — per this project's own standard of not silently
picking an option a reviewer would ask about.

### 3.1 Isolation mechanism: tenant_id column + enforced query layer,
not per-tenant database files

**Rejected alternative: one SQLite file per tenant** (`review_queue_
{tenant_id}.db`). Attractive because it makes cross-tenant leakage
*structurally* impossible — there's no shared table to leak from. But
it fails on three things this product will need almost immediately: (a)
`list_submissions()`-style cross-tenant admin/ops queries (support
debugging, this repo's own future usage-metering work in Phase 4)
become "open N files and merge," not a query; (b) migrations become "run
this ALTER on every tenant's file," with no transactional guarantee
across them; (c) it doesn't extend to the RazorpayX-balance/audit-log
surfaces at all, so it would only solve a third of the problem and the
other two-thirds would need a different mechanism anyway — two isolation
strategies in one system is a bigger long-term risk than one, done
right, everywhere.

**Chosen: single database (Postgres, not SQLite — see 3.2), every
tenant-owned table gets a `tenant_id` column, and every query goes
through a layer that makes `tenant_id` mandatory, not optional.**
Concretely: no function in the persistence layer accepts a *filter* that
happens to include tenant_id — every function accepts tenant_id as a
required positional argument and adds `WHERE tenant_id = ?` unconditionally,
not as one clause among several a future call site could omit. If the
underlying database is Postgres (chosen in 3.2), enforce this a second,
independent way with row-level security policies — belt-and-suspenders
specifically because "a reviewer forgot the WHERE clause in a new
function" is exactly the class of bug this whole document exists to
prevent, and a single enforcement layer (application code only) has
already been the source of a similar-shaped bug once this session (the
Finance bulk-decide count that silently dropped rows) — that was a
counting bug, not a leak, but it's the same failure mode: an invariant
that held everywhere it was checked, until a new code path didn't check
it.

**RLS variable scope is `SET LOCAL`, transaction-scoped, never
session-scoped `SET` on the connection — this is not a stylistic
choice.** With connection pooling (PgBouncer, or any pool the app uses
at real scale — and it will), a connection is reused across unrelated
requests. A session-scoped `SET app.tenant_id = ...` persists on that
physical connection until explicitly changed, so a pooled connection
that isn't perfectly reset between checkouts can carry request A's
tenant context into request B — a documented, real category of RLS
production bugs, not a hypothetical one. Worse than a crash: request B
gets a 200 with request A's tenant's data, nothing errors, nothing logs
a failure. `SET LOCAL app.tenant_id = ...` is scoped to the current
transaction only and is automatically discarded at `COMMIT` or
`ROLLBACK` regardless of what the pool does with the connection
afterward — so the persistence layer's contract is: **every query runs
inside a transaction that opens with `SET LOCAL app.tenant_id`, no
query ever runs on a connection outside that transaction boundary.**
This is a hard requirement on the query-layer wrapper (3.1's "every
function accepts tenant_id as a required argument"), not an
implementation detail left to whoever writes the pool config later.

**Missing tenant_id fails closed, the same way `auth.py`'s
`require_role` already does — stated with the same explicitness, not
left implicit.** `require_role()` (`auth.py:43-56`) already 401s if
`session.get("role")` isn't one of the allowed roles; a `require_tenant`
decorator with the identical shape wraps every tenant-scoped route and
401s immediately if `session.get("tenant_id")` is `None` — before any
query runs, before `SET LOCAL` is even attempted. No route computes a
default tenant, no route treats a missing tenant_id as "act on nothing"
and return an empty list (which reads to a caller as "you have zero
rows," a materially different and worse failure than "you're not
authorized"). A stale session, a bug in the login flow, or a request
that skips login entirely all hit the same hard failure, matching this
project's existing precedent of failing closed on an unexpected null —
`classify_row()`'s `None` route defaulting to `needs_review` rather than
auto-pass is the same discipline applied here.

### 3.2 Database: migrate off SQLite to Postgres as part of 1.1, not
after

SQLite has no row-level security, no per-connection session variables to
key a defense-in-depth policy on (3.1's second enforcement layer), and
`review_queue.py`'s own docstring already says plainly it "is demo-scale
persistence... not a multi-tenant company roster." Deferring this
migration to a later phase means building the tenant_id-column layer
twice — once naively on SQLite, again properly on Postgres — for no
benefit, since 1.1 is exactly the phase that's supposed to replace this
assumption. This also folds in (subsumes, doesn't duplicate) part of the
original roadmap's audit-infrastructure gap (2.2.6 / "queryable
storage") for the submissions/rows tables specifically — the audit
*log* (JSONL) is a separate concern, addressed in 3.4 below, and its
production-grade version (retention policy, tamper-evidence) is still
correctly scoped to Phase 2.6, not pulled forward.

### 3.3 Tenant resolution: subdomain, with session carrying tenant_id
once resolved — not a request body field

**Rejected: trusting a `tenant_id` or `company` field in the request
body/JSON.** That's a client-supplied value with zero verification —
any authenticated session could pass a different tenant's id and read
its data; this is the exact "no code path can return another tenant's
row" guarantee failing at the very first hop, not a hardening gap found
later.

**Chosen: `{tenant-slug}.grosslo.app` subdomain resolves to a tenant at
the reverse-proxy/routing layer, and the Flask session — once a role
login succeeds against that tenant's codes — carries `tenant_id`
alongside `role`:** `{"role": "hr", "tenant_id": 42}`. Every
request handler reads tenant_id from `session`, never from the request
payload. This is deliberately compatible with 1.2's eventual real-account
session shape (`{"user_id": ..., "tenant_id": ..., "roles": [...]}`) —
1.1 only needs to get `tenant_id` into the session correctly; 1.2 replaces
`role` with real per-user role data without touching how tenant_id got
there.

**Interim step for 1.1 specifically, before 1.2 exists:** since 1.1
deliberately does NOT build real per-user accounts, tenant login for 1.1
is "shared HR/Finance codes, now scoped per-tenant" — i.e.
`auth.py`'s `_DEFAULT_CODES`/`_ENV_VARS` become per-tenant configuration
(a `tenant_settings` table row per tenant holding its own HR/Finance
codes) instead of one global pair. This is intentionally the same
shared-secret model as today, not an upgrade to real accounts — that
upgrade is 1.2's job, not 1.1's. Flagging this explicitly so it isn't
mistaken for 1.1 secretly doing half of 1.2's work.

**One genuine improvement beyond pure tenant-scoping, called out
explicitly rather than folded in silently:** section 4's schema stores
`hr_access_code_hash`/`finance_access_code_hash`, not the plaintext
codes `auth.py`'s `_DEFAULT_CODES` currently compares against directly.
That's a real security improvement (a DB read no longer discloses the
login code outright) beyond what "add a tenant_id column" requires — it
would have been possible to keep storing plaintext per-tenant codes and
still satisfy the tenancy scope. Naming it here on purpose, per this
document's own standard applied to itself: this repo's numeric-guard
work treats an unstated scope expansion as a defect class, and a
document about isolation guarantees doesn't get an exemption from its
own standard just because the addition happens to be good.

### 3.4 Audit log: tenant_id field in every JSONL line, not per-tenant
files

Matches 3.1's reasoning, scaled down: one file with a mandatory
`tenant_id` field per event, and `_append_audit_log()` (`app.py:63`)
takes tenant_id as a required argument, not an optional one — same
"required, not filtered" principle as the database layer, applied
consistently rather than inventing a second pattern for this one file.
`/api/audit-log` (`app.py:1027`) must filter by the requesting session's
tenant_id before returning anything, with a test asserting a
cross-tenant read of this endpoint returns zero foreign rows — this
endpoint is a real, currently-open reason a "silent leak" bug here would
be worse than most: it's explicitly a compliance/trust surface, not
just an internal debug tool.

### 3.5 RazorpayX credentials: per-tenant, stored encrypted, not env vars

`RAZORPAYX_KEY_ID`/`RAZORPAYX_KEY_SECRET` move from process env to a
per-tenant row (in the same `tenant_settings` table as 3.3's login
codes) — this is real banking API credentials for a specific company's
real account, categorically higher-stakes than the demo-fake bank
details this project has been careful about elsewhere.
`razorpayx_client.py`'s functions take a resolved credential pair as an
argument (resolved from `tenant_id` by the caller), not read
`os.environ` internally — this also, as a side effect, makes the
existing "does the key start with `rzp_test_`" guard
(`razorpayx_client.py:77`) something that can be enforced per-tenant
independently, which matters once real tenants exist that legitimately
have `rzp_live_` keys and others still on `rzp_test_`.

**"Encrypted at rest," made precise rather than left as a goal:**
envelope encryption via a managed KMS (AWS KMS or GCP KMS, whichever
matches the eventual hosting choice in section 6) — the application
encrypts each `razorpayx_key_secret` with a per-tenant data key, and
that data key is itself encrypted by a KMS master key that never leaves
the KMS. The encrypted data key is what's stored alongside the ciphertext
in `tenant_settings`; the master key is not in this database, not in
`.env`, and not in application code — it exists only inside the KMS
service, accessed at decrypt time via an IAM role the application
process assumes. This is deliberately not `pgcrypto` with a
static key: `pgcrypto` would put the decryption key in the same
database (or the same `.env`) as the ciphertext it protects, which
defeats the point for a credential whose entire threat model is "the
database itself is compromised or over-broadly queried" — the same
class of risk 3.1's RLS is defending against. Rolling custom
application-level crypto with a hand-managed key is explicitly rejected
too, for the same reason this project already rejected an unearned
compliance claim elsewhere: "encrypted" has to name a real, auditable
mechanism, not describe an aspiration.

## 4. Concrete schema shape

```sql
CREATE TABLE tenants (
    id            SERIAL PRIMARY KEY,
    slug          TEXT UNIQUE NOT NULL,      -- subdomain
    display_name  TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE tenant_settings (
    tenant_id             INTEGER PRIMARY KEY REFERENCES tenants(id),
    hr_access_code_hash   TEXT NOT NULL,     -- interim shared-code model, see 3.3
    finance_access_code_hash TEXT NOT NULL,
    razorpayx_key_id      TEXT,              -- KMS-enveloped ciphertext, see 3.5
    razorpayx_key_secret  TEXT,              -- KMS-enveloped ciphertext, see 3.5
    razorpayx_account_number TEXT
);

-- existing tables, tenant_id added as a required column + FK, never
-- nullable even transiently — Postgres 11+ adds a NOT NULL column with a
-- constant DEFAULT as a single atomic metadata change (no table rewrite,
-- no window where existing rows read back NULL), which is exactly what
-- resolves the apparent tension between "NOT NULL from the start" and
-- "backfill existing rows into a default tenant": both happen in the
-- same statement, not as a nullable-add followed by a later constraint.
ALTER TABLE submissions      ADD COLUMN tenant_id INTEGER NOT NULL REFERENCES tenants(id) DEFAULT <default_tenant_id>;
ALTER TABLE submission_rows  ADD COLUMN tenant_id INTEGER NOT NULL REFERENCES tenants(id) DEFAULT <default_tenant_id>;
-- Drop the DEFAULT immediately after (ALTER COLUMN ... DROP DEFAULT) once
-- the backfill is confirmed — the default exists only to make this one
-- statement atomic, not as an ongoing fallback for future inserts, which
-- must always supply tenant_id explicitly (see 3.1's "required argument,
-- never optional" rule).
-- (submission_rows gets it too, not just via join to submissions — so
--  the RLS policy in 3.1 can key directly on the row without a join,
--  and so a query bug that skips the join can't accidentally cross
--  tenants either.)

CREATE INDEX idx_submissions_tenant ON submissions(tenant_id);
CREATE INDEX idx_rows_tenant ON submission_rows(tenant_id);
```

Every existing index that isn't already tenant-scoped
(`idx_rows_dedupe`, `idx_rows_route` — `review_queue.py:132-134`) gets
`tenant_id` prepended to its column list, since a global unique/lookup
index across tenants is itself a subtle leak surface (e.g. dedupe
hashing today is per-day-global; two different companies hiring two
different "Anika Verma"s at the same CTC on the same day would currently
false-collide — `_dedupe_hash()` needs `tenant_id` folded into its key,
not just the table needing the column).

## 5. What 1.1 hands to 1.2 (the seam, stated explicitly)

1.1 ships: every table tenant-scoped, `session["tenant_id"]` populated
correctly on login, RLS policies in place, RazorpayX credentials
resolved per-tenant. 1.1 explicitly does NOT ship: per-user accounts,
password reset, SSO, or a real role model beyond the existing two shared
strings — 1.2 replaces `session["role"]` (single shared string) with
real per-user role assignment, scoped to a `tenant_id` that already
exists in the session by the time 1.2 starts. 1.2 should not need to
touch the schema in section 4 at all beyond adding its own `users` /
`user_roles` tables that reference `tenants(id)` — if 1.2 turns out to
need a schema change to how tenants themselves are modeled, that's a
signal 1.1 was scoped wrong, worth flagging rather than absorbing
silently.

## 6. Open decisions needing an explicit call, not a silent default

- **Provisioning a new tenant**: self-serve signup, or admin-created
  only? Affects whether `tenants`/`tenant_settings` need a public
  creation endpoint at all in 1.1, or just a CLI/admin script for the
  pilot-customer stage this roadmap's Phase 4 exit criterion implies.
- **Existing demo data**: does the current single `review_queue.db`'s
  contents become "tenant 1" (a real migration with a default tenant
  row), or is it discarded as demo-only data not worth carrying forward?
  Determines whether the ALTER TABLE in section 4 needs a backfill step.
- **Postgres hosting**: self-managed, or a managed provider (RDS,
  Supabase, Neon)? Not this document's call — affects ops/cost (Phase 4
  territory) more than the schema/isolation design above, which is the
  same either way.

## 7. Suggested internal sequencing for 1.1 itself

1. Stand up Postgres, port the two existing tables verbatim (no
   tenant_id yet) — proves the DB migration works in isolation from the
   tenancy change, so a bug is attributable to one or the other, not both
   at once.
2. Add `tenants`/`tenant_settings`; add `tenant_id` to `submissions`/
   `submission_rows` via the atomic `ADD COLUMN ... NOT NULL DEFAULT
   <default_tenant_id>` form in section 4 (backfills existing rows into
   the default tenant and enforces NOT NULL in the same statement, per
   the open decision above), then drop the column default immediately
   after — no nullable window at any point.
3. Rewrite the persistence layer's function signatures to require
   `tenant_id`; add the RLS policies as the second enforcement layer,
   using transaction-scoped `SET LOCAL` per 3.1 — never a session-scoped
   `SET` on the pooled connection; add the `require_tenant` fail-closed
   decorator from 3.1 to every tenant-scoped route.
4. Move RazorpayX credentials off env vars into `tenant_settings`,
   resolved per-request.
5. Update session creation (`/api/auth/login`) to resolve and store
   `tenant_id`; update every route to read it from `session`, never from
   the request body.
6. Test plan (non-negotiable, mirrors this project's existing
   verification discipline) — two separate tests, because they prove two
   separate claims:
   - **Application-layer test:** create two tenants with overlapping/
     identical data (same employee name, same CTC, same day — the exact
     case `_dedupe_hash()` needs tenant-scoping for), and assert every
     read/write endpoint returns/mutates only the requesting tenant's
     rows. Also assert a request with no `tenant_id` in session (stale
     cookie, simulated login-flow bug) gets a hard 401 from
     `require_tenant`, never an empty result.
   - **RLS-as-independent-layer test, separate from the above:** connect
     directly with the tenant DB role (bypassing the application's query
     wrapper entirely — no `WHERE tenant_id` in the query at all,
     deliberately simulating "a reviewer forgot the clause") and assert
     the database itself still returns zero cross-tenant rows. Section
     3.1's "belt and suspenders" claim is only proven once this test
     exists — the application-layer test above exercises the correctly-
     written path and would still pass even if RLS were silently
     misconfigured or missing, so it cannot stand in for this one.
