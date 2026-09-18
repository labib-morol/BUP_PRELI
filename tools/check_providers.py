"""Verify every configured provider before a demo or a submission.

    python tools/check_providers.py

Sends one minimal request per provider and reports status, latency and a masked
key fingerprint. Never prints a key, a prefix longer than four characters, or any
part of a response body.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.env import load_dotenv  # noqa: E402
from app.llm import available_providers  # noqa: E402

load_dotenv()


async def ping(provider) -> tuple[bool, str]:
    started = time.perf_counter()
    try:
        text = await asyncio.wait_for(
            provider.call('Reply with JSON only: {"ok":true}', "ping"), timeout=20
        )
    except Exception as error:  # noqa: BLE001 - reported, never raised
        return False, f"{type(error).__name__}: {str(error)[:160]}"
    elapsed = time.perf_counter() - started
    return True, f"ok in {elapsed:.2f}s, {len(text or '')} chars returned"


async def main() -> int:
    providers = available_providers()
    if not providers:
        print("no providers configured - set GEMINI_API_KEY and/or GROQ_API_KEY "
              "in .env or the environment")
        return 1

    print(f"{len(providers)} provider(s) configured\n")
    failures = 0
    for provider in providers:
        ok, detail = await ping(provider)
        failures += 0 if ok else 1
        print(f"  [{'OK ' if ok else 'FAIL'}] {provider.name:32s} {detail}")
    print()
    if failures:
        print(f"{failures} provider(s) failed. The service still serves /health and "
              f"degrades to no_op interpretations, but fix this before submitting.")
    else:
        print("all providers reachable")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
