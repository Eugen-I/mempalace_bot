"""Unit tests for cli/dialog.py — CLICompleter и chat_loop."""

import asyncio
import json
from types import SimpleNamespace

import pytest

import cli.dialog as dialog
from cli.dialog import CLICompleter


class FakeDoc:
    def __init__(self, text):
        self.text_before_cursor = text


def completions_of(text):
    comp = CLICompleter()
    return [c.text for c in comp.get_completions(FakeDoc(text), None)]


def test_completer_tunnels_subcommands():
    out = completions_of("/tunnels li")
    assert "list" in out and "create" not in out


def test_completer_commands():
    out = completions_of("/sea")
    assert "/search" in out
    assert all(c.startswith("/sea") for c in out)


def test_completer_sound():
    out = completions_of("звук-1")
    assert "звук-100" in out and "звук-150" in out


def test_completer_other_text_no_completions():
    assert completions_of("просто текст") == []


def test_completer_no_slash():
    out = completions_of("")
    assert "/help" not in out


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    async def prompt_async(self, html, completer=None):
        self.prompts.append(html)
        if not self.responses:
            raise EOFError()
        return self.responses.pop(0)


@pytest.fixture
def loop_env(tmp_path, monkeypatch):
    chat_path = str(tmp_path / "chat.json")
    with open(chat_path, "w", encoding="utf-8") as f:
        json.dump({"summary": "", "messages": [], "summaries": []}, f)
    monkeypatch.setattr(dialog, "get_current_ai", lambda: ("e", "m"))
    monkeypatch.setattr(dialog, "get_cli_voice",
                        lambda: {"enabled": True, "speed": 160, "voice": "M"})
    calls = []

    def make(name):
        async def fake(*a, **k):
            calls.append(name)
            return None
        return fake

    for fn_name in [
        "cmd_photos", "cmd_analyze_photo", "cmd_sound_toggle", "cmd_sound_speed",
        "cmd_history", "cmd_export", "cmd_search", "cmd_status", "cmd_mcp",
        "cmd_wakeup", "cmd_repair", "cmd_compact", "cmd_compress", "cmd_palace",
        "cmd_wings", "cmd_rooms", "cmd_taxonomy", "cmd_graph", "cmd_traverse",
        "cmd_tunnels", "cmd_follow", "cmd_kg", "cmd_kgstats", "cmd_enrich",
        "cmd_sync", "cmd_remind", "cmd_pdfs", "cmd_yt", "cmd_transkript",
        "cmd_kgadd", "cmd_settings", "cmd_web", "save_quick_note",
        "save_extraction", "process_ai_query",
    ]:
        monkeypatch.setattr(dialog, fn_name, make(fn_name))
    return {"path": chat_path, "calls": calls, "tmp": tmp_path}


def run_loop(env, responses):
    return asyncio.run(dialog.chat_loop(env["path"], FakeSession(responses)))


# ─── базовые команды ───


def test_loop_quit_saves(loop_env):
    env = loop_env
    assert run_loop(env, ["q"]) == "quit"
    assert env["calls"] == []


def test_loop_photos(loop_env):
    env = loop_env
    assert run_loop(env, ["/photos", "q"]) == "quit"
    assert env["calls"] == ["cmd_photos"]


def test_loop_analyze_photo(loop_env):
    env = loop_env
    run_loop(env, ["/analyze_photo", "q"])
    assert "cmd_analyze_photo" in env["calls"]


def test_loop_sound_toggle(loop_env):
    env = loop_env
    run_loop(env, ["звук", "/звук", "q"])
    assert env["calls"].count("cmd_sound_toggle") == 2


def test_loop_sound_speed(loop_env):
    env = loop_env
    run_loop(env, ["звук-150", "q"])
    assert "cmd_sound_speed" in env["calls"]


@pytest.mark.parametrize("quit_cmd", ["й", "quit", "exit", "выход"])
def test_loop_quit_variants(loop_env, quit_cmd):
    assert run_loop(loop_env, [quit_cmd]) == "quit"


def test_loop_help_and_sections(loop_env, monkeypatch, capsys):
    shown = []
    monkeypatch.setattr("cli.help_sections.show_help", lambda: shown.append("help"))
    monkeypatch.setattr("cli.help_sections.show_section", lambda k: shown.append(k))
    monkeypatch.setattr("cli.help_sections.show_all_help", lambda: shown.append("all"))
    run_loop(loop_env, ["h", "2", "0", "h 3", "h 0", "h 99", "q"])
    assert shown == ["help", "2", "all", "3", "all"]
    assert "Неизвестный раздел" in capsys.readouterr().out


def test_loop_history_export_search(loop_env):
    env = loop_env
    run_loop(env, ["/history", "/export", "/search сон", "q"])
    assert env["calls"][:3] == ["cmd_history", "cmd_export", "cmd_search"]


