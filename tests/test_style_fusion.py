"""tests/test_style_fusion.py — Unit-тесты для движка стилистического синтеза."""

import json
from unittest.mock import patch

import pytest

from services.brainstorm import (
    collect_context,
    format_fusion_ideas_text,
    ideas_to_text,
    parse_fusion_ideas,
    storm_sampling_params,
    storm_system_prompt,
)
from services.style_fusion import (
    AVAILABLE_STYLES,
    STYLE_ROLE_TRAITS,
    TRIAD_ROLES,
    FusedPhotoConcept,
    StyleAssignment,
    StyleTriad,
    build_concept_navigation_kb,
    build_deepen_system_prompt,
    build_deepen_user_prompt,
    build_fusion_system_prompt,
    build_fusion_user_prompt,
    build_midjourney_prompt,
    export_concept_to_apple_notes,
    format_concept_for_apple_notes,
    format_concept_page,
    format_deepen_card,
    format_fusion_concept_card,
    format_references_card,
    generate_style_triad,
    get_curated_references,
    parse_fusion_concepts,
    validate_fusion_concept,
)


def test_style_definitions_and_traits():
    assert len(AVAILABLE_STYLES) == 4
    for style in ("Сюрреализм", "Пиктореализм", "Экспрессионизм", "Импрессионизм"):
        assert style in AVAILABLE_STYLES
        assert style in STYLE_ROLE_TRAITS
        for role in TRIAD_ROLES:
            assert role in STYLE_ROLE_TRAITS[style]
            assert len(STYLE_ROLE_TRAITS[style][role]) > 10


def test_style_assignment_serialization():
    assign = StyleAssignment(
        role="narrative",
        style="Сюрреализм",
        traits="Онейрический сюжет",
    )
    d = assign.to_dict()
    assert d["role"] == "narrative"
    assert d["style"] == "Сюрреализм"

    restored = StyleAssignment.from_dict(d)
    assert restored.role == assign.role
    assert restored.style == assign.style
    assert restored.traits == assign.traits


def test_style_triad_serialization_and_methods():
    triad = StyleTriad(
        narrative=StyleAssignment(role="narrative", style="Сюрреализм"),
        lighting=StyleAssignment(role="lighting", style="Экспрессионизм"),
        optics=StyleAssignment(role="optics", style="Пиктореализм"),
        rationale="Контраст сна и жесткого света",
    )
    assert triad.styles() == ["Сюрреализм", "Экспрессионизм", "Пиктореализм"]
    assert "Сюрреализм [сюжет]" in triad.summary()
    assert "Экспрессионизм [свет]" in triad.summary()
    assert "Пиктореализм [оптика]" in triad.summary()

    d = triad.to_dict()
    restored = StyleTriad.from_dict(d)
    assert restored.styles() == triad.styles()
    assert restored.rationale == triad.rationale


def test_generate_style_triad_default():
    triad = generate_style_triad()
    styles = triad.styles()
    # Все три стиля обязаны быть уникальными
    assert len(styles) == 3
    assert len(set(styles)) == 3
    for s in styles:
        assert s in AVAILABLE_STYLES
    assert triad.rationale


def test_generate_style_triad_preferred():
    triad = generate_style_triad(preferred_styles=["Импрессионизм", "Сюрреализм", "Экспрессионизм"])
    assert triad.narrative.style == "Импрессионизм"
    assert triad.lighting.style == "Сюрреализм"
    assert triad.optics.style == "Экспрессионизм"


@pytest.mark.parametrize(
    "theme,expected_optics",
    [
        ("осенний парк с листьями и водой", "Импрессионизм"),
        ("акварельный пейзаж у реки", "Импрессионизм"),
        ("портрет в старинном тумане", "Пиктореализм"),
    ],
)
def test_generate_style_triad_heuristics(theme, expected_optics):
    triad = generate_style_triad(theme=theme)
    assert triad.optics.style == expected_optics
    assert len(set(triad.styles())) == 3


