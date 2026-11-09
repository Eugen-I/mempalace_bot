"""Unit-тесты для модуля services/fuji_recipes.py (Шаг D1, FR-1).

Проверяет:
- Валидацию параметров X-T4 под прошивку 2.12 (границы и недопустимые значения).
- Детерминированный подбор рецептов под 5 арт-стилей.
- Стохастический сюрреалистический генератор Cadavre Exquis.
- Неповторимость случайных рецептов за 100 итераций (>4.8e12 пространство состояний).
- Генератор поэтических сюрреалистических названий.
- Сериализацию to_dict/from_dict.
- Форматирование карточки камеры в тегах <pre> и соблюдение правил Telegram HTML.
- Интеграцию с движком копайлота services/copilot_engine.py.
"""

from unittest.mock import MagicMock

from services.copilot_session import CopilotSession
import services.copilot_engine as engine
from services.fuji_recipes import (
    FujiRecipe,
    TONE_CURVE_VALUES,
    VALID_FILM_SIMULATIONS,
    build_fuji_recipe_for_project,
    format_fuji_recipe_card,
    generate_surreal_recipe_title,
    generate_surreal_stochastic_recipe,
)


def test_fuji_recipe_dataclass_defaults_and_validation_happy_path():
    """Happy path: базовый валидный рецепт без ошибок."""
    recipe = FujiRecipe(
        recipe_name="Тестовый рецепт",
        film_simulation="Classic Chrome",
        dynamic_range="DR200",
        highlight_tone=0.0,
        shadow_tone=0.5,
        color=1,
        sharpness=0,
        high_iso_nr=-2,
        clarity=0,
        grain_effect="Слабый / Мелкое",
        color_chrome_effect="Слабый",
        color_chrome_fx_blue="Выкл",
        white_balance="Авто",
        wb_shift_r=2,
        wb_shift_b=-3,
        exposure_compensation="0 EV",
        action_mechanic="Съемка с рук",
    )
    errors = recipe.validate()
    assert errors == []


def test_fuji_recipe_validation_negative_film_simulation():
    """Негативный тест: неподдерживаемая эмуляция (Nostalgic Negative) отклоняется."""
    recipe = FujiRecipe(
        recipe_name="Недопустимый",
        film_simulation="Nostalgic Negative",  # официально нет в X-T4
    )
    errors = recipe.validate()
    assert any("Неизвестная эмуляция плёнки" in err for err in errors)


def test_fuji_recipe_validation_negative_boundary_ranges():
    """Граничные условия: проверка выхода за пределы допустимых диапазонов X-T4 v2.12."""
    recipe = FujiRecipe(
        recipe_name="Ошибочные диапазоны",
        film_simulation="PROVIA/Стандартный",
        dynamic_range="DR800",  # нет такого
        highlight_tone=4.5,     # макс +4.0
        shadow_tone=-2.5,       # мин -2.0
        color=5,                # [-4, +4]
        sharpness=-5,           # [-4, +4]
        high_iso_nr=6,          # [-4, +4]
        clarity=6,              # [-5, +5]
        grain_effect="Супер",   # не из списка
        color_chrome_effect="Макс",
        color_chrome_fx_blue="Ультра",
        wb_shift_r=10,          # [-9, +9]
        wb_shift_b=-12,         # [-9, +9]
    )
    errors = recipe.validate()
    assert len(errors) >= 10
    assert any("DR800" in err for err in errors)
    assert any("Highlight Tone" in err for err in errors)
    assert any("Shadow Tone" in err for err in errors)
    assert any("Color 5" in err for err in errors)
    assert any("Sharpness -5" in err for err in errors)
    assert any("Clarity 6" in err for err in errors)
    assert any("WB Shift R 10" in err for err in errors)
    assert any("WB Shift B -12" in err for err in errors)


def test_fuji_recipe_serialization_roundtrip():
    """Сериализация to_dict и десериализация from_dict с устойчивостью к лишним полям."""
    original = FujiRecipe(
        recipe_name="Тестовый сериализатор",
        film_simulation="Velvia/Яркий",
        dynamic_range="DR400",
        highlight_tone=-1.5,
        shadow_tone=2.0,
        color=3,
        sharpness=-1,
        clarity=-2,
        action_mechanic="Лессировка",
    )
    data = original.to_dict()
    assert isinstance(data, dict)
    assert data["film_simulation"] == "Velvia/Яркий"

    # Добавляем стороннее поле из внешнего API
    data["unknown_legacy_field"] = "some_value"
    restored = FujiRecipe.from_dict(data)

    assert restored.recipe_name == original.recipe_name
    assert restored.film_simulation == original.film_simulation
    assert restored.highlight_tone == original.highlight_tone
    assert restored.shadow_tone == original.shadow_tone
    assert restored.color == original.color


