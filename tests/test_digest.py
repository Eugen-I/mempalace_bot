"""Тесты services/digest.py — утренний дайджест.

Покрытие: границы суток, сбор напоминаний/заметок/KG, форматирование,
отправка, автозапуск (окно времени, отметка last_send, ошибки).
"""
import os
import time
from datetime import datetime, timedelta

import pytest

import services.digest as dg
from services.kv_store import KVStore


@pytest.fixture
def kv(monkeypatch, tmp_path):
    store = KVStore(db_path=str(tmp_path / "digest.sqlite"))
    monkeypatch.setattr(dg, "get_kv_store", lambda: store)
    return store


def _ts(hour: int, minute: int = 0, day_offset: int = 0, now_ts: float | None = None) -> float:
    base = datetime.fromtimestamp(now_ts) if now_ts else datetime.now()
    dt = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return (dt + timedelta(days=day_offset)).timestamp()
# ─── Границы суток ───


def test_day_bounds_midnight():
    ts = _ts(0, 0, 0)
    start, end = dg._day_bounds(ts)
    assert start == ts
    assert end == ts + 86400


def test_day_bounds_evening():
    ts = _ts(23, 59, 59)
    start, end = dg._day_bounds(ts)
    assert start < ts < end


def test_yesterday_bounds():
    start, _ = dg._day_bounds()
    y_start, y_end = dg._yesterday_bounds()
    assert y_end == start
    assert y_end - y_start == 86400


# ─── Напоминания дня ───

def _add_reminder(kv, key, ts, chat_id=42):
    kv.set(key, {"remind_at": ts, "text": f"текст {key}", "chat_id": chat_id},
           namespace="reminders")


def test_collect_today_reminders_happy(kv):
    now = time.time()
    today_9 = _ts(9, 0, 0, now)
    today_12 = _ts(12, 0, 0, now)
    tomorrow = _ts(9, 0, 1, now)
    yesterday = _ts(9, 0, -1, now)
    _add_reminder(kv, "a", today_12)
    _add_reminder(kv, "b", today_9)
    _add_reminder(kv, "c", tomorrow)
    _add_reminder(kv, "d", yesterday)
    got = dg.collect_today_reminders(now, kv=kv)
    assert [r["text"] for r in got] == ["текст b", "текст a"]
    assert len(got) == 2


def test_collect_today_reminders_boundaries(kv):
    now = time.time()
    start, end = dg._day_bounds(now)
    _add_reminder(kv, "start", start)
    _add_reminder(kv, "end", end)
    _add_reminder(kv, "before", start - 0.001)
    got = dg.collect_today_reminders(now, kv=kv)
    assert [r["text"] for r in got] == ["текст start"]
    assert "текст end" not in [r["text"] for r in got]


def test_collect_today_reminders_empty(kv):
    assert dg.collect_today_reminders(time.time(), kv=kv) == []


def test_collect_today_reminders_limit(kv):
    now = time.time()
    for i in range(15):
        _add_reminder(kv, f"r{i}", _ts(8 + (i % 5), i % 60, 0, now))
    got = dg.collect_today_reminders(now, kv=kv)
    assert len(got) == dg.MAX_REMINDERS


def test_collect_today_reminders_null_data_skipped(kv):
    now = time.time()
    kv.set("null_key", None, namespace="reminders")
    kv.set("bad", "строка", namespace="reminders")
    assert dg.collect_today_reminders(now, kv=kv) == []


def test_collect_today_reminders_kv_down(kv, monkeypatch, caplog):
    class BrokenKV:
        def keys(self, namespace=None):
            raise RuntimeError("kv down")

    monkeypatch.setattr(dg, "get_kv_store", lambda: BrokenKV())
    assert dg.collect_today_reminders(time.time(), kv=BrokenKV()) == []


def test_collect_today_reminders_get_failed_skipped(kv, caplog):
    now = time.time()
    _add_reminder(kv, "r", _ts(9, 0, 0, now))

    class FlakyKV:
        def __init__(self, inner):
            self.inner = inner

        def keys(self, namespace=None):
            return self.inner.keys(namespace)

        def get(self, key, namespace="default", default=None):
            raise RuntimeError("get boom")

    got = dg.collect_today_reminders(now, kv=FlakyKV(kv))
    assert got == []
    assert "kv get failed" in caplog.text


# ─── Заметки вчера ───

@pytest.fixture
def notes_dir(tmp_path):
    d = tmp_path / "my_notes"
    d.mkdir()
    return str(d)


def _touch(path: str, ts: float, content: str = "текст"):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    os.utime(path, (ts, ts))


