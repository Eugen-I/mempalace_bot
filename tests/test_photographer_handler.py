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
    cb_gear_add_list,
    cb_gear_cancel_input,
    cb_gear_category,
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
    process_bulk_gear_input,
)
from services.photo_mechanics import VisualMechanic
from services.photographer_gear import GearItem

TEST_UIDS = {12345, 999, 888, 123, 555, 777, 111, 54321}


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
    msg.chat = MagicMock()
    msg.chat.id = user_id
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
    with patch("handlers.photographer.save_gear_profile") as mock_save:
        await cb_gear_reset_default(cb)
        mock_save.assert_called_once()
    cb.answer.assert_called_once_with("Сброшено к базовому набору")
    cb.message.edit_text.assert_called_once()


@pytest.mark.asyncio
async def test_gear_close():
    cb = make_mock_callback("gear_close", user_id=999)
    await cb_gear_close(cb)
    cb.message.edit_text.assert_called_once()
    assert "Штурм" in cb.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_gear_category_navigation():
    cb = make_mock_callback("gear_cat_lens", user_id=999)
    await cb_gear_category(cb)
    cb.message.edit_text.assert_called_once()
    text = cb.message.edit_text.call_args[0][0]
    assert "Объективы" in text


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
    cb = make_mock_callback("mech_close", user_id=999)
    await cb_mech_close(cb)
    cb.message.edit_text.assert_called_once()
    assert "Штурм" in cb.message.edit_text.call_args[0][0]


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

    with patch("handlers.photographer.enrich_gear_item", new_callable=AsyncMock) as mock_enrich, \
         patch("handlers.photographer.save_gear_profile") as mock_save:
        mock_enrich.return_value = fake_item
        await handle_gear_text_input(msg)
        mock_save.assert_called_once()

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


@pytest.mark.asyncio
async def test_cb_gear_add_list():
    cb = make_mock_callback("gear_add_list", user_id=777)
    await cb_gear_add_list(cb)
    assert _gear_waiting[777] == "list"
    cb.message.answer.assert_called_once()
    assert "списком" in cb.message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_gear_bulk_text_input(tmp_path):
    _gear_waiting[123] = "list"
    raw = (
        "Фотокамера Fujifilm X-T4. Объективы: 1. Pentacon 2.8/29, 2. Kamlan 50mm F1.1.\n"
        "Свотофильтр: K&F ND-Filtr 2-400nd.\n"
        "Фотовспышка Godox V1F."
    )
    msg = make_mock_message(raw, user_id=123)
    status_msg = AsyncMock()
    msg.answer.return_value = status_msg

    with patch("handlers.photographer.enrich_gear_profile") as mock_enrich:
        from services.photographer_gear import GearItem, GearProfile
        fake_prof = GearProfile()
        fake_prof.add_item(GearItem(name="Fujifilm X-T4", category="camera"))
        fake_prof.add_item(GearItem(name="Pentacon 2.8/29", category="lens"))
        fake_prof.add_item(GearItem(name="Kamlan 50mm F1.1", category="lens"))
        fake_prof.add_item(GearItem(name="K&F ND-Filtr 2-400nd", category="filter"))
        fake_prof.add_item(GearItem(name="Godox V1F", category="lighting"))
        mock_enrich.return_value = fake_prof

        with patch("handlers.photographer.save_gear_profile") as mock_save:
            await handle_gear_text_input(msg)
            assert mock_save.called

    assert 123 not in _gear_waiting
    assert status_msg.edit_text.called
    final_text = status_msg.edit_text.call_args[0][0]
    assert "Арсенал успешно сформирован" in final_text


@pytest.mark.asyncio
async def test_messages_interception_for_gear_in_storm_waiting():
    from handlers.brainstorm import _storm_waiting
    from handlers.messages import process_user_message
    from services.copilot_session import get_copilot_manager

    uid = 54321
    get_copilot_manager().clear_session(uid)
    _storm_waiting[uid] = True
    gear_text = (
        "Фотокамера Fujifilm X-T4. Объективы: 1. Pentacon 2.8/29, 2. Kamlan 50mm F1.1.\n"
        "Свотофильтр: K&F ND-Filtr 2-400nd."
    )
    msg = make_mock_message(gear_text, user_id=uid)

    with patch("handlers.photographer.process_bulk_gear_input", new_callable=AsyncMock) as mock_bulk:
        await process_user_message(msg)
        assert mock_bulk.called
        assert uid not in _storm_waiting
