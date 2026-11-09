"""Шаги BDD для features/fuji_recipe_book.feature (Шаг D3)."""

from pathlib import Path
import tempfile
from unittest.mock import MagicMock
from behave import given, then, when

from services.fuji_recipes import (
    FujiRecipe,
    build_fuji_recipe_for_concept,
    delete_saved_recipe,
    export_recipe_book_to_apple_notes,
    load_saved_recipes,
    save_recipe_to_book,
)
from services.style_fusion import (
    FusedPhotoConcept,
    StyleAssignment,
    StyleTriad,
)


@given('у фотографа сформирован концепт Штурма "{title}" с триадой стилей')
def step_concept_created(context, title):
    context.tmp_dir = Path(tempfile.mkdtemp())
    context.book_file = context.tmp_dir / "test_recipe_book.json"
    context.concept = FusedPhotoConcept(
        title=title,
        triad=StyleTriad(
            narrative=StyleAssignment(role="narrative", style="Экспрессионизм"),
            lighting=StyleAssignment(role="lighting", style="Конструктивизм"),
            optics=StyleAssignment(role="optics", style="Пиктореализм"),
        ),
        shooting_action="Съемка с голландским углом под мостом.",
    )


@when("извлекается внутрикамерный рецепт X-T4 для данного концепта")
def step_extract_recipe_for_concept(context):
    context.recipe = build_fuji_recipe_for_concept(context.concept)


@then('рецепт получает имя "{name}" и параметры под доминирующий стиль')
def step_check_recipe_name_and_style(context, name):
    assert context.recipe.recipe_name == name
    assert context.recipe.film_simulation == "ACROS (+R Красный)"
    assert context.recipe.validate() == []


@when("рецепт сохраняется в персистентную книгу фотографа")
def step_save_recipe_to_book(context):
    context.save_res = save_recipe_to_book(
        context.recipe,
        user_id=777,
        slot_hint="C1",
        file_path=context.book_file,
    )
    assert context.save_res is True


@then('книга содержит сохраненный рецепт с метаданными слота "{slot}"')
def step_check_book_has_recipe(context, slot):
    recipes = load_saved_recipes(user_id=777, file_path=context.book_file)
    assert len(recipes) == 1
    assert recipes[0].recipe_name == context.recipe.recipe_name


@when("выполняется экспорт всей книги рецептов в Apple Notes")
def step_export_book_to_notes(context):
    context.mock_notes = []

    def mock_create(title, body, folder="Фотопроекты"):
        context.mock_notes.append({"title": title, "body": body, "folder": folder})
        return "x-coredata://mock/note-all-1"

    import services.apple_notes as an
    an.ensure_folder = MagicMock()
    an.create_note = mock_create

    context.export_ok, context.export_val = export_recipe_book_to_apple_notes(
        user_id=777,
        folder="Фотопроекты",
        file_path=context.book_file,
    )


@then('создается общая заметка в папке "Фотопроекты" с описанием всех рецептов коллекции')
def step_check_notes_created(context):
    assert context.export_ok is True
    assert len(context.mock_notes) == 1
    note = context.mock_notes[0]
    assert "Коллекция рецептов фотографа" in note["title"]
    assert context.recipe.recipe_name in note["body"]


@given("книга рецептов фотографа не содержит сохраненных записей")
def step_empty_recipe_book(context):
    context.tmp_dir = Path(tempfile.mkdtemp())
    context.book_file = context.tmp_dir / "empty_book.json"


@when("запрашивается экспорт всей книги рецептов в Apple Notes")
def step_request_export_empty_book(context):
    context.mock_create = MagicMock()
    import services.apple_notes as an
    an.create_note = context.mock_create

    context.export_ok, context.export_msg = export_recipe_book_to_apple_notes(
        user_id=888,
        folder="Фотопроекты",
        file_path=context.book_file,
    )


@then("операция отклоняется с сообщением о пустой книге")
def step_check_export_rejected_empty(context):
    assert context.export_ok is False
    assert "пуста" in context.export_msg.lower()


@then("вызов внешнего скрипта Apple Notes блокируется")
def step_check_apple_notes_blocked(context):
    assert not context.mock_create.called


