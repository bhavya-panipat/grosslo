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
#   be fetched and read. R1 (Code on Wages, 2019) and R5 (Income-tax Act,
#   2025, s. 17(1)(h), formerly 1961 s. 17(2)(vii)) are the only two of the
#   original six that make this claim. (This comment used to name R1's Act by
#   its 2025 commencement year, repeating R1's own emitted-text error, and R5
#   by its repealed 1961 section. R1's EMITTED text is still left as-is for a
#   CA to rule on; a comment is not emitted, so it is simply corrected.)
# CONVENTION — "this is unusual, or outside typical policy, and worth
#   confirming". Needs a stated basis, NOT a statute. R2, R3, R4 and R6 are
#   these. Demanding a citation from a convention rule does not make it more
#   rigorous; it pressures whoever writes it into attaching a provision that
#   does not actually say what the rule claims, which is worse than no citation
#   because it looks like evidence.
STATUTORY = "statutory"
CONVENTION = "convention"

# NON_APPLICABILITY — "the law does NOT require this, and here is the authority
# for that" (INVENTORY_EXPANSION_DESIGN.md §2.3). Needs the same citation
# evidence as STATUTORY, because it is a statutory claim: it asserts what a
# provision does not reach, which is as checkable and as falsifiable as
# asserting what it does.
#
# WHY IT IS WORTH INVENTORYING AT ALL, given it describes something the code
# does NOT do: a reasoned exclusion rots invisibly. If the authority behind it
# is overruled, or the tool's scope changes so the provision starts applying,
# nothing in the codebase notices — and the absence of a penalty model is far
# harder to spot than a wrong number would be. An absent thing is harder to
# notice than a wrong one, which is this project's most repeated lesson.
NON_APPLICABILITY = "non_applicability"
CLAIM_TYPES = (STATUTORY, CONVENTION, NON_APPLICABILITY)

# The claim types that make an assertion about a statute and therefore owe a
# citation. NON_APPLICABILITY is here deliberately: "this provision does not
# apply" is not a softer claim than "this provision requires X", and letting it
# ship without a source would make the easiest way to avoid citing a provision
# be to assert it does not apply.
CITEABLE_CLAIM_TYPES = (STATUTORY, NON_APPLICABILITY)

# citation_checked_on has THREE distinguishable states, not two. "Nobody has
# tried" and "someone tried and could not get to a primary source" are
# different facts, and the second is worse: it means the claim is uncheckable
# from here, not merely unchecked. Collapsing them into an empty string would
# lose exactly the information a reviewer needs.
#
#   ""                      -> never attempted
#   "unresolved: <reason>"  -> attempted, no stable primary source reached
#   "2026-09-09"            -> fetched and read on that date
#
# WHAT A DATE HERE REQUIRES, and it is a standing rule rather than a judgement
# made per claim (INVENTORY_EXPANSION_DESIGN.md §5.1):
#
#   A verified citation must be sufficient for an INDEPENDENT PARTY TO REDO THE
#   CHECK. Evidence that a past check occurred is not the same thing.
#
# A named instrument someone can look up qualifies; a named, locatable
# government document qualifies. "Verified against multiple independent
# sources", with no source named, does not — it records that someone checked
# and gives nobody a way to check again. A date alone never qualifies: this
# field answers WHEN, and the trail lives in instrument/provision/source_url.
#
# COROLLARY, and it is the easy mistake: do NOT retroactively supply a trail
# the original check did not have. Going out today to find a better source and
# crediting it to a check made earlier on different evidence produces a claim
# that reads as verified on a basis nobody actually used — the fabricated
# citation failure in a subtler costume. Finding better evidence today is
# worthwhile; it is a NEW check, with today's date and today's source, never a
# backdated upgrade.
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

