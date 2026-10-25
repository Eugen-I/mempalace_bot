"""Pytest configuration for the mempalace_bot repository.

Ensure the repository root is on sys.path so tests can import the local
package layout consistently from any invocation path.
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PARENT_DIR = os.path.abspath(os.path.join(REPO_ROOT, ".."))

paths = [REPO_ROOT]
if os.path.basename(REPO_ROOT) != "mutants":
    paths.append(PARENT_DIR)

for path in paths:
    if path not in sys.path:
        sys.path.insert(0, path)

try:
    import importlib.util

    if importlib.util.find_spec("mempalace_bot") is None:
        import types

        package = types.ModuleType("mempalace_bot")
        package.__path__ = [REPO_ROOT]
        sys.modules["mempalace_bot"] = package
except Exception:
    pass


@dataclass
class FakeAIClient:
    """Небольшой управляемый AI-клиент для unit-тестов.

    Не зависит от реального провайдера. Позволяет задать ответ, ошибку и
    задержку, а также записывает все вызовы. Синхронный и асинхронный методы
    специально названы по-разному, чтобы тест явно выбирал режим.
    """

    response: Any = "fake response"
    error: BaseException | None = None
    delay: float = 0.0
    calls: list[dict[str, Any]] = field(default_factory=list)

    def _record(self, prompt: str, mode: str, kwargs: dict[str, Any]) -> None:
        self.calls.append({"prompt": prompt, "mode": mode, **kwargs})

    def complete(self, prompt: str, **kwargs: Any) -> Any:
        """Синхронный вызов: вернуть ответ или поднять заданную ошибку."""
        self._record(prompt, "sync", kwargs)
        if self.error is not None:
            raise self.error
        return self.response

    async def acomplete(self, prompt: str, **kwargs: Any) -> Any:
        """Асинхронный вызов с опциональной задержкой."""
        self._record(prompt, "async", kwargs)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return self.response


class Heartbeat:
    """Тикает в event loop, пока тест ждёт асинхронную операцию.

    Используется как async context manager:

        async with heartbeat(interval=0.01) as hb:
            await asyncio.sleep(0.1)
        assert hb.ticks >= 2

    Если во время `await` event loop заблокирован синхронным вызовом,
    количество тиков будет меньше ожидаемого.
    """

    def __init__(self, interval: float = 0.01) -> None:
        if interval <= 0:
            raise ValueError("interval must be positive")
        self.interval = interval
        self.ticks = 0
        self._task: asyncio.Task[None] | None = None
        self._stop: asyncio.Event | None = None

    async def _run(self) -> None:
        assert self._stop is not None
        while not self._stop.is_set():
            await asyncio.sleep(self.interval)
            if not self._stop.is_set():
                self.ticks += 1

    async def __aenter__(self) -> Self:
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._run())
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._stop is not None:
            self._stop.set()
        if self._task is not None:
            try:
                await self._task
            except asyncio.CancelledError:
                pass


@dataclass
class FixedClock:
    """Управляемые часы без подмены глобального `time`/`datetime`."""

    current: datetime = field(
        default_factory=lambda: datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )

    def now(self, tz: tzinfo | None = None) -> datetime:
        if tz is None:
            return self.current
        return self.current.astimezone(tz)

    def time(self) -> float:
        return self.current.timestamp()

    def advance(self, seconds: float) -> datetime:
        self.current += timedelta(seconds=seconds)
        return self.current


@pytest.fixture
def fake_ai_client() -> FakeAIClient:
    """Opt-in fixture: свежий fake AI-клиент для каждого теста."""
    return FakeAIClient()


@pytest.fixture
def heartbeat() -> type[Heartbeat]:
    """Opt-in fixture: фабрика Heartbeat для проверки отзывчивости loop."""
    return Heartbeat


@pytest.fixture
def temp_chat_dir(tmp_path: Path) -> Path:
    """Opt-in fixture: изолированный пустой каталог для чатов."""
    chats = tmp_path / "chats"
    chats.mkdir()
    return chats


@pytest.fixture
def fixed_clock() -> FixedClock:
    """Opt-in fixture: фиксированные часы, которые можно двигать вручную."""
    return FixedClock()
