"""Шаги BDD для features/reflection.feature.

Реализуют сценарии через реальный код services.reflection и
handlers.brainstorm (maybe_ask_reflection, cb_reflect_skip) с
фейковыми сообщениями и kv_store.
"""
import asyncio
import os
import tempfile

from behave import given, then, when

import config
from handlers import brainstorm as h
from services.kv_store import KVStore
from services.reflection import (
    MAX_THEME_LEN,
    REFLECTION_NS,
    save_reflection_answer,
)

config.ALLOWED_IDS = {424242}


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class FakeMsg:
    def __init__(self):
        self.answers = []
        self.edits = []

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append(text)
        return self

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)


class FakeCb:
    def __init__(self, data):
        self.from_user = type("U", (), {"id": 424242})()
        self.data = data
        self.message = FakeMsg()
        self.answered = []

    async def answer(self, text=None, show_alert=None):
        self.answered.append(text)


def _setup(context):
    context.tmpdir = tempfile.mkdtemp(prefix="reflection_bdd_")
    context.kv = KVStore(db_path=os.path.join(context.tmpdir, "reflection.sqlite"))
    h._reflection_data.clear()
    h._reflection_waiting.clear()
    context.msg = FakeMsg()
    context.answered_text = None


@given('идеи штурма по теме "{theme}" сохранены в Дворец')
def given_idea_saved(context, theme):
    _setup(context)
    h._reflection_data[424242] = {
        "theme": theme,
        "ideas_count": 3,
    }


@given("нет активного штурма")
def given_no_storm(context):
    _setup(context)


@given('идеи штурма по теме из {n:d} символов сохранены в Дворец')
def given_long_theme(context, n):
    _setup(context)
    h._reflection_data[424242] = {
        "theme": "Т" * n,
        "ideas_count": 1,
    }


@given("сохранение в Дворец падает с ошибкой")
def given_save_fails(context):
    context.save_fail = True


@when("пользователь подтверждает сохранение в Дворец")
def when_confirm_save(context):
    from handlers.palace import save as palace_save

    palace_save._save_state[424242] = {
        "text": "идея штурма", "wing": "крыло", "room": "комната", "mode": "full",
    }

    class FakeMCP:
        async def call_tool(self, name, params=None):
            raise RuntimeError("mcp упал")

    palace_save.get_mcp = lambda: FakeMCP()
    context.palace_cb = FakeCb("p_sv_c")
    _run(palace_save.cb_save_confirm_execute(context.palace_cb))


@then("сохранение показало ошибку")
def then_save_error(context):
    assert any("Ошибка сохранения" in e for e in context.palace_cb.message.edits)


@then("вопрос рефлексии не задан")
def then_reflection_not_asked(context):
    assert context.palace_cb.message.answers == []


@when("бот задаёт вопрос рефлексии")
def when_ask(context):
    context.asked = _run(h.maybe_ask_reflection(424242, context.msg.answer))


@when("бот проверяет необходимость вопроса рефлексии")
def when_check(context):
    context.asked = _run(h.maybe_ask_reflection(424242, context.msg.answer))


@when('пользователь отвечает "{answer}"')
def when_answer(context, answer):
    context.answered_text = save_reflection_answer(
        context.kv, 424242, "Сны", answer,
    )


@when('пользователь нажимает "Пропустить"')
def when_skip(context):
    cb = FakeCb("bs_reflect_skip")
    _run(h.cb_reflect_skip(cb))
    context.msg.edits = cb.message.edits


@then('вопрос содержит тему "{theme}" и просьбу назвать самую сильную идею')
def then_question_content(context, theme):
    text = context.msg.answers[-1]
    assert theme in text
    assert "самой сильной" in text
    assert context.asked is True


@then("вопрос не задан")
def then_not_asked(context):
    assert context.asked is False
    assert context.msg.answers == []


@then('ответ сохранён в журнале рефлексий с темой "{theme}"')
def then_answer_saved(context, theme):
    keys = context.kv.keys(namespace=REFLECTION_NS)
    assert len(keys) == 1
    saved = context.kv.get(keys[0], namespace=REFLECTION_NS)
    assert saved["theme"] == theme
    assert "полёт" in saved["answer"]


@then('бот отвечает фрагментом "{fragment}"')
def then_user_sees(context, fragment):
    assert fragment in context.answered_text


@then("журнал рефлексий пуст")
def then_journal_empty(context):
    assert context.kv.keys(namespace=REFLECTION_NS) == []


@then("вопрос останется ждать следующего успешного сохранения")
def then_pending_kept(context):
    assert 424242 in h._reflection_data
    assert 424242 not in h._reflection_waiting


@then("рефлексия пропущена и ожидание ответа очищено")
def then_skipped(context):
    assert any("Рефлексия пропущена" in e for e in context.msg.edits)
    assert 424242 not in h._reflection_waiting
    assert 424242 not in h._reflection_data


@then("вопрос содержит не более {n:d} символов темы")
def then_theme_limited(context, n):
    text = context.msg.answers[-1]
    assert n == MAX_THEME_LEN
    assert ("Т" * (n + 1)) not in text
