"""Шаги BDD для ранжирования поиска и кнопок «📄 Читать [N]»."""
import asyncio

from behave import given, then, when

import services.palace_bridge as pb
from handlers.search import cmd_search, search_result_cache

_query_calls = []
_context = {}


def _reset():
    _query_calls.clear()
    _context.clear()
    search_result_cache.clear()
    pb.get_palace_circuit_breaker().reset()


def _run(coro):
    return asyncio.run(coro)


@given('поиск вернул записи: близкую, среднюю и нерелевантную')
def step_hits_mixed(context):
    _reset()
    context.hits = [
        {"distance": 0.1, "bm25_score": 8.0, "text": "близкая запись"},
        {"distance": 0.45, "bm25_score": 2.0, "text": "средняя запись"},
        {"distance": 0.8, "bm25_score": 0.0, "text": "нерелевантная запись"},
    ]


@when("результаты ранжируются")
def step_rank(context):
    context.ranked = pb._rank_hits(context.hits)


@then("первой идёт близкая запись")
def step_first_is_close(context):
    assert context.ranked[0]["text"] == "близкая запись"


@then("нерелевантная запись идёт последней")
def step_irrelevant_last(context):
    assert context.ranked[-1]["text"] == "нерелевантная запись"


@given("в крыле «projects» ничего нет")
def step_wing_empty(context):
    _reset()
    context.wing_empty = True


@when('выполняется поиск «память» в крыле «projects»')
def step_search_wing(context):
    async def fake_api(query, limit=5, wing="", room=""):
        _query_calls.append((query, wing))
        if wing == "projects":
            return {"text": "", "sources": []}
        return {"text": "найдено глобально", "sources": []}

    _context["orig_api"] = pb._search_via_api
    pb._search_via_api = fake_api
    context.result = _run(pb.search_palace_with_sources("память", wing="projects"))


@then('выполняется глобальный поиск «память»')
def step_global_fallback(context):
    assert ("память", "projects") in _query_calls
    assert ("память", "") in _query_calls


@then("результат показывает найденное")
def step_result_shows(context):
    assert context.result[0] == "найдено глобально"
    if "orig_api" in _context:
        pb._search_via_api = _context.pop("orig_api")


@given('две записи: точное слово «квант» и слабая векторная близость')
def step_lexical_vs_vector(context):
    _reset()
    context.hits = [
        {"distance": 0.05, "bm25_score": 1.0, "text": "слабая векторная близость"},
        {"distance": 0.85, "bm25_score": 50.0, "text": "точное слово квант"},
    ]


@then("точное совпадение идёт первой")
def step_lexical_first(context):
    assert context.ranked[0]["text"] == "точное слово квант"


@given("пустой текст запроса")
def step_empty_query(context):
    _reset()
    context.empty_query = True


@when("выполняется поиск")
def step_do_search_empty(context):
    context.result = _run(pb.search_palace_context("   "))


@then("поиск не вызывается")
def step_not_called(context):
    assert context.result == ""


@then("результат пуст")
def step_empty_result(context):
    assert context.result == ""


@given("найденные источники: dreams/коридор и projects/идеи")
def step_sources(context):
    _reset()
    context.sources = [
        {"id": 1, "wing": "dreams", "room": "коридор", "file": "", "score": 0.9},
        {"id": 2, "wing": "projects", "room": "идеи", "file": "", "score": 0.7},
    ]


@when("пользователь выполняет /search сны")
def step_run_cmd_search(context):
    async def fake_search(text, limit=5, wing=""):
        return "Результат по запросу", context.sources

    import handlers.search as search_mod

    _context["orig_search"] = search_mod.search_palace_with_sources
    search_mod.search_palace_with_sources = fake_search

    class Msg:
        def __init__(self):
            self.edited = []
            self.markups = []
            self.text = "/search сны"
            self.from_user = type("U", (), {"id": 424242})()
            self.deleted = False

        async def answer(self, text=None, **kwargs):
            self.edited.append(text or "")
            self.markups.append(kwargs.get("reply_markup"))
            return self

        async def edit_text(self, text, **kwargs):
            self.edited.append(text)
            self.markups.append(kwargs.get("reply_markup"))
            return self

        async def delete(self):
            self.deleted = True

    context.msg = Msg()
    _run(cmd_search(context.msg))


def _labels(msg):
    kb = msg.markups[-1]
    if kb is None:
        return []
    return [b.text for row in kb.inline_keyboard for b in row]


def _datas(msg):
    kb = msg.markups[-1]
    if kb is None:
        return []
    return [b.callback_data for row in kb.inline_keyboard for b in row]


@then('вывод содержит кнопку «Читать [1]»')
def step_btn1(context):
    assert any("Читать [1]" in t for t in _labels(context.msg))


@then('вывод содержит кнопку «Читать [2]»')
def step_btn2(context):
    assert any("Читать [2]" in t for t in _labels(context.msg))


@then("кнопки ведут на p_src:1 и p_src:2")
def step_btns_data(context):
    data = _datas(context.msg)
    assert "p_src:1" in data
    assert "p_src:2" in data


@given("поиск не нашёл ничего")
def step_no_results(context):
    _reset()
    context.sources = []


@when("пользователь выполняет /search несуществующее")
def step_run_cmd_search_empty(context):
    async def fake_search(text, limit=5, wing=""):
        return "", []

    import handlers.search as search_mod

    search_mod.search_palace_with_sources = fake_search

    class Msg:
        def __init__(self):
            self.edited = []
            self.markups = []
            self.text = "/search несуществующее"
            self.from_user = type("U", (), {"id": 424242})()

        async def answer(self, text=None, **kwargs):
            self.edited.append(text or "")
            return self

        async def edit_text(self, text, **kwargs):
            self.edited.append(text)
            return self

        async def delete(self):
            pass

    context.msg = Msg()
    _run(cmd_search(context.msg))


@then('бот отвечает «Ничего не найдено»')
def step_answered(context):
    assert any("Ничего не найдено" in e for e in context.msg.edited)


@then("кнопок нет")
def step_no_buttons(context):
    kb = context.msg.markups[-1] if context.msg.markups else None
    assert kb is None or kb.inline_keyboard == []