def test_collect_yesterday_notes_happy(notes_dir):
    now = time.time()
    y_start, _ = dg._yesterday_bounds(now)
    y_noon = y_start + 12 * 3600
    _touch(os.path.join(notes_dir, "a.txt"), y_noon)
    _touch(os.path.join(notes_dir, "b.md"), y_noon + 60)
    _touch(os.path.join(notes_dir, "today.txt"), _ts(9, 0, 0, now))
    _touch(os.path.join(notes_dir, "older.txt"), y_start - 3600)
    _touch(os.path.join(notes_dir, "skip.pdf"), y_noon)
    got = dg.collect_yesterday_notes(now, notes_dir=notes_dir)
    assert [n["name"] for n in got] == ["a.txt", "b.md"]


def test_collect_yesterday_notes_boundary(notes_dir):
    now = time.time()
    y_start, y_end = dg._yesterday_bounds(now)
    _touch(os.path.join(notes_dir, "at_start.txt"), y_start)
    _touch(os.path.join(notes_dir, "at_end.txt"), y_end)
    got = dg.collect_yesterday_notes(now, notes_dir=notes_dir)
    assert [n["name"] for n in got] == ["at_start.txt"]


def test_collect_yesterday_notes_missing_dir(tmp_path):
    assert dg.collect_yesterday_notes(time.time(), notes_dir=str(tmp_path / "nope")) == []


def test_collect_yesterday_notes_limit(notes_dir):
    now = time.time()
    y_start, _ = dg._yesterday_bounds(now)
    for i in range(12):
        _touch(os.path.join(notes_dir, f"n{i}.txt"), y_start + 1000 * i)
    got = dg.collect_yesterday_notes(now, notes_dir=notes_dir)
    assert len(got) == dg.MAX_NOTES


def test_collect_yesterday_notes_broken_mtime(notes_dir, monkeypatch):
    now = time.time()
    _touch(os.path.join(notes_dir, "ok.txt"), _ts(9, 0, 0, now) - 86400)
    _touch(os.path.join(notes_dir, "broken.txt"), _ts(9, 0, 0, now) - 86400)
    real_getmtime = os.path.getmtime
    calls = {"n": 0}

    def flaky_getmtime(path):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("gone")
        return real_getmtime(path)

    monkeypatch.setattr(os.path, "getmtime", flaky_getmtime)
    got = dg.collect_yesterday_notes(now, notes_dir=notes_dir)
    assert [n["name"] for n in got] == ["ok.txt"]


# ─── KG-сводка ───

async def test_collect_kg_summary_happy():
    async def cb():
        return '{"entities": 3, "triples": 5, "current_facts": 2, "nested": {"a": 1}}'

    got = await dg.collect_kg_summary(cb)
    assert got == {"entities": 3, "triples": 5, "current_facts": 2}


async def test_collect_kg_summary_non_dict():
    async def cb():
        return "[1, 2, 3]"

    assert await dg.collect_kg_summary(cb) == {}


async def test_collect_kg_summary_bad_json():
    async def cb():
        return "not json"

    assert await dg.collect_kg_summary(cb) == {}


async def test_collect_kg_summary_mcp_down(caplog):
    async def cb():
        raise RuntimeError("mcp down")

    assert await dg.collect_kg_summary(cb) == {}
    assert "kg summary failed" in caplog.text


async def test_collect_kg_summary_default_cb(monkeypatch):
    calls = []

    class FakeMCP:
        async def call_tool(self, name, args=None):
            calls.append(name)
            return '{"entities": 1}'

    monkeypatch.setattr("services.palace_mcp.get_mcp", lambda: FakeMCP())
    assert await dg.collect_kg_summary() == {"entities": 1}
    assert calls == ["mempalace_kg_stats"]


# ─── Форматирование ───

def test_build_digest_text_all_blocks():
    now = time.time()
    text = dg.build_digest_text(
        [{"remind_at": _ts(9, 0, 0, now), "text": "позвонить маме"}],
        [{"name": "Идея проекта"}],
        {"entities": 3},
        now,
    )
    assert "Напоминания на сегодня" in text
    assert "Заметки вчера" in text
    assert "Граф знаний" in text


def test_build_digest_text_escapes_html():
    now = time.time()
    text = dg.build_digest_text(
        [{
            "remind_at": _ts(9, 0, 0, now),
            "text": "позвонить <b>маме</b> <script>alert(1)</script>",
        }],
        [],
        {},
        now,
    )
    assert "<b>маме</b>" in text
    assert "<script>" not in text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text


def test_build_digest_text_empty():
    assert dg.build_digest_text([], [], {}) == ""


