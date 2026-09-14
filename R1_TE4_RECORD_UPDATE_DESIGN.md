# R1 and TE4 record updates — design

**Status:** design only. Nothing here is built, and no data record has changed.

The second primary-source lookup (`docs/PRIMARY_SOURCE_LOOKUP_TASK.md`, "SECOND
LOOKUP", commit `fd601fc`) reached the primary source for both records and
resolved neither outright. This document designs what each record should now
say.

**It opens with something else, because it outranks the rest.** Designing TE4
required reading how the tax engine uses the NPS cap, and that reading found a
defect in the tax computation itself. It is measured below, it is not fixed here,
and it blocks exactly one part of this design.

---

## 1. A defect in the tax engine, found while designing TE4

### 1.1 What the statute says

Read from the primary source on 2026-09-14 (`incometaxindia.gov.in`, Income-tax
Act, 2025, as amended by Finance Act 2026):

- **s. 16(k)** — *"salary" includes … "the contribution made by the Central
  Government or any other employer in any tax year, to the account of an
  employee under a pension scheme referred to in section 124"*.
- **s. 124(1)** — that contribution is deductible *"in the computation of his
  total income"*, up to 10% of salary (14% for a government employer; 14% for
  anyone under the new regime, s. 124(2)).

So an employer NPS contribution is **added to salary and then deducted.** Within
the cap, the two cancel exactly.

### 1.2 What the engine does

`tax_engine.taxable_income_for_structure()`:

```python
gross_salary = structure.basic + structure.hra + structure.lta + structure.special_allowance
...
taxable = (gross_salary - hra_exempt - lta_exempt - std_deduction - structure.employer_nps)
```

`gross_salary` **excludes** employer NPS, and `taxable` **subtracts** it anyway.
The function's own docstring states the intent — contributions within the cap are
*"fully exempt"*, which is net zero. The code produces net **minus** the
contribution.

### 1.3 Measured, not reasoned

Two structures at the same CTC; B moves ₹80,000 from special allowance into
employer NPS (10% of basic — exactly the old-regime cap for a non-government
employer):

| regime | engine: B − A | statute: B − A | engine under-states B's taxable income by |
|---|---|---|---|
| old | −₹1,60,000 | −₹80,000 | **₹80,000** |
| new | −₹1,60,000 | −₹80,000 | **₹80,000** |

The saving from routing money into NPS is counted **twice**. For every structure
carrying employer NPS, taxable income — and therefore tax — is under-stated by
the full contribution.

### 1.4 What follows, and what does not

- **Tax is under-stated** for any structure with employer NPS, in both regimes.
- **The optimizer's NPS lever is over-valued**, because the benefit it measures
  is doubled. Recommendations to opt into NPS may rest partly on a saving that
  does not exist.
- **The characterization baseline would move** if this were fixed: employer NPS
  appears 16 times in `tests/fixtures/pipeline_baseline.json`, and structures
  with employer NPS are exercised in five test files.

**Not established here:** how often it bites in real use, and whether any
emitted figure has reached a user who acted on it. Those need the fix's own
design.

**Deliberately not fixed here.** This is the tax math the numeric guard exists
to protect, and changing it needs its own design, its own baseline decision, and
a decision from the project owner. **It is recorded as decision D1** and is the
most severe item this design turned up.

**The one part of this design it blocks:** the *direction* of TE4's divergence
(§3.4). Whether the tool's employer-type assumption over- or under-states tax
cannot be stated while the engine mis-computes the same deduction.

---

## 2. R1 — Code on Wages, 2019, s. 2(y)

### 2.1 What the lookup established

**Verified:** Act Number 29, enacted 08-08-2019; the text of s. 2(y) and its
first proviso (verbatim in the lookup doc). **Not verified:** the commencement of
s. 2 (India Code lists only a partial 18-Dec-2020 notification), and whether
"one-half" has been re-notified.

### 2.2 Field by field

