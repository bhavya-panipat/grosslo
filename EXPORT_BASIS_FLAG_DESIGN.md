# Carrying the basis flags into the exported payload — design (D-S3)

**Status:** design and measurement complete, **awaiting approval.** No code is
changed. Decision D-S3 (§6) is the owner's.

**Why now.** Found 2026-09-22 by the neighbouring-route sweep
(`NEIGHBOURING_ROUTE_CLAIM_SWEEP.md` §2.2). The owner asked for it next on
2026-09-26.

**Read §2 before §3.** The measurement changes this decision's justification,
though not — in my reading — its answer. It would be easy to implement this on
the strength of the sweep's recommendation alone and never notice that the
population is empty.

---

## 1. The defect

`review_queue._row_to_dict()` attaches `tax_basis_flag` and
`treasury_basis_flag` to every row it returns, and appends their reasons to
`orchestration.reasons`. `/api/submissions/<id>/rows/<i>/export` reads its row
through `get_submission()`, so **it holds both flags and reads neither.**
`app.py` does not contain the string `tax_basis` anywhere.

Verified end to end on 2026-09-22: a row forced to the pre-fix basis exports
`200` with a payload containing no trace of the flag.

**The flag reaches the Finance screen and not the payment instruction.** D1-4 and
D-T3 built the read-time mechanism so that a figure someone may act on says when
its basis is superseded. A payout payload is the document that gets acted on, and
it is the one surface the mechanism does not reach.

## 2. The measurement

Per `CLAUDE.md`'s *Measure the population before ranking severity*, which this
project adopted after D-S6 — and which applies to its own recommendations.

### 2.1 Which rows could be exported carrying a flag

Export requires `status == "approved"` **and** either bank details (the new-hire
path) or a `current_structure` (the correction path). A flag requires a pre-fix
basis.

| Store | Rows | Would carry `tax_basis_flag` | Would carry `treasury_basis_flag` | **Exportable and flagged** |
|---|---|---|---|---|
| Postgres (all tenants) | **0** | 0 | 0 | **0** |
| Pre-port SQLite `review_queue.db` | 5 | **2** | **0** | **0** |

The two flagged SQLite rows are `sub3 row0` (pending, employer NPS ₹2,01,600) and
`sub4 row1` (rejected, ₹2,56,200). **Neither is approved, and neither has bank
details or a `current_structure`**, so neither can reach the export route at all.
The one approved row has no employer NPS, so it would not be flagged.

**`treasury_basis_flag` fires on none of them, and the reason is worth stating
because I expected otherwise:** those rows predate the treasury forecast
entirely, so `_forecasts()` finds nothing, `stale` is empty, and the function
returns `None`. There is no stale forecast to detect — not a forecast that
happens to be current. Measured, not reasoned from the fix dates.

### 2.2 The flagged set is closed

`tax_basis` is written at insert as `nps-as-salary-capped`, which is the only
member of `_NPS_CORRECT_TAX_BASES`. **So a row created today is never flagged,
and the flagged set cannot grow.** Same shape as D-S6.

### 2.3 What this means

**The population this change would serve is empty today and cannot grow from
here.** Anything below is defense-in-depth against §5's trigger conditions, not
a repair of something currently wrong. Stating it plainly because the sweep's
recommendation reads as though it were fixing a live exposure, and it is not.

## 3. Why I still recommend implementing it, unlike D-S6

D-S6 measured zero and the recommendation was **don't build**. This measures zero
and the recommendation is **build**. The difference has to be stated, or the two
decisions look inconsistent and the measurement looks decorative.

| | D-S6 | D-S3 |
|---|---|---|
| Mechanism | would need a **new** one — flag derivation, a response field, a frontend badge | **already exists**; the flags are on the row object the route holds |
| Cost | a column-or-derivation decision plus frontend work | roughly three lines, no new derivation, no new state |
| Cost when inactive | **a badge beside two working ones that can never fire**, which teaches people to discount all three | **an absent key**. Nothing renders, nothing is shown, no one is trained to ignore anything |
| Nature of the gap | a consequence nobody had decided about | **an existing mechanism left incomplete by oversight**, whose own stated purpose is not served until it reaches the artefact that gets acted on |
| Flagged population | 0 rows, in any store | **2 rows exist and carry a flag** — they are merely not exportable |

