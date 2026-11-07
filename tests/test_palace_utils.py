"""Unit tests for handlers.palace._utils."""

import pytest
from aiogram.types import InaccessibleMessage

from handlers.palace import _utils as u


class FakeMessage:
    def __init__(self, fail_on=None, answer_result=None):
        self.fail_on = fail_on
        self.answer_result = answer_result
        self.edited = []
        self.answered = []
        self.deleted = False
        self.voices = []
        self.reply_markup_cleared = False

    async def edit_text(self, text, **kwargs):
        if self.fail_on == "edit":
            raise RuntimeError("edit fail")
        if self.fail_on == "not_modified":
            from aiogram.exceptions import TelegramBadRequest
            raise TelegramBadRequest(
                method="editMessageText",
                message="Bad Request: message is not modified",
            )
        if self.fail_on == "no_text":
            from aiogram.exceptions import TelegramBadRequest
            raise TelegramBadRequest(
                method="editMessageText",
                message="Bad Request: there is no text in the message to edit",
            )
        self.edited.append((text, kwargs))

    async def edit_reply_markup(self, reply_markup=None):
        if self.fail_on == "markup":
            raise RuntimeError("markup fail")
        self.reply_markup_cleared = True

    async def answer(self, text, **kwargs):
        if self.fail_on == "answer" or self.fail_on == "no_text_answer_fail":
            raise RuntimeError("answer fail")
        self.answered.append((text, kwargs))
        return self.answer_result if self.answer_result is not None else self

    async def delete(self, **kwargs):
        if self.fail_on == "delete":
            raise RuntimeError("delete fail")
        self.deleted = True

    async def answer_voice(self, voice, **kwargs):
        if self.fail_on == "voice":
            raise RuntimeError("voice fail")
        self.voices.append((voice, kwargs))


@pytest.fixture(autouse=True)
def _restore_logging():
    u.set_error_logging(True)
    yield
    u.set_error_logging(True)


def _inaccessible():
    return InaccessibleMessage.model_construct(
        chat=type("C", (), {"id": 1})(), message_id=1,
    )


# ---------- set_error_logging / _log_error ----------


def test_set_error_logging_toggle():
    u.set_error_logging(False)
    assert u._error_logging_enabled is False
    u.set_error_logging(True)
    assert u._error_logging_enabled is True


def test_log_error_enabled(caplog):
    u.set_error_logging(True)
    with caplog.at_level("ERROR", logger="PalaceUtils"):
        u._log_error("ctx", RuntimeError("x"))
    assert any("PALACE_UTILS" in r.message for r in caplog.records)


def test_log_error_disabled(caplog):
    u.set_error_logging(False)
    with caplog.at_level("ERROR", logger="PalaceUtils"):
        u._log_error("ctx", RuntimeError("x"))
    assert caplog.records == []


# ---------- safe_edit_text ----------


@pytest.mark.asyncio
async def test_safe_edit_text_success():
    msg = FakeMessage()
    assert await u.safe_edit_text(msg, "текст", parse_mode="HTML") is True
    assert msg.edited == [("текст", {"parse_mode": "HTML"})]


@pytest.mark.asyncio
async def test_safe_edit_text_none():
    assert await u.safe_edit_text(None, "текст") is False


@pytest.mark.asyncio
async def test_safe_edit_text_inaccessible():
    assert await u.safe_edit_text(_inaccessible(), "текст") is False


