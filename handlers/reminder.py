import logging
import time
import uuid
from datetime import datetime, timedelta

from aiogram import F, Router, types
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import allowed_callback, allowed_only
from services.json_parser import safe_parse_llm_json
from services.ttl_dict import TtlDict
from services.kv_store import get_kv_store
from services.text_formatter import safe_html_format

logger = logging.getLogger("Reminder")
router = Router()
REMINDER_NS = "reminders"

_remind_pending: TtlDict = TtlDict()

REMINDER_KEYWORDS = [
    "напомни",
    "напомнить",
    "напоминание",
    "напомните",
    "remind",
    "reminder",
    "напомн",
]


def _is_reminder(text: str) -> bool:
    t = text.strip().lower()
    return any(k in t for k in REMINDER_KEYWORDS)


PAST_TIME_TEXT = (
    "❌ Это время уже прошло. Укажи будущее время, например «завтра в 15:00»."
)


def _now_local() -> datetime:
    """Текущее локальное время с явным часовым поясом."""
    return datetime.now().astimezone()


def _local_dt(ts: float) -> datetime:
    """Epoch → локальное aware-время для отображения."""
    return datetime.fromtimestamp(ts).astimezone()


def _is_past(ts: float, now_ts: float | None = None) -> bool:
    return ts <= (time.time() if now_ts is None else now_ts)


def _parse_time_description(hour: int, minute: int, day_offset: int) -> float:
    now_local = _now_local()
    target = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if day_offset > 0:
        target += timedelta(days=day_offset)
    return target.timestamp()


def _build_reminder_prompt(
    text: str,
    *,
    time_only: bool = False,
    now: datetime | None = None,
) -> str:
    """Строит prompt для полного разбора напоминания или только времени."""
    current = now or _now_local()
    weekday_ru = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"][current.weekday()]
    context = (
        f"Сегодня: {current.strftime('%Y-%m-%d')} ({weekday_ru})\n"
        f"Сейчас: {current.strftime('%H:%M')}"
    )

    if time_only:
        return (
            f"{context}\n\n"
            "Определи время из сообщения. Верни JSON:\n"
            '{"hour": 16, "minute": 0, "day_offset": 0, '
            '"time_description": "..."}\n'
            "hour=0-23, minute=0-59, day_offset: "
            "0=сегодня, 1=завтра, 2=послезавтра\n"
            f"Сообщение: {text}"
        )

    return (
        f"Ты — парсер напоминаний.\n{context}\n\n"
        "Извлеки из сообщения пользователя текст напоминания и желаемое время.\n"
        "Правила:\n"
        "- hour — часы (0-23), minute — минуты (0-59)\n"
        "- day_offset — 0 = сегодня, 1 = завтра, 2 = послезавтра и т.д.\n"
        "- Если время не указано — hour=null, minute=null, day_offset=0\n"
        "- Если текст не указан — reminder_text = null\n"
        "- time_description — человекочитаемое описание времени "
        "(для подтверждения)\n\n"
        f"Сообщение: {text}\n\n"
        "Верни ТОЛЬКО JSON: "
        '{"reminder_text": "...", "hour": null, "minute": null, '
        '"day_offset": 0, "time_description": "..."}'
    )


async def _request_reminder_json(text: str, *, time_only: bool = False) -> dict:
    """Запрашивает JSON у AI и разбирает его общим json_parser."""
    from services.ai_engine import get_ai_response_async, get_current_ai

    prompt = _build_reminder_prompt(text, time_only=time_only)
    system_prompt = (
        "Ты — JSON-парсер времени. Отвечай только JSON."
        if time_only
        else "Ты — JSON-парсер напоминаний. Отвечай только JSON."
    )
    engine, model = get_current_ai()
    resp = await get_ai_response_async(
        engine,
        model,
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
    )
    parsed = safe_parse_llm_json(resp, expected_type=dict)
    if parsed is None:
        length = len(resp) if isinstance(resp, str) else 0
        logger.warning("[REM] failed to parse JSON (length=%d)", length)
        return {}
    return parsed


async def _parse_reminder(text: str) -> dict:
    parsed = await _request_reminder_json(text)
    if parsed.get("hour") is not None and parsed.get("minute") is not None:
        unix_ts = _parse_time_description(
            hour=int(parsed["hour"]),
            minute=int(parsed["minute"]),
            day_offset=int(parsed.get("day_offset", 0)),
        )
        parsed["unix_timestamp"] = unix_ts
    return parsed


