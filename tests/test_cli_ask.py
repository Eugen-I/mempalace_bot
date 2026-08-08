"""Unit tests for cli_ask.py — главный цикл выбора чатов.

Модуль cli_ask при импорте может выполнить os.execv (auto-activate venv),
поэтому он загружается внутри фикстуры с временным патчем os.path.exists.
"""

import asyncio
import importlib
import os
from types import SimpleNamespace

import pytest


class FakePromptSession:
    _queue = []

    def __init__(self, responses=None, **kwargs):
        if responses is None:
            responses = self._queue.pop(0) if self._queue else []
        self.responses = list(responses)
        self.prompts = []

    @classmethod
    def feed(cls, responses):
        cls._queue.append(list(responses))

    async def prompt_async(self, html, **kwargs):
        self.prompts.append(html)
        if not self.responses:
            raise EOFError()
        return self.responses.pop(0)


class FakeKeyBindings:
    def __init__(self):
        self.handlers = {}

    def add(self, key):
        def deco(fn):
            self.handlers[key] = fn
            return fn
        return deco


@pytest.fixture
def cli_ask_mod(monkeypatch):
    real_exists = os.path.exists
    venv_python = os.path.expanduser("~/Documents/mempalace/venv/bin/python3")

    def fake_exists(path):
        if path == venv_python:
            return False
        return real_exists(path)

    monkeypatch.setattr(os.path, "exists", fake_exists)
    mod = importlib.import_module("cli_ask")
    monkeypatch.setattr(mod, "PromptSession", FakePromptSession)
    monkeypatch.setattr(mod, "KeyBindings", FakeKeyBindings)
    return mod


@pytest.fixture
def ask_env(tmp_path, monkeypatch, cli_ask_mod):
    chats_dir = tmp_path / "chats"
    chats_dir.mkdir()
    for name in ("ch_first.json", "ch_second.json"):
        (chats_dir / name).write_text("{}")
    monkeypatch.setattr(cli_ask_mod, "CHATS_DIR", str(chats_dir))
    monkeypatch.setattr(
        cli_ask_mod, "list_chats",
        lambda: ["ch_first.json", "ch_second.json"],
    )
    monkeypatch.setattr(cli_ask_mod, "get_current_ai", lambda: ("e", "m"))
    return {"chats_dir": chats_dir, "mod": cli_ask_mod}


def run_main(ask_env, responses):
    FakePromptSession.feed(responses)
    return asyncio.run(ask_env["mod"].main())


def test_main_quit_immediately(ask_env, capsys):
    assert run_main(ask_env, ["q"]) is None
    out = capsys.readouterr().out
    assert "До свидания" in out and "Меню чатов" in out


def test_main_eof(ask_env, capsys):
    run_main(ask_env, [])
    assert "Выход." in capsys.readouterr().out


def test_main_new_chat(ask_env, monkeypatch):
    mod = ask_env["mod"]
    created = []
    monkeypatch.setattr(
        mod, "create_new_chat",
        lambda: created.append("path") or str(ask_env["chats_dir"] / "ch_new.json"),
    )
    results = []
    monkeypatch.setattr(
        mod, "chat_loop",
        lambda p, s: results.append((p, s)) or _async_val("new")(p, s),
    )
    run_main(ask_env, ["new", "q"])
    assert created == ["path"]
    assert results[0][0].endswith("ch_new.json")


def test_main_open_chat_number(ask_env, monkeypatch):
    mod = ask_env["mod"]
    results = []
    monkeypatch.setattr(
        mod, "chat_loop",
        lambda p, s: results.append(p) or _async_val("quit")(p, s),
    )
    run_main(ask_env, ["2"])
    assert results[0].endswith("ch_second.json")


def test_main_open_chat_bad_number(ask_env, monkeypatch, capsys):
    monkeypatch.setattr(
        ask_env["mod"], "chat_loop", lambda p, s: _async_val(None)(p, s),
    )
    run_main(ask_env, ["9", "q"])
    assert "Неверный номер" in capsys.readouterr().out


