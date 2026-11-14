"""tests/test_copilot_palace_bridge.py — Тесты моста копайлота и Дворца Памяти (Шаг B1, MP-1).

Проверяет:
- Поиск семантических резонансов в Apple Notes и личной памяти.
- Graceful degradation при отсутствии заметок или сбоях векторной базы.
- Форматирование контекста для системного промпта арт-директора.
- Форматирование визуальной карточки для Telegram UI (HTML safety: blockquote, b, i, no <!-- -->).
- Кэширование резонансов внутри сессии копайлота.
- Интеграцию кнопки в клавиатуру Сократического диалога и callbacks.
"""

from unittest.mock import MagicMock
import pytest

from handlers import copilot as hc
from services import copilot_engine as engine
import services.copilot_palace_bridge as bridge
from services.copilot_session import CopilotSession, CopilotSessionManager


class FakeUser:
    def __init__(self, uid=7777):
        self.id = uid


class FakeMessage:
    def __init__(self, uid=7777):
        self.from_user = FakeUser(uid)
        self.edits = []
        self.answers = []
        self.last_reply_markup = None

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)
        self.last_reply_markup = reply_markup

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append(text)
        self.last_reply_markup = reply_markup


class FakeCb:
    def __init__(self, uid=7777, data=""):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = FakeMessage(uid)
        self.answered = []

    async def answer(self, text=None, show_alert=False):
        self.answered.append((text, show_alert))


@pytest.fixture
def temp_manager(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "ALLOWED_IDS", {7777})
    mgr = CopilotSessionManager(file_path=tmp_path / "palace_bridge_sessions.json")
    monkeypatch.setattr(hc, "get_copilot_manager", lambda: mgr)
    monkeypatch.setattr(engine, "get_copilot_manager", lambda: mgr)
    return mgr


def test_find_palace_resonances_empty_topic():
    """Пустая тема возвращает пустой список без обращения к базам."""
    assert bridge.find_palace_resonances("") == []
    assert bridge.find_palace_resonances("   ") == []


def test_find_palace_resonances_hybrid_notes(monkeypatch):
    """Поиск резонансов в Apple Notes через notes_embeddings."""
    mock_notes = [
        {
            "id": "note1",
            "name": "Сон о мокром асфальте",
            "snippet": "Отражения фонарей в лужах...",
            "_score": 0.88,
        },
        {
            "id": "note2",
            "name": "Одиночество мегаполиса",
            "snippet": "Пустые витрины в 3 часа ночи...",
            "_score": 0.75,
        },
    ]
    monkeypatch.setattr(
        "services.notes_embeddings.search_notes_hybrid",
        lambda query, limit: mock_notes,
    )

    resonances = bridge.find_palace_resonances("Ночной город", limit=2)
    assert len(resonances) == 2
    assert resonances[0]["title"] == "Сон о мокром асфальте"
    assert resonances[0]["source"] == "Apple Notes"
    assert resonances[0]["score"] == 0.88
    assert "Отражения фонарей" in resonances[0]["snippet"]


def test_find_palace_resonances_memory_fallback(monkeypatch):
    """Дополнение резонансов из личной памяти пользователя (memory_embeddings)."""
    # 1 заметка из Apple Notes
    monkeypatch.setattr(
        "services.notes_embeddings.search_notes_hybrid",
        lambda query, limit: [
            {"id": "n1", "name": "Заметка", "snippet": "Тестовый сниппет 1", "_score": 0.9}
        ],
    )
    # 1 факт из личной памяти
    monkeypatch.setattr(
        "services.memory_embeddings.search_similar",
        lambda query, user_id, limit: [
            {
                "id": "m1",
                "title": "Мысль о свете",
                "snippet": "Контровой свет в сумерках",
                "_score": 0.82,
            }
        ],
    )

    resonances = bridge.find_palace_resonances("Сумерки", user_id=7777, limit=2)
    assert len(resonances) == 2
    sources = [r["source"] for r in resonances]
    assert "Apple Notes" in sources
    assert "Личная память" in sources


def test_find_palace_resonances_graceful_degradation(monkeypatch):
    """Сбой в сервисах эмбеддингов не приводит к ошибке (возвращается пустой список)."""
    def mock_fail(*args, **kwargs):
        raise RuntimeError("Ollama connection failed")

    monkeypatch.setattr("services.notes_embeddings.search_notes_hybrid", mock_fail)
    monkeypatch.setattr("services.memory_embeddings.search_similar", mock_fail)

    resonances = bridge.find_palace_resonances("Туманный пейзаж", user_id=7777)
    assert resonances == []


def test_format_palace_resonances_context():
    """Форматирование контекста для системного промпта Сократического диалога."""
    resonances = [
        {"title": "Сон о стеклянном лабиринте", "snippet": "Стены двоятся, преломляя свет."},
    ]
    ctx = bridge.format_palace_resonances_context(resonances)
    assert "АССОЦИАТИВНЫЕ РЕЗОНАНСЫ ИЗ ДВОРЦА ПАМЯТИ" in ctx
    assert "Сон о стеклянном лабиринте" in ctx
    assert "Стены двоятся" in ctx
    assert "ИНСТРУКЦИЯ КУРАТОРА" in ctx

    # Пустой список отдаёт пустую строку
    assert bridge.format_palace_resonances_context([]) == ""


