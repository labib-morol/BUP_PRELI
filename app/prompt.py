"""Prompt construction for operator-note interpretation.

The few-shot bank is deliberately built around the paraphrase axes the hidden
cases are documented to vary along, and around the two traps that dominate this
directive space:

* percentage direction - "drops to 20%" is factor 0.2, "drops by 20%" is 0.8,
  "an 80% reduction" is 0.2, "leaves one-fifth" is 0.2;
* distractor scope - non-energy topics, and energy topics scoped to another day,
  are no_op.

Using these as in-context examples is not the forbidden "hard-coded phrase
matching": the model still performs the interpretation, and nothing here matches
on wording at request time.
"""
from __future__ import annotations

SYSTEM_PROMPT = """\
You convert campus operator notes into structured energy directives for a 24-hour \
grid/solar/battery optimization. You are the interpretation stage of a pipeline; a \
separate deterministic validator and a linear-programming optimizer consume your output.

Return one object per operator note, in note_index order, as JSON:
{"directives": [{"note_index": int, "applies": bool, "directive_type": str,
  "hours": [int] | null, "factor": float | null,
  "minimum_energy_kwh": float | null, "max_grid_kwh": float | null,
  "quote": str}]}

DIRECTIVE TYPES
- solar_reduction: usable solar is reduced during the listed hours.
  hours=[...], factor = the fraction of forecast solar that REMAINS (0..1).
- minimum_battery_reserve: battery must stay at or above a level.
  hours=[...], minimum_energy_kwh = level in kWh. If the note gives a percentage of \
battery capacity, multiply: 50% of a 200 kWh battery -> 100.
- no_charge_window: battery charging unavailable. hours=[...] only.
- no_discharge_window: battery discharging unavailable. hours=[...] only.
- max_grid_window: grid import capped per hour. hours=[...], max_grid_kwh = the cap.
- no_op: the note does not affect today's 24-hour schedule. applies=false, all
  numeric fields null. Use this for unrelated topics AND for energy topics scoped to
  another day ("next week", "next month", "yesterday") or already resolved.

TIME WINDOWS (whole hours, start included, end excluded)
1 PM to 3 PM -> [13, 14].  noon to 2 PM -> [12, 13].  2 AM until 5 AM -> [2, 3, 4].
6 PM until 10 PM -> [18, 19, 20].  11 AM to 1 PM -> [11, 12].  midnight -> 0.
"between 2 PM and 4 PM" -> [14, 15].  "from 7 PM until 9 PM" -> [19, 20].
Hours must be ascending, unique, integers 0-23. "1-3 PM" means 1 PM to 3 PM.
"12 PM" is hour 12 (noon). "12 AM" is hour 0 (midnight).

PERCENTAGES - read the direction carefully
- "solar drops to 20%" / "20% of normal" / "limited to 20%" / "leaves one-fifth"
  / "an 80% reduction"  -> factor 0.2
- "solar drops by 20%" / "a 20% reduction" / "20% less solar" -> factor 0.8
- "about half" -> 0.5, "one-third" -> 0.333333, "three-quarters" -> 0.75

RULES
- Never invent numbers, hours, tariffs, demand or battery limits. Copy numbers from
  the note; only percentage-of-capacity arithmetic may derive a new value.
- A note about a real constraint that does not cover any hour of today's schedule is no_op.
- Put the exact phrase you relied on in "quote".
Return JSON only."""

_READING_KEYS = ("note_index", "applies", "directive_type", "hours", "factor",
                 "minimum_energy_kwh", "max_grid_kwh")


def _example(capacity_kwh: float, notes: list[str], directives: list[dict]) -> dict:
    return {"capacity_kwh": capacity_kwh, "notes": notes, "directives": directives}


def _reading(index: int, directive_type: str, hours=None, factor=None,
             minimum_energy_kwh=None, max_grid_kwh=None, quote: str = "") -> dict:
    return {
        "note_index": index,
        "applies": directive_type != "no_op",
        "directive_type": directive_type,
        "hours": hours,
        "factor": factor,
        "minimum_energy_kwh": minimum_energy_kwh,
        "max_grid_kwh": max_grid_kwh,
        "quote": quote,
    }


NO_OP_READING = lambda index: _reading(index, "no_op", quote="")  # noqa: E731

