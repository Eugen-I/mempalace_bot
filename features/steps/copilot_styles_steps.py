"""Шаги BDD для features/copilot_styles.feature."""

from behave import given, then, when

import services.copilot_engine as engine
from services.copilot_session import CopilotSession, CopilotSessionManager


@given('пользователь находится на этапе выбора стилей "styles"')
def step_session_in_styles_stage(context):
    context.manager = CopilotSessionManager(file_path=None, ttl=3600)
    context.session = context.manager.create_or_replace_session(
        user_id=1234, topic="Архитипы Юнга",
    )
    context.session.summary = "🎯 Концептуальный конфликт: Встреча с Тенью"
    context.session.stage = "styles"
    context.last_alert = None


@when('фотограф переключает стиль "{style_name}"')
def step_toggle_style(context, style_name):
    if style_name in context.session.selected_styles:
        context.session.selected_styles.remove(style_name)
    else:
        if len(context.session.selected_styles) >= 3:
            context.last_alert = "максимум 3 стиля"
        else:
            context.session.selected_styles.append(style_name)


@then("в сессии выбрано ровно 2 стиля")
def step_check_two_styles(context):
    assert len(context.session.selected_styles) == 2


@when("фотограф подтверждает выбор стилей")
def step_confirm_styles(context):
    if not context.session.selected_styles:
        context.last_alert = "хотя бы 1 стиль"
        return
    engine.append_styles_to_summary(context.session)
    context.session.stage = "manifesto"
    context.manager.save_session(context.session)


@then("концептуальное резюме дополняется выбранными стилями")
def step_summary_has_styles(context):
    assert "Выбранные стили синтеза:" in context.session.summary
    for s in context.session.selected_styles:
        assert s in context.session.summary


@then('сессия переходит на этап "manifesto"')
def step_check_manifesto_stage(context):
    assert context.session.stage == "manifesto"


@when('выбраны стили "{s1}", "{s2}", "{s3}"')
def step_select_three_styles(context, s1, s2, s3):
    context.session.selected_styles = [s1, s2, s3]


@when('фотограф пытается выбрать четвертый стиль "{s4}"')
def step_attempt_fourth_style(context, s4):
    if len(context.session.selected_styles) >= 3:
        context.last_alert = "максимум 3 стиля"
    else:
        context.session.selected_styles.append(s4)


@then("система отклоняет четвертый стиль с предупреждением")
def step_check_alert_three_styles(context):
    assert context.last_alert is not None
    assert "максимум 3 стиля" in context.last_alert


@then("в сессии остается ровно 3 выбранных стиля")
def step_check_stays_three_styles(context):
    assert len(context.session.selected_styles) == 3


@when("не выбран ни один стиль")
def step_no_styles_selected(context):
    context.session.selected_styles.clear()


@when("фотограф нажимает подтверждение стилей")
def step_press_confirm(context):
    if not context.session.selected_styles:
        context.last_alert = "хотя бы 1 стиль"
        return
    engine.append_styles_to_summary(context.session)
    context.session.stage = "manifesto"


@then("система сообщает о необходимости выбрать хотя бы 1 стиль")
def step_check_alert_at_least_one(context):
    assert context.last_alert is not None
    assert "хотя бы 1 стиль" in context.last_alert


@then('сессия остается на этапе "styles"')
def step_check_stays_styles(context):
    assert context.session.stage == "styles"


@then('стиль "{style_name}" добавлен в сессию')
def step_check_style_added(context, style_name):
    assert style_name in context.session.selected_styles


@when('фотограф повторно переключает стиль "{style_name}"')
def step_toggle_again(context, style_name):
    step_toggle_style(context, style_name)


@then('стиль "{style_name}" удаляется из сессии')
def step_check_style_removed(context, style_name):
    assert style_name not in context.session.selected_styles


@when('фотограф применяет пресет "{preset_key}"')
def step_apply_preset(context, preset_key):
    if preset_key == "preset_drama":
        context.session.selected_styles = ["Сюрреализм", "Экспрессионизм"]


@then('выбраны стили "Сюрреализм" и "Экспрессионизм"')
def step_check_drama_styles(context):
    assert context.session.selected_styles == ["Сюрреализм", "Экспрессионизм"]


@when('фотограф нажимает "Очистить"')
def step_click_clear(context):
    context.session.selected_styles.clear()


@then("список выбранных стилей становится пустым")
def step_check_empty_styles(context):
    assert len(context.session.selected_styles) == 0


@when('фотограф нажимает "Случайная синергия"')
def step_click_random_synergy(context):
    context.session.selected_styles = engine.get_random_style_synergy(count=3)


@then("система выбирает 3 уникальных гармоничных стиля")
def step_check_three_random_styles(context):
    assert len(context.session.selected_styles) == 3
    assert len(set(context.session.selected_styles)) == 3


@then("все выбранные стили входят в официальную палитру копайлота")
def step_check_all_in_palette(context):
    for s in context.session.selected_styles:
        assert s in engine.COPILOT_STYLES
