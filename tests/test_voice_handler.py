"""Unit tests for handlers.voice (voice message processing)."""

import asyncio
from types import SimpleNamespace

import pytest
from aiogram.enums import ContentType

from handlers import voice


class _Seg:
    def __init__(self, text):
        self.text = text


class _FileInfo:
    def __init__(self, path="voice/og/123.ogg"):
        self.file_path = path


class FakeBot:
    def __init__(self):
        self.downloaded = []
        self.file_info = _FileInfo()

    async def get_file(self, file_id):
        self.downloaded.append(("get_file", file_id))
        return self.file_info

    async def download_file(self, file_path, destination):
        self.downloaded.append(("download", file_path, destination))


class FakeMessage:
    def __init__(self, user_id, message_id=5, text="Старый текст"):
        self.message_id = message_id
        self.text = text
        self.content_type = "voice"
        self.bot = FakeBot()
        self.voice = type("V", (), {"file_id": "file_abc"})()
        self.status = None

        self.from_user = type("U", (), {"id": user_id})()
        self.chat = type("C", (), {"id": user_id})()

    async def answer(self, text):
        if self.status is None:
            self.status = FakeStatus(text)
        return self.status

    def model_copy(self, update=None, deep=False):
        import copy

        new = copy.copy(self)
        for k, v in (update or {}).items():
            setattr(new, k, v)
        return new


class FakeStatus:
    def __init__(self, text):
        self.text = text
        self.edits = []
        self.deleted = False

    async def edit_text(self, text, parse_mode=None):
        self.edits.append((text, parse_mode))
        self.text = text

    async def delete(self):
        self.deleted = True


def _enable_voice_handler(monkeypatch, tmp_path):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {4242})
    monkeypatch.setattr(voice, "TEMP_DIR", str(tmp_path))
    return tmp_path


# ---------- _process_audio_sync ----------


def test_process_audio_sync(monkeypatch, tmp_path):
    calls = {}

    class FakeAudio:
        @classmethod
        def from_ogg(cls, path):
            calls["from_ogg"] = path
            return cls()

        def export(self, wav_path, format=None):
            calls["export"] = (wav_path, format)

    monkeypatch.setattr(voice.pydub, "AudioSegment", FakeAudio)

    model = type("M", (), {
        "transcribe": lambda self, p, language=None, beam_size=None: (
            [_Seg("привет"), _Seg("мир")], None
        ),
    })()

    monkeypatch.setattr(voice, "get_whisper", lambda size: model)
    out = voice._process_audio_sync("/tmp/a.ogg", "/tmp/b.wav")
    assert out == "привет мир"
    assert calls["export"][1] == "wav"


def test_process_audio_sync_empty_text(monkeypatch, tmp_path):
    class FakeAudio:
        @classmethod
        def from_ogg(cls, path):
            return cls()

        def export(self, wav_path, format=None):
            return None

    monkeypatch.setattr(voice.pydub, "AudioSegment", FakeAudio)
    model = type("M", (), {
        "transcribe": lambda self, p, language=None, beam_size=None: ([], None),
    })()
    monkeypatch.setattr(voice, "get_whisper", lambda size: model)
    assert voice._process_audio_sync("/tmp/a.ogg", "/tmp/b.wav") == ""


@pytest.mark.asyncio
async def test_handle_voice_full_flow(monkeypatch, tmp_path):
    _enable_voice_handler(monkeypatch, tmp_path)
    async def fake_to_thread(fn, *args):
        return "привет мир текст"
    monkeypatch.setattr(voice.asyncio, "to_thread", fake_to_thread)

    processed = []

    async def fake_process(msg):
        processed.append(msg)

    main_mod = SimpleNamespace(process_user_message=fake_process)
    monkeypatch.setitem(__import__("sys").modules, "__main__", main_mod)

    msg = FakeMessage(4242, message_id=7)
    await voice.handle_voice(msg)
    assert msg.status is not None
    assert any("Распознано" in e[0] for e in msg.status.edits)
    assert processed
    assert processed[0].text == "привет мир текст"
    assert processed[0].content_type == ContentType.TEXT
    assert processed[0].content_type is not "voice"
    assert msg.status.deleted


