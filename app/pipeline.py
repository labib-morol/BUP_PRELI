"""Orchestration: notes -> LLM -> guardrails -> LP -> replay verification.

Kept separate from the HTTP layer so the whole pipeline can be exercised without
a server, and so the transport layer stays a thin contract implementation.
"""
from __future__ import annotations

import logging

from .directives import Directive
from .directives import NO_OP
from .guardrails import Assessment, assess, explain, factor_candidate, window_candidate, wrap_candidate
from .llm import gather_readings
from .optimizer import Solution, solve, static_plan, to_plan, totals
from .schemas import DirectiveInterpretation, HourlyPlanEntry, OptimizeRequest, OptimizeResponse
from .verifier import verify

log = logging.getLogger("gridwise.pipeline")


def _candidate_sets(applied: list[Directive]) -> list[list[Directive]]:
    """Directive sets to try, most faithful first. Never raises, always ends at [].

    Used when the faithful model turns out to be infeasible or fails replay: the
    least we can do is return a plan that satisfies the base energy rules.
    """
    sets = [applied]
    for index in range(len(applied)):
        sets.append([d for i, d in enumerate(applied) if i != index])
    sets.append([])
    return sets


def _best_effort(request: OptimizeRequest, applied: list[Directive]) -> tuple[list[dict], list[str], int]:
    last: tuple[list[dict], list[str]] | None = None
    for tier, directives in enumerate(_candidate_sets(applied)):
        solution: Solution | None = solve(request, directives, tier=tier)
        if solution is None:
            continue
        plan = to_plan(solution, request)
        errors = verify(request, plan, directives)
        if not errors:
            if tier:
                log.warning("tier %d plan accepted after relaxing directives", tier)
            return plan, directives, tier
        last = (plan, errors)
    if last is not None:
        log.error("no directive set passed replay; returning best effort (%s)", last[1][:3])
        return last[0], applied, -1

    static = to_plan(static_plan(request), request)
    log.error("LP infeasible even without directives; returning static plan")
    return static, [], -2


async def run(request: OptimizeRequest) -> tuple[OptimizeResponse, dict]:
    notes = request.operator_notes
    battery = request.battery

    readings = await gather_readings(
        notes, battery.capacity_kwh, battery.initial_energy_kwh, battery.minimum_energy_kwh
    )
    degraded = not any(readings)

    assessments: list[Assessment] = []
    for index, note in enumerate(notes):
        parsed = [_parse(raw, battery.capacity_kwh) for raw in readings[index]]
        primary = parsed[0] if parsed else NO_OP
        for candidate in (window_candidate(note, primary),
                          factor_candidate(note, primary),
                          wrap_candidate(note, primary)):
            if candidate is not None:
                parsed.append(candidate)
        assessments.append(assess(index, note, parsed, battery.capacity_kwh))

    applied: list[Directive] = []
    for assessment in assessments:
        applied.extend(assessment.applied)

    plan, used, tier = _best_effort(request, applied)
    total_grid, total_cost, peak = totals(plan, request)

    interpretation = [
        DirectiveInterpretation(
            note_index=assessment.index,
            applies=assessment.reported.applies,
            directive_type=assessment.reported.directive_type,
            structured_adjustment=assessment.reported.adjustment(),
            explanation=explain(assessment),
        )
        for assessment in assessments
    ]

    response = OptimizeResponse(
        scenario_id=request.scenario_id,
        directive_interpretation=interpretation,
        hourly_plan=[HourlyPlanEntry(**row) for row in plan],
        total_grid_kwh=total_grid,
        total_cost_bdt=total_cost,
        peak_grid_kwh=peak,
        plan_summary=_summary(assessments, used, degraded),
    )
    diagnostics = {
        "tier": tier,
        "degraded": degraded,
        "applied": [d.directive_type for d in used],
        "flags": {a.index: a.flags for a in assessments if a.flags},
    }
    return response, diagnostics


def _parse(raw: dict, capacity: float) -> Directive:
    from .guardrails import parse_directive

    return parse_directive(raw, capacity)


def _summary(assessments: list[Assessment], used: list[Directive], degraded: bool) -> str:
    parts: list[str] = []
    active = [a for a in assessments if a.reported.applies]
    ignored = len(assessments) - len(active)
    if active:
        described = ", ".join(
            f"{a.reported.directive_type} over hours {list(a.reported.hours)}" for a in active
        )
        parts.append(f"Applied {len(active)} operator directive(s): {described}.")
    else:
        parts.append("No operator note changed today's schedule.")
    if ignored:
        parts.append(f"Ignored {ignored} note(s) that do not affect the 24-hour plan.")
    if used:
        parts.append(
            "The battery charges in low-tariff hours and discharges into the "
            "highest-tariff hours it can serve, returning to its initial energy at hour 23."
        )
    else:
        parts.append(
            "Directive constraints were relaxed to keep the plan feasible; the battery "
            "follows base energy rules and ends the day at its initial energy."
        )
    if degraded:
        parts.append(
            "Warning: no language-model provider was reachable, so notes could not be "
            "interpreted and were treated as no-ops."
        )
    return " ".join(parts)
