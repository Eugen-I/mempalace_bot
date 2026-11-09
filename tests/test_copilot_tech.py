"""Unit-тесты для технического диалога и сетапа арт-копайлота (Шаг 10)."""

import pytest

from handlers import copilot as hc
import services.copilot_engine as engine
from services.copilot_session import CopilotSessionManager


class FakeUser:
    def __init__(self, uid=12345):
        self.id = uid


class FakeStatus:
    def __init__(self):
        self.edits = []
        self.last_kw = {}

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)
        self.last_kw = {"parse_mode": parse_mode, "reply_markup": reply_markup}


class FakeMessage:
    def __init__(self, uid=12345, text=""):
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


class FakeCb:
    def __init__(self, uid=12345, data=""):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = FakeMessage(uid)
        self.answers = []

    async def answer(self, text=None, show_alert=None):
        self.answers.append((text, show_alert))


@pytest.fixture(autouse=True)
def clean_copilot_manager(tmp_path, monkeypatch):
    import config
    f = tmp_path / "copilot_sessions.json"
    mgr = CopilotSessionManager(file_path=f, ttl=3600)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr("services.copilot_session._global_manager", mgr)
    monkeypatch.setattr("services.copilot_engine.get_copilot_manager", lambda: mgr)
    monkeypatch.setattr("handlers.copilot.get_copilot_manager", lambda: mgr)
    return mgr


@pytest.fixture
def tech_session(clean_copilot_manager):
    sess = clean_copilot_manager.create_or_replace_session(
        user_id=12345, topic="Архитипы Юнга в метро",
    )
    sess.selected_styles = ["Импрессионизм", "Пиктореализм"]
    sess.manifesto = "Свет ломает формы, обнажая теневую суть."
    sess.stage = "tech"
    return sess


def test_init_tech_preferences_impressionism(tech_session):
    tech = engine.init_tech_preferences(tech_session)
    assert tech["camera"] == "Fujifilm X-T4"
    assert "Гелиос" in tech["lens"]
    assert "С рук" in tech["support"]
    assert tech["shutter_speed"] == '1/6"'
    assert tech["film_sim"] == "Velvia"
    assert "Pro-Mist" in tech["filter_accessory"]


def test_init_tech_preferences_expressionism(clean_copilot_manager):
    sess = clean_copilot_manager.create_or_replace_session(user_id=222, topic="Крик города")
    sess.selected_styles = ["Экспрессионизм"]
    tech = engine.init_tech_preferences(sess)
    assert tech["film_sim"] == "Monochrome"
    assert "Импульс" in tech["lighting"]
    assert tech["shutter_speed"] == '1/15"'


def test_init_tech_preferences_surrealism(clean_copilot_manager):
    sess = clean_copilot_manager.create_or_replace_session(user_id=333, topic="Геометрия снов")
    sess.selected_styles = ["Сюрреализм", "Конструктивизм"]
    tech = engine.init_tech_preferences(sess)
    assert "18-55" in tech["lens"]
    assert "призма" in tech["filter_accessory"].lower()


def test_update_tech_preference(tech_session):
    engine.init_tech_preferences(tech_session)

    # Переключение на штатив
    engine.update_tech_preference(tech_session, "support", "tripod")
    assert "Штатив" in tech_session.tech_preferences["support"]
    assert tech_session.tech_preferences["shutter_speed"] == '1/15"'

    # Переключение объектива на Fuji
    engine.update_tech_preference(tech_session, "lens", "fuji")
    assert "18-55" in tech_session.tech_preferences["lens"]
    assert tech_session.tech_preferences["aperture"] == "f/2.8–f/4"

    # Переключение фильтра на призму
    engine.update_tech_preference(tech_session, "filter", "prism")
    assert "призма" in tech_session.tech_preferences["filter_accessory"].lower()

    # Переключение света на импульс
    engine.update_tech_preference(tech_session, "light", "flash")
    assert "Импульс" in tech_session.tech_preferences["lighting"]