def test_build_fuji_recipe_expressionism():
    """Детерминированный рецепт под Экспрессионизм: ACROS+R, тени +3.5, EV -0.7."""
    session = MagicMock()
    session.selected_styles = ["Экспрессионизм"]

    recipe = build_fuji_recipe_for_project(session)
    assert recipe.film_simulation == "ACROS (+R Красный)"
    assert recipe.shadow_tone == 3.5
    assert recipe.highlight_tone == 2.0
    assert recipe.clarity == 3
    assert recipe.grain_effect == "Сильный / Крупное"
    assert recipe.exposure_compensation == "-0.7 EV"
    assert "Голландский угол" in recipe.action_mechanic
    assert recipe.validate() == []


def test_build_fuji_recipe_pictorialism():
    """Детерминированный рецепт под Пиктореализм: Classic Chrome, Clarity -4, мягкий свет."""
    session = MagicMock()
    session.selected_styles = ["Пиктореализм"]

    recipe = build_fuji_recipe_for_project(session)
    assert recipe.film_simulation == "Classic Chrome"
    assert recipe.clarity == -4
    assert recipe.highlight_tone == -2.0
    assert recipe.grain_effect == "Сильный / Крупное"
    assert "Black Pro-Mist" in recipe.action_mechanic
    assert recipe.validate() == []


def test_build_fuji_recipe_impressionism():
    """Детерминированный рецепт под Импрессионизм: Velvia, лессировка 1/6с Тёмный."""
    session = MagicMock()
    session.selected_styles = ["Импрессионизм"]

    recipe = build_fuji_recipe_for_project(session)
    assert recipe.film_simulation == "Velvia/Яркий"
    assert recipe.color == 3
    assert recipe.dynamic_range == "DR200"
    assert "Мультиэкспозиция (2–4 кадра), режим Тёмный" in recipe.action_mechanic
    assert recipe.validate() == []


def test_build_fuji_recipe_surrealism():
    """Детерминированный рецепт под Сюрреализм: Классический Негатив, призма, 5800K."""
    session = MagicMock()
    session.selected_styles = ["Сюрреализм"]

    recipe = build_fuji_recipe_for_project(session)
    assert recipe.film_simulation == "Классический Негатив"
    assert recipe.white_balance == "5800K"
    assert recipe.wb_shift_r == 6
    assert recipe.wb_shift_b == -7
    assert "призма" in recipe.action_mechanic.lower()
    assert recipe.validate() == []


def test_build_fuji_recipe_constructivism():
    """Детерминированный рецепт под Конструктивизм: ACROS, резкость +3, clarity +4."""
    session = MagicMock()
    session.selected_styles = ["Конструктивизм"]

    recipe = build_fuji_recipe_for_project(session)
    assert recipe.film_simulation == "ACROS"
    assert recipe.sharpness == 3
    assert recipe.clarity == 4
    assert "диагональ" in recipe.action_mechanic.lower()
    assert recipe.validate() == []


def test_build_fuji_recipe_default_fallback():
    """Детерминированный рецепт без выбранных стилей отдаёт сбалансированный дефолт."""
    recipe_none = build_fuji_recipe_for_project(None)
    assert recipe_none.film_simulation == "Classic Chrome"
    assert recipe_none.validate() == []

    session_empty = MagicMock()
    session_empty.selected_styles = []
    recipe_empty = build_fuji_recipe_for_project(session_empty)
    assert recipe_empty.film_simulation == "Classic Chrome"
    assert recipe_empty.validate() == []


def test_generate_surreal_stochastic_recipe_wild_validity():
    """Стохастический генератор (интенсивность wild) генерирует 100% валидный рецепт X-T4."""
    for _ in range(10):
        recipe = generate_surreal_stochastic_recipe(intensity="wild")
        errors = recipe.validate()
        assert errors == [], f"Ошибки валидации wild: {errors}"
        assert recipe.film_simulation in VALID_FILM_SIMULATIONS
        assert recipe.highlight_tone in TONE_CURVE_VALUES
        assert recipe.shadow_tone in TONE_CURVE_VALUES
        assert -4 <= recipe.color <= 4
        assert -5 <= recipe.clarity <= 5
        assert -9 <= recipe.wb_shift_r <= 9
        assert -9 <= recipe.wb_shift_b <= 9


