"""Unit tests for handlers.reminder."""

import json
import time
from datetime import datetime, timedelta

import pytest

from handlers import reminder as rem


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeChat:
    def __init__(self, cid):
        self.id = cid


class FakeMessage:
    def __init__(self, uid=4242, text=""):
        self.from_user = FakeUser(uid)
        self.text = text
        self.answers = []
        self.chat = FakeChat(1)

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append((text, parse_mode, reply_markup))
        return None

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits = getattr(self, "edits", [])
        self.edits.append(text)
        self.last_markup = reply_markup


class FakeCb:
    def __init__(self, uid=4242):
        self.from_user = FakeUser(uid)
        self.message = FakeMessage(uid)
        self.answered = []
        self.edited = []

    async def answer(self, text=None, show_alert=None):
        self.answered.append((text, show_alert))

    async def edit_text(self, text):
        self.edited.append(text)


@pytest.fixture
def clean_pending(monkeypatch):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {4242})
    monkeypatch.setattr(rem, "_remind_pending", rem.TtlDict())
    return rem._remind_pending


def _future_ts(minutes: int = 60) -> float:
    return time.time() + minutes * 60


def _future_hm(hours: int = 2) -> tuple[int, int, int]:
    now = datetime.now().astimezone()
    target = now + timedelta(hours=hours)
    return target.hour, target.minute, (target.date() - now.date()).days


# ---------- _is_reminder ----------


def test_is_reminder_keywords():
    for kw in rem.REMINDER_KEYWORDS:
        assert rem._is_reminder(f" {kw} в 10:00 ")
    assert not rem._is_reminder("просто текст")
    assert not rem._is_reminder("")


def test_is_reminder_case_insensitive():
    assert rem._is_reminder("Напомни мне")

# ---------- _parse_time_description ----------


def test_parse_time_description_today():
    from datetime import datetime

    now = datetime.now()
    ts = rem._parse_time_description(now.hour, now.minute, 0)
    assert abs(ts - now.replace(second=0, microsecond=0).timestamp()) < 2


def test_parse_time_description_with_offset():
    from datetime import datetime

    now = datetime.now()
    ts = rem._parse_time_description(now.hour, now.minute, 2)
    expected = now.replace(second=0, microsecond=0).timestamp() + 2 * 86400
    assert abs(ts - expected) < 2


def test_reminder_datetimes_are_timezone_aware():
    assert rem._now_local().tzinfo is not None
    assert rem._local_dt(time.time()).tzinfo is not None


def test_is_past_boundary():
    assert rem._is_past(100.0, now_ts=100.0) is True
    assert rem._is_past(101.0, now_ts=100.0) is False


# ---------- _build_reminder_prompt ----------


def test_build_reminder_prompt_full():
    now = datetime(2026, 10, 30, 14, 5).astimezone()
    prompt = rem._build_reminder_prompt("завтра в 16:30 позвонить", now=now)

    assert "Ты — парсер напоминаний." in prompt
    assert "Сегодня: 2026-10-30 (пт)" in prompt
    assert "Сейчас: 14:05" in prompt
    assert "Извлеки из сообщения" in prompt
    assert "reminder_text" in prompt
    assert "Сообщение: завтра в 16:30 позвонить" in prompt


def test_build_reminder_prompt_time_only():
    now = datetime(2026, 10, 30, 14, 5).astimezone()
    prompt = rem._build_reminder_prompt("в 16:30", time_only=True, now=now)

    assert "Сегодня: 2026-10-30 (пт)" in prompt
    assert "Сейчас: 14:05" in prompt
    assert "Определи время из сообщения" in prompt
    assert "reminder_text" not in prompt
    assert "Сообщение: в 16:30" in prompt


# ---------- _parse_reminder ----------


@pytest.mark.asyncio
async def test_parse_reminder_fenced_json(monkeypatch):
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("o", "m"))
    monkeypatch.setattr(
        "services.ai_engine.get_ai_response_async",
        _make_async(
            '```json\n{"reminder_text": "позвонить", "hour": 16, '
            '"minute": 30, "day_offset": 1, "time_description": "завтра"}\n```',
        ),
    )

    parsed = await rem._parse_reminder("завтра в 16:30 позвонить")

    assert parsed["reminder_text"] == "позвонить"
    assert "unix_timestamp" in parsed


