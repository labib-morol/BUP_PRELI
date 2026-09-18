"""Regression guard: an invalid reference must not be treated as ground truth.

A supplied edge case ("capacity ceiling saturation") claimed a cheaper schedule than
ours, but its plan failed three rules: unmet demand in hours 21 and 22, and a final
battery of 80 kWh against an initial 300 kWh. Its low cost came from not supplying
50 kWh of load and from spending 220 kWh of stored energy as a free one-time source -
the exact behaviour end-of-day neutrality exists to forbid.

This is worth pinning down because such a plan looks better on the raw number while
scoring zero: the judge replays the plan rather than trusting the reported cost. The
test asserts both halves of the correct response - that our verifier rejects the
reference, and that our optimizer still returns a valid, cheaper-than-naive plan.

    python tools/test_edge_cases.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.directives import Directive  # noqa: E402
from app.optimizer import solve, to_plan, totals  # noqa: E402
from app.schemas import OptimizeRequest  # noqa: E402
from app.verifier import verify  # noqa: E402

CASE = {
    "scenario_id": "EDGE-10-CAPACITY-CEILING-SATURATION",
    "operator_notes": [
        "Inverter maintenance forbids battery charging between 4 PM and 7 PM.",
        "Grid peak load restriction of 120 kWh from 8 PM to 11 PM.",
    ],
    "battery": {"capacity_kwh": 500.0, "initial_energy_kwh": 300.0,
                "minimum_energy_kwh": 80.0, "max_charge_kwh_per_hour": 100.0,
                "max_discharge_kwh_per_hour": 100.0},
    "hours": [
        {"hour": 0, "demand_kwh": 120.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 6.0},
        {"hour": 1, "demand_kwh": 110.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 6.0},
        {"hour": 2, "demand_kwh": 100.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 6.0},
        {"hour": 3, "demand_kwh": 100.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 6.0},
        {"hour": 4, "demand_kwh": 110.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 6.0},
        {"hour": 5, "demand_kwh": 130.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 6.0},
        {"hour": 6, "demand_kwh": 160.0, "solar_kwh": 20.0, "tariff_bdt_per_kwh": 8.0},
        {"hour": 7, "demand_kwh": 200.0, "solar_kwh": 60.0, "tariff_bdt_per_kwh": 8.0},
        {"hour": 8, "demand_kwh": 240.0, "solar_kwh": 120.0, "tariff_bdt_per_kwh": 10.0},
        {"hour": 9, "demand_kwh": 250.0, "solar_kwh": 180.0, "tariff_bdt_per_kwh": 10.0},
        {"hour": 10, "demand_kwh": 230.0, "solar_kwh": 220.0, "tariff_bdt_per_kwh": 10.0},
        {"hour": 11, "demand_kwh": 220.0, "solar_kwh": 250.0, "tariff_bdt_per_kwh": 10.0},
        {"hour": 12, "demand_kwh": 210.0, "solar_kwh": 240.0, "tariff_bdt_per_kwh": 10.0},
        {"hour": 13, "demand_kwh": 220.0, "solar_kwh": 210.0, "tariff_bdt_per_kwh": 10.0},
        {"hour": 14, "demand_kwh": 240.0, "solar_kwh": 160.0, "tariff_bdt_per_kwh": 10.0},
        {"hour": 15, "demand_kwh": 250.0, "solar_kwh": 90.0, "tariff_bdt_per_kwh": 10.0},
        {"hour": 16, "demand_kwh": 230.0, "solar_kwh": 30.0, "tariff_bdt_per_kwh": 12.0},
        {"hour": 17, "demand_kwh": 200.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 14.0},
        {"hour": 18, "demand_kwh": 180.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 14.0},
        {"hour": 19, "demand_kwh": 170.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 14.0},
        {"hour": 20, "demand_kwh": 160.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 14.0},
        {"hour": 21, "demand_kwh": 150.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 10.0},
        {"hour": 22, "demand_kwh": 140.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 8.0},
        {"hour": 23, "demand_kwh": 130.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 6.0},
    ],
}

# The plan that was supplied as the reference answer, verbatim.
REFERENCE_PLAN = [
    (0, 120.0, 0.0, "idle", 0.0, 300.0), (1, 110.0, 0.0, "idle", 0.0, 300.0),
    (2, 100.0, 0.0, "idle", 0.0, 300.0), (3, 100.0, 0.0, "idle", 0.0, 300.0),
    (4, 210.0, 0.0, "charge", 100.0, 400.0), (5, 230.0, 0.0, "charge", 100.0, 500.0),
    (6, 140.0, 20.0, "idle", 0.0, 500.0), (7, 140.0, 60.0, "idle", 0.0, 500.0),
    (8, 120.0, 120.0, "idle", 0.0, 500.0), (9, 70.0, 180.0, "idle", 0.0, 500.0),
    (10, 10.0, 220.0, "idle", 0.0, 500.0), (11, 0.0, 220.0, "idle", 0.0, 500.0),
    (12, 0.0, 210.0, "idle", 0.0, 500.0), (13, 10.0, 210.0, "idle", 0.0, 500.0),
    (14, 80.0, 160.0, "idle", 0.0, 500.0), (15, 160.0, 90.0, "idle", 0.0, 500.0),
    (16, 150.0, 30.0, "discharge", 50.0, 450.0), (17, 100.0, 0.0, "discharge", 100.0, 350.0),
    (18, 80.0, 0.0, "discharge", 100.0, 250.0), (19, 70.0, 0.0, "discharge", 100.0, 150.0),
    (20, 90.0, 0.0, "discharge", 70.0, 80.0), (21, 120.0, 0.0, "idle", 0.0, 80.0),
    (22, 120.0, 0.0, "idle", 0.0, 80.0), (23, 130.0, 0.0, "idle", 0.0, 80.0),
]

DIRECTIVES = [Directive("no_charge_window", (16, 17, 18)),
              Directive("max_grid_window", (20, 21, 22), max_grid_kwh=120.0)]
REFERENCE_COST = 22440.0

FAILURES: list[str] = []


def check(condition: bool, label: str) -> None:
    print(f"  [{'OK ' if condition else 'FAIL'}] {label}")
    if not condition:
        FAILURES.append(label)


def main() -> int:
    request = OptimizeRequest(**CASE)

    print("the supplied reference plan must be rejected:")
    plan = [{"hour": h, "grid_kwh": g, "solar_used_kwh": s, "battery_action": a,
             "battery_kwh": k, "battery_energy_after_kwh": e}
            for h, g, s, a, k, e in REFERENCE_PLAN]
    errors = verify(request, plan, DIRECTIVES)
    check(any("energy balance" in e for e in errors),
          f"unmet demand detected ({sum('energy balance' in e for e in errors)} hours)")
    check(any("end-of-day" in e for e in errors),
          "end-of-day neutrality violation detected")

    print("\nour own answer must be valid and exactly optimal:")
    solution = solve(request, DIRECTIVES)
    check(solution is not None, "the problem is feasible under the real rules")
    if solution is not None:
        ours = to_plan(solution, request)
        check(not verify(request, ours, DIRECTIVES), "our plan passes replay verification")
        _, cost, _ = totals(ours, request)
        check(abs(ours[23]["battery_energy_after_kwh"] - 300.0) < 1e-6,
              "our plan returns the battery to its initial 300 kWh")
        check(cost > REFERENCE_COST,
              f"our honest cost {cost:.2f} exceeds the invalid reference {REFERENCE_COST:.2f}"
              " (the gap is the demand it failed to supply)")
        print(f"       ours={cost:.2f}   invalid reference={REFERENCE_COST:.2f}   "
              f"ratio {min(1, REFERENCE_COST / cost):.4f}")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S)")
        for item in FAILURES:
            print(" -", item)
        return 1
    print("EDGE CASE GUARD PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
