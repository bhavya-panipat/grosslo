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
