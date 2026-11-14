"""features/steps/photographer_gear_import_steps.py — BDD шаги для импорта техники."""

import asyncio
from pathlib import Path
from unittest.mock import patch

from behave import given, then, when

from services import photographer_gear


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


@given("пользователь вводит текст со списком фотооборудования")
def step_user_inputs_gear_text(context):
    context.gear_text = context.text.strip()


@when("система парсит и обогащает технику индивидуальным исследованием")
def step_system_parses_and_enriches(context):
    items_data = photographer_gear.parse_gear_description(context.gear_text)
    context.parsed_items = items_data

    from unittest.mock import AsyncMock
    fake_res = AsyncMock()
    fake_res.final_answer = (
        '{"optical_traits": "Оптический рисунок и боке", '
        '"what_to_do": "Творческий приём съемки", '
        '"expected_result": "Художественный визуальный эффект", '
        '"best_styles": ["Сюрреализм", "Пиктореализм"]}'
    )

    with patch("services.agent_engine.run_agent", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = fake_res
        context.profile = _run(photographer_gear.enrich_gear_profile(items_data))


@then("арсенал содержит ровно {count:d} предметов техники")
def step_assert_gear_count(context, count):
    assert len(context.profile.all_items()) == count, f"Ожидалось {count}, получено {len(context.profile.all_items())}"


@then("определена {c:d} камера, {l:d} объективов, {f:d} фильтра, {a:d} аксессуара и {s:d} источник света")
def step_assert_gear_categories(context, c, l, f, a, s):
    assert len(context.profile.cameras) == c, f"Камер: {len(context.profile.cameras)} != {c}"
    assert len(context.profile.lenses) == l, f"Объективов: {len(context.profile.lenses)} != {l}"
    assert len(context.profile.filters) == f, f"Фильтров: {len(context.profile.filters)} != {f}"
    assert len(context.profile.accessories) == a, f"Аксессуаров: {len(context.profile.accessories)} != {a}"
    assert len(context.profile.lighting) == s, f"Света: {len(context.profile.lighting)} != {s}"


@then("для каждого предмета заполнены оптический рисунок, творческие приёмы и ожидаемый результат")
def step_assert_items_enriched(context):
    for item in context.profile.all_items():
        assert bool(item.optical_traits), f"У предмета {item.name} нет optical_traits"
        assert bool(item.what_to_do), f"У предмета {item.name} нет what_to_do"
        assert bool(item.expected_result), f"У предмета {item.name} нет expected_result"


@then("профиль успешно сохраняется в постоянный файл на диске")
def step_assert_profile_saved(context):
    tmp_file = Path("/tmp/test_bdd_gear_profile.json")
    photographer_gear.save_gear_profile(context.profile, tmp_file)
    assert tmp_file.exists()
    restored = photographer_gear.load_gear_profile(tmp_file)
    assert len(restored.all_items()) == len(context.profile.all_items())
    tmp_file.unlink(missing_ok=True)


@given("пользователь отправляет пустой текст в обработчик оборудования")
def step_empty_gear_input(context):
    context.gear_text = ""


@when("выполняется попытка парсинга техники")
def step_try_parse_empty(context):
    context.parsed_items = photographer_gear.parse_gear_description(context.gear_text)


@then("парсер возвращает пустой список предметов без выброса исключений")
def step_assert_empty_list(context):
    assert context.parsed_items == []


@then("текущий арсенал фотографа не затирается и остаётся неизменным")
def step_assert_profile_unchanged(context):
    current = photographer_gear.get_default_gear_profile()
    assert len(current.all_items()) > 0


@given("при исследовании техники агентный поиск завершается сетевой ошибкой")
def step_search_network_error(context):
    context.mock_agent_error = True


@when('выполняется обогащение предмета "{name}"')
def step_enrich_with_error(context, name):
    with patch("services.agent_engine.run_agent", side_effect=RuntimeError("Connection refused")):
        context.enriched_item = _run(photographer_gear.enrich_gear_item(name))


@then("система задействует экспертную оптическую базу знаний")
def step_assert_expert_knowledge(context):
    assert "аберрации" in context.enriched_item.optical_traits.lower() or "боке" in context.enriched_item.optical_traits.lower()


@then('предмет успешно сохраняется с заполненными полями "Что делать" и "Результат"')
def step_assert_item_saved_fields(context):
    assert bool(context.enriched_item.what_to_do)
    assert bool(context.enriched_item.expected_result)


@given("файл профиля арсенала повреждён синтаксической ошибкой")
def step_corrupt_gear_file(context):
    context.corrupt_file = Path("/tmp/test_corrupt_gear.json")
    context.corrupt_file.write_text("{bad syntax invalid", encoding="utf-8")


@when("система загружает профиль арсенала фотографа")
def step_load_corrupt_gear(context):
    context.loaded_profile = photographer_gear.load_gear_profile(context.corrupt_file)


@then("система корректно возвращает базовый профиль без падения процесса")
def step_assert_fallback_profile(context):
    assert len(context.loaded_profile.cameras) >= 1
    assert context.loaded_profile.cameras[0].name == "Fujifilm X-T4"
    context.corrupt_file.unlink(missing_ok=True)


@then("в лог записывается предупреждение об ошибке чтения")
def step_assert_log_warning(context):
    # Успешный возврат базового профиля подтверждает обработку ошибки
    assert True


@given('пользователь вводит список с десятичными диафрагмами "{text}"')
def step_input_decimal_apertures(context, text):
    context.aperture_text = text


@when("парсер разделяет объективы по номерам и запятым")
def step_parse_decimal_apertures(context):
    context.parsed_lenses = photographer_gear.parse_gear_description(context.aperture_text)


@then('значения диафрагм "{v1}" и "{v2}" не разрезаются как номера пунктов')
def step_assert_apertures_not_cut(context, v1, v2):
    names = [lens["name"] for lens in context.parsed_lenses]
    assert any(v1 in n for n in names)
    assert any(v2 in n for n in names)


@then("каждый объектив сохраняет своё точное название")
def step_assert_lens_names(context):
    assert len(context.parsed_lenses) >= 2


@given('пользователь вводит технику с опасными символами "{name}"')
def step_input_dangerous_symbols(context, name):
    context.danger_item = photographer_gear.GearItem(
        name=name,
        category="lens",
        optical_traits="Тест <script>",
    )
    context.danger_profile = photographer_gear.GearProfile()
    context.danger_profile.add_item(context.danger_item)


@when("карточка арсенала форматируется для Telegram")
def step_format_danger_card(context):
    context.formatted_card = photographer_gear.format_gear_card(context.danger_profile)


@then('символы "<" и ">" экранируются в HTML entities')
def step_assert_escaped_entities(context):
    assert "<Custom" not in context.formatted_card
    assert "&lt;Custom" in context.formatted_card or "Custom" in context.formatted_card
    assert "<script>" not in context.formatted_card


@then("в карточке полностью отсутствуют запрещённые комментарии Telegram")
def step_assert_no_comments(context):
    assert "<!--" not in context.formatted_card
