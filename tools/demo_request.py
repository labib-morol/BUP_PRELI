"""One-command demo request, safe in any shell.

Python quoting differs between bash, PowerShell and cmd, and PowerShell aliases
`curl` to Invoke-WebRequest while treating `@file` as splatting syntax. This script
avoids all of it: one command, no shell metacharacters, works on any platform.

    python tools/demo_request.py
    python tools/demo_request.py --url https://your-service.onrender.com
    python tools/demo_request.py --case 3          # SAMPLE-03
    python tools/demo_request.py --note "Do not charge the battery between 2 PM and 4 PM."
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "docs" / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"
DEFAULT_URL = "https://gridwise-llm-rm21.onrender.com"


def load_cases() -> list[dict]:
    return json.loads(CASES.read_text(encoding="utf-8"))["cases"]


def post(url: str, payload: dict, timeout: float) -> tuple[int, dict | str, float]:
    request = urllib.request.Request(
        f"{url.rstrip('/')}/optimize-energy",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.load(response), time.perf_counter() - started
    except urllib.error.HTTPError as error:
        body = error.read().decode(errors="replace")[:300]
        return error.code, body, time.perf_counter() - started
    except Exception as error:  # noqa: BLE001 - a demo should explain, not traceback
        return 0, f"{type(error).__name__}: {error}", time.perf_counter() - started


def get(url: str) -> tuple[int, object]:
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/health", timeout=90) as response:
            return response.status, json.load(response)
    except Exception as error:  # noqa: BLE001
        return 0, f"{type(error).__name__}: {error}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--case", type=int, default=1, help="public case number, 1-10")
    parser.add_argument("--note", help="use your own note instead of a public case")
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    print(f"GET  {args.url}/health")
    status, body = get(args.url)
    print(f"  -> HTTP {status} {body}")
    if status != 200:
        print("\nThe service did not answer /health. If this is a fresh deployment it may "
              "still be building; wait a minute and run this again.")
        return 1

    cases = load_cases()
    index = min(max(args.case, 1), len(cases)) - 1
    case = cases[index]
    payload = dict(case["input"])

    if args.note:
        payload["operator_notes"] = [args.note]
        payload["scenario_id"] = "DEMO-CUSTOM"
        reference = None
        print(f"\nPOST {args.url}/optimize-energy")
        print(f'  note: "{args.note}"')
    else:
        reference = case["expected_output"]["total_cost_bdt"]
        print(f"\nPOST {args.url}/optimize-energy")
        print(f"  case {case['id']}: {case['label']}")
        for i, note in enumerate(payload["operator_notes"]):
            print(f'    note {i}: "{note}"')

    status, body, elapsed = post(args.url, payload, args.timeout)
    if status != 200 or not isinstance(body, dict):
        print(f"  -> HTTP {status} in {elapsed:.2f}s: {body}")
        return 1

    print(f"  -> HTTP 200 in {elapsed:.2f}s")
    print("\ninterpretation")
    for entry in body["directive_interpretation"]:
        adjustment = entry["structured_adjustment"]
        detail = "" if adjustment is None else " " + json.dumps(adjustment)
        print(f"  [{entry['note_index']}] applies={str(entry['applies']).lower():5s} "
              f"{entry['directive_type']}{detail}")

    if not args.quiet:
        print("\nhourly plan        (hour | grid | solar | battery | action | E_after)")
        for row in body["hourly_plan"]:
            print(f"  {row['hour']:2d} | {row['grid_kwh']:7.2f} | {row['solar_used_kwh']:6.2f} | "
                  f"{row['battery_kwh']:6.2f} | {row['battery_action']:9s} | "
                  f"{row['battery_energy_after_kwh']:7.2f}")

    print(f"\ntotal_grid_kwh : {body['total_grid_kwh']}")
    print(f"total_cost_bdt : {body['total_cost_bdt']}")
    print(f"peak_grid_kwh  : {body['peak_grid_kwh']}")
    if reference is not None:
        ratio = min(1.0, reference / body["total_cost_bdt"]) if body["total_cost_bdt"] else 1.0
        verdict = "OPTIMAL - matches the organizer reference" if ratio > 0.9999 else "suboptimal"
        print(f"reference      : {reference}  ->  ratio {ratio:.4f}  ({verdict})")
    print(f"\nplan_summary   : {body['plan_summary']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
