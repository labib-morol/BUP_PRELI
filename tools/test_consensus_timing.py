"""Timing tests for the consensus collector, with no provider calls.

Quota exhaustion makes live timing measurements unreliable, so this drives the real
`_consensus` logic with fake providers whose latency and success are scripted. It
pins the four scenarios that matter and costs nothing to run:

  1. fast success + slow failure  -> return as soon as the grace window closes, not
     when the failing provider gives up (this was a 7.28s bug live)
  2. two successes                -> both readings kept, so hedging stays available
  3. slow success + fast failure  -> the working provider is never cancelled early
  4. total failure                -> the recovery path runs and the deadline holds

    python tools/test_consensus_timing.py
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app.llm as llm  # noqa: E402

FAILURES: list[str] = []


def check(condition: bool, label: str) -> None:
    print(f"  [{'OK ' if condition else 'FAIL'}] {label}")
    if not condition:
        FAILURES.append(label)


def scripted(plan: dict[str, tuple[float, bool]]):
    """A fake provider call: sleeps for the scripted delay, then succeeds or not."""
    async def call(provider, user, note_count, timeout=None):
        delay, ok = plan[provider.name]
        await asyncio.sleep(delay)
        return [{"note_index": 0, "directive_type": "no_op"}] if ok else None
    return call


async def scenario(label: str, plan: dict[str, tuple[float, bool]],
                   expected_seconds: tuple[float, float], expected_readings: int) -> None:
    names = list(plan)
    fakes = [llm.Provider(name, name, None) for name in names]
    original_providers, original_call = llm.available_providers, llm._call_provider
    llm.available_providers = lambda: fakes
    llm._call_provider = scripted(plan)
    try:
        started = time.perf_counter()
        readings = await llm._consensus(fakes, "note 0: test", 1)
        elapsed = time.perf_counter() - started
    finally:
        llm.available_providers, llm._call_provider = original_providers, original_call

    low, high = expected_seconds
    print(f"{label}: {elapsed:.2f}s, {len(readings)} reading(s)")
    check(low <= elapsed <= high, f"{label}: {elapsed:.2f}s within [{low}, {high}]")
    check(len(readings) == expected_readings,
          f"{label}: {len(readings)} reading(s), expected {expected_readings}")


async def main() -> int:
    original_consensus = llm.CONSENSUS
    original_grace, original_budget = llm.GRACE, llm.BUDGET
    llm.CONSENSUS = 2
    llm.GRACE, llm.BUDGET = 2.0, 8.0
    try:
        await scenario(
            "fast success + slow failure",
            {"fast": (0.2, True), "slow": (6.0, False)},
            expected_seconds=(2.0, 3.2), expected_readings=1)

        await scenario(
            "two successes",
            {"fast": (0.2, True), "other": (0.8, True)},
            expected_seconds=(0.8, 2.4), expected_readings=2)

        await scenario(
            "slow success + fast failure",
            {"fast": (0.1, False), "slow": (3.0, True)},
            expected_seconds=(3.0, 5.4), expected_readings=1)

        await scenario(
            "total failure",
            {"a": (0.3, False), "b": (0.3, False)},
            expected_seconds=(0.3, 22.0), expected_readings=0)
    finally:
        llm.CONSENSUS = original_consensus
        llm.GRACE, llm.BUDGET = original_grace, original_budget

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S)")
        for item in FAILURES:
            print(" -", item)
        return 1
    print("ALL CONSENSUS TIMING TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
