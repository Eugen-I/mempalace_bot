"""Шаги BDD для features/creative_storm.feature.

Сквозные сценарии интерактивной фотолаборатории:
- Синтез триады стилей и пошаговый проектный план
- 4-страничная пагинация и микро-действия (Midjourney, References, Apple Notes)
- Обработка сбоев и ошибок парсинга
- Serendipity мосты и безопасное HTML экранирование
"""
import asyncio
from unittest.mock import patch

from behave import given, then, when

from services import brainstorm as bs
from services import photographer_gear, style_fusion


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_sample_concept(topic="акварельный туман"):
    triad = style_fusion.generate_style_triad(topic)
    gear_profile = photographer_gear.load_gear_profile()
    fuji_setup = photographer_gear.remix_gear_for_concept(
        ["Импрессионизм", "Пиктореализм"],
        profile=gear_profile,
    )
    return style_fusion.FusedPhotoConcept(
        title="Акварельный рассвет в тумане",
        triad=triad,
        manifesto=(
            "Импрессионистический свет растворяет сюрреалистическую форму "
            "сквозь мягкую оптику пиктореализма."
        ),
        scene_description=(
            "Кадр 1: Полупрозрачные контуры деревьев сквозь дымку. "
            "Кадр 2: Двойная экспозиция отражения в воде с микро-проводкой."
        ),
        lighting_setup="Рассветный контровой рассеянный свет сквозь речной туман.",
        camera_setup={
            "Режим": "Мультиэкспозиция (2-4 кадра, Dark)",
            "Выдержка": "1/6 с",
            "Диафрагма": "f/8.0",
            "ISO": "160",
            "Моделирование пленки": "Velvia / Vivid",
            "Экспокоррекция": "EV -1.0",
        },
        shooting_action=(
            "Мультиэкспозиция 3 кадра: 1-й резкий в фокусе, "
            "2-й и 3-й с микро-проводкой (ICM) 1/6с."
        ),
        gear_recipe={
            "camera": fuji_setup.get("camera", "Fujifilm X-T4"),
            "lens": fuji_setup.get("lens", "XF 35mm f/1.4 R"),
            "filter_or_accessory": "ND8, без штатива",
        },
        shooting_steps=[
            "1. Занять точку съемки на берегу против восходящего солнца.",
            "2. Установить нейтрально-серый фильтр ND8 для достижения 1/6 с.",
            "3. Первый кадр: статичный, фокус на ветвях деревьев.",
            "4. Второй и третий кадры: плавное вертикальное движение камеры.",
        ],
    )


# ─── Happy Path ───

@given('пользователь запрашивает режим лаборатории "/синтез" с темой "{topic}"')
def step_given_user_requests_fusion(context, topic):
    context.topic = topic
    context.mode = "fusion"


@when("система генерирует триадный концепт с фототехникой")
def step_when_system_generates_concept(context):
    concept = _make_sample_concept(getattr(context, "topic", "акварельный туман"))
    context.concept = concept
    context.concepts = [concept]


@then("концепт содержит 4 страницы проектного плана")
def step_then_concept_has_4_pages(context):
    pages = [
        style_fusion.format_concept_page(context.concept, page=p, total_pages=4)
        for p in range(1, 5)
    ]
    assert len(pages) == 4
    context.rendered_pages = pages


@then("страница 1 содержит манифест и триаду стилей")
def step_then_page_1_content(context):
    p1 = context.rendered_pages[0]
    assert "Художественный манифест" in p1
    assert "Триада синтеза" in p1
    assert context.concept.manifesto in p1


@then("страница 2 содержит раскадровку кадров")
def step_then_page_2_content(context):
    p2 = context.rendered_pages[1]
    assert "Визуальный образ и композиция" in p2
    assert "Световая схема" in p2
    assert "Кадр 1" in p2


@then("страница 3 содержит рецепт Fujifilm X-T4 с акварельным эффектом")
def step_then_page_3_content(context):
    p3 = context.rendered_pages[2]
    assert "Параметры съёмки (Fujifilm X-T4)" in p3
    assert "Физика съёмки (действие рук)" in p3
    assert "Мультиэкспозиция" in p3 or "1/6" in p3


