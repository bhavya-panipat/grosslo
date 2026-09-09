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
# Each names a rule id, and a test asserts every id here still exists, so the
# packet cannot end up asking about a rule that was deleted.
# ---------------------------------------------------------------------------

ACTIVE_RULE_QUESTIONS = [
    ("R1", "The rule's emitted text says \"Code on Wages 2025\". The Act is the "
           "Code on Wages, **2019** (Act 29 of 2019); 21 November 2025 is when "
           "it came into force, not its year. The text is deliberately left "
           "byte-identical — changing emitted text is a behaviour change, not "
           "provenance backfill. Should it be corrected, and does the "
           "underlying claim (Basic + DA at least 50% of remuneration, with no "
           "DA field in this private-sector-scoped tool) hold as stated?"),
    ("R3", "Classified CONVENTION, but its stated reason is a legal "
           "precondition — the HRA exemption requires rent actually paid and "
           "documented. It was classified as a convention because it flags a "
           "realisability risk rather than asserting a violation, and its "
           "severity is Low. That is a judgement call this file should not "
           "settle on its own. Is CONVENTION right, or is this STATUTORY and "
           "mislabelled?"),
    ("R2", "The Rs 6,00,000 threshold has NO recorded derivation. It has been "
           "in the code since the initial commit with no basis stated in any "
           "commit message, the project brief, or the rules table. It is "
           "recorded as unknown rather than given a plausible-sounding "
           "justification. Where should this line actually sit?"),
    ("R4", "The 10% figure has NO recorded derivation either — present since "
           "the initial commit, with no survey, policy sample or source named "
           "anywhere in the repository. Same question: where should it sit, and "
           "on what basis?"),
    ("R5", "Cites Section 17(2)(vii) of the Income-tax Act, **1961**, which the "
           "Income-tax Act, 2025 replaced with effect from 1 April 2026. The "
           "underlying obligation (a Rs 7.5L aggregate ceiling on employer "
           "PF/NPS/superannuation) is believed to survive, but this citation no "
           "longer locates it and the successor number was NOT guessed. "
           "Separately: the excess is not modelled in this tool's tax engine at "
           "all, so a structure crossing the threshold carries an unmodelled "
           "liability. Both need confirming."),
]


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
    for rule_id, question in ACTIVE_RULE_QUESTIONS:
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
        "## 3. What is blocked, and why no statutory candidate is in this batch",
        "",
        "Primary legal sources could not be reached from the environment these "
        "rules were drafted in. Official government sites returned HTTP 403 or "
        "refused connections across repeated attempts, by two people "
        "independently. Only secondary aggregators were reachable, and a search "
        "snippet is not a fetched primary source.",
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
        "above 50% of basic*, on the ground that the exemption is capped at "
        "50%/40% of basic regardless of rent, so the excess can never be "
        "exempt. It is held back because that 50% is a statutory number, and "
        "shipping it as a convention rule would put a statutory figure into the "
        "rule set with no citation behind it. It needs a provision, and the "
        "provision needs a reachable source. See "
        "`docs/PRIMARY_SOURCE_LOOKUP_TASK.md`.",
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