@pytest.mark.asyncio
async def test_parse_reminder_invalid_json_returns_empty(monkeypatch, caplog):
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("o", "m"))
    monkeypatch.setattr(
        "services.ai_engine.get_ai_response_async",
        _make_async("не json"),
    )

    assert await rem._parse_reminder("завтра") == {}
    assert "failed to parse JSON" in caplog.text


@pytest.mark.asyncio
async def test_parse_reminder_empty_response_returns_empty(monkeypatch, caplog):
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("o", "m"))
    monkeypatch.setattr(
        "services.ai_engine.get_ai_response_async",
        _make_async(""),
    )

    assert await rem._parse_reminder("завтра") == {}
    assert "failed to parse JSON (length=0)" in caplog.text


@pytest.mark.asyncio
async def test_parse_reminder_full(monkeypatch):
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("ollama", "qwen"))
    monkeypatch.setattr(
        "services.ai_engine.get_ai_response_async",
        _make_async(_json({"reminder_text": "позвонить маме", "hour": 16, "minute": 30,
                          "day_offset": 1, "time_description": "завтра в 16:30"})),
    )
    parsed = await rem._parse_reminder("завтра в 16:30 позвонить маме")
    assert parsed["reminder_text"] == "позвонить маме"
    assert "unix_timestamp" in parsed


@pytest.mark.asyncio
async def test_parse_reminder_no_time(monkeypatch):
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("o", "m"))
    monkeypatch.setattr(
        "services.ai_engine.get_ai_response_async",
        _make_async(_json({"reminder_text": "купить хлеб", "hour": None, "minute": None,
                          "day_offset": 0, "time_description": ""})),
    )
    parsed = await rem._parse_reminder("купить хлеб")
    assert parsed["reminder_text"] == "купить хлеб"
    assert "unix_timestamp" not in parsed


def _json(d):
    return json.dumps(d)


def _make_async(value):
    async def _inner(*a, **kw):
        return value

    return _inner


# ---------- detect_reminder ----------


@pytest.mark.asyncio
async def test_detect_reminder_not_reminder_raises_skip(clean_pending, monkeypatch):
    msg = FakeMessage(4242, text="просто текст")
    with pytest.raises(Exception):
        await rem.detect_reminder(msg)


@pytest.mark.asyncio
async def test_detect_reminder_full_flow(clean_pending, monkeypatch):
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("o", "m"))
    hour, minute, day_offset = _future_hm()

    async def fake_ai(*a, **kw):
        return _json({"reminder_text": "позвонить", "hour": hour, "minute": minute,
                     "day_offset": day_offset, "time_description": "в будущем"})

    monkeypatch.setattr("services.ai_engine.get_ai_response_async", fake_ai)
    msg = FakeMessage(4242, text="напомни позвонить в 10:00")
    await rem.detect_reminder(msg)
    assert clean_pending[4242]["step"] == "confirm"
    assert msg.answers[0][0].startswith("📅")


@pytest.mark.asyncio
async def test_detect_reminder_ask_text(clean_pending, monkeypatch):
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("o", "m"))
    hour, minute, day_offset = _future_hm()
    monkeypatch.setattr(
        "services.ai_engine.get_ai_response_async",
        _make_async(_json({"reminder_text": None, "hour": hour, "minute": minute,
                          "day_offset": day_offset, "time_description": "в будущем"})),
    )
    msg = FakeMessage(4242, text="напомни в 9 утра")
    await rem.detect_reminder(msg)
    assert clean_pending[4242]["step"] == "ask_text"
    assert "О чём напомнить" in msg.answers[0][0]


@pytest.mark.asyncio
async def test_detect_reminder_ask_time(clean_pending, monkeypatch):
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("o", "m"))
    monkeypatch.setattr(
        "services.ai_engine.get_ai_response_async",
        _make_async(_json({"reminder_text": "позвонить", "hour": None, "minute": None,
                          "day_offset": 0, "time_description": ""})),
    )
    msg = FakeMessage(4242, text="напомни позвонить")
    await rem.detect_reminder(msg)
    assert clean_pending[4242]["step"] == "ask_time"
    assert "Когда напомнить" in msg.answers[0][0]


