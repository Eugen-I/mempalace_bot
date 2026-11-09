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
        self.last_reply_markup = None

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append(text)
        status = FakeStatus()
        self.last_status = status
        return status

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

    async def _fake_context(topic, mode="standard", folder=None):
        return {"notes": "n", "palace": "p", "kg": "k"}

    monkeypatch.setattr(bs, "collect_context", _fake_context)
    h._storm_data.clear()
    h._storm_waiting.clear()
    h._reflection_data.clear()
    h._reflection_waiting.clear()


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
        "notes": "- <b>идея</b> с тегом <script>сырым</script>",
        "palace": "",
        "kg": "",
    }
    cb = FakeCb(data="bs_pick:1")
    await h.cb_pick_idea(cb)
    preview = cb.message.edits[-1]
    assert "<b>идея</b>" in preview
    assert "<script>" not in preview
    assert "&lt;script&gt;сырым&lt;/script&gt;" in preview


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


# ─── Рефлексия после штурма ───

async def test_maybe_ask_reflection_asks_question():
    h._reflection_data[4242] = {"theme": "Сны", "ideas_count": 3}
    msg = FakeMessage()
    assert await h.maybe_ask_reflection(4242, msg.answer) is True
    assert "Рефлексия" in msg.answers[0]
    assert "Сны" in msg.answers[0]
    assert "самой сильной" in msg.answers[0]
    assert 4242 in h._reflection_waiting
    assert h._reflection_waiting[4242]["ideas_count"] == 3
    assert 4242 not in h._reflection_data


async def test_maybe_ask_reflection_no_pending():
    h._reflection_data.clear()
    msg = FakeMessage()
    assert await h.maybe_ask_reflection(4242, msg.answer) is False
    assert msg.answers == []
    assert 4242 not in h._reflection_waiting


async def test_cb_reflect_skip_clears_waiting():
    h._reflection_waiting[4242] = {"theme": "Сны", "ideas_count": 1}
    h._reflection_data[4242] = {"theme": "Сны", "ideas_count": 1}
    cb = FakeCb(data="bs_reflect_skip")
    await h.cb_reflect_skip(cb)
    assert 4242 not in h._reflection_waiting
    assert 4242 not in h._reflection_data
    assert "Рефлексия пропущена" in cb.message.edits[-1]


async def test_cb_reflect_skip_without_pending():
    h._reflection_waiting.clear()
    cb = FakeCb(data="bs_reflect_skip")
    await h.cb_reflect_skip(cb)
    assert "Рефлексия пропущена" in cb.message.edits[-1]


async def test_cb_confirm_save_sets_reflection_pending(monkeypatch):
    await h.run_storm(4242, FakeStatus(), "Тема про сны")
    cb = FakeCb(data="bs_pick:1")
    await h.cb_pick_idea(cb)

    async def fake_show_save_wings(edit_func, uid):
        pass

    monkeypatch.setattr("handlers.palace._show_save_wings", fake_show_save_wings)
    cb2 = FakeCb(data="bs_save")
    await h.cb_confirm_save(cb2)
    pending = h._reflection_data.get(4242)
    assert pending is not None
    assert pending["theme"] == "Тема про сны"
    assert pending["ideas_count"] == 5


# ─── Экспорт проекта в Apple Notes ───

async def test_confirm_screen_has_export_notes_button():
    """На экране подтверждения должна присутствовать кнопка экспорта в Apple Notes."""
    await h.run_storm(4242, FakeStatus(), "Тема штурма")
    cb = FakeCb(data="bs_pick:1")
    await h.cb_pick_idea(cb)

    pending = h._storm_data[4242].get("pending")
    assert pending is not None
    assert "ideas" in pending
    # Проверяем, что в разметке последнего редактирования есть кнопка bs_export_notes
    kb = cb.message.last_reply_markup
    assert kb is not None
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "bs_export_notes" in callbacks
    assert "bs_save" in callbacks


