"""tests/test_fuji_multiexposure.py — Unit-тесты мультиэкспозиции Fujifilm X-T4 (Шаг S1, ST-1).

Проверяет:
- Датаклассы MultiExposureLayer и MultiExposurePlan.
- Автоматический подбор 4 режимов наложения (DARK, BRIGHT, AVERAGE, ADDITIVE) под арт-стили.
- Граничные условия по числу слоев (2..9 кадров, min=2, max=9).
- Стохастическую сюрреалистическую генерацию (Cadavre Exquis).
- Форматирование карточки для Telegram (HTML: no <!-- -->, safe escaping).
- Интеграцию с Telegram UI (кнопка в ассистенте, клавиатура режимов, callbacks).
"""

import pytest

from handlers import copilot as hc
import services.fuji_multiexposure as fme
from services.copilot_session import CopilotSession, CopilotSessionManager


class FakeUser:
    def __init__(self, uid=8888):
        self.id = uid


class FakeMessage:
    def __init__(self, uid=8888):
        self.from_user = FakeUser(uid)
        self.edits: list[str] = []
        self.answers: list[str] = []
        self.last_reply_markup = None

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)
        self.last_reply_markup = reply_markup

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append(text)
        self.last_reply_markup = reply_markup


class FakeCb:
    def __init__(self, uid=8888, data=""):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = FakeMessage(uid)
        self.answered: list[tuple[str | None, bool]] = []

    async def answer(self, text=None, show_alert=False):
        self.answered.append((text, show_alert))


@pytest.fixture
def temp_manager(tmp_path, monkeypatch):
    """Изолированный менеджер сессий для тестов."""
    storage_file = tmp_path / "test_multiexposure_sessions.json"
    mgr = CopilotSessionManager(storage_file)
    monkeypatch.setattr(hc, "get_copilot_manager", lambda: mgr)
    return mgr


# ============================================================================
# 1. ТЕСТЫ ДВИЖКА И ПОДБОРА РЕЖИМОВ (Happy path & Styles mapping)
# ============================================================================

def test_multiexposure_plan_default_dark_impressionism():
    """Happy path: импрессионизм автоматически выбирает режим DARK с акварельной лессировкой."""
    session = CopilotSession(user_id=101, topic="Париж в тумане")
    session.selected_styles = [{"name": "Импрессионизм"}]

    plan = fme.build_multiexposure_plan(session)
    assert plan.blend_mode == "DARK"
    assert "ТЁМНЫЙ" in plan.blend_mode_ru
    assert plan.frames_count == 2
    assert plan.total_ev_compensation == "-1.0 EV"
    assert len(plan.layers) == 2
    assert plan.layers[0].layer_idx == 1
    assert plan.layers[1].layer_idx == 2
    assert "1/6s" in plan.layers[1].shutter_speed  # лессировка
    assert len(plan.camera_steps) >= 5


def test_multiexposure_plan_pictorialism_average():
    """Стиль Пикториализм выбирает режим AVERAGE (усреднение) для мягкого расфокус-микса."""
    session = CopilotSession(user_id=102, topic="Старый сад")
    session.selected_styles = [{"name": "Пикториализм"}]

    plan = fme.build_multiexposure_plan(session)
    assert plan.blend_mode == "AVERAGE"
    assert "УСРЕДНЕНИЕ" in plan.blend_mode_ru
    assert plan.total_ev_compensation == "0.0 EV"
    assert len(plan.layers) == 2
    # Слой 1 - резкий, слой 2 - расфокус f/1.4
    assert plan.layers[0].aperture == "f/4.0"
    assert plan.layers[1].aperture == "f/1.4"
    assert "расфокус" in plan.layers[1].physics_action.lower()


def test_multiexposure_plan_expressionism_additive():
    """Стиль Экспрессионизм выбирает ADDITIVE (сложение) со световым контрастом."""
    session = CopilotSession(user_id=103, topic="Индустриальная геометрия")
    session.selected_styles = [{"name": "Экспрессионизм"}]

    plan = fme.build_multiexposure_plan(session)
    assert plan.blend_mode == "ADDITIVE"
    assert "СЛОЖЕНИЕ" in plan.blend_mode_ru
    assert plan.total_ev_compensation == "-1.5 EV"
    assert "ACROS+R" in plan.layers[0].film_simulation
    assert "ETERNA Bleach Bypass" in plan.layers[1].film_simulation


