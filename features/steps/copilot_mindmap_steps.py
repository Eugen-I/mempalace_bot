"""Шаги BDD для features/copilot_mindmap.feature (Шаг B3 / MP-3).

Сквозные сценарии генерации автономной ментальной карты (Canvas force-directed graph) фотопроекта.
"""

from pathlib import Path
from unittest.mock import patch

from behave import given, then, when

from handlers import copilot as hc
import services.copilot_mindmap as mm
from services.copilot_session import CopilotSession, CopilotSessionManager


class FakeUser:
    def __init__(self, uid=424242):
        self.id = uid


class FakeMessage:
    def __init__(self, uid=424242):
        self.from_user = FakeUser(uid)
        self.answers = []
        self.documents = []

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append(text)

    async def answer_document(self, document, caption=None, parse_mode=None, reply_markup=None):
        self.documents.append({"document": document, "caption": caption})


class FakeCb:
    def __init__(self, uid=424242, data=""):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = FakeMessage(uid)
        self.answered = []

    async def answer(self, text=None, show_alert=False):
        self.answered.append((text, show_alert))


@given('фотограф завершил сессию копайлота с темой "{topic}"')
def step_finished_session(context, topic):
    context.session = CopilotSession(user_id=424242, topic=topic)


@given('проект содержит стили "{style}", оптику "{lens}" и референс "{artist}"')
def step_set_copilot_params(context, style, lens, artist):
    context.session.selected_styles = [{"name": style}]
    context.session.tech_preferences = {"lens": lens}
    context.session.manifesto_text = f"Вдохновлено мастером {artist}."


@when("запрашивается экспорт ментальной карты концепта")
def step_request_mindmap(context):
    context.html = mm.generate_project_mindmap_html(context.session)
    context.data = mm.build_project_mindmap_data(context.session)


@then("генерируется автономный HTML5 Canvas граф с 60 FPS без внешних CDN")
def step_verify_canvas_html(context):
    assert "<!DOCTYPE html>" in context.html
    assert "<canvas id=\"canvas\"></canvas>" in context.html
    assert "https://" not in context.html
    assert "http://" not in context.html


@then("в графе присутствуют узлы проекта, чертога Дворца, стилей, техники и референсов")
def step_verify_nodes(context):
    types = [n["type"] for n in context.data["nodes"]]
    assert "project" in types
    assert "palace" in types
    assert "style" in types
    assert "gear" in types
    assert "reference" in types


@then('в меню ассистента доступна кнопка "Ментальная карта (.html)"')
def step_check_button_in_assistant(context):
    kb = hc.build_field_assistant_kb(context.session)
    cbs = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "cp_export_mindmap" in cbs


@then("пользователю отправляется HTML-файл документа с информационной карточкой")
def step_verify_document_sent(context):
    import asyncio
    mgr = CopilotSessionManager(file_path=None, ttl=3600)
    mgr.save_session(context.session)
    with patch.object(hc, "get_copilot_manager", lambda: mgr):
        cb = FakeCb(424242, data="cp_export_mindmap")
        asyncio.run(hc.cb_copilot_export_mindmap(cb))
        assert len(cb.message.documents) == 1
        assert "Ментальная карта концепта" in cb.message.documents[0]["caption"]


@given("активна сессия копайлота с концептом для экспорта")
def step_active_session_export(context):
    context.mgr = CopilotSessionManager(file_path=None, ttl=3600)
    context.session = context.mgr.create_or_replace_session(424242, "Хрупкий свет")


@when("файловая система возвращает ошибку переполнения диска")
def step_disk_full_error(context):
    import asyncio

    def fake_io_error(*args, **kwargs):
        raise OSError("Disk full")

    with patch.object(hc, "get_copilot_manager", lambda: context.mgr):
        with patch.object(hc, "export_project_mindmap_file", fake_io_error):
            cb = FakeCb(424242, data="cp_export_mindmap")
            asyncio.run(hc.cb_copilot_export_mindmap(cb))
            context.last_cb = cb


@then("бот изолирует сбой и отправляет пользователю понятное уведомление об ошибке")
def step_verify_error_handled(context):
    assert len(context.last_cb.message.answers) == 1
    assert "Не удалось создать ментальную карту" in context.last_cb.message.answers[0]


@then("сессия копайлота не сбрасывается и остается доступной")
def step_session_still_active(context):
    assert context.mgr.get_session(424242) is not None


@given('в сессии есть только базовая тема "{topic}" без выбранных стилей')
def step_minimal_session(context, topic):
    context.session = CopilotSession(user_id=424242, topic=topic)


@when("строится граф ментальной карты")
def step_build_mindmap(context):
    context.min_data = mm.build_project_mindmap_data(context.session)


@then("формируются обязательные узлы темы, Дворца Памяти и базовой камеры")
def step_verify_mandatory_nodes(context):
    types = [n["type"] for n in context.min_data["nodes"]]
    assert "project" in types
    assert "palace" in types
    assert "gear" in types


@then("граф успешно генерируется без пустых ссылок")
def step_verify_links_not_empty(context):
    assert len(context.min_data["links"]) >= 2


@given("пользователь не имеет активной сессии копайлота")
def step_no_active_session(context):
    p = Path("/tmp/empty_mindmap_bdd.json")
    if p.exists():
        p.unlink()
    context.empty_mgr = CopilotSessionManager(file_path=p, ttl=3600)
    context.empty_mgr.clear_session(424242)


@when("поступает callback экспорта ментальной карты")
def step_cb_export_no_session(context):
    import asyncio
    with patch.object(hc, "get_copilot_manager", lambda: context.empty_mgr):
        cb = FakeCb(424242, data="cp_export_mindmap")
        asyncio.run(hc.cb_copilot_export_mindmap(cb))
        context.no_session_cb = cb


@then('обработчик отклоняет запрос с уведомлением "{msg}"')
def step_verify_session_rejected(context, msg):
    assert len(context.no_session_cb.answered) >= 1
    assert context.no_session_cb.answered[0][0] == msg


@given("в сессии кэшированы ассоциативные резонансы из Apple Notes")
def step_cache_palace_resonances(context):
    context.session = CopilotSession(user_id=424242, topic="Эхо памяти")
    context.session.tech_preferences = {
        "palace_resonances": [{"title": "Забытая аллея", "snippet": "Шелест листвы"}]
    }


@then("резонансы отображаются как связанные узлы чертога Дворца Памяти")
def step_verify_resonance_nodes(context):
    data = mm.build_project_mindmap_data(context.session)
    types = [n["type"] for n in data["nodes"]]
    assert "resonance" in types
    assert any("Забытая аллея" in n["label"] for n in data["nodes"])


@given('концепт содержит опасные спецсимволы "{sym}" и теги скриптов')
def step_dangerous_symbols(context, sym):
    context.session = CopilotSession(
        user_id=424242,
        topic=f"Проект {sym} <script>alert(1)</script>",
    )


@when("формируется HTML-документ ментальной карты и карточка сообщения")
def step_format_dangerous_html(context):
    context.html = mm.generate_project_mindmap_html(context.session)
    context.card = mm.format_mindmap_card(context.session)


@then("специальные символы экранированы и не нарушают разметку Telegram")
def step_verify_escaped_html(context):
    assert "<script>alert(1)</script>" not in context.html
    assert "<script>" not in context.card
    assert "&amp;" in context.card


@then("карточка ментальной карты не содержит запрещенных тегов")
def step_verify_no_bad_tags(context):
    assert "<!--" not in context.card
    assert "<div>" not in context.card
    assert "<p>" not in context.card
