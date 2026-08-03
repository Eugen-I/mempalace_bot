"""Шаги BDD для действий с транскриптами."""
import asyncio
import os
import shutil

from behave import given, then, when

import handlers.transkript as tr

TEST_UID = 424242
TMP_DIR = os.path.join(os.path.dirname(__file__), "..", "_behave_tr")
TMP_FILE = os.path.join(TMP_DIR, "test_tr.txt")
TMP_CONTENT = "Это тестовый транскрипт. Говорится о квантах и о памяти."

state = {}


def _run(coro):
    return asyncio.run(coro)


def _reset():
    state.clear()
    tr._tr_content_cache.clear()
    tr._tr_ai_waiting.clear()
    tr._tr_last_question.clear()
    if os.path.isdir(TMP_DIR):
        shutil.rmtree(TMP_DIR)
    os.makedirs(TMP_DIR)
    with open(TMP_FILE, "w", encoding="utf-8") as f:
        f.write(TMP_CONTENT)
    tr.TRANSKRIPT_DIR = TMP_DIR


def _open_file():
    _reset()
    tr._tr_content_cache[TEST_UID] = {
        "pages": [TMP_CONTENT], "total": 1, "idx": 0,
        "fname": "test_tr.txt", "dt": "01.01.2026 00:00",
    }


class Msg:
    def __init__(self):
        self.edited = []
        self.markups = []
        self.from_user = type("U", (), {"id": TEST_UID})()

    async def answer(self, text=None, **kwargs):
        self.edited.append(text or "")
        self.markups.append(kwargs.get("reply_markup"))
        return self

    async def edit_text(self, text, **kwargs):
        self.edited.append(text)
        self.markups.append(kwargs.get("reply_markup"))
        return self


class Cb:
    def __init__(self, data, msg=None):
        self.data = data
        self.message = msg or Msg()
        self.from_user = type("U", (), {"id": TEST_UID})()

    async def answer(self, text=None, **kwargs):
        pass


# ─── Given ───

@given('открыт транскрипт «test_tr.txt»')
def step_open(context):
    _open_file()


@given("вопрос ещё не задавался")
def step_no_question(context):
    _open_file()
    tr._tr_last_question.clear()


@given("сессия истекла")
def step_expired(context):
    _reset()


# ─── Удаление ───

@when('пользователь нажимает «🗑️ Удалить» и подтверждает')
def step_delete(context):
    msg = Msg()
    state["msg"] = msg
    _run(tr.cb_tr_del(Cb("tr_del", msg)))
    _run(tr.cb_tr_del_yes(Cb("tr_del_yes", msg)))


@then("файл удалён и бот подтверждает")
def step_deleted(context):
    assert not os.path.exists(TMP_FILE)
    assert any("удалён" in e.lower() for e in state["msg"].edited)


@then('бот сообщает «Сессия истекла»')
def step_expired_msg(context):
    assert any("Сессия истекла" in e for e in state["msg"].edited)


# ─── Обсудить с ИИ ───

@when('пользователь нажимает «🤖 Обсудить»')
def step_ai_prompt(context):
    msg = Msg()
    state["msg"] = msg
    _run(tr.cb_tr_ai(Cb("tr_ai", msg)))


@then("бот спрашивает вопрос")
def step_prompt_question(context):
    msg = state["msg"]
    assert any("Задайте вопрос" in e for e in msg.edited)


@when('пользователь отправляет вопрос «О чём это?»')
def step_ask_question(context):
    from unittest import mock

    def fake_ai(engine, model, messages):
        state["messages"] = messages
        return "Ответ ИИ."

    msg = state["msg"]
    fname = tr._tr_ai_waiting[TEST_UID]["fname"]
    with mock.patch("services.ai_engine._sync_ai_call", fake_ai), \
         mock.patch("services.ai_engine.get_current_ai", lambda: ("gemini", "g")):
        _run(tr.handle_tr_ai_question(TEST_UID, msg, fname, "О чём это?"))


@then("ответ получен от ИИ и содержит директиву русского языка")
def step_answer(context):
    assert any("Ответ ИИ" in e for e in state["msg"].edited)
    system = state["messages"][0]["content"]
    assert "Отвечай на русском языке" in system


# ─── Интернет ───

@when('пользователь нажимает «🌐 Интернет»')
def step_web(context):
    msg = Msg()
    state["msg"] = msg
    _run(tr.cb_tr_ai_web(Cb("tr_ai_web", msg)))


@then("бот просит сначала задать вопрос через «Обсудить»")
def step_web_prompt(context):
    assert any("Сначала задайте вопрос" in e for e in state["msg"].edited)


# ─── Сохранение в MemPalace ───

@when('пользователь нажимает «💾 В MemPalace»')
def step_save(context):
    from unittest import mock

    from handlers.palace import save as palace_save

    state["saved_text"] = ""

    def fake_state_put(uid, val):
        state["saved_text"] = val["text"]

    async def fake_wings(edit_func, uid):
        await edit_func("Выберите крыло:")

    msg = Msg()
    state["msg"] = msg
    cb = Cb("tr_save", msg)
    with mock.patch.object(palace_save, "_show_save_wings", fake_wings), \
         mock.patch.object(palace_save, "_save_state", {}):
        _run(tr.cb_tr_save(cb))
    state["shown"] = msg.edited
    state["saved_text"] = tr._get_content(TEST_UID)


@then("отображается выбор крыла")
def step_wings_shown(context):
    assert any("Выберите крыло" in e for e in state["shown"])


@then("состояние сохранения содержит полный текст транскрипта")
def step_save_content(context):
    assert "тестовый транскрипт" in state["saved_text"]


# ─── Кнопки действий ───

@then("видны кнопки: Обсудить, Интернет, Цитата, В MemPalace, Связи, Удалить")
def step_action_buttons_visible(context):
    msg = Msg()
    _run(tr._show_content_page(msg, TEST_UID, 0))
    labels = [b.text for row in msg.markups[0].inline_keyboard for b in row]
    for t in ["Обсудить", "Интернет", "Цитата", "В MemPalace", "связи", "Удалить"]:
        assert any(
            t in lbl or t.lower() in lbl.lower() for lbl in labels
        ), f"кнопка {t} отсутствует"
