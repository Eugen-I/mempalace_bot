"""Unit tests for handlers.palace.admin."""

import asyncio

import pytest

from handlers.palace import admin as a


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeMessage:
    def __init__(self, uid=4242):
        self.from_user = FakeUser(uid)
        self.answers = []
        self.edits = []

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append((text, parse_mode, reply_markup))
        return self

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append((text, parse_mode, reply_markup))


class FakeCb:
    def __init__(self, uid=4242, data="", message=None):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = message or FakeMessage(uid)
        self.answered = []

    async def answer(self, text=None, show_alert=None):
        self.answered.append((text, show_alert))


def _enable(monkeypatch):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {4242})


def _async_result(value):
    async def _inner(*a, **kw):
        return value

    return _inner


# ---------- _finalize_admin_result ----------


def test_finalize_admin_result(monkeypatch):
    _enable(monkeypatch)
    captured = {}

    async def fake_finalize(uid, edit_func, text, ctx=None, extra_rows=None):
        captured["uid"] = uid
        captured["edit_func"] = edit_func
        captured["text"] = text
        captured["ctx"] = ctx

    monkeypatch.setattr(
        "handlers.palace.action_bar.finalize_answer", fake_finalize,
    )
    msg = FakeMessage()
    asyncio.run(a._finalize_admin_result(4242, msg.edit_text, "текст", "parent_x"))
    assert captured["uid"] == 4242
    assert captured["text"] == "текст"
    assert captured["ctx"] == {"parent_cb": "parent_x"}


def test_finalize_admin_result_empty(monkeypatch):
    _enable(monkeypatch)
    captured = {}

    async def fake_finalize(uid, edit_func, text, ctx=None, extra_rows=None):
        captured["text"] = text

    monkeypatch.setattr(
        "handlers.palace.action_bar.finalize_answer", fake_finalize,
    )
    msg = FakeMessage()
    asyncio.run(a._finalize_admin_result(4242, msg.edit_text, "", "parent_x"))
    assert captured["text"] == "❌ Нет данных."


# ---------- cb_palace_status / cb_palace_mcp / cb_palace_instructions ----------


