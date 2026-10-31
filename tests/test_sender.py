"""Unit tests for services.sender.

Covers reply-message helper functions: web search button, text/voice send
modes and text-only sending.
"""

import pytest

import services.sender as sender


class FakeMessage:
    def __init__(self, from_user=None):
        self._from_user = from_user or FakeUser()
        self.answers = []
        self.edits = []
        self.voices = []

    @property
    def from_user(self):
        return self._from_user

    async def answer(self, text, **kwargs):
        m = FakeMessage(self._from_user)
        self.answers.append((text, kwargs))
        return m

    async def answer_voice(self, voice, **kwargs):
        self.voices.append(voice)

    async def edit_reply_markup(self, reply_markup=None):
        self.edits.append(reply_markup)


class FakeUser:
    def __init__(self, id=1):
        self.id = id


# ---------- _add_web_search_button ----------


@pytest.mark.asyncio
async def test_add_web_search_button_success():
    msg = FakeMessage()
    await sender._add_web_search_button(msg)
    assert len(msg.edits) == 1
    kb = msg.edits[0]
    assert kb.inline_keyboard
    texts = [b.text for row in kb.inline_keyboard for b in row]
    assert "📥 В заметки" in texts
    assert "🌐 В интернет" in texts


@pytest.mark.asyncio
async def test_add_web_search_button_none():
    await sender._add_web_search_button(None)


@pytest.mark.asyncio
async def test_add_web_search_button_error_silent():
    class Broken:
        pass

    await sender._add_web_search_button(Broken())


# ---------- send_response_with_mode ----------


@pytest.mark.asyncio
async def test_send_text_mode_only(monkeypatch):
    msg = FakeMessage()
    sent = await sender.send_response_with_mode(msg, "простое сообщение", "text")
    assert sent is not None
    assert len(msg.answers) == 1
    assert msg.answers[0][0] == "простое сообщение"
    assert msg.answers[0][1]["parse_mode"] == "HTML"
    assert len(msg.voices) == 0
    assert len(sent.edits) == 1  # button on first msg


@pytest.mark.asyncio
async def test_send_voice_mode_only(monkeypatch):
    msg = FakeMessage()
    monkeypatch.setattr(
        sender, "prepare_tts_text", lambda text: "голосовой текст",
    )
    monkeypatch.setattr(
        sender, "split_tts_text", lambda text, max_chars=1800: ["голосовой текст"],
    )
    async def fake_voice(uid, text):
        return ["/tmp/a.ogg", "/tmp/b.ogg"]

    monkeypatch.setattr(sender, "generate_voice_async", fake_voice)
    removed = []
    monkeypatch.setattr(sender.os, "remove", lambda p: removed.append(p))
    sent = await sender.send_response_with_mode(msg, "неважно", "voice")
    assert sent is None  # нет текстового first_msg
    assert len(msg.answers) == 0
    assert len(msg.voices) == 2
    assert removed == ["/tmp/a.ogg", "/tmp/b.ogg"]


@pytest.mark.asyncio
async def test_send_both_modes(monkeypatch):
    msg = FakeMessage()
    monkeypatch.setattr(sender, "prepare_tts_text", lambda text: "tts")
    monkeypatch.setattr(
        sender, "split_tts_text", lambda text, max_chars=1800: ["tts"],
    )
    async def fake_voice(uid, text):
        return ["/tmp/x.ogg"]

    monkeypatch.setattr(sender, "generate_voice_async", fake_voice)
    monkeypatch.setattr(sender.os, "remove", lambda p: None)
    sent = await sender.send_response_with_mode(msg, "текст и голос", "both")
    assert sent is not None
    assert len(msg.answers) == 1
    assert len(msg.voices) == 1
    assert len(sent.edits) == 1


@pytest.mark.asyncio
async def test_send_split_long_text(monkeypatch):
    msg = FakeMessage()
    long_text = ("слово " * 2000).strip()
    monkeypatch.setattr(
        sender, "split_message",
        lambda text: [long_text[:2000], long_text[:1000]],
    )
    sent = await sender.send_response_with_mode(msg, long_text, "text")
    assert len(msg.answers) == 2
    assert sent is not None
    assert len(sent.edits) == 1


@pytest.mark.asyncio
async def test_send_answer_failure_skips(monkeypatch):
    class FailingMessage(FakeMessage):
        async def answer(self, text, **kwargs):
            raise RuntimeError("telegram error")

    msg = FailingMessage()
    sent = await sender.send_response_with_mode(msg, "текст", "text")
    assert sent is None
    assert len(msg.answers) == 0


@pytest.mark.asyncio
async def test_send_voice_sends_when_prepare_empty(monkeypatch):
    msg = FakeMessage()
    monkeypatch.setattr(sender, "prepare_tts_text", lambda text: "")
    sent = await sender.send_response_with_mode(msg, "текст", "voice")
    assert sent is None
    assert len(msg.voices) == 0


