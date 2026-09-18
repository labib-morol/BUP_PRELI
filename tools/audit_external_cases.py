"""Audit an external case file: is the reference answer itself correct?

The supplied file may have been generated rather than derived, so this checks the
reference output on its own terms before comparing our service to it:

  1. Is the reference plan VALID under the Problem Statement's own rules?
  2. Is the reference cost OPTIMAL for its stated directives (independent LP solve)?
  3. Does the reference interpretation AGREE with the deterministic parser
     (window convention and percentage direction)?

A disagreement is only our bug if the reference passes all three.

    python tools/audit_external_cases.py "C:/path/to/cases.json"
    python tools/audit_external_cases.py "C:/path/to/cases.json" --http http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.directives import Directive, compute_effects  # noqa: E402
from app.guardrails import expected_solar_factor, expected_window, parse_directive  # noqa: E402
from app.optimizer import solve, to_plan, totals  # noqa: E402
from app.schemas import OptimizeRequest  # noqa: E402
from app.verifier import verify, verify_totals  # noqa: E402


def as_directives(entries: list[dict], capacity: float) -> list[Directive]:
    out = []
    for entry in entries:
        adjustment = entry.get("structured_adjustment") or {}
        out.append(parse_directive({
            "directive_type": entry.get("directive_type"),
            "hours": adjustment.get("hours"),
            "factor": adjustment.get("factor"),
            "minimum_energy_kwh": adjustment.get("minimum_energy_kwh"),
            "max_grid_kwh": adjustment.get("max_grid_kwh"),
        }, capacity))
    return out


def check_reference(case: dict) -> list[str]:
    """Problems with the reference answer itself."""
    problems: list[str] = []
    request = OptimizeRequest(**case["input"])
    expected = case["expected_output"]
    capacity = request.battery.capacity_kwh

    # 1. interpretation vs the deterministic parser
    for entry in expected.get("directive_interpretation", []):
        if not entry.get("applies"):
            continue
        note = request.operator_notes[entry["note_index"]]
        truth_hours = (entry.get("structured_adjustment") or {}).get("hours")
        window = expected_window(note)
        if window is not None and truth_hours is not None and list(window) != list(truth_hours):
            problems.append(
                f"note {entry['note_index']}: reference hours {truth_hours} disagree with the "
                f"note's own clock expression {list(window)}")
        if entry.get("directive_type") == "solar_reduction":
            factor = expected_solar_factor(note)
            stated = (entry.get("structured_adjustment") or {}).get("factor")
            if factor is not None and stated is not None and abs(factor - stated) > 0.02:
                problems.append(
                    f"note {entry['note_index']}: reference factor {stated} disagrees with the "
                    f"note's own wording ({round(factor, 4)})")

    # 2. is the reference plan valid?
    directives = as_directives(expected.get("directive_interpretation", []), capacity)
    errors = verify(request, expected.get("hourly_plan", []), directives, tol=0.02)
    problems.extend(f"reference plan invalid: {e}" for e in errors[:4])

    # 3. is the reference cost optimal?
    solution = solve(request, directives)
    if solution is None:
        problems.append("reference directives make the problem infeasible")
    else:
        reference_cost = expected.get("total_cost_bdt")
        if reference_cost is not None:
            gap = reference_cost - solution.cost
            if gap > 0.02:
                problems.append(
                    f"reference cost is NOT optimal: {reference_cost} vs true optimum "
                    f"{round(solution.cost, 2)} (overpaying by {round(gap, 2)} BDT)")
    return problems


def our_answer(case: dict, url: str) -> dict:
    payload = json.dumps(case["input"]).encode()
    request = urllib.request.Request(f"{url.rstrip('/')}/optimize-energy", data=payload,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def compare(case: dict, theirs: dict, ours: dict) -> list[str]:
    """Where our response differs from the reference, in judge-relevant terms."""
    diffs: list[str] = []
    reference = case["expected_output"]

    mine = {e["note_index"]: e for e in ours["directive_interpretation"]}
    for entry in reference.get("directive_interpretation", []):
        idx = entry["note_index"]
        got = mine.get(idx)
        if got is None:
            diffs.append(f"note {idx}: no interpretation returned")
            continue
        if got["directive_type"] != entry["directive_type"]:
            diffs.append(f"note {idx}: type ours={got['directive_type']} "
                         f"reference={entry['directive_type']}")
            continue
        want = (entry.get("structured_adjustment") or {})
        have = (got.get("structured_adjustment") or {})
        if sorted(want.get("hours", [])) != sorted(have.get("hours", [])):
            diffs.append(f"note {idx}: hours ours={have.get('hours')} "
                         f"reference={want.get('hours')}")
        for key in ("factor", "minimum_energy_kwh", "max_grid_kwh"):
            if key in want and key in have and abs(want[key] - have[key]) > 0.02:
                diffs.append(f"note {idx}: {key} ours={have[key]} reference={want[key]}")

    ref_cost = reference.get("total_cost_bdt")
    if ref_cost and ours["total_cost_bdt"] > ref_cost + 0.02:
        diffs.append(f"cost ours={ours['total_cost_bdt']} reference={ref_cost} "
                     f"(ratio {min(1, ref_cost / ours['total_cost_bdt']):.4f})")
    return diffs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    parser.add_argument("--http", help="also compare against a running service")
    args = parser.parse_args()

    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    cases = data["cases"] if isinstance(data, dict) else data
    print(f"{len(cases)} case(s) loaded from {args.file}\n")

    reference_ok = 0
    for case in cases:
        sid = case["input"].get("scenario_id", "?")
        problems = check_reference(case)
        if not problems:
            reference_ok += 1
        print(f"{sid}")
        if problems:
            for problem in problems:
                print(f"   REFERENCE PROBLEM: {problem}")
        else:
            print("   reference: valid plan, optimal cost, interpretation matches the wording")

        if args.http:
            try:
                ours = our_answer(case, args.http)
            except Exception as error:  # noqa: BLE001
                print(f"   SERVICE ERROR: {type(error).__name__}: {error}")
                continue
            diffs = compare(case, ours, list(case for case in [case])[0] and ours)
            diffs = compare(case, case, ours)
            if diffs:
                for diff in diffs:
                    print(f"   OURS DIFFERS: {diff}")
            else:
                print("   ours: matches the reference exactly")

    print(f"\nreference self-consistent on {reference_ok}/{len(cases)} case(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