def test_build_digest_text_bad_timestamp():
    now = time.time()
    text = dg.build_digest_text(
        [{"remind_at": 10 ** 20, "text": "далеко в будущем"}],
        [], {}, now,
    )
    assert "⏰ ?" in text


def test_build_digest_text_kg_labels():
    now = time.time()
    text = dg.build_digest_text([], [], {"current_facts": 7}, now)
    assert "Граф знаний" in text
    assert "7" in text


def test_build_digest_text_kg_zero_values_hidden():
    now = time.time()
    text = dg.build_digest_text([], [], {"entities": 0, "current_facts": 0}, now)
    assert text == ""


def test_interpreter_name_fallback(monkeypatch):
    def boom(name):
        raise RuntimeError("interpreter down")

    monkeypatch.setattr("services.interpreter.display_name", boom)
    assert dg.interpreter_name("current_facts") == "current_facts"


# ─── Отправка ───

class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, parse_mode=None):
        self.sent.append((chat_id, text, parse_mode))


async def test_send_digest_to_chat_happy(kv, monkeypatch):
    async def _empty(*a, **k):
        return {}

    monkeypatch.setattr(dg, "collect_kg_summary", _empty)
    now = time.time()
    _add_reminder(kv, "r", _ts(10, 0, 0, now), chat_id=77)
    bot = FakeBot()
    sent = await dg.send_digest_to_chat(bot, 77, now_ts=now, kv=kv)
    assert sent is True
    assert bot.sent[0][0] == 77
    assert "Напоминания на сегодня" in bot.sent[0][1]


async def test_send_digest_to_chat_empty_skips(kv, monkeypatch):
    async def _empty(*a, **k):
        return {}

    monkeypatch.setattr(dg, "collect_kg_summary", _empty)
    bot = FakeBot()
    sent = await dg.send_digest_to_chat(bot, 77, now_ts=time.time(), kv=kv)
    assert sent is False
    assert bot.sent == []


# ─── Автозапуск ───

def test_digest_window_open():
    ts = _ts(dg.DIGEST_START_HOUR, 0, 0)
    assert dg._digest_window_open(ts) is True
    ts_end = _ts(dg.DIGEST_END_HOUR, 0, 0)
    assert dg._digest_window_open(ts_end) is False


async def test_maybe_send_outside_window(kv, monkeypatch):
    async def _empty(*a, **k):
        return {}

    monkeypatch.setattr(dg, "collect_kg_summary", _empty)
    bot = FakeBot()
    now = _ts(6, 0, 0)
    _add_reminder(kv, "r", _ts(9, 0, 0, now), chat_id=77)
    assert await dg.maybe_send_daily_digest(bot, now_ts=now, kv=kv) is False
    assert bot.sent == []


async def test_maybe_send_happy(kv, monkeypatch):
    async def _empty(*a, **k):
        return {}

    monkeypatch.setattr(dg, "collect_kg_summary", _empty)
    bot = FakeBot()
    now = _ts(dg.DIGEST_START_HOUR + 1, 0, 0)
    _add_reminder(kv, "r1", _ts(9, 0, 0, now), chat_id=77)
    _add_reminder(kv, "r2", _ts(10, 30, 0, now), chat_id=77)
    _add_reminder(kv, "r3", _ts(11, 0, 0, now), chat_id=88)
    assert await dg.maybe_send_daily_digest(bot, now_ts=now, kv=kv) is True
    assert {s[0] for s in bot.sent} == {77, 88}
    ymd = datetime.fromtimestamp(now).strftime("%Y-%m-%d")
    assert kv.get(dg.LAST_SEND_KEY, namespace=dg.DIGEST_NS) == ymd


async def test_maybe_send_once_per_day(kv, monkeypatch):
    async def _empty(*a, **k):
        return {}

    monkeypatch.setattr(dg, "collect_kg_summary", _empty)
    bot = FakeBot()
    now = _ts(dg.DIGEST_START_HOUR + 1, 0, 0)
    _add_reminder(kv, "r", _ts(9, 0, 0, now), chat_id=77)
    assert await dg.maybe_send_daily_digest(bot, now_ts=now, kv=kv) is True
    assert len(bot.sent) == 1
    later = _ts(dg.DIGEST_START_HOUR + 2, 0, 0)
    assert await dg.maybe_send_daily_digest(bot, now_ts=later, kv=kv) is False
    assert len(bot.sent) == 1


