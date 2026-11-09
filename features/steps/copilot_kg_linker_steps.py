"""Шаги BDD для features/copilot_kg_linker.feature (Шаг B2 / MP-2).

Сквозные сценарии извлечения сущностей, генерации триплетов и привязки фотопроектов к Дворцу.
"""

from unittest.mock import AsyncMock

from behave import given, then, when

from handlers.copilot import build_field_assistant_kb, build_kg_linker_kb
import services.copilot_kg_linker as linker
from services.copilot_session import CopilotSession


@given('пользователь завершил проработку концепта с темой "{topic}"')
def step_completed_concept(context, topic):
    context.session = CopilotSession(user_id=888, topic=topic)


@given('в проекте выбраны стили "{style}", оптика "{lens}" и художник "{artist}"')
def step_set_project_params(context, style, lens, artist):
    context.session.selected_styles = [{"name": style}]
    context.session.tech_preferences = {"lens": lens}
    context.session.manifesto_text = f"Вдохновлено работами художника {artist}."


@when("выполняется привязка проекта к Графу Знаний и Дворцу")
def step_perform_linking(context):
    context.link_data = linker.link_project_to_palace_kg(context.session)


@then('проект классифицирован в крыло "{wing}" и комнату "{room}"')
def step_check_classification(context, wing, room):
    assert context.link_data["wing_key"] == wing
    assert context.link_data["room"] == room


@then("сгенерированы нормализованные триплеты для Графа Знаний")
def step_check_triplets(context):
    triplets = context.link_data["triplets"]
    assert len(triplets) >= 3
    preds = [p for _, p, _ in triplets]
    assert "has_style" in preds
    assert "located_in_wing" in preds


@then('в клавиатуре полевого ассистента доступна кнопка "Привязать к Дворцу и Графу"')
def step_check_assistant_kb(context):
    kb = build_field_assistant_kb(context.session)
    cbs = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "cp_link_palace_kg" in cbs


@then("при сохранении фактов MCP-инструмент фиксирует триплеты в базе знаний")
def step_save_via_mock_mcp(context):
    import asyncio
    mock_mcp = AsyncMock()
    mock_mcp.call_tool.return_value = '{"status": "ok"}'
    count, errors = asyncio.run(
        linker.save_project_to_kg(context.session, mcp_client=mock_mcp),
    )
    assert count >= 3
    assert errors == []


@given("подготовлен проект для привязки к Графу Знаний")
def step_prepare_project(context):
    context.session = CopilotSession(user_id=888, topic="Сбойная тема")


@when("MCP-сервер mempalace недоступен или возвращает ошибку")
def step_mcp_fails(context):
    import asyncio
    mock_mcp = AsyncMock()
    mock_mcp.call_tool.side_effect = ConnectionError("MCP server is down")
    count, errors = asyncio.run(
        linker.save_project_to_kg(context.session, mcp_client=mock_mcp),
    )
    context.save_count = count
    context.save_errors = errors


@then("система применяет graceful degradation без падения бота")
def step_verify_graceful(context):
    assert context.save_count == 0
    assert len(context.save_errors) >= 1


@then("пользователь получает уведомление об ошибке записи в Граф")
def step_error_notification(context):
    assert "MCP server is down" in context.save_errors[0]


@given("передан пустой концепт без указания темы и стилей")
def step_empty_concept(context):
    context.empty_concept = {}


@when("извлекаются сущности и генерируются триплеты")
def step_extract_empty(context):
    context.empty_link = linker.link_project_to_palace_kg(context.empty_concept)


@then("формируются безопасные базовые триплеты с техникой по умолчанию")
def step_base_triplets(context):
    triplets = context.empty_link["triplets"]
    assert len(triplets) >= 2
    assert any("Fujifilm X-T4" in str(t) for t in triplets)


@then("концепт направляется в общую фотолабораторию")
def step_default_room(context):
    assert "Фотолаборатория" in context.empty_link["room"]


@given("факты проекта уже успешно записаны в Граф Знаний")
def step_already_saved(context):
    context.saved_kb = build_kg_linker_kb(saved=True)


@when("пользователь нажимает кнопку подтверждения записи повторно")
def step_click_saved_button(context):
    context.saved_cbs = [
        btn.callback_data
        for row in context.saved_kb.inline_keyboard
        for btn in row
    ]


@then("система сообщает что факты уже зафиксированы без дублирования записей")
def step_check_noop(context):
    assert "cp_noop" in context.saved_cbs
    assert "cp_save_kg" not in context.saved_cbs


@given('пользователь прорабатывает проект с темой "{topic}"')
def step_psychology_topic(context, topic):
    context.session = CopilotSession(user_id=888, topic=topic)


@when("определяется локация во Дворце Памяти")
def step_classify_location(context):
    context.classification = linker.classify_palace_room_for_project(context.session)


@then('проект направляется в крыло "{wing1}" или "{wing2}" с тематическим залом')
def step_check_wings(context, wing1, wing2):
    assert context.classification["wing_key"] in (wing1, wing2)
    assert any(
        kw in context.classification["room"]
        for kw in ["Архетипов", "Экзистенции", "Зал", "Галерея"]
    )


@given('проект содержит в заголовке и оптике спецсимволы "{sym}" и кавычки')
def step_dangerous_chars(context, sym):
    context.dangerous_link_data = {
        "project_title": f"Свет {sym} Тень \"Кадр\"",
        "wing_display": "🎨 Творчество",
        "room": f"Чертог {sym}",
        "triplets": [(f"Свет {sym}", "has_style", "Стиль <X>")],
    }


@when("формируется карточка привязки к Графу Знаний")
def step_format_card(context):
    context.card_html = linker.format_kg_link_card(context.dangerous_link_data)


@then("специальные символы экранированы для Telegram HTML")
def step_check_escaped(context):
    assert "&lt;&amp;&gt;" in context.card_html
    assert "Стиль &lt;X&gt;" in context.card_html


@then("карточка триплетов не содержит запрещенных тегов и комментариев")
def step_no_forbidden_tags(context):
    assert "<!--" not in context.card_html
    assert "<div>" not in context.card_html
    assert "<script>" not in context.card_html
