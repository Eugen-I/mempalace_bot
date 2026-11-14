"""PDF training plan and one-page doctor sheet.

The plan PDF is deterministic and portrait-oriented.  It contains the six-week
overview, the first detailed week, adaptation rules, medication precautions,
red flags, citations and a disclaimer.  The doctor sheet is a separate page (or
standalone PDF) with the user's current medications, class-level precautions,
symptoms from check-ins/events, a brief plan summary and questions for the
prescriber.  It never contains dose advice.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, SimpleDocTemplate, Spacer

from .evidence import format_citations
from .medications import MedicationLayer, build_layer, doctor_questions
from .models import Checkin, Event, TrainingPlan, UserProfile
from .pdf_report import _font_name, _p, _styles, _table

PLAN_TITLE = "План тренировок Garmin"
DOCTOR_TITLE = "Doctor sheet: вопросы врачу"
DISCLAIMER = (
    "Это не медицинская рекомендация, не диагноз и не назначение. "
    "Дозы, отмену и комбинации препаратов обсуждайте только с врачом."
)
RED_FLAGS = (
    "боль в груди, обморок, выраженная одышка, спутанность сознания, "
    "тремор/лихорадка/потливость, судороги, боль ≥4/10, суицидальные мысли"
)
GOAL_LABELS = {
    "fat_loss": "снижение веса",
    "strength": "сила",
    "health": "здоровье и энергия",
    "cycling": "велосипед",
    "endurance": "выносливость",
    "mixed": "смешанный формат",
}
FOCUS_LABELS = {
    "base": "база",
    "build": "нагрузка",
    "deload": "разгрузка",
    "taper": "подводка",
    "test": "тест",
    "consolidation": "консолидация",
}


def _footer(canvas, doc, font: str, label: str) -> None:
    canvas.saveState()
    canvas.setFont(font, 7)
    canvas.setFillColor(colors.HexColor("#6b7280"))
    canvas.drawString(
        16 * mm,
        9 * mm,
        f"{label} · локальные данные · не медицинский документ",
    )
    canvas.drawRightString(doc.pagesize[0] - 16 * mm, 9 * mm, f"Стр. {doc.page}")
    canvas.restoreState()


def _list(story: list, heading: str, items: Iterable[str], styles) -> None:
    values = [str(item) for item in items if item]
    if not values:
        return
    if heading:
        story.append(_p(heading, styles["h2"]))
    for item in values:
        story.append(_p(f"• {item}", styles["body"]))


def _overview_rows(plan: TrainingPlan, styles) -> list[list]:
    rows = [
        [
            _p("Неделя", styles["cell_bold"]),
            _p("Фокус", styles["cell_bold"]),
            _p("Силовые", styles["cell_bold"]),
            _p("Вело/Z2", styles["cell_bold"]),
            _p("Объём", styles["cell_bold"]),
            _p("Цель нагрузки", styles["cell_bold"]),
        ]
    ]
    for week in plan.weeks:
        strength = sum(1 for item in week.sessions if item.type == "strength")
        aerobic = sum(1 for item in week.sessions if item.type == "aerobic")
        volume = sum(item.duration_min or 0 for item in week.sessions)
        rows.append(
            [
                _p(str(week.week), styles["cell"]),
                _p(FOCUS_LABELS.get(week.focus, week.focus), styles["cell"]),
                _p(str(strength), styles["cell"]),
                _p(str(aerobic), styles["cell"]),
                _p(f"{volume} мин", styles["cell"]),
                _p(
                    "—" if week.target_load is None else f"{week.target_load:g}%",
                    styles["cell"],
                ),
            ]
        )
    return rows


def _week_rows(plan: TrainingPlan, week_number: int, styles) -> list[list]:
    rows = [
        [
            _p("День", styles["cell_bold"]),
            _p("Сессия", styles["cell_bold"]),
            _p("Мин", styles["cell_bold"]),
            _p("Интенсивность", styles["cell_bold"]),
            _p("Структура", styles["cell_bold"]),
        ]
    ]
    week = next((item for item in plan.weeks if item.week == week_number), None)
    if week is None:
        return rows
    day_names = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
    from datetime import date

    for session in week.sessions:
        day = date.fromisoformat(session.date)
        structure = " / ".join(
            part
            for part in (
                session.structure.warmup,
                session.structure.main,
                session.structure.cooldown,
            )
            if part
        )
        rows.append(
            [
                _p(f"{day_names[day.weekday()]} {day.strftime('%d.%m')}", styles["cell"]),
                _p(session.title, styles["cell"]),
                _p(str(session.duration_min or 0), styles["cell"]),
                _p(session.intensity or "—", styles["cell"]),
                _p(structure or "—", styles["cell"]),
            ]
        )
    return rows


def _plan_story(
    plan: TrainingPlan,
    profile: UserProfile,
    layer: MedicationLayer,
    styles,
) -> list:
    story = [
        _p(PLAN_TITLE, styles["title"]),
        _p(
            f"Цель: {GOAL_LABELS.get(plan.goal, plan.goal)} · "
            f"горизонт: {plan.horizon_weeks} нед. · "
            f"уверенность: {plan.confidence}",
            styles["subtitle"],
        ),
        Spacer(1, 6),
    ]
    _list(story, "Допущения", plan.assumptions, styles)
    if plan.missing_data:
        _list(story, "Не хватает данных", plan.missing_data, styles)

    story.append(_p("Обзор недель", styles["h1"]))
    story.append(
        _table(
            _overview_rows(plan, styles),
            font=_font_name(),
            widths=[20 * mm, 30 * mm, 24 * mm, 24 * mm, 26 * mm, 32 * mm],
        )
    )

    story.append(PageBreak())
    story.append(_p("Первая неделя подробно", styles["h1"]))
    story.append(
        _table(
            _week_rows(plan, 1, styles),
            font=_font_name(),
            widths=[22 * mm, 42 * mm, 14 * mm, 30 * mm, 72 * mm],
        )
    )

    rules: list[str] = []
    for week in plan.weeks:
        for rule in week.adaptation_rules:
            if rule not in rules:
                rules.append(rule)
    _list(story, "Правила адаптации", rules, styles)

    if layer.entries:
        story.append(_p("Препараты: только предосторожности", styles["h1"]))
        story.append(_p(layer.summary, styles["body"]))
        for flag in layer.safety_flags:
            story.append(_p(f"• {flag.text}", styles["body"]))
        _list(story, "Вопросы врачу", doctor_questions(layer), styles)
        story.append(
            _p(
                "В этом PDF намеренно нет доз и схем приёма: бот не меняет "
                "лечение.",
                styles["small"],
            )
        )

    story.append(_p("Красные флаги", styles["h1"]))
    story.append(_p(RED_FLAGS + ". В этих случаях — стоп и срочно к врачу.", styles["body"]))

    citations = format_citations(plan.citations)
    if citations:
        _list(story, "Источники", citations, styles)

    story.append(Spacer(1, 6))
    story.append(_p(DISCLAIMER, styles["small"]))
    return story


def _doctor_story(
    profile: UserProfile,
    layer: MedicationLayer,
    plan: TrainingPlan | None,
    checkins: list[Checkin] | None,
    events: list[Event] | None,
    styles,
) -> list:
    story = [
        _p(DOCTOR_TITLE, styles["title"]),
        _p(
            "Подготовлено пользователем для обсуждения с врачом. "
            "Не является диагнозом или назначением.",
            styles["subtitle"],
        ),
        Spacer(1, 6),
    ]

    story.append(_p("Профиль", styles["h1"]))
    story.append(
        _p(
            f"Цель: {GOAL_LABELS.get(profile.primary_goal, profile.primary_goal)} · "
            f"опыт: {profile.experience} · стресс: {profile.stress_level} · "
            f"сон-цель: {profile.sleep_target_h:g} ч",
            styles["body"],
        )
    )
    if profile.conditions:
        _list(story, "Состояния (со слов пользователя)", profile.conditions, styles)
    if profile.injuries:
        _list(story, "Травмы/ограничения (со слов пользователя)", profile.injuries, styles)
    if profile.doctor_clearance != "unknown":
        story.append(
            _p(
                "Допуск врача: "
                + ("есть" if profile.doctor_clearance == "yes" else "нет"),
                styles["body"],
            )
        )

    story.append(_p("Текущие препараты и БАДы", styles["h1"]))
    if not layer.entries and not profile.supplements:
        story.append(_p("Не указаны.", styles["body"]))
    for entry in layer.entries:
        details = " · ".join(
            part
            for part in (
                entry.dose,
                entry.frequency,
                entry.timing,
                entry.reason,
                entry.class_name,
            )
            if part
        )
        story.append(
            _p(
                f"• {entry.name}" + (f" — {details}" if details else ""),
                styles["body"],
            )
        )
        for precaution in entry.precautions:
            story.append(_p(f"  – {precaution}", styles["small"]))
    if profile.supplements:
        story.append(_p("БАДы: " + ", ".join(profile.supplements), styles["body"]))

    story.append(_p("Симптомы и события за период", styles["h1"]))
    symptom_lines: list[str] = []
    for checkin in checkins or []:
        if (
            (checkin.pain_score or 0) >= 1
            or (checkin.soreness or 0) >= 4
            or (checkin.stress or 0) >= 4
            or (checkin.mood or 5) <= 2
        ):
            parts = [f"{checkin.date}"]
            if checkin.pain_score:
                location = (
                    f" ({checkin.pain_location})" if checkin.pain_location else ""
                )
                parts.append(f"боль {checkin.pain_score}/10{location}")
            if checkin.soreness:
                parts.append(f"болезненность {checkin.soreness}/10")
            if checkin.stress:
                parts.append(f"стресс {checkin.stress}/5")
            if checkin.mood:
                parts.append(f"настроение {checkin.mood}/5")
            symptom_lines.append(" · ".join(parts))
    for event in events or []:
        if event.severity in {"warning", "critical"}:
            symptom_lines.append(
                f"{event.date} · {event.kind}: {event.title}"
            )
    if symptom_lines:
        _list(story, "", symptom_lines[:12], styles)
    else:
        story.append(_p("Значимых симптомов в чек-инах и событиях нет.", styles["body"]))

    if plan is not None:
        story.append(_p("План нагрузок вкратце", styles["h1"]))
        story.append(
            _p(
                f"{plan.horizon_weeks} недель · "
                f"цель: {GOAL_LABELS.get(plan.goal, plan.goal)}",
                styles["body"],
            )
        )
        for week in plan.weeks[:2]:
            volume = sum(item.duration_min or 0 for item in week.sessions)
            story.append(
                _p(
                    f"• Неделя {week.week} ({FOCUS_LABELS.get(week.focus, week.focus)}): "
                    f"{volume} мин, "
                    f"{sum(1 for item in week.sessions if item.type == 'strength')} "
                    f"силовых",
                    styles["body"],
                )
            )

    _list(story, "Вопросы врачу", doctor_questions(layer), styles)
    story.append(_p("Красные флаги", styles["h2"]))
    story.append(_p(RED_FLAGS + ".", styles["body"]))
    story.append(Spacer(1, 6))
    story.append(_p(DISCLAIMER, styles["small"]))
    return story


def _build(
    output_path: str | Path,
    story: list,
    *,
    title: str,
    footer_label: str,
    font: str,
) -> Path:
    output = Path(output_path).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=17 * mm,
        title=title,
        author="MemPalace",
        subject="Garmin training plan and doctor sheet",
    )
    doc.build(
        story,
        onFirstPage=lambda canvas, document: _footer(
            canvas, document, font, footer_label
        ),
        onLaterPages=lambda canvas, document: _footer(
            canvas, document, font, footer_label
        ),
    )
    return output


def build_plan_pdf(
    plan: TrainingPlan,
    profile: UserProfile,
    output_path: str | Path,
    *,
    layer: MedicationLayer | None = None,
    checkins: list[Checkin] | None = None,
    events: list[Event] | None = None,
    include_doctor_sheet: bool = True,
) -> Path:
    """Build the plan PDF (2–4 pages) and optionally append the doctor sheet."""
    font = _font_name()
    styles = _styles(font)
    medication_layer = layer or build_layer(profile)
    story = _plan_story(plan, profile, medication_layer, styles)
    if include_doctor_sheet:
        story.append(PageBreak())
        story.extend(
            _doctor_story(
                profile,
                medication_layer,
                plan,
                checkins,
                events,
                styles,
            )
        )
    return _build(
        output_path,
        story,
        title=PLAN_TITLE,
        footer_label="Garmin training plan",
        font=font,
    )


def build_doctor_pdf(
    profile: UserProfile,
    output_path: str | Path,
    *,
    layer: MedicationLayer | None = None,
    plan: TrainingPlan | None = None,
    checkins: list[Checkin] | None = None,
    events: list[Event] | None = None,
) -> Path:
    """Build a standalone one-page doctor sheet."""
    font = _font_name()
    styles = _styles(font)
    story = _doctor_story(
        profile,
        layer or build_layer(profile),
        plan,
        checkins,
        events,
        styles,
    )
    return _build(
        output_path,
        story,
        title=DOCTOR_TITLE,
        footer_label="Garmin doctor sheet",
        font=font,
    )
