"""Deterministic 6-week training-plan skeleton and hard validator.

All dates, durations, intensity and progression are computed here.  A local
LLM may only fill names, structure and rationale; it cannot change these
numbers.  The validator enforces the safety rules from the integration plan.
"""

from __future__ import annotations

import html
import uuid
from datetime import date, timedelta
from typing import Any, Iterable

from .evidence import CITATION_IDS
from .medications import MedicationLayer, build_layer
from .models import (
    Event,
    PlanSession,
    PlanWeek,
    SafetyFlag,
    SessionStructure,
    TrainingPlan,
    UserProfile,
)
from .status import DataStatus

WEEK_FOCUS = ("base", "build", "build", "deload", "build", "consolidation")
VOLUME_FACTOR = (1.0, 1.05, 1.11, 0.65, 1.16, 0.88)
DAY_NAMES = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")

FOCUS_LABELS = {
    "base": "базовая",
    "build": "нагрузочная",
    "deload": "разгрузочная",
    "taper": "подводящая",
    "test": "тестовая",
    "consolidation": "консолидация",
}

CONFIDENCE_LABELS = {
    "low": "базовая",
    "medium": "умеренная",
    "high": "высокая",
}

# Default week: three full-body strength sessions, two Zone-2 rides,
# one mobility day and one full rest day.
DEFAULT_LAYOUT = (
    "strength",
    "cycling",
    "strength",
    "mobility",
    "cycling",
    "strength",
    "rest",
)

DISCLAIMER = (
    "Это не медицинская рекомендация и не назначение. При красных флагах "
    "остановитесь и обратитесь к врачу."
)

BASE_CITATIONS = ("E1", "E2", "E3", "E4", "E5")


def _layout(profile: UserProfile) -> tuple[str, ...]:
    primary = profile.primary_goal
    if primary in {"cycling", "endurance"}:
        return (
            "strength",
            "cycling",
            "cycling",
            "mobility",
            "strength",
            "cycling",
            "rest",
        )
    if primary == "health":
        return (
            "strength",
            "cycling",
            "mobility",
            "cycling",
            "strength",
            "cycling",
            "rest",
        )
    return DEFAULT_LAYOUT


