"""Unit tests for cli/commands.process_ai_query"""

import asyncio

import pytest

import cli.commands as commands


@pytest.fixture
def ai_env(monkeypatch):
    calls = {}

    async def fake_ai(e, m, msgs, context="", **kw):
        calls["answer"] = msgs
        return "ОТВЕТ ИИ"

    async def fake_search(q, limit=3, wing=None):
        calls["search"] = (q, wing)
        return "palace ctx"

    monkeypatch.setattr(commands, "classify_wing", lambda q: None)
    monkeypatch.setattr(commands, "search_with_kg", fake_search)
    monkeypatch.setattr(commands, "get_smart_prompt", lambda **k: "SYS")
    monkeypatch.setattr(commands, "get_memory_context", lambda q, uid: None)
    monkeypatch.setattr(commands, "get_ai_response_async", fake_ai)
    monkeypatch.setattr(commands, "extract_and_store_facts",
                        lambda *a, **k: _noop_coro())
    monkeypatch.setattr(commands, "save_chat", lambda p, d: None)
    monkeypatch.setattr(commands, "get_cli_voice",
                        lambda: {"enabled": False, "speed": 160, "voice": "M"})
    monkeypatch.setattr(commands, "speak_text", lambda *a, **k: None)
    monkeypatch.setattr(commands, "check_capability", lambda m, c: False)
    monkeypatch.setattr(commands, "list_photos", lambda: [])
    monkeypatch.setattr("services.code_mode.is_coding_context", lambda q, m: False)
    monkeypatch.setattr(commands, "PHOTOS_DIR", "/photos")
    calls["mock_answer"] = lambda: "ОТВЕТ ИИ"
    return calls


def _noop_coro():
    async def _inner(*a, **k):
        return None
    return _inner()


def _run(clean_q, messages, data, chat_path, engine="e", model="m"):
    return asyncio.run(
        commands.process_ai_query(clean_q, messages, data, chat_path, engine, model)
    )


# ─── базовый поток ───


def test_basic_query(ai_env, capsys):
    messages = [{"role": "user", "content": "x"}]
    data = {"summaries": []}
    result = _run("привет", messages, data, "/c.json")
    assert result == "ОТВЕТ ИИ"
    assert ai_env["search"] == ("привет", None)
    assert messages[-2:] == [
        {"role": "user", "content": "привет"},
        {"role": "assistant", "content": "ОТВЕТ ИИ"},
    ]
    assert "думает" in capsys.readouterr().out


def test_explicit_wing(ai_env, capsys):
    data = {"summaries": []}
    _run("/dreams: моя идея", [], data, "/c.json")
    assert ai_env["search"] == ("моя идея", "dreams")
    assert "Явное крыло: dreams" in capsys.readouterr().out


def test_explicit_non_wing_falls_back_to_auto(ai_env, capsys, monkeypatch):
    monkeypatch.setattr(commands, "classify_wing", lambda q: "creative")
    data = {"summaries": []}
    _run("/foo: запрос", [], data, "/c.json")
    assert ai_env["search"] == ("/foo: запрос", "creative")
    assert "Авто-крыло: creative" in capsys.readouterr().out


def test_auto_wing(ai_env, capsys, monkeypatch):
    monkeypatch.setattr(commands, "classify_wing", lambda q: "psychology")
    data = {"summaries": []}
    _run("сон", [], data, "/c.json")
    assert ai_env["search"] == ("сон", "psychology")
    assert "Авто-крыло: psychology" in capsys.readouterr().out


def test_summary_appended(ai_env, monkeypatch):
    seen = {}

    def fake_prompt(**k):
        seen["ctx"] = k
        return "SYS"

    monkeypatch.setattr(commands, "get_smart_prompt", fake_prompt)
    data = {"summaries": ["prev summary"]}
    _run("q", [], data, "/c.json")
    msgs = ai_env["answer"]
    assert "prev summary" in msgs[0]["content"]


def test_memory_context_appended(ai_env, monkeypatch):
    seen = {}
    monkeypatch.setattr(
        commands, "get_memory_context",
        lambda q, uid: (seen.update(uid=uid) or "MEMORY CTX"),
    )
    data = {"summaries": []}
    _run("q", [], data, "/c.json")
    assert seen["uid"] == hash("/c.json")
    assert "MEMORY CTX" in ai_env["answer"][0]["content"]


def test_memory_error_ignored(ai_env, monkeypatch):
    def boom(q, uid):
        raise RuntimeError("mem down")

    monkeypatch.setattr(commands, "get_memory_context", boom)
    data = {"summaries": []}
    result = _run("q", [], data, "/c.json")
    assert result == "ОТВЕТ ИИ"


# ─── coding mode ───


def test_coding_mode_activation(ai_env, monkeypatch, capsys):
    monkeypatch.setattr("services.code_mode.is_coding_context", lambda q, m: True)
    monkeypatch.setattr("services.code_mode.ensure_project_dir", lambda b: "/proj")
    saved = {}
    monkeypatch.setattr(commands, "save_chat", lambda p, d: saved.update(p=p, d=d))
    data = {}
    _run("напиши код", [], data, "/c.json")
    assert data == {"is_coding_mode": True, "project_dir": "/proj"}
    assert saved["p"] == "/c.json"
    assert "Активирован режим программирования" in capsys.readouterr().out


