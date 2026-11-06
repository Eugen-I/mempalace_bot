"""Pydantic contracts for Garmin imports, profiles, plans, and adaptation.

These models are deliberately transport-neutral: they can be serialized to
JSON, encrypted into ``garmin_profile.profile_blob``, or sent to Ollama after
the caller has removed unnecessary personal data.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Goal = Literal[
    "fat_loss",
    "strength",
    "health",
    "cycling",
    "endurance",
    "mixed",
]
SessionType = Literal["aerobic", "strength", "mobility", "rest", "test", "event"]
Readiness = Literal["green", "amber", "red", "unknown"]
Recommendation = Literal["keep", "reduce", "deload", "progress", "rest", "medical"]


class MedicationEntry(BaseModel):
    """User-entered medication; class/precautions are filled by the KB layer."""

    model_config = ConfigDict(extra="forbid")

    name: str
    dose: str | None = None
    frequency: str | None = None
    timing: str | None = None
    reason: str | None = None
    prescriber: str | None = None
    class_name: str | None = None
    precautions: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)


class AvailabilitySlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day_of_week: int = Field(ge=0, le=6)  # Monday=0
    minutes: int = Field(ge=10, le=300)
    activity: str | None = None


class UserProfile(BaseModel):
    """Stable context used by the deterministic plan engine and the LLM."""

    model_config = ConfigDict(extra="forbid")

    goals: list[Goal] = Field(
        default_factory=lambda: ["fat_loss", "strength", "cycling", "health"]
    )
    primary_goal: Goal = "fat_loss"
    secondary_goals: list[Goal] = Field(
        default_factory=lambda: ["strength", "cycling", "health"]
    )
    horizon_weeks: int = Field(default=6, ge=1, le=52)
    event_date: str | None = None
    experience: Literal[
        "beginner", "returning", "regular", "advanced"
    ] = "returning"
    availability: list[AvailabilitySlot] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    injuries: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    medications: list[MedicationEntry] = Field(default_factory=list)
    supplements: list[str] = Field(default_factory=list)
    sleep_target_h: float = Field(default=7.5, ge=4.0, le=12.0)
    stress_level: Literal["low", "medium", "high"] = "medium"
    doctor_clearance: Literal["yes", "no", "unknown"] = "unknown"
    notes: str | None = None
    version: int = Field(default=1, ge=1)

    @property
    def completeness(self) -> str:
        """Coarse profile completeness used by the data-sufficiency gate."""
        if not self.availability and not self.equipment:
            return "minimal"
        if not self.availability or not self.experience:
            return "partial"
        return "complete"


class SessionStructure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    warmup: str | None = None
    main: str | None = None
    cooldown: str | None = None


class PlanSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str
    type: SessionType
    title: str
    duration_min: int | None = Field(default=None, ge=0, le=300)
    intensity: str | None = None
    structure: SessionStructure = Field(default_factory=SessionStructure)
    purpose: str | None = None
    alternatives: list[str] = Field(default_factory=list)
    safety: str | None = None
    citations: list[str] = Field(default_factory=list)


class PlanWeek(BaseModel):
    model_config = ConfigDict(extra="forbid")

    week: int = Field(ge=1)
    focus: Literal["base", "build", "deload", "taper", "test", "consolidation"]
    target_load: float | None = Field(default=None, ge=0)
    sessions: list[PlanSession] = Field(default_factory=list)
    adaptation_rules: list[str] = Field(default_factory=list)


class SafetyFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: Literal["info", "warning", "critical"]
    text: str


class TrainingPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str
    goal: Goal
    horizon_weeks: int = Field(default=6, ge=1, le=52)
    confidence: Literal["low", "medium", "high"] = "medium"
    assumptions: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    safety_flags: list[SafetyFlag] = Field(default_factory=list)
    weeks: list[PlanWeek] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    disclaimer: str = "Не является медицинской рекомендацией."


class DeltaMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    metric: str
    from_value: float | None = Field(default=None, alias="from")
    to_value: float | None = Field(default=None, alias="to")
    delta: float | None = None
    important: bool = False


class DeltaReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    compared_from: str | None = None
    compared_to: str | None = None
    new_days: int = 0
    changed_metrics: list[DeltaMetric] = Field(default_factory=list)
    likely_context: list[str] = Field(default_factory=list)
    recommendation_window: str = "next_3_days"
    recommendation: Recommendation = "keep"
    confidence: Literal["low", "medium", "high"] = "medium"
    needs_confirm: bool = True


class Checkin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str
    kind: Literal["morning", "post", "manual"] = "morning"
    sleep_h: float | None = Field(default=None, ge=0, le=24)
    sleep_quality: int | None = Field(default=None, ge=1, le=5)
    hrv: int | None = Field(default=None, ge=0, le=500)
    rhr: int | None = Field(default=None, ge=0, le=250)
    soreness: int | None = Field(default=None, ge=0, le=10)
    pain_score: int | None = Field(default=None, ge=0, le=10)
    pain_location: str | None = None
    mood: int | None = Field(default=None, ge=1, le=5)
    stress: int | None = Field(default=None, ge=1, le=5)
    adherence: bool | None = None
    notes: str | None = None


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str
    kind: Literal[
        "illness",
        "alcohol",
        "travel",
        "stress",
        "injury",
        "med_change",
        "heat",
        "altitude",
        "menstrual",
        "hard_session",
        "other",
    ]
    title: str
    notes: str | None = None
    severity: Literal["info", "warning", "critical"] = "info"


class AdaptationLogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str
    trigger: Literal["import", "checkin", "weekly", "manual"]
    compared_from: str | None = None
    compared_to: str | None = None
    delta: DeltaReport
    recommendation: Recommendation
    confidence: Literal["low", "medium", "high"] = "medium"
    needs_confirm: bool = True
    applied: bool = False