def test_multiexposure_plan_explicit_blend_mode_override():
    """Явное указание режима наложения переопределяет автоподбор по стилям."""
    session = CopilotSession(user_id=104, topic="Ночные силуэты")
    session.selected_styles = [{"name": "Импрессионизм"}]  # авто подобрал бы DARK

    # Принудительно заказываем BRIGHT
    plan = fme.build_multiexposure_plan(session, blend_mode="BRIGHT")
    assert plan.blend_mode == "BRIGHT"
    assert "ЯРКИЙ" in plan.blend_mode_ru
    assert plan.total_ev_compensation == "-0.5 EV"
    assert len(plan.layers) == 2


# ============================================================================
# 2. ГРАНИЧНЫЕ ЗНАЧЕНИЯ И ЗАЩИТА ЛИМИТОВ X-T4 (BVA / Edge cases)
# ============================================================================

def test_multiexposure_frames_limits_min_clamped_to_2():
    """Граничное условие min-1: заказ 1 кадра нормализуется до минимального аппаратного (2)."""
    plan = fme.build_multiexposure_plan(
        session_or_concept={"title": "Одиночный кадр", "styles": []},
        frames_count=1,
    )
    assert plan.frames_count == 2
    assert len(plan.layers) == 2


def test_multiexposure_frames_limits_max_clamped_to_9():
    """Граничное условие max+1: заказ 15 кадров ограничивается аппаратным лимитом X-T4 (9)."""
    plan = fme.build_multiexposure_plan(
        session_or_concept={"title": "Многократная экспозиция", "styles": []},
        frames_count=15,
    )
    assert plan.frames_count == 9
    assert len(plan.layers) == 9
    assert plan.layers[-1].layer_idx == 9


def test_multiexposure_intermediate_frames_count():
    """Проверка генерации 4 кадров со сквозной нумерацией."""
    plan = fme.build_multiexposure_plan(
        session_or_concept={"title": "Квартет", "styles": []},
        frames_count=4,
    )
    assert plan.frames_count == 4
    assert len(plan.layers) == 4
    for idx, layer in enumerate(plan.layers, start=1):
        assert layer.layer_idx == idx


# ============================================================================
# 3. СТОХАСТИЧЕСКИЙ СЮРРЕАЛИСТИЧЕСКИЙ ГЕНЕРАТОР (Cadavre Exquis)
# ============================================================================

def test_generate_surreal_multiexposure_stochastic():
    """Стохастический генератор создает комбо со случайным режимом и префиксом в названии."""
    session = CopilotSession(user_id=105, topic="Загадка времени")
    plan = fme.generate_surreal_multiexposure(session)

    assert "Сюрреалистический комбо:" in plan.title
    assert plan.blend_mode in fme.BLEND_MODES
    assert 2 <= plan.frames_count <= 4
    assert len(plan.layers) == plan.frames_count


def test_generate_surreal_multiexposure_random_diversity():
    """За 20 запусков стохастический генератор охватывает разные режимы наложения."""
    session = CopilotSession(user_id=106, topic="Фантом")
    modes = {fme.generate_surreal_multiexposure(session).blend_mode for _ in range(20)}
    assert len(modes) >= 2


# ============================================================================
# 4. БЕЗОПАСНОСТЬ И ФОРМАТИРОВАНИЕ КАРТОЧКИ ДЛЯ TELEGRAM (HTML Rules)
# ============================================================================

def test_format_multiexposure_card_telegram_html_safety():
    """Карточка соблюдает правила Telegram: нет <!-- -->, экранирование спецсимволов."""
    plan = fme.build_multiexposure_plan(
        session_or_concept={"title": "Тест <script>alert('xss')</script> & кадр", "styles": []},
        blend_mode="DARK",
        frames_count=2,
    )
    card = fme.format_multiexposure_card(plan)

    assert "<!--" not in card
    assert "-->" not in card
    assert "<script>" not in card
    assert "&lt;script&gt;" in card
    assert "&amp;" in card
    assert "<b>" in card
    assert "<code>" in card
    assert "<blockquote>" in card
    assert "🎬 <b>Послойный сценарий съемки:</b>" in card
    assert "📋 <b>Порядок действий на камере X-T4:</b>" in card


