"""tests/test_photo_mechanics.py — Unit-тесты для банка фотомеханик."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.photo_mechanics import (
    VisualMechanic,
    add_user_mechanic,
    extract_text_from_image,
    format_mechanic_card,
    format_mechanics_context,
    format_mechanics_list,
    get_factory_mechanics,
    get_relevant_mechanics,
    load_mechanics,
    parse_mechanic_from_text,
    save_mechanics,
)


def test_visual_mechanic_serialization():
    mech = VisualMechanic(
        id="test_mech",
        title="Тестовый приём",
        styles=["Импрессионизм"],
        visual_outcome="Мягкое свечение",
        camera_setup={"Выдержка": "1/60", "Диафрагма": "f/2"},
        physical_action="Вращение объектива",
        required_gear=["Гелиос"],
        tags=["боке", "тест"],
    )
    d = mech.to_dict()
    assert d["id"] == "test_mech"
    assert d["title"] == "Тестовый приём"
    assert d["styles"] == ["Импрессионизм"]
    assert d["camera_setup"]["Выдержка"] == "1/60"

    restored = VisualMechanic.from_dict(d)
    assert restored.id == mech.id
    assert restored.title == mech.title
    assert restored.camera_setup == mech.camera_setup
    assert restored.tags == ["боке", "тест"]


def test_get_factory_mechanics():
    factory = get_factory_mechanics()
    assert len(factory) >= 4
    ids = [m.id for m in factory]
    assert "watercolor_dark_multiexposure" in ids
    assert "pictorial_sfumato_monocle" in ids
    assert "expressionist_caligari_shadows" in ids
    assert "surreal_prism_refraction" in ids

    # Проверяем параметры акварельного рецепта
    watercolor = next(m for m in factory if m.id == "watercolor_dark_multiexposure")
    assert "Импрессионизм" in watercolor.styles
    assert watercolor.camera_setup.get("Режим мультиэкспозиции") == "Тёмный"
    assert watercolor.camera_setup.get("Выдержка") == '1/6"'
    assert watercolor.camera_setup.get("Компенсация экспозиции (EV)") == "-1.0"
    assert "Микро-тремор" in watercolor.camera_setup.get("Движение камеры / Руки", "")


def test_load_and_save_mechanics(tmp_path):
    file_path = tmp_path / "mechs.json"

    # При отсутствии файла создаются заводские
    mechs = load_mechanics(file_path)
    assert file_path.exists()
    assert len(mechs) >= 4

    # Добавляем новую
    new_mech = VisualMechanic(id="user_custom", title="Кастомный приём")
    save_mechanics(mechs + [new_mech], file_path)

    reloaded = load_mechanics(file_path)
    assert any(m.id == "user_custom" for m in reloaded)


def test_load_mechanics_corrupted_fallback(tmp_path):
    file_path = tmp_path / "corrupted_mechs.json"
    file_path.write_text("invalid json!", encoding="utf-8")

    mechs = load_mechanics(file_path)
    assert len(mechs) >= 4
    assert any(m.id == "watercolor_dark_multiexposure" for m in mechs)


def test_add_user_mechanic(tmp_path):
    file_path = tmp_path / "mechs.json"
    new_mech = VisualMechanic(id="test_id", title="Мой приём", styles=["Сюрреализм"])
    add_user_mechanic(new_mech, path=file_path)

    loaded = load_mechanics(file_path)
    assert any(m.id == "test_id" for m in loaded)

    # Повторное добавление с тем же id обновляет приём без дубликатов
    updated_mech = VisualMechanic(id="test_id", title="Обновлённый приём")
    add_user_mechanic(updated_mech, path=file_path)
    reloaded = load_mechanics(file_path)
    matches = [m for m in reloaded if m.id == "test_id"]
    assert len(matches) == 1
    assert matches[0].title == "Обновлённый приём"


def test_extract_text_from_image_mock():
    mock_img = MagicMock()
    with patch("PIL.Image.open", return_value=mock_img):
        with patch("pytesseract.image_to_string", return_value="Multi-exposure Dark 1/6s"):
            res = extract_text_from_image(b"fake_bytes")
            assert res == "Multi-exposure Dark 1/6s"


def test_extract_text_from_image_error_fallback():
    with patch("PIL.Image.open", side_effect=Exception("Decode error")):
        res = extract_text_from_image(b"broken_bytes")
        assert res == ""


@pytest.mark.asyncio
async def test_parse_mechanic_from_text_happy_path():
    llm_payload = {
        "title": "Световая кисть в тумане",
        "styles": ["Пиктореализм"],
        "visual_outcome": "Мягкие светящиеся дорожки",
        "camera_setup": {
            "Выдержка": '2"',
            "Диафрагма": "f/8",
        },
        "physical_action": "Движение фонариком в темноте",
        "required_gear": ["Штатив", "Фонарь"],
        "tags": ["свет", "туман"],
    }

    with patch("services.ai_engine.get_ai_response_async", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = json.dumps(llm_payload)
        mech = await parse_mechanic_from_text("Снимаем ночью на выдержке 2 секунды с фонариком")

    assert mech is not None
    assert mech.title == "Световая кисть в тумане"
    assert mech.styles == ["Пиктореализм"]
    assert mech.camera_setup["Выдержка"] == '2"'
    assert mech.source == "user"
    assert mech.id.startswith("user_")


@pytest.mark.asyncio
async def test_parse_mechanic_from_text_empty_or_failure():
    assert await parse_mechanic_from_text("   ") is None

    with patch("services.ai_engine.get_ai_response_async", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = "Невалидный ответ без JSON"
        mech = await parse_mechanic_from_text("Текст рецепта")
        assert mech is None


def test_get_relevant_mechanics():
    mechs = get_factory_mechanics()
    with patch("services.photo_mechanics.load_mechanics", return_value=mechs):
        # Поиск по стилю Импрессионизм и ключевому слову акварель
        relevant = get_relevant_mechanics(
            topic="акварельный пейзаж в парке", styles=["Импрессионизм"], limit=1,
        )
        assert len(relevant) == 1
        assert relevant[0].id == "watercolor_dark_multiexposure"


def test_format_mechanics_context():
    mechs = [
        VisualMechanic(
            id="m1",
            title="Приём 1",
            styles=["Сюрреализм"],
            visual_outcome="Раздвоение",
            camera_setup={"Выдержка": "1/125"},
            physical_action="Вращение призмы",
        )
    ]
    ctx = format_mechanics_context(mechs)
    assert "[Банк проверенных фотомеханик" in ctx
    assert "Приём 1" in ctx
    assert "Раздвоение" in ctx
    assert "1/125" in ctx

    assert format_mechanics_context([]) == ""


def test_format_mechanic_card():
    mech = VisualMechanic(
        id="m1",
        title="Тест <HTML & спецсимволы>",
        styles=["Экспрессионизм"],
        visual_outcome="Контрастный свет",
        camera_setup={"Выдержка": "1/500"},
        physical_action="Наклон",
        required_gear=["Вспышка"],
    )
    card = format_mechanic_card(mech)
    assert "🎨 <b>Фотоприём: Тест &lt;HTML &amp; спецсимволы&gt;</b>" in card
    assert "1/500" in card
    assert "<!--" not in card


def test_format_mechanics_list():
    mechs = get_factory_mechanics()
    text = format_mechanics_list(mechs)
    assert "📚 <b>Банк фотомеханик" in text
    assert "Акварельная лессировка" in text
    assert "<!--" not in text

    empty_text = format_mechanics_list([])
    assert "Банк фотомеханик пуст" in empty_text


def test_format_mechanics_context_sanitizes_double_quotes():
    """Выдержка вида 1/6\" заменяется на '1/6 с' в контексте для LLM."""
    mechs = get_factory_mechanics()
    ctx = format_mechanics_context(mechs)
    assert '1/6"' not in ctx
    assert '1/125"' not in ctx
    assert "1/6 с" in ctx
