"""Unit tests for cli_extras.py"""

import asyncio
import json
import os

import pytest

import cli_extras as extras


class FakeMCP:
    def __init__(self):
        self.calls = []
        self.results = {}

    async def call_tool(self, name, args=None):
        self.calls.append((name, args))
        return self.results.get(name, "")


class FakeKV:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value


def _async_val(value):
    async def _inner(*a, **k):
        return value
    return _inner


# ─── cli_remind ───


def test_cli_remind_empty():
    result = asyncio.run(extras.cli_remind("/remind", 0))
    assert "Укажите: /remind <текст>" in result


def test_cli_remind_not_reminder(monkeypatch):
    monkeypatch.setattr("handlers.reminder._is_reminder", lambda t: False)
    result = asyncio.run(extras.cli_remind("/remind завтра в 15:00 что-то"))
    assert "Не похоже на напоминание" in result


def test_cli_remind_parse_fail(monkeypatch):
    monkeypatch.setattr("handlers.reminder._is_reminder", lambda t: True)
    monkeypatch.setattr(
        "handlers.reminder._parse_reminder",
        lambda t: asyncio.coroutine(lambda: None)() if False else _async_val(None)(),
    )
    result = asyncio.run(extras.cli_remind("/remind завтра в 15:00 x"))
    assert "Не удалось разобрать" in result


def test_cli_remind_success(monkeypatch):
    monkeypatch.setattr("handlers.reminder._is_reminder", lambda t: True)
    monkeypatch.setattr(
        "handlers.reminder._parse_reminder",
        lambda t: _async_val({"text": "позвонить маме", "time_str": "завтра 15:00"})(),
    )
    kv = FakeKV()
    monkeypatch.setattr(extras, "get_kv_store", lambda: kv)
    result = asyncio.run(extras.cli_remind("/remind завтра в 15:00 позвонить маме"))
    assert "✅ Напоминание создано: позвонить маме — в завтра 15:00" in result
    assert kv.data["reminders"] == [{"text": "позвонить маме", "time_str": "завтра 15:00"}]


def test_cli_remind_appends_to_existing(monkeypatch):
    monkeypatch.setattr("handlers.reminder._is_reminder", lambda t: True)
    monkeypatch.setattr(
        "handlers.reminder._parse_reminder",
        lambda t: _async_val({"text": "t2", "time_str": "now"})(),
    )
    kv = FakeKV()
    kv.data["reminders"] = [{"text": "t1", "time_str": "old"}]
    monkeypatch.setattr(extras, "get_kv_store", lambda: kv)
    asyncio.run(extras.cli_remind("/remind x"))
    assert len(kv.data["reminders"]) == 2


# ─── cli_pdfs ───


def test_cli_pdfs_empty_list(monkeypatch):
    monkeypatch.setattr(extras, "list_archived_pdfs", lambda: [])
    assert "Архив PDF пуст" in asyncio.run(extras.cli_pdfs(""))


def test_cli_pdfs_list(monkeypatch):
    monkeypatch.setattr(
        extras, "list_archived_pdfs",
        lambda: [{"id": "1", "original_name": "doc.pdf"}],
    )
    out = asyncio.run(extras.cli_pdfs(""))
    assert "doc.pdf" in out and "1)" in out


def test_cli_pdfs_list_missing_name(monkeypatch):
    monkeypatch.setattr(
        extras, "list_archived_pdfs", lambda: [{"id": "abc"}],
    )
    assert "abc" in asyncio.run(extras.cli_pdfs(""))


def test_cli_pdfs_bad_number(monkeypatch):
    monkeypatch.setattr(
        extras, "list_archived_pdfs",
        lambda: [{"id": "1", "original_name": "doc.pdf"}],
    )
    assert "Неверный номер PDF" in asyncio.run(extras.cli_pdfs("5"))


def test_cli_pdfs_read_ok(monkeypatch):
    monkeypatch.setattr(
        extras, "list_archived_pdfs",
        lambda: [{"id": "1", "original_name": "doc.pdf", "path": "/p"}],
    )
    monkeypatch.setattr(
        extras, "extract_pdf_async",
        lambda p: _async_val(("TEXT" * 1000, "meta x"))(),
    )
    out = asyncio.run(extras.cli_pdfs("1"))
    assert "doc.pdf" in out and "4000 символов" in out and "meta x" in out


def test_cli_pdfs_read_empty_text(monkeypatch):
    monkeypatch.setattr(
        extras, "list_archived_pdfs",
        lambda: [{"id": "1", "original_name": "doc.pdf", "path": "/p"}],
    )
    monkeypatch.setattr(
        extras, "extract_pdf_async", lambda p: _async_val(("", None))(),
    )
    assert "Не удалось извлечь текст" in asyncio.run(extras.cli_pdfs("1"))


