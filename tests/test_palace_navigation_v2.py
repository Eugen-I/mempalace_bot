"""tests/test_palace_navigation_v2.py
Тесты модернизированной навигации и Telegram интерфейса (Этап 3).

Проверяет:
3.1 Хлебные крошки (render_breadcrumbs) во всех разделах.
3.2 Быстрый поиск и фильтрацию комнат текстом в крыле.
3.3 Оптимизированный предпросмотр ящиков (до 300 символов, даты, теги).
3.4 Экспорт визуальной карты комнат и туннелей в интерактивный HTML-файл.
"""

import asyncio
import json
import pytest

from handlers.palace import navigation as nav
from handlers import messages
from services.bot_setup import pending_room_filter


class FakeUser:
    id = 4242


class FakeMsg:
    from_user = FakeUser()
    answers = []
    edits = []
    documents = []

    def __init__(self, text=""):
        self.text = text
        self.chat = type("Chat", (), {"id": 1234})()
        self.answers = []
        self.edits = []
        self.documents = []

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append((text, parse_mode, reply_markup))
        return self

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append((text, parse_mode, reply_markup))
        return self

    async def answer_document(self, document, caption=None, parse_mode=None):
        self.documents.append((document, caption, parse_mode))
        return self


class FakeCb:
    def __init__(self, data=""):
        self.data = data
        self.from_user = FakeUser()
        self.message = FakeMsg()
        self.answered = False

    async def answer(self, text=None, show_alert=False):
        self.answered = True


@pytest.fixture(autouse=True)
def _auth(monkeypatch):
    import config
    monkeypatch.setattr(config, "ALLOWED_IDS", {4242})


def test_render_breadcrumbs():
    """3.1: Проверка формирования хлебных крошек."""
    b_wing = nav.render_breadcrumbs(wing="Наука")
    assert "🏰 <b>Дворец</b>" in b_wing
    assert "🕸️ <b>Наука</b>" in b_wing

    b_room = nav.render_breadcrumbs(wing="Наука", room="Физика")
    assert "🕸️ Наука" in b_room
    assert "📁 <b>Физика</b>" in b_room

    b_drawer = nav.render_breadcrumbs(wing="Наука", room="Физика", drawer="Кванты")
    assert "📁 Физика" in b_drawer
    assert "📄 <b>Кванты</b>" in b_drawer


@pytest.mark.asyncio
async def test_room_filter_prompt_and_search(monkeypatch):
    """3.2: Тест запроса фильтра комнат и выдачи отфильтрованного списка."""
    cb = FakeCb(data="p_rmsrch:it_wing")
    await nav.cb_room_search_prompt(cb)

    assert cb.answered is True
    assert pending_room_filter.get(4242) == "it_wing"
    assert "Поиск комнаты в крыле" in cb.message.edits[-1][0]

    # Пользователь отправляет запрос в чат
    class FakeMCP:
        async def call_tool(self, name, args=None):
            return json.dumps({
                "rooms": {
                    "python_core": 10,
                    "python_asyncio": 5,
                    "database_sql": 8,
                }
            })

    monkeypatch.setattr("services.palace_mcp.get_mcp", lambda: FakeMCP())

    msg = FakeMsg(text="python")
    await messages.process_user_message(msg)

    assert 4242 not in pending_room_filter
    last_edit = msg.edits[-1][0]
    assert "Найдено комнат (2)" in last_edit
    assert "python_core" in last_edit
    assert "python_asyncio" in last_edit
    assert "database_sql" not in last_edit


@pytest.mark.asyncio
async def test_room_filter_no_matches(monkeypatch):
    """3.2: Обработка случая, когда комната не найдена."""
    pending_room_filter[4242] = "it_wing"

    class FakeMCP:
        async def call_tool(self, name, args=None):
            return json.dumps({"rooms": {"java_core": 10}})

    monkeypatch.setattr("services.palace_mcp.get_mcp", lambda: FakeMCP())

    msg = FakeMsg(text="python")
    await messages.process_user_message(msg)

    assert 4242 not in pending_room_filter
    last_edit = msg.edits[-1][0]
    assert "не найдено комнат" in last_edit


@pytest.mark.asyncio
async def test_drawers_page_rich_preview_and_breadcrumbs(monkeypatch):
    """3.3: Проверка аккуратного предпросмотра до 300 симв., дат и тегов."""
    class FakeMCP:
        async def call_tool(self, name, args=None):
            return json.dumps({
                "drawers": [
                    {
                        "drawer_id": "d1",
                        "closet_name": "Запись 1",
                        "content_preview": "Длинный текст предпросмотра " * 10,
                        "created_at": "2026-11-01 12:00:00",
                        "tags": ["ai", "architecture"],
                    }
                ],
                "count": 1,
            })

    monkeypatch.setattr(nav, "get_mcp", lambda: FakeMCP())

    captured = {}
    async def fake_finalize(uid, edit_func, text, is_html=False, ctx=None, extra_rows=None, title=""):
        captured["text"] = text
        captured["ctx"] = ctx

    monkeypatch.setattr("handlers.palace.action_bar.finalize_answer", fake_finalize)

    msg = FakeMsg()
    await nav._show_drawers_page(msg.edit_text, 4242, "w_test", "r_test", 0)

    content = captured.get("text", "")
    assert "🏰 <b>Дворец</b> › 🕸️ w_test › 📁 <b>r_test</b>" in content
    assert "📅 2026-11-01" in content
    assert "🏷️ ai, architecture" in content
    assert "Длинный текст предпросмотра" in content


@pytest.mark.asyncio
async def test_export_palace_map_html_callback(monkeypatch):
    """3.4: Экспорт интерактивной карты в HTML-файл."""
    class FakeMCP:
        async def call_tool(self, name, args=None):
            if name == "mempalace_list_wings":
                return json.dumps({"wings": {"w1": 10, "w2": 5}})
            if name == "mempalace_list_tunnels":
                return json.dumps({"tunnels": [{"source": {"wing": "w1", "room": "r1"}, "target": {"wing": "w2", "room": "r2"}, "label": "связь"}]})
            if name == "mempalace_list_rooms":
                return json.dumps({"rooms": {"r1": 5, "r2": 5}})
            return "{}"

    monkeypatch.setattr(nav, "get_mcp", lambda: FakeMCP())

    cb = FakeCb(data="p_export_map")
    await nav.cb_export_map(cb)

    assert cb.answered is True
    assert len(cb.message.documents) == 1
    doc, caption, _ = cb.message.documents[0]
    assert doc.filename == "palace_map.html"
    assert "Интерактивная карта" in caption
    html_text = doc.data.decode("utf-8")
    assert "<!DOCTYPE html>" in html_text
    assert "graph-canvas" in html_text
    assert "w1" in html_text
    assert "r1" in html_text
