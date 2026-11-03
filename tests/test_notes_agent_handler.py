"""Unit-тесты для handlers.notes_agent — агент Apple Notes.

Паттерн: happy path + негативные сценарии + граничные значения (BVA).
Подтверждения тестируются через реальные async-события: задача confirm_write
запускается в фоне, клики по кнопкам имитируются вызовом cb-хендлеров.
"""

import asyncio

import pytest

from handlers import notes_agent as na


class FakeUserLite:
    def __init__(self, uid):
        self.id = uid


class FakeStatus:
    """Статус-сообщение: и answer (карточки подтверждения), и edit_text."""

    def __init__(self):
        self.edits = []
        self.cards = []
        self.reply_markup = None

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.cards.append(text)
        self.reply_markup = reply_markup
        return self

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)


class FakeMessageLite:
    def __init__(self, uid=4242, text=""):
        self.from_user = FakeUserLite(uid)
        self.chat = type("Chat", (), {"id": 1})()
        self.text = text
        self.answers = []
        self.edits = []
        self.edits_reply_markup = None
        self.last_answer = None

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append(text)
        sent = FakeMessageLite(self.from_user.id)
        self.last_answer = sent
        return sent

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)
        self.edits_reply_markup = reply_markup


class FakeCbLite:
    def __init__(self, uid=4242, data=""):
        self.from_user = FakeUserLite(uid)
        self.data = data
        self.message = FakeMessageLite(uid)
        self.answered = []

    async def answer(self, text=None, show_alert=None):
        self.answered.append((text, show_alert))


@pytest.fixture(autouse=True)
def allow_user(monkeypatch):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {4242})


@pytest.fixture(autouse=True)
def clear_pending():
    na._pending_confirm.clear()
    na._waiting_for_notes_input.clear()
    na._notes_list_store.clear()
    na._notes_discuss_ctx.clear()
    na._notes_view_store.clear()
    yield
    na._pending_confirm.clear()
    na._waiting_for_notes_input.clear()
    na._notes_list_store.clear()
    na._notes_discuss_ctx.clear()
    na._notes_view_store.clear()


def _token_from(status: FakeStatus) -> str:
    """Извлекает токен подтверждения из reply_markup карточки."""
    kb = status.reply_markup
    for row in kb.inline_keyboard:
        for btn in row:
            if btn.callback_data.startswith("notes_confirm:"):
                return btn.callback_data.split(":", 1)[1]
    raise AssertionError("Кнопка подтверждения не найдена")


def _cancel_token_from(status: FakeStatus) -> str:
    kb = status.reply_markup
    for row in kb.inline_keyboard:
        for btn in row:
            if btn.callback_data.startswith("notes_cancel:"):
                return btn.callback_data.split(":", 1)[1]
    raise AssertionError("Кнопка отмены не найдена")


# ─── _describe_action: карточки подтверждения ───


def test_describe_create_card():
    text = na._describe_action("notes_create", {"title": "Идеи", "text": "Текст"})
    assert "Создать заметку" in text
    assert "Идеи" in text
    assert "Текст" in text


def test_describe_update_card():
    text = na._describe_action("notes_update", {"note_id": "A1", "append_text": "дозапись"})
    assert "Обновить заметку" in text
    assert "A1" in text
    assert "дозапись" in text


def test_describe_delete_card():
    text = na._describe_action("notes_delete", {"note_id": "B2"})
    assert "Удалить заметку" in text
    assert "B2" in text


def test_describe_move_card():
    text = na._describe_action("notes_move", {"note_id": "C3", "target_folder": "Фото"})
    assert "Переместить заметку" in text
    assert "Фото" in text
    assert "C3" in text


def test_describe_unknown_tool_fallback():
    text = na._describe_action("notes_warp", {"a": 1})
    assert "notes_warp" in text


def test_describe_escapes_html():
    text = na._describe_action(
        "notes_create", {"title": "<script>X</script>", "text": "<i>Y</i>"}
    )
    assert "<script>" not in text
    assert "&lt;script&gt;X&lt;/script&gt;" in text
    # Разрешённое форматирование сохраняется по контракту safe_html_format.
    assert "<i>Y</i>" in text


# ─── _note_title: best-effort поиск названия по ID ───


def test_note_title_empty_id_short_circuit(monkeypatch):
    import asyncio

    def boom(note_id):
        raise AssertionError("list_notes не должен вызываться для пустого id")

    monkeypatch.setattr("services.apple_notes.list_notes", boom)
    assert asyncio.run(na._note_title("")) == ""


def test_note_title_found_in_index(monkeypatch):
    import asyncio

    monkeypatch.setattr(
        "services.apple_notes.list_notes",
        lambda: [{"id": "AAA", "name": "Идеи"}, {"id": "BBB", "name": "Другое"}],
    )
    assert asyncio.run(na._note_title("BBB")) == "Другое"


def test_note_title_unknown_id(monkeypatch):
    import asyncio

    monkeypatch.setattr("services.apple_notes.list_notes", lambda: [{"id": "AAA"}])
    assert asyncio.run(na._note_title("ZZZ")) == ""


def test_note_title_failure_returns_empty(monkeypatch):
    import asyncio

    def boom():
        raise RuntimeError("osascript down")

    monkeypatch.setattr("services.apple_notes.list_notes", boom)
    assert asyncio.run(na._note_title("AAA")) == ""


# ─── maybe_suggest_note_action: эвристика интента ───


def test_suggest_save_intent():
    assert na.maybe_suggest_note_action("Сохрани в заметку рецепт") is not None


def test_suggest_note_word():
    assert na.maybe_suggest_note_action("что там в заметках про фудзи") is not None


def test_suggest_apple_notes_word():
    assert na.maybe_suggest_note_action("запиши это в apple notes") is not None


def test_suggest_none_for_commands():
    for prefix in ("/", "~", "#", "!"):
        assert na.maybe_suggest_note_action(f"{prefix}сохрани заметку") is None


def test_suggest_none_for_empty_and_plain():
    assert na.maybe_suggest_note_action("") is None
    assert na.maybe_suggest_note_action("  ") is None
    assert na.maybe_suggest_note_action("как дела") is None
    assert na.maybe_suggest_note_action("напомни купить молока") is None


# ─── Режим ожидания ввода ───


def test_waiting_mode_helpers():
    assert not na.is_waiting_for_notes_input(4242)
    na._waiting_for_notes_input[4242] = True
    assert na.is_waiting_for_notes_input(4242)
    assert na.consume_notes_input(4242) is True
    assert not na.is_waiting_for_notes_input(4242)
    assert na.consume_notes_input(4242) is False


async def test_cb_notes_agent_start_enables_waiting():
    cb = FakeCbLite(4242, "notes_agent_start")
    await na.cb_notes_agent_start(cb)
    assert na.is_waiting_for_notes_input(4242)
    assert "Работа с заметками Apple Notes" in cb.message.edits[0]


# ─── _ask_once: подтверждение через события ───


async def test_ask_once_approved_by_confirm():
    status = FakeStatus()
    task = asyncio.create_task(na._ask_once(4242, status, "Карточка", "tok1"))
    await asyncio.sleep(0.05)
    assert status.cards == ["Карточка"]
    assert status.reply_markup is not None
    token = _token_from(status)
    cb = FakeCbLite(4242, f"notes_confirm:{token}")
    await na.cb_notes_confirm(cb)
    assert await asyncio.wait_for(task, timeout=1) is True


async def test_ask_once_rejected_by_cancel():
    status = FakeStatus()
    task = asyncio.create_task(na._ask_once(4242, status, "Карточка", "tok2"))
    await asyncio.sleep(0.05)
    token = _cancel_token_from(status)
    cb = FakeCbLite(4242, f"notes_cancel:{token}")
    await na.cb_notes_cancel(cb)
    assert await asyncio.wait_for(task, timeout=1) is False


