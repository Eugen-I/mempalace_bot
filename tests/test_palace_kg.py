"""Unit tests for handlers.palace.kg."""

import asyncio
import json

import pytest

from handlers.palace import kg as k


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeMessage:
    def __init__(self, uid=4242):
        self.from_user = FakeUser(uid)
        self.answers = []
        self.edits = []

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append((text, parse_mode, reply_markup))
        return self

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append((text, parse_mode, reply_markup))


class FakeCb:
    def __init__(self, uid=4242, data="", message=None):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = message or FakeMessage(uid)
        self.answered = []

    async def answer(self, text=None, show_alert=None):
        self.answered.append((text, show_alert))


class FakeMCP:
    def __init__(self, result="{}", fail_on=None):
        self.result = result
        self.calls = []
        self.fail_on = fail_on

    async def call_tool(self, name, params=None):
        self.calls.append((name, params))
        if self.fail_on:
            raise RuntimeError(self.fail_on)
        return self.result


class FakeMCPSeq(FakeMCP):
    def __init__(self, results):
        self.results = list(results)
        self.calls = []
        self.fail_on = None

    async def call_tool(self, name, params=None):
        self.calls.append((name, params))
        return self.results.pop(0)


def _enable(monkeypatch):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {4242})
    monkeypatch.setattr(k, "safe_html_format", lambda x: x)


@pytest.fixture(autouse=True)
def _clean_state():
    from handlers.palace import shared as sh

    for key in ("_pending_mcp_input", "_kg_page_data", "_kg_search_data",
                "_kg_add_state", "_read_state"):
        sh.fsm.pop_data(4242, key)
    yield
    for key in ("_pending_mcp_input", "_kg_page_data", "_kg_search_data",
                "_kg_add_state", "_read_state"):
        sh.fsm.pop_data(4242, key)


@pytest.fixture(autouse=True)
def _tmp_interpretation(monkeypatch, tmp_path):
    from services import interpreter

    monkeypatch.setattr(
        interpreter, "PAIRS_FILE", str(tmp_path / "interpretation.json"),
    )
    interpreter._pairs.clear()
    interpreter._loaded = False
    yield
    interpreter._pairs.clear()
    interpreter._loaded = False


def _kb_data(markup):
    if markup is None:
        return []
    return [b.callback_data for row in markup.inline_keyboard for b in row]


def _capture_finalize(monkeypatch):
    captured = {}

    async def fake_finalize(uid, edit_func, text, is_html=False, ctx=None,
                            extra_rows=None, title=None):
        captured["uid"] = uid
        captured["text"] = text
        captured["ctx"] = ctx
        captured["extra_rows"] = extra_rows
        captured["title"] = title
        captured["is_html"] = is_html

    monkeypatch.setattr(
        "handlers.palace.action_bar.finalize_answer", fake_finalize,
    )
    return captured


def _capture_finalize_with_edit(monkeypatch):
    captured = {}

    async def fake_finalize(uid, edit_func, text, is_html=False, ctx=None,
                            extra_rows=None, title=None):
        captured["uid"] = uid
        captured["text"] = text
        captured["ctx"] = ctx
        captured["is_html"] = is_html
        captured["title"] = title
        if edit_func:
            await edit_func(text, parse_mode="HTML")

    monkeypatch.setattr(
        "handlers.palace.action_bar.finalize_answer", fake_finalize,
    )
    return captured


# ---------- cb_kg_menu ----------


