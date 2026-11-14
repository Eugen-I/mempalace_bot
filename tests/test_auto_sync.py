"""Тесты services/auto_sync.py — автосинхронизация чата в Дворец.

Покрытие: успех, пустой экспорт, исключения.
"""
import asyncio
import logging

import services.auto_sync as auto_sync


def test_auto_sync_happy_path(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(
        auto_sync, "export_chat_verbatim", lambda path, name: "экспорт"
    )

    async def fake_sync(exported):
        return "OK 3 записи"

    monkeypatch.setattr(auto_sync, "sync_to_palace", fake_sync)
    asyncio.run(auto_sync.auto_sync_chat(42, "Чат", "/tmp/chat.md"))
    assert "OK 3 записи" in caplog.text


def test_auto_sync_empty_export_returns_early(monkeypatch):
    monkeypatch.setattr(auto_sync, "export_chat_verbatim", lambda path, name: "")

    async def fake_sync(exported):
        raise AssertionError("sync не должен вызываться")

    monkeypatch.setattr(auto_sync, "sync_to_palace", fake_sync)
    asyncio.run(auto_sync.auto_sync_chat(42, "Чат", "/tmp/chat.md"))


def test_auto_sync_exception_logged(monkeypatch, caplog):
    monkeypatch.setattr(
        auto_sync, "export_chat_verbatim", lambda path, name: "экспорт"
    )

    async def fake_sync(exported):
        raise RuntimeError("palace down")

    monkeypatch.setattr(auto_sync, "sync_to_palace", fake_sync)
    asyncio.run(auto_sync.auto_sync_chat(1, "Чат", "/tmp/chat.md"))
    assert "palace down" in caplog.text


def test_auto_sync_export_exception_logged(monkeypatch, caplog):
    def fake_export(path, name):
        raise RuntimeError("export broke")

    monkeypatch.setattr(auto_sync, "export_chat_verbatim", fake_export)
    asyncio.run(auto_sync.auto_sync_chat(1, "Чат", "/tmp/chat.md"))
    assert "export broke" in caplog.text
