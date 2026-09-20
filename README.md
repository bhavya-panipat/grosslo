# grosslo — the decision and compliance layer for RazorpayX payroll

Built for the Razorpay AI Buildathon 2026, AI Finance Controller track.

**Stated precisely, up front:** grosslo is the decision and compliance layer
a real autonomous payroll controller would need underneath it — not yet the
acting system itself. It does now call RazorpayX's real API and does write
state (a Postgres review queue, a signed session cookie) — stated exactly,
not glossed over: exactly one route (`GET /api/razorpayx/balance`, see
`razorpayx_client.py`) makes a live, read-only call with zero money
movement, and state-writing is scoped to persisting a submission for
human review and authenticating who can see it — never to a payout.
No route moves money or dispatches a payout; every payout/export code
path still terminates in a generated payload, not a live disbursement.
That boundary is deliberate (see "Known limitations" and "Roadmap"
below), not a gap discovered after the fact.

grosslo structures a compensation offer, checks it against a company's approved
band and statutory ceilings, forecasts the capital a treasury team needs to fund
it, and exports a schema-accurate RazorpayX Composite Payout payload — for one
candidate at a time or a whole CSV batch. Every step is logged as a real
execution trace, not a black box: what ran, what it found, and why.

## Who and where this is for — decided, not assumed

**Salaried employees, taxed in India. Not contractors, and not a second
country.** A decision rather than a description of what happens to exist; see
`PRODUCT_SCOPE_DESIGN.md` for the evidence and the reasoning.

- **Employees only.** Not a limitation waiting to be lifted. The product is
  *take a CTC and split it to minimise tax* — and a contractor has no CTC to
  split. HRA exemption, LTA and employer PF are not features a contractor is
  missing; they are categories that do not exist for one. Even with every
  supporting piece added, the optimiser would have nothing to act on. Serving
  contractors would be a **different product** sharing this tax engine, not an
  extension of this one.
- **India only, meaning the employee's TAX JURISDICTION is India.** The
  employer's domicile is irrelevant: an Indian employee of a foreign-domiciled
  company is **in scope**.
- **Why not both, right now — a sequencing argument, not a verdict on the
  ideas.** A second jurisdiction would multiply an unverified corpus rather than
  deepen a verified one. Today 15 of this codebase's 17 inventoried legal claims
  are unverified and *none* has been signed off by a qualified professional (see
  `docs/PROJECT_STATUS.md`). Widening the surface before that is settled makes
  the existing problem larger, not the product better.

**Isn't this what RazorpayX Payroll already does?** RazorpayX Payroll is a
real, shipped product with CTC structuring, statutory filing, and direct
disbursement already built. grosslo doesn't re-implement that — it's
narrower and more forensic: per-hire tax-optimization modeling, a
maker-checker governance layer with a real audit trail, and an audit-sweep
mode that runs the same checks *backwards* over payroll a company already
runs elsewhere, which a payroll-execution product has no reason to build.
See "Isn't this what RazorpayX Payroll already does?" in
`FINOS_PROJECT_BRIEF.md` for the full answer, not just the summary.

## What it actually does

- **Structure**: given a CTC (or a pasted, messy offer letter), computes the
  tax-minimizing salary split under both the old and new Indian tax regimes and
  recommends the better one — the deterministic core this was originally built
  around.
- **Check**: every structure is run against a fixed compliance rule set
  (`compliance_rules.md`, six rules) and a payroll guardrail (approved
  compensation band, the ₹7.5L aggregate EPFO contribution ceiling, the
  regime-specific Section 124 employer-NPS cap, formerly Section 80CCD(2)
  under the 1961 Act — see "Regulatory currency" below).
- **Forecast**: net take-home, TDS escrow, and EPFO challan are summed into a
  single capital-outlay number, with a funding lead time — what treasury needs
  to have ready before payroll runs.
