"""Unit tests for handlers.youtube_ui."""

import os
from types import SimpleNamespace

import pytest

from handlers import youtube_ui as yt
from services import bot_setup
from services import youtube as youtube_svc


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeFile:
    def __init__(self, file_id="f1", file_name="clip.mp3", duration=10):
        self.file_id = file_id
        self.file_name = file_name
        self.duration = duration


class FakeBot:
    def __init__(self):
        self.downloads = []
        self.file_path = "path/to/f1.mp3"

    async def get_file(self, file_id):
        return SimpleNamespace(file_path=self.file_path)

    async def download_file(self, file_path, destination=None):
        self.downloads.append((file_path, destination))


class FakeMessage:
    def __init__(self, uid=4242, text="", audio=None):
        self.from_user = FakeUser(uid)
        self.text = text
        self.audio = audio
        self.message_id = 1
        self.bot = FakeBot()
        self.answers = []
        self.answer_audios = []
        self.answer_videos = []
        self.answered_cbs = []

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append((text, parse_mode, reply_markup))
        return FakeStatus()

    async def answer_audio(self, input_file, caption=None):
        self.answer_audios.append((input_file, caption))

    async def answer_video(self, input_file, caption=None):
        self.answer_videos.append((input_file, caption))

    async def edit_text(self, text, parse_mode=None):
        self.edited = getattr(self, "edited", [])
        self.edited.append(text)


class FakeStatus:
    def __init__(self):
        self.text = None
        self.edits = []
        self.deleted = False

    async def edit_text(self, text, parse_mode=None):
        self.edits.append(text)
        self.text = text

    async def delete(self):
        self.deleted = True


class FakeCb:
    def __init__(self, uid=4242, data="", message=None):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = message or FakeMessage(uid)
        self.answered = []
        self.edited = []

    async def answer(self, text=None, show_alert=None):
        self.answered.append((text, show_alert))

    async def edit_text(self, text, parse_mode=None):
        self.edited.append(text)


def _enable(monkeypatch, tmp_path):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {4242})
    d = tmp_path / "audio_downloads"
    d.mkdir()
    monkeypatch.setattr(yt, "AUDIO_DIR", str(d))
    monkeypatch.setattr(yt, "_yt_audio_cache", {})
    monkeypatch.setattr(yt, "_yt_quality_url", {})
    monkeypatch.setattr(yt, "_yt_waiting_url", {})
    return d


# ---------- menu commands ----------


