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


def _is_closing_quote(
    text: str,
    quote_idx: int,
    stack: list[str],
    expecting_colon: bool,
    string_has_newline: bool = False,
) -> bool:
    """Определяет, является ли кавычка закрывающей для JSON-строки или внутренней."""
    if string_has_newline:
        return True

    n = len(text)
    line_end = text.find("\n", quote_idx + 1)
    if line_end == -1:
        line_end = n
    # Если до конца текущей строки больше нет кавычек, эта кавычка точно закрывающая
    if '"' not in text[quote_idx + 1:line_end]:
        return True

    j = quote_idx + 1
    while j < n and text[j] in " \t":
        j += 1
    k = j
    while k < n and text[k] in " \t\r\n":
        k += 1

    if expecting_colon:
        if k >= n:
            return True
        if text[k] != ":":
            return False
        m = k + 1
        while m < n and text[m] in " \t\r\n":
            m += 1
        if m >= n:
            return True
        return (
            text[m] in '"{[]-0123456789'
            or text.startswith(("true", "false", "null"), m)
        )

    if k >= n:
        return True
    if text[k] in "}]":
        return True
    if text[k] == ",":
        m = k + 1
        while m < n and text[m] in " \t\r\n":
            m += 1
        if m >= n:
            return True
        if stack and stack[-1] == "{":
            if text[m] == "}":
                return True
            if text[m] == '"':
                if "\n" in text[k:m]:
                    return True
                q = m + 1
                while q < n:
                    if text[q] == "\\":
                        q += 2
                        continue
                    if text[q] == '"':
                        r = q + 1
                        while r < n and text[r] in " \t":
                            r += 1
                        return r < n and text[r] == ":"
                    if text[q] == "\n":
                        break
                    q += 1
            return False
        if stack and stack[-1] == "[":
            return (
                text[m] in '"{[]-0123456789'
                or text.startswith(("true", "false", "null"), m)
            )
        return True

    # Пропущенная запятая в конце строки перед следующим ключом/объектом
    if j < k and text[k] in '"{[':
        return True

    return False


def _repair_llm_json(text: str) -> str:
    """Исправляет частые синтаксические ошибки JSON от локальных LLM:
    - неэкранированные кавычки внутри значений (например, "1/6"", "эффект "тумана"")
    - висячие запятые перед } или ]
    - пропущенные запятые между полями на соседних строках
    """
    if not text:
        return text

    out: list[str] = []
    n = len(text)
    in_string = False
    string_has_newline = False
    escaped = False
    stack: list[str] = []
    expecting_colon = False
    after_value = False

    i = 0
    while i < n:
        ch = text[i]
        if in_string:
            if escaped:
                out.append(ch)
                escaped = False
            elif ch == "\\":
                out.append(ch)
                escaped = True
            elif ch == "\n":
                out.append(ch)
                string_has_newline = True
            elif ch == '"':
                if _is_closing_quote(
                    text, i, stack, expecting_colon, string_has_newline
                ):
                    out.append('"')
                    in_string = False
                    string_has_newline = False
                    if not expecting_colon:
                        after_value = bool(stack)
                else:
                    out.append('\\"')
            else:
                out.append(ch)
            i += 1
            continue

        if ch in " \t\r\n":
            out.append(ch)
            i += 1
            continue

        if ch == "{":
            if after_value:
                out.append(",")
            out.append("{")
            stack.append("{")
            expecting_colon = True
            after_value = False
        elif ch == "[":
            if after_value:
                out.append(",")
            out.append("[")
            stack.append("[")
            expecting_colon = False
            after_value = False
        elif ch == "}":
            if stack and stack[-1] == "{":
                stack.pop()
            expecting_colon = False
            after_value = bool(stack)
            out.append("}")
        elif ch == "]":
            if stack and stack[-1] == "[":
                stack.pop()
            expecting_colon = False
            after_value = bool(stack)
            out.append("]")
        elif ch == ":":
            out.append(":")
            expecting_colon = False
            after_value = False
        elif ch == ",":
            k = i + 1
            while k < n and text[k] in " \t\r\n":
                k += 1
            if k < n and text[k] in "}]":
                # Пропускаем висячую запятую перед } или ]
                after_value = False
            else:
                out.append(",")
                expecting_colon = bool(stack and stack[-1] == "{")
                after_value = False
        elif ch == '"':
            if after_value:
                out.append(",")
                expecting_colon = bool(stack and stack[-1] == "{")
                after_value = False
            out.append('"')
            in_string = True
            string_has_newline = False
        else:
            out.append(ch)
            if not expecting_colon and (i + 1 >= n or text[i + 1] in " \t\r\n,}]"):
                after_value = bool(stack)
        i += 1

    return "".join(out)


def extract_json_from_text(text: str):
    """Извлекает JSON (dict/list) из текста LLM; None — если не найден."""
    if not text:
        return None
    text = text.strip()

    for candidate in (text, _repair_llm_json(text)):
        try:
            return _loads(candidate)
        except json.JSONDecodeError:
            pass

    for match in _FENCE_RE.finditer(text):
        block = match.group(1).strip()
        for candidate in (block, _repair_llm_json(block)):
            try:
                return _loads(candidate)
            except json.JSONDecodeError:
                continue

    obj = _OBJECT_RE.search(text)
    if obj:
        raw_obj = obj.group(1)
        for candidate in (raw_obj, _repair_llm_json(raw_obj)):
            try:
                return _loads(candidate)
            except json.JSONDecodeError:
                pass

    # Финальный рубеж: модель «перезапустила» JSON посреди строки
    # (локальные LLM, например qwen2.5, вставляют артефакт и продолжают
    # новый блок). Пробуем raw_decode на каждой позиции '{'/'[' и берём
    # первый объект, который парсится целиком.
    decoder = json.JSONDecoder(strict=False)
    for source in (text, _repair_llm_json(text)):
        for match in _OBJECT_START_RE.finditer(source):
            try:
                result, _ = decoder.raw_decode(source, match.start())
            except json.JSONDecodeError:
                continue
            return result

    return None