async def _show_reminder_confirm(reply_func, text: str, ts: float, time_desc: str = ""):
    dt = _local_dt(ts) if ts else None
    desc = time_desc or (dt.strftime("%d.%m %H:%M") if dt else "?")
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(text="✅ Да", callback_data="rem_yes"),
        types.InlineKeyboardButton(text="❌ Нет", callback_data="rem_no"),
    )
    await reply_func(
        f"📅 <b>Напомнить:</b>\n⏰ {desc}\n{safe_html_format(text)}",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.message(F.text)
@allowed_only
async def detect_reminder(msg: types.Message):
    if not _is_reminder(msg.text):
        raise SkipHandler
    uid = msg.from_user.id
    text = msg.text.strip()
    try:
        parsed = await _parse_reminder(text)
    except Exception as e:
        logger.error(f"Reminder parse error: {e}")
        parsed = {}

    reminder_text = parsed.get("reminder_text") or ""
    unix_ts = parsed.get("unix_timestamp")
    time_desc = parsed.get("time_description") or ""

    if unix_ts and _is_past(unix_ts):
        _remind_pending.pop(uid, None)
        await msg.answer(PAST_TIME_TEXT, parse_mode="HTML")
        return

    if reminder_text and unix_ts:
        _remind_pending[uid] = {"text": reminder_text, "ts": unix_ts, "step": "confirm"}
        await _show_reminder_confirm(msg.answer, reminder_text, unix_ts, time_desc)
    elif not reminder_text and unix_ts:
        _remind_pending[uid] = {"ts": unix_ts, "step": "ask_text"}
        await msg.answer(
            "📝 <b>О чём напомнить?</b>\nНапиши текст напоминания.", parse_mode="HTML",
        )
    elif reminder_text and not unix_ts:
        _remind_pending[uid] = {"text": reminder_text, "step": "ask_time"}
        await msg.answer(
            "⏰ <b>Когда напомнить?</b>\n"
            "Напиши время, например:\n"
            "• через 2 часа\n• завтра в 15:00\n• послезавтра в 10:30",
            parse_mode="HTML",
        )
    else:
        _remind_pending[uid] = {"step": "ask_all"}
        await msg.answer(
            "📝 <b>Создание напоминания</b>\n\n"
            "Напиши, когда и о чём напомнить.\n"
            "Например: <i>завтра в 15:00 позвонить маме</i>",
            parse_mode="HTML",
        )


@router.callback_query(F.data == "rem_yes")
@allowed_callback
async def cb_remind_confirm(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    data = _remind_pending.get(uid)
    if not data:
        return await cb.message.edit_text("❌ Сессия истекла.")
    text = data.get("text", "")
    ts = data.get("ts", 0)
    if not text or not ts:
        return await cb.message.edit_text("❌ Ошибка: не хватает данных.")
    if _is_past(ts):
        _remind_pending.pop(uid, None)
        return await cb.message.edit_text(PAST_TIME_TEXT)

    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(text="⏰ В бот", callback_data="rem_tgt:bot"),
        types.InlineKeyboardButton(text="📅 Apple Calendar", callback_data="rem_tgt:cal"),
    )
    kb.row(types.InlineKeyboardButton(text="⚡ В оба", callback_data="rem_tgt:both"))
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="rem_no"))
    dt = _local_dt(ts)
    await cb.message.edit_text(
        f"📅 <b>Напомнить:</b>\n🕐 {dt.strftime('%d.%m.%Y %H:%M')}\n"
        f"{safe_html_format(text)}\n\n"
        "Где сохранить напоминание?",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("rem_tgt:"))
@allowed_callback
async def cb_remind_target(cb: types.CallbackQuery):
    """Сохраняет напоминание: в бот, в Apple Calendar или в оба."""
    await cb.answer()
    if not cb.data:
        return
    target = cb.data.split(":", 1)[1]
    uid = cb.from_user.id
    data = _remind_pending.pop(uid, None)
    if not data:
        return await cb.message.edit_text("❌ Сессия истекла.")
    text = data.get("text", "")
    ts = data.get("ts", 0)
    if not text or not ts:
        return await cb.message.edit_text("❌ Ошибка: не хватает данных.")
    if _is_past(ts):
        return await cb.message.edit_text(PAST_TIME_TEXT)

    await cb.message.edit_text("⏳ Сохраняю…")
    parts: list[str] = []

    if target in ("bot", "both"):
        try:
            kv = get_kv_store()
            key = f"rem{int(ts)}_{uid}_{uuid.uuid4().hex}"
            kv.set(
                key,
                {
                    "user_id": uid,
                    "chat_id": cb.message.chat.id,
                    "text": text,
                    "remind_at": ts,
                    "created_at": time.time(),
                },
                namespace=REMINDER_NS,
                ttl=None,
            )
            parts.append("⏰ <b>Бот:</b> ✅")
        except Exception as e:  # noqa: BLE001
            logger.error("[REM] kv save failed: %s", e)
            parts.append(f"⏰ <b>Бот:</b> ❌ {safe_html_format(str(e)[:100])}")

    if target in ("cal", "both"):
        try:
            from services.apple_calendar import create_calendar_event

            ev_id = create_calendar_event(
                title=text[:200],
                start_ts=ts,
                duration_minutes=15,
                notes=f"Напоминание из MemPalace (uid={uid})",
            )
            parts.append(f"📅 <b>Apple Calendar:</b> ✅ <code>{safe_html_format(ev_id[:8])}…</code>")
        except Exception as e:  # noqa: BLE001
            logger.error("[REM] calendar save failed: %s", e)
            parts.append(f"📅 <b>Apple Calendar:</b> ❌ {safe_html_format(str(e)[:100])}")

    dt = _local_dt(ts)
    summary = (
        f"✅ <b>Напоминание сохранено!</b>\n"
        f"🕐 {dt.strftime('%d.%m.%Y %H:%M')}\n"
        f"{safe_html_format(text)}\n\n"
        + "\n".join(parts)
    )
    await cb.message.edit_text(summary, parse_mode="HTML")


