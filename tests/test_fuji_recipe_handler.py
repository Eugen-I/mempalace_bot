"""Unit-тесты для Telegram-обработчиков рецептов Fujifilm X-T4 (Шаг D2, FR-2).

Проверяет:
- Формирование клавиатуры слотов C1-C7 и кнопок Cadavre Exquis.
- Колбэк просмотра рецепта в полевом ассистенте (cp_recipe_view).
- Переключение между пользовательскими слотами (cp_recipe_slot).
- Стохастический роллер Cadavre Exquis (cp_recipe_stochastic).
- Сброс к каноническому рецепту проекта (cp_recipe_reset).
- Экспорт рецепта в Apple Notes и обработку ошибок (cp_recipe_export).
- Команду /recipe (/рецепт, /cadavre) с сессией и в автономном режиме.
- Повторный стохастический бросок без сессии (cp_recipe_standalone_roll).
"""

from unittest.mock import patch
import pytest

from handlers import copilot as hc
import services.copilot_engine as engine
from services.copilot_session import CopilotSessionManager


class FakeUser:
    def __init__(self, uid=7777):
        self.id = uid


class FakeStatus:
    def __init__(self):
        self.edits = []
        self.last_kw = {}

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)
        self.last_kw = {"parse_mode": parse_mode, "reply_markup": reply_markup}


class FakeMessage:
    def __init__(self, uid=7777, text=""):
        self.from_user = FakeUser(uid)
        self.chat = type("C", (), {"id": 1})()
        self.text = text
        self.answers = []
        self.edits = []
        self.last_reply_markup = None

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append(text)
        self.last_reply_markup = reply_markup
        status = FakeStatus()
        return status

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)
        self.last_reply_markup = reply_markup


class FakeCb:
    def __init__(self, uid=7777, data=""):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = FakeMessage(uid)
        self.answered = []

    async def answer(self, text=None, show_alert=False):
        self.answered.append((text, show_alert))


@pytest.fixture
def temp_manager(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "ALLOWED_IDS", {7777})
    mgr = CopilotSessionManager(file_path=tmp_path / "fuji_handlers_test.json")
    monkeypatch.setattr(hc, "get_copilot_manager", lambda: mgr)
    monkeypatch.setattr(engine, "get_copilot_manager", lambda: mgr)
    return mgr


@pytest.fixture
def active_session(temp_manager):
    session = temp_manager.create_or_replace_session(7777, "Ночной сюрреализм")
    session.stage = "completed"
    session.selected_styles = ["Сюрреализм", "Экспрессионизм"]
    session.tech_preferences = {
        "support": "С рук (микро-ICM)",
        "lens": "Гелиос 44-2 58mm f/2",
        "film_sim": "Classic Chrome",
    }
    temp_manager.save_session(session)
    return session


def test_build_fuji_recipe_kb_slots_and_active_indicator():
    """Проверка формирования инлайн-клавиатуры рецепта с индикацией активного слота."""
    kb_c1 = hc.build_fuji_recipe_kb("C1")
    # Проверяем наличие индикатора • C1 •
    buttons_c1 = [btn.text for row in kb_c1.inline_keyboard for btn in row]
    assert "• C1 •" in buttons_c1
    assert "C2" in buttons_c1
    assert "C7" in buttons_c1
    assert "🎲 Сюрреалистический Cadavre Exquis" in buttons_c1
    assert "🎯 Рецепт проекта" in buttons_c1
    assert "🍏 В Apple Notes" in buttons_c1
    assert "📋 К полевому чек-листу" in buttons_c1

    # Проверяем переключение слота на C3
    kb_c3 = hc.build_fuji_recipe_kb("C3")
    buttons_c3 = [btn.text for row in kb_c3.inline_keyboard for btn in row]
    assert "• C3 •" in buttons_c3
    assert "C1" in buttons_c3


