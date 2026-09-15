# Project status — what shipped, and who is holding what is left

**Standing artefact. Update this at every phase close, before the merge.** It is
maintained by hand rather than generated: what a phase left undone, and who has
to act on it, is a judgement no script can derive from the code.

Its purpose is to be the single place someone can read to know where a
multi-phase effort with real human dependencies actually stands, without
reconstructing it from separate closing reports.

_Last updated: 2026-09-15, after the D1 approvals and blast-radius check
(`TAX_ENGINE_EMPLOYER_NPS_DESIGN.md` §8). Earlier the same day, after the R1/TE4 record updates
(`R1_TE4_RECORD_UPDATE_DESIGN.md`). Before that, 2026-09-14, after the R5 citation
propagation (`R5_CITATION_PROPAGATION_DESIGN.md`) and the gap-owner table below. Previously
2026-09-13, at the close of Phase 2.4b._

---

## The phases on `main`

| Phase | Shipped | Waiting on a person |
|---|---|---|
| **1.1** Multi-tenancy | Postgres row-level security, `FORCE ROW LEVEL SECURITY`, transaction-scoped `SET LOCAL app.tenant_id`, startup assertion that RLS is actually enforceable | — |
| **1.2** Identity & RBAC | Permission-based `require_permission`, order-independent guards, login timing oracle closed (77× → 1.02×), audit-log split into two sinks | 1 frontend file uncompiled (`finance-flow.tsx`) |
| **2.1** Pipeline orchestration | Declared `STAGES` sequence, `stages_run` in the API response, characterization baseline | 1 frontend file uncompiled (`api-types.ts`) |
| **2.2** Compliance rule breadth | Rule set as data with one source of truth, candidate-rule protocol with six steps, generated rules table, `compliance_pct` reports its denominator | **CA review packet** — 2 candidate rules + 5 questions on live rules. 1 frontend file uncompiled (`ring-metric.tsx`) |
| **2.4** Legal claim inventory | `provenance.py` evidence model, `Claim` record with no inert state, 4 `tax_engine` claims, drift check, ranked review queue over both carriers | — superseded by 2.4b below |
| **2.4b** Inventory expansion | **17 claims across five files**, including `optimizer.py`'s `BASIC_PCT_MIN`. `instrument_kind`, value-less claims, key paths, `known_divergence`, the §5.1 verified rule | **14 unverified claims** (TE4's citation verified 2026-09-14); no human has signed off on anything. *(The browser lookup for R5 that was listed here is done — 2026-09-13.)* |

## The honest state of the compliance work

Phases 2.2, 2.4 and 2.4b together built the machinery for knowing whether this
tool's legal claims are correct.

**It is no longer reading zero.** Three claims now carry verified citations. TE4, the
employer-NPS cap, was verified from the primary source on 2026-09-14 by the repeatable
browser method below. The first two were PT1
Karnataka, cited by named amending Act, and PT4 Tamil Nadu, checked against the
government's own PDF. They arrived from an unplanned direction: `payroll_breakdown.py`
had already done the work properly and, crucially, **named the documents**. Three
other states got the same diligence on the same day and no names, and are
unresolved. That difference — what got written down — is the entire difference in
outcome, and it is the clearest argument in this repository for §5.1.

**14 of 17 claims remain unverified, and nothing at all has been signed off by a
qualified human.**

Stated plainly and not rounded up, because it would be easy to let *"we built
the system that tracks this"* slide into sounding like *"this is tracked and
fine"*: **2.4 shipped a measuring instrument, not a fix. It now reads three out of
seventeen.** Replacing an unexamined assumption with a measured, named gap is
real progress. It is not the same claim as the gap being closed.

Every remaining step needs a person, not more code.

## Dates outstanding

| Date | What | Status |
|---|---|---|
| **2026-09-13** | Primary-source browser lookup (`docs/PRIMARY_SOURCE_LOOKUP_TASK.md`) — two lookups, one session, 15–30 min | **Done 2026-09-13, from the primary source.** R5: 1961 s. 17(2)(vii) → 2025 **s. 17(1)(h)**, ceiling and fund composition unchanged; R5 has cited the in-force Act since `ca170d4`. HRA candidate: Schedule III, Table Sl. No. 11, percentages in Rules 2026 r. 279 — unblocked, not yet drafted. *(This row previously read "Not started", with R5 active on the repealed 1961 Act.)* |
| **2026-10-10** | CA packet escalation trigger — if no reviewer engaged, escalate finding one | Not started |
| **2026-11-09** | Check-in on the build-block date, 30 days out | Pending |
| **2026-12-09** | An unverified claim becomes build-blocking | **14 claims unverified.** Three are verified: PT1 and PT4 through a file that had already done the work, and **TE4 through the repeatable browser method** — CBDT's section browser and its parallel-reading Compare — on 2026-09-14. Verified is not cleared: TE4 still carries an unreviewed finding and an unreviewed divergence. *(Until 2026-09-15 this row said the method had cleared no claim yet.)* |