def _build_weekly_slots(profile: UserProfile) -> list[str]:
    """Return a 7-element tuple/list of session kinds for weekdays 0..6."""
    if not profile.availability:
        return list(_layout(profile))

    avail_map = {slot.day_of_week: slot.minutes for slot in profile.availability}
    sorted_avail = sorted(avail_map.keys())
    n = len(sorted_avail)
    ptype = getattr(profile, "plan_type", "fullbody")

    day_kinds: dict[int, str] = {}
    if ptype == "upper_lower":
        if n == 1:
            day_kinds[sorted_avail[0]] = "fullbody_1"
        elif n == 2:
            day_kinds[sorted_avail[0]] = "upper_1"
            day_kinds[sorted_avail[1]] = "lower_1"
        elif n == 3:
            day_kinds[sorted_avail[0]] = "upper_1"
            day_kinds[sorted_avail[1]] = "lower_1"
            day_kinds[sorted_avail[2]] = "cycling"
        elif n == 4:
            day_kinds[sorted_avail[0]] = "upper_1"
            day_kinds[sorted_avail[1]] = "lower_1"
            day_kinds[sorted_avail[2]] = "upper_2"
            day_kinds[sorted_avail[3]] = "lower_2"
        elif n == 5:
            day_kinds[sorted_avail[0]] = "upper_1"
            day_kinds[sorted_avail[1]] = "lower_1"
            day_kinds[sorted_avail[2]] = "cycling"
            day_kinds[sorted_avail[3]] = "upper_2"
            day_kinds[sorted_avail[4]] = "lower_2"
        else:
            day_kinds[sorted_avail[0]] = "upper_1"
            day_kinds[sorted_avail[1]] = "lower_1"
            day_kinds[sorted_avail[2]] = "cycling"
            day_kinds[sorted_avail[3]] = "upper_2"
            day_kinds[sorted_avail[4]] = "lower_2"
            day_kinds[sorted_avail[5]] = "cycling"

    elif ptype == "ppl":
        if n == 1:
            day_kinds[sorted_avail[0]] = "fullbody_1"
        elif n == 2:
            day_kinds[sorted_avail[0]] = "push"
            day_kinds[sorted_avail[1]] = "pull_legs"
        elif n == 3:
            day_kinds[sorted_avail[0]] = "push"
            day_kinds[sorted_avail[1]] = "pull"
            day_kinds[sorted_avail[2]] = "legs"
        elif n == 4:
            day_kinds[sorted_avail[0]] = "push"
            day_kinds[sorted_avail[1]] = "pull"
            day_kinds[sorted_avail[2]] = "legs"
            day_kinds[sorted_avail[3]] = "cycling"
        elif n == 5:
            day_kinds[sorted_avail[0]] = "push"
            day_kinds[sorted_avail[1]] = "pull"
            day_kinds[sorted_avail[2]] = "legs"
            day_kinds[sorted_avail[3]] = "cycling"
            day_kinds[sorted_avail[4]] = "fullbody_1"
        else:
            day_kinds[sorted_avail[0]] = "push"
            day_kinds[sorted_avail[1]] = "pull"
            day_kinds[sorted_avail[2]] = "legs"
            day_kinds[sorted_avail[3]] = "push"
            day_kinds[sorted_avail[4]] = "pull"
            day_kinds[sorted_avail[5]] = "legs"

    elif ptype == "hybrid":
        if n == 1:
            day_kinds[sorted_avail[0]] = "hybrid_double"
        elif n == 2:
            day_kinds[sorted_avail[0]] = "fullbody_1"
            day_kinds[sorted_avail[1]] = "hybrid_double"
        elif n == 3:
            day_kinds[sorted_avail[0]] = "fullbody_1"
            day_kinds[sorted_avail[1]] = "cycling"
            day_kinds[sorted_avail[2]] = "hybrid_double"
        elif n == 4:
            day_kinds[sorted_avail[0]] = "fullbody_1"
            day_kinds[sorted_avail[1]] = "cycling"
            day_kinds[sorted_avail[2]] = "fullbody_2"
            day_kinds[sorted_avail[3]] = "hybrid_double"
        elif n == 5:
            day_kinds[sorted_avail[0]] = "fullbody_1"
            day_kinds[sorted_avail[1]] = "cycling"
            day_kinds[sorted_avail[2]] = "fullbody_2"
            day_kinds[sorted_avail[3]] = "cycling"
            day_kinds[sorted_avail[4]] = "hybrid_double"
        else:
            day_kinds[sorted_avail[0]] = "fullbody_1"
            day_kinds[sorted_avail[1]] = "cycling"
            day_kinds[sorted_avail[2]] = "fullbody_2"
            day_kinds[sorted_avail[3]] = "cycling"
            day_kinds[sorted_avail[4]] = "hybrid_double"
            day_kinds[sorted_avail[5]] = "cycling"

    elif ptype == "functional":
        if n == 1:
            day_kinds[sorted_avail[0]] = "functional"
        elif n == 2:
            day_kinds[sorted_avail[0]] = "functional"
            day_kinds[sorted_avail[1]] = "cycling"
        elif n == 3:
            day_kinds[sorted_avail[0]] = "functional"
            day_kinds[sorted_avail[1]] = "cycling"
            day_kinds[sorted_avail[2]] = "functional"
        elif n == 4:
            day_kinds[sorted_avail[0]] = "functional"
            day_kinds[sorted_avail[1]] = "cycling"
            day_kinds[sorted_avail[2]] = "functional"
            day_kinds[sorted_avail[3]] = "cycling"
        elif n == 5:
            day_kinds[sorted_avail[0]] = "functional"
            day_kinds[sorted_avail[1]] = "cycling"
            day_kinds[sorted_avail[2]] = "functional"
            day_kinds[sorted_avail[3]] = "cycling"
            day_kinds[sorted_avail[4]] = "functional"
        else:
            day_kinds[sorted_avail[0]] = "functional"
            day_kinds[sorted_avail[1]] = "cycling"
            day_kinds[sorted_avail[2]] = "functional"
            day_kinds[sorted_avail[3]] = "cycling"
            day_kinds[sorted_avail[4]] = "functional"
            day_kinds[sorted_avail[5]] = "cycling"

    else:
        if n == 1:
            day_kinds[sorted_avail[0]] = "fullbody_1"
        elif n == 2:
            day_kinds[sorted_avail[0]] = "fullbody_1"
            day_kinds[sorted_avail[1]] = "fullbody_2"
        elif n == 3:
            day_kinds[sorted_avail[0]] = "fullbody_1"
            day_kinds[sorted_avail[1]] = "cycling"
            day_kinds[sorted_avail[2]] = "fullbody_2"
        elif n == 4:
            day_kinds[sorted_avail[0]] = "fullbody_1"
            day_kinds[sorted_avail[1]] = "cycling"
            day_kinds[sorted_avail[2]] = "fullbody_2"
            day_kinds[sorted_avail[3]] = "cycling"
        elif n == 5:
            day_kinds[sorted_avail[0]] = "fullbody_1"
            day_kinds[sorted_avail[1]] = "cycling"
            day_kinds[sorted_avail[2]] = "fullbody_2"
            day_kinds[sorted_avail[3]] = "cycling"
            day_kinds[sorted_avail[4]] = "fullbody_1"
        else:
            day_kinds[sorted_avail[0]] = "fullbody_1"
            day_kinds[sorted_avail[1]] = "cycling"
            day_kinds[sorted_avail[2]] = "fullbody_2"
            day_kinds[sorted_avail[3]] = "cycling"
            day_kinds[sorted_avail[4]] = "fullbody_1"
            day_kinds[sorted_avail[5]] = "cycling"

    result: list[str] = []
    mobility_placed = False
    for day_i in range(7):
        if day_i in day_kinds:
            result.append(day_kinds[day_i])
        elif day_i == 6:
            result.append("rest")
        elif not mobility_placed and day_i in (2, 3):
            result.append("mobility")
            mobility_placed = True
        else:
            result.append("rest")

    return result