async def test_cb_export_notes_happy_path(monkeypatch):
    """Успешный экспорт FusedPhotoConcept в Apple Notes (папка Фотопроекты)."""
    from services.style_fusion import (
        FusedPhotoConcept,
        StyleAssignment,
        StyleTriad,
    )

    triad = StyleTriad(
        narrative=StyleAssignment(role="narrative", style="Сюрреализм"),
        lighting=StyleAssignment(role="lighting", style="Экспрессионизм"),
        optics=StyleAssignment(role="optics", style="Импрессионизм"),
    )
    concept = FusedPhotoConcept(
        title="Тестовый экспортный проект",
        triad=triad,
        camera_setup={"Выдержка": "1/6s"},
        shooting_action="Тремор",
        shooting_steps=["1. Снять", "2. Проверить"],
    )

    h._storm_data[4242] = {
        "pending": {
            "ideas": [concept],
            "text": "Текст проекта",
            "label": "Идея 1",
        }
    }

    exported_calls = []

    def mock_export(c, folder="Фотопроекты"):
        exported_calls.append((c.title, folder))
        return "x-coredata://note-123"

    monkeypatch.setattr("services.style_fusion.export_concept_to_apple_notes", mock_export)

    cb = FakeCb(data="bs_export_notes")
    await h.cb_export_notes(cb)

    assert len(exported_calls) == 1
    assert exported_calls[0] == ("Тестовый экспортный проект", "Фотопроекты")
    assert "Проект сохранён в Apple Notes!" in cb.message.edits[-1]
    assert "Фотопроекты" in cb.message.edits[-1]
    assert "[В планах]" in cb.message.edits[-1]


async def test_cb_export_notes_expired_session():
    """Попытка экспорта при истекшей сессии возвращает сообщение об ошибке."""
    h._storm_data.pop(4242, None)
    cb = FakeCb(data="bs_export_notes")
    await h.cb_export_notes(cb)
    assert "Сессия истекла" in cb.message.edits[-1]


async def test_cb_export_notes_error_handling(monkeypatch):
    """Сбой Apple Notes корректно отлавливается и выводит понятную ошибку."""
    from services.apple_notes import AppleNotesError

    h._storm_data[4242] = {
        "pending": {
            "ideas": [{"title": "Проект с ошибкой"}],
            "text": "Текст",
            "label": "Идея",
        }
    }

    def mock_fail(*args, **kwargs):
        raise AppleNotesError("JXA Timeout")

    monkeypatch.setattr("services.apple_notes.create_note", mock_fail)
    monkeypatch.setattr("services.apple_notes.ensure_folder", lambda f: True)

    cb = FakeCb(data="bs_export_notes")
    await h.cb_export_notes(cb)
    assert any("Ошибка Apple Notes: JXA Timeout" in ans for ans in cb.message.answers)


# ─── Тесты Шага 5: Многостраничная лаборатория и микро-действия ───

def _make_sample_fused_concept(title="Концепт синтеза"):
    from services.style_fusion import (
        FusedPhotoConcept,
        StyleAssignment,
        StyleTriad,
    )
    triad = StyleTriad(
        narrative=StyleAssignment(role="narrative", style="Сюрреализм"),
        lighting=StyleAssignment(role="lighting", style="Экспрессионизм"),
        optics=StyleAssignment(role="optics", style="Импрессионизм"),
        rationale="Синергия сна и света",
    )
    return FusedPhotoConcept(
        title=title,
        triad=triad,
        manifesto="Манифест серии",
        scene_description="Одинокая фигура на причале",
        lighting_setup="Контровой закатный свет",
        camera_setup={"Выдержка": "1/6s", "Диафрагма": "f/4"},
        shooting_action="Поворот призмы на втором кадре",
        gear_recipe={"camera": "Fujifilm X-T4", "lens": "Гелиос 44-2 58mm"},
        shooting_steps=["1. Первый кадр", "2. Второй кадр"],
    )


async def test_cmd_fusion_storm_without_topic():
    msg = FakeMessage(text="/синтез")
    await h.cmd_fusion_storm(msg)
    assert "Творческая лаборатория: Стилистический синтез" in msg.answers[0]
    assert h._storm_waiting.get(4242) == "fusion"


