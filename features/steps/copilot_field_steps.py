"""Шаги BDD для features/copilot_field.feature."""

import asyncio
from pathlib import Path
import tempfile
from unittest.mock import patch

from behave import given, then, when

from handlers import copilot as hc
import services.copilot_engine as engine
from services.copilot_session import CopilotSessionManager


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class FakeUser:
    def __init__(self, uid=424242):
        self.id = uid


class FakeMessage:
    def __init__(self, uid=424242, text=""):
        self.from_user = FakeUser(uid)
        self.chat = type("C", (), {"id": 1})()
        self.text = text
        self.answers = []
        self.edits = []

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append(text)

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)


class FakeCb:
    def __init__(self, uid=424242, data=""):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = FakeMessage(uid)
        self.answered = []

    async def answer(self, text=None, show_alert=False):
        self.answered.append((text, show_alert))


@given('завершенная сессия копайлота с утвержденным проектом "{title}"')
def step_completed_session_named(context, title):
    tmp_file = Path(tempfile.mkdtemp()) / "copilot_field.json"
    context.manager = CopilotSessionManager(file_path=tmp_file, ttl=3600)
    context.session = context.manager.create_or_replace_session(
        user_id=424242, topic="Архитипы Юнга в городе",
    )
    context.session.stage = "completed"
    context.session.selected_styles = ["Сюрреализм", "Экспрессионизм"]
    context.session.manifesto = "Манифест: исследование Тени через оптические искажения."
    context.session.summary = "Психологический нерв — столкновение Персоны и Тени."
    context.session.tech_preferences = {
        "support": "Съемка с рук (микро-ICM)",
        "lens": "Гелиос 44-2 58mm f/2",
        "filter_accessory": "Black Pro-Mist 1/4",
        "lighting": "Контровой натриевый свет",
    }
    context.session.candidate_projects = [
        {
            "id": 1,
            "title": title,
            "vector": "Интимный / Камерный",
            "visual_hook": "Одинокая фигура у мокрой стены проулка.",
            "lighting_scene": "Один узкий луч контрового натриевого фонаря.",
            "camera_setup": "1/15 с, f/2, ISO 200, Velvia",
            "shooting_action": "Микро-тремор с рук в момент экспозиции.",
            "gear_summary": "Fujifilm X-T4, Гелиос 44-2, Black Pro-Mist 1/4",
            "shooting_steps": [
                "Найти контровой свет",
                "Выставить экспозицию по светам",
            ],
        },
    ]
    context.session.selected_project_idx = 0
    context.manager.save_session(context.session)


@when("фотограф запрашивает полевой ассистент")
def step_request_field_assistant(context):
    context.checklist = engine.generate_field_assistant_checklist(context.session)


@then("формируется карманный чек-лист с параметрами Fujifilm X-T4, аккумуляторами и объективом")
def step_verify_checklist(context):
    assert "Полевой ассистент съемки: «Шепот Тени»" in context.checklist
    assert "Fujifilm X-T4" in context.checklist
    assert "NP-W235" in context.checklist
    assert "Гелиос 44-2 58mm f/2" in context.checklist
    assert "Black Pro-Mist 1/4" in context.checklist


@then("генерируется готовый Midjourney-промпт с оптикой и стилями")
def step_verify_mj_prompt(context):
    context.mj_card = engine.generate_midjourney_prompt(context.session)
    assert "🎨 <b>Эскизный промпт" in context.mj_card
    assert "<code>" in context.mj_card
    assert "surrealism aesthetic" in context.mj_card
    assert "Helios 44-2" in context.mj_card
    assert "Fujifilm X-T4" in context.mj_card


@then('проект успешно экспортируется в Apple Notes в папку "Фотопроекты" со статусом "[К съемке]"')
def step_verify_apple_notes_export(context):
    with patch("services.apple_notes.ensure_folder", return_value=True) as mock_folder:
        with patch(
            "services.apple_notes.create_note", return_value="x-coredata://note-bdd-1",
        ) as mock_create:
            note_id = engine.export_copilot_project_to_apple_notes(
                context.session, folder="Фотопроекты",
            )

    assert note_id == "x-coredata://note-bdd-1"
    mock_folder.assert_called_once_with("Фотопроекты")
    mock_create.assert_called_once()
    assert "[К съемке] Шепот Тени" in mock_create.call_args[1]["title"]
    assert mock_create.call_args[1]["folder"] == "Фотопроекты"


@given("завершенная сессия копайлота с утвержденным проектом")
def step_given_completed_generic(context):
    step_completed_session_named(context, "Городской туман")


