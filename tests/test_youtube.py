"""Unit tests for services.youtube.

Covers filename sanitizing, temp dirs, download_video/download_audio with a
mocked yt_dlp, transcription formatting, transcribe_audio with a mocked
whisper, and _compress_video.
"""

import asyncio
import os

import pytest

import services.youtube as yt


class FakeYDL:
    def __init__(self, opts=None):
        self.opts = opts or {}
        self._info = {}
        self.downloaded = []

    def extract_info(self, url, download=False):
        return self._info

    def download(self, urls):
        self.downloaded.extend(urls)
        return {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeProc:
    async def wait(self):
        return 0

    async def communicate(self):
        return b"", b""


def _mock_thread(monkeypatch):
    async def fake_to_thread(fn):
        return fn()

    monkeypatch.setattr(yt.asyncio, "to_thread", fake_to_thread)


def _patch_ydl(monkeypatch, make_download_file):
    calls = []

    def factory(opts=None):
        obj = FakeYDL(opts or {})
        if not opts or "outtmpl" not in opts:
            obj._info = {"title": "Видео про космос"}
        else:
            make_download_file(opts)
        calls.append(opts or {})
        return obj

    monkeypatch.setattr(yt.yt_dlp, "YoutubeDL", factory)
    return calls


# ---------- _sanitize_filename ----------


def test_sanitize_filename_basic():
    assert yt._sanitize_filename("Lofi Hip Hop Radio") == "Lofi_Hip_Hop_Radio"


def test_sanitize_filename_strips_special_chars():
    assert yt._sanitize_filename('Наполеон: приключение?!') == "Наполеон_приключение"


def test_sanitize_filename_empty_returns_video():
    assert yt._sanitize_filename("!!!") == "video"


def test_sanitize_filename_long_truncated_to_40():
    out = yt._sanitize_filename("x" * 100)
    assert len(out) <= 40


def test_sanitize_filename_unicode_kept():
    assert yt._sanitize_filename("Заметка_о_вики") == "Заметка_о_вики"


# ---------- File size limit ----------


def test_file_limit_is_50mb():
    assert yt.FILE_LIMIT == 50 * 1024 * 1024


# ---------- _yt_path / _tr_path ----------


def test_yt_path_looks_in_temp_dir():
    import config

    out = yt._yt_path()
    assert out == config.TEMP_DIR
    assert os.path.isdir(out)


def test_tr_path_looks_in_transkript_dir():
    import config

    out = yt._tr_path()
    assert out == config.TRANSKRIPT_DIR
    assert os.path.isdir(out)


# ---------- download_video ----------


class _VideoTmp:
    def __init__(self):
        self.mp4_path = None


def test_download_video_happy_path(monkeypatch, tmp_path):
    _mock_thread(monkeypatch)
    monkeypatch.setattr(yt, "_yt_path", lambda: str(tmp_path))
    state = _VideoTmp()

    def make_file(opts):
        if state.mp4_path is None:
            path = opts["outtmpl"].replace("%(ext)s", "mp4")
            if not os.path.exists(path):
                with open(path, "wb") as f:
                    f.write(b"x")
            state.mp4_path = path

    calls = _patch_ydl(monkeypatch, make_file)

    async def main():
        return await yt.download_video("https://youtu.be/abc", quality="720")

    result = asyncio.run(main())
    assert result.endswith(".mp4")
    assert os.path.exists(result)
    assert "yt_" in os.path.basename(result)
    assert "bestvideo[height<=720]+bestaudio/best[height<=720]" in calls[1]["format"]
    assert calls[1]["merge_output_format"] == "mp4"


def test_download_video_missing_merged_file_returns_mp4_path(monkeypatch, tmp_path):
    """mp4 не существует и part-файлов нет — возвращается путь к mp4 без проверки."""
    _mock_thread(monkeypatch)
    monkeypatch.setattr(yt, "_yt_path", lambda: str(tmp_path))

    def make_file(opts):
        pass  # эмулируем неудачную загрузку

    calls = _patch_ydl(monkeypatch, make_file)

    async def main():
        # в каталоге есть чужие файлы, но не с нужным префиксом
        (tmp_path / "other_file.mp4").write_bytes(b"x")
        return await yt.download_video("https://youtu.be/abc", quality="1080")

    result = asyncio.run(main())
    assert result.endswith(".mp4")
    assert "1080" in calls[1]["format"]


def test_download_video_finds_existing_part_file(monkeypatch, tmp_path):
    """Нет mp4, но есть webm с нужным префиксом — возвращается он."""
    _mock_thread(monkeypatch)
    monkeypatch.setattr(yt, "_yt_path", lambda: str(tmp_path))
    webm_path = None

    def make_file(opts):
        nonlocal webm_path
        base = opts["outtmpl"].replace("%(ext)s", "")
        webm_path = base + "webm"
        if not os.path.exists(webm_path):
            with open(webm_path, "wb") as f:
                f.write(b"x")

    _patch_ydl(monkeypatch, make_file)

    async def main():
        return await yt.download_video("https://youtu.be/zz", quality="360")

    result = asyncio.run(main())
    assert result.endswith(".webm")
    assert os.path.exists(result)


def test_download_video_default_title_fallback(monkeypatch, tmp_path):
    _mock_thread(monkeypatch)
    monkeypatch.setattr(yt, "_yt_path", lambda: str(tmp_path))

    def factory(opts=None):
        obj = FakeYDL(opts or {})
        if not opts or "outtmpl" not in opts:
            obj._info = {}  # нет title
        else:
            path = opts["outtmpl"].replace("%(ext)s", "mp4")
            if not os.path.exists(path):
                with open(path, "wb") as f:
                    f.write(b"x")
        return obj

    monkeypatch.setattr(yt.yt_dlp, "YoutubeDL", factory)

    async def main():
        return await yt.download_video("https://youtu.be/n")

    result = asyncio.run(main())
    assert "_video_" in os.path.basename(result)
    assert result.endswith(".mp4")


# ---------- download_audio ----------


def test_download_audio_happy_path(monkeypatch, tmp_path):
    _mock_thread(monkeypatch)
    monkeypatch.setattr(yt, "_yt_path", lambda: str(tmp_path))
    calls = []

    def factory(opts=None):
        obj = FakeYDL(opts or {})
        if not opts or "outtmpl" not in opts:
            obj._info = {"title": "Сону часы"}
        else:
            path = opts["outtmpl"].replace("%(ext)s", "mp3")
            if not os.path.exists(path):
                with open(path, "wb") as f:
                    f.write(b"x")
        calls.append(opts or {})
        return obj

    monkeypatch.setattr(yt.yt_dlp, "YoutubeDL", factory)

    async def main():
        return await yt.download_audio("https://youtu.be/song")

    path, raw = asyncio.run(main())
    assert path.endswith(".mp3")
    assert raw == "Сону часы"
    assert os.path.exists(path)
    dl_opts = calls[1]
    assert any(pp["key"] == "FFmpegExtractAudio" for pp in dl_opts["postprocessors"])
    assert dl_opts["format"] == "bestaudio/best"


def test_download_audio_default_title(monkeypatch, tmp_path):
    _mock_thread(monkeypatch)
    monkeypatch.setattr(yt, "_yt_path", lambda: str(tmp_path))

    def factory(opts=None):
        obj = FakeYDL(opts or {})
        if not opts or "outtmpl" not in opts:
            obj._info = {"duration": 42}  # нет title
        else:
            path = opts["outtmpl"].replace("%(ext)s", "mp3")
            if not os.path.exists(path):
                with open(path, "wb") as f:
                    f.write(b"x")
        return obj

    monkeypatch.setattr(yt.yt_dlp, "YoutubeDL", factory)

    async def main():
        return await yt.download_audio("https://youtu.be/n")

    path, raw = asyncio.run(main())
    assert raw == "audio"
    assert path.endswith(".mp3")


# ---------- _format_transcription ----------


class _Seg:
    def __init__(self, start, end, text):
        self.start = start
        self.end = end
        self.text = text


def test_format_transcription_single_group():
    segs = [
        _Seg(0.0, 1.5, "Привет мир"),
        _Seg(1.5, 3.0, "как дела"),
    ]
    assert yt._format_transcription(segs) == "Привет мир. как дела."


def test_format_transcription_splits_on_gap():
    segs = [
        _Seg(0.0, 1.0, "первый абзац"),
        _Seg(5.0, 6.0, "второй абзац"),
    ]
    out = yt._format_transcription(segs)
    assert out == "первый абзац.\n\nвторой абзац."


def test_format_transcription_keeps_existing_punct():
    segs = [_Seg(0.0, 1.0, "Уже с точкой!")]
    assert yt._format_transcription(segs) == "Уже с точкой!"


def test_format_transcription_skips_blank_text():
    segs = [_Seg(0.0, 1.0, "  "), _Seg(1.0, 2.0, "текст")]
    assert yt._format_transcription(segs) == "текст."


def test_format_transcription_empty():
    assert yt._format_transcription([]) == ""


# ---------- transcribe_audio ----------


def test_transcribe_audio_happy_path(monkeypatch, tmp_path):
    import services.whisper_service as ws

    _mock_thread(monkeypatch)
    monkeypatch.setattr(yt, "_tr_path", lambda: str(tmp_path))
    model = FakeModel()
    monkeypatch.setattr(ws, "get_whisper", lambda size: model)
    src = tmp_path / "audio.mp3"
    src.write_bytes(b"x")

    async def main():
        return await yt.transcribe_audio(str(src), title="Интервью лето")

    result = asyncio.run(main())
    assert os.path.exists(result)
    with open(result, encoding="utf-8") as f:
        content = f.read()
    assert content == "первый блок.\n\nвторой блок."
    assert "Интервью_лето" in os.path.basename(result)


def test_transcribe_audio_default_title_from_filename(monkeypatch, tmp_path):
    import services.whisper_service as ws

    _mock_thread(monkeypatch)
    monkeypatch.setattr(yt, "_tr_path", lambda: str(tmp_path))
    model = FakeModel()
    monkeypatch.setattr(ws, "get_whisper", lambda size: model)
    src = tmp_path / "запись.mp3"
    src.write_bytes(b"x")

    async def main():
        return await yt.transcribe_audio(str(src))

    result = asyncio.run(main())
    assert "запись" in os.path.basename(result)


def test_transcribe_audio_calls_whisper_small(monkeypatch, tmp_path):
    import services.whisper_service as ws

    _mock_thread(monkeypatch)
    monkeypatch.setattr(yt, "_tr_path", lambda: str(tmp_path))
    seen = {}
    model = FakeModel()
    monkeypatch.setattr(ws, "get_whisper", lambda size: model if seen.setdefault("size", size) else model)
    src = tmp_path / "a.mp3"
    src.write_bytes(b"x")

    async def main():
        await yt.transcribe_audio(str(src))

    asyncio.run(main())
    assert seen["size"] == "small"


# ---------- _compress_video ----------


def test_compress_video_success(monkeypatch, tmp_path):
    src = tmp_path / "vid.mp4"
    src.write_bytes(b"original")

    async def fake_exec(*args, **kwargs):
        compressed = args[-1]
        with open(compressed, "wb") as f:
            f.write(b"compressed")
        return FakeProc()

    async def main():
        monkeypatch.setattr(yt.asyncio, "create_subprocess_exec", fake_exec)
        return await yt._compress_video(str(src))

    result = asyncio.run(main())
    assert result.endswith("_compressed.mp4")
    assert not os.path.exists(str(src))
    assert os.path.exists(result)


def test_compress_video_ffmpeg_fails_keeps_original(monkeypatch, tmp_path):
    src = tmp_path / "vid.mp4"
    src.write_bytes(b"original")

    async def fake_exec(*args, **kwargs):
        return FakeProc()

    async def main():
        monkeypatch.setattr(yt.asyncio, "create_subprocess_exec", fake_exec)
        return await yt._compress_video(str(src))

    result = asyncio.run(main())
    assert result == str(src)
    assert os.path.exists(str(src))


def test_compress_video_args(monkeypatch, tmp_path):
    src = tmp_path / "vid.mp4"
    src.write_bytes(b"x")
    seen = []

    async def fake_exec(*args, **kwargs):
        seen.append(args)
        return FakeProc()

    async def main():
        monkeypatch.setattr(yt.asyncio, "create_subprocess_exec", fake_exec)
        await yt._compress_video(str(src))

    asyncio.run(main())
    assert seen[0][0] == "ffmpeg"
    assert "-crf" in seen[0]
    assert seen[0][seen[0].index("-crf") + 1] == "28"


# ---------- compress_audio ----------


def test_compress_audio_success(monkeypatch, tmp_path):
    src = tmp_path / "voice.ogg"
    src.write_bytes(b"original")

    async def fake_exec(*args, **kwargs):
        compressed = args[-1]
        with open(compressed, "wb") as f:
            f.write(b"compressed")
        return FakeProc()

    async def main():
        monkeypatch.setattr(yt.asyncio, "create_subprocess_exec", fake_exec)
        return await yt.compress_audio(str(src))

    result = asyncio.run(main())
    assert result.endswith("_compressed.mp3")
    assert not os.path.exists(str(src))
    assert os.path.exists(result)


def test_compress_audio_ffmpeg_fails_keeps_original(monkeypatch, tmp_path):
    src = tmp_path / "voice.ogg"
    src.write_bytes(b"original")

    async def fake_exec(*args, **kwargs):
        return FakeProc()

    async def main():
        monkeypatch.setattr(yt.asyncio, "create_subprocess_exec", fake_exec)
        return await yt.compress_audio(str(src))

    result = asyncio.run(main())
    assert result == str(src)
    assert os.path.exists(str(src))


def test_compress_audio_args(monkeypatch, tmp_path):
    src = tmp_path / "voice.ogg"
    src.write_bytes(b"x")
    seen = []

    async def fake_exec(*args, **kwargs):
        seen.append(args)
        return FakeProc()

    async def main():
        monkeypatch.setattr(yt.asyncio, "create_subprocess_exec", fake_exec)
        await yt.compress_audio(str(src))

    asyncio.run(main())
    assert seen[0][0] == "ffmpeg"
    assert "-ac" in seen[0]
    assert seen[0][seen[0].index("-c:a") + 1] == "libmp3lame"


# ---------- _media_duration ----------


def test_media_duration_success(monkeypatch, tmp_path):
    src = tmp_path / "media.mp4"
    src.write_bytes(b"x")

    class Proc:
        async def communicate(self):
            return b"12.5\n", b""

    async def fake_exec(*args, **kwargs):
        return Proc()

    async def main():
        monkeypatch.setattr(yt.asyncio, "create_subprocess_exec", fake_exec)
        return await yt._media_duration(str(src))

    assert asyncio.run(main()) == 12.5


def test_media_duration_invalid_output_returns_zero(monkeypatch, tmp_path):
    src = tmp_path / "media.mp4"
    src.write_bytes(b"x")

    class Proc:
        async def communicate(self):
            return b"not-a-number", b""

    async def fake_exec(*args, **kwargs):
        return Proc()

    async def main():
        monkeypatch.setattr(yt.asyncio, "create_subprocess_exec", fake_exec)
        return await yt._media_duration(str(src))

    assert asyncio.run(main()) == 0.0


def test_media_duration_undecodable_output_returns_zero(monkeypatch, tmp_path):
    src = tmp_path / "media.mp4"
    src.write_bytes(b"x")

    class Proc:
        async def communicate(self):
            return b"\xff\xfe\x00", b""

    async def fake_exec(*args, **kwargs):
        return Proc()

    async def main():
        monkeypatch.setattr(yt.asyncio, "create_subprocess_exec", fake_exec)
        return await yt._media_duration(str(src))

    assert asyncio.run(main()) == 0.0


# ---------- split_media ----------


def test_split_media_under_limit_returns_original(tmp_path):
    src = tmp_path / "small.mp4"
    src.write_bytes(b"tiny")
    assert asyncio.run(yt.split_media(str(src))) == [str(src)]


def test_split_media_no_duration_returns_original(monkeypatch, tmp_path):
    src = tmp_path / "big.mp4"
    src.write_bytes(b"x" * (yt.FILE_LIMIT + 1))

    class Proc:
        async def communicate(self):
            return b"not-a-number", b""

    async def fake_exec(*args, **kwargs):
        return Proc()

    async def main():
        monkeypatch.setattr(yt.asyncio, "create_subprocess_exec", fake_exec)
        return await yt.split_media(str(src))

    result = asyncio.run(main())
    assert result == [str(src)]
    assert os.path.exists(str(src))


def test_split_media_success(monkeypatch, tmp_path):
    src = tmp_path / "video.mp4"
    src.write_bytes(b"x" * (yt.FILE_LIMIT * 2 + 1))
    seen = []

    class Proc:
        async def communicate(self):
            return b"100.0\n", b""

        async def wait(self):
            return 0

    async def fake_exec(*args, **kwargs):
        seen.append(args)
        if args[0] == "ffmpeg":
            pattern = args[-1]
            base = pattern[: pattern.index("_part_")]
            for i in range(3):
                with open(f"{base}_part_{i:03d}.mp4", "wb") as f:
                    f.write(b"part")
        return Proc()

    async def main():
        monkeypatch.setattr(yt.asyncio, "create_subprocess_exec", fake_exec)
        return await yt.split_media(str(src))

    result = asyncio.run(main())
    assert len(result) == 3
    assert not os.path.exists(str(src))
    assert "-segment_time" in seen[1]


def test_split_media_segment_time_floor(monkeypatch, tmp_path):
    src = tmp_path / "video.mp4"
    src.write_bytes(b"x" * (yt.FILE_LIMIT * 2 + 1))
    seen = []

    class Proc:
        async def communicate(self):
            return b"1.0\n", b""

        async def wait(self):
            return 0

    async def fake_exec(*args, **kwargs):
        seen.append(args)
        if args[0] == "ffmpeg":
            pattern = args[-1]
            base = pattern[: pattern.index("_part_")]
            with open(f"{base}_part_000.mp4", "wb") as f:
                f.write(b"part")
        return Proc()

    async def main():
        monkeypatch.setattr(yt.asyncio, "create_subprocess_exec", fake_exec)
        return await yt.split_media(str(src))

    asyncio.run(main())
    st = seen[1]
    assert st[st.index("-segment_time") + 1] == "1.0"


def test_split_media_no_parts_returns_original(monkeypatch, tmp_path):
    src = tmp_path / "video.mp4"
    src.write_bytes(b"x" * (yt.FILE_LIMIT * 2 + 1))

    class Proc:
        async def communicate(self):
            return b"100.0\n", b""

        async def wait(self):
            return 0

    async def fake_exec(*args, **kwargs):
        return Proc()

    async def main():
        monkeypatch.setattr(yt.asyncio, "create_subprocess_exec", fake_exec)
        return await yt.split_media(str(src))

    result = asyncio.run(main())
    assert result == [str(src)]
    assert os.path.exists(str(src))


def test_split_media_remove_error_ignored(monkeypatch, tmp_path):
    src = tmp_path / "video.mp4"
    src.write_bytes(b"x" * (yt.FILE_LIMIT * 2 + 1))

    class Proc:
        async def communicate(self):
            return b"100.0\n", b""

        async def wait(self):
            return 0

    async def fake_exec(*args, **kwargs):
        if args[0] == "ffmpeg":
            pattern = args[-1]
            base = pattern[: pattern.index("_part_")]
            with open(f"{base}_part_000.mp4", "wb") as f:
                f.write(b"part")
        return Proc()

    async def main():
        monkeypatch.setattr(yt.asyncio, "create_subprocess_exec", fake_exec)
        monkeypatch.setattr(os, "remove", lambda p: (_ for _ in ()).throw(OSError("busy")))
        return await yt.split_media(str(src))

    result = asyncio.run(main())
    assert len(result) == 1


class FakeModel:
    def transcribe(self, audio_path, language="ru"):
        return [
            _Seg(0.0, 1.0, "первый блок"),
            _Seg(4.0, 5.0, "второй блок"),
        ], None