@pytest.mark.asyncio
async def test_consult_tech_parameters_happy_path(tech_session, monkeypatch):
    engine.init_tech_preferences(tech_session)

    async def fake_call(*args, **kwargs):
        return "В ночном дожде поднимите ISO до 800 и используйте контровой свет витрин."

    monkeypatch.setattr(engine, "get_ai_response_async", fake_call)
    advice = await engine.consult_tech_parameters(
        tech_session, "Будет темный дождь, снимаю со штатива на пленку velvia",
    )

    assert "ISO до 800" in advice
    # Проверяем учет ключевых слов
    assert "Штатив" in tech_session.tech_preferences["support"]
    assert tech_session.tech_preferences["film_sim"] == "Velvia"
    assert "Будет темный дождь" in tech_session.tech_preferences["handwriting_notes"]


@pytest.mark.asyncio
async def test_consult_tech_parameters_fallback_on_error(tech_session, monkeypatch):
    engine.init_tech_preferences(tech_session)

    async def fail_call(*args, **kwargs):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(engine, "get_ai_response_async", fail_call)
    advice = await engine.consult_tech_parameters(tech_session, "Как снять на открытой f/2?")

    assert "Fujifilm X-T4" in advice
    assert "Focus Peaking" in advice


def test_format_tech_card(tech_session):
    engine.init_tech_preferences(tech_session)
    card = engine.format_tech_card(
        tech_session, advice="Держите камеру двумя руками с упором в локти.",
    )

    assert "⚙️ <b>Съемочный сетап и почерк автора</b>" in card
    assert "Fujifilm X-T4" in card
    assert "Гелиос 44-2" in card
    assert "Совет оператора:" in card
    assert "Держите камеру" in card
    assert "<!--" not in card


@pytest.mark.asyncio
async def test_cb_copilot_to_tech(tech_session):
    cb = FakeCb(uid=tech_session.user_id, data="cp_to_tech")
    await hc.cb_copilot_to_tech(cb)

    assert tech_session.stage == "tech"
    assert any("Съемочный сетап" in e for e in cb.message.edits)


@pytest.mark.asyncio
async def test_cb_copilot_tech_toggle(tech_session):
    engine.init_tech_preferences(tech_session)

    cb = FakeCb(uid=tech_session.user_id, data="cp_tech:support:tripod")
    await hc.cb_copilot_tech_toggle(cb)

    assert any("Параметры обновлены" in a[0] for a in cb.answers)
    assert "Штатив" in tech_session.tech_preferences["support"]
    assert any("Съемочный сетап" in e for e in cb.message.edits)


@pytest.mark.asyncio
async def test_cb_copilot_confirm_tech(tech_session):
    engine.init_tech_preferences(tech_session)

    cb = FakeCb(uid=tech_session.user_id, data="cp_confirm_tech")
    await hc.cb_copilot_confirm_tech(cb)

    assert any("Съемочный сетап зафиксирован" in a[0] for a in cb.answers)
    assert tech_session.stage == "variants"
    assert any("утвержден" in e for e in cb.message.edits)
    btn_cbs = [
        btn.callback_data
        for row in cb.message.last_reply_markup.inline_keyboard
        for btn in row
    ]
    assert "cp_to_variants" in btn_cbs


@pytest.mark.asyncio
async def test_handle_copilot_text_message_in_tech_stage(tech_session, monkeypatch):
    engine.init_tech_preferences(tech_session)

    async def fake_consult(sess, user_input):
        sess.tech_preferences["support"] = "Штатив"
        return "Рекомендую выдержку 1/2 секунды для смаза фона."

    monkeypatch.setattr(hc, "consult_tech_parameters", fake_consult)

    msg = FakeMessage(uid=tech_session.user_id, text="Снимаю ночью на штативе со вспышкой")
    handled = await hc.handle_copilot_text_message(msg)

    assert handled is True
    assert tech_session.tech_preferences["support"] == "Штатив"
    assert any("Съемочный сетап" in e for e in msg.last_status.edits)
