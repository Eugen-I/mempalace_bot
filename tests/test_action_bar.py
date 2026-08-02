"""Тесты action_bar.py — пагинация, рендер, store, колбэки.

Покрытие шагов 1–2 ТЗ: чистые функции + колбэки с mocked bot.
"""
import asyncio

import pytest

from handlers.palace.action_bar import (
    PAGE_LIMIT,
    Answer,
    _find_cut,
    _render_page,
    answer_store,
    build_action_bar,
    get_answer,
    paginate,
)

SID = "a1b2c3d4"

TEST_UID = 424242


@pytest.fixture(autouse=True)
def _allow_test_user(monkeypatch):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {TEST_UID})
    yield
    answer_store.clear()


# ─── _find_cut: границы ───


def test_find_cut_paragraph_boundary():
    text = "a" * 900 + "\n\n" + "b" * 900
    cut = _find_cut(text, 1500)
    assert cut == 902
    assert text[:cut] == "a" * 900 + "\n\n"


def test_find_cut_single_newline_fallback():
    text = "a" * 900 + "\n" + "b" * 900
    cut = _find_cut(text, 1500)
    assert cut == 901
    assert text[:cut] == "a" * 900 + "\n"


def test_find_cut_space_fallback():
    text = "a" * 900 + " " + "b" * 900
    cut = _find_cut(text, 1500)
    assert cut == 901


def test_find_cut_hard_cut_no_boundary():
    text = "x" * 1500
    assert _find_cut(text, 1500) == 1500


def test_find_cut_does_not_cut_too_early():
    text = "a" * 100 + "\n" + "b" * 1400
    cut = _find_cut(text, 1500)
    assert cut == 1500


# ─── paginate: BVA границы ───


def test_paginate_empty_text():
    assert paginate("") == [""]


def test_paginate_single_page_below_limit():
    text = "слово" * 200  # 800 символов
    assert paginate(text) == [text]


def test_paginate_exactly_at_limit():
    text = "а" * PAGE_LIMIT
    assert paginate(text) == [text]


def test_paginate_one_over_limit_no_boundaries():
    text = "x" * (PAGE_LIMIT + 1)
    pages = paginate(text)
    assert len(pages) == 2
    assert len(pages[0]) == PAGE_LIMIT
    assert pages[1] == "x"


def test_paginate_multiple_pages_with_boundaries():
    text = ("ab" * 500 + "\n\n") * 2 + "cd" * 500
    pages = paginate(text, limit=PAGE_LIMIT)
    assert len(pages) >= 2
    assert all(p.strip() for p in pages)
    joined = "".join(pages)
    assert joined.replace("\n", "") == text.replace("\n", "")


def test_paginate_reassembles_full_text():
    paragraphs = [("word " * 300).strip() for _ in range(4)]
    text = "\n\n".join(paragraphs)
    pages = paginate(text)
    joined = "".join(pages)
    assert joined.replace("\n\n", "") == text.replace("\n\n", "")


def test_paginate_near_limit_1499():
    text = "а" * 1499
    assert paginate(text) == [text]


def test_paginate_over_limit_1501():
    text = "а" * 1501
    pages = paginate(text)
    assert len(pages) == 2


# ─── Answer / _render_page ───


def test_render_page_escapes_raw_text():
    answer = Answer(sid=SID, text="<b>не html</b>", pages=["<b>не html</b>"])
    rendered = _render_page(answer, 0)
    assert "&lt;b&gt;" in rendered
    assert "<b>не html</b>" not in rendered


def test_render_page_html_mode_keeps_tags():
    answer = Answer(sid=SID, text="<b>html</b>", pages=["<b>html</b>"], is_html=True)
    assert _render_page(answer, 0) == "<b>html</b>"


def test_render_page_title_only_on_first_page():
    answer = Answer(sid=SID, text="текст", pages=["текст"], title="<b>Заголовок</b>")
    first = _render_page(answer, 0)
    second = _render_page(answer, 1) if len(answer.pages) > 1 else None
    assert first.startswith("<b>Заголовок</b>")
    assert second is None


def test_render_page_title_not_repeated():
    answer = Answer(
        sid=SID, text="а" * 3000,
        pages=["а" * 1500, "а" * 1500],
        title="<b>Заголовок</b>",
    )
    page1 = _render_page(answer, 1)
    assert not page1.startswith("<b>Заголовок</b>")


# ─── build_action_bar ───


def _button_labels(answer, idx=0):
    kb = build_action_bar(answer, idx)
    return [b.text for row in kb.export() for b in row]


def _button_data(answer, idx=0):
    kb = build_action_bar(answer, idx)
    return [b.callback_data for row in kb.export() for b in row]


def test_action_bar_base_buttons():
    answer = Answer(sid=SID, text="короткий", pages=["короткий"], ctx={"parent_cb": "p_rdb"})
    labels = _button_labels(answer)
    assert "🤖 Анализ ИИ" in labels
    assert "🌐 Поиск в интернете" in labels
    assert "💾 Сохранить" in labels


def test_action_bar_no_pagination_short_text():
    answer = Answer(sid=SID, text="короткий", pages=["короткий"])
    data = _button_data(answer)
    assert not any("ab_pg:" in d for d in data)


def test_action_bar_pagination_buttons():
    answer = Answer(sid=SID, text="а" * 3000, pages=["а" * 1500, "а" * 1500])
    data = _button_data(answer, 0)
    assert "ab_pg:%s:1" % SID in data
    assert "📄 1/2" in _button_labels(answer, 0)
    assert "ab_pg_noop" in data


def test_action_bar_pagination_middle_page():
    answer = Answer(sid=SID, text="а" * 4500, pages=["а" * 1500] * 3)
    data = _button_data(answer, 1)
    assert "ab_pg:%s:0" % SID in data
    assert "ab_pg:%s:2" % SID in data
    labels = _button_labels(answer, 1)
    assert "📄 2/3" in labels


def test_action_bar_last_page_no_next():
    answer = Answer(sid=SID, text="а" * 4500, pages=["а" * 1500] * 3)
    data = _button_data(answer, 2)
    assert not any(d == "ab_pg:%s:3" % SID for d in data)
    assert "ab_pg:%s:1" % SID in data


def test_action_bar_back_button_only_with_parent():
    with_parent = Answer(sid=SID, text="т", pages=["т"], ctx={"parent_cb": "p_rdb"})
    assert any("ab_back:" in d for d in _button_data(with_parent))
    without_parent = Answer(sid=SID, text="т", pages=["т"])
    assert not any("ab_back:" in d for d in _button_data(without_parent))


# ─── store ───


def test_answer_store_roundtrip():
    answer = Answer(sid=SID, text="текст", pages=["текст"])
    answer_store[SID] = answer
    assert get_answer(SID) is answer
    assert get_answer("missing") is None


def test_answer_store_get_unknown_returns_none():
    assert get_answer("zzzz") is None


# ─── колбэки (mocked) ───


