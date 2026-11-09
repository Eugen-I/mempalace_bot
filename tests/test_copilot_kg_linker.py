"""tests/test_copilot_kg_linker.py — Тесты привязки к Графу Знаний и Дворцу Памяти (MP-2).

Проверяет:
- Извлечение сущностей (стили, техника, механики, референсы, концепты).
- Интеллектуальное определение крыла (Wing) и чертога (Room) Дворца Памяти.
- Построение нормализованных триплетов (Subject -> Predicate -> Object).
- Безопасное форматирование карточки для Telegram (HTML: blockquote, code, no <!-- -->).
- Сохранение фактов через MemPalace MCP и graceful degradation при сбоях.
- Обработчики Telegram UI (кнопка в ассистенте, callbacks link и save).
"""

from unittest.mock import AsyncMock
import pytest

from handlers import copilot as hc
import services.copilot_kg_linker as linker
from services.copilot_session import CopilotSession, CopilotSessionManager


class FakeUser:
    def __init__(self, uid=8888):
        self.id = uid


class FakeMessage:
    def __init__(self, uid=8888):
        self.from_user = FakeUser(uid)
        self.edits = []
        self.answers = []
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
        self.answered = []

    async def answer(self, text=None, show_alert=False):
        self.answered.append((text, show_alert))


@pytest.fixture
def temp_manager(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "ALLOWED_IDS", {8888})
    mgr = CopilotSessionManager(file_path=tmp_path / "kg_linker_sessions.json")
    monkeypatch.setattr(hc, "get_copilot_manager", lambda: mgr)
    return mgr


def test_extract_project_kg_entities_empty():
    """Пустой объект получает дефолтное снаряжение без падений."""
    res = linker.extract_project_kg_entities(None)
    assert res["gear"] == ["Fujifilm X-T4"]
    assert res["styles"] == []
    assert res["concepts"] == []


def test_extract_project_kg_entities_copilot_session():
    """Корректное извлечение сущностей из сессии арт-копайлота."""
    session = CopilotSession(user_id=8888, topic="Ночной туман и зеркала")
    session.selected_styles = [{"name": "Пикториализм"}, "Сюрреализм"]
    session.manifesto_text = "Исследуем зеркальные отражения и свет."
    session.tech_preferences = {
        "lens": "Гелиос 44-2 58mm f/2",
        "filter": "Black Pro-Mist",
        "method": "микро-ICM со штатива",
    }
    session.project_variants = [
        {
            "title": "Зеркальный лабиринт",
            "gear": "Гелиос 44-2",
            "action_mechanic": "смаз на 1/4с",
        }
    ]
    session.selected_project_idx = 0

    entities = linker.extract_project_kg_entities(session)
    assert "Ночной туман и зеркала" in entities["concepts"]
    assert "Зеркальный лабиринт" in entities["concepts"]
    assert "Пикториализм" in entities["styles"]
    assert "Сюрреализм" in entities["styles"]
    assert any("Гелиос 44-2" in g for g in entities["gear"])
    assert any("микро-ICM" in m or "смаз" in m for m in entities["mechanics"])


def test_extract_project_kg_entities_from_dict_concept():
    """Извлечение сущностей из словарного концепта (Штурм 2.0)."""
    concept = {
        "title": "Тени старого города",
        "styles": [{"name": "Экспрессионизм"}],
        "gear": "Fujifilm X-T4 + XF 18-55mm",
        "action_mechanic": "контровой импульс света",
    }
    entities = linker.extract_project_kg_entities(concept)
    assert "Тени старого города" in entities["concepts"]
    assert "Экспрессионизм" in entities["styles"]
    assert "Fujifilm X-T4 + XF 18-55mm" in entities["gear"]
    assert "контровой импульс света" in entities["mechanics"]


def test_extract_known_artists_references():
    """Автоматическое распознавание упоминаний известных художников и авторов."""
    session = CopilotSession(user_id=8888, topic="Парящие яблоки в стиле Рене Магритт и Дали")
    entities = linker.extract_project_kg_entities(session)
    assert "Рене Магритт" in entities["references"]
    assert "Дали" in entities["references"]


def test_classify_palace_room_dreams():
    """Проекты со снами и сюрреализмом относятся к крылу dreams."""
    session = CopilotSession(user_id=8888, topic="Сюрреалистический сон о парящих часах")
    clf = linker.classify_palace_room_for_project(session)
    assert clf["wing_key"] == "dreams"
    assert "Сны" in clf["wing_display"]
    assert "Сюрреализма" in clf["room"]


def test_classify_palace_room_psychology():
    """Проекты с архетипами Юнга относятся к крылу psychology."""
    session = CopilotSession(user_id=8888, topic="Встреча с Тенью: архетипы Юнга и страх")
    clf = linker.classify_palace_room_for_project(session)
    assert clf["wing_key"] == "psychology"
    assert "Психология" in clf["wing_display"]
    assert "Архетипов" in clf["room"]


def test_classify_palace_room_philosophy():
    """Экзистенциальные темы относятся к крылу philosophy."""
    session = CopilotSession(user_id=8888, topic="Бытие и время: экзистенциальная пустота")
    clf = linker.classify_palace_room_for_project(session)
    assert clf["wing_key"] == "philosophy"
    assert "Философия" in clf["wing_display"]
    assert "Экзистенции" in clf["room"]