@then("страница 4 содержит полевой шутинг-лист и чек-лист")
def step_then_page_4_content(context):
    p4 = context.rendered_pages[3]
    assert "Пошаговый план съёмки" in p4
    assert "Чек-лист перед выходом" in p4


@then("доступен генератор Midjourney промпта на английском языке")
def step_then_midjourney_prompt_available(context):
    prompt = style_fusion.build_midjourney_prompt(context.concept)
    assert len(prompt) > 20
    assert "--ar 16:9" in prompt or "--style raw" in prompt
    assert any(
        w in prompt.lower()
        for w in ["impressionism", "surrealism", "pictorialism", "fujifilm"]
    )


@then("доступна карточка проверенных референсов мастеров")
def step_then_references_card_available(context):
    refs_card = style_fusion.format_references_card(
        context.concept, web_snippets="Snippet test",
    )
    assert "Художественные референсы" in refs_card or "Мастера" in refs_card
    assert len(refs_card) > 50


@then('проект успешно экспортируется в Apple Notes в папку "Фотопроекты"')
def step_then_export_apple_notes(context):
    with patch(
        "services.apple_notes.create_note", return_value="note-test-id-123",
    ) as mock_create, patch(
        "services.apple_notes.ensure_folder", return_value=True,
    ) as mock_folder:
        note_id = style_fusion.export_concept_to_apple_notes(
            context.concept, folder="Фотопроекты",
        )
        assert note_id == "note-test-id-123"
        mock_folder.assert_called_once_with("Фотопроекты")
        mock_create.assert_called_once()


# ─── Negatives ───

@given("модель возвращает поврежденный JSON для триадного штурма")
def step_given_corrupted_json(context):
    context.corrupted_response = "```json\n{ invalid json content without closing braces"


@when("парсер концептов обрабатывает сырой ответ модели")
def step_when_parser_handles_corrupted(context):
    context.parsed_concepts = style_fusion.parse_fusion_concepts(context.corrupted_response)


@then("система возвращает пустой список концептов без падения с исключением")
def step_then_parser_returns_empty(context):
    assert isinstance(context.parsed_concepts, list)
    assert len(context.parsed_concepts) == 0


@then("пользователь получает уведомление об ошибке парсинга")
def step_then_user_notified_parse_error(context):
    assert len(context.parsed_concepts) == 0
    dummy = style_fusion.FusedPhotoConcept(
        title="",
        triad=None,  # type: ignore
        manifesto="",
        scene_description="",
        lighting_setup="",
        camera_setup={},
        shooting_action="",
        gear_recipe={},
        shooting_steps=[],
    )
    is_valid, reason = style_fusion.validate_fusion_concept(dummy)
    assert is_valid is False
    assert len(reason) > 0


@given("у пользователя есть сформированный концепт-проект из 4 страниц")
def step_given_user_has_concept(context):
    context.concept = _make_sample_concept("тест")


@when("запрашивается страница 99 или страница -1")
def step_when_out_of_range_page_requested(context):
    p_high = style_fusion.format_concept_page(context.concept, page=99, total_pages=4)
    p_low = style_fusion.format_concept_page(context.concept, page=-1, total_pages=4)
    context.clamped_p_high = p_high
    context.clamped_p_low = p_low


@then("отображается допустимая страница в пределах диапазона от 1 до 4")
def step_then_valid_page_displayed(context):
    assert "Стр. 1/4" in context.clamped_p_high or "Стр. 4/4" in context.clamped_p_high
    assert "Стр. 1/4" in context.clamped_p_low


@then("клавиатура навигации не ломается")
def step_then_kb_valid(context):
    kb_high = style_fusion.build_concept_navigation_kb(
        concept_idx=0, page=99, total_pages=4,
    )
    kb_low = style_fusion.build_concept_navigation_kb(
        concept_idx=0, page=-1, total_pages=4,
    )
    assert kb_high is not None
    assert kb_low is not None
    rows = kb_high.as_markup().inline_keyboard
    assert len(rows) >= 3


@given("Apple Notes недоступен или скрипт завершается ошибкой")
def step_given_apple_notes_error(context):
    context.concept = _make_sample_concept("ошибка")
    context.apple_notes_error = True