def _minutes_for(profile: UserProfile, weekday: int, default: int) -> int:
    for slot in profile.availability:
        if slot.day_of_week == weekday:
            return max(10, min(slot.minutes, default))
    return default


def _strength_details(kind: str) -> tuple[str, SessionStructure]:
    if kind == "upper_1":
        return (
            "Силовая: Верх тела (А)",
            SessionStructure(
                warmup="5–8 мин: суставная разминка плеч и грудного отдела",
                main="Жим штанги/гантелей лежа, тяга штанги к поясу, жим гантелей, подтягивания",
                cooldown="5 мин: растяжка грудных мышц и широчайших",
            ),
        )
    if kind == "lower_1":
        return (
            "Силовая: Низ тела (А)",
            SessionStructure(
                warmup="5–8 мин: мобильность тазобедренных суставов и голеностопа",
                main="Приседания со штангой, румынская тяга, выпады на месте, подъем на носки",
                cooldown="5 мин: растяжка передней и задней поверхности бедра",
            ),
        )
    if kind == "upper_2":
        return (
            "Силовая: Верх тела (Б)",
            SessionStructure(
                warmup="5–8 мин: разминка ротаторов плеча и лопаток",
                main="Армейский жим стоя, тяга верхнего блока, отжимания на брусьях/полу, разводка",
                cooldown="5 мин: растяжка плечевого пояса и шеи",
            ),
        )
    if kind == "lower_2":
        return (
            "Силовая: Низ тела (Б)",
            SessionStructure(
                warmup="5–8 мин: разминка коленей и активация ягодичных",
                main="Жим ногами, сгибания ног лежа/сидя, ягодичный мостик, гиперэкстензия",
                cooldown="5 мин: мягкая растяжка и дыхание",
            ),
        )
    if kind == "push":
        return (
            "Силовая: Жим (Push)",
            SessionStructure(
                warmup="5–8 мин: суставная разминка плеч и груди",
                main="Жим штанги/гантелей лежа, армейский жим стоя, брусья/отжимания, трицепс",
                cooldown="5 мин: растяжка грудных мышц и дельт",
            ),
        )
    if kind == "pull":
        return (
            "Силовая: Тяга (Pull)",
            SessionStructure(
                warmup="5–8 мин: разминка грудного отдела и плечевого пояса",
                main="Подтягивания/тяга верхнего блока, тяга штанги в наклоне, пулловер, бицепс",
                cooldown="5 мин: растяжка широчайших мышц и предплечий",
            ),
        )
    if kind == "legs":
        return (
            "Силовая: Ноги (Legs)",
            SessionStructure(
                warmup="5–8 мин: мобильность таза и коленных суставов",
                main="Приседания со штангой, румынская тяга, жим ногами, икры в тренажере",
                cooldown="5 мин: растяжка ног и поясницы",
            ),
        )
    if kind == "pull_legs":
        return (
            "Силовая: Тяга и Ноги",
            SessionStructure(
                warmup="5–8 мин: динамическая разминка",
                main="Приседания, румынская тяга, подтягивания, тяга к поясу",
                cooldown="5 мин: растяжка",
            ),
        )
    if kind == "fullbody_2":
        return (
            "Силовая: всё тело (Б)",
            SessionStructure(
                warmup="5–8 мин: суставная разминка, легкое кардио",
                main="Румынская тяга, отжимания на брусьях, подтягивания, выпады; отдых 90 с",
                cooldown="5 мин: спокойная ходьба и растяжка",
            ),
        )
    return (
        "Силовая: всё тело (А)",
        SessionStructure(
            warmup="5–8 мин: суставная разминка, лёгкое кардио",
            main="Присед/жим/тяга + 1–2 вспомогательных; отдых 90–120 с",
            cooldown="5 мин: спокойная ходьба, растяжка",
        ),
    )