async def test_ask_once_timeout_returns_false(monkeypatch):
    monkeypatch.setattr(na, "CONFIRM_TIMEOUT", 0.05)
    status = FakeStatus()
    ok = await na._ask_once(4242, status, "Карточка", "tok3")
    assert ok is False
    assert "истекло" in status.edits[-1]


async def test_confirm_stale_token_rejected():
    cb = FakeCbLite(4242, "notes_confirm:stale")
    await na.cb_notes_confirm(cb)
    assert any(a[1] is True for a in cb.answered)


async def test_confirm_wrong_uid_rejected(monkeypatch):
    monkeypatch.setattr(na, "CONFIRM_TIMEOUT", 5)
    status = FakeStatus()
    task = asyncio.create_task(na._ask_once(4242, status, "Карточка", "tok4"))
    await asyncio.sleep(0.05)
    token = _token_from(status)
    cb = FakeCbLite(9999, f"notes_confirm:{token}")
    await na.cb_notes_confirm(cb)
    assert any(a[1] is True for a in cb.answered)  # show_alert
    assert not task.done()
    cb2 = FakeCbLite(4242, f"notes_cancel:{token}")
    await na.cb_notes_cancel(cb2)
    assert await asyncio.wait_for(task, timeout=1) is False


# ─── _make_confirm_write: гейтинг write-инструментов ───


async def test_confirm_write_create_single(monkeypatch):
    monkeypatch.setattr(na, "CONFIRM_TIMEOUT", 5)
    status = FakeStatus()
    confirm = na._make_confirm_write(4242, status)
    task = asyncio.create_task(
        confirm("notes_create", {"title": "Идеи", "text": "Текст"}),
    )
    await asyncio.sleep(0.05)
    token = _token_from(status)
    await na.cb_notes_confirm(FakeCbLite(4242, f"notes_confirm:{token}"))
    assert await asyncio.wait_for(task, timeout=1) is True


async def test_confirm_write_delete_requires_two_confirmations(monkeypatch):
    monkeypatch.setattr(na, "CONFIRM_TIMEOUT", 5)
    status = FakeStatus()
    confirm = na._make_confirm_write(4242, status)
    task = asyncio.create_task(
        confirm("notes_delete", {"note_id": "B2"}),
    )
    await asyncio.sleep(0.05)
    token1 = _token_from(status)
    await na.cb_notes_confirm(FakeCbLite(4242, f"notes_confirm:{token1}"))
    await asyncio.sleep(0.05)
    assert not task.done(), "Одного «Да» недостаточно для удаления"
    assert "Двойное подтверждение" in status.cards[-1]
    token2 = _token_from(status)
    await na.cb_notes_confirm(FakeCbLite(4242, f"notes_confirm:{token2}"))
    assert await asyncio.wait_for(task, timeout=1) is True


async def test_confirm_write_delete_second_cancel(monkeypatch):
    monkeypatch.setattr(na, "CONFIRM_TIMEOUT", 5)
    status = FakeStatus()
    confirm = na._make_confirm_write(4242, status)
    task = asyncio.create_task(
        confirm("notes_delete", {"note_id": "B2"}),
    )
    await asyncio.sleep(0.05)
    token1 = _token_from(status)
    await na.cb_notes_confirm(FakeCbLite(4242, f"notes_confirm:{token1}"))
    await asyncio.sleep(0.05)
    token2 = _cancel_token_from(status)
    await na.cb_notes_cancel(FakeCbLite(4242, f"notes_cancel:{token2}"))
    assert await asyncio.wait_for(task, timeout=1) is False


async def test_confirm_write_delete_first_cancel_stops(monkeypatch):
    monkeypatch.setattr(na, "CONFIRM_TIMEOUT", 5)
    status = FakeStatus()
    confirm = na._make_confirm_write(4242, status)
    task = asyncio.create_task(
        confirm("notes_delete", {"note_id": "B2"}),
    )
    await asyncio.sleep(0.05)
    token1 = _cancel_token_from(status)
    await na.cb_notes_cancel(FakeCbLite(4242, f"notes_cancel:{token1}"))
    assert await asyncio.wait_for(task, timeout=1) is False
    assert len(status.cards) == 1, "После первого отказа вторая карточка не показывается"


async def test_confirm_write_move(monkeypatch):
    monkeypatch.setattr(na, "CONFIRM_TIMEOUT", 5)
    status = FakeStatus()
    confirm = na._make_confirm_write(4242, status)
    task = asyncio.create_task(
        confirm("notes_move", {"note_id": "C3", "target_folder": "Фото"}),
    )
    await asyncio.sleep(0.05)
    token = _token_from(status)
    await na.cb_notes_confirm(FakeCbLite(4242, f"notes_confirm:{token}"))
    assert await asyncio.wait_for(task, timeout=1) is True


# ─── _run_notes_agent_reply: маршрутизация и форматирование ───


async def test_run_notes_agent_wiring(monkeypatch):
    from handlers.palace import action_bar

    calls = []

    async def fake_run_agent(*args, **kwargs):
        calls.append(kwargs)
        return na.ae.AgentResult(final_answer="Вот ваша заметка")

    async def fake_finalize(uid, edit, answer, ctx=None, title="", extra_rows=None):
        fake_finalize.args = (uid, answer, ctx, title, extra_rows)

    monkeypatch.setattr(na.ae, "run_agent", fake_run_agent)
    monkeypatch.setattr(action_bar, "finalize_answer", fake_finalize)

    status = FakeStatus()
    result = await na._run_notes_agent_reply(4242, status, "найди про фудзи")
    assert result.ok is True
    assert result.final_answer == "Вот ваша заметка"
    assert calls[0]["allowed_categories"] == (na.CAT_NOTES,)
    assert calls[0]["include_write"] is True
    assert callable(calls[0]["confirm_write"])
    assert fake_finalize.args[1] == "Вот ваша заметка"
    assert fake_finalize.args[3] == "<b>📝 Apple Notes</b>"
    assert fake_finalize.args[4] is None


async def test_run_notes_agent_engine_error(monkeypatch):
    async def boom(*args, **kwargs):
        raise na.ae.AgentEngineError("Агентный режим работает только с Ollama")

    monkeypatch.setattr(na.ae, "run_agent", boom)
    status = FakeStatus()
    result = await na._run_notes_agent_reply(4242, status, "вопрос")
    assert result.ok is False
    assert result.final_answer == ""
    assert "только с Ollama" in (result.error or "")
    assert "только с Ollama" in status.edits[-1]


