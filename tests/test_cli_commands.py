"""Unit tests for cli/commands.py — простые команды."""

import asyncio
import json

import pytest

import cli.commands as commands
from cli.utils import C



def _async_val(value):
    async def _inner(*a, **k):
        return value
    return _inner


class FakeMCP:
    def __init__(self, payload="{}", raise_on=None):
        self.payload = payload
        self.raise_on = raise_on
        self.started = 0
        self.calls = []

    async def start(self):
        self.started += 1
        if self.raise_on == "start":
            raise RuntimeError("no mcp server")

    async def call_tool(self, name, args=None):
        self.calls.append((name, args))
        if self.raise_on == "tool":
            raise RuntimeError("tool failed")
        return self.payload


@pytest.fixture
def fake_mcp(monkeypatch):
    mcp = FakeMCP()
    monkeypatch.setattr(commands, "get_mcp", lambda: mcp)
    return mcp


@pytest.fixture
def models_config(tmp_path, monkeypatch):
    path = tmp_path / "models.json"
    monkeypatch.setattr(commands, "MODELS_CONFIG_PATH", str(path))
    monkeypatch.setattr(commands, "CONFIG_AI_FILE", str(tmp_path / "ai.txt"))
    return path


# ─── cmd_photos ───


def test_cmd_photos_empty(monkeypatch, capsys):
    monkeypatch.setattr(commands, "list_photos", lambda: [])
    asyncio.run(commands.cmd_photos())
    assert "Папка photos пуста" in capsys.readouterr().out


def test_cmd_photos_with_photos(monkeypatch, capsys):
    monkeypatch.setattr(commands, "list_photos", lambda: ["a.jpg", "b.jpg"])
    asyncio.run(commands.cmd_photos())
    out = capsys.readouterr().out
    assert "Фото в базе (2)" in out
    assert "1) a.jpg" in out and "2) b.jpg" in out


# ─── cmd_analyze_photo ───


def test_analyze_photo_no_capability(monkeypatch, capsys):
    monkeypatch.setattr(commands, "check_capability", lambda m, c: False)
    asyncio.run(commands.cmd_analyze_photo("e", "tiny-model", []))
    assert "не поддерживает анализ фото" in capsys.readouterr().out


def test_analyze_photo_no_photos(monkeypatch, capsys):
    monkeypatch.setattr(commands, "check_capability", lambda m, c: True)
    monkeypatch.setattr(commands, "list_photos", lambda: [])
    asyncio.run(commands.cmd_analyze_photo("e", "gpt", []))
    assert "Нет фото для анализа" in capsys.readouterr().out


def test_analyze_photo_encode_error_then_success(monkeypatch, capsys):
    monkeypatch.setattr(commands, "check_capability", lambda m, c: True)
    monkeypatch.setattr(commands, "list_photos", lambda: ["bad.jpg", "good.jpg"])
    monkeypatch.setattr(
        commands, "encode_image_to_base64",
        lambda p: (_ for _ in ()).throw(RuntimeError("encode fail")) if "bad" in p else "b64",
    )
    monkeypatch.setattr(commands, "search_palace_context", _async_val("ctx"))
    monkeypatch.setattr(commands, "get_smart_prompt", lambda **k: "sys")
    calls = []

    async def fake_ai(e, m, msgs, context="", images=None):
        calls.append(msgs)
        return "ANSWER"

    monkeypatch.setattr(commands, "get_ai_response_async", fake_ai)
    asyncio.run(commands.cmd_analyze_photo("e", "gpt", [{"role": "user", "content": "x"}]))
    out = capsys.readouterr().out
    assert "Ошибка кодирования bad.jpg" in out
    assert "ANSWER" in out
    assert calls[0][0] == {"role": "system", "content": "sys"}
    assert calls[0][-1]["role"] == "user"
    assert calls[0][-1]["content"].startswith("Проанализируй")