@router.callback_query(F.data == "rem_no")
@allowed_callback
async def cb_remind_cancel(cb: types.CallbackQuery):
    await cb.answer()
    _remind_pending.pop(cb.from_user.id, None)
    await cb.message.edit_text("❌ Напоминание отменено.")


async def handle_reminder_text(uid: int, text: str, reply_func) -> bool:
    """Handle follow-up text input for reminder wizard steps. Returns True if handled."""
    data = _remind_pending.get(uid)
    if not data:
        return False
    step = data.get("step", "")
    if step == "ask_text":
        ts = data.get("ts", 0)
        if ts and _is_past(ts):
            _remind_pending.pop(uid, None)
            await reply_func(PAST_TIME_TEXT)
            return True
        _remind_pending[uid] = {"text": text, "ts": ts, "step": "confirm"}
        dt = _local_dt(ts) if ts else None
        desc = dt.strftime("%d.%m %H:%M") if dt else "?"
        kb = InlineKeyboardBuilder()
        kb.row(
            types.InlineKeyboardButton(text="✅ Да", callback_data="rem_yes"),
            types.InlineKeyboardButton(text="❌ Нет", callback_data="rem_no"),
        )
        await reply_func(
            f"📅 <b>Напомнить:</b>\n🕐 {desc}\n{safe_html_format(text)}",
            parse_mode="HTML",
            reply_markup=kb.as_markup(),
        )
        return True

    if step == "ask_time":
        try:
            parsed = await _request_reminder_json(text, time_only=True)
            if parsed.get("hour") is not None and parsed.get("minute") is not None:
                ts = _parse_time_description(
                    hour=int(parsed["hour"]),
                    minute=int(parsed["minute"]),
                    day_offset=int(parsed.get("day_offset", 0)),
                )
                if _is_past(ts):
                    _remind_pending.pop(uid, None)
                    await reply_func(PAST_TIME_TEXT)
                    return True
                _remind_pending[uid] = {
                    "text": data.get("text"),
                    "ts": ts,
                    "step": "confirm",
                }
                dt = _local_dt(ts)
                desc = parsed.get("time_description", dt.strftime("%d.%m %H:%M"))
                kb = InlineKeyboardBuilder()
                kb.row(
                    types.InlineKeyboardButton(text="✅ Да", callback_data="rem_yes"),
                    types.InlineKeyboardButton(text="❌ Нет", callback_data="rem_no"),
                )
                await reply_func(
                    f"📅 <b>Напомнить:</b>\n⏰ {desc}\n{safe_html_format(data['text'])}",
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
                return True
        except Exception as e:  # noqa: BLE001
            logger.error("[REM] ask_time parse failed: %s", e)
        _remind_pending.pop(uid, None)
        await reply_func("❌ Не удалось определить время. Начни заново с «напомни».")
        return True

    if step == "ask_all":
        _remind_pending.pop(uid, None)
        try:
            parsed = await _parse_reminder(text)
        except Exception as e:
            logger.error("[REM] ask_all parse failed: %s", e, exc_info=True)
            await reply_func(
                "❌ Не удалось разобрать напоминание. Начни заново с «напомни».",
            )
            return True
        reminder_text = parsed.get("reminder_text") or ""
        unix_ts = parsed.get("unix_timestamp")
        time_desc = parsed.get("time_description") or ""
        if unix_ts and _is_past(unix_ts):
            await reply_func(PAST_TIME_TEXT)
            return True
        if reminder_text and unix_ts:
            _remind_pending[uid] = {
                "text": reminder_text,
                "ts": unix_ts,
                "step": "confirm",
            }
            await _show_reminder_confirm(reply_func, reminder_text, unix_ts, time_desc)
        elif not reminder_text and unix_ts:
            _remind_pending[uid] = {"ts": unix_ts, "step": "ask_text"}
            await reply_func(
                "📝 <b>О чём напомнить?</b>\nНапиши текст напоминания.",
                parse_mode="HTML",
            )
        elif reminder_text and not unix_ts:
            _remind_pending[uid] = {"text": reminder_text, "step": "ask_time"}
            await reply_func(
                "⏰ <b>Когда напомнить?</b>\nНапиши время.", parse_mode="HTML",
            )
        else:
            await reply_func("❌ Не удалось понять. Начни заново с «напомни».")
        return True

    return False