def test_fused_photo_concept_serialization():
    triad = generate_style_triad()
    concept = FusedPhotoConcept(
        title="Отражение времени",
        triad=triad,
        manifesto="Изучение зыбкости бытия",
        scene_description="Одинокое зеркало в осеннем лесу",
        lighting_setup="Мягкий рассеянный контровой свет",
        camera_setup={"Выдержка": '1/6"', "Диафрагма": "f/2"},
        shooting_action="Микро-тремор рук при мультиэкспозиции",
        gear_recipe={"camera": "Fujifilm X-T4", "lens": "Гелиос 44-2"},
        shooting_steps=["1. Установить камеру", "2. Сфокусироваться", "3. Сделать 3 кадра"],
    )
    d = concept.to_dict()
    assert d["title"] == "Отражение времени"
    assert d["triad"]["narrative"]["style"] == triad.narrative.style

    restored = FusedPhotoConcept.from_dict(d)
    assert restored.title == concept.title
    assert restored.manifesto == concept.manifesto
    assert restored.camera_setup == concept.camera_setup
    assert len(restored.shooting_steps) == 3


def test_build_fusion_prompts():
    sys_prompt = build_fusion_system_prompt()
    assert "ТРИАДЕ СТИЛЕЙ" in sys_prompt
    assert "narrative" in sys_prompt and "lighting" in sys_prompt and "optics" in sys_prompt
    assert "projects" in sys_prompt
    assert "shooting_action" in sys_prompt
    assert "shooting_steps" in sys_prompt

    triad = generate_style_triad()
    user_prompt = build_fusion_user_prompt(
        topic="Зеркала и тени",
        triad=triad,
        gear_context="[Арсенал]: X-T4",
        mechanics_context="[Банк]: Лессировка",
        notes_context="Заметка про сны",
    )
    assert "Тема творческого штурма: Зеркала и тени" in user_prompt
    assert triad.narrative.style in user_prompt
    assert "[Арсенал]: X-T4" in user_prompt
    assert "[Банк]: Лессировка" in user_prompt
    assert "Заметка про сны" in user_prompt


def test_validate_fusion_concept():
    triad = generate_style_triad()
    good = FusedPhotoConcept(
        title="Валидный концепт",
        triad=triad,
        scene_description="Глубокое описание сцены в лесу с туманом",
        camera_setup={"Выдержка": "1/6s", "Диафрагма": "f/2"},
        shooting_action="Микро-ICM с рук",
        shooting_steps=["Шаг 1: Подготовка", "Шаг 2: Съемка"],
    )
    ok, reason = validate_fusion_concept(good)
    assert ok is True
    assert reason == "OK"

    # Негатив 1: короткое название
    bad_title = FusedPhotoConcept(
        title="X",
        triad=triad,
        camera_setup={"Выдержка": "1/6s", "f": "2"},
        shooting_action="Действие",
        shooting_steps=["Шаг 1", "Шаг 2"],
    )
    ok, _ = validate_fusion_concept(bad_title)
    assert ok is False

    # Негатив 2: меньше 3 уникальных стилей
    bad_triad = StyleTriad(
        narrative=StyleAssignment(role="narrative", style="Сюрреализм"),
        lighting=StyleAssignment(role="lighting", style="Сюрреализм"),
        optics=StyleAssignment(role="optics", style="Сюрреализм"),
    )
    bad_styles = FusedPhotoConcept(
        title="Повтор стилей",
        triad=bad_triad,
        camera_setup={"Выдержка": "1/6s", "f": "2"},
        shooting_action="Действие",
        shooting_steps=["Шаг 1", "Шаг 2"],
    )
    ok, _ = validate_fusion_concept(bad_styles)
    assert ok is False

    # Негатив 3: пустой camera_setup
    bad_camera = FusedPhotoConcept(
        title="Без настроек камеры",
        triad=triad,
        camera_setup={},
        shooting_action="Действие",
        shooting_steps=["Шаг 1", "Шаг 2"],
    )
    ok, _ = validate_fusion_concept(bad_camera)
    assert ok is False

    # Негатив 4: нет шагов съёмки
    bad_steps = FusedPhotoConcept(
        title="Без шагов",
        triad=triad,
        camera_setup={"Выдержка": "1/6s", "f": "2"},
        shooting_action="Действие",
        shooting_steps=[],
    )
    ok, _ = validate_fusion_concept(bad_steps)
    assert ok is False


