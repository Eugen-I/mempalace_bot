"""Unit tests for handlers.settings."""

import json
import os
from types import SimpleNamespace

import pytest

from handlers import settings as st


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
        status = SimpleNamespace(edits=[], deleted=False)
        status.edit_text = _make_edit(status)
        self.status = status
        return status

    async def _edit(self, text, parse_mode=None):
        pass

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits = getattr(self, "edits", [])
        self.edits.append((text, parse_mode, reply_markup))
        return SimpleNamespace(edit_text=self._edit)


class FakeCb:
    def __init__(self, uid=4242, data=""):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = FakeMessage(uid)
        self.answered = []

    async def answer(self, text=None, show_alert=None):
        self.answered.append((text, show_alert))

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.message.edits.append((text, parse_mode, reply_markup))


def _make_edit(status):
    async def _edit(text, parse_mode=None):
        status.edits.append(text)

    return _edit


def _enable(monkeypatch, tmp_path):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {4242})
    ai_file = tmp_path / "ai.txt"
    ai_file.write_text("", encoding="utf-8")
    models = tmp_path / "models.json"
    models.write_text(
        json.dumps({"ollama": [{"tag": "qwen", "name": "Qwen"}, {"tag": "llava", "name": "Llava"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(st, "CONFIG_AI_FILE", str(ai_file))
    monkeypatch.setattr(st, "MODELS_CONFIG_PATH", str(models))
    voice = tmp_path / "voice.json"
    monkeypatch.setattr("services.tts_processor.VOICE_REPLY_CONFIG", str(voice))
    monkeypatch.setattr(st, "get_voice_settings", lambda uid: {"mode": "text", "speed": 160})
    monkeypatch.setattr(st, "set_voice_setting", lambda uid, k, v: None)
    monkeypatch.setattr(st, "get_agent_enabled", lambda uid: False)
    monkeypatch.setattr(st, "toggle_agent_enabled", lambda uid: True)
    return tmp_path


# ---------- build_settings_kb ----------


def test_build_settings_kb_default(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    markup, curr = st.build_settings_kb(4242)
    texts = _markup_texts(markup)
    assert curr == "gemini-flash-latest"
    assert "Режим: 📝 Текст" in texts
    assert "160 wpm" in texts
    assert "🤖 Агент: ВЫКЛ" in texts


def test_build_settings_kb_agent_enabled(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(st, "get_agent_enabled", lambda uid: True)
    markup, _ = st.build_settings_kb(4242)
    assert "🤖 Агент: ВКЛ" in _markup_texts(markup)


def test_build_settings_kb_current_model_from_file(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    (tmp_path / "ai.txt").write_text("qwen", encoding="utf-8")
    markup, curr = st.build_settings_kb(4242)
    assert curr == "qwen"


def test_build_settings_kb_voice_mode(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(st, "get_voice_settings", lambda uid: {"mode": "voice", "speed": 200})
    markup, _ = st.build_settings_kb(4242)
    assert "🎤 Голос" in _markup_texts(markup)


def test_build_settings_kb_both_mode(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(st, "get_voice_settings", lambda uid: {"mode": "both", "speed": 200})
    markup, _ = st.build_settings_kb(4242)
    assert "📝+🎤 Вместе" in _markup_texts(markup)


def _markup_texts(markup):
    return "|".join(b.text for row in markup.inline_keyboard for b in row)


# ---------- cb_show_help ----------


@pytest.mark.asyncio
async def test_cb_show_help(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="show_help")
    await st.cb_show_help(cb)
    assert "MemPalace Bot" in cb.message.edits[0][0]
    assert cb.message.edits[0][2] is not None
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cb_show_help_not_allowed(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(999, data="show_help")
    await st.cb_show_help(cb)
    assert cb.message.edits == []
    assert cb.answered == [("❌ Нет доступа", True)]


# ---------- cmd_callback_handler ----------


@pytest.mark.asyncio
async def test_cmd_callback_photos_empty(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr("services.multimodal.list_photos", lambda: [])
    cb = FakeCb(4242, data="cmd:photos")
    await st.cmd_callback_handler(cb)
    bodies = [a[0] for a in cb.message.answers]
    assert any("пуста" in b for b in bodies)
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cmd_callback_photos_with_items(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr("services.multimodal.list_photos", lambda: ["a.jpg", "b.jpg"])
    cb = FakeCb(4242, data="cmd:photos")
    await st.cmd_callback_handler(cb)
    bodies = [a[0] for a in cb.message.answers]
    assert any("a.jpg" in b for b in bodies)


@pytest.mark.asyncio
async def test_cmd_callback_analyze_photo_no_photos(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr("services.multimodal.list_photos", lambda: [])
    cb = FakeCb(4242, data="cmd:analyze_photo")
    await st.cmd_callback_handler(cb)
    assert cb.message.status.edits == ["❌ Нет фото для анализа."]


@pytest.mark.asyncio
async def test_cmd_callback_analyze_photo_not_multimodal(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr("services.multimodal.list_photos", lambda: ["a.jpg"])
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("ollama", "qwen"))
    monkeypatch.setattr("services.multimodal.check_capability", lambda m, f: False)
    cb = FakeCb(4242, data="cmd:analyze_photo")
    await st.cmd_callback_handler(cb)
    assert cb.message.status.edits[0].startswith("⚠️")


@pytest.mark.asyncio
async def test_cmd_callback_analyze_photo_success(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    photos = tmp_path / "photos"
    photos.mkdir()
    (photos / "a.jpg").write_bytes(b"x")
    monkeypatch.setattr("config.PHOTOS_DIR", str(photos))
    monkeypatch.setattr("services.multimodal.list_photos", lambda: ["a.jpg"])
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("ollama", "llava"))
    monkeypatch.setattr("services.multimodal.check_capability", lambda m, f: True)
    monkeypatch.setattr("services.multimodal.encode_image_to_base64", lambda p: "b64")
    monkeypatch.setattr("services.ai_engine._sync_ai_call", lambda *a, **kw: "описание фото")
    monkeypatch.setattr("services.text_formatter.safe_html_format", lambda t: t)
    monkeypatch.setattr("services.text_formatter.split_message", lambda t: [t])

    async def fake_to_thread(fn):
        return fn()

    import asyncio

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    cb = FakeCb(4242, data="cmd:analyze_photo")
    await st.cmd_callback_handler(cb)
    bodies = [a[0] for a in cb.message.answers]
    assert any("описание фото" in b for b in bodies)


@pytest.mark.asyncio
async def test_cmd_callback_analyze_photo_no_b64(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    photos = tmp_path / "photos2"
    photos.mkdir()
    (photos / "a.jpg").write_bytes(b"x")
    monkeypatch.setattr("config.PHOTOS_DIR", str(photos))
    monkeypatch.setattr("services.multimodal.list_photos", lambda: ["a.jpg"])
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("ollama", "llava"))
    monkeypatch.setattr("services.multimodal.check_capability", lambda m, f: True)
    monkeypatch.setattr("services.multimodal.encode_image_to_base64", lambda p: "")
    cb = FakeCb(4242, data="cmd:analyze_photo")
    await st.cmd_callback_handler(cb)
    assert cb.message.status.edits == ["❌ Ошибка кодирования фото."]


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_cmd_callback_analyze_photo_whitespace_part(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    photos = tmp_path / "photos3"
    photos.mkdir()
    (photos / "a.jpg").write_bytes(b"x")
    monkeypatch.setattr("config.PHOTOS_DIR", str(photos))
    monkeypatch.setattr("services.multimodal.list_photos", lambda: ["a.jpg"])
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("ollama", "llava"))
    monkeypatch.setattr("services.multimodal.check_capability", lambda m, f: True)
    monkeypatch.setattr("services.multimodal.encode_image_to_base64", lambda p: "Zm9v")
    monkeypatch.setattr("services.ai_engine._sync_ai_call", lambda *a, **k: "ответ")
    monkeypatch.setattr(
        "services.text_formatter.split_message", lambda t: ["   ", "<b>часть</b>"],
    )
    cb = FakeCb(4242, data="cmd:analyze_photo")
    await st.cmd_callback_handler(cb)
    bodies = [a[0] for a in cb.message.answers]
    assert any("часть" in b for b in bodies)
    assert any(a[1] is None for a in cb.message.answers)


@pytest.mark.asyncio
async def test_cmd_callback_analyze_photo_html_fallback(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    photos = tmp_path / "photos4"
    photos.mkdir()
    (photos / "a.jpg").write_bytes(b"x")
    monkeypatch.setattr("config.PHOTOS_DIR", str(photos))
    monkeypatch.setattr("services.multimodal.list_photos", lambda: ["a.jpg"])
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("ollama", "llava"))
    monkeypatch.setattr("services.multimodal.check_capability", lambda m, f: True)
    monkeypatch.setattr("services.multimodal.encode_image_to_base64", lambda p: "Zm9v")
    monkeypatch.setattr("services.ai_engine._sync_ai_call", lambda *a, **k: "ответ")
    monkeypatch.setattr("services.text_formatter.split_message", lambda t: ["<b>x</b>"])

    orig_answer = FakeMessage.answer

    async def flaky_answer(self, text, parse_mode=None, reply_markup=None):
        if parse_mode == "HTML":
            raise ValueError("HTML parse error")
        return await orig_answer(self, text, parse_mode, reply_markup)

    monkeypatch.setattr(FakeMessage, "answer", flaky_answer)
    cb = FakeCb(4242, data="cmd:analyze_photo")
    await st.cmd_callback_handler(cb)
    bodies = [a[0] for a in cb.message.answers]
    assert any("<b>x</b>" in b for b in bodies)


@pytest.mark.asyncio
async def test_cmd_callback_analyze_photo_ai_error(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    photos = tmp_path / "photos5"
    photos.mkdir()
    (photos / "a.jpg").write_bytes(b"x")
    monkeypatch.setattr("config.PHOTOS_DIR", str(photos))
    monkeypatch.setattr("services.multimodal.list_photos", lambda: ["a.jpg"])
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("ollama", "llava"))
    monkeypatch.setattr("services.multimodal.check_capability", lambda m, f: True)
    monkeypatch.setattr("services.multimodal.encode_image_to_base64", lambda p: "Zm9v")
    monkeypatch.setattr(
        "services.ai_engine._sync_ai_call", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    cb = FakeCb(4242, data="cmd:analyze_photo")
    await st.cmd_callback_handler(cb)
    # format_user_error для RuntimeError возвращает "❌ Ошибка выполнения"
    assert "Ошибка выполнения" in cb.message.status.edits[0]


async def test_build_settings_kb_ai_file_empty(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    (tmp_path / "ai.txt").write_text(" \n ", encoding="utf-8")
    markup, curr = st.build_settings_kb(4242)
    assert curr == "gemini-flash-latest"
    assert _markup_texts(markup)  # non-empty


def test_build_settings_kb_ai_file_set(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    (tmp_path / "ai.txt").write_text("qwen", encoding="utf-8")
    _, curr = st.build_settings_kb(4242)
    assert curr == "qwen"


def test_build_settings_kb_ai_file_missing(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    (tmp_path / "ai.txt").unlink()
    _, curr = st.build_settings_kb(4242)
    assert curr == "gemini-flash-latest"


async def test_cmd_callback_history(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="cmd:history")
    await st.cmd_callback_handler(cb)
    assert "историю" in cb.message.answers[0][0]


@pytest.mark.asyncio
async def test_cmd_callback_export(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="cmd:export")
    await st.cmd_callback_handler(cb)
    assert "Экспортирую" in cb.message.answers[0][0]


@pytest.mark.asyncio
async def test_cmd_callback_insights(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="cmd:insights")
    await st.cmd_callback_handler(cb)
    assert "insights" in cb.message.answers[0][0]


@pytest.mark.asyncio
async def test_cmd_callback_research(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="cmd:research")
    await st.cmd_callback_handler(cb)
    assert "research" in cb.message.answers[0][0]


@pytest.mark.asyncio
async def test_cmd_callback_sync_no_session(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    from handlers.chat import user_sessions

    monkeypatch.delitem(user_sessions, 4242, raising=False)
    cb = FakeCb(4242, data="cmd:sync")
    await st.cmd_callback_handler(cb)
    assert "Нет активного чата" in cb.message.answers[1][0]


@pytest.mark.asyncio
async def test_cmd_callback_sync_empty_chat(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    from handlers.chat import user_sessions

    monkeypatch.setitem(user_sessions, 4242, "chat_4242.md")
    chats = tmp_path / "chats"
    chats.mkdir()
    monkeypatch.setattr("config.CHATS_DIR", str(chats))
    monkeypatch.setattr("services.palace_bridge.export_chat_verbatim", lambda p, f: None)
    cb = FakeCb(4242, data="cmd:sync")
    await st.cmd_callback_handler(cb)
    assert "Чат пуст или не найден" in cb.message.answers[1][0]


@pytest.mark.asyncio
async def test_cmd_callback_sync_success(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    from handlers.chat import user_sessions

    monkeypatch.setitem(user_sessions, 4242, "chat_4242.md")
    chats = tmp_path / "chats"
    chats.mkdir()
    (chats / "chat_4242.md").write_text("данные", encoding="utf-8")
    monkeypatch.setattr("config.CHATS_DIR", str(chats))
    monkeypatch.setattr(
        "services.palace_bridge.export_chat_verbatim",
        lambda p, f: {"text": "экспорт"},
    )
    monkeypatch.setattr("services.palace_bridge.sync_to_palace", _async_result("✅ Синхронизировано"))
    cb = FakeCb(4242, data="cmd:sync")
    await st.cmd_callback_handler(cb)
    assert any("Синхронизировано" in a[0] for a in cb.message.answers)


def _async_result(value):
    async def _inner(*a, **kw):
        return value

    return _inner


@pytest.mark.asyncio
async def test_cmd_callback_unknown_command(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="cmd:nothing")
    await st.cmd_callback_handler(cb)
    assert cb.message.answers == []
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cmd_callback_no_data(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="cmd:x")
    cb.data = None
    await st.cmd_callback_handler(cb)
    assert cb.message.answers == []


# ---------- render_ollama_list ----------


@pytest.mark.asyncio
async def test_render_ollama_list(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    (tmp_path / "ai.txt").write_text("qwen", encoding="utf-8")
    cb = FakeCb(4242, data="list_ollama")
    await st.render_ollama_list(cb)
    assert "Активная модель" in cb.message.edits[0][0]
    texts = _markup_texts(cb.message.edits[0][2])
    assert "✅ Qwen (qwen)" in texts
    assert "🦙 Llava" in texts


@pytest.mark.asyncio
async def test_render_ollama_list_broken_models_file(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    (tmp_path / "models.json").write_text("{broken", encoding="utf-8")
    cb = FakeCb(4242, data="list_ollama")
    await st.render_ollama_list(cb)
    assert "Активная модель" in cb.message.edits[0][0]


# ---------- cmd_settings ----------


@pytest.mark.asyncio
async def test_cmd_settings(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage(4242, text="⚙️ Настройки")
    await st.cmd_settings(msg)
    assert "Текущая модель" in msg.answers[0][0]
    assert msg.answers[0][2] is not None


@pytest.mark.asyncio
async def test_cmd_settings_not_allowed(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage(999, text="⚙️ Настройки")
    await st.cmd_settings(msg)
    assert msg.answers == []


# ---------- cb_agent_toggle ----------


@pytest.mark.asyncio
async def test_cb_agent_toggle_enables(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    state = {"enabled": False}
    monkeypatch.setattr(st, "get_agent_enabled", lambda uid: state["enabled"])
    monkeypatch.setattr(
        st, "toggle_agent_enabled",
        lambda uid: state.update(enabled=not state["enabled"]) or state["enabled"],
    )
    cb = FakeCb(4242, data="agent_toggle")
    await st.cb_agent_toggle(cb)
    assert state["enabled"] is True
    assert cb.message.edits[-1][0] == "🤖 Модель: <code>gemini-flash-latest</code>"
    assert cb.answered == [("🤖 Агентный режим: ВКЛ", None)]


@pytest.mark.asyncio
async def test_cb_agent_toggle_disables(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    state = {"enabled": True}
    monkeypatch.setattr(st, "get_agent_enabled", lambda uid: state["enabled"])
    monkeypatch.setattr(
        st, "toggle_agent_enabled",
        lambda uid: state.update(enabled=not state["enabled"]) or state["enabled"],
    )
    cb = FakeCb(4242, data="agent_toggle")
    await st.cb_agent_toggle(cb)
    assert state["enabled"] is False
    assert cb.answered == [("🤖 Агентный режим: ВЫКЛ", None)]


# ---------- cb_voice_toggle ----------


@pytest.mark.asyncio
async def test_cb_voice_toggle_cycles_modes(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    states = {"mode": "text", "speed": 160}
    monkeypatch.setattr(st, "get_voice_settings", lambda uid: {"mode": "text", "speed": 160, **states})
    monkeypatch.setattr(st, "set_voice_setting", lambda uid, k, v: states.update({k: v}))

    for expected in ("voice", "both", "text"):
        cb = FakeCb(4242, data="voice_toggle")
        await st.cb_voice_toggle(cb)
        assert states["mode"] == expected
        assert cb.answered == [(None, None)]


# ---------- cb_speed ----------


@pytest.mark.asyncio
async def test_cb_speed_increase(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    states = {"speed": 160}
    monkeypatch.setattr(st, "get_voice_settings", lambda uid: {"mode": "text", **states})
    monkeypatch.setattr(st, "set_voice_setting", lambda uid, k, v: states.update({k: v}))
    cb = FakeCb(4242, data="spd:+10")
    await st.cb_speed(cb)
    assert states["speed"] == 170


@pytest.mark.asyncio
async def test_cb_speed_decrease(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    states = {"speed": 160}
    monkeypatch.setattr(st, "get_voice_settings", lambda uid: {"mode": "text", **states})
    monkeypatch.setattr(st, "set_voice_setting", lambda uid, k, v: states.update({k: v}))
    cb = FakeCb(4242, data="spd:-10")
    await st.cb_speed(cb)
    assert states["speed"] == 150


@pytest.mark.asyncio
async def test_cb_speed_clamped_low(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    states = {"speed": 95}
    monkeypatch.setattr(st, "get_voice_settings", lambda uid: {"mode": "text", **states})
    monkeypatch.setattr(st, "set_voice_setting", lambda uid, k, v: states.update({k: v}))
    cb = FakeCb(4242, data="spd:-10")
    await st.cb_speed(cb)
    assert states["speed"] == 100


@pytest.mark.asyncio
async def test_cb_speed_clamped_high(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    states = {"speed": 295}
    monkeypatch.setattr(st, "get_voice_settings", lambda uid: {"mode": "text", **states})
    monkeypatch.setattr(st, "set_voice_setting", lambda uid, k, v: states.update({k: v}))
    cb = FakeCb(4242, data="spd:+10")
    await st.cb_speed(cb)
    assert states["speed"] == 300


@pytest.mark.asyncio
async def test_cb_speed_no_data(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="spd:+10")
    cb.data = None
    await st.cb_speed(cb)
    assert cb.message.edits == []


# ---------- cb_list_ollama / cb_set_ai / cb_back ----------


@pytest.mark.asyncio
async def test_cb_list_ollama(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="list_ollama")
    await st.cb_list_ollama(cb)
    assert "Активная модель" in cb.message.edits[0][0]
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cb_set_ai_success(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    invalidated = []
    monkeypatch.setattr(st, "invalidate_ai_cache", lambda: invalidated.append(1))
    cb = FakeCb(4242, data="set_ai:qwen")
    await st.cb_set_ai(cb)
    assert (tmp_path / "ai.txt").read_text(encoding="utf-8") == "qwen"
    assert invalidated == [1]
    assert cb.answered == [("✅ Выбрана: qwen", True)]


@pytest.mark.asyncio
async def test_cb_set_ai_write_error(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(st, "CONFIG_AI_FILE", str(tmp_path / "no_dir" / "ai.txt"))
    invalidated = []
    monkeypatch.setattr(st, "invalidate_ai_cache", lambda: invalidated.append(1))
    cb = FakeCb(4242, data="set_ai:qwen")
    await st.cb_set_ai(cb)
    assert invalidated == []
    assert cb.answered == [("✅ Выбрана: qwen", True)]


@pytest.mark.asyncio
async def test_cb_back(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="back_settings")
    await st.cb_back(cb)
    assert "Модель" in cb.message.edits[0][0]
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cb_voice_toggle_not_allowed(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(999, data="voice_toggle")
    await st.cb_voice_toggle(cb)
    assert cb.message.edits == []