@when("фотограф нажимает экспорт в Apple Notes, но системный мост возвращает ошибку")
def step_export_notes_error(context):
    cb = FakeCb(424242, data="cp_export_apple_notes")
    with patch.object(hc, "get_copilot_manager", lambda: context.manager):
        with patch(
            "handlers.copilot.export_copilot_project_to_apple_notes",
            side_effect=RuntimeError("AppleScript bridge failed"),
        ):
            context.exception_raised = False
            try:
                _run(hc.cb_copilot_export_apple_notes(cb))
            except Exception:
                context.exception_raised = True
            context.cb = cb


@then("бот не падает с исключением")
def step_verify_no_exception(context):
    assert context.exception_raised is False


@then("пользователю выводится информативное сообщение об ошибке Apple Notes")
def step_verify_error_message(context):
    assert any("Не удалось создать заметку" in a[0] for a in context.cb.answered if a[0])


@given("сессия копайлота отсутствует у пользователя")
def step_no_session(context):
    tmp_file = Path(tempfile.mkdtemp()) / "copilot_empty.json"
    context.manager = CopilotSessionManager(file_path=tmp_file, ttl=3600)
    context.cb = FakeCb(424242, data="cp_to_field_assistant")


@when('приходит callback "cp_to_field_assistant"')
def step_call_to_field_assistant_no_session(context):
    with patch.object(hc, "get_copilot_manager", lambda: context.manager):
        _run(hc.cb_copilot_to_field_assistant(context.cb))


@then('система отвечает "Сессия не найдена" и не вызывает падения')
def step_verify_session_not_found(context):
    assert any("Сессия не найдена" in a[0] for a in context.cb.answered if a[0])


@given("сессия копайлота уже завершена и удалена")
def step_session_already_finished(context):
    tmp_file = Path(tempfile.mkdtemp()) / "copilot_empty.json"
    context.manager = CopilotSessionManager(file_path=tmp_file, ttl=3600)
    context.cb = FakeCb(424242, data="cp_finish")


@when('приходит повторный callback "cp_finish"')
def step_call_finish_again(context):
    with patch.object(hc, "get_copilot_manager", lambda: context.manager):
        _run(hc.cb_copilot_finish(context.cb))


@then('система отвечает "Сессия уже завершена" без исключений')
def step_verify_session_already_finished(context):
    assert any("Сессия уже завершена" in a[0] for a in context.cb.answered if a[0])


@given("сессия со списком проектов, но selected_project_idx равен None")
def step_session_no_selected_idx(context):
    step_completed_session_named(context, "Импульсивный кадр")
    context.session.selected_project_idx = None
    context.manager.save_session(context.session)


@then("ассистент автоматически использует первый проект из списка и не падает с IndexError")
def step_verify_fallback_first_project(context):
    assert "Полевой ассистент съемки: «Импульсивный кадр»" in context.checklist


@given("завершенная сессия с пустыми tech_preferences и без шагов съемки")
def step_session_empty_tech(context):
    tmp_file = Path(tempfile.mkdtemp()) / "copilot_empty_tech.json"
    context.manager = CopilotSessionManager(file_path=tmp_file, ttl=3600)
    context.session = context.manager.create_or_replace_session(
        user_id=424242, topic="Минималистичный свет",
    )
    context.session.selected_styles = []
    context.session.tech_preferences = {}
    context.session.candidate_projects = [
        {
            "id": 1,
            "title": "Минимализм",
            "vector": "Авторский вектор",
            "visual_hook": "Белый лист на черном фоне.",
            "lighting_scene": "",
            "camera_setup": "",
            "shooting_action": "",
            "shooting_steps": [],
        },
    ]
    context.session.selected_project_idx = 0
    context.manager.save_session(context.session)


@when("формируется полевой чек-лист и Markdown для Apple Notes")
def step_format_empty_tech(context):
    context.checklist = engine.generate_field_assistant_checklist(context.session)
    context.notes_title, context.notes_body = engine.format_copilot_project_for_notes(
        context.session
    )


@then("подставляются надежные значения по умолчанию для X-T4 и базовый алгоритм съемки")
def step_verify_defaults(context):
    assert "Fujifilm X-T4" in context.checklist
    assert "NP-W235" in context.checklist
    assert "1. Оценить геометрию локации" in context.checklist
    assert "[К съемке] Минимализм" in context.notes_title
    assert "## 📷 Параметры съёмки (Fujifilm X-T4)" in context.notes_body
