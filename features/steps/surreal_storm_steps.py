"""Шаги BDD для features/surreal_storm.feature.

Реализуют сценарии через реальный код services.brainstorm с фейковыми
источниками (search_notes, кэш руководства) и фейковой моделью.
"""
import asyncio
import json

from behave import given, then, when

from services import ai_engine
from services import brainstorm as bs


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
_ORIG_FUJI_DIR = bs._FUJI_GUIDE_DIR
_ORIG_FUJI_NAMES = bs._FUJI_GUIDE_NAMES


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


@when('модель возвращает идею с camera_setup-отговоркой')
def when_model_returns_idea_with_setup_slogan(context):
    raw = json.dumps({
        "ideas": [{"title": "Слоган", "camera_setup": "Просто сюрреализм"}],
    }, ensure_ascii=False)
    try:
        bs.parse_ideas(raw, require_camera_setup=True, require_camera_keywords=True)
        context.error = None
    except ValueError as exc:
        context.error = str(exc)


@when("проверяется сюрреалистичный системный промпт")
def when_check_surreal_prompt(context):
    context.prompt = bs.SURREAL_STORM_SYSTEM_PROMPT
    context.sampling = bs.storm_sampling_params("surreal")


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


@when("модель возвращает идеи с полем description (место, предметы, образ)")
def when_model_returns_ideas_with_description(context):
    raw = json.dumps({
        "ideas": [
            {
                "title": "Сонный вокзал",
                "description": "Пустой вокзал в 3 часа ночи, чемоданы без "
                               "владельцев, стрелки часов назад.",
                "reason": "время замерло",
                "camera_setup": "ACROS, тени -2",
                "steps": "снять длинной выдержкой",
            }
        ],
    }, ensure_ascii=False)
    context.ideas = bs.parse_ideas(raw, require_camera_setup=True)


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


@then("промпт требует минимум три семейства приёмов, а не только мультиэкспозицию")
def then_prompt_requires_diverse_techniques(context):
    assert "МИНИМУМ три разных" in context.prompt
    assert "не должна быть единственным" in context.prompt


@then("промпт запрещает настраиваемые параметры для приёма «Расширенный фильтр»")
def then_prompt_blocks_settings_for_advanced_filter(context):
    assert "Расширенный фильтр" in context.prompt
    assert "Advanced Filter" in context.prompt
    assert "Toy Camera" in context.prompt and "Pop Color" in context.prompt
    assert "ADV" in context.prompt
    assert "НАСТРОЙКА ПРИВОДА" in context.prompt
    assert "ДОП. НАСТРОЙКА ФИЛЬТРА" in context.prompt
    for blocked in ("имитацию плёнки", "Тоновую кривую", "Баланс белого"):
        assert blocked in context.prompt
    assert "полный набор параметров" in context.prompt


@then("промпт требует описание образа (место, предметы) с критериями приёмки")
def then_prompt_requires_description_and_criteria(context):
    assert "description" in context.prompt
    assert "место" in context.prompt and "предметы" in context.prompt
    assert "пошаговый план" in context.prompt
    assert "Критерии приёмки" in context.prompt


@then('пользователь видит блок "🎨 Образ" с местом и предметами')
def then_see_description_block(context):
    text = bs.format_surreal_ideas_text("ночные сны", context.ideas)
    assert "🎨" in text and "<b>Образ:</b>" in text
    assert "вокзал в 3 часа ночи" in text
    assert "чемоданы без владельцев" in text


@then("для сюрреалистичного штурма заданы креативные параметры выборки")
def then_surreal_sampling_creative(context):
    assert context.sampling["temperature"] >= 0.9
    assert context.sampling["top_p"] >= 0.9
    assert 0.4 <= context.sampling["frequency_penalty"] <= 0.7


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
    # Восстанавливаем оригинальные настройки гайда после мок-теста
    bs._FUJI_GUIDE_DIR = _ORIG_FUJI_DIR
    bs._FUJI_GUIDE_NAMES = _ORIG_FUJI_NAMES
    bs.reset_fuji_guide_cache()


@then("промпт включает четыре стиля: Сюрреализм, Пиктореализм, Экспрессионизм и Импрессионизм")
def then_prompt_includes_four_styles(context):
    for s in ("Сюрреализм", "Пиктореализм", "Экспрессионизм", "Импрессионизм"):
        assert s in context.prompt, f"Стиль {s} отсутствует в промпте"


@then("промпт требует обязательное правило триады стилей")
def then_prompt_requires_triad_rule(context):
    assert "ОБЯЗАТЕЛЬНОЕ ПРАВИЛО ТРИАДЫ СТИЛЕЙ" in context.prompt
    assert "МИНИМУМ ТРИ стиля" in context.prompt


@then('руководство FUJI_XT4_CREATIVE_GUIDE.md содержит раздел "{section}"')
def then_guide_has_section(context, section):
    guide = bs._load_fuji_guide()
    assert section in guide, f"Раздел {section} не найден в руководстве"


@then("в контексте присутствуют блоки gear и mechanics")
def then_context_has_gear_and_mechanics(context):
    assert "gear" in context.ctx and context.ctx["gear"], "Блок gear отсутствует"
    assert "mechanics" in context.ctx and context.ctx["mechanics"], "Блок mechanics отсутствует"


