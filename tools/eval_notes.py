"""Paraphrase evaluation harness — measures interpretation accuracy per rubric axis.

Ground truth lives in `tools/notes_corpus.json` and is hand-written, never generated
by the model under test. Each entry is scored on the four sub-scores the judge uses:

    relevance (applies)  ·  directive_type  ·  affected hours  ·  numeric value / shape

Run it after any prompt change:

    python tools/eval_notes.py              # full run
    python tools/eval_notes.py --axis solar # one axis only
    python tools/eval_notes.py --verbose    # print every mismatch

Requires a configured provider key; it calls the real model through the same
`app.llm` path the service uses.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.guardrails import assess, parse_directive  # noqa: E402
from app.llm import gather_readings  # noqa: E402
from app.schemas import Battery, HourEntry, OptimizeRequest  # noqa: E402

CORPUS = ROOT / "tools" / "notes_corpus.json"

DEMAND = [90, 85, 80, 80, 85, 95, 110, 130, 150, 165, 175, 180,
          185, 180, 170, 165, 170, 185, 205, 215, 205, 175, 135, 105]
SOLAR = [0, 0, 0, 0, 0, 0, 5, 20, 50, 90, 130, 160,
         180, 170, 140, 90, 45, 10, 0, 0, 0, 0, 0, 0]
TARIFF = [6, 6, 5, 5, 5, 6, 8, 10, 12, 14, 16, 16,
          15, 14, 13, 14, 18, 22, 28, 30, 26, 18, 10, 7]

FACTOR_TOL = 0.02
KWH_TOL = 0.51


def scenario(capacity_kwh: float) -> OptimizeRequest:
    return OptimizeRequest(
        scenario_id="EVAL",
        operator_notes=["placeholder"],
        hours=[HourEntry(hour=h, demand_kwh=DEMAND[h], solar_kwh=SOLAR[h],
                         tariff_bdt_per_kwh=TARIFF[h]) for h in range(24)],
        battery=Battery(capacity_kwh=capacity_kwh, initial_energy_kwh=capacity_kwh * 0.5,
                        minimum_energy_kwh=capacity_kwh * 0.2,
                        max_charge_kwh_per_hour=capacity_kwh * 0.25,
                        max_discharge_kwh_per_hour=capacity_kwh * 0.25),
    )


def score(entry: dict, directive) -> dict[str, bool]:
    expect = entry["expect"]
    applies = directive.applies
    result = {"relevance": applies == bool(expect["applies"]), "type": True, "hours": True,
              "value": True}

    if not expect["applies"]:
        result["type"] = directive.directive_type == "no_op"
        result["hours"] = directive.hours == ()
        result["value"] = directive.adjustment() is None
        return result

    result["type"] = directive.directive_type == expect["directive_type"]
    result["hours"] = tuple(directive.hours) == tuple(expect["hours"])
    expected_value = expect.get("factor", expect.get("minimum_energy_kwh",
                                                     expect.get("max_grid_kwh")))
    if expected_value is None:
        result["value"] = directive.adjustment() is not None
    else:
        actual = {"solar_reduction": directive.factor,
                  "minimum_battery_reserve": directive.minimum_energy_kwh,
                  "max_grid_window": directive.max_grid_kwh}.get(directive.directive_type)
        tolerance = FACTOR_TOL if expect.get("factor") is not None else KWH_TOL
        result["value"] = actual is not None and abs(actual - expected_value) <= tolerance
    return result


async def run(entries: list[dict], verbose: bool) -> int:
    totals: dict[str, list[bool]] = defaultdict(list)
    axis_totals: dict[str, list[bool]] = defaultdict(list)
    failures: list[str] = []

    for entry in entries:
        request = scenario(entry["capacity_kwh"])
        notes = [entry["note"]]
        readings = await gather_readings(
            notes, entry["capacity_kwh"], request.battery.initial_energy_kwh,
            request.battery.minimum_energy_kwh,
        )
        if not any(readings):
            print("no provider responded — set a provider key in the environment")
            return 2

        parsed = [parse_directive(raw, entry["capacity_kwh"]) for raw in readings[0]]
        directive = assess(0, notes[0], parsed, entry["capacity_kwh"]).reported
        result = score(entry, directive)
        for key, ok in result.items():
            totals[key].append(ok)
            axis_totals[entry["axis"]].append(all(result.values()))
        if not all(result.values()):
            failures.append(
                f"{entry['id']:7s} {entry['axis']:28s} "
                f"got={directive.directive_type}{list(directive.hours)} "
                f"f={directive.factor} r={directive.minimum_energy_kwh} "
                f"g={directive.max_grid_kwh} "
                f"want={entry['expect']['directive_type']}"
                f"{entry['expect'].get('hours', '')} "
                f"{ {k: v for k, v in entry['expect'].items() if k in ('factor', 'minimum_energy_kwh', 'max_grid_kwh')} }"
                f"  failed={[k for k, v in result.items() if not v]}"
            )

    total = len(entries)
    correct = sum(1 for values in zip(*totals.values()) if all(values))
    print(f"\ncorpus: {total} notes\n")
    print("per-axis accuracy (all four sub-scores correct):")
    for axis in sorted(axis_totals):
        values = axis_totals[axis]
        print(f"  {axis:30s} {sum(values):3d}/{len(values):<3d} {100 * sum(values) / len(values):5.1f}%")
    print("\nper-sub-score accuracy (the judge's 5+5+5+5 split):")
    for key in ("relevance", "type", "hours", "value"):
        values = totals[key]
        print(f"  {key:30s} {sum(values):3d}/{len(values):<3d} {100 * sum(values) / len(values):5.1f}%")
    print(f"\nfully correct notes: {correct}/{total} ({100 * correct / total:.1f}%)")
    print(f"projected interpretation category: {25 * correct / total:.2f}/25")

    if failures:
        print(f"\n{len(failures)} mismatch(es):")
        for line in failures if verbose else failures[:15]:
            print("  " + line)
        if not verbose and len(failures) > 15:
            print(f"  … {len(failures) - 15} more (use --verbose)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--axis")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    entries = json.loads(CORPUS.read_text(encoding="utf-8"))["entries"]
    if args.axis:
        entries = [e for e in entries if args.axis in e["axis"]]
    return asyncio.run(run(entries, args.verbose))


if __name__ == "__main__":
    sys.exit(main())
