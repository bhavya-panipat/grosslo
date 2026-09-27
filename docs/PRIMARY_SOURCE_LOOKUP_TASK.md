# Primary-source lookup task — for a human with an ordinary browser

**Two lookups, one session.** Both blocked the same way from automated fetching,
both plausibly solvable in a few minutes by a person clicking through.

This file exists because the blocker is environmental, not analytical. Two
independent automated attempts hit the same wall. The wall turns out to be
**domain-specific, not category-wide**: official government sites
(`indiacode.nic.in`, `labour.gov.in`, `incometaxindia.gov.in`) return HTTP 403
or refuse connections, while third-party concordance resources are reachable and
are built for exactly this problem.

---

## Where to look

In rough order of promise:

1. **A CA-built interactive lookup tool** covering 550+ sections, mapping in
   both directions (1961 → 2025 and back). Built for practitioners doing this
   exact conversion.
2. **`itact2025.org`** — claims full verbatim coverage of the Income-tax Act,
   2025 with cross-references to the 1961 Act.
3. **ClearTax / Tax2win** old-to-new mapping guides.

**Search by section number inside these tools**, not on the open web. That
matters: open-web searches for a specific old section number keep surfacing
1961-Act citations, because practitioner documents still use the old numbers
well past the changeover — a January 2026 memo was still citing 17(2)(vii).
Hits like that look like confirmation and are not.

---

## Lookup 1 — R5's successor provision (blocking)

**Find:** what Section 17(2)(vii) of the Income-tax Act, 1961 became in the
Income-tax Act, 2025.

**Search string:** `17(2)(vii)` — and if that misses, `17(2)(viia)`, which is
the companion provision (annual accretion on the excess).

**What the old provision said:** employer contributions to a recognised
provident fund, the NPS, and an approved superannuation fund are treated as a
taxable perquisite to the extent they exceed **Rs 7,50,000 in aggregate** in a
year.

**What counts as success:** the successor section number, **plus** confirmation
that the Rs 7.5L aggregate ceiling and the three-fund composition carried over
unchanged. The number alone is not enough — if the successor changed the ceiling
or the set of funds, R5's predicate is wrong regardless of its citation.

**What to record:** section number, the URL it came from, and the date. Those go
into `compliance_rules.py` R5 as `provision`, `source_url`,
`citation_checked_on`, with `instrument` becoming `Income-tax Act, 2025 (Act 30
of 2025)` and `instrument_status` becoming `in_force`.

**If it can't be found:** leave R5 exactly as it is. It is honestly labelled
right now — active, citing a superseded instrument, both problems recorded, and
surfacing as a known-open protocol violation. A guessed section number would be
strictly worse than that, because it would read as verified.

---

## Lookup 2 — the HRA candidate's provision (not blocking)

**Find:** the provision in the Income-tax Act, 2025 that sets the HRA exemption
formula — specifically the **50% of salary (metro) / 40% (non-metro)** limb.

**Search string:** `10(13A)` — the 1961-Act home of the HRA exemption — and
`Rule 2A`, which carried the actual percentages.

**Why this is wanted:** a candidate rule was drafted and held back — *HRA
structured above 50% of basic*. `tax_engine.hra_exemption()` caps the exemption
at 50%/40% of basic regardless of rent paid, so HRA above that line can never be
exempt and is dead weight in the structure. Useful rule; the problem is that
**the 50% is a statutory number**, so it cannot honestly ship as a CONVENTION
rule with no citation, and cannot ship as STATUTORY without this provision.

**What counts as success:** the section (and sub-rule, if the percentages still
live in a rule rather than the Act), confirmation that the percentages are still
50/40, and confirmation of what "salary" means for that computation — the tool
uses `basic` alone, which is a modelling assumption a CA should check.

**If it can't be found:** the candidate stays held back. It is not blocking
anything; step 6's packet ships without it.

---

## What this task does NOT settle

