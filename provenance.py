"""
provenance.py — the evidence model, independent of what carries it.

EXTRACTED FROM compliance_rules.py (LEGAL_CLAIM_INVENTORY_DESIGN.md §4.3,
Phase 2.4 step 2). It lived there because compliance rules were the only things
that carried provenance. They are not: this codebase makes roughly 25 legal
claims across 8 files, and the rule set is the SMALLEST concentration of them.
tax_engine.py's slab tables, payroll_breakdown.py's five state PT tables,
penalty_exposure.py's EPF and TDS sections, and optimizer.py's Code on Wages
floor all assert law with none of this structure attached.

Given its own module rather than imported out of compliance_rules.py so that an
inventory of tax constants does not have to import the compliance rule set —
predicates, RULES and all — merely to describe a number. That is a dependency
an inventory should not carry, not just an untidy one.

STRUCTURAL ONLY. Nothing here is new and nothing behaves differently.
compliance_rules.py re-exports every name, so its callers are untouched.
"""

from __future__ import annotations

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

# citation_checked_on has THREE distinguishable states, not two. "Nobody has
# tried" and "someone tried and could not get to a primary source" are
# different facts, and the second is worse: it means the claim is uncheckable
# from here, not merely unchecked. Collapsing them into an empty string would
# lose exactly the information a reviewer needs.
#
#   ""                      -> never attempted
#   "unresolved: <reason>"  -> attempted, no stable primary source reached
#   "2026-09-09"            -> fetched and read on that date
UNRESOLVED = "unresolved: "

# Whether the cited INSTRUMENT is still the governing law. Separate from
# whether the cited TEXT says what the rule claims, because those can diverge
# in the worst possible direction: a citation can match its source perfectly
# and still point at a repealed Act. That combination reads as verified while
# citing dead law — strictly worse than an unresolved citation, which at least
# surfaces as a visible gap.
IN_FORCE = "in_force"
SUPERSEDED = "superseded"
INSTRUMENT_UNKNOWN = "unknown"

class ProvenanceMixin:
    """
    The evidence model, extracted so it can describe things that are NOT
    compliance rules (LEGAL_CLAIM_INVENTORY_DESIGN.md §4.3).

    WHAT WAS ALREADY GENERIC, MEASURED BEFORE MOVING ANYTHING: every property
    below reads ONLY provenance fields — never predicate, severity, check,
    rationale or why. So did 8 of the 10 checks in protocol_violations(). The
    evidence model was general; only its container was not.

    WHY A PROPERTIES MIXIN AND NOT A SHARED DATACLASS BASE. This project runs
    on Python 3.9, where dataclass field inheritance cannot put required fields
    on a subclass of a base with defaults, and `kw_only` does not exist:

        @dataclass
        class B: x: str = ""
        @dataclass
        class D(B): y: str
        -> TypeError: non-default argument 'y' follows default argument

    So the provenance FIELDS are declared on each carrier and the LOGIC lives
    here once. That leaves two field lists that could drift, which is a real
    cost and is not hand-waved: a test asserts the two sets agree. Same
    deliberate-second-copy-plus-a-test shape as §4.5's value check, for the
    same reason — the alternative that cannot drift also cannot be checked.
    """

    # What a recorded reviewer is ASSERTING. Overridden per carrier because the
    # act genuinely differs: for a compliance rule it is "this predicate
    # correctly implements the claim"; for a legal claim it is "this value
    # matches the cited source". Both are human judgements no check can make,
    # but a message that names the wrong one sends a reviewer to the wrong task.
    REVIEW_MEANS = "reviewed the implementation"

    @property
    def is_live(self) -> bool:
        """
        Whether this claim is in force in the running system.

        Defaults to True, and that default carries the phase's central finding
        (design §4.4): A RULE CAN BE INERT, A CONSTANT CANNOT. A compliance
        rule is optional — an unreviewed one ships as a candidate and costs
        nothing while it waits. A load-bearing constant like STANDARD_DEDUCTION
        is read on every tax computation and has no inert state to park it in.
        So for anything that is not a Rule, this is unconditionally True: being
        unverified is a live risk, not a safe holding pen. Rule overrides it.
        """
        return True

    @property
    def citation_is_checked(self) -> bool:
        """
        The provision was fetched and read. NOT the same as reviewed: this says
        the source exists and says what is quoted, and says nothing about
        whether the predicate implements it correctly.
        """
        value = self.citation_checked_on.strip()
        if not value or value.startswith(UNRESOLVED):
            return False
        # A matched text in a repealed Act is not a verified citation. Requiring
        # the instrument to be in force is what stops a rule going green while
        # pointing at law that no longer governs.
        return self.instrument_status == IN_FORCE

    @property
    def cites_superseded_law(self) -> bool:
        """
        The cited instrument has been repealed or replaced. The rule may still
        describe a real obligation — the successor Act usually carries the rule
        forward somewhere — but this citation no longer locates it.
        """
        return self.instrument_status == SUPERSEDED

    @property
    def citation_attempt_unresolved(self) -> bool:
        """
        Someone tried to reach a primary source and could not. Distinct from
        never having tried, and distinct from having succeeded — a rule in this
        state is making a statutory claim nobody has been able to confirm.
        """
        return self.citation_checked_on.strip().startswith(UNRESOLVED)

    @property
    def implementation_is_reviewed(self) -> bool:
        """A qualified human judged the predicate a correct implementation."""
        return bool(self.reviewed_by.strip() and self.reviewed_on.strip())



