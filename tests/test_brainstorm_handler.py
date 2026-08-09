"""Unit-тесты для handlers.brainstorm — Telegram-обвязка штурма.

Паттерн: happy path + негативные сценарии + граничные значения (BVA).
Модель (get_ai_response_async), контекст (collect_context) и save-флоу
Дворца замоканы; проверяется маршрутизация, кнопки и мост в сохранение.
"""

import json

import pytest

from handlers import brainstorm as h
from services import brainstorm as bs


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeStatus:
    def __init__(self):
        self.edits = []
        self.last_kw = None

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)
        self.last_kw = {"parse_mode": parse_mode, "reply_markup": reply_markup}


class FakeMessage:
    def __init__(self, uid=4242, text="/штурм фото"):
        self.from_user = FakeUser(uid)
        self.chat = type("C", (), {"id": 1})()
        self.text = text
        self.answers = []
        self.edits = []

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append(text)
        status = FakeStatus()
        self.last_status = status
        return status

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)


class FakeCb:
    def __init__(self, uid=4242, data=""):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = FakeMessage(uid)
        self.answers = []

    async def answer(self, text=None, show_alert=None):
        self.answers.append((text, show_alert))


def _ideas(n=5):
    return [{"title": f"Идея {i}", "reason": "р", "steps": "ш"} for i in range(1, n + 1)]


@pytest.fixture(autouse=True)
def allow_user(monkeypatch):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", [4242], raising=False)
    monkeypatch.setattr(config, "ADMIN_ID", 4242, raising=False)


@pytest.fixture(autouse=True)
def mock_ai(monkeypatch):
    async def _fake_ai(engine, model, msgs):
        return json.dumps({"ideas": _ideas()}, ensure_ascii=False)

    monkeypatch.setattr(h, "get_ai_response_async", _fake_ai)
    monkeypatch.setattr(h, "get_current_ai", lambda: ("ollama", "qwen2.5"))

    async def _fake_context(topic):
        return {"notes": "n", "palace": "p", "kg": "k"}

    monkeypatch.setattr(bs, "collect_context", _fake_context)
    h._storm_data.clear()
    h._storm_waiting.clear()


# ─── run_storm: happy path ───

async def test_run_storm_shows_ideas_with_buttons():
    status = FakeStatus()
    await h.run_storm(4242, status, "Фото-проект")
    assert any("Штурм" in t for t in status.edits)
    final = status.edits[-1]
    assert "Идея 1" in final
    markup = status.last_kw["reply_markup"]
    texts = [b.text for r in markup.inline_keyboard for b in r]
    assert "💡 1" in texts and "💡 5" in texts
    assert "💾 Сохранить все" in texts


async def test_run_storm_empty_topic_shows_error():
    status = FakeStatus()
    await h.run_storm(4242, status, "   ")
    assert "Тема не задана" in status.edits[-1]


async def test_run_storm_parse_error_shown():
    async def _bad_ai(engine, model, msgs):
        return "не json"

    h.get_ai_response_async = _bad_ai
    status = FakeStatus()
    await h.run_storm(4242, status, "Тема")
    assert "Ошибка штурма" in status.edits[-1]


async def test_run_storm_context_empty_still_works(monkeypatch):
    async def _empty(topic):
        return {"notes": "", "palace": "", "kg": ""}

    monkeypatch.setattr(bs, "collect_context", _empty)
    status = FakeStatus()
    await h.run_storm(4242, status, "Тема")
    assert any("Идея 1" in t for t in status.edits)


async def test_run_storm_context_error_shows_error():
    async def _boom(topic):
        raise RuntimeError("notes down")

    bs.collect_context = _boom
    status = FakeStatus()
    await h.run_storm(4242, status, "Тема")
    assert "Ошибка штурма" in status.edits[-1]


# ─── Команда /штурм ───

async def test_cmd_storm_with_topic_runs():
    msg = FakeMessage(text="/штурм  Фото-проект")
    await h.cmd_storm(msg)
    assert any("Запускаю штурм" in a for a in msg.answers)
    assert msg.last_status.edits


async def test_cmd_storm_without_topic_asks():
    msg = FakeMessage(text="/штурм")
    await h.cmd_storm(msg)
    assert "Введите тему" in msg.answers[0]
    assert 4242 in h._storm_waiting


async def test_btn_storm_asks_topic():
    msg = FakeMessage(text="🧠 Штурм")
    await h.btn_storm(msg)
    assert "Введите тему" in msg.answers[0]
    assert 4242 in h._storm_waiting


# ─── Выбор идеи ───

async def test_cb_pick_idea_shows_preview():
    await h.run_storm(4242, FakeStatus(), "Тема")
    cb = FakeCb(data="bs_pick:2")
    await h.cb_pick_idea(cb)
    assert "Сохранить в Дворец" in cb.message.edits[-1]


async def test_cb_pick_idea_expired_session():
    cb = FakeCb(data="bs_pick:1")
    await h.cb_pick_idea(cb)
    assert "Сессия истекла" in cb.message.edits[-1]


