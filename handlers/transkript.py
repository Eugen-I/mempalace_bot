import os
from datetime import datetime

from aiogram import F, Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from cachetools import TTLCache

from config import TRANSKRIPT_DIR, allowed_callback, allowed_only
from services.text_formatter import safe_html_format, split_message
from services.ttl_dict import TtlDict

router = Router()
PAGE_SIZE = 5
CONTENT_PAGE_SIZE = 2500

_tr_content_cache: TTLCache[int, dict] = TTLCache(maxsize=50, ttl=600)
_tr_ai_waiting: TtlDict = TtlDict()
_tr_last_question: TtlDict = TtlDict()


def _list_files() -> list:
    if not os.path.isdir(TRANSKRIPT_DIR):
        return []
    return sorted(
        [f for f in os.listdir(TRANSKRIPT_DIR) if f.endswith(".txt")],
        key=lambda x: os.path.getmtime(os.path.join(TRANSKRIPT_DIR, x)),
        reverse=True,
    )


@router.message(F.text == "📜 Транскрипты")
@allowed_only
async def cmd_transkript(message: types.Message):
    files = _list_files()
    if not files:
        return await message.answer("📂 Папка transkript пуста.")
    await _show_page(message, files, offset=0)


async def _show_page(
    target: types.Message | types.CallbackQuery,
    files: list,
    offset: int,
):
    page = files[offset : offset + PAGE_SIZE]
    total = len(files)
    lines = [
        f"📜 <b>Транскрипты ({total}):</b>\n",
    ]

    kb = InlineKeyboardBuilder()
    for i, f in enumerate(page):
        path = os.path.join(TRANSKRIPT_DIR, f)
        size = os.path.getsize(path)
        mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%d.%m.%y")
        label = f[:50] + (".." if len(f) > 50 else "")
        lines.append(f"{offset + i + 1}) <code>{label}</code> — {size // 1024} KB, {mtime}")
        kb.row(
            types.InlineKeyboardButton(
                text=f"📄 {offset + i + 1}",
                callback_data=f"tr_read:{offset + i}",
            ),
        )

    nav = []
    if offset > 0:
        nav.append(
            types.InlineKeyboardButton(
                text="◀️", callback_data=f"tr_page:{offset - PAGE_SIZE}",
            ),
        )
    if offset + PAGE_SIZE < total:
        nav.append(
            types.InlineKeyboardButton(
                text="▶️", callback_data=f"tr_page:{offset + PAGE_SIZE}",
            ),
        )
    if nav:
        kb.row(*nav)

    text = "\n".join(lines)

    if isinstance(target, types.CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("tr_page:"))
@allowed_callback
async def cb_tr_page(callback: types.CallbackQuery):
    offset = int(callback.data.split(":")[1])
    files = _list_files()
    if not files:
        return await callback.answer("Папка пуста.")
    await _show_page(callback, files, offset)
    await callback.answer()


@router.callback_query(F.data.startswith("tr_read:"))
@allowed_callback
async def cb_tr_read(callback: types.CallbackQuery):
    idx = int(callback.data.split(":")[1])
    files = _list_files()
    if idx >= len(files):
        return await callback.answer("Файл не найден.")
    fname = files[idx]
    path = os.path.join(TRANSKRIPT_DIR, fname)

    dt = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%d.%m.%Y %H:%M")
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return await callback.message.answer(f"❌ Ошибка чтения: {e}")

    formatted = safe_html_format(content)
    pages = split_message(formatted, limit=CONTENT_PAGE_SIZE)

    uid = callback.from_user.id
    _tr_content_cache[uid] = {
        "pages": pages,
        "total": len(pages),
        "idx": 0,
        "fname": fname,
        "dt": dt,
    }

    await _show_content_page(callback, uid, 0)
    await callback.answer()


