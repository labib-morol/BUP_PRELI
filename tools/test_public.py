"""Score the solution against the public sample pack.

Modes
-----
--guards   deterministic guardrail layer only (no API key required)
--direct   ground-truth directives through optimizer + verifier (no API key required)
--http     full pipeline against a running server (requires a provider key)

Usage
-----
    python tools/test_public.py --guards
    python tools/test_public.py --direct
    python tools/test_public.py --http http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.directives import Directive  # noqa: E402
from app.guardrails import expected_solar_factor, expected_window, parse_directive  # noqa: E402
from app.optimizer import solve, to_plan, totals  # noqa: E402
from app.schemas import OptimizeRequest  # noqa: E402
from app.verifier import verify, verify_totals  # noqa: E402

CASES = ROOT / "docs" / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"


def load():
    return json.loads(CASES.read_text(encoding="utf-8"))["cases"]


def truth_directives(case) -> list[Directive]:
    out = []
    for entry in case["expected_output"]["directive_interpretation"]:
        adjustment = entry.get("structured_adjustment") or {}
        out.append(parse_directive(
            {
                "directive_type": entry["directive_type"],
                "hours": adjustment.get("hours"),
                "factor": adjustment.get("factor"),
                "minimum_energy_kwh": adjustment.get("minimum_energy_kwh"),
                "max_grid_kwh": adjustment.get("max_grid_kwh"),
            },
            case["input"]["battery"]["capacity_kwh"],
        ))
    return out


def mode_guards(cases) -> int:
    """The deterministic layer must agree with organizer ground truth on every note."""
    failures = 0
    checked_window = checked_factor = 0
    for case in cases:
        for entry in case["expected_output"]["directive_interpretation"]:
            if not entry["applies"]:
                continue
            note = case["input"]["operator_notes"][entry["note_index"]]
            hours = entry["structured_adjustment"]["hours"]
            window = expected_window(note)
            if window is not None:
                checked_window += 1
                if list(window) != hours:
                    failures += 1
                    print(f"  {case['id']} note {entry['note_index']}: window {window} != truth {hours}")
            if entry["directive_type"] == "solar_reduction":
                factor = expected_solar_factor(note)
                if factor is not None:
                    checked_factor += 1
                    if abs(factor - entry["structured_adjustment"]["factor"]) > 0.02:
                        failures += 1
                        print(f"  {case['id']} note {entry['note_index']}: factor {factor} "
                              f"!= truth {entry['structured_adjustment']['factor']}")
    print(f"guards: {checked_window} windows and {checked_factor} factors cross-checked, "
          f"{failures} disagreement(s)")
    return failures


def mode_direct(cases) -> int:
    """Ground-truth directives -> LP -> rounding -> replay, against reference cost."""
    failures = 0
    ratios = []
    for case in cases:
        request = OptimizeRequest(**case["input"])
        directives = truth_directives(case)
        solution = solve(request, directives)
        if solution is None:
            print(f"  {case['id']}: LP infeasible under ground truth")
            failures += 1
            continue
        plan = to_plan(solution, request)
        errors = verify(request, plan, directives) + verify_totals(
            request, plan, dict(zip(("total_grid_kwh", "total_cost_bdt", "peak_grid_kwh"),
                                    totals(plan, request))))
        reference = case["expected_output"]["total_cost_bdt"]
        cost = totals(plan, request)[1]
        ratio = min(1.0, reference / cost) if cost > 0 else 1.0
        ratios.append(ratio)
        status = "ok" if not errors else "INVALID"
        if errors or ratio < 0.999:
            failures += 1
            print(f"  {case['id']}: {status} cost={cost:.2f} reference={reference} "
                  f"ratio={ratio:.4f} errors={errors[:2]}")
    mean = sum(ratios) / len(ratios) if ratios else 0.0
    print(f"direct: {len(cases) - failures}/{len(cases)} valid and optimal, "
          f"mean cost ratio {mean:.4f} (optimization quality {10 * mean:.2f}/10)")
    return failures


def mode_http(cases, base_url: str) -> int:
    import httpx

    failures = 0
    latencies = []
    with httpx.Client(timeout=30.0) as client:
        health = client.get(f"{base_url}/health")
        print(f"health: {health.status_code} {health.text.strip()[:60]}")
        for case in cases:
            started = time.perf_counter()
            response = client.post(f"{base_url}/optimize-energy", json=case["input"])
            latencies.append(time.perf_counter() - started)
            if response.status_code != 200:
                print(f"  {case['id']}: HTTP {response.status_code} {response.text[:120]}")
                failures += 1
                continue
            body = response.json()
            request = OptimizeRequest(**case["input"])
            truth = truth_directives(case)

            reported = body["directive_interpretation"]
            truth_entries = case["expected_output"]["directive_interpretation"]
            interpretation_ok = len(reported) == len(truth_entries) and all(
                r["directive_type"] == t["directive_type"]
                and (not t["applies"] or (
                    sorted(r["structured_adjustment"]["hours"]) == sorted(
                        t["structured_adjustment"]["hours"])))
                for r, t in zip(reported, truth_entries)
            )
            errors = verify(request, body["hourly_plan"], truth)
            errors += verify_totals(request, body["hourly_plan"], body)
            reference = case["expected_output"]["total_cost_bdt"]
            cost = body["total_cost_bdt"]
            ratio = min(1.0, reference / cost) if cost > 0 else 1.0
            print(f"  {case['id']}: interp={'ok' if interpretation_ok else 'MISMATCH'} "
                  f"plan={'ok' if not errors else 'INVALID'} cost={cost:.2f} "
                  f"ratio={ratio:.4f} {('errors=' + str(errors[:2])) if errors else ''}")
            if not interpretation_ok or errors or ratio < 0.999:
                failures += 1
    latencies.sort()
    p95 = latencies[max(0, int(0.95 * len(latencies)) - 1)]
    print(f"http: {len(cases) - failures}/{len(cases)} fully correct, "
          f"p95 latency {p95:.2f}s")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--guards", action="store_true")
    group.add_argument("--direct", action="store_true")
    group.add_argument("--http")
    args = parser.parse_args()
    cases = load()

    if args.guards:
        return 1 if mode_guards(cases) else 0
    if args.direct:
        return 1 if mode_direct(cases) else 0
    return 1 if mode_http(cases, args.http) else 0


if __name__ == "__main__":
    sys.exit(main())