async def test_maybe_send_send_error_still_marks(kv, caplog, monkeypatch):
    async def _empty(*a, **k):
        return {}

    monkeypatch.setattr(dg, "collect_kg_summary", _empty)
    bot = FakeBot()

    async def boom(chat_id, text, parse_mode=None):
        raise RuntimeError("telegram down")

    bot.send_message = boom
    now = _ts(dg.DIGEST_START_HOUR + 1, 0, 0)
    _add_reminder(kv, "r", _ts(9, 0, 0, now), chat_id=77)
    assert await dg.maybe_send_daily_digest(bot, now_ts=now, kv=kv) is True
    assert "send to 77 failed" in caplog.text
    assert kv.get(dg.LAST_SEND_KEY, namespace=dg.DIGEST_NS) is not None


async def test_maybe_send_last_send_check_fails(kv, monkeypatch, caplog):
    async def _empty(*a, **k):
        return {}

    monkeypatch.setattr(dg, "collect_kg_summary", _empty)
    bot = FakeBot()
    now = _ts(dg.DIGEST_START_HOUR + 1, 0, 0)
    _add_reminder(kv, "r", _ts(9, 0, 0, now), chat_id=77)

    class FlakyGetKV:
        def __init__(self, inner):
            self.inner = inner

        def get(self, key, namespace="default", default=None):
            if key == dg.LAST_SEND_KEY:
                raise RuntimeError("get boom")
            return self.inner.get(key, namespace, default)

        def set(self, *a, **k):
            return self.inner.set(*a, **k)

        def keys(self, namespace=None):
            return self.inner.keys(namespace)

    assert await dg.maybe_send_daily_digest(bot, now_ts=now, kv=FlakyGetKV(kv)) is True
    assert "last_send check failed" in caplog.text
    assert bot.sent != []


async def test_maybe_send_mark_fails_still_sends(kv, monkeypatch, caplog):
    async def _empty(*a, **k):
        return {}

    monkeypatch.setattr(dg, "collect_kg_summary", _empty)
    bot = FakeBot()
    now = _ts(dg.DIGEST_START_HOUR + 1, 0, 0)
    _add_reminder(kv, "r", _ts(9, 0, 0, now), chat_id=77)

    class FlakySetKV:
        def __init__(self, inner):
            self.inner = inner

        def get(self, *a, **k):
            return self.inner.get(*a, **k)

        def set(self, *a, **k):
            if k.get("namespace") == dg.DIGEST_NS:
                raise RuntimeError("set boom")
            return self.inner.set(*a, **k)

        def keys(self, namespace=None):
            return self.inner.keys(namespace)

    assert await dg.maybe_send_daily_digest(bot, now_ts=now, kv=FlakySetKV(kv)) is True
    assert "last_send mark failed" in caplog.text
    assert bot.sent != []


# ─── Хендлер /дайджест ───

class FakeHandlerMessage:
    def __init__(self, chat_id):
        self.bot = FakeBot()
        self.chat = FakeChatId(chat_id)
        self.from_user = FakeUserId(4242)
        self.answers = []

    async def answer(self, text, parse_mode=None):
        self.answers.append(text)


class FakeUserId:
    def __init__(self, uid):
        self.id = uid


class FakeChatId:
    def __init__(self, cid):
        self.id = cid


async def test_cmd_digest_happy(monkeypatch):
    import config as cfg
    from handlers import digest as dh

    monkeypatch.setattr(cfg, "ALLOWED_IDS", {4242})
    msg = FakeHandlerMessage(77)

    async def fake_send(bot, chat_id, now_ts=None, kv=None):
        bot.sent.append((chat_id, "текст дайджеста"))
        return True

    monkeypatch.setattr(dh, "send_digest_to_chat", fake_send)
    await dh.cmd_digest(msg)
    assert msg.bot.sent == [(77, "текст дайджеста")]
    assert msg.answers == []


async def test_cmd_digest_empty_day(monkeypatch):
    import config as cfg
    from handlers import digest as dh

    monkeypatch.setattr(cfg, "ALLOWED_IDS", {4242})
    msg = FakeHandlerMessage(77)

    async def fake_send(bot, chat_id, now_ts=None, kv=None):
        return False

    monkeypatch.setattr(dh, "send_digest_to_chat", fake_send)
    await dh.cmd_digest(msg)
    assert msg.bot.sent == []
    assert msg.answers and "Всё чисто" in msg.answers[0]


async def test_cmd_digest_error(monkeypatch, caplog):
    import config as cfg
    from handlers import digest as dh

    monkeypatch.setattr(cfg, "ALLOWED_IDS", {4242})
    msg = FakeHandlerMessage(77)

    async def fake_send(bot, chat_id, now_ts=None, kv=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(dh, "send_digest_to_chat", fake_send)
    await dh.cmd_digest(msg)
    assert msg.answers and "Не удалось собрать" in msg.answers[0]