@then("блок gear содержит доступную камеру и оптику")
def then_gear_has_camera_and_optics(context):
    gear_text = context.ctx["gear"]
    assert "Камеры" in gear_text
    assert "Fujifilm X-T4" in gear_text
    assert "Объективы" in gear_text


@then("блок mechanics содержит рецепт акварельной лессировки")
def then_mechanics_has_watercolor(context):
    mech_text = context.ctx["mechanics"]
    assert "Акварельная лессировка" in mech_text or "микро-ICM" in mech_text


@given('пользователь запрашивает штурм в режиме fusion по теме "{topic}"')
def given_fusion_storm_request(context, topic):
    context.fusion_topic = topic


@when("генерируется триада стилистического синтеза")
def when_triad_generated(context):
    from services.style_fusion import generate_style_triad
    context.triad = generate_style_triad(theme=context.fusion_topic)


@then("триада содержит ровно три уникальных стиля из четырёх")
def then_triad_has_three_unique_styles(context):
    styles = context.triad.styles()
    assert len(styles) == 3
    assert len(set(styles)) == 3
    for s in styles:
        assert s in ("Сюрреализм", "Пиктореализм", "Экспрессионизм", "Импрессионизм")


@then("модель возвращает концепт-проект с пошаговым планом съёмки и физикой действия")
def then_model_returns_fusion_concept(context):
    import json
    from services.style_fusion import parse_fusion_concepts

    fake_payload = {
        "projects": [
            {
                "title": "Сон о золотой листве",
                "triad": context.triad.to_dict(),
                "manifesto": "Слияние онейризма и импрессионистической вибрации",
                "scene_description": "Пруд в парке с плавающими листьями клена",
                "lighting_setup": "Мягкий контровой свет заката",
                "camera_setup": {
                    "Приём съёмки": "Мультиэкспозиция (3 кадра)",
                    "Режим мультиэкспозиции": "Тёмный",
                    "Выдержка": '1/6"',
                    "Диафрагма": "f/8",
                },
                "shooting_action": "Микро-тремор рук 1 мм",
                "gear_recipe": {"camera": "Fujifilm X-T4", "lens": "Гелиос 44-2"},
                "shooting_steps": [
                    "Шаг 1: Фокус на водную гладь",
                    "Шаг 2: Включить режим Тёмный",
                    "Шаг 3: Снять серию с рук",
                ],
            }
        ]
    }
    concepts = parse_fusion_concepts(json.dumps(fake_payload))
    assert len(concepts) == 1
    assert concepts[0].shooting_action == "Микро-тремор рук 1 мм"
    assert len(concepts[0].shooting_steps) == 3


@given("в базе заметок есть две контрастные заметки")
def given_two_contrasting_notes(context):
    context.notes_for_bridge = [
        {"id": "n1", "name": "Квантовая суперпозиция", "folder": "Наука",
         "preview": "Теория кубитов"},
        {"id": "n2", "name": "Сосновый бор на закате", "folder": "Природа",
         "preview": "Аромат хвои", "_similarity": 0.32},
    ]


@when("строится ассоциативный мост Serendipity")
def when_serendipity_bridge_built(context):
    from services.brainstorm import format_serendipity_bridge

    n1, n2 = context.notes_for_bridge
    context.bridge_text = format_serendipity_bridge(n1, n2)


@then("мост содержит оба концепта и семантический контраст")
def then_bridge_has_both_concepts(context):
    assert "Квантовая суперпозиция" in context.bridge_text
    assert "Сосновый бор на закате" in context.bridge_text
    assert "32%" in context.bridge_text
    assert "<!--" not in context.bridge_text


@then(
    'концепт-проект успешно экспортируется в Apple Notes '
    'в папку "{folder}" со статусом "{status}"'
)
def then_concept_exports_to_apple_notes(context, folder, status):
    from unittest.mock import patch
    from services.style_fusion import (
        FusedPhotoConcept,
        StyleAssignment,
        StyleTriad,
        export_concept_to_apple_notes,
        format_concept_for_apple_notes,
    )

    triad = StyleTriad(
        narrative=StyleAssignment(role="narrative", style="Сюрреализм"),
        lighting=StyleAssignment(role="lighting", style="Экспрессионизм"),
        optics=StyleAssignment(role="optics", style="Импрессионизм"),
    )
    concept = FusedPhotoConcept(
        title="Квантовая хвоя",
        triad=triad,
        camera_setup={"Выдержка": "1/6s"},
        shooting_action="Поворот призмы",
        shooting_steps=["1. Настройка", "2. Съёмка"],
    )

    title, body = format_concept_for_apple_notes(concept)
    assert status in title
    assert status in body

    with patch("services.apple_notes.ensure_folder", return_value=True) as mock_ensure:
        with patch(
            "services.apple_notes.create_note", return_value="x-coredata://note-42",
        ) as mock_cr:
            note_id = export_concept_to_apple_notes(concept, folder=folder)

    assert note_id == "x-coredata://note-42"
    mock_ensure.assert_called_once_with(folder)
    mock_cr.assert_called_once()
    assert mock_cr.call_args[1]["folder"] == folder