## Open gaps: owner and next action

_Added 2026-09-14. The table above lists dates; this lists gaps that were found
while working on something else. Each row names who holds it, so that "checked
that it doesn't affect my change" never becomes the last anyone hears of it._

Owners are records and roles, not sessions. Sessions end; records don't.

| Gap | Severity | Owner | Next action | Deadline |
|---|---|---|---|---|
| **The rationale guard: what is left after the fix.** *Updated 2026-09-15.* Steps 3–8 of `RATIONALE_GUARD_CITATION_DESIGN.md` shipped (`a98e83f` to `ef98fc2`, each suite- and sabotage-verified). Each rephrased line is now grounded only in its own flag's rationale; a rationale's citation digits no longer ground figures; and a line citing a section it was never supplied is rejected, at all four citing call sites. **Still open:** (1) lines for two *figure-free* flags (e.g. R3 and R6) returned in swapped order are still served, each with the other's reason; (2) an unparsed citation form ("s. 17(1)(h)", plurals) whose digits equal a real figure is not checked; (3) "Rs 2,025" in R1's own line (Act years deferred, decision 3); (4) `output_boundary.py` has the same citation/figure namespace problem, and one of its tests grounds a year by hand. | **Fail-open, but narrow.** The broad cases are closed: figures borrowed across flags, swapped lines with figures, citation-digit figures, and fabricated citations. (1) can still attach the wrong reason to a routing decision, but only between flags with no figures. | Numeric guard, `ai_layer.py`; `output_boundary.py` for (4). Decisions: project owner. | (1) needs a design, because a figure check cannot see it. (3) waits on the CA's ruling on packet question R1. (2) and (4): decide whether to address. | None formal. |
| **The tax engine double-counts employer NPS.** `taxable_income_for_structure()` leaves employer NPS out of gross salary and subtracts it anyway, so every NPS-opted structure's tax is under-stated by the tax on the whole contribution — measured: +₹23,587 at ₹18L CTC to +₹1,31,040 at ₹50L, 15–24% of tax owed. *(This row said "No recommendation changes"; false, see §8.7: the recommended regime or structure changes in 111 of 1,140 NPS-on cases.)* *Updated 2026-09-15, blast-radius check (`TAX_ENGINE_EMPLOYER_NPS_DESIGN.md` §8):* the liability and treasury **totals cannot move** (tax cancels in `total_capital_outlay`), but inside them TDS escrow is under-stated and net take-home over-stated by the same amount. Also wrong: the s. 398(3) penalty scenario (under), `optimization_value_pct` (about double), `annual_saving` (both directions), and batch `unclaimed_savings`/`clean_count` (an above-cap offer reads ₹0 and clean). **Routing:** reached through the regime; in 9,564 measured cases, 68 routes change, all `escalate` → `auto_pass_candidate`, none the other way. | **Wrong tax figure, live** for every structure with employer NPS, AI layer or not. | Tax engine, `tax_engine.py`. Decisions: project owner. | **D1-1 to D1-4 approved 2026-09-15** (Option B; redraft R7; record and visibly flag pre-fix submissions). D1-5 (`tax_basis` column; NULL reads pre-fix) and D1-6 (flag only) approved. **Waiting on D1-7, reopened** (§8.6: a pending pre-fix row can carry a different recommended structure; recommended option (b), flag reason in `orchestration.reasons`, no gate change). Then implement §5 as revised by §8.5. | None formal. It is live now. |
| **Treasury funding leaves out employer NPS.** `total_capital_outlay` reduces to `cash + employer_pf`; the employer's NPS remittance is in no component. An ₹18L structure with 14% NPS reports ₹16,74,000. Found 2026-09-15 (`TAX_ENGINE_EMPLOYER_NPS_DESIGN.md` §8.3), not caused by the double count. | Required Treasury Funding under-stated by the employer NPS of every pending row that has it. | Treasury path, `payroll_breakdown.py`. Decisions: project owner. | A design. It touches the treasury path, which carries the hard constraints. | None formal. |
| **The payout payload's amount is gross, not net.** `_build_composite_payout()` (`app.py`) sets `amount` from `(basic + hra + lta + special_allowance) / 12` in a variable named `net_monthly`; no TDS, employee PF or PT is withheld. `net_monthly_disbursement()`, which withholds them, has no callers. No test pins the amount. Present since `90e43cc` (2026-08-31); found 2026-09-15 (§8.3). | A wrong amount in an exported payment payload. Schema-only; no dispatch exists anywhere. | Payout path, `app.py`. Decisions: project owner. | A design, with a test pinning the amount first. Same hard constraints as above. **Owner, 2026-09-15: scope it soon, well before Phase 3 execution exists**, and not left queued indefinitely. | Before Phase 3 starts. |
| **An annual figure is labelled "Monthly".** The Executive Summary's "Total Monthly Payroll Liability" sums `total_capital_outlay`, which `treasury_forecast()` defines as annual; nothing divides by 12. The Treasury Gate compares the same annual sum to the live balance, so bulk-approve is blocked against a year of payroll: conservative, but not what the label says. Read from code, not run (no `node`); found 2026-09-15 (§8.3). | Mislabelled figure; the gate errs toward blocking. | Frontend, `executive-summary-card.tsx` and `finance-flow.tsx`. Decisions: project owner. | Decide what the banners should show: annual labelled as annual, or a real monthly figure. Owner, 2026-09-15: errs safe; queued behind D1. | None formal. |
| **R1 cites s. 2(y) of the Code on Wages, 2019, whose commencement is not verified.** The text and Act No. 29 were read from India Code on 2026-09-14; India Code lists only a partial 18 Dec 2020 notification, not one for s. 2. OP1 records the same proposition. | A statutory rule whose provision may not yet be in force — unknown, not known wrong. | Legal-claim inventory: R1 in `compliance_rules.py`, and OP1. | A person with a browser finds the Gazette commencement notification for s. 2 of the Code on Wages. Found: record it and mark the citation checked. The Gazette's search needs a keyword with no hyphen and dates as `dd-Mon-yyyy`. | 2026-12-09 (OP1 is a claim) |
| **R1's emitted text says "Code on Wages 2025"; its `instrument` says 2019. Added 2026-09-14: s. 2(y) is a deeming rule, and whether R1's predicate implements it depends on how allowances outside the exclusion list are read.** | A wrong year in user-facing text, pending a CA ruling. It also keeps one guard leak open (`RATIONALE_GUARD_CITATION_DESIGN.md` §4.6). | CA reviewer. Already tracked as packet question R1 (`docs/CA_REVIEW_PACKET.md`) and deliberately not restated here. | The CA rules on the packet question. | 2026-10-10 escalation trigger |