# WHAT KIND of instrument, which is separate from whether it still governs.
# instrument/instrument_status were designed when every citation in this
# codebase pointed at an Act. They do not (INVENTORY_EXPANSION_DESIGN.md §2.2):
#
#   KIND_ACT           primary legislation — "Income-tax Act, 2025"
#   KIND_SUBORDINATE   rules, schemes, notifications made under an Act — e.g.
#                      the Ministry of Labour notification of 15 June 2024 that
#                      set EPF s. 14B damages at 1%/month
#   KIND_JUDGMENT      a court decision — e.g. US Technologies v. CIT, which is
#                      why s. 448 is deliberately not modelled
#   KIND_CONSTITUTION  e.g. Article 276's Rs 2,500 annual ceiling on
#                      professional tax
#
# This is descriptive: no check branches on it beyond validating the value. It
# exists because WHAT IT TAKES TO RE-CHECK a citation differs by kind — an Act
# is looked up, a notification is searched for by date and subject, a judgment
# is read for what it actually held — and a reader who assumes "Act" when the
# instrument is a notification will look in the wrong place.
#
# A KIND_NONE_EXISTS was designed for Delhi, whose professional tax is zero
# because no Act has ever been enacted for the NCT. It was never used and is
# deleted: implementing it showed that an ABSENCE CANNOT BE CITED, and an
# "instrument: none" tag is indistinguishable from nobody having looked. Delhi
# cites Article 276 instead — the provision that PERMITS a professional tax
# without requiring one, which is what makes the absence lawful rather than an
# oversight. That is a stronger claim than an untethered tag, so the tag went
# rather than the claim.
KIND_ACT = "act"
KIND_SUBORDINATE = "subordinate"
KIND_JUDGMENT = "judgment"
KIND_CONSTITUTION = "constitution"
INSTRUMENT_KINDS = (KIND_ACT, KIND_SUBORDINATE, KIND_JUDGMENT,
                    KIND_CONSTITUTION)

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

    # KNOWN_DIVERGENCE — where the implementation DELIBERATELY does not match
    # the instrument, and why (INVENTORY_EXPANSION_DESIGN.md §2.4).
    #
    # This is a THIRD claim, separate from the two already here, and the gap it
    # fills is subtle: a citation can be verified AND the implementation correct
    # as designed, while the code still knowingly differs from the statute.
    # Maharashtra's professional tax varies by gender; this tool collects no
    # gender and uses the general — higher — slab. Tamil Nadu's is a half-yearly
    # assessment expressed as a monthly equivalent. Both are deliberate, both
    # conservative, both documented in payroll_breakdown.py, and nothing in the
    # evidence model could record either.
    #
    # Left unrecorded, `verified` reads as "matches the law exactly", and a
    # future reader either believes that or "fixes" a divergence that was
    # chosen. Empty means the implementation is INTENDED to match exactly, which
    # is itself an assertion rather than an absence of one.
    #
    # A divergence does NOT block verification: the citation claim and the
    # fidelity claim are different, exactly as citation_checked_on and
    # reviewed_by are different.
    known_divergence = ""

    # What a recorded reviewer is ASSERTING. Overridden per carrier because the
    # act genuinely differs: for a compliance rule it is "this predicate
    # correctly implements the claim"; for a legal claim it is "this value
    # matches the cited source". Both are human judgements no check can make,
    # but a message that names the wrong one sends a reviewer to the wrong task.
    REVIEW_MEANS = "reviewed the implementation"

    # Class-level fallback for fields the SHARED CHECKER reads. Both dataclass
    # carriers declare instrument_kind themselves and shadow this; it exists so
    # that adding a field to the evidence model cannot make provenance_violations
    # raise AttributeError on a carrier written before that field existed.
    # Found by the test stand-in doing exactly that when instrument_kind landed.
    #
    # It cannot mask a real omission on the two real carriers: a separate test
    # asserts their declared field sets agree.
    instrument_kind = KIND_ACT

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



def _looks_like_a_date(value: str) -> bool:
    """
    An ISO date, which is what a completed check records.

    Deliberately shape-only: this says the field holds a date, not that the date
    is plausible or that anything happened on it. Validating further would be
    checking the claim rather than its form, and that is a human's job.
    """
    parts = value.split("-")
    return (len(parts) == 3 and len(parts[0]) == 4
            and all(p.isdigit() for p in parts))


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

        if rule.claim_type not in CLAIM_TYPES:
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
        if rule.claim_type in CITEABLE_CLAIM_TYPES:
            # A RE-FINDABLE TRAIL, satisfied EITHER way. This check used to
            # demand source_url outright, which was always a proxy for
            # re-findability rather than the property itself — and the proxy
            # broke the moment a claim was verified without one.
            #
            # PT1 cites the Karnataka amending Act by name, amendment and year.
            # That is as followable as a link, arguably more durable than one,
            # and INVENTORY_EXPANSION_DESIGN.md §5.1 says so directly: "a named
            # instrument a reader can look up qualifies — its specificity is the
            # trail". Forcing a URL onto it would have meant either leaving a
            # verified claim permanently flagged, or inventing a link nobody
            # used, which §5.1's corollary forbids.
            #
            # A provision WITHOUT an instrument is not a trail — a section
            # number is meaningless without an Act — and the check below still
            # says so separately.
            has_url = bool(rule.source_url.strip())
            has_named_instrument = bool(rule.instrument.strip()
                                        and rule.provision.strip())
            if not (has_url or has_named_instrument):
                problems.append(
                    f"{rule.id} claims statute but carries no re-findable trail "
                    f"— needs either a source_url, or a named instrument "
                    f"together with the provision within it")
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
            if rule.instrument_kind not in INSTRUMENT_KINDS:
                problems.append(
                    f"{rule.id} has unknown instrument_kind {rule.instrument_kind!r} "
                    f"— expected one of {', '.join(INSTRUMENT_KINDS)}")
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

        # CHECK 7: a deliberate divergence nobody has signed off on. The
        # existing reviewer check does not express this — a claim can satisfy it
        # while the divergence itself was never put to anyone. Deciding that
        # using Maharashtra's general slab for every employee is an acceptable
        # conservative simplification is a bigger assertion than "the table
        # matches the Act", and it is the one a reviewer is really being asked
        # to make.
        if rule.known_divergence.strip() and not rule.implementation_is_reviewed:
            problems.append(
                f"{rule.id} knowingly diverges from its instrument and no one "
                f"has signed off on the divergence — this is a deliberate "
                f"departure from the law as written, not a stale value, and "
                f"needs a reviewer who accepts it rather than one who checks it")

        # CHECK 8: a citation state that is none of the three recognised ones.
        # Tracked from Stage C1, where this file's OWN data fell into the gap:
        # a reason was recorded without the "unresolved: " prefix, leaving two
        # claims neither checked nor attempted-unresolved — the exact silent
        # miscategorisation the three-valued convention exists to prevent.
        state = rule.citation_checked_on.strip()
        if state and not state.startswith(UNRESOLVED) and not _looks_like_a_date(state):
            problems.append(
                f"{rule.id} has a citation_checked_on that is neither empty, nor "
                f"an ISO date, nor prefixed \"{UNRESOLVED}\" — so it belongs to "
                f"none of the three recognised states and will be read as "
                f"unchecked-but-not-attempted, which is not what it says")

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
