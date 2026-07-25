import json, logging, time
from datetime import datetime
from aiogram import F, Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import allowed_callback
from services.kv_store import get_kv_store
from services.text_formatter import safe_html_format
from handlers.palace import TtlDict

logger = logging.getLogger("Reminder")
router = Router()
REMINDER_NS = "reminders"

_remind_pending: TtlDict[int, dict] = TtlDict()

REMINDER_KEYWORDS = [
    "напомни", "напомнить", "напоминание", "напомните",
    "remind", "reminder", "напомн",
]

def _is_reminder(text: str) -> bool:
    t = text.strip().lower()
    return any(k in t for k in REMINDER_KEYWORDS)


async def _parse_reminder(text: str) -> dict:
    from services.ai_engine import get_current_ai, get_ai_response_async
    now = datetime.now()
    weekday_ru = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"][now.weekday()]
    prompt = (
        f"Ты — парсер напоминаний.\n"
        f"Сегодня: {now.strftime('%Y-%m-%d')} ({weekday_ru})\n"
        f"Сейчас: {now.strftime('%H:%M')}\n\n"
        f"Извлеки из сообщения пользователя текст напоминания и желаемое время.\n"
        f"Правила:\n"
        f"- unix_timestamp — число секунд с 1970-01-01 (если время указано)\n"
        f"- Если время не указано — unix_timestamp = null\n"
        f"- Если текст не указан — reminder_text = null\n"
        f"- time_description — человекочитаемое описание времени (для подтверждения)\n\n"
        f"Сообщение: {text}\n\n"
        f"Верни ТОЛЬКО JSON: {{\"reminder_text\": \"...\", \"unix_timestamp\": 1234567890, \"time_description\": \"...\"}}"
    )
    engine, model = get_current_ai()
    resp = await get_ai_response_async(engine, model, [
        {"role": "system", "content": "Ты — JSON-парсер напоминаний. Отвечай только JSON."},
        {"role": "user", "content": prompt},
    ])
    return _clean_json(resp)


async def _show_reminder_confirm(reply_func, text: str, ts: float, time_desc: str = ""):
    dt = datetime.fromtimestamp(ts) if ts else None
    desc = time_desc or (dt.strftime('%d.%m %H:%M') if dt else "?")
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(text="✅ Да", callback_data="rem_yes"),
        types.InlineKeyboardButton(text="❌ Нет", callback_data="rem_no"),
    )
    await reply_func(
        f"📅 <b>Напомнить:</b>\n⏰ {desc}\n{safe_html_format(text)}",
        parse_mode="HTML", reply_markup=kb.as_markup()
    )


@router.message(F.text)
async def detect_reminder(msg: types.Message):
    if not _is_reminder(msg.text):
        return
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

    if reminder_text and unix_ts:
        _remind_pending[uid] = {"text": reminder_text, "ts": unix_ts, "step": "confirm"}
        await _show_reminder_confirm(msg.answer, reminder_text, unix_ts, time_desc)
    elif not reminder_text and unix_ts:
        _remind_pending[uid] = {"ts": unix_ts, "step": "ask_text"}
        await msg.answer("📝 <b>О чём напомнить?</b>\nНапиши текст напоминания.", parse_mode="HTML")
    elif reminder_text and not unix_ts:
        _remind_pending[uid] = {"text": reminder_text, "step": "ask_time"}
        await msg.answer(
            "⏰ <b>Когда напомнить?</b>\n"
            "Напиши время, например:\n"
            "• через 2 часа\n• завтра в 15:00\n• послезавтра в 10:30",
            parse_mode="HTML"
        )
    else:
        _remind_pending[uid] = {"step": "ask_all"}
        await msg.answer(
            "📝 <b>Создание напоминания</b>\n\n"
            "Напиши, когда и о чём напомнить.\n"
            "Например: <i>завтра в 15:00 позвонить маме</i>",
            parse_mode="HTML"
        )