The full list of items the R5 propagation left open, including CA questions
already in the packet, is `R5_CITATION_PROPAGATION_DESIGN.md` §4.7.5. This table
covers only the rows above that have no other owner, plus the rationale guard's
residuals, the tax-engine double count, and the three treasury and payout gaps found while measuring it. With the guard's broad fail-open
cases closed on 2026-09-15, the tax-engine double count is the most severe open
item in the repository: a wrong tax figure, live, whether or not the AI layer
is configured.

**Closed 2026-09-14:**
- ~~`(Act 30 of 2025)` unverified but recorded as fact on TE1–TE4 and PE4~~ — the Gazette
  check could not settle it in one session — the Act's own entry was not located, and
  the subject lines inspected carried no act numbers, so the number would have to be
  read from a Gazette PDF — so it was **removed from all five**, matching
  R5. Commit `3f717f9`.
- ~~R1's and TE4's `citation_checked_on` say primary sources are unreachable~~ —
  **TE4** was verified from s. 124 on the primary source (`3f717f9`). **R1**'s reason
  was corrected: its text and act number are verified, and its commencement is
  not (`2521f3f`). That remaining part is the R1 row above.

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
- **Automated requests to primary legal sources are refused (HTTP 403)** —
  re-tested 2026-09-14 with default and browser headers alike. **The sources
  themselves are readable in an ordinary browser**, which is how both
  outstanding lookups were resolved on 2026-09-13. This entry used to say the
  sources return 403, full stop; that read two automated failures as a fact
  about the source and stood for four days. Practical consequence: legal
  lookups are a person-with-a-browser task, not blocked — see
  `docs/PRIMARY_SOURCE_LOOKUP_TASK.md`.
- **Verification runs `python3 -B`** with `~/Library/Caches/com.apple.python`
  cleared if anything looks inconsistent — see
  `LEGAL_CLAIM_INVENTORY_DESIGN.md` §9 for why this is standing rather than a
  one-off.
