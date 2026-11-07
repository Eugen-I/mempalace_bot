"""Unit tests for handlers.transkript."""

import os
import time
from types import SimpleNamespace

import pytest

from handlers import transkript as tr


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeMessage:
    def __init__(self, uid=4242, text=""):
        self.from_user = FakeUser(uid)
        self.text = text
        self.answers = []
        self.edits = []

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append((text, parse_mode, reply_markup))
        status = SimpleNamespace(edits=[], deleted=False, answers=[])
        status.edit_text = _make_edit(status.edits)

        async def _ans(t, parse_mode=None, reply_markup=None):
            status.answers.append((t, parse_mode, reply_markup))

        status.answer = _ans
        self.status = status
        return status

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append((text, parse_mode, reply_markup))


def _make_edit(store):
    async def _edit(text, parse_mode=None, reply_markup=None):
        store.append((text, reply_markup))

    return _edit


class FakeCb:
    def __init__(self, uid=4242, data=""):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = FakeMessage(uid)
        self.answered = []

    async def answer(self, text=None, show_alert=None, parse_mode=None, reply_markup=None):
        if parse_mode is not None:
            self.message.answers.append((text, parse_mode, reply_markup))
        else:
            self.answered.append((text, show_alert))

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.message.edits.append((text, parse_mode, reply_markup))


def _enable(monkeypatch, tmp_path):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {4242})
    d = tmp_path / "transkript"
    d.mkdir()
    monkeypatch.setattr(tr, "TRANSKRIPT_DIR", str(d))
    monkeypatch.setattr("services.text_formatter.safe_html_format", lambda t: t)
    monkeypatch.setattr(
        "services.text_formatter.split_message", lambda t, limit=4000: [t],
    )
    return d


def _clear_caches():
    tr._tr_content_cache.clear()
    tr._tr_ai_waiting.clear()
    tr._tr_last_question.clear()


@pytest.fixture(autouse=True)
def _clean_caches():
    _clear_caches()
    from handlers.personal_note import _quote_waiting

    _quote_waiting.clear()
    from handlers.palace.save import _save_state

    _save_state.pop(4242, None)
    yield
    _clear_caches()


def _write_file(d, name, content, mtime):
    p = d / name
    p.write_text(content, encoding="utf-8")
    os.utime(p, (mtime, mtime))
    return p


# ---------- _list_files ----------


def test_list_files_missing_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(tr, "TRANSKRIPT_DIR", str(tmp_path / "nope"))
    assert tr._list_files() == []


def test_list_files_filters_and_sorts(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "b.txt", "b", 100)
    _write_file(d, "a.txt", "a", 200)
    _write_file(d, "skip.log", "s", 300)
    assert tr._list_files() == ["a.txt", "b.txt"]


# ---------- cmd_transkript ----------


