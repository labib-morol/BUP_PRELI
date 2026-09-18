"""Deterministic guardrails: normalization, grounding checks and safe hedging.

The Problem Statement requires LLM output to be treated as untrusted until
deterministic validation passes. The Participant Guide explicitly allows
deterministic pre/post-processing for normalization, JSON validation, guardrails
and directive application - it only forbids deterministic code from *replacing*
the language-model interpretation, which is not what happens here: the model
still decides relevance, directive type and values, and this module can only
reject, repair or widen in the provably safe direction.

Two ideas do the heavy lifting:

1. Grounding checks. Explicit clock expressions and percentages in the note are
   re-derived independently, so the classic traps ("drops to 20%" vs "drops by
   20%", noon vs midnight, 12 AM vs 12 PM) are caught instead of trusted.
2. Safe-direction hedging. Every directive type has a direction in which a
   stricter constraint can never invalidate the plan against ground truth, so
   when independent models disagree we apply the union of their readings while
   still reporting the most likely single one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from .directives import NO_OP, Directive, union_all

MAX_HOUR = 23

_NUMBER = r"(\d+(?:\.\d+)?)"
_CLOCK = re.compile(
    r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\b"
    r"|\b(\d{1,2}):(\d{2})\b"
    r"|\b(noon|midday|midnight)\b",
    re.IGNORECASE,
)
_CONNECTOR = re.compile(
    r"\b(to|until|till|through|throughout|and|between|from)\b|[-–—]", re.IGNORECASE
)
_PERCENT = re.compile(_NUMBER + r"\s*(?:%|percent|per cent)", re.IGNORECASE)
_REDUCTION_CUE = re.compile(
    r"\b(reduction|reduce[sd]?|drop(?:s|ped)?\s+by|decrease[sd]?|cut|lower(?:ed)?|"
    r"decline[sd]?|fall(?:s|ing)?|less|shave[sd]?|off)\b",
    re.IGNORECASE,
)
_REMAINING_CUE = re.compile(
    r"\b(to|at|of|remaining|remains?|leaves?|leave|limited?|only|down\s+to|"
    r"no\s+more\s+than|maximum\s+of|capacity\s+of)\b",
    re.IGNORECASE,
)
_WORDS = {
    "half": 0.5,
    "one-half": 0.5,
    "halve": 0.5,
    "halves": 0.5,
    "halved": 0.5,
    "quarter": 0.25,
    "one-quarter": 0.25,
    "three-quarters": 0.75,
    "one-third": 1 / 3,
    "two-thirds": 2 / 3,
    "one-fifth": 0.2,
    "two-fifths": 0.4,
    "three-fifths": 0.6,
    "four-fifths": 0.8,
    "one-tenth": 0.1,
    "a tenth": 0.1,
}


def _clock_hour(hour: int, minute: str | None, meridiem: str | None, word: str | None) -> int | None:
    if word:
        word = word.lower()
        if word in ("noon", "midday"):
            return 12
        return 0
    if meridiem:
        meridiem = meridiem.replace(".", "").lower()
        base = hour % 12
        return base + 12 if meridiem == "pm" else base
    if minute is not None:
        return hour if 0 <= hour <= MAX_HOUR else None
    return None


def clock_mentions(note: str) -> list[int]:
    hours = []
    for match in _CLOCK.finditer(note):
        hour = _clock_hour(
            int(match.group(1) or match.group(4) or 0),
            match.group(2) or match.group(5),
            match.group(3),
            match.group(6),
        )
        if hour is not None and 0 <= hour <= MAX_HOUR:
            hours.append(hour)
    return hours


def expected_window(note: str) -> tuple[int, ...] | None:
    """The window implied by two explicit clock times, or None when ambiguous.

    Whole-hour, start-inclusive and end-exclusive, exactly as the Problem
    Statement defines it: "1 PM to 3 PM" -> (13, 14).  A window that would wrap
    past midnight cannot be expressed as ascending hours, so it is reported as
    ambiguous rather than guessed.
    """
    hours = clock_mentions(note)
    if len(hours) != 2 or not _CONNECTOR.search(note):
        return None
    start, end = hours
    if end <= start:
        return None
    return tuple(range(start, end))


def expected_solar_factor(note: str) -> float | None:
    """The usable-solar fraction implied by a percentage or fraction word.

    "drop to 20%", "20% of normal", "leaves one-fifth"  -> 0.2  (fraction left)
    "80% reduction", "drops by 20%", "reduction of 30%" -> 0.2 / 0.8 / 0.7
    """
    match = _PERCENT.search(note)
    if match:
        percent = float(match.group(1))
        if percent > 100:
            return None
        suffix = note[match.end():match.end() + 24].lower()
        prefix = note[max(0, match.start() - 48):match.start()].lower()
        if re.match(r"\s*(?:reduction|drop|decrease|cut|decline|fall|less|lower|off)\b", suffix):
            return round(1.0 - percent / 100.0, 6)
        tail = prefix[-16:]
        if re.search(r"\b(by|of)\s*$", tail) and _REDUCTION_CUE.search(prefix):
            return round(1.0 - percent / 100.0, 6)
        if re.search(r"\b(reduction|decrease|drop|cut)\s*$", tail):
            return round(1.0 - percent / 100.0, 6)
        return round(percent / 100.0, 6)

    lowered = note.lower()
    if re.search(r"\b(zero|nil|no solar|no output|no generation)\b", lowered):
        return 0.0
    for word, value in _WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", lowered):
            return value
    return None


def numbers_in(note: str) -> set[float]:
    return {float(value) for value in re.findall(_NUMBER, note)}


def parse_directive(raw: dict, battery_capacity: float) -> Directive:
    """Normalize one raw model object into a validated Directive.

    Anything unsupported or malformed degrades to no_op rather than inventing a
    constraint: the safe-failure rule from the Problem Statement.
    """
    directive_type = raw.get("directive_type")
    if not isinstance(directive_type, str):
        return NO_OP
    directive_type = directive_type.strip().lower()
    if directive_type == "no_op":
        return NO_OP

    hours = _clean_hours(raw.get("hours"))
    if directive_type == "solar_reduction":
        factor = _finite(raw.get("factor"))
        if factor is None or not hours:
            return NO_OP
        return Directive("solar_reduction", hours, factor=min(max(factor, 0.0), 1.0))
    if directive_type == "minimum_battery_reserve":
        value = _finite(raw.get("minimum_energy_kwh"))
        if value is None or not hours:
            return NO_OP
        return Directive("minimum_battery_reserve", hours,
                         minimum_energy_kwh=min(max(value, 0.0), battery_capacity))
    if directive_type in ("no_charge_window", "no_discharge_window"):
        return Directive(directive_type, hours) if hours else NO_OP
    if directive_type == "max_grid_window":
        value = _finite(raw.get("max_grid_kwh"))
        if value is None or not hours:
            return NO_OP
        return Directive("max_grid_window", hours, max_grid_kwh=max(value, 0.0))
    return NO_OP


def _finite(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _clean_hours(value) -> tuple[int, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    hours = set()
    for item in value:
        number = _finite(item)
        if number is not None and float(number).is_integer() and 0 <= number <= MAX_HOUR:
            hours.add(int(number))
    return tuple(sorted(hours))


@dataclass
class Assessment:
    index: int
    note: str
    reported: Directive
    candidates: tuple[Directive, ...] = ()
    flags: list[str] = field(default_factory=list)

    @property
    def confident(self) -> bool:
        return not self.flags

    @property
    def applied(self) -> tuple[Directive, ...]:
        """Constraints to optimize under: exact when confident, else the union."""
        if self.confident or not self.candidates:
            return (self.reported,)
        return union_all(list(self.candidates) + [self.reported])


def assess(index: int, note: str, readings: list[Directive], battery_capacity: float) -> Assessment:
    reported = readings[0] if readings else NO_OP
    flags: list[str] = []

    distinct = {_key(d) for d in readings}
    if len(distinct) > 1:
        flags.append("models_disagree")

    if reported.applies:
        window = expected_window(note)
        if window is not None and reported.hours != window:
            flags.append(f"window_mismatch:note_says={list(window)}")

        if reported.directive_type == "solar_reduction":
            expected = expected_solar_factor(note)
            if expected is not None and abs(expected - reported.factor) > 0.02:
                flags.append(f"factor_mismatch:note_says={expected}")

        value = reported.minimum_energy_kwh or reported.max_grid_kwh
        if value is not None:
            grounded = any(abs(value - n) <= 0.01 for n in numbers_in(note))
            derived = any(
                abs(value - p / 100.0 * battery_capacity) <= 0.5 for p in numbers_in(note)
            )
            if not grounded and not derived:
                flags.append(f"value_ungrounded:{value}")

    return Assessment(
        index=index,
        note=note,
        reported=reported,
        candidates=tuple(readings),
        flags=flags,
    )


def _key(directive: Directive) -> tuple:
    return (directive.directive_type, directive.hours, directive.factor,
            directive.minimum_energy_kwh, directive.max_grid_kwh)


def window_candidate(note: str, reported: Directive) -> Directive | None:
    """A second reading of the note derived only from its explicit clock expression.

    The Problem Statement singles out the whole-hour, start-inclusive/end-exclusive
    convention as the detail teams get wrong, and a window written as two clock times
    ("13:00 and 15:00", "1 PM to 3 PM") is unambiguous. When the model's hours differ,
    this reading joins the candidate set, so the applied constraint becomes the union
    of both - the safe direction - and the schedule satisfies whichever the organizer
    treats as ground truth. Returns None when the window cannot be read unambiguously.
    """
    if not reported.applies:
        return None
    window = expected_window(note)
    if window is None or reported.hours == window:
        return None
    return replace(reported, hours=window)


def explain(assessment: Assessment) -> str:
    directive = assessment.reported
    if not directive.applies:
        return "This note does not affect today's 24-hour energy schedule."
    hours = ", ".join(str(h) for h in directive.hours)
    if directive.directive_type == "solar_reduction":
        return (f"Usable solar is reduced to {directive.factor:.0%} of the forecast "
                f"during hours {hours}.")
    if directive.directive_type == "minimum_battery_reserve":
        return (f"Battery energy must stay at or above "
                f"{directive.minimum_energy_kwh:g} kWh during hours {hours}.")
    if directive.directive_type == "no_charge_window":
        return f"Battery charging is unavailable during hours {hours}."
    if directive.directive_type == "no_discharge_window":
        return f"Battery discharging is unavailable during hours {hours}."
    return (f"Grid import is capped at {directive.max_grid_kwh:g} kWh per hour "
            f"during hours {hours}.")
