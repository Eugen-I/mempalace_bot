"""Unit-тесты для services/copilot_engine.py и handlers/copilot.py.

Проверяет:
- Формирование Сократического промпта
- Генерацию ответов арт-директора с авто-fallback на Ollama
- Суммаризацию творческого диалога
- Обработку Telegram команд /copilot, кнопок пауз, сброса, перехода к стилям
- Перехват текстовых сообщений пользователя в активной сессии
"""

import pytest

from handlers import copilot as h
import services.copilot_engine as engine
from services.copilot_session import CopilotSession, CopilotSessionManager, get_copilot_manager


class FakeUser:
    def __init__(self, uid=4242):
        self.id = uid


class FakeStatus:
    def __init__(self):
        self.edits = []
        self.last_kw = {}

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)
        self.last_kw = {"parse_mode": parse_mode, "reply_markup": reply_markup}


class FakeMessage:
    def __init__(self, uid=4242, text="/copilot Архитипы"):
        self.from_user = FakeUser(uid)
        self.chat = type("C", (), {"id": 1})()
        self.text = text
        self.answers = []
        self.last_status = None

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append(text)
        status = FakeStatus()
        self.last_status = status
        return status


class FakeCb:
    def __init__(self, uid=4242, data=""):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = FakeMessage(uid)
        self.answers = []

    async def answer(self, text=None, show_alert=None):
        self.answers.append((text, show_alert))


@pytest.fixture(autouse=True)
def clean_copilot_manager(tmp_path, monkeypatch):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", [4242], raising=False)
    monkeypatch.setattr(config, "ADMIN_ID", 4242, raising=False)

    fpath = tmp_path / "copilot_sessions.json"
    mgr = CopilotSessionManager(file_path=fpath)
    monkeypatch.setattr(h, "get_copilot_manager", lambda: mgr)
    monkeypatch.setattr(engine, "get_copilot_manager", lambda: mgr)


# ─── 1. services.copilot_engine тесты ───

def test_build_socratic_messages():
    history = [
        {"role": "user", "content": "Хочу снять человека перед зеркалом"},
        {"role": "assistant", "content": "Зеркало — классический символ Тени. Какое освещение?"},
    ]
    msgs = engine.build_socratic_messages("Архитипы Юнга", history)
    assert len(msgs) == 3
    assert msgs[0]["role"] == "system"
    assert "Архитипы Юнга" in msgs[0]["content"]
    assert msgs[1]["content"] == "Хочу снять человека перед зеркалом"
    assert msgs[2]["content"] == "Зеркало — классический символ Тени. Какое освещение?"


@pytest.mark.asyncio
async def test_generate_socratic_reply_happy_path(monkeypatch):
    sess = CopilotSession(user_id=4242, topic="Архитипы Юнга")

    async def fake_ai(eng, model, msgs, sampling=None):
        return "Зеркало разделяет реальность. Какое выражение лица у героя?"

    monkeypatch.setattr(engine, "get_ai_response_async", fake_ai)

    reply = await engine.generate_socratic_reply(sess, "Герой смотрит в отражение")
    assert "Зеркало разделяет реальность" in reply
    assert len(sess.dialogue_history) == 2
    assert sess.dialogue_history[0]["content"] == "Герой смотрит в отражение"
    assert sess.dialogue_history[1]["content"] == reply


@pytest.mark.asyncio
async def test_generate_socratic_reply_auto_fallback(monkeypatch):
    sess = CopilotSession(user_id=4242, topic="Архитипы Юнга")
    calls = []

    async def fake_ai(eng, model, msgs, sampling=None):
        calls.append(eng)
        if eng == "gemini":
            return "❌ Ошибка ИИ (gemini): 429 Quota exceeded"
        return "Ответ от локального Qwen: где источник света?"

    monkeypatch.setattr(engine, "get_current_ai", lambda: ("gemini", "gemini-2.5-flash"))
    monkeypatch.setattr(engine, "get_ai_response_async", fake_ai)

    reply = await engine.generate_socratic_reply(sess, "Снимаем ночью")
    assert "Ответ от локального Qwen" in reply
    assert calls == ["gemini", "qwen"]