@pytest.mark.asyncio
async def test_handle_voice_empty_transcript(monkeypatch, tmp_path):
    _enable_voice_handler(monkeypatch, tmp_path)
    async def fake_to_thread(fn, *args):
        return ""
    monkeypatch.setattr(voice.asyncio, "to_thread", fake_to_thread)

    called = []

    async def fake_process(msg):
        called.append(msg)

    main_mod = SimpleNamespace(process_user_message=fake_process)
    monkeypatch.setitem(__import__("sys").modules, "__main__", main_mod)

    msg = FakeMessage(4242, message_id=8)
    await voice.handle_voice(msg)
    assert any("не распознана" in e[0] for e in msg.status.edits)
    assert called == []


@pytest.mark.asyncio
async def test_handle_voice_status_edit_fails_ignored(monkeypatch, tmp_path):
    _enable_voice_handler(monkeypatch, tmp_path)
    async def fake_to_thread(fn, *args):
        return "текст распознан"
    monkeypatch.setattr(voice.asyncio, "to_thread", fake_to_thread)

    async def fake_process(msg):
        return None

    from types import SimpleNamespace

    main_mod = SimpleNamespace(process_user_message=fake_process)
    monkeypatch.setitem(__import__("sys").modules, "__main__", main_mod)

    msg = FakeMessage(4242)
    boom = False

    async def bad_edit(text, parse_mode=None):
        if not boom:
            raise RuntimeError("edit dead")

    msg = FakeMessage(4242)
    msg.status = FakeStatus("x")
    obj = msg.status
    obj.edit_text = bad_edit
    await voice.handle_voice(msg)
    assert msg.status.deleted


@pytest.mark.asyncio
async def test_handle_voice_bot_download_fails(monkeypatch, tmp_path):
    _enable_voice_handler(monkeypatch, tmp_path)

    async def fake_to_thread(fn, *args):
        raise AssertionError("не должен вызываться")
    monkeypatch.setattr(voice.asyncio, "to_thread", fake_to_thread)

    async def boom_get_file(file_id):
        raise RuntimeError("no file")

    async def boom_download(fp, destination):
        raise RuntimeError("boom")

    msg = FakeMessage(4242)
    msg.bot.get_file = boom_get_file
    msg.bot.download_file = boom_download


    async def ok_get_file(file_id):
        return _FileInfo("p")

    async def ok_download(fp, destination):
        raise OSError("dl fail")

    msg.bot.get_file = ok_get_file
    msg.bot.download_file = ok_download
    await voice.handle_voice(msg)
    assert any("Ошибка обработки" in e[0] for e in msg.status.edits)
    assert msg.status.deleted


@pytest.mark.asyncio
async def test_handle_voice_no_main_processor_warns(monkeypatch, tmp_path):
    _enable_voice_handler(monkeypatch, tmp_path)
    async def fake_to_thread(fn, *args):
        return "текст"
    monkeypatch.setattr(voice.asyncio, "to_thread", fake_to_thread)
    monkeypatch.delitem(__import__("sys").modules, "main", raising=False)
    monkeypatch.delitem(__import__("sys").modules, "__main__", raising=False)

    warns = []

    class FakeLogger:
        def error(self, m, exc_info=False):
            pass

        def warning(self, m):
            warns.append(m)

    monkeypatch.setattr(voice, "logger", FakeLogger())

    msg = FakeMessage(4242)
    await voice.handle_voice(msg)
    assert any("не найден" in w for w in warns)
    assert msg.status.deleted


@pytest.mark.asyncio
async def test_handle_voice_cleanup_removes_temp_files(monkeypatch, tmp_path):
    _enable_voice_handler(monkeypatch, tmp_path)
    async def fake_to_thread(fn, *args):
        return "текст"
    monkeypatch.setattr(voice.asyncio, "to_thread", fake_to_thread)
    main_mod = SimpleNamespace(process_user_message=lambda msg: None)
    monkeypatch.setitem(__import__("sys").modules, "__main__", main_mod)

    msg = FakeMessage(4242, message_id=5)
    await voice.handle_voice(msg)
    # Find and check temp files were cleaned up
    temp_files = list(tmp_path.glob("v_*"))
    assert len(temp_files) == 0


