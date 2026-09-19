# Frontend login against the per-user identity model — fix design

**Status:** design only, **awaiting approval.** No code is changed. Decisions
D-L1 to D-L4 (§7) are the owner's.

**Why this exists.** Phase 1.2 (`IDENTITY_DESIGN.md`) replaced the two shared
role codes with per-person accounts, and verified the backend by its own tests.
The page that uses it, `frontend/components/role-gate.tsx`, was never updated
and never run against it, because Node was believed absent (it was installed but
not on `PATH`; `docs/PROJECT_STATUS.md`, closed 2026-09-19). On 2026-09-20 the
frontend-rebuild session ran it end to end and found that **no tenant that has
completed bootstrap can sign in through the UI.**

---

## 1. What is broken — found by running it, then traced

| # | Break | Evidence |
|---|---|---|
| 1 | `RoleGate` POSTs `{role, code}` to `/api/auth/login`. After bootstrap the backend refuses that, correctly: *"Shared access codes are no longer used for this workspace."* | Hit for real in the end-to-end run. `app.api_auth_login`, shared-code branch. |
| 2 | `RoleGate` unlocks on `session.role === role`. `GET /api/auth/session` returns `{user_id, tenant_id, roles}`, with no `role` field, so the check can never pass. | `app.api_auth_session`. |
| 3 | In local development, requests through the Next rewrite reach Flask with `Host: 127.0.0.1:8000`. Login resolves the tenant from `Host`, so it answers *"Unknown workspace"*. | **Measured, not read** (§1.1). |
| 4 | **Same cause, found while designing:** the anonymous *"Submit correction"* flow (`batch-flow.tsx`, `POST /api/submissions`) also resolves its tenant from `Host` (`auth.resolved_tenant_id`), so it also fails through the proxy in development. The logged-in HR flow does not, because a session supplies the tenant. | `auth.require_resolved_tenant`, `auth.resolved_tenant_id`. |

