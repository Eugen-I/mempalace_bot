"""Unit tests for handlers.palace.hints."""

from types import SimpleNamespace

import pytest

from handlers.palace import hints as h


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeMessage:
    def __init__(self, uid=4242):
        self.from_user = FakeUser(uid)
        self.answers = []
        self.edits = []
        self.deleted = False

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append((text, parse_mode, reply_markup))
        return self

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append((text, parse_mode, reply_markup))

    async def delete(self):
        self.deleted = True


class FakeCb:
    def __init__(self, uid=4242, data="", message=None):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = message or FakeMessage(uid)
        self.answered = []

    async def answer(self, text=None, show_alert=None):
        self.answered.append((text, show_alert))


class FakeMCP:
    def __init__(self, result="{}", fail_on=None):
        self.result = result
        self.calls = []
        self.fail_on = fail_on

    async def call_tool(self, name, params=None):
        self.calls.append((name, params))
        if self.fail_on:
            raise RuntimeError(self.fail_on)
        return self.result


def _enable(monkeypatch):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {4242})
    monkeypatch.setattr(h, "safe_html_format", lambda t: t)


@pytest.fixture(autouse=True)
def _clean_state():
    h._hint_data.clear()
    yield
    h._hint_data.clear()


def _kb_data(markup):
    if markup is None:
        return []
    return [b.callback_data for row in markup.inline_keyboard for b in row]


# ---------- suggest_tunnel_hint ----------


def test_suggest_tunnel_hint_short_query():
    msg = FakeMessage()
    import asyncio

    asyncio.run(h.suggest_tunnel_hint(msg, "ab"))
    assert msg.answers == []


def test_suggest_tunnel_hint_no_match(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"rooms": {"комната а": {}, "комната б": {}}}')
    monkeypatch.setattr(h, "get_mcp", lambda: mcp)
    monkeypatch.setattr(
        "services.wing_classifier.classify_wing", lambda q: "крыло",
    )
    msg = FakeMessage()
    import asyncio

    asyncio.run(h.suggest_tunnel_hint(msg, "запрос"))
    assert msg.answers == []
    assert 4242 not in h._hint_data


class FakeMCPSeq(FakeMCP):
    def __init__(self, results):
        self.results = list(results)
        self.calls = []
        self.fail_on = None

    async def call_tool(self, name, params=None):
        self.calls.append((name, params))
        return self.results.pop(0)


