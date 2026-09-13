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