def test_parse_fusion_concepts_happy_path():
    triad = generate_style_triad()
    payload = {
        "projects": [
            {
                "title": "Сон об исчезающем мосте",
                "triad": triad.to_dict(),
                "manifesto": "Исследование зыбкости воспоминаний",
                "scene_description": "Старый каменный мост в тумане над зеркальной водой",
                "lighting_setup": "Контровой рассеянный свет с глубокими тенями",
                "camera_setup": {
                    "Приём съёмки": "Мультиэкспозиция (3 кадра)",
                    "Режим мультиэкспозиции": "Тёмный",
                    "Выдержка": '1/6"',
                    "Диафрагма": "f/5.6",
                },
                "shooting_action": "Микро-тремор рук на месте на 1 мм",
                "gear_recipe": {"camera": "Fujifilm X-T4", "lens": "Гелиос 44-2"},
                "shooting_steps": [
                    "Шаг 1: Включить мультиэкспозицию в режиме Тёмный",
                    "Шаг 2: Установить выдержку 1/6 с и EV -1.0",
                    "Шаг 3: Снять 3 кадра с естественным микро-тремором",
                ],
            }
        ]
    }
    concepts = parse_fusion_concepts(json.dumps(payload))
    assert len(concepts) == 1
    c = concepts[0]
    assert c.title == "Сон об исчезающем мосте"
    assert len(c.shooting_steps) == 3
    assert c.camera_setup["Режим мультиэкспозиции"] == "Тёмный"


def test_parse_fusion_concepts_direct_list():
    triad = generate_style_triad()
    payload = [
        {
            "title": "Проект из прямого списка",
            "triad": triad.to_dict(),
            "scene_description": "Улица ночного города",
            "camera_setup": {"Выдержка": "1/125", "Диафрагма": "f/4"},
            "shooting_action": "Голландский угол 20 градусов",
            "shooting_steps": ["Шаг 1", "Шаг 2", "Шаг 3"],
        }
    ]
    concepts = parse_fusion_concepts(json.dumps(payload))
    assert len(concepts) == 1
    assert concepts[0].title == "Проект из прямого списка"


def test_parse_fusion_concepts_malformed_and_empty():
    assert parse_fusion_concepts("not a json at all") == []
    assert parse_fusion_concepts("{}") == []
    assert parse_fusion_concepts('{"projects": []}') == []


def test_format_fusion_concept_card_html():
    triad = generate_style_triad()
    concept = FusedPhotoConcept(
        title="Тестовый проект <HTML & символы>",
        triad=triad,
        manifesto="Манифест о свете",
        scene_description="Локация",
        lighting_setup="Жесткий луч",
        camera_setup={"Выдержка": "1/6s", "Диафрагма": "f/2"},
        shooting_action="Поворот призмы",
        gear_recipe={"camera": "Fujifilm X-T4"},
        shooting_steps=["1. Настройка", "2. Спуск"],
    )
    card = format_fusion_concept_card(concept)
    assert "Тестовый проект &lt;HTML &amp; символы&gt;" in card
    assert "<code>1/6s</code>" in card
    assert "<!--" not in card  # Запрет HTML комментариев в Telegram


@pytest.mark.asyncio
async def test_brainstorm_fusion_integration():
    with patch(
        "services.brainstorm.search_notes",
        return_value=[{"name": "Сон", "snippet": "лес"}],
    ):
        with patch("services.brainstorm._load_fuji_guide", return_value="ГАЙД X-T4"):
            ctx = await collect_context("осенний сон", mode="fusion")

    assert "triad" in ctx
    assert "fusion_prompt" in ctx
    assert "gear" in ctx
    assert "mechanics" in ctx

    # Проверка промптов и параметров выборки
    assert "ТРИАДЕ СТИЛЕЙ" in storm_system_prompt("fusion")
    assert storm_sampling_params("fusion")["temperature"] > 0.8

    # Парсинг идей в режиме fusion
    triad = generate_style_triad()
    sample_json = json.dumps({
        "projects": [
            {
                "title": "Интеграционный концепт",
                "triad": triad.to_dict(),
                "scene_description": "Описание сцены",
                "camera_setup": {"Выдержка": "1/60", "Диафрагма": "f/2"},
                "shooting_action": "Действие рук",
                "shooting_steps": ["Шаг 1", "Шаг 2"],
            }
        ]
    })
    concepts = parse_fusion_ideas(sample_json)
    assert len(concepts) == 1
    assert concepts[0].title == "Интеграционный концепт"

    # Форматирование списка концептов
    formatted_text = format_fusion_ideas_text("осенний сон", concepts)
    assert "Творческая лаборатория (Триада стилей)" in formatted_text
    assert "Интеграционный концепт" in formatted_text
    assert "<!--" not in formatted_text

    # Конвертация в текст для сохранения во Дворец
    saved_text = ideas_to_text(concepts)
    assert "1. Интеграционный концепт" in saved_text
    assert "Сюжет: Описание сцены" in saved_text


