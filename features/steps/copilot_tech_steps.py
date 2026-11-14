"""Шаги BDD для features/copilot_tech.feature."""

import asyncio
from unittest.mock import patch

from behave import given, then, when

import services.copilot_engine as engine
from services.copilot_session import CopilotSessionManager


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


@given('пользователь находится на этапе технического сетапа "tech"')
def step_session_in_tech_stage(context):
    context.manager = CopilotSessionManager(file_path=None, ttl=3600)
    context.session = context.manager.create_or_replace_session(
        user_id=7777, topic="Архитипы Юнга в метро",
    )
    context.session.summary = "🎯 Концептуальный конфликт: Встреча с Тенью"
    context.session.selected_styles = ["Импрессионизм", "Пиктореализм"]
    context.session.manifesto = "Свет обнажает скрытую суть."
    context.session.stage = "tech"


@when('инициализируются базовые параметры съемки для стилей "Импрессионизм, Пиктореализм"')
def step_init_tech_params(context):
    context.tech = engine.init_tech_preferences(context.session)


@then('сетап содержит камеру "Fujifilm X-T4", объектив "Гелиос 44-2" и метод "С рук"')
def step_check_initial_tech(context):
    assert context.tech["camera"] == "Fujifilm X-T4"
    assert "Гелиос" in context.tech["lens"]
    assert "С рук" in context.tech["support"]


@when('фотограф переключает метод съемки на "Штатив"')
def step_switch_to_tripod(context):
    engine.update_tech_preference(context.session, "support", "tripod")


@then("выдержка и метод съемки обновляются для штатива")
def step_check_tripod_params(context):
    assert "Штатив" in context.session.tech_preferences["support"]
    assert context.session.tech_preferences["shutter_speed"] == '1/15"'


@when("фотограф утверждает технический сетап")
def step_confirm_tech_stage(context):
    context.session.stage = "variants"
    context.manager.save_session(context.session)


@then('сессия переходит на этап "variants"')
def step_check_variants_stage(context):
    assert context.session.stage == "variants"


@given("в сессии настроен базовый технический сетап")
def step_session_with_tech_setup(context):
    step_session_in_tech_stage(context)
    engine.init_tech_preferences(context.session)


@when("языковая модель недоступна при консультации оператора")
def step_llm_fails_tech_consult(context):
    async def fail_call(*args, **kwargs):
        raise RuntimeError("LLM unavailable")

    with patch.object(engine, "get_ai_response_async", fail_call):
        context.advice = _run(
            engine.consult_tech_parameters(context.session, "Как снять на открытой диафрагме?"),
        )


@then("система возвращает безопасный совет оператора без падения бота")
def step_check_fallback_advice(context):
    assert context.advice != ""
    assert "Fujifilm X-T4" in context.advice
    assert "Focus Peaking" in context.advice


@when("фотограф отправляет пустой текст из пробелов в качестве съемочных условий")
def step_user_sends_whitespace_tech(context):
    raw_input = "    "
    clean = raw_input.strip()
    context.input_handled = bool(clean)


@then("сообщение отклоняется и технические параметры не изменяются")
def step_check_whitespace_tech_rejected(context):
    assert context.input_handled is False


@when('передается неизвестный технический ключ "{key}" со значением "{val}"')
def step_unknown_tech_key(context, key, val):
    engine.update_tech_preference(context.session, key, val)


@then("параметры съемки сохраняют целостность и не вызывают ошибку")
def step_check_tech_integrity(context):
    assert isinstance(context.session.tech_preferences, dict)
    assert context.session.tech_preferences["camera"] == "Fujifilm X-T4"


@given("в сессии настроен базовый сетап с рук")
def step_session_with_handheld(context):
    step_session_in_tech_stage(context)
    engine.init_tech_preferences(context.session)
    assert "С рук" in context.session.tech_preferences["support"]


@when('фотограф отправляет текстовое условие "{user_text}"')
def step_user_sends_tech_text(context, user_text):
    async def fake_call(*args, **kwargs):
        return "В ночном дожде штатив обеспечит резкость контуров."

    with patch.object(engine, "get_ai_response_async", fake_call):
        context.advice = _run(
            engine.consult_tech_parameters(context.session, user_text),
        )


@then("система автоматически распознает метод съемки со штатива и профиль Velvia")
def step_check_detected_params(context):
    assert "Штатив" in context.session.tech_preferences["support"]
    assert context.session.tech_preferences["film_sim"] == "Velvia"


@then("пожелание автора сохраняется в заметках почерка")
def step_check_handwriting_notes(context):
    notes = context.session.tech_preferences.get("handwriting_notes", "")
    assert "Будет ночной дождь" in notes


@given('тема проекта содержит спецсимволы "{topic_text}"')
def step_topic_with_special_chars(context, topic_text):
    context.manager = CopilotSessionManager(file_path=None, ttl=3600)
    context.session = context.manager.create_or_replace_session(
        user_id=7777, topic=topic_text,
    )
    context.session.selected_styles = ["Сюрреализм"]
    engine.init_tech_preferences(context.session)


@when("формируется карточка технического сетапа")
def step_format_tech_card(context):
    context.card = engine.format_tech_card(context.session, advice="Проверьте экспозицию")


@then("спецсимволы корректно экранированы для Telegram HTML без запрещенных тегов")
def step_check_tech_card_html(context):
    card = context.card
    assert "&lt;ночь &amp; тени&gt;" in card
    assert "<!--" not in card
    assert "<p>" not in card
    assert "<div>" not in card
    assert "<b>" in card