def test_generate_surreal_stochastic_recipe_moderate_validity():
    """Стохастический генератор (интенсивность moderate) генерирует валидный рецепт."""
    for _ in range(5):
        recipe = generate_surreal_stochastic_recipe(intensity="moderate")
        errors = recipe.validate()
        assert errors == [], f"Ошибки валидации moderate: {errors}"


def test_stochastic_recipe_uniqueness_100_iterations():
    """Стохастическая энтропия: 100 независимых генераций дают 100 уникальных комбинаций."""
    recipes_signatures = set()
    for _ in range(100):
        recipe = generate_surreal_stochastic_recipe(intensity="wild")
        sig = (
            recipe.film_simulation,
            recipe.dynamic_range,
            recipe.highlight_tone,
            recipe.shadow_tone,
            recipe.color,
            recipe.sharpness,
            recipe.high_iso_nr,
            recipe.clarity,
            recipe.grain_effect,
            recipe.color_chrome_effect,
            recipe.color_chrome_fx_blue,
            recipe.white_balance,
            recipe.wb_shift_r,
            recipe.wb_shift_b,
            recipe.exposure_compensation,
        )
        recipes_signatures.add(sig)

    assert len(recipes_signatures) == 100, "Обнаружены повторяющиеся стохастические рецепты!"


def test_surreal_poetic_titles_generation():
    """Генератор поэтических названий выдает разнообразные метафоры Магритта и Дали."""
    titles = [generate_surreal_recipe_title() for _ in range(20)]
    assert len(titles) == 20
    assert all(len(t.strip()) > 5 for t in titles)
    # Все названия не пустые и начинаются с заглавной буквы
    assert all(t[0].isupper() for t in titles)


def test_format_fuji_recipe_card_html_safety_and_structure():
    """Форматирование визуальной карточки для слота камеры C1-C7 в моноширинном блоке."""
    recipe = FujiRecipe(
        recipe_name="Вероломство бирюзовой тени",
        film_simulation="Классический Негатив",
        dynamic_range="DR400",
        highlight_tone=1.5,
        shadow_tone=-1.0,
        color=2,
        sharpness=1,
        high_iso_nr=-2,
        clarity=3,
        grain_effect="Сильный / Крупное",
        color_chrome_effect="Сильный",
        color_chrome_fx_blue="Слабый",
        white_balance="5500K",
        wb_shift_r=6,
        wb_shift_b=-8,
        exposure_compensation="+0.7 EV",
        action_mechanic="Съемка сквозь хрустальную призму на открытой f/2.",
        notes="Инопланетная бирюза в полутонах.",
    )

    card = format_fuji_recipe_card(recipe, slot_name="C3")

    # Проверка структуры и слота
    assert "🎛 <b>Fujifilm X-T4 • Рецепт в слот C3</b>" in card
    assert "«<b>Вероломство бирюзовой тени</b>»" in card
    assert "<pre>" in card and "</pre>" in card
    assert "ИМИТАЦИЯ ПЛЁНКИ:" in card
    assert "Классический Негатив" in card
    assert "ДИНАМИЧ. ДИАПАЗОН:DR400" in card
    assert "ТОН (ПОДСВЕТКА):  +1.5" in card
    assert "ТОН (ТЕНЬ):       -1.0" in card
    assert "СДВИГ ББ (R / B): R+6 / B-8" in card
    assert "Художественный эффект:" in card

    # Строгое соблюдение Telegram HTML (AGENTS.md)
    assert "<!--" not in card
    assert "<p>" not in card
    assert "<div>" not in card
    assert "<br>" not in card


def test_format_fuji_recipe_card_custom_slot_fallback():
    """Некорректный номер слота нормализуется в C1."""
    recipe = FujiRecipe(
        recipe_name="Тест слота",
        film_simulation="Classic Chrome",
    )
    card_invalid = format_fuji_recipe_card(recipe, slot_name="C99")
    assert "Рецепт в слот C1" in card_invalid

    card_empty = format_fuji_recipe_card(recipe, slot_name="")
    assert "Рецепт в слот C1" in card_empty