@pytest.mark.asyncio
async def test_summarize_creative_dialogue(monkeypatch):
    sess = CopilotSession(user_id=4242, topic="Архитипы Юнга")
    sess.add_user_message("Хочу передать страх встречи с Тенью в метро")
    sess.add_assistant_message("Метро дает геометрию. Будет ли смаз?")
    sess.add_user_message("Да, длинная выдержка и силуэт")

    async def fake_ai(eng, model, msgs, sampling=None):
        return (
            "🎯 <b>Концептуальный конфликт:</b> Встреча с бессознательным в урбанистической суете\n"
            "💡 <b>Ключевая метафора:</b> Растворение силуэта в толпе\n"
            "🏛 <b>Пространство и свет:</b> Подземный переход, длинная выдержка\n"
            "👤 <b>Герой / Объект:</b> Застывшая фигура среди смазанного потока"
        )

    monkeypatch.setattr(engine, "get_ai_response_async", fake_ai)
    summary = await engine.summarize_creative_dialogue(sess)

    assert "Встреча с бессознательным" in summary
    assert sess.summary == summary


# ─── 2. handlers.copilot Telegram тесты ───

@pytest.mark.asyncio
async def test_cmd_copilot_without_args_shows_intro():
    msg = FakeMessage(text="/copilot")
    await h.cmd_copilot(msg)
    assert any("Арт-копайлот: Соавторство фотопроекта" in a for a in msg.answers)


@pytest.mark.asyncio
async def test_cmd_copilot_with_topic_starts_session(monkeypatch):
    async def fake_start(sess):
        return "Тема прекрасна. Кто главный герой сцены?"

    monkeypatch.setattr(h, "start_copilot_discussion", fake_start)

    msg = FakeMessage(text="/copilot Городской туман")
    await h.cmd_copilot(msg)

    mgr = h.get_copilot_manager()
    sess = mgr.get_session(4242)
    assert sess is not None
    assert sess.topic == "Городской туман"
    assert sess.stage == "discuss"
    assert any("Арт-директор изучает тему" in a for a in msg.answers)
    assert any("Кто главный герой сцены?" in e for e in msg.last_status.edits)


@pytest.mark.asyncio
async def test_handle_copilot_text_message(monkeypatch):
    mgr = h.get_copilot_manager()
    sess = mgr.create_or_replace_session(4242, "Городской туман")

    async def fake_reply(sess, text):
        return "Интересная мысль про фонари. Какой свет используем?"

    monkeypatch.setattr(h, "generate_socratic_reply", fake_reply)

    msg = FakeMessage(text="Фонари светят сквозь дымку")
    handled = await h.handle_copilot_text_message(msg)

    assert handled is True
    assert any("Интересная мысль про фонари" in e for e in msg.last_status.edits)


@pytest.mark.asyncio
async def test_handle_copilot_text_message_ignores_if_paused():
    mgr = h.get_copilot_manager()
    mgr.create_or_replace_session(4242, "Городской туман")
    mgr.pause_session(4242)

    msg = FakeMessage(text="Любой текст")
    handled = await h.handle_copilot_text_message(msg)
    assert handled is False


@pytest.mark.asyncio
async def test_cb_copilot_pause_and_resume():
    mgr = h.get_copilot_manager()
    sess = mgr.create_or_replace_session(4242, "Тема")
    sess.add_assistant_message("Вопрос")

    # Пауза
    cb_pause = FakeCb(data="cp_pause")
    await h.cb_copilot_pause(cb_pause)
    assert mgr.get_session(4242).is_paused is True

    # Возобновление
    cb_resume = FakeCb(data="cp_resume")
    await h.cb_copilot_resume(cb_resume)
    assert mgr.get_session(4242).is_paused is False


@pytest.mark.asyncio
async def test_cb_copilot_to_styles_and_back(monkeypatch):
    mgr = h.get_copilot_manager()
    sess = mgr.create_or_replace_session(4242, "Тема")
    sess.add_user_message("Ответ 1")
    sess.add_assistant_message("Вопрос 2")

    async def fake_summary(session):
        return "🎯 Концептуальный конфликт: Резюме темы"

    monkeypatch.setattr(h, "summarize_creative_dialogue", fake_summary)

    cb = FakeCb(data="cp_to_styles")
    await h.cb_copilot_to_styles(cb)

    assert sess.stage == "styles"
    assert "Концептуальный конфликт" in sess.summary

    # Возврат к обсуждению
    cb_back = FakeCb(data="cp_back_to_discuss")
    await h.cb_copilot_back_to_discuss(cb_back)
    assert sess.stage == "discuss"


@pytest.mark.asyncio
async def test_cb_copilot_reset():
    mgr = h.get_copilot_manager()
    mgr.create_or_replace_session(4242, "Тема")
    assert mgr.get_session(4242) is not None

    cb = FakeCb(data="cp_reset")
    await h.cb_copilot_reset(cb)
    assert mgr.get_session(4242) is None