- **Export**: a real RazorpayX Composite Payout payload (verified against
  RazorpayX's own API docs, not guessed) — nested `fund_account`/`contact`,
  amount in paise. The amount is **net pay**: the treasury forecast's take-home,
  after employee PF, TDS and professional tax, which are remitted separately and
  reported beside the payload as `payout_basis`. No live call is ever made; this
  generates the payload only.
- **Batch**: `/hr`'s CSV upload structures a set of new offers in one pass —
  the single path for this now, single or batch, so every new hire goes
  through the same Finance review an individual offer does (see "Redundancy
  fix" below). `/optimize/batch` is a separate, audit-only CSV flow: point
  the same guardrail checks at *existing* employee structures, surface
  unclaimed regime-switch savings and excess EPFO contributions across the
  whole set, and send any flagged row to Finance the same way. The summary
  isn't just two currency totals — it reports clean vs. flagged counts and
  a real exception breakdown (over the EPFO cap vs. filed under the wrong
  regime entirely for that structure, a genuinely different signal from
  "unclaimed savings"), so a batch narration has actual on-screen counts to
  point at instead of a number nobody watching can verify.
- **Trace**: a live-looking execution log on every result — parse → compliance
  pass → math solver → policy gate — where every line is built from a field
  the underlying computation actually returned, never a scripted placeholder.

## Maker-checker review (demo-scoped, stated explicitly)

Closes a real gap the earlier build had: Compliance & Savings Audit could
detect a problem, but there was no path from "here's an issue" to an
actual decision being made and recorded. This adds that loop, scoped
honestly for a demo rather than dressed up as production workflow
infrastructure:

- **HR submits** (`POST /api/submissions`) — a single offer or a CSV
  batch, computed through the exact same `_build_optimize_response()`
  every other route uses. Nothing new is computed here; this only decides
  whether a result gets persisted for review.
- **Every submitted row is auto-routed by risk before Finance ever sees
  it** (`orchestration.py`'s `classify_row()`, a routing/presentation
  decision only — never an approval). Four routes, evaluated in priority
  order: `escalate` (a failing guardrail check, or any High-severity
  compliance flag), `guardrail_not_run` (no approved compensation band was
  supplied — a real, visibly distinct "never checked" state, not folded
  into "clean"), `needs_review` (Medium-severity flag), or
  `auto_pass_candidate` (nothing above Low severity, and the guardrail
  ran and passed — still visibly badged if a Low flag exists, e.g.
  "Fast-tracked · 1 low-severity note, R4," never silently indistinguishable
  from a genuinely flag-free row). A human still clicks Approve on every
  single row regardless of route — see the next bullet for exactly how far
  routing is allowed to go.
- **Finance reviews** (`GET /api/submissions`, `/hr` and `/finance` as two
  separate frontend pages) — inspects the real execution trace, the real
  compliance flags, and a before/after diff (below), then approves or
  rejects **per row**, not only per whole submission — a 50-row batch
  where 2 rows have flags doesn't require an all-or-nothing decision. The
  queue itself is sectioned by the routing decision above (Clean / Needs
  review / Guardrail not run / Escalated), so risk is visible before
  opening a single row, not just after — and the sections render in
  urgency order, Escalated first and Clean last, not in whatever order
  they happened to be coded in. (They originally rendered Clean-first,
  the opposite of what a reviewer opening the page actually wants;
  fixed once that was pointed out.)
- **Approving never dispatches anything.** It writes a status change and
  an audit-log entry that says exactly that: *"Approved — Payout
  SIMULATED, no live dispatch."* This is the same live-execution boundary
  drawn everywhere else in this codebase, in button copy this time instead
  of pitch copy, and it doesn't move here either.
- **Rejecting requires a reason** (free text, mandatory) — a review
  process that can't say no isn't a review process. The rejected row
  returns to HR's queue with that reason visible, and the rejection is
  logged exactly like an approval — a decision either way belongs in the
  trail.
- **A before/after diff, not just a raw trace — and now visible without
  opening the row.** For every offer with a prior structure to compare
  against, Finance sees exactly which fields changed and *why* —
  attributed to the specific compliance rule it resolves (e.g. "Basic:
  ₹5,00,000 → ₹9,00,000 — R1 compliance fix") or to "tax optimization"
  when no rule is involved. Zero new computation: this reads the same
  `negotiation`/`compliance` data every other route already produces
  (`diff_view.py`). This used to render only inside the "Inspect" expand
  panel — a reviewer scanning the queue saw a flag count, never the
  actual fix, unless they clicked into every row. A one-line summary of
  the single highest-severity fix — not just the first field that happens
  to differ — now renders directly in the collapsed row. A row with no
  prior offer to compare against (a plain new hire) shows no suggested-fix
  line at all, on purpose — a vague placeholder would be worse than
  showing nothing.
- **Duplicate submissions are flagged, not silently reprocessed.** The
  same employee at the same CTC submitted twice in the same day is
  detected and blocked before it's inserted (`review_queue.py`). A
  double-click on Approve doesn't write a second audit-log entry either —
  the status transition only fires once, by construction, not because of
  a special case bolted on for double-clicks.
- **Bulk actions batch the click, never the judgment — and are now
  structurally scoped to the clean bucket only.** A "Submit all N for
  review" button on the audit page sends every flagged row in one
  `/api/submissions` batch call instead of N separate ones — the endpoint
  already accepted a batch array, this just uses it. On `/finance`, only
  the "Clean — ready to fast-track" section renders a "select all" /
  per-row checkbox at all; `Needs review`, `Guardrail not run`, and
  `Escalated` rows render with **no checkbox in the DOM**, not a disabled
  one with a warning — there is structurally nothing to select-around. A
  row in any of those three sections is approved/rejected individually,
  through the same per-row flow, full stop. When a bulk action completes,
  a summary states the split plainly, e.g. *"12 of 15 rows bulk-approved.
  3 require individual review (2 high-severity, 1 guardrail not run)."*
  Rejection (bulk or single) still requires a reason. There's no
  bulk-decide endpoint and no need for one — this fires the same
  idempotent per-row `/decide` call once per selected row, in parallel, so
  every row still gets its own individually logged decision, now recorded
  under the real Finance session's role rather than a client-supplied
  string. Nothing here lets anything but a person decide.
- **Bulk Salary Revision export** (`POST
  /api/submissions/<id>/rows/<row_index>/export`, approved rows only)
  closes the audit loop the rest of the way: takes a flagged employee's
  current + corrected structure (already computed by the audit, invented
  nowhere here) and generates a real multi-sheet XLSX — modeled on
  RazorpayX Payroll's own documented two-sheet Salary Revision format
  (Default Structure, Custom Structure), plus a Read Me sheet. **The exact
  column headers were not verified against a live RazorpayX account** —
  the file says so explicitly, in its own Read Me sheet and in the
  response's `X-Template-Honesty-Label` header, so this is never mistaken
  for a confirmed, ready-to-upload template. After download, `/finance`
  shows a **"Simulate upload to RazorpayX Payroll"** confirmation
  button — deliberately *not* a fake API-call preview like new hire's
  Composite Payout payload gets: Bulk Salary Revision is a RazorpayX
  Payroll dashboard file-upload feature, not a documented JSON API, so
  simulating an API call for it would mean inventing a schema nothing
  has verified. The confirmation step mirrors new hire's "review, then
  confirm" UX without pretending an API call happened where only a file
  upload actually would.

**What this is, and isn't:** real server-side authentication with
**per-user accounts** as of Roadmap Phase 1.2. Sign-in is email + password
(`POST /api/auth/login`), resolved inside the tenant the subdomain names and
never from a tenant field in the request body. Passwords are hashed with
pbkdf2:sha256; a failed lookup still performs a dummy hash, so a valid email
cannot be distinguished from an invalid one by timing. Authorisation is
permission-based (`auth.py`'s `PERMISSIONS` / `ROLE_PERMISSIONS` /
`require_permission`), not a role-string comparison, and `/api/users` manages
accounts and their roles. The session is a signed, HttpOnly, expiring cookie
(`flask.session`), not a client-side `sessionStorage` check anyone could read
past in devtools. See "Security and privacy posture" below for exactly which
routes it gates.

**Sign-in is throttled**, per IP and per account, in a rolling window
(`LOGIN_MAX_PER_IP`, `LOGIN_MAX_PER_ACCOUNT`, `LOGIN_WINDOW_SECONDS`). The
check runs *before* any credential is verified, so a throttled attempt also
costs no pbkdf2 work — the limiter doubles as the defence against using login
as a CPU amplifier.

**The shared role-codes still exist, narrowed to one job.** A tenant's code
bootstraps its *first owner account*, once, and a code login deliberately does
not produce a usable session. After bootstrap the path is refused outright
("Shared access codes are no longer used for this workspace").

What's still genuinely absent: **password reset, MFA, and any permanent
lockout** — the limiter is a rolling window, not a lock. Also absent: a
steady-state company roster (persistence is Postgres as of Phase 1.1, but it
stores submissions awaiting review, not an employee master), a second-approver
escalation tier, and a notification system for pending reviews. These are reasonable ideas in isolation; none of them
belong on top of an approval layer already honestly labeled as a demo
simplification — making that layer *look* more sophisticated than it
actually is would undermine the exact honesty this section is trying to
model.

### Redundancy fix: one path for structuring a new hire, not two

`/optimize/batch` used to have a "New Hire Batch" mode alongside
"Compliance & Savings Audit" — it computed a structure via
`/api/optimize-batch` and offered a direct "Export N to RazorpayX" button
with **no Finance review step at all**, while `/hr`'s batch upload went
through the exact same computation and then queued it for approval. Same
underlying pipeline, two different governance outcomes depending on which
page happened to be open — a real workflow gap, not a cosmetic one.

Fixed by removing the redundant path entirely, not just hiding it in the
UI: `/api/optimize-batch` no longer exists, `/optimize/batch`'s mode
toggle is gone, and it's audit-only now. `/hr` is the sole path for
structuring a new hire, single offer or CSV batch, and it always goes
through Finance.

That fix surfaced three more gaps behind the same redundancy, closed
together rather than one at a time:

- **`/api/submissions` never ran the payroll guardrail at all.** Only the
  standalone `/api/optimize-batch`/`/api/export-razorpayx` paths checked
  a compensation band; an offer submitted through `/hr` could be approved
  with zero guardrail signal anywhere in the review queue. Fixed —
  `/api/submissions` now runs `evaluate_band_guardrail()` whenever
  `band_min`/`band_max` are supplied, the same function every other route
  uses.
- **No path from an approved row to a real export.** Approving in
  `/finance` only ever wrote a status change; there was no way to turn
  that decision into an actual RazorpayX payload or Salary Revision file
  without leaving the review queue and re-entering everything by hand in
  a separate modal. Fixed with `POST
  /api/submissions/<id>/rows/<row_index>/export` — approved-only, and it
  branches on what the row actually was: a correction (has a prior
  `current_structure`) generates the Salary Revision XLSX, a new hire
  generates a RazorpayX Composite Payout payload from the bank details
  supplied at submission time. `/hr` now also collects `band_min`/
  `band_max`/`bank_account_number`/`ifsc`/`email` (all optional) for
  exactly this reason — see the persistence note above for what that
  means for stored data.
- **The Bulk Salary Revision export had zero frontend wiring.**
  `/api/export-salary-revision` (the original standalone endpoint) is
  still never called from any page — it remains a real, tested capability
  with no UI path to it, which is itself a known gap rather than
  something newly introduced here. The new per-row export above reuses
  the same `build_salary_revision_workbook()` function directly instead
  of routing through that standalone endpoint, so a correction row's
  export works today even though the standalone route's own UI gap is
  unresolved.

## Architecture — the one rule that matters most

```
Input (CTC form, or a pasted offer letter, or a CSV batch)
        │
        ▼
ai_layer.py — extraction          (LLM, with a deterministic regex fallback)
        │
        ▼
optimizer.py + tax_engine.py      (deterministic, unit-tested — sole source of
        │                          every tax figure shown to the user)
        ▼
ai_layer.py — explanation          (LLM narrates the engine's numbers, never
        │                           invents its own — see the numeric guard below)
        ▼
ai_layer.py — compliance flags     (rule matching is always deterministic;
        │                           LLM only rephrases already-decided flags)
        ▼
ai_layer.py — payroll guardrail    (band / EPFO ceiling / 80CCD(2) — same
        │                           deterministic-first pattern as compliance)
        ▼
payroll_breakdown.py — treasury forecast, penalty_exposure.py — delay scenario
        │
        ▼
app.py — RazorpayX Composite Payout payload (schema only, no live dispatch)
```

**No LLM call anywhere in this codebase is ever allowed to compute, restate
with different rounding, or invent a tax/salary/compliance figure.** Every
number the user sees traces back to `tax_engine.py` / `optimizer.py` /
`payroll_breakdown.py` / `penalty_exposure.py`. Enforced two ways:

- **Explanation and negotiation-adjacent text** — a numeric guard extracts
  every number the LLM's response contains and rejects the response (falling
  back to a templated deterministic version) if any number isn't traceable to
  the input data the LLM was given.
- **Compliance and guardrail flags** — rule matching happens entirely in
  Python before the LLM ever sees anything. The LLM's only job is rephrasing
  already-decided flags into cleaner sentences; it cannot add, remove, or
  reinterpret one.

The execution trace (`execution_trace.py`) follows the same discipline from a
different angle: it never hooks into `optimize()`, `flag_compliance()`, or
`evaluate_band_guardrail()` internally. It's a thin wrapper that runs *after*
those functions return, and formats trace lines by quoting their real output
verbatim — so a trace line citing a compliance section is never a citation
grosslo invented, only one the compliance engine already decided.

## Running it

**Postgres is required**, for the app *and* for the test suite. Persistence
moved from a single SQLite file to Postgres in Roadmap Phase 1.1 step 1 (see
`MULTI_TENANT_DESIGN.md` section 7) because SQLite has no row-level security
and no per-connection session variables to key one on:

```bash
brew install postgresql@16
brew services start postgresql@16
createdb grosslo                        # or set DATABASE_URL to point elsewhere
psql -d grosslo -f scripts/setup_app_role.sql   # once; needs superuser
pip3 install -r requirements.txt
```

That third command creates `grosslo_app`, the unprivileged role the
application connects as. It is not optional and not cosmetic: PostgreSQL
exempts superusers and `BYPASSRLS` roles from every row-level-security policy,
and the Homebrew default connection role is a superuser — so connecting as
yourself would leave the tenant-isolation policies present in the schema and
enforcing nothing, while every test still passed.

If Postgres isn't running, the test suite fails at *collection* with a wall of
connection errors, before a single test executes — `app.py` calls
`review_queue.init_db()` at import time and every test module imports `app`.
That failure means the service is down; it does not mean the code under test is
broken. `brew services start postgresql@16` fixes it.

Provision at least one tenant — the app is multi-tenant as of Roadmap Phase
1.1, and a request that resolves to no tenant cannot log in or submit:

```bash
python3 scripts/create_tenant.py --slug acme --name "Acme Corp" --hr-code HR2026 --finance-code FINANCE2026
```

Tenants are resolved from the subdomain (`acme.grosslo.app`), never from a
request body — a client-supplied tenant id is unverified, and trusting one
would let any authenticated session read another company's data. Access codes
are per tenant and stored hashed; the old process-wide `HR_ACCESS_CODE` /
`FINANCE_ACCESS_CODE` are gone, because one shared pair would have opened every
company's review queue.

Backend:
```bash
python3 -m unittest discover -s tests   # 615 tests, all pass with no API key set
python3 app.py 8000                     # serves the API at http://127.0.0.1:8000
```

**You must reach the app on a tenant subdomain — plain `localhost` will not
log in.** The tenant comes from the host, so `http://localhost:3000` resolves
to no tenant and `/api/auth/login` returns 401 "Unknown workspace". That is
correct behaviour, not a misconfiguration, but it will stop you dead if you
open the URL the frontend prints. Two ways round it:

```bash
# Easiest — no /etc/hosts edit needed; *.localhost resolves to 127.0.0.1 already
echo 'TENANT_DOMAIN_SUFFIX=localhost' >> .env   # then use http://acme.localhost:3000

# Or keep the real suffix and add the host yourself
echo '127.0.0.1  acme.grosslo.app' | sudo tee -a /etc/hosts   # then http://acme.grosslo.app:3000
```

Frontend (Next.js — Node isn't bundled with this repo, install it separately):
```bash
cd frontend
npm install
npm run dev                             # prints http://localhost:3000 — open it on a
                                        # tenant subdomain instead (see above);
                                        # proxies /api/* to Flask on :8000
```

To enable the real LLM-backed extraction/explanation/compliance-phrasing/query
answering, put `ANTHROPIC_API_KEY=sk-...` in a `.env` file in the project root
(gitignored, loaded automatically via `python-dotenv` at startup — no manual
`export` needed) or set it in your shell before starting the backend.
**Without a key, every AI-layer function still works correctly** via its
deterministic fallback, and `/health` reports `ai_layer_active: false` so
this is visible rather than silent — a deliberate design choice, not a
bolted-on fallback.

## Known unverified surfaces — one standing limitation, not separate gaps

**Corrected 2026-09-19: Node was installed all along, just not on `PATH`.** This
section used to open *"There is no `node` binary in the environment this was
built in"*. That was a fact about how the shell looked for it, not about the
machine: a binary is at `~/.local/node-v24.20.0-darwin-arm64/bin`. It is the same
mistake as reading two automated 403s as "the legal sources are unreachable",
concluding from one access method that a thing is absent. It stood from Phase
1.2 until another session located the binary.

What is now verified, 2026-09-19, by that session:
- a whole-project `tsc --noEmit` exits 0, so **every file below type-checks**;
- the Next.js dev server compiles and serves `/finance` with a 200 and no console
  or runtime errors. **Scope:** this shows the frontend compiles and renders, and
  nothing about the backend. The backend answering on port 8000 was a process
  started 2026-09-04, before tenancy, identity and the NPS fix. It issued a
  session with no tenant at all, so no current backend logic was exercised, and
  the page never got past login.

**What is still unverified is behaviour with data.** The rows below say what
has to be rendered and seen, and none of those checks has been done yet. They
are listed together because they are one gap with several instances:

| File | Added in | Type-checked | What must still be rendered and seen |
|---|---|---|
| `frontend/components/finance/finance-flow.tsx` (`DecidedBy`) | Phase 1.2 | yes | Render a decided row and confirm the decider's name appears; render one with a NULL `decided_by_user_id` and confirm it shows as *Unattributed* rather than blank or, worse, attributed to someone |
| `frontend/lib/api-types.ts` | Phase 2.1, 2.2, D1 | yes | Nothing further: declarations only (`stages_run`, `PipelineStage`, `rules_triggered`/`rules_total`, `tax_basis_flag`) |
| `frontend/components/ring-metric.tsx` | Phase 2.2 | yes | Confirm the Compliance ring shows the rule ratio beside the percentage, and that a response lacking those fields still renders the bare percentage rather than `undefined/undefined` |

| `frontend/components/finance/finance-flow.tsx` (`TaxBasisBadge`, `RouteBadge`) | D1 (`1dc3b98`) | yes | **Partly seen, 2026-09-20**, by another session, end to end, against a current backend on a separate port with a throwaway tenant (cleaned up afterwards). A real submission's `tax_basis` was set to NULL, and the API served `tax_basis_flag`. A screenshot showed an `auto_pass_candidate` row with gold *"Fast-tracked"* and *"Computed before tax fix"*, not green *"Clean"*. **Not yet seen:** the badge on the other routes, and a legacy row with no `orchestration` showing the reason under *"Tax basis"* |

Until each is checked, the honest description of this project is **"backend
verified, UI surfaces type-checked, their behaviour with data unverified"**.

**The Finance/HR login does not work against current code for any tenant that
has completed bootstrap.** Found 2026-09-20 by the session above, not yet fixed.
`frontend/components/role-gate.tsx` still speaks the pre-Phase-1.2 protocol, and
fails in two independent ways:

1. It POSTs `{role, code}` to `/api/auth/login`. Once a tenant's access codes are
   retired, the backend correctly answers 401, *"Shared access codes are no longer
   used for this workspace"*. This was hit for real.
2. It checks `d.role === role` against `GET /api/auth/session`, which now returns
   `{user_id, tenant_id, roles}` with no `role` field. So the check cannot pass.

Separately, for local development, Next's rewrite proxy does not forward the
original `Host` header to an absolute destination. `/api/auth/login` resolves
the tenant from `Host`, so through the proxy it answers *"Unknown workspace"*.

The backend's identity model was verified by its own tests. The page that uses
it was never exercised against it, because no one could run Node here. The fix is
feature work: an email/password form and a bootstrap flow. Tracked in
`docs/PROJECT_STATUS.md`. `IDENTITY_DESIGN.md` §7 and
`COMPLIANCE_BREADTH_DESIGN.md` reference this table rather than keeping their
own copies — a second list would be the same drift problem those phases were
written to remove.

## What's genuinely AI-native, and what isn't

Being direct about this, because a reviewer will ask: the tax calculation
(`tax_engine.py`, `optimizer.py`) is entirely deterministic, on purpose — a
grid-search optimizer over a well-defined rules problem, chosen specifically
*because* a general-purpose LLM should not be doing arithmetic on someone's
tax or payroll liability. The AI-native surface is `ai_layer.py`'s functions:
pulling structured numbers out of messy unstructured offer-letter text
(genuinely hard to do reliably with regex alone), turning a table of optimizer
output into a plain-language explanation personalized to the actual numbers,
phrasing compliance and guardrail findings clearly, and answering natural-
language follow-up questions — including "what if" questions that trigger a
real re-run of the deterministic engine with the changed input, not an LLM
guess at what the new number would be.

## Known limitations (stated explicitly, not left for a reviewer to find)

- **Surcharge** (income above ₹50L) is not modeled. Scoped for the salaried
  CTC ranges typical of early-to-mid career hires.
- **Aggregate employer PF + NPS above ₹7.5L/year** is a taxable perquisite
  under Section 17(1)(h) of the Income-tax Act, 2025 (formerly Section
  17(2)(vii)) that the tax engine does not compute into the tax figure itself
  — the guardrail's EPFO ceiling check exists specifically so this is flagged
  rather than silently absent. **Also:** the statute aggregates *three* funds
  (recognised PF, the notified pension scheme, and an approved superannuation
  fund); this tool sums two and models no superannuation component, so the
  check is exact only for structures with none.
- **LTA exemption** is modeled at a conservative assumed 70% utilization
  rather than the full claimed amount, since real LTA exemption depends on
  actual travel, valid bills, and a twice-per-4-year block limit this tool
  can't know in advance.
- **Basic salary is constrained to 50–60% of CTC.** The floor is now
  statutory, not convention — the Code on Wages 2025 requires Basic + DA to
  be at least 50% of remuneration, and this tool has no DA field (see
  "Regulatory currency" below for the full fix). The ceiling stops an
  unconstrained tax-minimizing search from pushing basic upward
  indefinitely, which produced structures no real company would implement
  in early testing.
- **Employee-side PF is not modeled in `tax_engine.py`** (only the
  employer's cost-to-company contribution is). `payroll_breakdown.py`
  introduces employee PF as a new, explicit assumption (12% of basic,
  symmetric with the engine's own employer-PF convention) purely for
  net-disbursement and treasury math — it never feeds back into the tax
  calculation itself.
- **The delayed-remittance penalty scenario (`penalty_exposure.py`) models
  Section 7Q interest and Section 14B damages (EPF) and Section 398(3)
  (formerly Section 201(1A) under the 1961 Act) interest (TDS) —
  deliberately not Section 448 (formerly Section 271C).** The Supreme Court
  held in *US Technologies International (P.) Ltd. v. CIT* (2023), under
  the 1961 Act's numbering current at the time, that 271C applies only to
  failure to *deduct* TDS, not to late remittance after deduction — the
  exact scenario this feature models. Including that figure here would have
  been a real citation error, not a rounding one, so it's excluded on
  purpose. Professional tax (state-variable) and ESI (wage ceiling below
  this tool's target salary bracket) are excluded for similar scope
  reasons.
- **Extraction is not guaranteed accurate**, LLM-backed or not — extracted
  values are always shown for manual correction before use, with a mismatch
  warning when extracted components don't sum to the extracted CTC.
- Assumes a resident individual, under 60, salaried, with no other income
  sources or capital gains.
- **The RazorpayX Composite Payout / Salary Revision exports generate a
  schema-verified payload only — no live payout dispatch is made anywhere
  in this codebase.** One route is a deliberate, narrow exception:
  `GET /api/razorpayx/balance` (`razorpayx_client.py`) makes a real, live,
  read-only call to RazorpayX's account-balance API (`GET
  /v1/banking_balances`) — verified working against a real test-mode
  account, returning a genuine (zero, freshly-provisioned) balance. It
  refuses to run against anything but a test-mode key (`rzp_test_...`
  prefix required, no override) and moves zero money. This exists to
  prove the RazorpayX integration is real and reachable, not simulated —
  every payout-generating route stays payload-construction-only,
  unchanged, gated behind Finance approval either way.
- **Security and privacy posture, stated plainly rather than left silent —
  this matters more than most limitations here, because this tool handles
  real compensation data.** Persistence is now limited to two things: the
  Postgres review queue that lets an HR submission survive
  until Finance reviews it, and the local `audit_log.jsonl` decision
  trail — nothing else. **The trail isn't just a claim in this README —
  `GET /api/audit-log` (optionally `?limit=`) reads it back live**, so a
  reviewer can inspect exactly what's actually been logged (every
  optimize/submit/decide/export/balance-check call, with its own
  timestamp and payload) rather than trusting that a file on disk says
  what this document says it does. Not in the pitch video, since it's a
  read-only inspection endpoint rather than a visual demo beat — the
  route itself, and this section, are the pointer for it. Specifically:
  - **No encryption at rest.** Neither the Postgres tables nor
    `audit_log.jsonl` is encrypted; the JSONL is plain text on disk.
  - **No data-retention or deletion policy.** Data lives as long as the
    demo session/database does, with no expiry or purge mechanism.
  - **`/hr` and `/finance` now have real server-side session
    authentication** — `auth.py` verifies the role code server-side and
    issues a signed, HttpOnly, 8-hour session cookie (`flask.session`);
    `GET /api/submissions*` (real PII and bank details) requires an `hr` or
    `finance` session, `.../decide`, `.../export`, and
    `/api/razorpayx/balance` require `finance` specifically. Verified live:
    an anonymous `curl` to `/api/submissions` now 401s, where it previously
    returned everyone's name/CTC/bank account/IFSC/email with zero auth.
    What's still true, stated plainly: accounts are **created by an owner
    through `/api/users`, not by self-registration**, and there is no
    password reset, no MFA, and no permanent lockout — sign-in throttling
    is a rolling per-IP and per-account window. `POST /api/submissions`
    (creating a submission) is deliberately left open, since
    `/optimize/batch`'s public audit-correction flow also calls it and
    exposes no one else's data by doing so — see the code comment on that
    route for the full reasoning. `SESSION_COOKIE_SECURE=False` for local
    HTTP dev; a real deployment behind HTTPS would need that flipped to
    `True`. See "Maker-checker review, demo-scoped" below — approve/reject
    still always requires a human click regardless of session, unrelated
    to this change.
  - **No server-side session revocation.** The session cookie is a signed,
    stateless `itsdangerous` token, not a lookup against a server-held
    session store — there's nothing to revoke server-side without adding a
    revocation table, which would contradict the deliberately minimal
    "no new tables beyond the review queue" design this auth system was
    reviewed and cleared against. `/api/auth/logout` clears the cookie on
    the client; it does not and cannot invalidate that cookie's signature
    before its 8-hour expiry if a copy of it existed elsewhere. An
    enterprise deployment would replace the shared demo codes with
    OAuth2/SAML through a real identity provider, which supports central
    token revocation as a first-class feature — this demo's shared-secret
    model deliberately does not.
  - **That one open route is rate-limited, not just unauthenticated.**
    Found in a live-defense pressure-test, not by inspection: staying
    open doesn't mean staying unguarded — a submitted row can carry
    attacker-controlled `bank_account_number`/`ifsc`, and if a reviewer
    approves a well-disguised fraudulent row among many legitimate ones,
    export generates a real payout payload to that account. Fixed with an
    in-memory, per-IP limit (20 requests/60s) on `POST /api/submissions`
    specifically — bounds how many attempts one source gets to slip a
    fraudulent row past review, without requiring the identity check that
    would break the public audit flow. Demo-scale, stated plainly: resets
    on restart, doesn't coordinate across multiple server processes behind
    a real load balancer — this is a real, named limitation, not a claim
    of production hardening. Distinct from sign-in throttling above — that
    limits repeated login *attempts* per IP and per account; this limits
    repeated *submission* attempts against the one route that stays open.
    Both are now real; they cover different doors.
  - **A sharper version of the same gap, flagged in external review and
    deliberately not rushed into a fix:** the limiter keys on
    `request.remote_addr`, which is a real, well-known failure mode behind
    a reverse proxy or load balancer — that value resolves to the proxy's
    own IP, not the real client's, silently collapsing every client onto
    one shared bucket and defeating the per-source limit entirely. A
    multi-worker deployment (Gunicorn/Uvicorn without a shared cache) has
    the same problem from a different angle — each worker process keeps
    its own in-memory count, so the effective limit multiplies by worker
    count instead of applying globally. The correct fix is a shared store
    (Redis) plus parsing `X-Forwarded-For` against a known, trusted proxy
    hop — and that second part is the part not to rush: get the trust
    boundary wrong and the header becomes attacker-spoofable by design,
    which reads as "fixed" while being less safe than the honest gap
    stated here. Left undone under this deadline for the same reason a
    rushed security build was correctly avoided earlier in this project —
    an admitted gap is a better outcome than a fix that only looks solved.
  - **The review queue does store employee PII, including bank details —
    named explicitly, not glossed over.** Employee name and CTC were
    always stored (needed for the dedupe check); as of the redundancy fix
    that unified new-hire structuring onto `/hr`, an offer's `band_min`/
    `band_max`/`bank_account_number`/`ifsc`/`email` are stored too, when
    HR supplies them — this is what lets an approved row generate a real
    RazorpayX payout payload later, rather than requiring the export
    modal's separate manual re-entry. It sits in the same unencrypted
    Postgres tables as everything else here — reading it requires a real
    `hr`/`finance` session (see above), but the "no encryption at rest"
    gap is still real and unaffected by that change. **What the Phase 1.1
    Postgres port DID change is the shape of that exposure, and the
    difference is worth stating rather than swapping a noun:** under the
    old single SQLite file, anyone with filesystem access to the machine
    could read it directly. Under Postgres they additionally need database
    credentials, and the `grosslo_app` role is subject to row-level
    security, so reading another tenant's rows needs more than file access.
    That is a narrower exposure, not a closed one — a superuser connection
    or the postmaster's data directory still reads everything, and nothing
    is encrypted. Real production use needs that closed before real bank
    details go anywhere near this schema. The audit log remains the one exception: it
    excludes names/bank details/emails by construction (see its own
    section below), and that claim is unaffected by this change.

  Named explicitly as a pre-production gap, not an oversight — the same
  discipline already applied to the LTA-utilization estimate, the
  Basic-salary statutory floor, and the no-live-dispatch boundary
  elsewhere in this document. **This paragraph used to say "real security
  infrastructure was deliberately not built for this submission" — that
  stopped being true partway through this build and the sentence went
  stale until this pass caught it.** Real session auth, route-level
  permission gating, per-user accounts, sign-in throttling and a submission
  rate-limit are all now real and described above, not simulated.

  **This passage was itself stale, and the irony is the point.** It claimed
  credit for catching staleness while asserting three things that Phases 1.1
  and 1.2 had already changed: no per-person accounts, no login rate-limiting,
  no production database. A disclaimer that boasts about being checked is not
  thereby checked. What's still genuinely absent — no encryption at rest, no
  password reset, no MFA, no permanent lockout — is named explicitly in each
  case above, rather than folded into one blanket line that ages badly.
- **The treasury forecast (`payroll_breakdown.treasury_forecast`) has no
  concept of history or an existing payroll baseline** — there's no database
  anywhere in this app, so the "capital required" figure is a literal sum
  over whatever structure(s) are in the current request, not a delta against
  a company's actual recurring payroll. The UI label says this explicitly
  ("capital required for these employees... not your full existing
  payroll") so it isn't mistaken for more than it is. See Roadmap below for
  what closing this gap actually requires.
- **The live treasury gate on `/finance` compares against total exposure,
  not time-phased need.** `payroll_breakdown.py` already tracks a
  `funding_deadline_hours_before_payroll` per structure, but the gate's
  "Required Treasury Funding" sums every pending row's full
  `total_capital_outlay` regardless of when each row's funding is
  actually due — a batch could technically be blocked by money not
  needed for weeks. Named here as a stated decision, not silently left
  for a reviewer to find: staging required funding against each row's own
  funding lead time is the next iteration; this one demonstrates the gate
  compares against something 100% real, not that it's fully time-aware
  yet.
- **State-level Professional Tax (PT) is now a real deduction line in
  `treasury_forecast()`, not a missing one.** Five states (Karnataka,
  Maharashtra, Telangana, Tamil Nadu, Delhi), an optional `work_location`
  on the `/hr` form and CSV schemas, and every slab re-verified live
  against a primary source, not carried over stale — see "what broke"
  below for the two real corrections that verification pass found.
  Additive by construction: omitting `work_location` reproduces the exact
  pre-PT figures, confirmed directly, not assumed.

## Regulatory currency — verified live on 2026-09-01, not assumed

India's payroll law changed substantially for FY 2026-27, and a codebase
that hardcodes statutory citations doesn't stay current on its own. This
section states exactly what was checked, against what, and what's still
open — the same "verify the source, don't trust recall" discipline that
caught the 271C citation error elsewhere in this document, applied to law
that changed after this build's own knowledge was formed, not just to a
citation that was wrong from the start.

**Confirmed current via live search, sources checked, not recalled:**
- The Income-tax Act 2025 replaced the Income-tax Act 1961 effective
  1 April 2026. Salary TDS moved from **Section 192 to Section 392**; the
  annual TDS certificate moved from **Form 16 to Form 130**.
- HRA's 50%-exemption metro-city list expanded from 4 cities to
  **8 — Delhi, Mumbai, Kolkata, Chennai, plus Bengaluru, Hyderabad, Pune,
  and Ahmedabad** — effective 1 April 2026. This build never hardcoded a
  city-name list anywhere (`city` is an abstract `"metro"`/`"non_metro"`
  flag the user selects) — so this law change doesn't correspond to a code
  defect here, only to a stale section citation (below).
- Section 10(13A) (HRA exemption) moved to **Section 11, read with
  ~~Schedule II~~ Schedule III, Table Sl. No. 11** — **corrected 2026-09-13,
  see below.** Section 80CCD(2) (employer NPS deduction) moved to
  **Section 124, read with Schedule XV** — the 10%/14% old-vs-new-regime
  rate split itself is unchanged and was already correct in
  `tax_engine.py`'s `NPS_80CCD2_CAP_PCT`.
- **Fixed in code**: every user-facing citation of the old section numbers
  (392/11+Schedule III/124) across `ai_layer.py`, `execution_trace.py`,
  `payroll_breakdown.py`, and this document — the old number is kept
  alongside the new one ("Section 124, formerly 80CCD(2)") since it's
  still the more recognizable, more-searched-for term, not because the old
  number is still correct on its own.

**Corrected 2026-09-13 — the HRA exemption's schedule number was wrong:**
- It is **Schedule III, Table Sl. No. 11**, not Schedule II. Schedule II is a
  different exemption schedule entirely (agricultural income, life insurance
  proceeds); Schedule III is *"Income not to be included in total income of
  eligible persons"*, and entry 11 of its Table is the rent allowance.
- **Verified from the primary source, and the chain is re-checkable.** CBDT's
  official *Income-tax Rules, 1962 vis-à-vis Income-tax Rules, 2026* utility
  maps **Rule 2A → Rule 279**, and Rule 279's own title is *"Limits for the
  purposes of Schedule III [Table: Sl. No. 11] to the Act"*. Rule 2A was
  headed *"Limits for the purposes of section 10(13A)"*. So the government's
  own rule title ties the HRA limits to Schedule III Sl. No. 11 directly —
  no inference from a third-party concordance is needed.
- **The 50%/40% split is unchanged**, and it is not in the Act at all:
  Schedule III Sl. No. 11 delegates it (*"to such extent as may be
  prescribed"*), exactly as s. 10(13A) delegated to Rule 2A. Rule 279 carries
  the percentages. Full text in `docs/PRIMARY_SOURCE_LOOKUP_TASK.md`.
- **Not re-checked, and therefore not asserted here:** *Section 124, read with
  Schedule XV* above. Section 124 itself is confirmed (the 2025 Act's
  s. 17(1)(h) refers to *"the scheme referred to in section 124(1)"*), but the
  Schedule XV pairing came from the same 2026-09-02 pass that produced this
  Schedule II error and has not been verified independently.

**Checked and found NOT to need a citation change:**
- Sections 7Q and 14B (`penalty_exposure.py`'s EPF interest/damages) are
  under the EPF & Miscellaneous Provisions Act 1952 — a different statute
  from the Income-tax Act entirely, unaffected by this renumbering.
- ~~**Section 17(2)(vii)**~~ — **THIS ENTRY WAS WRONG AND IS CORRECTED
  BELOW.** It should never have been in this list.

**Corrected 2026-09-13 — an entry in the list above that was not true:**
- **Section 17(2)(vii)** (the >₹7.5L aggregate PF+NPS perquisite rule behind
  Rule R5 and the payroll guardrail) **did move.** It is **Section 17(1)(h)**
  of the Income-tax Act, 2025, and the companion accretion provision moved
  17(2)(viia) → **17(1)(i)**.

  What this document said on 2026-09-02 was: *"re-checked … against multiple
  independent sources on the Income-tax Act 2025's actual salary chapter
  (Sections 15–17). Confirmed retained at its original number; not every
  section moved in the renumbering, and this was verified rather than assumed
  just because most of its neighbors did move."*

  **The interesting part is that most of that was right.** The 2025 Act's
  salary chapter *is* Sections 15–17. Section 17 *is* still the perquisite
  section. It *is* true that not every section moved. The sweep was not
  inventing anything.

  **It checked at section granularity and reported at sub-clause
  granularity.** "Section 17 is still perquisites" is true and was verified;
  "therefore 17(2)(vii) is retained" does not follow from it and was not. The
  1961 Act's 17(2) perquisite list was restructured into the 2025 Act's 17(1),
  so every sub-clause under it moved while the section number above it did
  not. A check one level coarser than the claim it is used to support will
  keep returning confirmations, and they will keep being real confirmations
  of a different proposition.

  That is a sharper failure than "someone guessed", and a more dangerous one,
  because the verification genuinely happened.

  The correction came from the primary source on 2026-09-13: CBDT's own
  parallel-reading comparison on `incometaxindia.gov.in`, which places 1961
  s. 17 beside 2025 s. 17. Verbatim text of both is in
  `docs/PRIMARY_SOURCE_LOOKUP_TASK.md`.

  **The rule itself was never wrong.** The Rs 7,50,000 aggregate ceiling and
  the three-fund composition (recognised PF, the notified pension scheme,
  approved superannuation) carried over unchanged. What was wrong was the
  citation, and the confidence attached to it.

  **Why this is left visible rather than quietly rewritten.** A verified
  citation must let an independent party redo the check. This one could not:
  the "multiple independent sources" were never named, so nobody could repeat
  the check and notice it had been run one level too coarse. And it went
  unchallenged for eleven days because it read as *more* rigorous than the
  entries around it — an explicit claim that something was verified rather
  than assumed is the last thing anyone re-checks.

**Resolved 2026-09-02 — previously left as an open gap below, now
confirmed and fixed in code:**
- **Section 201(1A)** (TDS late-deposit interest, in
  `penalty_exposure.py`) moved to **Section 398(3)**. The two earlier
  search attempts noted below found no confirmed mapping at the time;
  re-searching found it directly. Citation updated everywhere it appears —
  `penalty_exposure.py`, this document, and the penalty-scenario table's
  column header in the frontend.
- **Section 271C** (the section deliberately *not* modeled in the
  delayed-remittance feature, see above) moved to **Section 448**. Same
  update pattern: the historical "an early draft cited 271C and I caught
  it" story below keeps the old number, since that's the number that was
  actually wrong at the time — but the present-tense design explanation of
  what's excluded and why now cites Section 448.
- **Section 87A** (both regimes' rebate, `tax_engine.py`) moved to
  **Section 156**. This one was missed by the original 2026-09-01 sweep
  entirely — that pass covered the NPS/HRA sections a specific review
  raised, not every statutory reference in the product. A follow-up
  external review flagged the gap directly: a stale citation anywhere is a
  live symptom the whole citation surface wasn't re-swept, not an isolated
  miss. `REBATE_87A_THRESHOLD`/`REBATE_87A_MAX` keep their 1961-Act-numbered
  Python names, same precedent as `NPS_80CCD2_CAP_PCT` — only the citation
  text a user or judge would read was in scope.

No open citation gaps remain as of this sweep — every statutory reference
in `compliance_rules.md`, `ai_layer.py`, `tax_engine.py`,
`penalty_exposure.py`, `optimizer.py`, `execution_trace.py`, and every
frontend component that displays a section number was grepped and checked,
not just the ones a prior review happened to name.

**A real correctness gap, found, decided on, and fixed — not a citation:**
- **The Code on Wages 2025** (one of the four labour codes, effective
  21 November 2025, no grace period) requires basic pay + dearness
  allowance to be **at least 50%** of total remuneration; falling short
  triggers automatic reclassification of the excess allowances as "wages"
  for PF and gratuity purposes. `optimizer.py`'s `BASIC_PCT_MIN` was
  `0.40`, letting the search space recommend structures as low as 40%
  basic — below that legal floor, for every structure this tool
  recommended since 21 November 2025. This was a real, verified
  correctness gap, not a stale citation, in a file this project has
  treated as protected all along — first flagged here rather than
  silently patched, then fixed as its own deliberate change once the
  decision was made explicitly rather than assumed:
  - `BASIC_PCT_MIN` raised to `0.50` (the statutory floor) and
    `BASIC_PCT_MAX` raised to `0.60` (the same 10-point band width the old
    40–50% range had, repositioned above the floor instead of collapsing
    the search space to a single point at exactly 0.50).
  - Rule R1 (`compliance_rules.md`, `ai_layer.py`) updated to match: the
    trigger threshold moved from "under 35% of CTC" to "under 50%," and
    the severity from Medium to High, since this is now real penalty
    exposure, not a soft market-convention flag.
  - The law technically allows a lower stated Basic if the excess
    allowances are legally reclassified as wages for PF/gratuity purposes
    instead — that mechanism was deliberately **not** built. This tool
    gives automated advice to people who aren't compliance officers;
    relying on "the paperwork says one thing, the law recalculates it as
    another" is exactly the fragile, audit-risk-prone pattern an advisory
    tool should steer people away from, not optimize into, and every
    real-world compliance source checked recommends the direct fix
    (raise Basic to ≥50%) over relying on the reclassification safety
    net — that's where actual HR/payroll practice has converged. The law
    is also ~9 months old with rules still being finalized state by
    state; modeling the reclassification mechanism precisely would be
    real legal-logic risk this project shouldn't take on under a 4-day
    deadline.

## Roadmap toward a real product (explicitly out of scope for this submission)

This was built to demonstrate the core mechanism correctly, not to be
production-complete — these are the specific, known next steps, not vague
future plans:

- **Persistence — and the decisions that come bundled with it, not
  sequentially after it.** Going from this build's fully stateless
  request/response model to one that remembers a company's roster over
  time is a genuine re-architecture, not an incremental feature. Three
  things have to be designed together, not added one at a time: a real
  database so the treasury forecast can show a company's steady-state
  payroll baseline (not just the incremental capital for whichever CSV was
  uploaded); **multi-tenant isolation**, so company A's payroll data is
  never reachable from company B's request the moment more than one
  company's data exists in the same system; and a **system-of-record
  decision** — does grosslo become the source of truth for a company's
  compensation data, or does it ingest from and stay in sync with
  RazorpayX Payroll or whatever HRIS a company already runs. None of these
  three is answered yet, and none of them can be answered independently of
  the other two.
- **Live RazorpayX dispatch, gated behind real OAuth and a human-approval
  step** — today the export stops at generating a correct payload on
  purpose; going further requires real credentials and an audit trail
  before any actual payout is safe to trigger automatically.
- **Ecosystem-partner integration** — distributed to companies already on
  RazorpayX rather than as a standalone tool competing for signups.
- **Wider compliance and tax coverage, named specifically rather than left
  as a direction.** The current 6 rules and the tax engine's scope (no
  surcharge, single income source, resident individuals only) don't yet
  cover the messier reality of real payroll: mid-year joiners and leavers
  with pro-rated CTC, multiple income sources, prior-employer TDS
  certificates, bonuses and variable pay, and ESOP taxation. Each of these
  needs its own scoping work, ideally reviewed by a practicing CA before
  being trusted at real enterprise scale — the same discipline that caught
  the 271C citation error above.
- **Closing the audit-mode loop further — this is now partially built, not
  fully.** The maker-checker review flow and the Bulk Salary Revision
  export (see the dedicated section above) take a flagged employee from
  "here's an issue" to a real, reviewable, approved correction and a
  downloadable revision file. What's still roadmap, not built: any actual
  RazorpayX-side application of that correction — the export produces a
  file for manual upload, it doesn't touch RazorpayX at all, matching the
  no-live-dispatch boundary drawn everywhere else in this project.
- **Who actually operates this, day to day — an open product question,
  not yet a design decision.** HR, a payroll admin, an individual employee,
  or an API Razorpay's own systems call internally are all plausible, and
  each implies a different permission model and a different UI. This
  build doesn't answer it yet.

## What broke during development (and what that caught)

- **The payout payload paid gross salary, from 2026-08-31 to 2026-09-21**
  (`PAYOUT_NET_AMOUNT_DESIGN.md`). `_build_composite_payout()` set `amount` from
  the whole monthly cash salary, in a variable named `net_monthly`, withholding
  nothing. On the recommended ₹18L structure in Karnataka it paid ₹1,39,200 where
  ₹1,17,851.47 was owed — ₹2,56,182 a year per employee, with that month's TDS and
  PF left unremitted.
  - **How it survived:** no test pinned the amount, and
    `payroll_breakdown.net_monthly_disbursement()` — which withheld PF and TDS,
    though not professional tax — sat beside it with **no callers at all**. A
    correct-looking function nobody calls is not a safety net; it is a decoy.
  - **What it cost to keep quiet:** nothing dispatches money, so no payment was
    ever made. The export screen renders the payload and offers *Copy*, though,
    so the realistic path was a person pasting it into RazorpayX.
  - **The fix:** the amount now comes from the same treasury forecast the
    response already returns, so the payload and the forecast cannot disagree.
    The unused function was deleted rather than left as a second definition of
    "net pay".
  - **Found** while measuring the blast radius of a different bug, which is the
    argument for measuring wider than the change under review.
- **The tax engine double-counted employer NPS, from the first version until
  2026-09-16** (`TAX_ENGINE_EMPLOYER_NPS_DESIGN.md`). `taxable_income_for_structure()`
  left the employer's contribution out of gross salary and subtracted it anyway,
  uncapped. So every structure with employer NPS showed too little tax: 12–24% of
  the tax owed above ₹20L CTC, up to 80% between ₹10L and ₹20L, and ₹0 where up to
  ₹82,419 was owed.
  - **What it also changed:** the recommended regime or structure in 111 of 1,140
    NPS-on cases, and 68 routing decisions, all towards escalation. No row was
    fast-tracked that should not have been.
  - **How it survived:** the tests pinned what the code returned, not what the Act
    says. The first measurement sampled 36 hand-picked cases and missed every
    changed recommendation.
  - **The fix (`02d05a8`):** add the contribution to salary (s. 16(k)) and deduct
    it only up to the cap (s. 124). It is pinned by tests that derive the expected
    figure from the statute and were committed failing first.
  - **Rows already stored:** they are not recomputed. Those computed before the fix
    carry a `tax_basis` and are flagged when read, with the reason shown to the
    approver.
- An early draft of the 87A rebate function was left in a broken, duplicate
  state after an editing false-start, before the final version replaced it.
  Caught by review before it reached production logic.
- A test asserting "salary up to ₹12.75L is tax-free" initially failed — not
  because the engine was wrong, but because the test fed the engine *taxable*
  income where the ₹12.75L figure actually refers to *gross* salary before
  the ₹75,000 standard deduction. The engine was correct; the test needed
  fixing — catching your own test being wrong is a stronger signal than
  catching a bug in the code itself.
- The optimizer's `basic_pct` search initially had no upper bound. A pure
  tax-minimizing search with no ceiling pushes basic toward unrealistic
  levels, since more basic mathematically shelters more income via employer
  PF/NPS. A 50% ceiling was added as an explicit, documented tradeoff. (The
  band itself moved later — see "Regulatory currency" above — but the
  reasoning for having a ceiling at all, stated here, is unchanged.)
- While building the delayed-remittance penalty scenario, an initial draft
  included a Section 271C figure paired with the deposit-delay case this
  feature models. Independent verification against the actual Supreme Court
  ruling (not just training-data recall) caught that 271C legally cannot
  apply to that scenario, and it was removed before shipping rather than
  left in — the exact kind of citation error a feature built around "real
  citations, not hallucinated" can't afford to make.
- The hypothetical-recalc query path (`/api/query`, "what if my rent were
  X") had never been run against the real Claude API before a live test
  pass caught that its numeric guard was silently rejecting almost every
  real answer: the guard's allow-list checked the recalculated tax figures
  but not the changed parameter's own new value, which any natural-language
  answer restates as a matter of course ("if your rent were ₹2,00,000..."),
  so the feature was quietly always falling back to its templated response.
  The deterministic-fallback test suite couldn't have caught this — it
  exercises the fallback path directly, not the guard logic that sits in
  front of a real LLM response. Fixed by adding the changed value to the
  guard's allow-list when it's numeric.
- A second, different bug in the same numeric guard, found while wiring
  its rejection state into the UI for the first time, not by inspection:
  in both branches of `answer_query()`, `guard_triggered` was computed
  correctly inside the try block, but the fallback return two lines down
  always hardcoded `"guard_triggered": False` — discarding the real
  computed value whenever the guard had actually just fired. A genuine
  live rejection would have silently reported itself as "nothing
  happened." `explain_result()` and `negotiate()` never had this bug, only
  the query layer's two paths did. Fixed by declaring `guard_triggered`
  outside the try block in both places. New tests mock only the external
  Claude call (a fabricated response stating an untraceable number) — the
  guard logic, the fallback text, and the True/False it reports are all
  real; this is the guard's rejection branch getting automated coverage
  for the first time, not just the pass-through branch.
- `/api/optimize-batch` had never been load-tested. With a live API key, a
  20-row batch didn't complete inside 60 seconds, and a 500-row batch
  didn't complete inside 2 minutes. Measured, not assumed: isolating the
  same 20-row batch with the AI layer off completed in 0.11 seconds — the
  entire cost was one sequential, blocking Claude API call per row to
  generate that row's prose explanation. Checked whether that explanation
  was actually used anywhere: `batch-results-table.tsx` renders only
  row/CTC/regime/saving/guardrail columns — the explanation text was
  computed and then discarded on every single row, in every batch, before
  this was found. Fixed by skipping that AI call in batch mode specifically
  (originally `explain_result(..., skip_ai=True)`); the single-candidate
  flow, where the explanation is actually shown, is untouched.
  `/api/optimize-batch` itself no longer exists — it was the "New Hire
  Batch" mode's route, removed as part of the redundancy fix below.
  **This wasn't actually the full fix, discovered much later**: months
  after this landed, a real 10-row `POST /api/submissions` batch was
  measured at ~79s — the skip had carried forward correctly, but a
  second, unrelated AI call (`flag_compliance()`'s compliance-flag
  rephrasing, added after this original fix shipped) had no equivalent
  skip and brought the batch back down to only ~55s, not fast. Profiling
  each sub-call in isolation — not guessing which one was slow — found
  the actual dominant cost was a *third* function, `negotiate()`
  (~5.5s/row on its own), called unconditionally for every correction row
  with no skip flag at all, the same "computed and silently discarded"
  pattern as the very first fix, just in a sibling function nobody had
  re-checked. All three are gated by one renamed `skip_ai` parameter now.
  Net result: the same 10-row batch that took ~79s now takes ~0.1s; a
  45-row batch (the real audit-sweep CSV's actual flagged-row count)
  completes in ~0.4s, down from a would-be ~6 minutes.
- **The numeric guard extended to compliance-flag and guardrail-check
  phrasing had a bug in its own safety check, caught in code review, not
  by a test written after the fact.** Once `orchestration.py` started
  surfacing AI-phrased compliance/guardrail text as the stated reason for
  a routing decision, a numbers-only guard turned out to be insufficient
  — a rephrasing could keep a number grounded and still flip the
  conclusion ("exceeds the ceiling" reworded as "is within the ceiling").
  A second, polarity-aware check was added, grounded in this codebase's
  own rationale-template vocabulary rather than a guessed keyword list.
  The first version of that check false-positived on a *correctly
  negated* rephrasing of a real violation — "the structure is **not**
  compliant" contains the bare substring "compliant" and tripped the
  guard as if it were the soft-pedal it exists to catch. Fixed with a
  negation-aware check. A second review round caught the same bug's
  hyphenated form ("**non-compliant**"), missed by the first fix's
  negation-word list and character class — fixed by normalizing hyphens
  to spaces before matching, then deliberately stopped hardening the
  marker lists further once two related gaps had been caught in a row —
  stated explicitly in the code as a known, bounded limitation rather
  than implied as a closed problem.
- The salary-revision export's honesty-label header hung the dev server
  on the first real request against it, not in testing against mocked
  data. `X-Template-Honesty-Label` carried the label text verbatim,
  including an em dash — HTTP header values have to be Latin-1-encodable,
  and the em dash isn't, so werkzeug threw a `UnicodeEncodeError` mid
  response and the client hung waiting for a response that never
  finished. The file's own Read Me sheet keeps the original Unicode text
  fine (a spreadsheet cell has no such constraint); only the header copy
  needed sanitizing. Caught by actually calling the endpoint over real
  HTTP with a timeout, not by reading the code — this is exactly the kind
  of bug that inspection alone doesn't surface.
- **Building state Professional Tax, the initial spec's own draft figures
  were wrong in two places — caught by verifying against a primary
  source before writing the table, not after.** Karnataka's PT exemption
  threshold was drafted at Rs 15,000, which was correct once but moved to
  Rs 25,000 under a 2025 amendment already in force — a hardcoded Rs
  15,000 figure would have overcharged every real salary between the two
  thresholds from day one. Tamil Nadu's Greater Chennai Corporation slab
  was drafted as a simple 2-tier approximation; the real slab is a 6-tier
  half-yearly table, confirmed by fetching tnswp.com's own PDF directly
  — not an aggregator's summary, which for this specific table gave
  numbers that didn't match the government source when checked side by
  side. Both fixed before the table shipped, using the primary source's
  real figures rather than the numbers the spec happened to propose.

## Test coverage

615 tests across 18 files, all passing with no skips — measured at
commit `0277b6a` with `python3 -B -m unittest discover -s tests`, not
estimated. Re-run it yourself to confirm. The commit is part of the claim:
`tests/` changes often here, so a bare number goes stale silently, and if
you are on a later commit you should trust your own run over this sentence.

Note that counting `def test_` in the source undercounts the suite: at
`0277b6a` that gives 609, while the runner reports 615. The six-test
difference is deliberate —
`TestAnswerQueryRejectsSectionsItNeverSupplied` in
`tests/test_query_guard_citations.py` subclasses
`TestAnswerQueryServesAnswersThatCiteWhatItSupplied`, re-running its six
parent tests with the membership check in place.

- **82 in `tests/test_finos.py`** — the marginal relief calculation
  (validated against the government's own worked example), the
  old-vs-new regime crossover, HRA metro vs non-metro, the PF
  statutory-ceiling toggle, extraction's mismatch-detection logic, the
  explainer's numeric guard (including that batch mode's `skip_ai` path
  stays deterministic and that the conversational query layer's guard
  genuinely rejects an untraceable number and reports that it did, not
  just that it passes a traceable one), each compliance rule's trigger
  condition, the conversational query layer's hypothetical-recalculation
  path, the Code on Wages 2025 statutory-floor fix (the search space
  is genuinely 10 points wide, R1 fires at the correct boundary, and
  `naive_baseline_tax()`'s hardcoded 0.50 is explicitly tied to
  `BASIC_PCT_MIN` so the two can't silently drift apart), the numeric+
  polarity guard on compliance-flag/guardrail-check phrasing (including
  the negated-marker and hyphenated-negation cases found in review), the
  NPS 10%/14% old-vs-new-regime rate differential (re-verified live
  during the Income Tax Act 2025 citation sweep, since the citation text
  had gone stale but the underlying rate logic had never actually been
  tested directly), and the state Professional Tax table (Karnataka's
  and Tamil Nadu's corrected-live slabs, the Karnataka/Maharashtra
  February bump landing at the real Rs 2,500 annual ceiling, Delhi's
  confirmed-zero distinguished from an unrecognized `work_location`, and
  `treasury_forecast()`'s net-disbursement identity holding with PT
  folded in as a fourth term).
- **57 in `tests/test_review_workflow.py`** — the maker-checker flow end
  to end: submission persistence, approval writes the correct
  simulated-not-dispatched status, rejection requires and stores a
  reason, the diff view's before/after values match a real optimizer run
  exactly, mixed-batch rows are decided independently, duplicate
  submissions are flagged rather than reprocessed, a double-approve
  doesn't double-write, the salary-revision export's XLSX contains the
  real corrected values with the honesty label present, exports are
  gated on approval, bank details flow through correctly, the batch
  audit's clean/flagged/exception counts match a hand-verified mix of
  rows, the dedup-collision fix (same name+CTC, different email, no
  longer collide; same candidate's same-day resubmission still does),
  `orchestration.route` on `/api/batch-audit` matched against a real
  hand-counted tally of `auto_pass_candidate` rows (the exact computation
  the batch executive summary's Compliance Clean Rate does client-side),
  and `treasury_forecast`'s presence plus its own internal
  net-take-home+TDS-escrow+EPFO-challan identity on submission rows (what
  the live treasury gate on `/finance` sums for Required Treasury Funding).
- **19 in `tests/test_orchestration.py`** — every routing outcome
  (`auto_pass_candidate`/`needs_review`/`guardrail_not_run`/`escalate`)
  against real `flag_compliance()`/`evaluate_band_guardrail()` output,
  including the two gaps found during plan review before this shipped: a
  High-severity flag and a failing guardrail on the same row (proves the
  `reasons` ordering, not just the route), and two different-severity
  flags on one row (proves the aggregation picks the higher one, not
  just that the logic reads correctly).
- **51 in `tests/test_auth.py`** — login/logout/session-check against
  real correct and incorrect codes, that protected routes 401 with no
  session and succeed with the right role, that the wrong role (HR on a
  Finance-only route) is rejected specifically — not just "any login
  passes" — and the explicit regression guard that `POST
  /api/submissions` (create) stays open with zero session, since a
  future "fix" gating it would break `/optimize/batch`'s public flow.
- **13 in `tests/test_razorpayx_client.py`** — the not-configured and
  live-key-refusal guards, plus one test that genuinely round-trips to
  RazorpayX's real server with a deliberately fake key and confirms a
  real `401` comes back, proving requests actually leave the machine
  rather than hitting a local stub.

The thirteen files the list above predated, which together are most of the
suite. Counts at `0277b6a`:

- **91 in `tests/test_compliance_rules.py`** — the rule set as data (Phase
  2.2): that the count is derived rather than declared, that active and
  candidate rules partition the set, that the candidate gate holds in both
  directions, and that the protocol is enforced rather than merely documented.
- **85 in `tests/test_legal_claims.py`** — the legal claim inventory (Phase
  2.4): the mechanism proved by probes independently of the inventory it
  holds, that a claim has no inert state, and that the value check compares
  two real copies rather than a copy against itself.
- **50 in `tests/test_tenant_isolation.py`** — the Phase 1.1 exit criterion:
  two companies in use simultaneously with zero leakage, asserted at the
  application layer and again at RLS as an independent layer, plus per-tenant
  payout source accounts and audit-log isolation.
- **40 in `tests/test_rationale_guard_citations.py`** — that citation digits
  are not grounding: a section number in a rationale must not license
  restating that number as a figure, and grounding can only narrow.
- **27 in `tests/test_output_boundary.py`** — the second enforcement layer for
  the numeric guard, which trusts no call site to have supplied a correct
  allow-set, including against real AI-backed responses.
- **24 in `tests/test_query_guard_citations.py`** — the guard's citation-token
  exemption: supplied references are not figures, what only looks like one is
  still checked, and an answer citing what was actually supplied is served
  rather than spuriously rejected.
- **23 in `tests/test_identity.py`** — Phase 1.2's exit criteria: the
  permission matrix driven by every role against every guarded route,
  cross-tenant user isolation, and that guard order cannot reintroduce the bug.
- **16 in `tests/test_rationale_guard_scope.py`** — per-line grounding: each
  rephrased rationale is checked against its own flag rather than one pooled
  set, with one model call per flag.
- **10 in `tests/test_usage_tracking.py`** — that every model call is accounted
  for, that usage is recorded, and that no behaviour changed.
- **9 in `tests/test_pipeline_baseline.py`** — the Phase 2.1 characterization
  baseline, asserted against a fixture committed before the restructure began.
- **8 in `tests/test_employer_nps_statute.py`** — employer NPS pinned to the
  statute rather than to the engine (s. 16(k), s. 124(1)–(2)), including named
  cases where the fix changes the advice.
- **7 in `tests/test_pipeline_stages.py`** — that every declared stage actually
  runs, and that a dropped stage fails by name.
- **3 in `tests/test_execution_trace.py`** — the POLICY_GATE stage returned by
  `/api/guardrail`, which nothing covered before.

All pass with no `ANTHROPIC_API_KEY` set, exercising every deterministic
fallback. With a real key set (live Claude calls active), a small number
of AI-backed-path tests in `test_finos.py` can flake — confirmed
unrelated to correctness by passing cleanly in isolation; it's the same
tests expecting deterministic-fallback wording that get a live AI
response instead in that specific environment, not a real regression.

**The live LLM-backed path has been tested end-to-end against the real
Claude API**, not just its deterministic fallback: extraction, explanation,
compliance-flag phrasing, query classification, and the hypothetical-recalc
query path were each exercised with a real `ANTHROPIC_API_KEY` and their
output checked against the deterministic figures they're supposed to be
grounded in. This testing caught one real bug — the hypothetical-recalc
numeric guard's `allowed` set was missing the changed parameter's own new
value (e.g. a restated rent figure), so any live answer that naturally
repeated the number from the question (nearly all of them) was spuriously
guard-rejected and silently fell back to the templated response, even though
nothing was actually wrong with the answer. Fixed in `ai_layer.py` by adding
the new numeric value to the guard's allow-list when the changed parameter
is itself a number (`rent_paid`/`ctc`) — the full suite passed at the time,
same as it does today.
