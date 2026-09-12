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
    CONVENTION, IN_FORCE, INSTRUMENT_UNKNOWN, NON_APPLICABILITY, STATUTORY,
    KIND_ACT, KIND_SUBORDINATE, KIND_JUDGMENT, KIND_CONSTITUTION,
    ProvenanceMixin, provenance_violations,
)


class _NoValue:
    """
    Sentinel for a claim that asserts no value at all.

    NOT None, deliberately. None is a legitimate value for a constant to hold,
    so using it here would make "this claim has no value" indistinguishable from
    "this claim's value is None" — the same collapse-two-states-into-one mistake
    that citation_checked_on's three-valued convention exists to avoid.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self):
        return "NO_VALUE"


NO_VALUE = _NoValue()


class ValuelessClaimError(RuntimeError):
    """
    Raised when the drift check is asked about a claim that asserts no value.

    The alternative — returning False, meaning "has not drifted" — is what this
    exists to prevent. A NON_APPLICABILITY claim would then report as checked
    and fine on every run, having been checked by nothing. A green result
    nobody computed is worse than a visible gap, which is this project's
    recurring finding applied to its own checking machinery.
    """


class SymbolMissingError(RuntimeError):
    """
    A claim names a module attribute that no longer exists.

    Its own failure mode, separate from value drift, because the two mean
    different things: a changed value is a number someone edited, while a
    missing symbol is a claim describing code that has been deleted or renamed
    — a claim about nothing. Named rather than left as a bare AttributeError so
    the message says which claim, which symbol, and what to do about it.
    """


class KeyPathMissingError(SymbolMissingError):
    """
    The symbol exists but the key path into it does not.

    A SUBCLASS, because it is the same kind of failure at a finer grain — a
    claim describing something that is no longer there — so anything catching
    SymbolMissingError still catches this. Separate because the remedy differs:
    a missing symbol means the constant went away, while a missing key means
    the constant is still there and one entry inside it went away. For the PT
    table that is the difference between "professional tax was removed from
    this tool" and "a state was dropped from its coverage".
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
    # NO_VALUE for a claim that asserts no figure at all — see §2.3. A
    # NON_APPLICABILITY claim says a provision does not apply; there is no
    # number to compare, and §4.5's drift check cannot cover it.
    asserted_value: object

    # Keys to walk into the symbol's value, for a constant that holds MANY
    # independently-governed things (INVENTORY_EXPANSION_DESIGN.md §2.1).
    # PT_MONTHLY_TABLE is one Python name holding five separate state statutes;
    # Karnataka's Act changing has nothing to do with Telangana's, so one claim
    # per symbol cannot work — drift would be unattributable and one
    # citation_checked_on cannot describe five separately-verified tables.
    #
    # The alternative was splitting the constant into five module-level names.
    # Rejected: that changes working tax-adjacent code to suit its description,
    # which is the inversion this inventory exists not to perform.
    key_path: tuple = ()

    claim_type: str = STATUTORY

    # ---- provenance: see the class docstring on why these are re-declared ----
    source_url: str = ""
    provision: str = ""
    citation_checked_on: str = ""
    instrument: str = ""
    instrument_status: str = INSTRUMENT_UNKNOWN
    # What KIND of instrument — an Act, a notification, a judgment, a
    # constitutional provision, or none at all. See provenance.py; it
    # changes what re-checking the citation actually involves.
    instrument_kind: str = KIND_ACT
    basis: str = ""

    # Where the implementation DELIBERATELY differs from the instrument,
    # and why. Empty means it is intended to match exactly. See
    # provenance.py — a divergence does not block verification.
    known_divergence: str = ""
    threshold_origin: str = ""
    reviewed_by: str = ""
    reviewed_on: str = ""

    @property
    def REVIEW_MEANS(self) -> str:
        """
        What a reviewer of THIS claim would be asserting.

        A property rather than a constant because it genuinely differs by claim
        kind, and a message naming the wrong assertion sends a reviewer to the
        wrong task. Found when PE5 — which has no value — was reported as
        needing someone to "verify the value against the cited source".

        Same correction as Stage 2b's, one level finer: there it was rules
        versus claims, here it is claims that assert a figure versus claims that
        assert a provision does not reach this tool at all.
        """
        if self.claim_type == NON_APPLICABILITY:
            return ("confirmed the authority still holds and the provision still "
                    "does not apply")
        return "verified the value against the cited source"

    @property
    def asserts_a_value(self) -> bool:
        """Whether there is a figure for the drift check to compare."""
        return self.asserted_value is not NO_VALUE

    @property
    def where(self) -> str:
        # A claim about an ABSENCE has no symbol to name — it is about the
        # module as a whole, and saying "penalty_exposure." would read as a
        # truncation rather than as deliberate.
        if not self.symbol:
            return self.module
        path = "".join(f"[{k!r}]" for k in self.key_path)
        return f"{self.module}.{self.symbol}{path}"

    def live_value(self):
        """The value as the running code actually holds it, read fresh."""
        if not self.asserts_a_value:
            raise ValuelessClaimError(
                f"{self.id} asserts no value ({self.claim_type}), so there is "
                f"nothing in the code to read. A claim that a provision does "
                f"not apply is checked by reading the authority behind it, not "
                f"by comparing a number.")
        module = importlib.import_module(self.module)
        try:
            value = getattr(module, self.symbol)
        except AttributeError:
            raise SymbolMissingError(
                f"{self.id} describes {self.where}, which no longer exists. "
                f"The claim is describing code that has been deleted or "
                f"renamed. Update the claim to point at the current symbol, or "
                f"remove it if the number it described is gone.") from None
        for key in self.key_path:
            try:
                value = value[key]
            except (KeyError, IndexError, TypeError):
                raise KeyPathMissingError(
                    f"{self.id} describes {self.where}, but {key!r} is not in "
                    f"{self.module}.{self.symbol}. The constant is still there "
                    f"and the entry this claim describes is gone — for the PT "
                    f"table that means a state was dropped from coverage, "
                    f"which is a scope change a reviewer should see, not a "
                    f"stale number.") from None
        return value

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
        if not self.asserts_a_value:
            raise ValuelessClaimError(
                f"{self.id} asserts no value, so it cannot drift. Asking this "
                f"would return False — 'has not drifted' — for a claim nothing "
                f"has checked, which reads as a clean result nobody computed. "
                f"Use drift_is_not_applicable() to see which claims the drift "
                f"check cannot cover.")
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

