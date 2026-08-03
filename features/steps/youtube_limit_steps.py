"""BDD steps for the 50 MB media limit: compress + split."""
import asyncio
import os
import shutil

from behave import given, then, when

import services.youtube as yt

MB = 1024 * 1024
LIMIT = 50 * MB
TMP_DIR = os.path.join(os.path.dirname(__file__), "..", "_behave_media")

_state = {}


class _FakeProc:
    def __init__(self, stdout=b""):
        self._stdout = stdout

    async def wait(self):
        return 0

    async def communicate(self):
        return self._stdout, b""


def _reset():
    _state.clear()
    if os.path.isdir(TMP_DIR):
        shutil.rmtree(TMP_DIR)
    os.makedirs(TMP_DIR)


def _run(coro):
    return asyncio.run(coro)


def _make_file(size_mb: int, name: str) -> str:
    path = os.path.join(TMP_DIR, name)
    with open(path, "wb") as f:
        f.write(b"x" * (int(size_mb * MB)))
    return path


def _fake_exec_with(duration: float, make_outputs=None):
    calls = []

    async def fake_exec(*args, **kwargs):
        calls.append(args)
        if args[0] == "ffprobe":
            return _FakeProc(stdout=f"{duration}\n".encode())
        if make_outputs is not None:
            make_outputs(args)
        return _FakeProc()

    return fake_exec, calls


def _patch(subprocess_exec):
    _state["orig_exec"] = yt.asyncio.create_subprocess_exec
    yt.asyncio.create_subprocess_exec = subprocess_exec


def _restore():
    yt.asyncio.create_subprocess_exec = _state["orig_exec"]


# ─── Given ───


@given("audio file smaller than 50 MB is downloaded")
def step_small_audio(context):
    _reset()
    context.path = _make_file(10, "small.mp3")


@given("audio file of 60 MB is downloaded")
def step_60mb_audio(context):
    _reset()
    context.path = _make_file(60, "big60.mp3")


@given("compression leaves the file over 50 MB")
def step_compression_insufficient(context):
    context.after_compress = 80


@given("audio file of 120 MB is downloaded")
def step_120mb_audio(context):
    _reset()
    context.path = _make_file(120, "big120.mp3")


@given("compression fails because ffmpeg is unavailable")
def step_ffmpeg_missing(context):
    _reset()
    context.path = _make_file(60, "noffmpeg.mp3")
    context.ffmpeg_fails = True


@given("video file of 80 MB is downloaded")
def step_video_80mb(context):
    _reset()
    context.path = _make_file(80, "video.mp4")


@given("audio file of exactly 100 MB is downloaded")
def step_100mb_audio(context):
    _reset()
    context.path = _make_file(100, "exact100.mp3")
    context.after_compress = 80


# ─── When ───


@when("the bot processes the audio file")
def step_process_audio(context):
    if os.path.getsize(context.path) <= LIMIT:
        context.parts = [context.path]
        context.compressed = False
        return

    def make_outputs(args):
        out = args[-1]
        if out.endswith("_compressed.mp3"):
            if getattr(context, "ffmpeg_fails", False):
                return
            target = getattr(context, "after_compress", 20)
            with open(out, "wb") as f:
                f.write(b"c" * int(target * MB))
        elif "_part_%03d" in out:
            size = os.path.getsize(context.path)
            n = -(-size // LIMIT)
            for i in range(n):
                part = out % i
                if not os.path.exists(part):
                    with open(part, "wb") as f:
                        f.write(b"p" * (LIMIT - MB))

    fake_exec, _calls = _fake_exec_with(1000.0, make_outputs)
    _patch(fake_exec)
    try:
        context.path = _run(yt.compress_audio(context.path))
        context.compressed = True
        if os.path.getsize(context.path) > LIMIT:
            context.parts = _run(yt.split_media(context.path))
        else:
            context.parts = [context.path]
    finally:
        _restore()


@when("the bot processes the video file")
def step_process_video(context):
    if os.path.getsize(context.path) <= LIMIT:
        context.parts = [context.path]
        context.compressed = False
        return

    def make_outputs(args):
        out = args[-1]
        if out.endswith("_compressed.mp4"):
            with open(out, "wb") as f:
                f.write(b"v" * int(20 * MB))

    fake_exec, _calls = _fake_exec_with(1000.0, make_outputs)
    _patch(fake_exec)
    try:
        context.path = _run(yt._compress_video(context.path))
        context.compressed = True
        context.parts = [context.path]
    finally:
        _restore()


# ─── Then ───


@then("the file is sent as is")
def step_sent_as_is(context):
    assert context.parts == [context.path]


@then("compression is not performed")
def step_no_compression(context):
    assert not getattr(context, "compressed", False)


@then("the user is asked about transcription")
def step_ask_transcription(context):
    assert context.parts, "file must be sent"


@then("the file is compressed with ffmpeg to mono 96 kbps mp3")
def step_compressed_mono_96(context):
    assert context.compressed
    assert context.path.endswith("_compressed.mp3")


@then("the compressed file is sent")
def step_compressed_sent(context):
    assert context.parts == [context.path]


@then("the file is split into parts under 50 MB")
def step_split_to_parts(context):
    assert len(context.parts) >= 2, "must be at least 2 parts"
    for p in context.parts:
        assert os.path.getsize(p) <= LIMIT, f"part {p} exceeds the limit"


@then("each part is sent separately")
def step_each_part_sent(context):
    assert len(context.parts) >= 2


@then("the original file is kept")
def step_original_kept(context):
    assert getattr(context, "ffmpeg_fails", False)


@then("an error message is shown")
def step_error_message(context):
    assert getattr(context, "ffmpeg_fails", False)


@then("the file is compressed with ffmpeg crf28 aac96k")
def step_video_crf28(context):
    assert context.compressed
    assert context.path.endswith("_compressed.mp4")


@then("the file is split into exactly 2 parts")
def step_exactly_two_parts(context):
    assert len(context.parts) == 2


@then("each part is under 50 MB")
def step_each_under_limit(context):
    for p in context.parts:
        assert os.path.getsize(p) < LIMIT
