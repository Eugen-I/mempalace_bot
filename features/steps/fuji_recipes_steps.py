"""Шаги BDD для features/fuji_recipes.feature."""

from pathlib import Path
import tempfile
from unittest.mock import patch
from behave import given, then, when

from services.copilot_session import CopilotSession, CopilotSessionManager
from services.fuji_recipes import (
    FujiRecipe,
    build_fuji_recipe_for_project,
    export_fuji_recipe_to_apple_notes,
    format_fuji_recipe_card,
    generate_surreal_stochastic_recipe,
)


@given('у фотографа активна сессия арт-копайлота со стилем "{style}"')
def step_active_session_with_style(context, style):
    tmp_file = Path(tempfile.mkdtemp()) / "fuji_session.json"
    context.manager = CopilotSessionManager(file_path=tmp_file)
    context.session = CopilotSession(
        user_id=5555,
        topic="Осенний сад Моне",
        selected_styles=[style],
    )
    context.manager.save_session(context.session)


@when("генерируется рецепт камеры для проекта")
def step_generate_recipe_for_project(context):
    context.recipe = build_fuji_recipe_for_project(context.session)


@then('рецепт содержит эмуляцию "{film}" и динамический диапазон "{dr}"')
def step_check_recipe_params(context, film, dr):
    assert context.recipe.film_simulation == film, (
        f"Expected {film}, got {context.recipe.film_simulation}"
    )
    assert context.recipe.dynamic_range == dr, (
        f"Expected {dr}, got {context.recipe.dynamic_range}"
    )


@then("физика съемки включает микро-ICM тремор на выдержке 1/6с")
def step_check_action_mechanic(context):
    assert "1/6с" in context.recipe.action_mechanic
    mech = context.recipe.action_mechanic
    assert "микро-тремор" in mech or "микро-ICM" in mech


@when('рецепт форматируется для слота "{slot}"')
def step_format_recipe_for_slot(context, slot):
    context.card_text = format_fuji_recipe_card(context.recipe, slot_name=slot)


@then('карточка содержит моноширинный блок "<pre>" и заголовок "Рецепт в слот {slot}"')
def step_check_card_structure(context, slot):
    assert "<pre>" in context.card_text
    assert "</pre>" in context.card_text
    assert f"Рецепт в слот {slot}" in context.card_text


@when("выполняется экспорт рецепта в Apple Notes")
def step_export_recipe_to_notes(context):
    with patch("services.apple_notes.ensure_folder", return_value=True):
        with patch(
            "services.apple_notes.create_note", return_value="x-coredata://note-fuji-55",
        ) as mock_create:
            context.note_id = export_fuji_recipe_to_apple_notes(
                context.recipe,
                slot_name="C1",
                project_title=context.session.topic,
                folder="Фотопроекты",
            )
            context.mock_create = mock_create


@then('создается заметка в папке "{folder}" с префиксом "{prefix}"')
def step_check_note_created(context, folder, prefix):
    assert context.note_id == "x-coredata://note-fuji-55"
    assert context.mock_create.call_args[1]["folder"] == folder
    title = context.mock_create.call_args[1]["title"]
    assert prefix in title


@given('формируется рецепт с неподдерживаемой эмуляцией "{film}" и тоном {tone:f}')
def step_create_invalid_recipe(context, film, tone):
    context.invalid_recipe = FujiRecipe(
        recipe_name="Тест сбоя",
        film_simulation=film,
        highlight_tone=tone,
    )


@when("выполняется валидация рецепта")
def step_validate_recipe(context):
    context.validation_errors = context.invalid_recipe.validate()


@then("валидация возвращает список ошибок")
def step_check_errors_present(context):
    assert len(context.validation_errors) > 0


@then('зафиксирована ошибка "{err_part}"')
def step_check_specific_error(context, err_part):
    found = any(err_part in e for e in context.validation_errors)
    assert found, f"Expected '{err_part}' in {context.validation_errors}"


@then("зафиксирована ошибка недопустимой тоновой кривой")
def step_check_tone_error(context):
    assert any("Highlight Tone" in e for e in context.validation_errors)


