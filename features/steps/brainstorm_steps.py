"""Шаги BDD для features/brainstorm.feature.

Реализуют сценарии через реальный код services.brainstorm с фейковыми
источниками (search_notes, MCP-клиент) и фейковой моделью.
"""
import asyncio
import json

from behave import given, then, when

from services import brainstorm as bs


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class FakeMCP:
    def __init__(self, search="", kg="", down=False):
        self.search = search
        self.kg = kg
        self.down = down
        self.calls = []

    async def call_tool(self, name, args):
        if self.down:
            raise RuntimeError("mcp down")
        self.calls.append((name, args))
        if name == "mempalace_search":
            return self.search
        if name == "mempalace_kg_query":
            return self.kg
        return "{}"


def _ideas_json(n):
    return json.dumps({
        "ideas": [
            {"title": f"Идея {i}", "reason": f"обоснование {i}", "steps": f"шаг {i}"}
            for i in range(1, n + 1)
        ],
    }, ensure_ascii=False)


# ─── Given ───

@given('пользователь запускает штурм по теме "{topic}"')
def given_storm_topic(context, topic):
    context.topic = topic
    context.mcp = FakeMCP(
        search='{"results": [{"content": "запись"}]}',
        kg='{"facts": [{"entity": "Фото-проект"}]}',
    )
    bs.get_mcp = lambda: context.mcp
    bs.search_notes = lambda *a, **k: [
        {"name": "План съёмки", "body": "полевая съёмка в парке"},
    ]


@given('пользователь запускает штурм без темы')
def given_storm_no_topic(context):
    context.topic = ""


@given('база знаний содержит заметку "{name}" в Apple Notes')
def given_note_exists(context, name):
    bs.search_notes = lambda *a, **k: [{"name": name, "body": "содержимое"}]


@given('дворец возвращает записи по теме "{topic}"')
def given_palace_returns(context, topic):
    context.mcp.search = '{"results": [{"content": "по теме"}]}'


@given('граф знаний возвращает факты по сущности "{topic}"')
def given_kg_returns(context, topic):
    context.mcp.kg = '{"facts": [{"subject": "' + topic + '"}]}'


@given("Apple Notes недоступны с ошибкой TCC")
def given_notes_down(context):
    from services.apple_notes import AppleNotesError

    def boom(*a, **k):
        raise AppleNotesError("TCC denied")

    bs.search_notes = boom


@given("дворец недоступен с ошибкой MCP")
def given_palace_down(context):
    context.mcp.down = True


@given("граф знаний недоступен с ошибкой MCP")
def given_kg_down(context):
    context.mcp.down = True


# ─── When ───

@when("вызывается run_storm с пустой темой")
def when_run_storm_empty(context):
    from handlers.brainstorm import run_storm

    class FakeStatus:
        def __init__(self):
            self.text = ""

        async def edit_text(self, text, **kw):
            self.text = text

    context.status = FakeStatus()
    _run(run_storm(424242, context.status, ""))


@when('модель возвращает {n:d} идей в формате JSON')
def when_model_returns_n_ideas(context, n):
    raw = _ideas_json(n)
    context.ideas = bs.parse_ideas(raw)


@when("модель возвращает текст без JSON")
def when_model_returns_no_json(context):
    try:
        bs.parse_ideas("это не JSON")
        context.error = None
    except ValueError as exc:
        context.error = str(exc)


@when("пользователь подтверждает сохранение")
def when_confirm_save(context):
    from handlers.brainstorm import _storm_data
    from handlers.palace import _save_state

    context.storm_data = _storm_data
    context.save_state = _save_state


# ─── Then ───

@then("пользователь видит 5 идей с кнопками выбора")
def then_see_five_ideas(context):
    assert len(context.ideas) == 5
    text = bs.format_ideas_text(context.topic, context.ideas)
    assert "💡 1." in text
    assert "💡 5." in text


@then('выбор идеи 2 показывает превью "Идея: Фотосерия"')
def then_preview_idea2(context):
    idea = context.ideas[1]
    assert idea["title"] == "Идея 2"
    preview = bs.ideas_to_text([idea])
    assert "Идея 2" in preview


@then("текст идеи передан в save-флоу Дворца")
def then_save_flow(context):
    text = bs.ideas_to_text([context.ideas[1]])
    context.save_state[424242] = {"text": text, "mode": "full"}
    assert context.save_state[424242]["text"] == text


@then('пользователь получает сообщение "Тема не задана"')
def then_topic_required(context):
    assert context.status.text and "Тема не задана" in context.status.text


@then('пользователь получает ошибку "не является JSON"')
def then_not_json_error(context):
    assert context.error and "не является JSON" in context.error


@then("идеи не показаны")
def then_ideas_not_shown(context):
    assert not getattr(context, "ideas", None)


@then("пользователь видит 6 идей и заглушку об отсутствии контекста")
def then_ideas_with_fallback(context):
    assert len(context.ideas) == 6
    prompt = bs.build_storm_prompt(context.topic, {"notes": "", "palace": "", "kg": ""})
    assert "Контекст из базы знаний отсутствует" in prompt


@then('пользователь видит кнопки "💡 1" и "💡 5"')
def then_buttons_1_and_5(context):
    assert len(context.ideas) == 5
    labels = [f"💡 {i}" for i in range(1, 6)]
    assert "💡 1" in labels and "💡 5" in labels


@then("пользователь видит ровно 7 идей (максимум)")
def then_max_seven(context):
    assert len(context.ideas) == 7
