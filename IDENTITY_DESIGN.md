# Identity and RBAC — design for Roadmap Phase 1.2

Scope: **real per-user accounts, and role enforcement based on permissions
rather than a shared string.** SSO is deliberately 1.3 — see 3.2. This is the
second half of the roadmap's Phase 1 ("real multi-tenant architecture + real
identity/RBAC"); 1.1 delivered the tenancy half and is merged
(`MULTI_TENANT_DESIGN.md`, `ebe233f`).

1.1's §5 stated the seam this picks up: `session["tenant_id"]` is already
populated correctly on every request, every table is tenant-scoped, and RLS is
in place. 1.2 replaces `session["role"]` — one shared string per tenant — with
real per-user identity, without re-deriving the tenant boundary.

## 1. Current state — grounded in what the code actually does today

- **There are no users.** `auth.py:37`: `ROLES = ("hr", "finance")`. A session
  is `{"role": "hr" | "finance", "tenant_id": int}` (`app.py:1277-1281`).
  Anyone holding a tenant's HR code is indistinguishable from anyone else
  holding it.
- **Authentication is a shared secret per tenant per role.**
  `tenant_settings.hr_access_code_hash` / `finance_access_code_hash`
  (`review_queue.py:260-261`). 1.1 scoped these per tenant and hashed them,
  which was a real improvement over one global pair — but they remain shared
  secrets, and 1.1 said so explicitly rather than implying otherwise.
- **The maker-checker trail records a ROLE, not a PERSON.** `app.py:984`:
  `decided_by=session["role"]`. Every approval and rejection in the review
  queue is attributed to the literal string `"finance"`. This is the single
  most important fact in this document: the feature whose entire purpose is
  governance and accountability cannot currently name who made any decision.
  A rejection reason says why, the audit log says when — and nothing, anywhere,
  says who.
- **Authorisation is a decorator over that string.** `require_role("finance")`
  (`auth.py:139-149`) checks `session.get("role")` against an allow-list
  hardcoded at each route. There is no notion of a permission, so a new role
  means editing every route that should accept it.
- **`/api/auth/login` has no rate limiting.** `_rate_limited()`
  (`app.py:108-116`) exists and guards exactly one route, `POST /api/submissions`.
  Login is unguarded. Today that is defensible-ish: there is one code per role
  per tenant and no username to enumerate. With named accounts it becomes
  credential stuffing against a known list of people, which is a different and
  worse problem — see 3.5.
- **There is no email infrastructure of any kind.** No SMTP, no delivery
  provider, nothing. Password reset has nowhere to send a token today — this is
  a real dependency, not a detail, and it is section 6's first open decision.