@pytest.mark.asyncio
async def test_detect_reminder_ask_all(clean_pending, monkeypatch):
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("o", "m"))
    monkeypatch.setattr(
        "services.ai_engine.get_ai_response_async",
        _make_async(_json({"reminder_text": None, "hour": None, "minute": None,
                          "day_offset": 0, "time_description": ""})),
    )
    msg = FakeMessage(4242, text="напомни")
    await rem.detect_reminder(msg)
    assert clean_pending[4242]["step"] == "ask_all"
    assert "Создание напоминания" in msg.answers[0][0]


@pytest.mark.asyncio
async def test_detect_reminder_parse_error(clean_pending, monkeypatch):
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("o", "m"))

    async def boom(*a, **kw):
        raise RuntimeError("ai down")

    monkeypatch.setattr("services.ai_engine.get_ai_response_async", boom)
    msg = FakeMessage(4242, text="напомни")
    await rem.detect_reminder(msg)
    assert clean_pending[4242]["step"] == "ask_all"


@pytest.mark.asyncio
async def test_detect_reminder_past_time_rejected(clean_pending, monkeypatch):
    fixed = datetime(2026, 10, 25, 12, 0).astimezone()
    monkeypatch.setattr(rem, "_now_local", lambda: fixed)
    monkeypatch.setattr(rem.time, "time", lambda: fixed.timestamp())
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("o", "m"))
    monkeypatch.setattr(
        "services.ai_engine.get_ai_response_async",
        _make_async(_json({
            "reminder_text": "позвонить", "hour": 10, "minute": 0,
            "day_offset": 0, "time_description": "в 10:00",
        })),
    )
    msg = FakeMessage(4242, text="напомни в 10:00 позвонить")
    await rem.detect_reminder(msg)
    assert 4242 not in clean_pending
    assert rem.PAST_TIME_TEXT in msg.answers[0][0]


# ---------- cb_remind_confirm ----------


@pytest.mark.asyncio
async def test_cb_remind_confirm_asks_target(clean_pending, monkeypatch):
    """rem_yes теперь спрашивает, куда сохранить (бот/календарь/оба)."""
    clean_pending[4242] = {"text": "текст", "ts": _future_ts(), "step": "confirm"}
    cb = FakeCb(4242)
    await rem.cb_remind_confirm(cb)
    assert cb.answered == [(None, None)]
    assert "Где сохранить" in cb.message.edits[-1]
    texts = [b.text for r in cb.message.last_markup.inline_keyboard for b in r]
    assert "⏰ В бот" in texts
    assert "📅 Apple Calendar" in texts
    assert "⚡ В оба" in texts
    assert 4242 in clean_pending  # данные ждут выбора цели


@pytest.mark.asyncio
async def test_cb_remind_confirm_no_session(clean_pending):
    cb = FakeCb(4242)
    await rem.cb_remind_confirm(cb)
    assert cb.message.edits == ["❌ Сессия истекла."]


@pytest.mark.asyncio
async def test_cb_remind_confirm_missing_data(clean_pending):
    clean_pending[4242] = {"step": "confirm"}
    cb = FakeCb(4242)
    await rem.cb_remind_confirm(cb)
    assert cb.message.edits == ["❌ Ошибка: не хватает данных."]


@pytest.mark.asyncio
async def test_cb_remind_confirm_rejects_stale_past_time(clean_pending):
    clean_pending[4242] = {
        "text": "текст", "ts": time.time() - 60, "step": "confirm",
    }
    cb = FakeCb(4242)
    await rem.cb_remind_confirm(cb)
    assert cb.message.edits == [rem.PAST_TIME_TEXT]
    assert 4242 not in clean_pending


# ---------- cb_remind_target ----------


class FakeKV:
    def __init__(self):
        self.stored = []

    def set(self, key, data, namespace=None, ttl=None):
        self.stored.append((key, data, namespace, ttl))


