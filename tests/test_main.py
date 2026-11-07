"""Unit tests for main.py — bootstrapping, кнопки-обработчики, main()."""

import asyncio
import importlib
import sys

import pytest

import config
import main
from services import chat_sync


@pytest.fixture(autouse=True)
def _allow_test_user(monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_IDS", {4242, 4243})
    yield


@pytest.fixture(autouse=True)
def _no_ollama_prewarm(monkeypatch):
    """По умолчанию не запускаем реальный prewarm Ollama."""
    monkeypatch.setattr(
        "services.ai_engine.get_current_ai",
        lambda: ("gemini", "gemini-flash-latest"),
    )


class FakeUser:
    def __init__(self, uid=4242):
        self.id = uid


class FakeMessage:
    def __init__(self, uid=4242):
        self.from_user = FakeUser(uid)
        self.answers = []
        self.edits = []

    async def answer(self, text, reply_markup=None, **kwargs):
        self.answers.append((text, reply_markup))
        return self

    async def edit_text(self, text, **kwargs):
        self.edits.append(text)


class FakeCallback:
    def __init__(self, uid=4242):
        self.from_user = FakeUser(uid)
        self.message = FakeMessage(uid)
        self.answered = 0

    async def answer(self, **kwargs):
        self.answered += 1


# ─── _safe_include ───


def test_import_guard_exits_on_bad_config(monkeypatch, capsys):
    monkeypatch.setattr(config, "API_TOKEN", "your_telegram_bot_token")
    monkeypatch.setattr(config, "ADMIN_ID", 0)
    exits = []

    def fake_exit(code=0):
        exits.append(code)
        raise SystemExit(code)

    monkeypatch.setattr(sys, "exit", fake_exit)
    with pytest.raises(SystemExit):
        importlib.reload(importlib.import_module("main"))
    assert exits == [1]
    assert "TELEGRAM_BOT_TOKEN" in capsys.readouterr().out


def test_import_guard_exits_on_missing_token(monkeypatch, capsys):
    monkeypatch.setattr(config, "API_TOKEN", "")
    monkeypatch.setattr(config, "ADMIN_ID", 4242)
    exits = []

    def fake_exit(code=0):
        exits.append(code)
        raise SystemExit(code)

    monkeypatch.setattr(sys, "exit", fake_exit)
    with pytest.raises(SystemExit):
        importlib.reload(importlib.import_module("main"))
    assert exits == [1]
    output = capsys.readouterr().out
    assert "TELEGRAM_BOT_TOKEN" in output
    assert config.PROJECT_ENV_PATH in output
    assert config.LEGACY_ENV_PATH in output


def test_safe_include_success(monkeypatch):
    included = []
    monkeypatch.setattr(
        main.dp, "include_router", lambda router: included.append(router)
    )
    main._safe_include("fake_router")
    assert included == ["fake_router"]


def test_safe_include_swallows_runtime_error(monkeypatch, caplog):
    def boom(router):
        raise RuntimeError("already included")

    monkeypatch.setattr(main.dp, "include_router", boom)
    main._safe_include("fake_router")


# ─── cmd_start ───


def test_cmd_start_answers_with_keyboard(monkeypatch, caplog):
    msg = FakeMessage()
    asyncio.run(main.cmd_start(msg))
    assert len(msg.answers) == 1
    text, kb = msg.answers[0]
    assert "🦾 <b>MemPalace запущен.</b>" in text
    assert kb is not None
    assert "⚙️ Настройки" in repr(kb)
    assert any("started" in r.getMessage() for r in caplog.records)


# ─── cmd_palace_button ───


def test_cmd_palace_button_delegates(monkeypatch):
    called = []

    async def fake_cmd_palace(message):
        called.append(message)

    monkeypatch.setattr("handlers.palace.cmd_palace", fake_cmd_palace)
    msg = FakeMessage()
    asyncio.run(main.cmd_palace_button(msg))
    assert called == [msg]


# ─── cmd_sync_button ───


def test_cmd_sync_button_no_active_chat(monkeypatch):
    monkeypatch.setattr(main, "user_sessions", {})
    msg = FakeMessage()
    asyncio.run(main.cmd_sync_button(msg))
    assert msg.answers[0][0] == "⚠️ Нет активного чата для синхронизации."


def test_cmd_sync_button_empty_chat(monkeypatch):
    monkeypatch.setitem(main.user_sessions, 4242, "chat.json")
    monkeypatch.setattr(chat_sync, "export_chat_verbatim", lambda path, fname: None)
    msg = FakeMessage()
    asyncio.run(main.cmd_sync_button(msg))
    assert msg.answers[0][0] == "ℹ️ Чат пуст или не найден."


def test_cmd_sync_button_success(monkeypatch):
    monkeypatch.setitem(main.user_sessions, 4242, "chat.json")
    monkeypatch.setattr(chat_sync, "export_chat_verbatim", lambda path, fname: "exported")

    async def fake_sync(exported):
        return "✅ Синхронизировано"

    monkeypatch.setattr(chat_sync, "sync_to_palace", fake_sync)
    msg = FakeMessage()
    asyncio.run(main.cmd_sync_button(msg))
    assert msg.answers[0][0] == "🔄 Синхронизирую с MemPalace (verbatim)..."
    assert msg.edits == ["✅ Синхронизировано"]


# ─── cmd_search_button ───


def test_cmd_search_button_builds_kb():
    msg = FakeMessage()
    asyncio.run(main.cmd_search_button(msg))
    text, kb = msg.answers[0]
    assert text == "Выберите тип поиска:"
    assert "search:wing" in repr(kb)


# ─── cb_search_wing ───


def test_cb_search_wing_delegates(monkeypatch):
    called = []

    async def fake_prompt(message):
        called.append(message)

    monkeypatch.setattr("handlers.search.cmd_wing_search_prompt", fake_prompt)
    cb = FakeCallback()
    asyncio.run(main.cb_search_wing(cb))
    assert called == [cb.message]
    assert cb.answered == 1


# ─── cb_search_web ───


def test_cb_search_web_sets_pending(monkeypatch):
    pending = {}
    monkeypatch.setattr("services.bot_setup.pending_web_search", pending)
    cb = FakeCallback(uid=4242)
    asyncio.run(main.cb_search_web(cb))
    assert pending == {4242: True}
    assert cb.answered == 1
    assert cb.message.answers[0][0].startswith("🔍 Введите запрос")


# ─── main() ───


def _main_mocks(monkeypatch):
    class FakeBot:
        async def delete_webhook(self, drop_pending_updates=None):
            return True

    class FakeMCP:
        async def start(self):
            return None

    class FakeDP:
        async def start_polling(self, bot, allowed_updates=None):
            return None

    monkeypatch.setattr(main, "bot", FakeBot())
    monkeypatch.setattr(main, "dp", FakeDP())
    monkeypatch.setattr(main, "get_mcp", lambda: FakeMCP())
    return FakeMCP()


def test_main_run(monkeypatch):
    _main_mocks(monkeypatch)
    started = []
    prewarmed = []
    monkeypatch.setattr(
        "services.whisper_service.prewarm",
        lambda: prewarmed.append(1),
    )
    monkeypatch.setattr(
        "services.reminder_scheduler.start_scheduler",
        lambda bot: started.append(bot),
    )
    asyncio.run(main.main())
    assert started
    assert prewarmed == [1]


def test_main_mcp_failure_continues(monkeypatch, caplog):
    _main_mocks(monkeypatch)

    class BrokenMCP:
        async def start(self):
            raise RuntimeError("no server")

    monkeypatch.setattr(main, "get_mcp", lambda: BrokenMCP())
    monkeypatch.setattr("services.whisper_service.prewarm", lambda: None)
    monkeypatch.setattr(
        "services.reminder_scheduler.start_scheduler", lambda bot: None
    )
    asyncio.run(main.main())
    assert any("MCP client failed" in r.getMessage() for r in caplog.records)


def test_main_prewarm_failure_continues(monkeypatch, caplog):
    _main_mocks(monkeypatch)

    def boom():
        raise RuntimeError("model too big")

    monkeypatch.setattr("services.whisper_service.prewarm", boom)
    monkeypatch.setattr(
        "services.reminder_scheduler.start_scheduler", lambda bot: None
    )
    asyncio.run(main.main())
    assert any("Whisper pre-warm failed" in r.getMessage() for r in caplog.records)


# ─── main(): prewarm Ollama ───


def _ollama_fake_thread(monkeypatch):
    class FakeThread:
        def __init__(self, target=None, daemon=False):
            self.target = target
            self.daemon = daemon

        def start(self):
            self.target()

    monkeypatch.setattr("threading.Thread", FakeThread)
    return FakeThread


def test_main_ollama_prewarm_started_for_qwen(monkeypatch):
    _main_mocks(monkeypatch)
    prewarmed = []
    ensured = []
    monkeypatch.setattr("services.whisper_service.prewarm", lambda: prewarmed.append(1))
    monkeypatch.setattr(
        "services.reminder_scheduler.start_scheduler", lambda bot: None,
    )
    monkeypatch.setattr(
        "services.ai_engine.get_current_ai", lambda: ("qwen", "qwen2.5:7b"),
    )
    monkeypatch.setattr(
        "services.ollama_process.ensure_ollama_running",
        lambda model="qwen2.5:7b": ensured.append(model),
    )
    _ollama_fake_thread(monkeypatch)
    asyncio.run(main.main())
    assert ensured == ["qwen2.5:7b"]
    assert prewarmed == [1]


def test_main_ollama_prewarm_failure_continues(monkeypatch, caplog):
    _main_mocks(monkeypatch)
    monkeypatch.setattr("services.whisper_service.prewarm", lambda: None)
    monkeypatch.setattr(
        "services.reminder_scheduler.start_scheduler", lambda bot: None,
    )
    monkeypatch.setattr(
        "services.ai_engine.get_current_ai", lambda: ("qwen", "qwen2.5:7b"),
    )

    def boom(model="qwen2.5:7b"):
        raise RuntimeError("no server")

    monkeypatch.setattr("services.ollama_process.ensure_ollama_running", boom)
    _ollama_fake_thread(monkeypatch)
    asyncio.run(main.main())
    assert any("Ollama pre-warm failed" in r.getMessage() for r in caplog.records)


def test_main_ollama_prewarm_skipped_for_gemini(monkeypatch):
    _main_mocks(monkeypatch)
    monkeypatch.setattr("services.whisper_service.prewarm", lambda: None)
    monkeypatch.setattr(
        "services.reminder_scheduler.start_scheduler", lambda bot: None,
    )
    monkeypatch.setattr(
        "services.ai_engine.get_current_ai", lambda: ("gemini", "gemini-flash-latest"),
    )

    def fake_ensure(model="qwen2.5:7b"):
        raise AssertionError("ensure не должен вызываться для gemini")

    monkeypatch.setattr("services.ollama_process.ensure_ollama_running", fake_ensure)
    asyncio.run(main.main())


def test_main_calls_stop_all_on_shutdown(monkeypatch):
    _main_mocks(monkeypatch)
    monkeypatch.setattr("services.whisper_service.prewarm", lambda: None)
    monkeypatch.setattr(
        "services.reminder_scheduler.start_scheduler", lambda bot: None,
    )
    stopped = []
    monkeypatch.setattr(
        "services.ollama_process.stop_all", lambda: stopped.append(1),
    )
    asyncio.run(main.main())
    assert stopped == [1]
