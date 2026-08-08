"""Unit tests for services.bot_setup (bot factory + security middleware)."""

import pytest

import services.bot_setup as bs


class FakeUser:
    def __init__(self, id):
        self.id = id


class FakeMessage:
    def __init__(self, user):
        self.from_user = user


class FakeCallbackQuery:
    def __init__(self, user):
        self.from_user = user


class FakeEvent:
    def __init__(self, user=None, message=None, callback_query=None):
        self.from_user = user
        self.message = message
        self.callback_query = callback_query


# ---------- set_logger / init_bot ----------


def test_set_logger_stores_globally():
    import logging

    lg = logging.getLogger("test")
    bs.set_logger(lg)
    assert bs.logger is lg


def test_init_bot_returns_global_bot_dp(monkeypatch):
    registered = []
    monkeypatch.setattr(bs.dp.message, "middleware", lambda fn: registered.append(("message", fn)))
    monkeypatch.setattr(
        bs.dp.callback_query,
        "middleware",
        lambda fn: registered.append(("cb", fn)),
    )
    bot, dp = bs.init_bot(None)
    assert bot is bs.bot
    assert dp is bs.dp
    assert [r[0] for r in registered] == ["message", "cb"]
    assert registered[0][1] is bs.security_middleware


def test_init_bot_sets_logger():
    import logging

    lg = logging.getLogger("init")
    bs.init_bot(lg)
    assert bs.logger is lg


# ---------- caches ----------


def test_caches_exist():
    assert bs.photo_delete_cache.maxsize == 500
    assert bs.pending_web_search.ttl == 120
    assert bs.yt_audio_cache.ttl == 3600
    assert bs.sync_counter.ttl == 3600


# ---------- security_middleware ----------


@pytest.mark.asyncio
async def test_security_allows_allowed_user(monkeypatch):
    monkeypatch.setattr(bs, "ALLOWED_IDS", {111})
    called = []

    async def handler(event, data):
        called.append(event)
        return "ok"

    res = await bs.security_middleware(handler, FakeEvent(user=FakeUser(111)), {})
    assert res == "ok"
    assert called


@pytest.mark.asyncio
async def test_security_blocks_unknown_user(monkeypatch):
    monkeypatch.setattr(bs, "ALLOWED_IDS", {111})
    warned = []
    monkeypatch.setattr(
        bs,
        "logger",
        type("L", (), {"warning": lambda self, m: warned.append(m)})(),
    )

    async def handler(event, data):
        raise AssertionError("не должно вызываться")

    res = await bs.security_middleware(handler, FakeEvent(user=FakeUser(999)), {})
    assert res is None
    assert any("Blocked" in w for w in warned)


@pytest.mark.asyncio
async def test_security_blocked_without_logger(monkeypatch):
    monkeypatch.setattr(bs, "ALLOWED_IDS", {111})
    monkeypatch.setattr(bs, "logger", None)

    async def handler(event, data):
        raise AssertionError("не должно вызываться")

    assert await bs.security_middleware(handler, FakeEvent(user=FakeUser(500)), {}) is None


@pytest.mark.asyncio
async def test_security_uid_from_message(monkeypatch):
    monkeypatch.setattr(bs, "ALLOWED_IDS", {222})
    called = []

    async def handler(event, data):
        called.append(True)
        return None

    ev = FakeEvent(message=FakeMessage(FakeUser(222)))
    await bs.security_middleware(handler, ev, {})
    assert called


@pytest.mark.asyncio
async def test_security_uid_from_message_blocked(monkeypatch):
    monkeypatch.setattr(bs, "ALLOWED_IDS", {222})
    monkeypatch.setattr(bs, "logger", None)

    async def handler(event, data):
        raise AssertionError("не должно вызываться")

    ev = FakeEvent(message=FakeMessage(FakeUser(777)))
    assert await bs.security_middleware(handler, ev, {}) is None


@pytest.mark.asyncio
async def test_security_uid_from_callback_query(monkeypatch):
    monkeypatch.setattr(bs, "ALLOWED_IDS", {333})
    called = []

    async def handler(event, data):
        called.append(True)
        return None

    ev = FakeEvent(callback_query=FakeCallbackQuery(FakeUser(333)))
    await bs.security_middleware(handler, ev, {})
    assert called


@pytest.mark.asyncio
async def test_security_uid_from_callback_blocked(monkeypatch):
    monkeypatch.setattr(bs, "ALLOWED_IDS", {333})
    monkeypatch.setattr(bs, "logger", None)

    async def handler(event, data):
        raise AssertionError("не должно вызываться")

    ev = FakeEvent(callback_query=FakeCallbackQuery(FakeUser(444)))
    assert await bs.security_middleware(handler, ev, {}) is None


@pytest.mark.asyncio
async def test_security_no_user_id_passes(monkeypatch):
    monkeypatch.setattr(bs, "ALLOWED_IDS", {111})
    called = []

    async def handler(event, data):
        called.append(True)
        return None

    ev = FakeEvent()
    await bs.security_middleware(handler, ev, {})
    assert called


@pytest.mark.asyncio
async def test_security_message_without_from_user(monkeypatch):
    """message есть, но from_user None → uid None → handler выполняется."""
    monkeypatch.setattr(bs, "ALLOWED_IDS", {111})
    called = []

    async def handler(event, data):
        called.append(True)
        return None

    ev = FakeEvent(message=FakeMessage(None))
    await bs.security_middleware(handler, ev, {})
    assert called
