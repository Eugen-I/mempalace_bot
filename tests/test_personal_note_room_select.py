"""Тесты Шага 1 ТЗ (личные мысли): выбор крыла по индексу вместо полного имени.

Баг: callback_data=f"pn_wing:{wing}" с длинными именами крыльев (>64 байт)
отклонялся Telegram (BUTTON_DATA_INVALID) → «✏️ Другая комната» молча не работал.
"""
import asyncio

import pytest

TEST_UID = 424242


@pytest.fixture(autouse=True)
def _allow_test_user(monkeypatch):
    import config

    from handlers.personal_note import _note_data, _waiting_for_note

    monkeypatch.setattr(config, "ALLOWED_IDS", {TEST_UID})
    _note_data.clear()
    _waiting_for_note.clear()
    yield
    _note_data.clear()


class FakeMessage:
    def __init__(self):
        self.edited = []
        self.markups = []

    async def edit_text(self, text, **kwargs):
        self.edited.append(text)
        self.markups.append(kwargs.get("reply_markup"))
        return self

    async def answer(self, text=None, **kwargs):
        self.edited.append(text or "")
        self.markups.append(kwargs.get("reply_markup"))
        return self


class FakeCallback:
    def __init__(self, data, msg=None):
        self.data = data
        self.message = msg or FakeMessage()
        self.answered = None
        self.from_user = type("U", (), {"id": TEST_UID})()

    async def answer(self, text=None, **kwargs):
        self.answered = (text, kwargs)


def _markup_data(msg, idx=-1):
    kb = msg.markups[idx]
    if kb is None:
        return []
    return [b.callback_data for row in kb.inline_keyboard for b in row]


def _long_wing():
    return "ПСИХОАНАЛИТИЧЕСКАЯ МОДЕЛЬ ОПЫТА В ТВОРЧЕСТВЕ ФОТОГРАФА"


def _seed_note_data(wing_name=_long_wing()):
    from handlers.personal_note import _note_data

    _note_data[TEST_UID] = {
        "text": "Заметка",
        "raw": "Заметка",
        "wing": "личные_мысли",
        "room": "inbox",
        "taxonomy": {
            wing_name: {"Комната": {}},
            "my_notes": {"general": {}},
        },
    }


def _button_texts(msg, idx=-1):
    kb = msg.markups[idx]
    if kb is None:
        return []
    return [b.text for row in kb.inline_keyboard for b in row]


# ─── ШАГ 1: cb_pn_reclass строит клавиатуру с индексами ───


def test_reclass_uses_index_callback_data():
    from handlers.personal_note import cb_pn_reclass

    _seed_note_data()
    msg = FakeMessage()
    cb = FakeCallback("pn_reclass", msg)
    asyncio.run(cb_pn_reclass(cb))
    data = _markup_data(msg)
    assert "pn_wing:0" in data
    assert "pn_wing:1" in data
    assert "pn_wing:2" in data
    assert _long_wing() not in "".join(data)


def test_reclass_all_callback_data_within_64_bytes():
    from handlers.personal_note import cb_pn_reclass

    _seed_note_data()
    msg = FakeMessage()
    cb = FakeCallback("pn_reclass", msg)
    asyncio.run(cb_pn_reclass(cb))
    for cd in _markup_data(msg):
        assert len(cd.encode("utf-8")) <= 64


def test_reclass_render_text_contains_full_wing_name():
    from handlers.personal_note import cb_pn_reclass

    _seed_note_data()
    msg = FakeMessage()
    cb = FakeCallback("pn_reclass", msg)
    asyncio.run(cb_pn_reclass(cb))
    assert "Выберите крыло" in msg.edited[-1]
    assert any(_long_wing() in t for t in _button_texts(msg))


def test_reclass_empty_session():
    from handlers.personal_note import cb_pn_reclass

    msg = FakeMessage()
    cb = FakeCallback("pn_reclass", msg)
    asyncio.run(cb_pn_reclass(cb))
    assert "Сессия истекла" in msg.edited[-1]


# ─── ШАГ 1: cb_pn_wing парсит индекс обратно в имя ───


def test_wing_select_by_index():
    from handlers.personal_note import cb_pn_wing, _note_data

    _seed_note_data()
    _note_data[TEST_UID]["wings"] = ["личные_мысли", _long_wing(), "my_notes"]
    msg = FakeMessage()
    cb = FakeCallback("pn_wing:1", msg)
    asyncio.run(cb_pn_wing(cb))
    assert _long_wing() in msg.edited[-1]
    assert _note_data[TEST_UID]["wing"] == _long_wing()


def test_wing_select_index_zero():
    from handlers.personal_note import cb_pn_wing, _note_data

    _seed_note_data()
    _note_data[TEST_UID]["wings"] = ["личные_мысли", "my_notes"]
    msg = FakeMessage()
    cb = FakeCallback("pn_wing:0", msg)
    asyncio.run(cb_pn_wing(cb))
    assert "личные_мысли" in msg.edited[-1]
    assert _note_data[TEST_UID]["wing"] == "личные_мысли"


def test_wing_select_out_of_range_falls_back():
    from handlers.personal_note import cb_pn_wing, _note_data

    _seed_note_data()
    _note_data[TEST_UID]["wings"] = ["личные_мысли", "my_notes"]
    msg = FakeMessage()
    cb = FakeCallback("pn_wing:99", msg)
    asyncio.run(cb_pn_wing(cb))
    assert _note_data[TEST_UID]["wing"] == "личные_мысли"


def test_wing_select_malformed_index_falls_back():
    from handlers.personal_note import cb_pn_wing, _note_data

    _seed_note_data()
    _note_data[TEST_UID]["wings"] = ["личные_мысли", "my_notes"]
    msg = FakeMessage()
    cb = FakeCallback("pn_wing:abc", msg)
    asyncio.run(cb_pn_wing(cb))
    assert _note_data[TEST_UID]["wing"] == "личные_мысли"


def test_wing_select_empty_session():
    from handlers.personal_note import cb_pn_wing

    msg = FakeMessage()
    cb = FakeCallback("pn_wing:0", msg)
    asyncio.run(cb_pn_wing(cb))
    assert "Сессия истекла" in msg.edited[-1]


def test_wing_select_no_rooms_falls_back_to_inbox():
    from handlers.personal_note import cb_pn_wing, _note_data

    _seed_note_data()
    _note_data[TEST_UID]["wings"] = ["личные_мысли"]
    _note_data[TEST_UID]["taxonomy"] = {}
    msg = FakeMessage()
    cb = FakeCallback("pn_wing:0", msg)
    asyncio.run(cb_pn_wing(cb))
    assert _note_data[TEST_UID]["room_list"] == ["inbox"]
    assert any(t == "🆕 inbox" for t in _button_texts(msg))