def test_cli_pdfs_analyze(monkeypatch):
    monkeypatch.setattr(
        extras, "list_archived_pdfs",
        lambda: [{"id": "1", "original_name": "doc.pdf", "path": "/p"}],
    )
    monkeypatch.setattr(
        extras, "extract_pdf_async",
        lambda p: _async_val(("TEXT" * 300, None))(),
    )
    out = asyncio.run(extras.cli_pdfs("analyze 1"))
    assert "Текст извлечён (1200 символов)" in out
    assert "Первые 1000" in out


def test_cli_pdfs_analyze_bad_number(monkeypatch):
    monkeypatch.setattr(
        extras, "list_archived_pdfs",
        lambda: [{"id": "1", "original_name": "doc.pdf", "path": "/p"}],
    )
    assert "Неверный номер PDF" in asyncio.run(extras.cli_pdfs("analyze 5"))


def test_cli_pdfs_unknown_returns_none(monkeypatch):
    assert asyncio.run(extras.cli_pdfs("что-то там")) is None


# ─── cli_yt ───


def test_cli_yt_no_url():
    out = asyncio.run(extras.cli_yt("", "video"))
    assert "Укажите URL" in out


def test_cli_yt_video_ok(monkeypatch):
    monkeypatch.setattr(extras, "download_video",
                        lambda url, q: _async_val("/v.mp4")(url, q))
    out = asyncio.run(extras.cli_yt("https://youtube.com/x 480", "video"))
    assert "📹 Видео: /v.mp4" in out


def test_cli_yt_video_fail(monkeypatch):
    monkeypatch.setattr(extras, "download_video",
                        lambda url, q: _async_val(None)(url, q))
    assert "Не удалось скачать видео" in asyncio.run(extras.cli_yt("https://x", "video"))


def test_cli_yt_audio_ok(monkeypatch, tmp_path):
    trans = tmp_path / "t.txt"
    trans.write_text("subtitle text")
    monkeypatch.setattr(
        extras, "download_audio", lambda url: _async_val(("/a.mp3", "meta"))(url))
    monkeypatch.setattr(
        extras, "transcribe_audio",
        lambda p, n: _async_val(str(trans))(p, n))
    out = asyncio.run(extras.cli_yt("https://x", "audio"))
    assert "🎵 Аудио: /a.mp3" in out
    assert "13 символов" in out
    assert "subtitle text" in out


def test_cli_yt_audio_transcribe_failed(monkeypatch):
    monkeypatch.setattr(
        extras, "download_audio", lambda url: _async_val("/a.mp3")(url))
    monkeypatch.setattr(
        extras, "transcribe_audio", lambda p, n: _async_val("/nonexistent")())
    out = asyncio.run(extras.cli_yt("https://x", "audio"))
    assert "0 символов" in out and "(транскрипция не удалась)" in out


def test_cli_yt_audio_download_fail(monkeypatch):
    monkeypatch.setattr(
        extras, "download_audio", lambda url: _async_val(None)(url))
    assert "Не удалось скачать аудио" in asyncio.run(extras.cli_yt("https://x", "audio"))


# ─── cli_tunnels ───


def test_tunnels_list_empty(monkeypatch):
    mcp = FakeMCP()
    mcp.results["mempalace_list_tunnels"] = "[]"
    monkeypatch.setattr(extras, "get_mcp", lambda: mcp)
    assert "Туннелей пока нет" in asyncio.run(extras.cli_tunnels("list"))


def test_tunnels_list_parsed(monkeypatch):
    mcp = FakeMCP()
    mcp.results["mempalace_list_tunnels"] = json.dumps([
        {"source": "A/1", "target": "B/2", "label": "lab"},
        {"wing_a": "A", "room_a": "1", "wing_b": "B", "room_b": "2", "label": ""},
    ])
    monkeypatch.setattr(extras, "get_mcp", lambda: mcp)
    out = asyncio.run(extras.cli_tunnels(""))
    assert "A/1 ↔ B/2 — lab" in out
    assert "A/1 ↔ B/2" in out


def test_tunnels_list_bad_json(monkeypatch):
    mcp = FakeMCP()
    mcp.results["mempalace_list_tunnels"] = "not json"
    monkeypatch.setattr(extras, "get_mcp", lambda: mcp)
    out = asyncio.run(extras.cli_tunnels("list"))
    assert "not json" in out


def test_tunnels_create(monkeypatch):
    mcp = FakeMCP()
    mcp.results["mempalace_create_tunnel"] = "ok"
    monkeypatch.setattr(extras, "get_mcp", lambda: mcp)
    out = asyncio.run(extras.cli_tunnels("create A 1 B 2 ярлык"))
    assert "✅ Туннель создан: A/1 ↔ B/2" in out
    assert mcp.calls[0][1]["label"] == "ярлык"


def test_tunnels_create_fail(monkeypatch):
    mcp = FakeMCP()
    monkeypatch.setattr(extras, "get_mcp", lambda: mcp)
    assert "Ошибка" in asyncio.run(extras.cli_tunnels("create A 1 B 2"))


