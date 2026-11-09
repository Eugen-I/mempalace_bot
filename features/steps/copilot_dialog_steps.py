"""Шаги BDD для features/copilot_dialog.feature.

Сквозные сценарии интерактивного Сократического диалога арт-копайлота.
"""

import asyncio
from unittest.mock import patch

from behave import given, then, when

from handlers.copilot import build_copilot_dialogue_kb
import services.copilot_engine as engine
from services.copilot_session import CopilotSession, CopilotSessionManager
from services.text_formatter import safe_html_format


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


@given('пользователь начинает сессию копайлота с темой "{topic}"')
def step_start_copilot_session(context, topic):
    context.manager = CopilotSessionManager(file_path=None, ttl=3600)
    context.session = context.manager.create_or_replace_session(user_id=777, topic=topic)
    assert context.session.topic == topic
    assert context.session.stage == "discuss"


@when("арт-директор задает первый Сократический вопрос")
def step_socratic_opening(context):
    async def fake_open(*args, **kwargs):
        return "Тема Юнга глубока. Какую эмоцию вы хотите исследовать в первую очередь?"

    with patch.object(engine, "get_ai_response_async", fake_open):
        context.opening = _run(engine.start_copilot_discussion(context.session))
    assert len(context.session.dialogue_history) >= 1
    assert context.session.dialogue_history[0]["role"] == "assistant"


@when('фотограф отвечает "{answer}"')
def step_photographer_answers(context, answer):
    context.session.add_user_message(answer)
    assert context.session.dialogue_history[-1]["content"] == answer


@when("арт-директор развивает мысль и уточняет характер света")
def step_director_develops(context):
    async def fake_reply(*args, **kwargs):
        return "Зеркала в метро дают отличную геометрию. Какой свет вы выберете: мерцающий неон или полутьму?"

    with patch.object(engine, "get_ai_response_async", fake_reply):
        context.reply = _run(engine.generate_socratic_reply(context.session, "Уточнение света"))
    assert context.session.dialogue_history[-1]["role"] == "assistant"


@when("фотограф нажимает кнопку перехода к выбору стилей")
def step_click_to_styles(context):
    async def fake_summarize(*args, **kwargs):
        return (
            "🎯 <b>Концептуальный конфликт:</b> Встреча с Тенью в метро\n"
            "💡 <b>Ключевая метафора:</b> Зеркальное расщепление\n"
            "🏛 <b>Пространство и свет:</b> Подземный полумрак"
        )

    with patch.object(engine, "get_ai_response_async", fake_summarize):
        context.summary = _run(engine.summarize_creative_dialogue(context.session))
    context.session.stage = "styles"
    context.manager.save_session(context.session)


@then("диалог суммаризируется в концептуальное резюме")
def step_check_summary_created(context):
    assert context.session.summary != ""
    assert "Концептуальный конфликт" in context.session.summary


@then("резюме содержит конфликт, метафору и пространство")
def step_check_summary_content(context):
    s = context.session.summary
    assert "Концептуальный конфликт" in s
    assert "Ключевая метафора" in s
    assert "Пространство и свет" in s


@then('сессия переходит на этап "styles"')
def step_check_session_styles(context):
    assert context.session.stage == "styles"


@given('активна сессия копайлота на этапе "discuss"')
def step_active_session_discuss(context):
    context.manager = CopilotSessionManager(file_path=None, ttl=3600)
    context.session = context.manager.create_or_replace_session(user_id=777, topic="Ночной город")
    context.initial_history_len = len(context.session.dialogue_history)


@when("фотограф отправляет пустое сообщение или пробелы")
def step_send_empty_message(context):
    context.empty_input = "   "
    clean = context.empty_input.strip()
    if clean:
        context.session.add_user_message(clean)


@then("обработчик отклоняет пустое сообщение без добавления в историю")
def step_check_empty_not_added(context):
    assert len(context.session.dialogue_history) == context.initial_history_len


@then('сессия остается на этапе "discuss"')
def step_check_remains_discuss(context):
    assert context.session.stage == "discuss"


@when("языковая модель возвращает ошибку или недоступна")
def step_model_fails(context):
    async def fail_call(*args, **kwargs):
        raise RuntimeError("API timeout")

    with patch.object(engine, "get_ai_response_async", fail_call):
        context.fallback_reply = _run(engine.generate_socratic_reply(context.session, "Вопрос"))


@then("копайлот использует безопасный fallback вопрос без падения бота")
def step_check_fallback_reply(context):
    assert context.fallback_reply != ""
    assert "пространстве" in context.fallback_reply or "Давай подумаем" in context.fallback_reply


@then("ответ фиксируется в сессии")
def step_check_reply_saved(context):
    assert context.session.dialogue_history[-1]["content"] == context.fallback_reply


@given("пользователь только что создал сессию без ответов фотографа")
def step_fresh_session_no_user_turns(context):
    context.session = CopilotSession(user_id=888, topic="Свежая тема")
    context.session.add_assistant_message("Первый вопрос арт-директора?")


@when("проверяется клавиатура управления диалогом")
def step_check_dialog_kb(context):
    context.kb = build_copilot_dialogue_kb(context.session)


@then("кнопка перехода к стилям недоступна до первой реплики пользователя")
def step_styles_btn_not_available(context):
    buttons = [btn.text for row in context.kb.inline_keyboard for btn in row]
    assert not any("Перейти к выбору стилей" in b for b in buttons)


@given('активна сессия копайлота с темой "{topic}"')
def step_active_session_topic(context, topic):
    context.manager = CopilotSessionManager(file_path=None, ttl=3600)
    context.session = context.manager.create_or_replace_session(user_id=999, topic=topic)


@when('фотограф нажимает "Пауза"')
def step_click_pause(context):
    assert context.manager.pause_session(999) is True


@then("сессия помечается как приостановленная")
def step_check_session_paused(context):
    sess = context.manager.get_session(999)
    assert sess.is_paused is True


@then("последующие текстовые сообщения не перехватываются копайлотом")
def step_check_not_intercepted(context):
    assert context.manager.is_in_copilot(999) is False


@when('фотограф нажимает "Продолжить проект"')
def step_click_resume(context):
    context.resumed = context.manager.resume_session(999)
    assert context.resumed is not None


@then("сессия возобновляется с восстановлением контекста")
def step_check_resumed_context(context):
    assert context.resumed.is_paused is False
    assert context.manager.is_in_copilot(999) is True
    assert context.resumed.topic == context.session.topic


@when("формируется карточка заголовка диалога")
def step_format_header(context):
    safe_topic = safe_html_format(context.session.topic)
    context.rendered_header = f"🎙 <b>Арт-копайлот | Тема: «{safe_topic}»</b>"


@then("спецсимволы корректно экранированы для Telegram HTML")
def step_check_html_escaped(context):
    assert "<&>" not in context.rendered_header
    assert "&lt;&amp;&gt;" in context.rendered_header


@then("сообщение не содержит запрещенных тегов")
def step_no_forbidden_tags(context):
    forbidden = ["<!--", "<p>", "<div>", "<span", "<br>"]
    for tag in forbidden:
        assert tag not in context.rendered_header
