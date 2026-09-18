"""Independent replay of a returned plan against the Problem Statement rules.

This is the guardrail the specification calls "Final replay": the completed
schedule is re-run hour by hour against the effective solar and every extracted
directive before the response is allowed out.
"""
from __future__ import annotations

import math

from .directives import Directive, compute_effects
from .schemas import OptimizeRequest

DEFAULT_TOL = 1e-3


def verify(
    request: OptimizeRequest,
    plan: list[dict],
    directives: list[Directive],
    tol: float = DEFAULT_TOL,
) -> list[str]:
    errors: list[str] = []
    bat = request.battery
    hours = request.hour

    if len(plan) != 24 or sorted(row["hour"] for row in plan) != list(range(24)):
        return ["hourly_plan must contain exactly hours 0..23 once each"]

    rows = sorted(plan, key=lambda row: row["hour"])
    effects = compute_effects(request.solar_profile, bat.minimum_energy_kwh, directives)

    energy = bat.initial_energy_kwh
    for row in rows:
        h = row["hour"]
        grid, solar_used = row["grid_kwh"], row["solar_used_kwh"]
        action, magnitude = row["battery_action"], row["battery_kwh"]

        for name, value in (("grid_kwh", grid), ("solar_used_kwh", solar_used),
                            ("battery_kwh", magnitude), ("battery_energy_after_kwh",
                                                         row["battery_energy_after_kwh"])):
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                errors.append(f"h{h}: {name} is not a finite number")
            elif value < -tol:
                errors.append(f"h{h}: {name} is negative ({value})")

        if action not in ("charge", "discharge", "idle"):
            errors.append(f"h{h}: battery_action must be charge, discharge or idle")
            continue
        if action == "idle" and abs(magnitude) > tol:
            errors.append(f"h{h}: idle hour reports battery_kwh={magnitude}")

        charge = magnitude if action == "charge" else 0.0
        discharge = magnitude if action == "discharge" else 0.0
        if charge > bat.max_charge_kwh_per_hour + tol:
            errors.append(f"h{h}: charge {charge} exceeds max_charge_kwh_per_hour")
        if discharge > bat.max_discharge_kwh_per_hour + tol:
            errors.append(f"h{h}: discharge {discharge} exceeds max_discharge_kwh_per_hour")
        if h in effects.no_charge and charge > tol:
            errors.append(f"h{h}: charge inside a no_charge_window")
        if h in effects.no_discharge and discharge > tol:
            errors.append(f"h{h}: discharge inside a no_discharge_window")

        balance = grid + solar_used + discharge - (request.hour(h).demand_kwh + charge)
        if abs(balance) > tol:
            errors.append(f"h{h}: energy balance off by {balance}")
        if solar_used > effects.effective_solar[h] + tol:
            errors.append(
                f"h{h}: solar_used {solar_used} exceeds effective solar "
                f"{effects.effective_solar[h]}"
            )
        if h in effects.grid_cap and grid > effects.grid_cap[h] + tol:
            errors.append(f"h{h}: grid {grid} exceeds max_grid_window {effects.grid_cap[h]}")

        energy = energy + charge - discharge
        floor = max(bat.minimum_energy_kwh, effects.reserve[h])
        if energy < floor - tol:
            errors.append(f"h{h}: battery {energy} below required floor {floor}")
        if energy > bat.capacity_kwh + tol:
            errors.append(f"h{h}: battery {energy} above capacity {bat.capacity_kwh}")
        if abs(row["battery_energy_after_kwh"] - energy) > tol:
            errors.append(
                f"h{h}: reported battery_energy_after_kwh "
                f"{row['battery_energy_after_kwh']} != replayed {energy}"
            )

    if abs(energy - bat.initial_energy_kwh) > tol:
        errors.append(f"end-of-day battery {energy} != initial {bat.initial_energy_kwh}")
    return errors


def verify_totals(request: OptimizeRequest, plan: list[dict], reported: dict) -> list[str]:
    tariff = request.tariff_profile
    expected_grid = sum(row["grid_kwh"] for row in plan)
    expected_cost = sum(row["grid_kwh"] * tariff[row["hour"]] for row in plan)
    expected_peak = max(row["grid_kwh"] for row in plan)

    errors = []
    for name, expected in (("total_grid_kwh", expected_grid), ("total_cost_bdt", expected_cost),
                           ("peak_grid_kwh", expected_peak)):
        actual = reported.get(name)
        if actual is None or abs(float(actual) - expected) > 0.011:
            errors.append(f"{name} {actual} does not match hourly_plan ({expected})")
    return errors