@pytest.mark.parametrize(
    "cmd", [
        "/status", "/mcp", "/wakeup", "/repair", "/compact", "/compress",
        "/palace", "/wings", "/rooms", "/taxonomy", "/graph", "/traverse",
        "/tunnels list", "/follow dreams A", "/kg сон", "/enrich", "/kgstats",
        "/sync", "/remind завтра", "/pdfs", "/transkript 1", "/yt url",
        "/ytaudio url", "/kgadd a b c", "/settings", "/web запрос",
    ],
)
def test_loop_palace_commands(loop_env, cmd):
    env = loop_env
    run_loop(env, [cmd, "q"])
    called = env["calls"][0]
    expected_map = {
        "/status": "cmd_status", "/mcp": "cmd_mcp", "/wakeup": "cmd_wakeup",
        "/repair": "cmd_repair", "/compact": "cmd_compact",
        "/compress": "cmd_compress", "/palace": "cmd_palace",
        "/wings": "cmd_wings", "/rooms": "cmd_rooms", "/taxonomy": "cmd_taxonomy",
        "/graph": "cmd_graph", "/traverse": "cmd_traverse",
        "/tunnels list": "cmd_tunnels", "/follow dreams A": "cmd_follow",
        "/kg сон": "cmd_kg", "/enrich": "cmd_enrich", "/kgstats": "cmd_kgstats",
        "/sync": "cmd_sync", "/remind завтра": "cmd_remind",
        "/pdfs": "cmd_pdfs", "/transkript 1": "cmd_transkript",
        "/yt url": "cmd_yt", "/ytaudio url": "cmd_yt",
        "/kgadd a b c": "cmd_kgadd", "/settings": "cmd_settings",
        "/web запрос": "cmd_web",
    }
    assert called == expected_map[cmd]


def test_loop_web_prompt_fallback(loop_env, monkeypatch, capsys):
    env = loop_env
    result = asyncio.run(
        dialog.chat_loop(env["path"], FakeSession(["/web", "поиск", "q"]))
    )
    assert result == "quit"
    assert env["calls"].count("cmd_web") == 1


def test_loop_web_empty_cancelled(loop_env, monkeypatch, capsys):
    env = loop_env
    asyncio.run(dialog.chat_loop(env["path"], FakeSession(["/web", "", "q"])))
    assert "Отменено." in capsys.readouterr().out


def test_loop_del(loop_env):
    env = loop_env
    assert run_loop(env, ["/del"]) == "deleted"
    import os
    assert not os.path.exists(env["path"])


def test_loop_del_missing_file(loop_env, capsys):
    env = loop_env
    import os
    os.remove(env["path"])
    result = run_loop(env, ["/del", "q"])
    assert result == "quit"


def test_loop_new_and_chats(loop_env):
    env = loop_env
    assert run_loop(env, ["/new"]) == "new"
    assert run_loop(env, ["/chats"]) == "chats"


def test_loop_context_with_summary(loop_env, capsys):
    env = loop_env
    with open(env["path"], "w", encoding="utf-8") as f:
        json.dump({
            "summary": "", "messages": [],
            "summaries": ["Длинное саммари " + "x" * 600],
        }, f)
    run_loop(env, ["~", "q"])
    out = capsys.readouterr().out
    assert "Контекст чата" in out and "..." in out


def test_loop_context_empty_summary(loop_env, capsys):
    env = loop_env
    run_loop(env, ["#ctx", "q"])
    assert "Саммари пусто." in capsys.readouterr().out


def test_loop_quick_note(loop_env):
    env = loop_env
    run_loop(env, ["! заметка", "q"])
    assert "save_quick_note" in env["calls"]


def test_loop_save_extraction(loop_env):
    env = loop_env
    with open(env["path"], "w", encoding="utf-8") as f:
        json.dump({
            "summary": "", "summaries": [],
            "messages": [{"role": "assistant", "content": "ответ"}],
        }, f)
    run_loop(env, ["!!", "??", "???", "q"])
    assert env["calls"].count("save_extraction") == 2


def test_loop_extraction_no_last_ai(loop_env):
    env = loop_env
    run_loop(env, ["!!", "q"])
    assert "save_extraction" not in env["calls"]


def test_loop_noise_guard(loop_env, capsys):
    env = loop_env
    run_loop(env, ["a", "q"])
    out = capsys.readouterr().out
    assert "Слишком короткий ввод" in out
    assert "process_ai_query" not in env["calls"]


def test_loop_empty_input_skipped(loop_env):
    env = loop_env
    run_loop(env, ["", "q"])
    assert env["calls"] == []


def test_loop_ai_query(loop_env):
    env = loop_env
    run_loop(env, ["расскажи о снах", "q"])
    assert "process_ai_query" in env["calls"]


def test_key_bindings_c_c_and_c_r(monkeypatch):
    from cli.dialog import bindings
    from prompt_toolkit.keys import Keys

    c_c = bindings.get_bindings_for_keys((Keys.ControlC,))
    c_r = bindings.get_bindings_for_keys((Keys.ControlR,))
    assert len(c_c) == 1 and len(c_r) == 1

    exited = []

    class FakeApp:
        def exit(self, result=None):
            exited.append(result)

    event = SimpleNamespace(app=FakeApp())
    c_c[0].handler(event)
    assert exited == [KeyboardInterrupt]
    c_r[0].handler(event)
    assert exited == [KeyboardInterrupt]


def test_loop_eof_exits(loop_env, capsys):
    env = loop_env
    assert run_loop(env, []) == "quit"
    assert "Завершение" in capsys.readouterr().out