def _extract_objects_from_array_text(
    cleaned: str,
    array_keys: tuple[str, ...],
) -> list[dict]:
    """Вспомогательный проход raw_decode по элементам массива."""
    decoder = json.JSONDecoder(strict=False)
    results: list[dict] = []

    start_bracket = -1
    for key in array_keys:
        idx = cleaned.find(f'"{key}"')
        if idx != -1:
            bracket_idx = cleaned.find("[", idx)
            if bracket_idx != -1:
                start_bracket = bracket_idx
                break

    if start_bracket == -1:
        start_bracket = cleaned.find("[")

    if start_bracket != -1:
        pos = start_bracket + 1
        length = len(cleaned)
        while pos < length:
            while pos < length and cleaned[pos] in " \t\r\n,":
                pos += 1
            if pos >= length or cleaned[pos] == "]":
                break
            if cleaned[pos] == "{":
                try:
                    obj, end_pos = decoder.raw_decode(cleaned, pos)
                    if isinstance(obj, dict):
                        results.append(obj)
                    pos = end_pos
                except json.JSONDecodeError:
                    break
            else:
                pos += 1

    return results


def extract_partial_json_array(
    text: str,
    array_keys: tuple[str, ...] = ("projects", "ideas"),
) -> list[dict]:
    """Извлекает завершённые словари из частично обрезанного JSON массива.

    Если ответ модели был обрезан по лимиту токенов посреди генерации,
    стандартный JSONDecoder ломается на всём документе. Данная функция
    находит массив по ключам (или корневой список [) и поочередно
    извлекает все полностью закрытые объекты {...}, игнорируя недописанный хвост.
    """
    if not text:
        return []

    cleaned = re.sub(r"⚠️.*$", "", text, flags=re.DOTALL).strip()
    cleaned = re.sub(r"```+$", "", cleaned).strip()

    results = _extract_objects_from_array_text(cleaned, array_keys)
    if results:
        return results

    repaired = _repair_llm_json(cleaned)
    if repaired != cleaned:
        return _extract_objects_from_array_text(repaired, array_keys)
    return []


def salvage_truncated_json_object(
    text: str,
    array_keys: tuple[str, ...] = ("projects", "ideas"),
) -> list[dict]:
    """Спасает первый незакрытый объект из массива, если генерация оборвалась внутри него."""
    if not text:
        return []

    cleaned = re.sub(r"⚠️.*$", "", text, flags=re.DOTALL).strip()
    cleaned = re.sub(r"```+$", "", cleaned).strip()

    start_bracket = -1
    for key in array_keys:
        idx = cleaned.find(f'"{key}"')
        if idx != -1:
            bracket_idx = cleaned.find("[", idx)
            if bracket_idx != -1:
                start_bracket = bracket_idx
                break

    if start_bracket == -1:
        start_bracket = cleaned.find("[")

    first_brace = cleaned.find("{", start_bracket + 1 if start_bracket != -1 else 0)
    if first_brace == -1:
        return []

    fragment = _repair_llm_json(cleaned[first_brace:])
    in_string = False
    escaped = False
    stack: list[str] = []
    expecting_colon = False
    cut_points: list[tuple[int, list[str]]] = []

    for i, ch in enumerate(fragment):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
                if not expecting_colon and stack:
                    cut_points.append((i + 1, list(stack)))
            continue

        if ch == "{":
            stack.append("{")
            expecting_colon = True
        elif ch == "[":
            stack.append("[")
            expecting_colon = False
        elif ch == "}":
            if stack and stack[-1] == "{":
                stack.pop()
            expecting_colon = False
            if stack:
                cut_points.append((i + 1, list(stack)))
        elif ch == "]":
            if stack and stack[-1] == "[":
                stack.pop()
            expecting_colon = False
            if stack:
                cut_points.append((i + 1, list(stack)))
        elif ch == ":":
            expecting_colon = False
        elif ch == ",":
            if stack:
                cut_points.append((i, list(stack)))
            expecting_colon = bool(stack and stack[-1] == "{")
        elif ch == '"':
            in_string = True

    # Попытка 1: если оборвалось внутри строкового значения — закрыть строку и скобки
    if in_string and not expecting_colon and stack:
        closers = '"' + "".join("}" if c == "{" else "]" for c in reversed(stack))
        try:
            obj = _loads(fragment + closers)
            if isinstance(obj, dict) and obj:
                return [obj]
        except json.JSONDecodeError:
            pass

    # Попытка 2: откат к последней завершённой паре ключ-значение / объекту
    for pos, saved_stack in reversed(cut_points):
        prefix = fragment[:pos].rstrip(" \t\r\n,")
        closers = "".join("}" if c == "{" else "]" for c in reversed(saved_stack))
        try:
            obj = _loads(prefix + closers)
            if isinstance(obj, dict) and obj:
                return [obj]
        except json.JSONDecodeError:
            continue

    return []


def safe_parse_llm_json(text: str, expected_type=None):
    """Безопасный парсинг JSON от LLM с валидацией типа результата."""
    result = extract_json_from_text(text)
    if result is None:
        return None
    if expected_type is not None and not isinstance(result, expected_type):
        return None
    return result