def test_suggest_tunnel_hint_no_traverse(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([
        '{"rooms": {"комната а": {}, "комната б": {}}}',
        '[]',
    ])
    monkeypatch.setattr(h, "get_mcp", lambda: mcp)
    monkeypatch.setattr(
        "services.wing_classifier.classify_wing", lambda q: "крыло",
    )
    msg = FakeMessage()
    import asyncio

    asyncio.run(h.suggest_tunnel_hint(msg, "запрос с комната а"))
    assert mcp.calls[1] == ("mempalace_traverse", {"start_room": "комната а", "max_hops": 1})
    assert msg.answers == []


def test_suggest_tunnel_hint_success(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([
        '{"rooms": {"комната а": {}, "комната б": {}}}',
        '[{"room": "комната б", "wing": "крыло"}]',
    ])
    monkeypatch.setattr(h, "get_mcp", lambda: mcp)
    monkeypatch.setattr(
        "services.wing_classifier.classify_wing", lambda q: "крыло",
    )
    msg = FakeMessage()
    import asyncio

    asyncio.run(h.suggest_tunnel_hint(msg, "запрос комната а"))
    assert "Найдена связь" in msg.answers[0][0]
    assert _kb_data(msg.answers[0][2]) == ["p_hnt", "p_kga"]
    assert h._hint_data[4242] == {
        "room": "комната а",
        "traverse": [{"room": "комната б", "wing": "крыло"}],
        "wing": "крыло",
    }


def test_suggest_tunnel_hint_traverse_empty_string(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([
        '{"rooms": {"комната а": {}}}',
        "",
    ])
    monkeypatch.setattr(h, "get_mcp", lambda: mcp)
    monkeypatch.setattr(
        "services.wing_classifier.classify_wing", lambda q: "крыло",
    )
    msg = FakeMessage()
    import asyncio

    asyncio.run(h.suggest_tunnel_hint(msg, "запрос комната а"))
    assert msg.answers == []


def test_suggest_tunnel_hint_exception(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP(fail_on="mcp упал")
    monkeypatch.setattr(h, "get_mcp", lambda: mcp)
    msg = FakeMessage()
    import asyncio

    asyncio.run(h.suggest_tunnel_hint(msg, "запрос комната а"))
    assert msg.answers == []


# ---------- cb_hint_show ----------


def test_cb_hint_show_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_hnt")
    import asyncio

    asyncio.run(h.cb_hint_show(cb))
    assert cb.message.edits[-1][0] == "❌ Нет данных подсказки."


def test_cb_hint_show_success(monkeypatch):
    _enable(monkeypatch)
    h._hint_data[4242] = {
        "room": "комната а",
        "traverse": [
            {"room": "комната б", "wing": "крыло"},
            {"room": "комната в", "wing": "крыло"},
            "строковый узел",
        ],
        "wing": "крыло",
    }
    cb = FakeCb(data="p_hnt")
    import asyncio

    asyncio.run(h.cb_hint_show(cb))
    body = cb.message.edits[-1][0]
    assert "Связи комнаты «комната а»" in body
    assert "комната б" in body
    assert _kb_data(cb.message.edits[-1][2]) == ["p_hnt_r", "p_hnt_d"]


# ---------- cb_hint_read ----------


def test_cb_hint_read_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_hnt_r")
    import asyncio

    asyncio.run(h.cb_hint_read(cb))
    assert cb.message.edits[-1][0] == "❌ Нет данных."


def test_cb_hint_read_success(monkeypatch):
    _enable(monkeypatch)
    h._hint_data[4242] = {"room": "комната а", "wing": "крыло"}
    shown = []

    async def fake_show_drawers(edit_func, uid, wing, room, offset):
        shown.append((edit_func, uid, wing, room, offset))

    monkeypatch.setattr(h, "_show_drawers_page", fake_show_drawers)
    cb = FakeCb(data="p_hnt_r")
    import asyncio

    asyncio.run(h.cb_hint_read(cb))
    assert shown[0] == (cb.message.edit_text, 4242, "крыло", "комната а", 0)


# ---------- cb_hint_dismiss ----------


def test_cb_hint_dismiss_delete(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_hnt_d")
    import asyncio

    asyncio.run(h.cb_hint_dismiss(cb))
    assert cb.message.deleted is True


def test_cb_hint_dismiss_delete_fails(monkeypatch):
    _enable(monkeypatch)

    class BoomMsg(FakeMessage):
        async def delete(self):
            raise RuntimeError("delete fail")

    cb = FakeCb(data="p_hnt_d", message=BoomMsg())
    import asyncio

    asyncio.run(h.cb_hint_dismiss(cb))
    assert cb.message.edits[-1][0] == "✅"


# ---------- _get_full_text_from_chroma ----------


class FakeOs:
    """Fake os module: path functions configurable per test."""

    def __init__(self, db_path, exists=True):
        self.db_path = db_path
        self._exists = exists

        class _Path:
            def __init__(self, outer):
                self.outer = outer

            def expanduser(self, p):
                return self.outer.db_path

            def exists(self, p):
                return self.outer._exists

            def basename(self, p):
                return p.rsplit("/", 1)[-1]

        self.path = _Path(self)
        import builtins
        self.builtins = builtins


def _enable_fake_os(monkeypatch, db_path, exists=True):
    monkeypatch.setattr(h, "os", FakeOs(db_path, exists))


def test_chroma_empty_source(monkeypatch, tmp_path):
    assert h._get_full_text_from_chroma("") == ""


def test_chroma_db_missing(monkeypatch, tmp_path):
    _enable_fake_os(
        monkeypatch,
        str(tmp_path / "no_such_dir" / "chroma.sqlite3"),
        exists=False,
    )
    assert h._get_full_text_from_chroma("some/source.md") == ""


def test_chroma_db_exists_no_match(monkeypatch, tmp_path):
    import sqlite3

    db = tmp_path / "chroma.sqlite3"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE embedding_metadata (id TEXT, key TEXT, string_value TEXT)",
    )
    con.execute(
        "CREATE TABLE embeddings (id TEXT, embedding_id TEXT)",
    )
    con.commit()
    con.close()
    _enable_fake_os(monkeypatch, str(db))
    assert h._get_full_text_from_chroma("some/source.md") == ""


def test_chroma_db_full_text(monkeypatch, tmp_path):
    import sqlite3

    db = tmp_path / "chroma.sqlite3"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE embedding_metadata (id TEXT, key TEXT, string_value TEXT)",
    )
    con.execute(
        "CREATE TABLE embeddings (id TEXT, embedding_id TEXT)",
    )
    con.executemany(
        "INSERT INTO embedding_metadata VALUES (?, ?, ?)",
        [
            ("e1", "source_file", "source.md"),
            ("e1", "chroma:document", "блок один"),
            ("e2", "source_file", "source.md"),
            ("e2", "chroma:document", "блок два"),
        ],
    )
    con.executemany(
        "INSERT INTO embeddings VALUES (?, ?)",
        [("e1", "drawer_1"), ("e2", "drawer_2")],
    )
    con.commit()
    con.close()
    _enable_fake_os(monkeypatch, str(db))
    out = h._get_full_text_from_chroma("C:\\palace\\source.md")
    assert "блок один" in out
    assert "блок два" in out


def test_chroma_db_duplicate_blocks(monkeypatch, tmp_path):
    import sqlite3

    db = tmp_path / "chroma.sqlite3"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE embedding_metadata (id TEXT, key TEXT, string_value TEXT)",
    )
    con.execute(
        "CREATE TABLE embeddings (id TEXT, embedding_id TEXT)",
    )
    con.executemany(
        "INSERT INTO embedding_metadata VALUES (?, ?, ?)",
        [
            ("e1", "source_file", "source.md"),
            ("e1", "chroma:document", "блок"),
            ("e2", "source_file", "source.md"),
            ("e2", "chroma:document", "блок"),
        ],
    )
    con.executemany(
        "INSERT INTO embeddings VALUES (?, ?)",
        [("e1", "drawer_1"), ("e2", "drawer_2")],
    )
    con.commit()
    con.close()
    _enable_fake_os(monkeypatch, str(db))
    out = h._get_full_text_from_chroma("source.md")
    assert out == "блок"


def test_chroma_db_error(monkeypatch, tmp_path):
    import sqlite3

    def boom(*a, **k):
        raise sqlite3.OperationalError("нет таблицы")

    monkeypatch.setattr(h.sqlite3, "connect", boom)
    monkeypatch.setattr(
        h.os, "path", SimpleNamespace(
            expanduser=lambda p: "/fake/chroma.sqlite3",
            exists=lambda p: True,
            basename=lambda p: p.rsplit("/", 1)[-1],
        ),
    )
    assert h._get_full_text_from_chroma("source.md") == ""
