"""Шаги BDD для features/digest.feature.

Реализуют сценарии через реальный код services.digest с фейковыми
kv_store, ботом и источником KG-сводки (без живого MCP). Заметки
вчера — реальные файлы во временной папке с utime.
"""
import asyncio
import os
import tempfile
from datetime import datetime

from behave import given, then, when

import services.digest as dg
from services.kv_store import KVStore

REMINDER_NS = dg.REMINDER_NS


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class FakeBot:
    def __init__(self):
        self.sent = []
        self.fail = False

    async def send_message(self, chat_id, text, parse_mode=None):
        if self.fail:
            raise RuntimeError("telegram down")
        self.sent.append((chat_id, text))


def _now_at(hour: int, minute: int = 0) -> float:
    now = datetime.now()
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0).timestamp()


def _setup(context, now_ts):
    context.digest_now_ts = now_ts
    context.bot = FakeBot()
    context.kv = KVStore(db_path=os.path.join(context.tmpdir, "digest_bdd.sqlite"))
    dg.get_kv_store = lambda: context.kv
    dg.collect_yesterday_notes = _notes_with_dir(context)
    dg.collect_kg_summary = _kg_summary(context)


def _notes_with_dir(context):
    original = dg.collect_yesterday_notes

    def impl(now_ts=None, notes_dir=None):
        return original(now_ts=now_ts, notes_dir=context.notes_dir)

    return impl


def _kg_summary(context):
    def impl(mcp_cb=None):
        async def _out():
            return {"entities": context.kg_entities}

        return _out()

    return impl


# ─── Given ───

@given("сейчас {hour:d}:{minute:d} утра")
def given_now(context, hour, minute):
    context.tmpdir = tempfile.mkdtemp(prefix="digest_bdd_")
    context.notes_dir = os.path.join(context.tmpdir, "my_notes")
    os.makedirs(context.notes_dir, exist_ok=True)
    context.kg_entities = 0
    _setup(context, _now_at(hour, minute))


@given('есть напоминание на сегодня в {hour:d}:{minute:d} в чате {chat:d}')
def given_reminder_today(context, hour, minute, chat):
    ts = _now_at(hour, minute)
    context.kv.set(
        f"rem_{chat}_{hour}{minute}",
        {"remind_at": ts, "text": "позвонить маме", "chat_id": chat},
        namespace=REMINDER_NS,
    )


@given('есть напоминание ровно в 00:00 сегодня в чате {chat:d}')
def given_reminder_midnight(context, chat):
    start, _ = dg._day_bounds(context.digest_now_ts)
    context.kv.set(
        "rem_midnight",
        {"remind_at": start, "text": "полночь", "chat_id": chat},
        namespace=REMINDER_NS,
    )


@given('вчера была изменена заметка "{name}"')
def given_yesterday_note(context, name):
    y_start, _ = dg._yesterday_bounds(context.digest_now_ts)
    path = os.path.join(context.notes_dir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write("текст заметки")
    os.utime(path, (y_start + 3600, y_start + 3600))


@given("граф знаний содержит {n:d} сущности")
def given_kg_entities(context, n):
    context.kg_entities = n


@given("нет напоминаний и вчерашних заметок")
def given_empty_day(context):
    pass


@given("Telegram не отвечает")
def given_telegram_down(context):
    context.bot.fail = True


# ─── When ───

@when("пользователь отправляет команду /дайджест в чат {chat:d}")
def when_manual_digest(context, chat):
    context.result = _run(
        dg.send_digest_to_chat(context.bot, chat, context.digest_now_ts, kv=context.kv),
    )


@when("планировщик проверяет ежедневный дайджест")
def when_scheduler_check(context):
    context.result = _run(
        dg.maybe_send_daily_digest(context.bot, context.digest_now_ts, kv=context.kv),
    )


@when("планировщик снова проверяет ежедневный дайджест в 09:30")
def when_scheduler_check_again(context):
    context.result = _run(
        dg.maybe_send_daily_digest(context.bot, _now_at(9, 30), kv=context.kv),
    )


# ─── Then ───

@then("бот отправляет дайджест в чат {chat:d}")
def then_digest_sent(context, chat):
    assert context.result is True
    assert context.bot.sent, "дайджест не отправлен"
    assert context.bot.sent[0][0] == chat


@then('в дайджесте есть блок "{block}"')
def then_block_present(context, block):
    text = context.bot.sent[0][1]
    assert block in text


@then("в дайджесте есть сводка графа знаний")
def then_kg_block(context):
    text = context.bot.sent[0][1]
    assert "Граф знаний" in text
    assert "3" in text


@then("дайджест не отправляется")
def then_not_sent(context):
    assert context.bot.sent == []


@then("дайджест отправлен ровно 1 раз")
def then_sent_once(context):
    assert len(context.bot.sent) == 1


@then("дайджест не отправляется повторно")
def then_not_resent(context):
    assert len(context.bot.sent) == 1


@then("ошибка залогирована, дайджест отмечен отправленным")
def then_error_logged_and_marked(context):
    assert context.bot.sent == []
    assert context.kv.get(dg.LAST_SEND_KEY, namespace=dg.DIGEST_NS) is not None


@then('бот отвечает "Всё чисто" и ничего не отправляет')
def then_empty_reply(context):
    assert context.result is False
    assert context.bot.sent == []


@then("в дайджесте есть напоминание на 00:00")
def then_midnight_present(context):
    text = context.bot.sent[0][1]
    assert "00:00" in text
    assert "полночь" in text
