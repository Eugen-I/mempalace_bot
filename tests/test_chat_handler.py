"""Unit tests for handlers.chat."""

import json
from types import SimpleNamespace

import pytest

from handlers import chat as ch
from services import chat_store, chat_sync


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeMessage:
    def __init__(self, uid=4242, text=""):
        self.from_user = FakeUser(uid)
        self.text = text
        self.answers = []
        self.edits = []
        self.chat = SimpleNamespace(id=100 + uid)
        self.message_id = uid * 10
        self.deleted = False

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append((text, parse_mode, reply_markup))
        return self

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append((text, parse_mode, reply_markup))

    async def edit_reply_markup(self, reply_markup=None):
        self.reply_markup = reply_markup

    async def delete(self):
        self.deleted = True

    async def answer_document(self, document, caption=None, parse_mode=None):
        self.sent_document = (document, caption)


class FakeCb:
    def __init__(self, uid=4242, data="", message=None):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = message or FakeMessage(uid)
        self.answered = []

    async def answer(self, text=None, show_alert=None):
        self.answered.append((text, show_alert))

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.message.edits.append((text, parse_mode, reply_markup))


@pytest.fixture(autouse=True)
def _clean_state():
    ch.user_sessions.clear()
    ch.waiting_for_name.clear()
    ch._chat_callback_cache.clear()
    yield
    ch.user_sessions.clear()
    ch.waiting_for_name.clear()
    ch._chat_callback_cache.clear()


def _enable(monkeypatch, tmp_path):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {4242})
    d = tmp_path / "chats"
    d.mkdir()
    monkeypatch.setattr(ch, "CHATS_DIR", str(d))
    monkeypatch.setattr(ch, "secrets", SimpleNamespace(token_hex=lambda n: "abcd"))
    monkeypatch.setattr("services.text_formatter.safe_html_format", lambda t: t)
    monkeypatch.setattr(
        "services.text_formatter.split_message", lambda t, limit=4000: [t],
    )
    return d


def _write_chat(d, fname, messages, summary=""):
    p = d / fname
    p.write_text(
        json.dumps({"summary": summary, "messages": messages}, ensure_ascii=False),
        encoding="utf-8",
    )
    return p


# ---------- _short_id / load_chat / save_chat / save_summary_file ----------


