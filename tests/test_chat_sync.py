"""Unit tests for services.chat_sync — shared manual chat sync scenario."""

import pytest

from services import chat_sync


@pytest.mark.asyncio
async def test_sync_chat_file_empty_export_skips_palace(monkeypatch):
    calls = []
    monkeypatch.setattr(
        chat_sync, "export_chat_verbatim", lambda path, name: None,
    )

    async def fake_sync(exported):
        calls.append(exported)
        return "✅ Синхронизировано"

    monkeypatch.setattr(chat_sync, "sync_to_palace", fake_sync)

    assert await chat_sync.sync_chat_file("/tmp/chat.json", "chat.json") is None
    assert calls == []


@pytest.mark.asyncio
async def test_sync_chat_file_passes_export_to_palace(monkeypatch):
    seen = []

    def fake_export(path, name):
        seen.append(("export", path, name))
        return "/tmp/chat_verbatim.txt"

    async def fake_sync(exported):
        seen.append(("sync", exported))
        return "✅ Синхронизировано"

    monkeypatch.setattr(chat_sync, "export_chat_verbatim", fake_export)
    monkeypatch.setattr(chat_sync, "sync_to_palace", fake_sync)

    result = await chat_sync.sync_chat_file("/tmp/chat.json", "chat.json")

    assert result == "✅ Синхронизировано"
    assert seen == [
        ("export", "/tmp/chat.json", "chat.json"),
        ("sync", "/tmp/chat_verbatim.txt"),
    ]


@pytest.mark.asyncio
async def test_sync_chat_file_export_error_returns_message(monkeypatch):
    def fake_export(path, name):
        raise OSError("disk")

    monkeypatch.setattr(chat_sync, "export_chat_verbatim", fake_export)

    result = await chat_sync.sync_chat_file("/tmp/chat.json", "chat.json")

    assert result == "❌ Ошибка синхронизации: disk"


@pytest.mark.asyncio
async def test_sync_chat_file_sync_error_returns_message(monkeypatch):
    monkeypatch.setattr(
        chat_sync, "export_chat_verbatim", lambda path, name: "/tmp/export.txt",
    )

    async def fake_sync(exported):
        raise RuntimeError("palace down")

    monkeypatch.setattr(chat_sync, "sync_to_palace", fake_sync)

    result = await chat_sync.sync_chat_file("/tmp/chat.json", "chat.json")

    assert result == "❌ Ошибка синхронизации: palace down"


@pytest.mark.asyncio
async def test_sync_active_chat_without_session(monkeypatch):
    async def fail_sync(*args, **kwargs):
        raise AssertionError("sync_chat_file не должен вызываться")

    monkeypatch.setattr(chat_sync, "sync_chat_file", fail_sync)

    result = await chat_sync.sync_active_chat(4242, {})

    assert result.status is chat_sync.ChatSyncStatus.NO_ACTIVE_CHAT
    assert result.message == chat_sync.NO_ACTIVE_CHAT_MESSAGE


@pytest.mark.asyncio
async def test_sync_active_chat_empty_chat_uses_chats_dir(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(chat_sync, "CHATS_DIR", str(tmp_path))

    def fake_export(path, name):
        seen.append((path, name))
        return None

    monkeypatch.setattr(chat_sync, "export_chat_verbatim", fake_export)

    result = await chat_sync.sync_active_chat(4242, {4242: "chat_4242.json"})

    assert result.status is chat_sync.ChatSyncStatus.EMPTY_CHAT
    assert result.message == chat_sync.EMPTY_CHAT_MESSAGE
    assert seen == [(str(tmp_path / "chat_4242.json"), "chat_4242.json")]


@pytest.mark.asyncio
async def test_sync_active_chat_returns_sync_result(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_sync, "CHATS_DIR", str(tmp_path))
    monkeypatch.setattr(
        chat_sync, "export_chat_verbatim", lambda path, name: "/tmp/export.txt",
    )

    async def fake_sync(exported):
        return "✅ Синхронизировано"

    monkeypatch.setattr(chat_sync, "sync_to_palace", fake_sync)

    result = await chat_sync.sync_active_chat(4242, {4242: "chat_4242.json"})

    assert result.status is chat_sync.ChatSyncStatus.RESULT
    assert result.message == "✅ Синхронизировано"