| Field | Now | Proposed | Why |
|---|---|---|---|
| `source_url` | `indiacode.nic.in/handle/123456789/15793` — **dead** | `https://indiacode.gov.in/act/77a51a9b-c4c0-455c-809c-13d2efb3c8e5/details` | India Code migrated. Verified to load on 2026-09-14. |
| `provision` | s. 2(y)…; *"In force 21 Nov 2025."* | s. 2(y) and its first proviso stated accurately, **the commencement claim removed**, plus the navigation path to re-read it | The commencement is unverified. A record should not assert it. |
| `instrument` | `Code on Wages, 2019 (Act 29 of 2019)` | **unchanged** | The act number is now verified. |
| `instrument_status` | `in_force` | **unchanged** — see §2.3 | |
| `citation_checked_on` | `unresolved: attempted 2026-09-09; no primary source reachable…` | `unresolved:` with the **2026-09-14** outcome: text and act number verified against India Code; **commencement of s. 2 not verified** | Stays unresolved. The *reason* changes, because the old reason is now false. |
| `threshold_origin` | empty | STATUTORY — *"one-half", s. 2(y) first proviso, "or such other per cent. as may be notified" (whether any was notified: not checked)* | The origin of R1's 50% is now known and should be recorded where CHECK 6 looks for it. |
| `rationale` (emitted) | *"violating the Code on Wages 2025 requirement…"* | **unchanged** | See §2.4. |
| predicate | basic < 50% of CTC | **unchanged** | See §2.4. |

### 2.3 Why `in_force` stays, and why that does not make the citation checked

The Act is in force at least in part — India Code's own record shows provisions
commenced by notification of 18 December 2020. So `instrument_status = in_force`
is true **at the level of the Act**.

It is **not** true at the level of the claim, which is about s. 2. Marking R1's
citation checked on the strength of the Act being partly in force would be
**checking at Act granularity and reporting at provision granularity** — the
exact failure named in `R5_CITATION_PROPAGATION_DESIGN.md` §1.1, where a sweep
confirmed "Section 17 is still perquisites" and reported "17(2)(vii) is retained".

So `instrument_status` stays `in_force`, and `citation_checked_on` stays
`unresolved:` specifically because the provision-level fact is the unverified
one. The two fields are correct together; either alone would mislead. This is
written into the record rather than left for a reader to infer.

### 2.4 What is deliberately NOT changed for R1

**The emitted text.** R1's *"violating … requirement"* wording is the subject of
an existing CA packet question (the "Code on Wages 2025" year), deliberately
parked for a CA ruling. The lookup adds evidence to that question: the proviso
is a **deeming rule**, and it prohibits nothing. Changing emitted text ahead of
the ruling would pre-empt it, and it would also move the pipeline baseline and
touch text the rationale-guard work defers to the same ruling
(`RATIONALE_GUARD_CITATION_DESIGN.md` §4.6).

**The predicate.** R1 tests *basic < 50% of CTC*; the proviso tests *payments
under (a)–(i) > one-half of all remuneration*. Whether those coincide turns on
whether an allowance outside the (a)–(k) list — for example a special allowance
— counts as wages. That is **statutory interpretation**, protocol step 5, for a
CA.

### 2.5 The CA packet question grows; its condition does not

Extend R1's existing `ACTIVE_RULE_QUESTIONS` entry with a second part:

> (2) The primary text makes this a deeming rule: payments under clauses (a)–(i)
> above one-half of all remuneration are *deemed remuneration and added to
> wages*. R1 instead flags basic below 50% of CTC. Those are the same test only
> if every allowance outside (a)–(k) — a special allowance, for example — is
> itself an excluded payment. If such allowances count as wages, R1 flags
> structures on which no deeming occurs. Which reading applies?

**One entry, not two.** Two `R1` entries would render two identical
`### R1 — Basic salary < 50% of CTC` headings. The existing condition —
*"Code on Wages 2025" in the rationale AND not reviewed* — still holds for the
combined question. When a CA rules and the text changes, the condition goes
false, generation refuses, and whoever rewrites it must keep part (2) if it is
still open. That is the mechanism working as step 6 designed it. (Decision D4.)

---

## 3. TE4 — Income-tax Act, 2025, s. 124

### 3.1 What the lookup established

**Verified:** s. 124(1)(a) 14% for a Central/State Government employer; (b) 10%
otherwise; of salary. s. 124(2): 10% → 14% under s. 202(1), officially headed
*"New tax regime for individuals, Hindu undivided family and others"*.
s. 124(13)(b): salary includes DA. Pairing with 1961 s. 80CCD(2) confirmed.

### 3.2 Field by field