class FakeMessage:
    def __init__(self):
        self.edited = []
        self.markups = []

    async def edit_text(self, text, **kwargs):
        self.edited.append(text)
        self.markups.append(kwargs.get("reply_markup"))
        return self

    async def answer(self, text=None, **kwargs):
        self.edited.append(text or "")
        self.markups.append(kwargs.get("reply_markup"))
        return self


def _markup_data(msg, idx=-1):
    kb = msg.markups[idx]
    if kb is None:
        return []
    return [b.callback_data for row in kb.inline_keyboard for b in row]


class FakeCallback:
    def __init__(self, data, msg=None):
        self.data = data
        self.message = msg or FakeMessage()
        self.answered = None
        self.from_user = type("U", (), {"id": TEST_UID})()

    async def answer(self, text=None, **kwargs):
        self.answered = (text, kwargs)


async def run(coro):
    return await coro


def test_cb_ab_page_switches_content():
    from handlers.palace.action_bar import cb_ab_page

    answer = Answer(sid=SID, text="а" * 3000, pages=["стр1", "стр2"])
    answer_store[SID] = answer
    msg = FakeMessage()
    cb = FakeCallback(f"ab_pg:{SID}:1", msg)
    asyncio.run(cb_ab_page(cb))
    assert "стр2" in msg.edited[-1]
    assert answer.page == 1


def test_cb_ab_page_unknown_sid():
    from handlers.palace.action_bar import cb_ab_page

    msg = FakeMessage()
    cb = FakeCallback("ab_pg:unknown:1", msg)
    asyncio.run(cb_ab_page(cb))
    assert cb.answered and "Сессия истекла" in cb.answered[0]


def test_cb_ab_back_unknown_sid():
    from handlers.palace.action_bar import cb_ab_back

    cb = FakeCallback("ab_back:unknown")
    asyncio.run(cb_ab_back(cb))
    assert cb.answered and "Сессия истекла" in cb.answered[0]


def test_cb_ab_ai_unknown_sid():
    from handlers.palace.action_bar import cb_ab_ai

    cb = FakeCallback("ab_ai:unknown")
    asyncio.run(cb_ab_ai(cb))
    assert cb.answered and "Сессия истекла" in cb.answered[0]


def test_cb_ab_web_unknown_sid():
    from handlers.palace.action_bar import cb_ab_web

    cb = FakeCallback("ab_web:unknown")
    asyncio.run(cb_ab_web(cb))
    assert cb.answered and "Сессия истекла" in cb.answered[0]


def test_cb_ab_sv_unknown_sid():
    from handlers.palace.action_bar import cb_ab_sv

    cb = FakeCallback("ab_sv:unknown")
    asyncio.run(cb_ab_sv(cb))
    assert cb.answered and "Сессия истекла" in cb.answered[0]


def test_finalize_answer_stores_and_renders(monkeypatch):
    import handlers.palace.action_bar as ab

    msg = FakeMessage()

    async def edit_func(text, **kwargs):
        msg.edited.append(text)
        return msg

    answer = asyncio.run(ab.finalize_answer(
        1, edit_func, "простой текст", ctx={"parent_cb": "p_nav"},
    ))
    assert answer is not None
    assert get_answer(answer.sid) is answer
    assert "простой текст" in msg.edited[-1]


def test_finalize_answer_error_returns_none(monkeypatch):
    import handlers.palace.action_bar as ab

    async def bad_edit(text, **kwargs):
        raise RuntimeError("fail")

    answer = asyncio.run(ab.finalize_answer(1, bad_edit, "текст"))
    assert answer is None


def test_finalize_answer_error_logs_exact_message(caplog):
    import handlers.palace.action_bar as ab

    async def bad_edit(text, **kwargs):
        raise RuntimeError("boom")

    with caplog.at_level("ERROR", logger="handlers.palace.action_bar"):
        asyncio.run(ab.finalize_answer(1, bad_edit, "текст"))
    record = caplog.records[-1]
    assert record.getMessage() == "[ACTION_BAR] finalize_answer error: boom"
    assert record.exc_info


def test_finalize_answer_default_title_and_html():
    import handlers.palace.action_bar as ab

    msg = FakeMessage()

    async def edit_func(text, **kwargs):
        msg.edited.append(text)
        return msg

    answer = asyncio.run(ab.finalize_answer(1, edit_func, "текст"))
    assert answer.title == ""
    assert answer.is_html is False


def test_finalize_answer_pages_by_page_limit():
    import handlers.palace.action_bar as ab

    msg = FakeMessage()

    async def edit_func(text, **kwargs):
        msg.edited.append(text)
        return msg

    answer = asyncio.run(ab.finalize_answer(1, edit_func, "т" * 1600, is_html=True))
    assert len(answer.pages) == 2


def test_finalize_answer_empty_text_renders_empty():
    import handlers.palace.action_bar as ab

    msg = FakeMessage()

    async def edit_func(text, **kwargs):
        msg.edited.append(text)
        return msg

    asyncio.run(ab.finalize_answer(1, edit_func, ""))
    assert msg.edited[-1] == ""


def test_finalize_answer_parse_mode_html_for_plain_text():
    import handlers.palace.action_bar as ab

    captured = {}

    async def edit_func(text, **kwargs):
        captured["parse_mode"] = kwargs.get("parse_mode")
        return FakeMessage()

    asyncio.run(ab.finalize_answer(1, edit_func, "текст"))
    assert captured["parse_mode"] == "HTML"


# ─── 🤖 Анализ ИИ ───


def test_cb_ab_ai_shows_mode_submenu():
    from handlers.palace.action_bar import cb_ab_ai

    answer = Answer(sid=SID, text="текст", pages=["текст"])
    answer_store[SID] = answer
    msg = FakeMessage()
    cb = FakeCallback(f"ab_ai:{SID}", msg)
    asyncio.run(cb_ab_ai(cb))
    assert "Режим анализа" in msg.edited[-1]
    data = _markup_data(msg)
    assert f"ab_ai_m:a:{SID}" in data
    assert f"ab_ai_m:c:{SID}" in data


def test_cb_ab_ai_run_mode_answer(monkeypatch):
    import handlers.palace.action_bar as ab

    monkeypatch.setattr(ab, "get_current_ai", lambda: ("gemini", "m"))
    monkeypatch.setattr(ab, "_sync_ai_call", lambda *a, **k: "Анализ готов")

    answer = Answer(sid=SID, text="текст", pages=["текст"])
    answer_store[SID] = answer
    msg = FakeMessage()
    cb = FakeCallback(f"ab_ai_m:a:{SID}", msg)
    asyncio.run(ab.cb_ab_ai_run(cb))
    assert "Анализ готов" in msg.edited[-1]