@pytest.mark.asyncio
async def test_cb_remind_target_bot(clean_pending, monkeypatch):
    fake_kv = FakeKV()
    monkeypatch.setattr(rem, "get_kv_store", lambda: fake_kv)
    called = {}
    monkeypatch.setattr(
        "services.apple_calendar.create_calendar_event",
        lambda *a, **k: called.setdefault("x", 1),
    )
    clean_pending[4242] = {"text": "текст", "ts": _future_ts(), "step": "confirm"}
    cb = FakeCb(4242)
    cb.data = "rem_tgt:bot"
    await rem.cb_remind_target(cb)
    assert len(fake_kv.stored) == 1
    assert fake_kv.stored[0][1]["text"] == "текст"
    assert fake_kv.stored[0][2] == "reminders"
    assert "x" not in called
    assert "Бот:" in cb.message.edits[-1]


@pytest.mark.asyncio
async def test_cb_remind_target_cal(clean_pending, monkeypatch):
    fake_kv = FakeKV()
    monkeypatch.setattr(rem, "get_kv_store", lambda: fake_kv)
    created = {}

    def fake_create(title, start_ts, duration_minutes=15, notes=""):
        created["id"] = title
        return "EVENT-ID-123"

    monkeypatch.setattr("services.apple_calendar.create_calendar_event", fake_create)
    clean_pending[4242] = {"text": "текст", "ts": _future_ts(), "step": "confirm"}
    cb = FakeCb(4242)
    cb.data = "rem_tgt:cal"
    await rem.cb_remind_target(cb)
    assert created["id"] == "текст"
    assert fake_kv.stored == []
    assert "Apple Calendar:" in cb.message.edits[-1] and "✅" in cb.message.edits[-1]


@pytest.mark.asyncio
async def test_cb_remind_target_both(clean_pending, monkeypatch):
    fake_kv = FakeKV()
    monkeypatch.setattr(rem, "get_kv_store", lambda: fake_kv)
    created = {}

    def fake_create(title, start_ts, duration_minutes=15, notes=""):
        created["id"] = title
        return "EVENT-ID-456"

    monkeypatch.setattr("services.apple_calendar.create_calendar_event", fake_create)
    clean_pending[4242] = {"text": "текст", "ts": _future_ts(), "step": "confirm"}
    cb = FakeCb(4242)
    cb.data = "rem_tgt:both"
    await rem.cb_remind_target(cb)
    assert len(fake_kv.stored) == 1
    assert created["id"] == "текст"
    text = cb.message.edits[-1]
    assert "Бот:" in text and "Apple Calendar:" in text and "✅" in text


@pytest.mark.asyncio
async def test_cb_remind_target_cal_error_still_saves_bot(clean_pending, monkeypatch):
    """Ошибка календаря не роняет сохранение в бот (для both)."""
    fake_kv = FakeKV()
    monkeypatch.setattr(rem, "get_kv_store", lambda: fake_kv)

    def fake_create(title, start_ts, duration_minutes=15, notes=""):
        raise RuntimeError("TCC denied")

    monkeypatch.setattr("services.apple_calendar.create_calendar_event", fake_create)
    clean_pending[4242] = {"text": "текст", "ts": _future_ts(), "step": "confirm"}
    cb = FakeCb(4242)
    cb.data = "rem_tgt:both"
    await rem.cb_remind_target(cb)
    assert len(fake_kv.stored) == 1
    text = cb.message.edits[-1]
    assert "Бот:" in text and "✅" in text
    assert "Apple Calendar:" in text and "❌" in text
    assert "TCC denied" in text


@pytest.mark.asyncio
async def test_cb_remind_target_no_session(clean_pending):
    cb = FakeCb(4242)
    cb.data = "rem_tgt:bot"
    await rem.cb_remind_target(cb)
    assert cb.message.edits == ["❌ Сессия истекла."]


@pytest.mark.asyncio
async def test_cb_remind_target_missing_data(clean_pending):
    clean_pending[4242] = {"step": "confirm"}
    cb = FakeCb(4242)
    cb.data = "rem_tgt:bot"
    await rem.cb_remind_target(cb)
    assert cb.message.edits == ["❌ Ошибка: не хватает данных."]


