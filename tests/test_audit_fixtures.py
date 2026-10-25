"""Smoke-тесты общих audit-фикстур (шаг S0.2).

Проверяют, что фикстуры из `tests/conftest.py` действительно работают и
пригодны для последующих шагов: fake AI, heartbeat, временный каталог чатов
и управляемые часы.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest


def test_fake_ai_client_sync_records_call(fake_ai_client):
    fake_ai_client.response = {"text": "ok"}

    assert fake_ai_client.complete("hello", model="test-model") == {"text": "ok"}
    assert fake_ai_client.calls == [
        {"prompt": "hello", "mode": "sync", "model": "test-model"},
    ]


def test_fake_ai_client_raises_configured_error(fake_ai_client):
    error = RuntimeError("provider is down")
    fake_ai_client.error = error

    with pytest.raises(RuntimeError, match="provider is down"):
        fake_ai_client.complete("hello")

    assert fake_ai_client.calls[0]["mode"] == "sync"


async def test_fake_ai_client_async_respects_delay(fake_ai_client):
    fake_ai_client.response = "async-ok"
    fake_ai_client.delay = 0.01

    assert await fake_ai_client.acomplete("hello") == "async-ok"
    assert fake_ai_client.calls[0]["mode"] == "async"


async def test_heartbeat_ticks_while_awaiting(heartbeat):
    async with heartbeat(interval=0.01) as hb:
        await asyncio.sleep(0.1)

    assert hb.ticks >= 2


def test_temp_chat_dir_is_writable(temp_chat_dir):
    chat_file = temp_chat_dir / "chat.json"
    chat_file.write_text("{}", encoding="utf-8")

    assert chat_file.read_text(encoding="utf-8") == "{}"


def test_fixed_clock_can_advance(fixed_clock):
    start = fixed_clock.now()

    assert fixed_clock.time() == start.timestamp()

    later = fixed_clock.advance(90)

    assert later - start == timedelta(seconds=90)
    assert fixed_clock.time() == later.timestamp()