def test_cb_ab_ai_run_mode_context_with_summary(monkeypatch):
    import handlers.palace.action_bar as ab

    monkeypatch.setattr(ab, "get_current_ai", lambda: ("gemini", "m"))
    monkeypatch.setattr(ab, "_sync_ai_call", lambda *a, **k: "Контекстный анализ")

    answer = Answer(
        sid=SID, text="текст", pages=["текст"],
        ctx={"wing": "w1", "room": "r1"},
    )
    answer_store[SID] = answer

    from handlers.palace import shared

    monkeypatch.setattr(shared, "_user_context", {TEST_UID: {"_room_summary": "саммари"}})

    msg = FakeMessage()
    cb = FakeCallback(f"ab_ai_m:c:{SID}", msg)
    asyncio.run(ab.cb_ab_ai_run(cb))
    assert "Контекстный анализ" in msg.edited[-1]


def test_cb_ab_ai_run_error(monkeypatch):
    import handlers.palace.action_bar as ab

    def boom(*a, **k):
        raise RuntimeError("AI fail")

    monkeypatch.setattr(ab, "get_current_ai", boom)

    answer = Answer(sid=SID, text="текст", pages=["текст"])
    answer_store[SID] = answer
    msg = FakeMessage()
    cb = FakeCallback(f"ab_ai_m:a:{SID}", msg)
    asyncio.run(ab.cb_ab_ai_run(cb))
    assert "Ошибка" in msg.edited[-1]


# ─── 🌐 Поиск ───


def test_cb_ab_web_generates_query(monkeypatch):
    import handlers.palace.action_bar as ab

    monkeypatch.setattr(ab, "get_current_ai", lambda: ("gemini", "m"))
    monkeypatch.setattr(ab, "_sync_ai_call", lambda *a, **k: '"тестовый запрос"')

    answer = Answer(sid=SID, text="текст", pages=["текст"])
    answer_store[SID] = answer
    msg = FakeMessage()
    cb = FakeCallback(f"ab_web:{SID}", msg)
    asyncio.run(ab.cb_ab_web(cb))
    assert "тестовый запрос" in msg.edited[-1]
    assert answer.ctx["web_query"] == "тестовый запрос"


def test_cb_ab_web_empty_query_error(monkeypatch):
    import handlers.palace.action_bar as ab

    monkeypatch.setattr(ab, "get_current_ai", lambda: ("gemini", "m"))
    monkeypatch.setattr(ab, "_sync_ai_call", lambda *a, **k: "   ")

    answer = Answer(sid=SID, text="текст", pages=["текст"])
    answer_store[SID] = answer
    msg = FakeMessage()
    cb = FakeCallback(f"ab_web:{SID}", msg)
    asyncio.run(ab.cb_ab_web(cb))
    assert "Ошибка" in msg.edited[-1]


def test_cb_ab_web_go_runs_search(monkeypatch):
    import handlers.palace.action_bar as ab
    from services import web_search

    async def fake_search(q):
        return "результаты поиска"

    monkeypatch.setattr(web_search, "search_web", fake_search)
    monkeypatch.setattr(ab, "get_current_ai", lambda: ("gemini", "m"))
    monkeypatch.setattr(ab, "_sync_ai_call", lambda *a, **k: "Ответ с поиском")

    answer = Answer(sid=SID, text="текст", pages=["текст"], ctx={})
    answer.ctx["web_query"] = "запрос"
    answer_store[SID] = answer
    msg = FakeMessage()
    cb = FakeCallback(f"ab_web_go:{SID}", msg)
    asyncio.run(ab.cb_ab_web_go(cb))
    assert "Ответ с поиском" in msg.edited[-1]


def test_cb_ab_web_go_no_query():
    from handlers.palace.action_bar import cb_ab_web_go

    answer = Answer(sid=SID, text="текст", pages=["текст"])
    answer_store[SID] = answer
    cb = FakeCallback(f"ab_web_go:{SID}")
    asyncio.run(cb_ab_web_go(cb))
    assert cb.answered and "Нет запроса" in cb.answered[0]


def test_cb_ab_web_edit_sets_pending(monkeypatch):
    import handlers.palace.action_bar as ab
    from handlers.palace import shared

    monkeypatch.setattr(shared, "_pending_mcp_input", {})

    answer = Answer(sid=SID, text="текст", pages=["текст"])
    answer_store[SID] = answer
    msg = FakeMessage()
    cb = FakeCallback(f"ab_web_edit:{SID}", msg)
    asyncio.run(ab.cb_ab_web_edit(cb))
    assert shared._pending_mcp_input.get(TEST_UID) == f"ab_web_query:{SID}"
    assert "Введите свой запрос" in msg.edited[-1]


def test_run_web_search_with_query(monkeypatch):
    import handlers.palace.action_bar as ab
    from services import web_search

    async def fake_search(q):
        return "web"

    monkeypatch.setattr(web_search, "search_web", fake_search)
    monkeypatch.setattr(ab, "get_current_ai", lambda: ("gemini", "m"))
    monkeypatch.setattr(ab, "_sync_ai_call", lambda *a, **k: "Поиск с ручным запросом")

    answer = Answer(sid=SID, text="текст", pages=["текст"])
    answer_store[SID] = answer
    msg = FakeMessage()
    asyncio.run(ab.run_web_search_with_query(1, msg, SID, "  мой запрос  "))
    assert answer.ctx["web_query"] == "мой запрос"
    assert "Поиск с ручным запросом" in msg.edited[-1]


def test_run_web_search_with_query_expired():
    import handlers.palace.action_bar as ab

    msg = FakeMessage()
    asyncio.run(ab.run_web_search_with_query(1, msg, "unknown", "запрос"))
    assert "истекла" in msg.edited[-1]


def test_run_web_search_title_truncated_to_80(monkeypatch):
    import handlers.palace.action_bar as ab
    from services import web_search

    async def fake_search(q):
        return "web"

    monkeypatch.setattr(web_search, "search_web", fake_search)
    monkeypatch.setattr(ab, "get_current_ai", lambda: ("gemini", "m"))
    monkeypatch.setattr(ab, "_sync_ai_call", lambda *a, **k: "Ответ")

    answer = Answer(sid=SID, text="текст", pages=["текст"])
    answer_store[SID] = answer
    msg = FakeMessage()
    asyncio.run(ab.run_web_search_with_query(1, msg, SID, "q" * 81))
    assert msg.edited[-1].count("q") == 80


# ─── 💾 Сохранить ───


def test_cb_ab_sv_shows_submenu():
    from handlers.palace.action_bar import cb_ab_sv

    answer = Answer(sid=SID, text="текст", pages=["текст"])
    answer_store[SID] = answer
    msg = FakeMessage()
    cb = FakeCallback(f"ab_sv:{SID}", msg)
    asyncio.run(cb_ab_sv(cb))
    assert "Куда сохранить" in msg.edited[-1]
    data = _markup_data(msg)
    assert f"ab_sv_p:{SID}" in data
    assert f"ab_sv_n:{SID}" in data


def test_cb_ab_sv_palace_starts_wizard(monkeypatch):
    import handlers.palace.action_bar as ab
    from handlers.palace import save as save_mod

    called = {}

    async def fake_wings(edit_func, uid):
        called["uid"] = uid
        await edit_func("крылья")

    monkeypatch.setattr(save_mod, "_show_save_wings", fake_wings)

    answer = Answer(sid=SID, text="текст", pages=["текст"])
    answer_store[SID] = answer
    msg = FakeMessage()
    cb = FakeCallback(f"ab_sv_p:{SID}", msg)
    asyncio.run(ab.cb_ab_sv_palace(cb))
    assert called["uid"] == TEST_UID
    assert "крылья" in msg.edited[-1]


