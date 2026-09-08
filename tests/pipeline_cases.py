"""
The input spread the characterization baseline is captured over
(ORCHESTRATION_DESIGN.md §3.3).

Deliberately NOT happy-path. A characterization suite built from typical inputs
misses exactly the boundary conditions most likely to shift silently during a
restructure — which is the entire failure this baseline exists to catch. Every
case below is here because it exercises a specific branch that a careless
restructure could drop without any existing test noticing.

Shared by the capture script and the comparison test so the two can never
disagree about what is being pinned.
"""

# Each case: (name, kwargs for _build_optimize_response).
#
# skip_ai=True throughout, and that is not a shortcut. The LLM paths are
# nondeterministic by nature, so pinning them would produce a baseline that
# fails for reasons unrelated to any refactor. What the guards actually promise
# is that the DETERMINISTIC output is identical either way: an ungrounded
# number in an explanation is rejected and the deterministic template is used
# instead, and compliance flags are matched in Python before the LLM sees
# anything. So the deterministic path is the one whose exactness is meaningful.
CASES = [
    (
        # R1 — Basic below the Code on Wages 50% statutory floor. This is the
        # gap this project already found once by luck rather than process, so
        # it is the first thing pinned.
        "code_on_wages_floor_breach",
        dict(
            ctc=2_000_000, rent_paid=300_000, city="metro", nps_opted=False,
            current_extracted={
                "basic": 900_000,          # 45% of CTC — under the 50% floor
                "hra": 400_000, "lta": 0, "employer_pf": 108_000,
            },
            extraction_ai_backed=False,
        ),
    ),
    (
        # The same rule at its exact boundary. A restructure that changed a
        # comparison from <= to < would leave the case above still firing and
        # only this one would move.
        "code_on_wages_floor_exactly_at_50pct",
        dict(
            ctc=2_000_000, rent_paid=300_000, city="metro", nps_opted=False,
            current_extracted={
                "basic": 1_000_000,        # exactly 50% of CTC
                "hra": 400_000, "lta": 0, "employer_pf": 120_000,
            },
            extraction_ai_backed=False,
        ),
    ),
    (
        # R5 — employer contributions over the Rs 7,50,000 aggregate EPFO
        # ceiling. High severity, and the guardrail path reads it too.
        "epfo_aggregate_ceiling_breach",
        dict(
            ctc=4_000_000, rent_paid=500_000, city="metro", nps_opted=False,
            current_extracted={
                "basic": 1_800_000, "hra": 900_000, "lta": 100_000,
                "employer_pf": 900_000,    # over the ceiling on its own
            },
            extraction_ai_backed=False,
        ),
    ),
    (
        # Zero flags. "Nothing fired" is an outcome that has to be pinned too —
        # a restructure that stopped running compliance entirely would produce
        # exactly this shape for every input, and without a clean case pinned
        # there would be nothing to contrast it against.
        "clean_pass_no_flags",
        dict(
            ctc=1_800_000, rent_paid=0, city="metro", nps_opted=False,
            current_extracted={
                "basic": 1_080_000,        # 60% — inside the statutory band
                "hra": 0, "lta": 0, "employer_pf": 129_600,
            },
            extraction_ai_backed=False,
        ),
    ),
    (
        # No extraction at all. Exercises the §1 ordering decision directly:
        # with no as-offered structure, compliance falls back to checking the
        # RECOMMENDATION, and compliance_checked_against flips. Negotiation is
        # deliberately skipped here — there is no offered structure to
        # negotiate away from.
        "no_extraction_falls_back_to_recommended",
        dict(
            ctc=1_800_000, rent_paid=400_000, city="metro", nps_opted=False,
            current_extracted=None,
            extraction_ai_backed=False,
        ),
    ),
    (
        # Extraction present but internally inconsistent — components that do
        # not reconcile against the stated CTC. Exercises the mismatch path
        # through _build_current_structure().
        "extraction_mismatch_components_exceed_ctc",
        dict(
            ctc=1_200_000, rent_paid=200_000, city="metro", nps_opted=False,
            current_extracted={
                "basic": 900_000, "hra": 600_000, "lta": 100_000,
                "employer_pf": 108_000,    # sums past the stated CTC
            },
            extraction_ai_backed=True,     # also pins the ai_backed metric path
        ),
    ),
    (
        # The naive-baseline case: an already-optimal structure, where
        # total_saving <= 0 and negotiate() zeroes changed_levers. A
        # restructure that reordered negotiate relative to the regime
        # comparison would change this and nothing else.
        "already_optimal_zero_saving",
        dict(
            ctc=900_000, rent_paid=0, city="non_metro", nps_opted=False,
            current_extracted={
                "basic": 540_000, "hra": 0, "lta": 0, "employer_pf": 64_800,
            },
            extraction_ai_backed=False,
        ),
    ),
    (
        # NPS opted-in, non-metro. Exercises the employer-NPS cap path and the
        # non-metro HRA rate, neither of which the cases above touch.
        "nps_opted_non_metro",
        dict(
            ctc=2_400_000, rent_paid=240_000, city="non_metro", nps_opted=True,
            current_extracted={
                "basic": 1_200_000, "hra": 480_000, "lta": 0,
                "employer_pf": 144_000,
            },
            extraction_ai_backed=False,
        ),
    ),
]
