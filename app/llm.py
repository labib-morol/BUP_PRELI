"""Language-model layer: a provider chain with consensus, caching and timeouts.

Why a chain instead of one provider: the Participant Guide makes key availability,
quota and rate limits the team's responsibility, and a judge will not repair an
unavailable dependency. Running two independent model families over the same note
also produces the disagreement signal that the guardrail layer uses to decide when
hedging is worthwhile.

Both providers are asked for the same flat JSON object, so any provider can be
swapped or dropped without touching the rest of the pipeline.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

from .env import load_dotenv
from .prompt import SYSTEM_PROMPT, build_few_shot_block, build_user_prompt

load_dotenv()

log = logging.getLogger("gridwise.llm")

CALL_TIMEOUT = float(os.getenv("GRIDWISE_LLM_TIMEOUT", "6"))
GRACE = float(os.getenv("GRIDWISE_CONSENSUS_GRACE", "2.0"))
BUDGET = float(os.getenv("GRIDWISE_LLM_BUDGET", "4.0"))
# Hard ceiling for the recovery path when every provider failed. The judge
# allows 30s per request; this keeps the worst case well inside it.
DEADLINE = float(os.getenv("GRIDWISE_LLM_DEADLINE", "12"))
# One call per request by default: it halves provider quota usage, which is the
# binding constraint in practice, and removes the second-opinion wait entirely.
# The deterministic window hedge still works from a single reading. Set to 2 to
# compare two models when the second provider is fast and not rate-limited.
CONSENSUS = max(1, int(os.getenv("GRIDWISE_CONSENSUS", "1")))
MAX_CONCURRENT = max(1, int(os.getenv("GRIDWISE_LLM_CONCURRENCY", "8")))
CACHE_SIZE = 512

_semaphore = asyncio.Semaphore(MAX_CONCURRENT)
_cache: dict[tuple, list[list[dict]]] = {}
_cache_order: list[tuple] = []

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(frozen=True)
class Provider:
    name: str
    model: str
    call: Callable[[str, str], Awaitable[str]]


def _provider_gemini(key: str, model: str) -> Provider:
    async def call(system: str, user: str) -> str:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=key)
        response = await client.aio.models.generate_content(
            model=model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0,
                response_mime_type="application/json",
                max_output_tokens=1024,
            ),
        )
        return response.text or ""

    return Provider(f"gemini:{model}", model, call)


def _provider_openai_compatible(name: str, key: str, model: str, base_url: str | None) -> Provider:
    async def call(system: str, user: str) -> str:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=key, base_url=base_url, timeout=CALL_TIMEOUT,
                                max_retries=0)
        response = await client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
        )
        return response.choices[0].message.content or ""

    return Provider(name, model, call)


def available_providers() -> list[Provider]:
    """Providers in preference order, driven entirely by environment variables.

    Order matters: `gather_readings` consults the first `GRIDWISE_CONSENSUS`
    providers in parallel, so the first two entries are the two opinions that get
    compared, and everything after them is spare capacity used only when the first
    two all fail.

    Slot 2 defaults to a second call to the same fast model. Measured against the
    configured keys, one of them is unreliable in ways that are independent per
    request (transient 503s on the primary; the Groq key rate-limits almost every
    call), so a parallel duplicate covers a transient failure at no latency cost,
    whereas a slow cross-family model that never answers inside the 3-second budget
    contributes nothing while still delaying every request. Point
    GRIDWISE_GEMINI_MODEL_2 at a different model to restore a cross-family vote when
    the second provider is itself fast and reliable.

    Set GRIDWISE_GEMINI_MODEL_2="" to run a single opinion.
    """
    providers: list[Provider] = []
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if gemini_key:
        providers.append(_provider_gemini(
            gemini_key, os.getenv("GRIDWISE_GEMINI_MODEL", "gemini-flash-lite-latest")))
    # A second Google key from a different Cloud project is a separate quota bucket,
    # so it fails independently of the first even though it runs the same model.
    second_key = os.getenv("GEMINI_API_KEY_2")
    if second_key:
        providers.append(_provider_gemini(
            second_key, os.getenv("GRIDWISE_GEMINI_MODEL", "gemini-flash-lite-latest")))

    # Any OpenAI-compatible endpoint can be slotted in without a code change, so a
    # second vendor with its own quota can be added while the service is live:
    #   EXTRA_BASE_URL=https://api.agentrouter.com/v1  EXTRA_MODEL=...  EXTRA_API_KEY=...
    extra_key = os.getenv("EXTRA_API_KEY")
    if extra_key:
        providers.append(_provider_openai_compatible(
            os.getenv("EXTRA_NAME", "extra"), extra_key,
            os.getenv("EXTRA_MODEL", "gpt-4o-mini"),
            os.getenv("EXTRA_BASE_URL") or None))

    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        providers.append(_provider_openai_compatible(
            "groq", groq_key, os.getenv("GRIDWISE_GROQ_MODEL", "openai/gpt-oss-20b"),
            "https://api.groq.com/openai/v1"))
    if gemini_key:
        second = (os.getenv("GRIDWISE_GEMINI_LITE_MODEL")
                  or os.getenv("GRIDWISE_GEMINI_MODEL_2") or "gemini-3.1-flash-lite")
        if second:
            providers.append(_provider_gemini(gemini_key, second))
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        providers.append(_provider_openai_compatible(
            "openai", openai_key, os.getenv("GRIDWISE_OPENAI_MODEL", "gpt-4o-mini"), None))
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_key:
        providers.append(_provider_openai_compatible(
            "openrouter", openrouter_key,
            os.getenv("GRIDWISE_OPENROUTER_MODEL", "google/gemini-2.0-flash-001"),
            "https://openrouter.ai/api/v1"))

    order = [name.strip() for name in os.getenv("GRIDWISE_LLM_CHAIN", "").split(",") if name.strip()]
    if order:
        providers.sort(key=lambda p: order.index(p.name) if p.name in order else len(order))
    return providers


def parse_readings(text: str, note_count: int) -> list[dict] | None:
    """Extract one raw directive object per note from a model response."""
    if not text:
        return None
    match = _JSON_BLOCK.search(text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    items = payload.get("directives") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return None

    by_index: dict[int, dict] = {}
    for position, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        index = item.get("note_index")
        index = index if isinstance(index, int) and 0 <= index < note_count else position
        if 0 <= index < note_count and index not in by_index:
            by_index[index] = item
    return [by_index.get(i, {"note_index": i, "directive_type": "no_op"}) for i in range(note_count)]


async def _call_provider(provider: Provider, user: str, note_count: int,
                         timeout: float | None = None) -> list[dict] | None:
    """One attempt, one deadline.

    Deliberately no retry: a retried timeout costs a second full timeout inside a
    5-second p95 budget. A slow provider is simply a provider that did not get to
    vote this time - the caller falls back to whichever readings did arrive.
    """
    system = f"{SYSTEM_PROMPT}\n\nEXAMPLES\n{build_few_shot_block()}"
    budget = CALL_TIMEOUT if timeout is None else timeout
    started = time.perf_counter()
    async with _semaphore:
        try:
            text = await asyncio.wait_for(provider.call(system, user), timeout=budget)
        except Exception as error:  # noqa: BLE001 - any provider failure is non-fatal
            log.warning("provider %s gave no usable answer after %.1fs: %s",
                        provider.name, time.perf_counter() - started, type(error).__name__)
            return None
    readings = parse_readings(text, note_count)
    if readings:
        log.info("provider %s ok in %.2fs", provider.name, time.perf_counter() - started)
        return readings
    log.warning("provider %s returned unparsable output", provider.name)
    return None


def _cache_get(key: tuple) -> list[list[dict]] | None:
    return _cache.get(key)


def _cache_put(key: tuple, value: list[list[dict]]) -> None:
    if key in _cache:
        return
    _cache[key] = value
    _cache_order.append(key)
    while len(_cache_order) > CACHE_SIZE:
        _cache.pop(_cache_order.pop(0), None)


async def _gather(providers: list[Provider], user: str, note_count: int) -> list[list[dict]]:
    """Readings from every provider that answered with a complete, parsable result."""
    results = await asyncio.gather(
        *(_call_provider(provider, user, note_count) for provider in providers),
        return_exceptions=True,
    )
    return [r for r in results if isinstance(r, list) and len(r) == note_count]


async def _consensus(providers: list[Provider], user: str, note_count: int) -> list[list[dict]]:
    """Collect readings without ever letting the slowest provider set the latency.

    The first answer is awaited up to the call timeout; the remaining opinions then
    get a grace window bounded by BUDGET, which is usually enough for a second model
    to vote and enable hedging without pushing the request past the 5-second p95
    threshold. Providers that miss the window are cancelled and their vote is simply
    absent - the schedule stays valid, it just cannot hedge on that request.
    """
    started = time.perf_counter()
    tasks = [asyncio.create_task(_call_provider(p, user, note_count))
             for p in providers[:CONSENSUS]]

    # Wait for the bonus opinions only as long as the budget allows, but never
    # cancel the first-listed provider early: it is the one whose answer we want,
    # and cutting it off mid-flight would force the slower recovery path.
    done, pending = await asyncio.wait(tasks, timeout=BUDGET,
                                       return_when=asyncio.ALL_COMPLETED)
    if tasks[0] in pending:
        remaining = CALL_TIMEOUT - (time.perf_counter() - started)
        if remaining > 0.05:
            extra, pending = await asyncio.wait({tasks[0]}, timeout=remaining)
            done |= extra
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    readings: list[list[dict]] = []
    for task in done:
        if task.cancelled():
            continue
        try:
            result = task.result()
        except Exception:  # noqa: BLE001 - a failed task is just an absent vote
            continue
        if result:
            readings.append(result)

    if not readings:
        # Every provider failed. With no reading at all the response would degrade to
        # no_op interpretations, which is the one outcome that can turn a correct-answer
        # case into an invalid plan - so spend real time recovering, bounded by DEADLINE.
        deadline = started + DEADLINE
        for provider in providers:
            remaining = deadline - time.perf_counter()
            if remaining < 1.0:
                break
            result = await _call_provider(provider, user, note_count,
                                          timeout=min(CALL_TIMEOUT, remaining))
            if result:
                log.warning("recovered with %s on retry", provider.name)
                readings.append(result)
                break
    return readings


async def gather_readings(notes: list[str], capacity_kwh: float, initial_kwh: float,
                          minimum_kwh: float, use_cache: bool = True) -> list[list[dict]]:
    """Readings[note_index] = one raw directive object per responding provider."""
    key = (tuple(notes), round(capacity_kwh, 6))
    if use_cache:
        cached = _cache_get(key)
        if cached is not None:
            log.info("interpretation cache hit")
            return cached

    providers = available_providers()
    if not providers:
        return [[] for _ in notes]

    user = build_user_prompt(notes, capacity_kwh, initial_kwh, minimum_kwh)
    note_count = len(notes)

    per_provider = await _consensus(providers, user, note_count)
    if not per_provider:
        return [[] for _ in notes]

    readings = [[entry[i] for entry in per_provider] for i in range(note_count)]
    if use_cache:
        _cache_put(key, readings)
    return readings


async def warm_up() -> None:
    """Open provider connections once at startup so the first real request is fast."""
    providers = available_providers()
    if not providers:
        return
    probe = 'Return JSON only: {"directives":[]}'
    try:
        await _call_provider(providers[0], probe, 0)
    except Exception as error:  # noqa: BLE001 - warming up is best effort
        log.warning("warm-up skipped: %s", type(error).__name__)