def test_parse_fusion_ideas_empty_raises_error():
    with pytest.raises(ValueError, match="Нет валидных концепт-проектов"):
        parse_fusion_ideas('{"projects": []}')


def test_build_fusion_user_prompt_with_serendipity():
    triad = generate_style_triad()
    prompt = build_fusion_user_prompt(
        topic="Отражение времени",
        triad=triad,
        serendipity_context="🌉 Ассоциативный мост: Кванты и Сосны",
    )
    assert "Отражение времени" in prompt
    assert "🌉 Ассоциативный мост: Кванты и Сосны" in prompt
    assert triad.narrative.style in prompt


def test_format_concept_for_apple_notes():
    triad = StyleTriad(
        narrative=StyleAssignment(role="narrative", style="Сюрреализм", traits="Сон разума"),
        lighting=StyleAssignment(
            role="lighting", style="Экспрессионизм", traits="Кьяроскуро",
        ),
        optics=StyleAssignment(
            role="optics", style="Импрессионизм", traits="Размытие и лессировка",
        ),
        rationale="Гармония сна и цвета",
    )
    concept = FusedPhotoConcept(
        title="Акварельный призрак",
        triad=triad,
        manifesto="Исследование эфемерности материи.",
        scene_description="Отражение в мокром асфальте под фонарём.",
        lighting_setup="Контровой натриевый фонарь + отражатель снизу.",
        camera_setup={
            "Приём съёмки": "Мультиэкспозиция",
            "Выдержка": "1/6 с",
            "Диафрагма": "f/2.8",
            "Компенсация экспозиции": "-1.0 EV",
            "Имитация плёнки": "Velvia",
        },
        shooting_action="Лёгкий микро-тремор камеры на втором экспозиционном слое.",
        gear_recipe={
            "camera": "Fujifilm X-T4",
            "lens": "Гелиос 44-2 58mm f/2",
            "filter_or_accessory": "Black Pro-Mist 1/4",
        },
        shooting_steps=[
            "Кадр 1: Резкий контур фонаря.",
            "Кадр 2: Микро-движение с расфокусировкой.",
        ],
    )

    title, body = format_concept_for_apple_notes(concept)
    assert title == "[В планах] Акварельный призрак"
    assert "<h1>[В планах] Акварельный призрак</h1>" in body
    assert "<b>Статус:</b> <code>[В планах]</code>" in body
    assert "<h2>🎭 Триада стилистического синтеза</h2>" in body
    assert "Сюрреализм" in body
    assert "Экспрессионизм" in body
    assert "Импрессионизм" in body
    assert "<h2>📜 Художественный манифест</h2>" in body
    assert "Исследование эфемерности материи" in body
    assert "<h2>🖼 Визуальная сцена и композиция</h2>" in body
    assert "<h2>💡 Схема освещения</h2>" in body
    assert "<h2>📷 Параметры камеры (Fujifilm X-T4)</h2>" in body
    assert "<b>Выдержка:</b> <code>1/6 с</code>" in body
    assert "<h2>👐 Физика съёмки (действие рук)</h2>" in body
    assert "<h2>🎒 Рецепт оборудования</h2>" in body
    assert "<h2>📋 Пошаговый план съёмки</h2>" in body
    assert "<li>Кадр 1: Резкий контур фонаря.</li>" in body
    assert "<h2>✅ Чек-лист перед выходом</h2>" in body
    assert "Fujifilm X-T4 + объектив: Гелиос 44-2 58mm f/2" in body
    assert "Насадки/аксессуары: Black Pro-Mist 1/4" in body


def test_format_concept_for_apple_notes_already_prefixed():
    triad = generate_style_triad()
    concept = FusedPhotoConcept(
        title="[В планах] Уже спланированный проект",
        triad=triad,
        camera_setup={"Выдержка": "1/125"},
        shooting_action="Статичный снимок",
        shooting_steps=["1. Спуск", "2. Просмотр"],
    )
    title, _ = format_concept_for_apple_notes(concept)
    assert title == "[В планах] Уже спланированный проект"
    assert not title.startswith("[В планах] [В планах]")