async def _show_content_page(target: types.Message | types.CallbackQuery, uid: int, idx: int):
    data = _tr_content_cache.get(uid)
    if not data:
        if isinstance(target, types.CallbackQuery):
            await target.message.answer("⏳ Сессия истекла. Откройте файл заново.")
        return

    pages = data["pages"]
    total = data["total"]
    idx = max(0, min(idx, total - 1))
    data["idx"] = idx

    header = f"📜 <code>{data['fname']}</code>\n📅 {data['dt']}\n\n"
    body = f"{header}{pages[idx]}"

    kb = InlineKeyboardBuilder()
    nav = []
    if idx > 0:
        nav.append(types.InlineKeyboardButton(text="◀️", callback_data=f"tr_cp:{idx - 1}"))
    nav.append(types.InlineKeyboardButton(text=f"{idx + 1}/{total}", callback_data="tr_cp:noop"))
    if idx < total - 1:
        nav.append(types.InlineKeyboardButton(text="▶️", callback_data=f"tr_cp:{idx + 1}"))
    kb.row(*nav)

    # Действия с транскриптом
    kb.row(
        types.InlineKeyboardButton(text="🤖 Обсудить", callback_data="tr_ai"),
        types.InlineKeyboardButton(text="🌐 Интернет", callback_data="tr_ai_web"),
    )
    kb.row(
        types.InlineKeyboardButton(text="💬 Цитата", callback_data="tr_q"),
        types.InlineKeyboardButton(text="💾 В MemPalace", callback_data="tr_save"),
    )
    kb.row(
        types.InlineKeyboardButton(text="🔗 Смысловые связи", callback_data="tr_links"),
        types.InlineKeyboardButton(text="🗑️ Удалить", callback_data="tr_del"),
    )

    if isinstance(target, types.CallbackQuery):
        await target.message.edit_text(body, reply_markup=kb.as_markup(), parse_mode="HTML")
    else:
        await target.answer(body, reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("tr_cp:"))
@allowed_callback
async def cb_tr_content_page(callback: types.CallbackQuery):
    idx_str = callback.data.split(":", 1)[1]
    if idx_str == "noop":
        return await callback.answer()
    idx = int(idx_str)
    await _show_content_page(callback, callback.from_user.id, idx)
    await callback.answer()


def _get_content(uid: int) -> str:
    """Полный текст транскрипта из кэша."""
    data = _tr_content_cache.get(uid)
    if not data:
        return ""
    fname = data.get("fname", "")
    if not fname:
        return ""
    path = os.path.join(TRANSKRIPT_DIR, fname)
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


# ─── ДЕЙСТВИЯ С ТРАНСКРИПТОМ ───

