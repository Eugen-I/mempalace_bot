"""Unit-тесты для Шага 11: Контрастная дивергенция вариантов и интерактивный выбор."""

import json
import pytest

from handlers import copilot as hc
import services.copilot_engine as engine
from services.copilot_session import CopilotSessionManager


class FakeUser:
    def __init__(self, uid=8888):
        self.id = uid


class FakeStatus:
    def __init__(self):
        self.edits = []
        self.last_kw = {}

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)
        self.last_kw = {"parse_mode": parse_mode, "reply_markup": reply_markup}


class FakeMessage:
    def __init__(self, uid=8888, text=""):
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
    def __init__(self, uid=8888, data=""):
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
def variants_session(clean_copilot_manager):
    sess = clean_copilot_manager.create_or_replace_session(user_id=8888, topic="Архитипы Юнга")
    sess.selected_styles = ["Сюрреализм", "Экспрессионизм"]
    sess.manifesto = "Тень — не враг, а зеркало подавленных желаний."
    sess.tech_preferences = {
        "camera": "Fujifilm X-T4",
        "lens": "Гелиос 44-2 58mm f/2",
        "support": "С рук (микро-ICM)",
        "shutter_speed": '1/6"',
        "aperture": "f/2",
        "film_sim": "Classic Chrome",
        "lighting": "Контровой свет фонаря",
        "filter_accessory": "Black Pro-Mist 1/4",
        "handwriting_notes": "Микро-тремор на 1-2 мм",
    }
    sess.stage = "variants"
    return sess


def test_build_fallback_contrast_variants(variants_session):
    fallback = engine._build_fallback_contrast_variants(variants_session)
    assert len(fallback) == 3
    vectors = [p["vector"] for p in fallback]
    assert "Интимный / Камерный" in vectors
    assert "Монументальный / Геометрический" in vectors
    assert "Экспериментальный / Оптический" in vectors
    for p in fallback:
        assert p["title"] != ""
        assert p["visual_hook"] != ""
        assert p["camera_setup"] != ""
        assert len(p["shooting_steps"]) >= 2


@pytest.mark.asyncio
async def test_generate_contrast_variants_happy_path(variants_session, monkeypatch):
    mock_projects = [
        {
            "id": 1,
            "title": "«Лик Тени»",
            "vector": "Интимный / Камерный",
            "visual_hook": "Отражение в зеркале с мягким светом",
            "lighting_scene": "Мягкий контровой свет",
            "camera_setup": "X-T4 • Гелиос • f/2",
            "shooting_action": "Съемка с рук",
            "gear_summary": "X-T4 + Гелиос",
            "shooting_steps": ["Шаг 1", "Шаг 2"],
        },
        {
            "id": 2,
            "title": "«Лабиринт разума»",
            "vector": "Монументальный / Геометрический",
            "visual_hook": "Силуэт на лестнице",
            "lighting_scene": "Жесткий кьяроскуро",
            "camera_setup": "X-T4 • XF 18-55mm",
            "shooting_action": "Со штатива",
            "gear_summary": "X-T4 + XF 18-55mm",
            "shooting_steps": ["Шаг 1", "Шаг 2"],
        },
    ]

    async def fake_ai(*args, **kwargs):
        return f"```json\n{json.dumps(mock_projects, ensure_ascii=False)}\n```"

    monkeypatch.setattr(engine, "get_ai_response_async", fake_ai)
    res = await engine.generate_contrast_variants(variants_session)

    assert len(res) == 2
    assert res[0]["title"] == "«Лик Тени»"
    assert variants_session.stage == "variants"
    assert len(variants_session.candidate_projects) == 2


@pytest.mark.asyncio
async def test_generate_contrast_variants_fallback_on_error(variants_session, monkeypatch):
    async def fail_ai(*args, **kwargs):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(engine, "get_ai_response_async", fail_ai)
    res = await engine.generate_contrast_variants(variants_session)

    assert len(res) == 3
    assert variants_session.candidate_projects == res
    assert "Зеркальная тень" in res[0]["title"]


def test_format_single_variant_card(variants_session):
    variants_session.candidate_projects = engine._build_fallback_contrast_variants(variants_session)
    card = engine.format_single_variant_card(variants_session, idx=0)

    assert "Проект 1 из 3" in card
    assert "Интимный / Камерный" in card
    assert "Визуальный образ кадра:" in card
    assert "<!--" not in card

    # Проверка бейджа выбранного проекта
    variants_session.selected_project_idx = 0
    card_selected = engine.format_single_variant_card(variants_session, idx=0)
    assert "[ГЛАВНЫЙ ВЫБОР]" in card_selected