@pytest.mark.asyncio
async def test_cb_copilot_recipe_view(active_session):
    """Открытие карточки внутрикамерного рецепта из меню полевого ассистента."""
    cb = FakeCb(7777, data="cp_recipe_view:C1")
    await hc.cb_copilot_recipe_view(cb)

    assert len(cb.message.edits) == 1
    text = cb.message.edits[0]
    assert "Fujifilm X-T4 • Рецепт в слот C1" in text
    assert "<pre>" in text
    assert "ИМИТАЦИЯ ПЛЁНКИ:" in text


@pytest.mark.asyncio
async def test_cb_copilot_recipe_slot_switch(active_session):
    """Переключение слота камеры (C1 -> C5)."""
    cb = FakeCb(7777, data="cp_recipe_slot:C5")
    await hc.cb_copilot_recipe_slot(cb)

    assert len(cb.message.edits) == 1
    text = cb.message.edits[0]
    assert "Рецепт в слот C5" in text
    assert any("Слот C5" in a[0] for a in cb.answered if a[0])


@pytest.mark.asyncio
async def test_cb_copilot_recipe_stochastic_roll(active_session, temp_manager):
    """Стохастический сюрреалистический бросок Cadavre Exquis."""
    cb = FakeCb(7777, data="cp_recipe_stochastic:C2")
    await hc.cb_copilot_recipe_stochastic(cb)

    assert len(cb.message.edits) == 1
    text = cb.message.edits[0]
    assert "Рецепт в слот C2" in text

    # Проверяем, что в сессии сохранился сгенерированный рецепт
    updated = temp_manager.get_session(7777)
    assert updated is not None
    saved_recipe = updated.tech_preferences.get("fuji_recipe")
    assert saved_recipe is not None
    assert "Стохастический рецепт Cadavre Exquis" in saved_recipe.get("notes", "")
    assert any("Cadavre Exquis" in a[0] for a in cb.answered if a[0])


@pytest.mark.asyncio
async def test_cb_copilot_recipe_reset_to_project(active_session, temp_manager):
    """Сброс к каноническому рецепту под стили проекта."""
    # Задаем сначала стохастический рецепт
    active_session.tech_preferences["fuji_recipe"] = {
        "recipe_name": "Случайный",
        "film_simulation": "Сепия",
        "dynamic_range": "DR100",
    }
    temp_manager.save_session(active_session)

    cb = FakeCb(7777, data="cp_recipe_reset:C1")
    await hc.cb_copilot_recipe_reset(cb)

    assert len(cb.message.edits) == 1
    text = cb.message.edits[0]
    # В active_session стили: ["Сюрреализм", "Экспрессионизм"]. Экспрессионизм дает ACROS (+R)
    assert "ACROS" in text
    assert any("сброшен к стилистике проекта" in a[0] for a in cb.answered if a[0])


@pytest.mark.asyncio
async def test_cb_copilot_recipe_export_success(active_session):
    """Экспорт рецепта в Apple Notes со всплывающим уведомлением."""
    cb = FakeCb(7777, data="cp_recipe_export:C3")
    with patch(
        "handlers.copilot.export_fuji_recipe_to_apple_notes",
        return_value="x-coredata://note-fuji-1",
    ) as mock_export:
        await hc.cb_copilot_recipe_export(cb)

    mock_export.assert_called_once()
    assert any("успешно сохранен в Apple Notes" in a[0] for a in cb.answered if a[0])


@pytest.mark.asyncio
async def test_cb_copilot_recipe_export_failure(active_session):
    """Обработка ошибки при экспорте рецепта в Apple Notes."""
    cb = FakeCb(7777, data="cp_recipe_export:C1")
    with patch(
        "handlers.copilot.export_fuji_recipe_to_apple_notes",
        side_effect=RuntimeError("AppleScript failure"),
    ):
        await hc.cb_copilot_recipe_export(cb)

    assert any("Не удалось создать заметку" in a[0] for a in cb.answered if a[0])


@pytest.mark.asyncio
async def test_cmd_recipe_with_active_session(active_session):
    """Вызов команды /recipe при наличии активной сессии."""
    msg = FakeMessage(7777, text="/recipe")
    await hc.cmd_recipe(msg)

    assert len(msg.answers) == 1
    text = msg.answers[0]
    assert "Fujifilm X-T4 • Рецепт в слот C1" in text
    assert msg.last_reply_markup is not None


