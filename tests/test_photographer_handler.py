"""tests/test_photographer_handler.py — Unit-тесты для Telegram-обработчиков арсенала и механик."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram import types

import config
from handlers.photographer import (
    _gear_waiting,
    _mech_waiting,
    _pending_mechanic,
    cb_gear_add,
    cb_gear_cancel_input,
    cb_gear_close,
    cb_gear_reset_default,
    cb_gear_to_mechanics,
    cb_mech_add,
    cb_mech_cancel,
    cb_mech_cancel_input,
    cb_mech_close,
    cb_mech_confirm_save,
    cb_mech_to_gear,
    cmd_gear,
    cmd_mechanics,
    handle_gear_text_input,
    handle_mech_photo_input,
    handle_mech_text_input,
)
from services.photo_mechanics import VisualMechanic
from services.photographer_gear import GearItem

TEST_UIDS = {12345, 999, 888, 123, 555, 777, 111}


@pytest.fixture(autouse=True)
def clean_waiting_states(monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_IDS", TEST_UIDS)
    _gear_waiting.clear()
    _mech_waiting.clear()
    _pending_mechanic.clear()
    yield
    _gear_waiting.clear()
    _mech_waiting.clear()
    _pending_mechanic.clear()


def make_mock_message(text: str = "", user_id: int = 12345):
    msg = AsyncMock(spec=types.Message)
    msg.text = text
    msg.from_user = MagicMock()
    msg.from_user.id = user_id
    msg.answer = AsyncMock()
    msg.photo = None
    msg.document = None
    msg.bot = AsyncMock()
    return msg


def make_mock_callback(data: str, user_id: int = 12345):
    cb = AsyncMock(spec=types.CallbackQuery)
    cb.data = data
    cb.from_user = MagicMock()
    cb.from_user.id = user_id
    cb.answer = AsyncMock()
    cb.message = AsyncMock(spec=types.Message)
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.message.delete = AsyncMock()
    return cb


@pytest.mark.asyncio
async def test_cmd_gear():
    msg = make_mock_message("/gear")
    await cmd_gear(msg)
    msg.answer.assert_called_once()
    args, kwargs = msg.answer.call_args
    assert "Арсенал фотографа" in args[0]
    assert kwargs.get("parse_mode") == "HTML"


@pytest.mark.asyncio
async def test_cmd_mechanics():
    msg = make_mock_message("/mechanics")
    await cmd_mechanics(msg)
    msg.answer.assert_called_once()
    args, kwargs = msg.answer.call_args
    assert "Банк фотомеханик" in args[0]
    assert kwargs.get("parse_mode") == "HTML"


@pytest.mark.asyncio
async def test_gear_navigation_and_cancel():
    cb = make_mock_callback("gear_add", user_id=999)
    await cb_gear_add(cb)
    assert 999 in _gear_waiting
    cb.message.answer.assert_called_once()

    cb_cancel = make_mock_callback("gear_cancel_input", user_id=999)
    await cb_gear_cancel_input(cb_cancel)
    assert 999 not in _gear_waiting
    cb_cancel.message.edit_text.assert_called_once()


@pytest.mark.asyncio
async def test_gear_reset_default():
    cb = make_mock_callback("gear_reset_default")
    await cb_gear_reset_default(cb)
    cb.answer.assert_called_once_with("Сброшено к базовому набору")
    cb.message.edit_text.assert_called_once()


@pytest.mark.asyncio
async def test_gear_close():
    cb = make_mock_callback("gear_close")
    await cb_gear_close(cb)
    cb.message.delete.assert_called_once()


@pytest.mark.asyncio
async def test_mech_navigation_and_cancel():
    cb = make_mock_callback("mech_add", user_id=888)
    await cb_mech_add(cb)
    assert 888 in _mech_waiting
    cb.message.answer.assert_called_once()

    cb_cancel = make_mock_callback("mech_cancel_input", user_id=888)
    await cb_mech_cancel_input(cb_cancel)
    assert 888 not in _mech_waiting
    cb_cancel.message.edit_text.assert_called_once()


@pytest.mark.asyncio
async def test_mech_close():
    cb = make_mock_callback("mech_close")
    await cb_mech_close(cb)
    cb.message.delete.assert_called_once()


@pytest.mark.asyncio
async def test_cross_navigation_callbacks():
    cb_to_mech = make_mock_callback("gear_to_mechanics")
    await cb_gear_to_mechanics(cb_to_mech)
    cb_to_mech.message.edit_text.assert_called_once()
    assert "Банк фотомеханик" in cb_to_mech.message.edit_text.call_args[0][0]

    cb_to_gear = make_mock_callback("mech_to_gear")
    await cb_mech_to_gear(cb_to_gear)
    cb_to_gear.message.edit_text.assert_called_once()
    assert "Арсенал фотографа" in cb_to_gear.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_gear_text_input():
    _gear_waiting[123] = True
    msg = make_mock_message("Юпитер-37А 135mm f/3.5", user_id=123)
    status_msg = AsyncMock()
    msg.answer.return_value = status_msg

    fake_item = GearItem(
        name="Юпитер-37А 135mm f/3.5",
        category="lens",
        optical_traits="Мягкое боке, отличная резкость",
        best_styles=["Пиктореализм"],
    )

    with patch("handlers.photographer.enrich_gear_item", new_callable=AsyncMock) as mock_enrich:
        mock_enrich.return_value = fake_item
        await handle_gear_text_input(msg)

    assert 123 not in _gear_waiting
    status_msg.edit_text.assert_called_once()
    text = status_msg.edit_text.call_args[0][0]
    assert "Техника добавлена в арсенал" in text
    assert "Юпитер-37А" in text


@pytest.mark.asyncio
async def test_handle_mech_text_input_and_save():
    _mech_waiting[555] = True
    msg = make_mock_message("Двойная экспозиция с силуэтом и ветками", user_id=555)
    status_msg = AsyncMock()
    msg.answer.return_value = status_msg

    fake_mech = VisualMechanic(
        id="user_test_silhouette",
        title="Силуэтная мультиэкспозиция",
        styles=["Сюрреализм"],
        visual_outcome="Наложение веток внутри фигуры",
        camera_setup={"Приём": "Мультиэкспозиция (2 кадра)"},
    )

    with patch(
        "handlers.photographer.parse_mechanic_from_text", new_callable=AsyncMock,
    ) as mock_parse:
        mock_parse.return_value = fake_mech
        await handle_mech_text_input(msg)

    assert 555 not in _mech_waiting
    assert _pending_mechanic[555] == fake_mech
    status_msg.edit_text.assert_called_once()
    assert "Силуэтная мультиэкспозиция" in status_msg.edit_text.call_args[0][0]

    # Теперь подтверждаем сохранение
    cb_confirm = make_mock_callback("mech_confirm_save", user_id=555)
    with patch("handlers.photographer.add_user_mechanic") as mock_add:
        await cb_mech_confirm_save(cb_confirm)
        mock_add.assert_called_once_with(fake_mech)

    assert 555 not in _pending_mechanic
    cb_confirm.message.edit_text.assert_called_once()
    assert "успешно сохранён" in cb_confirm.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_mech_photo_input_happy_path(tmp_path):
    _mech_waiting[777] = True
    msg = make_mock_message("", user_id=777)
    status_msg = AsyncMock()
    msg.answer.return_value = status_msg

    fake_photo = MagicMock()
    fake_photo.file_id = "test_file_id"
    msg.photo = [fake_photo]

    fake_file_info = MagicMock()
    fake_file_info.file_path = "/tmp/fake.jpg"
    msg.bot.get_file.return_value = fake_file_info

    fake_mech = VisualMechanic(
        id="user_ocr_mech",
        title="Акварельный прием из фото",
        styles=["Импрессионизм"],
    )

    with patch("handlers.photographer.extract_text_from_image", return_value="Dark mode 1/6s"):
        with patch(
            "handlers.photographer.parse_mechanic_from_text", new_callable=AsyncMock,
        ) as mock_p:
            mock_p.return_value = fake_mech
            await handle_mech_photo_input(msg)

    assert 777 not in _mech_waiting
    assert _pending_mechanic[777] == fake_mech
    call_args = status_msg.edit_text.call_args
    assert "Акварельный прием из фото" in call_args[0][0]
    assert call_args[1]["parse_mode"] == "HTML"
    assert "reply_markup" in call_args[1]


@pytest.mark.asyncio
async def test_cb_mech_cancel():
    _pending_mechanic[111] = VisualMechanic(id="to_cancel", title="Приём")
    cb = make_mock_callback("mech_cancel", user_id=111)
    await cb_mech_cancel(cb)
    assert 111 not in _pending_mechanic
    cb.message.edit_text.assert_called_once_with("❌ Сохранение приёма отменено.")