def test_cb_ab_sv_notes_writes_file(tmp_path, monkeypatch):
    import handlers.palace.action_bar as ab

    monkeypatch.setattr(ab, "NOTES_DIR", str(tmp_path))

    answer = Answer(sid=SID, text="сохраняемый текст", pages=["сохраняемый текст"])
    answer_store[SID] = answer
    msg = FakeMessage()
    cb = FakeCallback(f"ab_sv_n:{SID}", msg)
    asyncio.run(ab.cb_ab_sv_notes(cb))
    files = list(tmp_path.glob("notes_*.md"))
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8") == "сохраняемый текст"
    assert "Сохранено" in msg.edited[-1]


def test_cb_ab_sv_notes_error(tmp_path, monkeypatch):
    import builtins

    import handlers.palace.action_bar as ab

    def bad_open(*a, **k):
        raise PermissionError("no write")

    monkeypatch.setattr(ab, "NOTES_DIR", str(tmp_path))
    monkeypatch.setattr(builtins, "open", bad_open)

    answer = Answer(sid=SID, text="текст", pages=["текст"])
    answer_store[SID] = answer
    msg = FakeMessage()
    cb = FakeCallback(f"ab_sv_n:{SID}", msg)
    asyncio.run(ab.cb_ab_sv_notes(cb))
    assert "Ошибка" in msg.edited[-1]


# ─── 🔙 Возврат ───


def test_cb_ab_back_dispatches_parent(monkeypatch):
    import handlers.palace.action_bar as ab

    dispatched = []

    async def fake_dispatch(cb, parent):
        dispatched.append(parent)
        return True

    monkeypatch.setattr(ab, "_dispatch_parent", fake_dispatch)

    answer = Answer(
        sid=SID, text="текст", pages=["текст"],
        ctx={"parent_cb": "p_rdb"},
    )
    answer_store[SID] = answer
    cb = FakeCallback(f"ab_back:{SID}")
    asyncio.run(ab.cb_ab_back(cb))
    assert dispatched == ["p_rdb"]


def test_cb_ab_back_no_parent():
    from handlers.palace.action_bar import cb_ab_back

    answer = Answer(sid=SID, text="текст", pages=["текст"])
    answer_store[SID] = answer
    cb = FakeCallback(f"ab_back:{SID}")
    asyncio.run(cb_ab_back(cb))
    assert cb.answered and "Нет родительского" in cb.answered[0]


def test_get_parent_handler_known_and_unknown():
    import handlers.palace.action_bar as ab

    assert ab._get_parent_handler("p_rdb") is not None
    assert ab._get_parent_handler("p_nav") is not None
    assert ab._get_parent_handler("nonexistent") is None


def test_dispatch_parent_unknown_returns_false(monkeypatch):
    import handlers.palace.action_bar as ab

    assert asyncio.run(ab._dispatch_parent(None, "nope")) is False


# ─── _build_ai_context ───


def test_build_ai_context_no_wing_room():
    import handlers.palace.action_bar as ab

    answer = Answer(sid=SID, text="т", pages=["т"], ctx={})
    assert asyncio.run(ab._build_ai_context(answer, 1)) == ""


def test_build_ai_context_uses_cached_summary(monkeypatch):
    import handlers.palace.action_bar as ab
    from handlers.palace import shared

    monkeypatch.setattr(shared, "_user_context", {1: {"_room_summary": "САММАРИ"}})

    answer = Answer(sid=SID, text="т", pages=["т"], ctx={"wing": "w", "room": "r"})
    result = asyncio.run(ab._build_ai_context(answer, 1))
    assert "САММАРИ" in result


def test_build_ai_context_mcp_fetch(monkeypatch):
    import handlers.palace.action_bar as ab
    from handlers.palace import shared
    from services import palace_mcp

    class FakeMCP:
        async def call_tool(self, name, args=None):
            return '{"drawers": [{"closet_name": "Запись", "content_preview": "превью"}]}'

    monkeypatch.setattr(shared, "_user_context", {})
    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: FakeMCP())

    answer = Answer(sid=SID, text="т", pages=["т"], ctx={"wing": "w", "room": "r"})
    result = asyncio.run(ab._build_ai_context(answer, 1))
    assert "Запись" in result


def test_build_ai_context_mcp_empty(monkeypatch):
    import handlers.palace.action_bar as ab
    from handlers.palace import shared
    from services import palace_mcp

    class FakeMCP:
        async def call_tool(self, name, args=None):
            return '{"drawers": []}'

    monkeypatch.setattr(shared, "_user_context", {})
    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: FakeMCP())

    answer = Answer(sid=SID, text="т", pages=["т"], ctx={"wing": "w", "room": "r"})
    assert asyncio.run(ab._build_ai_context(answer, 1)) == ""


# ─── Шаг 3–5: интеграция (extra_rows, navigation, parent) ───


def test_finalize_answer_extra_rows_rendered_and_kept_on_page_flip():
    import handlers.palace.action_bar as ab
    from aiogram import types

    msg = FakeMessage()
    extra = [
        [types.InlineKeyboardButton(text="📄 Запись 1", callback_data="p_rd:0")],
        [types.InlineKeyboardButton(text="◀️ Пред.", callback_data="p_rdp:0")],
    ]

    async def edit_func(text, **kwargs):
        msg.edited.append(text)
        msg.markups.append(kwargs.get("reply_markup"))
        return msg

    answer = asyncio.run(ab.finalize_answer(
        TEST_UID, edit_func, "а" * 3200,
        ctx={"parent_cb": "p_rdb"}, extra_rows=extra,
    ))
    assert answer is not None
    data0 = _markup_data(msg, 0)
    assert "p_rd:0" in data0
    assert "p_rdp:0" in data0
    assert "ab_ai:%s" % answer.sid in data0

    page_msg = FakeMessage()
    cb = FakeCallback("ab_pg:%s:1" % answer.sid, page_msg)
    asyncio.run(ab.cb_ab_page(cb))
    page_data = _markup_data(page_msg)
    assert "p_rd:0" in page_data
    assert "p_rdp:0" in page_data


def test_show_drawers_page_integration(monkeypatch):
    from handlers.palace import navigation

    class FakeMCP:
        async def call_tool(self, name, args=None):
            return (
                '{"drawers": [{"closet_name": "Запись 1", "content_preview": "пр1"},'
                '{"closet_name": "Запись 2", "content_preview": "пр2"}], "count": 7}'
            )

    monkeypatch.setattr(navigation, "_drawer_list_state", {TEST_UID: {}})
    monkeypatch.setattr(navigation, "get_mcp", lambda: FakeMCP())

    msg = FakeMessage()
    asyncio.run(navigation._show_drawers_page(
        msg.edit_text, TEST_UID, "dreams", "r1", 0,
    ))
    assert "Записи в dreams/r1" in msg.edited[-1]
    data = _markup_data(msg)
    assert "p_rd:0" in data
    assert "p_rd:1" in data
    assert "p_room_ai" in data
    assert any(d.startswith("ab_ai:") for d in data)
    assert "p_rdp:5" in data


