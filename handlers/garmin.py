"""Telegram UI for the local Garmin health and training integration.

All data stays local.  Imports are manual, reports are generated from SQLite
and the PDF is sent back as a Telegram document.  The local Ollama model only
narrates already-computed numbers.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import shlex
import shutil
from datetime import date
from pathlib import Path

from aiogram import F, Router, types
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import allowed_callback, allowed_only
from services.bot_setup import (
    garmin_last_plan,
    garmin_profile_draft,
    garmin_text_state,
)
import services.garmin.agent_tools  # noqa: F401 - register Garmin agent tools
from services.garmin.analytics import build_report
from services.garmin.charts import render_charts
from services.garmin.coach import coach_text, generate_causes_async
from services.garmin.config import get_config
from services.garmin.db import init_db
from services.garmin.delta import apply_delta, compute_delta, delta_text, log_delta
from services.garmin.errors import GarminError
from services.garmin.importers import import_any_path, looks_like_full_export
from services.garmin.medications import build_layer, doctor_questions
from services.garmin.models import (
    AvailabilitySlot,
    Checkin,
    Event,
    MedicationEntry,
    UserProfile,
)
from services.garmin.pdf_report import build_pdf
from services.garmin.plan_engine import (
    build_skeleton,
    clarifying_questions,
    first_week_text,
    plan_summary,
    validate_plan,
    week_detail_text,
)
from services.garmin.plan_report import build_doctor_pdf, build_plan_pdf
from services.garmin.plan_review import (
    apply_review,
    build_review,
    get_review,
    mark_review_applied,
    review_from_row,
    review_text,
    save_review,
)
from services.garmin.plan_store import (
    latest_plan,
    load_plan,
    save_plan,
    set_plan_status,
)
from services.garmin.retention import (
    apply_rolling,
    cleanup,
    extend,
    status as retention_status,
)
from services.garmin.profile_store import (
    delete_last_event,
    load_profile,
    recent_checkins,
    resolve_illness_events,
    save_checkin,
    save_event,
    save_profile,
)
from services.garmin.raw_store import RawStore
from services.garmin.readiness import assess_readiness
from services.garmin.safety import (
    assess_safety,
    merge_safety_flags,
    safety_text,
)
from services.garmin.status import data_status, status_text

logger = logging.getLogger("GarminHandler")
router = Router()

REPORT_DAYS = (7, 30, 90, 365)
TELEGRAM_LIMIT_MB = 20
IMPORT_SUFFIXES = {".zip", ".fit", ".csv", ".json", ".tcx"}
PROFILE_GOALS = {
    "fat_loss": "снижение веса",
    "strength": "сила",
    "health": "здоровье/энергия",
    "cycling": "велосипед",
    "mixed": "смешанный формат",
}
EXPERIENCE = {
    "beginner": "новичок",
    "returning": "возвращаюсь",
    "regular": "регулярно 6+ мес",
    "advanced": "продвинутый",
}
EQUIPMENT = {"gym": "зал", "home": "дом", "bike": "велосипед"}


# ---------------------------------------------------------------------------
# helpers


def _cfg():
    cfg = get_config()
    cfg.ensure_dirs()
    return cfg


async def _safe_edit(message: types.Message, text: str, **kwargs) -> None:
    """Edit a message, ignoring Telegram's harmless "not modified" error.

    Pressing an already selected inline button re-renders the same screen.
    Telegram rejects the identical edit; the screen is already correct.
    """
    try:
        await message.edit_text(text, **kwargs)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


def _connect():
    return init_db(_cfg().db_path)


def _uid(event) -> int:
    return int(event.from_user.id)


def _esc(value) -> str:
    return html.escape(str(value), quote=False)


def _fmt_day(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return date.fromisoformat(value[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return value


def _med_names(conn, user_id: int) -> list[str]:
    try:
        stored = load_profile(conn, user_id)
    except GarminError:
        return []
    if stored is None:
        return []
    return [entry.name for entry in stored.profile.medications]


def _profile(conn, user_id: int):
    try:
        return load_profile(conn, user_id)
    except GarminError as exc:
        logger.warning("Cannot load Garmin profile: %s", exc)
        return None


def _recent_events(conn, user_id: int, limit: int = 20) -> list[Event]:
    rows = conn.execute(
        "SELECT date, kind, title, notes, severity FROM garmin_events"
        " WHERE user_id = ? ORDER BY date DESC LIMIT ?",
        (int(user_id), int(limit)),
    ).fetchall()
    events: list[Event] = []
    for row in rows:
        try:
            events.append(
                Event(
                    date=str(row["date"]),
                    kind=str(row["kind"]),
                    title=str(row["title"]),
                    notes=row["notes"],
                    severity=str(row["severity"]),
                )
            )
        except ValueError:
            continue
    return events


def _main_kb() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(text="📊 PDF-отчёт", callback_data="garmin:pdf"),
        types.InlineKeyboardButton(text="🏋️ План", callback_data="garmin:plan"),
    )
    kb.row(
        types.InlineKeyboardButton(text="🌙 Сон", callback_data="garmin:sleep"),
        types.InlineKeyboardButton(text="❤️ Восстановление", callback_data="garmin:today"),
    )
    kb.row(
        types.InlineKeyboardButton(text="🧩 Профиль", callback_data="garmin:profile"),
        types.InlineKeyboardButton(text="💊 Препараты", callback_data="garmin:meds"),
    )
    kb.row(
        types.InlineKeyboardButton(text="📅 Чек-ин", callback_data="garmin:checkin"),
        types.InlineKeyboardButton(text="📈 Неделя", callback_data="garmin:week"),
    )
    kb.row(
        types.InlineKeyboardButton(
            text="🤒 Болезнь / Состояние", callback_data="garmin:illness"
        ),
        types.InlineKeyboardButton(
            text="🔄 Что изменилось", callback_data="garmin:changes"
        ),
    )
    kb.row(
        types.InlineKeyboardButton(text="📥 Импорт", callback_data="garmin:import"),
        types.InlineKeyboardButton(text="⚙️ Настройки", callback_data="garmin:settings"),
    )
    return kb.as_markup()


def _back_kb() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="garmin:main"))
    return kb.as_markup()


def _safety_kb() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="✅ Выздоровел (мягкий возврат)",
            callback_data="garmin:illness:recovered",
        )
    )
    kb.row(
        types.InlineKeyboardButton(
            text="🤒 Болезнь / Состояние", callback_data="garmin:illness"
        ),
        types.InlineKeyboardButton(
            text="🩺 Вопросы врачу", callback_data="garmin:doctor"
        ),
    )
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="garmin:main"))
    return kb.as_markup()


async def _main_text(conn, user_id: int) -> str:
    status = data_status(conn, user_id)
    lines = [status_text(status)]
    stored = _profile(conn, user_id)
    if stored is not None:
        lines.append(
            f"Цель: {PROFILE_GOALS.get(stored.profile.primary_goal, stored.profile.primary_goal)}"
            f" · {stored.profile.horizon_weeks} нед. · v{stored.version}"
        )
    else:
        lines.append("Профиль не заполнен — нажмите «🧩 Профиль».")
    recent_evs = _recent_events(conn, user_id, limit=5)
    active_ill = [
        ev
        for ev in recent_evs
        if ev.kind == "illness" and ev.severity in {"critical", "warning"}
    ]
    if active_ill:
        lines.append(
            f"🤒 Статус: отмечена болезнь («{_esc(active_ill[0].title[:60])}», "
            f"{_fmt_day(active_ill[0].date)})"
        )
    elif any(ev.kind == "illness" and ev.severity == "info" for ev in recent_evs):
        lines.append("🌿 Статус: мягкое восстановление после болезни/простуды.")
    try:
        retention = retention_status(
            conn, user_id, default_days=_cfg().retention_days
        )
        if retention.due:
            lines.append(
                "🗓 Данным Garmin исполняется год — откройте «⚙️ Настройки», "
                "чтобы продлить хранение."
            )
        elif retention.retention_until:
            lines.append(f"🗓 Хранение до {retention.retention_until}.")
    except Exception:  # noqa: BLE001 - retention info is optional
        logger.exception("Cannot read Garmin retention status")
    return "\n".join(lines)


async def _show_main(message: types.Message, user_id: int) -> None:
    conn = _connect()
    try:
        text = await _main_text(conn, user_id)
    finally:
        conn.close()
    await message.answer(text, reply_markup=_main_kb(), parse_mode="HTML")


def _import_sync(path: Path, user_id: int):
    cfg = _cfg()
    conn = init_db(cfg.db_path)
    try:
        result = import_any_path(
            path,
            conn=conn,
            raw_store=RawStore(cfg.raw_dir),
            user_id=user_id,
            tmp_dir=cfg.tmp_dir,
        )
        try:
            apply_rolling(
                conn,
                user_id,
                default_days=cfg.retention_days,
                raw_dir=cfg.raw_dir,
                charts_dir=cfg.charts_dir,
                report_dir=cfg.report_dir,
            )
        except Exception:  # noqa: BLE001 - retention must not break an import
            logger.exception("Garmin rolling retention failed")
        return result
    finally:
        conn.close()


def _build_report_sync(db_path, user_id: int, days: int):
    conn = init_db(db_path)
    try:
        return build_report(conn, user_id=user_id, days=days)
    finally:
        conn.close()


def _format_import_result(result) -> str:
    if result.status == "ok":
        title = "✅ <b>Импорт завершён</b>"
    elif result.status == "failed":
        title = "❌ <b>Импорт не удался</b>"
    else:
        title = "⚠️ <b>Импорт частичный</b>"
    lines = [
        title,
        f"Статус: {_esc(result.status)}",
        f"Файлов: {result.files_total}, успешно: {result.files_ok}, "
        f"ошибок: {result.files_failed}",
        f"Дней с данными: {len(set(result.days))}",
    ]
    if getattr(result, "rows_total", 0):
        lines.append(
            f"Строк: {result.rows_total}, активностей: {result.rows_ok}, "
            f"пропущено: {result.rows_skipped}, ошибок: {result.rows_failed}"
        )
    if result.days:
        days = sorted(set(result.days))
        lines.append(f"Период: {_fmt_day(days[0])} — {_fmt_day(days[-1])}")
    if result.issues:
        lines.append("")
        lines.append("Первые проблемы:")
        for issue in result.issues[:3]:
            lines.append(f"• {_esc(issue.error[:180])}")
    return "\n".join(lines)


async def _send_report(message: types.Message, user_id: int, days: int) -> None:
    cfg = _cfg()
    status_msg = await message.answer(f"📊 Собираю отчёт за {days} дней...")
    try:
        report = await asyncio.to_thread(
            _build_report_sync, cfg.db_path, user_id, days
        )
        conn = init_db(cfg.db_path)
        try:
            meds = _med_names(conn, user_id)
            coach = await generate_causes_async(
                conn,
                report,
                model=cfg.ai_model,
                timeout=min(cfg.ai_timeout, 75.0),
                ai_enabled=cfg.ai_enabled,
                medications=meds,
                fallback_model=cfg.ai_fallback_model,
                fallback_timeout=min(cfg.ai_fallback_timeout, 60.0),
            )
        finally:
            conn.close()

        charts = await asyncio.to_thread(
            render_charts, report, cfg.charts_dir, dpi=cfg.chart_dpi
        )
        output = cfg.report_dir / f"garmin_{user_id}_{report.end}_{days}d.pdf"
        pdf = await asyncio.to_thread(build_pdf, report, charts, output, coach=coach)
        if pdf.stat().st_size > cfg.pdf_max_mb * 1024 * 1024:
            pdf = await asyncio.to_thread(build_pdf, report, {}, output, coach=coach)
        await status_msg.delete()
        await message.answer_document(
            types.FSInputFile(pdf),
            caption=(
                f"📊 Garmin: {_fmt_day(report.start)} — {_fmt_day(report.end)} · "
                f"данные: {report.confidence} · ИИ: {coach.source}"
            ),
        )
    except Exception as exc:  # noqa: BLE001 - user-facing error, no secrets
        logger.exception("Garmin PDF failed")
        await status_msg.edit_text(
            "❌ Не удалось собрать PDF. Проверьте, что данные импортированы, "
            f"и попробуйте снова.\n<code>{_esc(type(exc).__name__)}</code>",
            parse_mode="HTML",
        )


def _draft(user_id: int) -> dict:
    draft = garmin_profile_draft.get(user_id)
    if draft is None:
        draft = {
            "primary_goal": "fat_loss",
            "secondary_goals": ["strength", "cycling", "health"],
            "experience": "returning",
            "availability_days": 3,
            "equipment": ["gym", "bike"],
            "stress_level": "medium",
            "medications": [],
        }
        garmin_profile_draft[user_id] = draft
    return draft


def _availability(days: int) -> list[AvailabilitySlot]:
    plans = {
        3: ((0, 45), (2, 45), (4, 45)),
        4: ((0, 45), (1, 40), (3, 45), (5, 60)),
        5: ((0, 45), (1, 40), (2, 45), (4, 45), (5, 60)),
    }
    return [
        AvailabilitySlot(day_of_week=weekday, minutes=minutes)
        for weekday, minutes in plans.get(days, plans[3])
    ]


def _profile_from_draft(draft: dict) -> UserProfile:
    medications: list[MedicationEntry] = []
    for item in draft.get("medications", []):
        if isinstance(item, MedicationEntry):
            medications.append(item)
        elif isinstance(item, dict):
            medications.append(MedicationEntry.model_validate(item))
    primary = draft.get("primary_goal", "fat_loss")
    secondary = [goal for goal in draft.get("secondary_goals", []) if goal != primary]
    return UserProfile(
        goals=[primary, *secondary],
        primary_goal=primary,
        secondary_goals=secondary,
        horizon_weeks=6,
        experience=draft.get("experience", "returning"),
        availability=_availability(int(draft.get("availability_days", 3))),
        equipment=list(draft.get("equipment", [])),
        medications=medications,
        stress_level=draft.get("stress_level", "medium"),
        sleep_target_h=7.5,
        doctor_clearance="unknown",
    )


def _profile_summary_kb() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="✅ Сохранить", callback_data="garmin:profile:save"))
    kb.row(types.InlineKeyboardButton(text="⬅️ Заново", callback_data="garmin:profile:new"))
    kb.row(types.InlineKeyboardButton(text="🏠 В меню", callback_data="garmin:main"))
    return kb.as_markup()


def _parse_medication_entries(text: str) -> list[MedicationEntry]:
    """Parse manual comma/semicolon/newline-separated medication list."""
    entries: list[MedicationEntry] = []
    for raw_part in re.split(r"[,;\n]", text or ""):
        cleaned = raw_part.strip()
        if not cleaned:
            continue
        entries.append(MedicationEntry(name=cleaned[:80]))
        if len(entries) >= 10:
            break
    return entries


# ---------------------------------------------------------------------------
# entry points


@router.message(Command("garmin"))
@allowed_only
async def cmd_garmin(message: types.Message):
    await _show_main(message, _uid(message))


@router.callback_query(F.data == "garmin:main")
@allowed_callback
async def cb_main(cb: types.CallbackQuery):
    await cb.answer()
    conn = _connect()
    try:
        text = await _main_text(conn, _uid(cb))
    finally:
        conn.close()
    await cb.message.edit_text(text, reply_markup=_main_kb(), parse_mode="HTML")


@router.message(Command("garmin_import"))
@allowed_only
async def cmd_garmin_import(message: types.Message):
    await _import_screen(message)


@router.callback_query(F.data == "garmin:import")
@allowed_callback
async def cb_import(cb: types.CallbackQuery):
    await cb.answer()
    await _import_screen(cb.message)


async def _import_screen(message: types.Message) -> None:
    cfg = _cfg()
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="📂 Проверить папку import", callback_data="garmin:import:folder"
        )
    )
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="garmin:main"))
    await message.answer(
        "📥 <b>Импорт Garmin</b>\n\n"
        "1) Дневной <b>Export Wellness Data</b> — ZIP или FIT.\n"
        "2) <b>Activities → Export CSV</b> — файл Activities.csv.\n"
        "3) Полный <b>Export Your Data</b> — ZIP, TCX, JSON или "
        "распакованная папка.\n\n"
        "Большие файлы (>20 МБ) положите в:\n"
        f"<code>{_esc(cfg.import_dir)}</code>\n"
        "и нажмите «Проверить папку import».\n\n"
        "Пароль Garmin не нужен: это официальные экспорты.",
        reply_markup=kb.as_markup(),
        parse_mode="HTML",
    )


@router.message(F.document)
@allowed_only
async def handle_garmin_document(message: types.Message):
    doc = message.document
    name = (doc.file_name or "").lower()
    suffix = Path(name).suffix
    if suffix not in IMPORT_SUFFIXES:
        return UNHANDLED
    if suffix == ".csv" and not name.startswith("activities"):
        return UNHANDLED
    if suffix == ".json" and "summarizedactivities" not in name:
        return UNHANDLED
    if (doc.file_size or 0) > TELEGRAM_LIMIT_MB * 1024 * 1024:
        await message.answer(
            "⚠️ Файл больше 20 МБ Telegram не отдаёт боту. Положите его в "
            f"<code>{_esc(_cfg().import_dir)}</code> и нажмите «Проверить папку».",
            parse_mode="HTML",
        )
        return None

    cfg = _cfg()
    safe_name = re.sub(r"[^\w.\-]", "_", doc.file_name or "garmin.zip")
    target = Path(cfg.import_dir) / f"tg_{message.from_user.id}_{safe_name}"
    status_msg = await message.answer("📥 Загружаю и разбираю Garmin export...")
    try:
        file_info = await message.bot.get_file(doc.file_id)
        await message.bot.download_file(file_info.file_path, destination=str(target))
        result = await asyncio.to_thread(
            _import_sync, target, int(message.from_user.id)
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Garmin document import failed")
        await status_msg.edit_text(
            "❌ Импорт не удался. Убедитесь, что это официальный Garmin ZIP/FIT."
            f"\n<code>{_esc(type(exc).__name__)}</code>",
            parse_mode="HTML",
        )
        return None

    await status_msg.edit_text(
        _format_import_result(result),
        parse_mode="HTML",
        reply_markup=_import_done_kb(),
    )
    await _maybe_send_delta(message, int(message.from_user.id), trigger="import")
    return None


async def _maybe_send_delta(
    message: types.Message, user_id: int, *, trigger: str
) -> None:
    """Show a confirmed adaptation prompt only when a threshold was crossed."""
    conn = _connect()
    try:
        delta = compute_delta(conn, user_id)
        log_delta(conn, user_id, delta, trigger=trigger)
    except Exception:  # noqa: BLE001 - delta must not break the import result
        logger.exception("Garmin delta failed")
        return
    finally:
        conn.close()
    if delta.recommendation == "keep":
        return
    await message.answer(
        delta_text(delta),
        reply_markup=_adapt_kb(show_accept=delta.recommendation != "medical"),
        parse_mode="HTML",
    )


def _import_done_kb() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(text="📊 PDF", callback_data="garmin:pdf"),
        types.InlineKeyboardButton(text="🏋️ План", callback_data="garmin:plan"),
    )
    kb.row(types.InlineKeyboardButton(text="📥 Ещё", callback_data="garmin:import"))
    kb.row(types.InlineKeyboardButton(text="🏠 Garmin", callback_data="garmin:main"))
    return kb.as_markup()


@router.callback_query(F.data == "garmin:import:folder")
@allowed_callback
async def cb_import_folder(cb: types.CallbackQuery):
    await cb.answer("Проверяю папку...")
    cfg = _cfg()
    import_root = Path(cfg.import_dir)
    files = sorted(
        path
        for path in import_root.glob("*")
        if path.suffix.lower() in IMPORT_SUFFIXES and path.is_file()
    )
    folders = sorted(
        path
        for path in import_root.glob("*")
        if path.is_dir() and looks_like_full_export(path)
    )
    candidates = files + folders
    if not candidates:
        await cb.message.answer(
            "📂 В папке import нет ZIP/FIT/CSV/TCX/JSON или распакованного "
            "полного экспорта. Скопируйте туда файл и повторите."
        )
        return
    status_msg = await cb.message.answer(
        f"📥 Нашёл объектов: {len(candidates)}. Импортирую..."
    )
    ok = 0
    failed = 0
    days: list[str] = []
    for path in candidates[:50]:
        try:
            result = await asyncio.to_thread(_import_sync, path, _uid(cb))
            if result.status in {"ok", "partial"}:
                ok += 1
                days.extend(result.days)
            else:
                failed += 1
        except Exception:  # noqa: BLE001 - continue with the next file
            logger.exception("Garmin folder import failed for %s", path.name)
            failed += 1
    lines = [
        "✅ <b>Папка обработана</b>",
        f"Успешно: {ok}, ошибок: {failed}",
        f"Дней с данными: {len(set(days))}",
    ]
    if days:
        ordered = sorted(set(days))
        lines.append(f"Период: {_fmt_day(ordered[0])} — {_fmt_day(ordered[-1])}")
    await status_msg.edit_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=_import_done_kb()
    )


# ---------------------------------------------------------------------------
# PDF


@router.callback_query(F.data == "garmin:pdf")
@allowed_callback
async def cb_pdf(cb: types.CallbackQuery):
    await cb.answer()
    kb = InlineKeyboardBuilder()
    for days in REPORT_DAYS:
        kb.button(text=f"{days} дней", callback_data=f"garmin:report:{days}")
    kb.adjust(2)
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="garmin:main"))
    await cb.message.edit_text(
        "📊 <b>PDF-отчёт</b>\nВыберите период. В отчёт входят графики, "
        "таблицы, флаги и локальный ИИ-разбор.",
        reply_markup=kb.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("garmin:report:"))
@allowed_callback
async def cb_report(cb: types.CallbackQuery):
    try:
        days = int(cb.data.rsplit(":", 1)[1])
    except ValueError:
        await cb.answer("Неверный период", show_alert=True)
        return
    if days not in REPORT_DAYS:
        await cb.answer("Неверный период", show_alert=True)
        return
    await cb.answer("Готовлю отчёт...")
    await _send_report(cb.message, _uid(cb), days)


@router.message(Command("garmin_report"))
@allowed_only
async def cmd_report(message: types.Message):
    parts = (message.text or "").split()
    days = 30
    if len(parts) > 1:
        try:
            days = int(parts[1])
        except ValueError:
            days = 30
    if days not in REPORT_DAYS:
        await message.answer("Период: 7, 30, 90 или 365 дней.")
        return
    await _send_report(message, _uid(message), days)


# ---------------------------------------------------------------------------
# summaries


def _readiness_text(report, checkin, events=None) -> str:
    readiness = assess_readiness(report, checkin=checkin, events=events)
    lines = [
        f"{readiness.emoji} <b>Готовность: {_esc(readiness.level)}</b>",
        "",
        _esc(readiness.advice),
    ]
    if readiness.reasons:
        lines.append("")
        lines.append("Почему:")
        lines.extend(f"• {_esc(reason)}" for reason in readiness.reasons)
    corrs = getattr(report, "event_correlations", None) or []
    if corrs:
        lines.append("")
        lines.append("🔗 <b>Связь состояния и метрик:</b>")
        for corr in corrs[-3:]:
            lines.append(f"• {_esc(corr.get('summary', ''))}")
    return "\n".join(lines)


@router.callback_query(F.data == "garmin:today")
@allowed_callback
async def cb_today(cb: types.CallbackQuery):
    await cb.answer()
    await _send_today(cb.message, _uid(cb))


@router.message(Command("garmin_today"))
@allowed_only
async def cmd_today(message: types.Message):
    await _send_today(message, _uid(message))


async def _send_today(message: types.Message, user_id: int) -> None:
    cfg = _cfg()
    conn = init_db(cfg.db_path)
    try:
        report = build_report(conn, user_id=user_id, days=7)
        checkins = recent_checkins(conn, user_id, limit=1)
        stored = _profile(conn, user_id)
        events = _recent_events(conn, user_id)
        plan = latest_plan(conn, user_id)
        latest_checkin = checkins[0] if checkins else None
        assessment = assess_safety(
            checkin=latest_checkin,
            profile=stored.profile if stored is not None else None,
            events=events,
            report=report,
        )
    finally:
        conn.close()
    if assessment.blocked:
        await message.answer(
            safety_text(assessment),
            reply_markup=_safety_kb(),
            parse_mode="HTML",
        )
        return
    text = _readiness_text(report, latest_checkin, events=events)
    if assessment.warnings:
        text += "\n\n" + safety_text(assessment)
    today = date.today().isoformat()
    if plan is not None:
        sessions = [
            session
            for week in plan.weeks
            for session in week.sessions
            if session.date == today
        ]
        if sessions:
            session = sessions[0]
            text += (
                f"\n\n📅 Сегодня по плану: <b>{_esc(session.title)}</b> · "
                f"{session.duration_min or 0} мин"
            )
            if session.intensity:
                text += f"\n{_esc(session.intensity)}"
        else:
            text += "\n\n📅 На сегодня в плане нет сессии."
    await message.answer(text, reply_markup=_back_kb(), parse_mode="HTML")


@router.callback_query(F.data == "garmin:sleep")
@allowed_callback
async def cb_sleep(cb: types.CallbackQuery):
    await cb.answer()
    await _send_sleep(cb.message, _uid(cb))


@router.message(Command("garmin_sleep"))
@allowed_only
async def cmd_sleep(message: types.Message):
    await _send_sleep(message, _uid(message))


async def _send_sleep(message: types.Message, user_id: int) -> None:
    cfg = _cfg()
    conn = init_db(cfg.db_path)
    try:
        report = build_report(conn, user_id=user_id, days=7)
    finally:
        conn.close()
    sleep = report.series["sleep_hours"]
    recent = [value for value in sleep.values if value is not None]
    if not recent:
        await message.answer(
            "🌙 Данных о сне нет. Импортируйте Garmin wellness export.",
            reply_markup=_back_kb(),
        )
        return
    debt = sum(max(0.0, 7.5 - value) for value in recent)
    lines = [
        "🌙 <b>Сон за 7 дней</b>",
        f"Средний: {sleep.avg_7d:.1f} ч · последний: {sleep.latest:.1f} ч",
        f"Ночей короче 6 ч: {sum(1 for value in recent if value < 6)}",
        f"Долг сна к цели 7,5 ч: {debt:.1f} ч",
    ]
    if sleep.baseline is not None:
        lines.append(f"Baseline: {sleep.baseline:.1f} ч")
    await message.answer("\n".join(lines), reply_markup=_back_kb(), parse_mode="HTML")


@router.callback_query(F.data == "garmin:week")
@allowed_callback
async def cb_week(cb: types.CallbackQuery):
    await cb.answer()
    await _send_week(cb.message, _uid(cb))


@router.message(Command("garmin_week"))
@allowed_only
async def cmd_week(message: types.Message):
    await _send_week(message, _uid(message))


async def _send_week(message: types.Message, user_id: int) -> None:
    cfg = _cfg()
    conn = init_db(cfg.db_path)
    try:
        report = build_report(conn, user_id=user_id, days=14)
    finally:
        conn.close()
    lines = ["📈 <b>Последние недели</b>"]
    for week in report.weekly[-3:]:
        lines.append("")
        lines.append(f"<b>{_fmt_day(week.week_start)} — {_fmt_day(week.week_end)}</b>")
        parts = []
        if week.sleep_hours is not None:
            parts.append(f"сон {week.sleep_hours:.1f} ч")
        if week.hrv is not None:
            parts.append(f"HRV {week.hrv:.0f}")
        if week.resting_hr is not None:
            parts.append(f"пульс {week.resting_hr:.0f}")
        if week.steps is not None:
            parts.append(f"шаги {week.steps:.0f}")
        lines.append(" · ".join(parts) if parts else "нет данных")
        lines.append(
            f"Тренировок: {week.activities}, минут: {week.training_min:.0f}"
        )
    await message.answer("\n".join(lines), reply_markup=_back_kb(), parse_mode="HTML")


def _adapt_kb(show_accept: bool = True) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if show_accept:
        kb.row(
            types.InlineKeyboardButton(
                text="✅ Принять адаптацию", callback_data="garmin:adapt:accept"
            ),
            types.InlineKeyboardButton(
                text="✏️ Оставить план", callback_data="garmin:adapt:keep"
            ),
        )
        kb.row(
            types.InlineKeyboardButton(
                text="🩺 Обсудить с врачом", callback_data="garmin:doctor"
            )
        )
    kb.row(
        types.InlineKeyboardButton(text="📊 PDF", callback_data="garmin:pdf"),
        types.InlineKeyboardButton(text="🏋️ План", callback_data="garmin:plan"),
    )
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="garmin:main"))
    return kb.as_markup()


@router.callback_query(F.data == "garmin:changes")
@allowed_callback
async def cb_changes(cb: types.CallbackQuery):
    await cb.answer()
    await _send_changes(cb.message, _uid(cb), edit=True)


@router.message(Command("garmin_changes", "garmin_adapt"))
@allowed_only
async def cmd_changes(message: types.Message):
    await _send_changes(message, _uid(message), edit=False)


async def _send_changes(
    message: types.Message, user_id: int, *, edit: bool = False
) -> None:
    conn = _connect()
    try:
        delta = compute_delta(conn, user_id)
        log_delta(conn, user_id, delta, trigger="manual")
    finally:
        conn.close()
    text = delta_text(delta)
    markup = _adapt_kb(show_accept=delta.recommendation not in {"keep", "medical"})
    if delta.recommendation == "medical":
        text += "\n\n🛑 Автоматическая адаптация заблокирована: нужен врач."
    if edit:
        await message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data.in_({"garmin:adapt:accept", "garmin:adapt:keep"}))
@allowed_callback
async def cb_adapt(cb: types.CallbackQuery):
    user_id = _uid(cb)
    accept = cb.data.endswith("accept")
    await cb.answer("Применяю..." if accept else "Оставляю план")
    errors: list[str] = []
    conn = _connect()
    try:
        delta = compute_delta(conn, user_id)
        if delta.recommendation == "medical":
            log_delta(conn, user_id, delta, trigger="manual", applied=False)
            await cb.message.edit_text(
                "🛑 Есть красный флаг или боль ≥4/10. План не меняю: "
                "остановитесь и обратитесь к врачу.",
                reply_markup=_back_kb(),
            )
            return
        if not accept or delta.recommendation == "keep":
            log_delta(conn, user_id, delta, trigger="manual", applied=False)
            await cb.message.edit_text(
                "✏️ План оставлен без изменений. Запись добавлена в журнал адаптации.",
                reply_markup=_back_kb(),
            )
            return
        stored = _profile(conn, user_id)
        plan = latest_plan(conn, user_id)
        if stored is None or plan is None:
            await cb.message.edit_text(
                "Сначала постройте план, затем адаптацию можно будет применить.",
                reply_markup=_back_kb(),
            )
            return
        adapted = apply_delta(plan, delta)
        errors = validate_plan(adapted, stored.profile)
        save_plan(
            conn,
            user_id,
            adapted,
            profile_version=stored.version,
            validation_errors=errors,
            status="accepted",
        )
        log_delta(conn, user_id, delta, trigger="manual", applied=True)
        garmin_last_plan[user_id] = adapted.plan_id
    finally:
        conn.close()
    text = delta_text(delta) + "\n\n✅ План адаптирован на ближайшие 3 дня."
    if errors:
        text += "\n⚠️ Валидатор: " + "; ".join(_esc(e) for e in errors[:3])
    await cb.message.edit_text(text, reply_markup=_back_kb(), parse_mode="HTML")


@router.message(Command("garmin_last"))
@allowed_only
async def cmd_last(message: types.Message):
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT activity_type, name, start_time, duration_min, distance_m,"
            " avg_hr, training_load FROM garmin_activities"
            " WHERE user_id = ? ORDER BY start_time DESC LIMIT 1",
            (_uid(message),),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        await message.answer("🏃 Тренировок пока нет.", reply_markup=_back_kb())
        return
    lines = [
        "🏃 <b>Последняя тренировка</b>",
        f"{_fmt_day(row['start_time'])} · {_esc(row['activity_type'] or '—')}",
        f"{_esc(row['name'] or '')}",
    ]
    if row["duration_min"] is not None:
        lines.append(f"Длительность: {row['duration_min']:.0f} мин")
    if row["distance_m"] is not None:
        lines.append(f"Дистанция: {row['distance_m'] / 1000:.2f} км")
    if row["avg_hr"] is not None:
        lines.append(f"Средний пульс: {row['avg_hr']:.0f}")
    await message.answer("\n".join(lines), reply_markup=_back_kb(), parse_mode="HTML")


# ---------------------------------------------------------------------------
# profile wizard


@router.callback_query(F.data == "garmin:profile")
@allowed_callback
async def cb_profile(cb: types.CallbackQuery):
    await cb.answer()
    conn = _connect()
    try:
        stored = _profile(conn, _uid(cb))
    finally:
        conn.close()
    if stored is None:
        await _profile_screen1(cb.message, _uid(cb), edit=True)
        return
    profile = stored.profile
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="✏️ Заполнить заново", callback_data="garmin:profile:new"
        )
    )
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="garmin:main"))
    await cb.message.edit_text(
        "🧩 <b>Профиль</b>\n"
        f"Цель: {PROFILE_GOALS.get(profile.primary_goal, profile.primary_goal)}\n"
        f"Опыт: {EXPERIENCE.get(profile.experience, profile.experience)}\n"
        f"Горизонт: {profile.horizon_weeks} недель\n"
        f"Оборудование: {', '.join(profile.equipment) or '—'}\n"
        f"Препараты: {', '.join(m.name for m in profile.medications) or 'не указаны'}\n"
        f"Версия: {stored.version} · обновлён: {_esc(stored.updated_at[:16])}",
        reply_markup=kb.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "garmin:profile:new")
@allowed_callback
async def cb_profile_new(cb: types.CallbackQuery):
    await cb.answer()
    garmin_profile_draft.pop(_uid(cb), None)
    await _profile_screen1(cb.message, _uid(cb), edit=True)


async def _profile_screen1(message: types.Message, user_id: int, *, edit: bool) -> None:
    _draft(user_id)
    kb = InlineKeyboardBuilder()
    for key, label in PROFILE_GOALS.items():
        kb.button(text=label, callback_data=f"garmin:profile:goal:{key}")
    kb.adjust(2)
    kb.row(types.InlineKeyboardButton(text="⬅️ Отмена", callback_data="garmin:main"))
    text = (
        "🧩 <b>Профиль · шаг 1/3</b>\n"
        "Выберите главную цель. Потом уточним опыт и расписание."
    )
    if edit:
        await _safe_edit(message, text, reply_markup=kb.as_markup(), parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("garmin:profile:goal:"))
@allowed_callback
async def cb_profile_goal(cb: types.CallbackQuery):
    await cb.answer()
    goal = cb.data.rsplit(":", 1)[1]
    if goal not in PROFILE_GOALS:
        return
    draft = _draft(_uid(cb))
    draft["primary_goal"] = goal
    draft["secondary_goals"] = [
        item
        for item in ("strength", "cycling", "health", "fat_loss", "mixed")
        if item != goal
    ][:3]
    kb = InlineKeyboardBuilder()
    for key, label in EXPERIENCE.items():
        kb.button(text=label, callback_data=f"garmin:profile:exp:{key}")
    kb.adjust(2)
    await cb.message.edit_text(
        "🧩 <b>Профиль · шаг 1/3</b>\nКакой у вас опыт тренировок?",
        reply_markup=kb.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("garmin:profile:exp:"))
@allowed_callback
async def cb_profile_exp(cb: types.CallbackQuery):
    await cb.answer()
    exp = cb.data.rsplit(":", 1)[1]
    if exp not in EXPERIENCE:
        return
    draft = _draft(_uid(cb))
    draft["experience"] = exp
    await _profile_screen2(cb.message, _uid(cb))


async def _profile_screen2(message: types.Message, user_id: int) -> None:
    draft = _draft(user_id)
    kb = InlineKeyboardBuilder()
    for days in (3, 4, 5):
        kb.button(
            text=f"{days} дня" if days < 5 else "5 дней",
            callback_data=f"garmin:profile:days:{days}",
        )
    kb.adjust(3)
    for key, label in EQUIPMENT.items():
        mark = "✅ " if key in draft["equipment"] else ""
        kb.button(text=f"{mark}{label}", callback_data=f"garmin:profile:equip:{key}")
    kb.adjust(3, 3)
    kb.row(
        types.InlineKeyboardButton(
            text="😌 Низкий стресс", callback_data="garmin:profile:stress:low"
        ),
        types.InlineKeyboardButton(
            text="😐 Средний", callback_data="garmin:profile:stress:medium"
        ),
    )
    kb.row(
        types.InlineKeyboardButton(
            text="😰 Высокий", callback_data="garmin:profile:stress:high"
        )
    )
    kb.row(types.InlineKeyboardButton(text="➡️ Далее", callback_data="garmin:profile:next3"))
    await _safe_edit(
        message,
        "🧩 <b>Профиль · шаг 2/3</b>\n"
        f"Дней в неделю: {draft['availability_days']} · "
        f"стресс: {draft['stress_level']}\n"
        "Отметьте оборудование и нажмите «Далее».",
        reply_markup=kb.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("garmin:profile:days:"))
@allowed_callback
async def cb_profile_days(cb: types.CallbackQuery):
    await cb.answer()
    try:
        days = int(cb.data.rsplit(":", 1)[1])
    except ValueError:
        return
    _draft(_uid(cb))["availability_days"] = days
    await _profile_screen2(cb.message, _uid(cb))


@router.callback_query(F.data.startswith("garmin:profile:equip:"))
@allowed_callback
async def cb_profile_equip(cb: types.CallbackQuery):
    await cb.answer()
    key = cb.data.rsplit(":", 1)[1]
    draft = _draft(_uid(cb))
    equipment = list(draft.get("equipment", []))
    if key in equipment:
        equipment.remove(key)
    elif key in EQUIPMENT:
        equipment.append(key)
    draft["equipment"] = equipment
    await _profile_screen2(cb.message, _uid(cb))


@router.callback_query(F.data.startswith("garmin:profile:stress:"))
@allowed_callback
async def cb_profile_stress(cb: types.CallbackQuery):
    await cb.answer()
    value = cb.data.rsplit(":", 1)[1]
    if value not in {"low", "medium", "high"}:
        return
    _draft(_uid(cb))["stress_level"] = value
    await _profile_screen2(cb.message, _uid(cb))


@router.callback_query(F.data == "garmin:profile:next3")
@allowed_callback
async def cb_profile_next3(cb: types.CallbackQuery):
    await cb.answer()
    await _profile_screen3(cb.message, _uid(cb))


async def _profile_screen3(message: types.Message, user_id: int) -> None:
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="✏️ Ввести препараты вручную",
            callback_data="garmin:profile:meds:other",
        )
    )
    conn = _connect()
    try:
        stored = _profile(conn, user_id)
    finally:
        conn.close()
    if stored is not None and stored.profile.medications:
        kb.row(
            types.InlineKeyboardButton(
                text="🔒 Оставить текущие",
                callback_data="garmin:profile:meds:keep",
            )
        )
    kb.row(
        types.InlineKeyboardButton(
            text="Не указывать / Очистить",
            callback_data="garmin:profile:meds:none",
        )
    )
    await _safe_edit(
        message,
        "🧩 <b>Профиль · шаг 3/3</b>\n"
        "Препараты и добавки вводятся только вручную и хранятся локально в "
        "зашифрованном виде (Keychain + Fernet). ИИ учитывает их влияние на "
        "архитектуру сна, эмоциональное состояние, ВСР и пульс покоя.\n"
        "Бот не меняет дозы и не отменяет препараты.\n\n"
        "Выберите действие:",
        reply_markup=kb.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("garmin:profile:meds:"))
@allowed_callback
async def cb_profile_meds(cb: types.CallbackQuery):
    kind = cb.data.rsplit(":", 1)[1]
    user_id = _uid(cb)
    draft = _draft(user_id)
    if kind == "other":
        garmin_text_state[user_id] = "profile_meds"
        await cb.answer()
        await cb.message.answer(
            "✏️ Напишите принимаемые препараты или добавки через запятую "
            "(название и, по желанию, время приёма).\n"
            "🔒 Ваше сообщение будет автоматически удалено из чата после чтения "
            "и сохранено локально в зашифрованном профиле.\n"
            "/cancel — отмена."
        )
        return
    if kind == "keep":
        conn = _connect()
        try:
            stored = _profile(conn, user_id)
        finally:
            conn.close()
        draft["medications"] = (
            list(stored.profile.medications) if stored is not None else []
        )
    else:
        draft["medications"] = []
    await cb.answer()
    await _profile_preview(cb.message, user_id)


async def _profile_preview(
    message: types.Message, user_id: int, *, edit: bool = True
) -> None:
    draft = _draft(user_id)
    profile = _profile_from_draft(draft)
    layer = build_layer(profile)
    meds = ", ".join(entry.name for entry in layer.entries) or "не указаны"
    text = (
        "🧩 <b>Проверьте профиль</b>\n"
        f"Цель: {PROFILE_GOALS.get(profile.primary_goal, profile.primary_goal)}\n"
        f"Опыт: {EXPERIENCE.get(profile.experience, profile.experience)}\n"
        f"Дней в неделю: {draft.get('availability_days', 3)}\n"
        f"Оборудование: {', '.join(profile.equipment) or '—'}\n"
        f"Стресс: {profile.stress_level}\n"
        f"Препараты: {_esc(meds)}\n\n"
        "Профиль хранится зашифрованным локально."
    )
    if edit:
        await _safe_edit(
            message, text, reply_markup=_profile_summary_kb(), parse_mode="HTML"
        )
    else:
        await message.answer(
            text, reply_markup=_profile_summary_kb(), parse_mode="HTML"
        )


@router.callback_query(F.data == "garmin:profile:save")
@allowed_callback
async def cb_profile_save(cb: types.CallbackQuery):
    user_id = _uid(cb)
    draft = garmin_profile_draft.get(user_id)
    if draft is None:
        await cb.answer("Профиль устарел, начните заново", show_alert=True)
        return
    await cb.answer("Сохраняю...")
    profile = _profile_from_draft(draft)
    conn = _connect()
    try:
        stored = save_profile(conn, user_id, profile)
    except GarminError as exc:
        logger.exception("Cannot save Garmin profile")
        await cb.message.answer(
            "❌ Не удалось сохранить профиль. Проверьте доступ к Keychain "
            f"или GARMIN_ENCRYPTION_KEY.\n<code>{_esc(type(exc).__name__)}</code>",
            parse_mode="HTML",
        )
        return
    finally:
        conn.close()
    garmin_profile_draft.pop(user_id, None)
    await _safe_edit(
        cb.message,
        "✅ Профиль сохранён.\n"
        f"Версия {stored.version}. Теперь можно построить план.",
        reply_markup=_back_kb(),
    )


@router.message(Command("garmin_profile"))
@allowed_only
async def cmd_profile(message: types.Message):
    await _profile_screen1(message, _uid(message), edit=False)


# ---------------------------------------------------------------------------
# medications / doctor sheet


@router.callback_query(F.data == "garmin:meds")
@allowed_callback
async def cb_meds(cb: types.CallbackQuery):
    await cb.answer()
    await _send_meds(cb.message, _uid(cb))


@router.message(Command("garmin_meds"))
@allowed_only
async def cmd_meds(message: types.Message):
    await _send_meds(message, _uid(message))


def _meds_kb(has_meds: bool) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="✏️ Ввести / изменить вручную",
            callback_data="garmin:meds:edit",
        )
    )
    if has_meds:
        kb.row(
            types.InlineKeyboardButton(
                text="🤖 ИИ-анализ: сон и эмоции",
                callback_data="garmin:meds:ai",
            ),
            types.InlineKeyboardButton(
                text="🗑 Очистить список",
                callback_data="garmin:meds:clear",
            ),
        )
    kb.row(
        types.InlineKeyboardButton(
            text="🩺 Вопросы врачу", callback_data="garmin:doctor"
        ),
        types.InlineKeyboardButton(
            text="🧩 Профиль", callback_data="garmin:profile"
        ),
    )
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="garmin:main"))
    return kb.as_markup()


async def _send_meds(
    message: types.Message,
    user_id: int,
    *,
    edit: bool = False,
    prefix: str = "",
) -> None:
    conn = _connect()
    try:
        stored = _profile(conn, user_id)
    finally:
        conn.close()
    has_meds = bool(stored is not None and stored.profile.medications)
    markup = _meds_kb(has_meds)
    if not has_meds:
        text = (
            (f"{prefix}\n\n" if prefix else "")
            + "💊 <b>Препараты и добавки не указаны</b>\n\n"
            "Вы можете ввести их вручную (список шифруется локально, сообщение "
            "удаляется из чата). ИИ будет учитывать их влияние на архитектуру "
            "сна, эмоциональное состояние, уровень стресса, ВСР и пульс покоя.\n"
            "Дозы и отмену обсуждайте только с врачом."
        )
        if edit:
            await _safe_edit(message, text, reply_markup=markup, parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=markup, parse_mode="HTML")
        return
    assert stored is not None
    layer = build_layer(stored.profile)
    lines: list[str] = []
    if prefix:
        lines.extend([prefix, ""])
    lines.extend(
        [
            "💊 <b>Препараты, сон и эмоциональное состояние</b>",
            _esc(layer.summary),
        ]
    )
    if layer.sleep_effects:
        lines.append("")
        lines.append("🌙 <b>Влияние на сон:</b>")
        lines.extend(f"• {_esc(item)}" for item in layer.sleep_effects)
    if layer.emotional_effects:
        lines.append("")
        lines.append("🧠 <b>Эмоциональное состояние и ВНС:</b>")
        lines.extend(f"• {_esc(item)}" for item in layer.emotional_effects)
    if layer.safety_flags:
        lines.append("")
        lines.append("⚠️ <b>Предосторожности для тренировок:</b>")
        lines.extend(f"• {_esc(flag.text)}" for flag in layer.safety_flags)
    lines.append("")
    lines.append("🔒 Хранится зашифрованным локально. Бот не меняет дозы и не отменяет препараты.")
    text = "\n".join(lines)
    if edit:
        await _safe_edit(message, text, reply_markup=markup, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data == "garmin:meds:edit")
@allowed_callback
async def cb_meds_edit(cb: types.CallbackQuery):
    user_id = _uid(cb)
    garmin_text_state[user_id] = "meds_direct"
    await cb.answer()
    await cb.message.answer(
        "✏️ Введите названия препаратов или добавок через запятую.\n"
        "🔒 Сообщение будет сразу удалено из чата после чтения и сохранено в "
        "зашифрованном локальном профиле.\n"
        "/cancel — отмена."
    )


@router.callback_query(F.data == "garmin:meds:clear")
@allowed_callback
async def cb_meds_clear(cb: types.CallbackQuery):
    user_id = _uid(cb)
    await cb.answer("Очищаю список препаратов...")
    conn = _connect()
    try:
        stored = _profile(conn, user_id)
        if stored is not None:
            updated = stored.profile.model_copy(update={"medications": []})
            save_profile(conn, user_id, updated)
    finally:
        conn.close()
    await _send_meds(
        cb.message,
        user_id,
        edit=True,
        prefix="🗑 Список препаратов очищен.",
    )


@router.callback_query(F.data == "garmin:meds:ai")
@allowed_callback
async def cb_meds_ai(cb: types.CallbackQuery):
    user_id = _uid(cb)
    await cb.answer("Анализирую влияние на сон и эмоции...")
    cfg = _cfg()
    status_msg = await cb.message.answer(
        "🤖 <i>Анализирую связь препаратов, сна, ВСР и эмоционального состояния...</i>",
        parse_mode="HTML",
    )
    conn = _connect()
    try:
        report = build_report(conn, user_id=user_id, days=14)
        meds = _med_names(conn, user_id)
        coach = await generate_causes_async(
            conn,
            report,
            model=cfg.ai_model,
            timeout=min(cfg.ai_timeout, 75.0),
            ai_enabled=cfg.ai_enabled,
            medications=meds,
            fallback_model=cfg.ai_fallback_model,
            fallback_timeout=min(cfg.ai_fallback_timeout, 60.0),
            use_cache=False,
        )
    finally:
        conn.close()
    lines = [
        "🤖 <b>ИИ-разбор: препараты, сон и эмоциональное состояние (14 дней)</b>",
        "",
        _esc(coach_text(coach)),
    ]
    await _safe_edit(
        status_msg,
        "\n".join(lines),
        reply_markup=_meds_kb(bool(meds)),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "garmin:doctor")
@allowed_callback
async def cb_doctor(cb: types.CallbackQuery):
    await cb.answer()
    conn = _connect()
    try:
        stored = _profile(conn, _uid(cb))
    finally:
        conn.close()
    layer = build_layer(stored.profile) if stored else build_layer(UserProfile())
    lines = ["🩺 <b>Вопросы врачу</b>", ""]
    lines.extend(f"• {_esc(question)}" for question in doctor_questions(layer))
    lines.append("")
    lines.append(
        "Красные флаги: боль в груди, обморок, выраженная одышка, "
        "спутанность/тремор/лихорадка, судороги, боль ≥4/10, "
        "суицидальные мысли. В этих случаях — стоп и срочно к врачу."
    )
    lines.append("")
    lines.append("Это не диагноз и не назначение.")
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="📄 PDF для врача", callback_data="garmin:doctor:pdf"
        )
    )
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="garmin:main"))
    await cb.message.answer(
        "\n".join(lines), reply_markup=kb.as_markup(), parse_mode="HTML"
    )


@router.callback_query(F.data == "garmin:doctor:pdf")
@allowed_callback
async def cb_doctor_pdf(cb: types.CallbackQuery):
    await cb.answer("Собираю PDF...")
    user_id = _uid(cb)
    cfg = _cfg()
    conn = _connect()
    try:
        stored = _profile(conn, user_id)
        plan = latest_plan(conn, user_id)
        checkins = recent_checkins(conn, user_id, limit=30)
        events = _recent_events(conn, user_id, limit=30)
    finally:
        conn.close()
    if stored is None:
        await cb.message.answer(
            "Сначала заполните профиль — без него doctor sheet будет пустым.",
            reply_markup=_back_kb(),
        )
        return
    status_msg = await cb.message.answer("📄 Собираю doctor sheet...")
    try:
        output = (
            Path(cfg.report_dir)
            / f"garmin_{user_id}_doctor_{date.today().isoformat()}.pdf"
        )
        pdf = await asyncio.to_thread(
            build_doctor_pdf,
            stored.profile,
            output,
            plan=plan,
            checkins=checkins,
            events=events,
        )
        await status_msg.delete()
        await cb.message.answer_document(
            types.FSInputFile(pdf),
            caption="📄 Doctor sheet: препараты, симптомы и вопросы врачу.",
        )
    except Exception as exc:  # noqa: BLE001 - user-facing error
        logger.exception("Garmin doctor PDF failed")
        await status_msg.edit_text(
            "❌ Не удалось собрать doctor sheet. Попробуйте ещё раз.\n"
            f"<code>{_esc(type(exc).__name__)}</code>",
            parse_mode="HTML",
        )


# ---------------------------------------------------------------------------
# check-in


@router.callback_query(F.data == "garmin:checkin")
@allowed_callback
async def cb_checkin(cb: types.CallbackQuery):
    await cb.answer()
    await _checkin_screen(cb.message, edit=True)


@router.message(Command("garmin_checkin"))
@allowed_only
async def cmd_checkin(message: types.Message):
    await _checkin_screen(message, edit=False)


async def _checkin_screen(message: types.Message, *, edit: bool) -> None:
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="🟢 Всё ок", callback_data="garmin:checkin:ok"
        ),
        types.InlineKeyboardButton(
            text="🟡 Устал", callback_data="garmin:checkin:tired"
        ),
    )
    kb.row(
        types.InlineKeyboardButton(
            text="🔴 Плохо / болит", callback_data="garmin:checkin:bad"
        )
    )
    kb.row(
        types.InlineKeyboardButton(
            text="✏️ Ввести вручную", callback_data="garmin:checkin:manual"
        )
    )
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="garmin:main"))
    text = (
        "📅 <b>Утренний чек-ин</b>\n"
        "Как самочувствие? Ответ влияет только на совет на сегодня."
    )
    if edit:
        await message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("garmin:checkin:"))
@allowed_callback
async def cb_checkin_choice(cb: types.CallbackQuery):
    choice = cb.data.rsplit(":", 1)[1]
    user_id = _uid(cb)
    if choice == "manual":
        garmin_text_state[user_id] = "checkin"
        await cb.answer()
        await cb.message.answer(
            "Напишите в формате: <code>сон 6.5, боль 2, усталость 4, "
            "стресс 3, настроение 3</code>\n/cancel — отмена.",
            parse_mode="HTML",
        )
        return
    presets = {
        "ok": (7.5, 4, 1, 0, 4, 2),
        "tired": (6.5, 3, 4, 2, 3, 4),
        "bad": (5.5, 2, 6, 5, 2, 5),
    }
    if choice not in presets:
        await cb.answer()
        return
    sleep_h, quality, soreness, pain, mood, stress = presets[choice]
    checkin = Checkin(
        date=date.today().isoformat(),
        kind="morning",
        sleep_h=sleep_h,
        sleep_quality=quality,
        soreness=soreness,
        pain_score=pain,
        mood=mood,
        stress=stress,
    )
    await cb.answer("Сохраняю...")
    await _save_and_show_checkin(cb.message, user_id, checkin)


async def _save_and_show_checkin(
    message: types.Message,
    user_id: int,
    checkin: Checkin,
    *,
    edit: bool = True,
) -> None:
    conn = _connect()
    try:
        save_checkin(conn, user_id, checkin)
        report = build_report(conn, user_id=user_id, days=7)
        stored = _profile(conn, user_id)
        events = _recent_events(conn, user_id)
        assessment = assess_safety(
            checkin=checkin,
            profile=stored.profile if stored is not None else None,
            events=events,
            report=report,
        )
    finally:
        conn.close()

    if assessment.blocked:
        text = safety_text(assessment) + "\n\n✅ Чек-ин сохранён."
        markup = _safety_kb()
    else:
        text = _readiness_text(report, checkin, events=events)
        if assessment.warnings:
            text += "\n\n" + safety_text(assessment)
        text += "\n\n✅ Чек-ин сохранён."
        markup = _back_kb()
    if edit:
        await message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=markup, parse_mode="HTML")


def _parse_checkin(text: str) -> Checkin:
    def number(pattern: str, cast=float):
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None
        try:
            return cast(match.group(1).replace(",", "."))
        except ValueError:
            return None

    return Checkin(
        date=date.today().isoformat(),
        kind="morning",
        sleep_h=number(r"сон\s*([0-9.,]+)"),
        pain_score=number(r"боль\s*(\d+)", int),
        soreness=number(r"усталост\w*\s*(\d+)", int),
        stress=number(r"стресс\s*(\d+)", int),
        mood=number(r"настроени\w*\s*(\d+)", int),
        notes=text[:500],
    )


# ---------------------------------------------------------------------------
# plan


@router.callback_query(F.data == "garmin:plan")
@allowed_callback
async def cb_plan(cb: types.CallbackQuery):
    await cb.answer()
    await _plan_screen(cb.message, _uid(cb))


@router.message(Command("garmin_plan"))
@allowed_only
async def cmd_plan(message: types.Message):
    await _plan_screen(message, _uid(message))


async def _plan_screen(message: types.Message, user_id: int) -> None:
    conn = _connect()
    try:
        stored = _profile(conn, user_id)
        status = data_status(conn, user_id, has_profile=stored is not None)
        plan = latest_plan(conn, user_id)
    finally:
        conn.close()

    if stored is None:
        kb = InlineKeyboardBuilder()
        kb.row(
            types.InlineKeyboardButton(
                text="🧩 Заполнить профиль", callback_data="garmin:profile"
            )
        )
        kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="garmin:main"))
        await message.answer(
            "🏋️ Для плана нужен профиль: цель, опыт и расписание. Это 3 коротких шага.",
            reply_markup=kb.as_markup(),
        )
        return

    kb = InlineKeyboardBuilder()
    if status.ready_for_plan:
        kb.row(
            types.InlineKeyboardButton(
                text="▶️ Построить план", callback_data="garmin:plan:build"
            )
        )
    else:
        kb.row(
            types.InlineKeyboardButton(
                text="⚡ Быстрый план", callback_data="garmin:plan:force"
            )
        )
        kb.row(
            types.InlineKeyboardButton(
                text="📥 Импортировать данные", callback_data="garmin:import"
            )
        )
    if plan is not None:
        kb.row(
            types.InlineKeyboardButton(
                text="📋 Показать последний план", callback_data="garmin:plan:show"
            )
        )
        kb.row(
            types.InlineKeyboardButton(
                text="📄 PDF плана", callback_data="garmin:plan:pdf"
            ),
            types.InlineKeyboardButton(
                text="📈 Обзор недели", callback_data="garmin:plan:review"
            ),
        )
    kb.row(
        types.InlineKeyboardButton(
            text="✏️ Изменить профиль", callback_data="garmin:profile:new"
        ),
        types.InlineKeyboardButton(text="💊 Препараты", callback_data="garmin:meds"),
    )
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="garmin:main"))
    lines = [
        "🏋️ <b>План тренировок</b>",
        f"Цель: {PROFILE_GOALS.get(stored.profile.primary_goal, stored.profile.primary_goal)}",
        f"Горизонт: {stored.profile.horizon_weeks} недель",
        "",
        status_text(status),
    ]
    questions = clarifying_questions(stored.profile, status)
    if questions:
        lines.extend(["", "Уточните, пожалуйста:"])
        lines.extend(f"• {_esc(question)}" for question in questions)
    await message.answer(
        "\n".join(lines), reply_markup=kb.as_markup(), parse_mode="HTML"
    )


@router.callback_query(F.data.in_({"garmin:plan:build", "garmin:plan:force"}))
@allowed_callback
async def cb_plan_build(cb: types.CallbackQuery):
    await cb.answer("Строю план...")
    user_id = _uid(cb)
    conn = _connect()
    try:
        stored = _profile(conn, user_id)
        if stored is None:
            await cb.message.answer("Сначала заполните профиль.")
            return
        status = data_status(conn, user_id, has_profile=True)
        report = build_report(conn, user_id=user_id, days=7)
        checkins = recent_checkins(conn, user_id, limit=1)
        events = _recent_events(conn, user_id)
        assessment = assess_safety(
            checkin=checkins[0] if checkins else None,
            profile=stored.profile,
            events=events,
            report=report,
        )
        if assessment.blocked:
            garmin_last_plan.pop(user_id, None)
            await cb.message.answer(
                safety_text(assessment),
                reply_markup=_safety_kb(),
                parse_mode="HTML",
            )
            return
        plan = build_skeleton(stored.profile, status, events=events)
        plan.safety_flags = merge_safety_flags(plan.safety_flags, assessment)
        errors = validate_plan(plan, stored.profile)
        save_plan(
            conn,
            user_id,
            plan,
            profile_version=stored.version,
            validation_errors=errors,
        )
        garmin_last_plan[user_id] = plan.plan_id
    finally:
        conn.close()

    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(text="✅ Принять", callback_data="garmin:plan:accept"),
        types.InlineKeyboardButton(
            text="🔄 Пересобрать", callback_data="garmin:plan:build"
        ),
    )
    kb.row(
        types.InlineKeyboardButton(text="📄 PDF плана", callback_data="garmin:plan:pdf"),
        types.InlineKeyboardButton(
            text="📈 Обзор недели", callback_data="garmin:plan:review"
        ),
    )
    kb.row(
        types.InlineKeyboardButton(text="🩺 Вопросы врачу", callback_data="garmin:doctor"),
        types.InlineKeyboardButton(text="💊 Препараты", callback_data="garmin:meds"),
    )
    week_buttons = [
        types.InlineKeyboardButton(
            text=f"Неделя {week.week}",
            callback_data=f"garmin:plan:week:{week.week}",
        )
        for week in plan.weeks
    ]
    for start in range(0, len(week_buttons), 3):
        kb.row(*week_buttons[start:start + 3])
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="garmin:main"))
    text = plan_summary(plan) + "\n\n" + first_week_text(plan)
    if errors:
        text += (
            "\n\n⚠️ План упрощён из-за ограничений:\n"
            + "\n".join(f"• {_esc(error)}" for error in errors[:5])
        )
    if assessment.warnings:
        text += "\n\n" + safety_text(assessment)
    await cb.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "garmin:plan:show")
@allowed_callback
async def cb_plan_show(cb: types.CallbackQuery):
    await cb.answer()
    conn = _connect()
    try:
        plan = latest_plan(conn, _uid(cb))
    finally:
        conn.close()
    if plan is None:
        await cb.message.answer("Плана пока нет.")
        return
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(text="✅ Принять", callback_data="garmin:plan:accept"),
        types.InlineKeyboardButton(text="🩺 Врач", callback_data="garmin:doctor"),
    )
    kb.row(
        types.InlineKeyboardButton(text="📄 PDF плана", callback_data="garmin:plan:pdf"),
        types.InlineKeyboardButton(
            text="📈 Обзор недели", callback_data="garmin:plan:review"
        ),
    )
    week_buttons = [
        types.InlineKeyboardButton(
            text=f"Неделя {week.week}",
            callback_data=f"garmin:plan:week:{week.week}",
        )
        for week in plan.weeks
    ]
    for start in range(0, len(week_buttons), 3):
        kb.row(*week_buttons[start:start + 3])
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="garmin:main"))
    await cb.message.answer(
        plan_summary(plan) + "\n\n" + first_week_text(plan),
        reply_markup=kb.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("garmin:plan:week:"))
@allowed_callback
async def cb_plan_week(cb: types.CallbackQuery):
    await cb.answer()
    try:
        week_number = int(cb.data.rsplit(":", 1)[1])
    except ValueError:
        return
    conn = _connect()
    try:
        plan = latest_plan(conn, _uid(cb))
    finally:
        conn.close()
    if plan is None:
        await cb.message.answer("Плана пока нет.")
        return
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="⬅️ К обзору плана", callback_data="garmin:plan:show"
        ),
        types.InlineKeyboardButton(text="🩺 Врач", callback_data="garmin:doctor"),
    )
    await cb.message.answer(
        week_detail_text(plan, week_number),
        reply_markup=kb.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "garmin:plan:accept")
@allowed_callback
async def cb_plan_accept(cb: types.CallbackQuery):
    plan_id = garmin_last_plan.get(_uid(cb))
    conn = _connect()
    try:
        if plan_id is None:
            plan = latest_plan(conn, _uid(cb))
            plan_id = plan.plan_id if plan else None
        if plan_id:
            set_plan_status(conn, plan_id, "accepted")
    finally:
        conn.close()
    if not plan_id:
        await cb.answer("План не найден", show_alert=True)
        return
    await cb.answer("План принят")
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(text="📄 PDF плана", callback_data="garmin:plan:pdf"),
        types.InlineKeyboardButton(
            text="📈 Обзор недели", callback_data="garmin:plan:review"
        ),
    )
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="garmin:main"))
    await cb.message.edit_text(
        "✅ План принят.\n\n"
        "Дальше: ежедневный чек-ин и адаптация при новых данных. "
        "Пропущенную сессию не догоняйте; при плохом сне или боли — отдых.",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "garmin:plan:pdf")
@allowed_callback
async def cb_plan_pdf(cb: types.CallbackQuery):
    await cb.answer("Собираю PDF...")
    user_id = _uid(cb)
    cfg = _cfg()
    conn = _connect()
    try:
        stored = _profile(conn, user_id)
        plan = latest_plan(conn, user_id)
        checkins = recent_checkins(conn, user_id, limit=14)
        events = _recent_events(conn, user_id)
    finally:
        conn.close()
    if stored is None or plan is None:
        await cb.message.answer(
            "Сначала постройте план — тогда появится PDF.",
            reply_markup=_back_kb(),
        )
        return
    status_msg = await cb.message.answer("📄 Собираю PDF плана...")
    try:
        output = (
            Path(cfg.report_dir)
            / f"garmin_{user_id}_plan_{plan.plan_id}.pdf"
        )
        pdf = await asyncio.to_thread(
            build_plan_pdf,
            plan,
            stored.profile,
            output,
            checkins=checkins,
            events=events,
        )
        await status_msg.delete()
        await cb.message.answer_document(
            types.FSInputFile(pdf),
            caption=(
                f"📄 План на {plan.horizon_weeks} недель · "
                f"{PROFILE_GOALS.get(plan.goal, plan.goal)} · "
                f"уверенность: {plan.confidence}"
            ),
        )
    except Exception as exc:  # noqa: BLE001 - user-facing error
        logger.exception("Garmin plan PDF failed")
        await status_msg.edit_text(
            "❌ Не удалось собрать PDF плана. Попробуйте ещё раз.\n"
            f"<code>{_esc(type(exc).__name__)}</code>",
            parse_mode="HTML",
        )


@router.callback_query(F.data == "garmin:plan:review")
@allowed_callback
async def cb_plan_review(cb: types.CallbackQuery):
    await cb.answer("Считаю неделю...")
    await _show_plan_review(cb.message, _uid(cb))


async def _show_plan_review(message: types.Message, user_id: int) -> None:
    conn = _connect()
    try:
        stored = _profile(conn, user_id)
        plan = latest_plan(conn, user_id)
        if stored is None or plan is None:
            await message.answer(
                "Сначала постройте и примите план — тогда появится недельный "
                "обзор.",
                reply_markup=_back_kb(),
            )
            return
        review = build_review(conn, user_id, plan, stored.profile)
        review_id = save_review(conn, user_id, review)
    finally:
        conn.close()

    text = review_text(review)
    kb = InlineKeyboardBuilder()
    if review.decision == "medical":
        text += "\n\n🛑 Автоматическая адаптация заблокирована: нужен врач."
        kb.row(
            types.InlineKeyboardButton(
                text="🩺 Вопросы врачу", callback_data="garmin:doctor"
            )
        )
    elif review.decision in {"keep", "progress"}:
        kb.row(
            types.InlineKeyboardButton(
                text="✅ Понятно",
                callback_data=f"garmin:plan:review:accept:{review_id}",
            )
        )
    else:
        kb.row(
            types.InlineKeyboardButton(
                text="✅ Принять",
                callback_data=f"garmin:plan:review:accept:{review_id}",
            ),
            types.InlineKeyboardButton(
                text="✏️ Оставить как было",
                callback_data=f"garmin:plan:review:keep:{review_id}",
            ),
        )
        kb.row(
            types.InlineKeyboardButton(
                text="🩺 Вопросы врачу", callback_data="garmin:doctor"
            )
        )
    kb.row(
        types.InlineKeyboardButton(
            text="📄 PDF плана", callback_data="garmin:plan:pdf"
        ),
        types.InlineKeyboardButton(text="⬅️ Назад", callback_data="garmin:plan"),
    )
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")


def _review_id(cb: types.CallbackQuery) -> int | None:
    try:
        return int(cb.data.rsplit(":", 1)[1])
    except (ValueError, AttributeError):
        return None


@router.callback_query(F.data.startswith("garmin:plan:review:accept:"))
@allowed_callback
async def cb_plan_review_accept(cb: types.CallbackQuery):
    review_id = _review_id(cb)
    if review_id is None:
        await cb.answer("Некорректный обзор", show_alert=True)
        return
    await cb.answer("Применяю...")
    user_id = _uid(cb)
    errors: list[str] = []
    conn = _connect()
    try:
        row = get_review(conn, review_id)
        if row is None or int(row["user_id"]) != user_id:
            await cb.message.edit_text(
                "Обзор не найден. Постройте новый.",
                reply_markup=_back_kb(),
            )
            return
        review = review_from_row(row)
        if review.decision == "medical":
            mark_review_applied(conn, review_id, applied=False)
            await cb.message.edit_text(
                "🛑 Есть красный флаг или боль ≥4/10. План не меняю: "
                "остановитесь и обратитесь к врачу.",
                reply_markup=_back_kb(),
            )
            return
        stored = _profile(conn, user_id)
        plan = load_plan(conn, review.plan_id) or latest_plan(conn, user_id)
        if stored is None or plan is None:
            await cb.message.edit_text(
                "План не найден. Постройте его заново.",
                reply_markup=_back_kb(),
            )
            return
        if review.decision in {"keep", "progress"}:
            mark_review_applied(conn, review_id, applied=True)
            await cb.message.edit_text(
                "✅ Продолжайте по плану. Прогрессия остаётся недельной; "
                "пропущенную сессию не догоняйте.",
                reply_markup=_back_kb(),
            )
            return
        adapted = apply_review(plan, review)
        errors = validate_plan(adapted, stored.profile)
        save_plan(
            conn,
            user_id,
            adapted,
            profile_version=stored.version,
            validation_errors=errors,
            status="accepted",
        )
        mark_review_applied(conn, review_id, applied=True)
        garmin_last_plan[user_id] = adapted.plan_id
    finally:
        conn.close()

    text = (
        "✅ План адаптирован по недельному обзору.\n\n"
        + plan_summary(adapted)
    )
    if errors:
        text += "\n⚠️ Валидатор: " + "; ".join(_esc(e) for e in errors[:3])
    await cb.message.edit_text(text, reply_markup=_back_kb(), parse_mode="HTML")


@router.callback_query(F.data.startswith("garmin:plan:review:keep:"))
@allowed_callback
async def cb_plan_review_keep(cb: types.CallbackQuery):
    review_id = _review_id(cb)
    if review_id is None:
        await cb.answer("Некорректный обзор", show_alert=True)
        return
    await cb.answer("Оставляю план")
    conn = _connect()
    try:
        row = get_review(conn, review_id)
        if row is not None and int(row["user_id"]) == _uid(cb):
            mark_review_applied(conn, review_id, applied=False)
    finally:
        conn.close()
    await cb.message.edit_text(
        "✏️ План оставлен без изменений. Обзор сохранён в журнале.",
        reply_markup=_back_kb(),
    )


# ---------------------------------------------------------------------------
# illness / events and settings


_ILLNESS_PRESETS: dict[str, tuple[str, str, str]] = {
    "cold": ("illness", "Простуда / ОРВИ (без температуры)", "warning"),
    "fever": ("illness", "Температура / острая инфекция", "critical"),
    "malaise": ("illness", "Слабость / недомогание", "warning"),
    "injury": ("injury", "Травма / локальная боль", "warning"),
    "alcohol": ("alcohol", "Алкоголь / перелёт / нарушение режима", "info"),
    "stress": ("stress", "Высокий бытовой или рабочий стресс", "info"),
}


def _illness_kb(has_active_illness: bool, has_events: bool) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="🤧 Простуда / ОРВИ", callback_data="garmin:illness:add:cold"
        ),
        types.InlineKeyboardButton(
            text="🤒 Температура / Грипп", callback_data="garmin:illness:add:fever"
        ),
    )
    kb.row(
        types.InlineKeyboardButton(
            text="😴 Недомогание", callback_data="garmin:illness:add:malaise"
        ),
        types.InlineKeyboardButton(
            text="🤕 Травма / Боль", callback_data="garmin:illness:add:injury"
        ),
    )
    kb.row(
        types.InlineKeyboardButton(
            text="🍷 Алкоголь / Перелёт", callback_data="garmin:illness:add:alcohol"
        ),
        types.InlineKeyboardButton(
            text="😰 Сильный стресс", callback_data="garmin:illness:add:stress"
        ),
    )
    kb.row(
        types.InlineKeyboardButton(
            text="✏️ Описать своё состояние", callback_data="garmin:illness:custom"
        )
    )
    if has_active_illness:
        kb.row(
            types.InlineKeyboardButton(
                text="✅ Выздоровел (мягкий возврат)",
                callback_data="garmin:illness:recovered",
            )
        )
    kb.row(
        types.InlineKeyboardButton(
            text="🤖 ИИ-разбор связи с метриками",
            callback_data="garmin:illness:ai",
        )
    )
    if has_events:
        kb.row(
            types.InlineKeyboardButton(
                text="🗑 Удалить последнюю запись",
                callback_data="garmin:illness:delete_last",
            )
        )
    kb.row(
        types.InlineKeyboardButton(text="🏋️ К плану", callback_data="garmin:plan"),
        types.InlineKeyboardButton(text="⬅️ Назад", callback_data="garmin:main"),
    )
    return kb.as_markup()


def _illness_screen_data(conn, user_id: int) -> tuple[str, bool, bool]:
    report = build_report(conn, user_id=user_id, days=14)
    rows = conn.execute(
        "SELECT id, date, kind, title, notes, severity FROM garmin_events"
        " WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT 10",
        (int(user_id),),
    ).fetchall()
    has_events = bool(rows)
    has_active_illness = any(
        row["kind"] == "illness" and row["severity"] in {"critical", "warning"}
        for row in rows
    )
    lines = [
        "🤒 <b>Болезнь, простуда и контекст состояния</b>",
        "Отметьте простуду, температуру, недомогание или стресс — ИИ и "
        "алгоритм свяжут их с изменениями HRV, пульса покоя и сна и "
        "скорректируют тренировочный план.",
    ]
    if rows:
        lines.append("")
        lines.append("📋 <b>Последние записи:</b>")
        badge = {"critical": "🔴", "warning": "🟡", "info": "🟢"}
        for row in rows[:6]:
            icon = badge.get(str(row["severity"]), "⚪")
            note_suffix = f" ({_esc(row['notes'])})" if row["notes"] else ""
            lines.append(
                f"{icon} {_fmt_day(row['date'])} · {_esc(row['title'])}{note_suffix}"
            )
    else:
        lines.append("")
        lines.append("📋 Записей о болезни или событиях пока нет.")

    if report.event_correlations:
        lines.append("")
        lines.append("🔗 <b>Связь состояния с метриками Garmin (14 дн.):</b>")
        for corr in report.event_correlations[-4:]:
            lines.append(f"• {_esc(corr['summary'])}")

    if has_active_illness:
        lines.append("")
        lines.append(
            "💡 Когда симптомы пройдут, нажмите «✅ Выздоровел (мягкий возврат)» — "
            "запись сохранится в истории для ИИ-анализа, а план перейдёт в "
            "щадящий режим восстановления."
        )
    return "\n".join(lines), has_active_illness, has_events


async def _show_illness_screen(
    message: types.Message,
    user_id: int,
    *,
    edit: bool = True,
    prefix: str = "",
) -> None:
    conn = _connect()
    try:
        text, has_active, has_events = _illness_screen_data(conn, user_id)
    finally:
        conn.close()
    if prefix:
        text = f"{prefix}\n\n{text}"
    markup = _illness_kb(has_active, has_events)
    if edit:
        await _safe_edit(message, text, reply_markup=markup, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data == "garmin:illness")
@allowed_callback
async def cb_illness(cb: types.CallbackQuery):
    await cb.answer()
    await _show_illness_screen(cb.message, _uid(cb), edit=True)


@router.message(Command("garmin_illness"))
@allowed_only
async def cmd_illness(message: types.Message):
    await _show_illness_screen(message, _uid(message), edit=False)


@router.callback_query(F.data.startswith("garmin:illness:add:"))
@allowed_callback
async def cb_illness_add(cb: types.CallbackQuery):
    preset_key = cb.data.rsplit(":", 1)[1]
    preset = _ILLNESS_PRESETS.get(preset_key)
    if preset is None:
        await cb.answer("Неизвестный вариант", show_alert=True)
        return
    kind, title, severity = preset
    user_id = _uid(cb)
    event = Event(
        date=date.today().isoformat(),
        kind=kind,
        title=title,
        severity=severity,
    )
    conn = _connect()
    try:
        save_event(conn, user_id, event)
    finally:
        conn.close()
    await cb.answer("Записано")
    await _show_illness_screen(
        cb.message,
        user_id,
        edit=True,
        prefix=f"✅ Сохранено на сегодня: <b>{_esc(title)}</b>.",
    )
    await _maybe_send_delta(cb.message, user_id, trigger="illness")


@router.callback_query(F.data == "garmin:illness:custom")
@allowed_callback
async def cb_illness_custom(cb: types.CallbackQuery):
    user_id = _uid(cb)
    garmin_text_state[user_id] = "illness_note"
    await cb.answer()
    await cb.message.answer(
        "✏️ Опишите самочувствие или симптомы одним сообщением "
        "(например: <code>насморк, першит горло, без температуры</code> "
        "или <code>температура 38.2, озноб</code>).\n"
        "/cancel — отмена.",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "garmin:illness:recovered")
@allowed_callback
async def cb_illness_recovered(cb: types.CallbackQuery):
    user_id = _uid(cb)
    conn = _connect()
    try:
        updated = resolve_illness_events(conn, user_id)
    finally:
        conn.close()
    if updated:
        await cb.answer("Статус обновлён: выздоровление")
        prefix = (
            "🌿 <b>Выздоровление отмечено!</b> Активная блокировка снята, "
            "история болезни сохранена для ИИ, а план переведён на мягкий возврат."
        )
    else:
        await cb.answer("Активных записей о болезни не было")
        prefix = "ℹ️ Активных записей о болезни не найдено."
    await _show_illness_screen(cb.message, user_id, edit=True, prefix=prefix)


@router.callback_query(F.data == "garmin:illness:delete_last")
@allowed_callback
async def cb_illness_delete_last(cb: types.CallbackQuery):
    user_id = _uid(cb)
    conn = _connect()
    try:
        deleted = delete_last_event(conn, user_id)
    finally:
        conn.close()
    await cb.answer("Удалено" if deleted else "Записей нет")
    prefix = "🗑 Последняя запись удалена." if deleted else "ℹ️ Записей нет."
    await _show_illness_screen(cb.message, user_id, edit=True, prefix=prefix)


@router.callback_query(F.data == "garmin:illness:ai")
@allowed_callback
async def cb_illness_ai(cb: types.CallbackQuery):
    await cb.answer("Анализирую связь состояния и метрик...")
    user_id = _uid(cb)
    cfg = _cfg()
    status_msg = await cb.message.answer(
        "🤖 <i>Анализирую влияние состояния на HRV, пульс покоя, сон и нагрузку...</i>",
        parse_mode="HTML",
    )
    conn = init_db(cfg.db_path)
    try:
        report = build_report(conn, user_id=user_id, days=14)
        meds = _med_names(conn, user_id)
        coach = await generate_causes_async(
            conn,
            report,
            model=cfg.ai_model,
            timeout=min(cfg.ai_timeout, 75.0),
            ai_enabled=cfg.ai_enabled,
            medications=meds,
            fallback_model=cfg.ai_fallback_model,
            fallback_timeout=min(cfg.ai_fallback_timeout, 60.0),
        )
    finally:
        conn.close()

    lines = ["🤖 <b>ИИ-разбор состояния и показателей (14 дн.)</b>", ""]
    if report.event_correlations:
        lines.append("🔗 <b>Зафиксированные корреляции:</b>")
        for corr in report.event_correlations[-4:]:
            lines.append(f"• {_esc(corr['summary'])}")
        lines.append("")
    lines.append(_esc(coach_text(coach)))
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="🤒 К состоянию", callback_data="garmin:illness"
        ),
        types.InlineKeyboardButton(text="🏋️ К плану", callback_data="garmin:plan"),
    )
    kb.row(types.InlineKeyboardButton(text="⬅️ В меню", callback_data="garmin:main"))
    await status_msg.edit_text(
        "\n".join(lines)[:4000],
        reply_markup=kb.as_markup(),
        parse_mode="HTML",
    )


@router.message(Command("garmin_events"))
@allowed_only
async def cmd_events(message: types.Message):
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT date, kind, title, severity FROM garmin_events"
            " WHERE user_id = ? ORDER BY date DESC LIMIT 10",
            (_uid(message),),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        await message.answer(
            "📅 Событий пока нет.\n"
            "Добавить: <code>/garmin_event 2026-11-03 stress «дедлайн»</code>",
            parse_mode="HTML",
            reply_markup=_back_kb(),
        )
        return
    lines = ["📅 <b>Последние события</b>"]
    for row in rows:
        lines.append(
            f"• {_fmt_day(row['date'])} · {_esc(row['kind'])} · "
            f"{_esc(row['title'])}"
        )
    lines.append("")
    lines.append("Добавить: <code>/garmin_event YYYY-MM-DD kind текст</code>")
    await message.answer(
        "\n".join(lines), reply_markup=_back_kb(), parse_mode="HTML"
    )


@router.message(Command("garmin_event"))
@allowed_only
async def cmd_event(message: types.Message):
    parts = shlex.split(message.text or "")
    if len(parts) < 4:
        await message.answer(
            "Формат: <code>/garmin_event 2026-11-03 stress «дедлайн»</code>\n"
            "Виды: illness, alcohol, travel, stress, injury, med_change, "
            "heat, altitude, menstrual, hard_session, other",
            parse_mode="HTML",
        )
        return
    try:
        day = date.fromisoformat(parts[1])
    except ValueError:
        await message.answer("Дата должна быть YYYY-MM-DD.")
        return
    kind = parts[2]
    allowed = {
        "illness", "alcohol", "travel", "stress", "injury", "med_change",
        "heat", "altitude", "menstrual", "hard_session", "other",
    }
    if kind not in allowed:
        await message.answer("Неизвестный вид события.")
        return
    event = Event(date=day.isoformat(), kind=kind, title=" ".join(parts[3:]))
    conn = _connect()
    try:
        save_event(conn, _uid(message), event)
    finally:
        conn.close()
    await message.answer("✅ Событие сохранено.")


def _settings_text(conn, user_id: int, cfg) -> str:
    retention = retention_status(conn, user_id, default_days=cfg.retention_days)
    if retention.retention_until and (
        retention.days_left is None or retention.days_left >= 0
    ):
        storage = (
            f"{retention.retention_days} дней · до {retention.retention_until}"
        )
    elif retention.retention_until:
        storage = (
            f"{retention.retention_days} дней · срок истёк "
            f"{retention.retention_until}"
        )
    else:
        storage = (
            f"{retention.retention_days} дней · скользящее, "
            f"старше {retention.cutoff} удаляется"
        )
    due = (
        "\n⚠️ Данным исполняется год. Продлите хранение или удалите старое."
        if retention.due
        else ""
    )
    return (
        "⚙️ <b>Garmin: настройки</b>\n"
        f"Данные: <code>{_esc(cfg.data_dir)}</code>\n"
        f"ИИ: {'включён' if cfg.ai_enabled else 'выключен'} · "
        f"модель: <code>{_esc(cfg.ai_model)}</code>\n"
        f"Онлайн-режим: {'включён' if cfg.online_enabled else 'выключен'}\n"
        f"Хранение: {storage}{due}\n\n"
        "Импорт только ручной. Пароль Garmin не хранится."
    )


def _settings_kb() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="🔄 Продлить хранение на год",
            callback_data="garmin:retention:extend",
        )
    )
    kb.row(
        types.InlineKeyboardButton(
            text="🗑 Удалить старше срока",
            callback_data="garmin:retention:purge",
        )
    )
    kb.row(
        types.InlineKeyboardButton(
            text="🗑 Удалить все Garmin-данные", callback_data="garmin:delete"
        )
    )
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="garmin:main"))
    return kb.as_markup()


@router.callback_query(F.data == "garmin:settings")
@allowed_callback
async def cb_settings(cb: types.CallbackQuery):
    await cb.answer()
    cfg = _cfg()
    conn = _connect()
    try:
        text = _settings_text(conn, _uid(cb), cfg)
    finally:
        conn.close()
    await cb.message.edit_text(
        text, reply_markup=_settings_kb(), parse_mode="HTML"
    )


@router.message(Command("garmin_settings"))
@allowed_only
async def cmd_settings(message: types.Message):
    cfg = _cfg()
    conn = _connect()
    try:
        text = _settings_text(conn, _uid(message), cfg)
    finally:
        conn.close()
    await message.answer(text, parse_mode="HTML", reply_markup=_settings_kb())


@router.callback_query(F.data == "garmin:retention:extend")
@allowed_callback
async def cb_retention_extend(cb: types.CallbackQuery):
    cfg = _cfg()
    conn = _connect()
    try:
        current = extend(conn, _uid(cb), days=cfg.retention_days)
        text = _settings_text(conn, _uid(cb), cfg)
    finally:
        conn.close()
    await cb.answer(f"Хранение продлено до {current.retention_until}")
    await cb.message.edit_text(
        text, reply_markup=_settings_kb(), parse_mode="HTML"
    )


@router.callback_query(F.data == "garmin:retention:purge")
@allowed_callback
async def cb_retention_purge(cb: types.CallbackQuery):
    await cb.answer()
    cfg = _cfg()
    conn = _connect()
    try:
        current = retention_status(conn, _uid(cb), default_days=cfg.retention_days)
    finally:
        conn.close()
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="🗑 Да, удалить старое",
            callback_data="garmin:retention:purge:confirm",
        )
    )
    kb.row(
        types.InlineKeyboardButton(
            text="Отмена", callback_data="garmin:settings"
        )
    )
    await cb.message.answer(
        f"Удалить Garmin-данные старше <b>{current.cutoff}</b>? "
        "Профиль, препараты и планы останутся. Это действие необратимо.",
        reply_markup=kb.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "garmin:retention:purge:confirm")
@allowed_callback
async def cb_retention_purge_confirm(cb: types.CallbackQuery):
    await cb.answer("Удаляю...")
    cfg = _cfg()
    conn = _connect()
    try:
        current = retention_status(
            conn, _uid(cb), default_days=cfg.retention_days
        )
        removed = cleanup(
            conn,
            _uid(cb),
            cutoff=current.cutoff,
            raw_dir=cfg.raw_dir,
            charts_dir=cfg.charts_dir,
            report_dir=cfg.report_dir,
        )
        text = _settings_text(conn, _uid(cb), cfg)
    finally:
        conn.close()
    await cb.message.edit_text(
        text
        + f"\n\n🗑 Удалено строк: {removed.total_rows}, "
        f"файлов: {removed.files_removed + removed.pdf_removed}.",
        reply_markup=_settings_kb(),
        parse_mode="HTML",
    )


@router.message(Command("garmin_disconnect"))
@allowed_only
async def cmd_disconnect(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="🗑 Да, удалить", callback_data="garmin:delete:confirm"
        )
    )
    kb.row(types.InlineKeyboardButton(text="Отмена", callback_data="garmin:main"))
    await message.answer(
        "Удалить профиль, импортированные данные, планы и архив? "
        "Это действие необратимо.",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "garmin:delete")
@allowed_callback
async def cb_delete(cb: types.CallbackQuery):
    await cb.answer()
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="🗑 Да, удалить", callback_data="garmin:delete:confirm"
        )
    )
    kb.row(types.InlineKeyboardButton(text="Отмена", callback_data="garmin:main"))
    await cb.message.answer(
        "Удалить профиль, импортированные данные, планы и архив? "
        "Это действие необратимо.",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "garmin:delete:confirm")
@allowed_callback
async def cb_delete_confirm(cb: types.CallbackQuery):
    await cb.answer("Удаляю...")
    user_id = _uid(cb)
    cfg = _cfg()
    conn = init_db(cfg.db_path)
    tables = (
        "garmin_daily",
        "garmin_activities",
        "garmin_extra_metrics",
        "garmin_raw_files",
        "garmin_runs",
        "garmin_analysis_cache",
        "garmin_profile",
        "garmin_events",
        "garmin_checkins",
        "garmin_plan_reviews",
        "garmin_plan_sessions",
        "garmin_training_plans",
        "garmin_settings",
        "garmin_accounts",
        "garmin_mfa_state",
    )
    try:
        for table in tables:
            conn.execute(
                f"DELETE FROM {table} WHERE user_id = ?",  # nosec B608
                (user_id,),
            )
        conn.commit()
    finally:
        conn.close()
    shutil.rmtree(Path(cfg.raw_dir) / str(user_id), ignore_errors=True)
    for path in Path(cfg.report_dir).glob(f"garmin_{user_id}_*.pdf"):
        try:
            path.unlink()
        except OSError:
            pass
    await cb.message.edit_text(
        "🗑 Garmin-данные удалены.",
        reply_markup=_back_kb(),
    )


# ---------------------------------------------------------------------------
# free-text wizard input (must stay before the generic fallback router)


@router.message(F.text)
@allowed_only
async def handle_garmin_text(message: types.Message):
    user_id = _uid(message)
    state = garmin_text_state.get(user_id)
    if not state:
        return UNHANDLED
    text = (message.text or "").strip()
    if text.lower() in {"/cancel", "отмена", "❌ отмена"}:
        garmin_text_state.pop(user_id, None)
        garmin_profile_draft.pop(user_id, None)
        await message.answer("Отменено.", reply_markup=_back_kb())
        return None

    if state == "profile_meds":
        entries = _parse_medication_entries(text)
        _draft(user_id)["medications"] = entries
        garmin_text_state.pop(user_id, None)
        try:
            await message.delete()
        except Exception:  # noqa: BLE001 - best-effort privacy cleanup
            pass
        await _profile_preview(message, user_id, edit=False)
        return None

    if state == "meds_direct":
        entries = _parse_medication_entries(text)
        garmin_text_state.pop(user_id, None)
        try:
            await message.delete()
        except Exception:  # noqa: BLE001 - best-effort privacy cleanup
            pass
        conn = _connect()
        try:
            stored = _profile(conn, user_id)
            base_profile = (
                stored.profile
                if stored is not None
                else _profile_from_draft(_draft(user_id))
            )
            updated_profile = base_profile.model_copy(
                update={"medications": entries}
            )
            save_profile(conn, user_id, updated_profile)
        finally:
            conn.close()
        await _send_meds(
            message,
            user_id,
            edit=False,
            prefix=(
                "✅ Список препаратов сохранён в зашифрованном профиле "
                "(сообщение удалено из чата)."
            ),
        )
        return None

    if state == "checkin":
        checkin = _parse_checkin(text)
        garmin_text_state.pop(user_id, None)
        await _save_and_show_checkin(message, user_id, checkin, edit=False)
        return None

    if state == "illness_note":
        garmin_text_state.pop(user_id, None)
        check = assess_safety(text=text)
        severity = "critical" if check.blocked else "warning"
        event = Event(
            date=date.today().isoformat(),
            kind="illness",
            title=text[:200],
            severity=severity,
        )
        conn = _connect()
        try:
            save_event(conn, user_id, event)
        finally:
            conn.close()
        await _show_illness_screen(
            message,
            user_id,
            edit=False,
            prefix=f"✅ Состояние записано: <b>{_esc(text[:120])}</b>.",
        )
        await _maybe_send_delta(message, user_id, trigger="illness")
        return None

    garmin_text_state.pop(user_id, None)
    return UNHANDLED
