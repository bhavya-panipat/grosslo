# Project status — what shipped, and who is holding what is left

**Standing artefact. Update this at every phase close, before the merge.** It is
maintained by hand rather than generated: what a phase left undone, and who has
to act on it, is a judgement no script can derive from the code.

Its purpose is to be the single place someone can read to know where a
multi-phase effort with real human dependencies actually stands, without
reconstructing it from separate closing reports.

_Last updated: 2026-09-25, after the CTC reconciliation fix (D-S2, all three sites).
Before that, 2026-09-22, after the two neighbouring-route sweeps opened D-S1 to D-S5.
Before that, 2026-09-19, after the employer-NPS fix was implemented (D1, steps 0–8).
Before that, 2026-09-15, after the D1 approvals and blast-radius check
(`TAX_ENGINE_EMPLOYER_NPS_DESIGN.md` §8). Earlier the same day, after the R1/TE4 record updates
(`R1_TE4_RECORD_UPDATE_DESIGN.md`). Before that, 2026-09-14, after the R5 citation
propagation (`R5_CITATION_PROPAGATION_DESIGN.md`) and the gap-owner table below. Previously
2026-09-13, at the close of Phase 2.4b._

---

## The phases on `main`

| Phase | Shipped | Waiting on a person |
|---|---|---|
| **1.1** Multi-tenancy | Postgres row-level security, `FORCE ROW LEVEL SECURITY`, transaction-scoped `SET LOCAL app.tenant_id`, startup assertion that RLS is actually enforceable | — |
| **1.2** Identity & RBAC | Permission-based `require_permission`, order-independent guards, login timing oracle closed (77× → 1.02×), audit-log split into two sinks | — `finance-flow.tsx`'s `DecidedBy` seen in both states 2026-09-22; see README's *Known unverified surfaces* table for the current per-surface status rather than a copy here |
| **2.1** Pipeline orchestration | Declared `STAGES` sequence, `stages_run` in the API response, characterization baseline | `api-types.ts` is declarations only — nothing to render, not a pending check |
| **2.2** Compliance rule breadth | Rule set as data with one source of truth, candidate-rule protocol with six steps, generated rules table, `compliance_pct` reports its denominator | **CA review packet** — 2 candidate rules + 5 questions on live rules. `ring-metric.tsx` seen 2026-09-22, both the normal ratio-detail case and the graceful-degradation case (see README) |
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
| **The tax/treasury basis flags reach the Finance screen but not the exported payload.** `review_queue._row_to_dict()` attaches `tax_basis_flag` and `treasury_basis_flag` to every row it returns, and `/api/submissions/<id>/rows/<i>/export` reads its row through `get_submission()` — so it **holds both flags and reads neither**. `app.py` does not contain the string `tax_basis` anywhere. Verified end to end 2026-09-22: a row forced to the pre-fix basis exports 200 with no trace of the flag in the payload. | **The one surface the flag does not reach is the one that gets acted on.** D1-4 and D-T3 built the read-time mechanism so a figure someone may act on says when its basis is superseded; a payment instruction is that document. The route already carries `WARNING_DO_NOT_UPLOAD` in body and header, so the mechanism exists and is unused. | `app.py` `api_export_approved_row`. Decision D-S3: project owner. | Carry the flag and its reason text into the payload, by the placeholder-account precedent. **Not** a refusal — D1-7(b) already settled that the reasons say so rather than the route blocking, and a new gate on approved work is a product decision. | None formal. |
| **The per-row export payload mixes two computation bases, and two names overstate their content.** `treasury_forecast`, `payouts` and `payout_basis` are recomputed fresh at export; `guardrail` is the one stored at submission time. They agree while the engine is unchanged and diverge exactly when it is not — as on 2026-09-19, when the NPS fix changed the recommendation in 111 of 1,140 cases. Separately: the route docstring promises a revision XLSX "current vs. corrected" and the workbook has **no current column** (`current` is passed in and discarded); `summary.total_rows` in batch-audit is the valid-row count, not the submitted count. | **Low today, and the names are lower.** The mixed basis needs a pre-fix row still awaiting export to bite. `total_rows` has one consumer that already uses it correctly, as "Processed Records: N / M". | `app.py`; `salary_revision_export.py`. Decisions D-S4 (label vs. recompute) and D-S5 (the two names): project owner. | D-S5 is the cheap half and can go first: correct the docstring to match the file, rename `total_rows` to `valid_row_count`. D-S4 recommendation is **label, not recompute** — recomputing silently replaces the verdict a human approved, which erodes the maker-checker gate as a side effect. Recorded as the least certain call in the sweep. | None formal. |
| **`epfo_challan_annual` is named for a challan it does not fully compute.** It sums the employer's PF share and the employee's; a real EPF challan also carries EDLI and administrative charges, and nothing in this repository mentions either (`grep -ri` returns nothing). Found 2026-09-21 by the deliberate sweep in `EXPORT_NUMERIC_CLAIM_SWEEP.md`, not by an incident. | A funding figure lower than a real challan, by components whose rates are not established here. Same defect class as the three totals fixed this week. | Treasury path, `payroll_breakdown.py`. Decision D-S1: project owner. | A person with a browser establishes each missing component from a primary source — the rates must not be written from memory (`docs/PRIMARY_SOURCE_LOOKUP_TASK.md` describes the method). Cheaper half available first: rename the field to what it actually sums. | None formal. |
| **`(Act 30 of 2025)` is still unverified — the removal closed the exposure, not the question.** *Added 2026-09-20 at the user's instruction, so that "handled by removing it" does not become the last anyone hears of it.* The number was struck from TE1–TE4, PE4 and R5 on 2026-09-14 (`3f717f9`), and the code comments at `legal_claims.py:311` and `compliance_rules.py:343` record why. What was never done is the verification itself: the Gazette check failed in one session — the Act's own entry was not located and the subject lines carried no act numbers, so the number has to be read out of a Gazette PDF. Two design docs still write it in prose (`COMPLIANCE_BREADTH_DESIGN.md` §238, `R1_TE4_RECORD_UPDATE_DESIGN.md`), which is harmless as long as nobody copies it back into a record. The short title and the 1 April 2026 commencement *are* verified from s. 1 (read 2026-09-13). | **Not fail-open today** — no record asserts the number, so nothing false is emitted. It becomes one the moment anyone writes it back in on the strength of these docs. | The legal-claims records (`legal_claims.py`, `compliance_rules.py`) and whoever next does a primary-source lookup; the design-doc prose is the same owner's. Decision: project owner. | Either verify it from a Gazette PDF and restore it to all six records in one commit, or decide it stays out permanently and strike it from the two design docs' prose so it cannot be copied back. Not to be done piecemeal: one record carrying it while five do not is the inconsistency the 2026-09-14 removal existed to avoid. | None formal; fold into the next primary-source lookup session. |
| **The rationale guard: what is left after the fix.** *Updated 2026-09-20: items (1) and (4) below were implemented and verified; see the notes after each.* Steps 3–8 of `RATIONALE_GUARD_CITATION_DESIGN.md` shipped (`a98e83f` to `ef98fc2`, each suite- and sabotage-verified). Each rephrased line is now grounded only in its own flag's rationale; a rationale's citation digits no longer ground figures; and a line citing a section it was never supplied is rejected, at all four citing call sites. **Still open:** (1) any two rephrased lines that *contain no figures*, returned in swapped order, are still served, each flag carrying the other's reason. That covers any flag pair, R1 + R4 included, and the guardrail's checks too. *(Corrected 2026-09-16: this item first said "figure-free flags (e.g. R3 and R6)", which was measured to be too narrow.)* **Closed 2026-09-18** by one model call per flag (`9fd7bbf`, `84c8173`, `REPHRASING_ALIGNMENT_DESIGN.md`): the code sets the pairing, so no line can land on another flag. What remains of it is narrower: an *off-topic* line inside a flag's own call is still served (the (C) detector was deliberately not built); (2) an unparsed citation form ("s. 17(1)(h)", plurals) whose digits equal a real figure is not checked. **Closed 2026-09-25** (`57960bd`..`452d30e`, `CITATION_FORM_COVERAGE_DESIGN.md`, user-approved D-C1–D-C4): measuring it found not one narrow gap but four, three **fail-open** — `"breaches the cap u/s 14"` was *served* where the identical `"under Section 14"` was rejected, because one pattern defined what a citation IS, so an abbreviated form was not an unmatchable citation but not a citation at all, leaving the membership check nothing to test. Abbreviations and plurals are now parsed (a plural is expanded into the singulars it means), every section spelling canonicalises to one key so widening cannot widen the exemption, and `explain_result` — which supplies no sections, so *every* citation it writes is fabricated, and which needed no exotic spelling to fail — now forbids citing statute and guards for it. 675 OK; three sabotages, two exactly as predicted and one failing 8 of 9 predicted tests, the ninth being protected by a second layer and therefore not a detector. Bare designators stay figures (D-C4, pinned); (3) "Rs 2,025" in R1's own line (Act years deferred, decision 3); (4) `output_boundary.py` had the same citation/figure namespace problem, and one of its tests grounded a year by hand. **Closed 2026-09-20** (`bada9d4`..`866176e`, `OUTPUT_BOUNDARY_GROUNDING_DESIGN.md`): measuring it found it misjudged real AI output both ways. It now checks only declared model fields, grounds them per object, matches below 100 exactly, and is tested on real output. Its one residual — negotiate's lever text "formerly 80CCD2" grounding 80 and 2 — was **closed 2026-09-20** in `f104214` (user-approved emitted-text change): the lever now reads "(Section 124, formerly Section 80CCD(2))", `_grounded_figures(lever)` is empty, and a fabricated "2 lakh" in a negotiation point is now reported on real output (597 OK; the one-line sabotage fails exactly the 7 tests predicted). | **Fail-open.** The figure-bearing cases are closed: figures borrowed across flags, swapped lines with figures, citation-digit figures, and fabricated citations. (1) can still attach the wrong reason to a routing decision whenever the model phrases both lines without numbers, which is less narrow than first stated. | Numeric guard, `ai_layer.py`; `output_boundary.py` for (4). Decisions: project owner. | (1) is being designed in `REPHRASING_ALIGNMENT_DESIGN.md` (user-approved 2026-09-15), because a figure check cannot see it. (3) waits on the CA's ruling on packet question R1. (4) is done, including its residual. (2) is done: the decision was taken 2026-09-25 and all four sub-decisions implemented. | None formal. |
| **R1 cites s. 2(y) of the Code on Wages, 2019, whose commencement is not verified.** The text and Act No. 29 were read from India Code on 2026-09-14; India Code lists only a partial 18 Dec 2020 notification, not one for s. 2. OP1 records the same proposition. | A statutory rule whose provision may not yet be in force — unknown, not known wrong. | Legal-claim inventory: R1 in `compliance_rules.py`, and OP1. | A person with a browser finds the Gazette commencement notification for s. 2 of the Code on Wages. Found: record it and mark the citation checked. The Gazette's search needs a keyword with no hyphen and dates as `dd-Mon-yyyy`. | 2026-12-09 (OP1 is a claim) |
| **R1's emitted text says "Code on Wages 2025"; its `instrument` says 2019. Added 2026-09-14: s. 2(y) is a deeming rule, and whether R1's predicate implements it depends on how allowances outside the exclusion list are read.** | A wrong year in user-facing text, pending a CA ruling. It also keeps one guard leak open (`RATIONALE_GUARD_CITATION_DESIGN.md` §4.6). | CA reviewer. Already tracked as packet question R1 (`docs/CA_REVIEW_PACKET.md`) and deliberately not restated here. | The CA rules on the packet question. | 2026-10-10 escalation trigger |

