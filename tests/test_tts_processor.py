"""Unit tests for services.tts_processor.

Covers text preparation for speech, chunk splitting, per-user settings and
async OGG generation via say/ffmpeg.
"""

import json
import os

import pytest

import services.tts_processor as tts

# ---------- prepare_tts_text ----------


def test_prepare_tts_text_empty():
    assert tts.prepare_tts_text("") == ""
    assert tts.prepare_tts_text(None) == ""


def test_prepare_tts_text_blocks_errors():
    assert tts.prepare_tts_text("❌ Ошибка ИИ") == ""
    assert tts.prepare_tts_text("произошла Ошибка подключения") == ""
    assert tts.prepare_tts_text("NOT_FOUND значение") == ""


def test_prepare_tts_text_removes_technical_emoji():
    out = tts.prepare_tts_text("Текст 📎✅ с эмодзи")
    assert "📎" not in out
    assert "✅" not in out
    assert "Текст" in out


def test_prepare_tts_text_converts_emotional_emoji_to_pause():
    out = tts.prepare_tts_text("Привет 😂!")
    assert "[[slnc 400]]" in out
    assert "😂" not in out


def test_prepare_tts_text_removes_code_blocks():
    out = tts.prepare_tts_text("текст ```python\nprint(1)\n``` конец")
    assert "print" not in out
    assert "блок кода пропущен" in out


def test_prepare_tts_text_inline_code_and_links():
    out = tts.prepare_tts_text("смотри `x = 1` и https://example.com/page")
    assert "фрагмент кода" in out
    assert "ссылка" in out
    assert "example.com" not in out


def test_prepare_tts_text_strips_escapes():
    out = tts.prepare_tts_text(r"текст \n \t \* \_ \\ и ещё")
    assert "\\" not in out
    assert "*" not in out
    assert "_" not in out


def test_prepare_tts_text_paragraphs_to_pause():
    out = tts.prepare_tts_text("абзац один\n\nабзац два")
    assert "[[slnc 500]]" in out


def test_prepare_tts_text_normalizes_whitespace():
    out = tts.prepare_tts_text("  много    пробелов   ")
    assert out == "много пробелов"


# ---------- split_tts_text ----------


def test_split_tts_short_text():
    assert tts.split_tts_text("короткий") == ["короткий"]


def test_split_tts_exact_limit():
    assert tts.split_tts_text("x" * 1800) == ["x" * 1800]


def test_split_tts_on_sentence_boundaries():
    text = ("Предложение первое. " * 30) + ("Предложение второе! " * 30)
    parts = tts.split_tts_text(text, max_chars=200)
    assert len(parts) > 1
    for p in parts:
        assert len(p) <= 200


def test_split_tts_no_boundary_hard_split():
    text = "a" * 5000
    parts = tts.split_tts_text(text, max_chars=1800)
    assert len(parts) >= 2
    assert "".join(parts) == "a" * 5000


def test_split_tts_exhausts_exactly():
    text = "a" * 3602  # ровно два куска по 1801, rem обнуляется
    parts = tts.split_tts_text(text, max_chars=1800)
    assert parts == ["a" * 1801, "a" * 1801]


def test_split_tts_empty():
    assert tts.split_tts_text("") == [""]


# ---------- get_voice_settings ----------


def test_get_voice_settings_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(tts, "VOICE_REPLY_CONFIG", str(tmp_path / "nope.json"))
    assert tts.get_voice_settings(1) == {"mode": "text", "speed": 175}


def test_get_voice_settings_existing_user(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"42": {"mode": "voice", "speed": 200}}), encoding="utf-8")
    monkeypatch.setattr(tts, "VOICE_REPLY_CONFIG", str(cfg))
    assert tts.get_voice_settings(42) == {"mode": "voice", "speed": 200}


def test_get_voice_settings_missing_user(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"1": {"mode": "voice"}}), encoding="utf-8")
    monkeypatch.setattr(tts, "VOICE_REPLY_CONFIG", str(cfg))
    assert tts.get_voice_settings(99) == {"mode": "text", "speed": 175}


# ---------- set_voice_setting ----------


def test_set_voice_setting_creates_file(tmp_path, monkeypatch):
    cfg_path = tmp_path / "voice_cfg.json"
    monkeypatch.setattr(tts, "VOICE_REPLY_CONFIG", str(cfg_path))
    tts.set_voice_setting(7, "speed", 150)
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert data["7"]["speed"] == 150
    assert data["7"]["mode"] == "text"


def test_set_voice_setting_updates_existing(tmp_path, monkeypatch):
    cfg_path = tmp_path / "voice_cfg.json"
    cfg_path.write_text(json.dumps({"7": {"mode": "voice", "speed": 175}}), encoding="utf-8")
    monkeypatch.setattr(tts, "VOICE_REPLY_CONFIG", str(cfg_path))
    tts.set_voice_setting(7, "mode", "both")
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert data["7"]["mode"] == "both"
    assert data["7"]["speed"] == 175


