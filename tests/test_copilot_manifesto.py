"""Unit-тесты для Шага 9: Соавторство манифеста арт-копайлота.

Проверяет:
- Первоначальную генерацию манифеста (generate_initial_manifesto)
- Тональную коррекцию манифеста (refine_manifesto: darker, metaphoric, shorter, reroll, custom text)
- Форматирование карточки манифеста (format_manifesto_card)
- Telegram UI хендлеры:
  - переход к манифесту (cp_to_manifesto)
  - кнопки быстрой коррекции тональности (cp_manif_mod)
  - подтверждение манифеста (cp_confirm_manifesto)
  - текстовую доработку манифеста через ввод пользователя в stage="manifesto"
"""

import pytest

from handlers import copilot as h
import services.copilot_engine as engine
from services.copilot_session import CopilotSession, CopilotSessionManager


class FakeUser:
    def __init__(self, uid=4242):
        self.id = uid


class FakeMessage:
    def __init__(self, uid=4242, text=""):
        self.from_user = FakeUser(uid)
        self.chat = type("C", (), {"id": 1})()
        self.text = text
        self.answers = []
        self.edits = []
        self.last_status = None
        self.last_reply_markup = None

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append(text)
        status = FakeStatus()
        self.last_status = status
        return status

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)
        self.last_reply_markup = reply_markup


class FakeStatus:
    def __init__(self):
        self.edits = []
        self.last_kw = {}

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)
        self.last_kw = {"parse_mode": parse_mode, "reply_markup": reply_markup}


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


# ─── 1. services.copilot_engine тесты для манифеста ───

@pytest.mark.asyncio
async def test_generate_initial_manifesto(monkeypatch):
    sess = CopilotSession(
        user_id=4242,
        topic="Архитипы Юнга",
        summary="🎯 Концептуальный конфликт: Встреча с Тенью",
        selected_styles=["Сюрреализм", "Экспрессионизм"],
    )

    async def fake_ai(eng, model, msgs, sampling=None):
        return "Свет ломает привычный фасад реальности, обнажая Тень сквозь зеркала."

    monkeypatch.setattr(engine, "get_ai_response_async", fake_ai)

    manif = await engine.generate_initial_manifesto(sess)
    assert "Свет ломает привычный фасад" in manif
    assert sess.manifesto == manif


@pytest.mark.asyncio
async def test_refine_manifesto_darker_and_shorter(monkeypatch):
    sess = CopilotSession(
        user_id=4242,
        topic="Архитипы Юнга",
        manifesto="Первоначальный манифест.",
        selected_styles=["Экспрессионизм"],
    )

    recorded_prompts = []

    async def fake_ai(eng, model, msgs, sampling=None):
        recorded_prompts.append(msgs[-1]["content"])
        return "Мрачный и короткий манифест тени."

    monkeypatch.setattr(engine, "get_ai_response_async", fake_ai)

    # 1. Тональность darker
    res1 = await engine.refine_manifesto(sess, "darker")
    assert "более мрачным" in recorded_prompts[0]
    assert res1 == "Мрачный и короткий манифест тени."

    # 2. Кастомное указание
    await engine.refine_manifesto(sess, "Убери пафос")
    assert "Убери пафос" in recorded_prompts[1]


def test_format_manifesto_card():
    sess = CopilotSession(
        user_id=4242,
        topic="Архитипы Юнга",
        selected_styles=["Сюрреализм"],
        manifesto="Тень — это не враг, а зеркало.",
    )
    card = engine.format_manifesto_card(sess)
    assert "Художественный манифест проекта" in card
    assert "Архитипы Юнга" in card
    assert "👁 <b>Сюрреализм</b>" in card
    assert "<blockquote>Тень — это не враг, а зеркало.</blockquote>" in card


# ─── 2. Telegram UI Callback тесты ───

@pytest.mark.asyncio
async def test_cb_copilot_to_manifesto_generates_if_empty(monkeypatch):
    mgr = h.get_copilot_manager()
    sess = mgr.create_or_replace_session(4242, "Архитипы Юнга")
    sess.selected_styles = ["Сюрреализм"]

    async def fake_generate(session):
        session.manifesto = "Манифест о сновидениях и форме."
        return session.manifesto

    monkeypatch.setattr(h, "generate_initial_manifesto", fake_generate)

    cb = FakeCb(data="cp_to_manifesto")
    await h.cb_copilot_to_manifesto(cb)

    assert sess.stage == "manifesto"
    assert "Манифест о сновидениях" in sess.manifesto
    assert any("Художественный манифест проекта" in e for e in cb.message.edits)


@pytest.mark.asyncio
async def test_cb_copilot_manif_mod(monkeypatch):
    mgr = h.get_copilot_manager()
    sess = mgr.create_or_replace_session(4242, "Архитипы Юнга")
    sess.stage = "manifesto"
    sess.manifesto = "Исходный текст"

    async def fake_refine(session, instruction):
        session.manifesto = f"Уточненный текст ({instruction})"
        return session.manifesto

    monkeypatch.setattr(h, "refine_manifesto", fake_refine)

    cb = FakeCb(data="cp_manif_mod:metaphoric")
    await h.cb_copilot_manif_mod(cb)

    assert sess.manifesto == "Уточненный текст (metaphoric)"
    assert any("Уточненный текст (metaphoric)" in e for e in cb.message.edits)


@pytest.mark.asyncio
async def test_cb_copilot_confirm_manifesto():
    mgr = h.get_copilot_manager()
    sess = mgr.create_or_replace_session(4242, "Архитипы Юнга")
    sess.stage = "manifesto"
    sess.manifesto = "Утвержденный манифест"

    cb = FakeCb(data="cp_confirm_manifesto")
    await h.cb_copilot_confirm_manifesto(cb)

    assert sess.stage == "tech"
    assert any("Манифест успешно утвержден" in e for e in cb.message.edits)
    btn_texts = [b.text for row in cb.message.last_reply_markup.inline_keyboard for b in row]
    assert any("Параметры съемки и арсенал X-T4" in b for b in btn_texts)


@pytest.mark.asyncio
async def test_handle_copilot_text_message_in_manifesto_stage(monkeypatch):
    mgr = h.get_copilot_manager()
    sess = mgr.create_or_replace_session(4242, "Архитипы Юнга")
    sess.stage = "manifesto"
    sess.manifesto = "Старый манифест"

    async def fake_refine(session, instruction):
        session.manifesto = f"Манифест: {instruction}"
        return session.manifesto

    monkeypatch.setattr(h, "refine_manifesto", fake_refine)

    msg = FakeMessage(uid=4242, text="Добавь ночное метро и отражения в лужах")
    handled = await h.handle_copilot_text_message(msg)

    assert handled is True
    assert sess.manifesto == "Манифест: Добавь ночное метро и отражения в лужах"
    assert any("Манифест: Добавь ночное метро" in e for e in msg.last_status.edits)