@pytest.mark.asyncio
async def test_cb_remind_target_rejects_past_time(clean_pending, monkeypatch):
    fake_kv = FakeKV()
    monkeypatch.setattr(rem, "get_kv_store", lambda: fake_kv)
    clean_pending[4242] = {
        "text": "текст", "ts": time.time() - 60, "step": "confirm",
    }
    cb = FakeCb(4242)
    cb.data = "rem_tgt:bot"
    await rem.cb_remind_target(cb)
    assert fake_kv.stored == []
    assert cb.message.edits == [rem.PAST_TIME_TEXT]
    assert 4242 not in clean_pending


@pytest.mark.asyncio
async def test_cb_remind_target_keys_unique_within_same_second(
    clean_pending, monkeypatch,
):
    fake_kv = FakeKV()
    monkeypatch.setattr(rem, "get_kv_store", lambda: fake_kv)
    fixed = 1_700_000_000.0
    monkeypatch.setattr(rem.time, "time", lambda: fixed)
    future_ts = fixed + 3600

    for _ in range(2):
        clean_pending[4242] = {
            "text": "два напоминания", "ts": future_ts, "step": "confirm",
        }
        cb = FakeCb(4242)
        cb.data = "rem_tgt:bot"
        await rem.cb_remind_target(cb)

    keys = [entry[0] for entry in fake_kv.stored]
    assert len(keys) == 2
    assert keys[0] != keys[1]


# ---------- cb_remind_cancel ----------


@pytest.mark.asyncio
async def test_cb_remind_cancel(clean_pending):
    clean_pending[4242] = {"text": "x", "ts": 1, "step": "confirm"}
    cb = FakeCb(4242)
    await rem.cb_remind_cancel(cb)
    assert cb.answered == [(None, None)]
    assert 4242 not in clean_pending
    assert cb.message.edits == ["❌ Напоминание отменено."]


@pytest.mark.asyncio
async def test_cb_remind_cancel_no_session(clean_pending):
    cb = FakeCb(4242)
    await rem.cb_remind_cancel(cb)
    assert cb.message.edits == ["❌ Напоминание отменено."]


# ---------- handle_reminder_text ----------


@pytest.mark.asyncio
async def test_handle_reminder_text_no_pending(clean_pending):
    reply = []
    res = await rem.handle_reminder_text(4242, "время", _reply(reply))
    assert res is False
    assert reply == []


@pytest.mark.asyncio
async def test_handle_reminder_text_ask_text(clean_pending):
    clean_pending[4242] = {"ts": _future_ts(), "step": "ask_text"}
    reply = []
    res = await rem.handle_reminder_text(4242, "позвонить", _reply(reply))
    assert res is True
    assert clean_pending[4242]["step"] == "confirm"
    assert "Напомнить" in reply[0][0]


@pytest.mark.asyncio
async def test_handle_reminder_text_ask_text_rejects_stale_past_time(clean_pending):
    clean_pending[4242] = {"ts": time.time() - 60, "step": "ask_text"}
    reply = []
    res = await rem.handle_reminder_text(4242, "позвонить", _reply(reply))
    assert res is True
    assert 4242 not in clean_pending
    assert reply[0][0] == rem.PAST_TIME_TEXT


@pytest.mark.asyncio
async def test_handle_reminder_text_ask_time_success(clean_pending, monkeypatch):
    clean_pending[4242] = {"text": "позвонить", "step": "ask_time"}
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("o", "m"))
    hour, minute, day_offset = _future_hm()
    monkeypatch.setattr(
        "services.ai_engine.get_ai_response_async",
        _make_async(_json({
            "hour": hour, "minute": minute, "day_offset": day_offset,
            "time_description": "в будущем",
        })),
    )
    reply = []
    res = await rem.handle_reminder_text(4242, "в 10:00", _reply(reply))
    assert res is True
    assert clean_pending[4242]["step"] == "confirm"
    assert "Напомнить" in reply[0][0]