def test_cb_read_drawer_long_content_paginates(monkeypatch):
    import handlers.palace.action_bar as ab
    from handlers.palace import navigation

    long_text = ("абвгд " * 400)  # 2400 символов -> 2 страницы по 1500

    class FakeMCP:
        async def call_tool(self, name, args=None):
            return '{"content": "%s"}' % long_text

    monkeypatch.setattr(navigation, "_drawer_list_state", {
        TEST_UID: {
            "wing": "w1", "room": "r1", "offset": 0,
            "drawers": [{"closet_name": "Длинная", "drawer_id": "d1"}],
        },
    })
    monkeypatch.setattr(navigation, "get_mcp", lambda: FakeMCP())

    msg = FakeMessage()
    cb = FakeCallback("p_rd:0", msg)
    asyncio.run(navigation.cb_read_drawer(cb))
    assert len(msg.edited) == 1
    assert "Длинная" in msg.edited[-1]
    data = _markup_data(msg)
    assert any(d.startswith("ab_pg:") for d in data)
    assert "ab_back" in "".join(data)
    answer = ab.get_answer([d for d in data if d.startswith("ab_ai:")][0][6:])
    assert answer is not None
    assert answer.total_pages == 2


def test_cb_read_drawer_short_content_no_pagination(monkeypatch):
    from handlers.palace import navigation

    class FakeMCP:
        async def call_tool(self, name, args=None):
            return '{"content": "короткий текст"}'

    monkeypatch.setattr(navigation, "_drawer_list_state", {
        TEST_UID: {
            "wing": "w1", "room": "r1", "offset": 0,
            "drawers": [{"closet_name": "Короткая", "drawer_id": "d1"}],
        },
    })
    monkeypatch.setattr(navigation, "get_mcp", lambda: FakeMCP())

    msg = FakeMessage()
    cb = FakeCallback("p_rd:0", msg)
    asyncio.run(navigation.cb_read_drawer(cb))
    data = _markup_data(msg)
    assert not any(d.startswith("ab_pg:") for d in data)


def test_parent_handler_tunnels_menu_and_kg_search():
    import handlers.palace.action_bar as ab

    assert ab._get_parent_handler("p_tun") is not None
    assert ab._get_parent_handler("p_kgsr") is not None


def test_dispatch_parent_calls_real_handler(monkeypatch):
    import handlers.palace.action_bar as ab
    from handlers.palace import navigation

    called = []

    async def fake_menu(cb):
        called.append(cb)

    monkeypatch.setattr(navigation, "cb_tunnels_menu", fake_menu)

    cb = FakeCallback("ab_back:x")
    assert asyncio.run(ab._dispatch_parent(cb, "p_tun")) is True
    assert called == [cb]


# ─── Добивание выживших мутантов (мутационное тестирование) ───


# _build_ai_context: MCP-ветка и границы


def test_build_ai_context_missing_wing_or_room(monkeypatch):
    import handlers.palace.action_bar as ab
    from services import palace_mcp

    class FakeMCP:
        async def call_tool(self, name, args=None):
            return '{"drawers": []}'

    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: FakeMCP())
    answer = Answer(sid=SID, text="т", pages=["т"], ctx={"wing": "w1"})
    assert asyncio.run(ab._build_ai_context(answer, 1)) == ""
    answer = Answer(sid=SID, text="т", pages=["т"], ctx={"room": "r1"})
    assert asyncio.run(ab._build_ai_context(answer, 1)) == ""


def test_build_ai_context_mcp_args_exact(monkeypatch):
    import handlers.palace.action_bar as ab
    from services import palace_mcp

    captured = {}

    class FakeMCP:
        async def call_tool(self, name, args=None):
            captured["name"] = name
            captured["args"] = args
            return '{"drawers": []}'

    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: FakeMCP())
    answer = Answer(sid=SID, text="т", pages=["т"], ctx={"wing": "w1", "room": "r1"})
    asyncio.run(ab._build_ai_context(answer, 1))
    assert captured["name"] == "mempalace_list_drawers"
    assert captured["args"] == {"wing": "w1", "room": "r1", "limit": 15, "offset": 0}


def test_build_ai_context_mcp_name_fallback_chain(monkeypatch):
    import handlers.palace.action_bar as ab
    from services import palace_mcp

    class FakeMCP:
        async def call_tool(self, name, args=None):
            return '{"drawers": [{"title": "Только title", "content_preview": "пр"}]}'

    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: FakeMCP())
    answer = Answer(sid=SID, text="т", pages=["т"], ctx={"wing": "w1", "room": "r1"})
    result = asyncio.run(ab._build_ai_context(answer, 1))
    assert "Только title" in result


def test_build_ai_context_mcp_name_only_name_field(monkeypatch):
    import handlers.palace.action_bar as ab
    from services import palace_mcp

    class FakeMCP:
        async def call_tool(self, name, args=None):
            return '{"drawers": [{"name": "Имя", "content_preview": "пр"}]}'

    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: FakeMCP())
    answer = Answer(sid=SID, text="т", pages=["т"], ctx={"wing": "w1", "room": "r1"})
    result = asyncio.run(ab._build_ai_context(answer, 1))
    assert "Имя" in result


def test_build_ai_context_mcp_content_fallback(monkeypatch):
    import handlers.palace.action_bar as ab
    from services import palace_mcp

    long_content = "с" * 290 + "ХВОСТ-НЕ-ДОЛЖЕН-ПОПАСТЬ"

    class FakeMCP:
        async def call_tool(self, name, args=None):
            return '{"drawers": [{"closet_name": "Зап", "content": "%s"}]}' % long_content

    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: FakeMCP())
    answer = Answer(sid=SID, text="т", pages=["т"], ctx={"wing": "w1", "room": "r1"})
    result = asyncio.run(ab._build_ai_context(answer, 1))
    assert long_content[:300] in result
    assert "ХВОСТ-НЕ-ДОЛЖЕН-ПОПАСТЬ" not in result


def test_build_ai_context_mcp_join_separator(monkeypatch):
    import handlers.palace.action_bar as ab
    from services import palace_mcp

    class FakeMCP:
        async def call_tool(self, name, args=None):
            return '{"drawers": [' \
                   '{"closet_name": "A", "content_preview": "pa"},' \
                   '{"closet_name": "B", "content_preview": "pb"}]}'

    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: FakeMCP())
    answer = Answer(sid=SID, text="т", pages=["т"], ctx={"wing": "w1", "room": "r1"})
    result = asyncio.run(ab._build_ai_context(answer, 1))
    assert "pa\n\n--- B ---" in result