@pytest.mark.asyncio
async def test_refine_active_variant(variants_session, monkeypatch):
    variants_session.candidate_projects = engine._build_fallback_contrast_variants(variants_session)

    async def fake_refine(*args, **kwargs):
        return (
            "КАДР: Силуэт с каплями дождя на лице\n"
            "СВЕТ: Неоновый контровой блик\n"
            "СОВЕТ: Отличная идея для драмы"
        )

    monkeypatch.setattr(engine, "get_ai_response_async", fake_refine)
    advice = await engine.refine_active_variant(variants_session, "Добавь капли дождя", idx=0)

    assert "Отличная идея" in advice
    assert variants_session.candidate_projects[0]["visual_hook"] == "Силуэт с каплями дождя на лице"
    assert variants_session.candidate_projects[0]["lighting_scene"] == "Неоновый контровой блик"


@pytest.mark.asyncio
async def test_cb_copilot_to_variants(variants_session, monkeypatch):
    async def fake_gen(sess):
        sess.candidate_projects = engine._build_fallback_contrast_variants(sess)
        return sess.candidate_projects

    monkeypatch.setattr(hc, "generate_contrast_variants", fake_gen)

    cb = FakeCb(uid=variants_session.user_id, data="cp_to_variants")
    await hc.cb_copilot_to_variants(cb)

    assert variants_session.stage == "variants"
    assert len(variants_session.candidate_projects) == 3
    assert any("Проект 1 из 3" in e for e in cb.message.edits)


@pytest.mark.asyncio
async def test_cb_copilot_view_variant(variants_session):
    variants_session.candidate_projects = engine._build_fallback_contrast_variants(variants_session)

    cb = FakeCb(uid=variants_session.user_id, data="cp_view_var:1")
    await hc.cb_copilot_view_variant(cb)

    assert any("Проект 2 из 3" in e for e in cb.message.edits)


@pytest.mark.asyncio
async def test_cb_copilot_pick_variant(variants_session):
    variants_session.candidate_projects = engine._build_fallback_contrast_variants(variants_session)

    cb = FakeCb(uid=variants_session.user_id, data="cp_pick_var:1")
    await hc.cb_copilot_pick_variant(cb)

    assert variants_session.selected_project_idx == 1
    assert variants_session.stage == "completed"
    assert any("утвержден" in e for e in cb.message.edits)
    btn_cbs = [
        btn.callback_data
        for row in cb.message.last_reply_markup.inline_keyboard
        for btn in row
    ]
    assert "cp_to_field_assistant" in btn_cbs


@pytest.mark.asyncio
async def test_cb_copilot_reroll_variants(variants_session, monkeypatch):
    variants_session.candidate_projects = engine._build_fallback_contrast_variants(variants_session)
    variants_session.selected_project_idx = 0

    async def fake_gen(sess):
        sess.candidate_projects = [
            {"id": 1, "title": "Новый проект 1", "vector": "Интимный"},
            {"id": 2, "title": "Новый проект 2", "vector": "Монументальный"},
        ]
        return sess.candidate_projects

    monkeypatch.setattr(hc, "generate_contrast_variants", fake_gen)

    cb = FakeCb(uid=variants_session.user_id, data="cp_reroll_var")
    await hc.cb_copilot_reroll_variants(cb)

    assert variants_session.selected_project_idx is None
    assert len(variants_session.candidate_projects) == 2
    assert any("Новый проект 1" in e for e in cb.message.edits)


@pytest.mark.asyncio
async def test_handle_copilot_text_message_in_variants_stage(variants_session, monkeypatch):
    variants_session.candidate_projects = engine._build_fallback_contrast_variants(variants_session)

    async def fake_refine(sess, text, idx=0):
        sess.candidate_projects[idx]["visual_hook"] = f"Обновлено: {text}"
        return "Учтено"

    monkeypatch.setattr(hc, "refine_active_variant", fake_refine)

    msg = FakeMessage(uid=variants_session.user_id, text="Замени лицо на маску")
    handled = await hc.handle_copilot_text_message(msg)

    assert handled is True
    hook_val = variants_session.candidate_projects[0]["visual_hook"]
    assert "Обновлено: Замени лицо на маску" in hook_val
    assert any("Обновлено: Замени лицо на маску" in e for e in msg.last_status.edits)