@pytest.mark.asyncio
async def test_send_voice_generation_error_logged(monkeypatch, caplog):
    msg = FakeMessage()
    monkeypatch.setattr(
        sender, "prepare_tts_text", lambda text: "текст",
    )
    monkeypatch.setattr(
        sender, "split_tts_text", lambda text, max_chars=1800: ["текст"],
    )

    async def boom(uid, text):
        raise RuntimeError("tts down")

    monkeypatch.setattr(sender, "generate_voice_async", boom)
    sent = await sender.send_response_with_mode(msg, "текст", "voice")
    assert sent is None
    assert "Ошибка генерации голоса" in caplog.text


@pytest.mark.asyncio
async def test_send_voice_audio_fail_removes_file(monkeypatch):
    monkeypatch.setattr(sender, "prepare_tts_text", lambda text: "текст")
    monkeypatch.setattr(
        sender, "split_tts_text", lambda text, max_chars=1800: ["текст"],
    )
    async def fake_voice(uid, text):
        return ["/tmp/z.ogg"]

    monkeypatch.setattr(sender, "generate_voice_async", fake_voice)
    removed = []
    monkeypatch.setattr(sender.os, "remove", lambda p: removed.append(p))

    class FailingVoiceMessage(FakeMessage):
        async def answer_voice(self, voice, **kwargs):
            raise RuntimeError("send voice failed")

    fmsg = FailingVoiceMessage()
    sent = await sender.send_response_with_mode(fmsg, "текст", "voice")
    assert sent is None
    assert removed == ["/tmp/z.ogg"]


# ---------- send_text_only ----------


@pytest.mark.asyncio
async def test_send_text_only_multiple(monkeypatch):
    msg = FakeMessage()
    monkeypatch.setattr(
        sender, "split_message", lambda text: ["часть 1", "часть 2"],
    )
    calls = []
    async def fake_add(msgsg):
        calls.append(msgsg)

    monkeypatch.setattr(sender, "_add_web_search_button", fake_add)
    result = await sender.send_text_only(msg, "текст")
    assert result is None
    assert len(msg.answers) == 2
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_send_text_only_error_skipped(monkeypatch):
    class FailingMessage(FakeMessage):
        async def answer(self, text, **kwargs):
            raise RuntimeError("boom")

    msg = FailingMessage()
    monkeypatch.setattr(
        sender, "split_message", lambda text: ["часть"],
    )
    result = await sender.send_text_only(msg, "текст")
    assert result is None
    assert len(msg.edits) == 0

@pytest.mark.asyncio
async def test_add_web_search_button_raises_edit_error():
    class FailingMsg:
        async def edit_reply_markup(self, reply_markup=None):
            raise RuntimeError("edit fail")

    await sender._add_web_search_button(FailingMsg())


@pytest.mark.asyncio
async def test_send_voice_answer_raises_in_answer_text():
    class FailingMsg(FakeMessage):
        async def answer(self, text, **kwargs):
            raise RuntimeError("answer fail")

    msg = FailingMsg()
    sent = await sender.send_response_with_mode(msg, "текст", "text")
    assert sent is None


@pytest.mark.asyncio
async def test_send_text_skips_blank_parts(monkeypatch):
    msg = FakeMessage()
    monkeypatch.setattr(
        sender, "split_message", lambda text: ["первая", "", "   ", "третья"],
    )
    sent = await sender.send_response_with_mode(msg, "текст", "text")
    assert sent is not None
    assert len(msg.answers) == 2
    assert msg.answers[0][0] == "первая"
    assert msg.answers[1][0] == "третья"


@pytest.mark.asyncio
async def test_send_text_only_skips_blank_parts(monkeypatch):
    msg = FakeMessage()
    monkeypatch.setattr(
        sender, "split_message", lambda text: ["", "часть", ""],
    )
    result = await sender.send_text_only(msg, "текст")
    assert result is None
    assert len(msg.answers) == 1


@pytest.mark.asyncio
async def test_send_voice_remove_failure_ignored(monkeypatch):
    msg = FakeMessage()
    monkeypatch.setattr(sender, "prepare_tts_text", lambda text: "текст")
    monkeypatch.setattr(
        sender, "split_tts_text", lambda text, max_chars=1800: ["текст"],
    )

    async def fake_voice(uid, text):
        return ["/tmp/nope.ogg"]

    monkeypatch.setattr(sender, "generate_voice_async", fake_voice)

    def boom_remove(p):
        raise OSError("already gone")

    monkeypatch.setattr(sender.os, "remove", boom_remove)
    sent = await sender.send_response_with_mode(msg, "текст", "voice")
    assert sent is None
    assert len(msg.voices) == 1