| Field | Now | Proposed | Why |
|---|---|---|---|
| `provision` | *"Section 124, read with Schedule XV … deductible from salary income"* | **s. 124(1)(b), read with s. 124(2) and s. 124(13)(b)**: deductible *in computing total income* up to 10% of salary (14% for a government employer, s. 124(1)(a)), 10% read as 14% under s. 202(1); formerly 1961 s. 80CCD(2); navigation path | Schedule XV is not where the cap lives; "from salary income" is not what the text says. |
| `source_url` | `…/pages/acts/income-tax-act.aspx` | `https://www.incometaxindia.gov.in/income-tax-act-2025` | The old page redirects to the homepage. The trail is the navigation path, as for R5. |
| `threshold_origin` | *"STATUTORY -- … set by the Act. See TE1."* | STATUTORY — s. 124(1)–(2) | "See TE1" pointed at a claim with no verified provision. |
| `describes` | *"… as a percentage of basic: 14% new, 10% old"* | **unchanged** | It describes what the **code** asserts, and does so accurately. The statute's difference belongs in `known_divergence`. |
| `asserted_value` | `{new: 0.14, old: 0.10}` | **unchanged** | Matches the live constant; drift stays zero. |
| `known_divergence` | empty | two recorded departures — §3.4 | |
| `instrument` | `Income-tax Act, 2025 (Act 30 of 2025)` | **depends on D2** — §3.3 | |
| `citation_checked_on` | `unresolved: … Primary sources remain unreachable…` | **depends on D2** — §3.3 | |

### 3.3 TE4 cannot be marked verified while its instrument carries an unchecked number

TE4's provision is now verified. But its `instrument` field says
`(Act 30 of 2025)`, and **that act number has never been verified** — the same
number deliberately left out of R5. Writing a check date onto TE4 would put a
"verified" record around an unchecked number: precisely what was refused for R5.

And TE4 cannot be fixed on its own. `docs/PROJECT_STATUS.md` already records
that TE1–TE4 and PE4 must be resolved **together** with R5, because fixing one
record makes the inconsistency worse. So TE4's final state is coupled to that
six-record decision (**D2**):

- **A — leave the number everywhere.** TE4's provision and fields are corrected,
  but its citation stays `unresolved:` with a new reason: *"provision verified
  2026-09-14; the instrument's act number is not verified."* Smallest change.
- **B — remove the number from all five now.** Removing an unverified assertion
  needs no new evidence — it moves toward what is known, never away. R5 already
  omits it. TE4 can then be marked checked. Touches TE1–TE3 and PE4 as a string
  trim; no test pins those strings (measured).
- **C — verify it first, then add everywhere or remove everywhere.** India Code
  sends income-tax legislation to `incometaxindia.gov.in`, so the right place is
  the Gazette notification of the Income-tax Act, 2025.

**Recommendation: C, falling back to B** if the Gazette check does not settle it
in one session. B alone is safe but discards a number that may well be right.

### 3.4 The divergence TE4 should record — content now, direction later

Two deliberate departures, following the convention PT2 and PT4 already set:

1. **Employer type.** The statute's cap is 14% for a government employer under
   *both* regimes; the tool applies 10% under the old regime to every employer,
   because it models no employer type. Exact for non-government employers.
2. **Base.** The statute's base is *salary including dearness allowance*
   (s. 124(13)(b)); the tool uses basic. Exact where DA is zero — the same
   assumption as `hra_exemption()` and R1.

**What can be stated now, read from the code:**

- `derive_nps()` sets employer NPS **at** the cap. So for a government employee
  under the old regime, the tool recommends 10% of basic where 14% of salary is
  lawful — a smaller recommendation than the law permits.
- `evaluate_band_guardrail`'s `80ccd2_cap` check flags employer NPS above 10% of
  basic under the old regime. For a government employer, a lawful contribution
  between 10% and 14% **would be flagged as exceeding the cap** — a false
  positive.

**What cannot be stated yet: whether tax is over- or under-stated.** PT2's
divergence records *"OVER-states, never under-states"*, and that direction is
the part that decides whether a divergence is safe. For TE4 it depends on how the
engine treats the deduction, and §1 shows the engine currently mis-computes it.
Writing a direction now would describe a computation that is about to change.
So the divergence is recorded with its **direction explicitly marked as pending
D1**, not guessed.

---

## 4. Tests this changes — measured

