"""
pipeline.py — the optimize→explain→compliance→negotiate→metrics sequence,
declared rather than implied (ORCHESTRATION_DESIGN.md, Roadmap Phase 2.1).

WHAT THIS IS NOT. It is not a move of previously-client-side work to the
server: that sequence already ran server-side, in one function, in this order.
It is not new behaviour either — every stage below does exactly what the
corresponding block of `_build_optimize_response()` did, and the characterization
baseline in tests/fixtures/pipeline_baseline.json is what proves that rather
than a claim in this docstring.

WHAT IT IS FOR. Three things arrive immediately after this in the roadmap —
expanded compliance rules (2.2), adversarial verification (2.3), a
legal-change-monitoring agent (2.4) — and each needs somewhere to attach.
Without a declared sequence, each one grows another branch inside a function
that was already 98 lines. The alternative was not "no refactor"; it was the
same refactor later, entangled with new logic instead of done on its own.

CONTROL FLOW IS DETERMINISTIC HERE, DELIBERATELY. Python decides what runs
next, from values the deterministic engines already produced. LLMs stay exactly
where they were — phrasing explanations, parsing text — behind the guards that
already contain them (ai_layer.py's numeric guard: no LLM may compute, restate
with different rounding, or invent a tax figure). "Stages" here means separable
and individually testable, NOT stages that choose their own path. When 2.3
gives a second opinion influence over escalation, ORCHESTRATION_DESIGN.md §3.2
records the principle it has to satisfy: control flow needs a guard as serious
as the numeric one, because a wrong number reaching a human is visible and
correctable while a compliance check silently skipped is an absence.

THE ORDER IS LOAD-BEARING, NOT INCIDENTAL. `current_structure_stage` must
precede `compliance_stage`: compliance checks the AS-OFFERED structure, and
falls back to the optimizer's recommendation only when nothing was extracted.
Checking the recommendation instead would be nearly circular — the optimizer
enforces a 50-60% basic band by construction, so R1 (basic < 50% of CTC) could
structurally never fire against its own output, and compliance would silently
report zero risk on every input. Until this module existed that constraint was
enforced only by statement order and a comment.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from optimizer import (optimize, best_regime_for_given_structure,
                       optimization_value_pct)
from ai_layer import (explain_result, flag_compliance, negotiate,
                      compliance_pct, ai_coverage_pct)


@dataclass
class PipelineContext:
    """
    Everything a stage may read or write. Passing one context rather than
    threading arguments between stages is what lets a stage be added without
    changing the signature of the ones around it — which is the whole point of
    doing this before 2.2/2.3/2.4 rather than during them.
    """
    # Inputs
    ctc: float
    rent_paid: float
    city: str
    nps_opted: bool
    current_extracted: dict | None
    extraction_ai_backed: bool
    skip_ai: bool = False

    # Injected by the caller so this module does not import app.py (which
    # imports this one). app._build_current_structure() stays where it is.
    build_current_structure: callable = None

    # Accumulated by the stages
    result: dict | None = None
    current_structure: object | None = None
    explanation: dict | None = None
    compliance: dict | None = None
    response: dict = field(default_factory=dict)

    # Bookkeeping. Exposed in the API response as `stages_run`
    # (ORCHESTRATION_DESIGN.md §3.4/§6): a test-only record that a stage ran is
    # confirmable only from inside the test suite, and "the compliance check
    # executed" is exactly the kind of fact an audit trail should be able to
    # state. Same reasoning as orchestration.py's `checked` field, which
    # records what was evaluated including what did not fire.
    stages_run: list = field(default_factory=list)


def optimize_stage(ctx: PipelineContext) -> None:
    ctx.result = optimize(ctc=ctx.ctc, rent_paid=ctx.rent_paid,
                          city=ctx.city, nps_opted=ctx.nps_opted)
    ctx.response.update({
        "ctc": ctx.result["ctc"],
        "old_regime_best": _optresult_to_dict(ctx.result["old_regime_best"]),
        "new_regime_best": _optresult_to_dict(ctx.result["new_regime_best"]),
        "recommended_regime": ctx.result["recommended"].regime,
        "annual_saving": ctx.result["annual_tax_saving_vs_other_regime"],
    })


def current_structure_stage(ctx: PipelineContext) -> None:
    """
    Builds the as-offered structure, if extraction supplied one. MUST run
    before compliance_stage — see this module's docstring for why checking the
    recommendation instead would make compliance structurally unable to fire.
    """
    if isinstance(ctx.current_extracted, dict):
        ctx.current_structure = ctx.build_current_structure(
            ctx.current_extracted, ctx.ctc, ctx.result["recommended"].regime)


def explain_stage(ctx: PipelineContext) -> None:
    ctx.explanation = explain_result(ctx.result, ctx.rent_paid, ctx.city,
                                     skip_ai=ctx.skip_ai)
    ctx.response["explanation"] = ctx.explanation


def compliance_stage(ctx: PipelineContext) -> None:
    """
    Checks the AS-OFFERED structure when there is one — the real risk surface —
    and only falls back to the recommendation when nothing was extracted, so
    there is still something to check.
    """
    structure_to_check = (ctx.current_structure if ctx.current_structure is not None
                          else ctx.result["recommended"].structure)
    ctx.compliance = flag_compliance(structure_to_check, ctx.rent_paid, skip_ai=ctx.skip_ai)
    ctx.response["compliance"] = ctx.compliance
    ctx.response["compliance_checked_against"] = (
        "as_offered" if ctx.current_structure is not None else "recommended")


def negotiate_stage(ctx: PipelineContext) -> None:
    """
    Only when the caller supplied a real extracted current structure (from
    /api/extract, after the user reviewed and corrected it). A
    manually-entered CTC-only input has no offered structure to negotiate away
    from, so one is not fabricated.
    """
    if ctx.current_structure is None:
        return
    current_best = best_regime_for_given_structure(
        ctx.current_structure, ctx.rent_paid, ctx.city)
    ctx.response["negotiation"] = negotiate(
        current_structure=ctx.current_structure,
        current_best=current_best,
        recommended=ctx.result["recommended"].structure,
        recommended_regime=ctx.result["recommended"].regime,
        recommended_tax=ctx.result["recommended"].tax_breakdown,
        ctc=ctx.ctc,
        skip_ai=ctx.skip_ai,
    )


def metrics_stage(ctx: PipelineContext) -> None:
    """Radar/ring metrics — reuses data already computed above, no new work."""
    extraction_ran = ctx.current_structure is not None
    negotiation_ran = ctx.current_structure is not None
    negotiation_ai_backed = (ctx.response["negotiation"]["ai_backed"]
                             if negotiation_ran else False)
    ctx.response["metrics"] = {
        "optimization_value_pct": optimization_value_pct(
            ctx.ctc, ctx.rent_paid, ctx.city, ctx.nps_opted),
        "compliance_pct": compliance_pct(ctx.compliance["flags"]),
        "ai_coverage_pct": ai_coverage_pct(
            extraction_ran=extraction_ran,
            extraction_ai_backed=ctx.extraction_ai_backed,
            explanation_ai_backed=ctx.explanation["ai_backed"],
            compliance_ai_backed=ctx.compliance["ai_backed"],
            negotiation_ran=negotiation_ran,
            negotiation_ai_backed=negotiation_ai_backed,
            compliance_ran=len(ctx.compliance["flags"]) > 0,
        ),
    }


# The declared sequence. Order is part of the contract, not an artefact of how
# the file happens to be written — see this module's docstring on why
# current_structure_stage precedes compliance_stage.
STAGES = (
    ("optimize", optimize_stage),
    ("current_structure", current_structure_stage),
    ("explain", explain_stage),
    ("compliance", compliance_stage),
    ("negotiate", negotiate_stage),
    ("metrics", metrics_stage),
)


def run(ctx: PipelineContext) -> PipelineContext:
    """
    Runs every stage in declared order, recording that each ran.

    Every stage is recorded, including negotiate when it returns early with
    nothing to do. "Ran and had no work" and "never ran" are different facts,
    and collapsing them would defeat the reason stages_run exists: a stage that
    silently stopped being invoked would look identical to one that correctly
    declined. `compliance_checked_against` and the presence of `negotiation`
    already say what each stage decided; this says what was asked.
    """
    for name, stage in STAGES:
        stage(ctx)
        ctx.stages_run.append(name)
    ctx.response["stages_run"] = list(ctx.stages_run)
    return ctx


def _optresult_to_dict(r):
    return {
        "regime": r.regime,
        "structure": _structure_to_dict(r.structure),
        "taxable_income": r.taxable_income,
        "tax_breakdown": r.tax_breakdown,
        "basic_pct": r.basic_pct,
    }


def _structure_to_dict(s):
    return {
        "ctc": s.ctc, "basic": s.basic, "hra": s.hra, "lta": s.lta,
        "special_allowance": s.special_allowance,
        "employer_pf": s.employer_pf, "employer_nps": s.employer_nps,
        "nps_opted": s.nps_opted,
    }