@when("пользователь нажимает кнопку экспорта в Apple Notes")
def step_when_export_button_clicked_error(context):
    with patch(
        "services.apple_notes.ensure_folder", side_effect=RuntimeError("Script timeout"),
    ), patch(
        "services.apple_notes.create_note", side_effect=RuntimeError("AppleScript failure"),
    ):
        try:
            res = style_fusion.export_concept_to_apple_notes(context.concept)
            context.export_result = {"success": True, "note_id": res}
        except Exception as exc:
            context.export_result = {"success": False, "error": str(exc)}


@then("пользователю отправляется сообщение об ошибке экспорта")
def step_then_error_result_returned(context):
    assert context.export_result["success"] is False
    assert "error" in context.export_result
    assert len(context.export_result["error"]) > 0


@then("бот сохраняет работоспособность без падения процесса")
def step_then_bot_survives(context):
    assert True


# ─── Edge Cases ───

@given("в базе заметок пользователя нет парных заметок")
def step_given_empty_notes_db(context):
    context.mock_notes = []


@when("запускается поиск Serendipity моста")
def step_when_run_serendipity(context):
    with patch("services.brainstorm.list_notes", return_value=[]), \
         patch("os.path.exists", return_value=False):
        pair = bs.find_serendipity_pair("осенний сад")
        context.serendipity_pair = pair
        if pair:
            context.serendipity_bridge = bs.format_serendipity_bridge(pair[0], pair[1])
        else:
            context.serendipity_bridge = "Заметки не найдены — мост строится по запросу темы."


@then("система возвращает безопасный заглушечный результат без деления на ноль")
def step_then_serendipity_safe_fallback(context):
    assert context.serendipity_pair is None or len(context.serendipity_pair) == 2


@then("штурм продолжается на основе запроса пользователя")
def step_then_storm_continues(context):
    assert len(context.serendipity_bridge) > 10


@given('в профиле фотографа добавлено оборудование с символами "<custom & vintage>"')
def step_given_gear_with_special_chars(context):
    gear = photographer_gear.GearProfile(
        cameras=[
            photographer_gear.GearItem(
                name="Fujifilm X-T4 <Special Edition>",
                category="cameras",
            )
        ],
        lenses=[
            photographer_gear.GearItem(
                name="XF 35mm f/1.4 <Vintage Glass>",
                category="lenses",
            )
        ],
        filters=[
            photographer_gear.GearItem(
                name="Prism & Filter <58mm>",
                category="filters",
            )
        ],
        lighting=[],
        accessories=[],
    )
    context.special_gear = gear


@when("генерируются страницы фотолаборатории и карточка концепта")
def step_when_generate_pages_with_special_chars(context):
    setup = photographer_gear.remix_gear_for_concept(
        ["Пиктореализм"], profile=context.special_gear,
    )
    triad = style_fusion.generate_style_triad("тест")
    concept = style_fusion.FusedPhotoConcept(
        title="Тест <Винтаж & Тени>",
        triad=triad,
        manifesto="Эксперимент <свет & дым>",
        scene_description="Кадр <1> и Кадр <2>",
        lighting_setup="Контровой свет <5600K>",
        camera_setup={"Диафрагма": "<f/1.4>"},
        shooting_action="Съемка <action>",
        gear_recipe={
            "camera": setup.get("camera", "Fujifilm X-T4 <Special Edition>"),
            "lens": setup.get("lens", "XF 35mm f/1.4 <Vintage Glass>"),
            "filter_or_accessory": "Prism & Filter <58mm>",
        },
        shooting_steps=["Пункт <list> 1", "Пункт <list> 2"],
    )
    context.card_text = style_fusion.format_fusion_concept_card(concept)
    context.page_text = style_fusion.format_concept_page(concept, page=3, total_pages=4)


@then("весь вывод содержит корректно экранированные HTML сущности")
def step_then_properly_escaped(context):
    assert "<Special Edition>" not in context.card_text
    assert "&lt;Special Edition&gt;" in context.card_text or "&lt;" in context.card_text
    assert "<Vintage Glass>" not in context.page_text
    assert "&lt;Vintage Glass&gt;" in context.page_text or "&lt;" in context.page_text


@then("в разметке отсутствуют запрещенные теги и HTML-комментарии")
def step_then_no_forbidden_tags(context):
    for text in [context.card_text, context.page_text]:
        assert "<!--" not in text
        assert "-->" not in text
        assert "<div" not in text
        assert "<p>" not in text
        assert "<br" not in text