def test_classify_palace_room_creative_styles():
    """Проекты в крыле creative классифицируются по доминирующему стилю."""
    session_pict = CopilotSession(user_id=8888, topic="Утренний сад")
    session_pict.selected_styles = [{"name": "Пикториализм"}]
    clf = linker.classify_palace_room_for_project(session_pict)
    assert clf["wing_key"] == "creative"
    assert "Пикториальная" in clf["room"]

    session_expr = CopilotSession(user_id=8888, topic="Крик мегаполиса")
    session_expr.selected_styles = [{"name": "Экспрессионизм"}]
    clf_expr = linker.classify_palace_room_for_project(session_expr)
    assert clf_expr["wing_key"] == "creative"
    assert "Экспрессионистский" in clf_expr["room"]


def test_build_project_kg_triplets():
    """Генерация нормализованных триплетов графа знаний."""
    session = CopilotSession(user_id=8888, topic="Таинственный лес")
    session.selected_styles = [{"name": "Импрессионизм"}]
    session.tech_preferences = {"lens": "Гелиос 44-2"}

    triplets = linker.build_project_kg_triplets(session)
    predicates = [p for _, p, _ in triplets]
    assert "located_in_wing" in predicates
    assert "located_in_room" in predicates
    assert "has_style" in predicates
    assert ("Таинственный лес", "has_style", "Импрессионизм") in triplets


def test_link_project_to_palace_kg_structure():
    """Сводный интерфейс привязки возвращает полный словарь."""
    session = CopilotSession(user_id=8888, topic="Миражи пустыни")
    link_data = linker.link_project_to_palace_kg(session)
    assert link_data["project_title"] == "Миражи пустыни"
    assert link_data["wing_key"] in ["dreams", "creative", "psychology", "philosophy"]
    assert len(link_data["triplets"]) >= 2
    assert link_data["status"] == "ready"


def test_format_kg_link_card_html_safety():
    """Карточка для Telegram корректно экранирует спецсимволы и не содержит <!-- -->."""
    link_data = {
        "project_title": "Свет <&> Тень",
        "wing_display": "🎨 Творчество",
        "room": "Зал <1>",
        "triplets": [
            ("Свет <&> Тень", "has_style", "Пикториализм"),
            ("Свет <&> Тень", "uses_gear", "Fujifilm X-T4 <50mm>"),
        ],
    }
    card = linker.format_kg_link_card(link_data)
    assert "Граф Знаний • Привязка проекта" in card
    assert "Свет &lt;&amp;&gt; Тень" in card
    assert "<blockquote>" in card and "</blockquote>" in card
    assert "<!--" not in card
    assert "<div>" not in card
    assert "<script>" not in card


@pytest.mark.asyncio
async def test_save_project_to_kg_success():
    """Успешное сохранение триплетов через MCP-клиент."""
    session = CopilotSession(user_id=8888, topic="Осенняя элегия")
    session.selected_styles = [{"name": "Пикториализм"}]

    mock_mcp = AsyncMock()
    mock_mcp.call_tool.return_value = '{"status": "ok"}'

    count, errors = await linker.save_project_to_kg(session, mcp_client=mock_mcp)
    assert count >= 2
    assert errors == []
    assert mock_mcp.call_tool.call_count >= 2


@pytest.mark.asyncio
async def test_save_project_to_kg_mcp_failure_graceful_degradation():
    """Сбой MCP-клиента изолируется без исключений."""
    session = CopilotSession(user_id=8888, topic="Сбойный проект")
    mock_mcp = AsyncMock()
    mock_mcp.call_tool.side_effect = RuntimeError("MCP connection lost")

    count, errors = await linker.save_project_to_kg(session, mcp_client=mock_mcp)
    assert count == 0
    assert len(errors) >= 1
    assert "MCP connection lost" in errors[0]


def test_build_field_assistant_kb_has_kg_button():
    """В клавиатуре полевого ассистента присутствует кнопка привязки к Графу."""
    session = CopilotSession(user_id=8888, topic="Готовый проект")
    kb = hc.build_field_assistant_kb(session)
    cbs = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "cp_link_palace_kg" in cbs


@pytest.mark.asyncio
async def test_cb_copilot_link_and_save_kg(temp_manager, monkeypatch):
    """Сквозной тест открытия экрана линковки и сохранения в Граф Знаний."""
    session = temp_manager.create_or_replace_session(8888, "Городские миражи")
    session.selected_styles = [{"name": "Сюрреализм"}]
    temp_manager.save_session(session)

    # 1. Открытие экрана линковки
    cb_link = FakeCb(8888, data="cp_link_palace_kg")
    await hc.cb_copilot_link_palace_kg(cb_link)

    assert len(cb_link.message.edits) == 1
    card_text = cb_link.message.edits[0]
    assert "Граф Знаний • Привязка проекта" in card_text
    link_cbs = [
        btn.callback_data
        for row in cb_link.message.last_reply_markup.inline_keyboard
        for btn in row
    ]
    assert "cp_save_kg" in link_cbs
    assert "cp_to_field_assistant" in link_cbs

    # 2. Сохранение фактов
    mock_mcp = AsyncMock()
    mock_mcp.call_tool.return_value = '{"status": "ok"}'
    monkeypatch.setattr("services.palace_mcp.get_mcp", lambda: mock_mcp)

    cb_save = FakeCb(8888, data="cp_save_kg")
    await hc.cb_copilot_save_kg(cb_save)

    assert len(cb_save.answered) >= 1
    alert_text, is_alert = cb_save.answered[0]
    assert "добавлено" in alert_text
    assert is_alert is True
    assert len(cb_save.message.edits) == 1
    assert "Успешно сохранено триплетов" in cb_save.message.edits[0]