**The last two rows carry the argument.** D1-4 and D-T3 decided that a figure
someone may act on should say when its basis is superseded. That decision is
already taken; this route simply does not implement it. And the noise objection
that killed D-S6 — a signal that can never fire degrades the ones that can —
does not apply to a key that is absent when there is nothing to say.

**The honest counter-argument**, recorded rather than argued away: this project
has just established that a measured zero is a legitimate reason not to build,
and building anyway on a zero population risks making that principle look
selectively applied. If the owner reads it that way, **record-and-defer is a
defensible answer** and §5's triggers make it recoverable. I do not think the two
are the same case, for the reasons above, but the objection is real.

## 4. Design

**Carry the flags. Do not refuse the export.**

- The payload gains `tax_basis_flag` and `treasury_basis_flag` **only when the
  row carries them** — absent otherwise, so a consumer never has to distinguish
  "no flag" from "this response predates the field" by reading a `null`.
- When either is present, the payload also gains
  `WARNING_BASIS_SUPERSEDED`, carrying the same reason text the queue shows —
  **the same two-surface treatment `WARNING_DO_NOT_UPLOAD` already gets in this
  route**, and for the same reason: a warning must survive the payload being
  piped, saved or handed on.
- **Not** an HTTP header. `X-Source-Account-Placeholder` exists because that
  warning concerns the whole response; a basis flag concerns the figures, and
  headers get dropped by every tool that reformats a body. The body is where a
  payment instruction's caveats belong. *(Stated because the precedent invites
  copying the header too, and I do not think it should be copied.)*
- **Nothing is recomputed and nothing stored is rewritten**, exactly as D1-4 and
  D-T3 settled. The payout amount, the forecast and the guardrail are untouched.

### 4.1 Why not refuse

D1-7(b) already settled that a pre-fix row's reasons say so rather than the route
blocking. A refusal would be a **new gate on work a human has already approved**,
which is a product decision about the maker-checker flow and not a completion of
a flagging mechanism. It also fails closed on rows whose figures may well be
right — the flag says *may be wrong*, not *is wrong*.

### 4.2 Not in scope

D-S4, the mixed computation bases in the same payload — separate decision, still
open. The per-row export's other fields. Any change to who approves a payout, or
to what the Finance queue displays.

## 5. What would make this live

The same triggers as `STORED_ROW_BASIS_FLAG_DESIGN.md` §4, and they are why
record-and-defer would be recoverable rather than final:

- a pre-fix backup is restored, or any database predating 2026-09-19 is attached;
- `scripts/migrate_sqlite_to_postgres.py` is run — **note that this alone is not
  enough**: the two flagged rows still could not be exported, because neither is
  approved and neither has bank details or a `current_structure`;
- another deployment exists. No deploy configuration is evidenced in the
  repository (`TAX_ENGINE_EMPLOYER_NPS_DESIGN.md` §8), which is evidence about
  this machine, not proof.

## 6. Decision for the owner

| | Decision | Recommendation |
|---|---|---|
| **D-S3** | Carry the basis flags into the exported payload, refuse the export, or record and defer? | **Carry them.** An existing mechanism is incomplete by oversight, at a cost of about three lines and no new state, and it adds an absent key rather than a signal that can never fire. **But the population is measured at zero and closed (§2), so this is defense-in-depth, not a repair** — and *record-and-defer* is defensible on the same principle that settled D-S6, if the owner prefers consistency there. **Not** a refusal: D1-7(b) already ruled that reasons say so rather than the route blocking, and a new gate on approved work is a product decision. |

## 7. Tests, if approved

- **A flagged row's export carries the flag and the warning**, with the same
  reason text the queue shows — asserted against `review_queue`'s constant, not a
  copied string.
- **An unflagged row's export carries neither key** — the both-states pair, so the
  feature cannot be satisfied by always emitting it.
- **Both flags independently**: a tax-basis-flagged row and a
  treasury-basis-flagged row each produce their own key.
- **Nothing else moves**: on a flagged row, the payout amount, `payout_basis` and
  `treasury_forecast` are byte-identical to the unflagged case with the same
  input.
- **The correction path too** — the XLSX branch returns a file, not JSON, so the
  flag cannot ride in a body. **This is an open question in the design, not a
  solved one:** the workbook's honesty label uses a header
  (`X-Template-Honesty-Label`), so that branch may have to use one despite §4's
  argument against headers. Flagged rather than decided.

**Sabotage:** emit the flag unconditionally — the unflagged-row test fails alone,
proving the pair distinguishes "carried when present" from "always present".
