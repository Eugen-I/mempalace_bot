"""handlers/palace/unfiled_notes.py — Чтение и раскладка неразобранных заметок из my_notes."""
import json
import logging
import os
from pathlib import Path
import shutil
from typing import Any

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import NOTES_DIR, allowed_callback, allowed_only
from services.cascade_delete import cascade_delete_note
from services.palace_mcp import get_mcp
from services.text_formatter import safe_html_format

from .shared import _pending_mcp_input

logger = logging.getLogger("UnfiledNotes")
router = Router()

PAGE_SIZE = 5
TEXT_PAGE_SIZE = 3000

# Состояние пользователя: {uid: {...}}
_unfiled_state: dict[int, dict[str, Any]] = {}


def list_unfiled_notes() -> list[dict[str, Any]]:
    """Возвращает список неразобранных файлов (.md, .txt) из корня my_notes/."""
    notes_root = Path(NOTES_DIR)
    if not notes_root.exists():
        return []

    items = []
    try:
        for entry in os.scandir(notes_root):
            if entry.is_file() and not entry.name.startswith("."):
                ext = Path(entry.name).suffix.lower()
                if ext in [".md", ".txt"]:
                    stat = entry.stat()
                    preview = ""
                    try:
                        with open(entry.path, "r", encoding="utf-8", errors="replace") as f:
                            preview = f.read(300).strip().replace("\n", " ")
                    except Exception:
                        pass
                    items.append({
                        "filename": entry.name,
                        "path": entry.path,
                        "mtime": stat.st_mtime,
                        "size": stat.st_size,
                        "preview": preview[:150] + "…" if len(preview) > 150 else preview,
                    })
    except Exception as e:
        logger.error("Ошибка при чтении корня NOTES_DIR: %s", e)

    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items


def _format_size(size: int) -> str:
    """Форматирует размер файла."""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _format_mtime(mtime: float) -> str:
    """Форматирует дату изменения файла."""
    from datetime import datetime
    return datetime.fromtimestamp(mtime).strftime("%d.%m.%Y %H:%M")