def test_build_ai_context_mcp_truncation_12000(monkeypatch):
    import handlers.palace.action_bar as ab
    from services import palace_mcp

    big = "з" * 12000 + "УНИКАЛЬНЫЙ-ХВОСТ"

    class FakeMCP:
        async def call_tool(self, name, args=None):
            return '{"drawers": [{"closet_name": "Б", "content_preview": "%s"}]}' % big

    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: FakeMCP())
    answer = Answer(sid=SID, text="т", pages=["т"], ctx={"wing": "w1", "room": "r1"})
    result = asyncio.run(ab._build_ai_context(answer, 1))
    assert "(сокращено)" in result
    assert result.endswith("...(сокращено)")
    assert "УНИКАЛЬНЫЙ-ХВОСТ" not in result


def test_build_ai_context_summary_truncation_12000(monkeypatch):
    import handlers.palace.action_bar as ab
    from handlers.palace import shared

    summary = "м" * 12000 + "У"
    monkeypatch.setattr(shared, "_user_context", {
        TEST_UID: {"_room_summary": summary},
    })
    answer = Answer(sid=SID, text="т", pages=["т"], ctx={"wing": "w1", "room": "r1"})
    result = asyncio.run(ab._build_ai_context(answer, TEST_UID))
    assert summary[:12000] in result
    assert "У" not in result


def test_build_ai_context_mcp_drawer_without_name(monkeypatch):
    import handlers.palace.action_bar as ab
    from services import palace_mcp

    class FakeMCP:
        async def call_tool(self, name, args=None):
            return '{"drawers": [{"closet_name": "", "title": "", "content_preview": "p"}]}'

    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: FakeMCP())
    answer = Answer(sid=SID, text="т", pages=["т"], ctx={"wing": "w1", "room": "r1"})
    result = asyncio.run(ab._build_ai_context(answer, 1))
    assert "None" not in result
    assert "XXXX" not in result
    assert "---  ---\np" in result


def test_build_ai_context_mcp_error_logs(caplog):
    import handlers.palace.action_bar as ab
    from services import palace_mcp

    class BoomMCP:
        async def call_tool(self, name, args=None):
            raise RuntimeError("boom")

    monkeypatch = __import__("pytest").MonkeyPatch()
    try:
        monkeypatch.setattr(palace_mcp, "get_mcp", lambda: BoomMCP())
        answer = Answer(sid=SID, text="т", pages=["т"], ctx={"wing": "w1", "room": "r1"})
        with caplog.at_level("ERROR", logger="handlers.palace.action_bar"):
            assert asyncio.run(ab._build_ai_context(answer, 1)) == ""
        assert caplog.records[-1].getMessage() == "[ACTION_BAR] ai context error: boom"
    finally:
        monkeypatch.undo()


def test_build_ai_context_room_missing_skips_mcp(monkeypatch):
    import handlers.palace.action_bar as ab
    from services import palace_mcp

    called = []

    class FakeMCP:
        async def call_tool(self, name, args=None):
            called.append(name)
            return '{"drawers": [{"closet_name": "A", "content_preview": "pa"}]}'

    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: FakeMCP())
    answer = Answer(sid=SID, text="т", pages=["т"], ctx={"wing": "w1"})
    assert asyncio.run(ab._build_ai_context(answer, 1)) == ""
    assert called == []


def test_build_ai_context_wing_missing_skips_mcp(monkeypatch):
    import handlers.palace.action_bar as ab
    from services import palace_mcp

    called = []

    class FakeMCP:
        async def call_tool(self, name, args=None):
            called.append(name)
            return '{"drawers": [{"closet_name": "A", "content_preview": "pa"}]}'

    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: FakeMCP())
    answer = Answer(sid=SID, text="т", pages=["т"], ctx={"room": "r1"})
    assert asyncio.run(ab._build_ai_context(answer, 1)) == ""
    assert called == []


def test_build_ai_context_exact_12000_not_truncated(monkeypatch):
    import handlers.palace.action_bar as ab
    from services import palace_mcp

    exact = "з" * 11990

    class FakeMCP:
        async def call_tool(self, name, args=None):
            return '{"drawers": [{"closet_name": "Б", "content_preview": "%s"}]}' % exact

    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: FakeMCP())
    answer = Answer(sid=SID, text="т", pages=["т"], ctx={"wing": "w1", "room": "r1"})
    result = asyncio.run(ab._build_ai_context(answer, 1))
    assert "(сокращено)" not in result


def test_build_ai_context_12001_truncated(monkeypatch):
    import handlers.palace.action_bar as ab
    from services import palace_mcp

    big = "з" * 11990 + "М"

    class FakeMCP:
        async def call_tool(self, name, args=None):
            return '{"drawers": [{"closet_name": "Б", "content_preview": "%s"}]}' % big

    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: FakeMCP())
    answer = Answer(sid=SID, text="т", pages=["т"], ctx={"wing": "w1", "room": "r1"})
    result = asyncio.run(ab._build_ai_context(answer, 1))
    assert "(сокращено)" in result
    assert "М" not in result


def test_find_cut_rfind_last_separator():
    import handlers.palace.action_bar as ab

    assert ab._find_cut("a\n\nbb cc dd ee", 10) == 9


def test_find_cut_separator_at_start_returns_limit():
    import handlers.palace.action_bar as ab

    assert ab._find_cut("\n\n" + "b" * 1400, 1500) == 1500


def test_paginate_exact_limit_with_trailing_space():
    import handlers.palace.action_bar as ab

    text = "б" * 1499 + " "
    assert ab.paginate(text, 1500) == [text]


def test_paginate_remaining_exactly_limit():
    import handlers.palace.action_bar as ab

    text = "б" * 1499 + " " + "в" * 1499 + " "
    assert ab.paginate(text, 1500) == ["б" * 1499, "в" * 1499 + " "]


# _run_web_search_finalize


def test_run_web_search_finalize_success(monkeypatch):
    import handlers.palace.action_bar as ab
    from services import web_search

    captured = {}

    async def fake_search(q):
        captured["query"] = q
        return "web результаты"

    def fake_sync(engine, model, messages):
        captured["engine"] = engine
        captured["model"] = model
        captured["messages"] = messages
        return "Ответ поиска"

    monkeypatch.setattr(web_search, "search_web", fake_search)
    monkeypatch.setattr(ab, "get_current_ai", lambda: ("gemini", "m"))
    monkeypatch.setattr(ab, "_sync_ai_call", fake_sync)

    answer = Answer(sid=SID, text="контекст ответа", pages=["к"], ctx={"k": "v"})
    answer_store[SID] = answer

    msg = FakeMessage()
    asyncio.run(ab._run_web_search_finalize(TEST_UID, msg.edit_text, answer, "мой запрос"))

    assert captured["query"] == "мой запрос"
    assert captured["engine"] == "gemini"
    assert captured["model"] == "m"
    assert captured["messages"][0]["role"] == "system"
    assert captured["messages"][0]["content"].startswith(
        "Ты отвечаешь на запрос пользователя, используя результаты "
    )
    assert "результаты поиска" in captured["messages"][0]["content"]
    assert "поиска в интернете" in captured["messages"][0]["content"]
    assert "контекст ответа" in captured["messages"][0]["content"]
    assert captured["messages"][1] == {"role": "user", "content": "мой запрос"}
    assert "Ответ поиска" in msg.edited[-1]


