"""Тесты services/json_parser.py — надёжный парсинг JSON от LLM.

Покрытие: чистый JSON, markdown-фенсы, шум вокруг JSON, невалидный
ввод, валидация типа, граничные значения (None, пустая строка,
вложенные объекты, множественные фенсы).
"""
from services.json_parser import (
    extract_json_from_text,
    extract_partial_json_array,
    safe_parse_llm_json,
)

# ─── extract_json_from_text: happy path ───


def test_clean_object():
    assert extract_json_from_text('{"a": 1}') == {"a": 1}


def test_clean_array():
    assert extract_json_from_text('[1, 2, 3]') == [1, 2, 3]


def test_markdown_fence_json():
    text = '```json\n{"entities": ["e1"]}\n```'
    assert extract_json_from_text(text) == {"entities": ["e1"]}


def test_markdown_fence_without_lang():
    text = '```\n["a"]\n```'
    assert extract_json_from_text(text) == ["a"]


def test_json_with_explanation_prefix():
    text = 'Вот результат: {"a": 1} Надеюсь, поможет!'
    assert extract_json_from_text(text) == {"a": 1}


def test_json_array_inside_noise():
    text = 'Ответ: ["факт 1", "факт 2"] — конец.'
    assert extract_json_from_text(text) == ["факт 1", "факт 2"]


def test_nested_object_inside_noise():
    text = 'prefix {"x": {"y": [1]}} suffix'
    assert extract_json_from_text(text) == {"x": {"y": [1]}}


# ─── extract_json_from_text: негативы ───

def test_none_input():
    assert extract_json_from_text(None) is None


def test_empty_string():
    assert extract_json_from_text("") is None


def test_whitespace_only():
    assert extract_json_from_text("   \n\t ") is None


def test_not_json_text():
    assert extract_json_from_text("Извините, не смог выполнить запрос") is None


def test_broken_json_in_fence():
    text = '```json\n{"a": \n```'
    assert extract_json_from_text(text) is None


def test_literal_object_with_inner_braces_ignored():
    """Фигурные скобки в прозе не считаются JSON."""
    assert extract_json_from_text("просто {слово} в тексте") is None


# ─── safe_parse_llm_json: типовая валидация ───

def test_type_validation_list_ok():
    assert safe_parse_llm_json('["a"]', expected_type=list) == ["a"]


def test_type_validation_list_fail():
    assert safe_parse_llm_json('{"a": 1}', expected_type=list) is None


def test_type_validation_dict_ok():
    assert safe_parse_llm_json('{"a": 1}', expected_type=dict) == {"a": 1}


def test_type_validation_none_expected():
    assert safe_parse_llm_json('{"a": 1}') == {"a": 1}


def test_type_validation_invalid_source():
    assert safe_parse_llm_json("нет json", expected_type=list) is None


def test_facts_from_fenced_array_via_safe_parse():
    text = '```json\n["факт 1"]\n```'
    assert safe_parse_llm_json(text, expected_type=list) == ["факт 1"]


# ─── Конвенция: нет синхронного IO в async-функциях (memory.py) ───