def test_main_delete_chat(ask_env, monkeypatch, capsys):
    mod = ask_env["mod"]
    removed = []
    monkeypatch.setattr(os, "remove", lambda p: removed.append(p))
    monkeypatch.setattr(mod, "chat_loop", lambda p, s: _async_val(None)(p, s))
    run_main(ask_env, ["d 1", "q"])
    assert removed and removed[0].endswith("ch_first.json")
    assert "Чат удален" in capsys.readouterr().out


def test_main_delete_bad_index(ask_env, monkeypatch, capsys):
    mod = ask_env["mod"]
    removed = []
    monkeypatch.setattr(os, "remove", lambda p: removed.append(p))
    monkeypatch.setattr(mod, "chat_loop", lambda p, s: _async_val(None)(p, s))
    run_main(ask_env, ["d 9", "q"])
    assert removed == []
    assert "Неверный номер" in capsys.readouterr().out


def test_main_delete_bad_format(ask_env, monkeypatch, capsys):
    mod = ask_env["mod"]
    monkeypatch.setattr(mod, "chat_loop", lambda p, s: _async_val(None)(p, s))
    run_main(ask_env, ["d abc", "q"])
    assert "Неверный номер" in capsys.readouterr().out


def test_main_unknown_choice(ask_env, capsys):
    run_main(ask_env, ["xyz", "q"])
    assert "Неверный ввод" in capsys.readouterr().out


def test_main_chat_loop_deleted_returns_to_menu(ask_env, monkeypatch):
    monkeypatch.setattr(
        ask_env["mod"], "chat_loop", lambda p, s: _async_val("deleted")(p, s),
    )
    run_main(ask_env, ["1", "q"])
    assert ask_env["mod"].CHATS_DIR


def test_main_key_bindings_handlers(ask_env, monkeypatch):
    mod = ask_env["mod"]
    bindings = FakeKeyBindings()
    monkeypatch.setattr(mod, "KeyBindings", lambda: bindings)

    async def fake_loop(p, s):
        return "quit"

    monkeypatch.setattr(mod, "chat_loop", fake_loop)
    monkeypatch.setattr(mod, "list_chats", lambda: [])
    FakePromptSession.feed(["q"])
    asyncio.run(mod.main())
    exited = []

    class FakeApp:
        def exit(self, result=None):
            exited.append(result)

    event = SimpleNamespace(app=FakeApp())
    bindings.handlers["c-c"](event)
    bindings.handlers["c-d"](event)
    assert exited == [KeyboardInterrupt, KeyboardInterrupt]


def test_main_chat_loop_chats_result(ask_env, monkeypatch):
    async def fake_loop(p, s):
        return "chats"

    monkeypatch.setattr(ask_env["mod"], "chat_loop", fake_loop)
    run_main(ask_env, ["1", "q"])
    assert ask_env["mod"].CHATS_DIR


def test_main_no_chats(ask_env, monkeypatch, capsys):
    monkeypatch.setattr(ask_env["mod"], "list_chats", lambda: [])
    run_main(ask_env, ["q"])
    assert "Чатов нет" in capsys.readouterr().out


def test_execv_venv_branch(monkeypatch):
    real_exists = os.path.exists
    venv_python = os.path.expanduser("~/Documents/mempalace/venv/bin/python3")
    execv_calls = []
    monkeypatch.setattr(os, "execv", lambda *a: execv_calls.append(a))
    monkeypatch.setattr(
        os.path, "exists",
        lambda p: p == venv_python or real_exists(p),
    )
    import cli_ask
    importlib.reload(cli_ask)
    assert execv_calls
    assert execv_calls[0][1][0] == venv_python


def _async_val(value):
    async def _inner(*a, **k):
        return value
    return _inner