def test_copilot_engine_recipe_integration(tmp_path, monkeypatch):
    """Интеграция с движком копайлота services/copilot_engine.py."""
    import config
    monkeypatch.setattr(config, "ALLOWED_IDS", {8888})
    from services.copilot_session import CopilotSessionManager
    mgr = CopilotSessionManager(file_path=tmp_path / "fuji_test_sessions.json")
    monkeypatch.setattr(engine, "get_copilot_manager", lambda: mgr)

    session = CopilotSession(
        user_id=8888,
        topic="Сумеречная элегия",
        selected_styles=["Пиктореализм"],
    )
    mgr.save_session(session)

    # 1. Получение детерминированного рецепта под стиль
    recipe = engine.get_or_create_fuji_recipe(session, stochastic=False)
    assert recipe.film_simulation == "Classic Chrome"
    assert session.tech_preferences["fuji_recipe"]["film_simulation"] == "Classic Chrome"
    assert session.tech_preferences["film_sim"] == "Classic Chrome"

    # 2. Стохастический рецепт для той же сессии
    stochastic_recipe = engine.get_or_create_fuji_recipe(session, stochastic=True)
    assert stochastic_recipe.recipe_name != ""
    assert stochastic_recipe.validate() == []

    # 3. Карточка рецепта копайлота
    card = engine.format_copilot_recipe_card(session, slot_name="C2")
    assert "Fujifilm X-T4 • Рецепт в слот C2" in card
    assert "<pre>" in card


def test_build_fuji_recipe_for_concept():
    """Построение рецепта камеры под FusedPhotoConcept из режима «Штурм»."""
    from services.fuji_recipes import build_fuji_recipe_for_concept
    from services.style_fusion import (
        FusedPhotoConcept,
        StyleAssignment,
        StyleTriad,
    )

    concept = FusedPhotoConcept(
        title="Отражения в витрине",
        triad=StyleTriad(
            narrative=StyleAssignment(role="narrative", style="Экспрессионизм"),
            lighting=StyleAssignment(role="lighting", style="Конструктивизм"),
            optics=StyleAssignment(role="optics", style="Пиктореализм"),
        ),
        shooting_action="Съемка с голландским углом 20 градусов под козырьком.",
    )

    recipe = build_fuji_recipe_for_concept(concept)
    assert recipe.recipe_name == "X-T4: Отражения в витрине"
    assert recipe.film_simulation == "ACROS (+R Красный)"
    assert "голландским углом" in recipe.action_mechanic
    assert "Отражения в витрине" in recipe.notes
    assert recipe.validate() == []


def test_recipe_book_save_and_load(tmp_path):
    """Сохранение рецепта в книгу, персистентность и атомарная запись."""
    from services.fuji_recipes import (
        get_saved_recipe,
        load_saved_recipe_entries,
        load_saved_recipes,
        save_recipe_to_book,
    )

    book_file = tmp_path / "test_recipes.json"
    recipe1 = FujiRecipe(
        recipe_name="Тестовый Пикториализм",
        film_simulation="Classic Chrome",
        dynamic_range="DR200",
        highlight_tone=-2.0,
        shadow_tone=-1.0,
    )

    # 1. Сохранение
    ok = save_recipe_to_book(
        recipe1, user_id=12345, slot_hint="C2", file_path=book_file
    )
    assert ok is True
    assert book_file.exists()

    # 2. Чтение сырых записей
    entries = load_saved_recipe_entries(user_id=12345, file_path=book_file)
    assert len(entries) == 1
    assert entries[0]["recipe_name"] == "Тестовый Пикториализм"
    assert entries[0]["slot_hint"] == "C2"
    assert entries[0]["user_id"] == 12345
    assert "saved_at" in entries[0]

    # 3. Чтение объектов
    recipes = load_saved_recipes(user_id=12345, file_path=book_file)
    assert len(recipes) == 1
    assert recipes[0].film_simulation == "Classic Chrome"
    assert recipes[0].highlight_tone == -2.0

    # 4. Поиск по названию
    found = get_saved_recipe("тестовый пикториализм", user_id=12345, file_path=book_file)
    assert found is not None
    assert found.recipe_name == "Тестовый Пикториализм"

    # 5. Поиск несуществующего
    assert get_saved_recipe("Неизвестный", user_id=12345, file_path=book_file) is None


def test_recipe_book_update_existing(tmp_path):
    """Обновление существующего рецепта по имени без дублирования."""
    from services.fuji_recipes import (
        load_saved_recipes,
        save_recipe_to_book,
    )

    book_file = tmp_path / "test_recipes.json"
    r1 = FujiRecipe(recipe_name="Уникальный", film_simulation="Velvia/Яркий", clarity=0)
    save_recipe_to_book(r1, user_id=100, file_path=book_file)

    # Повторное сохранение с обновленными параметрами
    r2 = FujiRecipe(recipe_name="Уникальный", film_simulation="Velvia/Яркий", clarity=3)
    save_recipe_to_book(r2, user_id=100, file_path=book_file)

    recipes = load_saved_recipes(user_id=100, file_path=book_file)
    assert len(recipes) == 1
    assert recipes[0].clarity == 3