Also stale in the component, and misleading: its header comment ("two SHARED
role-codes... no login rate-limiting") and the on-screen *"Demo code:
FINANCE2026"* hint describe the pre-1.2 system.

### 1.1 What the proxy actually sends

`frontend/node_modules/next` is 15.5.24. Its rewrite proxy
(`dist/server/lib/router-utils/proxy-request.js`) was run as-is against a header
echo server. A request arriving with `Host: acme.grosslo.app:3000` reached the
destination with:

| Header | Value |
|---|---|
| `Host` | `127.0.0.1:<destination port>` (`changeOrigin: true`) |
| `X-Forwarded-Host` | `acme.grosslo.app:3000` |
| `X-Forwarded-For`, `X-Forwarded-Proto` | **absent** |

So the original host is recoverable. §4 is about whether the backend may believe
it.

## 2. The backend contract the page must use (unchanged except §3)

| Route | Request | Result |
|---|---|---|
| `POST /api/auth/login` | `{email, password}` on a tenant host | 200 `{user, tenant}` and a session holding `user_id`, `tenant_id`, `roles`. 401 with one generic message for a wrong email or password (enumeration-safe by content and timing). 429 when throttled. |
| `POST /api/auth/login` | `{role, code}`, only while the tenant has no users and codes are not retired | 200 `{bootstrap_required: true, tenant, message}` and a **bootstrap-only** session that every guarded route refuses. |
| `POST /api/auth/bootstrap` | `{email, display_name, password}` (password ≥ 8) with a bootstrap session | Creates the first **owner**, retires the codes permanently, and returns a normal session. 409 if accounts already exist. |
| `GET /api/auth/session` | — | `{user_id, tenant_id, roles}`, with nulls and an empty list when signed out. |
| `POST /api/auth/logout` | — | Clears the session. |

Permissions are derived server-side from roles (`auth.ROLE_PERMISSIONS`):
`hr` = {view_queue, view_audit_log}; `finance` = {view_queue, decide_row,
export_row, view_audit_log, view_bank_balance}; `owner` = all.

## 3. Design

### 3.1 The session reports permissions; the page never derives them

`GET /api/auth/session` gains two keys:
- `permissions`: the sorted union of `ROLE_PERMISSIONS` over the session's roles,
  computed by the same function `require_permission` uses;
- `display_name`: the signed-in user's own name, read under the session's
  tenant.

Both are additive, and existing keys are unchanged.

**Why not map roles to permissions in the frontend:** that would be a second copy
of `ROLE_PERMISSIONS`, and the two would drift. This project has removed that
shape repeatedly. The page asks the server what the person may do, and the
server remains the only enforcement: every route keeps its own
`@require_permission`, so a wrong gate can only show or hide a page, never grant
access.

### 3.2 Each page is gated on the one permission its purpose needs

| Page | Gate | Why |
|---|---|---|
| `/finance` | `decide_row` | Deciding rows is what the page is for. `finance` and `owner` pass. |
| `/hr` | `view_queue` | The page lists the tenant's submissions (`GET /api/submissions`, which requires `view_queue`) and submits new ones. `hr`, `finance` and `owner` pass. |

**This changes who can open `/hr`.** The old gate admitted only the `hr` role;
this admits anyone who can see the queue. That is decision **D-L1**.

`RoleGate` becomes `PermissionGate({ permission, label, children })`. The pages
pass `permission="decide_row"` / `"view_queue"`.

### 3.3 The states the gate renders

| State | Detected by | Shows |
|---|---|---|
| checking | before the first `/api/auth/session` answer | nothing, as today, to avoid a flash |
| signed out | `user_id` null | the email/password form |
| signed in, permitted | `permissions` contains the page's | the page, plus *"Signed in as {display_name}"* and *Sign out* |
| signed in, not permitted | `user_id` set, permission absent | *"Signed in as {display_name}. This account can't use {label}."* plus *Sign out*. **Never the login form**: showing a form to someone already signed in reads as "your password was wrong" |
| setting up a workspace | the secondary link below | the bootstrap steps (§3.4) |

**The form:**
- It POSTs `{email, password}` and, on 200, re-reads `/api/auth/session`. It does
  not trust the login response to decide the gate.
- It shows the server's `error` text verbatim. Those messages are already
  generic by design (IDENTITY_DESIGN §3.5), and the page must not add detail the
  server withheld, such as "no such user".
- The submit control is disabled while a request is in flight, and 429 is shown
  as the server words it.

**Removed:**
- the *"Demo code"* hint, because codes no longer sign anyone in and the hint is
  now simply wrong (D-L4);
- the stale header comment, replaced with one describing this contract.

### 3.4 Bootstrap: a secondary path, not a second login

Under the form: a link, *"Setting up this workspace for the first time?"*. It
opens two steps:

1. **Role and access code.** It POSTs `{role, code}` to `/api/auth/login`.
   - **A 200 with `bootstrap_required`** advances to step 2.
   - **Any 401** shows the server's message verbatim. After bootstrap that
     message is *"Shared access codes are no longer used… Sign in with your
     email and password"*, which is the right thing to tell someone who took
     this path by mistake.
2. **Create the owner account.** Email, display name, password (at least 8
   characters, also checked client-side for a friendlier message; the server's
   check is the real one).
   - It POSTs to `/api/auth/bootstrap`, then re-reads the session.
   - The new owner holds every permission, so both pages open.

The page cannot know in advance whether a tenant is still in bootstrap, and
adding an endpoint that says so would disclose tenant state to anonymous
callers. The backend's own answer to step 1 is the source of truth.

### 3.5 Out of scope

User administration UI, password reset, MFA (IDENTITY_DESIGN §6 deferrals); the
stale backend process on port 8000 (the owner's to restart); any change to
maker-checker, routes' guards, or the hard constraints.

## 4. The `Host` problem in local development

Breaks 3 and 4 have one cause. Four options:

- **(A) Recommended: trust `X-Forwarded-Host` for tenant resolution only, and
  only when explicitly enabled.**
  - `tenant_slug_from_host` reads `X-Forwarded-Host`, first value, when the
    environment variable `TRUST_FORWARDED_HOST=1` is set. Otherwise it keeps
    reading `Host`. Default: off.
  - Local development sets it, next to the Next proxy that sets the header.
- **(B) Werkzeug `ProxyFix(x_host=1)` on the whole app.** Rejected: it rewrites
  `request.host` for every consumer, not only tenant resolution, which is a wider
  change than the problem.
- **(C) The browser calls Flask directly (CORS plus cross-origin cookies).**
  Rejected: it drops the same-origin session cookie model the app relies on, and
  it would need `SameSite=None` in development.
- **(D) Leave it, and document "log in on the backend port".** Rejected as a fix.
  It is the workaround the frontend session used to test, and it leaves break 4
  as well.

**Why (A) is safe, and where it would not be** (the trust boundary is
`auth.tenant_slug_from_host`'s own docstring):

- **What a resolved host authorises today:** exactly two things. It chooses
  which tenant a login is attempted against, where the credentials still have
  to be valid for that tenant. And it chooses which tenant's queue an anonymous
  submission lands in. Every read takes its tenant from the signed session, never
  from a host.
- **Why that makes it no worse than today:** `Host` is already client-supplied.
  A client that can reach Flask directly can already send any `Host`, so
  believing `X-Forwarded-Host` gives such a client nothing new.
- **Where it becomes unsafe:** when a production proxy validates `Host` but
  passes a client's `X-Forwarded-Host` through unchanged. Trusting the header
  there would bypass that validation. That is why it is off by default.
- **The condition for enabling it in production:** it may be enabled only where
  the terminating proxy sets or overwrites `X-Forwarded-Host`. That is decision
  **D-L2**, and the variable's docstring will say so.

## 5. Tests and verification

**Backend** (Python suite, both states for each):
- **`permissions` in the session.**
  - Owner: all six.
  - `hr`: exactly `{view_audit_log, view_queue}`.
  - Signed out: empty.
  - One test pins that it equals what `require_permission` enforces: for each
    role and each guarded route, the route's permission is in `permissions`
    exactly when the route answers something other than 403.
- **`display_name`:** the user's own. `null` when signed out.
- **Forwarded host.**
  - With `TRUST_FORWARDED_HOST` unset, a request with a foreign
    `X-Forwarded-Host` and no tenant `Host` still gets "Unknown workspace", and
    one with a tenant `Host` still resolves that tenant, whatever
    `X-Forwarded-Host` says.
  - With it set, `X-Forwarded-Host` decides.
  - A malformed or multi-label value resolves to no tenant, as today.
- **Sabotage:**
  - Make the flag default to on: the "unset" tests fail.
  - Compute `permissions` from a copied table: the parity test fails once one
    role's entry differs.

**Frontend.** There is no test runner in `frontend/package.json`, and adding one
is not proposed here. Verification:
- `tsc --noEmit` over the whole project.
- **An end-to-end run through the real Next proxy.** It uses the current backend
  on a separate port with `TRUST_FORWARDED_HOST=1`, a throwaway tenant and a
  tenant host in `/etc/hosts` or a `Host` override, and records a screenshot of
  each of:
  - bootstrap on a fresh tenant;
  - password login as `finance` (both pages open);
  - login as `hr`, where `/finance` shows the not-permitted state and not the
    form;
  - a wrong password showing the generic message;
  - sign out;
  - the anonymous *Submit correction* flow succeeding through the proxy.

  All test data is removed afterwards, as in the 2026-09-20 run.

## 6. Sequence

Separate commits, full Python suite after each, request/go handshake:

1. `GET /api/auth/session` gains `permissions` and `display_name`, with tests.
   Backend, additive.
2. `TRUST_FORWARDED_HOST` in `tenant_slug_from_host`, default off, with tests.
   Only if D-L2 is approved.
3. `api-types.ts`: the session type.
4. `PermissionGate` replaces `RoleGate`, and the two pages switch to it.
5. `.env.example` and the README's run instructions: set the variable for local
   development, and why.
6. The end-to-end run (§5), then README / `docs/PROJECT_STATUS.md`: close the login
   row, or record exactly what is still unseen.

## 7. Decisions for the owner

| | Decision | Recommendation |
|---|---|---|
| **D-L1** | Who may open `/hr`? | **Anyone holding `view_queue`** (hr, finance, owner). The page's own data call already requires exactly that, and gating it more narrowly than its data would lock an owner out of HR for no security gain. The alternative: add a distinct `submit` permission held only by hr and owner, which is a change to the permission model. |
| **D-L2** | Trust `X-Forwarded-Host` for tenant resolution? | **Yes, opt-in (`TRUST_FORWARDED_HOST=1`), default off, enabled in local development only** until a production proxy is known to overwrite the header (§4). |
| **D-L3** | Who implements? | **The frontend-rebuild session, all six steps, with this session reviewing.** Its user asked it to build this, it has the Node toolchain and the end-to-end harness working, and one implementer avoids splitting a coupled backend/frontend change across two sessions. |
| **D-L4** | Remove the *"Demo code"* hint? | **Yes.** Codes no longer sign anyone in; after bootstrap the hint is simply false. |