# The citation state shared by every Stage B1 claim, written once because it is
# one fact about one file rather than four separate findings.
UNRESOLVED_PT = (
    'unresolved: payroll_breakdown.py records that "every slab" was "re-verified live on 2026-09-03 against a primary source", but names no source for this state. Under the standing rule (INVENTORY_EXPANSION_DESIGN.md 5.1) a re-findable trail AND a recorded check are both required; the check is recorded and the trail is not. NOT backdated: the Act was not looked up today and credited to the 2026-09-03 check.')

UNRESOLVED_PE = (
    'unresolved: penalty_exposure.py records that every rate was "independently verified against current sources" and names NONE of them. Note the wording against payroll_breakdown.py\'s, which says "re-verified live ... against a PRIMARY source" and names the document -- this file claims only "current sources", which does not assert a primary source and gives no trail to follow. Under the standing rule (INVENTORY_EXPANSION_DESIGN.md 5.1) that is evidence a check occurred, not something an independent party can redo. The instrument and provision below are recorded as the file itself states them. NOT backdated: nothing was looked up today and credited to the earlier check.')


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

    # -----------------------------------------------------------------------
    # STAGE A — optimizer.py (INVENTORY_EXPANSION_DESIGN.md §4). Two claims,
    # no new mechanism, and FIRST because OP1 is the claim this entire phase
    # was named after: the Code on Wages floor that sat wrong in this codebase
    # until a human happened to go looking.
    #
    # A FINDING THAT INVERTS WHAT §10.1 ASSUMED. Reading the three files in this
    # batch showed optimizer.py has the WEAKEST recorded provenance of the
    # three, not the strongest -- payroll_breakdown.py's PT tables record a
    # primary-source check against a named government PDF, while this file
    # records only "multiple independent sources", which are secondary. So OP1
    # leads on RISK, not on neglect: worst-evidenced AND the one with a history
    # of having actually been wrong.
    # -----------------------------------------------------------------------
    Claim(
        id="OP1", module="optimizer", symbol="BASIC_PCT_MIN",
        describes="Statutory floor on basic salary as a share of CTC: 50%. Every "
                  "structure this tool recommends is searched at or above it.",
        asserted_value=0.50,
        claim_type=STATUTORY,
        instrument="Code on Wages, 2019 (Act 29 of 2019)",
        instrument_status=IN_FORCE,
        # SAME NAMING DISCREPANCY R1 CARRIES, and recorded the same way rather
        # than silently corrected: optimizer.py's own text says "Code on Wages
        # 2025". The Act is the Code on Wages, 2019 (Act 29 of 2019);
        # 21 Nov 2025 is its commencement, not its year. Changing the comment is
        # a separate edit from describing it, and this file describes.
        provision="Code on Wages, 2019 (Act 29 of 2019), s. 2(y) -- definition of "
                  "\"wages\"; proviso on excluded allowances exceeding one-half of "
                  "all remuneration. In force 21 Nov 2025.",
        source_url="https://www.indiacode.nic.in/handle/123456789/15793",
        threshold_origin="STATUTORY -- the 50% is set by the Code on Wages, not "
                         "chosen here. optimizer.py's own docstring is explicit "
                         "that this floor is statute and the CEILING beside it is "
                         "not, which is why both are inventoried together.",
        citation_checked_on="unresolved: optimizer.py records 'Verified against "
                            "multiple independent sources on 2026-09-01' and names "
                            "NONE of them. Under the standing rule "
                            "(INVENTORY_EXPANSION_DESIGN.md §5.1) that is evidence a "
                            "check occurred, not a trail an independent party can "
                            "redo, so it does not qualify as verified. The provision "
                            "and source_url above are taken from R1's record of the "
                            "same proposition in compliance_rules.py -- optimizer.py "
                            "itself names no provision -- and R1's citation is ALSO "
                            "unresolved, so nothing here has been confirmed against a "
                            "primary source. NOT backdated: no source was hunted down "
                            "today and credited to the 2026-09-01 check.",
    ),
    Claim(
        id="OP2", module="optimizer", symbol="BASIC_PCT_MAX",
        describes="Ceiling on basic salary as a share of CTC: 60%. Bounds the "
                  "search space; not a legal limit.",
        asserted_value=0.60,
        claim_type=CONVENTION,
        basis="NOT LAW, and inventoried precisely to say so out loud. optimizer.py's "
              "docstring states the derivation in full: the ceiling was raised to "
              "60% to preserve the same 10-point search width the original 40-50% "
              "band had, repositioned above the new statutory floor, so the space "
              "does not collapse to a single point at exactly 0.50. It does real "
              "work -- an unconstrained tax-minimising search pushes basic upward "
              "indefinitely, because employer PF is not taxable to the employee and "
              "the Section 124 NPS deduction scales with basic, so more basic "
              "shelters more CTC. Unlike R2's Rs 6L and R4's 10%, this threshold's "
              "derivation IS recorded, in the file that defines it.",
        threshold_origin="NOT STATUTORY -- an engineering judgement, and the one "
                         "place in this batch where the codebase already said so "
                         "itself. HOW THIS IS KNOWN: optimizer.py's docstring "
                         "distinguishes the floor ('one of these is statute, not "
                         "assumption') from the ceiling and gives the ceiling's "
                         "reasoning explicitly. A reviewer may move it; moving it "
                         "changes this tool's search space, never its compliance "
                         "with anything external.",
    ),

    # -----------------------------------------------------------------------
    # STAGE B1 -- penalty_exposure.py's four rate claims
    # (INVENTORY_EXPANSION_DESIGN.md 4). Adds exactly ONE mechanism,
    # instrument_kind, because this is the first file whose citations are not
    # all Acts. The s. 448 non-applicability claim is deliberately NOT here:
    # it needs a value-less claim, which is a second mechanism, and the design
    # says one per stage. It lands in B2.
    #
    # WHY ALL FOUR ARE UNRESOLVED, from the file's own words rather than a
    # judgement about them: penalty_exposure.py says the rates were
    # "independently verified against current sources". payroll_breakdown.py,
    # by contrast, says "re-verified live ... against a PRIMARY source" and
    # names the document. The difference is not stylistic -- one asserts a
    # primary source and identifies it, the other asserts neither.
    # -----------------------------------------------------------------------
    Claim(
        id="PE1", module="penalty_exposure", symbol="EPF_7Q_MONTHLY_RATE",
        describes="Interest on delayed employer PF remittance: 1% per month "
                  "(12% p.a. simple). Mandatory, non-waivable, no discretion.",
        asserted_value=0.01,
        claim_type=STATUTORY,
        instrument="Employees' Provident Funds and Miscellaneous Provisions Act, 1952",
        instrument_kind=KIND_ACT,
        instrument_status=IN_FORCE,
        provision="s. 7Q -- simple interest on amounts due but not remitted.",
        source_url="https://www.epfindia.gov.in/site_en/index.php",
        threshold_origin="STATUTORY -- the 12% p.a. is fixed by the Act and the "
                         "file records it as carrying no discretion. Nothing here "
                         "is an engineering judgement.",
        citation_checked_on=UNRESOLVED_PE,
    ),
    Claim(
        id="PE2", module="penalty_exposure", symbol="EPF_14B_MONTHLY_RATE",
        describes="Damages on delayed employer PF remittance: a flat 1% of arrears "
                  "per month, replacing the pre-2024 tiered 5-25% structure.",
        asserted_value=0.01,
        claim_type=STATUTORY,
        # THE REASON instrument_kind EXISTS. This rate is not set by the Act --
        # it is set by a notification made under it, and re-checking a dated
        # Ministry notification is a different task from looking up a section.
        instrument="Ministry of Labour notification effective 15 June 2024, "
                   "amending Para 32A of the Employees' Provident Funds Scheme, 1952",
        instrument_kind=KIND_SUBORDINATE,
        instrument_status=IN_FORCE,
        provision="Para 32A (as amended 15 June 2024) -- damages at 1% of arrears "
                  "per month, operating within the s. 14B ceiling.",
        source_url="https://www.epfindia.gov.in/site_en/index.php",
        threshold_origin="STATUTORY, via subordinate legislation rather than the "
                         "Act itself: the 1%/month figure is set by the 15 June 2024 "
                         "notification. The file records the pre-2024 figure it "
                         "replaced (a tiered 5-25%), which is why this one is known "
                         "to have MOVED -- a rate that has changed once can change "
                         "again, and a notification changes more easily than an Act.",
        citation_checked_on=UNRESOLVED_PE,
    ),
    Claim(
        id="PE3", module="penalty_exposure", symbol="EPF_14B_CAP_FRACTION",
        describes="Ceiling on s. 14B damages: capped at 100% of the arrears amount.",
        asserted_value=1.0,
        claim_type=STATUTORY,
        instrument="Employees' Provident Funds and Miscellaneous Provisions Act, 1952",
        instrument_kind=KIND_ACT,
        instrument_status=IN_FORCE,
        provision="s. 14B -- statutory ceiling on damages, within which Para 32A's "
                  "1%/month formula operates.",
        source_url="https://www.epfindia.gov.in/site_en/index.php",
        threshold_origin="STATUTORY -- the 100% ceiling is in s. 14B itself. Recorded "
                         "as a claim even though the file notes it never binds in "
                         "practice at 1%/month (it would take ~100 months), because "
                         "a ceiling that is implemented but never exercised is "
                         "exactly the kind of figure that can go stale unnoticed.",
        citation_checked_on=UNRESOLVED_PE,
    ),
    Claim(
        id="PE4", module="penalty_exposure", symbol="TDS_201_1A_MONTHLY_RATE",
        describes="Interest on TDS deducted but not deposited: 1.5% per month. The "
                  "deducted-but-not-deposited case, not the failure-to-deduct case "
                  "(which is 1%/month and is not what this module models).",
        asserted_value=0.015,
        claim_type=STATUTORY,
        instrument="Income-tax Act, 2025 (Act 30 of 2025)",
        instrument_kind=KIND_ACT,
        instrument_status=IN_FORCE,
        provision="s. 398(3) (formerly s. 201(1A) of the Income-tax Act, 1961) -- "
                  "interest for failure to deposit tax already deducted.",
        source_url="https://www.incometaxindia.gov.in/pages/acts/income-tax-act.aspx",
        threshold_origin="STATUTORY -- both rates are set by the provision. WHICH of "
                         "the two applies is a scoping decision this module makes and "
                         "documents: it models the deposit-delay case, so 1.5% "
                         "applies rather than 1%. That selection is a judgement about "
                         "the tool's scenario, not about the figure.",
        citation_checked_on=UNRESOLVED_PE,
    ),

    # -----------------------------------------------------------------------
    # STAGE B2 -- the one claim in this codebase that asserts a provision does
    # NOT apply (INVENTORY_EXPANSION_DESIGN.md §2.3). Adds exactly one
    # mechanism: a claim with no value.
    #
    # It describes an ABSENCE -- penalty_exposure.py models no s. 448 penalty
    # anywhere -- and that is precisely why it belongs in an inventory. A
    # reasoned exclusion rots invisibly: if the judgment behind it is overruled,
    # or the tool's scope changes so the provision starts applying, nothing in
    # the codebase notices, and a missing penalty model is far harder to spot
    # than a wrong number.
    # -----------------------------------------------------------------------
    Claim(
        id="PE5", module="penalty_exposure", symbol="",
        describes="Section 448 (formerly s. 271C) penalty is deliberately NOT "
                  "modelled anywhere in this module. Not an omission -- a "
                  "provision checked and excluded as legally inapplicable.",
        asserted_value=NO_VALUE,
        claim_type=NON_APPLICABILITY,
        instrument="US Technologies International (P.) Ltd. v. CIT, "
                   "[2023] 149 taxmann.com 144 (SC), 10 April 2023",
        instrument_kind=KIND_JUDGMENT,
        instrument_status=IN_FORCE,
        provision="s. 448 (formerly s. 271C of the Income-tax Act, 1961) -- penalty "
                  "for failure to DEDUCT tax. Held to turn on the words \"fails to "
                  "deduct\", which do not reach failure to DEPOSIT tax already "
                  "deducted; belated remittance after deduction is covered "
                  "exclusively by s. 398(3) (formerly s. 201(1A)) interest.",
        source_url="https://www.incometaxindia.gov.in/pages/acts/income-tax-act.aspx",
        threshold_origin="NO NUMERIC THRESHOLD, and no value of any kind. This claim "
                         "asserts that a provision does not apply, so there is no "
                         "figure to source. HOW THIS IS KNOWN: by reading the claim "
                         "-- there is nothing here for a number to be wrong about.",
        # THE CONDITION THE EXCLUSION DEPENDS ON, recorded because it is the
        # thing most likely to quietly stop being true. s. 448 is inapplicable
        # BECAUSE every scenario this module models is the deducted-but-not-
        # deposited case. If penalty_exposure.py ever models FAILURE TO DEDUCT,
        # the provision applies and this claim becomes wrong -- not stale, wrong
        # -- without any law having changed. No automated check can catch that:
        # it would have to understand what a new scenario represents.
        citation_checked_on="unresolved: the CITATION here is the most specific in "
                            "penalty_exposure.py -- a full law-report citation, "
                            "[2023] 149 taxmann.com 144 (SC), which an independent "
                            "party can re-find. But the CHECK is recorded in the same "
                            "\"independently verified against current sources\" "
                            "language as PE1-PE4, which names no source and does not "
                            "assert a primary one. Under the standing rule "
                            "(INVENTORY_EXPANSION_DESIGN.md 5.1) a re-findable trail "
                            "and a recorded check are BOTH required; this has the "
                            "first and not the second. It is the closest claim in "
                            "this file to clearing the bar and a reviewer could "
                            "likely settle it quickly. NOT backdated. SEPARATELY "
                            "UNCHECKED, and not a citation question at all: whether "
                            "the judgment has since been overruled, distinguished, or "
                            "legislatively displaced by the 2025 Act's re-enactment.",
    ),

    # -----------------------------------------------------------------------
    # STAGE C1 -- payroll_breakdown.py's professional tax
    # (INVENTORY_EXPANSION_DESIGN.md 2.1). Adds exactly ONE mechanism: key
    # paths, because PT_MONTHLY_TABLE is one Python name holding five separate
    # STATE statutes. known_divergence is C2.
    #
    # THE FIRST VERIFIED CLAIMS IN THIS INVENTORY LAND HERE, and they arrive
    # from a direction nobody planned for: the previous design named the browser
    # lookup as the thing that would prove `verified` means something. Instead
    # this file already recorded a primary-source check and NAMED the documents
    # for two of the five states. Karnataka cites an amending Act by name and
    # year; Tamil Nadu names the government's own PDF and explicitly rejects an
    # aggregator's paraphrase that did not match. Those are trails an
    # independent party can follow, which is what 5.1 requires.
    #
    # The other three are unresolved for one reason: the file's blanket "every
    # slab re-verified against a primary source" records that a check happened
    # without naming what was read. Evidence of a check is not a trail.
    # -----------------------------------------------------------------------
    Claim(
        id="PT1", module="payroll_breakdown", symbol="PT_MONTHLY_TABLE",
        key_path=("karnataka",),
        describes="Karnataka professional tax: nil up to Rs 24,999/month gross, "
                  "Rs 200/month above Rs 25,000.",
        asserted_value=[(0, 24_999, 0), (25_000, None, 200)],
        claim_type=STATUTORY,
        instrument="Karnataka Tax on Professions, Trades, Callings and Employments "
                   "(Amendment) Act, 2025",
        instrument_kind=KIND_ACT,
        instrument_status=IN_FORCE,
        provision="Amendment raising the exemption threshold from Rs 15,000 to "
                  "Rs 25,000/month and the annual cap from Rs 2,400 to Rs 2,500, "
                  "in force 1 April 2025.",
        # VERIFIED. The instrument is named by Act, amendment and year, which is
        # a trail an independent party can follow, and payroll_breakdown.py
        # records a live primary-source check on this date. No URL was captured
        # and none is invented here -- 5.1 makes the named instrument the trail,
        # not a link.
        citation_checked_on="2026-09-03",
        threshold_origin="STATUTORY -- both figures are set by the amending Act. "
                         "This is also the clearest evidence in the codebase that "
                         "checking beats recalling: the file records that a first "
                         "draft proposed Rs 15,000, which the 2025 amendment had "
                         "already replaced, so a hardcoded threshold would have been "
                         "wrong from day one rather than eventually.",
    ),
    Claim(
        id="PT2", module="payroll_breakdown", symbol="PT_MONTHLY_TABLE",
        key_path=("maharashtra",),
        describes="Maharashtra professional tax, general slab: nil to Rs 7,500, "
                  "Rs 175/month to Rs 10,000, Rs 200/month above.",
        asserted_value=[(0, 7_500, 0), (7_501, 10_000, 175), (10_001, None, 200)],
        claim_type=STATUTORY,
        # The file refers to "Maharashtra's Act" without naming it. It is NOT
        # named here either: supplying the title from elsewhere today and
        # recording it against a 2026-09-03 check is precisely the backdating
        # 5.1 forbids.
        instrument="",
        instrument_kind=KIND_ACT,
        instrument_status=INSTRUMENT_UNKNOWN,
        provision="",
        known_divergence="THE ACT DIFFERENTIATES BY GENDER AND THIS TOOL DOES NOT. "
                         "Maharashtra exempts women up to Rs 25,000/month against "
                         "Rs 7,500 for the general slab recorded here. Nothing in "
                         "this product's intake collects gender, so the general slab "
                         "is applied to everyone. The direction matters and is "
                         "deliberate: it OVER-states professional tax for the "
                         "employees the exemption would cover, never under-states it, "
                         "so a treasury forecast built on it is conservative rather "
                         "than short. WHAT A REVIEWER IS ACCEPTING is not that the "
                         "table matches the Act -- it does, for the general slab -- "
                         "but that applying the general slab to every employee is an "
                         "acceptable simplification for this tool's purpose. That is "
                         "a judgement about the product, not about the law.",
        threshold_origin="STATUTORY -- set by Maharashtra's professional tax Act, "
                         "which payroll_breakdown.py refers to without naming. "
                         "SEPARATELY, AND FOR C2: the file records that the Act "
                         "differentiates by gender (women exempt to Rs 25,000/month "
                         "against Rs 7,500 for this general slab) and that the tool "
                         "does not model it, because nothing in the intake collects "
                         "gender. This table is the general slab -- a deliberate, "
                         "conservative, higher-PT approximation.",
        citation_checked_on=UNRESOLVED_PT,
    ),
    Claim(
        id="PT3", module="payroll_breakdown", symbol="PT_MONTHLY_TABLE",
        key_path=("telangana",),
        describes="Telangana professional tax: nil to Rs 15,000, Rs 150/month to "
                  "Rs 20,000, Rs 200/month above.",
        asserted_value=[(0, 15_000, 0), (15_001, 20_000, 150), (20_001, None, 200)],
        claim_type=STATUTORY,
        instrument="",
        instrument_kind=KIND_ACT,
        instrument_status=INSTRUMENT_UNKNOWN,
        provision="",
        threshold_origin="STATUTORY -- set by Telangana's professional tax Act, "
                         "which payroll_breakdown.py does not name. The file records "
                         "that Telangana matched the figures a first draft proposed "
                         "exactly, and was confirmed rather than assumed correct just "
                         "because two other states had not matched.",
        citation_checked_on=UNRESOLVED_PT,
    ),
    Claim(
        id="PT4", module="payroll_breakdown", symbol="PT_MONTHLY_TABLE",
        key_path=("tamil_nadu",),
        describes="Tamil Nadu / Greater Chennai Corporation professional tax, "
                  "expressed as a monthly equivalent of a six-tier HALF-YEARLY "
                  "assessment (Rs 0/100/235/510/760/1,095 divided by six).",
        asserted_value=[(0, 3_500, 0), (3_500.01, 5_000, 16.67),
                        (5_000.01, 7_500, 39.17), (7_500.01, 10_000, 85.0),
                        (10_000.01, 12_500, 126.67), (12_500.01, None, 182.5)],
        claim_type=STATUTORY,
        instrument="Greater Chennai Corporation professional tax schedule, published "
                   "by the Government of Tamil Nadu on tnswp.com",
        instrument_kind=KIND_SUBORDINATE,
        instrument_status=IN_FORCE,
        provision="Six-tier half-yearly slab: Rs 0 / 100 / 235 / 510 / 760 / 1,095 "
                  "across average-half-yearly-income bands.",
        source_url="https://www.tnswp.com/",
        # VERIFIED, and the strongest-evidenced claim in this codebase. The file
        # records that this was read against the GOVERNMENT'S OWN PDF and that an
        # aggregator's paraphrase of the same table was checked and DID NOT
        # MATCH -- a named document plus a recorded reason for distrusting the
        # secondary copy.
        citation_checked_on="2026-09-03",
        known_divergence="A HALF-YEARLY ASSESSMENT EXPRESSED AS A MONTHLY ONE. The "
                         "published schedule assesses six bands of average HALF-YEARLY "
                         "income; both the thresholds and the amounts are divided by "
                         "six here so that one monthly lookup works for every state. "
                         "Real payroll practice does not literally assess this monthly, "
                         "and the file flags it as an approximation at the call site. "
                         "It diverges most for an employee whose income varies across "
                         "the half-year, since a monthly-equivalent lookup cannot see "
                         "an average the real assessment is computed on. WHAT A "
                         "REVIEWER IS ACCEPTING: that a monthly equivalent is close "
                         "enough for a forecasting tool, and that the rounding to two "
                         "decimals on each divided figure does not accumulate into a "
                         "material annual difference.",
        threshold_origin="STATUTORY -- the six half-yearly figures are set by the "
                         "published schedule. The DIVISION BY SIX is not: it is this "
                         "tool's own conversion so one monthly lookup works for every "
                         "state, and the file flags it as an approximation at the call "
                         "site. That conversion is a deliberate divergence from how "
                         "the assessment actually works and is C2's subject.",
    ),
    Claim(
        id="PT5", module="payroll_breakdown", symbol="PT_MONTHLY_TABLE",
        key_path=("delhi",),
        describes="Delhi professional tax: Rs 0 at every income level. A real, "
                  "checked zero -- no PT Act has ever been enacted for the NCT of "
                  "Delhi -- not an omitted case.",
        asserted_value=[(0, None, 0)],
        claim_type=STATUTORY,
        instrument="Constitution of India, Article 276",
        instrument_kind=KIND_CONSTITUTION,
        instrument_status=IN_FORCE,
        provision="Art. 276 PERMITS a State to levy a tax on professions, trades, "
                  "callings and employments but does not require one. No such Act "
                  "has been enacted for the NCT of Delhi, so nothing is levied.",
        threshold_origin="STATUTORY in the sense that matters: the figure is zero "
                         "because no statute imposes anything. THE OPERATIVE FACT IS "
                         "AN ABSENCE -- no Delhi PT Act -- and an absence cannot be "
                         "cited, so Article 276 is recorded as the nearest citable "
                         "authority, being what makes the absence lawful rather than "
                         "an oversight. Recorded this way rather than as an empty "
                         "instrument, because an empty instrument would be "
                         "indistinguishable from nobody having looked.",
        citation_checked_on="unresolved: verifying a NEGATIVE is a different and "
                            "harder task than checking a slab, and payroll_breakdown.py "
                            "names no source for it. Confirming that no Delhi PT Act "
                            "exists means establishing the absence of an instrument "
                            "across the whole corpus, which no single document shows. "
                            "Article 276's permissive wording is citable and does not "
                            "by itself establish that Delhi never legislated. NOT "
                            "backdated.",
    ),
    Claim(
        id="PT6", module="payroll_breakdown", symbol="_FEBRUARY_BUMP_AMOUNT",
        describes="The one-off Rs 300 February professional tax month used by "
                  "Karnataka and Maharashtra so that 11 months at the base rate "
                  "plus one bumped month lands exactly on the Rs 2,500 annual cap.",
        asserted_value=300.0,
        claim_type=STATUTORY,
        instrument="Constitution of India, Article 276",
        instrument_kind=KIND_CONSTITUTION,
        instrument_status=IN_FORCE,
        provision="Art. 276(2) -- Rs 2,500 per person per year ceiling on the total "
                  "professional tax a State may levy.",
        threshold_origin="THE Rs 2,500 CEILING IS CONSTITUTIONAL. The Rs 300 figure "
                         "is NOT: it is arithmetic this tool performs to land on that "
                         "ceiling (11 x Rs 200 + Rs 300 = Rs 2,500), and whether the "
                         "states actually collect it as a February bump rather than "
                         "some other schedule is a mechanism the file asserts and "
                         "this claim does not confirm.",
        citation_checked_on="unresolved: Article 276 is a citable instrument and the "
                            "Rs 2,500 ceiling is attributed to it in the file, but no "
                            "source is named and the file records no check of the "
                            "constitutional provision itself -- only that the "
                            "arithmetic lands on Rs 2,500. Two separate things are "
                            "unverified here: the ceiling, and that a February bump "
                            "is how these states in fact apply it. NOT backdated.",
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
        # Value-less claims are skipped HERE, once and explicitly, rather than
        # by each call site remembering to — and drift_is_not_applicable()
        # below exists so the skip is visible rather than silent.
        if not claim.asserts_a_value:
            continue
        if claim.value_has_drifted:
            problems.append(
                f"{claim.id}: {claim.where} is now {claim.live_value()!r} but "
                f"the claim records {claim.asserted_value!r} as the verified "
                f"value. The number changed and its citation was not "
                f"re-verified. Re-check the source, then update BOTH "
                f"asserted_value and citation_checked_on — updating the value "
                f"alone reinstates exactly the state this check exists to find.")
    return problems


def drift_is_not_applicable() -> tuple:
    """
    Claims the drift check structurally cannot cover, named rather than
    silently skipped.

    drift_findings() returning [] means "nothing drifted", and without this it
    would quietly also mean "some claims were never eligible to". Those are
    different facts, and a reader entitled to the first should not be handed
    the second without being told.
    """
    return tuple(c for c in CLAIMS if not c.asserts_a_value)
