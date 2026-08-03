"""Тесты выбора крыла в навигации Дворца — callback_data по ключу вместо base64-имени.

Регрессия: cb_list_wings строил кнопки p_rs_:{base64(имя крыла)}; для длинных
крыльев callback_data превышала лимит Telegram 64 байта, и Telegram отклонял
клавиатуру целиком (BUTTON_DATA_INVALID) — список крыльев не появлялся.
"""
import json

import pytest

from handlers.palace import navigation

LONG_WING = "ПСИХОАНАЛИТИЧЕСКАЯ МОДЕЛЬ ОПЫТА В ТВОРЧЕСТВЕ ФОТОГРАФА"
SHORT_WING = "проекты"

WINGS = {"личные_мысли": 42, SHORT_WING: 17, LONG_WING: 3}

UID = 424242


class FakeMessage:
    def __init__(self, edit_ok=True):
        self.edited = []
        self.edit_ok = edit_ok

    async def edit_text(self, text, **kwargs):
        if self.edit_ok:
            self.edited.append((text, kwargs))
            return True
        return None

    async def answer(self, text, **kwargs):
        self.edited.append((text, kwargs))
        return True


class FakeCallback:
    def __init__(self, data, message=None, user_id=UID):
        self.data = data
        self.message = message or FakeMessage()
        self.from_user = type("User", (), {"id": user_id})()
        self.answered = False

    async def answer(self, *args, **kwargs):
        self.answered = True


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {UID})
    navigation._wing_callback_map.clear()
    from handlers.palace.shared import _wing_cache

    _wing_cache.pop(UID, None)
    yield
    navigation._wing_callback_map.clear()
    _wing_cache.pop(UID, None)


def _patch_mcp_list_wings(monkeypatch):
    class FakeMcp:
        async def call_tool(self, tool, args=None):
            if tool == "mempalace_list_wings":
                return json.dumps({"wings": WINGS})
            raise AssertionError(f"unexpected tool: {tool}")

    monkeypatch.setattr(navigation, "get_mcp", lambda: FakeMcp())


def _patch_mcp_list_rooms(monkeypatch, rooms):
    class FakeMcp:
        async def call_tool(self, tool, args=None):
            if tool == "mempalace_list_rooms":
                return json.dumps({"rooms": rooms})
            raise AssertionError(f"unexpected tool: {tool}")

    monkeypatch.setattr(navigation, "get_mcp", lambda: FakeMcp())


def _markup_of(msg):
    return msg.edited[-1][1]["reply_markup"]


def _buttons_of(msg):
    markup = _markup_of(msg)
    return [
        b for row in markup.inline_keyboard
        for b in row if not b.callback_data.startswith("p_nav")
    ]


@pytest.mark.asyncio
async def test_list_wings_long_wing_callback_under_64_bytes(monkeypatch):
    """Граница: callback_data длинного крыла ≤ 64 байт (лимит Telegram)."""
    _patch_mcp_list_wings(monkeypatch)
    msg = FakeMessage()
    cb = FakeCallback("p_wing", msg)
    await navigation.cb_list_wings(cb)
    assert "🕸️ Крылья MemPalace" in msg.edited[-1][0]
    for b in _buttons_of(msg):
        if b.callback_data.startswith("p_rs_:"):
            assert len(b.callback_data.encode("utf-8")) <= 64


@pytest.mark.asyncio
async def test_list_wings_all_wings_present(monkeypatch):
    _patch_mcp_list_wings(monkeypatch)
    msg = FakeMessage()
    await navigation.cb_list_wings(FakeCallback("p_wing", msg))
    text = msg.edited[-1][0]
    assert LONG_WING in text
    assert SHORT_WING in text


@pytest.mark.asyncio
async def test_list_wings_sorted_by_count_desc(monkeypatch):
    _patch_mcp_list_wings(monkeypatch)
    msg = FakeMessage()
    await navigation.cb_list_wings(FakeCallback("p_wing", msg))
    names = [b.text for b in _buttons_of(msg)]
    assert names == ["🪪 личные_мысли", f"🪪 {SHORT_WING}", f"🪪 {LONG_WING}"]


@pytest.mark.asyncio
async def test_select_long_wing_opens_rooms(monkeypatch):
    _patch_mcp_list_rooms(monkeypatch, {"Комната А": 1})
    msg = FakeMessage()
    cb = FakeCallback(navigation._build_wing_callback_data(LONG_WING), msg)
    await navigation.cb_rooms_select(cb)
    assert f"Комнаты крыла {LONG_WING}" in msg.edited[-1][0]
    assert "Комната А" in msg.edited[-1][0]


@pytest.mark.asyncio
async def test_select_short_wing_opens_rooms(monkeypatch):
    _patch_mcp_list_rooms(monkeypatch, {"Комната Б": 5})
    msg = FakeMessage()
    cb = FakeCallback(navigation._build_wing_callback_data(SHORT_WING), msg)
    await navigation.cb_rooms_select(cb)
    assert f"Комнаты крыла {SHORT_WING}" in msg.edited[-1][0]


@pytest.mark.asyncio
async def test_select_wing_unknown_key_fallback_to_base64(monkeypatch):
    """Негатив: ключ отсутствует в мапе — фолбэк на legacy base64-декодирование."""
    _patch_mcp_list_rooms(monkeypatch, {"Комната": 1})
    msg = FakeMessage()
    legacy = (
        "p_rs_:"
        + navigation._encode_callback_part(SHORT_WING)
    )
    cb = FakeCallback(legacy, msg)
    await navigation.cb_rooms_select(cb)
    assert f"Комнаты крыла {SHORT_WING}" in msg.edited[-1][0]


@pytest.mark.asyncio
async def test_select_wing_empty_rooms(monkeypatch):
    _patch_mcp_list_rooms(monkeypatch, {})
    msg = FakeMessage()
    cb = FakeCallback(navigation._build_wing_callback_data(SHORT_WING), msg)
    await navigation.cb_rooms_select(cb)
    assert "нет комнат" in msg.edited[-1][0]


@pytest.mark.asyncio
async def test_select_wing_short_data_ignored(monkeypatch):
    _patch_mcp_list_rooms(monkeypatch, {})
    msg = FakeMessage()
    cb = FakeCallback("p_rs_:x", msg)
    await navigation.cb_rooms_select(cb)
    assert len(msg.edited) == 1
    assert "нет комнат" in msg.edited[0][0]


@pytest.mark.asyncio
async def test_mcp_error_shows_message(monkeypatch):
    class FailingMcp:
        async def call_tool(self, tool, args=None):
            raise RuntimeError("MCP down")

    monkeypatch.setattr(navigation, "get_mcp", lambda: FailingMcp())
    msg = FakeMessage()
    cb = FakeCallback(navigation._build_wing_callback_data(SHORT_WING), msg)
    await navigation.cb_rooms_select(cb)
    assert "Ошибка загрузки комнат" in msg.edited[-1][0]


@pytest.mark.asyncio
async def test_wings_sorted_cached_in_state(monkeypatch):
    _patch_mcp_list_wings(monkeypatch)
    msg = FakeMessage()
    await navigation.cb_list_wings(FakeCallback("p_wing", msg))
    from handlers.palace.shared import _wing_cache

    assert _wing_cache.get(UID) == ["личные_мысли", SHORT_WING, LONG_WING]