def test_tunnels_delete(monkeypatch):
    mcp = FakeMCP()
    mcp.results["mempalace_delete_tunnel"] = "ok"
    monkeypatch.setattr(extras, "get_mcp", lambda: mcp)
    out = asyncio.run(extras.cli_tunnels("delete 42"))
    assert "Туннель 42 удалён" in out
    assert mcp.calls == [("mempalace_delete_tunnel", {"tunnel_id": "42"})]


def test_tunnels_delete_fail(monkeypatch):
    mcp = FakeMCP()
    monkeypatch.setattr(extras, "get_mcp", lambda: mcp)
    assert "Ошибка" in asyncio.run(extras.cli_tunnels("delete 42"))


def test_tunnels_analyze(monkeypatch):
    mcp = FakeMCP()
    mcp.results["mempalace_list_tunnels"] = "[1, 2, 3]"
    monkeypatch.setattr(extras, "get_mcp", lambda: mcp)
    out = asyncio.run(extras.cli_tunnels("analyze"))
    assert "Туннелей в базе: 9" in out


def test_tunnels_help(monkeypatch):
    mcp = FakeMCP()
    monkeypatch.setattr(extras, "get_mcp", lambda: mcp)
    out = asyncio.run(extras.cli_tunnels("unknown"))
    assert "ℹ️ /tunnels list" in out


# ─── cli_kgadd ───


def test_kgadd_short_args():
    assert "/kgadd <субъект>" in asyncio.run(extras.cli_kgadd("a b"))


def test_kgadd_ok(monkeypatch):
    mcp = FakeMCP()
    mcp.results["mempalace_add_fact"] = "ok"
    monkeypatch.setattr(extras, "get_mcp", lambda: mcp)
    out = asyncio.run(extras.cli_kgadd("суб пре об"))
    assert "✅ Факт: суб → пре → об" in out
    assert mcp.calls == [("mempalace_add_fact", {
        "subject": "суб", "predicate": "пре", "object": "об"})]


def test_kgadd_fail(monkeypatch):
    mcp = FakeMCP()
    monkeypatch.setattr(extras, "get_mcp", lambda: mcp)
    assert "Ошибка" in asyncio.run(extras.cli_kgadd("суб пре об"))


# ─── cli_transkript ───


def test_transkript_no_dir(monkeypatch):
    monkeypatch.setattr("config.TRANSKRIPT_DIR", "/nonexistent_dir_xyz")
    assert "не найдена" in asyncio.run(extras.cli_transkript(""))


def test_transkript_empty(monkeypatch, tmp_path):
    monkeypatch.setattr("config.TRANSKRIPT_DIR", str(tmp_path))
    assert "пуста" in asyncio.run(extras.cli_transkript(""))


def test_transkript_list(monkeypatch, tmp_path):
    (tmp_path / "a.txt").write_text("x" * 2048)
    (tmp_path / "b.txt").write_text("y" * 2048)
    monkeypatch.setattr("config.TRANSKRIPT_DIR", str(tmp_path))
    out = asyncio.run(extras.cli_transkript(""))
    assert "Транскрипты (2):" in out
    assert "a.txt" in out and "2 KB" in out


def test_transkript_bad_number(monkeypatch, tmp_path):
    (tmp_path / "a.txt").write_text("x")
    monkeypatch.setattr("config.TRANSKRIPT_DIR", str(tmp_path))
    assert "Номер от 1 до 1" in asyncio.run(extras.cli_transkript("5"))


def test_transkript_read(monkeypatch, tmp_path):
    (tmp_path / "a.txt").write_text("hello transkript")
    monkeypatch.setattr("config.TRANSKRIPT_DIR", str(tmp_path))
    out = asyncio.run(extras.cli_transkript("1"))
    assert "hello transkript" in out and "(16 символов)" in out


def test_transkript_read_error(monkeypatch, tmp_path):
    (tmp_path / "a.txt").write_text("x")
    monkeypatch.setattr("config.TRANSKRIPT_DIR", str(tmp_path))
    monkeypatch.setattr("builtins.open", _raise_open)
    assert "Ошибка чтения" in asyncio.run(extras.cli_transkript("1"))


def _raise_open(*a, **k):
    raise OSError("permission")


def test_transkript_unknown_returns_none(monkeypatch, tmp_path):
    (tmp_path / "a.txt").write_text("x")
    monkeypatch.setattr("config.TRANSKRIPT_DIR", str(tmp_path))
    assert asyncio.run(extras.cli_transkript("abc")) is None


# ─── cli_palace_cmd ───


@pytest.mark.parametrize(
    "cmd,svc",
    [
        ("status", "palace_status"),
        ("repair", "palace_repair"),
        ("compact", "palace_compact"),
        ("compress", "palace_compress"),
        ("wakeup", "palace_wake_up"),
    ],
)
def test_palace_cmd_dispatch(monkeypatch, cmd, svc):
    monkeypatch.setattr(extras, svc, _async_val(f"{svc} done"))
    assert asyncio.run(extras.cli_palace_cmd(cmd)) == f"{svc} done"


def test_palace_cmd_unknown():
    assert asyncio.run(extras.cli_palace_cmd("foo")) is None