async def test_cmd_fusion_storm_with_topic(monkeypatch):
    called = []

    async def fake_run_storm(uid, status_msg, topic, mode="standard"):
        called.append((uid, topic, mode))

    monkeypatch.setattr(h, "run_storm", fake_run_storm)
    msg = FakeMessage(text="/синтез туманный город")
    await h.cmd_fusion_storm(msg)
    assert len(called) == 1
    assert called[0] == (4242, "туманный город", "fusion")


async def test_cb_start_fusion():
    cb = FakeCb(data="bs_start_fusion")
    await h.cb_start_fusion(cb)
    assert h._storm_waiting.get(4242) == "fusion"
    assert "Творческая лаборатория (Синтез стилей)" in cb.message.edits[-1]


async def test_cb_pick_idea_opens_multipage_lab_for_fusion():
    concept = _make_sample_fused_concept()
    h._storm_data[4242] = {
        "topic": "сон",
        "ideas": [concept],
        "mode": "fusion",
    }
    cb = FakeCb(data="bs_pick:1")
    await h.cb_pick_idea(cb)

    assert "Стр. 1/4" in cb.message.edits[-1]
    assert "Концепт синтеза" in cb.message.edits[-1]
    kb = cb.message.last_reply_markup
    assert kb is not None
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "bs_page:1:2" in callbacks
    assert "bs_deepen:1" in callbacks
    assert "bs_refs:1" in callbacks
    assert "bs_prompt:1" in callbacks
    assert "bs_export_concept:1" in callbacks


async def test_cb_concept_page_navigation():
    concept = _make_sample_fused_concept()
    h._storm_data[4242] = {
        "topic": "сон",
        "ideas": [concept],
        "mode": "fusion",
    }
    # Переход на страницу 2 (Раскадровка)
    cb2 = FakeCb(data="bs_page:1:2")
    await h.cb_concept_page(cb2)
    assert "Стр. 2/4" in cb2.message.edits[-1]
    assert "Одинокая фигура на причале" in cb2.message.edits[-1]

    # Переход на страницу 3 (Сетап)
    cb3 = FakeCb(data="bs_page:1:3")
    await h.cb_concept_page(cb3)
    assert "Стр. 3/4" in cb3.message.edits[-1]
    assert "1/6s" in cb3.message.edits[-1]

    # Переход на страницу 4 (Шутинг-лист)
    cb4 = FakeCb(data="bs_page:1:4")
    await h.cb_concept_page(cb4)
    assert "Стр. 4/4" in cb4.message.edits[-1]
    assert "Чек-лист перед выходом" in cb4.message.edits[-1]


async def test_cb_concept_prompt_action():
    concept = _make_sample_fused_concept()
    h._storm_data[4242] = {
        "ideas": [concept],
    }
    cb = FakeCb(data="bs_prompt:1")
    await h.cb_concept_prompt(cb)
    assert "Промпт Midjourney / Flux.1" in cb.message.edits[-1]
    assert "surrealism aesthetic" in cb.message.edits[-1]
    assert "<code>" in cb.message.edits[-1]


async def test_cb_concept_refs_action(monkeypatch):
    concept = _make_sample_fused_concept()
    h._storm_data[4242] = {
        "ideas": [concept],
    }

    async def mock_search_web(*a, **kw):
        return "Тестовый сниппет веб-поиска"

    monkeypatch.setattr("services.web_search.search_web", mock_search_web)

    cb = FakeCb(data="bs_refs:1")
    await h.cb_concept_refs(cb)
    assert "Художественные референсы" in cb.message.edits[-1]
    assert "Мастера для визуального изучения" in cb.message.edits[-1]


async def test_cb_concept_deepen_action(monkeypatch):
    concept = _make_sample_fused_concept()
    h._storm_data[4242] = {
        "ideas": [concept],
    }

    async def mock_ai_response(*a, **kw):
        return "1. Скрытый символизм: Одиночество и бесконечность.\n2. Пластика: Наклон корпуса."

    monkeypatch.setattr("handlers.brainstorm.get_ai_response_async", mock_ai_response)

    cb = FakeCb(data="bs_deepen:1")
    await h.cb_concept_deepen(cb)
    assert "Режиссёрское углубление" in cb.message.edits[-1]
    assert "Одиночество и бесконечность" in cb.message.edits[-1]


