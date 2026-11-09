"""features/steps/copilot_series_steps.py — Реализация BDD-шагов для кураторской фотосерии.

Покрывает:
- Построение триптиха (3 кадра) и пентаптиха (5 кадров);
- Кураторскую экспликацию и промпты Midjourney;
- Драматургический ритм и чередование планов;
- Обработку сбоев Apple Notes и граничных индексов;
- Интерактивные callback-вызовы в Telegram.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch

from behave import given, then, when

from handlers.copilot import (
    cb_copilot_series_export_notes,
    cb_copilot_series_format,
    cb_copilot_series_shot,
    cb_copilot_view_series,
)
from services.copilot_series import (
    build_series_storyboard,
    export_series_to_apple_notes,
)
from services.copilot_session import CopilotSessionManager


class MockMessage:
    def __init__(self):
        self.texts = []
        self.kbs = []

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.texts.append(text)
        self.kbs.append(reply_markup)

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.texts.append(text)
        self.kbs.append(reply_markup)


class MockCallbackQuery:
    def __init__(self, data: str, user_id: int = 12345):
        self.data = data
        self.from_user = MagicMock()
        self.from_user.id = user_id
        self.message = MockMessage()
        self.answered = []

    async def answer(self, text=None, show_alert=False):
        self.answered.append((text, show_alert))


@given('утвержденный фотопроект копайлота с темой "{topic}"')
def step_given_approved_project(context, topic):
    tmp_path = Path(tempfile.mkdtemp()) / "test_bdd_series.json"
    context.manager = CopilotSessionManager(file_path=tmp_path, ttl=3600)
    context.session = context.manager.create_or_replace_session(user_id=888999, topic=topic)
    context.session.stage = "completed"
    context.session.selected_styles = ["Экспрессионизм", "Сюрреализм"]
    context.session.manifesto = "Манифест: исследование ночного города через оптические аберрации."
    context.session.tech_preferences = {
        "support": "Съемка с рук (микро-ICM)",
        "lens": "Гелиос 44-2 58mm f/2",
        "filter_accessory": "Black Pro-Mist 1/4",
        "lighting": "Контровой натриевый свет",
    }
    context.session.candidate_projects = [
        {
            "id": 1,
            "title": topic,
            "visual_hook": "Одинокая фигура у мокрой арки.",
            "lighting_scene": "Один узкий контровой фонарь.",
        }
    ]
    context.session.selected_project_idx = 0
    context.manager.save_session(context.session)


@when("куратор запрашивает построение фотосерии в формате триптиха")
def step_when_build_triptych(context):
    context.series = build_series_storyboard(context.session, series_format="triptych")
    context.session.series_data = context.series.to_dict()


@then("формируется серия из ровно 3 кадров с кураторской экспликацией")
def step_then_triptych_structure(context):
    assert context.series.series_format == "triptych"
    assert len(context.series.shots) == 3
    assert len(context.series.curatorial_statement) > 40
    assert "Гелиос 44-2" in context.series.curatorial_statement


@then("каждый кадр содержит крупность плана, световую схему и промпт Midjourney v6.1")
def step_then_shot_details(context):
    for shot in context.series.shots:
        assert shot.shot_type != ""
        assert shot.lighting_setup != ""
        assert "--ar 16:9" in shot.midjourney_prompt
        assert "--style raw" in shot.midjourney_prompt


@then('серия успешно экспортируется в Apple Notes с префиксом "[Серия к съемке]"')
def step_then_export_apple_notes(context):
    with patch("services.apple_notes.ensure_folder"), \
         patch("services.apple_notes.create_note", return_value="note-id-123") as mock_create:
        ok, note_id = export_series_to_apple_notes(context.series, folder="Фотопроекты")
        assert ok is True
        assert note_id == "note-id-123"
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["title"].startswith("[Серия к съемке]")


@given("пустая сессия копайлота без утвержденных проектов")
def step_given_empty_session(context):
    tmp_path = Path(tempfile.mkdtemp()) / "test_bdd_empty_series.json"
    context.manager = CopilotSessionManager(file_path=tmp_path, ttl=3600)
    context.empty_uid = 999111


@when('поступает callback вызова серии "{cb_data}"')
def step_when_cb_view_series_empty(context, cb_data):
    cb = MockCallbackQuery(data=cb_data, user_id=context.empty_uid)
    with patch("handlers.copilot.get_copilot_manager", return_value=context.manager):
        asyncio.run(cb_copilot_view_series(cb))
    context.cb = cb


@then('бот отвечает предупреждением "Сессия не найдена" без исключений')
def step_then_session_not_found(context):
    assert len(context.cb.answered) > 0
    ans_text, _ = context.cb.answered[0]
    assert ans_text == "Сессия не найдена"


@given('сформированная кураторская фотосерия проекта "{topic}"')
def step_given_formed_series(context, topic):
    step_given_approved_project(context, topic)
    context.series = build_series_storyboard(context.session, series_format="triptych")
    context.session.series_data = context.series.to_dict()
    context.manager.save_session(context.session)


@when("внешний вызов Apple Notes завершается тайм-аутом")
def step_when_apple_notes_timeout(context):
    cb = MockCallbackQuery(data="cp_series_export_notes", user_id=context.session.user_id)
    with patch("handlers.copilot.get_copilot_manager", return_value=context.manager), \
         patch("services.apple_notes.create_note", side_effect=OSError("AppleScript timeout")):
        asyncio.run(cb_copilot_series_export_notes(cb))
    context.cb = cb


@then("пользователь получает всплывающее предупреждение об ошибке без падения бота")
def step_then_apple_notes_alert_error(context):
    assert len(context.cb.answered) > 0
    alert_text, is_alert = context.cb.answered[0]
    assert is_alert is True
    assert "Ошибка экспорта" in alert_text


@when("запрашивается отображение кадра с недопустимым индексом {idx:d}")
def step_when_invalid_index_shot(context, idx):
    cb = MockCallbackQuery(data=f"cp_series_shot:{idx}", user_id=context.session.user_id)
    with patch("handlers.copilot.get_copilot_manager", return_value=context.manager):
        asyncio.run(cb_copilot_series_shot(cb))
    context.cb = cb


@then("система безопасно открывает начальный кадр 1 без исключений")
def step_then_safe_initial_frame(context):
    assert len(context.cb.message.texts) > 0
    text = context.cb.message.texts[0]
    assert "Кадр 1 из" in text


@when('куратор переключает формат серии на "{fmt}"')
def step_when_switch_series_format(context, fmt):
    cb = MockCallbackQuery(data=f"cp_series_format:{fmt}", user_id=context.session.user_id)
    with patch("handlers.copilot.get_copilot_manager", return_value=context.manager):
        asyncio.run(cb_copilot_series_format(cb))
    context.cb = cb


@then("серия мгновенно перестраивается ровно на 5 кадров с актами от I до V")
def step_then_rebuilt_penta(context):
    assert len(context.cb.message.texts) > 0
    text = context.cb.message.texts[0]
    assert "Пентаптих (5 кадров)" in text
    assert "Кадр 5" in text


@then("обновленные данные серии фиксируются в сессии копайлота")
def step_then_saved_in_session(context):
    saved_session = context.manager.get_session(context.session.user_id)
    assert saved_session is not None
    assert saved_session.series_data is not None
    assert saved_session.series_data["series_format"] == "penta"
    assert len(saved_session.series_data["shots"]) == 5


@given("построенная фотосерия в формате пентаптиха")
def step_given_penta_series(context):
    step_given_approved_project(context, "Ритм города")
    context.series = build_series_storyboard(context.session, series_format="penta")


@when("анализируется последовательность планов всех 5 кадров")
def step_when_analyze_plans(context):
    context.shot_types = [s.shot_type for s in context.series.shots]


@then("ни один соседний кадр не имеет повторяющейся крупности плана")
def step_then_no_consecutive_same_plans(context):
    assert len(context.shot_types) == 5
    for i in range(len(context.shot_types) - 1):
        assert context.shot_types[i] != context.shot_types[i + 1], (
            f"Кадры {i+1} и {i+2} имеют одинаковый план: {context.shot_types[i]}"
        )