@pytest.mark.asyncio
async def test_cmd_yt_video_sets_waiting(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage(4242)
    await yt.cmd_yt_video(msg)
    assert yt._yt_waiting_url[4242] == "video"
    assert msg.answers[0][0] == "📹 Введите ссылку на YouTube видео:"


@pytest.mark.asyncio
async def test_cmd_yt_audio_sets_waiting(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage(4242)
    await yt.cmd_yt_audio(msg)
    assert yt._yt_waiting_url[4242] == "audio"
    assert msg.answers[0][0] == "🎵 Введите ссылку на YouTube видео:"


@pytest.mark.asyncio
async def test_cmd_yt_video_not_allowed(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage(999)
    await yt.cmd_yt_video(msg)
    assert yt._yt_waiting_url.get(999) is None
    assert msg.answers == []


# ---------- uploaded audio ----------


@pytest.mark.asyncio
async def test_handle_uploaded_audio_small_file(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    msg = FakeMessage(4242, audio=FakeFile())
    local = str(d / "x.mp3")
    monkeypatch.setattr(yt.secrets, "token_hex", lambda n: "abcd")
    real_write = (d / "upload_abcd.mp3").write_bytes

    async def fake_get_file(file_id):
        return SimpleNamespace(file_path="some/path.mp3")

    async def fake_download(fp, destination):
        (d / "upload_abcd.mp3").write_bytes(b"audio" * 100)

    msg.bot.get_file = fake_get_file
    msg.bot.download_file = fake_download

    await yt.handle_uploaded_audio(msg)
    # маленький файл → 1 аудио, без транскрибации вопрос с кнопкой
    assert msg.answer_audios, "ожидался answer_audio"
    assert msg.answers[-1][0].startswith("📝 Транскрибировать")


@pytest.mark.asyncio
async def test_handle_uploaded_audio_empty_file(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(yt.secrets, "token_hex", lambda n: "empty")

    async def fake_get_file(file_id):
        return SimpleNamespace(file_path="p")

    async def fake_download(fp, destination):
        (d / "upload_empty.mp3").write_bytes(b"")

    msg = FakeMessage(4242, audio=FakeFile())
    msg.bot.get_file = fake_get_file
    msg.bot.download_file = fake_download
    st = FakeStatus()
    msg.answer = _stub_answer(st)

    await yt._handle_audio_file(msg, "f", "x.mp3")
    assert "❌ Аудио пустое." in st.edits
    assert msg.answer_audios == []


def _stub_answer(st):
    async def answer(text, parse_mode=None, reply_markup=None):
        st.edits.append(text)
        return st

    return answer


@pytest.mark.asyncio
async def test_handle_uploaded_audio_over_limit_compressed(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(yt.secrets, "token_hex", lambda n: "big")

    async def fake_get_file(file_id):
        return SimpleNamespace(file_path="p")

    async def fake_download(fp, destination):
        (d / "upload_big.mp3").write_bytes(b"x" * (60 * 1024 * 1024))

    compressed_path = str(d / "upload_big_compressed.mp3")

    async def fake_compress(path):
        (d / "upload_big_compressed.mp3").write_bytes(b"y" * 1024)
        return compressed_path

    monkeypatch.setattr(youtube_svc, "compress_audio", fake_compress)
    monkeypatch.setattr(youtube_svc, "split_media", _no_split)

    msg = FakeMessage(4242, audio=FakeFile())
    msg.bot.get_file = fake_get_file
    msg.bot.download_file = fake_download
    await yt._handle_audio_file(msg, "f", "x.mp3")
    assert msg.answer_audios, "ожидался ответ после сжатия"


async def _no_split(path):
    return [path]


@pytest.mark.asyncio
async def test_handle_uploaded_audio_compress_then_split(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(yt.secrets, "token_hex", lambda n: "big2")

    async def fake_get_file(file_id):
        return SimpleNamespace(file_path="p")

    async def fake_download(fp, destination):
        (d / "upload_big2.mp3").write_bytes(b"x" * (60 * 1024 * 1024))

    async def fake_compress(path):
        (d / "upload_big2_compressed.mp3").write_bytes(b"y" * (60 * 1024 * 1024))
        return str(d / "upload_big2_compressed.mp3")

    async def fake_split(path):
        p1, p2 = str(d / "p1.mp3"), str(d / "p2.mp3")
        (d / "p1.mp3").write_bytes(b"1")
        (d / "p2.mp3").write_bytes(b"2")
        return [p1, p2]

    monkeypatch.setattr(youtube_svc, "compress_audio", fake_compress)
    monkeypatch.setattr(youtube_svc, "split_media", fake_split)

    msg = FakeMessage(4242, audio=FakeFile())
    msg.bot.get_file = fake_get_file
    msg.bot.download_file = fake_download
    await yt._handle_audio_file(msg, "f", "x.mp3")
    assert len(msg.answer_audios) == 2
    assert msg.answer_audios[0][1] == "🎵 x (часть 1/2)"


@pytest.mark.asyncio
async def test_handle_uploaded_audio_exception(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(yt.secrets, "token_hex", lambda n: "err")

    async def fake_get_file(file_id):
        raise RuntimeError("boom")

    msg = FakeMessage(4242, audio=FakeFile())
    msg.bot.get_file = fake_get_file
    st = FakeStatus()
    msg.answer = _stub_answer(st)
    await yt._handle_audio_file(msg, "f", "x.mp3")
    assert st.edits[-1].startswith("❌ Ошибка")


# ---------- quality callback ----------


@pytest.mark.asyncio
async def test_cb_yt_quality_success(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    yt._yt_quality_url[4242] = "https://youtu.be/x"
    cb = FakeCb(4242, data="yt_q:720")
    video_path = str(d / "v.mp4")
    (d / "v.mp4").write_bytes(b"data" * 100)

    async def fake_download(url, quality):
        return video_path

    monkeypatch.setattr(yt, "download_video", fake_download)
    await yt.cb_yt_quality(cb)
    assert cb.answered == [(None, None)]
    assert cb.message.answer_videos, "ожидалось видео"
    assert not os.path.exists(video_path)


@pytest.mark.asyncio
async def test_cb_yt_quality_no_session(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="yt_q:1080")
    await yt.cb_yt_quality(cb)
    assert cb.answered[0][0] == "❌ Сессия истекла. Начните заново."


@pytest.mark.asyncio
async def test_cb_yt_quality_over_limit_compress(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    yt._yt_quality_url[4242] = "u"
    cb = FakeCb(4242, data="yt_q:360")
    video_path = str(d / "v.mp4")
    (d / "v.mp4").write_bytes(b"x" * (60 * 1024 * 1024))
    compressed = str(d / "v_compressed.mp4")

    async def fake_download(url, quality):
        return video_path

    async def fake_compress(path):
        (d / "v_compressed.mp4").write_bytes(b"y" * 1024)
        return compressed

    monkeypatch.setattr(yt, "download_video", fake_download)
    monkeypatch.setattr(yt, "_compress_video", fake_compress)
    await yt.cb_yt_quality(cb)
    assert cb.message.answer_videos
    assert not os.path.exists(compressed)


@pytest.mark.asyncio
async def test_cb_yt_quality_error(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    yt._yt_quality_url[4242] = "u"
    cb = FakeCb(4242, data="yt_q:360")

    async def fake_download(url, quality):
        raise RuntimeError("dl failed")

    monkeypatch.setattr(yt, "download_video", fake_download)
    await yt.cb_yt_quality(cb)
    # format_user_error для RuntimeError возвращает "❌ Ошибка выполнения"
    assert "Ошибка выполнения" in cb.message.answers[-1][0]


# ---------- transcribe callback ----------


@pytest.mark.asyncio
async def test_cb_yt_transcribe_yes(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    audio = str(d / "audio.mp3")
    (d / "audio.mp3").write_bytes(b"x")
    yt._yt_audio_cache["sid1"] = {"path": audio, "title": "т"}
    txt = str(d / "audio.txt")
    (d / "audio.txt").write_text("текст транскрипта", encoding="utf-8")

    async def fake_transcribe(path, title):
        return txt

    monkeypatch.setattr(yt, "transcribe_audio", fake_transcribe)
    cb = FakeCb(4242, data="yt_tr:sid1:yes")
    await yt.cb_yt_transcribe(cb)
    assert any("Транскрипт сохранён" in a[0] for a in cb.message.answers)
    assert not os.path.exists(audio)


@pytest.mark.asyncio
async def test_cb_yt_transcribe_no(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    audio = str(d / "audio.mp3")
    (d / "audio.mp3").write_bytes(b"x")
    yt._yt_audio_cache["sid2"] = {"path": audio, "title": "т"}
    cb = FakeCb(4242, data="yt_tr:sid2:no")
    await yt.cb_yt_transcribe(cb)
    assert cb.message.edited == ["✅ Транскрипция отменена."]
    assert not os.path.exists(audio)


@pytest.mark.asyncio
async def test_cb_yt_transcribe_short_data(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="yt_tr:sid")
    await yt.cb_yt_transcribe(cb)
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cb_yt_transcribe_missing_cache(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="yt_tr:ghost:yes")
    await yt.cb_yt_transcribe(cb)
    assert cb.answered[0][0].startswith("❌ Файл не найден в кэше")


@pytest.mark.asyncio
async def test_cb_yt_transcribe_missing_disk(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    yt._yt_audio_cache["sid3"] = {"path": "/no/such/audio.mp3", "title": "т"}
    cb = FakeCb(4242, data="yt_tr:sid3:yes")
    await yt.cb_yt_transcribe(cb)
    assert cb.answered[0][0].startswith("❌ Файл не найден на диске")


@pytest.mark.asyncio
async def test_cb_yt_transcribe_error(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    audio = str(d / "audio.mp3")
    (d / "audio.mp3").write_bytes(b"x")
    yt._yt_audio_cache["sid4"] = {"path": audio, "title": "т"}

    async def fake_transcribe(path, title):
        raise RuntimeError("no whisper")

    monkeypatch.setattr(yt, "transcribe_audio", fake_transcribe)
    cb = FakeCb(4242, data="yt_tr:sid4:yes")
    await yt.cb_yt_transcribe(cb)
    # format_user_error для RuntimeError возвращает "❌ Ошибка выполнения"
    assert "Ошибка выполнения" in cb.message.answers[-1][0]
    assert not os.path.exists(audio)


# ---------- compress ----------


@pytest.mark.asyncio
async def test_compress_video_success(monkeypatch, tmp_path):
    d = tmp_path
    src = d / "v.mp4"
    src.write_bytes(b"x")
    compressed = d / "v_compressed.mp4"
    compressed.write_bytes(b"y")

    class FakeProc:
        async def wait(self):
            return 0

    async def fake_create(*args, **kwargs):
        assert args[0] == "ffmpeg"
        return FakeProc()

    monkeypatch.setattr(yt.asyncio, "create_subprocess_exec", fake_create)
    out = await yt._compress_video(str(src))
    assert out == str(compressed)
    assert not src.exists()


@pytest.mark.asyncio
async def test_compress_video_no_output(monkeypatch, tmp_path):
    d = tmp_path
    src = d / "v.mp4"
    src.write_bytes(b"x")

    class FakeProc:
        async def wait(self):
            return 0

    async def fake_create(*args, **kwargs):
        return FakeProc()

    monkeypatch.setattr(yt.asyncio, "create_subprocess_exec", fake_create)
    out = await yt._compress_video(str(src))
    assert out == str(src)
    assert src.exists()


@pytest.mark.asyncio
async def test_cb_yt_quality_split_after_compress(monkeypatch, tmp_path):
    d = _enable(monkeypatch, tmp_path)
    yt._yt_quality_url[4242] = "u"
    cb = FakeCb(4242, data="yt_q:360")
    video_path = str(d / "v.mp4")
    (d / "v.mp4").write_bytes(b"x" * (60 * 1024 * 1024))
    compressed = str(d / "v_compressed.mp4")
    (d / "v_compressed.mp4").write_bytes(b"y" * (60 * 1024 * 1024))

    async def fake_download(url, quality):
        return video_path

    async def fake_compress(path):
        return compressed

    async def fake_split(path):
        p1, p2 = str(d / "c1.mp4"), str(d / "c2.mp4")
        (d / "c1.mp4").write_bytes(b"1")
        (d / "c2.mp4").write_bytes(b"2")
        return [p1, p2]

    monkeypatch.setattr(yt, "download_video", fake_download)
    monkeypatch.setattr(yt, "_compress_video", fake_compress)
    monkeypatch.setattr(youtube_svc, "split_media", fake_split)
    await yt.cb_yt_quality(cb)
    assert len(cb.message.answer_videos) == 2
    assert not os.path.exists(str(d / "c1.mp4"))
    assert not os.path.exists(str(d / "c2.mp4"))


@pytest.mark.asyncio
async def test_handle_uploaded_audio_remove_fails_ignored(monkeypatch, tmp_path):
    """Части аудио + os.remove падает → игнорируется (102-103)."""
    d = _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(yt.secrets, "token_hex", lambda n: "rm1")

    async def fake_get_file(file_id):
        return SimpleNamespace(file_path="p")

    async def fake_download(fp, destination):
        (d / "upload_rm1.mp3").write_bytes(b"x" * (60 * 1024 * 1024))

    async def fake_compress(path):
        (d / "upload_rm1_compressed.mp3").write_bytes(b"y" * (60 * 1024 * 1024))
        return str(d / "upload_rm1_compressed.mp3")

    async def fake_split(path):
        p1 = str(d / "p1.mp3")
        p2 = str(d / "p2.mp3")
        (d / "p1.mp3").write_bytes(b"1")
        (d / "p2.mp3").write_bytes(b"2")
        return [p1, p2]

    monkeypatch.setattr(youtube_svc, "compress_audio", fake_compress)
    monkeypatch.setattr(youtube_svc, "split_media", fake_split)

    import os as _os

    real_remove = _os.remove

    def flaky_remove(path):
        raise OSError("locked")

    monkeypatch.setattr(_os, "remove", flaky_remove)

    msg = FakeMessage(4242, audio=FakeFile())
    msg.bot.get_file = fake_get_file
    msg.bot.download_file = fake_download
    await yt._handle_audio_file(msg, "f", "x.mp3")
    assert len(msg.answer_audios) == 2


@pytest.mark.asyncio
async def test_cb_yt_quality_remove_fails_ignored(monkeypatch, tmp_path):
    """Видео после сжатия больше лимита → split, remove падает → ок (168-169)."""
    d = _enable(monkeypatch, tmp_path)
    yt._yt_quality_url[4242] = "u"
    cb = FakeCb(4242, data="yt_q:360")
    video_path = str(d / "v.mp4")
    (d / "v.mp4").write_bytes(b"x" * (60 * 1024 * 1024))
    compressed = str(d / "v_compressed.mp4")
    (d / "v_compressed.mp4").write_bytes(b"y" * (60 * 1024 * 1024))

    async def fake_download(url, quality):
        return video_path

    async def fake_compress(path):
        return compressed

    async def fake_split(path):
        p1 = str(d / "c1.mp4")
        (d / "c1.mp4").write_bytes(b"1")
        return [p1]

    monkeypatch.setattr(yt, "download_video", fake_download)
    monkeypatch.setattr(yt, "_compress_video", fake_compress)
    monkeypatch.setattr(youtube_svc, "split_media", fake_split)

    import os as _os

    def flaky_remove(path):
        raise OSError("locked")

    monkeypatch.setattr(_os, "remove", flaky_remove)

    await yt.cb_yt_quality(cb)
    assert len(cb.message.answer_videos) == 1


@pytest.mark.asyncio
async def test_cb_yt_transcribe_no_remove_fails_ignored(monkeypatch, tmp_path):
    """Ответ 'no' + os.remove падает → ок (206-207)."""
    d = _enable(monkeypatch, tmp_path)
    audio = str(d / "audio.mp3")
    (d / "audio.mp3").write_bytes(b"x")
    yt._yt_audio_cache["sid_no"] = {"path": audio, "title": "т"}

    import os as _os

    def flaky_remove(path):
        raise OSError("locked")

    monkeypatch.setattr(_os, "remove", flaky_remove)
    cb = FakeCb(4242, data="yt_tr:sid_no:no")
    await yt.cb_yt_transcribe(cb)
    assert cb.message.edited == ["✅ Транскрипция отменена."]


@pytest.mark.asyncio
async def test_cb_yt_transcribe_yes_remove_fails_ignored(monkeypatch, tmp_path):
    """Транскрипт успешен, но remove в finally падает → ок (225-226)."""
    d = _enable(monkeypatch, tmp_path)
    audio = str(d / "audio.mp3")
    (d / "audio.mp3").write_bytes(b"x")
    yt._yt_audio_cache["sid_fin"] = {"path": audio, "title": "т"}
    txt = str(d / "audio.txt")
    (d / "audio.txt").write_text("текст", encoding="utf-8")

    async def fake_transcribe(path, title):
        return txt

    monkeypatch.setattr(yt, "transcribe_audio", fake_transcribe)

    import os as _os

    def flaky_remove(path):
        raise OSError("locked")

    monkeypatch.setattr(_os, "remove", flaky_remove)

    cb = FakeCb(4242, data="yt_tr:sid_fin:yes")
    await yt.cb_yt_transcribe(cb)
    assert any("Транскрипт сохранён" in a[0] for a in cb.message.answers)