def _hybrid_double_session(
    day: date,
    *,
    duration: int,
    medication_note: str | None,
) -> PlanSession:
    return PlanSession(
        date=day.isoformat(),
        type="strength",
        title="Сдвоенная: Вело (Z2) + Зал",
        duration_min=duration,
        intensity="Утро: Z2 (разговорный темп) · Вечер: RPE 6–7, запас 2–3 повт.",
        structure=SessionStructure(
            warmup="Утро: 5 мин вращение педалей; Вечер: суставная разминка",
            main="Утро (30–35 мин): Вело Z2 аэробная база.\n"
                 "Вечер (35–40 мин): Силовая в зале — жим, тяга, приседания (2–3 подхода)",
            cooldown="Вечер: 5 мин спокойная ходьба и мягкая растяжка",
        ),
        purpose="Совмещение аэробной выносливости и силовой гипертрофии в один тренировочный день.",
        alternatives=[
            "Разделить тренировки на два разных дня при утомлении",
            "Оставить только кардио Z2 при недосыпе",
        ],
        safety=medication_note,
        citations=["E2", "E5"],
    )


def _functional_session(
    day: date,
    *,
    duration: int,
    medication_note: str | None,
) -> PlanSession:
    return PlanSession(
        date=day.isoformat(),
        type="aerobic",
        title="Функциональный тренинг / круговая",
        duration_min=duration,
        intensity="RPE 5–6, непрерывный комфортный темп, без закисления",
        structure=SessionStructure(
            warmup="6–8 мин: динамическая разминка, мобильность суставов",
            main="3–4 круга: махи гирей/гантелью, выпады, тяга к поясу, планка; отдых 60 с",
            cooldown="5 мин: растяжка и дыхательные упражнения",
        ),
        purpose="Развитие общей выносливости, координации и функциональной силы.",
        alternatives=["Снизить вес отягощений", "Использовать резиновые петли"],
        safety=medication_note,
        citations=["E1", "E2"],
    )


def _strength_session(
    day: date,
    *,
    duration: int,
    rpe: str,
    medication_note: str | None,
    title: str = "Силовая: всё тело",
    structure: SessionStructure | None = None,
    purpose: str | None = None,
) -> PlanSession:
    default_structure = SessionStructure(
        warmup="5–8 мин: суставная разминка, лёгкое кардио",
        main="Присед/жим/тяга + 1–2 вспомогательных; отдых 90–120 с",
        cooldown="5 мин: спокойная ходьба, растяжка",
    )
    return PlanSession(
        date=day.isoformat(),
        type="strength",
        title=title,
        duration_min=duration,
        intensity=f"RPE {rpe}, 2–3 подхода, 6–12 повторений, не до отказа",
        structure=structure or default_structure,
        purpose=purpose or "Сохранить мышцы и силу при снижении веса.",
        alternatives=["Гантели вместо штанги", "Резинки, если нет зала"],
        safety=medication_note,
        citations=["E2", "E8"],
    )


def _cycling_session(
    day: date,
    *,
    duration: int,
    tempo: bool,
    medication_note: str | None,
) -> PlanSession:
    if tempo:
        intensity = "Z2 + 1 короткий темп 8–10 мин, RPE 6–7"
        title = "Вело: Z2 + короткий темп"
        main = "10 мин Z2, 3 × (3 мин темп / 3 мин легко), остальное Z2"
        citations = ["E3", "E5"]
    else:
        intensity = "Z2, RPE 5–6, разговорный темп"
        title = "Вело: аэробная база"
        main = "Ровный Z2; каденс комфортный, без рывков"
        citations = ["E5", "E6"]
    return PlanSession(
        date=day.isoformat(),
        type="aerobic",
        title=title,
        duration_min=duration,
        intensity=intensity,
        structure=SessionStructure(
            warmup="8–10 мин легко",
            main=main,
            cooldown="5–8 мин легко + дыхание",
        ),
        purpose="Аэробная база и расход энергии без перегрузки.",
        alternatives=["Быстрая ходьба", "Эллипс, если нет велосипеда"],
        safety=medication_note,
        citations=citations,
    )


