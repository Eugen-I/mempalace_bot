"""Unit tests for handlers/messages.py."""

import asyncio
import json
import os
from types import SimpleNamespace

import pytest

import config
import handlers.messages as messages
from services.bot_setup import (
    pending_web_search as _pending_web_search,
    pending_wing_search as _pending_wing_search,
    sync_counter as _sync_counter,
    sync_in_progress as _sync_in_progress,
    yt_audio_cache as _yt_audio_cache,
    yt_quality_url as _yt_quality_url,
    yt_waiting_url as _yt_waiting_url,
)
from handlers.chat import user_sessions, waiting_for_name
from handlers.palace.shared import _user_context
from services.reflection import REFLECTION_NS


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeStatus:
    def __init__(self, owner, message_id):
        self.owner = owner
        self.message_id = message_id

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        if getattr(self.owner, "fail_status_edits", False):
            raise Exception("edit blocked")
        self.owner.edits.append((text, parse_mode, reply_markup))

    async def delete(self):
        self.owner.deleted.append(self.message_id)


class FakeMessage:
    def __init__(self, uid=4242, text="привет", chat_id=100, fail_status_edits=False):
        self.text = text
        self.from_user = FakeUser(uid)
        self.chat = SimpleNamespace(id=chat_id)
        self.fail_status_edits = fail_status_edits
        self.answers = []
        self.edits = []
        self.deleted = []
        self.audios = []

    async def answer(self, text, parse_mode=None, reply_markup=None):
        inner = FakeStatus(self, len(self.answers) + 1)
        inner.text = text
        inner.reply_markup = reply_markup
        self.answers.append((text, parse_mode, reply_markup))
        return inner

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append((text, parse_mode, reply_markup))
        return self

    async def answer_audio(self, audio, caption=None):
        self.audios.append((audio, caption))
        return self

    async def delete(self):
        self.deleted.append(True)


class FakeMCPSeq:
    def __init__(self, results):
        self.results = list(results)

    async def call_tool(self, name, args=None):
        result = self.results.pop(0)
        if callable(result):
            result = result()
        if isinstance(result, Exception):
            raise result
        return result


class FakeDeg:
    def __init__(self, palace=False, memory=False):
        self._palace = palace
        self._memory = memory

    def should_use_palace(self):
        return self._palace

    def should_use_memory(self):
        return self._memory


class FakeCache:
    def __init__(self, cached=None):
        self.cached = cached
        self.sets = []

    def get(self, query):
        return self.cached

    def set(self, query, answer):
        self.sets.append((query, answer))


class FakeBot:
    def __init__(self):
        self.deleted = []

    async def delete_message(self, chat_id, message_id):
        self.deleted.append((chat_id, message_id))


def _async(v):
    async def f(*a, **k):
        return v
    return f


async def _async_false(*a, **k):
    return False


async def _async_none(*a, **k):
    return None


def _agen(chunks):
    async def g():
        for c in chunks:
            yield c
    return g()


def _stream_factory(chunks):
    def f(*a, **k):
        return _agen(chunks)
    return f


def _enable(monkeypatch, tmp_path=None):
    monkeypatch.setattr(config, "ALLOWED_IDS", {4242})
    monkeypatch.setattr(config, "ADMIN_ID", 4242)
    monkeypatch.setattr(messages, "process_mcp_text_input", _async_false)
    monkeypatch.setattr(messages, "handle_reminder_text", _async_false)
    monkeypatch.setattr(messages, "suggest_tunnel_hint", _async_none)
    monkeypatch.setattr(messages, "get_current_ai", lambda: ("test-engine", "test-model"))
    monkeypatch.setattr(messages, "classify_wing", lambda q: None)
    monkeypatch.setattr(messages, "check_capability", lambda m, c: False)
    monkeypatch.setattr(messages, "is_coding_context", lambda q, msgs: False)
    monkeypatch.setattr(messages, "get_smart_prompt", lambda **kw: "SYSTEM-PROMPT")
    monkeypatch.setattr(messages, "get_voice_settings", lambda uid: {"mode": "text"})
    monkeypatch.setattr(messages, "save_chat", lambda *a, **k: None)
    monkeypatch.setattr(messages, "get_cache", lambda: FakeCache())
    monkeypatch.setattr(messages, "schedule_linking", lambda *a, **k: None)
    monkeypatch.setattr(messages, "extract_and_store_facts", _async_none)
    monkeypatch.setattr(messages, "cache_ai_response", lambda *a, **k: None)
    monkeypatch.setattr(messages, "auto_sync_chat", _async_none)
    monkeypatch.setattr(messages, "search_with_kg", _async(""))
    monkeypatch.setattr(messages, "get_memory_context", lambda q, uid: "memory-ctx")
    monkeypatch.setattr(messages, "report_failure", lambda *a: None)
    monkeypatch.setattr(messages, "report_success", lambda *a: None)
    monkeypatch.setattr(messages, "get_degradation_manager", lambda: FakeDeg())
    monkeypatch.setattr(messages, "load_chat", lambda path: {
        "messages": [], "summary": "", "summaries": [],
    })
    monkeypatch.setattr(messages, "stream_ai_response_async", _stream_factory(["ответ"]))

    async def fake_send(msg, answer, mode):
        return SimpleNamespace(message_id=1)

    monkeypatch.setattr(messages, "send_response_with_mode", fake_send)
    monkeypatch.setattr(messages, "_get_mcp", lambda: FakeMCPSeq([]))
    monkeypatch.setattr(messages, "bot", FakeBot())
    monkeypatch.setattr(
        "services.agent_settings.get_agent_enabled", lambda uid: False,
    )
    if tmp_path is not None:
        monkeypatch.setattr(messages, "CHATS_DIR", str(tmp_path))
        monkeypatch.setattr(messages, "NOTES_DIR", str(tmp_path))
        monkeypatch.setattr(messages, "INSIGHTS_DIR", str(tmp_path))
        monkeypatch.setattr(messages, "RESEARCH_DIR", str(tmp_path))
        monkeypatch.setattr(messages, "PHOTOS_DIR", str(tmp_path))