def test_run_web_search_finalize_context_truncated_6000(monkeypatch):
    import handlers.palace.action_bar as ab
    from services import web_search

    captured = {}

    async def fake_search(q):
        return "web"

    def fake_sync(engine, model, messages):
        captured["content"] = messages[0]["content"]
        return "Ответ"

    monkeypatch.setattr(web_search, "search_web", fake_search)
    monkeypatch.setattr(ab, "get_current_ai", lambda: ("gemini", "m"))
    monkeypatch.setattr(ab, "_sync_ai_call", fake_sync)

    answer = Answer(
        sid=SID, text="к" * 6000 + "УНИКАЛЬНЫЙ-ХВОСТ", pages=["к"],
        ctx={},
    )
    answer_store[SID] = answer
    msg = FakeMessage()
    asyncio.run(ab._run_web_search_finalize(TEST_UID, msg.edit_text, answer, "q"))
    assert "УНИКАЛЬНЫЙ-ХВОСТ" not in captured["content"]
    ctx_part = captured["content"].split("Контекст ответа:\n")[1].split("\n\nРезультаты поиска:")[0]
    assert ctx_part.count("к") == 6000


def test_run_web_search_finalize_empty_result_fallback(monkeypatch):
    import handlers.palace.action_bar as ab
    from services import web_search

    async def fake_search(q):
        return "web"

    monkeypatch.setattr(web_search, "search_web", fake_search)
    monkeypatch.setattr(ab, "get_current_ai", lambda: ("gemini", "m"))
    monkeypatch.setattr(ab, "_sync_ai_call", lambda *a, **k: "")

    answer = Answer(sid=SID, text="т", pages=["т"], ctx={})
    answer_store[SID] = answer
    msg = FakeMessage()
    asyncio.run(ab._run_web_search_finalize(TEST_UID, msg.edit_text, answer, "q"))
    assert msg.edited[-1].endswith("❌ Пустой ответ.")


def test_run_web_search_finalize_sets_origin_sid(monkeypatch):
    import handlers.palace.action_bar as ab
    from services import web_search

    captured = {}

    async def fake_search(q):
        return "web"

    def fake_sync(engine, model, messages):
        return "Ок"

    def fake_finalize(uid, edit_func, text, **kwargs):
        captured["uid"] = uid
        captured["kwargs"] = kwargs
        captured["text"] = text

    monkeypatch.setattr(web_search, "search_web", fake_search)
    monkeypatch.setattr(ab, "get_current_ai", lambda: ("gemini", "m"))
    monkeypatch.setattr(ab, "_sync_ai_call", fake_sync)
    monkeypatch.setattr(ab, "finalize_answer", fake_finalize)

    answer = Answer(sid=SID, text="т", pages=["т"], ctx={"k": "v"})
    asyncio.run(ab._run_web_search_finalize(TEST_UID, lambda *a, **k: None, answer, "q"))

    assert captured["uid"] == TEST_UID
    assert captured["kwargs"]["ctx"] == {"k": "v", "_origin_sid": SID}
    assert captured["kwargs"]["title"] == "<b>🌐 Поиск: q</b>"
    assert captured["kwargs"]["is_html"] is False


def test_run_web_search_finalize_title_truncated_80(monkeypatch):
    import handlers.palace.action_bar as ab
    from services import web_search

    captured = {}

    async def fake_search(q):
        return "web"

    def fake_sync(engine, model, messages):
        return "Ок"

    def fake_finalize(uid, edit_func, text, **kwargs):
        captured["title"] = kwargs["title"]

    monkeypatch.setattr(web_search, "search_web", fake_search)
    monkeypatch.setattr(ab, "get_current_ai", lambda: ("gemini", "m"))
    monkeypatch.setattr(ab, "_sync_ai_call", fake_sync)
    monkeypatch.setattr(ab, "finalize_answer", fake_finalize)

    query = "q" * 80 + "УНИКАЛЬНЫЙ-ХВОСТ"
    answer = Answer(sid=SID, text="т", pages=["т"], ctx={})
    asyncio.run(ab._run_web_search_finalize(TEST_UID, lambda *a, **k: None, answer, query))
    assert "УНИКАЛЬНЫЙ-ХВОСТ" not in captured["title"]


def test_run_web_search_finalize_search_error(monkeypatch):
    import handlers.palace.action_bar as ab
    from services import web_search

    async def boom(q):
        raise RuntimeError("search fail")

    monkeypatch.setattr(web_search, "search_web", boom)

    answer = Answer(sid=SID, text="т", pages=["т"], ctx={})
    msg = FakeMessage()
    asyncio.run(ab._run_web_search_finalize(TEST_UID, msg.edit_text, answer, "q"))
    assert "❌ Ошибка поиска: search fail" in msg.edited[-1]


def test_run_web_search_finalize_double_error_logs(caplog):
    import handlers.palace.action_bar as ab
    from services import web_search

    async def boom(q):
        raise RuntimeError("search fail")

    def bad_edit(text, **kwargs):
        raise RuntimeError("edit fail")

    monkeypatch = __import__("pytest").MonkeyPatch()
    try:
        monkeypatch.setattr(web_search, "search_web", boom)
        answer = Answer(sid=SID, text="т", pages=["т"], ctx={})
        asyncio.run(ab._run_web_search_finalize(TEST_UID, bad_edit, answer, "q"))
        assert any(
            r.name == "ActionBar"
            and r.getMessage().startswith("[ACTION_BAR] web search error:")
            for r in caplog.records
        )
        assert "search fail" in caplog.text
        assert "edit fail" in caplog.text
    finally:
        monkeypatch.undo()


# _finalize_answer


def test_finalize_answer_sid_length_8():
    import handlers.palace.action_bar as ab

    msg = FakeMessage()

    async def edit_func(text, **kwargs):
        msg.edited.append(text)
        return msg

    answer = asyncio.run(ab.finalize_answer(1, edit_func, "текст"))
    assert len(answer.sid) == 8


def test_finalize_answer_preserves_ctx_and_extra_rows():
    import handlers.palace.action_bar as ab
    from aiogram import types

    msg = FakeMessage()

    async def edit_func(text, **kwargs):
        msg.edited.append(text)
        msg.markups.append(kwargs.get("reply_markup"))
        return msg

    extra = [[types.InlineKeyboardButton(text="x", callback_data="p_rd:0")]]
    answer = asyncio.run(ab.finalize_answer(
        1, edit_func, "текст", ctx={"a": 1}, is_html=True,
        extra_rows=extra,
    ))
    assert answer.text == "текст"
    assert answer.ctx == {"a": 1}
    assert answer.is_html is True
    assert answer.extra_rows == extra
    assert [b.callback_data for b in msg.markups[-1].inline_keyboard[0]] == ["p_rd:0"]