async def show_unfiled_list(edit_func, uid: int, page: int = 0):
    """Отображает список неразобранных заметок с пагинацией."""
    files = list_unfiled_notes()
    total = len(files)
    st = _unfiled_state.setdefault(uid, {})
    st["files"] = files
    st["page"] = page

    if not files:
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="◀️ В меню Дворца", callback_data="palace_back"))
        await edit_func(
            "📂 <b>Неразобранные заметки (my_notes)</b>\n\n"
            "В корне папки <code>my_notes/</code> нет неразобранных файлов.\n"
            "Все заметки разложены по комнатам Дворца!",
            parse_mode="HTML",
            reply_markup=kb.as_markup(),
        )
        return

    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total)
    page_files = files[start:end]

    page_count = (total + PAGE_SIZE - 1) // PAGE_SIZE
    lines = [
        "📝 <b>Неразобранные заметки в my_notes</b>",
        f"<i>Всего файлов в инбоксе: {total} (страница {page + 1}/{page_count})</i>\n",
    ]

    for i, item in enumerate(page_files):
        num = start + i + 1
        fn = safe_html_format(item["filename"])
        dt = _format_mtime(item["mtime"])
        sz = _format_size(item["size"])
        prev = safe_html_format(item["preview"])
        lines.append(f"{num}. 📄 <b>{fn}</b>")
        lines.append(f"   📅 {dt} · 💾 {sz}")
        if prev:
            lines.append(f"   <i>{prev}</i>")
        lines.append("")

    kb = InlineKeyboardBuilder()
    for i, item in enumerate(page_files):
        idx = start + i
        fn = item["filename"]
        short_name = fn[:26] + "…" if len(fn) > 26 else fn
        kb.row(types.InlineKeyboardButton(
            text=f"📄 {start + i + 1}. {short_name}",
            callback_data=f"p_unf_v:{idx}",
        ))

    nav_row = []
    if page > 0:
        nav_row.append(types.InlineKeyboardButton(
            text="◀️ Пред.", callback_data=f"p_unf_p:{page - 1}",
        ))
    if end < total:
        nav_row.append(types.InlineKeyboardButton(
            text="След. ▶️", callback_data=f"p_unf_p:{page + 1}",
        ))
    if nav_row:
        kb.row(*nav_row)

    kb.row(
        types.InlineKeyboardButton(text="🔄 Обновить", callback_data="p_unfiled"),
        types.InlineKeyboardButton(text="◀️ В меню Дворца", callback_data="palace_back"),
    )

    await edit_func(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.message(Command("unfiled"))
@router.message(Command("saved_notes"))
@router.message(F.text == "📝 Неразобранные заметки")
@router.message(F.text == "📝 Сохранённые заметки")
@allowed_only
async def cmd_unfiled_message(message: types.Message):
    await show_unfiled_list(message.answer, message.from_user.id, page=0)


@router.callback_query(F.data == "p_unfiled")
@allowed_callback
async def cb_unfiled_menu(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    await show_unfiled_list(cb.message.edit_text, uid, page=0)


@router.callback_query(F.data.startswith("p_unf_p:"))
@allowed_callback
async def cb_unfiled_page(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    try:
        page = int(cb.data.split(":", 1)[1])
    except ValueError:
        page = 0
    await show_unfiled_list(cb.message.edit_text, uid, page=page)


async def show_unfiled_content(edit_func, uid: int, file_page: int = 0):
    """Показывает содержимое выбранной неразобранной заметки."""
    st = _unfiled_state.get(uid)
    if not st or "selected_path" not in st:
        await edit_func("❌ Заметка не выбрана. Вернитесь к списку.")
        return

    path = Path(st["selected_path"])
    if not path.is_file():
        await edit_func("❌ Файл заметки не найден на диске.")
        return

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        await edit_func(f"❌ Ошибка чтения файла: {e}")
        return

    st["selected_text"] = text
    st["text_page"] = file_page
    total_len = len(text)
    total_pages = max(1, (total_len + TEXT_PAGE_SIZE - 1) // TEXT_PAGE_SIZE)
    file_page = max(0, min(file_page, total_pages - 1))

    start = file_page * TEXT_PAGE_SIZE
    chunk = text[start:start + TEXT_PAGE_SIZE]

    fn = safe_html_format(st["filename"])
    header = (
        f"📝 <b>Заметка:</b> <code>{fn}</code>\n"
        f"<i>Страница {file_page + 1}/{total_pages} (всего {total_len} симв.)</i>\n\n"
    )

    body = safe_html_format(chunk)
    kb = InlineKeyboardBuilder()

    nav_row = []
    if file_page > 0:
        nav_row.append(types.InlineKeyboardButton(
            text="◀️ Пред. стр.", callback_data=f"p_unf_tp:{file_page - 1}",
        ))
    if file_page < total_pages - 1:
        nav_row.append(types.InlineKeyboardButton(
            text="След. стр. ▶️", callback_data=f"p_unf_tp:{file_page + 1}",
        ))
    if nav_row:
        kb.row(*nav_row)

    kb.row(
        types.InlineKeyboardButton(
            text="📁 Разложить в Дворец", callback_data="p_unf_file",
        ),
        types.InlineKeyboardButton(
            text="🗑️ Удалить", callback_data="p_unf_del",
        ),
    )
    kb.row(
        types.InlineKeyboardButton(
            text="◀️ К списку заметок", callback_data="p_unfiled",
        ),
    )

    await edit_func(
        f"{header}{body}",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("p_unf_v:"))
@allowed_callback
async def cb_unfiled_view(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    try:
        idx = int(cb.data.split(":", 1)[1])
    except ValueError:
        return
    st = _unfiled_state.get(uid) or {}
    files = st.get("files") or list_unfiled_notes()
    if idx >= len(files):
        await cb.message.edit_text("❌ Заметка не найдена в списке.")
        return

    item = files[idx]
    st["filename"] = item["filename"]
    st["selected_path"] = item["path"]
    st["selected_idx"] = idx
    _unfiled_state[uid] = st

    await show_unfiled_content(cb.message.edit_text, uid, file_page=0)


@router.callback_query(F.data.startswith("p_unf_open_name:"))
@allowed_callback
async def cb_unfiled_open_by_name(cb: types.CallbackQuery):
    """Открыть заметку по имени файла."""
    await cb.answer()
    uid = cb.from_user.id
    fname = cb.data.split(":", 1)[1]
    fpath = Path(NOTES_DIR) / fname
    if not fpath.is_file():
        await cb.message.answer(f"❌ Файл {fname} не найден в my_notes.")
        return

    st = _unfiled_state.setdefault(uid, {})
    st["filename"] = fname
    st["selected_path"] = str(fpath)
    await show_unfiled_content(cb.message.edit_text, uid, file_page=0)


@router.callback_query(F.data.startswith("p_unf_tp:"))
@allowed_callback
async def cb_unfiled_text_page(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    try:
        page = int(cb.data.split(":", 1)[1])
    except ValueError:
        page = 0
    await show_unfiled_content(cb.message.edit_text, uid, file_page=page)


# ─── УДАЛЕНИЕ НЕРАЗОБРАННОЙ ЗАМЕТКИ ───


@router.callback_query(F.data == "p_unf_del")
@allowed_callback
async def cb_unfiled_del_confirm(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    st = _unfiled_state.get(uid)
    if not st or "filename" not in st:
        await cb.message.edit_text("❌ Заметка не выбрана.")
        return

    fn = safe_html_format(st["filename"])
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(text="✅ Да, удалить", callback_data="p_unf_del_c"),
        types.InlineKeyboardButton(text="❌ Отмена", callback_data="p_unf_back_v"),
    )
    await cb.message.edit_text(
        f"🗑️ <b>Удалить заметку?</b>\n\n"
        f"Файл: <code>{fn}</code>\n\n"
        "Заметка будет безвозвратно удалена с диска и из всех баз.",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "p_unf_del_c")
@allowed_callback
async def cb_unfiled_del_execute(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    st = _unfiled_state.get(uid)
    if not st or "selected_path" not in st:
        await cb.message.edit_text("❌ Заметка не выбрана.")
        return

    path = st.get("selected_path", "")
    fn = st.get("filename", "")
    res = await cascade_delete_note(file_path=path, title=fn, source_file=fn)

    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="◀️ К списку заметок", callback_data="p_unfiled"))

    msg = f"🗑️ <b>Заметка «{safe_html_format(fn)}» удалена.</b>"
    if not res.get("file_deleted") and not res.get("success"):
        msg = f"❌ Не удалось удалить файл: {res.get('error') or 'ошибка доступа'}"

    await cb.message.edit_text(msg, parse_mode="HTML", reply_markup=kb.as_markup())


@router.callback_query(F.data == "p_unf_back_v")
@allowed_callback
async def cb_unfiled_back_to_view(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    st = _unfiled_state.get(uid) or {}
    page = st.get("text_page", 0)
    await show_unfiled_content(cb.message.edit_text, uid, file_page=page)


# ─── МАСТЕР РАСКЛАДКИ В ДВОРЕЦ ───


async def show_unfiled_wings(edit_func, uid: int):
    """Показывает список крыльев для раскладки."""
    mcp = get_mcp()
    try:
        raw = await mcp.call_tool("mempalace_list_wings")
        parsed = json.loads(raw)
        wings = parsed.get("wings", parsed)
    except Exception:
        wings = {}

    wing_names = list(wings.keys()) if isinstance(wings, dict) else list(wings)
    st = _unfiled_state.setdefault(uid, {})
    st["wings_cache"] = wing_names

    fn = safe_html_format(st.get("filename", ""))
    kb = InlineKeyboardBuilder()
    for i, w in enumerate(wing_names):
        kb.row(types.InlineKeyboardButton(
            text=f"🕸️ {w}", callback_data=f"p_ufw:{i}",
        ))

    kb.row(types.InlineKeyboardButton(text="➕ Новое крыло", callback_data="p_ufw_nw"))
    kb.row(types.InlineKeyboardButton(text="◀️ Назад к заметке", callback_data="p_unf_back_v"))

    await edit_func(
        f"📁 <b>Раскладка заметки</b> <code>{fn}</code>\n\n"
        "Выберите <b>крыло</b> Дворца:",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "p_unf_file")
@allowed_callback
async def cb_unfiled_file_start(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    await show_unfiled_wings(cb.message.edit_text, uid)


@router.callback_query(F.data.startswith("p_unf_file_name:"))
@allowed_callback
async def cb_unfiled_file_by_name(cb: types.CallbackQuery):
    """Старт раскладки сразу по имени файла (из Action Bar)."""
    await cb.answer()
    uid = cb.from_user.id
    fname = cb.data.split(":", 1)[1]
    fpath = Path(NOTES_DIR) / fname
    if not fpath.is_file():
        await cb.message.answer(f"❌ Файл {fname} не найден в my_notes.")
        return

    st = _unfiled_state.setdefault(uid, {})
    st["filename"] = fname
    st["selected_path"] = str(fpath)
    try:
        st["selected_text"] = fpath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        pass
    await show_unfiled_wings(cb.message.edit_text, uid)


@router.callback_query(F.data.startswith("p_ufw:"))
@allowed_callback
async def cb_unfiled_wing_chosen(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    try:
        idx = int(cb.data.split(":", 1)[1])
    except ValueError:
        return
    st = _unfiled_state.get(uid) or {}
    wings = st.get("wings_cache") or []
    if idx >= len(wings):
        await cb.message.edit_text("❌ Сессия истекла.")
        return
    st["wing"] = wings[idx]
    await show_unfiled_rooms(cb.message.edit_text, uid)


@router.callback_query(F.data == "p_ufw_nw")
@allowed_callback
async def cb_unfiled_new_wing_prompt(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    _pending_mcp_input[uid] = "unfiled_new_wing"
    await cb.message.edit_text(
        "🕸️ <b>Создание нового крыла</b>\n\n"
        "Введите название нового крыла (латиницей, без пробелов, "
        "например <code>psychology</code>):",
        parse_mode="HTML",
    )


async def show_unfiled_rooms(edit_func, uid: int):
    """Показывает список комнат в выбранном крыле."""
    st = _unfiled_state.get(uid)
    if not st:
        await edit_func("❌ Сессия истекла.")
        return
    wing = st.get("wing", "")
    mcp = get_mcp()
    try:
        raw = await mcp.call_tool("mempalace_list_rooms", {"wing": wing})
        parsed = json.loads(raw)
        rooms = parsed.get("rooms", {})
    except Exception:
        rooms = {}

    room_names = list(rooms.keys()) if isinstance(rooms, dict) else list(rooms)
    st["rooms_cache"] = room_names

    kb = InlineKeyboardBuilder()
    for i, r in enumerate(room_names):
        kb.row(types.InlineKeyboardButton(
            text=f"🚪 {r}", callback_data=f"p_ufr:{i}",
        ))

    kb.row(types.InlineKeyboardButton(text="➕ Новая комната", callback_data="p_ufr_nr"))
    kb.row(types.InlineKeyboardButton(text="◀️ К выбору крыла", callback_data="p_unf_file"))
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="p_unfiled"))

    await edit_func(
        f"📂 Крыло: <b>{safe_html_format(wing)}</b>\n"
        "Выберите <b>комнату</b> для заметки:",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("p_ufr:"))
@allowed_callback
async def cb_unfiled_room_chosen(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    try:
        idx = int(cb.data.split(":", 1)[1])
    except ValueError:
        return
    st = _unfiled_state.get(uid) or {}
    rooms = st.get("rooms_cache") or []
    if idx >= len(rooms):
        await cb.message.edit_text("❌ Сессия истекла.")
        return
    st["room"] = rooms[idx]
    await show_unfiled_confirm(cb.message.edit_text, uid)


@router.callback_query(F.data == "p_ufr_nr")
@allowed_callback
async def cb_unfiled_new_room_prompt(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    _pending_mcp_input[uid] = "unfiled_new_room"
    await cb.message.edit_text(
        "🚪 <b>Создание новой комнаты</b>\n\n"
        "Введите название новой комнаты (можно на русском или латинице, "
        "например <code>psychoanalysis</code>):",
        parse_mode="HTML",
    )


async def show_unfiled_confirm(edit_func, uid: int):
    """Экран подтверждения раскладки заметки."""
    st = _unfiled_state.get(uid)
    if not st:
        await edit_func("❌ Сессия истекла.")
        return

    fn = safe_html_format(st.get("filename", ""))
    wing = safe_html_format(st.get("wing", ""))
    room = safe_html_format(st.get("room", ""))

    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="✅ Разложить в Дворец", callback_data="p_uf_c"))
    kb.row(types.InlineKeyboardButton(text="◀️ Другая комната", callback_data="p_uf_br"))
    kb.row(types.InlineKeyboardButton(text="◀️ Другое крыло", callback_data="p_unf_file"))
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="p_unfiled"))

    await edit_func(
        f"📁 <b>Подтверждение раскладки заметки</b>\n\n"
        f"📄 Файл: <code>{fn}</code>\n"
        f"🕸️ Крыло: <b>{wing}</b>\n"
        f"🚪 Комната: <b>{room}</b>\n\n"
        "<i>Заметка будет проиндексирована в ChromaDB, а файл перемещён в папку комнаты.</i>",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "p_uf_br")
@allowed_callback
async def cb_unfiled_back_to_rooms(cb: types.CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    await show_unfiled_rooms(cb.message.edit_text, uid)


@router.callback_query(F.data == "p_uf_c")
@allowed_callback
async def cb_unfiled_execute_file(cb: types.CallbackQuery):
    """Выполняет перемещение файла в папку комнаты и добавление ящика в MemPalace."""
    await cb.answer()
    uid = cb.from_user.id
    st = _unfiled_state.pop(uid, None)
    if not st:
        await cb.message.edit_text("❌ Сессия истекла.")
        return

    src_path = Path(st.get("selected_path", ""))
    fname = st.get("filename", "")
    wing = st.get("wing", "my_notes")
    room = st.get("room", "general")
    text = st.get("selected_text", "")

    if not text and src_path.is_file():
        try:
            text = src_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if not text:
        await cb.message.edit_text("❌ Текст заметки пуст или файл недоступен.")
        return

    # 1. Перемещение файла в подпапку комнаты внутри my_notes
    target_dir = Path(NOTES_DIR) / room
    target_dir.mkdir(parents=True, exist_ok=True)
    dst_path = target_dir / fname

    if dst_path.exists() and dst_path != src_path:
        from datetime import datetime
        stem = Path(fname).stem
        ext = Path(fname).suffix
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst_path = target_dir / f"{stem}_{ts}{ext}"

    try:
        if src_path.is_file() and src_path != dst_path:
            shutil.move(str(src_path), str(dst_path))
            logger.info("Перемещён файл из %s в %s", src_path, dst_path)
    except Exception as e:
        logger.warning("Не удалось переместить файл на диске: %s", e)
        dst_path = src_path

    # 2. Добавление ящика в MemPalace ChromaDB
    try:
        mcp = get_mcp()
        raw = await mcp.call_tool(
            "mempalace_add_drawer",
            {
                "wing": wing,
                "room": room,
                "content": text,
                "source_file": str(dst_path),
            },
        )
        parsed = json.loads(raw) if raw else {}
    except Exception as e:
        logger.error("Ошибка MCP mempalace_add_drawer: %s", e)
        parsed = {"success": False, "error": str(e)}

    # Очищаем кэши комнат
    try:
        from .navigation import _drawer_list_state
        _drawer_list_state.pop(uid, None)
    except Exception as e:
        logger.debug("Не удалось очистить _drawer_list_state: %s", e)

    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="🚪 Открыть комнату", callback_data=f"p_r:{wing}:{room}",
        ),
    )
    kb.row(
        types.InlineKeyboardButton(
            text="📝 К неразобранным заметкам", callback_data="p_unfiled",
        ),
        types.InlineKeyboardButton(
            text="🏰 Главное меню Дворца", callback_data="palace_back",
        ),
    )

    if parsed.get("success") or not parsed.get("error"):
        rel_path = f"my_notes/{room}/{dst_path.name}"
        msg = (
            "✅ <b>Заметка успешно разложена во Дворец!</b>\n\n"
            f"🕸️ Крыло: <b>{safe_html_format(wing)}</b>\n"
            f"🚪 Комната: <b>{safe_html_format(room)}</b>\n"
            f"📁 Путь: <code>{safe_html_format(rel_path)}</code>\n\n"
            "Запись добавлена в индекс Чертогов Разума."
        )
    else:
        err = parsed.get("error", "неизвестная ошибка")
        msg = f"⚠️ Заметка перемещена на диске, но при индексации возникла ошибка: {err}"

    await cb.message.edit_text(msg, parse_mode="HTML", reply_markup=kb.as_markup())