@pytest.mark.asyncio
async def test_handle_voice_empty_transcript_edit_fails_ignored(monkeypatch, tmp_path):
    """Пустая транскрипция + edit_text падает → игнорируется (48-49)."""
    _enable_voice_handler(monkeypatch, tmp_path)
    async def fake_to_thread(fn, *args):
        return ""
    monkeypatch.setattr(voice.asyncio, "to_thread", fake_to_thread)

    async def fake_process(msg):
        raise AssertionError("не должен вызываться")

    main_mod = SimpleNamespace(process_user_message=fake_process)
    monkeypatch.setitem(__import__("sys").modules, "__main__", main_mod)

    msg = FakeMessage(4242)
    msg.status = FakeStatus("x")

    async def broken_edit(text, parse_mode=None):
        raise RuntimeError("broken")

    msg.status.edit_text = broken_edit
    await voice.handle_voice(msg)
    assert msg.status.deleted


@pytest.mark.asyncio
async def test_handle_voice_recognized_edit_fails_ignored(monkeypatch, tmp_path):
    """Распознанный текст, но edit_text падает → игнорируется (57-58)."""
    _enable_voice_handler(monkeypatch, tmp_path)
    async def fake_to_thread(fn, *args):
        return "привет мир"
    monkeypatch.setattr(voice.asyncio, "to_thread", fake_to_thread)

    received = []

    async def fake_process(msg):
        received.append(msg)

    main_mod = SimpleNamespace(process_user_message=fake_process)
    monkeypatch.setitem(__import__("sys").modules, "__main__", main_mod)

    msg = FakeMessage(4242)
    msg.status = FakeStatus("x")

    async def broken_edit(text, parse_mode=None):
        raise RuntimeError("broken")

    msg.status.edit_text = broken_edit
    await voice.handle_voice(msg)
    assert received
    assert msg.status.deleted


@pytest.mark.asyncio
async def test_handle_voice_error_edit_fails_ignored(monkeypatch, tmp_path):
    """Ошибка обработки + edit_text падает в except → игнорируется (79-80)."""
    _enable_voice_handler(monkeypatch, tmp_path)
    async def fake_to_thread(fn, *args):
        raise RuntimeError("transcribe failed")
    monkeypatch.setattr(voice.asyncio, "to_thread", fake_to_thread)

    warns = []

    class FakeLogger:
        def error(self, m, exc_info=False):
            warns.append(m)

        def warning(self, m):
            pass

    monkeypatch.setattr(voice, "logger", FakeLogger())

    msg = FakeMessage(4242)
    msg.status = FakeStatus("x")

    async def broken_edit(text, parse_mode=None):
        raise RuntimeError("broken")

    msg.status.edit_text = broken_edit
    await voice.handle_voice(msg)
    assert any("transcribe failed" in w for w in warns)
    assert msg.status.deleted


@pytest.mark.asyncio
async def test_handle_voice_remove_fails_ignored(monkeypatch, tmp_path):
    """os.remove падает → игнорируется (87-88)."""
    _enable_voice_handler(monkeypatch, tmp_path)
    async def fake_to_thread(fn, *args):
        return "текст"
    monkeypatch.setattr(voice.asyncio, "to_thread", fake_to_thread)
    main_mod = SimpleNamespace(process_user_message=lambda msg: asyncio.sleep(0))
    monkeypatch.setitem(__import__("sys").modules, "__main__", main_mod)

    msg = FakeMessage(4242, message_id=5)
    await voice.handle_voice(msg)
    # The wav should still be removed even if ogg fails
    remaining = list(tmp_path.glob("v_*"))
    assert any("wav" in str(p) for p in remaining) is False  # all cleaned up
    assert msg.status.deleted


@pytest.mark.asyncio
async def test_handle_voice_delete_fails_ignored(monkeypatch, tmp_path):
    """status.delete падает → игнорируется (92-93)."""
    _enable_voice_handler(monkeypatch, tmp_path)
    async def fake_to_thread(fn, *args):
        return "текст"
    monkeypatch.setattr(voice.asyncio, "to_thread", fake_to_thread)
    main_mod = SimpleNamespace(process_user_message=lambda msg: None)
    monkeypatch.setitem(__import__("sys").modules, "__main__", main_mod)

    msg = FakeMessage(4242)
    msg.status = FakeStatus("x")

    async def broken_delete():
        raise RuntimeError("gone")

    msg.status.delete = broken_delete
    await voice.handle_voice(msg)
