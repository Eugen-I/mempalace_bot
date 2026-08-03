"""Тесты сжатия и разбиения медиа (лимит 50 МБ)."""
import asyncio
import os

import pytest


class FakeProc:
    def __init__(self, stdout=b""):
        self._stdout = stdout

    async def wait(self):
        return 0

    async def communicate(self):
        return self._stdout, b""


@pytest.fixture
def tmp_media(tmp_path):
    big = tmp_path / "big.mp3"
    small = tmp_path / "small.mp3"
    big.write_bytes(b"x" * (60 * 1024 * 1024))
    small.write_bytes(b"x" * (10 * 1024 * 1024))
    return {"big": str(big), "small": str(small), "dir": str(tmp_path)}


def test_compress_audio_small_file(tmp_media):
    from services.youtube import compress_audio

    calls = []

    async def fake_exec(*args, **kwargs):
        calls.append(args)
        return FakeProc()

    async def main():
        import services.youtube as yt

        orig = yt.asyncio.create_subprocess_exec
        yt.asyncio.create_subprocess_exec = fake_exec
        try:
            await compress_audio(tmp_media["small"])
        finally:
            yt.asyncio.create_subprocess_exec = orig

    asyncio.run(main())
    assert calls, "ffmpeg должен быть вызван"
    args = calls[0]
    assert args[0] == "ffmpeg"
    assert "-ac" in args
    assert args[args.index("-ac") + 1] == "1"
    assert "-b:a" in args
    assert args[args.index("-b:a") + 1] == "96k"


def test_compress_audio_writes_output(tmp_media):
    """Если ffmpeg создал сжатый файл — исходник удаляется, возвращается новый путь."""
    import services.youtube as yt

    async def fake_exec(*args, **kwargs):
        out = args[-1]
        with open(out, "wb") as f:
            f.write(b"compressed")
        return FakeProc()

    async def main():
        orig = yt.asyncio.create_subprocess_exec
        yt.asyncio.create_subprocess_exec = fake_exec
        try:
            result = await yt.compress_audio(tmp_media["small"])
        finally:
            yt.asyncio.create_subprocess_exec = orig
        return result

    result = asyncio.run(main())
    assert result.endswith("_compressed.mp3")
    assert not os.path.exists(tmp_media["small"])


def test_compress_audio_ffmpeg_failed_keeps_original(tmp_media):
    """ffmpeg не создал файл — возвращается исходный путь."""
    import services.youtube as yt

    async def fake_exec(*args, **kwargs):
        return FakeProc()

    async def main():
        orig = yt.asyncio.create_subprocess_exec
        yt.asyncio.create_subprocess_exec = fake_exec
        try:
            result = await yt.compress_audio(tmp_media["small"])
        finally:
            yt.asyncio.create_subprocess_exec = orig
        return result

    result = asyncio.run(main())
    assert result == tmp_media["small"]
    assert os.path.exists(tmp_media["small"])


def test_split_media_small_file_untouched(tmp_media):
    """Файл <= лимита не разбивается."""
    import services.youtube as yt

    async def main():
        result = await yt.split_media(tmp_media["small"])
        return result

    result = asyncio.run(main())
    assert result == [tmp_media["small"]]


def test_split_media_big_file_splits(tmp_media):
    """Файл > лимита режется на части, исходник удаляется."""
    import services.youtube as yt

    calls = []

    async def fake_exec(*args, **kwargs):
        calls.append(args)
        # ffprobe: длительность 1000 сек
        if args[0] == "ffprobe":
            return FakeProc(stdout=b"1000.0\n")
        # ffmpeg segment: создаём part-файлы
        pattern = args[-1]
        for i in range(4):
            part = pattern % i
            if not os.path.exists(part):
                with open(part, "wb") as f:
                    f.write(b"part")
        return FakeProc()

    async def main():
        orig = yt.asyncio.create_subprocess_exec
        yt.asyncio.create_subprocess_exec = fake_exec
        try:
            result = await yt.split_media(tmp_media["big"])
        finally:
            yt.asyncio.create_subprocess_exec = orig
        return result

    result = asyncio.run(main())
    assert len(result) == 4
    assert all(os.path.exists(p) for p in result)
    assert not os.path.exists(tmp_media["big"])
    # segment_time должен быть ~ duration / n_parts (60MB/50MB = 2 → 500s)
    seg_args = calls[1]
    idx = seg_args.index("-segment_time")
    assert float(seg_args[idx + 1]) == pytest.approx(500.0, abs=1.0)


def test_split_media_ffprobe_fails_no_split(tmp_media):
    """ffprobe не вернул длительность — файл не разбивается."""
    import services.youtube as yt

    async def fake_exec(*args, **kwargs):
        if args[0] == "ffprobe":
            return FakeProc(stdout=b"")
        return FakeProc()

    async def main():
        orig = yt.asyncio.create_subprocess_exec
        yt.asyncio.create_subprocess_exec = fake_exec
        try:
            result = await yt.split_media(tmp_media["big"])
        finally:
            yt.asyncio.create_subprocess_exec = orig
        return result

    result = asyncio.run(main())
    assert result == [tmp_media["big"]]


def test_split_media_no_parts_created(tmp_media):
    """ffmpeg не создал частей — возвращается исходный путь."""
    import services.youtube as yt

    async def fake_exec(*args, **kwargs):
        if args[0] == "ffprobe":
            return FakeProc(stdout=b"1000.0\n")
        return FakeProc()

    async def main():
        orig = yt.asyncio.create_subprocess_exec
        yt.asyncio.create_subprocess_exec = fake_exec
        try:
            result = await yt.split_media(tmp_media["big"])
        finally:
            yt.asyncio.create_subprocess_exec = orig
        return result

    result = asyncio.run(main())
    assert result == [tmp_media["big"]]
    assert os.path.exists(tmp_media["big"])


def test_split_media_exact_limit_untouched(tmp_media):
    """Граница: файл ровно = лимиту не разбивается."""
    import services.youtube as yt

    exact = os.path.join(tmp_media["dir"], "exact.mp3")
    with open(exact, "wb") as f:
        f.write(b"x" * (50 * 1024 * 1024))

    async def main():
        result = await yt.split_media(exact, limit=50 * 1024 * 1024)
        return result

    result = asyncio.run(main())
    assert result == [exact]