# ============================================================================
# 5. ИНТЕГРАЦИЯ С TELEGRAM UI (Клавиатуры и Callback-хендлеры)
# ============================================================================

def test_build_field_assistant_kb_has_multiexposure_button():
    """В клавиатуре полевого ассистента присутствует кнопка мультиэкспозиции."""
    session = CopilotSession(user_id=8888, topic="Готовый кадр")
    kb = hc.build_field_assistant_kb(session)
    cbs = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "cp_multiexposure" in cbs


def test_build_multiexposure_kb_structure():
    """Клавиатура мультиэкспозиции содержит все 4 режима, сюрреализм и возврат."""
    kb = hc.build_multiexposure_kb(active_mode="BRIGHT", frames_count=2)
    cbs = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    texts = [btn.text for row in kb.inline_keyboard for btn in row]

    assert "cp_me_blend:DARK" in cbs
    assert "cp_me_blend:BRIGHT" in cbs
    assert "cp_me_blend:AVERAGE" in cbs
    assert "cp_me_blend:ADDITIVE" in cbs
    assert "cp_me_surreal" in cbs
    assert "cp_to_field_assistant" in cbs

    # Активный режим BRIGHT помечен галочкой
    bright_btn = [t for t in texts if "Яркий" in t][0]
    assert "✅" in bright_btn


@pytest.mark.asyncio
async def test_cb_copilot_multiexposure_open(temp_manager):
    """Открытие экрана мультиэкспозиции из ассистента."""
    session = temp_manager.create_or_replace_session(8888, "Городские зеркала")
    session.selected_styles = [{"name": "Пикториализм"}]
    temp_manager.save_session(session)

    cb = FakeCb(8888, data="cp_multiexposure")
    await hc.cb_copilot_multiexposure(cb)

    assert len(cb.answered) >= 1
    assert len(cb.message.edits) == 1
    text = cb.message.edits[0]
    assert "Мультиэкспозиция X-T4" in text
    assert "УСРЕДНЕНИЕ" in text  # Пикториализм -> AVERAGE


@pytest.mark.asyncio
async def test_cb_copilot_me_blend_switch(temp_manager):
    """Переключение аппаратного режима наложения через callback."""
    session = temp_manager.create_or_replace_session(8888, "Городские зеркала")
    temp_manager.save_session(session)

    cb = FakeCb(8888, data="cp_me_blend:ADDITIVE")
    await hc.cb_copilot_me_blend(cb)

    assert len(cb.answered) >= 1
    ans_text, _ = cb.answered[0]
    assert "СЛОЖЕНИЕ" in str(ans_text)
    assert len(cb.message.edits) == 1
    assert "СЛОЖЕНИЕ" in cb.message.edits[0]


@pytest.mark.asyncio
async def test_cb_copilot_me_surreal_random(temp_manager):
    """Сюрреалистический комбо Cadavre Exquis через callback."""
    session = temp_manager.create_or_replace_session(8888, "Сновидение")
    temp_manager.save_session(session)

    cb = FakeCb(8888, data="cp_me_surreal")
    await hc.cb_copilot_me_surreal(cb)

    assert len(cb.answered) >= 1
    assert len(cb.message.edits) == 1
    assert "Сюрреалистический комбо" in cb.message.edits[0]


@pytest.mark.asyncio
async def test_cb_copilot_multiexposure_no_session(temp_manager):
    """Негативный тест: запрос мультиэкспозиции при отсутствии сессии сообщает об ошибке."""
    cb = FakeCb(9999, data="cp_multiexposure")
    await hc.cb_copilot_multiexposure(cb)

    assert len(cb.answered) == 1
    assert "Сессия не найдена" in cb.answered[0][0]
    assert len(cb.message.edits) == 0