def test_cb_palace_status_success(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(a, "palace_status", _async_result("статус ок"))
    seen = []
    monkeypatch.setattr(
        a, "_finalize_admin_result",
        lambda uid, ef, text, parent_cb: seen.append((uid, text, parent_cb)),
    )
    cb = FakeCb(data="palace_status")
    asyncio.run(a.cb_palace_status(cb))
    assert cb.message.answers[0][0] == "🔍 Получаю статус..."
    assert seen[0] == (4242, "статус ок", "palace_back")


def test_cb_palace_status_error(monkeypatch):
    _enable(monkeypatch)

    async def boom():
        raise RuntimeError("status fail")

    monkeypatch.setattr(a, "palace_status", boom)
    cb = FakeCb(data="palace_status")
    asyncio.run(a.cb_palace_status(cb))
    assert cb.message.edits[-1][0] == "❌ Ошибка: status fail"


def test_cb_palace_mcp_success(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(a, "palace_mcp", _async_result("mcp cfg"))
    seen = []
    monkeypatch.setattr(
        a, "_finalize_admin_result",
        lambda uid, ef, text, parent_cb: seen.append((uid, text, parent_cb)),
    )
    cb = FakeCb(data="palace_mcp")
    asyncio.run(a.cb_palace_mcp(cb))
    assert cb.message.answers[0][0] == "🔌 Получаю настройку MCP..."
    assert seen[0] == (4242, "mcp cfg", "palace_admin")


def test_cb_palace_mcp_error(monkeypatch):
    _enable(monkeypatch)

    async def boom():
        raise RuntimeError("mcp fail")

    monkeypatch.setattr(a, "palace_mcp", boom)
    cb = FakeCb(data="palace_mcp")
    asyncio.run(a.cb_palace_mcp(cb))
    assert cb.message.edits[-1][0] == "❌ Ошибка: mcp fail"


def test_cb_palace_instructions_success(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(a, "palace_instructions", _async_result("инструкции"))
    seen = []
    monkeypatch.setattr(
        a, "_finalize_admin_result",
        lambda uid, ef, text, parent_cb: seen.append((uid, text, parent_cb)),
    )
    cb = FakeCb(data="palace_instructions")
    asyncio.run(a.cb_palace_instructions(cb))
    assert seen[0] == (4242, "инструкции", "palace_back")


def test_cb_palace_instructions_error(monkeypatch):
    _enable(monkeypatch)

    async def boom():
        raise RuntimeError("instr fail")

    monkeypatch.setattr(a, "palace_instructions", boom)
    cb = FakeCb(data="palace_instructions")
    asyncio.run(a.cb_palace_instructions(cb))
    assert cb.message.edits[-1][0] == "❌ Ошибка: instr fail"


# ---------- cb_palace_admin ----------


def test_cb_palace_admin(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="palace_admin")
    asyncio.run(a.cb_palace_admin(cb))
    body, parse_mode, kb = cb.message.edits[-1]
    assert "Обслуживание дворца" in body
    assert parse_mode == "Markdown"
    data = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert data == [
        "palace_repair", "palace_compact", "palace_compress",
        "palace_wakeup", "palace_back",
    ]


# ---------- background tasks (repair/compact/compress/wakeup) ----------


def test_cb_palace_repair_success(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(a, "palace_repair", _async_result("repair done"))
    seen = []
    monkeypatch.setattr(
        a, "_finalize_admin_result",
        lambda uid, ef, text, parent_cb: seen.append((uid, text, parent_cb)),
    )
    tasks = []
    monkeypatch.setattr(
        a.asyncio, "create_task", lambda coro: tasks.append(coro),
    )
    cb = FakeCb(data="palace_repair")
    asyncio.run(a.cb_palace_repair(cb))
    assert cb.message.answers[0][0].startswith("🔁 Repair")
    asyncio.run(tasks[0])
    assert seen[0] == (4242, "repair done", "palace_admin")


def test_cb_palace_repair_error(monkeypatch):
    _enable(monkeypatch)

    async def boom():
        raise RuntimeError("repair fail")

    monkeypatch.setattr(a, "palace_repair", boom)
    tasks = []
    monkeypatch.setattr(
        a.asyncio, "create_task", lambda coro: tasks.append(coro),
    )
    cb = FakeCb(data="palace_repair")
    asyncio.run(a.cb_palace_repair(cb))
    asyncio.run(tasks[0])
    assert cb.message.edits[-1][0] == "❌ Ошибка: repair fail"


def test_cb_palace_compact_success(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(a, "palace_compact", _async_result("compacted"))
    seen = []
    monkeypatch.setattr(
        a, "_finalize_admin_result",
        lambda uid, ef, text, parent_cb: seen.append((uid, text, parent_cb)),
    )
    tasks = []
    monkeypatch.setattr(
        a.asyncio, "create_task", lambda coro: tasks.append(coro),
    )
    cb = FakeCb(data="palace_compact")
    asyncio.run(a.cb_palace_compact(cb))
    assert cb.message.answers[0][0].startswith("🗜️ Compact")
    asyncio.run(tasks[0])
    assert seen[0] == (4242, "compacted", "palace_admin")


def test_cb_palace_compact_error(monkeypatch):
    _enable(monkeypatch)

    async def boom():
        raise RuntimeError("compact fail")

    monkeypatch.setattr(a, "palace_compact", boom)
    tasks = []
    monkeypatch.setattr(
        a.asyncio, "create_task", lambda coro: tasks.append(coro),
    )
    cb = FakeCb(data="palace_compact")
    asyncio.run(a.cb_palace_compact(cb))
    asyncio.run(tasks[0])
    assert cb.message.edits[-1][0] == "❌ Ошибка: compact fail"


def test_cb_palace_compress_success(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(a, "palace_compress", _async_result("compressed"))
    seen = []
    monkeypatch.setattr(
        a, "_finalize_admin_result",
        lambda uid, ef, text, parent_cb: seen.append((uid, text, parent_cb)),
    )
    tasks = []
    monkeypatch.setattr(
        a.asyncio, "create_task", lambda coro: tasks.append(coro),
    )
    cb = FakeCb(data="palace_compress")
    asyncio.run(a.cb_palace_compress(cb))
    asyncio.run(tasks[0])
    assert seen[0] == (4242, "compressed", "palace_admin")


def test_cb_palace_compress_error(monkeypatch):
    _enable(monkeypatch)

    async def boom():
        raise RuntimeError("compress fail")

    monkeypatch.setattr(a, "palace_compress", boom)
    tasks = []
    monkeypatch.setattr(
        a.asyncio, "create_task", lambda coro: tasks.append(coro),
    )
    cb = FakeCb(data="palace_compress")
    asyncio.run(a.cb_palace_compress(cb))
    asyncio.run(tasks[0])
    assert cb.message.edits[-1][0] == "❌ Ошибка: compress fail"


def test_cb_palace_wakeup_success(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(a, "palace_wake_up", _async_result("woken"))
    seen = []
    monkeypatch.setattr(
        a, "_finalize_admin_result",
        lambda uid, ef, text, parent_cb: seen.append((uid, text, parent_cb)),
    )
    tasks = []
    monkeypatch.setattr(
        a.asyncio, "create_task", lambda coro: tasks.append(coro),
    )
    cb = FakeCb(data="palace_wakeup")
    asyncio.run(a.cb_palace_wakeup(cb))
    assert cb.message.answers[0][0].startswith("🌙")
    asyncio.run(tasks[0])
    assert seen[0] == (4242, "woken", "palace_admin")


def test_cb_palace_wakeup_error(monkeypatch):
    _enable(monkeypatch)

    async def boom():
        raise RuntimeError("wakeup fail")

    monkeypatch.setattr(a, "palace_wake_up", boom)
    tasks = []
    monkeypatch.setattr(
        a.asyncio, "create_task", lambda coro: tasks.append(coro),
    )
    cb = FakeCb(data="palace_wakeup")
    asyncio.run(a.cb_palace_wakeup(cb))
    asyncio.run(tasks[0])
    assert cb.message.edits[-1][0] == "❌ Ошибка: wakeup fail"


# ---------- not allowed ----------


@pytest.mark.parametrize(
    "data",
    ["palace_status", "palace_mcp", "palace_instructions", "palace_admin",
     "palace_repair", "palace_compact", "palace_compress", "palace_wakeup"],
)
def test_callbacks_not_allowed(monkeypatch, data):
    _enable(monkeypatch)
    cb = FakeCb(uid=999, data=data)
    mapping = {
        "palace_status": a.cb_palace_status,
        "palace_mcp": a.cb_palace_mcp,
        "palace_instructions": a.cb_palace_instructions,
        "palace_admin": a.cb_palace_admin,
        "palace_repair": a.cb_palace_repair,
        "palace_compact": a.cb_palace_compact,
        "palace_compress": a.cb_palace_compress,
        "palace_wakeup": a.cb_palace_wakeup,
    }
    asyncio.run(mapping[data](cb))
    assert cb.answered == [("❌ Нет доступа", True)]


def test_spawn_background_task_tracks_and_cleans_up():
    """Регрессия: фоновые задачи хранятся в _background_tasks и удаляются по завершении."""
    async def _scenario():
        done = asyncio.Event()

        async def _worker():
            await done.wait()

        a._spawn_background_task(_worker())
        assert len(a._background_tasks) >= 1
        done.set()
        await asyncio.sleep(0.01)
        assert len(a._background_tasks) == 0

    asyncio.run(_scenario())