def test_recipe_book_delete(tmp_path):
    """Удаление рецепта из книги фотографа."""
    from services.fuji_recipes import (
        delete_saved_recipe,
        load_saved_recipes,
        save_recipe_to_book,
    )

    book_file = tmp_path / "test_recipes.json"
    r1 = FujiRecipe(recipe_name="Рецепт 1", film_simulation="ACROS")
    r2 = FujiRecipe(recipe_name="Рецепт 2", film_simulation="Classic Chrome")

    save_recipe_to_book(r1, user_id=10, file_path=book_file)
    save_recipe_to_book(r2, user_id=10, file_path=book_file)
    assert len(load_saved_recipes(user_id=10, file_path=book_file)) == 2

    # Удаление существующего
    del_ok = delete_saved_recipe("Рецепт 1", user_id=10, file_path=book_file)
    assert del_ok is True

    recipes_after = load_saved_recipes(user_id=10, file_path=book_file)
    assert len(recipes_after) == 1
    assert recipes_after[0].recipe_name == "Рецепт 2"

    # Удаление несуществующего
    assert delete_saved_recipe("Фантом", user_id=10, file_path=book_file) is False


def test_recipe_book_user_isolation(tmp_path):
    """Изоляция рецептов между разными пользователями."""
    from services.fuji_recipes import (
        load_saved_recipes,
        save_recipe_to_book,
    )

    book_file = tmp_path / "test_recipes.json"
    r_user1 = FujiRecipe(recipe_name="Рецепт Алисы", film_simulation="PROVIA/Стандартный")
    r_user2 = FujiRecipe(recipe_name="Рецепт Боба", film_simulation="ETERNA/Кино")

    save_recipe_to_book(r_user1, user_id=111, file_path=book_file)
    save_recipe_to_book(r_user2, user_id=222, file_path=book_file)

    alice_recipes = load_saved_recipes(user_id=111, file_path=book_file)
    bob_recipes = load_saved_recipes(user_id=222, file_path=book_file)

    assert len(alice_recipes) == 1
    assert alice_recipes[0].recipe_name == "Рецепт Алисы"

    assert len(bob_recipes) == 1
    assert bob_recipes[0].recipe_name == "Рецепт Боба"


def test_export_recipe_book_to_apple_notes(tmp_path, monkeypatch):
    """Экспорт книги рецептов в Apple Notes."""
    from services.fuji_recipes import (
        export_recipe_book_to_apple_notes,
        save_recipe_to_book,
    )

    book_file = tmp_path / "test_recipes.json"

    # 1. Экспорт пустой книги
    ok_empty, msg_empty = export_recipe_book_to_apple_notes(
        user_id=999, file_path=book_file
    )
    assert ok_empty is False
    assert "пуста" in msg_empty.lower()

    # 2. Добавляем рецепты
    r1 = FujiRecipe(recipe_name="Рецепт Альфа", film_simulation="Classic Chrome")
    r2 = FujiRecipe(recipe_name="Рецепт Бета", film_simulation="ACROS (+R Красный)")
    save_recipe_to_book(r1, user_id=999, slot_hint="C1", file_path=book_file)
    save_recipe_to_book(r2, user_id=999, slot_hint="C2", file_path=book_file)

    created_notes = []

    def mock_create_note(title: str, body: str, folder: str = "Фотопроекты"):
        created_notes.append({"title": title, "body": body, "folder": folder})
        return "x-coredata://mock/note-book-1"

    monkeypatch.setattr("services.apple_notes.ensure_folder", lambda f: True)
    monkeypatch.setattr("services.apple_notes.create_note", mock_create_note)

    ok, note_id = export_recipe_book_to_apple_notes(
        user_id=999, folder="Фотопроекты", file_path=book_file
    )
    assert ok is True
    assert note_id == "x-coredata://mock/note-book-1"
    assert len(created_notes) == 1
    assert "Коллекция рецептов фотографа" in created_notes[0]["title"]
    assert "Рецепт Альфа" in created_notes[0]["body"]
    assert "Рецепт Бета" in created_notes[0]["body"]
