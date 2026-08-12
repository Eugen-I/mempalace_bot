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

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append(text)
        return text

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)


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
    yield
    na._pending_confirm.clear()
    na._waiting_for_notes_input.clear()


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
    text = na._describe_action("notes_create", {"title": "<b>X</b>", "text": "<i>Y</i>"})
    assert "<b>X</b>" not in text
    assert "&lt;b&gt;X&lt;/b&gt;" in text


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

    async def fake_finalize(uid, edit, answer, ctx=None, title=""):
        fake_finalize.args = (uid, answer, ctx, title)

    monkeypatch.setattr(na.ae, "run_agent", fake_run_agent)
    monkeypatch.setattr(action_bar, "finalize_answer", fake_finalize)

    status = FakeStatus()
    await na._run_notes_agent_reply(4242, status, "найди про фудзи")
    assert calls[0]["allowed_categories"] == (na.CAT_NOTES,)
    assert calls[0]["include_write"] is True
    assert callable(calls[0]["confirm_write"])
    assert fake_finalize.args[1] == "Вот ваша заметка"
    assert fake_finalize.args[3] == "<b>📝 Apple Notes</b>"


async def test_run_notes_agent_engine_error(monkeypatch):
    async def boom(*args, **kwargs):
        raise na.ae.AgentEngineError("Агентный режим работает только с Ollama")

    monkeypatch.setattr(na.ae, "run_agent", boom)
    status = FakeStatus()
    await na._run_notes_agent_reply(4242, status, "вопрос")
    assert "только с Ollama" in status.edits[-1]


async def test_run_notes_agent_unexpected_error(monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("поломка")

    monkeypatch.setattr(na.ae, "run_agent", boom)
    status = FakeStatus()
    await na._run_notes_agent_reply(4242, status, "вопрос")
    assert "поломка" in status.edits[-1]


async def test_run_notes_agent_error_result(monkeypatch):
    async def fake_run_agent(*args, **kwargs):
        return na.ae.AgentResult(
            final_answer="", finished_reason="error", error="Модель вернула пустой ответ.",
        )

    monkeypatch.setattr(na.ae, "run_agent", fake_run_agent)
    status = FakeStatus()
    await na._run_notes_agent_reply(4242, status, "вопрос")
    assert "Модель вернула пустой ответ" in status.edits[-1]


async def test_run_notes_agent_max_iterations(monkeypatch):
    async def fake_run_agent(*args, **kwargs):
        return na.ae.AgentResult(
            final_answer="", finished_reason="max_iterations",
            error="Достигнут лимит итераций агента (5).",
        )

    monkeypatch.setattr(na.ae, "run_agent", fake_run_agent)
    status = FakeStatus()
    await na._run_notes_agent_reply(4242, status, "вопрос")
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
    from services import brainstorm as bs
    from services import ai_engine

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
    from services import brainstorm as bs
    from services import ai_engine

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


async def test_run_surreal_storm_rejects_ideas_without_camera_setup(monkeypatch):
    from services import brainstorm as bs
    from services import ai_engine

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


# ─── run_notes_agent: маршрутизация в сюрреалистичный штурм ───


async def test_run_notes_agent_routes_to_surreal_storm(monkeypatch):
    from services import brainstorm as bs
    from services import ai_engine

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