def provenance_violations(items, pre_protocol_ids=frozenset()) -> list:
    """
    Ways a COLLECTION of provenance-carrying things violates the protocol, as
    readable strings. Empty means compliant.

    Takes its collection rather than reading module-level RULES, which was one
    of exactly three things coupling this check to compliance rules
    (LEGAL_CLAIM_INVENTORY_DESIGN.md §4.3). The other two were `is_active`,
    now generalized to `is_live` on ProvenanceMixin, and PRE_PROTOCOL_RULE_IDS,
    now a parameter. Nothing below reads a predicate, a severity or any
    user-facing text, so it applies unchanged to a legal-claim inventory.

    Requirements differ BY CLAIM TYPE, because a convention rule has no statute
    to cite and demanding one would produce a fabricated citation — evidence
    that looks stronger than it is.

    Note what is NOT checked here, deliberately: nothing in this function can
    tell whether a predicate correctly implements the claim its rule makes.
    That is what reviewed_by exists to record, and it is the one assertion no
    automated check can produce.
    """
    problems = []
    for rule in items:
        pre = rule.id in pre_protocol_ids

        if rule.claim_type not in (STATUTORY, CONVENTION):
            problems.append(f"{rule.id} has unknown claim_type {rule.claim_type!r}")

        if rule.is_live and not pre and not rule.implementation_is_reviewed:
            # Activation requires the HUMAN claim, not the citation claim. A
            # rule with a perfect citation and no reviewer has had its source
            # confirmed and its implementation confirmed by nobody.
            problems.append(
                f"{rule.id} is live but no one has {rule.REVIEW_MEANS} "
                f"(reviewed_by/reviewed_on)")

        # CHECK 1 + 2 apply to every statutory rule, grandfathered or not.
        # R1 and R5 are exempt from having a BACKDATED reviewer, not from being
        # citable: a rule asserting that the law requires something, with no
        # provision recorded and no attempt logged, is unverifiable by anyone.
        if rule.claim_type == STATUTORY:
            for field in ("source_url", "provision"):
                if not getattr(rule, field).strip():
                    problems.append(f"{rule.id} claims statute but carries no {field}")
            # CHECK 2: a citation nobody has even attempted to reach. The
            # unresolved marker satisfies this — "tried and could not" is a
            # recorded outcome; silence is not.
            if not rule.citation_checked_on.strip():
                problems.append(
                    # Deliberately does NOT say "cites a provision but ...".
                    # That wording was written when only rules carried
                    # provenance and every statutory rule had a provision
                    # recorded. A legal claim can make a statutory claim with
                    # NO provision at all, and telling its reader it cites one
                    # is simply false.
                    f"{rule.id} records no citation_checked_on "
                    f"(neither a check date nor an unresolved attempt)")
            # CHECK 5: which instrument, and does it still govern.
            if not rule.instrument.strip():
                problems.append(
                    f"{rule.id} cites a provision without naming the instrument it "
                    f"belongs to — a section number is meaningless without an Act")
            if rule.instrument_status not in (IN_FORCE, SUPERSEDED, INSTRUMENT_UNKNOWN):
                problems.append(
                    f"{rule.id} has unknown instrument_status {rule.instrument_status!r}")
            if rule.is_live and rule.cites_superseded_law:
                problems.append(
                    f"{rule.id} is LIVE and cites a superseded instrument "
                    f"({rule.instrument}) — the obligation may survive in the "
                    f"successor Act, but this citation no longer locates it")

        # CHECK 3 applies to every convention rule, grandfathered or not: an
        # unstated basis is exactly as unreviewable as an unstated citation.
        if rule.claim_type == CONVENTION:
            if not rule.basis.strip():
                problems.append(f"{rule.id} is a convention rule with no stated basis")

        # CHECK 6: the threshold-origin question, asked of EVERY claim type.
        # Deliberately not restricted to convention rules even though that is
        # where the gap was found: a statutory rule can also carry a number the
        # provision does not actually specify, and the same question catches it.
        #
        # PRESENCE ONLY. This cannot tell a true answer from a confident wrong
        # one. It exists so that no candidate advances with the question
        # unanswered — process enforcement, with the code holding the door.
        if not pre and not rule.threshold_origin.strip():
            problems.append(
                f"{rule.id} does not say where its threshold number came from "
                f"(threshold_origin): every candidate must state in writing "
                f"whether the number is derived from a statute, and how that is "
                f"known, before it can advance")

        if not pre:
            if rule.claim_type == CONVENTION:
                if rule.provision.strip() or rule.source_url.strip():
                    # A convention rule carrying a provision is either
                    # mislabelled or is citing a statute that does not actually
                    # require what it claims.
                    problems.append(
                        f"{rule.id} is a convention rule but cites a provision — "
                        f"either it is statutory and mislabelled, or the citation "
                        f"does not say what the rule claims")
    return problems