def _mobility_session(day: date, *, duration: int = 25) -> PlanSession:
    return PlanSession(
        date=day.isoformat(),
        type="mobility",
        title="Мобилити и прогулка",
        duration_min=duration,
        intensity="RPE 2–3",
        structure=SessionStructure(
            warmup="2 мин дыхание",
            main="Мягкая мобилити таза, плеч и спины; прогулка",
            cooldown="2 мин спокойное дыхание",
        ),
        purpose="Восстановление и повседневная активность.",
        citations=["E1"],
    )


def _rest_session(day: date) -> PlanSession:
    return PlanSession(
        date=day.isoformat(),
        type="rest",
        title="Полный отдых",
        duration_min=0,
        intensity="—",
        purpose="Восстановление; сон и обычная бытовая активность.",
        citations=["E3"],
    )


def _week_sessions(
    offset: int,
    *,
    focus: str,
    factor: float,
    start: date,
    profile: UserProfile,
    layer: MedicationLayer,
) -> list[PlanSession]:
    layout = _build_weekly_slots(profile)
    medication_note = None
    if layer.intensity_caution:
        medication_note = (
            "Из-за препаратов: RPE не выше 6, без максимальных интервалов; "
            "при головокружении или необычном пульсе — стоп."
        )
    elif layer.orthostatic_caution:
        medication_note = (
            "Вставайте медленно, контролируйте головокружение; при "
            "ортостатических симптомах — стоп."
        )

    sessions: list[PlanSession] = []
    cycling_seen = 0
    for weekday, kind in enumerate(layout):
        day = start + timedelta(days=offset * 7 + weekday)
        if kind == "hybrid_double":
            base = 65 if focus != "deload" else 45
            dur = max(35, round(base * factor))
            sessions.append(
                _hybrid_double_session(
                    day,
                    duration=_minutes_for(profile, weekday, dur),
                    medication_note=medication_note,
                )
            )
        elif kind == "functional":
            base = 40 if focus != "deload" else 30
            dur = max(20, round(base * factor))
            sessions.append(
                _functional_session(
                    day,
                    duration=_minutes_for(profile, weekday, dur),
                    medication_note=medication_note,
                )
            )
        elif kind in {
            "strength",
            "fullbody_1",
            "fullbody_2",
            "upper_1",
            "lower_1",
            "upper_2",
            "lower_2",
            "push",
            "pull",
            "legs",
            "pull_legs",
        }:
            base = 45 if focus != "deload" else 35
            duration = max(20, round(base * factor))
            rpe = "5–6" if layer.intensity_caution else ("6" if focus == "base" else "6–7")
            title, struct = _strength_details(kind)
            sessions.append(
                _strength_session(
                    day,
                    duration=_minutes_for(profile, weekday, duration),
                    rpe=rpe,
                    medication_note=medication_note,
                    title=title,
                    structure=struct,
                )
            )
        elif kind == "cycling":
            base = 35 if focus == "base" else 45
            if focus == "deload":
                base = 30
            elif focus == "consolidation":
                base = 38
            duration = max(20, round(base * (factor if focus != "deload" else 1.0)))
            tempo = focus == "build" and offset in {2, 4} and cycling_seen == 0
            tempo = tempo and not layer.intensity_caution
            cycling_seen += 1
            sessions.append(
                _cycling_session(
                    day,
                    duration=_minutes_for(profile, weekday, duration),
                    tempo=tempo,
                    medication_note=medication_note,
                )
            )
        elif kind == "mobility":
            mob_dur = 20 if focus == "deload" else 25
            sessions.append(_mobility_session(day, duration=mob_dur))
        else:
            sessions.append(_rest_session(day))
    return sessions


def _plan_citations(profile: UserProfile, layer: MedicationLayer) -> list[str]:
    citations = set(BASE_CITATIONS)
    citations.update(layer.citations)
    if profile.primary_goal in {"fat_loss", "strength"}:
        citations.add("E2")
    if profile.primary_goal in {"cycling", "endurance"}:
        citations.update({"E5", "E6"})
    return sorted(citations)