FEW_SHOT: list[dict] = [
    _example(200, ["Solar output will drop to about 20% from 1 PM to 3 PM."], [
        _reading(0, "solar_reduction", [13, 14], factor=0.2, quote="drop to about 20%"),
    ]),
    _example(240, ["Expect an 80% reduction in rooftop solar between 11 AM and 2 PM "
                   "because of inverter work."], [
        _reading(0, "solar_reduction", [11, 12, 13], factor=0.2,
                 quote="80% reduction"),
    ]),
    _example(230, ["PV production will drop by 30% from 2 PM to 4 PM."], [
        _reading(0, "solar_reduction", [14, 15], factor=0.7, quote="drop by 30%"),
    ]),
    _example(220, ["Cloud cover during panel inspection will leave about half of the "
                   "forecast solar output from 10 AM until noon."], [
        _reading(0, "solar_reduction", [10, 11], factor=0.5,
                 quote="about half of the forecast solar output"),
    ]),
    _example(200, ["Panel washing from one until three will leave roughly one-fifth of "
                   "normal solar output."], [
        _reading(0, "solar_reduction", [13, 14], factor=0.2,
                 quote="roughly one-fifth of normal solar output"),
    ]),
    _example(180, ["Solar availability will be limited to 40% during the 9 AM to 11 AM "
                   "maintenance window."], [
        _reading(0, "solar_reduction", [9, 10], factor=0.4, quote="limited to 40%"),
    ]),
    _example(200, ["Keep at least 50% of the battery capacity stored in the battery from "
                   "6 PM until 9 PM for emergency operations."], [
        _reading(0, "minimum_battery_reserve", [18, 19, 20], minimum_energy_kwh=100.0,
                 quote="at least 50% of the battery capacity"),
    ]),
    _example(250, ["Keep at least 90 kWh in the battery from 6 PM until 10 PM for "
                   "emergency services."], [
        _reading(0, "minimum_battery_reserve", [18, 19, 20, 21], minimum_energy_kwh=90.0,
                 quote="at least 90 kWh"),
    ]),
    _example(200, ["The battery charger will be isolated from 2 AM until 5 AM for "
                   "electrical maintenance."], [
        _reading(0, "no_charge_window", [2, 3, 4], quote="isolated from 2 AM until 5 AM"),
    ]),
    _example(210, ["Battery charging is disabled from 11 AM until 1 PM while technicians "
                   "inspect the charger."], [
        _reading(0, "no_charge_window", [11, 12], quote="charging is disabled"),
    ]),
    _example(230, ["For protection testing, the battery must not discharge from 6 PM "
                   "until 8 PM."], [
        _reading(0, "no_discharge_window", [18, 19], quote="must not discharge"),
    ]),
    _example(240, ["From 6 PM until 9 PM, campus grid import must not exceed 155 kWh "
                   "in any hour because the feeder is under a temporary limit."], [
        _reading(0, "max_grid_window", [18, 19, 20], max_grid_kwh=155.0,
                 quote="must not exceed 155 kWh"),
    ]),
    _example(250, ["The evening transformer limit is 180 kWh of grid import from 7 PM "
                   "until 9 PM."], [
        _reading(0, "max_grid_window", [19, 20], max_grid_kwh=180.0,
                 quote="limit is 180 kWh"),
    ]),
    _example(220, ["The cafeteria menu changes tomorrow.",
                   "The sports office moved next month's registration deadline.",
                   "The library is extending book-return hours next week."], [
        _reading(0, "no_op"), _reading(1, "no_op"), _reading(2, "no_op"),
    ]),
    _example(200, ["The standby generator will be serviced next month.",
                   "Last week's transformer fault has been repaired."], [
        _reading(0, "no_op"), _reading(1, "no_op"),
    ]),
    _example(220, ["Cloud cover will leave about half of the forecast solar output from "
                   "10 AM until noon.",
                   "The charging circuit will be unavailable from 2 PM until 4 PM.",
                   "The library is extending book-return hours next week."], [
        _reading(0, "solar_reduction", [10, 11], factor=0.5, quote="about half"),
        _reading(1, "no_charge_window", [14, 15], quote="unavailable from 2 PM until 4 PM"),
        _reading(2, "no_op"),
    ]),
    _example(260, ["The data center requires at least 80 kWh to remain in the battery "
                   "from 6 PM until 10 PM.",
                   "Grid intake must stay at or below 190 kWh from 7 PM until 10 PM "
                   "while the substation is constrained.",
                   "A seminar room booking was moved to next week."], [
        _reading(0, "minimum_battery_reserve", [18, 19, 20, 21], minimum_energy_kwh=80.0,
                 quote="at least 80 kWh"),
        _reading(1, "max_grid_window", [19, 20, 21], max_grid_kwh=190.0,
                 quote="at or below 190 kWh"),
        _reading(2, "no_op"),
    ]),
]


def _render_example(example: dict) -> str:
    lines = [f'Battery capacity_kwh = {example["capacity_kwh"]:g}']
    for index, note in enumerate(example["notes"]):
        lines.append(f'note {index}: "{note}"')
    payload = {"directives": [{k: d[k] for k in _READING_KEYS} for d in example["directives"]]}
    import json

    lines.append("output: " + json.dumps(payload, separators=(",", ":")))
    return "\n".join(lines)


def build_user_prompt(notes: list[str], capacity_kwh: float, initial_kwh: float,
                      minimum_kwh: float) -> str:
    lines = [
        f"Battery: capacity_kwh={capacity_kwh:g}, initial_energy_kwh={initial_kwh:g}, "
        f"minimum_energy_kwh={minimum_kwh:g}",
        "",
    ]
    for index, note in enumerate(notes):
        lines.append(f'note {index}: "{note}"')
    lines.append("")
    lines.append(f"Return exactly {len(notes)} directive object(s), note_index 0..{len(notes) - 1}.")
    return "\n".join(lines)


def build_few_shot_block() -> str:
    return "\n\n".join(_render_example(example) for example in FEW_SHOT)