async def test_cb_concept_export_single(monkeypatch):
    concept = _make_sample_fused_concept("Проект экспорта")
    h._storm_data[4242] = {
        "ideas": [concept],
    }

    called = []

    def mock_export(c, folder="Фотопроекты"):
        called.append((c.title, folder))
        return "id-123"

    monkeypatch.setattr("services.style_fusion.export_concept_to_apple_notes", mock_export)

    cb = FakeCb(data="bs_export_concept:1")
    await h.cb_concept_export_single(cb)
    assert len(called) == 1
    assert called[0] == ("Проект экспорта", "Фотопроекты")
    assert any("Проект «Проект экспорта» сохранён" in str(ans) for ans in cb.answers)


async def test_cb_concept_save_palace_initiates_wings(monkeypatch):
    concept = _make_sample_fused_concept("Дворцовый проект")
    h._storm_data[4242] = {
        "ideas": [concept],
    }

    saved = []

    async def fake_show_save_wings(edit_func, uid):
        saved.append(uid)

    monkeypatch.setattr("handlers.palace._show_save_wings", fake_show_save_wings)

    cb = FakeCb(data="bs_save_concept:1")
    await h.cb_concept_save_palace(cb)
    assert len(saved) == 1
    assert saved[0] == 4242


async def test_cb_back_to_ideas_preserves_fusion():
    concept = _make_sample_fused_concept("Проект 1")
    h._storm_data[4242] = {
        "topic": "осенний парк",
        "ideas": [concept],
        "mode": "fusion",
    }
    cb = FakeCb(data="bs_back")
    await h.cb_back_to_ideas(cb)
    assert "Творческая лаборатория (Триада стилей)" in cb.message.edits[-1]
    kb = cb.message.last_reply_markup
    assert kb is not None
    # Кнопка идеи должна быть с палитрой 🎨 1
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "🎨 1" in labels


async def test_run_storm_auto_fallback_on_gemini_429(monkeypatch):
    """При ошибке 429 от Gemini штурм автоматически переключается на Ollama qwen2.5:7b."""
    calls = []

    async def fake_get_ai(engine, model, msgs, sampling=None):
        calls.append((engine, model))
        if engine == "gemini":
            return "❌ Ошибка ИИ (gemini): 429 Quota exceeded for metric: generate_content_free_tier_requests"
        return (
            '{"projects": [{\n'
            '  "title": "Локальный проект от Qwen",\n'
            '  "triad": {\n'
            '    "narrative": {"role": "narrative", "style": "Сюрреализм", "traits": "Сон"},\n'
            '    "lighting": {"role": "lighting", "style": "Экспрессионизм", "traits": "Тени"},\n'
            '    "optics": {"role": "optics", "style": "Импрессионизм", "traits": "Свет"},\n'
            '    "rationale": "Синергия"\n'
            '  },\n'
            '  "manifesto": "Манифест",\n'
            '  "scene_description": "Локация",\n'
            '  "lighting_setup": "Свет",\n'
            '  "camera_setup": {"Выдержка": "1/6 с", "Диафрагма": "f/8.0"},\n'
            '  "shooting_action": "Микро-ICM",\n'
            '  "gear_recipe": {"camera": "Fujifilm X-T4"},\n'
            '  "shooting_steps": ["1. Шаг 1", "2. Шаг 2"]\n'
            '}]}'
        )

    monkeypatch.setattr(h, "get_current_ai", lambda: ("gemini", "gemini-2.5-flash"))
    monkeypatch.setattr(h, "get_ai_response_async", fake_get_ai)

    status = FakeStatus()
    await h.run_storm(4242, status, "туман", mode="fusion")

    assert len(calls) == 2
    assert calls[0] == ("gemini", "gemini-2.5-flash")
    assert calls[1] == ("qwen", "qwen2.5:7b")

    assert any("Переключаюсь на локальный Qwen" in edit for edit in status.edits)
    assert 4242 in h._storm_data
    assert h._storm_data[4242]["ideas"][0].title == "Локальный проект от Qwen"