| Test | Why it moves | Approach |
|---|---|---|
| `test_legal_claims::test_exactly_the_two_documented_divergences_are_recorded` | pins `["PT2","PT4"]` | Update to include TE4. This pin is *about* the inventory's contents, so moving it deliberately is its purpose. |
| `…::test_each_divergence_says_what_a_reviewer_would_be_accepting` | **hardcodes PT2 and PT4** | **Iterate every recorded divergence.** As written it would stay green while TE4 broke the convention — `INVENTORY_EXPANSION_DESIGN.md` §7 again. |
| `…::test_an_unreviewed_divergence_is_its_own_finding` | hardcodes PT2 and PT4 | Same: iterate. |
| `…::test_the_two_citation_states_are_kept_apart` | asserts TE4 is `unresolved` | **Only under D2 = B or C.** Retarget to keep both states demonstrated with a carrier still unresolved (PE1–PE4), or a synthetic one. |
| CA packet / review queue sync tests | render R1 and TE4 | Regenerate. |
| `test_legal_claims::test_the_worst_tier_is_empty_and_would_still_rank_first` | names R1 and TE4 as lesser items | **Unaffected** — both stay in the queue whichever tier they land in. |

**R1 has no test pinning its citation fields** (measured: its only mention near
those fields is a comment). **No test pins the `evidence_findings()` count**;
adding TE4's divergence adds one CHECK 7 finding.

**Sabotage, per step:** strip *"WHAT A REVIEWER IS ACCEPTING"* from TE4's
divergence and confirm the now-universal format test fails; remove TE4's
divergence and confirm the updated list pin fails.

---

## 5. Sequencing

Separate commits. Full suite after each, using the request/go handshake with the
other session.

0. **D2 step, if C is chosen:** the Gazette lookup — documentation only.
1. **R1 record** (§2.2) + regenerate artefacts. Reviewer-facing data; no
   user-facing text changes.
2. **R1 packet question** (§2.5) + regenerate.
3. **TE4 provision, source, threshold origin** (§3.2) + regenerate.
4. **TE4 divergence** (§3.4, direction pending D1) + make the divergence tests
   universal + sabotage.
5. **The act number across the six records and TE4's citation date** — only once
   D2 is decided. Retarget the citation-states test.
6. **Records:** `docs/PROJECT_STATUS.md` gap rows and the lookup doc's outcome.

---

## 6. Decisions needed

| | Decision | Recommendation |
|---|---|---|
| **D1** | **Employer NPS is double-counted in taxable income (§1).** Open a separate design to fix the tax engine? | **Yes, and ahead of this work.** It under-states tax for every structure with employer NPS. It is also the only thing blocking TE4's divergence direction. |
| **D2** | The `(Act 30 of 2025)` number across six records (§3.3). | **C** — verify via the Gazette; fall back to **B**, remove it from all five. |
| **D3** | R1's `citation_checked_on`: replace the 2026-09-09 reason, or append to it? | **Replace.** The old reason is now false; its history lives in git and the lookup doc. The same was done for R5. |
| **D4** | R1's packet question: extend the one entry, or add a second? | **Extend** — two entries render duplicate headings (§2.5). |
| **D5** | Record R1's `threshold_origin` now? | **Yes** — the 50% has a verified origin, with the notification caveat stated. |
| **D6** | Make the divergence-format tests iterate every divergence? | **Yes** — hardcoded ids would let TE4 break the convention silently. |

---

## 7. Not in scope

- **Fixing the tax engine** (D1). Its own design.
- **R1's emitted text and predicate** — CA.
- **An employer-type or DA field in the tool** — a scope decision about what the
  tool models, not a record update.
- **`evaluate_band_guardrail`'s `80ccd2_cap` label** ("… of basic") — accurate
  about what the code does. It is also under active change by the rationale-guard
  work; not touched from here.
- **Verifying the commencement of s. 2 of the Code on Wages** — a follow-up
  lookup (the Gazette commencement notification), not a record change.
- `reviewed_by`, for either record.

## 8. Coordination

Implementation touches `compliance_rules.py` (R1), `legal_claims.py` (TE4, and
the other TE/PE records under D2), `scripts/generate_ca_review_packet.py`,
both generated artefacts, and `tests/test_legal_claims.py`. **Not `ai_layer.py`**,
where the rationale-guard implementation is in progress. Keeping R1's emitted
text unchanged was confirmed compatible with that work on 2026-09-14.