@pytest.mark.asyncio
async def test_handle_reminder_text_ask_time_fenced_json(clean_pending, monkeypatch):
    clean_pending[4242] = {"text": "позвонить", "step": "ask_time"}
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("o", "m"))
    hour, minute, day_offset = _future_hm()
    payload = _json({
        "hour": hour, "minute": minute, "day_offset": day_offset,
        "time_description": "в будущем",
    })
    monkeypatch.setattr(
        "services.ai_engine.get_ai_response_async",
        _make_async(f"```json\n{payload}\n```"),
    )
    reply = []
    res = await rem.handle_reminder_text(4242, "в 10:00", _reply(reply))
    assert res is True
    assert clean_pending[4242]["step"] == "confirm"
    assert "Напомнить" in reply[0][0]


@pytest.mark.asyncio
async def test_handle_reminder_text_ask_time_empty_response(
    clean_pending, monkeypatch, caplog,
):
    clean_pending[4242] = {"text": "позвонить", "step": "ask_time"}
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("o", "m"))
    monkeypatch.setattr(
        "services.ai_engine.get_ai_response_async",
        _make_async(""),
    )
    reply = []
    res = await rem.handle_reminder_text(4242, "в 10:00", _reply(reply))
    assert res is True
    assert 4242 not in clean_pending
    assert "Не удалось определить время" in reply[0][0]
    assert "failed to parse JSON (length=0)" in caplog.text


@pytest.mark.asyncio
async def test_handle_reminder_text_ask_time_past_rejected(
    clean_pending, monkeypatch,
):
    fixed = datetime(2026, 10, 25, 12, 0).astimezone()
    monkeypatch.setattr(rem, "_now_local", lambda: fixed)
    monkeypatch.setattr(rem.time, "time", lambda: fixed.timestamp())
    clean_pending[4242] = {"text": "позвонить", "step": "ask_time"}
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("o", "m"))
    monkeypatch.setattr(
        "services.ai_engine.get_ai_response_async",
        _make_async(_json({
            "hour": 10, "minute": 0, "day_offset": 0,
            "time_description": "в 10:00",
        })),
    )
    reply = []
    res = await rem.handle_reminder_text(4242, "в 10:00", _reply(reply))
    assert res is True
    assert 4242 not in clean_pending
    assert reply[0][0] == rem.PAST_TIME_TEXT


@pytest.mark.asyncio
async def test_handle_reminder_text_ask_time_failure(clean_pending, monkeypatch):
    clean_pending[4242] = {"text": "позвонить", "step": "ask_time"}
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("o", "m"))

    async def boom(*a, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr("services.ai_engine.get_ai_response_async", boom)
    reply = []
    res = await rem.handle_reminder_text(4242, "в 10:00", _reply(reply))
    assert res is True
    assert 4242 not in clean_pending
    assert "Не удалось определить время" in reply[0][0]


@pytest.mark.asyncio
async def test_handle_reminder_text_ask_time_bad_json(clean_pending, monkeypatch):
    clean_pending[4242] = {"text": "позвонить", "step": "ask_time"}
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("o", "m"))
    monkeypatch.setattr(
        "services.ai_engine.get_ai_response_async",
        _make_async("не json"),
    )
    reply = []
    res = await rem.handle_reminder_text(4242, "в 10:00", _reply(reply))
    assert res is True
    assert "Не удалось определить время" in reply[0][0]


@pytest.mark.asyncio
async def test_handle_reminder_text_ask_all_full(clean_pending, monkeypatch):
    clean_pending[4242] = {"step": "ask_all"}
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("o", "m"))
    monkeypatch.setattr(
        "services.ai_engine.get_ai_response_async",
        _make_async(_json({
            "reminder_text": "задача", "hour": 12, "minute": 0,
            "day_offset": 1, "time_description": "завтра",
        })),
    )
    reply = []
    res = await rem.handle_reminder_text(4242, "завтра в 12 задача", _reply(reply))
    assert res is True
    assert clean_pending[4242]["step"] == "confirm"


@pytest.mark.asyncio
async def test_handle_reminder_text_ask_all_time_only(clean_pending, monkeypatch):
    clean_pending[4242] = {"step": "ask_all"}
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("o", "m"))
    hour, minute, day_offset = _future_hm()
    monkeypatch.setattr(
        "services.ai_engine.get_ai_response_async",
        _make_async(_json({
            "reminder_text": None, "hour": hour, "minute": minute,
            "day_offset": day_offset, "time_description": "в будущем",
        })),
    )
    reply = []
    res = await rem.handle_reminder_text(4242, "в 12", _reply(reply))
    assert res is True
    assert clean_pending[4242]["step"] == "ask_text"