@pytest.mark.asyncio
async def test_cmd_transkript_empty(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage()
    await tr.cmd_transkript(msg)
    assert msg.answers[0][0] == "📂 Папка transkript пуста."


@pytest.mark.asyncio
async def test_cmd_transkript_with_files(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "meet.txt", "x", 100)
    msg = FakeMessage()
    await tr.cmd_transkript(msg)
    assert msg.answers[0][0].startswith("📜")
    assert "meet.txt" in msg.answers[0][0]
    assert msg.answers[0][2] is not None


@pytest.mark.asyncio
async def test_cmd_transkript_not_allowed(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage(uid=999)
    await tr.cmd_transkript(msg)
    assert msg.answers == []


def _real_cb(monkeypatch, data=""):
    from aiogram import types

    async def noop_edit(self, text, parse_mode=None, reply_markup=None):
        pass

    async def noop_answer(self, text, parse_mode=None, reply_markup=None):
        pass

    monkeypatch.setattr(types.Message, "edit_text", noop_edit)
    monkeypatch.setattr(types.Message, "answer", noop_answer)
    monkeypatch.setattr(
        types.CallbackQuery, "answer",
        lambda self, text=None, show_alert=None: None,
    )
    msg = types.Message(
        message_id=1, date=0, chat=types.Chat(id=1, type="private"),
        from_user=types.User(id=4242, is_bot=False, first_name="t"), text="x",
    )
    return types.CallbackQuery(
        id="1", from_user=types.User(id=4242, is_bot=False, first_name="t"),
        chat_instance="x", message=msg, data=data,
    )


# ---------- _show_page ----------


@pytest.mark.asyncio
async def test_show_page_real_callback_edit(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "one.txt", "x", 100)
    cb = _real_cb(monkeypatch, data="tr_page:0")
    await tr._show_page(cb, ["one.txt"], 0)


@pytest.mark.asyncio
async def test_show_content_page_no_cache_real_callback(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = _real_cb(monkeypatch, data="tr_cp:0")
    await tr._show_content_page(cb, 4242, 0)


@pytest.mark.asyncio
async def test_show_content_page_real_callback_edit(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    tr._tr_content_cache[4242] = {
        "pages": ["стр1"], "total": 1, "idx": 0,
        "fname": "a.txt", "dt": "01.01.2026",
    }
    cb = _real_cb(monkeypatch, data="tr_cp:0")
    await tr._show_content_page(cb, 4242, 0)


@pytest.mark.asyncio
async def test_show_page_message_target(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "one.txt", "x", 100)
    msg = FakeMessage()
    await tr._show_page(msg, ["one.txt"], 0)
    assert msg.answers[0][0].startswith("📜")
    assert "one.txt" in msg.answers[0][0]


@pytest.mark.asyncio
async def test_show_page_callback_target(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "one.txt", "x", 100)
    cb = FakeCb(data="tr_page:0")
    await tr._show_page(cb, ["one.txt"], 0)
    assert cb.message.answers[0][0].startswith("📜")
    assert cb.message.answers[0][1] == "HTML"


@pytest.mark.asyncio
async def test_show_page_prev_and_next_buttons(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    for i in range(12):
        _write_file(d, f"f{i}.txt", "x", 100 + i)
    files = [f"f{i}.txt" for i in range(11, -1, -1)]
    cb = FakeCb(data="tr_page:5")
    await tr._show_page(cb, files, 5)
    markup = cb.message.answers[0][2]
    texts = [b.text for row in markup.inline_keyboard for b in row]
    assert "◀️" in texts
    assert "▶️" in texts
    assert "tr_page:0" in [b.callback_data for row in markup.inline_keyboard for b in row]
    assert "tr_page:10" in [b.callback_data for row in markup.inline_keyboard for b in row]


@pytest.mark.asyncio
async def test_show_page_no_nav_on_single_page(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "one.txt", "x", 100)
    cb = FakeCb(data="tr_page:0")
    await tr._show_page(cb, ["one.txt"], 0)
    markup = cb.message.answers[0][2]
    texts = [b.text for row in markup.inline_keyboard for b in row]
    assert "◀️" not in texts
    assert "▶️" not in texts


@pytest.mark.asyncio
async def test_show_page_long_name_truncated(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    long_name = "a" * 60 + ".txt"
    _write_file(d, long_name, "x", 100)
    cb = FakeCb(data="tr_page:0")
    await tr._show_page(cb, [long_name], 0)
    assert ".." in cb.message.answers[0][0]


# ---------- cb_tr_page ----------


@pytest.mark.asyncio
async def test_cb_tr_page_empty(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(data="tr_page:0")
    await tr.cb_tr_page(cb)
    assert cb.answered == [("Папка пуста.", None)]


@pytest.mark.asyncio
async def test_cb_tr_page_success(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "a.txt", "x", 100)
    cb = FakeCb(data="tr_page:0")
    await tr.cb_tr_page(cb)
    assert cb.message.answers
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cb_tr_page_not_allowed(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(uid=999, data="tr_page:0")
    await tr.cb_tr_page(cb)
    assert cb.answered == [("❌ Нет доступа", True)]


# ---------- cb_tr_read ----------


@pytest.mark.asyncio
async def test_cb_tr_read_idx_out_of_range(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "a.txt", "x", 100)
    cb = FakeCb(data="tr_read:5")
    await tr.cb_tr_read(cb)
    assert cb.answered == [("Файл не найден.", None)]


@pytest.mark.asyncio
async def test_cb_tr_read_read_error(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "a.txt", "x", 100)

    def boom(path, encoding="utf-8"):
        raise OSError("нет файла")

    monkeypatch.setattr("builtins.open", boom)
    cb = FakeCb(data="tr_read:0")
    await tr.cb_tr_read(cb)
    assert "Ошибка чтения" in cb.message.answers[0][0]


@pytest.mark.asyncio
async def test_cb_tr_read_success(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "a.txt", "длинный контент", 100)
    cb = FakeCb(data="tr_read:0")
    await tr.cb_tr_read(cb)
    assert cb.message.answers[0][0].startswith("📜")
    assert "длинный контент" in cb.message.answers[0][0]
    assert tr._tr_content_cache[4242]["fname"] == "a.txt"
    assert tr._tr_content_cache[4242]["idx"] == 0
    assert cb.answered == [(None, None)]


# ---------- _show_content_page ----------


@pytest.mark.asyncio
async def test_show_content_page_no_cache_callback(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(data="tr_cp:0")
    await tr._show_content_page(cb, 4242, 0)
    assert cb.message.answers == []


@pytest.mark.asyncio
async def test_show_content_page_no_cache_message(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage()
    await tr._show_content_page(msg, 4242, 0)
    assert msg.answers == []


@pytest.mark.asyncio
async def test_show_content_page_idx_clamped(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    tr._tr_content_cache[4242] = {
        "pages": ["стр1", "стр2"], "total": 2, "idx": 0,
        "fname": "a.txt", "dt": "01.01.2026 10:00",
    }
    cb = FakeCb(data="tr_cp:99")
    await tr._show_content_page(cb, 4242, 99)
    assert "стр2" in cb.message.answers[0][0]
    assert tr._tr_content_cache[4242]["idx"] == 1


@pytest.mark.asyncio
async def test_show_content_page_nav_middle(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    tr._tr_content_cache[4242] = {
        "pages": ["a", "b", "c"], "total": 3, "idx": 0,
        "fname": "a.txt", "dt": "01.01.2026",
    }
    cb = FakeCb(data="tr_cp:1")
    await tr._show_content_page(cb, 4242, 1)
    texts = [b.text for row in cb.message.answers[0][2].inline_keyboard for b in row]
    assert "◀️" in texts and "▶️" in texts
    assert "2/3" in texts
    callbacks = [
        b.callback_data
        for row in cb.message.answers[0][2].inline_keyboard
        for b in row
    ]
    assert "tr_cp:0" in callbacks


# ---------- cb_tr_content_page ----------


@pytest.mark.asyncio
async def test_cb_tr_content_page_noop(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(data="tr_cp:noop")
    await tr.cb_tr_content_page(cb)
    assert cb.answered == [(None, None)]
    assert cb.message.edits == []


@pytest.mark.asyncio
async def test_cb_tr_content_page_success(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    tr._tr_content_cache[4242] = {
        "pages": ["a", "b"], "total": 2, "idx": 0,
        "fname": "a.txt", "dt": "01.01.2026",
    }
    cb = FakeCb(data="tr_cp:1")
    await tr.cb_tr_content_page(cb)
    assert "b" in cb.message.answers[0][0]
    assert cb.answered == [(None, None)]


# ---------- _get_content ----------


def test_get_content_no_cache():
    assert tr._get_content(4242) == ""


def test_get_content_no_fname(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    tr._tr_content_cache[4242] = {"fname": "", "pages": [], "total": 0, "idx": 0, "dt": ""}
    assert tr._get_content(4242) == ""


def test_get_content_read_error(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "a.txt", "данные", 100)
    tr._tr_content_cache[4242] = {
        "fname": "a.txt", "pages": [], "total": 0, "idx": 0, "dt": "",
    }

    def boom(path, encoding="utf-8"):
        raise OSError("нет файла")

    monkeypatch.setattr("builtins.open", boom)
    assert tr._get_content(4242) == ""


def test_get_content_success(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "a.txt", "данные", 100)
    tr._tr_content_cache[4242] = {
        "fname": "a.txt", "pages": [], "total": 0, "idx": 0, "dt": "",
    }
    assert tr._get_content(4242) == "данные"


# ---------- cb_tr_ai ----------


@pytest.mark.asyncio
async def test_cb_tr_ai_no_cache(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(data="tr_ai")
    await tr.cb_tr_ai(cb)
    assert "Сессия истекла" in cb.message.edits[0][0]
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cb_tr_ai_success(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    tr._tr_content_cache[4242] = {
        "fname": "a.txt", "pages": ["x"], "total": 1, "idx": 0, "dt": "",
    }
    cb = FakeCb(data="tr_ai")
    await tr.cb_tr_ai(cb)
    assert "Задайте вопрос" in cb.message.edits[0][0]
    assert tr._tr_ai_waiting[4242] == {"fname": "a.txt", "mode": "ask"}


# ---------- cb_tr_ai_web ----------


@pytest.mark.asyncio
async def test_cb_tr_ai_web_no_question(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(data="tr_ai_web")
    await tr.cb_tr_ai_web(cb)
    assert "Сначала задайте вопрос" in cb.message.answers[0][0]


@pytest.mark.asyncio
async def test_cb_tr_ai_web_no_cache(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    tr._tr_last_question[4242] = "вопрос"
    cb = FakeCb(data="tr_ai_web")
    await tr.cb_tr_ai_web(cb)
    assert "Сессия истекла" in cb.message.edits[0][0]


@pytest.mark.asyncio
async def test_cb_tr_ai_web_success(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "a.txt", "контент транскрипта", 100)
    tr._tr_content_cache[4242] = {
        "fname": "a.txt", "pages": ["x"], "total": 1, "idx": 0, "dt": "",
    }
    tr._tr_last_question[4242] = "вопрос"
    monkeypatch.setattr(
        "services.web_search.search_web",
        _async_result("результаты"),
    )
    monkeypatch.setattr(
        "services.ai_engine.get_current_ai", lambda: ("ollama", "llama3"),
    )
    monkeypatch.setattr(
        "services.ai_engine._sync_ai_call", lambda *a, **k: "ответ с интернетом",
    )
    cb = FakeCb(data="tr_ai_web")
    await tr.cb_tr_ai_web(cb)
    bodies = [a[0] for a in cb.message.answers]
    assert any("Ищу в интернете" in b for b in bodies)
    assert any("ответ с интернетом" in t[0] for t in cb.message.status.edits)
    assert tr._tr_last_question[4242] == "вопрос"


# ---------- cb_tr_q ----------


@pytest.mark.asyncio
async def test_cb_tr_q_no_cache(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(data="tr_q")
    await tr.cb_tr_q(cb)
    assert "Сессия истекла" in cb.message.edits[0][0]


@pytest.mark.asyncio
async def test_cb_tr_q_read_error(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "a.txt", "данные", 100)
    tr._tr_content_cache[4242] = {
        "fname": "a.txt", "pages": [], "total": 0, "idx": 0, "dt": "",
    }

    def boom(path, encoding="utf-8"):
        raise OSError("нет файла")

    monkeypatch.setattr("builtins.open", boom)
    cb = FakeCb(data="tr_q")
    await tr.cb_tr_q(cb)
    assert "Не удалось прочитать" in cb.message.edits[0][0]


@pytest.mark.asyncio
async def test_cb_tr_q_success(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "a.txt", "текст для цитаты", 100)
    tr._tr_content_cache[4242] = {
        "fname": "a.txt", "pages": [], "total": 0, "idx": 0, "dt": "",
    }
    cb = FakeCb(data="tr_q")
    await tr.cb_tr_q(cb)
    assert "Отправьте цитату" in cb.message.edits[0][0]
    assert "текст для цитаты" in cb.message.edits[0][0]
    from handlers.personal_note import _quote_waiting

    assert _quote_waiting[4242] == {"content": "текст для цитаты", "drawer_id": ""}


# ---------- cb_tr_save ----------


@pytest.mark.asyncio
async def test_cb_tr_save_no_content(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(data="tr_save")
    await tr.cb_tr_save(cb)
    assert "Сессия истекла" in cb.message.edits[0][0]


@pytest.mark.asyncio
async def test_cb_tr_save_success(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "a.txt", "сохраняемый текст", 100)
    tr._tr_content_cache[4242] = {
        "fname": "a.txt", "pages": [], "total": 0, "idx": 0, "dt": "",
    }
    shown = []

    async def fake_show_save_wings(edit_func, uid):
        shown.append((edit_func, uid))
        await edit_func("выбор крыла")

    monkeypatch.setattr("handlers.palace.save._show_save_wings", fake_show_save_wings)
    cb = FakeCb(data="tr_save")
    await tr.cb_tr_save(cb)
    from handlers.palace.save import _save_state

    assert _save_state[4242] == {"text": "сохраняемый текст", "mode": "full"}
    assert shown[0][1] == 4242


# ---------- cb_tr_links ----------


@pytest.mark.asyncio
async def test_cb_tr_links_no_cache(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(data="tr_links")
    await tr.cb_tr_links(cb)
    assert "Сессия истекла" in cb.message.edits[0][0]


@pytest.mark.asyncio
async def test_cb_tr_links_read_error(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "a.txt", "данные", 100)
    tr._tr_content_cache[4242] = {
        "fname": "a.txt", "pages": [], "total": 0, "idx": 0, "dt": "",
    }

    def boom(path, encoding="utf-8"):
        raise OSError("нет файла")

    monkeypatch.setattr("builtins.open", boom)
    cb = FakeCb(data="tr_links")
    await tr.cb_tr_links(cb)
    assert "Не удалось прочитать" in cb.message.edits[0][0]


@pytest.mark.asyncio
async def test_cb_tr_links_no_results(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "a.txt", "данные", 100)
    tr._tr_content_cache[4242] = {
        "fname": "a.txt", "pages": [], "total": 0, "idx": 0, "dt": "",
    }
    monkeypatch.setattr(
        "services.palace_bridge.search_palace_with_sources",
        _async_result(("", [])),
    )
    cb = FakeCb(data="tr_links")
    await tr.cb_tr_links(cb)
    assert cb.message.status.edits[0][0] == "🔗 Связанных записей в MemPalace не найдено."


@pytest.mark.asyncio
async def test_cb_tr_links_success(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "a.txt", "данные", 100)
    tr._tr_content_cache[4242] = {
        "fname": "a.txt", "pages": [], "total": 0, "idx": 0, "dt": "",
    }
    monkeypatch.setattr(
        "services.palace_bridge.search_palace_with_sources",
        _async_result(("связи текст", [{"id": 7, "wing": "w", "room": "r"}])),
    )
    cb = FakeCb(data="tr_links")
    await tr.cb_tr_links(cb)
    assert cb.message.status.edits[0][0].startswith("🔗 <b>Смысловые связи")
    markup = cb.message.status.edits[0][1]
    assert markup is not None
    texts = [b.text for row in markup.inline_keyboard for b in row]
    assert any("Читать [7]" in t for t in texts)


@pytest.mark.asyncio
async def test_cb_tr_links_error(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "a.txt", "данные", 100)
    tr._tr_content_cache[4242] = {
        "fname": "a.txt", "pages": [], "total": 0, "idx": 0, "dt": "",
    }

    async def boom(q, limit=5):
        raise RuntimeError("сеть упала")

    monkeypatch.setattr("services.palace_bridge.search_palace_with_sources", boom)
    cb = FakeCb(data="tr_links")
    await tr.cb_tr_links(cb)
    # format_user_error для RuntimeError возвращает "❌ Ошибка выполнения"
    assert "Ошибка выполнения" in cb.message.status.edits[0][0]


# ---------- cb_tr_del / cb_tr_del_yes ----------


@pytest.mark.asyncio
async def test_cb_tr_del_confirmation(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(data="tr_del")
    await tr.cb_tr_del(cb)
    assert "Удалить транскрипт?" in cb.message.edits[0][0]
    texts = [b.text for row in cb.message.edits[0][2].inline_keyboard for b in row]
    assert "✅ Удалить" in texts and "❌ Нет" in texts


@pytest.mark.asyncio
async def test_cb_tr_del_yes_no_cache(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(data="tr_del_yes")
    await tr.cb_tr_del_yes(cb)
    assert "Сессия истекла" in cb.message.edits[0][0]


@pytest.mark.asyncio
async def test_cb_tr_del_yes_success(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    p = _write_file(d, "a.txt", "данные", 100)
    tr._tr_content_cache[4242] = {
        "fname": "a.txt", "pages": [], "total": 0, "idx": 0, "dt": "",
    }
    cb = FakeCb(data="tr_del_yes")
    await tr.cb_tr_del_yes(cb)
    assert not p.exists()
    assert "Транскрипт удалён" in cb.message.edits[0][0]
    assert 4242 not in tr._tr_content_cache


@pytest.mark.asyncio
async def test_cb_tr_del_yes_remove_error(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "a.txt", "данные", 100)
    tr._tr_content_cache[4242] = {
        "fname": "a.txt", "pages": [], "total": 0, "idx": 0, "dt": "",
    }

    def boom(path):
        raise PermissionError("занят")

    monkeypatch.setattr(tr.os, "remove", boom)
    cb = FakeCb(data="tr_del_yes")
    await tr.cb_tr_del_yes(cb)
    # format_user_error для PermissionError возвращает "❌ Нет прав доступа"
    assert "Нет прав доступа" in cb.message.edits[0][0]


# ---------- _answer_tr_ai / handle_tr_ai_question ----------


def _async_result(value):
    async def _inner(*a, **kw):
        return value

    return _inner


@pytest.mark.asyncio
async def test_answer_tr_ai_read_error(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    st = SimpleNamespace(edits=[])
    st.edit_text = _make_edit(st.edits)

    def boom(path, encoding="utf-8"):
        raise OSError("нет файла")

    monkeypatch.setattr("builtins.open", boom)
    await tr._answer_tr_ai(st, 4242, "a.txt", "вопрос")
    assert "Ошибка чтения" in st.edits[0][0]


@pytest.mark.asyncio
async def test_answer_tr_ai_empty_content(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "a.txt", "   ", 100)
    st = SimpleNamespace(edits=[])
    st.edit_text = _make_edit(st.edits)
    await tr._answer_tr_ai(st, 4242, "a.txt", "вопрос")
    assert "Транскрипт пуст" in st.edits[0][0]


@pytest.mark.asyncio
async def test_answer_tr_ai_no_web(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "a.txt", "контент транскрипта", 100)
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("ollama", "llama3"))
    called = {}

    def fake_sync(engine, model, messages):
        called["messages"] = messages
        return "ответ по транскрипту"

    monkeypatch.setattr("services.ai_engine._sync_ai_call", fake_sync)
    st = SimpleNamespace(edits=[])
    st.edit_text = _make_edit(st.edits)
    await tr._answer_tr_ai(st, 4242, "a.txt", "вопрос", with_web=False)
    assert st.edits[0][0] == "ответ по транскрипту"
    assert "ИСКЛЮЧИТЕЛЬНО" in called["messages"][0]["content"]
    assert tr._tr_last_question[4242] == "вопрос"


@pytest.mark.asyncio
async def test_answer_tr_ai_with_web(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "a.txt", "контент транскрипта", 100)
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("ollama", "llama3"))
    monkeypatch.setattr("services.web_search.search_web", _async_result("веб"))
    monkeypatch.setattr("services.ai_engine._sync_ai_call", lambda *a, **k: "ответ+веб")
    st = SimpleNamespace(edits=[])
    st.edit_text = _make_edit(st.edits)
    await tr._answer_tr_ai(st, 4242, "a.txt", "вопрос", with_web=True)
    assert st.edits[0][0] == "ответ+веб"


@pytest.mark.asyncio
async def test_answer_tr_ai_empty_result(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "a.txt", "контент", 100)
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("ollama", "llama3"))
    monkeypatch.setattr("services.ai_engine._sync_ai_call", lambda *a, **k: "")
    st = SimpleNamespace(edits=[])
    st.edit_text = _make_edit(st.edits)
    await tr._answer_tr_ai(st, 4242, "a.txt", "вопрос")
    assert "Пустой ответ" in st.edits[0][0]


@pytest.mark.asyncio
async def test_answer_tr_ai_does_not_block_event_loop(monkeypatch, tmp_path, heartbeat):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "a.txt", "контент", 100)
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("ollama", "llama3"))

    def slow_sync(*a, **k):
        time.sleep(0.03)
        return "ответ"

    monkeypatch.setattr("services.ai_engine._sync_ai_call", slow_sync)
    st = SimpleNamespace(edits=[])
    st.edit_text = _make_edit(st.edits)

    async with heartbeat(interval=0.005) as hb:
        await tr._answer_tr_ai(st, 4242, "a.txt", "вопрос")

    assert hb.ticks >= 1
    assert st.edits[0][0] == "ответ"


@pytest.mark.asyncio
async def test_answer_tr_ai_error_replaces_status(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "a.txt", "контент", 100)
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("ollama", "llama3"))

    async def failing_ai(*a, **k):
        raise RuntimeError("ai down")

    monkeypatch.setattr(tr, "call_ai_async", failing_ai)
    st = SimpleNamespace(edits=[])
    st.edit_text = _make_edit(st.edits)
    await tr._answer_tr_ai(st, 4242, "a.txt", "вопрос")
    assert "Ошибка выполнения" in st.edits[0][0]


@pytest.mark.asyncio
async def test_answer_tr_ai_timeout_replaces_status(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "a.txt", "контент", 100)
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("ollama", "llama3"))

    async def timed_out(*a, **k):
        raise tr.AITimeoutError("too slow")

    monkeypatch.setattr(tr, "call_ai_async", timed_out)
    st = SimpleNamespace(edits=[])
    st.edit_text = _make_edit(st.edits)
    await tr._answer_tr_ai(st, 4242, "a.txt", "вопрос")
    assert st.edits[0][0] == "⏱️ ИИ не ответил вовремя. Попробуйте ещё раз."


@pytest.mark.asyncio
async def test_handle_tr_ai_question(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "a.txt", "контент", 100)
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("ollama", "llama3"))
    monkeypatch.setattr("services.ai_engine._sync_ai_call", lambda *a, **k: "ответ")
    msg = FakeMessage()
    await tr.handle_tr_ai_question(4242, msg, "a.txt", "вопрос")
    assert msg.answers[0][0] == "🤔 Анализирую транскрипт..."
    status = msg.answers[0][0]
    assert status is not None


@pytest.mark.asyncio
async def test_answer_tr_ai_long_result_splits(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "a.txt", "контент транскрипта", 100)
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("ollama", "llama3"))
    long_reply = ("Абзац текста для проверки разбиения сообщения.\n\n" * 150)
    monkeypatch.setattr("services.ai_engine._sync_ai_call", lambda *a, **k: long_reply)

    answers = []
    st = SimpleNamespace(edits=[])
    st.edit_text = _make_edit(st.edits)

    async def fake_answer(text, parse_mode=None, **kw):
        answers.append((text, parse_mode))

    st.answer = fake_answer

    await tr._answer_tr_ai(st, 4242, "a.txt", "вопрос", with_web=False)
    assert len(st.edits) == 1
    assert len(st.edits[0][0]) <= 4000
    assert len(answers) > 0


@pytest.mark.asyncio
async def test_answer_tr_ai_html_error_falls_back_to_plain_text(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_file(d, "a.txt", "контент", 100)
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("ollama", "llama3"))
    monkeypatch.setattr(
        "services.ai_engine._sync_ai_call",
        lambda *a, **k: "Ответ с <незакрытым тегом",
    )

    st = SimpleNamespace(edits=[], edit_count=0)

    async def fake_edit(text, parse_mode=None, **kw):
        st.edit_count += 1
        if parse_mode == "HTML":
            raise RuntimeError("TelegramBadRequest: can't parse entities")
        st.edits.append((text, parse_mode))

    st.edit_text = fake_edit

    await tr._answer_tr_ai(st, 4242, "a.txt", "вопрос", with_web=False)
    assert len(st.edits) == 1
    assert st.edits[0][1] is None