def test_export_concept_to_apple_notes():
    triad = generate_style_triad()
    concept = FusedPhotoConcept(
        title="Экспортный тест",
        triad=triad,
        camera_setup={"Выдержка": "1/60"},
        shooting_action="Вращение",
        shooting_steps=["1. Наведи", "2. Сними"],
    )

    with patch("services.apple_notes.ensure_folder", return_value=True) as mock_ensure:
        with patch(
            "services.apple_notes.create_note", return_value="x-coredata://note-99",
        ) as mock_create:
            note_id = export_concept_to_apple_notes(concept, folder="Фотопроекты")

    assert note_id == "x-coredata://note-99"
    mock_ensure.assert_called_once_with("Фотопроекты")
    mock_create.assert_called_once()
    assert mock_create.call_args[1]["folder"] == "Фотопроекты"
    assert "[В планах] Экспортный тест" in mock_create.call_args[1]["title"]


# ─── Тесты интерактивной фотолаборатории (пагинация и микро-действия) ───

def test_format_concept_pages_1_to_4():
    triad = StyleTriad(
        narrative=StyleAssignment(role="narrative", style="Сюрреализм", traits="Сон разума"),
        lighting=StyleAssignment(role="lighting", style="Экспрессионизм", traits="Кьяроскуро"),
        optics=StyleAssignment(role="optics", style="Импрессионизм", traits="Лессировка"),
        rationale="Единство противоположностей",
    )
    concept = FusedPhotoConcept(
        title="Отражение луны в воде",
        triad=triad,
        manifesto="Исследование иллюзии и материи.",
        scene_description="Одинокий мост через реку в тумане.",
        lighting_setup="Контровой лунный свет и натриевый фонарь.",
        camera_setup={"Выдержка": "1/6 с", "Диафрагма": "f/2.8"},
        shooting_action="Микро-тремор рук 1 мм",
        gear_recipe={"camera": "Fujifilm X-T4", "lens": "Гелиос 44-2 58mm"},
        shooting_steps=["1. Навести резкость", "2. Сделать спуск"],
    )

    # Стр. 1: Манифест и Триада
    p1 = format_concept_page(concept, page=1)
    assert "Стр. 1/4" in p1
    assert "Отражение луны в воде" in p1
    assert "Художественный манифест" in p1
    assert "Исследование иллюзии и материи" in p1
    assert "<!--" not in p1

    # Стр. 2: Раскадровка и свет
    p2 = format_concept_page(concept, page=2)
    assert "Стр. 2/4" in p2
    assert "Одинокий мост через реку в тумане" in p2
    assert "Световая схема" in p2
    assert "<!--" not in p2

    # Стр. 3: Сетап Fujifilm X-T4 и арсенал
    p3 = format_concept_page(concept, page=3)
    assert "Стр. 3/4" in p3
    assert "1/6 с" in p3
    assert "Микро-тремор рук 1 мм" in p3
    assert "Гелиос 44-2 58mm" in p3
    assert "<!--" not in p3

    # Стр. 4: Полевой шутинг-лист и чек-лист
    p4 = format_concept_page(concept, page=4)
    assert "Стр. 4/4" in p4
    assert "1. Навести резкость" in p4
    assert "Чек-лист перед выходом" in p4
    assert "NP-W235" in p4
    assert "<!--" not in p4

    # Граничный случай: несуществующий номер страницы возвращает Стр. 1
    assert "Стр. 1/4" in format_concept_page(concept, page=99)


def test_build_concept_navigation_kb():
    # Проверяем кнопки навигации на каждой из 4 страниц
    for page in range(1, 5):
        kb = build_concept_navigation_kb(concept_idx=2, page=page)
        markup = kb.as_markup()
        callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
        # Микро-действия должны присутствовать на всех страницах
        assert "bs_deepen:2" in callbacks
        assert "bs_refs:2" in callbacks
        assert "bs_prompt:2" in callbacks
        assert "bs_export_concept:2" in callbacks
        assert "bs_save_concept:2" in callbacks
        assert "bs_back" in callbacks

    # Проверка специфичных переходов
    kb1 = build_concept_navigation_kb(concept_idx=1, page=1)
    cb1 = [btn.callback_data for row in kb1.as_markup().inline_keyboard for btn in row]
    assert "bs_page:1:2" in cb1
    assert "bs_page:1:0" not in cb1

    kb4 = build_concept_navigation_kb(concept_idx=1, page=4)
    cb4 = [btn.callback_data for row in kb4.as_markup().inline_keyboard for btn in row]
    assert "bs_page:1:3" in cb4
    assert "bs_page:1:1" in cb4  # В начало


