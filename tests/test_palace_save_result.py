"""Тесты Шага 2 ТЗ: форматирование результата сохранения (баг — сырой JSON).

Баг: cb_save_confirm_execute показывал ответ MCP как есть (сырой JSON).
Теперь _format_save_result парсит ответ: успех → заголовок + drawer_id,
success:false → ошибка с деталью, невалидный JSON → только заголовок.
"""
from handlers.palace.save import _format_save_result

WING = "проекты"
ROOM = "inbox"


def test_success_returns_header_and_drawer_id():
    raw = '{"success": true, "drawer_id": "drawer_proekty_inbox_abc123"}'
    text = _format_save_result(raw, WING, ROOM)
    assert "✅ Сохранено в" in text
    assert "<b>проекты/inbox</b>" in text
    assert "drawer_proekty_inbox_abc123" in text
    assert "<code>" in text


def test_success_without_drawer_id_returns_header_only():
    raw = '{"success": true}'
    text = _format_save_result(raw, WING, ROOM)
    assert "✅ Сохранено в" in text
    assert "<code>" not in text


def test_success_empty_dict_returns_header_only():
    raw = "{}"
    text = _format_save_result(raw, WING, ROOM)
    assert "✅ Сохранено в" in text


def test_failure_returns_error_with_detail():
    raw = '{"success": false, "error": "room not found"}'
    text = _format_save_result(raw, WING, ROOM)
    assert "❌ Ошибка сохранения" in text
    assert "room not found" in text


def test_failure_without_error_uses_default_message():
    raw = '{"success": false}'
    text = _format_save_result(raw, WING, ROOM)
    assert "❌ Ошибка сохранения" in text
    assert "не удалось сохранить" in text


def test_invalid_json_returns_header_only():
    text = _format_save_result("not a json {", WING, ROOM)
    assert "✅ Сохранено в" in text
    assert "<code>" not in text


def test_empty_raw_returns_header_only():
    text = _format_save_result("", WING, ROOM)
    assert "✅ Сохранено в" in text


def test_none_raw_returns_header_only():
    text = _format_save_result(None, WING, ROOM)
    assert "✅ Сохранено в" in text


def test_html_injected_names_are_escaped():
    text = _format_save_result('{"success": true, "drawer_id": "a<b>c"}', "<x>", "y&")
    assert "<x>" not in text
    assert "&lt;x&gt;" in text
    assert "a&lt;b&gt;c" in text


def test_html_injected_error_detail_is_escaped():
    raw = '{"success": false, "error": "bad <script>alert(1)</script>"}'
    text = _format_save_result(raw, WING, ROOM)
    assert "<script>" not in text
    assert "&lt;script&gt;" in text


def test_real_response_format():
    raw = (
        '{\n  "success": true,\n  "drawer_id": "drawer_test_inbox_3ae85ef0",\n'
        '  "wing": "test",\n  "room": "inbox"\n}'
    )
    text = _format_save_result(raw, "test", "inbox")
    assert "✅ Сохранено в" in text
    assert "drawer_test_inbox_3ae85ef0" in text
