"""Unit tests for cli/utils.py"""

import asyncio
import json
import os
import subprocess

import pytest

import cli.utils as utils
from cli.utils import C


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "CHATS_DIR", str(tmp_path / "chats"))
    monkeypatch.setattr(utils, "VOICE_REPLY_CONFIG", str(tmp_path / "voice.json"))
    return tmp_path


# ─── format_for_terminal ───


def test_format_for_terminal_empty():
    assert utils.format_for_terminal("") == ""
    assert utils.format_for_terminal(None) == ""


def test_format_for_terminal_bold_italic_code():
    out = utils.format_for_terminal("**b** *i* `c`")
    assert f"{C.BOLD}b{C.END}" in out
    assert f"{C.ITALIC}i{C.END}" in out
    assert f"{C.CYAN}c{C.END}" in out
    assert "**" not in out and "*i*" not in out


def test_format_for_terminal_header_and_link():
    out = utils.format_for_terminal("# Title\n[text](http://x)")
    assert f"{C.BOLD}{C.YELLOW}Title{C.END}" in out
    assert "text" in out and "(http://x)" not in out


# ─── speak_text ───


def test_speak_text_disabled_or_empty(monkeypatch):
    called = []
    monkeypatch.setattr(
        subprocess, "Popen", lambda *a, **k: called.append(a),
    )
    utils.speak_text("", enabled=True)
    utils.speak_text("hi", enabled=False)
    assert called == []


def test_speak_text_success(monkeypatch):
    called = []
    monkeypatch.setattr(
        subprocess, "Popen",
        lambda *a, **k: called.append((a, k)) or "proc",
    )
    utils.speak_text("Привет")
    args, kwargs = called[0]
    assert args[0] == ["say", "-v", "Milena", "-r", "160", "Привет"]
    assert kwargs["stdout"] == subprocess.DEVNULL
    assert kwargs["stderr"] == subprocess.DEVNULL


def test_speak_text_error(monkeypatch, capsys):
    def boom(*a, **k):
        raise OSError("say not found")

    monkeypatch.setattr(subprocess, "Popen", boom)
    utils.speak_text("Привет")
    assert "Ошибка озвучки" in capsys.readouterr().out


# ─── load_chat / save_chat / list_chats ───


def test_utils_load_chat_missing():
    assert utils.load_chat("/nonexistent.json") == {
        "summary": "", "messages": [], "summaries": [],
    }


def test_utils_load_chat_list_migrates(tmp_path, monkeypatch):
    saved = []
    monkeypatch.setattr(utils, "save_chat", lambda p, d: saved.append((p, d)))
    path = tmp_path / "c.json"
    path.write_text(json.dumps([{"role": "user"}]))
    assert utils.load_chat(str(path))["messages"] == [{"role": "user"}]
    assert saved and saved[0][1]["messages"] == [{"role": "user"}]


def test_utils_save_chat_error(capsys):
    utils.save_chat("/nonexistent_dir_xyz/c.json", {})
    assert "Ошибка сохранения чата" in capsys.readouterr().out


def test_utils_list_chats_no_dir(env):
    assert utils.list_chats() == []


def test_utils_list_chats_missing_dir(monkeypatch):
    monkeypatch.setattr(utils, "CHATS_DIR", "/nonexistent_xyz")
    assert utils.list_chats() == []


# ─── save_code_from_text ───


def test_save_code_skips_missing_dir(tmp_path):
    assert utils.save_code_from_text("```py\nx=1\n```", "/no/such/dir") == []


def test_save_code_empty_block(tmp_path):
    assert utils.save_code_from_text("```py\n   \n```", str(tmp_path)) == []


def test_save_code_extensions(tmp_path, monkeypatch):
    monkeypatch.setattr(
        utils, "datetime",
        type("D", (), {"now": classmethod(lambda cls: type("N", (), {"strftime": lambda s, f: "123456"})())}),
    )
    text = (
        "```python\nprint(1)\n```\n"
        "```json\n{}\n```\n"
        "```js\nx();\n```\n"
        "```cpp\nint x;\n```\n"
        "```html\n<b></b>\n```\n"
        "```\nraw\n```\n"
    )
    saved = utils.save_code_from_text(text, str(tmp_path), "snippet")
    names = sorted(saved)
    assert names == [
        "snippet_123456.cpp", "snippet_123456.html", "snippet_123456.js",
        "snippet_123456.json", "snippet_123456.py", "snippet_123456.py",
    ]
    assert (tmp_path / "snippet_123456.cpp").exists()


