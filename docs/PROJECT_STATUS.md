# Project status — what shipped, and who is holding what is left

**Standing artefact. Update this at every phase close, before the merge.** It is
maintained by hand rather than generated: what a phase left undone, and who has
to act on it, is a judgement no script can derive from the code.

Its purpose is to be the single place someone can read to know where a
multi-phase effort with real human dependencies actually stands, without
reconstructing it from separate closing reports.

_Last updated: 2026-09-13, at the close of Phase 2.4b._

---

## The phases on `main`

| Phase | Shipped | Waiting on a person |
|---|---|---|
| **1.1** Multi-tenancy | Postgres row-level security, `FORCE ROW LEVEL SECURITY`, transaction-scoped `SET LOCAL app.tenant_id`, startup assertion that RLS is actually enforceable | — |
| **1.2** Identity & RBAC | Permission-based `require_permission`, order-independent guards, login timing oracle closed (77× → 1.02×), audit-log split into two sinks | 1 frontend file uncompiled (`finance-flow.tsx`) |
| **2.1** Pipeline orchestration | Declared `STAGES` sequence, `stages_run` in the API response, characterization baseline | 1 frontend file uncompiled (`api-types.ts`) |
| **2.2** Compliance rule breadth | Rule set as data with one source of truth, candidate-rule protocol with six steps, generated rules table, `compliance_pct` reports its denominator | **CA review packet** — 2 candidate rules + 5 questions on live rules. 1 frontend file uncompiled (`ring-metric.tsx`) |
| **2.4** Legal claim inventory | `provenance.py` evidence model, `Claim` record with no inert state, 4 `tax_engine` claims, drift check, ranked review queue over both carriers | — superseded by 2.4b below |
| **2.4b** Inventory expansion | **17 claims across five files**, including `optimizer.py`'s `BASIC_PCT_MIN`. `instrument_kind`, value-less claims, key paths, `known_divergence`, the §5.1 verified rule | **15 unverified claims**; **browser lookup** for R5; no human has signed off on anything |

## The honest state of the compliance work

Phases 2.2, 2.4 and 2.4b together built the machinery for knowing whether this
tool's legal claims are correct.

**It is no longer reading zero.** Two claims now carry verified citations — PT1
Karnataka, cited by named amending Act, and PT4 Tamil Nadu, checked against the
government's own PDF. They arrived from an unplanned direction: `payroll_breakdown.py`
had already done the work properly and, crucially, **named the documents**. Three
other states got the same diligence on the same day and no names, and are
unresolved. That difference — what got written down — is the entire difference in
outcome, and it is the clearest argument in this repository for §5.1.

**15 of 17 claims remain unverified, and nothing at all has been signed off by a
qualified human.**

Stated plainly and not rounded up, because it would be easy to let *"we built
the system that tracks this"* slide into sounding like *"this is tracked and
fine"*: **2.4 shipped a measuring instrument, not a fix. It now reads two out of
seventeen.** Replacing an unexamined assumption with a measured, named gap is
real progress. It is not the same claim as the gap being closed.

Every remaining step needs a person, not more code.

## Dates outstanding

| Date | What | Status |
|---|---|---|
| **2026-09-13** | Primary-source browser lookup (`docs/PRIMARY_SOURCE_LOOKUP_TASK.md`) — two lookups, one session, 15–30 min | **Not started.** Highest priority despite being smallest: R5 is ACTIVE and fires on real structures citing the repealed Income-tax Act, 1961 |
| **2026-10-10** | CA packet escalation trigger — if no reviewer engaged, escalate finding one | Not started |
| **2026-11-09** | Check-in on the build-block date, 30 days out | Pending |
| **2026-12-09** | An unverified claim becomes build-blocking | **15 claims pointed at it.** Two are now verified, so a path exists — but it ran through a file that had already done the work, not through anything repeatable yet |

## The inventory — `BASIC_PCT_MIN` is DONE; what is left

**DISCHARGED 2026-09-13.** `BASIC_PCT_MIN` was named the specific priority for
the next batch and led Stage A of 2.4b. It is now claim OP1. The argument for
prioritising it is kept below because it is the reasoning, not the status:

Two things were known to be true of it:

1. It is the most load-bearing threshold in the optimizer — it constrains every
   structure the tool recommends.
2. It has a **documented history of actually having been wrong**, caught only
   because a human happened to look.

It is also the claim Phase 2.4 was named after and did not cover.

**Deliberately not stated as "no other claim has both"**, because at the time
only 4 of ~25 claims had been inventoried and that would have been a confident
assertion about territory nobody had examined.

**That caution was vindicated immediately.** Reading the three files for 2.4b
showed the provenance quality was INVERTED from what had been assumed:
`payroll_breakdown.py` carried the strongest evidence in the codebase and
`optimizer.py` the weakest of the three. `BASIC_PCT_MIN` still led — on risk,
being worst-evidenced *and* already wrong once — but the flat picture of "~21
claims all in the same unverified state" was simply wrong.

**`BASIC_PCT_MIN` is now inventoried (OP1), as are `payroll_breakdown.py` and
`penalty_exposure.py`.** What remains: `tax_engine.py`'s five deferred figures
(`CESS_RATE`, `EMPLOYER_PF_RATE`, `PF_WAGE_CEILING_BASIC`, `REBATE_87A_*`), and
the section citations in `ai_layer.py` / `execution_trace.py` /
`orchestration.py`.

Those citations need a decision first, not just work: **every claim so far
asserts a NUMBER**, and both `asserted_value` and the drift check assume one. A
claim asserting only a section number has nothing to compare. Whether those are
claims at all, or something else, is open.

## Standing environmental limitations

- **No `node` binary**, though `frontend/node_modules` is populated. Three
  frontend files across three phases are uncompiled and unverified — one
  limitation with three instances, tracked in README's *Known unverified
  surfaces* table.
- **Primary legal sources return HTTP 403** from this environment. Confirmed
  independently by two people. Third-party concordance resources are reachable;
  see `docs/PRIMARY_SOURCE_LOOKUP_TASK.md`.
- **Verification runs `python3 -B`** with `~/Library/Caches/com.apple.python`
  cleared if anything looks inconsistent — see
  `LEGAL_CLAIM_INVENTORY_DESIGN.md` §9 for why this is standing rather than a
  one-off.
