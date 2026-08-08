"""Тесты services/note_linker.py — семантическая привязка заметок.

Покрытие: экранирование MarkdownV2, парсинг результатов поиска, запись блока связей.
"""
import asyncio

import pytest

import services.note_linker as linker


# ─── escape_markdown_v2 ───


def test_escape_markdown_v2_empty():
    assert linker.escape_markdown_v2("") == ""


def test_escape_markdown_v2_none():
    assert linker.escape_markdown_v2(None) == ""


def test_escape_markdown_v2_special_chars():
    assert linker.escape_markdown_v2("a_b*c") == r"a\_b\*c"


def test_escape_markdown_v2_cyrillic_unchanged():
    text = "Фауст великий том"
    assert linker.escape_markdown_v2(text) == text


def test_escape_markdown_v2_brackets_and_pipe():
    result = linker.escape_markdown_v2("[x] | {y}")
    assert "\\[" in result
    assert "\\|" in result
    assert "\\{" in result


# ─── link_note_async ───


def test_link_async_appends_block(tmp_path, monkeypatch):
    note = tmp_path / "selfy_note.txt"
    note.write_text("изначальный текст", encoding="utf-8")

    async def fake_search(query, limit=None):
        return (
            "[1] selfy_note.txt\nсам себя\n---\n"
            "[2] other_file.txt\nпохожая заметка\n---\n"
            "[3] research/deep.txt\nглубокий текст"
        )

    monkeypatch.setattr(linker, "search_palace_context", fake_search)
    asyncio.run(
        linker.link_note_async(
            str(note), "достаточно длинный текст для запроса больше десяти символов"
        )
    )

    content = note.read_text(encoding="utf-8")
    assert "## 🔗 Связанные записи" in content
    assert "other\\_file\\.txt" in content
    assert "deep\\.txt" in content


def test_link_async_skips_own_note(tmp_path, monkeypatch):
    note = tmp_path / "room_to_050.txt"
    note.write_text("изначальный текст", encoding="utf-8")

    async def fake_search(query, limit=None):
        return "[1] room_to_050.txt\nsame file\n---\n[2] other/another_file.txt\nдругая"

    monkeypatch.setattr(linker, "search_palace_context", fake_search)
    asyncio.run(
        linker.link_note_async(str(note), "длинный контент для связывания заметки здесь")
    )

    content = note.read_text(encoding="utf-8")
    assert "another\\_file\\.txt" in content
    assert "room_to_050" not in content


def test_link_async_short_note_noop(tmp_path, monkeypatch):
    note = tmp_path / "short.txt"
    note.write_text("x", encoding="utf-8")
    asyncio.run(linker.link_note_async(str(note), "коротк"))
    assert note.read_text(encoding="utf-8") == "x"


def test_link_async_no_results_noop(tmp_path, monkeypatch):
    note = tmp_path / "n.txt"
    note.write_text("x", encoding="utf-8")

    async def fake_search(query, limit=None):
        return "Ничего не найдено"

    monkeypatch.setattr(linker, "search_palace_context", fake_search)
    asyncio.run(
        linker.link_note_async(str(note), "контент заметки для поиска более десяти символов")
    )
    assert note.read_text(encoding="utf-8") == "x"


def test_link_async_results_without_related_filenames(tmp_path, monkeypatch):
    """Все найденные = сама заметка → ничего не добавляется."""
    note = tmp_path / "alone.txt"
    note.write_text("x", encoding="utf-8")

    async def fake_search(query, limit=None):
        return "[1] alone.txt\nто же самое"

    monkeypatch.setattr(linker, "search_palace_context", fake_search)
    asyncio.run(
        linker.link_note_async(str(note), "достаточно длинный контент для связывания заметки")
    )
    assert note.read_text(encoding="utf-8") == "x"


def test_link_async_limits_to_6(tmp_path, monkeypatch):
    note = tmp_path / "target.txt"
    note.write_text("x", encoding="utf-8")

    items = "\n".join(f"[{i}] path{i}.txt\nописание {i}\n---" for i in range(20))

    async def fake_search(query, limit=None):
        return items

    monkeypatch.setattr(linker, "search_palace_context", fake_search)
    asyncio.run(
        linker.link_note_async(str(note), "длинный контент для проверки лимита шести записей")
    )
    content = note.read_text(encoding="utf-8")
    count = content.count("- path")
    assert count == 6


def test_link_async_exception_logged(tmp_path, monkeypatch, caplog):
    note = tmp_path / "zone.txt"
    note.write_text("x", encoding="utf-8")

    async def fake_search(query, limit=None):
        raise RuntimeError("broken")

    monkeypatch.setattr(linker, "search_palace_context", fake_search)
    asyncio.run(
        linker.link_note_async(str(note), "достаточно длинный контент для связывания заметки")
    )
    assert "Ошибка связывания" in caplog.text


def test_link_async_skips_blank_lines(tmp_path, monkeypatch):
    note = tmp_path / "self.txt"
    note.write_text("x", encoding="utf-8")

    async def fake_search(query, limit=None):
        return "[1] self.txt\nтекст\n---\n\n\n[2] other/b.txt\nсниппет\n---"

    monkeypatch.setattr(linker, "search_palace_context", fake_search)
    asyncio.run(
        linker.link_note_async(str(note), "достаточно длинный контент для связывания заметки")
    )
    content = note.read_text(encoding="utf-8")
    assert "b\\.txt" in content


def test_link_async_trailing_separator_keeps_none(tmp_path, monkeypatch):
    """После --- нет новых результатов: current_item остаётся None."""
    note = tmp_path / "self.txt"
    note.write_text("x", encoding="utf-8")

    async def fake_search(query, limit=None):
        return "---"

    monkeypatch.setattr(linker, "search_palace_context", fake_search)
    asyncio.run(
        linker.link_note_async(str(note), "достаточно длинный контент для связывания заметки")
    )
    assert note.read_text(encoding="utf-8") == "x"


def test_schedule_linking_with_running_loop(tmp_path, monkeypatch):
    note = tmp_path / "n.txt"
    seen = []

    async def fake_link(path, content, prefix):
        seen.append((path, content, prefix))

    monkeypatch.setattr(linker, "link_note_async", fake_link)

    async def inner():
        linker.schedule_linking(str(note), "контент", "!")
        await asyncio.sleep(0)

    asyncio.run(inner())
    assert seen == [(str(note), "контент", "!")]


def test_schedule_linking_without_loop(tmp_path, monkeypatch):
    note = tmp_path / "n.txt"
    seen = []

    async def fake_link(path, content, prefix):
        seen.append((path, content, prefix))

    monkeypatch.setattr(linker, "link_note_async", fake_link)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        linker.schedule_linking(str(note), "контент", "!")
    finally:
        loop.close()
    assert seen == [(str(note), "контент", "!")]


def test_schedule_linking_no_loop_fallback(tmp_path, monkeypatch):
    note = tmp_path / "n.txt"
    seen = []

    async def fake_link(path, content, prefix):
        seen.append((path, content, prefix))

    monkeypatch.setattr(linker, "link_note_async", fake_link)

    def boom():
        raise RuntimeError("no running loop")

    monkeypatch.setattr(linker.asyncio, "get_event_loop", boom)
    linker.schedule_linking(str(note), "контент", "!")
    assert seen == [(str(note), "контент", "!")]