# ---------- generate_voice_async ----------


class FakeProc:
    def __init__(self, returncode=0, create_ogg=None):
        self.returncode = returncode
        self.create_ogg = create_ogg
        self.communicated = False

    async def communicate(self):
        self.communicated = True
        if self.create_ogg:
            with open(self.create_ogg, "w") as f:
                f.write("OGG")
        return b"", b""


class FakeSubprocess:
    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    async def __call__(self, *cmd, **kwargs):
        self.calls.append(cmd)
        return self._results.pop(0)


@pytest.mark.asyncio
async def test_generate_voice_async_empty_text():
    assert await tts.generate_voice_async(1, "❌ ошибка") == []


@pytest.mark.asyncio
async def test_generate_voice_async_success(monkeypatch, tmp_path):
    out_dir = tmp_path / "voice"
    out_dir.mkdir()
    monkeypatch.setattr(tts, "VOICE_OUTPUT_DIR", str(out_dir))
    monkeypatch.setattr(tts, "VOICE_REPLY_CONFIG", str(tmp_path / "nope.json"))

    generated = {}

    def make_proc(create_ogg=None):
        return FakeProc(create_ogg=create_ogg)

    async def fake_subprocess(*cmd, **kwargs):
        if cmd[0] == "ffmpeg":
            ogg = cmd[cmd.index("-b:a") + 2]
            generated["ogg"] = ogg
            return make_proc(create_ogg=ogg)
        return make_proc()

    monkeypatch.setattr(tts.asyncio, "create_subprocess_exec", fake_subprocess)

    _uid = 12345
    monkeypatch.setattr(
        tts.tempfile, "_get_candidate_names", lambda: iter([f"{_uid}{i}" for i in range(10)]),
    )

    paths = await tts.generate_voice_async(1, "привет мир")
    assert len(paths) == 1
    assert paths[0].endswith(".ogg")
    assert os.path.exists(paths[0])
    # aiff cleaned
    aiffs = [p for p in os.listdir(out_dir) if p.endswith(".aiff")]
    assert aiffs == []


@pytest.mark.asyncio
async def test_generate_voice_async_say_failure(monkeypatch, tmp_path):
    out_dir = tmp_path / "voice"
    out_dir.mkdir()
    monkeypatch.setattr(tts, "VOICE_OUTPUT_DIR", str(out_dir))
    runner = FakeSubprocess([FakeProc(returncode=1)])
    monkeypatch.setattr(tts.asyncio, "create_subprocess_exec", runner)
    paths = await tts.generate_voice_async(1, "текст")
    assert paths == []


@pytest.mark.asyncio
async def test_generate_voice_async_cleans_aiff(monkeypatch, tmp_path):
    out_dir = tmp_path / "voice"
    out_dir.mkdir()
    monkeypatch.setattr(tts, "VOICE_OUTPUT_DIR", str(out_dir))
    monkeypatch.setattr(tts, "VOICE_REPLY_CONFIG", str(tmp_path / "nope.json"))

    async def fake_subprocess(*cmd, **kwargs):
        if cmd[0] == "say":
            aiff = cmd[cmd.index("-o") + 1]
            with open(aiff, "w") as f:
                f.write("AIFF")
            return FakeProc()
        if cmd[0] == "ffmpeg":
            ogg = cmd[cmd.index("-b:a") + 2]
            return FakeProc(create_ogg=ogg)
        return FakeProc()

    monkeypatch.setattr(tts.asyncio, "create_subprocess_exec", fake_subprocess)
    monkeypatch.setattr(
        tts.tempfile, "_get_candidate_names", lambda: iter([f"{i}" for i in range(10)]),
    )

    paths = await tts.generate_voice_async(1, "текст для озвучки")
    assert len(paths) == 1
    aiffs = [p for p in os.listdir(out_dir) if p.endswith(".aiff")]
    assert aiffs == []


@pytest.mark.asyncio
async def test_generate_voice_async_ffmpeg_failure_no_ogg(monkeypatch, tmp_path):
    out_dir = tmp_path / "voice"
    out_dir.mkdir()
    monkeypatch.setattr(tts, "VOICE_OUTPUT_DIR", str(out_dir))
    runner = FakeSubprocess([FakeProc(), FakeProc()])
    monkeypatch.setattr(tts.asyncio, "create_subprocess_exec", runner)
    paths = await tts.generate_voice_async(1, "текст")
    assert paths == []


@pytest.mark.asyncio
async def test_generate_voice_async_exception_caught(monkeypatch, tmp_path):
    out_dir = tmp_path / "voice"
    out_dir.mkdir()
    monkeypatch.setattr(tts, "VOICE_OUTPUT_DIR", str(out_dir))

    async def boom(*cmd, **kwargs):
        raise OSError("say not found")

    monkeypatch.setattr(tts.asyncio, "create_subprocess_exec", boom)
    paths = await tts.generate_voice_async(1, "текст")
    assert paths == []