@given('в книге фотографа сохранен рецепт "{name}"')
def step_book_has_single_recipe(context, name):
    context.tmp_dir = Path(tempfile.mkdtemp())
    context.book_file = context.tmp_dir / "recipe_book.json"
    r = FujiRecipe(recipe_name=name, film_simulation="ACROS")
    save_recipe_to_book(r, user_id=555, file_path=context.book_file)


@when('запрашивается удаление рецепта с именем "{name}"')
def step_delete_recipe(context, name):
    context.del_res = delete_saved_recipe(
        name,
        user_id=555,
        file_path=context.book_file,
    )


@then("операция удаления возвращает статус неудачи")
def step_check_delete_failed(context):
    assert context.del_res is False


@then('исходный рецепт "{name}" остается в книге без изменений')
def step_check_recipe_remains(context, name):
    recipes = load_saved_recipes(user_id=555, file_path=context.book_file)
    assert len(recipes) == 1
    assert recipes[0].recipe_name == name


@given("подготовлен рецепт камеры с недопустимым значением резкости +9")
def step_invalid_recipe_sharpness(context):
    context.tmp_dir = Path(tempfile.mkdtemp())
    context.book_file = context.tmp_dir / "invalid_book.json"
    context.invalid_recipe = FujiRecipe(
        recipe_name="Сломанный рецепт",
        film_simulation="Classic Chrome",
        sharpness=9,  # Лимит -4..+4
    )


@when("инициируется сохранение невалидного рецепта в книгу")
def step_try_save_invalid(context):
    context.save_res = save_recipe_to_book(
        context.invalid_recipe,
        user_id=555,
        file_path=context.book_file,
    )


@then("операция сохранения завершается отказом")
def step_check_save_rejected(context):
    assert context.save_res is False


@then("файл книги рецептов не создается и не повреждается")
def step_check_file_not_created(context):
    assert not context.book_file.exists()


@given('в книге уже сохранен рецепт "{name}" со значением четкости {val:d}')
def step_saved_recipe_clarity(context, name, val):
    context.tmp_dir = Path(tempfile.mkdtemp())
    context.book_file = context.tmp_dir / "clarity_book.json"
    r = FujiRecipe(
        recipe_name=name,
        film_simulation="Classic Chrome",
        clarity=val,
    )
    save_recipe_to_book(r, user_id=444, file_path=context.book_file)


@when('фотограф повторно сохраняет рецепт "{name}" со значением четкости {val:d}')
def step_resave_recipe_clarity(context, name, val):
    r_updated = FujiRecipe(
        recipe_name=name,
        film_simulation="Classic Chrome",
        clarity=val,
    )
    save_recipe_to_book(r_updated, user_id=444, file_path=context.book_file)


@then("в книге по-прежнему числится ровно 1 рецепт")
def step_check_single_recipe_count(context):
    recipes = load_saved_recipes(user_id=444, file_path=context.book_file)
    assert len(recipes) == 1


@then("сохраненный рецепт содержит обновленное значение четкости {val:d}")
def step_check_updated_clarity(context, val):
    recipes = load_saved_recipes(user_id=444, file_path=context.book_file)
    assert recipes[0].clarity == val


@given('фотограф с ID {uid:d} сохраняет рецепт "{name}"')
def step_user_saves_recipe(context, uid, name):
    if not hasattr(context, "book_file"):
        context.tmp_dir = Path(tempfile.mkdtemp())
        context.book_file = context.tmp_dir / "multi_user_book.json"
    r = FujiRecipe(recipe_name=name, film_simulation="PROVIA/Стандартный")
    save_recipe_to_book(r, user_id=uid, file_path=context.book_file)


@when("фотограф {uid:d} запрашивает список своих рецептов")
def step_user_requests_recipes(context, uid):
    context.user_recipes = load_saved_recipes(user_id=uid, file_path=context.book_file)


@then('в списке присутствует только "{name}"')
def step_check_user_has_only_own(context, name):
    names = [r.recipe_name for r in context.user_recipes]
    assert names == [name]


@then('"{name}" полностью изолирован и не отображается')
def step_check_other_isolated(context, name):
    names = [r.recipe_name for r in context.user_recipes]
    assert name not in names