def _has_recent_illness(
    events: Iterable[Event | dict[str, Any]] | None,
    *,
    reference_day: date,
    days: int = 14,
) -> tuple[bool, str]:
    for item in events or ():
        ev_date: str
        ev_kind: str
        ev_title: str
        if isinstance(item, Event):
            ev_date = item.date
            ev_kind = str(item.kind)
            ev_title = item.title
        elif isinstance(item, dict):
            ev_date = str(item.get("date") or "")
            ev_kind = str(item.get("kind") or "")
            ev_title = str(item.get("title") or ev_kind)
        else:
            continue
        if ev_kind != "illness":
            continue
        try:
            parsed = date.fromisoformat(ev_date[:10])
        except ValueError:
            continue
        if -1 <= (reference_day - parsed).days <= days:
            return True, ev_title
    return False, ""


def build_skeleton(
    profile: UserProfile,
    status: DataStatus,
    *,
    start_date: date | None = None,
    today: date | None = None,
    events: Iterable[Event | dict[str, Any]] | None = None,
) -> TrainingPlan:
    """Build the deterministic plan; no LLM is involved."""
    ref_day = today or date.today()
    start = start_date or _next_monday(ref_day)
    horizon = min(max(profile.horizon_weeks, 1), 12)
    layer = build_layer(profile)
    post_illness, illness_title = _has_recent_illness(
        events, reference_day=ref_day
    )

    weeks: list[PlanWeek] = []
    for index in range(horizon):
        focus = WEEK_FOCUS[index] if horizon == 6 else _generic_focus(index, horizon)
        factor = VOLUME_FACTOR[index] if horizon == 6 else _generic_factor(index, horizon)
        if index == 0 and post_illness:
            focus = "deload"
            factor = 0.65
        sessions = _week_sessions(
            index,
            focus=focus,
            factor=factor,
            start=start,
            profile=profile,
            layer=layer,
        )
        rules = [
            "Пропущенную сессию не догонять.",
            "При сне <6 ч или боли ≥4/10 — отдых, а не перенос нагрузки.",
            "Прогрессия только по недельному правилу.",
        ]
        if index == 0 and post_illness:
            illness_note = (
                "После болезни/простуды: мягкий возврат (RPE 4–5), следите "
                "за пульсом покоя и самочувствием."
            )
            for pos, session in enumerate(sessions):
                if session.type == "rest":
                    continue
                combined_safety = (
                    f"{session.safety} {illness_note}".strip()
                    if session.safety
                    else illness_note
                )
                sessions[pos] = session.model_copy(
                    update={
                        "intensity": (
                            "RPE 4–5, лёгкая техника без отказа"
                            if session.type == "strength"
                            else session.intensity
                        ),
                        "safety": combined_safety,
                    }
                )
            rules.insert(
                0,
                "После простуды/болезни: первые 3–7 дней без интервалов; "
                "при возврате симптомов или скачке пульса покоя — стоп и отдых.",
            )
        weeks.append(
            PlanWeek(
                week=index + 1,
                focus=focus,
                target_load=round(100 * factor, 1),
                sessions=sessions,
                adaptation_rules=rules,
            )
        )

    flags = list(layer.safety_flags)
    if post_illness:
        flags.append(
            SafetyFlag(
                code="post_illness_week1",
                severity="warning",
                text=(
                    f"Неделя 1 переведена в щадящий режим (разгрузка −35%) "
                    f"для возврата после «{illness_title[:80]}»."
                ),
            )
        )
    flags.append(
        SafetyFlag(
            code="minimum_data_gate",
            severity="info" if status.ready_for_plan else "warning",
            text=(
                "Данных достаточно для плана."
                if status.ready_for_plan
                else "План предварительный: " + "; ".join(status.missing)
            ),
        )
    )
    if layer.entries:
        flags.append(
            SafetyFlag(
                code="medication_review",
                severity="info",
                text=(
                    "Препараты учтены только как предосторожности. Дозы, "
                    "отмену и комбинации обсуждайте с врачом."
                ),
            )
        )

    confidence = "low"
    if status.ready_for_plan and status.coverage_label == "высокое":
        confidence = "high"
    elif status.ready_for_plan or status.days >= 14:
        confidence = "medium"

    assumptions = [
        f"Цель: {_goal_text(profile.primary_goal)}; горизонт {horizon} нед.",
        "Тренировки выполняются с RPE 6–7, не до отказа.",
        "Сон и восстановление важнее «догоняния» плана.",
    ]
    if post_illness:
        assumptions.append(
            "Неделя 1 облегчена (разгрузка −35%, RPE 4–5) после болезни/простуды."
        )
    if profile.availability:
        assumptions.append("Длительности ограничены доступным временем.")

    return TrainingPlan(
        plan_id=uuid.uuid4().hex[:16],
        goal=profile.primary_goal,
        horizon_weeks=horizon,
        confidence=confidence,
        assumptions=assumptions,
        missing_data=list(status.missing),
        safety_flags=flags,
        weeks=weeks,
        citations=_plan_citations(profile, layer),
        disclaimer=DISCLAIMER,
    )