def test_save_code_write_error(tmp_path, monkeypatch, capsys):
    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr("builtins.open", boom)
    utils.save_code_from_text("```py\nx\n```", str(tmp_path))
    assert "Ошибка сохранения файла" in capsys.readouterr().out


# ─── voice config ───


def test_get_cli_voice_default(env):
    assert utils.get_cli_voice() == {"enabled": True, "speed": 160, "voice": "Milena"}


def test_get_cli_voice_from_file(env):
    env.joinpath("voice.json").write_text(
        json.dumps({"cli": {"enabled": False, "speed": 200, "voice": "Katya"}})
    )
    assert utils.get_cli_voice() == {"enabled": False, "speed": 200, "voice": "Katya"}


def test_set_cli_voice_creates_config(env):
    utils.set_cli_voice("speed", 180)
    cfg = json.loads(env.joinpath("voice.json").read_text())
    assert cfg["cli"]["speed"] == 180
    assert cfg["cli"]["voice"] == "Milena"


def test_set_cli_voice_merges_existing(env):
    env.joinpath("voice.json").write_text(
        json.dumps({"cli": {"enabled": False, "speed": 160, "voice": "Milena"}})
    )
    utils.set_cli_voice("enabled", True)
    cfg = json.loads(env.joinpath("voice.json").read_text())
    assert cfg["cli"] == {"enabled": True, "speed": 160, "voice": "Milena"}


# ─── generate_summary_if_needed ───


def test_summary_not_needed(env):
    messages = [{"role": "user", "content": "x"}] * 14
    result = asyncio.run(
        utils.generate_summary_if_needed(messages, {"messages": messages}, "/c.json")
    )
    assert result is None


def test_summary_generated(env, monkeypatch, capsys):
    monkeypatch.setattr(utils, "get_current_ai", lambda: ("engine", "model"))

    async def fake_ai(e, m, msgs, context):
        return "summary text"

    monkeypatch.setattr(utils, "get_ai_response_async", fake_ai)
    messages = [{"role": "user", "content": "msg"}] * 15
    chat_data = {"messages": messages}
    result = asyncio.run(
        utils.generate_summary_if_needed(messages, chat_data, "/tmp/c.json")
    )
    assert result == "summary text"
    assert chat_data["summaries"] == ["summary text"]
    assert messages[-1] == {
        "role": "system", "type": "summary", "content": "summary text",
    }
    out = capsys.readouterr().out
    assert "Генерирую саммари" in out and "Саммари сохранено" in out


def test_summary_error(env, monkeypatch, capsys):
    monkeypatch.setattr(utils, "get_current_ai", lambda: ("e", "m"))

    async def boom(*a, **k):
        raise RuntimeError("no model")

    monkeypatch.setattr(utils, "get_ai_response_async", boom)
    messages = [{"role": "user", "content": "msg"}] * 15
    result = asyncio.run(
        utils.generate_summary_if_needed(messages, {"messages": messages}, "/c.json")
    )
    assert result is None
    assert "Ошибка саммари" in capsys.readouterr().out


# ─── export_chat_to_md ───


def test_export_chat_to_md(env):
    chats = env / "chats"
    chats.mkdir()
    chat_path = chats / "conv.json"
    data = {
        "messages": [
            {"role": "system", "type": "summary", "content": "S1"},
            {"role": "system", "content": "ignored"},
            {"role": "user", "content": "Привет"},
            {"role": "assistant", "content": "Здравствуй"},
        ]
    }
    utils.save_chat(str(chat_path), data)
    md_path = utils.export_chat_to_md(str(chat_path))
    with open(md_path, encoding="utf-8") as f:
        content = f.read()
    assert "# 💬 Диалог: conv" in content
    assert "### 📜 Саммари этапа" in content and "S1" in content
    assert "### 👤 Вы" in content and "Привет" in content
    assert "### 🤖 ИИ" in content and "Здравствуй" in content


# ─── misc ───


def test_get_bot_dir():
    assert utils.get_bot_dir().endswith("/Documents/mempalace_bot")


@pytest.mark.parametrize(
    "text,expected",
    [
        ("", True),
        ("a", True),
        ("?", True),
        ("~", False),
        ("ab", True),
        ("??", True),
        ("!!", True),
        ("#ctx", False),
        (".,;", True),
        ("hello", False),
        ("Привет мир", False),
    ],
)
def test_is_noise_input(text, expected):
    assert utils.is_noise_input(text) is expected
