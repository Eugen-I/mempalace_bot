import os
from datetime import datetime

from aiogram import F, Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from cachetools import TTLCache

from config import TRANSKRIPT_DIR, allowed_callback, allowed_only
from services.text_formatter import safe_html_format, split_message

router = Router()
PAGE_SIZE = 5
CONTENT_PAGE_SIZE = 2500

_tr_content_cache: TTLCache[int, dict] = TTLCache(maxsize=50, ttl=600)


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