def _next_monday(today: date | None = None) -> date:
    current = today or date.today()
    return current + timedelta(days=(7 - current.weekday()) % 7)


def _generic_focus(index: int, horizon: int) -> str:
    if index == horizon - 1:
        return "consolidation"
    if index > 0 and index % 4 == 3:
        return "deload"
    return "base" if index == 0 else "build"


def _generic_factor(index: int, horizon: int) -> float:
    focus = _generic_focus(index, horizon)
    if focus == "deload":
        return 0.65
    if focus == "consolidation":
        return 0.88
    return 1.0 + 0.05 * min(index, 4)


def _goal_text(goal: str) -> str:
    return {
        "fat_loss": "снижение веса",
        "strength": "сила",
        "health": "здоровье и энергия",
        "cycling": "велосипед",
        "endurance": "выносливость",
        "mixed": "смешанный формат",
    }.get(goal, goal)


def week_volume(week: PlanWeek) -> int:
    return sum(session.duration_min or 0 for session in week.sessions)


def validate_plan(
    plan: TrainingPlan,
    profile: UserProfile,
    *,
    layer: MedicationLayer | None = None,
) -> list[str]:
    """Return hard validation errors; an empty list means the plan is valid."""
    errors: list[str] = []
    if not plan.weeks:
        return ["план пуст"]
    if len(plan.weeks) != plan.horizon_weeks:
        errors.append("число недель не совпадает с горизонтом")

    for index, week in enumerate(plan.weeks):
        dates = [session.date for session in week.sessions]
        if len(week.sessions) != 7:
            errors.append(f"неделя {week.week}: должно быть 7 дней")
        if len(set(dates)) != len(dates):
            errors.append(f"неделя {week.week}: даты сессий пересекаются")
        rest_days = sum(1 for session in week.sessions if session.type == "rest")
        if rest_days < 1:
            errors.append(f"неделя {week.week}: нет полного дня отдыха")
        hard_days = sum(
            1
            for session in week.sessions
            if "темп" in (session.title or "").lower()
            or "Z4" in (session.intensity or "")
            or "RPE 8" in (session.intensity or "")
        )
        if hard_days > 3:
            errors.append(f"неделя {week.week}: больше 3 тяжёлых дней")
        strength_days = sum(
            1 for session in week.sessions if session.type == "strength"
        )
        ptype = getattr(profile, "plan_type", "fullbody")
        n_avail = len(profile.availability)
        if ptype == "ppl" and n_avail >= 6:
            max_strength = 6
        elif profile.experience in {"regular", "advanced"} or ptype in {"upper_lower", "ppl"}:
            max_strength = 5
        elif ptype in {"upper_lower", "hybrid"}:
            max_strength = 4
        else:
            max_strength = 3
        if strength_days > max_strength:
            errors.append(f"неделя {week.week}: больше {max_strength} силовых")

        if index > 0:
            previous = week_volume(plan.weeks[index - 1])
            current = week_volume(week)
            if previous > 0:
                ratio = current / previous
                if week.focus == "deload" and not 0.5 <= ratio <= 0.75:
                    errors.append(f"неделя {week.week}: разгрузка не −25–50%")
                previous_focus = plan.weeks[index - 1].focus
                if week.focus == "build" and previous_focus != "deload" and ratio > 1.15:
                    errors.append(f"неделя {week.week}: слишком быстрый рост объёма")
                if week.focus == "consolidation" and ratio > 1.0:
                    errors.append(f"неделя {week.week}: консолидация растёт")

    if len(plan.citations) < 2:
        errors.append("нужно минимум 2 источника")
    unknown = [item for item in plan.citations if item not in CITATION_IDS]
    if unknown:
        errors.append("неизвестные источники: " + ", ".join(unknown))

    med_layer = layer or build_layer(profile)
    if med_layer.intensity_caution:
        for week in plan.weeks:
            for session in week.sessions:
                text = f"{session.title} {session.intensity}"
                if "Z4" in text or "RPE 8" in text or "максим" in text.lower():
                    errors.append(
                        f"неделя {week.week}: интенсивность несовместима с препаратами"
                    )
                    break

    forbidden = ("увеличьте дозу", "снизьте дозу", "прекратите приём", "отмените препарат")
    plan_text = " ".join(
        filter(
            None,
            [
                plan.disclaimer,
                *plan.assumptions,
                *[flag.text for flag in plan.safety_flags],
            ],
        )
    ).lower()
    for phrase in forbidden:
        if phrase in plan_text:
            errors.append("в плане есть медицинское назначение")
            break
    return errors


