"""Тесты действий с транскриптами."""
import asyncio
import os

import pytest

from tests.test_action_bar import FakeCallback, FakeMessage, _markup_data, TEST_UID

TMP_DIR = os.path.join(os.path.dirname(__file__), "_tmp_transkript")
TMP_FILE = os.path.join(TMP_DIR, "test_tr.txt")
TMP_CONTENT = "Это тестовый транскрипт. Здесь говорится о важной теме и о квантах."


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    import config
    import handlers.transkript as tr

    monkeypatch.setattr(config, "ALLOWED_IDS", {TEST_UID})
    os.makedirs(TMP_DIR, exist_ok=True)
    with open(TMP_FILE, "w", encoding="utf-8") as f:
        f.write(TMP_CONTENT)
    monkeypatch.setattr(tr, "TRANSKRIPT_DIR", TMP_DIR)
    yield
    import shutil

    shutil.rmtree(TMP_DIR, ignore_errors=True)


@pytest.fixture
def _cache(monkeypatch):
    import handlers.transkript as tr

    tr._tr_content_cache[TEST_UID] = {
        "pages": [TMP_CONTENT], "total": 1, "idx": 0, "fname": "test_tr.txt",
        "dt": "01.01.2026 00:00",
    }
    tr._tr_ai_waiting.clear()
    tr._tr_last_question.clear()
    yield tr
    tr._tr_content_cache.pop(TEST_UID, None)


def _markup_labels(msg):
    kb = msg.markups[-1]
    if kb is None:
        return []
    return [b.text for row in kb.inline_keyboard for b in row]


# ─── Кнопки действий ───

def test_content_page_has_action_buttons(_cache):
    import handlers.transkript as tr

    msg = FakeMessage()
    asyncio.run(tr._show_content_page(msg, TEST_UID, 0))
    data = _markup_data(msg)
    assert "tr_ai" in data
    assert "tr_ai_web" in data
    assert "tr_q" in data
    assert "tr_save" in data
    assert "tr_links" in data
    assert "tr_del" in data


# ─── Удаление ───

def test_tr_del_asks_confirmation(_cache):
    msg = FakeMessage()
    cb = FakeCallback("tr_del", msg)
    asyncio.run(_cache.cb_tr_del(cb))
    assert "Удалить транскрипт" in msg.edited[-1]
    data = _markup_data(msg)
    assert "tr_del_yes" in data


def test_tr_del_yes_removes_file(_cache):
    assert os.path.exists(TMP_FILE)
    msg = FakeMessage()
    cb = FakeCallback("tr_del_yes", msg)
    asyncio.run(_cache.cb_tr_del_yes(cb))
    assert not os.path.exists(TMP_FILE)
    assert "удалён" in msg.edited[-1].lower()


def test_tr_del_yes_no_session():
    import handlers.transkript as tr

    msg = FakeMessage()
    cb = FakeCallback("tr_del_yes", msg)
    asyncio.run(tr.cb_tr_del_yes(cb))
    assert "Сессия истекла" in msg.edited[-1]


# ─── Обсудить с ИИ ───

def test_tr_ai_prompts_question(_cache):
    msg = FakeMessage()
    cb = FakeCallback("tr_ai", msg)
    asyncio.run(_cache.cb_tr_ai(cb))
    assert "Задайте вопрос" in msg.edited[-1]
    assert TEST_UID in _cache._tr_ai_waiting


def test_handle_tr_ai_question_calls_ai(_cache, monkeypatch):
    captured = {}

    def fake_ai(engine, model, messages):
        captured["messages"] = messages
        return "Ответ по транскрипту."

    def fake_current_ai():
        return ("gemini", "g")

    monkeypatch.setattr(
        "services.ai_engine._sync_ai_call", fake_ai,
    )
    monkeypatch.setattr(
        "services.ai_engine.get_current_ai", fake_current_ai,
    )

    msg = FakeMessage()
    asyncio.run(_cache.handle_tr_ai_question(TEST_UID, msg, "test_tr.txt", "О чём это?"))
    assert "Ответ по транскрипту" in msg.edited[-1]
    assert "О чём это?" in captured["messages"][-1]["content"]
    assert "Отвечай на русском языке" in captured["messages"][0]["content"]