@pytest.fixture(autouse=True)
def _clean_state():
    for uid in list(_yt_waiting_url):
        del _yt_waiting_url[uid]
    for uid in list(_yt_quality_url):
        del _yt_quality_url[uid]
    for sid in list(_yt_audio_cache):
        del _yt_audio_cache[sid]
    for uid in list(_pending_wing_search):
        del _pending_wing_search[uid]
    for uid in list(_pending_web_search):
        del _pending_web_search[uid]
    for uid in list(user_sessions):
        del user_sessions[uid]
    for uid in list(waiting_for_name):
        del waiting_for_name[uid]
    for uid in list(_sync_counter):
        del _sync_counter[uid]
    for uid in list(_sync_in_progress):
        del _sync_in_progress[uid]
    from handlers.palace.shared import fsm

    fsm.clear(4242)
    fsm.clear(999)
    messages._last_user_query.clear()
    yield


# ---------- _on_ai_complete ----------


def test_on_ai_complete_with_data(monkeypatch):
    captured = {}

    async def fake_extract(uid, clean_q, answer):
        captured["uid"] = uid
        captured["q"] = clean_q
        captured["a"] = answer

    monkeypatch.setattr(messages, "extract_and_store_facts", fake_extract)
    asyncio.run(messages._on_ai_complete(answer="ans", clean_q="q", uid=7))
    assert captured == {"uid": 7, "q": "q", "a": "ans"}


def test_on_ai_complete_missing_data(monkeypatch):
    captured = []

    async def fake_extract(uid, clean_q, answer):
        captured.append((uid, clean_q, answer))

    monkeypatch.setattr(messages, "extract_and_store_facts", fake_extract)
    asyncio.run(messages._on_ai_complete(answer="", clean_q="q", uid=7))
    asyncio.run(messages._on_ai_complete(answer="ans", clean_q="", uid=7))
    assert captured == []


# ---------- _on_ai_sent ----------


def test_on_ai_sent_error_answer(monkeypatch):
    cache_called = []
    monkeypatch.setattr(messages, "cache_ai_response", lambda *a: cache_called.append(a))
    asyncio.run(messages._on_ai_sent(
        answer="❌ ошибка", clean_q="q", uid=7, sent_msg=SimpleNamespace(message_id=1),
    ))
    assert cache_called == []
    assert 7 not in messages._last_user_query


def test_on_ai_sent_full_flow(monkeypatch):
    cache_called = []
    monkeypatch.setattr(messages, "cache_ai_response", lambda *a: cache_called.append(a))
    tunnel_called = []

    async def fake_tunnel(*a):
        tunnel_called.append(a)

    monkeypatch.setattr(messages, "suggest_tunnel_hint", fake_tunnel)
    sync_called = []

    async def fake_sync(uid, fname, fpath):
        sync_called.append((uid, fname, fpath))

    monkeypatch.setattr(messages, "auto_sync_chat", fake_sync)
    _sync_counter[9] = 4
    asyncio.run(messages._on_ai_sent(
        answer="нормальный ответ", clean_q="вопрос", uid=9, chat_id=100,
        sent_msg=SimpleNamespace(message_id=42), message="msg", fname="f", fpath="p",
    ))
    assert cache_called == [(100, 42, "нормальный ответ")]
    assert messages._last_user_query[100] == "вопрос"
    assert _sync_counter[9] == 5
    assert sync_called == [(9, "f", "p")]
    assert _sync_in_progress.get(9) is False
    assert tunnel_called == [("msg", "вопрос")]


def test_on_ai_sent_no_sent_msg(monkeypatch):
    cache_called = []
    monkeypatch.setattr(messages, "cache_ai_response", lambda *a: cache_called.append(a))
    asyncio.run(messages._on_ai_sent(
        answer="ответ", clean_q="", uid=7, sent_msg=None, chat_id=100,
    ))
    assert cache_called == []


# ---------- _auto_sync_wrapper ----------


def test_auto_sync_wrapper_success(monkeypatch):
    called = []
    monkeypatch.setattr(messages, "auto_sync_chat", _async(called.append(1) or None))
    _sync_in_progress[5] = True
    asyncio.run(messages._auto_sync_wrapper(5, "f", "p"))
    assert called == [1]
    assert _sync_in_progress.get(5) is False


def test_auto_sync_wrapper_exception(monkeypatch):
    async def boom(uid, fname, fpath):
        raise RuntimeError("sync fail")

    monkeypatch.setattr(messages, "auto_sync_chat", boom)
    _sync_in_progress[6] = True
    with pytest.raises(RuntimeError):
        asyncio.run(messages._auto_sync_wrapper(6, "f", "p"))
    assert _sync_in_progress.get(6) is False


# ---------- get_ai_response_sync_wrapper ----------


def test_get_ai_response_sync_wrapper(monkeypatch):
    captured = {}

    def fake_sync(engine, model, msgs, context="", user_query="", has_images=False, **kw):
        captured["engine"] = engine
        captured["model"] = model
        captured["msgs"] = msgs
        captured["kw"] = kw
        return "sum"

    monkeypatch.setattr(messages, "_sync_ai_call", fake_sync)
    result = messages.get_ai_response_sync_wrapper(
        "e", "m", [{"role": "user", "content": "x"}], extra=1,
    )
    assert result == "sum"
    assert captured["engine"] == "e"
    assert captured["model"] == "m"
    assert captured["kw"] == {"extra": 1}


# ---------- non-text message ----------


def test_process_user_message_no_text(monkeypatch):
    _enable(monkeypatch)
    msg = FakeMessage(text=None)
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert msg.answers == []


# ---------- 💭 Рефлексия после штурма (0ccb) ----------


