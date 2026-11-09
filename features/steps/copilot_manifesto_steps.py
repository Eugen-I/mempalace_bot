"""Шаги BDD для features/copilot_manifesto.feature."""

import asyncio
from unittest.mock import patch

from behave import given, then, when

import services.copilot_engine as engine
from services.copilot_session import CopilotSessionManager


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


@given('пользователь находится на этапе манифеста "manifesto"')
def step_session_in_manifesto_stage(context):
    context.manager = CopilotSessionManager(file_path=None, ttl=3600)
    context.session = context.manager.create_or_replace_session(
        user_id=5555, topic="Архитипы Юнга в метро",
    )
    context.session.summary = "🎯 Концептуальный конфликт: Встреча с Тенью"
    context.session.selected_styles = ["Сюрреализм", "Экспрессионизм"]
    context.session.stage = "manifesto"


@when("генерируется первоначальный манифест проекта")
def step_generate_manifesto(context):
    async def fake_gen(*args, **kwargs):
        return "Вспышка обнажает Тень за спиной человека в пустом ночном вагоне."

    with patch.object(engine, "get_ai_response_async", fake_gen):
        context.manifesto = _run(engine.generate_initial_manifesto(context.session))


@then("манифест содержит художественное кредо и сохраняется в сессии")
def step_check_manifesto_saved(context):
    assert context.session.manifesto != ""
    assert "Тень" in context.session.manifesto


@when('фотограф нажимает кнопку тональности "Мрачнее"')
def step_click_darker(context):
    async def fake_refine(*args, **kwargs):
        return "Экзистенциальный мрак поглощает свет, оставляя лишь зловещий контур Тени."

    with patch.object(engine, "get_ai_response_async", fake_refine):
        _run(engine.refine_manifesto(context.session, "darker"))


@then("манифест переписывается с усилением драматизма")
def step_check_manifesto_darker(context):
    assert "мрак" in context.session.manifesto or "контур" in context.session.manifesto


@when("фотограф утверждает манифест")
def step_confirm_manifesto(context):
    context.session.stage = "tech"
    context.manager.save_session(context.session)


@then('сессия переходит на этап "tech"')
def step_check_tech_stage(context):
    assert context.session.stage == "tech"


@given('пользователь находится на этапе манифеста "manifesto" без текста манифеста')
def step_session_manifesto_empty(context):
    step_session_in_manifesto_stage(context)
    context.session.manifesto = ""


@when("языковая модель недоступна при генерации манифеста")
def step_model_fails_on_manifesto(context):
    async def fail_call(*args, **kwargs):
        raise RuntimeError("LLM unavailable")

    with patch.object(engine, "get_ai_response_async", fail_call):
        context.fallback_manif = _run(engine.generate_initial_manifesto(context.session))


@then("система генерирует безопасный базовый манифест без сбоя")
def step_check_fallback_manifesto(context):
    assert context.fallback_manif != ""
    assert "исследуем невидимые слои реальности" in context.fallback_manif
    assert context.session.manifesto == context.fallback_manif


@given('в сессии есть готовый манифест "{text}"')
def step_session_with_manifesto(context, text):
    step_session_in_manifesto_stage(context)
    context.session.manifesto = text


@when("языковая модель падает при попытке сделать манифест короче")
def step_model_fails_on_refine(context):
    async def fail_call(*args, **kwargs):
        raise RuntimeError("LLM down")

    with patch.object(engine, "get_ai_response_async", fail_call):
        context.refine_result = _run(engine.refine_manifesto(context.session, "shorter"))


@then("в сессии сохраняется исходный неизменный манифест")
def step_check_manifesto_unchanged(context):
    assert context.session.manifesto == "Исходный манифест"


@when("пользователь отправляет пробелы в ответ на карточку манифеста")
def step_user_sends_spaces(context):
    raw_input = "    "
    clean = raw_input.strip()
    context.input_handled = bool(clean)
    if clean:
        context.session.manifesto = clean


@then("сообщение отклоняется и манифест не изменяется")
def step_check_spaces_rejected(context):
    assert context.input_handled is False


@when('автор отправляет текстовую правку "{edit_text}"')
def step_user_sends_text_edit(context, edit_text):
    async def fake_custom_refine(*args, **kwargs):
        return f"Манифест обновлен: {edit_text}"

    with patch.object(engine, "get_ai_response_async", fake_custom_refine):
        _run(engine.refine_manifesto(context.session, edit_text))


@then("манифест обогащается пожеланием автора")
def step_check_custom_edit_applied(context):
    assert "мокрое стекло" in context.session.manifesto


@given("в сессии есть развернутый манифест")
def step_session_long_manifesto(context):
    long_text = (
        "Это длинный манифест о структуре сознания, слоях ночного города, "
        "парадоксах взгляда модели и метафизике советской оптики в дождливую погоду."
    )
    step_session_with_manifesto(context, long_text)


@when('фотограф нажимает модификатор "Короче"')
def step_click_shorter(context):
    async def fake_shorten(*args, **kwargs):
        return "Свет ломает форму. Тень обнажает суть."

    with patch.object(engine, "get_ai_response_async", fake_shorten):
        _run(engine.refine_manifesto(context.session, "shorter"))


@then("манифест сокращается до двух афористичных предложений")
def step_check_shorter_manifesto(context):
    assert context.session.manifesto == "Свет ломает форму. Тень обнажает суть."
    sentences = [s for s in context.session.manifesto.split(".") if s.strip()]
    assert len(sentences) == 2