def test_build_midjourney_prompt():
    triad = StyleTriad(
        narrative=StyleAssignment(role="narrative", style="Сюрреализм"),
        lighting=StyleAssignment(role="lighting", style="Экспрессионизм"),
        optics=StyleAssignment(role="optics", style="Импрессионизм"),
    )
    concept = FusedPhotoConcept(
        title="Тест промпта",
        triad=triad,
        scene_description="waterfall of floating pocket watches",
        lighting_setup="dramatic volumetric rim light",
        camera_setup={"Приём": "мультиэкспозиция ICM"},
        shooting_action="микро-тремор рук",
        gear_recipe={
            "lens": "Гелиос 44-2 58mm f/2",
            "filter_or_accessory": "Black Pro-Mist 1/4",
        },
        shooting_steps=["1. Спуск"],
    )

    prompt = build_midjourney_prompt(concept)
    assert "surrealism aesthetic" in prompt
    assert "German expressionist" in prompt
    assert "impressionistic photography" in prompt
    assert "Helios 44-2" in prompt
    assert "Black Pro-Mist" in prompt
    assert "multiple exposure layering" in prompt
    assert "--ar 16:9" in prompt
    assert "--v 6.1" in prompt


def test_deepen_and_references_prompts_and_cards():
    triad = generate_style_triad()
    concept = FusedPhotoConcept(
        title="Глубокий образ <&>",
        triad=triad,
        manifesto="Манифест",
        scene_description="Сцена с фигурой",
        lighting_setup="Контрастный свет",
        camera_setup={"Выдержка": "1/125"},
        shooting_action="Поворот",
        shooting_steps=["Шаг 1"],
    )

    # Системный и пользовательский промпты
    sys_prompt = build_deepen_system_prompt()
    assert "арт-директор" in sys_prompt
    assert "Скрытый символизм" in sys_prompt

    user_prompt = build_deepen_user_prompt(concept)
    assert "Глубокий образ <&>" in user_prompt
    assert "Сцена с фигурой" in user_prompt

    # Карточка углубления образа
    deepen_card = format_deepen_card(concept, "Символ 1: Зеркало как порог.\nСимвол 2: Тень.")
    assert "Режиссёрское углубление: «Глубокий образ &lt;&amp;&gt;»" in deepen_card
    assert "Зеркало как порог" in deepen_card
    assert "<!--" not in deepen_card

    # Канонические референсы
    refs = get_curated_references(concept)
    assert len(refs) >= 3
    for r in refs:
        assert "artist" in r
        assert "technique" in r
        assert "query" in r

    # Карточка референсов
    refs_card = format_references_card(concept, web_snippets="Сниппет из поиска")
    assert "Художественные референсы: «Глубокий образ &lt;&amp;&gt;»" in refs_card
    assert "Мастера для визуального изучения" in refs_card
    assert "Сниппет из поиска" in refs_card
    assert "<!--" not in refs_card


def test_parse_fusion_concepts_truncated_max_tokens():
    raw_truncated = (
        '```json\n{\n  "projects": [\n'
        '    {\n'
        '      "title": "Первый завершенный концепт",\n'
        '      "triad": {\n'
        '        "narrative": {"role": "narrative", "style": "Сюрреализм", "traits": "Сон"},\n'
        '        "lighting": {"role": "lighting", "style": "Экспрессионизм", "traits": "Тени"},\n'
        '        "optics": {"role": "optics", "style": "Пиктореализм", "traits": "Монокль"},\n'
        '        "rationale": "Синергия сна и теней"\n'
        '      },\n'
        '      "manifesto": "Манифест первого концепта",\n'
        '      "scene_description": "Улица ночью",\n'
        '      "lighting_setup": "Фонарь",\n'
        '      "camera_setup": {"Выдержка": "1/6 с", "Диафрагма": "f/8.0"},\n'
        '      "shooting_action": "Микро-ICM",\n'
        '      "gear_recipe": {"camera": "Fujifilm X-T4"},\n'
        '      "shooting_steps": ["1. Подготовить сетап", "2. Сделать спуск"]\n'
        '    },\n'
        '    {\n'
        '      "title": "Второй обрезанный концепт",\n'
        '      "manifesto": "Недописанный манифест...\n'
        '⚠️ <i>(Ответ модели был обрезан из-за лимита токенов)</i>'
    )
    concepts = parse_fusion_concepts(raw_truncated)
    assert len(concepts) == 1
    assert concepts[0].title == "Первый завершенный концепт"
    assert concepts[0].shooting_action == "Микро-ICM"