def clarifying_questions(
    profile: UserProfile,
    status: DataStatus,
) -> list[str]:
    """Return at most three deterministic questions before a plan is built."""
    questions: list[str] = []
    if not profile.availability:
        questions.append(
            "В какие дни недели и сколько минут вы реально можете тренироваться?"
        )
    if not profile.equipment:
        questions.append(
            "Что доступно: зал, дом, велосипед, резинки, гантели, улица?"
        )
    if not status.ready_for_plan:
        missing = "; ".join(status.missing[:2]) or "мало данных"
        questions.append(
            f"Данных пока мало ({missing}). Импортировать ещё или построить "
            "осторожный быстрый план?"
        )
    if profile.medications and profile.doctor_clearance == "unknown":
        questions.append(
            "Обсуждали ли вы с врачом ограничения нагрузки с учётом препаратов?"
        )
    return questions[:3]


def _esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def plan_summary(plan: TrainingPlan) -> str:
    """Compact Russian overview for Telegram."""
    conf = CONFIDENCE_LABELS.get(plan.confidence, plan.confidence)
    lines = [
        f"🏋️ <b>План на {plan.horizon_weeks} недель</b>",
        f"Цель: {_esc(_goal_text(plan.goal))} · надёжность: {_esc(conf)}",
        "",
    ]
    for week in plan.weeks:
        strength = sum(1 for session in week.sessions if session.type == "strength")
        aerobic = sum(1 for session in week.sessions if session.type == "aerobic")
        focus = FOCUS_LABELS.get(week.focus, week.focus)
        lines.append(
            f"Неделя {week.week} ({_esc(focus)}): "
            f"{strength} силовых, {aerobic} аэробных/вело, "
            f"{week_volume(week)} мин"
        )
    if plan.missing_data:
        lines.append("")
        lines.append(
            "⚠️ Не хватает: "
            + "; ".join(_esc(item) for item in plan.missing_data)
        )
    lines.append("")
    lines.append(_esc(plan.disclaimer))
    return "\n".join(lines)


def first_week_text(plan: TrainingPlan) -> str:
    return week_detail_text(plan, 1)


def week_detail_text(plan: TrainingPlan, week_number: int) -> str:
    """Detailed sessions for one week, including structure and safety notes."""
    if not plan.weeks:
        return ""
    index = max(0, min(week_number - 1, len(plan.weeks) - 1))
    week = plan.weeks[index]
    focus = FOCUS_LABELS.get(week.focus, week.focus)
    lines = [f"<b>Неделя {week.week} · {_esc(focus)}</b>"]
    for session in week.sessions:
        day = date.fromisoformat(session.date)
        lines.append("")
        lines.append(
            f"<b>{DAY_NAMES[day.weekday()]} {day.strftime('%d.%m')}: "
            f"{_esc(session.title)}</b> — {session.duration_min or 0} мин"
        )
        if session.intensity:
            lines.append(f"Интенсивность: {_esc(session.intensity)}")
        if session.structure.warmup:
            lines.append(f"Разминка: {_esc(session.structure.warmup)}")
        if session.structure.main:
            lines.append(f"Основная часть: {_esc(session.structure.main)}")
        if session.structure.cooldown:
            lines.append(f"Заминка: {_esc(session.structure.cooldown)}")
        if session.safety:
            lines.append(f"⚠️ {_esc(session.safety)}")
    if week.adaptation_rules:
        lines.append("")
        lines.append("<b>Правила недели:</b>")
        lines.extend(f"• {_esc(rule)}" for rule in week.adaptation_rules)
    lines.append("")
    lines.append(
        "💡 <i>Справка по терминам:\n"
        "• RPE (шкала нагрузки 1–10): RPE 6–7 — умеренное усилие, запас 2–3 повторения.\n"
        "• Зона 2 (Z2) — пульсовая аэробная база (разговорный темп без одышки).\n"
        "• ACWR — баланс острой и хронической нагрузки (норма: 0.8–1.3).</i>"
    )
    return "\n".join(lines)
