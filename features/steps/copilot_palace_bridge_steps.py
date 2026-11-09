"""Шаги BDD для features/copilot_palace_bridge.feature (Step B1 / MP-1).

Сквозные сценарии поиска и интеграции ассоциативных резонансов из Дворца Памяти в арт-копайлоте.
"""

from unittest.mock import MagicMock, patch

from behave import given, then, when

from handlers.copilot import build_copilot_dialogue_kb
from services import copilot_engine as engine
import services.copilot_palace_bridge as bridge
from services.copilot_session import CopilotSession, CopilotSessionManager


@given('пользователь начинает диалог копайлота с темой "{topic}"')
def step_start_copilot_topic(context, topic):
    context.manager = CopilotSessionManager(file_path=None, ttl=3600)
    context.session = context.manager.create_or_replace_session(user_id=777, topic=topic)
    context.topic = topic


@when("выполняется семантический поиск резонансов в Apple Notes")
def step_semantic_search_notes(context):
    mock_notes = [
        {
            "id": "n1",
            "name": "Ночной дождь на асфальте",
            "snippet": "Блики неоновых огней дрожат в лужах.",
            "_score": 0.89,
        }
    ]
    with patch("services.notes_embeddings.search_notes_hybrid", return_value=mock_notes):
        context.resonances = bridge.find_palace_resonances(context.topic, user_id=777)
    context.session.tech_preferences["palace_resonances"] = context.resonances


@then("найдены ассоциативные мосты с высокой релевантностью")
def step_resonances_found(context):
    assert len(context.resonances) >= 1
    assert context.resonances[0]["title"] == "Ночной дождь на асфальте"
    assert context.resonances[0]["score"] == 0.89


@then("в системный промпт арт-директора встраивается контекст мыслей из Дворца")
def step_prompt_contains_resonances(context):
    msgs = engine.build_socratic_messages(
        context.topic,
        [{"role": "user", "content": "Хочу мрачную атмосферу"}],
        palace_resonances=context.resonances,
    )
    system_prompt = msgs[0]["content"]
    assert "АССОЦИАТИВНЫЕ РЕЗОНАНСЫ ИЗ ДВОРЦА ПАМЯТИ" in system_prompt
    assert "Ночной дождь на асфальте" in system_prompt


@then('в клавиатуре диалога появляется кнопка "Мысли из Дворца Памяти"')
def step_dialogue_kb_has_resonances_btn(context):
    kb = build_copilot_dialogue_kb(context.session)
    cbs = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "cp_palace_resonances" in cbs


@then("при нажатии кнопки открывается карточка с цитатами в blockquote")
def step_card_with_blockquote(context):
    card = bridge.format_palace_resonances_card(context.resonances, context.topic)
    assert "<blockquote>" in card and "</blockquote>" in card
    assert "Ночной дождь на асфальте" in card


@given("пользователь передает пустую тему или одни пробелы")
def step_empty_topic(context):
    context.empty_topic = "   "


@when("инициируется поиск резонансов во Дворце Памяти")
def step_initiate_search_empty(context):
    context.search_mock = MagicMock()
    with patch("services.notes_embeddings.search_notes_hybrid", context.search_mock):
        context.result = bridge.find_palace_resonances(context.empty_topic)


@then("возвращается пустой список резонансов без обращения к базам данных")
def step_empty_list_no_db(context):
    assert context.result == []
    context.search_mock.assert_not_called()


@given('активна тема копайлота "{topic}"')
def step_active_copilot_topic(context, topic):
    context.topic = topic


@when("сервис поиска эмбеддингов выбрасывает сетевое исключение")
def step_embeddings_throw_error(context):
    def fake_error(*args, **kwargs):
        raise ConnectionError("Ollama host is unreachable")

    with patch("services.notes_embeddings.search_notes_hybrid", fake_error):
        with patch("services.memory_embeddings.search_similar", fake_error):
            context.result = bridge.find_palace_resonances(context.topic, user_id=777)


@then("копайлот применяет graceful degradation и возвращает пустой список")
def step_graceful_degradation(context):
    assert context.result == []


@then("работа диалога арт-директора продолжается без ошибок")
def step_dialogue_continues_safely(context):
    ctx_prompt = bridge.format_palace_resonances_context([])
    assert ctx_prompt == ""


@given('пользователь исследует редкую тему "{topic}"')
def step_rare_topic(context, topic):
    context.rare_topic = topic


@when("поиск во Дворце Памяти не находит релевантных записей")
def step_no_matches_found(context):
    with patch("services.notes_embeddings.search_notes_hybrid", return_value=[]):
        with patch("services.memory_embeddings.search_similar", return_value=[]):
            context.empty_resonances = bridge.find_palace_resonances(context.rare_topic)


@then("карточка ассоциаций выводит дружелюбное сообщение об отсутствии прямых записей")
def step_empty_card_message(context):
    card = bridge.format_palace_resonances_card(context.empty_resonances, context.rare_topic)
    assert "В чертогах Дворца пока не найдено прямых записей" in card
    assert context.rare_topic in card


@then("кнопка резонансов не перегружает клавиатуру диалога")
def step_no_btn_in_kb(context):
    session = CopilotSession(user_id=777, topic=context.rare_topic)
    kb = build_copilot_dialogue_kb(session)
    cbs = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "cp_palace_resonances" not in cbs


@given('активна сессия с темой "{topic}"')
def step_session_with_topic(context, topic):
    context.session = CopilotSession(user_id=777, topic=topic)


@when("резонансы найдены при инициализации диалога")
def step_resonances_cached(context):
    context.search_mock = MagicMock(return_value=[
        {"title": "Зеркало", "snippet": "Отражения", "source": "Notes", "score": 0.9}
    ])
    with patch.object(bridge, "find_palace_resonances", context.search_mock):
        context.first_call = bridge.get_or_find_session_resonances(context.session)


@then("повторные запросы резонансов читаются из кэша сессии без повторного поиска")
def step_cached_read(context):
    with patch.object(bridge, "find_palace_resonances", context.search_mock):
        context.second_call = bridge.get_or_find_session_resonances(context.session)
    assert context.first_call == context.second_call
    assert context.search_mock.call_count == 1


@given('найдены резонансы с опасными символами "{tag}" и "{amp}"')
def step_dangerous_symbols(context, tag, amp):
    context.dangerous_resonances = [
        {
            "title": f"Опасная заметка {amp} тест",
            "snippet": f"Вставка кода {tag} внутри текста",
            "source": "Apple Notes",
            "score": 0.85,
        }
    ]


@when("формируется Telegram-карточка ассоциативных мостов")
def step_format_telegram_card(context):
    context.rendered_card = bridge.format_palace_resonances_card(
        context.dangerous_resonances,
        topic="Безопасность",
    )


@then("специальные символы экранированы")
def step_symbols_escaped(context):
    assert "<script>" not in context.rendered_card
    assert "&amp;" in context.rendered_card


@then("карточка не содержит запрещенных тегов и комментариев")
def step_card_no_forbidden_tags(context):
    assert "<!--" not in context.rendered_card
    assert "<div>" not in context.rendered_card
    assert "<p>" not in context.rendered_card
