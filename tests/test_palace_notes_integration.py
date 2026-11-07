"""tests/test_palace_notes_integration.py — Комплексные тесты интеграции Заметок и Дворца памяти (Этап 4).

Тестирует:
- 4.1: Схему ящика и хранение обратных связей (drawer_backlinks) в SQLite.
- 4.2: Автоподбор комнаты через LLM и связывание через кнопку «💾 Связать с Дворцом».
- 4.3: Чекер обновлений: обнаружение изменений текста заметки и обновление ящика во Дворце.
- 4.4: Кнопку прямого перехода «📝 Открыть в Apple Notes» в просмотре ящика.
"""

import asyncio
import json
import sqlite3
import pytest

from services.notes_sync import (
    compute_content_hash,
    delete_backlink,
    get_backlink_by_drawer,
    get_backlinks_by_source,
    init_backlinks_db,
    list_all_backlinks,
    recommend_room_for_note,
    record_backlink,
    check_and_sync_note_updates,
)


class FakeMessage:
    def __init__(self, text: str = ""):
        self.text = text
        self.edits = []
        self.answers = []
        self.chat = type("Chat", (), {"id": 1234})()

    async def edit_text(self, text, **kwargs):
        self.edits.append((text, kwargs))
        self.text = text
        return self

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))
        return self


class FakeCb:
    def __init__(self, data: str, uid: int = 4242, message: FakeMessage | None = None):
        self.data = data
        self.from_user = type("User", (), {"id": uid, "username": "testuser"})()
        self.message = message or FakeMessage()
        self.answers = []

    async def answer(self, text: str | None = None, **kwargs):
        self.answers.append(text)


class FakeMCP:
    def __init__(self, responses: dict | None = None):
        self.responses = responses or {}
        self.calls = []

    async def call_tool(self, name: str, arguments: dict | None = None) -> str:
        self.calls.append((name, arguments or {}))
        if name in self.responses:
            res = self.responses[name]
            return json.dumps(res) if isinstance(res, dict) else str(res)
        if name == "mempalace_add_drawer":
            return json.dumps({"success": True, "drawer_id": "drawer_test_123"})
        if name == "mempalace_update_drawer":
            return json.dumps({"success": True, "drawer_id": arguments.get("drawer_id") if arguments else ""})
        if name == "mempalace_get_taxonomy":
            return json.dumps({"taxonomy": {"projects": ["alpha", "beta"], "my_notes": ["ideas", "daily"]}})
        return json.dumps({"success": True})


@pytest.fixture(autouse=True)
def allow_user(monkeypatch):
    import config
    monkeypatch.setattr(config, "ALLOWED_IDS", {4242})


# ============================================================================
# 4.1: Схема ящика и CRUD обратных связей (drawer_backlinks)
# ============================================================================

def test_backlinks_db_crud(tmp_path):
    db_file = str(tmp_path / "test_bot_state.sqlite")
    init_backlinks_db(db_file)

    # 1. Запись обратной связи
    rec = record_backlink(
        drawer_id="d_001",
        source_type="apple_notes",
        source_id="uuid-note-1",
        wing="projects",
        room="alpha",
        content="Контент важной заметки",
        title="План проекта",
        db_path=db_file,
    )
    assert rec["drawer_id"] == "d_001"
    assert rec["source_id"] == "uuid-note-1"
    assert rec["content_hash"] == compute_content_hash("Контент важной заметки")

    # 2. Получение по drawer_id
    item = get_backlink_by_drawer("d_001", db_path=db_file)
    assert item is not None
    assert item["wing"] == "projects"
    assert item["room"] == "alpha"
    assert item["source_title"] == "План проекта"

    # Несуществующий
    assert get_backlink_by_drawer("d_unknown", db_path=db_file) is None

    # 3. Получение по источнику
    by_src = get_backlinks_by_source("apple_notes", "uuid-note-1", db_path=db_file)
    assert len(by_src) == 1
    assert by_src[0]["drawer_id"] == "d_001"

    # Добавление второй связи для того же источника
    record_backlink(
        drawer_id="d_002",
        source_type="apple_notes",
        source_id="uuid-note-1",
        wing="archive",
        room="copy",
        content="Копия контента",
        title="План проекта (копия)",
        db_path=db_file,
    )
    by_src = get_backlinks_by_source("apple_notes", "uuid-note-1", db_path=db_file)
    assert len(by_src) == 2

    # 4. Список всех связей
    all_links = list_all_backlinks(db_path=db_file)
    assert len(all_links) == 2

    # 5. Удаление связи
    delete_backlink("d_001", db_path=db_file)
    assert get_backlink_by_drawer("d_001", db_path=db_file) is None
    by_src_after = get_backlinks_by_source("apple_notes", "uuid-note-1", db_path=db_file)
    assert len(by_src_after) == 1
    assert by_src_after[0]["drawer_id"] == "d_002"


