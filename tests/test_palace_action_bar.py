"""Unit tests for handlers.palace.action_bar."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from handlers.palace import action_bar as ab


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
        return self


class FakeCb:
    def __init__(self, uid=4242, data="", message=None):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = message or FakeMessage(uid)
        self.answered = []

    async def answer(self, text=None, show_alert=None):
        self.answered.append((text, show_alert))


def _enable(monkeypatch):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {4242})
    monkeypatch.setattr(ab, "secrets", SimpleNamespace(token_hex=lambda n: "abcd"))
    monkeypatch.setattr(ab, "safe_html_format", lambda x: x)


@pytest.fixture(autouse=True)
def _clean_store():
    from handlers.palace import shared as sh

    ab.answer_store.clear()
    sh.fsm.pop_data(4242, "_user_context")
    sh.fsm.pop_data(4242, "_save_state")
    sh.fsm.pop_data(4242, "_pending_mcp_input")
    yield
    ab.answer_store.clear()
    sh.fsm.pop_data(4242, "_user_context")
    sh.fsm.pop_data(4242, "_save_state")
    sh.fsm.pop_data(4242, "_pending_mcp_input")


def _kb_data(markup):
    if markup is None:
        return []
    if hasattr(markup, "as_markup"):
        markup = markup.as_markup()
    return [b.callback_data for row in markup.inline_keyboard for b in row]


def _seed_answer(text="текст", ctx=None, extra_rows=None, is_html=False):
    answer = ab.Answer(
        sid="abcd", text=text, ctx=ctx or {}, is_html=is_html,
        extra_rows=extra_rows or [],
    )
    answer.pages = ab.paginate(text) if not is_html else [text]
    ab.answer_store["abcd"] = answer
    return answer


# ---------- _find_cut ----------


def test_find_cut_paragraph():
    text = "абзац один\n\nабзац два\n\nабзац три"
    idx = ab._find_cut(text, 20)
    assert text[:idx].endswith("\n\n")


def test_find_cut_newline():
    text = "строка один\nстрока два\nстрока три"
    idx = ab._find_cut(text, 20)
    assert text[:idx].endswith("\n")


def test_find_cut_space():
    text = "слово один два три четыре пять"
    idx = ab._find_cut(text, 20)
    assert text[idx - 1] == " "


def test_find_cut_fallback_limit():
    text = "безразделителей" * 10
    assert ab._find_cut(text, 20) == 20


def test_find_cut_too_close_to_start():
    text = "короткое слово" + "x" * 60
    assert ab._find_cut(text, 40) == 40


# ---------- paginate ----------


def test_paginate_empty():
    assert ab.paginate("") == [""]


def test_paginate_short():
    assert ab.paginate("короткий текст", 100) == ["короткий текст"]


def test_paginate_multiple():
    text = ("слово " * 400).strip()
    pages = ab.paginate(text, 100)
    assert len(pages) > 1
    assert all(len(p) <= 100 for p in pages)
    assert "".join(pages).replace(" ", "") == text.replace(" ", "")


def test_paginate_exact_limit():
    text = "a" * 100
    assert ab.paginate(text, 100) == ["a" * 100]


def test_paginate_just_over():
    text = "b" * 101
    pages = ab.paginate(text, 100)
    assert len(pages) == 2


# ---------- _render_page ----------


def test_render_page_plain(monkeypatch):
    _enable(monkeypatch)
    answer = _seed_answer(text="простой текст")
    assert ab._render_page(answer, 0) == "простой текст"


def test_render_page_html():
    answer = ab.Answer(sid="x", text="<b>жирный</b>", is_html=True)
    answer.pages = ["<b>жирный</b>"]
    assert ab._render_page(answer, 0) == "<b>жирный</b>"


def test_render_page_title_first():
    answer = ab.Answer(sid="x", text="текст", title="<b>Заголовок</b>")
    answer.pages = ["текст"]
    out = ab._render_page(answer, 0)
    assert out.startswith("<b>Заголовок</b>")
    assert "текст" in out


def test_render_page_title_not_on_second():
    answer = ab.Answer(sid="x", text="текст", title="<b>Заголовок</b>")
    answer.pages = ["текст", "второй"]
    assert ab._render_page(answer, 1) == "второй"


# ---------- build_action_bar ----------


def test_build_action_bar_single_page():
    answer = ab.Answer(sid="x", text="t", ctx={"parent_cb": "p_kg"})
    answer.pages = ["t"]
    kb = ab.build_action_bar(answer, 0)
    assert _kb_data(kb) == [
        "ab_ai:x", "ab_web:x", "ab_sv:x", "ab_agent:x", "ab_back:x",
    ]


def test_build_action_bar_pagination_middle():
    answer = ab.Answer(sid="x", text="t")
    answer.pages = ["p1", "p2", "p3"]
    kb = ab.build_action_bar(answer, 1)
    data = _kb_data(kb)
    assert "ab_pg:x:0" in data
    assert "ab_pg_noop" in data
    assert "ab_pg:x:2" in data


def test_build_action_bar_pagination_first():
    answer = ab.Answer(sid="x", text="t")
    answer.pages = ["p1", "p2"]
    kb = ab.build_action_bar(answer, 0)
    data = _kb_data(kb)
    assert "ab_pg:x:1" in data
    assert "ab_pg:x:-1" not in data


def test_build_action_bar_pagination_last():
    answer = ab.Answer(sid="x", text="t")
    answer.pages = ["p1", "p2"]
    kb = ab.build_action_bar(answer, 1)
    data = _kb_data(kb)
    assert "ab_pg:x:0" in data
    assert "ab_pg:x:2" not in data


def test_build_action_bar_extra_rows():
    from aiogram import types

    answer = ab.Answer(sid="x", text="t")
    answer.pages = ["t"]
    answer.extra_rows = [[types.InlineKeyboardButton(
        text="🏰", callback_data="p_kgc")]]
    kb = ab.build_action_bar(answer, 0)
    assert _kb_data(kb)[0] == "p_kgc"


def test_build_action_bar_no_parent():
    answer = ab.Answer(sid="x", text="t")
    answer.pages = ["t"]
    kb = ab.build_action_bar(answer, 0)
    assert "ab_back:x" not in _kb_data(kb)


# ---------- finalize_answer ----------


def test_finalize_answer_success(monkeypatch):
    _enable(monkeypatch)
    edits = []

    async def edit_func(text, **kwargs):
        edits.append((text, kwargs))

    answer = asyncio.run(
        ab.finalize_answer(4242, edit_func, "длинный " * 500, ctx={"wing": "w"}),
    )
    assert answer is not None
    assert answer.sid == "abcd"
    assert answer.total_pages > 1
    assert edits[0][1]["parse_mode"] == "HTML"
    assert ab.get_answer("abcd") is answer


def test_finalize_answer_is_html(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(ab, "split_message", lambda text, limit=None: [text])
    edits = []

    async def edit_func(text, **kwargs):
        edits.append(text)

    answer = asyncio.run(
        ab.finalize_answer(4242, edit_func, "<b>x</b>", is_html=True),
    )
    assert answer is not None
    assert edits[0] == "<b>x</b>"


def test_finalize_answer_error(monkeypatch):
    _enable(monkeypatch)

    async def boom(text, **kwargs):
        raise RuntimeError("edit fail")

    answer = asyncio.run(ab.finalize_answer(4242, boom, "текст"))
    assert answer is None


# ---------- get_answer ----------


def test_get_answer_missing():
    assert ab.get_answer("nope") is None


# ---------- _get_parent_handler ----------


def test_get_parent_handler_known():
    handler = ab._get_parent_handler("p_kg")
    assert handler is not None


def test_get_parent_handler_unknown():
    assert ab._get_parent_handler("nope") is None


# ---------- _dispatch_parent ----------


def test_dispatch_parent_success(monkeypatch):
    called = []

    async def fake_handler(cb):
        called.append(cb)

    monkeypatch.setattr(ab, "_get_parent_handler", lambda p: fake_handler)
    cb = FakeCb(data="ab_back:abcd")
    assert asyncio.run(ab._dispatch_parent(cb, "p_kg")) is True
    assert called == [cb]


def test_dispatch_parent_no_handler(monkeypatch):
    monkeypatch.setattr(ab, "_get_parent_handler", lambda p: None)
    cb = FakeCb(data="ab_back:abcd")
    assert asyncio.run(ab._dispatch_parent(cb, "p_kg")) is False


def test_dispatch_parent_handler_error(monkeypatch):
    async def boom(cb):
        raise RuntimeError("handler fail")

    monkeypatch.setattr(ab, "_get_parent_handler", lambda p: boom)
    cb = FakeCb(data="ab_back:abcd")
    assert asyncio.run(ab._dispatch_parent(cb, "p_kg")) is False


# ---------- cb_ab_pg_noop ----------


def test_cb_ab_pg_noop(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="ab_pg_noop")
    asyncio.run(ab.cb_ab_pg_noop(cb))
    assert cb.answered == [(None, None)]


# ---------- cb_ab_page ----------


def test_cb_ab_page_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb()
    asyncio.run(ab.cb_ab_page(cb))
    assert cb.answered == [(None, None)]


def test_cb_ab_page_bad_parts(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="ab_pg:abc")
    asyncio.run(ab.cb_ab_page(cb))
    assert cb.answered == [(None, None)]


def test_cb_ab_page_bad_idx(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="ab_pg:abcd:нецифра")
    asyncio.run(ab.cb_ab_page(cb))
    assert cb.answered == [(None, None)]


def test_cb_ab_page_no_answer(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="ab_pg:nope:0")
    asyncio.run(ab.cb_ab_page(cb))
    assert cb.answered == [(None, None), ("Сессия истекла. Откройте заново.", True)]


def test_cb_ab_page_out_of_range(monkeypatch):
    _enable(monkeypatch)
    _seed_answer(text="текст")
    cb = FakeCb(data="ab_pg:abcd:5")
    asyncio.run(ab.cb_ab_page(cb))
    assert cb.answered == [(None, None), ("Сессия истекла. Откройте заново.", True)]


def test_cb_ab_page_success(monkeypatch):
    _enable(monkeypatch)
    answer = _seed_answer(text="первый\n\nвторой")
    answer.pages = ["первый", "второй"]
    cb = FakeCb(data="ab_pg:abcd:1")
    asyncio.run(ab.cb_ab_page(cb))
    assert cb.message.edits[-1][0] == "второй"
    assert answer.page == 1


# ---------- cb_ab_back ----------


def test_cb_ab_back_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb()
    asyncio.run(ab.cb_ab_back(cb))
    assert cb.answered == [(None, None)]


def test_cb_ab_back_no_answer(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="ab_back:nope")
    asyncio.run(ab.cb_ab_back(cb))
    assert cb.answered == [(None, None), ("Сессия истекла. Откройте заново.", True)]


def test_cb_ab_back_no_parent_cb(monkeypatch):
    _enable(monkeypatch)
    _seed_answer(text="текст")
    cb = FakeCb(data="ab_back:abcd")
    asyncio.run(ab.cb_ab_back(cb))
    assert cb.answered == [(None, None), ("Нет родительского экрана.", True)]


def test_cb_ab_back_dispatch(monkeypatch):
    _enable(monkeypatch)
    _seed_answer(text="текст", ctx={"parent_cb": "p_kg"})
    dispatched = []

    async def fake_dispatch(cb, p):
        dispatched.append(p)

    monkeypatch.setattr(ab, "_dispatch_parent", fake_dispatch)
    cb = FakeCb(data="ab_back:abcd")
    asyncio.run(ab.cb_ab_back(cb))
    assert dispatched == ["p_kg"]
    assert cb.answered == [(None, None)]


def test_cb_ab_back_dispatch_fail(monkeypatch):
    _enable(monkeypatch)
    _seed_answer(text="текст", ctx={"parent_cb": "p_kg"})

    async def fake_dispatch(cb, p):
        return False

    monkeypatch.setattr(ab, "_dispatch_parent", fake_dispatch)
    cb = FakeCb(data="ab_back:abcd")
    asyncio.run(ab.cb_ab_back(cb))
    assert cb.answered == [(None, None)]


# ---------- cb_ab_ai ----------


def test_cb_ab_ai_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb()
    asyncio.run(ab.cb_ab_ai(cb))
    assert cb.answered == [(None, None)]


def test_cb_ab_ai_no_answer(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="ab_ai:abcd")
    asyncio.run(ab.cb_ab_ai(cb))
    assert cb.answered == [(None, None), ("Сессия истекла. Откройте заново.", True)]


def test_cb_ab_ai_success(monkeypatch):
    _enable(monkeypatch)
    _seed_answer(text="текст", ctx={"wing": "w", "room": "r"})
    cb = FakeCb(data="ab_ai:abcd")
    asyncio.run(ab.cb_ab_ai(cb))
    text = cb.message.edits[-1][0]
    assert text == "🤖 <b>Режим анализа:</b>"
    assert _kb_data(cb.message.edits[-1][2]) == [
        "ab_ai_m:a:abcd", "ab_ai_m:c:abcd", "ab_back:abcd",
    ]


# ---------- _build_ai_context ----------


def test_build_ai_context_no_wing_room():
    answer = _seed_answer(text="текст")
    assert asyncio.run(ab._build_ai_context(answer, 4242)) == ""


def test_build_ai_context_cached_summary(monkeypatch):
    from handlers.palace import shared as sh

    sh.fsm.update_data(4242, _user_context={"_room_summary": "суммарий комнаты"})
    answer = _seed_answer(text="текст", ctx={"wing": "w", "room": "r"})
    ctx = asyncio.run(ab._build_ai_context(answer, 4242))
    assert "суммарий комнаты" in ctx
    assert "саммари" in ctx


def test_build_ai_context_drawers(monkeypatch):
    async def fake_call_tool(name, args):
        return json.dumps({"drawers": [
            {"closet_name": "Ящик 1", "content_preview": "факт из дворцов"},
        ]})

    monkeypatch.setattr(
        "services.palace_mcp.get_mcp",
        lambda: SimpleNamespace(call_tool=fake_call_tool),
    )
    answer = _seed_answer(text="текст", ctx={"wing": "w", "room": "r"})
    ctx = asyncio.run(ab._build_ai_context(answer, 4242))
    assert "w/r" in ctx
    assert "Ящик 1" in ctx
    assert "факт из дворцов" in ctx


def test_build_ai_context_empty_drawers(monkeypatch):
    async def fake_call_tool(name, args):
        return json.dumps({"drawers": []})

    monkeypatch.setattr(
        "services.palace_mcp.get_mcp",
        lambda: SimpleNamespace(call_tool=fake_call_tool),
    )
    answer = _seed_answer(text="текст", ctx={"wing": "w", "room": "r"})
    assert asyncio.run(ab._build_ai_context(answer, 4242)) == ""


def test_build_ai_context_error(monkeypatch):
    def boom():
        raise RuntimeError("mcp down")

    monkeypatch.setattr("services.palace_mcp.get_mcp", boom)
    answer = _seed_answer(text="текст", ctx={"wing": "w", "room": "r"})
    assert asyncio.run(ab._build_ai_context(answer, 4242)) == ""


# ---------- cb_ab_ai_run ----------


def test_cb_ab_ai_run_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb()
    asyncio.run(ab.cb_ab_ai_run(cb))
    assert cb.answered == [(None, None)]


def test_cb_ab_ai_run_bad_parts(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="ab_ai_m:a")
    asyncio.run(ab.cb_ab_ai_run(cb))
    assert cb.answered == [(None, None)]


def test_cb_ab_ai_run_no_answer(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="ab_ai_m:a:nope")
    asyncio.run(ab.cb_ab_ai_run(cb))
    assert cb.answered == [(None, None), ("Сессия истекла. Откройте заново.", True)]


def test_cb_ab_ai_run_mode_a(monkeypatch):
    _enable(monkeypatch)
    _seed_answer(text="текст ответа", ctx={"wing": "w", "room": "r"})
    captured = {}

    def fake_sync(engine, model, messages):
        captured["prompt"] = messages[1]["content"]
        return "результат анализа"

    monkeypatch.setattr(ab, "get_current_ai", lambda: ("ollama", "qwen"))
    monkeypatch.setattr(ab, "_sync_ai_call", fake_sync)

    async def fake_finalize(uid, edit_func, text, **kwargs):
        captured["text"] = text
        captured["ctx"] = kwargs.get("ctx", {})
        return None

    monkeypatch.setattr(ab, "finalize_answer", fake_finalize)
    cb = FakeCb(data="ab_ai_m:a:abcd")
    asyncio.run(ab.cb_ab_ai_run(cb))
    assert "результат анализа" in captured["text"]
    assert "текст ответа" in captured["prompt"]
    assert captured["ctx"]["_origin_sid"] == "abcd"
    assert cb.message.answers[0][0] == "🧠 Анализирую..."


def test_cb_ab_ai_run_mode_a_error(monkeypatch):
    _enable(monkeypatch)
    _seed_answer(text="текст", ctx={})

    def boom(*a, **k):
        raise RuntimeError("ai fail")

    monkeypatch.setattr(ab, "get_current_ai", lambda: ("ollama", "qwen"))
    monkeypatch.setattr(ab, "_sync_ai_call", boom)
    cb = FakeCb(data="ab_ai_m:a:abcd")
    asyncio.run(ab.cb_ab_ai_run(cb))
    assert cb.message.edits[-1][0].startswith("❌ Ошибка анализа")


def test_cb_ab_ai_run_mode_c(monkeypatch):
    _enable(monkeypatch)
    _seed_answer(text="текст", ctx={"wing": "w", "room": "r"})
    monkeypatch.setattr(ab, "get_current_ai", lambda: ("ollama", "qwen"))
    captured = {}

    def fake_sync(engine, model, messages):
        captured["prompt"] = messages[1]["content"]
        return "результат"

    monkeypatch.setattr(ab, "_sync_ai_call", fake_sync)

    async def fake_context(answer, uid):
        return "дворцовый контекст"

    monkeypatch.setattr(ab, "_build_ai_context", fake_context)

    async def fake_finalize(uid, edit_func, text, **kwargs):
        captured["text"] = text
        return None

    monkeypatch.setattr(ab, "finalize_answer", fake_finalize)
    cb = FakeCb(data="ab_ai_m:c:abcd")
    asyncio.run(ab.cb_ab_ai_run(cb))
    assert "дворцовый контекст" in captured["prompt"]
    assert "результат" in captured["text"]
    assert "контекст комнаты" in captured["prompt"]


# ---------- cb_ab_web ----------


def test_cb_ab_web_no_answer(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="ab_web:nope")
    asyncio.run(ab.cb_ab_web(cb))
    assert cb.answered == [(None, None), ("Сессия истекла. Откройте заново.", True)]


def test_cb_ab_web_success(monkeypatch):
    _enable(monkeypatch)
    answer = _seed_answer(text="текст")
    monkeypatch.setattr(ab, "get_current_ai", lambda: ("ollama", "qwen"))
    monkeypatch.setattr(ab, "_sync_ai_call",
                        lambda *a, **k: '"поисковой запрос"')
    cb = FakeCb(data="ab_web:abcd")
    asyncio.run(ab.cb_ab_web(cb))
    text = cb.message.edits[-1][0]
    assert "поисковой запрос" in text
    assert _kb_data(cb.message.edits[-1][2]) == [
        "ab_web_go:abcd", "ab_web_edit:abcd", "ab_back:abcd",
    ]
    assert answer.ctx["web_query"] == "поисковой запрос"


def test_cb_ab_web_empty_query_error(monkeypatch):
    _enable(monkeypatch)
    _seed_answer(text="текст")
    monkeypatch.setattr(ab, "get_current_ai", lambda: ("ollama", "qwen"))
    monkeypatch.setattr(ab, "_sync_ai_call", lambda *a, **k: "  «»  ")
    cb = FakeCb(data="ab_web:abcd")
    asyncio.run(ab.cb_ab_web(cb))
    assert cb.message.edits[-1][0].startswith("❌ Ошибка:")


def test_cb_ab_web_error(monkeypatch):
    _enable(monkeypatch)
    _seed_answer(text="текст")
    monkeypatch.setattr(ab, "get_current_ai", lambda: ("ollama", "qwen"))

    def boom(*a, **k):
        raise RuntimeError("ai fail")

    monkeypatch.setattr(ab, "_sync_ai_call", boom)
    cb = FakeCb(data="ab_web:abcd")
    asyncio.run(ab.cb_ab_web(cb))
    assert cb.message.edits[-1][0].startswith("❌ Ошибка:")


# ---------- cb_ab_web_go ----------


def test_cb_ab_web_go_no_answer(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="ab_web_go:nope")
    asyncio.run(ab.cb_ab_web_go(cb))
    assert cb.answered == [(None, None), ("Сессия истекла. Откройте заново.", True)]


def test_cb_ab_web_go_no_query(monkeypatch):
    _enable(monkeypatch)
    _seed_answer(text="текст")
    cb = FakeCb(data="ab_web_go:abcd")
    asyncio.run(ab.cb_ab_web_go(cb))
    assert cb.answered == [(None, None), ("Нет запроса. Начните поиск заново.", True)]


def test_cb_ab_web_go_success(monkeypatch):
    _enable(monkeypatch)
    answer = _seed_answer(text="текст", ctx={"web_query": "запрос"})
    captured = []

    async def fake_finalize(uid, edit_func, a, q):
        captured.append((uid, edit_func, a, q))

    monkeypatch.setattr(ab, "_run_web_search_finalize", fake_finalize)
    cb = FakeCb(data="ab_web_go:abcd")
    asyncio.run(ab.cb_ab_web_go(cb))
    assert cb.message.answers[0][0] == "🌐 Ищу в интернете..."
    assert captured == [(4242, cb.message.edit_text, answer, "запрос")]


# ---------- _run_web_search_finalize ----------


def test_run_web_search_finalize_success(monkeypatch):
    _enable(monkeypatch)
    answer = _seed_answer(text="контекст ответа")
    captured = {}

    async def fake_search(query, **kwargs):
        return ["источник один", "источник два"]

    monkeypatch.setattr("services.web_search.search_web", fake_search)
    monkeypatch.setattr(ab, "get_current_ai", lambda: ("ollama", "qwen"))

    def fake_sync(engine, model, messages):
        captured["system"] = messages[0]["content"]
        return "итоговый ответ"

    monkeypatch.setattr(ab, "_sync_ai_call", fake_sync)

    async def fake_finalize(uid, edit_func, text, **kwargs):
        captured["text"] = text
        captured["ctx"] = kwargs.get("ctx", {})
        return None

    monkeypatch.setattr(ab, "finalize_answer", fake_finalize)
    msg = FakeMessage()
    asyncio.run(ab._run_web_search_finalize(4242, msg.edit_text, answer, "запрос"))
    assert "источник один" in captured["system"]
    assert "итоговый ответ" in captured["text"]
    assert "контекст ответа" in captured["system"]
    assert captured["ctx"]["_origin_sid"] == "abcd"


def test_run_web_search_finalize_empty_results(monkeypatch):
    _enable(monkeypatch)
    answer = _seed_answer(text="контекст")
    captured = []

    async def fake_search(query, **kwargs):
        return []

    monkeypatch.setattr("services.web_search.search_web", fake_search)
    monkeypatch.setattr(ab, "get_current_ai", lambda: ("ollama", "qwen"))
    monkeypatch.setattr(ab, "_sync_ai_call", lambda *a, **k: "ответ")
    monkeypatch.setattr(
        ab, "finalize_answer",
        lambda uid, edit_func, text, **kwargs: captured.append(text),
    )
    asyncio.run(ab._run_web_search_finalize(4242, FakeMessage().edit_text,
                                            answer, "запрос"))
    assert captured == ["ответ"]


def test_run_web_search_finalize_error(monkeypatch):
    _enable(monkeypatch)
    answer = _seed_answer(text="контекст")

    async def fake_search(query, **kwargs):
        raise RuntimeError("search down")

    monkeypatch.setattr("services.web_search.search_web", fake_search)
    msg = FakeMessage()
    asyncio.run(ab._run_web_search_finalize(4242, msg.edit_text, answer, "запрос"))
    assert msg.edits[-1][0].startswith("❌ Ошибка поиска:")


def test_run_web_search_finalize_edit_fail(monkeypatch):
    _enable(monkeypatch)
    answer = _seed_answer(text="контекст")

    async def fake_search(query, **kwargs):
        raise RuntimeError("search down")

    monkeypatch.setattr("services.web_search.search_web", fake_search)

    class BoomMessage(FakeMessage):
        async def edit_text(self, text, parse_mode=None, reply_markup=None):
            raise RuntimeError("edit fail")

    asyncio.run(ab._run_web_search_finalize(
        4242, BoomMessage().edit_text, answer, "запрос"))


# ---------- cb_ab_web_edit ----------


def test_cb_ab_web_edit_no_answer(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="ab_web_edit:nope")
    asyncio.run(ab.cb_ab_web_edit(cb))
    assert cb.answered == [(None, None), ("Сессия истекла. Откройте заново.", True)]


def test_cb_ab_web_edit_success(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    answer = _seed_answer(text="текст")
    cb = FakeCb(data="ab_web_edit:abcd")
    asyncio.run(ab.cb_ab_web_edit(cb))
    assert cb.message.edits[-1][0] == "✏️ Введите свой запрос для поиска:"
    assert sh._pending_mcp_input.get(4242) == "ab_web_query:abcd"
    assert answer.ctx["_await_query"] is True
    sh.fsm.pop_data(4242, "_pending_mcp_input")


# ---------- run_web_search_with_query ----------


def test_run_web_search_with_query_no_answer(monkeypatch):
    _enable(monkeypatch)
    msg = FakeMessage()
    asyncio.run(ab.run_web_search_with_query(4242, msg, "nope", "запрос"))
    assert msg.edits[-1][0] == "❌ Сессия поиска истекла. Начните заново."


def test_run_web_search_with_query_success(monkeypatch):
    _enable(monkeypatch)
    answer = _seed_answer(text="текст")
    captured = []

    async def fake_finalize(uid, edit_func, a, q):
        captured.append((uid, a, q))

    monkeypatch.setattr(ab, "_run_web_search_finalize", fake_finalize)
    msg = FakeMessage()
    asyncio.run(ab.run_web_search_with_query(4242, msg, "abcd", "  новый запрос "))
    assert msg.edits[0][0] == "🌐 Ищу в интернете..."
    assert answer.ctx["web_query"] == "новый запрос"
    assert captured == [(4242, answer, "новый запрос")]


# ---------- cb_ab_sv ----------


def test_cb_ab_sv_no_answer(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="ab_sv:nope")
    asyncio.run(ab.cb_ab_sv(cb))
    assert cb.answered == [(None, None), ("Сессия истекла. Откройте заново.", True)]


def test_cb_ab_sv_success(monkeypatch):
    _enable(monkeypatch)
    _seed_answer(text="текст")
    cb = FakeCb(data="ab_sv:abcd")
    asyncio.run(ab.cb_ab_sv(cb))
    assert cb.message.edits[-1][0] == "💾 <b>Куда сохранить?</b>"
    assert _kb_data(cb.message.edits[-1][2]) == [
        "ab_sv_p:abcd", "ab_sv_n:abcd", "ab_back:abcd",
    ]


# ---------- cb_ab_sv_palace ----------


def test_cb_ab_sv_palace_no_answer(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="ab_sv_p:nope")
    asyncio.run(ab.cb_ab_sv_palace(cb))
    assert cb.answered == [(None, None), ("Сессия истекла. Откройте заново.", True)]


def test_cb_ab_sv_palace_success(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    _seed_answer(text="текст для дворца")
    captured = []

    async def fake_wings(edit_func, uid):
        captured.append((edit_func, uid))

    monkeypatch.setattr("handlers.palace.save._show_save_wings", fake_wings)
    cb = FakeCb(data="ab_sv_p:abcd")
    asyncio.run(ab.cb_ab_sv_palace(cb))
    assert captured == [(cb.message.edit_text, 4242)]
    assert sh._save_state.get(4242) == {"text": "текст для дворца", "mode": "full"}
    sh.fsm.pop_data(4242, "_save_state")


# ---------- cb_ab_sv_notes ----------


def test_cb_ab_sv_notes_no_answer(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="ab_sv_n:nope")
    asyncio.run(ab.cb_ab_sv_notes(cb))
    assert cb.answered == [(None, None), ("Сессия истекла. Откройте заново.", True)]


def test_cb_ab_sv_notes_success(monkeypatch, tmp_path):
    _enable(monkeypatch)
    monkeypatch.setattr(ab, "NOTES_DIR", str(tmp_path))
    _seed_answer(text="моя заметка")
    cb = FakeCb(data="ab_sv_n:abcd")
    asyncio.run(ab.cb_ab_sv_notes(cb))
    files = list(tmp_path.glob("notes_*.md"))
    assert len(files) == 1
    assert "моя заметка" in files[0].read_text()
    assert cb.message.edits[-1][0].startswith("✅ Сохранено в")


def test_cb_ab_sv_notes_error(monkeypatch, tmp_path):
    _enable(monkeypatch)
    monkeypatch.setattr(ab, "NOTES_DIR", str(tmp_path))
    monkeypatch.setattr(ab, "os", SimpleNamespace(
        makedirs=lambda *a, **k: 1 / 0, path=__import__("os").path,
    ))
    _seed_answer(text="моя заметка")
    cb = FakeCb(data="ab_sv_n:abcd")
    asyncio.run(ab.cb_ab_sv_notes(cb))
    assert cb.message.edits[-1][0].startswith("❌ Ошибка сохранения:")


# ---------- not allowed ----------


@pytest.mark.parametrize("prefix,handler", [
    ("ab_pg_noop", "cb_ab_pg_noop"),
    ("ab_pg", "cb_ab_page"),
    ("ab_back", "cb_ab_back"),
    ("ab_ai_m", "cb_ab_ai_run"),
    ("ab_ai", "cb_ab_ai"),
    ("ab_web_go", "cb_ab_web_go"),
    ("ab_web_edit", "cb_ab_web_edit"),
    ("ab_web", "cb_ab_web"),
    ("ab_sv_p", "cb_ab_sv_palace"),
    ("ab_sv_n", "cb_ab_sv_notes"),
    ("ab_sv", "cb_ab_sv"),
])
def test_action_bar_not_allowed(monkeypatch, prefix, handler):
    _enable(monkeypatch)
    data = "ab_pg_noop" if prefix == "ab_pg_noop" else f"{prefix}:abcd"
    cb = FakeCb(uid=999, data=data)
    asyncio.run(getattr(ab, handler)(cb))
    assert cb.answered == [("❌ Нет доступа", True)]


# ---------- edge coverage ----------


def test_paginate_trailing_whitespace_consumed():
    assert ab.paginate("b" * 100 + " " * 3, 100) == ["b" * 100]


def test_cb_ab_page_edit_error(monkeypatch):
    _enable(monkeypatch)
    answer = _seed_answer(text="первый\n\nвторой")
    answer.pages = ["первый", "второй"]

    class BoomMessage(FakeMessage):
        async def edit_text(self, text, parse_mode=None, reply_markup=None):
            raise RuntimeError("edit fail")

    cb = FakeCb(data="ab_pg:abcd:1", message=BoomMessage())
    asyncio.run(ab.cb_ab_page(cb))
    assert answer.page == 1


@pytest.mark.parametrize("handler", [
    ab.cb_ab_web, ab.cb_ab_web_go, ab.cb_ab_web_edit,
    ab.cb_ab_sv, ab.cb_ab_sv_palace, ab.cb_ab_sv_notes,
])
def test_cb_no_data_guard(monkeypatch, handler):
    _enable(monkeypatch)
    cb = FakeCb()
    asyncio.run(handler(cb))
    assert cb.answered == [(None, None)]


class TestActionBarMUTANTTexts:
    def test_build_action_bar_agent_button_exact_text(self):
        from handlers.palace.action_bar import build_action_bar
        from handlers.palace.action_bar import Answer

        answer = Answer(
            sid="s1", text="text", pages=["text"], title="", ctx={},
        )
        kb = build_action_bar(answer, 0)
        rows = kb.export()
        flat = [btn.text for row in rows for btn in row]
        assert "🤖 Агент" in flat

    def test_paginate_exact_limit_boundary(self):
        from handlers.palace.action_bar import paginate

        text = "abcdefghi "
        assert paginate(text, limit=10) == ["abcdefghi "]
