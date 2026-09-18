"""Directive model shared by the guardrail, optimizer and verifier layers.

A Directive is the normalized, machine-checkable form of one operator note.
Every supported directive has a "safe direction" in which tightening the
constraint can never invalidate a plan against organizer ground truth:

    solar_reduction        -> lower factor
    minimum_battery_reserve-> higher reserve
    no_charge_window       -> superset of hours
    no_discharge_window    -> superset of hours
    max_grid_window        -> lower cap

That property is what makes uncertainty hedging safe (see guardrails.hedge).
"""
from __future__ import annotations

from dataclasses import dataclass

DIRECTIVE_TYPES = (
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
)
WINDOW_TYPES = ("no_charge_window", "no_discharge_window")


@dataclass(frozen=True)
class Directive:
    directive_type: str
    hours: tuple[int, ...] = ()
    factor: float | None = None
    minimum_energy_kwh: float | None = None
    max_grid_kwh: float | None = None

    @property
    def applies(self) -> bool:
        return self.directive_type != "no_op"

    def adjustment(self) -> dict | None:
        """The exact structured_adjustment shape required by the Problem Statement."""
        if self.directive_type == "solar_reduction":
            return {"hours": list(self.hours), "factor": self.factor}
        if self.directive_type == "minimum_battery_reserve":
            return {"hours": list(self.hours), "minimum_energy_kwh": self.minimum_energy_kwh}
        if self.directive_type in WINDOW_TYPES:
            return {"hours": list(self.hours)}
        if self.directive_type == "max_grid_window":
            return {"hours": list(self.hours), "max_grid_kwh": self.max_grid_kwh}
        return None


NO_OP = Directive("no_op")


def union(a: Directive, b: Directive) -> tuple[Directive, ...]:
    """Combine two candidate readings of the same note into applied constraints.

    Same-type candidates merge in the safe direction (more restrictive).
    Different-type candidates are both kept: any plan satisfying both also
    satisfies whichever one the organizer treats as ground truth.
    """
    if a.directive_type == "no_op":
        return (b,)
    if b.directive_type == "no_op":
        return (a,)
    if a.directive_type != b.directive_type:
        return (a, b)

    hours = tuple(sorted(set(a.hours) | set(b.hours)))
    if a.directive_type == "solar_reduction":
        return (Directive("solar_reduction", hours, factor=min(a.factor or 1.0, b.factor or 1.0)),)
    if a.directive_type == "minimum_battery_reserve":
        return (
            Directive(
                "minimum_battery_reserve",
                hours,
                minimum_energy_kwh=max(a.minimum_energy_kwh or 0.0, b.minimum_energy_kwh or 0.0),
            ),
        )
    if a.directive_type in WINDOW_TYPES:
        return (Directive(a.directive_type, hours),)
    return (Directive("max_grid_window", hours, max_grid_kwh=min(a.max_grid_kwh, b.max_grid_kwh)),)


def union_all(directives: list[Directive]) -> tuple[Directive, ...]:
    acc: tuple[Directive, ...] = ()
    for d in directives:
        if not acc:
            acc = (d,)
            continue
        merged: list[Directive] = []
        for existing in acc:
            merged.extend(union(existing, d))
        acc = tuple(merged)
    return acc


@dataclass
class Effects:
    """How a set of directives changes the optimization model."""

    effective_solar: list[float]
    reserve: list[float]
    no_charge: set[int]
    no_discharge: set[int]
    grid_cap: dict[int, float]


def compute_effects(
    base_solar: list[float], base_minimum: float, directives: list[Directive]
) -> Effects:
    solar = list(base_solar)
    reserve = [base_minimum] * 24
    no_charge: set[int] = set()
    no_discharge: set[int] = set()
    grid_cap: dict[int, float] = {}

    for d in directives:
        if not d.applies:
            continue
        if d.directive_type == "solar_reduction":
            for h in d.hours:
                solar[h] *= d.factor
        elif d.directive_type == "minimum_battery_reserve":
            for h in d.hours:
                reserve[h] = max(reserve[h], d.minimum_energy_kwh)
        elif d.directive_type == "no_charge_window":
            no_charge.update(d.hours)
        elif d.directive_type == "no_discharge_window":
            no_discharge.update(d.hours)
        elif d.directive_type == "max_grid_window":
            for h in d.hours:
                grid_cap[h] = min(grid_cap.get(h, float("inf")), d.max_grid_kwh)
    return Effects(solar, reserve, no_charge, no_discharge, grid_cap)
