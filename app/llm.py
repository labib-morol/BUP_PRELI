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

from .prompt import SYSTEM_PROMPT, build_few_shot_block, build_user_prompt

log = logging.getLogger("gridwise.llm")

CALL_TIMEOUT = float(os.getenv("GRIDWISE_LLM_TIMEOUT", "8"))
CONSENSUS = max(1, int(os.getenv("GRIDWISE_CONSENSUS", "2")))
MAX_CONCURRENT = max(1, int(os.getenv("GRIDWISE_LLM_CONCURRENCY", "4")))
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
            ),
        )
        return response.text or ""

    return Provider(f"gemini:{model}", model, call)


def _provider_openai_compatible(name: str, key: str, model: str, base_url: str | None) -> Provider:
    async def call(system: str, user: str) -> str:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=key, base_url=base_url, timeout=CALL_TIMEOUT)
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

    A second model from the same key counts as an independent opinion: comparing
    readings across model families is what produces the disagreement signal the
    guardrails use to decide whether hedging is worth its cost. Set
    GRIDWISE_GEMINI_MODEL_2="" to run a single provider.
    """
    providers: list[Provider] = []
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if gemini_key:
        providers.append(_provider_gemini(
            gemini_key, os.getenv("GRIDWISE_GEMINI_MODEL", "gemini-2.5-flash")))
        second = os.getenv("GRIDWISE_GEMINI_MODEL_2", "gemini-2.5-flash-lite")
        if second:
            providers.append(_provider_gemini(gemini_key, second))
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        providers.append(_provider_openai_compatible(
            "groq", groq_key, os.getenv("GRIDWISE_GROQ_MODEL", "llama-3.3-70b-versatile"),
            "https://api.groq.com/openai/v1"))
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


async def _call_provider(provider: Provider, user: str, note_count: int) -> list[dict] | None:
    system = f"{SYSTEM_PROMPT}\n\nEXAMPLES\n{build_few_shot_block()}"
    async with _semaphore:
        for attempt in (1, 2):
            started = time.perf_counter()
            try:
                text = await asyncio.wait_for(provider.call(system, user), timeout=CALL_TIMEOUT)
            except Exception as error:  # noqa: BLE001 - any provider failure is non-fatal
                log.warning("provider %s attempt %d failed: %s: %s",
                            provider.name, attempt, type(error).__name__, error)
                continue
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
    chosen = providers[:CONSENSUS]
    results = await asyncio.gather(
        *(_call_provider(provider, user, note_count) for provider in chosen),
        return_exceptions=True,
    )

    per_provider: list[list[dict]] = []
    for result in results:
        if isinstance(result, list) and len(result) == note_count:
            per_provider.append(result)
    if not per_provider:
        return [[] for _ in notes]

    readings = [[entry[i] for entry in per_provider] for i in range(note_count)]
    if use_cache:
        _cache_put(key, readings)
    return readings