@pytest.mark.asyncio
async def test_handle_reminder_text_ask_all_text_only(clean_pending, monkeypatch):
    clean_pending[4242] = {"step": "ask_all"}
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("o", "m"))
    monkeypatch.setattr(
        "services.ai_engine.get_ai_response_async",
        _make_async(_json({
            "reminder_text": "задача", "hour": None, "minute": None,
            "day_offset": 0, "time_description": "",
        })),
    )
    reply = []
    res = await rem.handle_reminder_text(4242, "задача", _reply(reply))
    assert res is True
    assert clean_pending[4242]["step"] == "ask_time"


@pytest.mark.asyncio
async def test_handle_reminder_text_ask_all_unknown(clean_pending, monkeypatch):
    clean_pending[4242] = {"step": "ask_all"}
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("o", "m"))
    monkeypatch.setattr(
        "services.ai_engine.get_ai_response_async",
        _make_async(_json({"reminder_text": None, "hour": None, "minute": None,
                          "day_offset": 0, "time_description": ""})),
    )
    reply = []
    res = await rem.handle_reminder_text(4242, "???", _reply(reply))
    assert res is True
    assert 4242 not in clean_pending
    assert "Не удалось понять" in reply[0][0]


@pytest.mark.asyncio
async def test_handle_reminder_text_ask_all_past_rejected(
    clean_pending, monkeypatch,
):
    fixed = datetime(2026, 10, 25, 12, 0).astimezone()
    monkeypatch.setattr(rem, "_now_local", lambda: fixed)
    monkeypatch.setattr(rem.time, "time", lambda: fixed.timestamp())
    clean_pending[4242] = {"step": "ask_all"}
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("o", "m"))
    monkeypatch.setattr(
        "services.ai_engine.get_ai_response_async",
        _make_async(_json({
            "reminder_text": "позвонить", "hour": 10, "minute": 0,
            "day_offset": 0, "time_description": "в 10:00",
        })),
    )
    reply = []
    res = await rem.handle_reminder_text(4242, "в 10:00 позвонить", _reply(reply))
    assert res is True
    assert 4242 not in clean_pending
    assert reply[0][0] == rem.PAST_TIME_TEXT


@pytest.mark.asyncio
async def test_handle_reminder_text_ask_all_parse_error(
    clean_pending, monkeypatch, caplog,
):
    clean_pending[4242] = {"step": "ask_all"}
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("o", "m"))

    async def boom(*a, **kw):
        raise RuntimeError("ai down")

    monkeypatch.setattr("services.ai_engine.get_ai_response_async", boom)
    reply = []
    res = await rem.handle_reminder_text(4242, "завтра в 12", _reply(reply))
    assert res is True
    assert 4242 not in clean_pending
    assert "Не удалось разобрать" in reply[0][0]
    assert "ask_all parse failed" in caplog.text


@pytest.mark.asyncio
async def test_handle_reminder_text_ask_all_bad_json_fallback(
    clean_pending, monkeypatch, caplog,
):
    clean_pending[4242] = {"step": "ask_all"}
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("o", "m"))
    monkeypatch.setattr(
        "services.ai_engine.get_ai_response_async",
        _make_async("не json"),
    )
    reply = []
    res = await rem.handle_reminder_text(4242, "завтра в 12", _reply(reply))
    assert res is True
    assert 4242 not in clean_pending
    assert "Не удалось понять" in reply[0][0]
    assert "failed to parse JSON" in caplog.text


@pytest.mark.asyncio
async def test_handle_reminder_text_unknown_step_returns_false(clean_pending):
    clean_pending[4242] = {"step": "unknown_step_x"}
    reply = []
    res = await rem.handle_reminder_text(4242, "время", _reply(reply))
    assert res is False
    assert reply == []


def _reply(store):
    async def _inner(text, parse_mode=None, reply_markup=None):
        store.append((text, parse_mode, reply_markup))

    return _inner
