"""Unit tests for handlers.notes (prefix notes, archive reading, help)."""

import os
from types import SimpleNamespace

import pytest

from handlers import notes


class FakeBot:
    def __init__(self):
        self.messages = []

    async def get_file(self, file_id):
        return SimpleNamespace(file_path="p")

    async def download_file(self, file_path, destination=None):
        return None


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeMessage:
    def __init__(self, uid, text="", message_id=1):
        self.from_user = FakeUser(uid)
        self.text = text
        self.message_id = message_id
        self.bot = FakeBot()
        self.answers = []
        self.voice = SimpleNamespace(file_id="f")
        self.content_type = "text"

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append((text, parse_mode, reply_markup))
        return SimpleNamespace(edit_text=self._edit)

    async def _edit(self, text, parse_mode=None):
        pass


class FakeCb:
    def __init__(self, uid, data=""):
        self.from_user = FakeUser(uid)
        self.data = data
        self.answers_ = []
        self.message = FakeMessage(uid)
        self.answered = []

    async def answer(self, text=None, show_alert=None):
        self.answered.append((text, show_alert))


def _enable(monkeypatch, tmp_path):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {4242})
    d = tmp_path / "notes"
    d.mkdir()
    monkeypatch.setattr(notes, "NOTES_DIR", str(d))
    monkeypatch.setattr(notes, "INSIGHTS_DIR", str(tmp_path / "insights"))
    monkeypatch.setattr(notes, "RESEARCH_DIR", str(tmp_path / "research"))
    for sub in ("insights", "research"):
        (tmp_path / sub).mkdir(exist_ok=True)
    monkeypatch.setitem(notes.READ_MAP, "#!", str(d))
    monkeypatch.setitem(notes.READ_MAP, "#!!", str(tmp_path / "insights"))
    monkeypatch.setitem(notes.READ_MAP, "#??", str(tmp_path / "research"))
    return d


# ---------- /help ----------


@pytest.mark.asyncio
async def test_cmd_help_allowed(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage(4242)
    await notes.cmd_help(msg)
    assert msg.answers and "MemPalace: Справка" in msg.answers[0][0]
    assert msg.answers[0][1] == "HTML"


@pytest.mark.asyncio
async def test_cmd_help_not_allowed(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage(999)
    await notes.cmd_help(msg)
    assert msg.answers == []


@pytest.mark.asyncio
async def test_cb_help(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="show_help")
    await notes.cb_help(cb)
    assert cb.message.answers and "MemPalace: Справка" in cb.message.answers[0][0]
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cb_help_not_allowed(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(999, data="show_help")
    await notes.cb_help(cb)
    assert cb.answered == [("❌ Нет доступа", True)]


# ---------- archive read ----------


@pytest.mark.asyncio
async def test_cmd_read_archive_unknown_prefix_ignored(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage(4242, text="#zzz")
    await notes.cmd_read_archive(msg)
    assert msg.answers == []


@pytest.mark.asyncio
async def test_cmd_read_archive_known_prefix_shows_menu(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage(4242, text="#!")
    await notes.cmd_read_archive(msg)
    assert msg.answers and "Архив" in msg.answers[0][0]
    assert msg.answers[0][2] is not None


@pytest.mark.asyncio
async def test_cmd_read_archive_not_allowed(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage(999, text="#!")
    await notes.cmd_read_archive(msg)
    assert msg.answers == []


@pytest.mark.asyncio
async def test_cb_read_unknown_prefix(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="read|#xx|1")
    await notes.cb_read(cb)
    assert cb.answered == [("Папка не найдена", None)]


@pytest.mark.asyncio
async def test_cb_read_empty_dir(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="read|#!|3")
    await notes.cb_read(cb)
    assert cb.answered == [("Пусто", None)]


@pytest.mark.asyncio
async def test_cb_read_single_file(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    f = d / "note1.md"
    f.write_text("первая заметка", encoding="utf-8")
    os.utime(f, (1700000000, 1700000000))
    cb = FakeCb(4242, data="read|#!|1")
    await notes.cb_read(cb)
    assert len(cb.message.answers) == 1
    body = cb.message.answers[0][0]
    assert "первая заметка" in body
    assert "📅" in body
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cb_read_orders_by_mtime_newest_first(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    f1 = d / "old.md"
    f2 = d / "new.md"
    f1.write_text("старая", encoding="utf-8")
    f2.write_text("новая", encoding="utf-8")
    os.utime(f1, (1600000000, 1600000000))
    os.utime(f2, (1700000000, 1700000000))
    cb = FakeCb(4242, data="read|#!|2")
    await notes.cb_read(cb)
    assert "новая" in cb.message.answers[0][0]
    assert "старая" in cb.message.answers[1][0]


@pytest.mark.asyncio
async def test_cb_read_skips_hidden_files(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    hidden = d / ".hidden.md"
    visible = d / "ok.md"
    hidden.write_text("скрытый", encoding="utf-8")
    visible.write_text("видимый", encoding="utf-8")
    os.utime(hidden, (1700000000, 1700000000))
    os.utime(visible, (1600000000, 1600000000))
    cb = FakeCb(4242, data="read|#!|5")
    await notes.cb_read(cb)
    bodies = [a[0] for a in cb.message.answers]
    assert not any("скрытый" in b for b in bodies)
    assert any("видимый" in b for b in bodies)


@pytest.mark.asyncio
async def test_cb_read_long_note_split_into_parts(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    f = d / "long.md"
    f.write_text("слово " * 300, encoding="utf-8")  # ~1800 chars
    os.utime(f, (1700000000, 1700000000))
    cb = FakeCb(4242, data="read|#!|1")

    orig_split = notes.split_message
    parts = ["часть_А", "часть_Б", "часть_В"]
    monkeypatch.setattr(notes, "split_message", lambda t: parts)

    await notes.cb_read(cb)
    assert len(cb.message.answers) == 3
    assert cb.message.answers[0][0].startswith("📅") and "часть_А" in cb.message.answers[0][0]
    assert "часть_Б" in cb.message.answers[1][0]
    assert "часть_В" in cb.message.answers[2][0]
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cb_read_not_allowed(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(999, data="read|#!|1")
    await notes.cb_read(cb)
    assert cb.answered == [("❌ Нет доступа", True)]
