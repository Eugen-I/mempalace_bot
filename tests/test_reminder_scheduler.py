"""Тесты services/reminder_scheduler.py — фоновый планировщик напоминаний.

Покрытие: цикл обработки, отправка, ошибки отправки, старт/стоп синглтона.
"""
import asyncio
import time

import pytest

import services.reminder_scheduler as rs
from services.kv_store import KVStore


class FakeBot:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    async def send_message(self, chat_id, text, parse_mode=None):
        if self.fail:
            raise RuntimeError("telegram down")
        self.sent.append((chat_id, text, parse_mode))


@pytest.fixture(autouse=True)
def _reset_scheduler():
    rs._scheduler_task = None
    yield
    rs.stop_scheduler()


@pytest.fixture
def kv(monkeypatch, tmp_path):
    store = KVStore(db_path=str(tmp_path / "reminders.sqlite"))
    monkeypatch.setattr(rs, "get_kv_store", lambda: store)
    return store


async def _run_one_cycle(scheduler, bot, iterations=2):
    """Запускает корутину планировщика, прерывая после N итераций sleep."""
    original_sleep = asyncio.sleep
    counter = {"n": 0}

    async def short_sleep(delay):
        counter["n"] += 1
        if counter["n"] >= iterations:
            raise KeyboardInterrupt

    asyncio.sleep = short_sleep
    try:
        with pytest.raises(KeyboardInterrupt):
            await scheduler(bot)
    finally:
        asyncio.sleep = original_sleep


def test_scheduler_sends_due_reminder(kv):
    bot = FakeBot()
    kv.set(
        "r1",
        {"remind_at": time.time() - 5, "text": "позвонить маме", "user_id": 1, "chat_id": 42},
        namespace="reminders",
    )
    asyncio.run(_run_one_cycle(rs._run_scheduler, bot))
    assert len(bot.sent) == 1
    assert bot.sent[0][0] == 42
    assert "позвонить маме" in bot.sent[0][1]
    assert kv.get("r1", namespace="reminders") is None


def test_scheduler_skips_future_reminder(kv):
    bot = FakeBot()
    kv.set(
        "r1",
        {"remind_at": time.time() + 3600, "text": "в будущем", "user_id": 1, "chat_id": 42},
        namespace="reminders",
    )
    asyncio.run(_run_one_cycle(rs._run_scheduler, bot))
    assert bot.sent == []
    assert kv.get("r1", namespace="reminders") is not None


def test_scheduler_keeps_reminder_on_send_error(kv, caplog):
    bot = FakeBot(fail=True)
    kv.set(
        "r1",
        {"remind_at": time.time() - 1, "text": "не доставится", "user_id": 1, "chat_id": 42},
        namespace="reminders",
    )
    asyncio.run(_run_one_cycle(rs._run_scheduler, bot))
    assert bot.sent == []
    assert "Send failed" in caplog.text


def test_scheduler_missing_data_skipped(kv):
    bot = FakeBot()
    asyncio.run(_run_one_cycle(rs._run_scheduler, bot))
    assert bot.sent == []


def test_scheduler_null_data_skipped(kv):
    kv.set("r_null", None, namespace="reminders")
    bot = FakeBot()
    asyncio.run(_run_one_cycle(rs._run_scheduler, bot))
    assert bot.sent == []
    assert "r_null" in kv.keys(namespace="reminders")


def test_scheduler_outer_error_logged(kv, caplog, monkeypatch):
    class BrokenStore:
        def keys(self, namespace=None):
            raise RuntimeError("kv down")

        def get(self, *a, **k):
            return None

        def delete(self, *a, **k):
            return None

    monkeypatch.setattr(rs, "get_kv_store", lambda: BrokenStore())
    bot = FakeBot()
    asyncio.run(_run_one_cycle(rs._run_scheduler, bot))
    assert "Scheduler error" in caplog.text


def test_scheduler_due_zero_remind_at(kv):
    """Граница: remind_at=0 считается просроченным."""
    bot = FakeBot()
    kv.set(
        "r0",
        {"remind_at": 0, "text": "сейчас же", "user_id": 1, "chat_id": 7},
        namespace="reminders",
    )
    asyncio.run(_run_one_cycle(rs._run_scheduler, bot))
    assert len(bot.sent) == 1


def test_scheduler_runs_auto_categorize_every_n_cycles(kv, monkeypatch):
    calls = []

    async def fake_categorize(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(
        "services.auto_categorize.auto_categorize_notes", fake_categorize,
    )
    monkeypatch.setattr(rs, "_CATEGORIZE_EVERY_CYCLES", 1)
    bot = FakeBot()
    asyncio.run(_run_one_cycle(rs._run_scheduler, bot, iterations=2))
    assert len(calls) == 2
    assert all(c["limit"] == 20 for c in calls)


def test_scheduler_auto_categorize_error_logged(kv, caplog, monkeypatch):
    async def fake_categorize(**kwargs):
        raise RuntimeError("categorize boom")

    monkeypatch.setattr(
        "services.auto_categorize.auto_categorize_notes", fake_categorize,
    )
    monkeypatch.setattr(rs, "_CATEGORIZE_EVERY_CYCLES", 1)
    bot = FakeBot()
    asyncio.run(_run_one_cycle(rs._run_scheduler, bot, iterations=1))
    assert "[CATEGORIZE] auto run failed: categorize boom" in caplog.text


def test_scheduler_auto_categorize_not_called_before_interval(kv, monkeypatch):
    calls = []

    async def fake_categorize(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(
        "services.auto_categorize.auto_categorize_notes", fake_categorize,
    )
    monkeypatch.setattr(rs, "_CATEGORIZE_EVERY_CYCLES", 100)
    bot = FakeBot()
    asyncio.run(_run_one_cycle(rs._run_scheduler, bot, iterations=3))
    assert calls == []


def test_start_scheduler_creates_task(kv):
    bot = FakeBot()

    async def _go():
        rs.start_scheduler(bot)
        assert rs._scheduler_task is not None
        assert not rs._scheduler_task.done()

    asyncio.run(_go())


def test_start_scheduler_idempotent(kv):
    bot = FakeBot()

    async def _go():
        rs.start_scheduler(bot)
        first = rs._scheduler_task
        rs.start_scheduler(bot)
        assert rs._scheduler_task is first

    asyncio.run(_go())


def test_stop_scheduler_cancels(kv):
    bot = FakeBot()

    async def _go():
        rs.start_scheduler(bot)
        rs.stop_scheduler()
        assert rs._scheduler_task is None

    asyncio.run(_go())