async def test_cb_pick_idea_out_of_range():
    await h.run_storm(4242, FakeStatus(), "Тема")
    cb = FakeCb(data="bs_pick:99")
    await h.cb_pick_idea(cb)
    assert "не найдена" in cb.message.edits[-1]


async def test_cb_pick_idea_bad_index():
    await h.run_storm(4242, FakeStatus(), "Тема")
    cb = FakeCb(data="bs_pick:abc")
    await h.cb_pick_idea(cb)
    assert "не найдена" in cb.message.edits[-1]


async def test_cb_all_shows_preview_all():
    await h.run_storm(4242, FakeStatus(), "Тема")
    cb = FakeCb(data="bs_all")
    await h.cb_save_all(cb)
    assert "Сохранить в Дворец" in cb.message.edits[-1]


async def test_cb_all_expired_session():
    cb = FakeCb(data="bs_all")
    await h.cb_save_all(cb)
    assert "Сессия истекла" in cb.message.edits[-1]


# ─── Связывание идей («Связано с: …») ───

async def test_confirm_shows_linked_block():
    await h.run_storm(4242, FakeStatus(), "Тема")
    h._storm_data[4242]["context"] = {
        "notes": "- Заметка: идея про фотосерию",
        "palace": "",
        "kg": "",
    }
    cb = FakeCb(data="bs_pick:1")
    await h.cb_pick_idea(cb)
    preview = cb.message.edits[-1]
    assert "Связано с" in preview
    assert "Apple Notes" in preview
    assert "фотосерию" in preview


async def test_confirm_no_linked_block_without_overlap():
    await h.run_storm(4242, FakeStatus(), "Тема")
    h._storm_data[4242]["context"] = {
        "notes": "- Совсем другие слова",
        "palace": "тоже без пересечений",
        "kg": "",
    }
    cb = FakeCb(data="bs_pick:1")
    await h.cb_pick_idea(cb)
    assert "Связано с" not in cb.message.edits[-1]


async def test_confirm_no_linked_block_empty_context():
    await h.run_storm(4242, FakeStatus(), "Тема")
    h._storm_data[4242]["context"] = {"notes": "", "palace": "", "kg": ""}
    cb = FakeCb(data="bs_all")
    await h.cb_save_all(cb)
    assert "Связано с" not in cb.message.edits[-1]


async def test_confirm_linked_html_escaped():
    await h.run_storm(4242, FakeStatus(), "Тема")
    h._storm_data[4242]["context"] = {
        "notes": "- идея с тегом <b>сырым</b>",
        "palace": "",
        "kg": "",
    }
    cb = FakeCb(data="bs_pick:1")
    await h.cb_pick_idea(cb)
    preview = cb.message.edits[-1]
    assert "<b>сырым</b>" not in preview
    assert "&lt;b&gt;сырым&lt;/b&gt;" in preview


# ─── Сохранение (мост в save-флоу) ───

async def test_cb_confirm_save_bridges_to_palace(monkeypatch):
    await h.run_storm(4242, FakeStatus(), "Тема")
    cb = FakeCb(data="bs_pick:1")
    await h.cb_pick_idea(cb)

    shown = {}

    async def fake_show_save_wings(edit_func, uid):
        shown[uid] = True

    monkeypatch.setattr("handlers.palace._show_save_wings", fake_show_save_wings)
    import handlers.palace as palace

    cb2 = FakeCb(data="bs_save")
    await h.cb_confirm_save(cb2)
    state = palace._save_state.get(4242)
    assert state and "Идея 1" in state["text"]
    assert shown.get(4242) is True


async def test_cb_confirm_save_expired():
    cb = FakeCb(data="bs_save")
    await h.cb_confirm_save(cb)
    assert "Сессия истекла" in cb.message.edits[-1]


async def test_cb_back_returns_to_ideas():
    await h.run_storm(4242, FakeStatus(), "Тема")
    cb = FakeCb(data="bs_back")
    await h.cb_back_to_ideas(cb)
    assert "Идея 1" in cb.message.edits[-1]


async def test_cb_back_expired():
    cb = FakeCb(data="bs_back")
    await h.cb_back_to_ideas(cb)
    assert "Сессия истекла" in cb.message.edits[-1]


async def test_cb_cancel_clears_state():
    await h.run_storm(4242, FakeStatus(), "Тема")
    h._storm_waiting[4242] = True
    cb = FakeCb(data="bs_cancel")
    await h.cb_cancel(cb)
    assert "Отменено" in cb.message.edits[-1]
    assert 4242 not in h._storm_data
    assert 4242 not in h._storm_waiting


# ─── Границы: количество идей ───

async def test_run_storm_single_idea_no_save_all_button(monkeypatch):
    async def _one_idea(engine, model, msgs):
        return json.dumps({"ideas": [{"title": "Одна"}]}, ensure_ascii=False)

    monkeypatch.setattr(h, "get_ai_response_async", _one_idea)
    status = FakeStatus()
    await h.run_storm(4242, status, "Тема")
    markup = status.last_kw["reply_markup"]
    texts = [b.text for r in markup.inline_keyboard for b in r]
    assert "💡 1" in texts
    assert "💾 Сохранить все" not in texts