def test_short_id_stores_mapping(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    sid = ch._short_id("ch_1.json")
    assert sid == "abcd"
    assert ch._chat_callback_cache["abcd"] == "ch_1.json"


def test_load_chat_missing_file(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    assert ch.load_chat(str(tmp_path / "nope.json")) == {"summary": "", "messages": []}


def test_load_chat_plain_list(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    p = d / "ch_list.json"
    p.write_text(json.dumps([{"role": "user", "content": "hi"}]), encoding="utf-8")
    data = ch.load_chat(str(p))
    assert data["messages"] == [{"role": "user", "content": "hi"}]
    saved = json.loads(p.read_text(encoding="utf-8"))
    assert "summary" in saved


def test_load_chat_dict(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    p = _write_chat(d, "ch_1.json", [{"role": "user", "content": "x"}], "sum")
    data = ch.load_chat(str(p))
    assert data["summary"] == "sum"


def test_load_chat_corrupt_json_backs_up_original(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    p = d / "ch_bad.json"
    p.write_text("{broken", encoding="utf-8")

    data = ch.load_chat(str(p))

    assert data == {"summary": "", "messages": []}
    assert p.exists()
    assert p.read_text(encoding="utf-8") == "{broken"
    backups = list(d.glob("ch_bad.json.corrupt.*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "{broken"


def test_load_chat_invalid_root_backs_up_original(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    p = d / "ch_scalar.json"
    p.write_text('"not a chat"', encoding="utf-8")

    data = ch.load_chat(str(p))

    assert data == {"summary": "", "messages": []}
    assert p.exists()
    assert len(list(d.glob("ch_scalar.json.corrupt.*"))) == 1


def test_load_chat_corrupt_backup_failure_is_safe(
    monkeypatch, tmp_path, caplog,
):
    d = _enable(monkeypatch, tmp_path)
    p = d / "ch_bad.json"
    p.write_text("{broken", encoding="utf-8")

    def boom(*a, **kw):
        raise OSError("backup failed")

    monkeypatch.setattr(chat_store.shutil, "copy2", boom)

    assert ch.load_chat(str(p)) == {"summary": "", "messages": []}
    assert p.read_text(encoding="utf-8") == "{broken"
    assert "резервная копия: не создана" in caplog.text


def test_load_chat_list_migration_save_failure_returns_data(
    monkeypatch, tmp_path, caplog,
):
    d = _enable(monkeypatch, tmp_path)
    p = d / "ch_list.json"
    p.write_text('[{"role": "user", "content": "hi"}]', encoding="utf-8")
    monkeypatch.setattr(chat_store, "save_chat", lambda path, data: False)

    data = ch.load_chat(str(p))

    assert data["messages"] == [{"role": "user", "content": "hi"}]
    assert "Не удалось мигрировать чат" in caplog.text


def test_save_chat_roundtrip(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    p = d / "ch_1.json"
    assert ch.save_chat(str(p), {"summary": "s", "messages": []}) is True
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data == {"summary": "s", "messages": []}


def test_save_chat_error_returns_false(monkeypatch, tmp_path, caplog):
    _enable(monkeypatch, tmp_path)

    def boom(*a, **kw):
        raise OSError("disk")

    monkeypatch.setattr(chat_store.tempfile, "NamedTemporaryFile", boom)
    assert ch.save_chat(str(tmp_path / "x.json"), {"messages": []}) is False
    assert "Не удалось сохранить чат" in caplog.text


def test_save_chat_missing_directory_returns_false(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    target = tmp_path / "missing" / "x.json"
    assert ch.save_chat(str(target), {"messages": []}) is False
    assert not target.exists()


def test_save_chat_replace_error_keeps_original(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    p = d / "ch_1.json"
    original = '{"summary": "old", "messages": []}'
    p.write_text(original, encoding="utf-8")

    def boom(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr(chat_store.os, "replace", boom)

    assert ch.save_chat(str(p), {"summary": "new", "messages": []}) is False
    assert p.read_text(encoding="utf-8") == original
    assert list(d.iterdir()) == [p]


def test_save_summary_file(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch.save_summary_file("ch_1.json", "саммари")
    assert (d / "ch_1_summary.txt").read_text(encoding="utf-8") == "саммари"


# ---------- export_chat_to_md ----------


def test_export_chat_to_md_missing(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    assert ch.export_chat_to_md(str(tmp_path / "nope.json")) is None


def test_export_chat_to_md_empty_messages(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    p = _write_chat(d, "ch_1.json", [])
    assert ch.export_chat_to_md(str(p)) is None


def test_export_chat_to_md_success(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    p = _write_chat(
        d, "ch_1.json",
        [
            {"role": "user", "content": "привет"},
            {"role": "assistant", "content": "здравствуй"},
            {"role": "user", "content": "   "},
        ],
    )
    md = ch.export_chat_to_md(str(p))
    assert md is not None
    with open(md, encoding="utf-8") as f:
        text = f.read()
    assert "Диалог: ch_1" in text
    assert "👤 Вы" in text
    assert "🤖 ИИ" in text
    assert "привет" in text
    assert "   " not in text


# ---------- cmd_new_chat / cmd_list_chats ----------


@pytest.mark.asyncio
async def test_cmd_new_chat(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage()
    await ch.cmd_new_chat(msg)
    assert msg.answers[0][0] == "📝 Введите название для нового чата:"
    assert ch.waiting_for_name[4242] is True


@pytest.mark.asyncio
async def test_cmd_list_chats_empty(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage()
    await ch.cmd_list_chats(msg)
    assert msg.answers[0][0] == "📁 Чатов нет."


@pytest.mark.asyncio
async def test_cmd_list_chats_with_files(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    _write_chat(d, "ch_alpha_beta.json", [])
    _write_chat(d, "ch_second.json", [])
    msg = FakeMessage()
    await ch.cmd_list_chats(msg)
    body = msg.answers[0][0]
    assert "Выберите чат" in body
    texts = [b.text for row in msg.answers[0][2].inline_keyboard for b in row]
    assert any("alpha beta" in t for t in texts)
    assert any(t == "🗑️" for t in texts)


# ---------- cb_select_chat ----------


@pytest.mark.asyncio
async def test_cb_select_chat_stale_session(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(data="sel:unknown")
    await ch.cb_select_chat(cb)
    assert cb.answered == [("❌ Сессия истекла. Откройте список чатов заново.", True)]


@pytest.mark.asyncio
async def test_cb_select_chat_success_with_preview(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch._chat_callback_cache["abcd"] = "ch_1.json"
    _write_chat(
        d, "ch_1.json",
        [{"role": "user", "content": "привет"}, {"role": "assistant", "content": "привет" * 30}],
        summary="короткое",
    )
    cb = FakeCb(data="sel:abcd")
    await ch.cb_select_chat(cb)
    assert ch.user_sessions[4242] == "ch_1.json"
    body = cb.message.edits[0][0]
    assert "Активен" in body
    assert "Последние сообщения" in body
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cb_select_chat_empty_chat(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch._chat_callback_cache["abcd"] = "ch_1.json"
    _write_chat(d, "ch_1.json", [])
    cb = FakeCb(data="sel:abcd")
    await ch.cb_select_chat(cb)
    assert "Чат пуст" in cb.message.edits[0][0]


@pytest.mark.asyncio
async def test_cb_select_chat_expand_button(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch._chat_callback_cache["abcd"] = "ch_1.json"
    _write_chat(
        d, "ch_1.json",
        [{"role": "user", "content": "m" + str(i)} for i in range(8)],
        summary="x" * 600,
    )
    cb = FakeCb(data="sel:abcd")
    await ch.cb_select_chat(cb)
    texts = [b.text for row in cb.message.edits[0][2].inline_keyboard for b in row]
    assert "📖 Развернуть полностью" in texts


# ---------- cb_delete_chat ----------


@pytest.mark.asyncio
async def test_cb_delete_chat_stale_session(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(data="del:unknown")
    await ch.cb_delete_chat(cb)
    assert cb.answered == [("❌ Сессия истекла.", True)]


@pytest.mark.asyncio
async def test_cb_delete_chat_last_chat(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch._chat_callback_cache["abcd"] = "ch_1.json"
    p = _write_chat(d, "ch_1.json", [])
    ch.user_sessions[4242] = "ch_1.json"
    cb = FakeCb(data="del:abcd")
    await ch.cb_delete_chat(cb)
    assert not p.exists()
    assert 4242 not in ch.user_sessions
    assert "Чатов больше нет" in cb.message.edits[0][0]
    assert cb.answered == [("🗑️ Удален: ch_1.json", True)]


@pytest.mark.asyncio
async def test_cb_delete_chat_with_remaining(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch._chat_callback_cache["abcd"] = "ch_1.json"
    _write_chat(d, "ch_1.json", [])
    _write_chat(d, "ch_2.json", [])
    cb = FakeCb(data="del:abcd")
    await ch.cb_delete_chat(cb)
    assert "Выберите чат" in cb.message.edits[-1][0]


@pytest.mark.asyncio
async def test_cb_delete_chat_file_missing(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch._chat_callback_cache["abcd"] = "ch_1.json"
    _write_chat(d, "ch_2.json", [])
    cb = FakeCb(data="del:abcd")
    await ch.cb_delete_chat(cb)
    assert "Выберите чат" in cb.message.edits[-1][0]
    assert cb.answered == [("🗑️ Удален: ch_1.json", True)]


@pytest.mark.asyncio
async def test_cb_delete_chat_edit_fails(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch._chat_callback_cache["abcd"] = "ch_1.json"
    _write_chat(d, "ch_1.json", [])
    _write_chat(d, "ch_2.json", [])

    class FailMsg(FakeMessage):
        async def edit_text(self, text, parse_mode=None, reply_markup=None):
            raise RuntimeError("edit fail")

    cb = FakeCb(data="del:abcd", message=FailMsg())
    await ch.cb_delete_chat(cb)
    assert cb.answered == [("🗑️ Удален: ch_1.json", True)]


# ---------- generate_fresh_summary ----------


@pytest.mark.asyncio
async def test_generate_fresh_summary_empty(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    assert await ch.generate_fresh_summary([]) == "Чат пуст."


@pytest.mark.asyncio
async def test_generate_fresh_summary_success(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(ch, "get_current_ai", lambda: ("ollama", "llama3"))
    calls = {}

    async def fake_ai(engine, model, messages, context=""):
        calls["context"] = context
        return "короткое саммари диалога"

    monkeypatch.setattr(ch, "get_ai_response_async", fake_ai)
    msgs = [{"role": "user", "content": f"m{i}"} for i in range(25)]
    res = await ch.generate_fresh_summary(msgs, "старое саммари")
    assert res == "короткое саммари диалога"
    assert calls["context"] == ""


@pytest.mark.asyncio
async def test_generate_fresh_summary_truncated(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(ch, "get_current_ai", lambda: ("ollama", "llama3"))
    monkeypatch.setattr(ch, "get_ai_response_async", _async_result("сл " * 60))
    res = await ch.generate_fresh_summary([{"role": "user", "content": "x"}])
    assert res.endswith("...")
    assert len(res.split()) == 50


@pytest.mark.asyncio
async def test_generate_fresh_summary_error(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(ch, "get_current_ai", lambda: ("ollama", "llama3"))

    async def boom(*a, **kw):
        raise RuntimeError("ai down")

    monkeypatch.setattr(ch, "get_ai_response_async", boom)
    res = await ch.generate_fresh_summary([{"role": "user", "content": "x"}])
    assert res == "Не удалось сгенерировать саммари."


# ---------- update_summary_if_needed ----------


@pytest.mark.asyncio
async def test_update_summary_if_needed_skip_under_5(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    p = _write_chat(d, "ch_1.json", [{"role": "user", "content": "x"}])
    assert await ch.update_summary_if_needed(
        4242, str(p), [{"role": "user", "content": "x"}],
    ) is None
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["summary"] == ""


@pytest.mark.asyncio
async def test_update_summary_if_needed_success(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    p = _write_chat(d, "ch_1.json", [])
    monkeypatch.setattr(ch, "get_current_ai", lambda: ("ollama", "llama3"))
    monkeypatch.setattr(ch, "get_ai_response_async", _async_result("свежее саммари"))
    msgs = [{"role": "user", "content": f"m{i}"} for i in range(5)]
    res = await ch.update_summary_if_needed(4242, str(p), msgs)
    assert res == "свежее саммари"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["summary"] == "свежее саммари"
    assert (d / "ch_1_summary.txt").read_text(encoding="utf-8") == "свежее саммари"


@pytest.mark.asyncio
async def test_update_summary_if_needed_truncated(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    p = _write_chat(d, "ch_1.json", [])
    monkeypatch.setattr(ch, "get_current_ai", lambda: ("ollama", "llama3"))
    monkeypatch.setattr(ch, "get_ai_response_async", _async_result("слово " * 50))
    msgs = [{"role": "user", "content": f"m{i}"} for i in range(5)]
    res = await ch.update_summary_if_needed(4242, str(p), msgs)
    assert res.endswith("...")
    assert len(res.split()) == 40


@pytest.mark.asyncio
async def test_update_summary_if_needed_error(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    p = _write_chat(d, "ch_1.json", [])
    monkeypatch.setattr(ch, "get_current_ai", lambda: ("ollama", "llama3"))

    async def boom(*a, **kw):
        raise RuntimeError("ai down")

    monkeypatch.setattr(ch, "get_ai_response_async", boom)
    msgs = [{"role": "user", "content": f"m{i}"} for i in range(5)]
    assert await ch.update_summary_if_needed(4242, str(p), msgs) is None


# ---------- cmd_context ----------


@pytest.mark.asyncio
async def test_cmd_context_no_session(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage()
    await ch.cmd_context(msg)
    assert msg.answers[0][0] == "⚠️ Нет активного чата."


@pytest.mark.asyncio
async def test_cmd_context_existing_summary(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch.user_sessions[4242] = "ch_1.json"
    _write_chat(d, "ch_1.json", [], summary="x" * 30)
    cached = []
    monkeypatch.setattr(
        ch, "cache_ai_response",
        lambda cid, mid, text: cached.append((cid, mid, text)),
    )
    msg = FakeMessage()
    await ch.cmd_context(msg)
    assert "Контекст чата" in msg.answers[0][0]
    assert cached[0][2].startswith("xxx")


@pytest.mark.asyncio
async def test_cmd_context_generates_new(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch.user_sessions[4242] = "ch_1.json"
    p = _write_chat(d, "ch_1.json", [{"role": "user", "content": "hi"}])
    monkeypatch.setattr(ch, "get_current_ai", lambda: ("ollama", "llama3"))
    monkeypatch.setattr(ch, "get_ai_response_async", _async_result("новое саммари"))
    cached = []
    monkeypatch.setattr(
        ch, "cache_ai_response",
        lambda cid, mid, text: cached.append((cid, mid, text)),
    )
    msg = FakeMessage()
    await ch.cmd_context(msg)
    assert msg.deleted is True
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["summary"] == "новое саммари"
    assert cached[0][2] == "новое саммари"


@pytest.mark.asyncio
async def test_cmd_context_long_summary_expand_button(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch.user_sessions[4242] = "ch_1.json"
    _write_chat(d, "ch_1.json", [], summary="д" * 600)
    msg = FakeMessage()
    await ch.cmd_context(msg)
    texts = [b.text for row in msg.answers[0][2].inline_keyboard for b in row]
    assert "📖 Развернуть полностью" in texts


# ---------- cb_show_summary ----------


@pytest.mark.asyncio
async def test_cb_show_summary_stale(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(data="show_summary:unknown")
    await ch.cb_show_summary(cb)
    assert cb.answered == [("❌ Сессия истекла.", True)]


@pytest.mark.asyncio
async def test_cb_show_summary_from_file(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch._chat_callback_cache["abcd"] = "ch_1.json"
    (d / "ch_1_summary.txt").write_text("саммари из файла", encoding="utf-8")
    monkeypatch.setattr(
        ch, "split_message",
        lambda t, limit=4000: ["часть-1", "часть-2"],
    )
    cached = []
    monkeypatch.setattr(
        ch, "cache_ai_response",
        lambda cid, mid, text: cached.append((cid, mid, text)),
    )
    cb = FakeCb(data="show_summary:abcd")
    await ch.cb_show_summary(cb)
    bodies = [a[0] for a in cb.message.answers]
    assert "часть-1" in bodies
    assert "часть-2" in bodies
    assert cached[0][2] == "саммари из файла"
    assert cb.message.reply_markup is not None
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cb_show_summary_from_chat_fallback(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch._chat_callback_cache["abcd"] = "ch_1.json"
    _write_chat(d, "ch_1.json", [], summary="саммари из чата")
    cb = FakeCb(data="show_summary:abcd")
    await ch.cb_show_summary(cb)
    assert "саммари из чата" in cb.message.answers[0][0]


@pytest.mark.asyncio
async def test_cb_show_summary_empty(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch._chat_callback_cache["abcd"] = "ch_1.json"
    (d / "ch_1_summary.txt").write_text("   ", encoding="utf-8")
    cb = FakeCb(data="show_summary:abcd")
    await ch.cb_show_summary(cb)
    assert cb.answered == [("Саммари пусто", True)]


@pytest.mark.asyncio
async def test_cb_show_summary_send_fails(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch._chat_callback_cache["abcd"] = "ch_1.json"
    (d / "ch_1_summary.txt").write_text("текст", encoding="utf-8")
    monkeypatch.setattr(
        ch, "split_message",
        lambda t, limit=4000: ["а", "б"],
    )

    class FailMsg(FakeMessage):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.answer_calls = 0

        async def answer(self, text, parse_mode=None, reply_markup=None):
            self.answer_calls += 1
            if self.answer_calls == 1:
                raise RuntimeError("send fail")
            self.answers.append((text, parse_mode, reply_markup))
            return self

    cb = FakeCb(data="show_summary:abcd", message=FailMsg())
    await ch.cb_show_summary(cb)
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cb_show_summary_all_send_fail(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch._chat_callback_cache["abcd"] = "ch_1.json"
    (d / "ch_1_summary.txt").write_text("текст", encoding="utf-8")

    class FailMsg(FakeMessage):
        async def answer(self, text, parse_mode=None, reply_markup=None):
            raise RuntimeError("send fail")

    cb = FakeCb(data="show_summary:abcd", message=FailMsg())
    await ch.cb_show_summary(cb)
    assert cb.answered == [(None, None)]


# ---------- cb_show_full_chat ----------


@pytest.mark.asyncio
async def test_cb_show_full_chat_stale(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(data="show_full:unknown")
    await ch.cb_show_full_chat(cb)
    assert cb.answered == [("❌ Сессия истекла.", True)]


@pytest.mark.asyncio
async def test_cb_show_full_chat_empty(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch._chat_callback_cache["abcd"] = "ch_1.json"
    _write_chat(d, "ch_1.json", [])
    cb = FakeCb(data="show_full:abcd")
    await ch.cb_show_full_chat(cb)
    assert cb.answered == [("Чат пуст", True)]


@pytest.mark.asyncio
async def test_cb_show_full_chat_success(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch._chat_callback_cache["abcd"] = "ch_1.json"
    _write_chat(d, "ch_1.json", [
        {"role": "user", "content": "вопрос"},
        {"role": "assistant", "content": "ответ"},
    ])
    monkeypatch.setattr(
        ch, "split_message",
        lambda t, limit=4000: ["полный текст"],
    )
    sent = []

    async def fake_send_text_only(message, text):
        sent.append((message, text))

    monkeypatch.setattr("services.sender.send_text_only", fake_send_text_only)
    cb = FakeCb(data="show_full:abcd")
    await ch.cb_show_full_chat(cb)
    assert sent[0][1] == "полный текст"
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cb_show_full_chat_multi_part(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch._chat_callback_cache["abcd"] = "ch_1.json"
    _write_chat(d, "ch_1.json", [
        {"role": "user", "content": "вопрос"},
        {"role": "assistant", "content": "ответ"},
    ])
    monkeypatch.setattr(
        ch, "split_message",
        lambda t, limit=4000: ["часть-1", "часть-2"],
    )
    sent = []

    async def fake_send_text_only(message, text):
        sent.append((message, text))

    monkeypatch.setattr("services.sender.send_text_only", fake_send_text_only)
    cb = FakeCb(data="show_full:abcd")
    await ch.cb_show_full_chat(cb)
    bodies = [a[0] for a in cb.message.answers]
    assert "часть-1" in bodies
    assert sent[0][1] == "часть-2"
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cb_show_full_chat_send_fails(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch._chat_callback_cache["abcd"] = "ch_1.json"
    _write_chat(d, "ch_1.json", [
        {"role": "user", "content": "вопрос"},
        {"role": "assistant", "content": "ответ"},
    ])
    monkeypatch.setattr(
        ch, "split_message", lambda t, limit=4000: ["полный текст"],
    )

    async def boom(message, text):
        raise RuntimeError("send fail")

    monkeypatch.setattr("services.sender.send_text_only", boom)
    cb = FakeCb(data="show_full:abcd")
    await ch.cb_show_full_chat(cb)
    assert cb.answered == [(None, None)]


# ---------- cb_refresh_summary ----------


@pytest.mark.asyncio
async def test_cb_refresh_summary_stale(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(data="refresh_summary:unknown")
    await ch.cb_refresh_summary(cb)
    assert cb.answered == [("❌ Сессия истекла.", True)]


@pytest.mark.asyncio
async def test_cb_refresh_summary_empty(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch._chat_callback_cache["abcd"] = "ch_1.json"
    _write_chat(d, "ch_1.json", [])
    cb = FakeCb(data="refresh_summary:abcd")
    await ch.cb_refresh_summary(cb)
    assert cb.answered == [("Чат пуст", True)]


@pytest.mark.asyncio
async def test_cb_refresh_summary_success(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch._chat_callback_cache["abcd"] = "ch_1.json"
    p = _write_chat(d, "ch_1.json", [{"role": "user", "content": "hi"}])
    monkeypatch.setattr(ch, "get_current_ai", lambda: ("ollama", "llama3"))
    monkeypatch.setattr(ch, "get_ai_response_async", _async_result("обновлённое саммари"))
    cached = []
    monkeypatch.setattr(
        ch, "cache_ai_response",
        lambda cid, mid, text: cached.append((cid, mid, text)),
    )
    cb = FakeCb(data="refresh_summary:abcd")
    await ch.cb_refresh_summary(cb)
    assert cb.answered == [("🔄 Генерирую новое саммари...", True)]
    assert "Обновленное саммари" in cb.message.edits[0][0]
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["summary"] == "обновлённое саммари"
    assert cached[0][2] == "обновлённое саммари"


@pytest.mark.asyncio
async def test_cb_refresh_summary_long_expand(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch._chat_callback_cache["abcd"] = "ch_1.json"
    _write_chat(d, "ch_1.json", [{"role": "user", "content": "hi"}])
    monkeypatch.setattr(ch, "get_current_ai", lambda: ("ollama", "llama3"))
    monkeypatch.setattr(ch, "get_ai_response_async", _async_result("д" * 600))
    cb = FakeCb(data="refresh_summary:abcd")
    await ch.cb_refresh_summary(cb)
    texts = [b.text for row in cb.message.edits[0][2].inline_keyboard for b in row]
    assert "📖 Развернуть полностью" in texts


# ---------- cmd_sync_palace / get_ai_context / cmd_history / cmd_export ----------


@pytest.mark.asyncio
async def test_cmd_sync_palace_no_session(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage()
    await ch.cmd_sync_palace(msg)
    assert msg.answers[0][0] == "⚠️ Нет активного чата для синхронизации."


@pytest.mark.asyncio
async def test_cmd_sync_palace_empty_export(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch.user_sessions[4242] = "ch_1.json"
    _write_chat(d, "ch_1.json", [])
    monkeypatch.setattr(chat_sync, "export_chat_verbatim", lambda p, f: None)
    msg = FakeMessage()
    await ch.cmd_sync_palace(msg)
    assert msg.answers[0][0] == "ℹ️ Чат пуст или не найден."


@pytest.mark.asyncio
async def test_cmd_sync_palace_success(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch.user_sessions[4242] = "ch_1.json"
    _write_chat(d, "ch_1.json", [{"role": "user", "content": "hi"}])
    monkeypatch.setattr(chat_sync, "CHATS_DIR", str(d))
    monkeypatch.setattr(chat_sync, "export_chat_verbatim", lambda p, f: {"text": "экспорт"})
    monkeypatch.setattr(chat_sync, "sync_to_palace", _async_result("✅ Синхронизировано"))
    msg = FakeMessage()
    await ch.cmd_sync_palace(msg)
    assert msg.answers[0][0] == "🔄 Синхронизирую с MemPalace (verbatim)..."
    assert msg.edits[-1][0] == "✅ Синхронизировано"


@pytest.mark.asyncio
async def test_cmd_sync_palace_error_is_shown(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch.user_sessions[4242] = "ch_1.json"
    _write_chat(d, "ch_1.json", [{"role": "user", "content": "hi"}])
    monkeypatch.setattr(chat_sync, "export_chat_verbatim", lambda p, f: "exported")

    async def boom(exported):
        raise RuntimeError("palace down")

    monkeypatch.setattr(chat_sync, "sync_to_palace", boom)
    msg = FakeMessage()
    await ch.cmd_sync_palace(msg)
    assert msg.answers[0][0] == "🔄 Синхронизирую с MemPalace (verbatim)..."
    assert msg.edits[-1][0] == "❌ Ошибка синхронизации: palace down"


@pytest.mark.asyncio
async def test_get_ai_context_no_session(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    assert await ch.get_ai_context(4242) == ("", [])


@pytest.mark.asyncio
async def test_get_ai_context_with_chat(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch.user_sessions[4242] = "ch_1.json"
    msgs = [{"role": "user", "content": f"m{i}"} for i in range(8)]
    _write_chat(d, "ch_1.json", msgs, summary="саммари")
    summary, recent = await ch.get_ai_context(4242)
    assert summary == "саммари"
    assert len(recent) == 6
    assert recent[0]["content"] == "m2"


@pytest.mark.asyncio
async def test_cmd_history_no_session(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage()
    await ch.cmd_history(msg)
    assert msg.answers[0][0] == "⚠️ Нет активного чата."


@pytest.mark.asyncio
async def test_cmd_history_empty(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch.user_sessions[4242] = "ch_1.json"
    _write_chat(d, "ch_1.json", [])
    msg = FakeMessage()
    await ch.cmd_history(msg)
    assert msg.answers[0][0] == "📁 Чат пуст."


@pytest.mark.asyncio
async def test_cmd_history_success(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch.user_sessions[4242] = "ch_1.json"
    msgs = [{"role": "user", "content": f"m{i}"} for i in range(12)]
    _write_chat(d, "ch_1.json", msgs)
    msg = FakeMessage()
    await ch.cmd_history(msg)
    body = msg.answers[0][0]
    assert "История чата" in body
    assert "m2" in body
    assert "m11" in body
    texts = [b.text for row in msg.answers[0][2].inline_keyboard for b in row]
    assert "📖 Показать полностью" in texts


@pytest.mark.asyncio
async def test_cmd_export_no_session(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage()
    await ch.cmd_export(msg)
    assert msg.answers[0][0] == "⚠️ Нет активного чата для экспорта."


@pytest.mark.asyncio
async def test_cmd_export_no_md(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch.user_sessions[4242] = "ch_1.json"
    _write_chat(d, "ch_1.json", [])
    msg = FakeMessage()
    await ch.cmd_export(msg)
    assert msg.answers[0][0] == "❌ Ошибка экспорта: файл не создан."


@pytest.mark.asyncio
async def test_cmd_export_success(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch.user_sessions[4242] = "ch_1.json"
    _write_chat(d, "ch_1.json", [{"role": "user", "content": "hi"}])
    msg = FakeMessage()
    await ch.cmd_export(msg)
    assert msg.sent_document is not None
    assert "Чат экспортирован в Markdown" in msg.sent_document[1]


@pytest.mark.asyncio
async def test_cmd_export_error(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    ch.user_sessions[4242] = "ch_1.json"
    _write_chat(d, "ch_1.json", [{"role": "user", "content": "hi"}])

    def boom(path):
        raise OSError("disk fail")

    monkeypatch.setattr(ch, "export_chat_to_md", boom)
    msg = FakeMessage()
    await ch.cmd_export(msg)
    assert "Ошибка экспорта" in msg.answers[-1][0]


def _async_result(value):
    async def _inner(*a, **kw):
        return value

    return _inner
