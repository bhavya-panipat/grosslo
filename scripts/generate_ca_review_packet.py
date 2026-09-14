"""
Generates docs/CA_REVIEW_PACKET.md from compliance_rules.py
(COMPLIANCE_BREADTH_DESIGN.md §7 step 6).

    python3 scripts/generate_ca_review_packet.py [--check]

GENERATED IN FULL, unlike compliance_rules.md. That file is generated only
between markers because it had real hand-written prose worth preserving — §6's
resolution. This one has no prior prose to protect, and a packet is exactly the
artefact that must not drift from the rule set it describes: a reviewer signing
off on a hand-maintained summary would be approving something that no longer has
to match the code. So the editorial framing lives here, in the generator, and
the whole document is derived.

THE WORKED EXAMPLES ARE COMPUTED, NOT WRITTEN. Each example structure below is
run through the rule's own predicate, and generation FAILS LOUDLY if the result
disagrees with the label the example carries. A packet that claimed "this
structure is flagged" about a structure that is not flagged would be worse than
no packet — it would put a wrong worked example in front of the one person whose
job is to check the reasoning. This is the same discipline as R7's and R8's
falsifiable bases, applied to the document about them.

--check exits non-zero if the committed file is out of date.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import compliance_rules
from tax_engine import SalaryStructure

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "docs", "CA_REVIEW_PACKET.md")


# ---------------------------------------------------------------------------
# Worked examples. Each is (label, structure, rent_paid, should_flag).
# should_flag is ASSERTED against the real predicate at generation time.
# Both directions for every candidate: a reviewer needs to see where the line
# falls, and a rule shown only firing tells them nothing about its edge.
# ---------------------------------------------------------------------------

EXAMPLES = {
    "R7": [
        ("Employer NPS of Rs 80,000 with the opt-in flag false — reachable "
         "through a batch CSV, and the tax computation still deducts it",
         SalaryStructure(ctc=2_000_000, basic=1_000_000, hra=300_000, lta=0,
                         special_allowance=500_000, employer_pf=120_000,
                         employer_nps=80_000, nps_opted=False), 0, True),
        ("The same structure with the opt-in flag true — consistent inputs, "
         "nothing to confirm",
         SalaryStructure(ctc=2_000_000, basic=1_000_000, hra=300_000, lta=0,
                         special_allowance=500_000, employer_pf=120_000,
                         employer_nps=80_000, nps_opted=True), 0, False),
        ("No employer NPS at all and no opt-in — not a contradiction, and must "
         "not be flagged as one",
         SalaryStructure(ctc=2_000_000, basic=1_000_000, hra=300_000, lta=0,
                         special_allowance=580_000, employer_pf=120_000,
                         employer_nps=0, nps_opted=False), 0, False),
    ],
    "R8": [
        ("Components sum to Rs 13.48L against a stated CTC of Rs 50L — R1 and "
         "R4 still compute their percentages against the Rs 50L",
         SalaryStructure(ctc=5_000_000, basic=400_000, hra=200_000, lta=600_000,
                         special_allowance=100_000, employer_pf=48_000,
                         employer_nps=0, nps_opted=False), 0, True),
        ("Off by Rs 2 on a Rs 10L CTC — rounding scale, inside the tolerance",
         SalaryStructure(ctc=1_000_000, basic=500_000, hra=200_000, lta=0,
                         special_allowance=239_998, employer_pf=60_000,
                         employer_nps=0, nps_opted=False), 0, False),
        ("Off by Rs 20,000 on the same Rs 10L CTC — a missing component's "
         "scale, outside the tolerance",
         SalaryStructure(ctc=1_000_000, basic=500_000, hra=200_000, lta=0,
                         special_allowance=220_000, employer_pf=60_000,
                         employer_nps=0, nps_opted=False), 0, True),
    ],
}


# ---------------------------------------------------------------------------
# Questions about the rules that are ALREADY ACTIVE. These are not candidates
# and are not blocked on anything — they are things this phase found while
# building the rule set and could not settle without someone qualified.
#
# EACH QUESTION CARRIES THE CONDITION IT DEPENDS ON, AND GENERATION REFUSES TO
# EMIT A QUESTION WHOSE CONDITION NO LONGER HOLDS.
#
# Why (R5_CITATION_PROPAGATION_DESIGN.md §3). This list used to be (rule_id,
# question), guarded by a test that the rule id still existed. That guard was
# written against "a rule was deleted" and passed straight through "the rule's
# facts changed underneath the question". It did exactly that on 2026-09-13:
# R5's citation was fixed, and the packet went on asking a CA whether R5 still
# cited the repealed 1961 Act — ten lines above a derived count saying no rule
# cited superseded law, from a green generator.
#
# The condition is a predicate over the rule's STRUCTURED fields, not a
# substring of the question (INVENTORY_EXPANSION_DESIGN.md §8): a prose
# question cannot be diffed against a dataclass, and matching its wording would
# pass on coincidence and fail on honest rewording. Every entry has one, not
# only R5's — a guard on one entry would teach a reader that the unguarded four
# are safe by omission.
#
# Shape: (rule_id, depends_on, predicate, question). `depends_on` is the
# predicate in words, so a stale question names what changed rather than
# printing a lambda.
# ---------------------------------------------------------------------------

ACTIVE_RULE_QUESTIONS = [
    ("R1",
     # The ONE predicate here that reads free text, and deliberately: this
     # question's subject IS a phrase in R1's emitted text. Checking for the
     # exact phrase is checking the thing asked about, not inferring meaning
     # from wording — the distinction §8 turns on.
     "R1's emitted text still names the Code on Wages \"2025\" and its "
     "implementation has not been reviewed",
     lambda r: "Code on Wages 2025" in r.rationale and not r.implementation_is_reviewed,
     # EXTENDED 2026-09-14 (R1_TE4_RECORD_UPDATE_DESIGN.md §2.5, D4). One entry,
     # not two: a second R1 entry would render a duplicate "### R1" heading. The
     # condition above still holds for both parts. Part (1) also no longer
     # states a commencement date as fact -- the primary-source lookup could not
     # verify it, and this question used to assert it.
     "(1) The rule's emitted text says \"Code on Wages 2025\". The Act is the "
           "Code on Wages, **2019** (Act 29 of 2019 — verified on India Code). "
           "The 2025 is believed to be when s. 2 came into force, but that "
           "commencement was **not** verified from the primary source, so it is "
           "not asserted here. The text is deliberately left byte-identical — "
           "changing emitted text is a behaviour change, not provenance "
           "backfill. Should it be corrected, and does the underlying claim "
           "(Basic + DA at least 50% of remuneration, with no DA field in this "
           "private-sector-scoped tool) hold as stated?\n\n"
           "(2) The primary text of s. 2(y) makes this a **deeming rule**, not a "
           "requirement: payments under clauses (a) to (i) above one-half of all "
           "remuneration are *\"deemed as remuneration and … added in wages\"*. "
           "The rule's text calls a breach *\"violating\"* a requirement, and its "
           "predicate flags **basic below 50% of CTC**. Those are the same test "
           "only if every allowance outside the (a)–(k) exclusion list — a "
           "special allowance, for example — is itself an excluded payment. If "
           "such allowances count as wages, the rule flags structures on which "
           "no deeming occurs. Which reading applies?"),
    ("R3",
     "R3 is still classified CONVENTION",
     lambda r: r.claim_type == compliance_rules.CONVENTION,
     "Classified CONVENTION, but its stated reason is a legal "
           "precondition — the HRA exemption requires rent actually paid and "
           "documented. It was classified as a convention because it flags a "
           "realisability risk rather than asserting a violation, and its "
           "severity is Low. That is a judgement call this file should not "
           "settle on its own. Is CONVENTION right, or is this STATUTORY and "
           "mislabelled?"),
    ("R2",
     # threshold_origin is the field that exists to answer exactly "where did
     # this number come from" (CHECK 6). Recording one is what would settle
     # this question, so its absence is the precise condition — structured,
     # and it goes false the moment someone records a derivation.
     "no threshold_origin is recorded for R2's Rs 6,00,000 figure",
     lambda r: not r.threshold_origin.strip(),
     "The Rs 6,00,000 threshold has NO recorded derivation. It has been "
           "in the code since the initial commit with no basis stated in any "
           "commit message, the project brief, or the rules table. It is "
           "recorded as unknown rather than given a plausible-sounding "
           "justification. Where should this line actually sit?"),
    ("R4",
     "no threshold_origin is recorded for R4's 10% figure",
     lambda r: not r.threshold_origin.strip(),
     "The 10% figure has NO recorded derivation either — present since "
           "the initial commit, with no survey, policy sample or source named "
           "anywhere in the repository. Same question: where should it sit, and "
           "on what basis?"),
    ("R5",
     # REWRITTEN 2026-09-14. The previous question asked whether R5 still cited
     # the repealed 1961 Act; its condition (cites_superseded_law) went false
     # when the citation was fixed, and generation refused it — the first real
     # catch this mechanism made. The citation half is gone because it is
     # answered. The implementation half is not, and it is now sharper.
     #
     # This question deliberately does NOT restate R5's section number,
     # instrument or check date. Those live in structured fields; typing them
     # into prose is how this list became a second source of truth to begin
     # with. It states only what its condition guards (citation verified,
     # implementation unreviewed) plus claims about the LAW, which do not drift
     # with this repository's data.
     "R5's citation is verified but its implementation has not been reviewed",
     lambda r: r.citation_is_checked and not r.implementation_is_reviewed,
     "The citation is now verified against the in-force Act, and the Rs "
           "7,50,000 ceiling carried over unchanged — so what remains is "
           "whether the IMPLEMENTATION is acceptable, in two respects. "
           "(1) The rule sums employer PF and NPS, but the provision aggregates "
           "THREE funds: a recognised provident fund, the notified pension "
           "scheme, and an approved superannuation fund. This tool models no "
           "superannuation component, so the sum is exact for every structure "
           "it builds — but only under that assumption, which nobody has "
           "signed off. (2) The excess over the ceiling is a taxable perquisite "
           "that this tool's tax engine does not compute at all, so a "
           "structure crossing it carries an unmodelled liability that the "
           "rule flags but never quantifies. Are both acceptable as stated?"),
]


def stale_active_rule_questions() -> list:
    """
    Every active-rule question whose premise no longer holds, as
    (rule_id, depends_on). Empty means every question still makes sense.

    A question about a rule that no longer exists is reported as stale too,
    rather than raising KeyError — it is the same failure (the question's
    premise is gone), and it should read as one.
    """
    by_id = {r.id: r for r in compliance_rules.RULES}
    stale = []
    for rule_id, depends_on, predicate, _question in ACTIVE_RULE_QUESTIONS:
        rule = by_id.get(rule_id)
        if rule is None:
            stale.append((rule_id, f"rule {rule_id} exists"))
        elif not predicate(rule):
            stale.append((rule_id, depends_on))
    return stale


def _fmt_money(value: float) -> str:
    return f"Rs {value:,.0f}"


def _structure_table(structure: SalaryStructure) -> str:
    rows = [("CTC", structure.ctc), ("Basic", structure.basic),
            ("HRA", structure.hra), ("LTA", structure.lta),
            ("Special allowance", structure.special_allowance),
            ("Employer PF", structure.employer_pf),
            ("Employer NPS", structure.employer_nps)]
    cells = " | ".join(f"{name} {_fmt_money(v)}" for name, v in rows)
    return f"{cells} | NPS opted in: {'yes' if structure.nps_opted else 'no'}"


def render_examples(rule) -> list:
    lines = []
    for label, structure, rent_paid, should_flag in EXAMPLES.get(rule.id, []):
        actual = bool(rule.predicate(structure, rent_paid))
        if actual != should_flag:
            raise SystemExit(
                f"error: worked example for {rule.id} is wrong.\n"
                f"  example: {label}\n"
                f"  labelled should_flag={should_flag}, predicate returned {actual}.\n"
                f"  Fix the example or the rule — do NOT relabel to match.")
        marker = "**FLAGGED**" if should_flag else "not flagged"
        lines.append(f"- {marker} — {label}")
        lines.append(f"  - `{_structure_table(structure)}`")
    return lines


def render_candidate(rule) -> str:
    parts = [
        f"### {rule.id} — {rule.check}",
        "",
        f"**Severity:** {rule.severity}  ",
        f"**Claim type:** {rule.claim_type}  ",
        f"**Status:** CANDIDATE — cannot fire, produces no flag on any structure, "
        f"and is excluded from the compliance denominator.",
        "",
        "**Text the employee or HR reader would see if this were active:**",
        "",
        f"> {rule.rationale}",
        "",
        "**Why the rule exists (written for you, not for them):**",
        "",
        f"> {rule.why}",
        "",
        "**Where the threshold number came from** (protocol step 0):",
        "",
        f"> {rule.threshold_origin}",
        "",
        "**Basis** (a convention rule states a basis rather than citing a statute):",
        "",
        f"> {rule.basis}",
        "",
        "**Structures it would flag, computed by running the predicate:**",
        "",
    ]
    parts.extend(render_examples(rule))
    parts.extend([
        "",
        f"**What we are asking you to judge for {rule.id}:** not whether the "
        f"cited facts are true — those are checked by tests in this repository "
        f"and named above. Whether the rule's *reasoning* is sound, whether it "
        f"should fire at all, and whether its severity is right.",
        "",
    ])
    return "\n".join(parts)


def render_document() -> str:
    candidates = compliance_rules.candidate_rules()
    active = compliance_rules.active_rules()

    out = [
        "<!-- GENERATED by scripts/generate_ca_review_packet.py — do not edit. -->",
        "<!-- Edit compliance_rules.py or the generator, then regenerate. -->",
        "",
        "# CA review packet — grosslo compliance rules",
        "",
        f"**{len(candidates)} candidate rules awaiting review. "
        f"{len(active)} rules currently active.**",
        "",
        "## What is being asked",
        "",
        "Two new compliance rules have been drafted and are sitting **inert** — "
        "they exist in the rule set, they are visible here, and they cannot "
        "produce a flag on anybody's salary structure until someone qualified "
        "signs off. Activating one is a deliberate source change recording who "
        "reviewed it and when.",
        "",
        "**What has already been done for you:** every factual claim underneath "
        "these two rules is backed by an automated test against this codebase. "
        "If a future change makes one of those claims false, the test suite "
        "fails and names it. You are not being asked to verify that the code "
        "does what the rules say it does.",
        "",
        "**What only you can do:** judge whether each rule's *reasoning* is "
        "sound — whether the thing it flags is genuinely worth flagging, "
        "whether the threshold is in the right place, and whether the severity "
        "matches the real exposure. Confirming that a source exists and says "
        "what is quoted is a different act from judging that a threshold "
        "correctly implements it. The first has been done where it was "
        "possible; the second is yours.",
        "",
        "**Neither candidate cites a statute, deliberately.** Both are "
        "convention rules grounded in this tool's own behaviour, and both say "
        "so explicitly. See \"What is blocked\" at the end for why no statutory "
        "candidate is in this batch.",
        "",
        "---",
        "",
        "## 1. The candidates",
        "",
    ]
    for rule in candidates:
        out.append(render_candidate(rule))
        out.append("---")
        out.append("")

    out.extend([
        "## 2. Open questions on rules that are ALREADY ACTIVE",
        "",
        "These are not candidates. They are live rules, firing today, with "
        "problems this phase found and could not settle without someone "
        "qualified. They are listed because a review that covered only the new "
        "rules would leave the known-weakest parts of the existing set "
        "unexamined.",
        "",
    ])
    by_id = {r.id: r for r in compliance_rules.RULES}
    stale = stale_active_rule_questions()
    if stale:
        raise SystemExit(
            "error: the packet would ask a CA a question whose premise is no "
            "longer true.\n"
            + "".join(f"  {rid}: asked on the basis that {dep} — that no longer holds.\n"
                      for rid, dep in stale)
            + "  Rewrite or remove the question — do NOT loosen its condition to match.")
    for rule_id, _depends_on, _predicate, question in ACTIVE_RULE_QUESTIONS:
        rule = by_id[rule_id]
        out.append(f"### {rule_id} — {rule.check}")
        out.append("")
        out.append(f"*Severity {rule.severity}, {rule.claim_type}, currently "
                   f"{'ACTIVE' if rule.is_active else 'candidate'}.*")
        out.append("")
        out.append(question)
        out.append("")

    unresolved = [r for r in compliance_rules.RULES if r.citation_attempt_unresolved]
    superseded = [r for r in compliance_rules.RULES if r.cites_superseded_law]

    out.extend([
        "---",
        "",
        "## 3. What is still unresolved, and why no statutory candidate is in this batch yet",
        "",
        "**Automated requests to official government legal sources are refused** "
        "— HTTP 403, re-tested on 2026-09-14 with default headers and with a "
        "browser's — **but the same pages load normally for a person using an "
        "ordinary browser.** This packet previously said the sources themselves "
        "could not be reached. That was wrong, and it stood for four days: two "
        "automated attempts were read as proof that the source was unavailable, "
        "when they only showed that that kind of request is. A person in a "
        "browser resolved both outstanding lookups in one session on 2026-09-13 "
        "(`docs/PRIMARY_SOURCE_LOOKUP_TASK.md`). What has not changed: a search "
        "snippet or a secondary aggregator is still not a primary source.",
        "",
        f"**{len(unresolved)} rule(s) carry a citation attempt that could not be "
        f"resolved:** {', '.join(r.id for r in unresolved) or 'none'}. These are "
        "recorded as *attempted and unresolved*, which is deliberately "
        "distinguished from *never attempted* — the first means the claim is "
        "uncheckable from here, which is worse than merely unchecked.",
        "",
        f"**{len(superseded)} rule(s) cite an instrument that has been "
        f"superseded:** {', '.join(r.id for r in superseded) or 'none'}. A "
        "citation can match its source text perfectly and still point at a "
        "repealed Act, which would read as verified while citing dead law. That "
        "combination is treated as *not* a checked citation.",
        "",
        "A third candidate rule was drafted and **held back**: *HRA structured "
        "above 50% of basic*, on the ground that the exemption is capped at a "
        "percentage of salary regardless of rent, so HRA above that line can "
        "never be exempt. It was held back because that 50% is a statutory "
        "number with no citable provision.",
        "",
        "**That blocker is now removed; the rule is still not drafted.** The "
        "provision was found on 2026-09-13: the exemption is Schedule III, "
        "Table Sl. No. 11 to the Income-tax Act, 2025, and the 50%/40% split is "
        "prescribed by Rule 279 of the Income-tax Rules, 2026 — still 50/40, "
        "with the 50% city list now eight cities rather than four. Drafting it "
        "under the candidate-rule protocol is separate work, not done here.",
        "",
        "**One question for review before it is drafted.** Rule 279 computes the "
        "cap as a percentage of *salary*, which it defines as including dearness "
        "allowance where DA is a term of employment. This tool's "
        "`hra_exemption()` uses basic alone and has no DA field. That is exact "
        "for any employer that pays no DA, and wrong for one that does — an "
        "assumption that has never been written down. Is basic-only acceptable "
        "for this tool's scope? See `docs/PRIMARY_SOURCE_LOOKUP_TASK.md`.",
        "",
        "---",
        "",
        "## 4. How to sign off",
        "",
        "For each candidate you approve, the following change is made in "
        "`compliance_rules.py` — one commit per rule, so the diff is the audit "
        "trail:",
        "",
        "```python",
        "    status=ACTIVE,                    # was CANDIDATE",
        "    reviewed_by=\"<your name and credential>\",",
        "    reviewed_on=\"<ISO date>\",",
        "```",
        "",
        "A rule cannot be active without both `reviewed_by` and `reviewed_on`; "
        "an automated check refuses it and names the rule. Approving a rule "
        "*with changes* means the changed rule is what gets committed — the "
        "text, threshold, or severity you specify, not the draft above.",
        "",
        "Rejecting a candidate is a complete outcome and needs no "
        "justification beyond what you want recorded. The rule is deleted, and "
        "the reason belongs in the commit message.",
        "",
    ])
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    updated = render_document()
    existing = ""
    if os.path.exists(DOC):
        with open(DOC) as f:
            existing = f.read()

    if args.check:
        if updated != existing:
            print("docs/CA_REVIEW_PACKET.md is OUT OF SYNC with compliance_rules.py.\n"
                  "Run: python3 scripts/generate_ca_review_packet.py", file=sys.stderr)
            return 1
        print(f"CA review packet is in sync "
              f"({len(compliance_rules.candidate_rules())} candidates)")
        return 0

    os.makedirs(os.path.dirname(DOC), exist_ok=True)
    with open(DOC, "w") as f:
        f.write(updated)
    print(f"wrote {DOC}: {len(compliance_rules.candidate_rules())} candidates, "
          f"{len(ACTIVE_RULE_QUESTIONS)} questions on active rules")
    return 0


if __name__ == "__main__":
    sys.exit(main())