Neither lookup produces a reviewed rule. Confirming that a provision exists and
says what is quoted is a **different act** from judging that a given threshold
correctly implements it — protocol step 5. Both lookups feed the citation
fields; `reviewed_by` still requires the CA.

---

# OUTCOME — done 2026-09-13

Both lookups succeeded, **against the primary source**, not a concordance.

## The wall was an automation wall, not a site wall

The premise at the top of this file — that `incometaxindia.gov.in` is blocked —
is **wrong, and it was wrong in a way worth naming.** The site loads normally in
an ordinary browser. What returns HTTP 403 is a scripted fetch. The block is on
*how* the request is made, not on *who* may read the law.

Two automated attempts produced the same 403 and the conclusion drawn was
"the domain is blocked". The correct conclusion was "this access method is
blocked" — and the difference between those two mattered for four days, because
one of them ends the investigation and the other one doesn't.

**Standing correction:** a 403 from a public government site is evidence about
the client, not about the source. Before recording a source as unreachable,
try it the way a person would.

## Lookup 1 — R5's successor provision: FOUND

**Income-tax Act, 1961 s. 17(2)(vii) → Income-tax Act, 2025 s. 17(1)(h).**

Read side by side in CBDT's own parallel-reading comparison (the "Compare"
control on the Income-tax Act, 2025 section list, as amended by Finance Act
2026), which places 1961 s. 17 against 2025 s. 17 directly.

The successor text, verbatim:

> (h) aggregate amount of any contribution, in excess of Rs. 750000 in a tax
> year, made to the account of the assessee by the employer— (i) in a
> recognised provident fund; (ii) in the scheme referred to in section 124(1);
> and (iii) in an approved superannuation fund;

Against the 1961 provision it replaces:

> (vii) the amount or the aggregate of amounts of any contribution made to the
> account of the assessee by the employer— (a) in a recognised provident fund;
> (b) in the scheme referred to in sub-section (1) of section 80CCD; and (c) in
> an approved superannuation fund, to the extent it exceeds seven lakh and
> fifty thousand rupees in a previous year;

**Both success criteria met.** The Rs 7,50,000 aggregate ceiling carried over
unchanged, and so did the three-fund composition — recognised PF, the notified
pension scheme, and an approved superannuation fund. The NPS limb moved
citation (80CCD(1) → s. 124(1)) but not substance: s. 124 is headed *Deduction
in respect of contribution to pension scheme of Central Government or State
Government* and s. 124(1) is the employer-contribution sub-section.

> **Correction, 2026-09-14 — that heading was quoted from a secondary source.**
> The wording above came from `itact2025.org`, not from CBDT, and it was
> recorded in a section whose whole point is that everything was read from the
> primary source. The official heading, read on `incometaxindia.gov.in` during
> the second lookup, is *"Deduction in respect of employer and assessee
> contribution to pension scheme of Central Government"*. The conclusion is
> unaffected: s. 124(1) is the employer-contribution sub-section, confirmed
> from the primary text itself. What was wrong was the attribution of a quote.
> §5.1's point applies to this file too.

The companion provision moved with it: the annual-accretion charge is
**1961 s. 17(2)(viia) → 2025 s. 17(1)(i)**. Independently corroborated by the
Income-tax Rules, 2026, whose Rule 16 is titled *"Annual accretion referred to
in section 17(1)(i)"*.

**Source:** `https://www.incometaxindia.gov.in/income-tax-act-2025`, section 17,
CBDT parallel-reading comparison. Checked 2026-09-13.

### One departure from this file's own instructions

