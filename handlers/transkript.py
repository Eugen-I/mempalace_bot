import os
from datetime import datetime

from aiogram import F, Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import TRANSKRIPT_DIR, allowed_callback, allowed_only
from services.text_formatter import safe_html_format, split_message

router = Router()
PAGE_SIZE = 5


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
    await _show_page(message, message.from_user.id, files, offset=0)


async def _show_page(
    target: types.Message | types.CallbackQuery,
    uid: int,
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
    await _show_page(callback, callback.from_user.id, files, offset)
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

    header = f"📜 <code>{fname}</code>\n📅 {dt}\n\n"
    formatted = safe_html_format(content)
    parts = split_message(formatted)

    for i, part in enumerate(parts):
        msg = f"{header}{part}" if i == 0 else part
        await callback.message.answer(msg, parse_mode="HTML")

    await callback.answer()