@router.callback_query(F.data == "tr_ai")
@allowed_callback
async def cb_tr_ai(callback: types.CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    content = _tr_content_cache.get(uid)
    if not content:
        await callback.message.edit_text("⏳ Сессия истекла. Откройте файл заново.")
        return
    _tr_ai_waiting[uid] = {"fname": content["fname"], "mode": "ask"}
    await callback.message.edit_text(
        "🤖 Задайте вопрос по транскрипту — бот ответит по содержимому файла.\n\n"
        "Введите вопрос текстом:",
    )


@router.callback_query(F.data == "tr_ai_web")
@allowed_callback
async def cb_tr_ai_web(callback: types.CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    question = _tr_last_question.get(uid)
    if not question:
        await callback.message.answer(
            "🌐 Сначала задайте вопрос через «🤖 Обсудить», затем повторите.",
        )
        return
    content = _tr_content_cache.get(uid)
    if not content:
        await callback.message.edit_text("⏳ Сессия истекла. Откройте файл заново.")
        return
    status = await callback.message.answer("🌐 Ищу в интернете и отвечаю...")
    await _answer_tr_ai(status, uid, content["fname"], question, with_web=True)


@router.callback_query(F.data == "tr_q")
@allowed_callback
async def cb_tr_q(callback: types.CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    data = _tr_content_cache.get(uid)
    if not data:
        await callback.message.edit_text("⏳ Сессия истекла. Откройте файл заново.")
        return
    content = _get_content(uid)
    if not content:
        await callback.message.edit_text("❌ Не удалось прочитать файл.")
        return
    from handlers.personal_note import _quote_waiting

    _quote_waiting[uid] = {"content": content, "drawer_id": ""}
    await callback.message.edit_text(
        f"<b>💬 Отправьте цитату из транскрипта</b>\n\n"
        f"Скопируйте нужный фрагмент и отправьте его сообщением:\n\n"
        f"{safe_html_format(content[:800])}"
        + ("\u2026" if len(content) > 800 else ""),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "tr_save")
@allowed_callback
async def cb_tr_save(callback: types.CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    content = _get_content(uid)
    if not content:
        await callback.message.edit_text("⏳ Сессия истекла или файл не найден.")
        return
    from handlers.palace.save import _save_state, _show_save_wings

    _save_state[uid] = {"text": content, "mode": "full"}
    await _show_save_wings(callback.message.edit_text, uid)


@router.callback_query(F.data == "tr_links")
@allowed_callback
async def cb_tr_links(callback: types.CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    data = _tr_content_cache.get(uid)
    if not data:
        await callback.message.edit_text("⏳ Сессия истекла. Откройте файл заново.")
        return
    content = _get_content(uid)
    if not content:
        await callback.message.edit_text("❌ Не удалось прочитать файл.")
        return
    from services.palace_bridge import search_palace_with_sources

    st = await callback.message.answer("🔗 Ищу смысловые связи в MemPalace...")
    try:
        text, sources = await search_palace_with_sources(content[:500], limit=5)
        if not text:
            await st.edit_text("🔗 Связанных записей в MemPalace не найдено.")
            return
        body = (
            f"🔗 <b>Смысловые связи транскрипта</b>\n\n"
            f"{text[:2000]}"
        )
        kb = InlineKeyboardBuilder()
        for s in sources:
            kb.row(types.InlineKeyboardButton(
                text=f"📄 Читать [{s['id']}] {s['wing']}/{s['room']}",
                callback_data=f"p_src:{s['id']}",
            ))
        await st.edit_text(body, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception as e:
        await st.edit_text(f"❌ Ошибка поиска связей: {str(e)[:200]}")


@router.callback_query(F.data == "tr_del")
@allowed_callback
async def cb_tr_del(callback: types.CallbackQuery):
    await callback.answer()
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(text="✅ Удалить", callback_data="tr_del_yes"),
        types.InlineKeyboardButton(text="❌ Нет", callback_data="tr_cp:noop"),
    )
    await callback.message.edit_text(
        "🗑️ <b>Удалить транскрипт?</b>\n\nЭто действие необратимо.",
        parse_mode="HTML", reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "tr_del_yes")
@allowed_callback
async def cb_tr_del_yes(callback: types.CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    data = _tr_content_cache.pop(uid, None)
    if not data:
        await callback.message.edit_text("⏳ Сессия истекла.")
        return
    fname = data.get("fname", "")
    path = os.path.join(TRANSKRIPT_DIR, fname)
    try:
        os.remove(path)
        await callback.message.edit_text("✅ Транскрипт удалён.")
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка удаления: {str(e)[:200]}")


async def _answer_tr_ai(msg, uid: int, fname: str, question: str, with_web: bool = False):
    """Паттерн _answer_room_ai: ИИ отвечает по контенту транскрипта (опционально + интернет)."""
    path = os.path.join(TRANSKRIPT_DIR, fname)
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка чтения: {e}")
        return
    if not content.strip():
        await msg.edit_text("❌ Транскрипт пуст.")
        return

    from services.ai_engine import get_current_ai, _sync_ai_call

    engine, model = get_current_ai()
    _tr_last_question[uid] = question
    if with_web:
        from services.web_search import search_web

        web_results = await search_web(question)
        system = (
            f"Ты отвечаешь на вопрос пользователя на основе транскрипта.\n"
            f"Отвечай на русском языке.\n"
            f"Если в транскрипте нет информации — так и скажи.\n\n"
            f"Транскрипт:\n{content[:25000]}\n\n"
            f"Результаты поиска в интернете:\n{web_results}"
        )
    else:
        system = (
            f"Ты отвечаешь на вопрос пользователя ИСКЛЮЧИТЕЛЬНО на основе "
            f"транскрипта.\nОтвечай на русском языке.\n"
            f"Если в транскрипте нет нужной информации — так и скажи.\n\n"
            f"Транскрипт:\n{content[:25000]}"
        )

    result = _sync_ai_call(engine, model, [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ])
    await msg.edit_text(result or "❌ Пустой ответ.", parse_mode="HTML")


async def handle_tr_ai_question(uid: int, message: types.Message, fname: str, question: str):
    """Вызывается из messages.py: пользователь задал вопрос по транскрипту."""
    st = await message.answer("🤔 Анализирую транскрипт...")
    await _answer_tr_ai(st, uid, fname, question, with_web=False)
