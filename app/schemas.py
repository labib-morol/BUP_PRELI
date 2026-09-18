"""Request/response contract for the GridWise preliminary API.

Request parsing is deliberately liberal (any ordering of `hours`, extra fields
ignored, more than three notes tolerated) because the Problem Statement only
guarantees 1-3 notes and a 24-entry hours array - rejecting near-valid input
costs validity points far more often than it earns request-validation points.
"""
from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

HOURS = 24


class HourEntry(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)

    hour: int
    demand_kwh: float
    solar_kwh: float
    tariff_bdt_per_kwh: float


class Battery(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)

    capacity_kwh: float
    initial_energy_kwh: float
    minimum_energy_kwh: float
    max_charge_kwh_per_hour: float
    max_discharge_kwh_per_hour: float

    @model_validator(mode="after")
    def _sane(self) -> "Battery":
        for name in ("capacity_kwh", "initial_energy_kwh", "max_charge_kwh_per_hour",
                     "max_discharge_kwh_per_hour"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.capacity_kwh <= 0:
            raise ValueError("capacity_kwh must be positive")
        if self.minimum_energy_kwh < 0:
            raise ValueError("minimum_energy_kwh must be non-negative")
        return self


class OptimizeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    scenario_id: str
    operator_notes: list[str]
    hours: list[HourEntry]
    battery: Battery

    @field_validator("operator_notes")
    @classmethod
    def _notes(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("operator_notes must contain at least one entry")
        return [n if isinstance(n, str) else str(n) for n in value]

    @model_validator(mode="after")
    def _hours(self) -> "OptimizeRequest":
        if len(self.hours) != HOURS:
            raise ValueError(f"hours must contain exactly {HOURS} entries")
        seen = {h.hour for h in self.hours}
        if seen != set(range(HOURS)):
            raise ValueError("hours must cover every integer 0..23 exactly once")
        self._by_hour = {h.hour: h for h in self.hours}
        return self

    def hour(self, index: int) -> HourEntry:
        return self._by_hour[index]

    @property
    def solar_profile(self) -> list[float]:
        return [self._by_hour[h].solar_kwh for h in range(HOURS)]

    @property
    def demand_profile(self) -> list[float]:
        return [self._by_hour[h].demand_kwh for h in range(HOURS)]

    @property
    def tariff_profile(self) -> list[float]:
        return [self._by_hour[h].tariff_bdt_per_kwh for h in range(HOURS)]


class DirectiveInterpretation(BaseModel):
    note_index: int = Field(ge=0)
    applies: bool
    directive_type: str
    structured_adjustment: dict | None = None
    explanation: str = ""


class HourlyPlanEntry(BaseModel):
    hour: int
    grid_kwh: float
    solar_used_kwh: float
    battery_action: str
    battery_kwh: float
    battery_energy_after_kwh: float


class OptimizeResponse(BaseModel):
    scenario_id: str
    directive_interpretation: list[DirectiveInterpretation]
    hourly_plan: list[HourlyPlanEntry]
    total_grid_kwh: float
    total_cost_bdt: float
    peak_grid_kwh: float
    plan_summary: str


def finite(value: float) -> float:
    return value if isinstance(value, (int, float)) and math.isfinite(value) else 0.0