async def test_run_notes_agent_unexpected_error(monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("поломка")

    monkeypatch.setattr(na.ae, "run_agent", boom)
    status = FakeStatus()
    result = await na._run_notes_agent_reply(4242, status, "вопрос")
    assert result.ok is False
    assert result.final_answer == ""
    assert result.error == "Ошибка агента: поломка"
    assert "поломка" in status.edits[-1]


async def test_run_notes_agent_error_result(monkeypatch):
    async def fake_run_agent(*args, **kwargs):
        return na.ae.AgentResult(
            final_answer="", finished_reason="error", error="Модель вернула пустой ответ.",
        )

    monkeypatch.setattr(na.ae, "run_agent", fake_run_agent)
    status = FakeStatus()
    result = await na._run_notes_agent_reply(4242, status, "вопрос")
    assert result.ok is False
    assert result.error == "Модель вернула пустой ответ."
    assert "Модель вернула пустой ответ" in status.edits[-1]


async def test_run_notes_agent_max_iterations(monkeypatch):
    async def fake_run_agent(*args, **kwargs):
        return na.ae.AgentResult(
            final_answer="", finished_reason="max_iterations",
            error="Достигнут лимит итераций агента (5).",
        )

    monkeypatch.setattr(na.ae, "run_agent", fake_run_agent)
    status = FakeStatus()
    result = await na._run_notes_agent_reply(4242, status, "вопрос")
    assert result.ok is False
    assert result.finished_reason == "max_iterations"
    assert "лимит итераций" in status.edits[-1]


# ─── 💡 Творческий штурм: извлечение темы ───


def test_extract_storm_topic_happy():
    assert na._extract_storm_topic("💡 Творческий штурм: ночные сны") == "ночные сны"
    assert na._extract_storm_topic("Творческий штурм ночные сны") == "ночные сны"
    assert na._extract_storm_topic("сюрреалистичный штурм: море") == "море"
    assert na._extract_storm_topic("СЮРШТУРМ сны") == "сны"


def test_extract_storm_topic_with_separators():
    assert na._extract_storm_topic("💡 Творческий штурм — сны") == "сны"
    assert na._extract_storm_topic("💡 Творческий штурм:  сны  ") == "сны"


def test_extract_storm_topic_empty_topic():
    assert na._extract_storm_topic("💡 Творческий штурм") == ""
    assert na._extract_storm_topic("творческий штурм:") == ""


def test_extract_storm_topic_none_for_plain_text():
    assert na._extract_storm_topic("найди заметку про штурм") is None
    assert na._extract_storm_topic("") is None
    assert na._extract_storm_topic("   ") is None
    assert na._extract_storm_topic("как дела") is None


def _fake_coro(value):
    async def _run():
        return value
    return _run()


# ─── run_surreal_storm: пайплайн ───


async def test_run_surreal_storm_happy(monkeypatch):
    from services import ai_engine
    from services import brainstorm as bs

    monkeypatch.setattr(
        bs, "collect_context",
        lambda topic, mode="standard", folder=None: _fake_coro(
            {"notes": "заметка", "guide": "гайд"},
        ),
    )
    monkeypatch.setattr(ai_engine, "get_current_ai", lambda: ("fake", "model"))
    captured = {}

    async def fake_response(engine, model, msgs, **kwargs):
        captured["system"] = msgs[0]["content"]
        captured["user"] = msgs[1]["content"]
        captured["sampling"] = kwargs.get("sampling")
        camera = "Имитация плёнки ACROS, тени -2"
        return ('{"ideas": [{"title": "Сон", "reason": "р", '
                f'"camera_setup": "{camera}", "steps": "s"}}]}}')

    monkeypatch.setattr(ai_engine, "get_ai_response_async", fake_response)

    status = FakeStatus()
    await na.run_surreal_storm(4242, status, "ночные сны")

    assert captured["system"] == bs.SURREAL_STORM_SYSTEM_PROMPT
    assert "ночные сны" in captured["user"]
    assert "[Руководство Fujifilm X-T4]" in captured["user"]
    assert captured["sampling"] == bs.SURREAL_SAMPLING_PARAMS
    assert status.edits, "карточки должны быть показаны"
    joined = "\n".join(status.edits)
    assert "🌪" in joined and "Сон" in joined
    assert "📷" in joined and "<code>Имитация плёнки ACROS, тени -2</code>" in joined


async def test_run_surreal_storm_empty_topic(monkeypatch):
    status = FakeStatus()
    await na.run_surreal_storm(4242, status, "   ")
    assert "Укажите тему" in status.edits[-1]


async def test_run_surreal_storm_ai_error(monkeypatch):
    from services import ai_engine
    from services import brainstorm as bs

    monkeypatch.setattr(
        bs, "collect_context",
        lambda topic, mode="standard", folder=None: _fake_coro({"notes": "", "guide": ""}),
    )
    monkeypatch.setattr(ai_engine, "get_current_ai", lambda: ("fake", "model"))

    async def boom(engine, model, msgs, **kwargs):
        raise RuntimeError("ollama down")

    monkeypatch.setattr(ai_engine, "get_ai_response_async", boom)

    status = FakeStatus()
    await na.run_surreal_storm(4242, status, "сны")
    assert "Ошибка штурма" in status.edits[-1]


async def test_run_surreal_storm_retries_malformed_json(monkeypatch):
    """Первый ответ модели без массива ideas → ретрай → карточки показаны."""
    from services import ai_engine
    from services import brainstorm as bs

    monkeypatch.setattr(
        bs, "collect_context",
        lambda topic, mode="standard", folder=None: _fake_coro({"notes": "", "guide": ""}),
    )
    monkeypatch.setattr(ai_engine, "get_current_ai", lambda: ("fake", "model"))
    calls = []

    async def malformed_then_ok(engine, model, msgs, **kwargs):
        calls.append(kwargs.get("sampling"))
        if len(calls) == 1:
            return '{"title": "не та структура"}'
        camera = "Имитация плёнки ACROS, тени -2"
        return ('{"ideas": [{"title": "Сон", "reason": "р", '
                f'"camera_setup": "{camera}", "steps": "s"}}]}}')

    monkeypatch.setattr(ai_engine, "get_ai_response_async", malformed_then_ok)

    status = FakeStatus()
    await na.run_surreal_storm(4242, status, "сны")
    assert len(calls) == 2, "должен быть ровно один ретрай"
    assert status.edits, "карточки должны быть показаны после ретрая"
    joined = "\n".join(status.edits)
    assert "🌪" in joined and "Сон" in joined
    assert not any("Ошибка штурма" in e for e in status.edits), \
        "после успешного ретрая ошибки быть не должно"
    assert any("ещё раз" in e for e in status.edits), \
        "статус должен сообщить о повторной попытке"


async def test_run_surreal_storm_retry_fails_shows_error(monkeypatch):
    """Сырой ответ без ideas, ретрай тоже без ideas → ошибка пользователю."""
    from services import ai_engine
    from services import brainstorm as bs

    monkeypatch.setattr(
        bs, "collect_context",
        lambda topic, mode="standard", folder=None: _fake_coro({"notes": "", "guide": ""}),
    )
    monkeypatch.setattr(ai_engine, "get_current_ai", lambda: ("fake", "model"))
    calls = []

    async def always_malformed(engine, model, msgs, **kwargs):
        calls.append(1)
        return '{"заголовок": "снова без ideas"}'

    monkeypatch.setattr(ai_engine, "get_ai_response_async", always_malformed)

    status = FakeStatus()
    await na.run_surreal_storm(4242, status, "сны")
    assert len(calls) == 2, "ровно один ретрай, не бесконечный"
    assert "Ошибка штурма" in status.edits[-1]
    assert "нет массива ideas" in status.edits[-1]


async def test_run_surreal_storm_rejects_ideas_without_camera_setup(monkeypatch):
    from services import ai_engine
    from services import brainstorm as bs

    monkeypatch.setattr(
        bs, "collect_context",
        lambda topic, mode="standard", folder=None: _fake_coro({"notes": "", "guide": ""}),
    )
    monkeypatch.setattr(ai_engine, "get_current_ai", lambda: ("fake", "model"))

    async def no_camera(engine, model, msgs, **kwargs):
        return '{"ideas": [{"title": "Без камеры", "reason": "r"}]}'

    monkeypatch.setattr(ai_engine, "get_ai_response_async", no_camera)

    status = FakeStatus()
    await na.run_surreal_storm(4242, status, "сны")
    assert "Ошибка штурма" in status.edits[-1]
    assert "Нет валидных идей" in status.edits[-1]


async def test_run_surreal_storm_edit_failure_tolerated(monkeypatch):
    from services import ai_engine
    from services import brainstorm as bs

    monkeypatch.setattr(
        bs, "collect_context",
        lambda topic, mode="standard", folder=None: _fake_coro({"notes": "", "guide": ""}),
    )
    monkeypatch.setattr(ai_engine, "get_current_ai", lambda: ("fake", "model"))

    async def fake_response(engine, model, msgs, **kwargs):
        camera = "Имитация плёнки ACROS, тени -2"
        return ('{"ideas": [{"title": "Сон", "reason": "р", '
                f'"camera_setup": "{camera}", "steps": "s"}}]}}')

    monkeypatch.setattr(ai_engine, "get_ai_response_async", fake_response)

    class BrokenStatus(FakeStatus):
        async def edit_text(self, text, parse_mode=None, reply_markup=None):
            raise RuntimeError("message too old")

    status = BrokenStatus()
    await na.run_surreal_storm(4242, status, "сны")
    assert status.edits == [], "упавшая отрисовка не должна ронять штурм"


# ─── run_notes_agent: маршрутизация в сюрреалистичный штурм ───


async def test_run_notes_agent_routes_to_surreal_storm(monkeypatch):
    from services import ai_engine
    from services import brainstorm as bs

    monkeypatch.setattr(
        bs, "collect_context",
        lambda topic, mode="standard", folder=None: _fake_coro(
            {"notes": "", "guide": "гайд"},
        ),
    )
    monkeypatch.setattr(ai_engine, "get_current_ai", lambda: ("fake", "model"))

    async def fake_response(engine, model, msgs, **kwargs):
        camera = "Имитация плёнки ACROS, тень -1"
        return ('{"ideas": [{"title": "Т", '
                f'"camera_setup": "{camera}", "reason": "", "steps": ""}}]}}')

    monkeypatch.setattr(ai_engine, "get_ai_response_async", fake_response)

    status = FakeStatus()
    await na.run_notes_agent(4242, status, "💡 Творческий штурм: сны")
    joined = "\n".join(status.edits)
    assert "Сюрреалистичный штурм" in joined
    assert "ACROS" in joined


async def test_run_notes_agent_routes_to_surreal_storm_empty_topic(monkeypatch):
    status = FakeStatus()
    await na.run_notes_agent(4242, status, "💡 Творческий штурм")
    assert "Укажите тему" in status.edits[-1]


async def test_run_notes_agent_normal_text_goes_to_agent(monkeypatch):
    from handlers.palace import action_bar

    async def fake_finalize(uid, edit_func, text, **kwargs):
        pass

    async def fake_run_agent(*args, **kwargs):
        return na.ae.AgentResult(
            final_answer="Обычный ответ", finished_reason="done", error=None,
        )

    monkeypatch.setattr(na.ae, "run_agent", fake_run_agent)
    monkeypatch.setattr(action_bar, "finalize_answer", fake_finalize)

    status = FakeStatus()
    await na.run_notes_agent(4242, status, "найди заметку про фудзи")
    joined = "\n".join(status.edits)
    assert "Сюрреалистичный штурм" not in joined


# ─── 📄 Список найденных заметок: кнопки открытия и обсуждение ───


def _note_steps(note_rows: str) -> list:
    """Строит AgentResult со шагом, вернувшим notes_search output."""
    from types import SimpleNamespace

    step = SimpleNamespace(
        calls=[{"id": "c1", "name": "notes_search", "arguments": "{}"}],
        results=[{"name": "notes_search", "ok": True, "output": note_rows}],
    )
    return na.ae.AgentResult(final_answer="ok", steps=[step])


ROW_1 = "- Идеи для фото [id=AAA] (папка: Notes)"
ROW_2 = "- Покупки [id=BBB] (папка: Дом)"
ROW_1_DUP = "- Идеи для фото [id=AAA] (папка: Notes)"


def test_collect_notes_from_result_happy():
    notes = na._collect_notes_from_result(_note_steps(f"{ROW_1}\n{ROW_2}"))
    assert notes == [
        {"id": "AAA", "name": "Идеи для фото", "folder": "Notes"},
        {"id": "BBB", "name": "Покупки", "folder": "Дом"},
    ]


def test_collect_notes_from_result_line_without_folder():
    notes = na._collect_notes_from_result(
        _note_steps("- Просто строка [id=CCC]"),
    )
    assert notes == [{"id": "CCC", "name": "Просто строка", "folder": ""}]


def test_collect_notes_from_result_dedups_and_merges_notes_list():
    from types import SimpleNamespace

    step1 = SimpleNamespace(
        calls=[{"id": "c1", "name": "notes_search", "arguments": "{}"}],
        results=[{"name": "notes_search", "ok": True, "output": f"{ROW_1}\n{ROW_1_DUP}"}],
    )
    step2 = SimpleNamespace(
        calls=[{"id": "c2", "name": "notes_list", "arguments": "{}"}],
        results=[{"name": "notes_list", "ok": True, "output": ROW_2}],
    )
    result = na.ae.AgentResult(final_answer="ok", steps=[step1, step2])
    notes = na._collect_notes_from_result(result)
    assert [n["id"] for n in notes] == ["AAA", "BBB"]


def test_collect_notes_from_result_skips_other_tools_and_junk():
    from types import SimpleNamespace

    step = SimpleNamespace(
        calls=[{"id": "c1", "name": "notes_read", "arguments": "{}"}],
        results=[{"name": "notes_read", "ok": True, "output": "не разметка заметки"}],
    )
    result = na.ae.AgentResult(final_answer="ok", steps=[step])
    assert na._collect_notes_from_result(result) == []


def test_collect_notes_from_result_no_steps():
    result = na.ae.AgentResult(final_answer="ok", steps=[])
    assert na._collect_notes_from_result(result) == []
    assert na._collect_notes_from_result(None) == []


def test_collect_notes_from_result_line_without_id_ignored():
    notes = na._collect_notes_from_result(_note_steps("просто текст\n— Нет id"))
    assert notes == []
    assert na._collect_notes_from_result(_note_steps("")) == []


def test_clean_notes_text_strips_id_markers():
    text = (
        "Нашёл заметки:\n"
        "- Идеи для фото [id=AAA] (папка: Notes)\n"
        "- Покупки [id=BBB] (папка: Дом)"
    )
    assert na._clean_notes_text(text) == (
        "Нашёл заметки:\n"
        "- Идеи для фото (папка: Notes)\n"
        "- Покупки (папка: Дом)"
    )


def test_clean_notes_text_no_markers_unchanged():
    text = "Заметок не найдено.\nПопробуйте другой запрос."
    assert na._clean_notes_text(text) == text


def test_clean_notes_text_empty_and_none():
    assert na._clean_notes_text("") == ""
    assert na._clean_notes_text(None) is None


def test_clean_notes_text_marker_without_preceding_space():
    assert na._clean_notes_text("фото[id=X]") == "фото"


def test_clean_notes_text_multiple_markers_in_line():
    assert na._clean_notes_text("- A [id=1] и B [id=2]") == "- A и B"


def test_notes_list_key_and_note_by_index():
    assert na._notes_list_key(1) is None
    na._notes_list_store[1] = {"items": [{"id": "A", "name": "X"}], "text": ""}
    assert na._notes_list_key(1)["items"][0]["id"] == "A"
    assert na._note_by_index(1, 0) == {"id": "A", "name": "X"}


def test_note_by_index_bounds():
    na._notes_list_store[1] = {"items": [{"id": "A", "name": "X"}], "text": ""}
    assert na._note_by_index(1, -1) is None
    assert na._note_by_index(1, 1) is None
    assert na._note_by_index(1, 99) is None
    assert na._note_by_index(1, "0") is None
    assert na._note_by_index(2, 0) is None
    assert na._note_by_index(2, None) is None


def test_current_discuss_and_persistent():
    assert na._current_discuss(7) is None
    na._notes_discuss_ctx[7] = {"note_id": "A", "name": "X", "folder": ""}
    assert na._current_discuss(7) == {"note_id": "A", "name": "X", "folder": ""}
    assert na._current_discuss(7) == {"note_id": "A", "name": "X", "folder": ""}, \
        "контекст обсуждения персистентен, пока не нажата ⏹"
    na._notes_discuss_ctx.pop(7, None)
    assert na._current_discuss(7) is None


def test_build_open_rows_empty():
    assert na._build_open_rows(3) == []


def test_build_open_rows_packs_five_per_row_and_truncates():
    items = [{"id": f"n{i}", "name": f"Заметка {i}"} for i in range(6)]
    na._notes_list_store[1] = {"items": items, "text": ""}
    rows = na._build_open_rows(1)
    assert len(rows) == 2
    assert len(rows[0]) == 5 and len(rows[1]) == 1
    first = rows[0][0]
    assert first.callback_data == "notes_view:0"
    assert first.text == "📄 1. Заметка 0"
    assert rows[1][0].callback_data == "notes_view:5"


def test_build_open_rows_caps_at_max_buttons():
    items = [{"id": f"n{i}", "name": f"Заметка {i}"} for i in range(12)]
    na._notes_list_store[1] = {"items": items, "text": ""}
    rows = na._build_open_rows(1)
    buttons = [b for row in rows for b in row]
    assert len(buttons) == na.MAX_LIST_OPEN_BUTTONS


async def test_run_notes_agent_stores_notes_and_passes_rows(monkeypatch):
    from handlers.palace import action_bar

    captured = {}

    async def fake_run_agent(*args, **kwargs):
        status_cb = kwargs.get("status_cb")
        if status_cb:
            await status_cb("🔍 Ищу в заметках…")
        return _note_steps(ROW_1)

    async def fake_finalize(uid, edit, answer, ctx=None, title="", extra_rows=None):
        captured["rows"] = extra_rows
        captured["answer"] = answer

    monkeypatch.setattr(na.ae, "run_agent", fake_run_agent)
    monkeypatch.setattr(action_bar, "finalize_answer", fake_finalize)

    status = FakeStatus()
    await na._run_notes_agent_reply(4242, status, "найди про фудзи")
    assert captured["rows"], "кнопки заметок должны передаваться в finalize_answer"
    assert [b.callback_data for row in captured["rows"] for b in row] == ["notes_view:0"]
    assert na._notes_list_key(4242)["items"][0]["id"] == "AAA"
    assert "Ищу в заметках" in status.edits[-1]


async def test_run_notes_agent_strips_ids_from_displayed_list(monkeypatch):
    from handlers.palace import action_bar

    captured = {}
    raw_answer = (
        "Нашёл заметки:\n"
        f"{ROW_1}\n"
        f"{ROW_2}"
    )

    async def fake_run_agent(*args, **kwargs):
        from types import SimpleNamespace

        step = SimpleNamespace(
            calls=[{"id": "c1", "name": "notes_search", "arguments": "{}"}],
            results=[{"name": "notes_search", "ok": True, "output": f"{ROW_1}\n{ROW_2}"}],
        )
        return na.ae.AgentResult(final_answer=raw_answer, steps=[step])

    async def fake_finalize(uid, edit, answer, ctx=None, title="", extra_rows=None):
        captured["answer"] = answer
        captured["rows"] = extra_rows

    monkeypatch.setattr(na.ae, "run_agent", fake_run_agent)
    monkeypatch.setattr(action_bar, "finalize_answer", fake_finalize)

    status = FakeStatus()
    await na._run_notes_agent_reply(4242, status, "найди про фудзи")
    assert "[id=" not in captured["answer"], captured["answer"]
    assert captured["answer"] == (
        "Нашёл заметки:\n"
        "- Идеи для фото (папка: Notes)\n"
        "- Покупки (папка: Дом)"
    )
    assert captured["rows"], "кнопки открытия остаются в списке"
    stored = na._notes_list_key(4242)
    assert stored["text"] == captured["answer"], \
        "«← К списку» показывает тот же текст без id"
    assert "Идеи" in stored["text"] and "Покупки" in stored["text"]


async def test_run_notes_agent_no_notes_clears_store(monkeypatch):
    from handlers.palace import action_bar

    na._notes_list_store[4242] = {"items": [{"id": "OLD", "name": "ст"}], "text": ""}
    captured = {}

    async def fake_run_agent(*args, **kwargs):
        return na.ae.AgentResult(final_answer="без заметок", steps=[])

    async def fake_finalize(uid, edit, answer, ctx=None, title="", extra_rows=None):
        captured["rows"] = extra_rows

    monkeypatch.setattr(na.ae, "run_agent", fake_run_agent)
    monkeypatch.setattr(action_bar, "finalize_answer", fake_finalize)

    status = FakeStatus()
    await na._run_notes_agent_reply(4242, status, "привет")
    assert captured["rows"] is None
    assert na._notes_list_key(4242) is None


async def test_cb_notes_view_happy(monkeypatch):
    na._notes_list_store[4242] = {
        "items": [{"id": "AAA", "name": "Идеи", "folder": "Notes"}], "text": "",
    }

    def fake_read(note_id):
        return {"name": "Идеи", "body": "Снимать на рассвете"}

    monkeypatch.setattr("services.apple_notes.read_note", fake_read)

    cb = FakeCbLite(4242, "notes_view:0")
    await na.cb_notes_view(cb)
    assert na._current_discuss(4242) == {
        "note_id": "AAA", "name": "Идеи", "folder": "Notes",
    }
    assert na.is_waiting_for_notes_input(4242)
    assert not cb.message.answers, "короткая заметка — одно сообщение"
    joined = cb.message.edits[-1]
    assert "Идеи" in joined and "рассвете" in joined
    assert "Обсуждение включено" in joined
    assert "Notes" in joined, "имя папки видно в заголовке заметки"
    markup = cb.message.edits_reply_markup
    assert markup is not None, "у открытой заметки есть кнопки действий"
    actions = [
        b.callback_data for row in markup.inline_keyboard for b in row
    ]
    assert "notes_discuss:0" in actions
    assert "notes_storm:0" in actions
    assert "notes_save:0" in actions
    assert "notes_back:0" in actions, "кнопка возврата к списку"
    assert not any(d.startswith("notes_page:") for d in actions), \
        "короткая заметка листания не требует"


async def test_cb_notes_view_expired_list(monkeypatch):
    cb = FakeCbLite(4242, "notes_view:0")
    await na.cb_notes_view(cb)
    assert "устарел" in cb.message.edits[-1]
    assert na._current_discuss(4242) is None


async def test_cb_notes_view_out_of_range(monkeypatch):
    na._notes_list_store[4242] = {"items": [{"id": "A", "name": "x"}], "text": ""}
    cb = FakeCbLite(4242, "notes_view:5")
    await na.cb_notes_view(cb)
    assert "устарел" in cb.message.edits[-1]


async def test_cb_notes_view_bad_index(monkeypatch):
    cb = FakeCbLite(4242, "notes_view:abc")
    await na.cb_notes_view(cb)
    assert "Неверный запрос" in cb.message.edits[-1]


async def test_cb_notes_view_read_failure_falls_back(monkeypatch):
    na._notes_list_store[4242] = {
        "items": [{"id": "AAA", "name": "Идеи"}], "text": "",
    }

    def boom(note_id):
        raise RuntimeError("osascript down")

    monkeypatch.setattr("services.apple_notes.read_note", boom)

    cb = FakeCbLite(4242, "notes_view:0")
    await na.cb_notes_view(cb)
    assert na._current_discuss(4242) == {
        "note_id": "AAA", "name": "Идеи", "folder": "",
    }
    assert "Текст недоступен" in cb.message.edits[-1]


async def test_cb_notes_view_split_long_body(monkeypatch):
    """Длинная заметка: ОДНО сообщение-страница (≈1500 симв), листание стрелками."""
    na._notes_list_store[4242] = {
        "items": [{"id": "AAA", "name": "Длинная"}], "text": "",
    }

    def fake_read(note_id):
        return {"name": "Длинная", "body": "слово " * 2000}

    monkeypatch.setattr("services.apple_notes.read_note", fake_read)

    cb = FakeCbLite(4242, "notes_view:0")
    await na.cb_notes_view(cb)
    assert not cb.message.answers, "длинная заметка НЕ разбивается на несколько сообщений"
    assert len(cb.message.edits) == 1, "открытие заметки — один edit"
    joined = cb.message.edits[0]
    assert "Страница 1/8" in joined
    body_chunk = joined.split("\n\n")[1]
    assert len(body_chunk) <= na.NOTE_PAGE_SIZE + 100, "страница ≈1500 символов"
    assert na._notes_view_store.get(4242) is not None, "состояние листания сохранено"
    state = na._notes_view_store.get(4242)
    assert len(state["pages"]) == 8 and state["page"] == 0
    assert len(na._notes_discuss_ctx.get(4242) or {}) == 3

    markup = cb.message.edits_reply_markup
    cbs = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert "notes_page:0:1" in cbs, "есть стрелка ▶️ на следующую страницу"
    assert "notes_page:0:0" in cbs, "есть индикатор страницы"
    assert "notes_back:0" in cbs, "есть кнопка «← К списку»"
    assert "notes_page:0:-1" not in cbs, "на первой странице нет ◀️"


async def test_run_notes_agent_discusses_opened_note(monkeypatch):
    from services import ai_engine
    from services import brainstorm as bs

    monkeypatch.setattr(
        bs, "collect_context",
        lambda topic, mode="standard", folder=None: _fake_coro({"notes": "", "guide": ""}),
    )
    monkeypatch.setattr(ai_engine, "get_current_ai", lambda: ("fake", "model"))

    async def boom(engine, model, msgs, **kwargs):
        raise AssertionError("Штурм не должен запускаться для обсуждения")

    monkeypatch.setattr(ai_engine, "get_ai_response_async", boom)

    from handlers.palace import action_bar

    captured = {}

    async def fake_finalize(uid, edit_func, text, **kwargs):
        pass

    async def fake_run_agent(system, question, **kwargs):
        captured["question"] = question
        return na.ae.AgentResult(final_answer="Ответ", finished_reason="done")

    monkeypatch.setattr(na.ae, "run_agent", fake_run_agent)
    monkeypatch.setattr(action_bar, "finalize_answer", fake_finalize)

    na._notes_discuss_ctx[4242] = {"note_id": "AAA", "name": "Идеи", "folder": "Notes"}
    status = FakeStatus()
    await na.run_notes_agent(4242, status, "что там про рассвет?")
    assert "Идеи" in captured["question"]
    assert "AAA" in captured["question"]
    assert "что там про рассвет" in captured["question"]
    assert "Notes" in captured["question"], "папка подсказывается агенту"
    assert na._current_discuss(4242) is not None, \
        "контекст обсуждения не потребляется — он держится до кнопки ⏹"
    assert na.is_waiting_for_notes_input(4242), \
        "после ответа бот снова ждёт вопрос по заметке"


async def test_run_notes_agent_discuss_next_question_keeps_context(monkeypatch):
    from handlers.palace import action_bar

    captured = {}

    async def fake_finalize(uid, edit_func, text, **kwargs):
        pass

    async def fake_run_agent(system, question, **kwargs):
        captured["question"] = question
        return na.ae.AgentResult(final_answer="Ответ", finished_reason="done")

    monkeypatch.setattr(na.ae, "run_agent", fake_run_agent)
    monkeypatch.setattr(action_bar, "finalize_answer", fake_finalize)

    na._notes_discuss_ctx[4242] = {"note_id": "AAA", "name": "Идеи", "folder": ""}
    status = FakeStatus()
    await na.run_notes_agent(4242, status, "вопрос раз")
    await na.run_notes_agent(4242, status, "вопрос два")
    assert "вопрос два" in captured["question"]
    assert "Идеи" in captured["question"], \
        "второй вопрос тоже идёт с контекстом заметки"


async def test_cb_notes_stop_ends_discussion():
    na._notes_discuss_ctx[4242] = {"note_id": "AAA", "name": "Идеи", "folder": ""}
    na._waiting_for_notes_input[4242] = True
    cb = FakeCbLite(4242, "notes_stop:0")
    await na.cb_notes_stop(cb)
    assert na._current_discuss(4242) is None
    assert not na.is_waiting_for_notes_input(4242)
    assert "Обсуждение завершено" in cb.message.edits[-1]


async def test_run_notes_agent_without_discuss_context(monkeypatch):
    from handlers.palace import action_bar

    captured = {}

    async def fake_finalize(uid, edit_func, text, **kwargs):
        pass

    async def fake_run_agent(system, question, **kwargs):
        captured["question"] = question
        return na.ae.AgentResult(final_answer="Ответ", finished_reason="done")

    monkeypatch.setattr(na.ae, "run_agent", fake_run_agent)
    monkeypatch.setattr(action_bar, "finalize_answer", fake_finalize)

    status = FakeStatus()
    await na.run_notes_agent(4242, status, "найди фудзи")
    assert "обсуждает заметку" not in captured["question"]


async def test_cb_notes_view_not_allowed(monkeypatch):
    na._notes_list_store[777] = {"items": [{"id": "A", "name": "x"}], "text": ""}
    cb = FakeCbLite(777, "notes_view:0")
    await na.cb_notes_view(cb)
    assert not cb.message.edits, "неавторизованный пользователь ничего не получает"
    assert na._current_discuss(777) is None


async def test_start_notes_agent_session_via_message():
    msg = FakeMessageLite(4242, "игнор")
    await na.start_notes_agent_session(msg)
    assert na.is_waiting_for_notes_input(4242)
    assert msg.answers and "Работа с заметками" in msg.answers[0]


async def test_cb_notes_view_missing_callback_data():
    cb = FakeCbLite(4242, None)
    await na.cb_notes_view(cb)
    assert not cb.message.edits, "без callback_data не показываем ничего"


# ─── 💬 Действия с открытой заметкой: клавиатура и callback-хендлеры ───


def _action_data(uid: int, idx: int = 0, total: int = 1, page: int = 0) -> list:
    kb = na._build_note_view_kb(uid, idx, total=total, page=page)
    markup = kb.as_markup()
    return [b.callback_data for row in markup.inline_keyboard for b in row]


def test_build_note_view_kb_actions_and_back_when_no_discussion():
    data = _action_data(4242)
    assert "notes_discuss:0" in data
    assert "notes_storm:0" in data
    assert "notes_save:0" in data
    assert "notes_back:0" in data, "кнопка «← К списку» всегда есть"
    assert not any(d.startswith("notes_stop:") for d in data), \
        "⏹ видна только при активном обсуждении"
    assert not any(d.startswith("notes_page:") for d in data), \
        "на одной странице стрелок нет"


def test_build_note_view_kb_arrows_on_first_page():
    data = _action_data(4242, total=3, page=0)
    assert "notes_page:0:1" in data, "▶️ на следующую страницу"
    assert "notes_page:0:0" in data, "индикатор страницы"
    assert not any(d == "notes_page:0:-1" for d in data), "на 1-й нет ◀️"


def test_build_note_view_kb_arrows_on_middle_page():
    data = _action_data(4242, total=3, page=1)
    assert "notes_page:0:0" in data, "◀️ на предыдущую страницу"
    assert "notes_page:0:2" in data, "▶️ на следующую страницу"
    assert "notes_page:0:1" in data, "индикатор текущей страницы"


def test_build_note_view_kb_arrows_on_last_page():
    data = _action_data(4242, total=3, page=2)
    assert "notes_page:0:1" in data, "◀️ на предыдущую страницу"
    assert "notes_page:0:2" in data, "индикатор страницы"
    assert not any(d == "notes_page:0:3" for d in data), "на последней нет ▶️"


def test_build_note_view_kb_indicator_uses_given_idx():
    data = _action_data(4242, idx=3, total=2, page=1)
    assert "notes_page:3:0" in data
    assert "notes_page:3:1" in data
    assert "notes_back:3" in data


def test_build_note_view_kb_stop_shown_while_discussing():
    na._notes_discuss_ctx[4242] = {"note_id": "A", "name": "X", "folder": ""}
    data = _action_data(4242, idx=3)
    assert "notes_stop:3" in data


def test_chunk_text_empty_and_short():
    assert na._chunk_text("") == []
    assert na._chunk_text("короткая заметка") == ["короткая заметка"]


def test_chunk_text_exact_limit_and_plus_one():
    assert len(na._chunk_text("а" * na.NOTE_PAGE_SIZE)) == 1
    assert len(na._chunk_text("а" * (na.NOTE_PAGE_SIZE + 1))) == 2


def test_chunk_text_long_line_hard_split_without_loss():
    text = "б" * 3200
    chunks = na._chunk_text(text)
    assert len(chunks) == 3
    assert sum(len(c) for c in chunks) == 3200, "текст не теряется"
    assert all(len(c) <= na.NOTE_PAGE_SIZE for c in chunks)


def test_chunk_text_prefers_newline_boundaries():
    text = "\n".join(["строка" * 20] * 30)  # 30 строк по 100 символов
    chunks = na._chunk_text(text)
    assert len(chunks) == 3, "страницы режутся по границам строк"
    assert all(len(c) <= na.NOTE_PAGE_SIZE for c in chunks)
    assert all("\n" in c for c in chunks), "граница страницы — перенос строки"


def test_chunk_text_reconstructs_original_text():
    text = "первая строка\nвторая строка длинная " + "x" * 3000 + "\nхвост"
    chunks = na._chunk_text(text)
    assert "".join(chunks) == text, "склейка страниц даёт исходный текст"
    assert all(len(c) <= na.NOTE_PAGE_SIZE for c in chunks)


async def test_cb_notes_page_happy(monkeypatch):
    na._notes_list_store[4242] = {
        "items": [{"id": "AAA", "name": "Длинная", "folder": "Notes"}], "text": "",
    }
    na._notes_view_store[4242] = {
        "idx": 0, "name": "Длинная", "folder": "Notes",
        "pages": ["страница один", "страница два"], "page": 0,
    }
    cb = FakeCbLite(4242, "notes_page:0:1")
    await na.cb_notes_page(cb)
    assert "Страница 2/2" in cb.message.edits[-1]
    assert "страница два" in cb.message.edits[-1]
    assert na._notes_view_store.get(4242)["page"] == 1


async def test_cb_notes_page_on_indicator_keeps_page():
    na._notes_view_store[4242] = {
        "idx": 1, "name": "X", "folder": "",
        "pages": ["a", "b", "c"], "page": 1,
    }
    cb = FakeCbLite(4242, "notes_page:1:1")
    await na.cb_notes_page(cb)
    assert "Страница 2/3" in cb.message.edits[-1]
    assert na._notes_view_store.get(4242)["page"] == 1


async def test_cb_notes_page_stale_session():
    cb = FakeCbLite(4242, "notes_page:0:1")
    await na.cb_notes_page(cb)
    assert "Сессия заметки истекла" in cb.message.edits[-1]


async def test_cb_notes_page_idx_mismatch_is_stale():
    na._notes_view_store[4242] = {
        "idx": 1, "name": "X", "folder": "",
        "pages": ["a", "b"], "page": 0,
    }
    cb = FakeCbLite(4242, "notes_page:0:1")
    await na.cb_notes_page(cb)
    assert "Сессия заметки истекла" in cb.message.edits[-1]


async def test_cb_notes_page_out_of_range_is_stale():
    na._notes_view_store[4242] = {
        "idx": 0, "name": "X", "folder": "",
        "pages": ["a", "b"], "page": 0,
    }
    cb = FakeCbLite(4242, "notes_page:0:9")
    await na.cb_notes_page(cb)
    assert "Сессия заметки истекла" in cb.message.edits[-1]


async def test_cb_notes_page_bad_format():
    for data in ("notes_page:abc", "notes_page:0", "notes_page:0:1:2"):
        cb = FakeCbLite(4242, data)
        await na.cb_notes_page(cb)
        assert "Неверный запрос" in cb.message.edits[-1], data


async def test_cb_notes_page_missing_data():
    cb = FakeCbLite(4242, None)
    await na.cb_notes_page(cb)
    assert not cb.message.edits


async def test_cb_notes_back_restores_list(monkeypatch):
    from handlers.palace import action_bar

    na._notes_list_store[4242] = {
        "items": [{"id": "AAA", "name": "Идеи"}, {"id": "BBB", "name": "Покупки"}],
        "text": "вот что нашёл",
    }
    na._notes_view_store[4242] = {
        "idx": 0, "name": "Идеи", "folder": "",
        "pages": ["a"], "page": 0,
    }
    na._notes_discuss_ctx[4242] = {"note_id": "AAA", "name": "Идеи", "folder": ""}
    captured = {}

    async def fake_finalize(uid, edit, answer, ctx=None, title="", extra_rows=None):
        captured["answer"] = answer
        captured["rows"] = extra_rows

    monkeypatch.setattr(action_bar, "finalize_answer", fake_finalize)

    cb = FakeCbLite(4242, "notes_back:0")
    await na.cb_notes_back(cb)
    assert captured["answer"] == "вот что нашёл"
    cbs = [b.callback_data for row in captured["rows"] for b in row]
    assert "notes_view:0" in cbs and "notes_view:1" in cbs, cbs
    assert "notes_stop:0" in cbs, "⏹ остаётся доступным при активном обсуждении"
    assert 4242 not in na._notes_view_store, "состояние листания очищено"
    assert na._current_discuss(4242) is not None, "обсуждение не сбрасывается"


async def test_cb_notes_back_stale_list():
    cb = FakeCbLite(4242, "notes_back:0")
    await na.cb_notes_back(cb)
    assert "устарел" in cb.message.edits[-1]


async def test_cb_notes_page_not_allowed():
    na._notes_view_store[777] = {
        "idx": 0, "name": "X", "folder": "",
        "pages": ["a"], "page": 0,
    }
    cb = FakeCbLite(777, "notes_page:0:0")
    await na.cb_notes_page(cb)
    assert not cb.message.edits, "неавторизованный пользователь ничего не получает"


async def test_cb_notes_back_not_allowed():
    na._notes_list_store[777] = {"items": [{"id": "A", "name": "x"}], "text": ""}
    cb = FakeCbLite(777, "notes_back:0")
    await na.cb_notes_back(cb)
    assert not cb.message.edits, "неавторизованный пользователь ничего не получает"


async def test_cb_notes_discuss_happy(monkeypatch):
    na._notes_list_store[4242] = {
        "items": [{"id": "AAA", "name": "Идеи", "folder": "Notes"}], "text": "",
    }
    cb = FakeCbLite(4242, "notes_discuss:0")
    await na.cb_notes_discuss(cb)
    assert na._current_discuss(4242) == {
        "note_id": "AAA", "name": "Идеи", "folder": "Notes",
    }
    assert na.is_waiting_for_notes_input(4242)
    joined = "\n".join(cb.message.edits)
    assert "Обсуждение включено" in joined
    assert "Notes" in joined


async def test_cb_notes_discuss_stale_list():
    cb = FakeCbLite(4242, "notes_discuss:0")
    await na.cb_notes_discuss(cb)
    assert "устарел" in cb.message.edits[-1]
    assert na._current_discuss(4242) is None


async def test_cb_notes_discuss_bad_index():
    cb = FakeCbLite(4242, "notes_discuss:abc")
    await na.cb_notes_discuss(cb)
    assert "Неверный запрос" in cb.message.edits[-1]


async def test_cb_notes_storm_happy(monkeypatch):
    from services import ai_engine
    from services import brainstorm as bs

    na._notes_list_store[4242] = {
        "items": [{"id": "AAA", "name": "Ночные сны", "folder": ""}], "text": "",
    }

    def fake_read(note_id):
        return {"name": "Ночные сны", "body": "парящие дома"}

    monkeypatch.setattr("services.apple_notes.read_note", fake_read)
    monkeypatch.setattr(ai_engine, "get_current_ai", lambda: ("fake", "model"))
    monkeypatch.setattr(bs, "collect_context", lambda *a, **k: _fake_coro({}))

    async def fake_response(engine, model, msgs, **kwargs):
        return ('{"ideas": [{"title": "Т", "camera_setup": "Имитация плёнки ACROS, тени -2", '
                '"reason": "р", "steps": "s"}]}')

    monkeypatch.setattr(ai_engine, "get_ai_response_async", fake_response)

    cb = FakeCbLite(4242, "notes_storm:0")
    await na.cb_notes_storm(cb)
    assert not cb.message.edits, "заметка НЕ заменяется штурмом"
    assert cb.message.last_answer is not None, "штурм уходит в новое сообщение"
    joined = "\n".join(cb.message.last_answer.edits)
    assert "Сюрреалистичный штурм" in joined
    assert "ACROS" in joined


async def test_cb_notes_storm_injects_note_text_as_context(monkeypatch):
    from services import ai_engine
    from services import brainstorm as bs

    na._notes_list_store[4242] = {
        "items": [{"id": "AAA", "name": "Фудзи", "folder": ""}], "text": "",
    }
    captured = {}

    def fake_read(note_id):
        return {"name": "Фудзи", "body": "вид на гору в тумане"}

    monkeypatch.setattr("services.apple_notes.read_note", fake_read)
    monkeypatch.setattr(ai_engine, "get_current_ai", lambda: ("fake", "model"))
    monkeypatch.setattr(bs, "collect_context", lambda *a, **k: _fake_coro({}))

    async def fake_response(engine, model, msgs, **kwargs):
        captured["msgs"] = msgs
        return ('{"ideas": [{"title": "Т", "camera_setup": "Имитация плёнки ACROS, тени -2", '
                '"reason": "р", "steps": "s"}]}')

    monkeypatch.setattr(ai_engine, "get_ai_response_async", fake_response)

    cb = FakeCbLite(4242, "notes_storm:0")
    await na.cb_notes_storm(cb)
    assert any("вид на гору в тумане" in str(m) for m in captured.get("msgs", [])), \
        "текст заметки попадает в контекст штурма"


async def test_cb_notes_storm_empty_body(monkeypatch):
    na._notes_list_store[4242] = {
        "items": [{"id": "AAA", "name": "Пустая", "folder": ""}], "text": "",
    }

    def fake_read(note_id):
        return {"name": "Пустая", "body": ""}

    monkeypatch.setattr("services.apple_notes.read_note", fake_read)

    cb = FakeCbLite(4242, "notes_storm:0")
    await na.cb_notes_storm(cb)
    assert "Текст заметки недоступен" in cb.message.edits[-1]


async def test_cb_notes_storm_read_failure(monkeypatch):
    na._notes_list_store[4242] = {
        "items": [{"id": "AAA", "name": "Сломана", "folder": ""}], "text": "",
    }

    def boom(note_id):
        raise RuntimeError("osascript down")

    monkeypatch.setattr("services.apple_notes.read_note", boom)

    cb = FakeCbLite(4242, "notes_storm:0")
    await na.cb_notes_storm(cb)
    assert "Текст заметки недоступен" in cb.message.edits[-1]


async def test_cb_notes_storm_stale_list():
    cb = FakeCbLite(4242, "notes_storm:0")
    await na.cb_notes_storm(cb)
    assert "устарел" in cb.message.edits[-1]


async def test_cb_notes_save_happy(monkeypatch):
    from handlers.palace import _save_state

    na._notes_list_store[4242] = {
        "items": [{"id": "AAA", "name": "Идея", "folder": ""}], "text": "",
    }

    def fake_read(note_id):
        return {"name": "Идея", "body": "снять на плёнку"}

    monkeypatch.setattr("services.apple_notes.read_note", fake_read)

    async def fake_save_wings(edit_func, uid):
        await edit_func("выбери крыло", parse_mode="HTML")

    monkeypatch.setattr("handlers.palace._show_save_wings", fake_save_wings)

    cb = FakeCbLite(4242, "notes_save:0")
    await na.cb_notes_save(cb)
    state = _save_state.get(4242)
    assert state is not None, "сохранение из заметки заполняет _save_state"
    assert "снять на плёнку" in state["text"]
    assert "Идея" in state["text"]
    assert state["mode"] == "full"
    assert not cb.message.edits, "заметка НЕ заменяется мастером сохранения"
    assert cb.message.last_answer is not None, \
        "выбор крыла уходит в новое сообщение"
    _save_state.pop(4242, None)


async def test_cb_notes_save_empty_body(monkeypatch):
    from handlers.palace import _save_state

    na._notes_list_store[4242] = {
        "items": [{"id": "AAA", "name": "Пусто", "folder": ""}], "text": "",
    }

    def fake_read(note_id):
        return {"name": "Пусто", "body": "   "}

    monkeypatch.setattr("services.apple_notes.read_note", fake_read)

    cb = FakeCbLite(4242, "notes_save:0")
    await na.cb_notes_save(cb)
    assert "Текст заметки недоступен" in cb.message.edits[-1]
    assert 4242 not in _save_state


async def test_cb_notes_save_stale_list():
    from handlers.palace import _save_state

    cb = FakeCbLite(4242, "notes_save:0")
    await na.cb_notes_save(cb)
    assert "устарел" in cb.message.edits[-1]
    assert 4242 not in _save_state


async def test_cb_notes_actions_not_allowed(monkeypatch):
    na._notes_list_store[777] = {"items": [{"id": "A", "name": "x"}], "text": ""}
    na._notes_view_store[777] = {
        "idx": 0, "name": "x", "folder": "",
        "pages": ["a", "b"], "page": 0,
    }
    handlers = {
        "notes_storm:0": na.cb_notes_storm,
        "notes_discuss:0": na.cb_notes_discuss,
        "notes_save:0": na.cb_notes_save,
        "notes_stop:0": na.cb_notes_stop,
        "notes_page:0:1": na.cb_notes_page,
        "notes_back:0": na.cb_notes_back,
    }
    for data, handler in handlers.items():
        cb = FakeCbLite(777, data)
        await handler(cb)
        assert not cb.message.edits, f"{data}: неавторизованный ничего не получает"