def test_finalize_answer_empty_html_text_has_empty_page():
    import handlers.palace.action_bar as ab

    msg = FakeMessage()

    async def edit_func(text, **kwargs):
        msg.edited.append(text)
        msg.markups.append(kwargs.get("reply_markup"))
        return msg

    answer = asyncio.run(ab.finalize_answer(1, edit_func, "", is_html=True))
    assert answer.pages == [""]


# _get_parent_handler: все ключи карты


def test_get_parent_handler_all_keys():
    import handlers.palace.action_bar as ab

    for key in [
        "p_rdb", "p_nav", "p_wing", "p_tax", "p_tun",
        "p_kg", "p_kgr", "p_kgsr", "palace_back",
        "palace_status", "palace_admin", "palace_instructions",
    ]:
        assert ab._get_parent_handler(key) is not None, key


# _dispatch_parent: ошибка обработчика


def test_dispatch_parent_handler_error_returns_false(caplog):
    import handlers.palace.action_bar as ab
    from handlers.palace import navigation

    async def broken(cb):
        raise RuntimeError("dispatch fail")

    monkeypatch = __import__("pytest").MonkeyPatch()
    try:
        monkeypatch.setattr(navigation, "cb_tunnels_menu", broken)
        cb = FakeCallback("ab_back:x")
        with caplog.at_level("ERROR", logger="handlers.palace.action_bar"):
            assert asyncio.run(ab._dispatch_parent(cb, "p_tun")) is False
        record = caplog.records[-1]
        assert record.getMessage() == "[ACTION_BAR] parent dispatch error: dispatch fail"
        assert record.exc_info
    finally:
        monkeypatch.undo()


# _build_action_bar: точные тексты кнопок


def test_action_bar_exact_button_texts():
    answer = Answer(sid=SID, text="а" * 3000, pages=["а" * 1500, "а" * 1500])
    labels0 = _button_labels(answer, 0)
    assert "▶️ Вперёд" in labels0
    assert "◀️ Назад" not in labels0
    labels1 = _button_labels(answer, 1)
    assert "◀️ Назад" in labels1


def test_action_bar_back_button_text():
    answer = Answer(sid=SID, text="т", pages=["т"], ctx={"parent_cb": "p_rdb"})
    labels = _button_labels(answer)
    assert "🔙 Вернуться к списку" in labels


# _run_web_search_with_query: точные строки


def test_run_web_search_with_query_exact_expired_message():
    import handlers.palace.action_bar as ab

    msg = FakeMessage()
    asyncio.run(ab.run_web_search_with_query(1, msg, "unknown", "запрос"))
    assert msg.edited[-1] == "❌ Сессия поиска истекла. Начните заново."


def test_run_web_search_with_query_status_message(monkeypatch):
    import handlers.palace.action_bar as ab
    from services import web_search

    captured = {}

    async def fake_search(q):
        return "web"

    async def fake_finalize(uid, edit_func, answer, query):
        captured["uid"] = uid
        captured["answer"] = answer

    monkeypatch.setattr(web_search, "search_web", fake_search)
    monkeypatch.setattr(ab, "_run_web_search_finalize", fake_finalize)

    answer = Answer(sid=SID, text="т", pages=["т"], ctx={})
    answer_store[SID] = answer
    msg = FakeMessage()
    asyncio.run(ab.run_web_search_with_query(TEST_UID, msg, SID, "запрос"))
    assert msg.edited[0] == "🌐 Ищу в интернете..."
    assert captured["uid"] == TEST_UID
    assert captured["answer"] is answer


def test_run_web_search_with_query_no_session_answer(caplog):
    import handlers.palace.action_bar as ab

    msg = FakeMessage()
    asyncio.run(ab.run_web_search_with_query(TEST_UID, msg, "unknown", "запрос"))
    assert msg.edited[-1] == "❌ Сессия поиска истекла. Начните заново."


# __render_page: точный формат заголовка


def test_render_page_title_exact_format():
    answer = Answer(
        sid=SID, text="текст", pages=["текст"],
        title="<b>Заголовок</b>",
    )
    assert _render_page(answer, 0) == "<b>Заголовок</b>\n\nтекст"


# _find_cut: разделитель ровно на половине лимита (граница >= vs >)


def test_find_cut_exact_half_limit_boundary():
    import handlers.palace.action_bar as ab

    assert ab._find_cut("a" * 5 + "\n" + "b" * 10, 10) == 6


# _build_ai_context: drawer без content_preview и без content


def test_build_ai_context_mcp_drawer_empty_entries(monkeypatch):
    import handlers.palace.action_bar as ab
    from services import palace_mcp

    class FakeMCP:
        async def call_tool(self, name, args=None):
            return '{"drawers": [{"closet_name": "К", "title": "Т", "content_preview": ""}]}'

    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: FakeMCP())
    answer = Answer(sid=SID, text="т", pages=["т"], ctx={"wing": "w1", "room": "r1"})
    result = asyncio.run(ab._build_ai_context(answer, 1))
    assert "--- К ---" in result
    assert "None" not in result
    assert "XXXX" not in result


def test_build_ai_context_mcp_drawer_long_content_truncated(monkeypatch):
    import handlers.palace.action_bar as ab
    from services import palace_mcp

    class FakeMCP:
        async def call_tool(self, name, args=None):
            return (
                '{"drawers": [{"closet_name": "К", "title": "Т", '
                '"content": "' + "с" * 300 + "М" + '"}]}'
            )

    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: FakeMCP())
    answer = Answer(sid=SID, text="т", pages=["т"], ctx={"wing": "w1", "room": "r1"})
    result = asyncio.run(ab._build_ai_context(answer, 1))
    assert "М" not in result
    preview_part = result.split("--- К ---")[1]
    assert preview_part.count("с") == 300


# finalize_answer: одна страница — без навигации на первом сообщении


def test_finalize_answer_single_page_first_markup_has_no_nav():
    import handlers.palace.action_bar as ab

    msg = FakeMessage()

    async def edit_func(text, **kwargs):
        msg.edited.append(text)
        msg.markups.append(kwargs.get("reply_markup"))
        return msg

    asyncio.run(ab.finalize_answer(1, edit_func, "текст"))
    kb = msg.markups[0].inline_keyboard
    labels = [b.text for row in kb for b in row]


def test_finalize_answer_first_markup_uses_page_zero():
    import handlers.palace.action_bar as ab

    msg = FakeMessage()

    async def edit_func(text, **kwargs):
        msg.edited.append(text)
        msg.markups.append(kwargs.get("reply_markup"))
        return msg

    asyncio.run(ab.finalize_answer(1, edit_func, "а" * (ab.PAGE_LIMIT + 50)))
    kb = msg.markups[0].inline_keyboard
    labels = [b.text for row in kb for b in row]
    assert "◀️ Назад" not in labels
    assert "📄 1/2" in labels


# _find_cut: \n\n во второй половине лимита


def test_find_cut_double_newline_in_second_half():
    import handlers.palace.action_bar as ab

    assert ab._find_cut("aaaaa\n\nb\ncccc", 10) == 7