The full list of items the R5 propagation left open, including CA questions
already in the packet, is `R5_CITATION_PROPAGATION_DESIGN.md` §4.7.5. This table
covers only the rows above that have no other owner, plus the rationale guard's
residuals and the three treasury and payout gaps found while measuring the
tax-engine double count. That double count was the most severe open item until it
was fixed (closed below). No remaining row is a wrong tax figure. Of what remains,
the owner asked on 2026-09-15 for the payout gross/net gap to be scoped before
Phase 3 starts.

**Closed 2026-09-25 (the CTC reconciliation, D-S2):**
- ~~Three sites subtracted across two different amounts of money~~ —
  `CTC_RECONCILIATION_DESIGN.md`, D-S2a to D-S2e approved as recommended.
  The root cause was that `ctc` meant two things: `optimize()`, the band
  guardrail and R1 used the **stated** figure while `treasury_forecast()`, the
  payout and the EPFO/NPS checks used `SalaryStructure.total()`. They agree
  whenever a structure reconciles, which is why four sweeps missed the places
  that subtracted one from the other. A real stated CTC carries gratuity and
  insurance this tool does not model, so ordinary valid input diverges.
  - **Site A**, `/api/batch-audit` (`2215dd6`): optimises from
    `structure.total()`. Rows gain `reconciliation_gap` and `ctc_basis`; the
    summary gains `rows_not_reconciling`. The figure was understated 76–79% in
    the ordinary gratuity case and, inverted, reported an employee's entire
    ₹93,756 tax bill as available savings.
  - **Site B**, `negotiate()` (`1c7c393`): the comparison is rebuilt from the
    money actually in the structure. This was the severe one — ₹3,61,670 of
    negotiating leverage offered on a structure whose real saving is zero, in
    advice a candidate repeats to their employer. **The numeric guard did not
    catch it and was not failing:** the figure was supplied, so it was
    grounded. The guard certifies provenance, never truth.
  - **Site C**, `_build_current_structure()` (`f1e2cff`): a supplied
    `special_allowance` is honoured and only an absent one balanced, so the
    correction flow stops reclassifying ₹69,264 of gratuity as taxable pay and
    the audit and the correction describe the same structure.
  - **Containment held as designed** (§5), pinned by tests rather than
    asserted: `orchestration.route`, the Compliance Clean Rate metric,
    `treasury_forecast` and the funding gate, the payout amount and
    `payout_basis`, the EPFO ceiling check and the maker-checker gate are all
    untouched.
  - **The characterization baseline moved, deliberately.** Its own
    `extraction_mismatch_components_exceed_ctc` case — written for exactly this
    scenario — was pinning ₹1,13,100 of fabricated leverage as correct output.
    Every changed value was enumerated before regenerating: 16 additive field
    lines plus that one case's two values. **Fourth time in this project a test
    asserted the defect, and the second time a baseline did.**
  - **D-S2e deliberately not decided:** whether R1's 50%-of-CTC floor measures
    against the stated or the modelled CTC is a legal question, and stays with
    the CA packet's existing R1 question rather than being settled inside an
    arithmetic fix.
  - **Outstanding:** `api-types.ts` and the frontend surfaces (the frontend
    session's files, requested). The executive summary card's *"Discovered
    Annual Tax Inefficiency"* detail line still says *"the optimal split"*
    without saying of what, and that figure now generally reads higher.

**Closed 2026-09-21 (period labels):**
- ~~An annual figure is labelled "Monthly"~~ — `treasury_forecast()` gained
  `average_monthly_outlay` (`TREASURY_PERIOD_LABEL_DESIGN.md`, D-M1 to D-M4
  approved), and both surfaces are relabelled: the Executive Summary says
  *annual* and names all five components instead of three, and the Treasury Gate
  says which period it means.
  - **Deliberately NOT changed:** the gate still compares the annual figure to
    the balance. Comparing the monthly one would be more meaningful and would
    also make the gate about twelve times more permissive, which is a product
    decision about when to block bulk-approve, not a labelling fix. If wanted,
    it needs its own design.
  - **Named `average_monthly_outlay`, not `monthly_outlay`:** professional tax
    is eleven base instalments plus a higher February, so no real month equals a
    twelfth. A test pins that February exceeds the average, which is what makes
    the word honest.
  - **Frontend, done 2026-09-21 03:24** (`4a14439`): `executive-summary-card.tsx`
    relabelled *Total Annual Payroll Liability*, detail line corrected to name
    all five components; `treasury-gate.tsx` relabelled *Required Treasury
    Funding, annual (pending rows)*, comparison unchanged. `api-types.ts` gained
    `average_monthly_outlay` for type accuracy, not surfaced. First recorded
    as *verified by `tsc` only, not rendered*; **both seen rendering and
    screenshotted 2026-09-22** — the Executive Summary card via a CSV upload
    driven from page script (a `File` attached through `DataTransfer`), the
    Treasury Gate's `live` branch via a patched balance fetch. The balance
    was mocked, so that proves the label, not a real RazorpayX balance.
    Details in README's *Known unverified surfaces* table.

**Closed 2026-09-21 (later):**
- ~~Treasury funding leaves out employer NPS~~ — fixed
  (`TREASURY_NPS_OUTLAY_DESIGN.md`, D-T1 to D-T4 approved). `treasury_forecast()`
  gained a fifth component, `nps_remittance_annual`, and `total_capital_outlay`
  **rises** by it: unlike professional tax, this is money the total did not
  contain, not a re-split. The identity the tests now hold it to is
  `total_capital_outlay == SalaryStructure.total()`.
  - **Why it survived:** four tests asserted a total-outlay identity and all but
    one ran on structures with no employer NPS, so the missing term was always
    zero. The exception asserted `cash + employer_pf` — the defect written down
    as an expectation. All four are retargeted, and the payout identity test now
    runs an NPS case with a precondition that the contribution is real.
  - **Stored rows:** a forecast written before the term is flagged on read
    (`treasury_basis_flag`), identified by the absent key rather than a version
    marker, with its reason shown to the approver. Nothing stored is recomputed.
  - **Sabotages:** dropping the term from the total failed 14 assertions,
    sourcing it from employer PF failed 20, and disabling the stored-row flag
    failed exactly its 2. Under the first, the field-presence test still passed —
    so the identities, not the field's existence, are what catch it.
  - **Frontend, done 2026-09-21 02:58** (`646c5fa`): `api-types.ts` gained
    `nps_remittance_annual` and `treasury_basis_flag` (typed from the actual
    backend return value — no `basis` key, unlike `tax_basis_flag`, since a
    stored forecast either carries the term or predates it); `finance-flow.tsx`
    gained a `TreasuryBasisBadge` alongside `TaxBasisBadge`, same gold caution
    treatment, plus the legacy no-`orchestration` panel; the export modal's
    grid gained NPS remittance. **A second gap found while fixing this one,
    not left as a note**: the same grid also omitted `professional_tax_annual`,
    so it only reconciled to the total when PT was 0 for a row's
    `work_location` — fixed in the same session, 03:07 (`17051fd`).
  - **Verified**: a real submission with `nps_remittance_annual` stripped from
    its stored forecast under RLS context served `treasury_basis_flag`; the
    badge rendered on an `auto_pass_candidate` row with the reason surfacing
    via *Routing decision*. **Residual closed 2026-09-22:** both badges also
    seen on an `escalate` row and on a legacy row with no `orchestration`,
    where each reason sat in its own *Tax basis* / *Treasury basis* panel. A live
    `/optimize` → export run confirmed all five grid values (including a
    genuinely nonzero PT via `work_location: "karnataka"`, ₹2,500) sum exactly
    to the total. The 5-column layout was DOM-text confirmed at first, then
    **screenshotted 2026-09-25**: five columns at 1024px, two at 375px, all
    five values nonzero and summing to the total.

**Closed 2026-09-21 (login):**
- ~~The frontend login is broken against current code~~ — fixed
  (`LOGIN_FIX_DESIGN.md`, D-L1 to D-L4 approved). `role-gate.tsx` still spoke
  the pre-Phase-1.2 protocol: it POSTed `{role, code}` to `/api/auth/login`
  (401 once a tenant's codes are retired) and checked `session.role` against
  `GET /api/auth/session`, which no longer returns that field. Replaced by
  `permission-gate.tsx` — real email/password login, `permissions`
  server-derived from `auth.ROLE_PERMISSIONS` (`GET /api/auth/session` gained
  `permissions` and `display_name`, `ea63607`), the bootstrap flow as a
  secondary path reachable only via a genuine `bootstrap_required` response,
  and all five states named in the design (including *signed in, not
  permitted* never showing the login form, and a failed session fetch
  showing the form with a notice rather than a permanently blank page — a
  real bug caught in review, not shipped as found).
  - **The local-dev `Host`-forwarding gap is also closed**: Next's rewrite
    proxy doesn't forward the original `Host` to an absolute destination, so
    login (and the anonymous *Submit correction* flow, found while
    designing this) answered "Unknown workspace" through the proxy.
    `auth.tenant_slug_from_host` now reads `X-Forwarded-Host` when BOTH
    `TRUST_FORWARDED_HOST=1` and the request's peer is in `TRUSTED_PROXY_IPS`
    — neither alone does anything, specifically because a bare flag with no
    peer check was the reviewed-and-rejected first draft (same "one
    enforcement layer" risk `MULTI_TENANT_DESIGN.md` built RLS to catch,
    applied here to a route whose own docstring calls its contents
    attacker-controlled bank details) (`3ef625a`).
  - **Verified end-to-end**, not just type-checked: bootstrap on a fresh
    tenant, password login with both pages opening, an hr-only account
    hitting the not-permitted state on `/finance`, a wrong password showing
    the generic message, sign-out, the anonymous submission succeeding
    through the proxy, and a dead backend showing the form with a notice —
    all against the real backend, through the real Next proxy, with all test
    data cleaned up afterward. `permission-gate.tsx` is typed on the real
    `Permission` union (`api-types.ts`), not `string`, so a typo in a page's
    `permission` prop fails at build rather than silently denying everyone.
  - **Published**: `4097498` on `origin/main`.

**Closed 2026-09-21:**
- ~~The payout payload's amount is gross, not net~~ — fixed
  (`PAYOUT_NET_AMOUNT_DESIGN.md`, D-P1 to D-P5 approved). The Composite Payout
  `amount` now comes from `treasury_forecast()`'s `net_take_home_annual`: ₹1,17,851.47
  a month on the ₹18L Karnataka case, not ₹1,39,200. `payout_basis` reports the
  withholdings beside the payload, leaving the verified RazorpayX schema
  untouched, and `net_monthly_disbursement()` was deleted as a second, staler
  definition of net pay with no callers.
  - **Tests:** six, committed failing first, each deriving its expected value
    from the forecast in the same response. Sabotage: restoring the gross
    arithmetic fails five of them.
  - **Still open, raised by this work and not fixed:** `/api/export-razorpayx`
    builds every employee's payout from one structure, so a list of ten
    employees gets ten identical amounts with different bank accounts
    (D-P5). It needs its own design before Phase 3.

**Closed 2026-09-19:**
- ~~The tax engine double-counts employer NPS~~ — fixed in `02d05a8`
  (`TAX_ENGINE_EMPLOYER_NPS_DESIGN.md`, D1-1 to D1-8, all owner-approved). Employer NPS
  is now added to salary (s. 16(k)) and deducted up to the cap (s. 124). The fix is
  pinned by statute-derived tests committed failing first, and by two sabotage runs
  (restore the bug: 21 failures; drop the cap: 5).
  - **Stored rows:** those computed before it carry `tax_basis` and are flagged when
    read, with the reason appended to the approver's routing reasons (`debb0aa`). The
    Finance queue never shows them as green *Clean* (`1dc3b98`).
  - **Other records:** candidate R7 was redrafted (`1b13bc8`), TE4's direction is now
    recorded as over-states, never under-states (`59d677b`), and the unused
    `theoretical_minimum_tax()` was deleted (`ef85fd4`).
  - **Still open:** the badge has been type-checked but not seen rendering a flagged
    row (README, *Known unverified surfaces*). R7's severity is left to the reviewer.
- ~~No `node` binary~~ — Node was installed all along, just not on `PATH`
  (`~/.local/node-v24.20.0-darwin-arm64/bin`). Another session found it, and a
  whole-project `tsc --noEmit` exits 0.

**Closed 2026-09-14:**
- ~~`(Act 30 of 2025)` unverified but recorded as fact on TE1–TE4 and PE4~~ — the Gazette
  check could not settle it in one session — the Act's own entry was not located, and
  the subject lines inspected carried no act numbers, so the number would have to be
  read from a Gazette PDF — so it was **removed from all five**, matching
  R5. Commit `3f717f9`. *What closed is the exposure, not the question: the
  number is still unverified, and that now has its own row with an owner in
  "Open gaps" above.*
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

- **Node is not on `PATH`.** *(Corrected 2026-09-19.)* This entry said "No `node`
  binary" from Phase 1.2 until another session found one at
  `~/.local/node-v24.20.0-darwin-arm64/bin`. It was the same error as the 403 entry
  below: a fact about the access method, read as a fact about the thing. With it:
  - the whole frontend type-checks (`tsc --noEmit`, exit 0);
  - `/finance` compiles and serves, but against a stale backend process started
    2026-09-04. No current backend behaviour was exercised.

  What remains unverified is behaviour with data, tracked in README's *Known
  unverified surfaces* table.
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