def test_analyze_photo_falsy_b64_skipped(monkeypatch, capsys):
    monkeypatch.setattr(commands, "check_capability", lambda m, c: True)
    monkeypatch.setattr(commands, "list_photos", lambda: ["a.jpg", "b.jpg"])
    monkeypatch.setattr(commands, "encode_image_to_base64",
                        lambda p: "" if p.endswith("a.jpg") else "b64")
    monkeypatch.setattr(commands, "search_palace_context", _async_val("ctx"))
    monkeypatch.setattr(commands, "get_smart_prompt", lambda **k: "sys")

    async def fake_ai(e, m, msgs, context="", images=None):
        return "OK"

    monkeypatch.setattr(commands, "get_ai_response_async", fake_ai)
    asyncio.run(commands.cmd_analyze_photo("e", "gpt", []))
    assert "OK" in capsys.readouterr().out


def test_analyze_photo_no_images_after_errors(monkeypatch, capsys):
    monkeypatch.setattr(commands, "check_capability", lambda m, c: True)
    monkeypatch.setattr(commands, "list_photos", lambda: ["bad.jpg"])
    monkeypatch.setattr(
        commands, "encode_image_to_base64",
        lambda p: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    asyncio.run(commands.cmd_analyze_photo("e", "gpt", []))
    assert "Не удалось подготовить фото" in capsys.readouterr().out


def test_analyze_photo_ai_error(monkeypatch, capsys):
    monkeypatch.setattr(commands, "check_capability", lambda m, c: True)
    monkeypatch.setattr(commands, "list_photos", lambda: ["a.jpg"])
    monkeypatch.setattr(commands, "encode_image_to_base64", lambda p: "b64")
    monkeypatch.setattr(commands, "search_palace_context", _async_val("ctx"))
    monkeypatch.setattr(commands, "get_smart_prompt", lambda **k: "sys")

    async def boom(e, m, msgs, context="", images=None):
        raise RuntimeError("ai down")

    monkeypatch.setattr(commands, "get_ai_response_async", boom)
    asyncio.run(commands.cmd_analyze_photo("e", "gpt", []))
    assert "Ошибка анализа" in capsys.readouterr().out


# ─── cmd_sound_toggle / speed ───


def test_sound_toggle_on_to_off(monkeypatch, capsys):
    monkeypatch.setattr(commands, "get_cli_voice",
                        lambda: {"enabled": True, "speed": 160})
    calls = {}
    monkeypatch.setattr(commands, "set_cli_voice",
                        lambda k, v: calls.update({k: v}))
    asyncio.run(commands.cmd_sound_toggle())
    assert calls == {"enabled": False}
    assert "Озвучка: Выкл" in capsys.readouterr().out


def test_sound_toggle_off_to_on(monkeypatch, capsys):
    monkeypatch.setattr(commands, "get_cli_voice",
                        lambda: {"enabled": False, "speed": 160})
    calls = {}
    monkeypatch.setattr(commands, "set_cli_voice",
                        lambda k, v: calls.update({k: v}))
    asyncio.run(commands.cmd_sound_toggle())
    assert calls == {"enabled": True}


def test_sound_speed_clamps(monkeypatch, capsys):
    calls = {}
    monkeypatch.setattr(commands, "set_cli_voice",
                        lambda k, v: calls.update({k: v}))
    asyncio.run(commands.cmd_sound_speed("50"))
    assert calls == {"speed": 100}
    asyncio.run(commands.cmd_sound_speed("500"))
    assert calls == {"speed": 300}
    asyncio.run(commands.cmd_sound_speed("150"))
    assert calls == {"speed": 150}
    assert "150 wpm" in capsys.readouterr().out


def test_sound_speed_invalid(monkeypatch, capsys):
    asyncio.run(commands.cmd_sound_speed("abc"))
    assert "Неверный формат" in capsys.readouterr().out


# ─── cmd_history ───


def test_history_roles_and_summary(capsys):
    messages = [
        {"role": "system", "type": "summary", "content": "S"},
        {"role": "user", "content": "привет"},
        {"role": "assistant", "content": "здравствуй"},
        {"role": "tool", "content": "skip"},
    ]
    asyncio.run(commands.cmd_history(messages))
    out = capsys.readouterr().out
    assert "САММАРИ ЭТАПА" in out
    assert "Вы:" in out and "ИИ:" in out
    assert "skip" not in out


def test_history_long_content_truncated(capsys):
    messages = [{"role": "user", "content": "x" * 500}]
    asyncio.run(commands.cmd_history(messages))
    out = capsys.readouterr().out
    assert "..." in out
    assert "x" * 500 not in out


# ─── cmd_export / cmd_sync ───


def test_cmd_export(monkeypatch, capsys):
    monkeypatch.setattr(commands, "export_chat_to_md", lambda p: "/out.md")
    asyncio.run(commands.cmd_export("/c.json"))
    assert "Экспортировано в: /out.md" in capsys.readouterr().out


def test_cmd_sync_empty_chat(monkeypatch, capsys):
    monkeypatch.setattr(commands, "export_chat_verbatim", lambda p, n: None)
    asyncio.run(commands.cmd_sync("/c.json"))
    assert "Чат пуст или не найден" in capsys.readouterr().out


def test_cmd_sync_success(monkeypatch, capsys):
    monkeypatch.setattr(commands, "export_chat_verbatim", lambda p, n: "exported")
    monkeypatch.setattr(commands, "sync_to_palace", _async_val("synced"))
    asyncio.run(commands.cmd_sync("/c.json"))
    out = capsys.readouterr().out
    assert "verbatim-экспорта" in out and "synced" in out


# ─── cmd_search ───


def test_cmd_search_empty_query(monkeypatch, capsys):
    asyncio.run(commands.cmd_search("   "))
    assert "Укажите запрос" in capsys.readouterr().out


def test_cmd_search_global(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(
        commands, "search_palace_context",
        _async_val("res:сон:"),
    )
    asyncio.run(commands.cmd_search("  сон  "))
    assert "res:сон:" in capsys.readouterr().out


def test_cmd_search_wing_valid(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(
        commands, "search_palace_context",
        lambda q, limit=3, wing="": (seen.update(q=q, wing=wing) or _async_val("r")()),
    )
    asyncio.run(commands.cmd_search("--wing dreams моя идея"))
    assert seen == {"q": "моя идея", "wing": "dreams"}
    assert "крыло: dreams" in capsys.readouterr().out


def test_cmd_search_wing_unknown(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(
        commands, "search_palace_context",
        lambda q, limit=3, wing="": (seen.update(wing=wing) or _async_val("r")()),
    )
    asyncio.run(commands.cmd_search("--wing mars привет"))
    assert seen == {"wing": ""}
    assert "Неизвестное крыло" in capsys.readouterr().out


# ─── palace passthrough-команды ───


@pytest.mark.parametrize(
    "cmd_name,svc_name,expected_msg",
    [
        ("cmd_status", "palace_status", "Получаю статус"),
        ("cmd_mcp", "palace_mcp", "настройки MCP"),
        ("cmd_wakeup", "palace_wake_up", "Загружаю дворец"),
        ("cmd_repair", "palace_repair", "Запускаю repair"),
        ("cmd_compact", "palace_compact", "compact"),
        ("cmd_compress", "palace_compress", "Сжимаю текст"),
    ],
)
def test_palace_passthrough(monkeypatch, capsys, cmd_name, svc_name, expected_msg):
    async def fake(*a, **k):
        return "RESULT"

    monkeypatch.setattr(commands, svc_name, fake)
    asyncio.run(getattr(commands, cmd_name)())
    out = capsys.readouterr().out
    assert expected_msg in out
    assert "RESULT" in out


def test_cmd_palace(monkeypatch, capsys):
    monkeypatch.setattr(commands, "get_current_ai", lambda: ("ollama", "m"))
    asyncio.run(commands.cmd_palace())
    out = capsys.readouterr().out
    assert "Модель: m (ollama)" in out
    assert "/taxonomy" in out and "/kgstats" in out


# ─── mcp-команды (wings/rooms/taxonomy/graph/traverse/follow/kg/kgstats) ───


def test_cmd_wings(fake_mcp, capsys):
    fake_mcp.payload = json.dumps(
        {"wings": {"mempalace_dreams": 3, "mempalace_creative": 1}}
    )
    asyncio.run(commands.cmd_wings())
    out = capsys.readouterr().out
    assert fake_mcp.calls == [("mempalace_list_wings", None)]
    assert "Dreams" in out and "3 записей" in out
    assert "Creative" in out and "1 записей" in out


def test_cmd_wings_error(fake_mcp, capsys):
    fake_mcp.raise_on = "tool"
    asyncio.run(commands.cmd_wings())
    assert "Ошибка:" in capsys.readouterr().out


def test_cmd_rooms_with_wing(fake_mcp, capsys):
    fake_mcp.payload = json.dumps(
        {"rooms": {"Спальня": 2, "Атриум": 1}, "wing": "dreams"}
    )
    asyncio.run(commands.cmd_rooms("/rooms dreams"))
    assert fake_mcp.calls == [("mempalace_list_rooms", {"wing": "dreams"})]
    out = capsys.readouterr().out
    assert "dreams" in out
    assert "Спальня" in out and "2" in out


def test_cmd_rooms_all(fake_mcp, capsys):
    fake_mcp.payload = json.dumps({"rooms": {}, "wing": None})
    asyncio.run(commands.cmd_rooms("/rooms"))
    assert fake_mcp.calls == [("mempalace_list_rooms", {})]
    assert "None" in capsys.readouterr().out


def test_cmd_rooms_error(fake_mcp, capsys):
    fake_mcp.raise_on = "start"
    asyncio.run(commands.cmd_rooms("/rooms"))
    assert "Ошибка:" in capsys.readouterr().out


@pytest.mark.parametrize(
    "cmd_name,arg",
    [
        ("cmd_graph", None),
        ("cmd_traverse", "/traverse A 2"),
        ("cmd_follow", "/follow A B"),
        ("cmd_kg", "/kg сон"),
        ("cmd_kgstats", None),
        ("cmd_taxonomy", None),
    ],
)
def test_mcp_commands_error(fake_mcp, monkeypatch, capsys, cmd_name, arg):
    fake_mcp.raise_on = "tool"
    if cmd_name == "cmd_kg":
        monkeypatch.setattr("handlers.palace._normalize_query", lambda q: q)
    fn = getattr(commands, cmd_name)
    if arg is None:
        asyncio.run(fn())
    else:
        asyncio.run(fn(arg))
    assert "Ошибка:" in capsys.readouterr().out


def test_cmd_taxonomy(fake_mcp, capsys):
    fake_mcp.payload = json.dumps(
        {"taxonomy": {"dreams_w": {"A": 2, "B": 1}}}
    )
    asyncio.run(commands.cmd_taxonomy())
    assert fake_mcp.calls == [("mempalace_get_taxonomy", None)]
    out = capsys.readouterr().out
    assert "Dreams W" in out and "3 записей" in out and "2 комнат" in out


def test_cmd_taxonomy_empty_rooms(fake_mcp, capsys):
    fake_mcp.payload = json.dumps({"taxonomy": {"dreams_w": {}}})
    asyncio.run(commands.cmd_taxonomy())
    assert "0 записей, 0 комнат" in capsys.readouterr().out


def test_cmd_graph(fake_mcp, capsys):
    fake_mcp.payload = json.dumps(
        {"total_rooms": 10, "tunnel_rooms": 4, "total_edges": 7}
    )
    asyncio.run(commands.cmd_graph())
    out = capsys.readouterr().out
    assert "Комнат всего:" in out and "10" in out
    assert "Комнат с туннелями:" in out and "4" in out
    assert "Связей:" in out and "7" in out


def test_cmd_traverse_missing_args(capsys):
    asyncio.run(commands.cmd_traverse("/traverse"))
    assert "Укажите команду" in capsys.readouterr().out


def test_cmd_traverse_default_hops(fake_mcp, capsys):
    fake_mcp.payload = "path found"
    asyncio.run(commands.cmd_traverse("/traverse комната"))
    assert fake_mcp.calls == [
        ("mempalace_traverse", {"start_room": "комната", "max_hops": 2})
    ]


def test_cmd_traverse_with_hops(fake_mcp, capsys):
    fake_mcp.payload = "path"
    asyncio.run(commands.cmd_traverse("/traverse комната 5"))
    assert fake_mcp.calls == [
        ("mempalace_traverse", {"start_room": "комната", "max_hops": 5})
    ]


def test_cmd_follow_missing_args(capsys):
    asyncio.run(commands.cmd_follow("/follow dreams"))
    assert "Укажите крыло и комнату" in capsys.readouterr().out


def test_cmd_follow_ok(fake_mcp, capsys):
    fake_mcp.payload = "tunnel"
    asyncio.run(commands.cmd_follow("/follow dreams Спальня"))
    assert fake_mcp.calls == [
        ("mempalace_follow_tunnels", {"wing": "dreams", "room": "Спальня"})
    ]
    assert "tunnel" in capsys.readouterr().out


def test_cmd_kg_empty(monkeypatch, capsys):
    asyncio.run(commands.cmd_kg(""))
    assert "Укажите сущность" in capsys.readouterr().out


def test_cmd_kg_no_facts(fake_mcp, monkeypatch, capsys):
    fake_mcp.payload = json.dumps({"facts": []})
    monkeypatch.setattr("handlers.palace._normalize_query", lambda q: q.upper())
    asyncio.run(commands.cmd_kg("  сон  "))
    assert "Нет фактов о «СОН»" in capsys.readouterr().out


def test_cmd_kg_facts_dicts_and_plain(fake_mcp, monkeypatch, capsys):
    fake_mcp.payload = json.dumps([
        {"subject": "S", "predicate": "P", "object": "O", "valid_from": "2024"},
        {"subject": "A", "predicate": "B", "object": "C"},
        "plain fact",
    ])
    monkeypatch.setattr("handlers.palace._normalize_query", lambda q: q)
    asyncio.run(commands.cmd_kg("сон"))
    out = capsys.readouterr().out
    assert "S → P → O (с 2024)" in out
    assert "A → B → C" in out
    assert "plain fact" in out


def test_cmd_kgstats(fake_mcp, capsys):
    fake_mcp.payload = json.dumps(
        {"entities": 5, "triples": 6, "current_facts": 4, "expired_facts": 2}
    )
    asyncio.run(commands.cmd_kgstats())
    out = capsys.readouterr().out
    assert "Сущностей:" in out and "5" in out and "Связей:" in out and "6" in out
    assert "Актуальных фактов:" in out and "4" in out
    assert "Устаревших фактов:" in out and "2" in out


# ─── cmd_enrich ───


def test_cmd_enrich_cancelled(monkeypatch, tmp_path, capsys):
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "a.txt").write_text("x")
    monkeypatch.setattr(commands, "NOTES_DIR", str(notes))
    monkeypatch.setattr("builtins.input", lambda: "n")
    asyncio.run(commands.cmd_enrich())
    assert "Отменено." in capsys.readouterr().out


def test_cmd_enrich_eof(monkeypatch, tmp_path, capsys):
    notes = tmp_path / "notes"
    notes.mkdir()
    monkeypatch.setattr(commands, "NOTES_DIR", str(notes))

    def eof():
        raise EOFError()

    monkeypatch.setattr("builtins.input", eof)
    asyncio.run(commands.cmd_enrich())
    assert "Запускаю enrichment" in capsys.readouterr().out


def test_cmd_enrich_success(monkeypatch, tmp_path, capsys):
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "a.txt").write_text("x")
    (notes / "b.md").write_text("y")
    (notes / "skip.pdf").write_text("z")
    monkeypatch.setattr(commands, "NOTES_DIR", str(notes))
    monkeypatch.setattr("builtins.input", lambda: "y")

    async def fake_enrich(progress):
        await progress(2, 2, {"processed": 2, "kg_added": 1})
        return {
            "processed": 2, "failed": 0, "kg_added": 1,
            "authors": ["Гёте", "А", "Б", "В", "Г", "Д", "Е"],
            "books": ["Фауст"],
        }

    monkeypatch.setattr(commands, "enrich_all_notes", fake_enrich)
    asyncio.run(commands.cmd_enrich())
    out = capsys.readouterr().out
    assert "Найдено 2 файлов" in out
    assert "Enrichment завершён" in out
    assert "Обработано файлов: 2" in out
    assert "Фактов добавлено в KG: 1" in out
    assert "Найдено авторов: 7" in out
    assert "и ещё 2" in out


def test_cmd_enrich_few_authors(monkeypatch, tmp_path, capsys):
    notes = tmp_path / "notes"
    notes.mkdir()
    monkeypatch.setattr(commands, "NOTES_DIR", str(notes))
    monkeypatch.setattr("builtins.input", lambda: "y")

    async def fake_enrich(progress):
        return {
            "processed": 1, "failed": 0, "kg_added": 0,
            "authors": ["Один"], "books": [],
        }

    monkeypatch.setattr(commands, "enrich_all_notes", fake_enrich)
    asyncio.run(commands.cmd_enrich())
    out = capsys.readouterr().out
    assert "    - Один" in out
    assert "и ещё" not in out


def test_cmd_enrich_error_result(monkeypatch, tmp_path, capsys):
    notes = tmp_path / "notes"
    notes.mkdir()
    monkeypatch.setattr(commands, "NOTES_DIR", str(notes))
    monkeypatch.setattr("builtins.input", lambda: "y")

    async def fake_enrich(progress):
        return {"error": "db locked"}

    monkeypatch.setattr(commands, "enrich_all_notes", fake_enrich)
    asyncio.run(commands.cmd_enrich())
    assert "db locked" in capsys.readouterr().out


def test_cmd_enrich_exception(monkeypatch, tmp_path, capsys):
    notes = tmp_path / "notes"
    notes.mkdir()
    monkeypatch.setattr(commands, "NOTES_DIR", str(notes))
    monkeypatch.setattr("builtins.input", lambda: "y")

    async def boom(progress):
        raise RuntimeError("crash")

    monkeypatch.setattr(commands, "enrich_all_notes", boom)
    asyncio.run(commands.cmd_enrich())
    assert "Ошибка: crash" in capsys.readouterr().out


# ─── cmd_remind / pdfs / yt / transkript / kgadd / tunnels ───


@pytest.mark.parametrize(
    "cmd_name,extra_args,svc_name,input_arg,expected",
    [
        ("cmd_remind", ("/remind напомни купить хлеб",),
         "cli_remind", "напомни купить хлеб", None),
        ("cmd_tunnels", ("/tunnels dreams",), "cli_tunnels", "/tunnels dreams", None),
        ("cmd_kgadd", ("суб пред об",), "cli_kgadd", "суб пред об", None),
        ("cmd_pdfs", ("3",), "cli_pdfs", "3", ""),
        ("cmd_transkript", ("1",), "cli_transkript", "1", ""),
        ("cmd_yt", ("https://x", "audio"), "cli_yt", None, None),
    ],
)
def test_delegate_commands(monkeypatch, capsys, cmd_name, extra_args, svc_name,
                           input_arg, expected):
    seen = []

    async def fake(*a, **k):
        seen.append((a, k))
        return "DELEGATED"

    monkeypatch.setattr(commands, svc_name, fake)
    fn = getattr(commands, cmd_name)
    if cmd_name == "cmd_yt":
        asyncio.run(fn("https://x", "audio"))
        assert seen[0][0] == ("https://x", "audio")
        assert "DELEGATED" in capsys.readouterr().out
        return
    async def fake_empty(*a, **k):
        seen.append((a, k))
        return expected

    if expected == "":
        monkeypatch.setattr(commands, svc_name, fake_empty)
    asyncio.run(fn(*extra_args))
    assert seen[0][0][0] == input_arg
    if expected == "":
        assert "DELEGATED" not in capsys.readouterr().out
    else:
        assert "DELEGATED" in capsys.readouterr().out


# ─── cmd_settings ───


def test_cmd_pdfs_empty_result(monkeypatch, capsys):
    async def fake(p):
        return ""

    monkeypatch.setattr(commands, "cli_pdfs", fake)
    asyncio.run(commands.cmd_pdfs("1"))
    assert capsys.readouterr().out == ""


def test_cmd_transkript_empty_result(monkeypatch, capsys):
    async def fake(p):
        return ""

    monkeypatch.setattr(commands, "cli_transkript", fake)
    asyncio.run(commands.cmd_transkript("1"))
    assert capsys.readouterr().out == ""


def test_cmd_pdfs_with_result(monkeypatch, capsys):
    async def fake(p):
        return "СПИСОК PDF"

    monkeypatch.setattr(commands, "cli_pdfs", fake)
    asyncio.run(commands.cmd_pdfs(""))
    assert "СПИСОК PDF" in capsys.readouterr().out


def test_cmd_transkript_with_result(monkeypatch, capsys):
    async def fake(p):
        return "ТРАНСКРИПТ"

    monkeypatch.setattr(commands, "cli_transkript", fake)
    asyncio.run(commands.cmd_transkript("1"))
    assert "ТРАНСКРИПТ" in capsys.readouterr().out


def test_cmd_settings_no_models_file(models_config, capsys):
    asyncio.run(commands.cmd_settings([], {}, "/c.json"))
    assert "models.json не найден" in capsys.readouterr().out


def test_cmd_settings_cancel(models_config, capsys, monkeypatch):
    models_config.write_text(json.dumps({"ollama": [{"name": "A", "tag": "a"}]}))
    monkeypatch_input(monkeypatch, capsys, "0")
    asyncio.run(commands.cmd_settings([], {}, "/c.json"))


def monkeypatch_input(monkeypatch, capsys, value):
    import builtins
    monkeypatch.setattr(builtins, "input", lambda p: value)


def test_cmd_settings_select(models_config, capsys, monkeypatch):
    models_config.write_text(json.dumps({
        "ollama": [{"name": "Qwen", "tag": "qwen2.5:14b"}],
        "openai": [{"name": "GPT", "tag": "gpt-4o"}],
        "gemini": [],
    }))
    monkeypatch_input(monkeypatch, capsys, "2")
    written = {}
    monkeypatch.setattr("builtins.open", _open_wrapper(models_config, written))
    monkeypatch.setattr(commands, "invalidate_ai_cache", lambda: None)
    monkeypatch.setattr(commands, "get_current_ai", lambda: ("openai", "gpt-4o"))
    asyncio.run(commands.cmd_settings([], {}, "/c.json"))
    assert written[str(models_config.parent / "ai.txt")] == "gpt-4o"
    assert "Модель: gpt-4o" in capsys.readouterr().out


def test_cmd_settings_out_of_range(models_config, capsys, monkeypatch):
    models_config.write_text(json.dumps({"ollama": [{"name": "A", "tag": "a"}]}))
    monkeypatch_input(monkeypatch, capsys, "99")
    asyncio.run(commands.cmd_settings([], {}, "/c.json"))


def test_cmd_settings_invalid_input(models_config, capsys, monkeypatch):
    models_config.write_text(json.dumps({"ollama": [{"name": "A", "tag": "a"}]}))
    monkeypatch_input(monkeypatch, capsys, "abc")
    asyncio.run(commands.cmd_settings([], {}, "/c.json"))
    assert "Неверный ввод." in capsys.readouterr().out


def _open_wrapper(path, written):
    import builtins

    real_open = builtins.open

    def fake_open(p, mode="r", *a, **k):
        if "ai.txt" in str(p):
            written[str(path.parent / "ai.txt")] = ""
            return _FakeWriter(written, str(p))
        return real_open(p, mode, *a, **k)

    return fake_open


class _FakeWriter:
    def __init__(self, written, p):
        self.written = written
        self.p = p

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def write(self, content):
        self.written[self.p] = content


# ─── save_quick_note / save_extraction ───


def test_save_quick_note(monkeypatch, tmp_path, capsys):
    notes = tmp_path / "notes"
    notes.mkdir()
    monkeypatch.setattr(commands, "NOTES_DIR", str(notes))
    linked = []
    monkeypatch.setattr(
        commands, "link_note_async",
        lambda p, q, prefix="!": _async_val(linked.append((p, q, prefix)))(),
    )
    asyncio.run(commands.save_quick_note("заметка"))
    files = list(notes.glob("nt_cli_*.txt"))
    assert len(files) == 1
    assert files[0].read_text() == "заметка"
    out = capsys.readouterr().out
    assert "Сохранено в my_notes" in out and "Связывание завершено" in out


def test_save_quick_note_link_error(monkeypatch, tmp_path, capsys):
    notes = tmp_path / "notes"
    notes.mkdir()
    monkeypatch.setattr(commands, "NOTES_DIR", str(notes))

    async def boom(*a, **k):
        raise RuntimeError("link fail")

    monkeypatch.setattr(commands, "link_note_async", boom)
    asyncio.run(commands.save_quick_note("x"))
    assert "Ошибка связывания: link fail" in capsys.readouterr().out


def test_save_extraction_insights(monkeypatch, tmp_path, capsys):
    insights = tmp_path / "insights"
    insights.mkdir()
    monkeypatch.setattr(commands, "INSIGHTS_DIR", str(insights))
    asyncio.run(commands.save_extraction("!!", "q", [], "ANSWER", "e", "m"))
    files = list(insights.glob("ins_cli_*.txt"))
    assert len(files) == 1 and files[0].read_text() == "ANSWER"
    assert "Сохранено в Insights" in capsys.readouterr().out


def test_save_extraction_research(monkeypatch, tmp_path, capsys):
    research = tmp_path / "research"
    research.mkdir()
    monkeypatch.setattr(commands, "RESEARCH_DIR", str(research))
    asyncio.run(commands.save_extraction("???", "q", [], "R", "e", "m"))
    files = list(research.glob("res_cli_*.txt"))
    assert len(files) == 1 and files[0].read_text() == "R"
    assert "Сохранено в Research" in capsys.readouterr().out


def test_save_extraction_other_prefix(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(commands, "INSIGHTS_DIR", str(tmp_path))
    asyncio.run(commands.save_extraction("!!", "q", [], "", "e", "m"))
    assert "Нет ответа для сохранения" in capsys.readouterr().out


def test_save_extraction_ignored_prefix(capsys):
    asyncio.run(commands.save_extraction("!", "q", [], "", "e", "m"))


# ─── cmd_web ───


def test_cmd_web_search_error(monkeypatch, capsys):
    async def boom(q):
        raise RuntimeError("net down")

    monkeypatch.setattr("services.web_search.search_web", boom)
    asyncio.run(commands.cmd_web("запрос"))
    assert "Ошибка поиска: net down" in capsys.readouterr().out


def test_cmd_web_german_not_translated(monkeypatch, capsys):
    async def fake(q):
        return "der die das und ist"

    monkeypatch.setattr("services.web_search.search_web", fake)
    asyncio.run(commands.cmd_web("запрос"))
    out = capsys.readouterr().out
    assert "der die das und ist" in out


def test_cmd_web_english_translated(monkeypatch, capsys):
    async def fake(q):
        return "the and for with is are to of in a an"

    monkeypatch.setattr("services.web_search.search_web", fake)

    async def fake_ai(e, m, msgs, context="", user_query=""):
        return "РУССКИЙ ПЕРЕВОД"

    monkeypatch.setattr("services.ai_engine.get_ai_response_async", fake_ai)
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("e", "m"))
    asyncio.run(commands.cmd_web("запрос"))
    assert "РУССКИЙ ПЕРЕВОД" in capsys.readouterr().out


def test_cmd_web_russian_no_translate(monkeypatch, capsys):
    async def fake(q):
        return "только русский текст без английских слов"

    monkeypatch.setattr("services.web_search.search_web", fake)
    called = []
    monkeypatch.setattr(commands, "get_ai_response_async", lambda *a, **k: called.append(1))
    asyncio.run(commands.cmd_web("запрос"))
    out = capsys.readouterr().out
    assert "только русский текст" in out
    assert called == []


def test_cmd_web_translate_fails_keeps_original(monkeypatch, capsys):
    async def fake(q):
        return "the quick brown fox"

    monkeypatch.setattr("services.web_search.search_web", fake)

    async def boom(e, m, msgs, context="", user_query=""):
        raise RuntimeError("trans down")

    monkeypatch.setattr("services.ai_engine.get_ai_response_async", boom)
    monkeypatch.setattr("services.ai_engine.get_current_ai", lambda: ("e", "m"))
    asyncio.run(commands.cmd_web("запрос"))
    assert "the quick brown fox" in capsys.readouterr().out