def test_deepen_card_html_formatting():
    """format_deepen_card преобразует сырой маркдаун в безопасный HTML Telegram."""
    from services.style_fusion import format_deepen_card

    triad = generate_style_triad()
    concept = FusedPhotoConcept(title="Сновидение осени", triad=triad)
    raw_md = (
        "### 1. Скрытый символизм\n"
        "Лист как метафора **увядания времени**.\n\n"
        "### 2. Режиссура модели\n"
        "- Замедленное дыхание\n"
        "- Взгляд в сторону контрового света"
    )
    card = format_deepen_card(concept, raw_md)
    assert "###" not in card
    assert "**" not in card
    assert "<b>1. Скрытый символизм</b>" in card
    assert "<b>увядания времени</b>" in card
    assert "• Замедленное дыхание" in card


def test_apple_notes_export_full_content_and_html():
    """Экспорт в Apple Notes содержит все расширенные разделы без сырых символов маркдауна."""
    triad = generate_style_triad()
    concept = FusedPhotoConcept(
        title="Осенняя мистерия",
        triad=triad,
        manifesto="Философия осени.",
        scene_description="Опавшие кленовые листья в воде.",
        camera_setup={"Выдержка": "1/2 с", "Диафрагма": "f/8.0"},
        shooting_action="Штатив и поворот ND-фильтра",
        gear_recipe={"camera": "Fujifilm X-T4", "lens": "Kamlan 50mm F1.1"},
        shooting_steps=["1. Поставить штатив", "2. Сделать кадр"],
        deepened_analysis="### Символизм\n**Таинство** воды и времени.",
        midjourney_prompt="/imagine prompt: autumn leaves --ar 16:9",
        fuji_recipe="Film: Velvia, WB: Daylight R+2 B-1",
    )
    title, body = format_concept_for_apple_notes(concept)
    assert title == "[В планах] Осенняя мистерия"
    assert "<h1>[В планах] Осенняя мистерия</h1>" in body
    assert "<h2>🎭 Триада стилистического синтеза</h2>" in body
    assert "<h2>🔍 Режиссёрское углубление художественного образа</h2>" in body
    assert "<b>Таинство</b>" in body
    assert "###" not in body
    assert "**" not in body
    assert "<h2>🎨 Промпт Midjourney / Flux.1</h2>" in body
    assert "autumn leaves --ar 16:9" in body
    assert "<h2>🎛 Внутрикамерный рецепт Fujifilm X-T4" in body
    assert "<h2>🌐 Художественные референсы мастеров</h2>" in body


def test_factory_mechanics_diversity():
    """Заводские фотомеханики содержат разнообразный оптический арсенал."""
    from services.photo_mechanics import get_factory_mechanics

    mechs = get_factory_mechanics()
    ids = {m.id for m in mechs}
    assert "watercolor_dark_multiexposure" in ids
    assert "center_hole_distortion" in ids
    assert "reversed_front_element_swirl" in ids
    assert "kamlan_ultra_shallow_dof" in ids
    assert "nd_silky_motion" in ids
    assert "sheer_fabric_veil" in ids


def test_concept_micro_actions_persistence():
    """Поля углубления, Midjourney и рецепта сохраняются при to_dict / from_dict."""
    triad = generate_style_triad()
    c1 = FusedPhotoConcept(
        title="Проект с сохранением",
        triad=triad,
        deepened_analysis="Глубокий анализ",
        midjourney_prompt="mj prompt",
        fuji_recipe="fuji recipe",
    )
    d = c1.to_dict()
    assert d["deepened_analysis"] == "Глубокий анализ"
    assert d["midjourney_prompt"] == "mj prompt"
    assert d["fuji_recipe"] == "fuji recipe"

    c2 = FusedPhotoConcept.from_dict(d)
    assert c2.deepened_analysis == "Глубокий анализ"
    assert c2.midjourney_prompt == "mj prompt"
    assert c2.fuji_recipe == "fuji recipe"