def test_no_sync_io_in_async_functions():
    import ast
    import pathlib

    src = pathlib.Path("services/memory.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    blocked = {"open", "json.load", "json.dump"}
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    func = child.func
                    if isinstance(func, ast.Name):
                        name = func.id
                    elif (
                        isinstance(func, ast.Attribute)
                        and isinstance(func.value, ast.Name)
                        and func.value.id == "json"
                    ):
                        name = f"json.{func.attr}"
                    else:
                        name = ""
                    assert name not in blocked, (
                        f"sync IO {name} в async {node.name} (строка {child.lineno})"
                    )


# ─── Control chars (реальный баг: qwen2.5 возвращает неэкранированные
#     \n внутри JSON-строк; строгий json.loads падает) ───

def test_raw_newline_inside_string_parses_with_strict_false():
    text = '{"ideas": [{"title": "A", "reason": "строка 1\nстрока 2"}]}'
    result = safe_parse_llm_json(text, expected_type=dict)
    assert result == {"ideas": [{"title": "A", "reason": "строка 1\nстрока 2"}]}


def test_raw_tab_inside_string():
    text = '["a\tb"]'
    assert safe_parse_llm_json(text, expected_type=list) == ["a\tb"]


def test_raw_newline_inside_fenced_json():
    text = '```json\n{"x": "a\nb"}\n```'
    assert safe_parse_llm_json(text, expected_type=dict) == {"x": "a\nb"}


def test_invalid_json_still_returns_none():
    assert safe_parse_llm_json('{"a": ', expected_type=dict) is None


# ─── «Перезапущенный» JSON (реальный баг: qwen2.5 посреди строки
#     вставляет китайский артефакт и начинает новый ```json-блок) ───

def test_json_restart_with_artifact_mid_string():
    """Первый блок обрезан на середине строки, второй — валидный."""
    text = (
        '```json\n'
        '{"ideas": [{"title": "A", "reason": "незаконч'
        '器误操作，继续生成JSON格式内容。\n'
        '```json\n'
        '{"ideas": [{"title": "B", "reason": "валидный"}]}\n'
        '```'
    )
    result = safe_parse_llm_json(text, expected_type=dict)
    assert result == {"ideas": [{"title": "B", "reason": "валидный"}]}


def test_json_restart_without_fences():
    """Артефакт посреди объекта без markdown-фенсов — raw_decode спасает."""
    text = (
        '{"ideas": [{"title": "A", "reason": "незаконч'
        '器误操作继续生成\n'
        '{"ideas": [{"title": "B", "reason": "валидный"}]}'
    )
    result = safe_parse_llm_json(text, expected_type=dict)
    assert result == {"ideas": [{"title": "B", "reason": "валидный"}]}


def test_json_restart_first_block_valid_preferred():
    """Если первый блок валиден целиком — берём его, а не хвост."""
    text = '{"a": 1} хвост {"b": 2}'
    assert extract_json_from_text(text) == {"a": 1}


def test_json_restart_artifact_keeps_full_surreal_ideas():
    """Полный сюрреалистичный ответ: первый блок обрезан, хвост валиден."""
    raw = (
        '```json\n'
        '{"ideas": [{"title": "Первый", "reason": "строка обрезана\nнезаконч'
        '器误操作，继续生成JSON格式内容。\n'
        '```json\n'
        '{"ideas": [{"title": "Второй", "reason": "ок"}]}\n'
        '```'
    )
    result = safe_parse_llm_json(raw, expected_type=dict)
    assert result["ideas"][0]["title"] == "Второй"


def test_multiple_broken_fences_returns_none():
    """Все фенсы битые и объектов нет — по-прежнему None."""
    text = '```json\n{"a": \n```\n```json\n{"b":\n```'
    assert extract_json_from_text(text) is None


# ─── extract_partial_json_array: спасение обрезанных массивов ───

def test_extract_partial_json_array_truncated():
    text = (
        '{\n  "projects": [\n'
        '    {"title": "П1", "manifesto": "Текст 1"},\n'
        '    {"title": "П2", "manifesto": "Текст 2"},\n'
        '    {"title": "П3", "manifesto": "Обрезанная с'
    )
    items = extract_partial_json_array(text, array_keys=("projects",))
    assert len(items) == 2
    assert items[0]["title"] == "П1"
    assert items[1]["title"] == "П2"


def test_extract_partial_json_array_with_token_notice():
    text = (
        '```json\n{\n  "projects": [\n'
        '    {"title": "П1", "manifesto": "Текст 1"}\n'
        '  ]\n}\n```\n\n'
        '⚠️ <i>(Ответ модели был обрезан из-за лимита токенов)</i>'
    )
    items = extract_partial_json_array(text, array_keys=("projects",))
    assert len(items) == 1
    assert items[0]["title"] == "П1"


def test_extract_partial_json_array_empty():
    assert extract_partial_json_array("") == []
    assert extract_partial_json_array(None) == []
    assert extract_partial_json_array("просто текст без json") == []


def test_extract_partial_json_array_root_list():
    text = '[\n  {"title": "Идея 1"},\n  {"title": "Идея 2"},\n  {"title": "Идея 3'
    items = extract_partial_json_array(text)
    assert len(items) == 2
    assert items[0]["title"] == "Идея 1"
    assert items[1]["title"] == "Идея 2"


def test_repair_llm_json_unescaped_shutter_quote():
    """Реальный баг qwen2.5:7b: неэкранированная кавычка секунд '1/6\"' внутри JSON."""
    raw = (
        '{\n'
        '  "projects": [\n'
        '    {\n'
        '      "title": "Quantum",\n'
        '      "triad": {\n'
        '        "narrative": {"role": "narrative", "style": "Сюрреализм", '
        '"traits": "Онейрический сюжет, деконтекстуализация"}\n'
        '      },\n'
        '      "camera_setup": {\n'
        '        "Выдержка": "1/6"",\n'
        '        "Диафрагма": "f/5.6"\n'
        '      }\n'
        '    }\n'
        '  ]\n'
        '}'
    )
    parsed = safe_parse_llm_json(raw, expected_type=dict)
    assert parsed is not None
    assert "projects" in parsed
    assert parsed["projects"][0]["title"] == "Quantum"
    assert parsed["projects"][0]["camera_setup"]["Выдержка"] == '1/6"'


def test_repair_llm_json_inner_prose_quotes_and_trailing_commas():
    """Неэкранированные кавычки в русском тексте и висячие запятые перед } / ]."""
    raw = (
        '{\n'
        '  "projects": [\n'
        '    {\n'
        '      "title": "Осенний сплин",\n'
        '      "scene_description": "Парк в дождь, эффект "тумана", тишина и покой",\n'
        '    },\n'
        '  ],\n'
        '}'
    )
    parsed = safe_parse_llm_json(raw, expected_type=dict)
    assert parsed is not None
    assert parsed["projects"][0]["title"] == "Осенний сплин"
    assert 'эффект "тумана", тишина' in parsed["projects"][0]["scene_description"]


def test_salvage_truncated_json_object_mid_first_project():
    """Если первый проект оборвался на 'ligh, salvage_truncated_json_object спасает его."""
    from services.json_parser import salvage_truncated_json_object

    raw = (
        '{\n'
        '  "projects": [\n'
        '    {\n'
        '      "title": "Quantum",\n'
        '      "triad": {\n'
        '        "narrative": {"role": "narrative", "style": "Сюрреализм", '
        '"traits": "Онейрический сюжет, деконтекстуализация"},\n'
        '        "ligh'
    )
    salvaged = salvage_truncated_json_object(raw, array_keys=("projects",))
    assert len(salvaged) == 1
    assert salvaged[0]["title"] == "Quantum"
    assert salvaged[0]["triad"]["narrative"]["style"] == "Сюрреализм"
