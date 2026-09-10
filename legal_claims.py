"""
legal_claims.py — every legal claim this codebase makes, as data
(LEGAL_CLAIM_INVENTORY_DESIGN.md, Roadmap Phase 2.4).

WHY THIS EXISTS. optimizer.py's Code on Wages floor sat wrong until a human
happened to go looking. A change monitor would not have caught it: BASIC_PCT_MIN
is a module constant with no provision and no instrument, and the value was
wrong from birth rather than changed underneath us. A monitor diffs now against
a recorded earlier state; started today it has no "before" for anything. Over an
unverified corpus it reports "nothing changed" against a state nobody confirmed
— the same shape as RLS policies present but silently unenforced in Phase 1.1.

So the deliverable is the INVENTORY: make the truth-status of every legal claim
visible, most of it honestly unverified. The monitor is a small thing on top.

THE FINDING THAT SHAPES THIS FILE, and the one place instincts from Phase 2.2
will mislead: A RULE CAN BE INERT, A CONSTANT CANNOT (design §4.4). 2.2's
candidate gate works because a compliance rule is optional — an unreviewed one
ships inert and costs nothing while it waits. STANDARD_DEDUCTION is read on
every tax computation. There is no inert state to park it in and no way to make
it cost nothing. `unverified` here is a LIVE RISK, recorded — not a safe holding
pen. ProvenanceMixin.is_live defaults True for exactly this reason, and nothing
in this file overrides it.

WHAT A CLAIM NEVER DOES: change a value. Every number described here keeps
living in the module that owns it, untouched. This file is additive metadata
over tax math that does not move, held to the characterization baseline's
byte-identical standard.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass

from provenance import (
    IN_FORCE, INSTRUMENT_UNKNOWN, STATUTORY, ProvenanceMixin,
    provenance_violations,
)


class SymbolMissingError(RuntimeError):
    """
    A claim names a module attribute that no longer exists.

    Its own failure mode, separate from value drift, because the two mean
    different things: a changed value is a number someone edited, while a
    missing symbol is a claim describing code that has been deleted or renamed
    — a claim about nothing. Named rather than left as a bare AttributeError so
    the message says which claim, which symbol, and what to do about it.
    """


@dataclass(frozen=True)
class Claim(ProvenanceMixin):
    """
    One legal claim made somewhere in this codebase.

    Deliberately carries NO predicate, severity, or user-facing text. Those are
    compliance-rule concepts and do not generalize — a slab table does not fire,
    and STANDARD_DEDUCTION has no rationale to show a user.

    THE PROVENANCE FIELDS ARE DECLARED HERE AS WELL AS ON Rule, and that
    duplication is a real cost rather than an oversight. Python 3.9 has no
    dataclass `kw_only`, and a dataclass with required fields cannot subclass
    one whose fields are defaulted, so the field list cannot be inherited. The
    LOGIC lives once, in ProvenanceMixin; the field NAMES are written twice and
    a test asserts the two sets agree. Same deliberate-second-copy-plus-a-test
    shape as asserted_value below, for the same reason: the alternative that
    cannot drift also cannot be checked.
    """
    id: str
    module: str               # e.g. "tax_engine"
    symbol: str               # e.g. "STANDARD_DEDUCTION"
    describes: str            # what this number is, in a sentence

    # A HAND-RECORDED COPY of the value, and the copying is the mechanism
    # (design §4.5). Having the claim read the live constant instead cannot
    # drift — and cannot check anything either, because it would agree with the
    # code by construction. That is the TOTAL_COMPLIANCE_RULES derived-once
    # mistake in new packaging. Two copies plus a comparison is the point.
    asserted_value: object

    claim_type: str = STATUTORY

    # ---- provenance: see the class docstring on why these are re-declared ----
    source_url: str = ""
    provision: str = ""
    citation_checked_on: str = ""
    instrument: str = ""
    instrument_status: str = INSTRUMENT_UNKNOWN
    basis: str = ""
    threshold_origin: str = ""
    reviewed_by: str = ""
    reviewed_on: str = ""

    # For a claim, a reviewer asserts the VALUE matches the cited source — not
    # that a predicate is a correct implementation. See ProvenanceMixin.
    REVIEW_MEANS = "verified the value against the cited source"

    @property
    def where(self) -> str:
        return f"{self.module}.{self.symbol}"

    def live_value(self):
        """The value as the running code actually holds it, read fresh."""
        module = importlib.import_module(self.module)
        try:
            return getattr(module, self.symbol)
        except AttributeError:
            raise SymbolMissingError(
                f"{self.id} describes {self.where}, which no longer exists. "
                f"The claim is describing code that has been deleted or "
                f"renamed. Update the claim to point at the current symbol, or "
                f"remove it if the number it described is gone.") from None

    @property
    def value_has_drifted(self) -> bool:
        """
        The code's value no longer matches what was recorded and verified.

        This is the ONE thing §4.5's mechanism detects, and its limit is worth
        stating as plainly as its capability: it catches a value silently
        changed without its citation being re-verified, and NOTHING ELSE. It
        cannot catch the law moving while the code sits still — no local check
        can, and no automated check here can either, given the access wall.
        """
        return self.live_value() != self.asserted_value


# ---------------------------------------------------------------------------
# THE INVENTORY. Empty at step 2 on purpose: the mechanism is built and proven
# before anything depends on it, exactly as 2.2 built the candidate gate and
# proved it in both directions while zero candidates existed.
#
# Nothing here is grandfathered. PRE_PROTOCOL_RULE_IDS exists in the rule set
# because R1-R6 predate the protocol; this inventory has no such history, so
# every claim answers for itself from the first one.
# ---------------------------------------------------------------------------

CLAIMS: tuple = (
    # -----------------------------------------------------------------------
    # FIRST BATCH — tax_engine.py's core figures only (design §5). Four claims,
    # chosen because every tax number this tool produces depends on them.
    #
    # DELIBERATELY DEFERRED AND NAMED, so the boundary is explicit rather than
    # an oversight: CESS_RATE, EMPLOYER_PF_RATE, PF_WAGE_CEILING_BASIC,
    # REBATE_87A_THRESHOLD and REBATE_87A_MAX are equally statutory and sit in
    # the same file; payroll_breakdown.py's five state PT tables,
    # penalty_exposure.py's EPF and TDS sections, optimizer.py's Code on Wages
    # floor and ai_layer.py's section citations follow once the shape is proven.
    #
    # ALL FOUR LAND UNVERIFIED, AND THAT IS THE BATCH WORKING. The purpose is to
    # make truth-status visible, and the visible truth is that four of the most
    # load-bearing numbers in this system rest on nothing recorded.
    #
    # WHAT THE REPOSITORY ACTUALLY RECORDS, and the distinction that decided
    # every citation_checked_on below: tax_engine.py's docstring describes a
    # citation sweep on 2026-09-02 that re-verified SECTION NUMBERS (87A->156,
    # 80CCD(2)->124, 201(1A)->398(3), 271C->448). It did not verify the VALUES.
    # A sweep confirming that a section was renumbered says nothing about
    # whether the figures in these tables match what that section now says.
    #
    # `instrument` records which Act the CODE is claiming to implement — the
    # Income-tax Act, 2025, per COMPLIANCE_BREADTH_DESIGN.md §3.5's scope
    # decision. Whether these values actually match that Act is precisely what
    # is unverified, and that lives in citation_checked_on, not here.
    # -----------------------------------------------------------------------
    Claim(
        id="TE1", module="tax_engine", symbol="NEW_REGIME_SLABS",
        describes="New-regime income tax slab boundaries and rates: nil to Rs 4L, "
                  "then 5/10/15/20/25% bands, 30% above Rs 24L.",
        asserted_value=[(400_000, 0.00), (800_000, 0.05), (1_200_000, 0.10),
                        (1_600_000, 0.15), (2_000_000, 0.20), (2_400_000, 0.25),
                        (float("inf"), 0.30)],
        claim_type=STATUTORY,
        instrument="Income-tax Act, 2025 (Act 30 of 2025)",
        instrument_status=IN_FORCE,
        threshold_origin="STATUTORY, and that is the whole point of the claim: "
                         "these are not thresholds this tool chose but figures "
                         "the Act sets. Nothing here is an engineering "
                         "judgement, so there is no judgement to justify -- "
                         "only a citation to produce, which is what is missing.",
        # NOT "unresolved": nobody has attempted to verify these VALUES against a
        # source at all. That is a different and less bad state than "tried and
        # could not reach one", and collapsing the two would lose exactly what a
        # reviewer needs. The 2026-09-02 sweep covered section numbers only.
        citation_checked_on="",
    ),
    Claim(
        id="TE2", module="tax_engine", symbol="OLD_REGIME_SLABS",
        describes="Old-regime income tax slab boundaries and rates: nil to Rs 2.5L, "
                  "5% to Rs 5L, 20% to Rs 10L, 30% above.",
        asserted_value=[(250_000, 0.00), (500_000, 0.05), (1_000_000, 0.20),
                        (float("inf"), 0.30)],
        claim_type=STATUTORY,
        instrument="Income-tax Act, 2025 (Act 30 of 2025)",
        instrument_status=IN_FORCE,
        threshold_origin="STATUTORY -- set by the Act, not chosen here. See TE1.",
        citation_checked_on="",
    ),
    Claim(
        id="TE3", module="tax_engine", symbol="STANDARD_DEDUCTION",
        describes="Flat standard deduction from salary income: Rs 75,000 under the "
                  "new regime, Rs 50,000 under the old.",
        asserted_value={"new": 75_000, "old": 50_000},
        claim_type=STATUTORY,
        instrument="Income-tax Act, 2025 (Act 30 of 2025)",
        instrument_status=IN_FORCE,
        threshold_origin="STATUTORY -- set by the Act, not chosen here. See TE1.",
        citation_checked_on="",
    ),
    Claim(
        id="TE4", module="tax_engine", symbol="NPS_80CCD2_CAP_PCT",
        describes="Employer NPS contribution deductible as a percentage of basic: "
                  "14% under the new regime, 10% under the old.",
        asserted_value={"new": 0.14, "old": 0.10},
        claim_type=STATUTORY,
        # The ONE claim in this batch with a provision recorded anywhere in the
        # repository, and it is recorded here because the repo records it -- not
        # because it is confirmed. README's "Regulatory currency" section and
        # tax_engine.py's own docstring both name this mapping.
        provision="Section 124, read with Schedule XV (formerly s. 80CCD(2) of "
                  "the Income-tax Act, 1961) -- employer contribution to the "
                  "National Pension System deductible from salary income.",
        source_url="https://www.incometaxindia.gov.in/pages/acts/income-tax-act.aspx",
        instrument="Income-tax Act, 2025 (Act 30 of 2025)",
        instrument_status=IN_FORCE,
        threshold_origin="STATUTORY -- the 10%/14% split is set by the Act. See TE1.",
        citation_checked_on="unresolved: attempted 2026-09-10 and NOT resolved to a "
                            "primary source. What the repository records is a "
                            "2026-09-01 README pass and a 2026-09-02 sweep in "
                            "tax_engine.py's docstring, both against SECONDARY "
                            "sources, which this project's own standard refuses to "
                            "treat as verification (COMPLIANCE_BREADTH_DESIGN.md "
                            "§3.1 step 2). Those record the SECTION renumbering "
                            "80CCD(2) -> 124; the README additionally states the "
                            "10%/14% split is unchanged. Primary sources remain "
                            "unreachable from this environment -- see "
                            "docs/PRIMARY_SOURCE_LOOKUP_TASK.md. Recorded as "
                            "attempted-and-unresolved rather than verified.",
    ),
)


def evidence_findings() -> list:
    """
    What the inventory has not established, via the shared checker.

    NON-BLOCKING UNTIL 2026-12-09 (design §6). Every claim will appear here on
    day one, because none has a recorded verifier and is_live defaults True.
    That is the inventory working, not failing: the visible truth is that these
    numbers rest on nothing recorded. Blocking on day one would turn the signal
    into an obstacle to be silenced rather than acted on.
    """
    return provenance_violations(CLAIMS)


def drift_findings() -> list:
    """
    Claims whose recorded value no longer matches the code.

    BLOCKING, and the distinction from evidence_findings() is deliberate rather
    than inconsistent. The "would fail on day one" objection that makes evidence
    findings non-blocking does not apply here: on day one nothing has drifted,
    so this check is empty and stays empty until someone changes a number
    without re-verifying it — which is precisely the event worth stopping.
    """
    problems = []
    for claim in CLAIMS:
        if claim.value_has_drifted:
            problems.append(
                f"{claim.id}: {claim.where} is now {claim.live_value()!r} but "
                f"the claim records {claim.asserted_value!r} as the verified "
                f"value. The number changed and its citation was not "
                f"re-verified. Re-check the source, then update BOTH "
                f"asserted_value and citation_checked_on — updating the value "
                f"alone reinstates exactly the state this check exists to find.")
    return problems