@router.callback_query(F.data == "rem_yes")
@allowed_callback
async def cb_remind_confirm(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    data = _remind_pending.pop(uid, None)
    if not data:
        return await cb.message.edit_text("❌ Сессия истекла.")
    text = data.get("text", "")
    ts = data.get("ts", 0)
    if not text or not ts:
        return await cb.message.edit_text("❌ Ошибка: не хватает данных.")
    kv = get_kv_store()
    key = f"rem{int(ts)}_{uid}_{int(time.time())}"
    kv.set(key, {
        "user_id": uid,
        "chat_id": cb.message.chat.id,
        "text": text,
        "remind_at": ts,
        "created_at": time.time(),
    }, namespace=REMINDER_NS, ttl=None)
    dt = datetime.fromtimestamp(ts)
    await cb.message.edit_text(
        f"✅ <b>Напоминание сохранено!</b>\n"
        f"🕐 {dt.strftime('%d.%m.%Y %H:%M')}\n"
        f"{safe_html_format(text)}",
        parse_mode="HTML"
    )

@router.callback_query(F.data == "rem_no")
@allowed_callback
async def cb_remind_cancel(cb: types.CallbackQuery):
    await cb.answer()
    _remind_pending.pop(cb.from_user.id, None)
    await cb.message.edit_text("❌ Напоминание отменено.")

def _clean_json(raw: str) -> dict:
    cleaned = raw.strip()
    for p in ("```json", "```"):
        if cleaned.startswith(p):
            cleaned = cleaned[len(p):]
    for s in ("```",):
        if cleaned.endswith(s):
            cleaned = cleaned[:-len(s)]
    cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start:end])
            except json.JSONDecodeError:
                pass
    return {}


async def handle_reminder_text(uid: int, text: str, reply_func) -> bool:
    """Handle follow-up text input for reminder wizard steps. Returns True if handled."""
    data = _remind_pending.get(uid)
    if not data:
        return False
    step = data.get("step", "")
    if step == "ask_text":
        _remind_pending[uid] = {"text": text, "ts": data.get("ts"), "step": "confirm"}
        ts = data.get("ts", 0)
        dt = datetime.fromtimestamp(ts) if ts else None
        desc = dt.strftime('%d.%m %H:%M') if dt else "?"
        kb = InlineKeyboardBuilder()
        kb.row(
            types.InlineKeyboardButton(text="✅ Да", callback_data="rem_yes"),
            types.InlineKeyboardButton(text="❌ Нет", callback_data="rem_no"),
        )
        await reply_func(
            f"📅 <b>Напомнить:</b>\n🕐 {desc}\n{safe_html_format(text)}",
            parse_mode="HTML", reply_markup=kb.as_markup()
        )
        return True

    if step == "ask_time":
        from services.ai_engine import get_current_ai, get_ai_response_async
        now = datetime.now()
        weekday_ru = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"][now.weekday()]
        prompt = (
            f"Сегодня: {now.strftime('%Y-%m-%d')} ({weekday_ru})\n"
            f"Сейчас: {now.strftime('%H:%M')}\n\n"
            f"Определи время из сообщения. Верни JSON:\n"
            f"{{\"unix_timestamp\": 1234567890, \"time_description\": \"...\"}}\n"
            f"Сообщение: {text}"
        )
        try:
            engine, model = get_current_ai()
            resp = await get_ai_response_async(engine, model, [
                {"role": "system", "content": "Ты — JSON-парсер времени. Отвечай только JSON."},
                {"role": "user", "content": prompt},
            ])
            parsed = _clean_json(resp)
            ts = parsed.get("unix_timestamp")
            if ts:
                _remind_pending[uid] = {"text": data.get("text"), "ts": ts, "step": "confirm"}
                dt = datetime.fromtimestamp(ts)
                desc = parsed.get("time_description", dt.strftime('%d.%m %H:%M'))
                kb = InlineKeyboardBuilder()
                kb.row(
                    types.InlineKeyboardButton(text="✅ Да", callback_data="rem_yes"),
                    types.InlineKeyboardButton(text="❌ Нет", callback_data="rem_no"),
                )
                await reply_func(
                    f"📅 <b>Напомнить:</b>\n⏰ {desc}\n{safe_html_format(data['text'])}",
                    parse_mode="HTML", reply_markup=kb.as_markup()
                )
                return True
        except Exception:
            pass
        _remind_pending.pop(uid, None)
        await reply_func("❌ Не удалось определить время. Начни заново с «напомни».")
        return True

    if step == "ask_all":
        _remind_pending.pop(uid, None)
        parsed = await _parse_reminder(text)
        reminder_text = parsed.get("reminder_text") or ""
        unix_ts = parsed.get("unix_timestamp")
        time_desc = parsed.get("time_description") or ""
        if reminder_text and unix_ts:
            _remind_pending[uid] = {"text": reminder_text, "ts": unix_ts, "step": "confirm"}
            await _show_reminder_confirm(reply_func, reminder_text, unix_ts, time_desc)
        elif not reminder_text and unix_ts:
            _remind_pending[uid] = {"ts": unix_ts, "step": "ask_text"}
            await reply_func("📝 <b>О чём напомнить?</b>\nНапиши текст напоминания.", parse_mode="HTML")
        elif reminder_text and not unix_ts:
            _remind_pending[uid] = {"text": reminder_text, "step": "ask_time"}
            await reply_func("⏰ <b>Когда напомнить?</b>\nНапиши время.", parse_mode="HTML")
        else:
            await reply_func("❌ Не удалось понять. Начни заново с «напомни».")
        return True

    return False