@pytest.mark.asyncio
async def test_cmd_recipe_without_session_standalone(temp_manager):
    """Вызов команды /recipe без сессии: автономный Cadavre Exquis."""
    msg = FakeMessage(7777, text="/cadavre")
    await hc.cmd_recipe(msg)

    assert len(msg.answers) == 1
    text = msg.answers[0]
    assert "Fujifilm X-T4 • Рецепт в слот C1" in text
    assert "<pre>" in text
    assert msg.last_reply_markup is not None


@pytest.mark.asyncio
async def test_cb_copilot_recipe_standalone_roll():
    """Повторный автономный бросок кубиков Cadavre Exquis."""
    cb = FakeCb(7777, data="cp_recipe_standalone_roll:C1")
    await hc.cb_copilot_recipe_standalone_roll(cb)

    assert len(cb.message.edits) == 1
    text = cb.message.edits[0]
    assert "Fujifilm X-T4 • Рецепт в слот C1" in text
    assert any("🎲" in a[0] for a in cb.answered if a[0])


@pytest.mark.asyncio
async def test_cb_copilot_recipe_missing_session(temp_manager):
    """Колбэк рецепта при отсутствующей сессии возвращает уведомление."""
    cb = FakeCb(1111, data="cp_recipe_view:C1")
    await hc.cb_copilot_recipe_view(cb)

    assert any("Сессия не найдена" in a[0] for a in cb.answered if a[0])


def test_build_fuji_recipe_kb_contains_save_book():
    """Клавиатура рецепта содержит кнопку сохранения в книгу рецептов."""
    kb = hc.build_fuji_recipe_kb("C3")
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "cp_recipe_save_book:C3" in callbacks
    assert "cp_recipe_export:C3" in callbacks
    assert "cp_recipe_reset:C3" in callbacks


@pytest.mark.asyncio
async def test_cb_copilot_recipe_save_book(active_session, tmp_path, monkeypatch):
    """Сохранение активного рецепта сессии в постоянную книгу по кнопке."""
    import services.fuji_recipes as fr
    book_file = tmp_path / "fuji_saved_recipes.json"
    monkeypatch.setattr(fr, "RECIPES_BOOK_PATH", book_file)

    cb = FakeCb(7777, data="cp_recipe_save_book:C1")
    await hc.cb_copilot_recipe_save_book(cb)

    assert any("сохранён в книгу рецептов" in a[0] for a in cb.answered if a[0])
    # Проверяем, что рецепт действительно в файле
    saved = fr.load_saved_recipes(user_id=7777, file_path=book_file)
    assert len(saved) == 1
    assert saved[0].recipe_name != ""


@pytest.mark.asyncio
async def test_cmd_myrecipes_empty(temp_manager, tmp_path, monkeypatch):
    """Команда /myrecipes при пустой книге рецептов."""
    import services.fuji_recipes as fr
    book_file = tmp_path / "fuji_empty_recipes.json"
    monkeypatch.setattr(fr, "RECIPES_BOOK_PATH", book_file)

    msg = FakeMessage(7777, text="/myrecipes")
    await hc.cmd_myrecipes(msg)

    assert len(msg.answers) == 1
    text = msg.answers[0]
    assert "Книга рецептов Fujifilm X-T4 пуста" in text
    assert msg.last_reply_markup is not None


