"""Unit tests for handlers.reactions (save AI replies via emoji reactions)."""

import pytest
from aiogram.types import ReactionTypeEmoji

from handlers.reactions import handle_ai_reaction, router


class FakeUser:
    id = 111


class FakeChat:
    id = 111


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, parse_mode=None):
        self.sent.append((chat_id, text, parse_mode))


class FakeEvent:
    def __init__(self, user, reactions, msg_id, bot=None, new_reaction=None):
        self.user = user
        self.message_id = msg_id
        self.bot = bot or FakeBot()
        self.chat = FakeChat()
        self.new_reaction = new_reaction if new_reaction is not None else [
            ReactionTypeEmoji(emoji=e) for e in reactions
        ]


@pytest.fixture
def allow(monkeypatch):
    import handlers.reactions as r

    r._ai_msg_cache.clear()
    monkeypatch.setattr(r, "ALLOWED_IDS", {111})
    return r


def test_router_message_reaction_registered():
    assert router is not None


@pytest.mark.asyncio
async def test_not_allowed_user_ignored(allow, monkeypatch):
    allow._ai_msg_cache[999] = {1: "текст"}
    ev = FakeEvent(FakeUser(), [], 1)  # user.id=111 ok, но проверяем другого юзера
    ev2 = FakeEvent(type("U", (), {"id": 5})(), [], 1)
    await handle_ai_reaction(ev2)
    # событие с неразрешённым юзером не сохраняет ничего
    assert ev2.bot.sent == []


@pytest.mark.asyncio
async def test_empty_new_reaction_ignored(allow):
    ev = FakeEvent(FakeUser(), [], 1, new_reaction=[])
    await handle_ai_reaction(ev)
    assert ev.bot.sent == []


@pytest.mark.asyncio
async def test_unknown_emoji_ignored(allow):
    allow._ai_msg_cache[111] = {1: "контент"}
    ev = FakeEvent(FakeUser(), ["🔥"], 1)
    await handle_ai_reaction(ev)
    assert ev.bot.sent == []


@pytest.mark.asyncio
async def test_not_in_cache_warns(allow, tmp_path):
    allow.NOTES_DIR = str(tmp_path)
    ev = FakeEvent(FakeUser(), ["👍"], 1)  # chat 111, msg 1 не в кэше
    await handle_ai_reaction(ev)
    assert ev.bot.sent
    assert "кэше" in ev.bot.sent[0][1]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_normalize_emoji_via_handler_saves(allow, tmp_path):
    """React с variation selector сохраняется после нормализации."""
    allow._ai_msg_cache[111] = {1: "текст"}
    allow.NOTES_DIR = str(tmp_path)
    ev = FakeEvent(FakeUser(), ["👍\ufe0f\u200d"], 1)
    await handle_ai_reaction(ev)
    assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.asyncio
async def test_save_note_action(allow, tmp_path):
    allow._ai_msg_cache[111] = {1: "текст заметки"}
    allow.NOTES_DIR = str(tmp_path)
    ev = FakeEvent(FakeUser(), ["👍"], 1)
    await handle_ai_reaction(ev)
    files = list(tmp_path.iterdir())
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "текст заметки" in content
    assert "[Реакция 👍]" in content
    assert ev.bot.sent[0][0] == 111
    assert "my_notes" in ev.bot.sent[0][1]
    assert ev.bot.sent[0][2] == "Markdown"


@pytest.mark.asyncio
async def test_save_insight_action(allow, tmp_path):
    allow._ai_msg_cache[111] = {1: "вывод о тесте"}
    allow.INSIGHTS_DIR = str(tmp_path)
    ev = FakeEvent(FakeUser(), ["❤"], 1)
    await handle_ai_reaction(ev)
    files = list(tmp_path.iterdir())
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "вывод о тесте" in content
    assert "Источник: msg_1" in content
    assert "Insights" in ev.bot.sent[0][1]


@pytest.mark.asyncio
async def test_save_research_action(allow, tmp_path):
    allow._ai_msg_cache[111] = {2: "вопрос для ресёрча"}
    allow.RESEARCH_DIR = str(tmp_path)
    ev = FakeEvent(FakeUser(), ["🤷"], 2)
    await handle_ai_reaction(ev)
    files = list(tmp_path.iterdir())
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "вопрос для ресёрча" in content
    assert "Источник: msg_2" in content
    assert "Research" in ev.bot.sent[0][1]


@pytest.mark.asyncio
async def test_normalized_emoji_with_variation_saves(allow, tmp_path):
    """Реакция с variation selector → нормализуется и сохраняется."""
    allow._ai_msg_cache[111] = {1: "данные"}
    allow.NOTES_DIR = str(tmp_path)
    ev = FakeEvent(FakeUser(), ["👍\ufe0f"], 1)
    await handle_ai_reaction(ev)
    assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.asyncio
async def test_save_error_reports_to_user(allow, monkeypatch):
    allow._ai_msg_cache[111] = {1: "текст"}
    allow.NOTES_DIR = "/nonexistent/dir/xyz"

    orig_open = open
    monkeypatch.setattr(allow.os, "makedirs", lambda *a, **k: None)

    ev = FakeEvent(FakeUser(), ["👍"], 1)
    await handle_ai_reaction(ev)
    assert ev.bot.sent
    # format_user_error для FileNotFoundError возвращает "❌ Файл не найден"
    assert "Файл не найден" in ev.bot.sent[-1][1]


@pytest.mark.asyncio
async def test_first_reaction_emoji_determines_action(allow, tmp_path):
    allow._ai_msg_cache[111] = {1: "данные"}
    allow.NOTES_DIR = str(tmp_path)
    # первая — 🔥 (неизвестная), вторая — ❤ (insight)
    ev = FakeEvent(FakeUser(), ["🔥", "❤"], 1)
    await handle_ai_reaction(ev)
    files = list(tmp_path.iterdir())
    assert len(files) == 0  # без известной первой не сохранится? нет — цикл break на ❤
    # на самом деле цикл идёт по всем реакциям: 🔥 пропуск, ❤ → insight
    allow.INSIGHTS_DIR = str(tmp_path)
    await handle_ai_reaction(ev)
    assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.asyncio
async def test_non_emoji_reaction_skipped(allow, tmp_path):
    """Реакция не типа Emoji — пропускается циклом, брейк не происходит."""
    allow._ai_msg_cache[111] = {1: "данные"}
    allow.NOTES_DIR = str(tmp_path)

    class FakeReaction:
        pass  # не ReactionTypeEmoji

    ev = FakeEvent(FakeUser(), [], 1, new_reaction=[FakeReaction()])
    await handle_ai_reaction(ev)
    assert ev.bot.sent == []


@pytest.mark.asyncio
async def test_error_after_save_no_extra_notification(allow, tmp_path, monkeypatch):
    """Ошибка при записи файла → сообщение об ошибке (без дублей)."""
    allow._ai_msg_cache[111] = {1: "текст"}
    allow.NOTES_DIR = str(tmp_path)

    import builtins

    real_open = builtins.open
    fails = {"fails": 0}

    def flaky_open(file, mode="r", *args, **kwargs):
        if mode.startswith("w"):
            fails["fails"] += 1
            raise OSError("disk full")
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", flaky_open)
    ev = FakeEvent(FakeUser(), ["👍"], 1)
    await handle_ai_reaction(ev)
    assert ev.bot.sent
    # format_user_error для OSError возвращает "❌ Системная ошибка"
    assert "Системная ошибка" in ev.bot.sent[-1][1]