# ============================================================================
# 4.2: Автоподбор комнаты через LLM и связывание
# ============================================================================

@pytest.mark.asyncio
async def test_recommend_room_for_note_ai_success(monkeypatch):
    from services import notes_sync

    async def fake_ai(engine, model, msgs):
        return json.dumps({
            "wing": "projects",
            "room": "backend_arch",
            "reason": "Заметка содержит архитектурные схемы бэкенда",
        })

    monkeypatch.setattr("services.ai_engine.get_ai_response_async", fake_ai)
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("test_engine", "test_model"))

    tax = {"projects": ["backend_arch", "frontend"], "my_notes": ["inbox"]}
    rec = await recommend_room_for_note("Схема БД", "Текст про PostgreSQL и репликацию", taxonomy=tax)
    assert rec["wing"] == "projects"
    assert rec["room"] == "backend_arch"
    assert "архитектурные" in rec["reason"]


@pytest.mark.asyncio
async def test_recommend_room_for_note_ai_fallback(monkeypatch):
    from services import notes_sync

    async def fake_ai_fail(engine, model, msgs):
        raise RuntimeError("AI model unavailable")

    monkeypatch.setattr("services.ai_engine.get_ai_response_async", fake_ai_fail)
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("test_engine", "test_model"))
    monkeypatch.setattr("services.wing_classifier.classify_wing", lambda q: "my_notes")

    rec = await recommend_room_for_note("Заметка", "Текст заметки")
    assert rec["wing"] == "my_notes"
    assert rec["room"] == "inbox"


# ============================================================================
# 4.3: Чекер обновлений (Apple Notes -> MemPalace)
# ============================================================================

@pytest.mark.asyncio
async def test_check_and_sync_note_updates(tmp_path, monkeypatch):
    db_file = str(tmp_path / "sync_test.sqlite")
    init_backlinks_db(db_file)

    initial_body = "Первоначальный текст заметки"
    full_content = f"📄 Моя заметка\n\n{initial_body}"
    record_backlink(
        drawer_id="d_sync_1",
        source_type="apple_notes",
        source_id="note_123",
        wing="my_notes",
        room="ideas",
        content=full_content,
        title="Моя заметка",
        db_path=db_file,
    )

    fake_mcp = FakeMCP()
    monkeypatch.setattr("services.palace_mcp.get_mcp", lambda: fake_mcp)

    # 1. Проверка без изменений — ничего не обновляется
    monkeypatch.setattr(
        "services.apple_notes.read_note",
        lambda nid: {"id": nid, "name": "Моя заметка", "body": initial_body},
    )
    res_noop = await check_and_sync_note_updates(note_id="note_123", db_path=db_file)
    assert res_noop["checked"] == 1
    assert res_noop["updated"] == 0
    assert len(fake_mcp.calls) == 0

    # 2. Изменение текста в Apple Notes
    updated_body = "Обновленный текст заметки с новыми мыслями"
    monkeypatch.setattr(
        "services.apple_notes.read_note",
        lambda nid: {"id": nid, "name": "Моя заметка", "body": updated_body},
    )
    res_updated = await check_and_sync_note_updates(note_id="note_123", db_path=db_file)
    assert res_updated["checked"] == 1
    assert res_updated["updated"] == 1
    assert len(res_updated["drawers"]) == 1
    assert res_updated["drawers"][0]["drawer_id"] == "d_sync_1"

    # Проверяем, что MCP call_tool('mempalace_update_drawer') был вызван
    update_calls = [c for c in fake_mcp.calls if c[0] == "mempalace_update_drawer"]
    assert len(update_calls) == 1
    assert update_calls[0][1]["drawer_id"] == "d_sync_1"
    assert "Обновленный текст" in update_calls[0][1]["content"]

    # 3. Повторная проверка — уже синхронизировано, no-op
    res_synced = await check_and_sync_note_updates(note_id="note_123", db_path=db_file)
    assert res_synced["updated"] == 0