@pytest.mark.asyncio
async def test_cmd_myrecipes_with_entries(temp_manager, tmp_path, monkeypatch):
    """Команда /myrecipes при наличии сохраненных рецептов."""
    import services.fuji_recipes as fr
    book_file = tmp_path / "fuji_saved_recipes.json"
    monkeypatch.setattr(fr, "RECIPES_BOOK_PATH", book_file)

    r1 = fr.FujiRecipe(recipe_name="Тестовый Классик", film_simulation="Classic Chrome")
    r2 = fr.FujiRecipe(recipe_name="Тестовый Вельвия", film_simulation="Velvia/Яркий")
    fr.save_recipe_to_book(r1, user_id=7777, slot_hint="C1", file_path=book_file)
    fr.save_recipe_to_book(r2, user_id=7777, slot_hint="C2", file_path=book_file)

    msg = FakeMessage(7777, text="/myrecipes")
    await hc.cmd_myrecipes(msg)

    assert len(msg.answers) == 1
    text = msg.answers[0]
    assert "сохранено: 2" in text
    assert "Тестовый Классик" in text
    assert "Тестовый Вельвия" in text
    # Проверяем инлайн-кнопки
    markup = msg.last_reply_markup
    callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert "fbook_view:1" in callbacks
    assert "fbook_view:2" in callbacks
    assert "fbook_export_all" in callbacks


@pytest.mark.asyncio
async def test_cb_fbook_view_and_del(temp_manager, tmp_path, monkeypatch):
    """Просмотр карточки рецепта из книги и его последующее удаление."""
    import services.fuji_recipes as fr
    book_file = tmp_path / "fuji_saved_recipes.json"
    monkeypatch.setattr(fr, "RECIPES_BOOK_PATH", book_file)

    r = fr.FujiRecipe(recipe_name="Удаляемый рецепт", film_simulation="ACROS")
    fr.save_recipe_to_book(r, user_id=7777, slot_hint="C1", file_path=book_file)

    # 1. Просмотр
    cb_view = FakeCb(7777, data="fbook_view:1")
    await hc.cb_fbook_view(cb_view)

    assert len(cb_view.message.edits) == 1
    text = cb_view.message.edits[0]
    assert "Удаляемый рецепт" in text
    assert "<pre>" in text
    view_markup = cb_view.message.last_reply_markup
    view_cbs = [btn.callback_data for row in view_markup.inline_keyboard for btn in row]
    assert "fbook_del:1" in view_cbs
    assert "fbook_list" in view_cbs

    # 2. Удаление
    cb_del = FakeCb(7777, data="fbook_del:1")
    await hc.cb_fbook_del(cb_del)
    assert any("удалён" in a[0] for a in cb_del.answered if a[0])
    assert len(fr.load_saved_recipes(user_id=7777, file_path=book_file)) == 0


@pytest.mark.asyncio
async def test_cb_fbook_export_and_list(temp_manager, tmp_path, monkeypatch):
    """Экспорт рецепта в Apple Notes и возврат к списку книги."""
    import services.fuji_recipes as fr
    book_file = tmp_path / "fuji_saved_recipes.json"
    monkeypatch.setattr(fr, "RECIPES_BOOK_PATH", book_file)

    r = fr.FujiRecipe(recipe_name="Экспортный рецепт", film_simulation="Classic Chrome")
    fr.save_recipe_to_book(r, user_id=7777, slot_hint="C1", file_path=book_file)

    monkeypatch.setattr(fr, "export_fuji_recipe_to_apple_notes", lambda *a, **kw: "x-note-1")
    monkeypatch.setattr(
        fr, "export_recipe_book_to_apple_notes", lambda *a, **kw: (True, "x-note-all")
    )

    # Экспорт одного рецепта
    cb_exp_one = FakeCb(7777, data="fbook_export_one:1")
    await hc.cb_fbook_export_one(cb_exp_one)
    assert any("экспортирован в Apple Notes" in a[0] for a in cb_exp_one.answered if a[0])

    # Экспорт всей книги
    cb_exp_all = FakeCb(7777, data="fbook_export_all")
    await hc.cb_fbook_export_all(cb_exp_all)
    assert any("Вся книга рецептов экспортирована" in a[0] for a in cb_exp_all.answered if a[0])

    # Возврат к списку
    cb_list = FakeCb(7777, data="fbook_list")
    await hc.cb_fbook_list(cb_list)
    assert len(cb_list.message.edits) == 1
    assert "Книга рецептов Fujifilm X-T4" in cb_list.message.edits[0]
