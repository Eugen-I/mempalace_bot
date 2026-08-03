"""Шаги BDD для features/palace_save_result.feature."""
from behave import given, then, when

from handlers.palace.save import _format_save_result

WING = "проекты"
ROOM = "inbox"


@given('ответ MCP на сохранение: success true с drawer_id')
def step_success_drawer(context):
    context.raw = '{"success": true, "drawer_id": "drawer_proekty_inbox_abc123"}'


@given('ответ MCP на сохранение: success false')
def step_failure(context):
    context.raw = '{"success": false, "error": "room not found"}'


@given('ответ MCP — не JSON')
def step_invalid_json(context):
    context.raw = "not a json {"


@given('ответ MCP: success true с «{injected}» в drawer_id')
def step_injection(context, injected):
    context.raw = '{"success": true, "drawer_id": "pre%spost"}' % injected


@when('форматируется результат сохранения в крыло «{wing}» и комнату «{room}»')
def step_format(context, wing, room):
    context.result = _format_save_result(context.raw, wing, room)


@then('текст содержит «{prefix}»')
def step_contains(context, prefix):
    assert context.result.startswith(prefix), context.result

@then('в тексте есть drawer_id внутри тега <code>')
def step_has_code_drawer(context):
    assert "<code>drawer_proekty_inbox_abc123</code>" in context.result


@then('в тексте есть описание ошибки')
def step_has_error_detail(context):
    assert "room not found" in context.result


@then('в тексте нет фигурных скобок')
def step_no_braces(context):
    assert "{" not in context.result and "}" not in context.result


@then('в тексте нет тега <{tag}>')
def step_no_tag(context, tag):
    assert "<%s>" % tag not in context.result
