"""services/json_parser.py — надёжный парсинг JSON от LLM.

Объединяет паттерны, уже существующие в проекте (brainstorm.parse_ideas,
handlers/reminder._clean_json): принимает как чистый JSON, так и JSON
в markdown-фенсах, с текстовым префиксом/шумом вокруг. Возвращает None
при невалидном JSON — вызывающий код решает, что делать.
"""

import json
import re

_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_OBJECT_RE = re.compile(r"(\{[\s\S]*\}|\[[\s\S]*\])")


def extract_json_from_text(text: str):
    """Извлекает JSON (dict/list) из текста LLM; None — если не найден."""
    if not text:
        return None
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fence = _FENCE_RE.search(text)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except json.JSONDecodeError:
            pass

    obj = _OBJECT_RE.search(text)
    if obj:
        try:
            return json.loads(obj.group(1))
        except json.JSONDecodeError:
            pass

    return None


def safe_parse_llm_json(text: str, expected_type=None):
    """Безопасный парсинг JSON от LLM с валидацией типа результата."""
    result = extract_json_from_text(text)
    if result is None:
        return None
    if expected_type is not None and not isinstance(result, expected_type):
        return None
    return result
