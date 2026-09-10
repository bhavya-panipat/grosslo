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
    INSTRUMENT_UNKNOWN, STATUTORY, ProvenanceMixin, provenance_violations,
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

CLAIMS: tuple = ()


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