# ============================================================================
# 4.4: Кнопка прямого перехода «📝 Открыть в Apple Notes» в navigation.py
# ============================================================================

@pytest.mark.asyncio
async def test_navigation_drawer_content_with_apple_notes_button(tmp_path, monkeypatch):
    import handlers.palace.navigation as nav

    captured = {}

    async def fake_finalize(uid, edit_func, text, ctx=None, title="", is_html=False, extra_rows=None):
        captured["extra_rows"] = extra_rows
        captured["title"] = title
        return None

    monkeypatch.setattr("handlers.palace.action_bar.finalize_answer", fake_finalize)
    cb = FakeCb(data="p_rd:0")

    # Сценарий A: Без обратной связи — только кнопка удаления
    nav._read_state[4242] = {"source_id": "", "source_type": ""}
    await nav._show_drawer_content(cb, 4242, "Текст ящика", "Мой ящик", "my_notes", "inbox", 0)
    buttons = [[b.callback_data for b in row] for row in captured["extra_rows"]]
    assert buttons == [["p_drdel:0"]]

    # Сценарий B: С обратной связью Apple Notes — кнопка перехода + кнопка удаления
    nav._read_state[4242] = {
        "source_id": "apple-uuid-999",
        "source_type": "apple_notes",
        "source_title": "Заметка в Apple Notes",
    }
    await nav._show_drawer_content(cb, 4242, "Текст ящика", "Мой ящик", "my_notes", "inbox", 0)
    buttons = [[b.callback_data for b in row] for row in captured["extra_rows"]]
    assert buttons == [
        ["p_notesrc:apple-uuid-999"],
        ["p_drdel:0"],
    ]
    texts = [[b.text for b in row] for row in captured["extra_rows"]]
    assert texts[0][0] == "📝 Открыть в Apple Notes"


# ============================================================================
# Интеграция с handlers/notes_agent.py (кнопки связывания)
# ============================================================================

@pytest.mark.asyncio
async def test_notes_agent_card_markup_and_linking(monkeypatch):
    import handlers.notes_agent as na

    # 1. Проверяем разметку карточки: кнопки связывания присутствуют
    kb = na._build_note_view_kb(uid=4242, idx=0, total=1, page=0)
    actions = [btn.callback_data for row in kb.export() for btn in row]
    assert "notes_save:0" in actions
    assert "notes_link:0" in actions

    # 2. Клик по notes_link:0
    fake_note = {"id": "note_xyz", "name": "Тестовая заметка"}
    na._notes_list_store[4242] = {"items": [fake_note], "text": "list"}

    monkeypatch.setattr(
        "services.apple_notes.read_note",
        lambda nid: {"id": nid, "name": "Тестовая заметка", "body": "Содержимое заметки"},
    )
    monkeypatch.setattr(
        "services.notes_sync.recommend_room_for_note",
        lambda title, body: asyncio.sleep(0, result={"wing": "projects", "room": "backend", "reason": "Тест"}),
    )

    cb = FakeCb(data="notes_link:0", uid=4242)
    await na.cb_notes_link(cb)

    assert 4242 in na._notes_link_store
    assert na._notes_link_store[4242]["wing"] == "projects"
    assert na._notes_link_store[4242]["room"] == "backend"

    # 3. Подтверждение связывания (notes_link_confirm:0)
    fake_mcp = FakeMCP()
    monkeypatch.setattr("services.palace_mcp.get_mcp", lambda: fake_mcp)

    cb_confirm = FakeCb(data="notes_link_confirm:0", uid=4242)
    await na.cb_notes_link_confirm(cb_confirm)

    add_calls = [c for c in fake_mcp.calls if c[0] == "mempalace_add_drawer"]
    assert len(add_calls) == 1
    assert add_calls[0][1]["wing"] == "projects"
    assert add_calls[0][1]["room"] == "backend"
    assert add_calls[0][1]["source_id"] == "note_xyz"
    assert add_calls[0][1]["source_type"] == "apple_notes"
