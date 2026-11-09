"""Шаги BDD для fuji_multiexposure.feature (Шаг S1 / ST-1: Мультиэкспозиция X-T4)."""

import asyncio
from pathlib import Path
from behave import given, then, when

import config
from handlers import copilot as hc
import services.fuji_multiexposure as fme
from services.copilot_session import CopilotSessionManager


class FakeUser:
    def __init__(self, uid=424242):
        self.id = uid


class FakeMessage:
    def __init__(self, uid=424242):
        self.from_user = FakeUser(uid)
        self.edits: list[str] = []
        self.answers: list[str] = []
        self.last_reply_markup = None

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)
        self.last_reply_markup = reply_markup

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append(text)
        self.last_reply_markup = reply_markup


class FakeCb:
    def __init__(self, uid=424242, data=""):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = FakeMessage(uid)
        self.answered: list[tuple[str | None, bool]] = []

    async def answer(self, text=None, show_alert=False):
        self.answered.append((text, show_alert))


@given("авторизованный фотограф в Telegram с активной сессией копайлота")
def step_auth_photographer(context):
    context.uid = 424242
    context.clean_file = Path("/tmp/behave_multiexposure_sessions.json")
    if context.clean_file.exists():
        context.clean_file.unlink()
    context.manager = CopilotSessionManager(context.clean_file)
    context.session = context.manager.create_or_replace_session(context.uid, "Тестовый проект")


@given('сессия содержит проект "{topic}" со стилем "{style}"')
def step_session_with_style(context, topic, style):
    context.session.topic = topic
    context.session.selected_styles = [{"name": style}]
    context.manager.save_session(context.session)


@given("у фотографа нет активной сессии копайлота")
def step_no_active_session(context):
    context.manager.clear_session(context.uid)
    assert context.manager.get_session(context.uid) is None


@given('сессия содержит проект "{topic}" без указания стилей')
def step_session_without_styles(context, topic):
    context.session.topic = topic
    context.session.selected_styles = []
    context.manager.save_session(context.session)


@given('сессия содержит проект "{topic}"')
def step_session_with_topic(context, topic):
    context.session.topic = topic
    context.manager.save_session(context.session)


@given("неавторизованный пользователь с ID {uid:d}")
def step_unauthorized_user(context, uid):
    context.unauth_uid = uid
    assert uid not in config.ALLOWED_IDS


@when("фотограф нажимает кнопку мультиэкспозиции в полевом ассистенте")
def step_click_multiexposure(context):
    cb = FakeCb(context.uid, data="cp_multiexposure")
    context.cb = cb
    original_get_mgr = hc.get_copilot_manager
    try:
        hc.get_copilot_manager = lambda: context.manager
        asyncio.run(hc.cb_copilot_multiexposure(cb))
    finally:
        hc.get_copilot_manager = original_get_mgr


@when("отправляется callback запрос мультиэкспозиции")
def step_send_multiexposure_cb(context):
    cb = FakeCb(context.uid, data="cp_multiexposure")
    context.cb = cb
    original_get_mgr = hc.get_copilot_manager
    try:
        hc.get_copilot_manager = lambda: context.manager
        asyncio.run(hc.cb_copilot_multiexposure(cb))
    finally:
        hc.get_copilot_manager = original_get_mgr


@when('фотограф запрашивает режим мультиэкспозиции "{mode}"')
def step_request_multiexposure_mode(context, mode):
    context.plan = fme.build_multiexposure_plan(context.session, blend_mode=mode)
    context.card = fme.format_multiexposure_card(context.plan)


@when("неавторизованный пользователь отправляет callback мультиэкспозиции")
def step_unauth_click_cb(context):
    cb = FakeCb(context.unauth_uid, data="cp_multiexposure")
    context.cb = cb
    called = False

    async def dummy_handler(c):
        nonlocal called
        called = True

    decorated = config.allowed_callback(dummy_handler)
    asyncio.run(decorated(cb))
    context.unauth_called = called


@when("формируется сценарий мультиэкспозиции с заказом {count:d} кадра")
@when("формируется сценарий мультиэкспозиции с заказом {count:d} кадров")
def step_build_multiexposure_frames(context, count):
    context.plan = fme.build_multiexposure_plan(context.session, frames_count=count)


@then('бот отображает карточку мультиэкспозиции с режимом "{mode_part}"')
def step_assert_card_mode(context, mode_part):
    assert len(context.cb.message.edits) == 1
    text = context.cb.message.edits[0]
    assert mode_part in text


@then("карточка мультиэкспозиции не содержит запрещенных тегов и комментариев")
def step_assert_card_html_safety(context):
    text = context.cb.message.edits[0]
    assert "<!--" not in text
    assert "-->" not in text
    assert "<script>" not in text
    assert "<div>" not in text
    assert "<p>" not in text


@then("клавиатура содержит кнопки всех четырех аппаратных режимов X-T4")
def step_assert_kb_has_all_modes(context):
    kb = context.cb.message.last_reply_markup
    assert kb is not None
    cbs = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "cp_me_blend:DARK" in cbs
    assert "cp_me_blend:BRIGHT" in cbs
    assert "cp_me_blend:AVERAGE" in cbs
    assert "cp_me_blend:ADDITIVE" in cbs
    assert "cp_me_surreal" in cbs


@then('бот отвечает алертом "{expected_alert}"')
def step_assert_alert_text(context, expected_alert):
    assert len(context.cb.answered) >= 1
    alert_text = context.cb.answered[0][0]
    assert expected_alert in str(alert_text)


@then("текст сообщения не изменяется")
def step_assert_no_message_edits(context):
    assert len(context.cb.message.edits) == 0


@then('движок нормализует режим к безопасному дефолту "{expected_mode}"')
def step_assert_normalized_mode(context, expected_mode):
    assert context.plan.blend_mode == expected_mode


@then("карточка формируется без ошибок")
def step_assert_card_generated(context):
    assert len(context.card) > 0
    assert "Параметры прошивки камеры 2.12" in context.card


@then("доступ отклоняется фильтром безопасности")
def step_assert_security_denied(context):
    assert context.unauth_called is False
    assert len(context.cb.answered) >= 1
    alert_text = context.cb.answered[0][0]
    assert "Нет доступа" in str(alert_text)


@then("количество слоев нормализуется ровно до {expected:d} кадров")
@then("количество слоев ограничивается ровно {expected:d} кадрами")
def step_assert_layers_count(context, expected):
    assert context.plan.frames_count == expected
    assert len(context.plan.layers) == expected
