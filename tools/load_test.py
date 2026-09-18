"""Load and latency measurement against a running server.

Uses the paraphrase corpus so every request carries a *different* note - a repeated
note would be served from the interpretation cache in about a millisecond, which would
flatter the numbers the judge's p95 is actually measuring.

    python tools/load_test.py --url http://127.0.0.1:8000 --sequential 39 --concurrency 10
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from app.schemas import Battery, HourEntry  # noqa: E402
from eval_notes import DEMAND, SOLAR, TARIFF  # noqa: E402

CORPUS = ROOT / "tools" / "notes_corpus.json"


def payload(note: str, capacity: float, index: int) -> dict:
    return {
        "scenario_id": f"LOAD-{index:03d}",
        "operator_notes": [note],
        "hours": [{"hour": h, "demand_kwh": DEMAND[h], "solar_kwh": SOLAR[h],
                   "tariff_bdt_per_kwh": TARIFF[h]} for h in range(24)],
        "battery": {
            "capacity_kwh": capacity,
            "initial_energy_kwh": capacity * 0.5,
            "minimum_energy_kwh": capacity * 0.2,
            "max_charge_kwh_per_hour": capacity * 0.25,
            "max_discharge_kwh_per_hour": capacity * 0.25,
        },
    }


def report(label: str, latencies: list[float], failures: list[str]) -> None:
    if not latencies:
        print(f"{label}: no successful requests")
        return
    ordered = sorted(latencies)
    p50 = statistics.median(ordered)
    p95 = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]
    print(f"{label}: n={len(ordered)} p50={p50:.2f}s p95={p95:.2f}s max={max(ordered):.2f}s "
          f"failures={len(failures)}")
    if failures:
        for line in failures[:5]:
            print("   ", line)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--sequential", type=int, default=39)
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()

    import httpx

    entries = json.loads(CORPUS.read_text(encoding="utf-8"))["entries"]
    all_requests = [payload(e["note"], e["capacity_kwh"], i) for i, e in enumerate(entries)]
    requests = all_requests[: args.sequential]

    latencies: list[float] = []
    failures: list[str] = []

    with httpx.Client(timeout=30.0) as client:
        health = client.get(f"{args.url}/health")
        print(f"health: {health.status_code} {health.text.strip()[:40]}")

        for request in requests:
            started = time.perf_counter()
            try:
                response = client.post(f"{args.url}/optimize-energy", json=request)
            except Exception as error:  # noqa: BLE001
                failures.append(f"{request['scenario_id']}: {type(error).__name__}")
                continue
            latencies.append(time.perf_counter() - started)
            if response.status_code != 200:
                failures.append(f"{request['scenario_id']}: HTTP {response.status_code}")
    report("sequential", latencies, failures)

    burst_latencies: list[float] = []
    burst_failures: list[str] = []
    with httpx.Client(timeout=60.0) as client:
        started = time.perf_counter()
        with client.stream("GET", f"{args.url}/health") as _:
            pass
        import concurrent.futures

        def send(request: dict) -> tuple[float, str | None]:
            begin = time.perf_counter()
            try:
                response = client.post(f"{args.url}/optimize-energy", json=request)
            except Exception as error:  # noqa: BLE001
                return time.perf_counter() - begin, f"{request['scenario_id']}: {type(error).__name__}"
            if response.status_code != 200:
                return time.perf_counter() - begin, f"{request['scenario_id']}: HTTP {response.status_code}"
            return time.perf_counter() - begin, None

        wave = all_requests[args.sequential: args.sequential + args.concurrency]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            for elapsed, error in pool.map(send, wave):
                burst_latencies.append(elapsed)
                if error:
                    burst_failures.append(error)
        wall = time.perf_counter() - started
    report(f"concurrent x{args.concurrency}", burst_latencies, burst_failures)
    print(f"burst wall time: {wall:.2f}s for {len(wave)} simultaneous requests")

    total_failures = len(failures) + len(burst_failures)
    print("\nPASS" if not total_failures else f"\n{total_failures} FAILURE(S)")
    return 0 if not total_failures else 1


if __name__ == "__main__":
    sys.exit(main())
