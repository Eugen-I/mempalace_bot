"""Шаги BDD для features/surreal_storm.feature.

Реализуют сценарии через реальный код services.brainstorm с фейковыми
источниками (search_notes, кэш руководства) и фейковой моделью.
"""
import asyncio
import json

from behave import given, then, when

from services import brainstorm as bs
from services import ai_engine


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeStatus:
    def __init__(self):
        self.edits = []
        self.cards = []

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.cards.append(text)
        return self


def _fake_coro(value):
    async def _run_coro():
        return value
    return _run_coro()


_ORIG_LOAD_FUJI = bs._load_fuji_guide


# ─── Given ───

@given('пользователь в режиме заметок запрашивает "{text}"')
def given_notes_user_requests(context, text):
    from handlers.notes_agent import _extract_storm_topic

    context.request = text
    context.topic = _extract_storm_topic(text)


@given('заметка "{name}" содержит snippet "{snippet}"')
def given_note_with_snippet(context, name, snippet):
    bs.search_notes = lambda *a, **k: [
        {"name": name, "snippet": snippet},
    ]


@given('руководство FUJI_XT4_CREATIVE_GUIDE.md содержит раздел "{section}"')
def given_guide_with_section(context, section):
    bs.reset_fuji_guide_cache()
    bs._load_fuji_guide = lambda: f"ГАЙД...\n## {section}\n контент"


@given("руководство FUJI_XT4_CREATIVE_GUIDE.md доступно на диске")
def given_guide_available(context):
    class CountingPath:
        def __init__(self):
            self.reads = 0

        def read_text(self, encoding=None):
            self.reads += 1
            return "ГАЙД X-T4"

    class FakeDir:
        def __init__(self):
            self.path = CountingPath()

        def __truediv__(self, name):
            return self.path

    context.guide_dir = FakeDir()
    bs.reset_fuji_guide_cache()
    bs._FUJI_GUIDE_DIR = context.guide_dir
    bs._FUJI_GUIDE_NAMES = ("guide.md",)
    bs._load_fuji_guide = _ORIG_LOAD_FUJI


# ─── When ───

@when("модель возвращает 6 сюрреалистичных идей с полем camera_setup")
def when_model_returns_surreal_ideas(context):
    raw = json.dumps({
        "ideas": [
            {
                "title": f"Идея {i}",
                "reason": f"образ {i}",
                "camera_setup": f"ACROS, R+9 B-9, Зерно Сильное (идея {i})",
                "steps": f"шаг {i}",
            }
            for i in range(1, 7)
        ],
    }, ensure_ascii=False)
    context.ideas = bs.parse_ideas(raw, require_camera_setup=True)


@when("модель возвращает идею без поля camera_setup")
def when_model_returns_idea_without_camera_setup(context):
    raw = json.dumps({
        "ideas": [{"title": "Без настроек", "reason": "r"}],
    }, ensure_ascii=False)
    try:
        bs.parse_ideas(raw, require_camera_setup=True)
        context.error = None
    except ValueError as exc:
        context.error = str(exc)


@when("вызывается сюрреалистичный штурм с пустой темой")
def when_run_surreal_empty_topic(context):
    from handlers.notes_agent import run_surreal_storm

    context.status = _FakeStatus()
    _run(run_surreal_storm(424242, context.status, ""))


@when("модель недоступна с ошибкой")
def when_model_down(context):
    async def boom(engine, model, msgs):
        raise RuntimeError("ollama down")

    ai_engine.get_ai_response_async = boom
    ai_engine.get_current_ai = lambda: ("fake", "model")

    from handlers.notes_agent import run_surreal_storm

    context.status = _FakeStatus()
    _run(run_surreal_storm(424242, context.status, "море"))


@when("собирается контекст в режиме surreal")
def when_collect_surreal_context(context):
    bs.get_mcp = lambda: None
    context.ctx = _run(bs.collect_context(context.topic or "сны", mode="surreal"))


@when("руководство запрашивается дважды")
def when_guide_requested_twice(context):
    context.first = bs._load_fuji_guide()
    context.second = bs._load_fuji_guide()


# ─── Then ───

@then('пользователь видит карточки "💡 Идея" с заголовком "Сюрреалистичный штурм"')
def then_see_surreal_cards(context):
    text = bs.format_surreal_ideas_text("ночные сны", context.ideas)
    assert "🌪" in text and "Сюрреалистичный штурм" in text
    assert "💡" in text and "Идея 1" in text and "Идея 6" in text


@then('каждая карточка содержит блок "📷 Настройки камеры" в теге code')
def then_card_has_camera_setup(context):
    for idea in context.ideas:
        assert "camera_setup" in idea and idea["camera_setup"]
    text = bs.format_surreal_ideas_text("ночные сны", context.ideas)
    assert "📷" in text
    assert "<code>ACROS" in text and "</code>" in text


@then("контекст для модели содержит полный текст руководства")
def then_prompt_contains_guide(context):
    ctx = {"notes": "заметка", "guide": "ГАЙД...\n## Комбинации для сюрреализма\n контент"}
    prompt = bs.build_storm_prompt("ночные сны", ctx)
    assert "[Руководство Fujifilm X-T4]" in prompt
    assert "Комбинации для сюрреализма" in prompt


@then('штурм завершается ошибкой "Нет валидных идей"')
def then_no_valid_ideas_error(context):
    assert context.error and "Нет валидных идей" in context.error


@then('пользователь получает сообщение с подсказкой "Укажите тему"')
def then_topic_hint(context):
    assert context.status.edits and "Укажите тему" in context.status.edits[-1]


@then('пользователь получает сообщение "Ошибка штурма"')
def then_storm_error_message(context):
    assert context.status.edits and "Ошибка штурма" in context.status.edits[-1]


@then("в контексте нет источников palace и kg")
def then_no_palace_kg(context):
    assert "palace" not in context.ctx
    assert "kg" not in context.ctx


@then("файл прочитан с диска ровно один раз")
def then_guide_read_once(context):
    assert context.guide_dir.path.reads == 1
    assert context.first == "ГАЙД X-T4"
    assert context.second == "ГАЙД X-T4"