def test_process_user_message_reflection_answer(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    from services.kv_store import KVStore

    kv = KVStore(db_path=str(tmp_path / "reflection.sqlite"))
    monkeypatch.setattr("services.kv_store.get_kv_store", lambda: kv)
    from handlers import brainstorm as h

    h._reflection_waiting[4242] = {"theme": "Сны", "ideas_count": 3}
    msg = FakeMessage(text="Самая сильная — идея про полёт")
    asyncio.run(messages.process_user_message(msg))
    assert any("рефлексия записана" in a[0].lower() for a in msg.answers)
    assert 4242 not in h._reflection_waiting
    keys = kv.keys(namespace=REFLECTION_NS)
    assert len(keys) == 1
    saved = kv.get(keys[0], namespace=REFLECTION_NS)
    assert saved["theme"] == "Сны"
    assert "полёт" in saved["answer"]


def test_process_user_message_reflection_empty_answer(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    from services.kv_store import KVStore

    kv = KVStore(db_path=str(tmp_path / "reflection.sqlite"))
    monkeypatch.setattr("services.kv_store.get_kv_store", lambda: kv)
    from handlers import brainstorm as h

    h._reflection_waiting[4242] = {"theme": "Сны", "ideas_count": 1}
    msg = FakeMessage(text="   ")
    asyncio.run(messages.process_user_message(msg))
    assert any("не записана" in a[0] for a in msg.answers)
    assert kv.keys(namespace=REFLECTION_NS) == []
    assert 4242 not in h._reflection_waiting


# ---------- 🤖 Агентный режим (agent_enabled) ----------


def test_agent_mode_disabled_uses_normal_ai(monkeypatch):
    _enable(monkeypatch)
    calls = []
    monkeypatch.setattr(
        "handlers.agent._run_agent_reply",
        lambda *a, **k: calls.append(a),
    )
    msg = FakeMessage(text="обычный вопрос")
    asyncio.run(messages.process_user_message(msg))
    assert calls == []
    assert any("думает" in a[0] for a in msg.answers)


def test_agent_mode_enabled_routes_to_agent(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(
        "services.agent_settings.get_agent_enabled", lambda uid: True,
    )
    calls = []

    async def fake_run(uid, status, prompt, question, ctx=None, include_write=False):
        calls.append({
            "uid": uid, "prompt": prompt, "question": question, "ctx": ctx,
        })

    monkeypatch.setattr("handlers.agent._run_agent_reply", fake_run)
    msg = FakeMessage(text="вопрос агенту")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert calls
    assert calls[0]["uid"] == 4242
    assert calls[0]["question"] == "вопрос агенту"
    assert "Комната" not in calls[0]["prompt"]
    assert any(a[0].startswith("🤖") for a in msg.answers)


def test_agent_mode_skips_commands(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(
        "services.agent_settings.get_agent_enabled", lambda uid: True,
    )
    calls = []
    monkeypatch.setattr(
        "handlers.agent._run_agent_reply",
        lambda *a, **k: calls.append(a),
    )
    msg = FakeMessage(text="/unknowncmd что-то")
    asyncio.run(messages.process_user_message(msg))
    assert calls == []


def test_agent_mode_scoped_by_user_context(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(
        "services.agent_settings.get_agent_enabled", lambda uid: True,
    )
    calls = []

    async def fake_run(uid, status, prompt, question, ctx=None, include_write=False):
        calls.append({"prompt": prompt, "ctx": ctx})

    monkeypatch.setattr("handlers.agent._run_agent_reply", fake_run)
    _user_context[4242] = {"wing": "Философия", "room": "Шопенгауэр"}
    try:
        msg = FakeMessage(text="расскажи про волю")
        asyncio.run(messages.process_user_message(msg))
    finally:
        _user_context.pop(4242, None)
    assert calls
    assert "Философия" in calls[0]["prompt"]
    assert "Шопенгауэр" in calls[0]["prompt"]
    assert calls[0]["ctx"]["wing"] == "Философия"


# ---------- YouTube: video mode ----------


def test_yt_waiting_video_quality(monkeypatch):
    _enable(monkeypatch)
    _yt_waiting_url[4242] = "video"
    msg = FakeMessage(text="https://youtu.be/abc")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is not None
    assert 4242 not in _yt_waiting_url
    assert _yt_quality_url[4242] == "https://youtu.be/abc"
    text, pm, markup = msg.answers[-1]
    assert text == "🎥 Выберите качество:"
    data = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert data == ["yt_q:480", "yt_q:720"]
    del _yt_quality_url[4242]


# ---------- YouTube: audio flow ----------


def _yt_audio_setup(monkeypatch, tmp_path, file_size, compress_to=None, split=None):
    _enable(monkeypatch, tmp_path)
    path = os.path.join(str(tmp_path), "audio.mp3")
    with open(path, "wb") as f:
        f.truncate(file_size)

    async def fake_download(url):
        return path, "Заголовок"

    monkeypatch.setattr(messages, "download_audio", fake_download)
    if compress_to is not None:
        small = os.path.join(str(tmp_path), "small.mp3")
        with open(small, "wb") as f:
            f.truncate(compress_to)

        async def fake_compress(p):
            return small
        monkeypatch.setattr("services.youtube.compress_audio", fake_compress)
    if split is not None:
        monkeypatch.setattr("services.youtube.split_media", _async(split))
    _yt_waiting_url[4242] = "audio"
    return FakeMessage(text="https://youtu.be/abc"), path


def test_yt_audio_success(monkeypatch, tmp_path):
    msg, path = _yt_audio_setup(monkeypatch, tmp_path, 1000)
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert msg.audios[0][0].path == path
    text, pm, markup = msg.answers[-1]
    assert "Транскрибировать" in text
    sid = markup.inline_keyboard[0][0].callback_data.split(":")[1]
    assert sid in _yt_audio_cache
    assert _yt_audio_cache[sid] == {"path": path, "title": "Заголовок"}


def test_yt_audio_empty_file(monkeypatch, tmp_path):
    msg, _ = _yt_audio_setup(monkeypatch, tmp_path, 0)
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert "❌ Аудио пустое" in msg.edits[-1][0]
    assert not os.path.exists(os.path.join(str(tmp_path), "audio.mp3"))


def test_yt_audio_too_big_single_after_compress(monkeypatch, tmp_path):
    msg, _ = _yt_audio_setup(monkeypatch, tmp_path, messages.FILE_LIMIT + 1, compress_to=1000)
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert any("сжимаю" in e[0] for e in msg.edits)
    assert msg.audios[0][1] is None


def test_yt_audio_split_into_parts(monkeypatch, tmp_path):
    parts = [
        os.path.join(str(tmp_path), "p1.mp3"),
        os.path.join(str(tmp_path), "p2.mp3"),
    ]
    for p in parts:
        with open(p, "wb") as f:
            f.truncate(100)
    msg, _ = _yt_audio_setup(
        monkeypatch, tmp_path, messages.FILE_LIMIT + 1,
        compress_to=messages.FILE_LIMIT + 2, split=parts,
    )
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert len(msg.audios) == 2
    assert msg.audios[0][1] == "🎵 Заголовок (часть 1/2)"
    assert msg.deleted[0] == 1
    for p in parts:
        assert not os.path.exists(p)


def test_yt_audio_download_error(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)

    async def boom(url):
        raise RuntimeError("yt-dlp упал")

    monkeypatch.setattr(messages, "download_audio", boom)
    _yt_waiting_url[4242] = "audio"
    msg = FakeMessage(text="https://youtu.be/abc")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    # format_user_error для RuntimeError возвращает "❌ Ошибка выполнения"
    assert "Ошибка выполнения" in msg.edits[-1][0]


# ---------- mcp/reminder/quote/transkript/note early returns ----------


def test_process_mcp_input_handled(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(messages, "process_mcp_text_input", _async(True))
    msg = FakeMessage()
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert msg.answers == []


def test_reminder_handled(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(messages, "handle_reminder_text", _async(True))
    msg = FakeMessage(text="напомни завтра")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None


def test_quote_waiting(monkeypatch):
    _enable(monkeypatch)
    from handlers.personal_note import _quote_waiting

    _quote_waiting[4242] = True
    captured = {}

    async def fake_save(uid, text, answer):
        captured["uid"] = uid
        captured["text"] = text
        return "saved"

    monkeypatch.setattr(messages, "_save_quote_to_palace", fake_save)
    msg = FakeMessage(text="цитата")
    result = asyncio.run(messages.process_user_message(msg))
    assert result == "saved"
    assert captured == {"uid": 4242, "text": "цитата"}
    del _quote_waiting[4242]


def test_tr_ai_waiting(monkeypatch):
    _enable(monkeypatch)
    from handlers.transkript import _tr_ai_waiting

    _tr_ai_waiting[4242] = {"fname": "f.txt"}
    called = []

    async def fake_question(uid, message, fname, text):
        called.append((uid, fname, text))

    monkeypatch.setattr(messages, "handle_tr_ai_question", fake_question)
    msg = FakeMessage(text="вопрос")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert called == [(4242, "f.txt", "вопрос")]
    assert 4242 not in _tr_ai_waiting


def test_waiting_for_note(monkeypatch):
    _enable(monkeypatch)
    from handlers.personal_note import _waiting_for_note

    _waiting_for_note[4242] = True
    captured = {}

    async def fake_process(uid, text, answer):
        captured["uid"] = uid
        captured["text"] = text
        return "processed"

    monkeypatch.setattr(messages, "process_note_input", fake_process)
    msg = FakeMessage(text="заметка")
    result = asyncio.run(messages.process_user_message(msg))
    assert result == "processed"
    assert captured == {"uid": 4242, "text": "заметка"}
    del _waiting_for_note[4242]


# ---------- wing search ----------


def test_wing_search_success(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    _pending_wing_search[4242] = "dreams"
    sources = [
        {"id": "s1", "wing": "dreams", "room": "сон"},
    ]

    async def fake_search(text, limit=5, wing=None):
        return "результат поиска", sources

    monkeypatch.setattr(
        "services.palace_bridge.search_palace_with_sources", fake_search,
    )
    msg = FakeMessage(text="сны")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert 4242 not in _pending_wing_search
    assert "Ищу в MemPalace (крыло: dreams)..." in msg.answers[0][0]
    text, pm, markup = msg.edits[-1]
    assert text == "результат поиска"
    data = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert data == ["p_src:s1", "search:wing"]


def test_wing_search_no_results(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    _pending_wing_search[4242] = None

    async def fake_search(text, limit=5, wing=None):
        return "", []

    monkeypatch.setattr(
        "services.palace_bridge.search_palace_with_sources", fake_search,
    )
    msg = FakeMessage(text="сны")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert "Ничего не найдено." in msg.edits[-1][0]


def test_wing_search_error(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    _pending_wing_search[4242] = "dreams"

    async def boom(text, limit=5, wing=None):
        raise RuntimeError("mcp down")

    monkeypatch.setattr(
        "services.palace_bridge.search_palace_with_sources", boom,
    )
    msg = FakeMessage(text="сны")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    # format_user_error для RuntimeError возвращает "❌ Ошибка выполнения"
    assert "Ошибка выполнения" in msg.edits[-1][0]


# ---------- web search ----------


def test_web_search_ai_summary(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    _pending_web_search[4242] = True
    sent = []

    async def fake_deep(query):
        return {
            "search_id": "w1", "query": "запрос",
            "ai_summary": "саммари текст",
            "sources": [{"text": "src", "url": "http://x"}],
        }

    async def fake_send(message, text):
        sent.append(text)

    monkeypatch.setattr("services.web_search.deep_search_web", fake_deep)
    monkeypatch.setattr("services.sender.send_text_only", fake_send)
    msg = FakeMessage(text="запрос")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert 4242 not in _pending_web_search
    assert sent == ["саммари текст"]
    data = [b.callback_data for row in msg.answers[-1][2].inline_keyboard for b in row]
    assert data == ["ws_sources:w1", "ws_save:w1"]


def test_web_search_fallback_sources(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    _pending_web_search[4242] = True
    sent = []

    async def fake_deep(query):
        return {
            "search_id": "w2", "query": "запрос",
            "ai_summary": "", "sources": [{"text": "текст", "url": "http://u"}],
        }

    async def fake_send(message, text):
        sent.append(text)

    monkeypatch.setattr("services.web_search.deep_search_web", fake_deep)
    monkeypatch.setattr("services.sender.send_text_only", fake_send)
    msg = FakeMessage(text="запрос")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert "🔍 <b>Результаты по: запрос</b>" in sent[0]
    assert "http://u" in sent[0]


def test_web_search_nothing_found(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    _pending_web_search[4242] = True

    async def fake_deep(query):
        return {"search_id": "w3", "query": "запрос", "ai_summary": "", "sources": []}

    monkeypatch.setattr("services.web_search.deep_search_web", fake_deep)
    msg = FakeMessage(text="запрос")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert any("🤷 Ничего не найдено" in a[0] for a in msg.answers)


def test_web_search_non_dict(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    _pending_web_search[4242] = True

    async def fake_deep(query):
        return "строка"

    monkeypatch.setattr("services.web_search.deep_search_web", fake_deep)
    msg = FakeMessage(text="запрос")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert "❌ Ошибка: неожиданный формат ответа поиска" in [a[0] for a in msg.answers]


def test_web_search_error(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    _pending_web_search[4242] = True

    async def boom(query):
        raise RuntimeError("сеть недоступна")

    monkeypatch.setattr("services.web_search.deep_search_web", boom)
    msg = FakeMessage(text="запрос")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    # format_user_error для RuntimeError возвращает "❌ Ошибка выполнения"
    assert "Ошибка выполнения" in msg.edits[-1][0]


# ---------- Mac commands ----------


def test_mac_command_not_admin(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(messages, "ADMIN_ID", 999)
    msg = FakeMessage(text="уснуть")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is not None
    assert msg.answers[-1][0] == "❌ Доступ запрещен."


def test_mac_sleep(monkeypatch):
    _enable(monkeypatch)
    ran = []
    monkeypatch.setattr(messages, "ADMIN_ID", 4242)
    monkeypatch.setattr("subprocess.run", lambda *a, **k: ran.append(a[0]))
    msg = FakeMessage(text="уснуть")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert "osascript" in ran[0]
    assert "✅ Выполнено." in [a[0] for a in msg.answers]


def test_mac_lock_error(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(messages, "ADMIN_ID", 4242)

    def boom(*a, **k):
        raise OSError("нет сессии")

    monkeypatch.setattr("subprocess.run", boom)
    msg = FakeMessage(text="заблокировать")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert "❌ Ошибка выполнения команды." in [a[0] for a in msg.answers]


# ---------- fast note ! ----------


def test_fast_note(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    linked = []

    def fake_link(path, note, prefix="!"):
        linked.append((path, note, prefix))

    monkeypatch.setattr(messages, "schedule_linking", fake_link)
    msg = FakeMessage(text="!моя заметка")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is not None
    files = os.listdir(str(tmp_path))
    assert len(files) == 1
    assert files[0].startswith("nt_")
    with open(os.path.join(str(tmp_path), files[0]), encoding="utf-8") as f:
        assert f.read() == "моя заметка"
    assert linked[0][1] == "моя заметка"
    assert linked[0][2] == "!"
    data = [b.callback_data for row in result.reply_markup.inline_keyboard for b in row]
    assert data == [f"show_links:{files[0]}"]


def test_fast_note_linker_error(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)

    def boom(path, note, prefix="!"):
        raise RuntimeError("linker dead")

    monkeypatch.setattr(messages, "schedule_linking", boom)
    msg = FakeMessage(text="!заметка")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is not None
    assert "💾 Сохранено" in result.text


def test_fast_note_write_error(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    blocker = os.path.join(str(tmp_path), "blocker.txt")
    with open(blocker, "w", encoding="utf-8") as f:
        f.write("x")
    monkeypatch.setattr(messages, "NOTES_DIR", blocker)
    msg = FakeMessage(text="!заметка")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is not None
    assert "❌ Ошибка:" in result.text


# ---------- chat name input ----------


def test_waiting_for_name(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    waiting_for_name[4242] = True
    msg = FakeMessage(text="Мой Чат!")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is not None
    assert waiting_for_name[4242] is False
    assert user_sessions[4242].startswith("ch_Мой_Чат_")
    assert "✅ Чат создан" in result.text


def test_waiting_for_name_empty(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    waiting_for_name[4242] = True
    msg = FakeMessage(text="!!!")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is not None
    assert user_sessions[4242].startswith("ch_auto_")
    assert "✅ Чат создан" in result.text


def test_waiting_for_name_save_error(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    waiting_for_name[4242] = True

    def boom(path, data):
        raise OSError("disk full")

    monkeypatch.setattr(messages, "save_chat", boom)
    msg = FakeMessage(text="Чат")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is not None
    assert "❌ Ошибка создания чата." in result.text


# ---------- auto chat activation ----------


def test_auto_activate_existing_chat(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    old = os.path.join(str(tmp_path), "ch_old.json")
    new = os.path.join(str(tmp_path), "ch_new.json")
    with open(old, "w") as f:
        f.write("{}")
    with open(new, "w") as f:
        f.write("{}")
    os.utime(old, (1000, 1000))
    os.utime(new, (2000, 2000))
    msg = FakeMessage(uid=999, text="привет")
    asyncio.run(messages.process_user_message(msg))
    assert user_sessions[999] == "ch_new.json"
    assert any("🔄 Активирован" in a[0] for a in msg.answers)


def test_auto_create_chat(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage(uid=999, text="привет")
    asyncio.run(messages.process_user_message(msg))
    assert user_sessions[999].startswith("ch_auto_")
    assert any("🆕 Создан чат" in a[0] for a in msg.answers)


# ---------- chat load error ----------


def test_chat_load_error(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    user_sessions[4242] = "ch_test.json"

    def boom(path):
        raise OSError("corrupted")

    monkeypatch.setattr(messages, "load_chat", boom)
    msg = FakeMessage(text="привет")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is not None
    assert "❌ Ошибка загрузки чата." in result.text


# ---------- prefix !! / ??? ----------


def _prefix_setup(monkeypatch, tmp_path, msgs=None):
    _enable(monkeypatch, tmp_path)
    user_sessions[4242] = "ch_test.json"
    data = {
        "messages": msgs or [
            {"role": "user", "content": "источник"},
            {"role": "assistant", "content": "текст ответа"},
        ],
        "summary": "", "summaries": [],
    }
    monkeypatch.setattr(messages, "load_chat", lambda path: data)
    monkeypatch.setattr(messages, "get_ai_response_sync_wrapper", lambda *a, **k: "суммари")
    return data


def test_prefix_insight(monkeypatch, tmp_path):
    _prefix_setup(monkeypatch, tmp_path)
    msg = FakeMessage(text="!! что тут важного")
    asyncio.run(messages.process_user_message(msg))
    files = os.listdir(str(tmp_path))
    assert any(f.startswith("ext_") for f in files)
    with open(os.path.join(str(tmp_path), files[0]), encoding="utf-8") as f:
        content = f.read()
    assert content.startswith("!!\n")
    assert "ИТОГ: суммари" in content
    assert "✅ Сохранено в" in msg.edits[-1][0]


def test_prefix_research(monkeypatch, tmp_path):
    _prefix_setup(monkeypatch, tmp_path)
    msg = FakeMessage(text="??? вопрос для исследования")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    with open(os.path.join(str(tmp_path), os.listdir(str(tmp_path))[0]), encoding="utf-8") as f:
        content = f.read()
    assert content.startswith("???\n")


def test_prefix_no_clean_query(monkeypatch, tmp_path):
    _prefix_setup(monkeypatch, tmp_path)
    msg = FakeMessage(text="!!")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert "✅ Сохранено" in msg.edits[-1][0]
    assert "Ищу в интернете" not in [a[0] for a in msg.answers]


def test_prefix_ai_error(monkeypatch, tmp_path):
    _prefix_setup(monkeypatch, tmp_path)

    def boom(*a, **k):
        raise RuntimeError("ai down")

    monkeypatch.setattr(messages, "get_ai_response_sync_wrapper", boom)
    msg = FakeMessage(text="!! что тут важного")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    # format_user_error для RuntimeError возвращает "❌ Ошибка выполнения"
    assert "Ошибка выполнения" in msg.edits[-1][0]


# ---------- /web ----------


def test_web_command_usage(monkeypatch, tmp_path):
    _prefix_setup(monkeypatch, tmp_path)
    msg = FakeMessage(text="/web")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is not None
    assert "Использование: /web <запрос>" in result.text


def test_web_command_success(monkeypatch, tmp_path):
    _prefix_setup(monkeypatch, tmp_path)
    sent = []

    async def fake_search(query):
        return "результаты"

    async def fake_send(message, text):
        sent.append(text)

    monkeypatch.setattr("services.web_search.search_web", fake_search)
    monkeypatch.setattr("services.sender.send_text_only", fake_send)
    msg = FakeMessage(text="/web как работает python")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert sent == ["результаты"]
    assert msg.deleted == [1]


def test_web_command_error(monkeypatch, tmp_path):
    _prefix_setup(monkeypatch, tmp_path)

    async def boom(query):
        raise RuntimeError("net down")

    monkeypatch.setattr("services.web_search.search_web", boom)
    msg = FakeMessage(text="/web python")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert "❌ Ошибка: net down" in msg.edits[-1][0]


# ---------- helpers for AI core ----------


class FakeTime:
    def __init__(self):
        self.val = 0.0

    def __call__(self):
        self.val += 1.0
        return self.val


def _ai_setup(
    monkeypatch, tmp_path, msgs=None, data_extra=None,
    stream_chunks=("x" * 40, "y" * 40),
):
    _enable(monkeypatch, tmp_path)
    user_sessions[4242] = "ch_test.json"
    data = {
        "messages": msgs or [
            {"role": "user", "content": "первый"},
            {"role": "assistant", "content": "второй"},
        ],
        "summary": "", "summaries": [],
    }
    if data_extra:
        data.update(data_extra)
    monkeypatch.setattr(messages, "load_chat", lambda path: data)
    saves = []
    monkeypatch.setattr(messages, "save_chat", lambda path, d: saves.append((path, d)))
    calls = {}
    bot = FakeBot()
    monkeypatch.setattr(messages, "bot", bot)

    def stream_factory(*a, **k):
        calls["stream_kwargs"] = k
        calls["messages"] = a[2]
        return _agen(list(stream_chunks))

    monkeypatch.setattr(messages, "stream_ai_response_async", stream_factory)
    return data, saves, calls, bot


# ---------- fast note empty note ----------


def test_fast_note_empty_falls_to_ai(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)
    msg = FakeMessage(text="!")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert data["messages"][-1]["role"] == "assistant"


# ---------- main AI flow: happy path ----------


def test_ai_basic_flow(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)
    cache = FakeCache()
    monkeypatch.setattr(messages, "get_cache", lambda: cache)
    monkeypatch.setattr(messages.time, "time", FakeTime())
    msg = FakeMessage(text="привет")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert "⏳ <code>test-model</code> думает..." in msg.answers[0][0]
    assert data["messages"][-2] == {"role": "user", "content": "привет"}
    assert data["messages"][-1]["role"] == "assistant"
    assert len(data["messages"]) == 4
    assert saves[0][1] is data
    assert cache.sets[0][0] == "привет"
    assert "x" * 40 in cache.sets[0][1]
    assert calls["stream_kwargs"]["user_query"] == "привет"
    assert calls["stream_kwargs"]["context"] == ""
    assert any("SYSTEM-PROMPT" == s["content"] for s in calls["messages"])
    assert bot.deleted == [(100, 2), (100, 1)]


def test_ai_no_flush_short_chunks(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path, stream_chunks=("a", "b"))
    monkeypatch.setattr(messages.time, "time", FakeTime())
    msg = FakeMessage(text="привет")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert data["messages"][-1]["content"] == "ab"


def test_ai_cached_answer(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)
    cache = FakeCache("кэш-ответ")
    monkeypatch.setattr(messages, "get_cache", lambda: cache)
    msg = FakeMessage(text="привет")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert any("из кэша" in e[0] for e in msg.edits)
    assert cache.sets == []
    assert data["messages"][-1]["content"] == "кэш-ответ"


def test_ai_error_answer(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path, stream_chunks=("❌ ИИ сломан",))
    cache = FakeCache()
    monkeypatch.setattr(messages, "get_cache", lambda: cache)
    msg = FakeMessage(text="привет")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert cache.sets == []
    assert "❌ ИИ вернул ошибку" in msg.answers[-1][0]
    assert "❌ ИИ сломан" in msg.answers[-1][0]


def test_ai_empty_answer(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path, stream_chunks=("",))
    msg = FakeMessage(text="привет")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert data["messages"][-1]["content"] == "❌ Пустой ответ от ИИ."


def test_ai_send_failure(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)

    def boom(msg, answer, mode):
        raise RuntimeError("send down")

    monkeypatch.setattr(messages, "send_response_with_mode", boom)
    msg = FakeMessage(text="привет")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert "❌ Не удалось доставить ответ ИИ." in msg.answers[-1][0]


def test_ai_top_level_error(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)

    def boom(**kw):
        raise RuntimeError("prompt builder fail")

    monkeypatch.setattr(messages, "get_smart_prompt", boom)
    msg = FakeMessage(text="привет")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    # format_user_error для RuntimeError возвращает "❌ Ошибка выполнения"
    assert "Ошибка выполнения" in msg.answers[-1][0]
    assert bot.deleted == [(100, 1)]


def test_ai_finally_delete_fail(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)

    class BoomBot:
        async def delete_message(self, chat_id, message_id):
            raise Exception("already deleted")

    monkeypatch.setattr(messages, "bot", BoomBot())
    msg = FakeMessage(text="привет")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None


# ---------- wings ----------


def test_ai_explicit_wing(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)
    msg = FakeMessage(text="/dreams: расскажи о снах")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert data["messages"][-2] == {"role": "user", "content": "расскажи о снах"}
    assert any("Крыло: 🌙 Сны" in e[0] for e in msg.edits)


def test_ai_explicit_wing_status_edit_fail(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)
    msg = FakeMessage(text="/dreams: вопрос")
    msg.fail_status_edits = True
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert data["messages"][-1]["content"] == "x" * 40 + "y" * 40


def test_ai_unknown_wing_then_auto(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(messages, "classify_wing", lambda q: "psychology")
    msg = FakeMessage(text="/foo: вопрос")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert any("Крыло: 🧠 Психология" in e[0] for e in msg.edits)


# ---------- user context ----------


def _set_user_context(wing="w", room="r", drawer=None):
    from handlers.palace.shared import fsm

    fsm.update_data(4242, _user_context={
        "wing": wing, "room": room, "drawer": drawer,
    })


def test_ai_context_with_drawer(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)
    _set_user_context(drawer="d1")
    mcp = FakeMCPSeq(["текст записи"])
    monkeypatch.setattr(messages, "_get_mcp", lambda: mcp)
    msg = FakeMessage(text="о чём запись?")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert mcp.results == []
    assert calls["stream_kwargs"]["context"].startswith("\n--- ТЕКУЩАЯ ЗАПИСЬ")


def test_ai_context_room_drawers(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)
    _set_user_context(drawer=None)
    mcp = FakeMCPSeq([json.dumps({
        "drawers": [
            {"content_preview": "превью", "closet_name": "имя"},
            {"content": "нет превью", "title": "заголовок"},
            {"content": "без имени"},
        ],
    })])
    monkeypatch.setattr(messages, "_get_mcp", lambda: mcp)
    msg = FakeMessage(text="покажи записи")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    ctx = calls["stream_kwargs"]["context"]
    assert "ЗАПИСИ ИЗ ТЕКУЩЕЙ КОМНАТЫ" in ctx
    assert "--- имя ---" in ctx
    assert "--- заголовок ---" in ctx
    assert "без имени" not in ctx


def test_ai_context_empty_drawers(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)
    _set_user_context(drawer=None)
    mcp = FakeMCPSeq([json.dumps({"drawers": []})])
    monkeypatch.setattr(messages, "_get_mcp", lambda: mcp)
    msg = FakeMessage(text="вопрос")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert calls["stream_kwargs"]["context"] == ""


def test_ai_context_mcp_error(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)
    _set_user_context(drawer="d1")
    mcp = FakeMCPSeq([RuntimeError("mcp dead")])
    monkeypatch.setattr(messages, "_get_mcp", lambda: mcp)
    msg = FakeMessage(text="вопрос")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert calls["stream_kwargs"]["context"] == ""


# ---------- degrade / palace search ----------


def test_ai_degrade_palace_found(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(messages, "get_degradation_manager", lambda: FakeDeg(palace=True))
    monkeypatch.setattr(messages, "search_with_kg", _async("источники [1] текст"))
    success = []
    monkeypatch.setattr(messages, "report_success", lambda *a: success.append(a))
    msg = FakeMessage(text="вопрос")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert "ПРАВИЛА ЦИТИРОВАНИЯ" in calls["messages"][0]["content"]
    assert success == [("palace_search",)]


def test_ai_degrade_palace_empty(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(messages, "get_degradation_manager", lambda: FakeDeg(palace=True))
    failure = []
    monkeypatch.setattr(messages, "report_failure", lambda *a: failure.append(a))
    msg = FakeMessage(text="вопрос")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert failure == [("palace_search",)]


# ---------- coding mode ----------


def test_ai_enters_coding_mode(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(messages, "is_coding_context", lambda q, msgs: True)
    monkeypatch.setattr(messages, "ensure_project_dir", lambda fname: "/tmp/proj")
    msg = FakeMessage(text="напиши функцию")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert data["is_coding_mode"] is True
    assert data["project_dir"] == "/tmp/proj"


def test_ai_coding_mode_files(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(
        monkeypatch, tmp_path, data_extra={"is_coding_mode": True, "project_dir": "/p"},
    )
    monkeypatch.setattr(messages, "load_coding_prompt", lambda: "CODING-PROMPT")
    monkeypatch.setattr(messages, "read_project_files", lambda d: "file contents")
    msg = FakeMessage(text="продолжи")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    sys_msgs = calls["messages"][0]["content"]
    assert "CODING-PROMPT" in sys_msgs
    assert "file contents" in sys_msgs


# ---------- photos ----------


def test_ai_photo_analysis(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)
    prompts = {}
    monkeypatch.setattr(messages, "get_smart_prompt", lambda **kw: prompts.update(kw) or "P")
    monkeypatch.setattr(messages, "check_capability", lambda m, c: True)
    monkeypatch.setattr(messages, "list_photos", lambda: ["a.jpg", "b.jpg"])
    monkeypatch.setattr(messages, "encode_image_to_base64", lambda p: "b64:" + p)
    msg = FakeMessage(text="проанализируй фото")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert prompts["has_images"] is True
    assert calls["stream_kwargs"]["images"] == [
        "b64:" + os.path.join(str(tmp_path), "a.jpg"),
        "b64:" + os.path.join(str(tmp_path), "b.jpg"),
    ]


def test_ai_photo_no_capability(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)
    prompts = {}
    monkeypatch.setattr(messages, "get_smart_prompt", lambda **kw: prompts.update(kw) or "P")
    monkeypatch.setattr(messages, "check_capability", lambda m, c: False)
    msg = FakeMessage(text="проанализируй фото")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert prompts["has_images"] is False
    assert calls["stream_kwargs"]["images"] == []


def test_ai_photo_encode_none(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(messages, "check_capability", lambda m, c: True)
    monkeypatch.setattr(messages, "list_photos", lambda: ["a.jpg"])
    monkeypatch.setattr(messages, "encode_image_to_base64", lambda p: None)
    msg = FakeMessage(text="что на фото")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert calls["stream_kwargs"]["images"] == []


# ---------- memory ----------


def test_ai_memory_context(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(messages, "get_degradation_manager", lambda: FakeDeg(memory=True))
    monkeypatch.setattr(messages, "get_memory_context", lambda q, uid: "ПАМЯТЬ: факт")
    msg = FakeMessage(text="вопрос")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert "ПАМЯТЬ: факт" in calls["messages"][0]["content"]


def test_ai_memory_error(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(messages, "get_degradation_manager", lambda: FakeDeg(memory=True))

    def boom(q, uid):
        raise RuntimeError("memory down")

    monkeypatch.setattr(messages, "get_memory_context", boom)
    msg = FakeMessage(text="вопрос")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None


# ---------- summary / context additions ----------


def test_ai_active_summary(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path, data_extra={"summary": "СВОДКА"})
    msg = FakeMessage(text="вопрос")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert "📜 Контекст текущего диалога:\nСВОДКА" in calls["messages"][0]["content"]


def test_ai_critical_context_instruction(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)
    _set_user_context(room="r")
    mcp = FakeMCPSeq(["запись"])
    monkeypatch.setattr(messages, "_get_mcp", lambda: mcp)
    msg = FakeMessage(text="вопрос")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert "КРИТИЧЕСКИ ВАЖНО" in calls["messages"][0]["content"]


# ---------- SEARCH pattern ----------


def test_ai_search_pattern(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(
        monkeypatch, tmp_path, stream_chunks=("x" * 40 + " SEARCH: запрос в веб",),
    )
    monkeypatch.setattr(messages.time, "time", FakeTime())
    searched = []

    async def fake_search(query):
        searched.append(query)
        return "результаты веба"

    monkeypatch.setattr("services.web_search.search_web", fake_search)
    msg = FakeMessage(text="вопрос")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert searched == ["запрос в веб"]
    assert any("с поиском" in e[0] for e in msg.edits)
    assert len(bot.deleted) == 3


def test_ai_search_pattern_error(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path, stream_chunks=("SEARCH: тест",))

    async def boom(query):
        raise RuntimeError("web down")

    monkeypatch.setattr("services.web_search.search_web", boom)
    msg = FakeMessage(text="вопрос")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert data["messages"][-1]["content"] == "SEARCH: тест"


# ---------- save failure ----------


def test_ai_save_chat_failure(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)

    def boom(path, d):
        raise OSError("disk full")

    monkeypatch.setattr(messages, "save_chat", boom)
    msg = FakeMessage(text="привет")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None


# ---------- final branches ----------


def test_yt_audio_parts_cleanup_error(monkeypatch, tmp_path):
    part_dir = os.path.join(str(tmp_path), "pdir")
    os.makedirs(part_dir)
    part2 = os.path.join(str(tmp_path), "p2.mp3")
    with open(part2, "wb") as f:
        f.truncate(100)
    msg, _ = _yt_audio_setup(
        monkeypatch, tmp_path, messages.FILE_LIMIT + 1,
        compress_to=messages.FILE_LIMIT + 2, split=[part_dir, part2],
    )
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert len(msg.audios) == 2
    assert os.path.exists(part_dir)
    assert not os.path.exists(part2)


def test_ai_context_list_drawers_error(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)
    _set_user_context(drawer=None)
    mcp = FakeMCPSeq([RuntimeError("list fail")])
    monkeypatch.setattr(messages, "_get_mcp", lambda: mcp)
    msg = FakeMessage(text="вопрос")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert calls["stream_kwargs"]["context"] == ""


def test_ai_memory_empty(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(messages, "get_degradation_manager", lambda: FakeDeg(memory=True))
    monkeypatch.setattr(messages, "get_memory_context", lambda q, uid: "")
    msg = FakeMessage(text="вопрос")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None


def test_ai_cached_status_edit_fail(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(messages, "get_cache", lambda: FakeCache("кэш-ответ"))
    msg = FakeMessage(text="привет", fail_status_edits=True)
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert data["messages"][-1]["content"] == "кэш-ответ"


def test_ai_stream_flush_edit_fail(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(messages.time, "time", FakeTime())
    msg = FakeMessage(text="привет", fail_status_edits=True)
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert data["messages"][-1]["content"] == "x" * 40 + "y" * 40


def test_ai_context_empty_drawer_raw(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)
    _set_user_context(drawer="d1")
    mcp = FakeMCPSeq([""])
    monkeypatch.setattr(messages, "_get_mcp", lambda: mcp)
    msg = FakeMessage(text="вопрос")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert calls["stream_kwargs"]["context"] == ""


def test_ai_context_drawers_without_names(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)
    _set_user_context(drawer=None)
    mcp = FakeMCPSeq([json.dumps({"drawers": [
        {"content": "а"},
        {"content": "б"},
    ]})])
    monkeypatch.setattr(messages, "_get_mcp", lambda: mcp)
    msg = FakeMessage(text="вопрос")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert calls["stream_kwargs"]["context"] == ""


def test_ai_search_delete_fail(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(
        monkeypatch, tmp_path, stream_chunks=("x" * 40 + " SEARCH: q",),
    )
    monkeypatch.setattr(messages.time, "time", FakeTime())

    class BoomBot:
        async def delete_message(self, chat_id, message_id):
            raise Exception("cannot delete")

    monkeypatch.setattr(messages, "bot", BoomBot())

    async def fake_search(query):
        return "web results"

    monkeypatch.setattr("services.web_search.search_web", fake_search)
    msg = FakeMessage(text="вопрос")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert data["messages"][-1]["content"] == "x" * 40 + " SEARCH: q"


def test_ai_search_error_answer(monkeypatch, tmp_path):
    data, saves, calls, bot = _ai_setup(monkeypatch, tmp_path)
    queued = [["SEARCH: q"], ["❌ второй поток упал"]]

    def q_factory(*a, **k):
        return _agen(queued.pop(0))

    monkeypatch.setattr(messages, "stream_ai_response_async", q_factory)

    async def fake_search(query):
        return "results"

    monkeypatch.setattr("services.web_search.search_web", fake_search)
    msg = FakeMessage(text="вопрос")
    result = asyncio.run(messages.process_user_message(msg))
    assert result is None
    assert "❌ ИИ вернул ошибку" in msg.answers[-1][0]