def test_cb_kg_menu(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_kg")
    asyncio.run(k.cb_kg_menu(cb))
    body = cb.message.edits[-1][0]
    assert "Граф Знаний" in body
    assert _kb_data(cb.message.edits[-1][2]) == [
        "p_kgst", "p_kgq", "p_kga", "p_kg_help", "palace_back",
    ]


# ---------- cb_kg_help ----------


def test_cb_kg_help(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_kg_help")
    asyncio.run(k.cb_kg_help(cb))
    body = cb.message.edits[-1][0]
    assert "Граф Знаний — справка" in body
    assert "Платон → wrote → Государство" in body


# ---------- cb_kg_stats ----------


def test_cb_kg_stats_success(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"entities": 10, "facts": {"kind": 3}}')
    monkeypatch.setattr(k, "get_mcp", lambda: mcp)
    captured = _capture_finalize(monkeypatch)
    cb = FakeCb(data="p_kgst")
    asyncio.run(k.cb_kg_stats(cb))
    assert cb.message.answers[0][0] == "📊 Загружаю статистику KG..."
    assert "Сущностей в графе:</b> <code>10</code>" in captured["text"]
    assert "• kind: 3" in captured["text"]
    assert captured["ctx"] == {"parent_cb": "p_kg"}


def test_cb_kg_stats_relationship_types(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"relationship_types": ["author", "contains_idea"]}')
    monkeypatch.setattr(k, "get_mcp", lambda: mcp)
    captured = _capture_finalize(monkeypatch)
    cb = FakeCb(data="p_kgst")
    asyncio.run(k.cb_kg_stats(cb))
    assert "Типы связей (2):" in captured["text"]
    assert "author" in captured["text"]
    assert "автор" in captured["text"]
    assert "contains_idea" in captured["text"]
    assert "содержит идею" in captured["text"]


def test_cb_kg_stats_non_dict(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP("[1, 2]")
    monkeypatch.setattr(k, "get_mcp", lambda: mcp)
    captured = _capture_finalize(monkeypatch)
    cb = FakeCb(data="p_kgst")
    asyncio.run(k.cb_kg_stats(cb))
    assert "[1, 2]" in captured["text"]


def test_cb_kg_stats_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP(fail_on="mcp")
    monkeypatch.setattr(k, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_kgst")
    asyncio.run(k.cb_kg_stats(cb))
    assert cb.message.edits[-1][0] == "❌ Ошибка: mcp"


# ---------- cb_kg_add_start / cancel / subject / predicate ----------


def test_cb_kg_add_start(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_kga")
    asyncio.run(k.cb_kg_add_start(cb))
    assert k._pending_mcp_input[4242] == "kg_add_subject"
    assert k._kg_add_state[4242] == {"subject": "", "predicate": "", "object": ""}
    assert "субъект" in cb.message.edits[-1][0]


def test_cb_kg_add_cancel(monkeypatch):
    _enable(monkeypatch)
    k._kg_add_state[4242] = {"subject": "s"}
    k._pending_mcp_input[4242] = "kg_add_subject"
    cb = FakeCb(data="p_kga_x")
    asyncio.run(k.cb_kg_add_cancel(cb))
    assert cb.message.edits[-1][0] == "❌ Добавление факта отменено."
    assert 4242 not in k._kg_add_state
    assert 4242 not in k._pending_mcp_input


def test_cb_kg_add_subject_prompt(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_kga_s")
    asyncio.run(k.cb_kg_add_subject_prompt(cb))
    assert k._pending_mcp_input[4242] == "kg_add_subject"
    assert k._kg_add_state[4242] == {"subject": "", "predicate": "", "object": ""}


def test_cb_kg_add_predicate_menu(monkeypatch):
    _enable(monkeypatch)
    k._kg_add_state[4242] = {"subject": "Юнг"}
    cb = FakeCb(data="p_kga_p")
    asyncio.run(k.cb_kg_add_predicate_menu(cb))
    body = cb.message.edits[-1][0]
    assert "Субъект: <b>Юнг</b>" in body
    data = _kb_data(cb.message.edits[-1][2])
    assert "p_kga_pr:wrote" in data
    assert "p_kga_x" in data


def test_cb_kg_add_predicate_menu_no_state(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_kga_p")
    asyncio.run(k.cb_kg_add_predicate_menu(cb))
    assert cb.message.edits[-1][0] == "❌ Сессия истекла. Начните заново."


def test_cb_kg_add_predicate_chosen(monkeypatch):
    _enable(monkeypatch)
    k._kg_add_state[4242] = {"subject": "Юнг"}
    cb = FakeCb(data="p_kga_pr:influenced_by")
    asyncio.run(k.cb_kg_add_predicate_chosen(cb))
    assert k._kg_add_state[4242]["predicate"] == "influenced_by"
    assert k._pending_mcp_input[4242] == "kg_add_object"


def test_cb_kg_add_predicate_chosen_no_state(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_kga_pr:wrote")
    asyncio.run(k.cb_kg_add_predicate_chosen(cb))
    assert k._pending_mcp_input[4242] == "kg_add_object"


def test_cb_kg_add_object_prompt(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_kga_o")
    asyncio.run(k.cb_kg_add_object_prompt(cb))
    assert k._pending_mcp_input[4242] == "kg_add_object"


# ---------- cb_kg_add_confirm ----------


def test_cb_kg_add_confirm_success(monkeypatch):
    _enable(monkeypatch)
    k._kg_add_state[4242] = {
        "subject": "Юнг", "predicate": "wrote", "object": "Государство",
    }
    mcp = FakeMCP("✅ факт")
    monkeypatch.setattr(k, "get_mcp", lambda: mcp)
    captured = _capture_finalize(monkeypatch)
    cb = FakeCb(data="p_kga_c")
    asyncio.run(k.cb_kg_add_confirm(cb))
    assert mcp.calls[0] == (
        "mempalace_kg_add",
        {"subject": "Юнг", "predicate": "wrote", "object": "Государство"},
    )
    assert captured["text"] == "✅ факт"
    assert captured["ctx"] == {"parent_cb": "p_kg"}
    assert 4242 not in k._kg_add_state


def test_cb_kg_add_confirm_empty_raw(monkeypatch):
    _enable(monkeypatch)
    k._kg_add_state[4242] = {
        "subject": "Юнг", "predicate": "wrote", "object": "Государство",
    }
    mcp = FakeMCP("")
    monkeypatch.setattr(k, "get_mcp", lambda: mcp)
    captured = _capture_finalize(monkeypatch)
    cb = FakeCb(data="p_kga_c")
    asyncio.run(k.cb_kg_add_confirm(cb))
    assert captured["text"] == "✅ Факт сохранён!"


def test_cb_kg_add_confirm_no_state(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_kga_c")
    asyncio.run(k.cb_kg_add_confirm(cb))
    assert cb.message.edits[-1][0] == "❌ Сессия истекла."


def test_cb_kg_add_confirm_error(monkeypatch):
    _enable(monkeypatch)
    k._kg_add_state[4242] = {
        "subject": "Юнг", "predicate": "wrote", "object": "Государство",
    }
    mcp = FakeMCP(fail_on="mcp")
    monkeypatch.setattr(k, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_kga_c")
    asyncio.run(k.cb_kg_add_confirm(cb))
    assert cb.message.edits[-1][0] == "❌ Ошибка: mcp"


def test_cb_kg_add_confirm_renders_fact_json(monkeypatch):
    """Регрессия: сырой JSON движка (\\u-escaped) должен превращаться
    в читаемое сообщение с русским лейблом предиката."""
    _enable(monkeypatch)
    k._kg_add_state[4242] = {
        "subject": "Эмиль Чоран", "predicate": "author", "object": "Признания и проклятия",
    }
    raw = json.dumps({
        "success": True,
        "triple_id": "t_эмиль_чоран_author_признания",
        "fact": "Эмиль Чоран → author → Признания и проклятия",
    }, ensure_ascii=True)
    mcp = FakeMCP(raw)
    monkeypatch.setattr(k, "get_mcp", lambda: mcp)
    captured = _capture_finalize(monkeypatch)
    cb = FakeCb(data="p_kga_c")
    asyncio.run(k.cb_kg_add_confirm(cb))
    assert "✅ Факт сохранён в графе знаний!" in captured["text"]
    assert "→ автор →" in captured["text"]
    assert "triple_id" not in captured["text"]
    assert captured["ctx"] == {"parent_cb": "p_kg"}


def test_cb_kg_add_confirm_json_no_fact(monkeypatch):
    _enable(monkeypatch)
    k._kg_add_state[4242] = {
        "subject": "Юнг", "predicate": "wrote", "object": "Государство",
    }
    mcp = FakeMCP(json.dumps({"success": True, "triple_id": "t_1"}))
    monkeypatch.setattr(k, "get_mcp", lambda: mcp)
    captured = _capture_finalize(monkeypatch)
    cb = FakeCb(data="p_kga_c")
    asyncio.run(k.cb_kg_add_confirm(cb))
    assert captured["text"] == "✅ Факт сохранён!"


def test_cb_kg_add_confirm_json_failure(monkeypatch):
    _enable(monkeypatch)
    k._kg_add_state[4242] = {
        "subject": "Юнг", "predicate": "wrote", "object": "Государство",
    }
    mcp = FakeMCP(json.dumps({"success": False, "error": "нет прав"}))
    monkeypatch.setattr(k, "get_mcp", lambda: mcp)
    captured = _capture_finalize(monkeypatch)
    cb = FakeCb(data="p_kga_c")
    asyncio.run(k.cb_kg_add_confirm(cb))
    assert captured["text"] == "❌ Не удалось сохранить факт. нет прав"


def test_cb_kg_add_confirm_unknown_predicate_kept(monkeypatch):
    _enable(monkeypatch)
    k._kg_add_state[4242] = {
        "subject": "X", "predicate": "custom_rel", "object": "Y",
    }
    mcp = FakeMCP(json.dumps({"success": True, "fact": "X → custom_rel → Y"}))
    monkeypatch.setattr(k, "get_mcp", lambda: mcp)
    captured = _capture_finalize(monkeypatch)
    cb = FakeCb(data="p_kga_c")
    asyncio.run(k.cb_kg_add_confirm(cb))
    assert "→ custom_rel →" in captured["text"]
    assert "Факт сохранён в графе знаний" in captured["text"]


def test_cb_kg_add_confirm_non_dict_json(monkeypatch):
    _enable(monkeypatch)
    k._kg_add_state[4242] = {
        "subject": "Юнг", "predicate": "wrote", "object": "Государство",
    }
    mcp = FakeMCP(json.dumps(["a", "b"]))
    monkeypatch.setattr(k, "get_mcp", lambda: mcp)
    captured = _capture_finalize(monkeypatch)
    cb = FakeCb(data="p_kga_c")
    asyncio.run(k.cb_kg_add_confirm(cb))
    assert captured["text"] == '["a", "b"]'


# ---------- cb_kg_query_prompt / continue / restart / read ----------


def test_cb_kg_query_prompt(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_kgq")
    asyncio.run(k.cb_kg_query_prompt(cb))
    assert k._pending_mcp_input[4242] == "kg_query"


def test_cb_kg_continue(monkeypatch):
    _enable(monkeypatch)
    k._kg_page_data[4242] = {"entity": "Э", "facts": [], "page": 0}
    called = []

    async def fake_send(uid, edit_func):
        called.append((uid, edit_func))

    monkeypatch.setattr(k, "_send_kg_page", fake_send)
    cb = FakeCb(data="p_kgc")
    asyncio.run(k.cb_kg_continue(cb))
    assert k._kg_page_data[4242]["page"] == 1
    assert called[0][0] == 4242


def test_cb_kg_continue_no_data(monkeypatch):
    _enable(monkeypatch)
    called = []

    async def fake_send(uid, edit_func):
        called.append(uid)

    monkeypatch.setattr(k, "_send_kg_page", fake_send)
    cb = FakeCb(data="p_kgc")
    asyncio.run(k.cb_kg_continue(cb))
    assert called == [4242]


def test_cb_kg_restart(monkeypatch):
    _enable(monkeypatch)
    k._kg_page_data[4242] = {"entity": "Э", "facts": [], "page": 3}
    called = []

    async def fake_send(uid, edit_func):
        called.append(uid)

    monkeypatch.setattr(k, "_send_kg_page", fake_send)
    cb = FakeCb(data="p_kgs")
    asyncio.run(k.cb_kg_restart(cb))
    assert k._kg_page_data[4242]["page"] == 0


def test_cb_kg_restart_no_data(monkeypatch):
    _enable(monkeypatch)
    called = []

    async def fake_send(uid, edit_func):
        called.append(uid)

    monkeypatch.setattr(k, "_send_kg_page", fake_send)
    cb = FakeCb(data="p_kgs")
    asyncio.run(k.cb_kg_restart(cb))
    assert called == [4242]


def test_cb_kg_read_success(monkeypatch):
    _enable(monkeypatch)
    k._kg_page_data[4242] = {"entity": "Юнг", "facts": []}
    shown = []

    async def fake_read(uid, edit_func):
        shown.append((uid, edit_func))

    monkeypatch.setattr(k, "_kg_read_sources", fake_read)
    cb = FakeCb(data="p_kgr")
    asyncio.run(k.cb_kg_read(cb))
    assert shown[0][0] == 4242


def test_cb_kg_read_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_kgr")
    asyncio.run(k.cb_kg_read(cb))
    assert cb.message.edits[-1][0] == "❌ Нет данных для чтения."


# ---------- _kg_read_sources ----------


def test_kg_read_sources_success(monkeypatch):
    """Регрессия: «Читать записи» показывает ТОЛЬКО файлы из фактов графа,
    с дедупом и без глобального mempalace_search."""
    _enable(monkeypatch)
    k._kg_page_data[4242] = {
        "entity": "эмиль_чоран",
        "facts": [
            {"source_closet": "my_notes/Мысли из книг/Признания и проклятия..txt"},
            {"source_closet": "my_notes/Мысли из книг/Признания и проклятия..txt"},
            {"source_closet": "my_notes/Цитаты/Список книг.txt"},
            {"subject": "без файла", "predicate": "x", "object": "y"},
        ],
        "page": 0,
    }
    monkeypatch.setattr(k, "_get_full_text_from_chroma", lambda src: f"текст {src}")
    sent = []

    async def fake_send(uid, edit_func):
        sent.append(uid)

    monkeypatch.setattr(k, "_send_kg_search_page", fake_send)
    edits = []

    async def edit_func(text, **kw):
        edits.append(text)

    ok = asyncio.run(k._kg_read_sources(4242, edit_func))
    assert ok is True
    assert sent == [4242]
    assert edits == []
    assert k._kg_search_data[4242] == {
        "entity": "эмиль_чоран",
        "results": [
            {
                "content": "текст my_notes/Мысли из книг/Признания и проклятия..txt",
                "source_file": "Признания и проклятия..txt",
                "wing": "my_notes", "room": "Мысли из книг",
            },
            {
                "content": "текст my_notes/Цитаты/Список книг.txt",
                "source_file": "Список книг.txt",
                "wing": "my_notes", "room": "Цитаты",
            },
        ],
        "page": 0, "mode": "kg",
    }


def test_kg_read_sources_no_sources(monkeypatch):
    """Факты без source_closet (добавленные вручную) — сообщение + кнопка поиска."""
    _enable(monkeypatch)
    k._kg_page_data[4242] = {
        "entity": "юнг",
        "facts": [
            {"subject": "Юнг", "predicate": "wrote", "object": "Государство"},
        ],
        "page": 0,
    }
    edits = []
    markups = []

    async def edit_func(text, **kw):
        edits.append(text)
        markups.append(kw.get("reply_markup"))

    ok = asyncio.run(k._kg_read_sources(4242, edit_func))
    assert ok is False
    assert "не привязаны к файлам" in edits[-1]
    buttons = _kb_data(markups[-1])
    assert buttons == ["p_kgrs:юнг"]


def test_kg_read_sources_no_data(monkeypatch):
    _enable(monkeypatch)
    edits = []

    async def edit_func(text, **kw):
        edits.append(text)

    ok = asyncio.run(k._kg_read_sources(4242, edit_func))
    assert ok is False
    assert edits == ["❌ Сессия истекла. Начните заново."]


def test_kg_read_sources_all_missing_in_chroma(monkeypatch):
    """Все файлы из фактов не найдены в Chroma — сообщение."""
    _enable(monkeypatch)
    k._kg_page_data[4242] = {
        "entity": "юнг",
        "facts": [{"source_closet": "my_notes/Сны/Нет такого.txt"}],
        "page": 0,
    }
    monkeypatch.setattr(k, "_get_full_text_from_chroma", lambda src: "")
    edits = []

    async def edit_func(text, **kw):
        edits.append(text)

    ok = asyncio.run(k._kg_read_sources(4242, edit_func))
    assert ok is False
    assert edits == ["❌ Файлы из фактов не найдены в Дворце."]


def test_kg_read_sources_skip_missing_in_chroma(monkeypatch):
    """Файл без текста в Chroma пропускается, найденный — остаётся."""
    _enable(monkeypatch)
    k._kg_page_data[4242] = {
        "entity": "юнг",
        "facts": [
            {"source_closet": "my_notes/Сны/Нет.txt"},
            {"source_closet": "my_notes/Сны/Есть.txt"},
        ],
        "page": 0,
    }
    monkeypatch.setattr(
        k, "_get_full_text_from_chroma",
        lambda src: "текст есть" if "Есть" in src else "",
    )

    async def fake_send(*a, **kw):
        return None

    monkeypatch.setattr(k, "_send_kg_search_page", fake_send)
    ok = asyncio.run(k._kg_read_sources(4242, lambda *a, **kw: None))
    assert ok is True
    results = k._kg_search_data[4242]["results"]
    assert [r["source_file"] for r in results] == ["Есть.txt"]


def test_kg_read_sources_string_facts_ignored(monkeypatch):
    """Факт-строка (не dict) не ломает сбор источников."""
    _enable(monkeypatch)
    k._kg_page_data[4242] = {
        "entity": "юнг",
        "facts": ["простая строка", {"source_closet": "my_notes/Сны/Есть.txt"}],
        "page": 0,
    }
    monkeypatch.setattr(k, "_get_full_text_from_chroma", lambda src: "текст")

    async def fake_send(*a, **kw):
        return None

    monkeypatch.setattr(k, "_send_kg_search_page", fake_send)
    ok = asyncio.run(k._kg_read_sources(4242, lambda *a, **kw: None))
    assert ok is True
    assert [r["source_file"] for r in k._kg_search_data[4242]["results"]] == ["Есть.txt"]


# ---------- cb_kg_facts ----------


def test_cb_kg_facts(monkeypatch):
    _enable(monkeypatch)
    k._kg_page_data[4242] = {"entity": "юнг", "facts": [], "page": 0}
    called = []

    async def fake_send(uid, edit_func):
        called.append(uid)

    monkeypatch.setattr(k, "_send_kg_page", fake_send)
    cb = FakeCb(data="p_kgf")
    asyncio.run(k.cb_kg_facts(cb))
    assert called == [4242]


def test_cb_kg_facts_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_kgf")
    asyncio.run(k.cb_kg_facts(cb))
    assert cb.message.edits[-1][0] == "❌ Сессия истекла. Откройте заново."


# ---------- cb_kg_back_to_search / cb_kg_read_search ----------


def test_cb_kg_back_to_search(monkeypatch):
    _enable(monkeypatch)
    k._kg_search_data[4242] = {"entity": "Юнг", "results": [], "page": 0}
    called = []

    async def fake_send(uid, edit_func):
        called.append(uid)

    monkeypatch.setattr(k, "_send_kg_search_page", fake_send)
    cb = FakeCb(data="p_kgsr")
    asyncio.run(k.cb_kg_back_to_search(cb))
    assert called == [4242]


def test_cb_kg_back_to_search_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_kgsr")
    asyncio.run(k.cb_kg_back_to_search(cb))
    assert cb.message.edits[-1][0] == "❌ Сессия истекла. Откройте заново."


def test_cb_kg_read_search(monkeypatch):
    _enable(monkeypatch)
    shown = []

    async def fake_search(uid, edit_func, entity):
        shown.append((uid, entity))

    monkeypatch.setattr(k, "_kg_search_and_show", fake_search)
    cb = FakeCb(data="p_kgrs:Юнг")
    asyncio.run(k.cb_kg_read_search(cb))
    assert shown[0] == (4242, "Юнг")


# ---------- _kg_search_and_show ----------


def test_kg_search_and_show_success(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP(json.dumps({
        "query": "Юнг",
        "filters": {"wing": None, "room": None},
        "total_before_filter": 2,
        "results": [
            {"text": "текст", "source_file": "src.md"},
            {"text": "вторая запись", "source_file": "др.md"},
        ],
    }))
    monkeypatch.setattr(k, "get_mcp", lambda: mcp)
    called = []

    async def fake_send(uid, edit_func):
        called.append(uid)

    monkeypatch.setattr(k, "_send_kg_search_page", fake_send)
    edits = []

    async def edit_func(text, **kw):
        edits.append(text)

    asyncio.run(k._kg_search_and_show(4242, edit_func, "Юнг"))
    assert mcp.calls[0] == ("mempalace_search", {"query": "Юнг", "limit": 10})
    assert k._kg_search_data[4242] == {
        "entity": "Юнг", "results": [
            {"text": "текст", "source_file": "src.md"},
            {"text": "вторая запись", "source_file": "др.md"},
        ], "page": 0,
    }
    assert called == [4242]


def test_kg_search_and_show_legacy_list(monkeypatch):
    """Совместимость: старый движок мог возвращать плоский список."""
    _enable(monkeypatch)
    mcp = FakeMCP('[{"content": "текст", "source": "src.md"}, "простая запись"]')
    monkeypatch.setattr(k, "get_mcp", lambda: mcp)
    called = []

    async def fake_send(uid, edit_func):
        called.append(uid)

    monkeypatch.setattr(k, "_send_kg_search_page", fake_send)
    asyncio.run(k._kg_search_and_show(4242, lambda *a, **kw: None, "Юнг"))
    assert k._kg_search_data[4242] == {
        "entity": "Юнг", "results": [
            {"content": "текст", "source": "src.md"}, "простая запись",
        ], "page": 0,
    }
    assert called == [4242]


def test_kg_search_and_show_dict_no_results(monkeypatch):
    """Регрессия: движок возвращает dict с пустым results — не «ничего не найдено»."""
    _enable(monkeypatch)
    mcp = FakeMCP(json.dumps({"query": "Юнг", "results": []}))
    monkeypatch.setattr(k, "get_mcp", lambda: mcp)
    edits = []

    async def edit_func(text, **kw):
        edits.append(text)

    asyncio.run(k._kg_search_and_show(4242, edit_func, "Юнг"))
    assert edits == ["❌ По запросу «Юнг» ничего не найдено."]


def test_kg_search_and_show_dict_missing_results_key(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP(json.dumps({"error": "No palace found"}))
    monkeypatch.setattr(k, "get_mcp", lambda: mcp)
    edits = []

    async def edit_func(text, **kw):
        edits.append(text)

    asyncio.run(k._kg_search_and_show(4242, edit_func, "Юнг"))
    assert edits == ["❌ По запросу «Юнг» ничего не найдено."]


def test_kg_search_and_show_not_json(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP("не json вовсе")
    monkeypatch.setattr(k, "get_mcp", lambda: mcp)
    edits = []

    async def edit_func(text, **kw):
        edits.append(text)

    asyncio.run(k._kg_search_and_show(4242, edit_func, "Юнг"))
    assert edits == ["❌ По запросу «Юнг» ничего не найдено."]


def test_kg_search_and_show_no_results(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('[]')
    monkeypatch.setattr(k, "get_mcp", lambda: mcp)
    edits = []

    async def edit_func(text, **kw):
        edits.append(text)

    asyncio.run(k._kg_search_and_show(4242, edit_func, "Юнг"))
    assert edits == ["❌ По запросу «Юнг» ничего не найдено."]


def test_kg_search_and_show_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP(fail_on="mcp")
    monkeypatch.setattr(k, "get_mcp", lambda: mcp)
    edits = []

    async def edit_func(text, **kw):
        edits.append(text)

    asyncio.run(k._kg_search_and_show(4242, edit_func, "Юнг"))
    assert edits == ["❌ По запросу «Юнг» ничего не найдено."]


# ---------- _send_kg_search_page ----------


def test_send_kg_search_page_no_data(monkeypatch):
    edits = []

    async def edit_func(text, **kw):
        edits.append(text)

    asyncio.run(k._send_kg_search_page(4242, edit_func))
    assert edits == []


def test_send_kg_search_page_first(monkeypatch):
    _enable(monkeypatch)
    captured = _capture_finalize(monkeypatch)
    results = [
        {"content": "запись одна", "source": "a.md"},
        {"content": "запись два", "closet": "b.md"},
        {"content": "без источника"},
        "строка запись",
    ]
    k._kg_search_data[4242] = {"entity": "Юнг", "results": results, "page": 0}
    asyncio.run(k._send_kg_search_page(4242, lambda *a, **kw: None))
    assert "(4 всего)" in captured["text"]
    assert "запись одна" in captured["text"]
    assert "a.md" in captured["text"]
    assert "строка запись" in captured["text"]
    assert captured["extra_rows"][0][0].callback_data == "p_krd:0"
    assert captured["extra_rows"][0][1].callback_data == "p_krd:1"


def test_send_kg_search_page_second_page(monkeypatch):
    _enable(monkeypatch)
    captured = _capture_finalize(monkeypatch)
    results = [{"content": f"r{i}"} for i in range(8)]
    k._kg_search_data[4242] = {"entity": "Юнг", "results": results, "page": 1}
    asyncio.run(k._send_kg_search_page(4242, lambda *a, **kw: None))
    nav = captured["extra_rows"][0]
    data = [b.callback_data for b in nav]
    assert "p_krd:n" not in data
    assert "p_krd:p" in data


def test_send_kg_search_page_more_available(monkeypatch):
    _enable(monkeypatch)
    captured = _capture_finalize(monkeypatch)
    results = [{"content": f"r{i}"} for i in range(12)]
    k._kg_search_data[4242] = {"entity": "Юнг", "results": results, "page": 1}
    asyncio.run(k._send_kg_search_page(4242, lambda *a, **kw: None))
    nav = captured["extra_rows"][0]
    data = [b.callback_data for b in nav]
    assert "p_krd:n" in data
    assert "p_krd:p" in data


def test_send_kg_search_page_engine_keys(monkeypatch):
    """Рендер результатов в формате реального движка: text/source_file/wing/room."""
    _enable(monkeypatch)
    captured = _capture_finalize(monkeypatch)
    results = [{
        "text": "текст записи",
        "source_file": "эмиль_чоран.md",
        "wing": "my_notes",
        "room": "цитаты",
    }]
    k._kg_search_data[4242] = {"entity": "Юнг", "results": results, "page": 0}
    asyncio.run(k._send_kg_search_page(4242, lambda *a, **kw: None))
    assert "текст записи" in captured["text"]
    assert "эмиль_чоран.md" in captured["text"]
    assert captured["extra_rows"][0][0].callback_data == "p_krd:0"


def test_send_kg_search_page_kg_mode_back_to_facts(monkeypatch):
    """Регрессия: список записей графа должен вести «Вернуться к списку»
    на страницу фактов (p_kgf), а не в меню Графа Знаний."""
    _enable(monkeypatch)
    captured = _capture_finalize(monkeypatch)
    k._kg_search_data[4242] = {
        "entity": "юнг", "results": [{"text": "запись"}], "page": 0, "mode": "kg",
    }
    asyncio.run(k._send_kg_search_page(4242, lambda *a, **kw: None))
    assert "📚 Записи графа знаний" in captured["text"]
    assert captured["ctx"] == {"entity": "юнг", "parent_cb": "p_kgf"}


def test_send_kg_search_page_search_mode_back_to_menu(monkeypatch):
    """Глобальный поиск из заметок сохраняет «Вернуться к списку» → меню KG."""
    _enable(monkeypatch)
    captured = _capture_finalize(monkeypatch)
    k._kg_search_data[4242] = {"entity": "юнг", "results": [{"text": "запись"}], "page": 0}
    asyncio.run(k._send_kg_search_page(4242, lambda *a, **kw: None))
    assert "🔍 Результаты поиска" in captured["text"]
    assert captured["ctx"] == {"entity": "юнг", "parent_cb": "p_kg"}


def test_send_kg_search_page_empty_results(monkeypatch):
    _enable(monkeypatch)
    captured = _capture_finalize(monkeypatch)
    k._kg_search_data[4242] = {"entity": "Юнг", "results": [], "page": 0}
    asyncio.run(k._send_kg_search_page(4242, lambda *a, **kw: None))
    assert captured["extra_rows"] == []


def test_send_kg_search_page_last(monkeypatch):
    _enable(monkeypatch)
    captured = _capture_finalize(monkeypatch)
    results = [{"content": f"r{i}"} for i in range(7)]
    k._kg_search_data[4242] = {"entity": "Юнг", "results": results, "page": 1}
    asyncio.run(k._send_kg_search_page(4242, lambda *a, **kw: None))
    data = [b.callback_data for b in captured["extra_rows"][0]]
    assert "p_krd:n" not in data
    assert "p_krd:p" in data


# ---------- cb_kg_read_result ----------


def test_cb_kg_read_result_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_krd:0")
    asyncio.run(k.cb_kg_read_result(cb))
    assert cb.message.edits[-1][0] == "❌ Сессия истекла."


def test_cb_kg_read_result_next(monkeypatch):
    _enable(monkeypatch)
    k._kg_search_data[4242] = {"entity": "Юнг", "results": [], "page": 0}
    called = []

    async def fake_send(uid, edit_func):
        called.append(uid)

    monkeypatch.setattr(k, "_send_kg_search_page", fake_send)
    cb = FakeCb(data="p_krd:n")
    asyncio.run(k.cb_kg_read_result(cb))
    assert k._kg_search_data[4242]["page"] == 1
    assert called == [4242]


def test_cb_kg_read_result_prev(monkeypatch):
    _enable(monkeypatch)
    k._kg_search_data[4242] = {"entity": "Юнг", "results": [], "page": 1}
    called = []

    async def fake_send(uid, edit_func):
        called.append(uid)

    monkeypatch.setattr(k, "_send_kg_search_page", fake_send)
    cb = FakeCb(data="p_krd:p")
    asyncio.run(k.cb_kg_read_result(cb))
    assert k._kg_search_data[4242]["page"] == 0


def test_cb_kg_read_result_bad_param(monkeypatch):
    _enable(monkeypatch)
    k._kg_search_data[4242] = {"entity": "Юнг", "results": [], "page": 0}
    cb = FakeCb(data="p_krd:abc")
    asyncio.run(k.cb_kg_read_result(cb))
    assert cb.message.edits == []


def test_cb_kg_read_result_idx_out_of_range(monkeypatch):
    _enable(monkeypatch)
    k._kg_search_data[4242] = {"entity": "Юнг", "results": [{"content": "x"}], "page": 0}
    cb = FakeCb(data="p_krd:5")
    asyncio.run(k.cb_kg_read_result(cb))
    assert cb.message.edits == []


def test_cb_kg_read_result_success(monkeypatch):
    _enable(monkeypatch)
    captured = _capture_finalize_with_edit(monkeypatch)
    k._kg_search_data[4242] = {
        "entity": "Юнг",
        "results": [
            {"content": "текст записи", "source": "src.md", "wing": "крыло",
             "room": "комната"},
        ],
        "page": 0,
    }
    monkeypatch.setattr(k, "_get_full_text_from_chroma", lambda *a, **kw: "")
    cb = FakeCb(data="p_krd:0")
    asyncio.run(k.cb_kg_read_result(cb))
    assert captured["text"] == "текст записи"
    assert captured["ctx"] == {
        "wing": "крыло", "room": "комната", "drawer": "src.md",
        "parent_cb": "p_kgsr",
    }
    assert captured["title"] == "📄 src.md"
    assert k._read_state[4242] == {
        "room": "комната", "wing": "крыло", "drawer": "src.md", "source": "",
    }


def test_cb_kg_read_result_full_chroma(monkeypatch):
    _enable(monkeypatch)
    captured = _capture_finalize(monkeypatch)
    k._kg_search_data[4242] = {
        "entity": "Юнг",
        "results": [
            {"content": "короткий", "source": "src.md", "wing": "крыло",
             "room": "комната"},
        ],
        "page": 0,
    }
    monkeypatch.setattr(
        k, "_get_full_text_from_chroma",
        lambda *a, **kw: "длинный полный текст из хромы",
    )
    cb = FakeCb(data="p_krd:0")
    asyncio.run(k.cb_kg_read_result(cb))
    assert captured["text"] == "длинный полный текст из хромы"
    assert k._read_state[4242]["source"] == "длинный полный текст из хромы"


def test_cb_kg_read_result_string_result(monkeypatch):
    _enable(monkeypatch)
    captured = _capture_finalize_with_edit(monkeypatch)
    k._kg_search_data[4242] = {"entity": "Юнг", "results": ["строка"], "page": 0}
    cb = FakeCb(data="p_krd:0")
    asyncio.run(k.cb_kg_read_result(cb))
    assert captured["text"] == "строка"
    assert captured["ctx"]["wing"] == ""


def test_cb_kg_read_result_empty(monkeypatch):
    _enable(monkeypatch)
    captured = _capture_finalize_with_edit(monkeypatch)
    k._kg_search_data[4242] = {
        "entity": "Юнг", "results": [{"content": ""}], "page": 0,
    }
    cb = FakeCb(data="p_krd:0")
    asyncio.run(k.cb_kg_read_result(cb))
    assert captured["text"] == "📄 (пустая запись)"


# ---------- cb_kg_read_back ----------


def test_cb_kg_read_back_full(monkeypatch):
    _enable(monkeypatch)
    captured = _capture_finalize_with_edit(monkeypatch)
    k._read_state[4242] = {
        "room": "r", "wing": "w", "drawer": "d", "source": "полный текст",
    }
    cb = FakeCb(data="p_krb:f")
    asyncio.run(k.cb_kg_read_back(cb))
    assert captured["text"] == "полный текст"
    assert captured["is_html"] is False
    assert captured["title"] == "📄 <b>Полный текст источника</b>"


def test_cb_kg_read_back_full_no_source(monkeypatch):
    _enable(monkeypatch)
    k._read_state[4242] = {
        "room": "r", "wing": "w", "drawer": "d", "source": "",
    }
    cb = FakeCb(data="p_krb:f")
    asyncio.run(k.cb_kg_read_back(cb))
    assert cb.message.edits[-1][0] == "📖 Конец записи."


def test_cb_kg_read_back_no_state(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_krb:f")
    asyncio.run(k.cb_kg_read_back(cb))
    assert cb.message.edits[-1][0] == "📖 Конец записи."


def test_cb_kg_read_back_other(monkeypatch):
    _enable(monkeypatch)
    k._read_state[4242] = {"source": "текст"}
    cb = FakeCb(data="p_krb:x")
    asyncio.run(k.cb_kg_read_back(cb))
    assert cb.message.edits[-1][0] == "📖 Конец записи."


# ---------- not allowed ----------


@pytest.mark.parametrize(
    "data",
    ["p_kg", "p_kg_help", "p_kgst", "p_kga", "p_kga_x", "p_kga_s",
     "p_kga_p", "p_kga_pr:wrote", "p_kga_o", "p_kga_c", "p_kgq",
     "p_kgc", "p_kgs", "p_kgr", "p_kgf", "p_kgsr", "p_kgrs:Юнг", "p_krd:0",
     "p_krb:f"],
)
def test_callbacks_not_allowed(monkeypatch, data):
    _enable(monkeypatch)
    cb = FakeCb(uid=999, data=data)
    asyncio.run(_dispatch(cb))
    assert cb.answered == [("❌ Нет доступа", True)]


async def _dispatch(cb):
    d = cb.data
    if d.startswith("p_kga_pr:"):
        await k.cb_kg_add_predicate_chosen(cb)
    elif d.startswith("p_kga_c"):
        await k.cb_kg_add_confirm(cb)
    elif d.startswith("p_kgrs:"):
        await k.cb_kg_read_search(cb)
    elif d.startswith("p_krd:"):
        await k.cb_kg_read_result(cb)
    elif d.startswith("p_krb:"):
        await k.cb_kg_read_back(cb)
    else:
        mapping = {
            "p_kg": k.cb_kg_menu,
            "p_kg_help": k.cb_kg_help,
            "p_kgst": k.cb_kg_stats,
            "p_kga": k.cb_kg_add_start,
            "p_kga_x": k.cb_kg_add_cancel,
            "p_kga_s": k.cb_kg_add_subject_prompt,
            "p_kga_p": k.cb_kg_add_predicate_menu,
            "p_kga_o": k.cb_kg_add_object_prompt,
            "p_kgq": k.cb_kg_query_prompt,
            "p_kgc": k.cb_kg_continue,
            "p_kgs": k.cb_kg_restart,
            "p_kgr": k.cb_kg_read,
            "p_kgf": k.cb_kg_facts,
            "p_kgsr": k.cb_kg_back_to_search,
        }
        await mapping[d](cb)
