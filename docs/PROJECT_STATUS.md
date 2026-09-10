# Project status — what shipped, and who is holding what is left

**Standing artefact. Update this at every phase close, before the merge.** It is
maintained by hand rather than generated: what a phase left undone, and who has
to act on it, is a judgement no script can derive from the code.

Its purpose is to be the single place someone can read to know where a
multi-phase effort with real human dependencies actually stands, without
reconstructing it from separate closing reports.

_Last updated: 2026-09-10, at the close of Phase 2.4._

---

## The four phases on `main`

| Phase | Shipped | Waiting on a person |
|---|---|---|
| **1.1** Multi-tenancy | Postgres row-level security, `FORCE ROW LEVEL SECURITY`, transaction-scoped `SET LOCAL app.tenant_id`, startup assertion that RLS is actually enforceable | — |
| **1.2** Identity & RBAC | Permission-based `require_permission`, order-independent guards, login timing oracle closed (77× → 1.02×), audit-log split into two sinks | 1 frontend file uncompiled (`finance-flow.tsx`) |
| **2.1** Pipeline orchestration | Declared `STAGES` sequence, `stages_run` in the API response, characterization baseline | 1 frontend file uncompiled (`api-types.ts`) |
| **2.2** Compliance rule breadth | Rule set as data with one source of truth, candidate-rule protocol with six steps, generated rules table, `compliance_pct` reports its denominator | **CA review packet** — 2 candidate rules + 5 questions on live rules. 1 frontend file uncompiled (`ring-metric.tsx`) |
| **2.4** Legal claim inventory | `provenance.py` evidence model, `Claim` record with no inert state, 4 `tax_engine` claims, drift check, ranked review queue over both carriers | **4 unverified claims**; **browser lookup** for R5's successor provision |

## The honest state of the compliance work

Phases 2.2 and 2.4 together built the machinery for knowing whether this tool's
legal claims are correct. **That machinery currently reports that none of them
are confirmed.**

Stated plainly and not rounded up, because it would be easy to let *"we built
the system that tracks this"* slide into sounding like *"this is tracked and
fine"*: **2.4 shipped a measuring instrument, not a fix, and the thing it
measures currently reads zero.** Replacing an unexamined assumption with a
measured, named gap is real progress. It is not the same claim as the gap being
closed.

Every remaining step needs a person, not more code.

## Dates outstanding

| Date | What | Status |
|---|---|---|
| **2026-09-13** | Primary-source browser lookup (`docs/PRIMARY_SOURCE_LOOKUP_TASK.md`) — two lookups, one session, 15–30 min | **Not started.** Highest priority despite being smallest: R5 is ACTIVE and fires on real structures citing the repealed Income-tax Act, 1961 |
| **2026-10-10** | CA packet escalation trigger — if no reviewer engaged, escalate finding one | Not started |
| **2026-11-09** | Check-in on the build-block date, 30 days out | Pending |
| **2026-12-09** | An unverified claim becomes build-blocking | **4 claims pointed at it, no verified path to clearing any of them.** This is why 2026-11-09 exists |

## Next inventory batch — `optimizer.py:BASIC_PCT_MIN` leads

Not first among equals in a list: **the specific priority, ahead of everything
else in `LEGAL_CLAIM_INVENTORY_DESIGN.md` §10.1.**

Two things are true of it at once, and no other claim in this codebase has both:

1. It is the most load-bearing threshold in the optimizer — it constrains every
   structure the tool recommends.
2. It has a **proven history of actually having been wrong**, caught only
   because a human happened to look.

It is also the claim Phase 2.4 was named after and did not cover.

After it: `payroll_breakdown.py`'s five state PT tables (largest and most
frequently amended block), `penalty_exposure.py`'s EPF/TDS sections,
`tax_engine.py`'s five remaining figures, and the section citations in
`ai_layer.py` / `execution_trace.py` / `orchestration.py`.

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
