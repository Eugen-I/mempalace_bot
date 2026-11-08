"""tests/test_photographer_gear.py — Unit-тесты для профиля арсенала фотографа."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from services.photographer_gear import (
    GearItem,
    GearProfile,
    categorize_gear_name,
    enrich_gear_item,
    format_gear_card,
    format_gear_context,
    get_default_gear_profile,
    load_gear_profile,
    remix_gear_for_concept,
    save_gear_profile,
)


def test_gear_item_serialization():
    item = GearItem(
        name="Гелиос 44-2 58mm f/2",
        category="lens",
        optical_traits="Закрученное боке",
        best_styles=["Импрессионизм"],
        notes="Кольцо диафрагмы без щелчков",
    )
    d = item.to_dict()
    assert d["name"] == "Гелиос 44-2 58mm f/2"
    assert d["category"] == "lens"
    assert d["optical_traits"] == "Закрученное боке"

    restored = GearItem.from_dict(d)
    assert restored.name == item.name
    assert restored.category == item.category
    assert restored.best_styles == ["Импрессионизм"]
    assert restored.notes == item.notes


def test_gear_profile_categories_and_all_items():
    prof = GearProfile()
    cam = GearItem(name="Fujifilm X-T4", category="camera")
    lens = GearItem(name="Гелиос 44-2", category="lens")
    filt = GearItem(name="Black Mist", category="filter")
    light = GearItem(name="Godox V1", category="lighting")
    acc = GearItem(name="Призма", category="accessory")

    prof.add_item(cam)
    prof.add_item(lens)
    prof.add_item(filt)
    prof.add_item(light)
    prof.add_item(acc)

    assert prof.cameras == [cam]
    assert prof.lenses == [lens]
    assert prof.filters == [filt]
    assert prof.lighting == [light]
    assert prof.accessories == [acc]

    all_items = prof.all_items()
    assert len(all_items) == 5
    assert cam in all_items
    assert acc in all_items


def test_gear_profile_serialization():
    prof = get_default_gear_profile()
    data = prof.to_dict()
    restored = GearProfile.from_dict(data)
    assert len(restored.cameras) == len(prof.cameras)
    assert len(restored.lenses) == len(prof.lenses)
    assert restored.cameras[0].name == "Fujifilm X-T4"


@pytest.mark.parametrize(
    "name,expected_category",
    [
        ("Fujifilm X-T4", "camera"),
        ("Тушка Canon R5", "camera"),
        ("Sony A7 III", "camera"),
        ("Гелиос 44-2 58mm f/2", "lens"),
        ("Fujinon XF 35mm f/1.4", "lens"),
        ("Монокль 50mm", "lens"),
        ("Black Pro-Mist 1/4", "filter"),
        ("Полярик CPL 67mm", "filter"),
        ("ND1000 фильтр", "filter"),
        ("Вспышка Godox V860", "lighting"),
        ("Софтбокс 60x60", "lighting"),
        ("Фонарь светодиодный", "lighting"),
        ("Хрустальная треугольная призма", "accessory"),
        ("Штатив карбоновый", "accessory"),
        ("Что-то неизвестное", "accessory"),
    ],
)
def test_categorize_gear_name(name, expected_category):
    assert categorize_gear_name(name) == expected_category


def test_load_and_save_gear_profile(tmp_path):
    file_path = tmp_path / "gear.json"

    # Когда файл отсутствует — создаётся дефолтный профиль
    prof1 = load_gear_profile(file_path)
    assert file_path.exists()
    assert len(prof1.cameras) >= 1
    assert prof1.cameras[0].name == "Fujifilm X-T4"

    # Модифицируем и сохраняем
    prof1.add_item(GearItem(name="Юпитер-9 85mm f/2", category="lens"))
    save_gear_profile(prof1, file_path)

    # Читаем повторно
    prof2 = load_gear_profile(file_path)
    lens_names = [lens.name for lens in prof2.lenses]
    assert "Юпитер-9 85mm f/2" in lens_names


def test_load_gear_profile_corrupted_fallback(tmp_path):
    file_path = tmp_path / "corrupted_gear.json"
    file_path.write_text("{bad json syntax", encoding="utf-8")

    prof = load_gear_profile(file_path)
    assert len(prof.cameras) >= 1
    assert prof.cameras[0].name == "Fujifilm X-T4"


@pytest.mark.asyncio
async def test_enrich_gear_item_happy_path():
    fake_res = AsyncMock()
    fake_res.final_answer = json.dumps({
        "optical_traits": "Мягкий рисунок с выраженным вихревым боке.",
        "best_styles": ["Импрессионизм", "Пиктореализм"],
        "notes": "Требует переходник M42-FX",
    })

    with patch("services.agent_engine.run_agent", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = fake_res
        item = await enrich_gear_item("Гелиос 44-2 58mm f/2")

    assert item.name == "Гелиос 44-2 58mm f/2"
    assert item.category == "lens"
    assert "вихревым боке" in item.optical_traits
    assert item.best_styles == ["Импрессионизм", "Пиктореализм"]
    assert item.notes == "Требует переходник M42-FX"


@pytest.mark.asyncio
async def test_enrich_gear_item_non_json_fallback():
    fake_res = AsyncMock()
    fake_res.final_answer = "Отличный объектив с мягким рисунком для портретов."

    with patch("services.agent_engine.run_agent", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = fake_res
        item = await enrich_gear_item("Гелиос 44-2")

    assert item.name == "Гелиос 44-2"
    assert "Отличный объектив" in item.optical_traits
    assert "Пиктореализм" in item.best_styles


@pytest.mark.asyncio
async def test_enrich_gear_item_exception_fallback():
    with patch("services.agent_engine.run_agent", side_effect=RuntimeError("Web error")):
        item = await enrich_gear_item("Кастомная линза")

    assert item.name == "Кастомная линза"
    assert item.category == "lens"
    assert item.optical_traits == "Пользовательское оборудование"


def test_remix_gear_for_concept_picks_matching_lens_and_accessories():
    prof = get_default_gear_profile()
    # Запрос на Импрессионизм должен предпочесть Гелиос 44-2
    remix = remix_gear_for_concept(["Импрессионизм"], profile=prof)
    assert remix["camera"] == "Fujifilm X-T4"
    assert "Гелиос" in remix["lens"]
    assert "summary" in remix
    assert "Fujifilm X-T4" in remix["summary"]

    # Запрос на Сюрреализм должен предпочесть призму в аксессуарах
    remix_surreal = remix_gear_for_concept(["Сюрреализм"], profile=prof)
    assert any("призма" in a.lower() for a in remix_surreal["accessories"])


def test_remix_gear_for_concept_empty_profile():
    empty_prof = GearProfile()
    remix = remix_gear_for_concept(["Сюрреализм"], profile=empty_prof)
    assert remix["camera"] == "Fujifilm X-T4"
    assert remix["lens"] == "Стандартный объектив"
    assert remix["accessories"] == []


def test_format_gear_context():
    prof = get_default_gear_profile()
    ctx = format_gear_context(prof)
    assert "[Арсенал фотографа (доступное оборудование)]" in ctx
    assert "Fujifilm X-T4" in ctx
    assert "Гелиос" in ctx
    assert "Black Pro-Mist" in ctx


def test_format_gear_card_html():
    prof = get_default_gear_profile()
    card = format_gear_card(prof)
    assert "🎒 <b>Арсенал фотографа</b>" in card
    assert "📷 <b>Камеры:</b>" in card
    assert "Fujifilm X-T4" in card
    assert "<!--" not in card  # Запрет HTML комментариев в Telegram

    empty = GearProfile()
    empty_card = format_gear_card(empty)
    assert "Арсенал пуст" in empty_card