def test_format_palace_resonances_card_html_safety():
    """Форматирование карточки резонансов для Telegram с безопасными тегами."""
    resonances = [
        {
            "title": "Ночная аллея & туман",
            "snippet": "Желтый натриевый свет режет листву <script>",
            "source": "Apple Notes",
            "score": 0.85,
        }
    ]
    card = bridge.format_palace_resonances_card(resonances, topic="Осенняя элегия")

    assert "🏛 <b>Дворец Памяти • Ассоциативные мосты</b>" in card
    assert "Осенняя элегия" in card
    assert "<blockquote>" in card and "</blockquote>" in card
    assert "Ночная аллея &amp; туман" in card
    assert "<script>" not in card  # Экранировано
    assert "<!--" not in card
    assert "<div>" not in card
    assert "<p>" not in card


def test_format_palace_resonances_card_empty():
    """Карточка при отсутствии найденных резонансов."""
    card = bridge.format_palace_resonances_card([], topic="Неизведанная тема")
    assert "В чертогах Дворца пока не найдено прямых записей" in card
    assert "Неизведанная тема" in card


def test_get_or_find_session_resonances_caching(temp_manager, monkeypatch):
    """Кэширование найденных резонансов в сессии копайлота."""
    session = temp_manager.create_or_replace_session(7777, "Лабиринт зеркал")

    mock_search = MagicMock(return_value=[
        {
            "id": "n1",
            "title": "Зеркало",
            "snippet": "Отражения бесконечны",
            "source": "Apple Notes",
            "score": 0.9,
        }
    ])
    monkeypatch.setattr(bridge, "find_palace_resonances", mock_search)

    # 1. Первый вызов — выполняется поиск
    res1 = bridge.get_or_find_session_resonances(session)
    assert len(res1) == 1
    assert mock_search.call_count == 1
    assert session.tech_preferences["palace_resonances"] == res1

    # 2. Второй вызов — берётся из кэша tech_preferences
    res2 = bridge.get_or_find_session_resonances(session)
    assert res2 == res1
    assert mock_search.call_count == 1  # Повторного вызова не было


def test_build_socratic_messages_with_resonances():
    """build_socratic_messages встраивает резонансы в системный промпт."""
    resonances = [{"title": "Цитата о тишине", "snippet": "Тишина перед грозой"}]
    msgs = engine.build_socratic_messages(
        "Предчувствие бури",
        [{"role": "user", "content": "Хочу мрачный кадр"}],
        palace_resonances=resonances,
    )
    system_msg = msgs[0]["content"]
    assert "Цитата о тишине" in system_msg
    assert "Тишина перед грозой" in system_msg
    assert "АССОЦИАТИВНЫЕ РЕЗОНАНСЫ ИЗ ДВОРЦА ПАМЯТИ" in system_msg


def test_build_copilot_dialogue_kb_resonances_button():
    """Кнопка резонансов появляется в клавиатуре диалога только при их наличии."""
    session_no_res = CopilotSession(user_id=7777, topic="Тест 1")
    kb_no_res = hc.build_copilot_dialogue_kb(session_no_res)
    callbacks_no_res = [btn.callback_data for row in kb_no_res.inline_keyboard for btn in row]
    assert "cp_palace_resonances" not in callbacks_no_res

    session_with_res = CopilotSession(user_id=7777, topic="Тест 2")
    session_with_res.tech_preferences["palace_resonances"] = [
        {"title": "Мысль", "snippet": "Фрагмент"}
    ]
    kb_with_res = hc.build_copilot_dialogue_kb(session_with_res)
    callbacks_with_res = [btn.callback_data for row in kb_with_res.inline_keyboard for btn in row]
    assert "cp_palace_resonances" in callbacks_with_res


@pytest.mark.asyncio
async def test_cb_copilot_palace_resonances_and_back(temp_manager):
    """Нажатие на кнопку резонансов открывает карточку, а кнопка возврата возвращает диалог."""
    session = temp_manager.create_or_replace_session(7777, "Тени прошлого")
    session.add_assistant_message("Что заставило тебя выбрать этот образ?")
    session.tech_preferences["palace_resonances"] = [
        {
            "title": "Архивная заметка",
            "snippet": "Старые фотографии в пыли",
            "source": "Apple Notes",
            "score": 0.88,
        }
    ]
    temp_manager.save_session(session)

    # 1. Открытие экрана резонансов
    cb_res = FakeCb(7777, data="cp_palace_resonances")
    await hc.cb_copilot_palace_resonances(cb_res)

    assert len(cb_res.message.edits) == 1
    card_text = cb_res.message.edits[0]
    assert "Дворец Памяти • Ассоциативные мосты" in card_text
    assert "Архивная заметка" in card_text
    assert "Старые фотографии в пыли" in card_text
    kb_res = cb_res.message.last_reply_markup.inline_keyboard
    res_cbs = [btn.callback_data for row in kb_res for btn in row]
    assert "cp_back_to_dialogue" in res_cbs

    # 2. Возврат к диалогу
    cb_back = FakeCb(7777, data="cp_back_to_dialogue")
    await hc.cb_copilot_back_to_dialogue(cb_back)

    assert len(cb_back.message.edits) == 1
    dialogue_text = cb_back.message.edits[0]
    assert "Что заставило тебя выбрать этот образ?" in dialogue_text
    kb_back = cb_back.message.last_reply_markup.inline_keyboard
    back_cbs = [btn.callback_data for row in kb_back for btn in row]
    assert "cp_palace_resonances" in back_cbs
    assert "cp_pause" in back_cbs
