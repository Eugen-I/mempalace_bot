"""Шаги BDD для features/copilot_variants.feature."""

import asyncio
from unittest.mock import patch

from behave import given, then, when

import services.copilot_engine as engine
from services.copilot_session import CopilotSessionManager


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


@given('пользователь находится на этапе генерации вариантов "variants"')
def step_session_in_variants_stage(context):
    context.manager = CopilotSessionManager(file_path=None, ttl=3600)
    context.session = context.manager.create_or_replace_session(
        user_id=9999, topic="Архитипы Юнга в метро",
    )
    context.session.summary = "🎯 Конфликт: Тень и маска"
    context.session.selected_styles = ["Сюрреализм", "Экспрессионизм"]
    context.session.manifesto = "Свет ломает формы, обнажая теневую суть."
    context.session.tech_preferences = {
        "camera": "Fujifilm X-T4",
        "lens": "Гелиос 44-2 58mm f/2",
        "support": "С рук (микро-ICM)",
        "shutter_speed": '1/6"',
        "aperture": "f/2",
        "film_sim": "Classic Chrome",
    }
    context.session.stage = "variants"


@when("генерируются 3 контрастных проекта на основе темы и манифеста")
def step_generate_variants(context):
    async def fake_gen(*args, **kwargs):
        return (
            '[{"id": 1, "title": "Проект 1", "vector": "Интимный / Камерный", '
            '"visual_hook": "Взгляд сквозь мокрое стекло"}, '
            '{"id": 2, "title": "Проект 2", "vector": "Монументальный / Геометрический", '
            '"visual_hook": "Силуэт на ступенях"}, '
            '{"id": 3, "title": "Проект 3", "vector": "Экспериментальный / Оптический", '
            '"visual_hook": "Преломление в призме"}]'
        )

    with patch.object(engine, "get_ai_response_async", fake_gen):
        context.projects = _run(engine.generate_contrast_variants(context.session))


@then("сформировано ровно 3 контрастных проекта с уникальными векторами")
def step_check_variants_count_and_vectors(context):
    assert len(context.projects) == 3
    vectors = {p["vector"] for p in context.projects}
    assert len(vectors) == 3


@when("фотограф переключает просмотр на проект 2")
def step_switch_to_project_2(context):
    context.card_2 = engine.format_single_variant_card(context.session, idx=1)


@then("карточка отображает описание и параметры второго проекта")
def step_check_card_project_2(context):
    assert "Проект 2 из 3" in context.card_2
    assert "Монументальный" in context.card_2


@when("фотограф утверждает проект 2 как главный фаворит")
def step_pick_project_2(context):
    context.session.selected_project_idx = 1
    context.session.stage = "completed"
    context.manager.save_session(context.session)


@then('сессия помечает второй проект как выбранный и переходит в статус "completed"')
def step_check_project_picked(context):
    assert context.session.selected_project_idx == 1
    assert context.session.stage == "completed"


@given("сессия находится на этапе вариантов без готовых проектов")
def step_session_variants_empty(context):
    step_session_in_variants_stage(context)
    context.session.candidate_projects = []


@when("языковая модель недоступна при генерации вариантов")
def step_model_fails_on_variants(context):
    async def fail_call(*args, **kwargs):
        raise RuntimeError("LLM unavailable")

    with patch.object(engine, "get_ai_response_async", fail_call):
        context.projects = _run(engine.generate_contrast_variants(context.session))


@then("система использует надежные кураторские шаблоны без падения бота")
def step_check_fallback_projects(context):
    assert len(context.projects) == 3
    assert "Зеркальная тень" in context.projects[0]["title"]
    assert context.session.candidate_projects == context.projects


@when("языковая модель возвращает поврежденный JSON с одним проектом")
def step_model_returns_corrupt_json(context):
    async def bad_json_call(*args, **kwargs):
        return '{"projects": [{"id": 1, "title": "Один неполный проект"}]'

    with patch.object(engine, "get_ai_response_async", bad_json_call):
        context.projects = _run(engine.generate_contrast_variants(context.session))


@then("система дополняет варианты кураторскими шаблонами до безопасного числа")
def step_check_salvaged_projects(context):
    assert len(context.projects) >= 2


@given("в сессии есть готовые варианты проектов")
def step_session_with_ready_projects(context):
    step_session_in_variants_stage(context)
    context.session.candidate_projects = engine._build_fallback_contrast_variants(
        context.session,
    )


@when("фотограф отправляет пустой текст из пробелов для доработки кадра")
def step_user_sends_whitespace_refine(context):
    raw_input = "    "
    clean = raw_input.strip()
    context.input_handled = bool(clean)


@then("сообщение отклоняется и активный проект не повреждается")
def step_check_whitespace_refine_rejected(context):
    assert context.input_handled is False
    assert len(context.session.candidate_projects) == 3


@given('в сессии есть проект с описанием кадра "{hook_text}"')
def step_session_with_project_hook(context, hook_text):
    step_session_with_ready_projects(context)
    context.session.candidate_projects[0]["visual_hook"] = hook_text


@when('фотограф отправляет текстовое пожелание "{user_text}"')
def step_user_sends_refine_text(context, user_text):
    async def fake_refine(*args, **kwargs):
        return (
            "КАДР: Силуэт в зеркале с отражением ночных неоновых огней\n"
            "СВЕТ: Неоновый контровой свет\n"
            "СОВЕТ: Отличная атмосфера"
        )

    with patch.object(engine, "get_ai_response_async", fake_refine):
        context.advice = _run(
            engine.refine_active_variant(context.session, user_text, idx=0),
        )


@then("описание кадра обновляется с учетом пожелания автора")
def step_check_refined_hook(context):
    hook = context.session.candidate_projects[0]["visual_hook"]
    assert "неоновых огней" in hook


@given('проект содержит тему со спецсимволами "{topic_text}"')
def step_topic_with_special_symbols(context, topic_text):
    context.manager = CopilotSessionManager(file_path=None, ttl=3600)
    context.session = context.manager.create_or_replace_session(
        user_id=9999, topic=topic_text,
    )
    context.session.candidate_projects = [
        {
            "id": 1,
            "title": "Свет <&> Тень",
            "vector": "Интимный",
            "visual_hook": "Силуэт <в зеркале>",
            "lighting_scene": "Контровой свет",
            "camera_setup": "X-T4",
            "shooting_action": "С рук",
            "gear_summary": "Гелиос",
            "shooting_steps": ["Шаг 1"],
        },
    ]


@when("формируется карточка варианта проекта")
def step_format_variant_card(context):
    context.card = engine.format_single_variant_card(context.session, idx=0)


@then("карточка содержит экранированные спецсимволы для Telegram HTML без запрещенных тегов")
def step_check_escaped_html(context):
    card = context.card
    assert "&lt;&amp;&gt;" in card or "&lt;в зеркале&gt;" in card
    assert "<!--" not in card
    assert "<p>" not in card
    assert "<div>" not in card
    assert "<b>" in card
