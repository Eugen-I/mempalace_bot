"""PDF report for Garmin health and training data.

A4 landscape, Unicode Cyrillic, deterministic tables and charts.  The report is
assembled from :class:`~services.garmin.analytics.ReportData`; no AI calls are
made here.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING
from xml.sax.saxutils import escape  # nosec B406

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .analytics import ReportData
from .evidence import format_citations

if TYPE_CHECKING:
    from .coach import CoachResult

FONT_CANDIDATES = (
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)

CHART_ORDER = (
    "sleep_hours",
    "sleep_score",
    "hrv",
    "resting_hr",
    "stress_avg",
    "steps",
    "weight_kg",
    "readiness_score",
    "body_battery_morning",
)

NAVY = colors.HexColor("#243447")
BLUE = colors.HexColor("#3b6ea8")
MUTED = colors.HexColor("#6b7280")
LIGHT = colors.HexColor("#eef2f7")
WARN = colors.HexColor("#b45309")


def _font_name() -> str:
    explicit = (os.getenv("GARMIN_FONT_PATH") or "").strip()
    candidates = (explicit, *FONT_CANDIDATES) if explicit else FONT_CANDIDATES
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            if "GarminUnicode" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("GarminUnicode", candidate))
                pdfmetrics.registerFontFamily(
                    "GarminUnicode",
                    normal="GarminUnicode",
                    bold="GarminUnicode",
                    italic="GarminUnicode",
                    boldItalic="GarminUnicode",
                )
            return "GarminUnicode"
    return "Helvetica"


def _styles(font: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "GarminTitle",
            parent=base["Title"],
            fontName=font,
            fontSize=21,
            leading=25,
            textColor=NAVY,
            spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "GarminSubtitle",
            parent=base["Normal"],
            fontName=font,
            fontSize=10,
            leading=14,
            textColor=MUTED,
        ),
        "h1": ParagraphStyle(
            "GarminH1",
            parent=base["Heading1"],
            fontName=font,
            fontSize=14,
            leading=18,
            textColor=NAVY,
            spaceBefore=8,
            spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "GarminH2",
            parent=base["Heading2"],
            fontName=font,
            fontSize=10.5,
            leading=13,
            textColor=NAVY,
            spaceBefore=5,
            spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "GarminBody",
            parent=base["BodyText"],
            fontName=font,
            fontSize=8.5,
            leading=11.5,
            textColor=colors.black,
            spaceAfter=3,
        ),
        "small": ParagraphStyle(
            "GarminSmall",
            parent=base["BodyText"],
            fontName=font,
            fontSize=7.5,
            leading=9.5,
            textColor=MUTED,
        ),
        "cell": ParagraphStyle(
            "GarminCell",
            parent=base["BodyText"],
            fontName=font,
            fontSize=7,
            leading=8.5,
        ),
        "cell_bold": ParagraphStyle(
            "GarminCellBold",
            parent=base["BodyText"],
            fontName=font,
            fontSize=7,
            leading=8.5,
            textColor=colors.white,
        ),
    }


def _fmt(value, unit: str = "", digits: int = 1) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        text = f"{value:.{digits}f}"
    else:
        text = str(value)
    return f"{text} {unit}".strip()


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(text)), style)


def _table(
    data,
    *,
    font: str,
    widths=None,
    header: bool = True,
) -> Table:
    table = Table(data, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("LEADING", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d7dee8")),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]
    if header:
        commands += [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), font),
        ]
    for row_index in range(1 if header else 0, len(data)):
        if row_index % 2 == 0:
            commands.append(("BACKGROUND", (0, row_index), (-1, row_index), LIGHT))
    table.setStyle(TableStyle(commands))
    return table


def _image(path: Path, *, max_width: float, max_height: float) -> Image:
    with PILImage.open(path) as img:
        width, height = img.size
    scale = min(max_width / width, max_height / height, 1.0)
    return Image(str(path), width=width * scale, height=height * scale)


def _footer(canvas, doc, font: str) -> None:
    canvas.saveState()
    canvas.setFont(font, 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(
        16 * mm,
        9 * mm,
        "Garmin health report · локальные данные · не медицинский документ",
    )
    canvas.drawRightString(281 * mm, 9 * mm, f"Стр. {doc.page}")
    canvas.restoreState()


def _coach_story(coach: "CoachResult", styles: dict[str, ParagraphStyle]) -> list:
    output = coach.output
    heading = (
        "AI-разбор (локальная модель)"
        if coach.ok
        else "Детерминированный разбор (AI недоступен)"
    )
    story = [_p(heading, styles["h1"]), _p(str(output.get("summary", "")), styles["body"])]

    causes = output.get("possible_causes") or []
    if causes:
        story.append(_p("Возможные причины", styles["h2"]))
        for item in causes:
            citations = ", ".join(item.get("citations") or [])
            story.append(
                _p(
                    f"• {item.get('text', '')} "
                    f"(уверенность: {item.get('confidence', '—')}; {citations})",
                    styles["body"],
                )
            )

    help_items = output.get("what_could_help") or []
    if help_items:
        story.append(_p("Что может помочь", styles["h2"]))
        for item in help_items:
            citations = ", ".join(item.get("citations") or [])
            story.append(_p(f"• {item.get('text', '')} [{citations}]", styles["body"]))

    questions = output.get("questions") or []
    if questions:
        story.append(_p("Уточняющие вопросы", styles["h2"]))
        for question in questions:
            story.append(_p(f"• {question}", styles["body"]))

    safety_flags = output.get("safety_flags") or []
    if safety_flags:
        story.append(_p("Безопасность", styles["h2"]))
        for item in safety_flags:
            prefix = "⚠ " if item.get("severity") == "urgent" else ""
            story.append(
                _p(
                    f"{prefix}{item.get('text', '')} "
                    f"({item.get('severity', 'info')})",
                    styles["body"],
                )
            )

    limitations = output.get("limitations") or []
    if limitations:
        story.append(_p("Ограничения AI-разбора", styles["h2"]))
        for item in limitations:
            story.append(_p(f"• {item}", styles["small"]))

    citation_lines = format_citations(output.get("citations") or [])
    if citation_lines:
        story.append(_p("Источники", styles["h2"]))
        for citation in citation_lines:
            story.append(_p(citation, styles["small"]))

    story.append(
        _p(
            "Локальная модель объясняет данные, но не ставит диагноз и не меняет "
            "лечение. Дозы и препараты обсуждайте только с врачом.",
            styles["small"],
        )
    )
    return story


def build_pdf(
    report: ReportData,
    charts: dict[str, Path],
    output_path: str | Path,
    *,
    title: str = "Garmin: здоровье и тренировки",
    coach: "CoachResult | None" = None,
) -> Path:
    """Build the report and return its path."""
    output = Path(output_path).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    font = _font_name()
    styles = _styles(font)

    doc = SimpleDocTemplate(
        str(output),
        pagesize=landscape(A4),
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=13 * mm,
        bottomMargin=15 * mm,
        title=title,
        author="MemPalace",
        subject="Garmin health and training report",
    )

    story = []
    story.append(_p(title, styles["title"]))
    story.append(
        _p(
            f"Период: {report.start} — {report.end} · сформировано: {report.generated_at} · "
            f"достоверность данных: {report.confidence}",
            styles["subtitle"],
        )
    )
    story.append(Spacer(1, 8))

    # Key metrics table.
    header = [
        _p("Показатель", styles["cell_bold"]),
        _p("Последнее", styles["cell_bold"]),
        _p("7 дней", styles["cell_bold"]),
        _p("28 дней", styles["cell_bold"]),
        _p("Baseline", styles["cell_bold"]),
        _p("Покрытие", styles["cell_bold"]),
    ]
    rows = [header]
    for key in CHART_ORDER:
        series = report.series.get(key)
        if series is None or not any(value is not None for value in series.values):
            continue
        rows.append(
            [
                _p(f"{series.label} ({series.unit})", styles["cell"]),
                _p(_fmt(series.latest), styles["cell"]),
                _p(_fmt(series.avg_7d), styles["cell"]),
                _p(_fmt(series.avg_28d), styles["cell"]),
                _p(_fmt(series.baseline), styles["cell"]),
                _p(f"{series.coverage * 100:.0f}%", styles["cell"]),
            ]
        )
    story.append(
        _table(
            rows,
            font=font,
            widths=[62 * mm, 28 * mm, 28 * mm, 28 * mm, 28 * mm, 24 * mm],
        )
    )

    if report.flags:
        story.append(Spacer(1, 8))
        story.append(_p("Что требует внимания", styles["h1"]))
        for flag in report.flags:
            story.append(_p(f"• {flag.text}", styles["body"]))

    story.append(PageBreak())

    # Charts.
    story.append(_p("Динамика показателей", styles["h1"]))
    rendered = 0
    for key in CHART_ORDER:
        path = charts.get(key)
        series = report.series.get(key)
        if not path or series is None:
            continue
        block = [
            _p(f"{series.label} · {series.unit}", styles["h2"]),
            _image(path, max_width=260 * mm, max_height=54 * mm),
            Spacer(1, 3),
        ]
        story.append(KeepTogether(block))
        rendered += 1
    if rendered == 0:
        story.append(
            _p(
                "Нет данных для графиков. Импортируйте Garmin wellness export.",
                styles["body"],
            )
        )

    if len(report.dates) <= 90:
        story.append(PageBreak())
        story.append(_p("Все дни периода", styles["h1"]))
        day_header = [
            _p("Дата", styles["cell_bold"]),
            _p("Сон, ч", styles["cell_bold"]),
            _p("Sleep score", styles["cell_bold"]),
            _p("HRV", styles["cell_bold"]),
            _p("Пульс покоя", styles["cell_bold"]),
            _p("Стресс", styles["cell_bold"]),
            _p("Шаги", styles["cell_bold"]),
            _p("Вес, кг", styles["cell_bold"]),
        ]
        day_rows = [day_header]
        for index, day in enumerate(report.dates):
            day_rows.append(
                [
                    _p(day, styles["cell"]),
                    _p(_fmt(report.series["sleep_hours"].values[index]), styles["cell"]),
                    _p(_fmt(report.series["sleep_score"].values[index], digits=0), styles["cell"]),
                    _p(_fmt(report.series["hrv"].values[index], digits=0), styles["cell"]),
                    _p(_fmt(report.series["resting_hr"].values[index], digits=0), styles["cell"]),
                    _p(_fmt(report.series["stress_avg"].values[index], digits=0), styles["cell"]),
                    _p(_fmt(report.series["steps"].values[index], digits=0), styles["cell"]),
                    _p(_fmt(report.series["weight_kg"].values[index]), styles["cell"]),
                ]
            )
        story.append(
            _table(
                day_rows,
                font=font,
                widths=[30 * mm, 22 * mm, 28 * mm, 20 * mm, 28 * mm, 22 * mm, 28 * mm, 24 * mm],
            )
        )

    story.append(PageBreak())
    story.append(_p("Недельная сводка", styles["h1"]))
    week_header = [
        _p("Неделя", styles["cell_bold"]),
        _p("Сон, ч", styles["cell_bold"]),
        _p("HRV", styles["cell_bold"]),
        _p("Пульс покоя", styles["cell_bold"]),
        _p("Стресс", styles["cell_bold"]),
        _p("Шаги", styles["cell_bold"]),
        _p("Вес", styles["cell_bold"]),
        _p("Тренировки", styles["cell_bold"]),
    ]
    week_rows = [week_header]
    for week in report.weekly:
        week_rows.append(
            [
                _p(f"{week.week_start} — {week.week_end}", styles["cell"]),
                _p(_fmt(week.sleep_hours), styles["cell"]),
                _p(_fmt(week.hrv, digits=0), styles["cell"]),
                _p(_fmt(week.resting_hr, digits=0), styles["cell"]),
                _p(_fmt(week.stress_avg, digits=0), styles["cell"]),
                _p(_fmt(week.steps, digits=0), styles["cell"]),
                _p(_fmt(week.weight_kg), styles["cell"]),
                _p(f"{week.activities} / {week.training_min:.0f} мин", styles["cell"]),
            ]
        )
    story.append(
        _table(
            week_rows,
            font=font,
            widths=[
                52 * mm,
                22 * mm,
                20 * mm,
                27 * mm,
                22 * mm,
                27 * mm,
                22 * mm,
                38 * mm,
            ],
        )
    )

    story.append(Spacer(1, 8))
    story.append(_p("Тренировки", styles["h1"]))
    activity = report.activities
    story.append(
        _p(
            f"Всего: {activity.count} · {activity.total_min:.0f} мин · "
            f"суммарная нагрузка: {activity.total_load:.0f}",
            styles["body"],
        )
    )
    if activity.by_type:
        story.append(
            _p(
                "По типам: "
                + ", ".join(f"{key}: {value}" for key, value in sorted(activity.by_type.items())),
                styles["body"],
            )
        )
    else:
        story.append(_p("Активности не импортированы или отсутствуют за период.", styles["body"]))

    story.append(Spacer(1, 8))
    if coach is not None:
        story.extend(_coach_story(coach, styles))
    else:
        story.append(_p("Возможные причины изменений", styles["h1"]))
        for cause in report.causes:
            story.append(_p(f"• {cause}", styles["body"]))
        story.append(
            _p(
                "Это корреляционные гипотезы, а не диагноз. Учитывайте болезнь, "
                "алкоголь, поездки, стресс, жару и изменения лекарств.",
                styles["small"],
            )
        )

    story.append(Spacer(1, 8))
    story.append(_p("Ограничения данных", styles["h1"]))
    if report.missing_inputs:
        story.append(_p("Покрытие ниже 50%: " + ", ".join(report.missing_inputs), styles["body"]))
    else:
        story.append(_p("Ключевые метрики покрыты достаточно для обзора.", styles["body"]))
    if report.events:
        story.append(_p("События в периоде: " + ", ".join(
            f"{event['date']} {event['title']}" for event in report.events
        ), styles["body"]))

    story.append(Spacer(1, 8))
    story.append(
        _p(
            "Отчёт не заменяет врача. При боли в груди, обмороке, выраженной одышке, "
            "неконтролируемом давлении или новых неврологических симптомах обратитесь за помощью.",
            styles["small"],
        )
    )

    doc.build(
        story,
        onFirstPage=lambda canvas, doc: _footer(canvas, doc, font),
        onLaterPages=lambda canvas, doc: _footer(canvas, doc, font),
    )
    return output
