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
_OBJECT_START_RE = re.compile(r"[{\[]")


def _loads(text: str):
    """json.loads со strict=False: допускает неэкранированные control chars
    внутри строк (частая ошибка локальных LLM, например qwen2.5)."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(text, strict=False)


def extract_json_from_text(text: str):
    """Извлекает JSON (dict/list) из текста LLM; None — если не найден."""
    if not text:
        return None
    text = text.strip()

    try:
        return _loads(text)
    except json.JSONDecodeError:
        pass

    for match in _FENCE_RE.finditer(text):
        try:
            return _loads(match.group(1).strip())
        except json.JSONDecodeError:
            continue

    obj = _OBJECT_RE.search(text)
    if obj:
        try:
            return _loads(obj.group(1))
        except json.JSONDecodeError:
            pass

    # Финальный рубеж: модель «перезапустила» JSON посреди строки
    # (локальные LLM, например qwen2.5, вставляют артефакт и продолжают
    # новый блок). Пробуем raw_decode на каждой позиции '{'/'[' и берём
    # первый объект, который парсится целиком.
    decoder = json.JSONDecoder(strict=False)
    for match in _OBJECT_START_RE.finditer(text):
        try:
            result, _ = decoder.raw_decode(text, match.start())
        except json.JSONDecodeError:
            continue
        return result

    return None


def safe_parse_llm_json(text: str, expected_type=None):
    """Безопасный парсинг JSON от LLM с валидацией типа результата."""
    result = extract_json_from_text(text)
    if result is None:
        return None
    if expected_type is not None and not isinstance(result, expected_type):
        return None
    return result
