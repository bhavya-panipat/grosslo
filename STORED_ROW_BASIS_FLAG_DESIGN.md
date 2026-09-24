# Do pre-D-S2 stored rows need a basis flag? — measurement and decision

**Status:** **measurement complete, decision pending.** No code is changed, and
**no flag mechanism is designed here** — deliberately, because the measurement
below makes the mechanism unnecessary. Decision D-S6 (§6) is the owner's.

**Why this exists.** Raised 2026-09-25 by the frontend session while it was
typing `reconciliation_gap` and `components_exceed_stated_ctc` as *optional* on
`OptimizeResponse` — because stored submission rows predate them. That typing is
correct, and it points at the half of D-S2 the fix stopped short of: `/api/submissions`
computes a row once and stores it, and the Finance queue and export routes read
**stored** values. So a correctness fix ships clean for new rows and leaves
historical rows on the old basis.

**This is the third instance** — `tax_basis` (D1-5), `treasury_basis` (D-T3), and
now this. The standing rule that follows from it is written into `CLAUDE.md`
rather than restated here.

**The severity ranking is not the argument.** I previously wrote that this was "a
stronger case than the tax figures had" because the figure is user-facing advice.
That was a ranking by argument, and this project does not accept one — D1's own
recommendation only became precise after a wider sweep found 111 real hits a
36-case grid had missed. So the ranking is set aside and the population is
measured instead.

---

## 1. What would be affected, if anything were

Only fields that are **stored** can outlive the fix. Enumerated from the code:

| D-S2 site | Stored? | Affected stored field |
|---|---|---|
| **A**, `/api/batch-audit` | **No.** Stateless route, nothing persisted. | — none. It has no history to flag. |
| **B**, `negotiate()` | **Yes**, inside `submission_rows.computed_json`. | `negotiation.total_annual_saving` and `negotiation.points`, which embeds the figure in prose. |
| **C**, `_build_current_structure()` | **Yes**, indirectly. | The whole row was computed against a structure whose `special_allowance` was rebuilt, so `compliance` and `guardrail` could differ too. |

**Both B and C require the row to have a `current_structure`.** `negotiate_stage`
returns early without one, and Site C only bites when a caller supplies a
`special_allowance` to rebuild. That is the condition the measurement turns on.

## 2. The measurement

Read-only, run 2026-09-25. Two stores, because the obvious one is not the only
one — `TAX_ENGINE_EMPLOYER_NPS_DESIGN.md` §8 established that on 2026-09-15 and
this measurement follows it rather than rediscovering it.

### 2.1 Postgres — the live store

Scanned every tenant, every row:

| | |
|---|---|
| Tenants | 2 |
| `submission_rows` total | **0** |

There is nothing stored at all. (Consistent with §8's finding of 0 rows on
2026-09-15: the suite creates and tears down its own rows.)

### 2.2 The pre-port SQLite store

`review_queue.db`, git-ignored, last written 2026-09-07. The app no longer reads
it, but `scripts/migrate_sqlite_to_postgres.py` copies it **verbatim**, so
anything in it would arrive with no basis recorded. This is the store that made
D1-5's population non-empty, so it is the one that matters.

All five rows, read individually:

| Submission | Row | Status | CTC | `current_structure` | Stored `total_annual_saving` |
|---|---|---|---|---|---|
| 2 | 0 | pending | ₹18,50,000.50 | **none** | none |
| 3 | 0 | pending | ₹24,00,000 | **none** | none |
| 4 | 0 | approved | ₹12,75,500.75 | **none** | none |
| 4 | 1 | rejected | ₹30,50,000.25 | **none** | none |
| 4 | 2 | pending | ₹9,75,000.10 | **none** | none |

**Not one of the five has a `current_structure`**, so not one ever had a
negotiation figure computed for it, and none can be affected by Site C either.
The `total_annual_saving` column is empty for all five because
`negotiate_stage` never ran on them — not because the figure happened to be
right.

### 2.3 Result

**The affected population is zero, in both stores.**

**And the set is closed, not merely empty today.** Every row written after
`939e3f7`/`e521d5b` is computed on the corrected basis, so the population cannot
grow. Unlike `tax_basis`, where rows kept arriving on the old basis until the
column shipped, there is no window here that is still open.

### 2.4 Magnitude, for completeness

If such a row existed, the error would be the live-route figures already
measured in `CTC_RECONCILIATION_DESIGN.md` §3: up to **₹3,61,670** of
negotiating leverage against a real saving of ₹0. That is the magnitude of the
defect, **not a measurement of any stored row** — there is no stored row to
measure. Stated separately so the two are not confused.

## 3. Recommendation: no flag

**Because there is nothing to flag, and nothing that can become something to
flag.**

The precedent points the same way. `TAX_ENGINE_EMPLOYER_NPS_DESIGN.md` §8.2
declined to flag rows with no employer NPS on the grounds that flagging
unaffected rows "would be noise that teaches people to ignore the flag." A flag
whose population is empty is the limit case of that argument: a badge beside
`TaxBasisBadge` and `TreasuryBasisBadge` that can never fire, on a queue where
the other two *can*, actively degrades the two that work.

**This is the same question D1-5 and D-T3 answered yes to, and the difference is
measured, not reasoned.** D1-5's population was not empty — 2 of those same 5
SQLite rows carry employer NPS, at ₹1,44,000 and ₹1,83,000. That is why it got a
column and this does not.

## 4. What would change the answer

Named so that "measured zero" does not become permanent by default:

- **A pre-fix backup is restored**, or any database predating 2026-09-25 is
  attached. Nothing in the repository evidences one, and the code cannot know.
- **`scripts/migrate_sqlite_to_postgres.py` is run against a different SQLite
  file** than the one measured here — one whose rows carry a `current_structure`.
- **Another deployment exists.** §8 recorded the evidence that none does: no
  Dockerfile, Procfile or platform config, no `DATABASE_URL` in `.env`, and only
  the `postgres` and `grosslo` databases on this machine. That is evidence about
  this repository and this machine, not proof nobody ever ran a copy elsewhere.

**If any of those happens, this decision is void and the flag is needed** — and
the detection mechanism is already free: a pre-fix row is identifiable by the
*absence* of `reconciliation_gap` from its stored `computed`, exactly as
`_pre_nps_remittance_flag()` identifies a pre-treasury-fix row by the absence of
`nps_remittance_annual`. No column and no migration would be required, which is
also why deferring this costs nothing.

## 5. Not in scope

The three D-S2 sites, which are fixed and verified. D-S3 and D-S4 from
`NEIGHBOURING_ROUTE_CLAIM_SWEEP.md`, which are separate open decisions. Any
change to what the Finance queue displays or to who approves a row.

## 6. Decision for the owner

| | Decision | Recommendation |
|---|---|---|
| **D-S6** | Add a read-time basis flag for pre-D-S2 stored rows? | **No.** The measured population is zero in both stores — Postgres holds no rows, and none of the five SQLite rows has a `current_structure`, so none ever carried the figure. The set is closed: every row written after the fix is on the corrected basis. A flag would be a badge that can never fire, beside two that can, which is the noise D1-4 §8.2 already rejected. **Recorded with its trigger conditions (§4) rather than dismissed** — if a pre-fix store is ever attached, the decision is void, and the mechanism costs nothing then because the absence of `reconciliation_gap` already identifies such a row. |

**If the owner prefers to ship it anyway**, the honest framing is that it is
insurance against §4 rather than a fix for anything now, it should be built on
the absence-of-field mechanism rather than a new column, and the frontend badge
should not be added — a badge that cannot fire is the part that does harm.
