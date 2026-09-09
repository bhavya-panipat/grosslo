"""
compliance_rules.py — the single source of truth for the compliance rule set
(COMPLIANCE_BREADTH_DESIGN.md, Roadmap Phase 2.2).

WHY THIS FILE EXISTS. A rule used to live in three places: the table in
compliance_rules.md, the if-chain in ai_layer._check_rules(), and the constant
TOTAL_COMPLIANCE_RULES = 6, with nothing linking them. Going from 6 rules to N
is precisely the change that makes three hand-maintained copies bite.

An earlier description of this called the two rationale texts "drift". Comparing
all six showed that was wrong, and the correction matters: they are two
REGISTERS — one addressed to the user whose structure was flagged, one to a
reviewer reading the rule set — neither a stale copy of the other. Both are now
fields on one object (see the note above RULES). The real risk was never that
one had drifted; it was that a rule's justification could change in one file and
not the other with nothing noticing.

Now: the predicate, the text, the severity and the provenance are one object.
compliance_rules.md is GENERATED from this (scripts/generate_compliance_rules_md.py),
and the rule count is derived rather than declared.

RULE MATCHING STAYS DETERMINISTIC. Every predicate below is plain Python
evaluated before any LLM sees anything. An LLM may rephrase what these rules
decided; it may never add, remove, or reinterpret a flag. That is the numeric
guard applied to compliance, and this refactor does not touch it.

THE CANDIDATE-RULE PROTOCOL (design §3.1). A rule that has not been reviewed by
a qualified human ships with status="candidate" and CANNOT FIRE. It exists here
so a reviewer has something executable to act on rather than prose, and so the
eventual coded version is the thing that was approved. Activating one is an
explicit status change recording who reviewed it — not a side effect of anything
else. The five steps:

  1. Draft the rule as a deterministic threshold check.
  2. Cite a live-verified primary source: captured URL, the specific provision,
     and the date the check was performed. Never a recalled section number.
  3. Ship it INACTIVE.
  4. Activating requires an explicit status change plus reviewed_by/reviewed_on.
  5. Citation-checking NEVER substitutes for interpretation. Confirming a
     provision exists and says what is quoted is a different act from judging
     that a threshold correctly implements it.

WHY THAT PROTOCOL, CONCRETELY. optimizer.py's BASIC_PCT_MIN = 0.50 is right
today because it was checked against a live source after a training cutoff had
produced a confidently-worded wrong value. Indian payroll law changed for
FY 2026-27. A rule drafted from an LLM's recall in this domain carries the same
risk, and a confidently-worded wrong compliance rule is worse than an absent one
because an absent rule is visibly absent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

ACTIVE = "active"
CANDIDATE = "candidate"

# What KIND of claim a rule makes. This is not decoration: it determines what
# evidence the rule needs, and demanding the wrong kind is actively harmful.
#
# STATUTORY — "the law requires this". Needs a provision and a source that can
#   be fetched and read. R1 (Code on Wages 2025) and R5 (Section 17(2)(vii))
#   are the only two of the original six that make this claim.
# CONVENTION — "this is unusual, or outside typical policy, and worth
#   confirming". Needs a stated basis, NOT a statute. R2, R3, R4 and R6 are
#   these. Demanding a citation from a convention rule does not make it more
#   rigorous; it pressures whoever writes it into attaching a provision that
#   does not actually say what the rule claims, which is worse than no citation
#   because it looks like evidence.
STATUTORY = "statutory"
CONVENTION = "convention"


@dataclass(frozen=True)
class Rule:
    """
    One compliance rule. Frozen because a rule's identity, text and status
    should never be mutated in place by application code — activating a
    candidate is a source change that shows up in a diff, which is what makes
    the diff the audit trail (design §6).
    """
    id: str
    severity: str                    # High | Medium | Low
    check: str                       # short human-readable condition, for the table
    rationale: str                   # the exact text emitted on a flag, addressed
                                     # to the user: what is wrong with THIS structure
    why: str                         # why the rule exists at all, addressed to a
                                     # reader of the rule set — a reviewer or a CA.
                                     # A DIFFERENT REGISTER, not a copy: see below.
    predicate: Callable              # (structure, rent_paid) -> bool
    status: str                      # ACTIVE | CANDIDATE
    claim_type: str = CONVENTION     # STATUTORY | CONVENTION — see above

    # ---- Evidence for a STATUTORY claim -----------------------------------
    # These assert exactly ONE thing: that the cited provision exists and says
    # what this rule quotes. They assert NOTHING about whether the predicate
    # above is a correct implementation of it. A section number can be verified
    # by fetching a document; whether "< 50% of CTC" is the right threshold,
    # with the right rounding and the right edge-case handling, cannot be.
    source_url: str = ""
    provision: str = ""
    citation_checked_on: str = ""    # ISO date the SOURCE was fetched and read

    # ---- Evidence for a CONVENTION claim ----------------------------------
    # What makes this the typical or expected norm. Deliberately not a URL
    # field: the honest answer is often "industry practice" or "this tool's own
    # scope decision", and dressing that up as a citation would misrepresent it.
    basis: str = ""

    # ---- The human judgement, which is a DIFFERENT claim -------------------
    # reviewed_by asserts that a qualified person judged this rule's PREDICATE
    # to be a correct implementation of its stated claim. That is the assertion
    # citation-checking cannot make and no amount of source-fetching produces.
    # Required to be ACTIVE.
    reviewed_by: str = ""
    reviewed_on: str = ""

    @property
    def is_active(self) -> bool:
        return self.status == ACTIVE

    @property
    def citation_is_checked(self) -> bool:
        """
        The provision was fetched and read. NOT the same as reviewed: this says
        the source exists and says what is quoted, and says nothing about
        whether the predicate implements it correctly.
        """
        return bool(self.citation_checked_on.strip())

    @property
    def implementation_is_reviewed(self) -> bool:
        """A qualified human judged the predicate a correct implementation."""
        return bool(self.reviewed_by.strip() and self.reviewed_on.strip())


# ---------------------------------------------------------------------------
# R1-R6. `rationale` is copied BYTE-FOR-BYTE from ai_layer._check_rules(), so
# the migration changes no output. `why` is copied byte-for-byte from
# compliance_rules.md's table.
#
# TWO FIELDS, NOT ONE THAT DRIFTED — a correction to how step 1 described this.
# The two texts differ for all six rules, and comparing them shows why: they are
# different registers, written for different readers, and neither is a stale
# copy of the other. R2 is the clearest example:
#
#   rationale (emitted, addressed to the user):
#     "No employer PF component despite CTC above Rs 6L/year — PF is
#      near-universal at this level; confirm this isn't an oversight."
#   why (documentation, addressed to a reviewer):
#     "PF is near-universal for salaried employees above minimum wage
#      thresholds; a missing PF component at this CTC level is unusual and
#      worth confirming isn't an oversight"
#
# Collapsing them would have destroyed the documentation register that the
# generated table exists to present — the readable artefact a CA opens first.
#
# The REAL problem was never that one had drifted from the other: it is that
# they were maintained in two files with nothing linking them, so a rule's
# justification could change in one and not the other and nothing would notice.
# Holding both on one object fixes that without flattening the distinction.
# ---------------------------------------------------------------------------

RULES: tuple = (
    Rule(
        id="R1", severity="High",
        check="Basic salary < 50% of CTC",
        rationale="Basic salary is below 50% of CTC, violating the Code on Wages 2025 requirement that Basic + DA be at least 50% of total remuneration (no DA field in this tool — Basic alone is the relevant component for a private-sector structure). This triggers automatic reclassification of the excess allowances as \"wages\" for PF and gratuity purposes, not just a market-convention miss.",
        why="Statutory violation, not a soft convention: the Code on Wages 2025 (effective 21 Nov 2025) requires Basic + DA to be at least 50% of total remuneration — this tool has no separate DA field (scoped to private-sector employees, where DA doesn't apply), so Basic alone is the relevant component. Falling below this line triggers automatic reclassification of the excess allowances as \"wages\" for PF and gratuity purposes, with real penalty exposure — not just a market-convention miss",
        predicate=lambda s, rent_paid: (s.basic / s.ctc if s.ctc else 0) < 0.50,
        claim_type=STATUTORY,
        status=ACTIVE,
    ),
    Rule(
        id="R2", severity="Medium",
        check="CTC > Rs 6L/year but employer PF = 0",
        rationale="No employer PF component despite CTC above Rs 6L/year — PF is near-universal at this level; confirm this isn't an oversight.",
        why="PF is near-universal for salaried employees above minimum wage thresholds; a missing PF component at this CTC level is unusual and worth confirming isn't an oversight",
        predicate=lambda s, rent_paid: s.ctc > 600_000 and s.employer_pf == 0,
        claim_type=CONVENTION,
        status=ACTIVE,
    ),
    Rule(
        id="R3", severity="Low",
        check="HRA claimed but rent_paid = 0 or not provided",
        rationale="HRA is structured into the salary but no rent payment was provided — the HRA exemption requires actual rent with documentation.",
        why="HRA exemption requires actual rent payment with supporting documentation; claiming HRA structure without a rent input suggests the exemption may not be realizable",
        predicate=lambda s, rent_paid: s.hra > 0 and rent_paid <= 0,
        claim_type=CONVENTION,
        status=ACTIVE,
    ),
    Rule(
        id="R4", severity="Low",
        check="LTA > 10% of CTC",
        rationale="LTA exceeds 10% of CTC, above typical company policy ceilings, and may not be realizable given actual travel requirements.",
        why="Exceeds typical company LTA policy ceilings; may not be realizable given actual travel-and-bills requirements",
        predicate=lambda s, rent_paid: bool(s.ctc) and s.lta > 0.10 * s.ctc,
        claim_type=CONVENTION,
        status=ACTIVE,
    ),
    Rule(
        id="R5", severity="High",
        check="Aggregate employer PF + NPS > Rs 7.5L/year",
        rationale="Aggregate employer PF + NPS exceeds Rs 7.5L/year — the excess is a taxable perquisite under Section 17(2)(vii), which this tool's tax engine does not currently model.",
        why="The excess over Rs 7.5L is a taxable perquisite under Section 17(2)(vii) — NOT currently modeled in tax_engine.py's tax calculation, so any structure crossing this threshold has an unmodeled tax liability the tool doesn't account for",
        predicate=lambda s, rent_paid: (s.employer_pf + s.employer_nps) > 750_000,
        claim_type=STATUTORY,
        status=ACTIVE,
    ),
    Rule(
        id="R6", severity="Low",
        check="Special allowance = 0",
        rationale="Special allowance is zero, leaving no flexible cash component — check this wasn't an input error.",
        why="Leaves no flexible cash component; unusual structure that may indicate an input error rather than a deliberate choice",
        predicate=lambda s, rent_paid: s.special_allowance == 0,
        claim_type=CONVENTION,
        status=ACTIVE,
    ),
)


# R1-R6 predate the candidate-rule protocol. They were verified through the
# README's "Regulatory currency" pass — a real check, but performed against the
# rule set as a whole rather than per-rule, so they carry no per-rule
# source_url/provision/reviewed_by.
#
# Named explicitly rather than handled by "provenance is optional", because an
# optional field exempts every FUTURE rule too. This set is closed: anything
# added from now on must carry provenance to be active, and the test that
# enforces it reads this set rather than a length or a date.
PRE_PROTOCOL_RULE_IDS = frozenset({"R1", "R2", "R3", "R4", "R5", "R6"})


def protocol_violations() -> list:
    """
    Ways the rule set violates the candidate-rule protocol, as readable strings.
    Empty means compliant.

    Requirements differ BY CLAIM TYPE, because a convention rule has no statute
    to cite and demanding one would produce a fabricated citation — evidence
    that looks stronger than it is.

    Note what is NOT checked here, deliberately: nothing in this function can
    tell whether a predicate correctly implements the claim its rule makes.
    That is what reviewed_by exists to record, and it is the one assertion no
    automated check can produce.
    """
    problems = []
    for rule in RULES:
        pre = rule.id in PRE_PROTOCOL_RULE_IDS

        if rule.claim_type not in (STATUTORY, CONVENTION):
            problems.append(f"{rule.id} has unknown claim_type {rule.claim_type!r}")

        if rule.is_active and not pre and not rule.implementation_is_reviewed:
            # Activation requires the HUMAN claim, not the citation claim. A
            # rule with a perfect citation and no reviewer has had its source
            # confirmed and its implementation confirmed by nobody.
            problems.append(
                f"{rule.id} is active but no one has reviewed the implementation "
                f"(reviewed_by/reviewed_on)")

        if not pre:
            if rule.claim_type == STATUTORY:
                for field in ("source_url", "provision", "citation_checked_on"):
                    if not getattr(rule, field).strip():
                        problems.append(f"{rule.id} claims statute but carries no {field}")
            elif rule.claim_type == CONVENTION:
                if not rule.basis.strip():
                    problems.append(f"{rule.id} is a convention rule with no stated basis")
                if rule.provision.strip() or rule.source_url.strip():
                    # A convention rule carrying a provision is either
                    # mislabelled or is citing a statute that does not actually
                    # require what it claims.
                    problems.append(
                        f"{rule.id} is a convention rule but cites a provision — "
                        f"either it is statutory and mislabelled, or the citation "
                        f"does not say what the rule claims")
    return problems


def active_rules() -> tuple:
    """
    The rules that may actually fire. Candidates are excluded HERE, once, rather
    than at each call site — a gate that has to be remembered is a gate that
    eventually is not.
    """
    return tuple(r for r in RULES if r.is_active)


def candidate_rules() -> tuple:
    return tuple(r for r in RULES if not r.is_active)


def total_active() -> int:
    """
    Replaces the hand-declared TOTAL_COMPLIANCE_RULES = 6. Derived, so adding a
    rule cannot leave the denominator stale — and candidates are excluded, since
    a rule that cannot fire must not make a compliance score look better by
    inflating the total (design §3.4).
    """
    return len(active_rules())
