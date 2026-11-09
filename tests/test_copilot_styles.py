"""Unit-тесты для Шага 8: Стилистический конструктор арт-копайлота.

Проверяет:
- Карточку выбора стилей и отображение чекбоксов
- Добавление стилей в концептуальное резюме (append_styles_to_summary)
- Случайную синергию стилей (get_random_style_synergy)
- Интерактивные Telegram-хендлеры:
  - выбор и снятие стилей (toggle)
  - лимит до 3 стилей (отклонение 4-го с алертом)
  - применение готовых пресетов (драма, живопись, триада)
  - очистка выбора (clear)
  - подтверждение выбора (confirm) и переход к манифесту
"""

import pytest

from handlers import copilot as h
import services.copilot_engine as engine
from services.copilot_session import CopilotSession, CopilotSessionManager


class FakeUser:
    def __init__(self, uid=4242):
        self.id = uid


class FakeMessage:
    def __init__(self, uid=4242, text=""):
        self.from_user = FakeUser(uid)
        self.chat = type("C", (), {"id": 1})()
        self.text = text
        self.edits = []
        self.last_reply_markup = None

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)
        self.last_reply_markup = reply_markup


class FakeCb:
    def __init__(self, uid=4242, data=""):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = FakeMessage(uid)
        self.answers = []

    async def answer(self, text=None, show_alert=None):
        self.answers.append((text, show_alert))


@pytest.fixture(autouse=True)
def clean_copilot_manager(tmp_path, monkeypatch):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", [4242], raising=False)
    monkeypatch.setattr(config, "ADMIN_ID", 4242, raising=False)

    fpath = tmp_path / "copilot_sessions.json"
    mgr = CopilotSessionManager(file_path=fpath)
    monkeypatch.setattr(h, "get_copilot_manager", lambda: mgr)
    monkeypatch.setattr(engine, "get_copilot_manager", lambda: mgr)


# ─── 1. services.copilot_engine тесты для стилей ───

def test_format_styles_selection_card():
    sess = CopilotSession(
        user_id=4242,
        topic="Архитипы Юнга",
        summary="🎯 Концептуальный конфликт: Встреча с Тенью",
        selected_styles=["Сюрреализм"],
    )
    card = engine.format_styles_selection_card(sess)
    assert "Стилистический конструктор арт-копайлота" in card
    assert "Встреча с Тенью" in card
    assert "✅ <b>👁 Сюрреализм</b>" in card
    assert "▫️ <b>🌫 Пиктореализм</b>" in card
    assert "Выбрано: <b>1/3</b>" in card


def test_append_styles_to_summary():
    sess = CopilotSession(
        user_id=4242,
        topic="Архитипы Юнга",
        summary="🎯 Концептуальный конфликт: Встреча с Тенью",
        selected_styles=["Сюрреализм", "Пиктореализм"],
    )
    updated = engine.append_styles_to_summary(sess)
    assert "Выбранные стили синтеза:" in updated
    assert "👁 Сюрреализм" in updated
    assert "🌫 Пиктореализм" in updated

    # Повторный вызов не дублирует блок
    updated2 = engine.append_styles_to_summary(sess)
    assert updated2.count("Выбранные стили синтеза:") == 1


def test_get_random_style_synergy():
    styles = engine.get_random_style_synergy(count=3)
    assert len(styles) == 3
    assert len(set(styles)) == 3
    for s in styles:
        assert s in engine.COPILOT_STYLES


# ─── 2. Telegram UI Callback тесты ───

@pytest.mark.asyncio
async def test_cb_copilot_toggle_style_add_and_remove():
    mgr = h.get_copilot_manager()
    sess = mgr.create_or_replace_session(4242, "Тема")

    # 1. Добавление стиля
    cb_add = FakeCb(data="cp_toggle_style:Сюрреализм")
    await h.cb_copilot_toggle_style(cb_add)
    assert "Сюрреализм" in sess.selected_styles
    assert any("Добавлен: Сюрреализм" in (ans[0] or "") for ans in cb_add.answers)

    # 2. Повторное нажатие — снятие стиля
    cb_remove = FakeCb(data="cp_toggle_style:Сюрреализм")
    await h.cb_copilot_toggle_style(cb_remove)
    assert "Сюрреализм" not in sess.selected_styles
    assert any("Снят стиль: Сюрреализм" in (ans[0] or "") for ans in cb_remove.answers)


@pytest.mark.asyncio
async def test_cb_copilot_toggle_style_limit_three():
    mgr = h.get_copilot_manager()
    sess = mgr.create_or_replace_session(4242, "Тема")
    sess.selected_styles = ["Сюрреализм", "Пиктореализм", "Экспрессионизм"]

    # Попытка добавить 4-й стиль
    cb_fourth = FakeCb(data="cp_toggle_style:Импрессионизм")
    await h.cb_copilot_toggle_style(cb_fourth)

    assert "Импрессионизм" not in sess.selected_styles
    assert len(sess.selected_styles) == 3
    # Должен быть алерт
    assert any("максимум 3 стиля" in (ans[0] or "") and ans[1] is True for ans in cb_fourth.answers)


@pytest.mark.asyncio
async def test_cb_copilot_presets():
    mgr = h.get_copilot_manager()
    sess = mgr.create_or_replace_session(4242, "Тема")

    # Пресет: драма
    cb_drama = FakeCb(data="cp_preset:preset_drama")
    await h.cb_copilot_preset(cb_drama)
    assert sess.selected_styles == ["Сюрреализм", "Экспрессионизм"]

    # Пресет: случайная синергия
    cb_rnd = FakeCb(data="cp_preset:random")
    await h.cb_copilot_preset(cb_rnd)
    assert len(sess.selected_styles) == 3


@pytest.mark.asyncio
async def test_cb_copilot_clear_styles():
    mgr = h.get_copilot_manager()
    sess = mgr.create_or_replace_session(4242, "Тема")
    sess.selected_styles = ["Сюрреализм", "Экспрессионизм"]

    cb_clear = FakeCb(data="cp_clear_styles")
    await h.cb_copilot_clear_styles(cb_clear)
    assert len(sess.selected_styles) == 0


@pytest.mark.asyncio
async def test_cb_copilot_confirm_styles_validation_and_proceed():
    mgr = h.get_copilot_manager()
    sess = mgr.create_or_replace_session(4242, "Тема")
    sess.summary = "🎯 Концептуальный конфликт: Конфликт"

    # 1. Попытка подтвердить при 0 стилей -> ошибка
    cb_empty = FakeCb(data="cp_confirm_styles")
    await h.cb_copilot_confirm_styles(cb_empty)
    assert any("Выберите хотя бы 1 стиль" in (ans[0] or "") and ans[1] is True for ans in cb_empty.answers)
    assert sess.stage != "manifesto"

    # 2. Подтверждение с 2 стилями -> успех и переход к manifesto
    sess.selected_styles = ["Сюрреализм", "Пиктореализм"]
    cb_valid = FakeCb(data="cp_confirm_styles")
    await h.cb_copilot_confirm_styles(cb_valid)

    assert sess.stage == "manifesto"
    assert "Выбранные стили синтеза:" in sess.summary
    assert any("Стилистический синтез утвержден" in e for e in cb_valid.message.edits)