def test_handle_tr_ai_question_empty_file(monkeypatch):
    import handlers.transkript as tr

    with open(TMP_FILE, "w", encoding="utf-8") as f:
        f.write("   ")
    msg = FakeMessage()
    asyncio.run(tr.handle_tr_ai_question(TEST_UID, msg, "test_tr.txt", "Вопрос"))
    assert "пуст" in msg.edited[-1]


def test_tr_ai_web_without_question_asks_first(_cache):
    msg = FakeMessage()
    cb = FakeCallback("tr_ai_web", msg)
    asyncio.run(_cache.cb_tr_ai_web(cb))
    assert "Сначала задайте вопрос" in msg.edited[-1]


def test_tr_ai_web_with_question_uses_search(monkeypatch, _cache):
    import handlers.transkript as tr

    captured = {}
    monkeypatch.setattr(tr, "_tr_last_question", {TEST_UID: "Про кванты?"})

    async def fake_web(q):
        captured["q"] = q
        return "интернет-результат"

    def fake_ai(engine, model, messages):
        captured["messages"] = messages
        return "Ответ с интернетом."

    def fake_current_ai():
        return ("gemini", "g")

    monkeypatch.setattr("services.ai_engine._sync_ai_call", fake_ai)
    monkeypatch.setattr("services.ai_engine.get_current_ai", fake_current_ai)
    monkeypatch.setattr("services.web_search.search_web", fake_web)

    msg = FakeMessage()
    cb = FakeCallback("tr_ai_web", msg)
    asyncio.run(tr.cb_tr_ai_web(cb))
    assert captured["q"] == "Про кванты?"
    assert "интернет-результат" in captured["messages"][0]["content"]
    assert any("Ответ с интернетом" in e for e in msg.edited)


# ─── Сохранение в MemPalace ───

def test_tr_save_starts_wings_flow(_cache, monkeypatch):
    import handlers.transkript as tr

    shown = {}

    async def fake_wings(edit_func, uid):
        shown["uid"] = uid
        await edit_func("Выберите крыло:")

    class FakeSaveState(dict):
        pass

    monkeypatch.setattr("handlers.palace.save._show_save_wings", fake_wings)

    msg = FakeMessage()
    cb = FakeCallback("tr_save", msg)
    asyncio.run(tr.cb_tr_save(cb))
    assert shown["uid"] == TEST_UID
    assert msg.edited[-1] == "Выберите крыло:"


def test_tr_save_no_content():
    import handlers.transkript as tr

    msg = FakeMessage()
    cb = FakeCallback("tr_save", msg)
    asyncio.run(tr.cb_tr_save(cb))
    assert "Сессия истекла" in msg.edited[-1]


# ─── Цитата ───

def test_tr_q_sets_quote_waiting(_cache):
    import handlers.personal_note as pn

    pn._quote_waiting.clear()
    msg = FakeMessage()
    cb = FakeCallback("tr_q", msg)
    asyncio.run(_cache.cb_tr_q(cb))
    assert TEST_UID in pn._quote_waiting
    assert "Отправьте цитату" in msg.edited[-1]


# ─── Смысловые связи ───

def test_tr_links_shows_sources(_cache, monkeypatch):
    import handlers.transkript as tr

    sources = [
        {"id": 1, "wing": "dreams", "room": "коридор", "score": 0.9},
        {"id": 2, "wing": "projects", "room": "идеи", "score": 0.7},
    ]

    async def fake_search(text, limit=5, wing=""):
        return "Найдено по связям", sources

    monkeypatch.setattr("services.palace_bridge.search_palace_with_sources", fake_search)

    msg = FakeMessage()
    cb = FakeCallback("tr_links", msg)
    asyncio.run(tr.cb_tr_links(cb))
    data = _markup_data(msg, -1)
    assert "p_src:1" in data
    assert "p_src:2" in data
    labels = _markup_labels(msg)
    assert any("Смысловые связи" in lbl or "Читать [1]" in lbl for lbl in labels)


def test_tr_links_no_results(_cache, monkeypatch):
    import handlers.transkript as tr

    async def fake_search(text, limit=5, wing=""):
        return "", []

    monkeypatch.setattr("services.palace_bridge.search_palace_with_sources", fake_search)

    msg = FakeMessage()
    cb = FakeCallback("tr_links", msg)
    asyncio.run(tr.cb_tr_links(cb))
    assert any("Связанных записей" in e for e in msg.edited)