- **Password hashing already exists and works.** `hash_access_code()`
  (`auth.py:60-73`) uses `generate_password_hash(..., method="pbkdf2:sha256")`.
  The method is pinned deliberately: `hashlib.scrypt` (werkzeug's default) is
  absent on this repo's interpreter. 1.2 reuses this rather than introducing a
  second hashing path.

Net: the tenant boundary is real and enforced twice. Inside a tenant, there is
no identity at all.

## 2. The guarantee this design has to produce

Stated as a testable claim, the way 1.1's §2 was: **every state-changing action
in the system is attributable to exactly one identified human being, and no
state-changing action can be performed by a principal the system cannot name.**

Two clauses, both load-bearing:

- *Attributable to one human* — not to a role, not to "someone with the finance
  code". `decided_by` must resolve to a person who can be asked why.
- *Cannot be performed by an unnameable principal* — the shared codes do not
  survive as a fallback. A path that still lets an anonymous holder of a shared
  secret approve a payout would make the first clause a description of the happy
  path rather than a guarantee, which is exactly the distinction 1.1's §2 drew
  ("no code path — not merely no current path").

Explicitly NOT claimed by 1.2: that the human is who they say they are to any
standard beyond a password. Identity assurance (SSO, MFA) is 1.3.

## 3. Design decisions

Each stated with the real alternative and why it loses, per this project's
standard of not silently picking an option a reviewer would ask about.

### 3.1 Enforce on permissions; ship roles as fixed bundles of them

**Rejected: per-user assignment of the existing two role strings.** Smallest
diff — `users.role` is `'hr'` or `'finance'`, `require_role` keeps working
untouched. It loses because the enforcement point stays a hardcoded allow-list
at every route, so the next role (an auditor who may read the queue and the
audit log but decide nothing; an owner who may manage users) means editing
every decorator again and re-reviewing every route to confirm nothing was
missed. That is the same shape as 1.1's rejected "add `WHERE tenant_id` to the
queries we have today": correct for the paths written so far, one forgetful
edit away from wrong.

**Rejected: tenant-defined custom roles composed in an admin UI.** What large
customers eventually ask for, and a large build — role editor, permission
catalogue UI, migration when a permission is renamed. Nothing has asked for it,
and 1.2 does not need it to deliver the §2 guarantee.

**Chosen: routes are guarded by named PERMISSIONS; `hr` and `finance` ship as
fixed bundles.** Concretely:

```
submit_row        — POST /api/submissions
view_queue        — GET  /api/submissions, GET /api/submissions/<id>
decide_row        — POST .../decide
export_row        — POST .../export, POST .../complete
view_audit_log    — GET  /api/audit-log
view_bank_balance — GET  /api/razorpayx/balance
manage_users      — the 1.2 user-admin routes
```

`@require_permission("decide_row")` replaces `@require_role("finance")`. The
initial role set is exactly the two that exist today, so no tenant's effective
access changes on cutover — `hr` gets `submit_row` + `view_queue`, `finance`
gets those plus `decide_row`, `export_row`, `view_audit_log`,
`view_bank_balance`. A third role later is a row in a table, not a sweep
through `app.py`.

Roles are **system-defined in 1.2**, not tenant-editable. That keeps the
permission catalogue reviewable in code while making the enforcement point
future-proof, which is the only part that is expensive to change later.

### 3.2 Local password accounts now; SSO is 1.3

**Rejected: SSO (SAML/OIDC) inside 1.2.** It is what an enterprise buyer asks
for, and it removes password storage entirely. It loses on scope and on
testability: it needs an IdP to develop against, per-tenant IdP configuration,
JIT provisioning, and a role-mapping story from IdP groups to this system's
roles — each of which is a design decision of its own. None of it is required
by §2's guarantee, which is about attribution, not assurance.

**Chosen: email + password accounts, scoped to a tenant.** Reusing
`generate_password_hash(..., method="pbkdf2:sha256")` (`auth.py:73`), the path
already proven on this interpreter.

**The schema in §4 is shaped so 1.3 does not have to reshape it**, which is the
same courtesy 1.1 paid this phase: `users.password_hash` is NULLABLE. An
SSO-provisioned user simply has none and cannot authenticate locally. Adding
`users.idp_subject` and a per-tenant IdP config table in 1.3 touches no
existing column. If 1.3 turns out to need `users` reshaped, that is a signal
1.2 was scoped wrong — worth flagging rather than absorbing, per 1.1 §5's own
standard applied to itself.

### 3.3 The shared codes bootstrap one owner, then stop working

**Rejected: keep shared codes working alongside accounts.** Least disruptive
and directly contradicts §2. A shared secret that bypasses per-user
accountability makes every attribution claim conditional on nobody having used
it.

**Rejected: drop the columns at cutover, provision first users by CLI.**
Cleanest — no transitional dual-auth path to reason about. It loses on
operations: every existing tenant needs an operator to run a script before
anyone can log in, and there is no reason to require human intervention for a
transition the system can perform correctly by itself.

**Chosen: first successful login with a tenant's existing access code creates
that tenant's first user — an `owner` — and permanently disables the codes for
that tenant.** Specifically:

- The code is accepted only while `tenant_settings.codes_disabled_at IS NULL`
  **and** the tenant has zero users. Both conditions, not either: the timestamp
  records the transition, and the zero-users check means a tenant that somehow
  cleared the timestamp still cannot re-enter through the old door.
- That login is redirected into "set your email and password" before it can do
  anything else, so the owner account is a real credential, not a session
  minted from a shared secret.
- `codes_disabled_at` is set in the same transaction. The hashes are then dead
  weight; §6 asks whether to null them out or keep them as a record.

The result is that the shared secret dies on first use per tenant, automatically,
with no operator step and no window where both auth models are live for the same
tenant.

### 3.4 `decided_by` records a user id; the existing role strings stay legible

The review queue's `decided_by` column currently holds `'finance'`
(`review_queue.py`, written from `app.py:984`). After 1.2 it must identify a
person.

**Rejected: repurpose the column and backfill.** There is nothing to backfill
*to* — no user existed when those rows were decided, so any value invented for
them would be a fabricated attribution in an audit trail. That is worse than an
honest gap, and it is the same reasoning 1.1 used to refuse a default tenant.

**Chosen: add `decided_by_user_id INTEGER REFERENCES users(id)`, leave
`decided_by` as-is.** New decisions write both — the user id, and the user's
role at decision time as the text label, so the trail still reads correctly if
that person's role later changes. Historical rows keep `'finance'` with a NULL
user id, which is the truthful statement that the system did not know who acted.
The UI shows the person when there is one and the role otherwise, labelled as
pre-accounts rather than rendered identically.

Same treatment for the audit log: `_append_audit_log` gains a `user_id` field
alongside `tenant_id`. Lines written before 1.2 have none, and the reader must
not present them as if they did.

### 3.5 Login gets rate limiting, and it is keyed on the account

`_rate_limited()` (`app.py:108-116`) already exists, is per-IP, in-memory, and
guards only `POST /api/submissions`. 1.2 makes named accounts enumerable, so
login needs it too — but IP alone is the wrong key here: an attacker
distributing attempts across addresses defeats it, while a NAT'd office shares
one bucket.

**Chosen: limit on `(tenant_id, email)` AND on IP, whichever trips first**, and
respond identically whether the account exists or not, so the endpoint is not a
user-enumeration oracle. Lockout is a timed backoff, not a permanent lock, since
a permanent one is itself a denial-of-service an attacker can trigger against a
named person.

Stated plainly: the existing limiter is in-memory and per-process, which
`app.py:99-102` already names as a real limitation rather than production
hardening. 1.2 does not fix that; it is the same limitation applied to one more
route, and §6 records it.

### 3.6 `users` and `user_roles` are tenant-owned, and get the same two layers

They carry `tenant_id NOT NULL REFERENCES tenants(id)` and join
`_TENANT_SCOPED_TABLES`, so RLS applies exactly as it does to `submissions`
(1.1 §3.1). One tenant's user list is not reachable from another's session, by
application code or by a query that forgets a predicate.

The one deliberate exception is login itself, which must find a user before a
session exists. It resolves within the tenant already established from the
subdomain (1.1 §3.3) — the same mechanism `verify_login()` uses today to read
that tenant's code hashes under RLS, so no new trust boundary is introduced.

## 4. Concrete schema shape

```sql
CREATE TABLE users (
    id             INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id      INTEGER NOT NULL REFERENCES tenants(id),
    email          TEXT NOT NULL,
    display_name   TEXT NOT NULL,
    password_hash  TEXT,               -- NULLABLE: an SSO user (1.3) has none
    status         TEXT NOT NULL DEFAULT 'active',   -- active | invited | disabled
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at  TIMESTAMPTZ,
    UNIQUE (tenant_id, email)          -- NOT globally unique: the same person
);                                     -- may hold accounts at two companies

CREATE TABLE user_roles (
    tenant_id  INTEGER NOT NULL REFERENCES tenants(id),
    user_id    INTEGER NOT NULL REFERENCES users(id),
    role       TEXT NOT NULL,          -- owner | finance | hr
    PRIMARY KEY (user_id, role)
);

ALTER TABLE tenant_settings ADD COLUMN codes_disabled_at TIMESTAMPTZ;
ALTER TABLE submission_rows ADD COLUMN decided_by_user_id INTEGER REFERENCES users(id);

CREATE INDEX idx_users_tenant ON users(tenant_id);
CREATE INDEX idx_user_roles_tenant ON user_roles(tenant_id);
```

`UNIQUE (tenant_id, email)` and not a global unique index, deliberately: a
consultant working with two client companies is one human with two accounts,
and a global constraint would make that impossible while also leaking, via a
signup collision, that an address is already registered somewhere in the system.

The permission catalogue and the role→permission mapping live **in code**, not
in a table — they are system-defined in 1.2 (3.1), and a constant that ships
with the routes it guards cannot drift from them the way a seeded table can.

## 5. What 1.2 hands to 1.3 (the seam, stated explicitly)

1.2 ships: real accounts, per-user roles, permission-based route guards,
attribution on every new decision, shared codes retired. 1.2 explicitly does NOT
ship: SSO, MFA, tenant-defined custom roles, or a permission-editing UI.

1.3 should not need to touch `users` beyond adding `idp_subject` and a
per-tenant IdP configuration table, because `password_hash` is already nullable
and roles are already decoupled from the routes. Session shape after 1.2 is
`{"user_id": int, "tenant_id": int, "roles": [...]}` — the shape 1.1 §3.3
predicted, reached without ever re-deriving the tenant boundary.

## 6. Open decisions needing an explicit call, not a silent default

- **Password reset delivery.** There is no email infrastructure at all today
  (§1). Reset requires one, and the choice — a provider (SES/Postmark/Resend) vs.
  operator-issued reset links vs. deferring reset entirely to 1.3 with SSO —
  changes what 1.2 ships. Deferring is coherent: with an owner who can reset
  other users, only a locked-out sole owner is stuck.
- **Whether the retired code hashes are nulled or kept.** `codes_disabled_at`
  makes them unusable either way. Nulling removes a dead secret; keeping them
  preserves the record that a tenant was provisioned that way.
- **Rate-limit durability.** The existing limiter is in-memory and per-process
  and does not survive a restart or multiple workers (`app.py:99-102`). Whether
  1.2 keeps that honestly-labelled limitation or moves the limiter to Postgres
  is a real call, not a detail.

## 7. Suggested internal sequencing for 1.2

1. Add `users` / `user_roles` with `tenant_id` + RLS, and the two ALTERs in §4.
   No behaviour change; nothing reads them yet.
2. Add the permission catalogue and `@require_permission`, mapping the existing
   two roles to bundles. Swap every route's `@require_role` for it. The suite
   must stay green throughout — this step deliberately changes no access.
3. Add user CRUD behind `manage_users`, plus the admin CLI to create the first
   owner directly (needed by step 4's tests and by any tenant that never had
   codes).
4. Add real login against `users`, and the bootstrap-then-disable flow from 3.3.
   Session becomes `{"user_id", "tenant_id", "roles"}`.
5. Write `decided_by_user_id` and the audit log's `user_id`; update the UI to
   show a person, and to label pre-accounts rows as such rather than blending
   them in.
6. Add login rate limiting per 3.5.
7. Test plan, mirroring 1.1 §7.6 — separate tests for separate claims:
   - **Attribution:** every state-changing route records a resolvable user, and
     a decision made by one user is never attributed to another.
   - **Authorisation:** each permission is enforced at every route that needs
     it, asserted by driving every route with a role that lacks the permission
     and requiring a 403 — not by inspecting decorators.
   - **Cross-tenant, extending 1.1's suite:** a user of tenant A cannot be
     listed, edited, or authenticated into tenant B, at the application layer
     and again with the query wrapper bypassed.
   - **Shared-code retirement:** the code works exactly once, creates exactly
     one owner, and every subsequent attempt fails — including after the owner
     is deleted.