def test_coding_mode_already_active(ai_env, monkeypatch):
    monkeypatch.setattr("services.code_mode.is_coding_context", lambda q, m: True)
    monkeypatch.setattr("services.code_mode.load_coding_prompt", lambda: "CODING SYS")
    monkeypatch.setattr(
        "services.code_mode.read_project_files", lambda d: "files list",
    )
    data = {"is_coding_mode": True, "project_dir": "/proj"}
    _run("продолжай", [], data, "/c.json")
    sys_msg = ai_env["answer"][0]["content"]
    assert "CODING SYS" in sys_msg
    assert "files list" in sys_msg


def test_coding_mode_active_no_project_files(ai_env, monkeypatch):
    monkeypatch.setattr("services.code_mode.is_coding_context", lambda q, m: True)
    monkeypatch.setattr("services.code_mode.load_coding_prompt", lambda: "CODING SYS")
    monkeypatch.setattr("services.code_mode.read_project_files", lambda d: "")
    data = {"is_coding_mode": True, "project_dir": "/proj"}
    _run("продолжай", [], data, "/c.json")
    sys_msg = ai_env["answer"][0]["content"]
    assert "CODING SYS" in sys_msg
    assert "Файлы текущего проекта" not in sys_msg


# ─── photo handling ───


def test_photo_attached_when_multimodal(ai_env, monkeypatch):
    monkeypatch.setattr(commands, "check_capability", lambda m, c: True)
    monkeypatch.setattr(commands, "list_photos", lambda: ["p.jpg"])
    monkeypatch.setattr(commands, "encode_image_to_base64", lambda p: "B64DATA")
    data = {"summaries": []}
    _run("опиши фото", [], data, "/c.json")
    last = ai_env["answer"][-1]
    assert last["role"] == "user"
    assert last["content"][1]["type"] == "image_url"


def test_photo_skip_when_no_capability(ai_env, monkeypatch):
    monkeypatch.setattr(commands, "check_capability", lambda m, c: False)
    monkeypatch.setattr(commands, "list_photos", lambda: ["p.jpg"])
    data = {"summaries": []}
    _run("опиши фото", [], data, "/c.json")
    assert ai_env["answer"][-1]["content"] == "опиши фото"


def test_photo_attached_skips_non_string_user(ai_env, monkeypatch):
    monkeypatch.setattr(commands, "check_capability", lambda m, c: True)
    monkeypatch.setattr(commands, "list_photos", lambda: ["p.jpg"])
    monkeypatch.setattr(commands, "encode_image_to_base64", lambda p: "B64")
    data = {"summaries": []}
    messages = [{"role": "user", "content": {"type": "text"}}]
    _run("опиши фото", messages, data, "/c.json")
    last = ai_env["answer"][-1]
    assert last["role"] == "user"
    assert last["content"][1]["type"] == "image_url"


def test_photo_encode_failure_skipped(ai_env, monkeypatch):
    monkeypatch.setattr(commands, "check_capability", lambda m, c: True)
    monkeypatch.setattr(commands, "list_photos", lambda: ["p.jpg"])
    monkeypatch.setattr(commands, "encode_image_to_base64", lambda p: None)
    data = {"summaries": []}
    _run("опиши фото", [], data, "/c.json")
    assert ai_env["answer"][-1]["content"] == "опиши фото"


# ─── вывод ответа ───


def test_answer_plain_text(ai_env, capsys):
    data = {"summaries": []}
    _run("q", [], data, "/c.json")
    out = capsys.readouterr().out
    assert "AI: ОТВЕТ ИИ" in out


def test_answer_with_code_blocks(ai_env, monkeypatch, capsys):
    async def fake_ai(e, m, msgs, context="", **kw):
        return "объяснение\n```python\nprint(1)\n```\nконец"

    monkeypatch.setattr(commands, "get_ai_response_async", fake_ai)
    data = {"summaries": []}
    _run("код", [], data, "/c.json")
    out = capsys.readouterr().out
    assert "AI: объяснение" in out
    assert "print(1)" in out


def test_answer_code_block_odd_parts(ai_env, monkeypatch, capsys):
    async def fake_ai(e, m, msgs, context="", **kw):
        return "```\nraw code\n```"

    monkeypatch.setattr(commands, "get_ai_response_async", fake_ai)
    data = {"summaries": []}
    _run("код", [], data, "/c.json")
    assert "raw code" in capsys.readouterr().out


def test_answer_ai_error(ai_env, monkeypatch, capsys):
    async def boom(e, m, msgs, context="", **kw):
        raise RuntimeError("ai crashed")

    monkeypatch.setattr(commands, "get_ai_response_async", boom)
    data = {"summaries": []}
    result = _run("q", [], data, "/c.json")
    assert result is None
    out = capsys.readouterr().out
    assert "Ошибка ИИ: ai crashed" in out