@given("сформирован валидный рецепт камеры")
def step_given_valid_recipe(context):
    context.recipe = FujiRecipe(
        recipe_name="Элегия тумана",
        film_simulation="Classic Chrome",
        dynamic_range="DR200",
    )


@when('запрашивается форматирование для некорректного слота "{slot}"')
def step_format_invalid_slot(context, slot):
    context.card_text = format_fuji_recipe_card(context.recipe, slot_name=slot)


@then('слот автоматически нормализуется в "{slot}"')
def step_check_slot_normalized(context, slot):
    assert f"Рецепт в слот {slot}" in context.card_text


@then('в заголовке карточки отображается "Рецепт в слот {slot}"')
def step_check_card_header_slot(context, slot):
    assert f"Рецепт в слот {slot}" in context.card_text


@when("при сохранении в Apple Notes возникает системная ошибка AppleScript")
def step_export_error_applescript(context):
    err = RuntimeError("AppleScript bridge failed")
    with patch("services.apple_notes.ensure_folder", side_effect=err):
        try:
            export_fuji_recipe_to_apple_notes(
                context.recipe, slot_name="C1", project_title="Сбой",
            )
            context.caught_error = None
        except Exception as exc:
            context.caught_error = str(exc)


@then("исключение перехватывается без падения обработчика")
def step_check_exception_caught(context):
    assert context.caught_error is not None
    assert "AppleScript" in context.caught_error


@then("пользователю возвращается уведомление о невозможности создать заметку")
def step_check_user_notification(context):
    assert "AppleScript bridge failed" in context.caught_error


@given("инициализирован стохастический генератор сюрреалистических рецептов")
def step_init_stochastic_generator(context):
    context.stochastic_generator = generate_surreal_stochastic_recipe


@when("выполняется серия из 100 независимых генераций")
def step_run_100_generations(context):
    context.generated_recipes = [context.stochastic_generator(intensity="wild") for _ in range(100)]


@then("все 100 сгенерированных комбинаций параметров уникальны")
def step_check_100_unique(context):
    signatures = {
        (
            r.film_simulation,
            r.dynamic_range,
            r.highlight_tone,
            r.shadow_tone,
            r.color,
            r.sharpness,
            r.high_iso_nr,
            r.clarity,
            r.grain_effect,
            r.color_chrome_effect,
            r.color_chrome_fx_blue,
            r.white_balance,
            r.wb_shift_r,
            r.wb_shift_b,
            r.exposure_compensation,
        )
        for r in context.generated_recipes
    }
    assert len(signatures) == 100, f"Found {len(signatures)} unique out of 100"


@then("каждый рецепт строго соответствует аппаратным лимитам прошивки 2.12")
def step_check_all_recipes_valid(context):
    for r in context.generated_recipes:
        errors = r.validate()
        assert errors == [], f"Validation errors in recipe {r.recipe_name}: {errors}"


@given("сформирован стохастический рецепт с поэтическим метафорическим названием")
def step_given_stochastic_recipe_with_title(context):
    context.recipe = generate_surreal_stochastic_recipe(intensity="wild")
    context.recipe.notes = "Специальные символы: <test & alert> / 100% fine art"


@when("карточка форматируется для отправки в Telegram")
def step_format_card_for_tg(context):
    context.card_text = format_fuji_recipe_card(context.recipe, slot_name="C1")


@then('разметка содержит только разрешенные теги "<b>", "<pre>", "<i>"')
def step_check_allowed_tags(context):
    assert "<b>" in context.card_text and "</b>" in context.card_text
    assert "<pre>" in context.card_text and "</pre>" in context.card_text
    assert "<i>" in context.card_text and "</i>" in context.card_text


@then('в разметке полностью отсутствуют комментарии "<!--" и блочные теги "<div>", "<p>"')
def step_check_forbidden_tags(context):
    assert "<!--" not in context.card_text
    assert "<div>" not in context.card_text
    assert "</div>" not in context.card_text
    assert "<p>" not in context.card_text
    assert "</p>" not in context.card_text
    assert "<br>" not in context.card_text


@then("все спецсимволы в названии и примечаниях безопасно экранированы")
def step_check_special_chars_escaped(context):
    assert "<test & alert>" not in context.card_text
    assert "&lt;test &amp; alert&gt;" in context.card_text
