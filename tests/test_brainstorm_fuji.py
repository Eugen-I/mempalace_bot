"""tests/test_brainstorm_fuji.py — Unit-тесты интеграции рецептов Fujifilm X-T4 со Штурмом (Шаг D3).

Проверяет:
- Отображение блока внутрикамерного рецепта на Стр. 3 проекта.
- Наличие кнопки [ 🎛 Рецепт X-T4 ] в навигационной клавиатуре проекта.
- Callback bs_fuji_recipe:{idx} (отображение моноширинной карточки рецепта).
- Callback bs_recipe_save:{idx} (сохранение в постоянную книгу рецептов фотографа).
- Callback bs_recipe_export:{idx} (экспорт в Apple Notes в папку Фотопроекты).
"""

from unittest.mock import MagicMock
import pytest

from handlers import brainstorm as hb
import services.fuji_recipes as fr
from services.style_fusion import (
    FusedPhotoConcept,
    StyleAssignment,
    StyleTriad,
    build_concept_navigation_kb,
    format_concept_page,
)


class FakeUser:
    def __init__(self, uid=5555):
        self.id = uid


class FakeMessage:
    def __init__(self, uid=5555):
        self.from_user = FakeUser(uid)
        self.edits = []
        self.last_reply_markup = None

    async def edit_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        self.edits.append(text)
        self.last_reply_markup = reply_markup


class FakeCb:
    def __init__(self, uid=5555, data=""):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = FakeMessage(uid)
        self.answered = []

    async def answer(self, text=None, show_alert=False):
        self.answered.append((text, show_alert))


@pytest.fixture
def sample_concept():
    return FusedPhotoConcept(
        title="Геометрия теней",
        triad=StyleTriad(
            narrative=StyleAssignment(role="narrative", style="Конструктивизм"),
            lighting=StyleAssignment(role="lighting", style="Экспрессионизм"),
            optics=StyleAssignment(role="optics", style="Пиктореализм"),
        ),
        manifesto="Острые линии и графичность пространства.",
        scene_description="Диагональные балки моста в низком ключе.",
        lighting_setup="Жесткий боковой свет полуденного солнца.",
        shooting_action="Нижний ракурс с колен, выравнивание диагоналей.",
        camera_setup={"ISO": 160, "Диафрагма": "f/8", "Выдержка": "1/500s"},
        gear_recipe={"lens": "Fujinon XF 16-80mm f/4", "filter": "CPL поляризатор"},
        shooting_steps=["1. Найти диагональ.", "2. Зажать диафрагму до f/8."],
    )


def test_style_fusion_page3_displays_fuji_recipe(sample_concept):
    """Стр. 3 проекта отображает блок внутрикамерного рецепта Fujifilm X-T4."""
    page_text = format_concept_page(sample_concept, page=3, total_pages=4)

    assert "Рецепт камеры (слот C1):" in page_text
    assert "Имитация плёнки:" in page_text
    assert "Кривая:" in page_text
    assert "ББ:" in page_text
    assert "Зерно:" in page_text

    # Проверка Telegram HTML правил
    assert "<!--" not in page_text
    assert "<p>" not in page_text
    assert "<div>" not in page_text


def test_concept_navigation_kb_contains_fuji_recipe_button():
    """Навигационная клавиатура проекта содержит кнопку рецепта X-T4."""
    for page in range(1, 5):
        kb = build_concept_navigation_kb(concept_idx=1, page=page, total_pages=4)
        markup = kb.as_markup()
        callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
        assert "bs_fuji_recipe:1" in callbacks
        assert "bs_deepen:1" in callbacks
        assert "bs_back" in callbacks


@pytest.mark.asyncio
async def test_cb_concept_fuji_recipe(sample_concept, monkeypatch):
    """Callback bs_fuji_recipe:{idx} отображает карточку рецепта Fujifilm X-T4."""
    import config
    monkeypatch.setattr(config, "ALLOWED_IDS", {5555})
    hb._storm_data[5555] = {"ideas": [sample_concept]}

    cb = FakeCb(5555, data="bs_fuji_recipe:1")
    await hb.cb_concept_fuji_recipe(cb)

    assert len(cb.message.edits) == 1
    text = cb.message.edits[0]
    assert "Fujifilm X-T4 • Рецепт в слот C1" in text
    assert "<pre>" in text
    assert "«<b>X-T4: Геометрия теней</b>»" in text

    markup = cb.message.last_reply_markup
    callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert "bs_recipe_save:1" in callbacks
    assert "bs_recipe_export:1" in callbacks
    assert "bs_page:1:3" in callbacks


@pytest.mark.asyncio
async def test_cb_concept_recipe_save(sample_concept, tmp_path, monkeypatch):
    """Callback bs_recipe_save:{idx} сохраняет рецепт в fuji_saved_recipes.json."""
    import config
    monkeypatch.setattr(config, "ALLOWED_IDS", {5555})
    hb._storm_data[5555] = {"ideas": [sample_concept]}

    book_file = tmp_path / "fuji_saved_recipes.json"
    monkeypatch.setattr(fr, "RECIPES_BOOK_PATH", book_file)

    cb = FakeCb(5555, data="bs_recipe_save:1")
    await hb.cb_concept_recipe_save(cb)

    assert any("сохранён в книгу рецептов" in a[0] for a in cb.answered if a[0])

    saved = fr.load_saved_recipes(user_id=5555, file_path=book_file)
    assert len(saved) == 1
    assert "Геометрия теней" in saved[0].recipe_name


@pytest.mark.asyncio
async def test_cb_concept_recipe_export(sample_concept, monkeypatch):
    """Callback bs_recipe_export:{idx} выгружает рецепт в Apple Notes."""
    import config
    monkeypatch.setattr(config, "ALLOWED_IDS", {5555})
    hb._storm_data[5555] = {"ideas": [sample_concept]}

    mock_export = MagicMock(return_value="x-apple-note-concept-recipe")
    monkeypatch.setattr(fr, "export_fuji_recipe_to_apple_notes", mock_export)

    cb = FakeCb(5555, data="bs_recipe_export:1")
    await hb.cb_concept_recipe_export(cb)

    assert mock_export.called
    assert any("экспортирован в Apple Notes" in a[0] for a in cb.answered if a[0])


@pytest.mark.asyncio
async def test_cb_concept_recipe_session_expired(monkeypatch):
    """Обработка истечения сессии для callbacks рецептов штурма."""
    import config
    monkeypatch.setattr(config, "ALLOWED_IDS", {5555})
    hb._storm_data.pop(5555, None)

    cb_recipe = FakeCb(5555, data="bs_fuji_recipe:1")
    await hb.cb_concept_fuji_recipe(cb_recipe)
    assert any("Сессия истекла" in a[0] for a in cb_recipe.answered if a[0])

    cb_save = FakeCb(5555, data="bs_recipe_save:1")
    await hb.cb_concept_recipe_save(cb_save)
    assert any("Сессия истекла" in a[0] for a in cb_save.answered if a[0])

    cb_export = FakeCb(5555, data="bs_recipe_export:1")
    await hb.cb_concept_recipe_export(cb_export)
    assert any("Сессия истекла" in a[0] for a in cb_export.answered if a[0])