@pytest.mark.asyncio
async def test_safe_edit_text_error(caplog):
    msg = FakeMessage(fail_on="edit")
    assert await u.safe_edit_text(msg, "текст") is False
    assert any("safe_edit_text" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_safe_edit_text_not_modified(caplog):
    msg = FakeMessage(fail_on="not_modified")
    assert await u.safe_edit_text(msg, "текст") is True
    assert not any("safe_edit_text" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_safe_edit_text_no_text_fallback(caplog):
    msg = FakeMessage(fail_on="no_text")
    assert await u.safe_edit_text(msg, "текст", parse_mode="HTML") is True
    assert msg.reply_markup_cleared is True
    assert msg.answered == [("текст", {"parse_mode": "HTML"})]
    assert not any("safe_edit_text" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_safe_edit_text_no_text_fallback_fails(caplog):
    class FailingFallbackMessage(FakeMessage):
        async def answer(self, text, **kwargs):
            raise RuntimeError("fallback answer fail")

    msg = FailingFallbackMessage(fail_on="no_text")
    assert await u.safe_edit_text(msg, "текст") is False
    assert any("safe_edit_text_fallback" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_safe_edit_text_message_text_is_none(caplog):
    msg = FakeMessage()
    msg.text = None
    assert await u.safe_edit_text(msg, "текст", parse_mode="HTML") is True
    assert msg.reply_markup_cleared is True
    assert msg.answered == [("текст", {"parse_mode": "HTML"})]
    assert msg.edited == []
    assert not any("safe_edit_text" in r.message for r in caplog.records)


# ---------- safe_delete ----------


@pytest.mark.asyncio
async def test_safe_delete_success():
    msg = FakeMessage()
    assert await u.safe_delete(msg) is True
    assert msg.deleted is True


@pytest.mark.asyncio
async def test_safe_delete_none():
    assert await u.safe_delete(None) is False


@pytest.mark.asyncio
async def test_safe_delete_inaccessible():
    assert await u.safe_delete(_inaccessible()) is False


@pytest.mark.asyncio
async def test_safe_delete_error(caplog):
    msg = FakeMessage(fail_on="delete")
    assert await u.safe_delete(msg) is False
    assert any("safe_delete" in r.message for r in caplog.records)


# ---------- safe_answer_voice ----------


@pytest.mark.asyncio
async def test_safe_answer_voice_success():
    msg = FakeMessage()
    assert await u.safe_answer_voice(msg, "voice.ogg") is True
    assert msg.voices == [("voice.ogg", {})]


@pytest.mark.asyncio
async def test_safe_answer_voice_none():
    assert await u.safe_answer_voice(None, "voice.ogg") is False


@pytest.mark.asyncio
async def test_safe_answer_voice_inaccessible():
    assert await u.safe_answer_voice(_inaccessible(), "voice.ogg") is False


@pytest.mark.asyncio
async def test_safe_answer_voice_error(caplog):
    msg = FakeMessage(fail_on="voice")
    assert await u.safe_answer_voice(msg, "voice.ogg") is False
    assert any("safe_answer_voice" in r.message for r in caplog.records)


# ---------- safe_send ----------


@pytest.mark.asyncio
async def test_safe_send_success():
    msg = FakeMessage()
    assert await u.safe_send(msg, "текст") is True
    assert msg.answered == [("текст", {})]


@pytest.mark.asyncio
async def test_safe_send_none():
    assert await u.safe_send(None, "текст") is False


@pytest.mark.asyncio
async def test_safe_send_inaccessible():
    assert await u.safe_send(_inaccessible(), "текст") is False


@pytest.mark.asyncio
async def test_safe_send_error(caplog):
    msg = FakeMessage(fail_on="answer")
    assert await u.safe_send(msg, "текст") is False
    assert any("safe_send" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_safe_send_return_message_success():
    msg = FakeMessage(answer_result="sent")
    assert await u.safe_send(msg, "текст", return_message=True) == "sent"
    assert msg.answered == [("текст", {})]


@pytest.mark.asyncio
async def test_safe_send_return_message_none_and_inaccessible():
    assert await u.safe_send(None, "текст", return_message=True) is None
    assert await u.safe_send(
        _inaccessible(), "текст", return_message=True,
    ) is None


@pytest.mark.asyncio
async def test_safe_send_return_message_error(caplog):
    msg = FakeMessage(fail_on="answer")
    assert await u.safe_send(msg, "текст", return_message=True) is None
    assert any("safe_send" in r.message for r in caplog.records)