This file said to record `instrument` as `Income-tax Act, 2025 (Act 30 of
2025)`. **The act number was not verified and is therefore not written.**
`indiacode.nic.in` loaded but returned a server error on the browse and search
paths tried. The short title and commencement date *were* verified (s. 1: *"This
Act may be called the Income-tax Act, 2025 … shall come into force on the 1st
April, 2026"*), so that is what the field says.

Writing "(Act 30 of 2025)" would have cost nothing and looked more complete.
That is exactly the reason not to: §5.1 says a verified citation must let an
independent party redo the check, and a number nobody checked, sitting inside a
field whose date says it was checked, is the specific failure that rule exists
to prevent.

## Lookup 2 — the HRA candidate's provision: FOUND

**The exemption:** Income-tax Act, 2025 **Schedule III [Table: Sl. No. 11]**,
read with s. 11. Successor to 1961 s. 10(13A).

**The percentages:** not in the Act. Schedule III Sl. No. 11 condition (b)
delegates them — *"such allowance is to such extent as may be prescribed having
regard to the area or place in which such accommodation is situated"* — exactly
the architecture the 1961 Act used (s. 10(13A) + Rule 2A).

They live in **Rule 279 of the Income-tax Rules, 2026**, titled *"Limits for the
purposes of Schedule III [Table: Sl. No. 11] to the Act"*. The
1962 → 2026 mapping **Rule 2A → Rule 279** is CBDT's own, from the official
*Utility to check provisions of Income-tax Rules, 1962 vis-à-vis Income-tax
Rules, 2026*.

Rule 279 in full: the exemption is the least of (a) actual allowance received,
(b) rent paid less one-tenth of salary, (c) the tabled percentage of salary —

| Location of residential accommodation | % of salary |
|---|---|
| Mumbai, Kolkata, Delhi, Chennai, Hyderabad, Pune, Ahmedabad and Bengaluru | 50% |
| Any other place | 40% |

**All three success criteria met:**

1. The provision — Schedule III Sl. No. 11, with Rule 279 carrying the numbers.
2. **The percentages are still 50/40.** Unchanged.
3. **"salary" is defined**, and the definition is the answer to the question
   this file asked about the tool's modelling assumption:
   > (b) "salary" includes dearness allowance, if provided for under the terms
   > of employment, but excludes all other allowances and perquisites.

**Source:** `https://www.incometaxindia.gov.in/income-tax-rule-2026`, Rule 279,
via the official 1962-vis-à-vis-2026 rules utility. Checked 2026-09-13.

### What this says about `tax_engine.hra_exemption()`

`hra_exemption()` computes limb (c) as a percentage of `basic`. Under Rule 279
the base is *salary*, which is basic **plus dearness allowance** where DA is a
term of employment.

`SalaryStructure` has no DA field. So the tool is not using a wrong base — it is
using the right base under an **unstated assumption that DA is zero**, which
holds for the private-sector CTC structures it targets and fails for any
employer who pays DA as a contractual term. The assumption was never written
down. That is a CA question, and it is now a specific one rather than the vague
"a CA should check what salary means" this file opened with.

The 50%-city list is **not** a defect here: `city` is an abstract
`"metro"`/`"non_metro"` flag the user selects, and no city-name list is
hardcoded anywhere. README already records the 4 → 8 expansion. What is worth
noting is that a user in Bengaluru, Hyderabad, Pune or Ahmedabad who correctly
answered "non_metro" under the old law must now answer "metro", and nothing in
the tool tells them that.

## What is now unblocked, and what is not

**Unblocked:** the held-back HRA candidate rule. Its blocker was that the 50%
is a statutory number with no citable provision; it now has one. Drafting it is
a separate piece of work under the candidate-rule protocol, not part of this
lookup.

**Not settled, unchanged:** `reviewed_by`. Both lookups confirm that a provision
exists and says what is quoted. Neither judges that R5's predicate or the HRA
candidate's threshold correctly implements it. That is protocol step 5 and it
still requires the CA.

---

# SECOND LOOKUP — R1 and TE4, done 2026-09-14

Requested because both records say primary sources are "unreachable", while the
review queue that renders them says those sources load in a browser
(`docs/PROJECT_STATUS.md`, Open gaps). Both lookups reached the primary source.
**Neither resolves its record outright**, and the reasons are more useful than a
clean "verified" would have been.

Success criteria were set before searching, as for the first lookup, so that
finding a number could not be mistaken for confirming a claim.

## A second access finding: India Code moved

R1's recorded `source_url`,
`https://www.indiacode.nic.in/handle/123456789/15793`, returns a server-error
page **in an ordinary browser**. This is not the automated-request block.
**India Code has migrated** from `indiacode.nic.in` to **`indiacode.gov.in`**
(the redirect briefly shows a "Site Migration" page title), and the old
`/handle/…` URLs did not survive the move. That is almost certainly also why
India Code "served errors on the browse and search paths tried" on 2026-09-13.

So there are now two distinct ways a source looked unreachable while it was not,
and neither was about the law being unavailable: automated requests are refused
by `incometaxindia.gov.in`, and India Code's old URL scheme is dead. **Record
which of the two happened, not just that something failed.**

Relevant to the open `(Act 30 of 2025)` item: India Code's home page directs
income-tax legislation to `incometaxindia.gov.in`, so India Code was never going
to verify that act number. The Gazette is the better next place.

## R1 — Code on Wages, 2019, s. 2(y)

**Source:** India Code, `indiacode.gov.in`, *The Code on Wages, 2019* →
Sections → Section 2 "Definitions"; and its Act Details page. Checked 2026-09-14.

**Verified from the primary source:**

- **Act Number 29, enacted 08-08-2019.** "(Act 29 of 2019)" in R1's
  `instrument` is correct. The Act's PDF is published as `a2019-29.pdf`.
- **s. 2(y)** — *"wages" means all remuneration … and **includes** (i) basic pay;
  (ii) dearness allowance; and (iii) retaining allowance, if any, but **does not
  include** (a)–(k)* — bonus, house-accommodation and amenities, employer PF and
  pension contributions, conveyance, special expenses, **house rent allowance**,
  award remuneration, overtime, commission, gratuity, retrenchment compensation.
- **The first proviso, verbatim:**
  > Provided that, for calculating the wages under this clause, if payments made
  > by the employer to the employee under clauses (a) to (i) exceeds one-half,
  > or such other per cent. as may be notified by the Central Government, of the
  > all remuneration calculated under this clause, the amount which exceeds such
  > one-half, or the per cent. so notified, shall be deemed as remuneration and
  > shall be accordingly added in wages under this clause:

**NOT verified, and not asserted:**

- **Commencement on 21 November 2025.** Section 1 leaves commencement to
  notification. India Code's Act Details lists only the notification of
  **18 December 2020**, and that brought in parts of ss. 42, 67 and 69, not
  s. 2. "Last Modified 25-11-2025" is consistent with a late-November 2025
  commencement and is not evidence of one.
- **Whether "one-half" is still the operative figure.** The proviso lets the
  Central Government notify another percentage. No such notification was looked
  for or found.

### What the text says about R1, as findings rather than rulings

**1. It is a deeming rule, not a requirement.** R1's rationale says basic below
50% is *"violating the Code on Wages … requirement that Basic + DA be at least
50%"*. The proviso prohibits and requires nothing: excluded payments above
one-half are **deemed remuneration and added to wages**. R1's *second* sentence
— *"This triggers automatic reclassification of the excess allowances as
'wages' for PF and gratuity purposes"* — describes the mechanism the text
actually states. The first sentence does not.

**2. R1's predicate and the statute's test are different tests.** R1 flags
**basic < 50% of CTC**. The proviso asks whether **payments under clauses (a)–(i)
exceed one-half of all remuneration**. Three places they can diverge:

- **Allowances outside (a)–(k).** "Wages" is *all remuneration*, including
  allowances, less the listed exclusions. An allowance not on that list — for
  example a special allowance — may therefore count as wages rather than as an
  excluded payment. If it does, a structure with basic under 50% but a large
  special allowance triggers no deeming at all, and R1 over-flags it.
  **Whether it does is statutory interpretation** — whether the (i)–(iii)
  inclusion list is exhaustive — and practitioner summaries differ. That is
  protocol step 5, for a CA, and it is not decided here.
- **(j) and (k) are excluded from wages but outside the proviso's count.**
  Gratuity and retrenchment compensation never trigger the deeming.
- **CTC is not "all remuneration".** CTC includes employer PF, which is itself
  exclusion (c).

**3. DA is inside "wages".** Consistent with R1's note that the tool has no DA
field — the same unstated DA-is-zero assumption found in `hra_exemption()` and,
below, in TE4.

**Outcome for R1's record:** the citation text and act number are verified; the
commencement is not, so **R1 should stay `unresolved`**, with its reason changed
from "sources unreachable" to "commencement not verified". The predicate question
belongs in the CA packet next to the existing R1 question.

## TE4 — Income-tax Act, 2025, s. 124

**Source:** `incometaxindia.gov.in/income-tax-act-2025` → Section 124 → Compare
against Income-tax Act, 1961 s. 80CCD (CBDT parallel reading); and Section 202's
official heading. Checked 2026-09-14.

**Verified from the primary source:**

- **s. 124 is headed** *"Deduction in respect of employer and assessee
  contribution to pension scheme of Central Government"*.
- **s. 124(1):** the employer's contribution is deductible *"in the computation
  of his total income"* up to **(a) 14%, where the employer is the Central
  Government or a State Government**, and **(b) 10%, for any other employer**,
  *"of his salary in the tax year"*.
- **s. 124(2):** where total income is chargeable to tax under **s. 202(1)**, the
  10% in (b) is read as **14%**.
- **s. 202's official heading** is *"New tax regime for individuals, Hindu
  undivided family and others"*.
- **s. 124(13)(b):** *"salary" includes dearness allowance, if the terms of
  employment so provide, but excludes all other allowances and perquisites.*
- **Old-Act pairing confirmed.** 1961 s. 80CCD(2) has the same 14%/10% split and
  a proviso substituting 14% where income is chargeable under s. 115BAC(1A) —
  the old Act's new regime — in the identical position s. 124(2) now occupies.

### What the text says about TE4

TE4 asserts `{new: 14%, old: 10%}` as the employer-NPS cap, "as a percentage of
basic", citing "Section 124, read with Schedule XV".

**1. The value is right for non-government employers only.** For a Central or
State Government employer the cap is **14% under both regimes**; TE4's 10% for
the old regime is wrong for them. The tool models no employer type, so this is
correct under an unstated assumption: a private-sector employer. That is a
`known_divergence`, not a wrong value.

**2. The base is salary including DA, not basic.** Same assumption as
`hra_exemption()` and R1. Exact when DA is zero.

**3. "Read with Schedule XV" is not where the cap lives.** The rates, the regime
substitution and the definition of salary all sit inside s. 124 itself. Schedule
XV appears in s. 124 only in sub-sections (6) and (11), which tax amounts
withdrawn from the account. What Schedule XV itself contains was not read, so
nothing is claimed about it beyond that. The accurate citation for the cap is
**s. 124(1)(b), read with s. 124(2) and s. 124(13)(b)**.

**4. It is a deduction from total income,** not "from salary income" as TE4's
provision text puts it.

**Not verified:** `(Act 30 of 2025)` in TE4's `instrument` — unchanged, and
tracked in `docs/PROJECT_STATUS.md`.

**Outcome for TE4's record:** the provision is verified and the value holds for
the case the tool models. But **three fields are imprecise** — the Schedule XV
pairing, "of basic", and "from salary income" — plus an unrecorded divergence
and an unverified act number. Marking TE4 checked without correcting those would
put a verified date on a record whose provision text is partly wrong.

## What this lookup does NOT do

**No data record was changed.** R1, TE4 and the review queue are exactly as they
were.

> **Follow-up, 2026-09-14/15:** the records were then updated under
> `R1_TE4_RECORD_UPDATE_DESIGN.md`. **TE4 is now citation-checked** (2026-09-14).
> **R1 stays unresolved**, now for the true reason — commencement of s. 2 not
> verified. The unverified act number was removed from TE1–TE4 and PE4 after the
> Gazette check did not settle it (§9.1 of that design). This paragraph above
> described the state at the time of the lookup and is kept as written. Both outcomes need decisions first — the R1 predicate question needs a CA,
TE4 needs its provision text corrected and a divergence recorded — so the
records are not edited ahead of those decisions.

`reviewed_by` is unchanged for both, as with every lookup: confirming what a
provision says is not judging that the implementation is right.

---

# LOOKUP — D-S1: what an EPF challan carries beyond the PF shares (PARTLY DONE)

*Added 2026-09-28, when the owner ruled D-S1: **record now, fix after a
primary-source lookup** (`EXPORT_NUMERIC_CLAIM_SWEEP.md`). The rates are
established; four points are still open. See PARTIAL OUTCOME below.*

**Why:** `payroll_breakdown.treasury_forecast()`'s `epfo_challan_annual` sums the
employer's and the employee's PF shares and nothing else. A real EPF challan
also carries **EDLI contributions and administrative charges**, and nothing in
this repository states either rate (`grep -ri` returns nothing). The field is
named for a challan it does not fully compute, so every funding figure built on
it, and `penalty_scenario`'s arrears base, which inherits it
(`NEIGHBOURING_ROUTE_CLAIM_SWEEP.md` §1.4), is low by those components.

**The rates must not be written from memory.** That is the reason this is a
lookup and not a code change.

**Find, for each component (EDLI contribution; EPF administrative charges; EDLI
administrative charges, if separately levied):**

1. the rate, and what it is a percentage *of* (the wage base, and whether it is
   capped);
2. any minimum or fixed amount per challan;
3. **the instrument that sets it, and whether that instrument is in force.** The
   schemes framed under the EPF & MP Act, 1952 are expected to be relevant. The
   Code on Social Security, 2020 may have displaced them, and that is **the same
   commencement question R1 has for the Code on Wages**, so it must be settled
   from a source, not assumed either way.

**Where:** EPFO's own site, and India Code for the Acts and schemes. Search
inside those sites, not the open web. Practitioner pages still quote superseded
figures well after a change (see the caveat at the top of this file).

**What counts as success:** every rate with its base, the instrument and its
in-force status, and the URL and date of each. **What to record:** those, in
this file under an OUTCOME heading, as the earlier lookups do.

**What happens next, and what does not:** nothing in the code changes as a
result of the lookup alone. Adding components to `epfo_challan_annual` is a
correctness fix to a **stored** computed value, since submission rows store their
`treasury_forecast`. So its design must decide about pre-fix rows before
implementation, with the population measured (`CLAUDE.md`, *Fixing a stored
computed value*). The optional rename to `pf_contributions_annual` also touches
stored rows and was not taken on 2026-09-28.

## PARTIAL OUTCOME — 2026-09-28

Read on EPFO's own site in an ordinary browser, twice and independently: first
by the tenancy session, then re-read by the frontend session. No PDF was opened,
and nothing came from memory.

| Component | Finding | Source |
|---|---|---|
| EDLI contribution | **0.5% of wages, employer only**: *"Employers contribute 0.5% of wages, with no deduction from employees."* | `epfo.gov.in/insurance-scheme-edli/`, page text |
| EPF administrative charges | **0.50% of pay.** Circular titled *"Reduction in the rate of Administrative Charges from 0.65% to 0.50% of the pay"*, WSU, dated 29/05/2018 per the tenancy session's reading | `epfo.gov.in/circulars/` listing; PDF `WSU_AdmnCharges_4570.pdf` read later the same day, below |
| EDLI administrative charges | **Not levied.** Circular titled *"… Non levy of Administrative charges towards EDLI scheme, 1976"*, WSU, 22/03/2017 per the tenancy session | Same listing; PDF `WSU_FA_ADmCharges_33959-2.pdf` read later the same day, below |

~~**What the rates alone say:** `epfo_challan_annual` understates a real challan
by roughly 1.0% of the relevant pay.~~ **Withdrawn the same day.** That was
arithmetic on two rates, not a measured challan. If the wage base is capped at a
statutory ceiling, the shortfall at this tool's salary levels is far smaller and
roughly flat in rupees, not a percentage of pay. This tool deliberately applies PF
on full basic, above any ceiling (`derive_pf()`). The tenancy session, which first
offered the figure, asked for it to be withdrawn. Do not quote it.

## The circulars, read — 2026-09-28

With the owner's permission, both PDFs were downloaded from EPFO's own file server
(`pmvbry-cdn.epfindia.gov.in`; 1,384,000 and 119,163 bytes) and read. **This is a
single read, by the frontend session only.** The tenancy session did not read
them, because its own user had not approved it, and it must not be counted as
corroboration. Each circular encloses the **Gazette of India notification
itself**, so these readings are of the notification text, not of a summary.

| Finding | Notification | In force |
|---|---|---|
| **EPF administrative charges: 0.50% of pay**, *"subject to a minimum sum of seventy-five rupees per month for every non-functional establishment having no contributory member and five hundred rupees per month per establishment for other establishments."* Supersedes S.O. 827(E), which had set 0.65% with the same minimums. | **S.O. 2011(E)**, Gazette of India Extraordinary No. 1818, 21 May 2018, under para 30 read with para 39 of the EPF Scheme, 1952 | **From 1 June 2018** |
| **EDLI administrative charges: nil.** *"no sum shall be payable for the time being by the employer"* towards the administration of the EDLI Scheme, 1976. | **S.O. 828(E)**, 15 March 2017, under s. 6C(4)(a) of the EPF & MP Act, 1952 | **From 1 April 2017**, "for the time being" |

**So open points 1 and 2 are settled, as of those notifications:**

1. **Effective dates:** as in the table.
2. **The minimum exists, and it is per ESTABLISHMENT, not per employee.** That
   changes the shape of any fix. `epfo_challan_annual` is a per-employee field, and
   no per-row figure can apply a floor that attaches to the whole establishment.
   For a small employer, 0.50% of total pay can fall below ₹500 a month, and then
   the floor is what is owed. A correct fix therefore needs an establishment-level
   figure, not just a larger per-row one.

**Still open:**

3. **The wage base.** Both notifications say "the pay as referred to in the said
   paragraphs" (paras 30 and 38 of the EPF Scheme) without defining it there, and
   the EDLI page says "wages". Whether that base is capped decides whether the
   shortfall is a percentage or roughly flat. A newer EPFO document,
   `EPFO_Wage_Ceiling_FAQs.pdf` (uploaded 2026-09, linked from EPFO's homepage), is
   likely on point. **Downloading it needs the owner's permission**; the approval
   given was for the two circulars only.
4. **The EDLI contribution rate's own notification** was not read. The 0.5% comes
   from EPFO's scheme page, not from a notification.
5. **Later supersession.** Nothing after 2018 was found, but only through the
   circulars listing's search, which is not proof of absence.
6. **The in-force instrument.** Both notifications rest on the EPF & MP Act, 1952
   and its schemes. Whether the Code on Social Security, 2020 has displaced them is
   the same commencement question R1 has, and needs India Code or a practitioner.

## The wage-ceiling FAQ, read — 2026-09-28

With the owner's permission: `EPFO_Wage_Ceiling_FAQs.pdf`, EPFO's file server,
347,156 bytes, uploaded 2026-09. Read once, by the frontend session. **It is
EPFO's own FAQ, not the notification.** It cites **S.O. 5109(E), dated 17
September 2026**, which was not read.

**The statutory wage ceiling was raised from Rs 15,000 to Rs 25,000 a month,
effective 17 September 2026.** The FAQ frames it as the ceiling "for determining
mandatory EPF, EPS and EDLI coverage under the Code on Social Security, 2020".
That bears on open point 6, but it is the FAQ's framing, not the notification's
text.

**Open point 3, the wage base, answered for the mandatory case.** The FAQ's
table for October 2026 onwards (Q13) uses "Monthly PF Wages (Basic + DA)". For
PF wages of Rs 35,000, above the cap, it shows EDLI Rs 125 and EPF admin charges
Rs 125: 0.5% of the **Rs 25,000 ceiling**, not of the actual wage. **So EDLI and
admin charges are computed on wages capped at the ceiling**, at most Rs 125 each
per employee per month. Above the cap they are a flat amount, not a percentage
of pay. Q13 also restates the establishment minimum: Rs 500 a month with at
least one contributing member, Rs 75 with none.

**Not answered:** an employer contributing PF voluntarily on full basic, which
is this tool's default (`derive_pf()`). The FAQ shows only capped contributions.
Whether EDLI and admin charges then follow the capped or the full base is still
open, and is a question for the CA packet or the notification.

**Consequence found in passing:** `tax_engine.PF_WAGE_CEILING_BASIC = 15_000`
has stated superseded law since 17 September 2026. It was deliberately left out
of the claim inventory (`legal_claims.py`, "DELIBERATELY DEFERRED AND NAMED"),
which is why nothing caught it. Only a test calls `derive_pf()` with the ceiling
applied, so no production figure changes today. Tracked in
`docs/PROJECT_STATUS.md`, *Open gaps*.

## The Gazette, read — 2026-09-28

With the owner's permission, three notifications were downloaded from
`egazette.gov.in` (Ministry of Labour and Employment, found by month) and read
once, by the frontend session.

| Notification | What it settles |
|---|---|
| **S.O. 5109(E)**, 17 September 2026 (`CG-DL-E-17092026-276299`, 446,210 bytes) | **The wage ceiling is ₹25,000 a month** "for the purposes of Chapter III" of the Code on Social Security, 2020, under s. 2(89), from publication. It supersedes S.O. 2702(E) of 29 May 2026, which was not read. |
| **EPF Scheme, 2026**, 29 June 2026 (`CG-DL-E-01072026-273957`, 2,510,370 bytes) | **Para 19(3): admin charges are payable on the wages on which voluntary contributions are paid.** Para 28(2): the charge is a percentage of wages. Para 29(1): the percentage is fixed by separate notification. |
| **EDLI Scheme, 2026**, 29 June 2026 (`CG-DL-E-30062026-273942`, 1,022,320 bytes) | **Para 5(1): the EDLI contribution is on wages "subject to the wage ceiling"**, with no voluntary provision. Para 5(2): the rate is fixed by separate notification. |

**Open point 6 is settled:** the governing instrument is the **Code on Social
Security, 2020**, with separate EPF, EPS and EDLI Schemes of 2026 under s. 15(1)(a)
to (c), applicable from 29 June 2026. The 1952 Act's schemes are no longer the
reference. So the 2017 and 2018 notifications above (S.O. 828(E), S.O. 2011(E))
describe the old regime, and whether their rates carry over is the open question
below.

**The wage-base question is settled per component, and the answer split** (the
owner's direction to check each against its own clause): admin charges on the
full voluntary wage, EDLI capped. See `EPFO_CHALLAN_COMPLETENESS_DESIGN.md` §3.1.

**Still open:** the notifications fixing the rates under the 2026 schemes (EPF
para 29(1), EDLI para 5(2)) were not located. EPFO's September 2026 FAQ applies
0.50% to each. Also whether EDLI's own admin charge is still nil, and whether
basic alone is the right base under the Code's s. 2(88) definition of wages. All
four are in `docs/CA_REVIEW_PACKET.md` §4.
