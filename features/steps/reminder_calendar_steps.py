"""Шаги BDD для features/reminder_calendar.feature.

Реализуют сценарии через реальный код handlers.reminder (cb_remind_confirm,
cb_remind_target) с фейковыми kv_store, apple_calendar и Telegram-объектами.
"""
import asyncio

from behave import given, then, when

from handlers import reminder as rem


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeChat:
    def __init__(self, cid):
        self.id = cid


class FakeMessage:
    def __init__(self, uid):
        self.from_user = FakeUser(uid)
        self.chat = FakeChat(1)
        self.edits = []
        self.last_markup = None

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)
        self.last_markup = reply_markup


class FakeCb:
    def __init__(self, uid, data):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = FakeMessage(uid)
        self.answered = []

    async def answer(self, text=None, show_alert=None):
        self.answered.append((text, show_alert))


class FakeKV:
    def __init__(self):
        self.stored = []

    def set(self, key, data, namespace=None, ttl=None):
        self.stored.append((key, data, namespace, ttl))


TARGETS = {"⏰ В бот": "rem_tgt:bot",
           "📅 Apple Calendar": "rem_tgt:cal",
           "⚡ В оба": "rem_tgt:both"}


def _text_of(cb) -> str:
    return "\n".join(cb.message.edits)


# ─── Given ───

@given('пользователь подтвердил напоминание "{text}" на {time_desc}')
def given_confirmed_reminder(context, text, time_desc):
    from datetime import datetime, timedelta

    hour, minute = (18, 0) if time_desc.startswith("сегодня 18") else (15, 0)
    if time_desc.startswith("завтра"):
        dt = datetime.now() + timedelta(days=1)
    else:
        dt = datetime.now()
    ts = dt.replace(hour=hour, minute=minute, second=0, microsecond=0).timestamp()
    context.uid = 424242
    context.pending_text = text
    rem._remind_pending[context.uid] = {"text": text, "ts": ts, "step": "confirm"}
    context.kv = FakeKV()
    rem.get_kv_store = lambda: context.kv

    context.created = []

    def fake_create(title, start_ts, duration_minutes=15, notes=""):
        context.created.append((title, start_ts, notes))
        return "EVENT-ID"

    import services.apple_calendar as cal_mod

    cal_mod.create_calendar_event = fake_create


@given('Apple Calendar отвечает ошибкой "{err}"')
def given_calendar_error(context, err):
    def boom(title, start_ts, duration_minutes=15, notes=""):
        raise RuntimeError(err)

    import services.apple_calendar as cal_mod

    cal_mod.create_calendar_event = boom


@given('пользователь нажал "✅ Да" без активной сессии')
def given_yes_no_session(context):
    context.uid = 424242
    rem._remind_pending.clear()


@given("пользователь выбрал цель после истечения TTL")
def given_target_expired(context):
    context.uid = 424242
    rem._remind_pending.clear()


# ─── When ───

@when('он выбирает цель "{choice}"')
def when_choose_target(context, choice):
    cb = FakeCb(context.uid, TARGETS[choice])
    _run(rem.cb_remind_target(cb))
    context.cb = cb


# ─── Then ───

@then("напоминание сохранено в kv_store с user_id и remind_at")
def then_kv_saved(context):
    assert len(context.kv.stored) == 1
    _key, data, ns, _ttl = context.kv.stored[0]
    assert data["user_id"] == context.uid
    assert data["remind_at"] > 0
    assert ns == "reminders"


@then("напоминание сохранено в kv_store")
def then_kv_saved_simple(context):
    assert len(context.kv.stored) == 1


@then("событие в Apple Calendar не создаётся")
def then_cal_not_called(context):
    assert context.created == []


@then('пользователь видит "Бот: ✅"')
def then_bot_ok(context):
    assert "Бот:" in _text_of(context.cb)
    assert "✅" in _text_of(context.cb)


@then("событие создано в календаре с текстом напоминания")
def then_cal_created_with_text(context):
    assert len(context.created) == 1
    title, _ts, _notes = context.created[0]
    assert title == context.pending_text


@then("событие создано в календаре")
def then_cal_created(context):
    assert len(context.created) == 1


@then("в kv_store ничего не сохранено")
def then_kv_empty(context):
    assert context.kv.stored == []


@then('пользователь видит "Apple Calendar: ✅"')
def then_cal_ok(context):
    assert "Apple Calendar:" in _text_of(context.cb)
    assert "✅" in _text_of(context.cb)


@then('пользователь видит и "Бот: ✅" и "Apple Calendar: ✅"')
def then_both_ok(context):
    text = _text_of(context.cb)
    assert "Бот:" in text and "Apple Calendar:" in text and "✅" in text


@then('пользователь видит "Apple Calendar: ❌" с текстом ошибки')
def then_cal_error_shown(context):
    text = _text_of(context.cb)
    assert "Apple Calendar:" in text and "❌" in text
    assert "TCC denied" in text


@then('он видит "Сессия истекла"')
def then_session_expired(context):
    cb = FakeCb(context.uid, "rem_tgt:bot")
    _run(rem.cb_remind_target(cb))
    assert "Сессия истекла" in "\n".join(cb.message.edits)
