"""Unit-тесты для services.brainstorm — генерация идей (штурм).

Паттерн: happy path + негативные сценарии + граничные значения (BVA).
Модель/телеграм не вызываются: тестируется чистый пайплайн
(контекст → промпт → парсинг → форматирование).
"""

import asyncio

import pytest

from services import brainstorm as bs
from services.apple_notes import AppleNotesError


def run_async(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class FakeMCP:
    """Фейковый MCP-клиент с настраиваемыми ответами/ошибками."""

    def __init__(self, results=None, errors=None):
        self.results = results or {}
        self.errors = errors or {}

    async def call_tool(self, name, args):
        if name in self.errors:
            raise self.errors[name]
        return self.results.get(name, "{}")


# ─── parse_ideas: happy path ───

def test_parse_ideas_happy():
    raw = (
        '{"ideas": ['
        '{"title": "Идея 1", "reason": "потому что", "steps": "шаг 1"},'
        '{"title": "Идея 2"}]}'
    )
    ideas = bs.parse_ideas(raw)
    assert len(ideas) == 2
    assert ideas[0]["title"] == "Идея 1"
    assert ideas[0]["reason"] == "потому что"
    assert ideas[0]["steps"] == "шаг 1"
    assert ideas[1]["reason"] == ""
    assert ideas[1]["steps"] == ""


def test_parse_ideas_json_fence():
    raw = '```json\n{"ideas": [{"title": "Идея"}]}\n```'
    ideas = bs.parse_ideas(raw)
    assert ideas[0]["title"] == "Идея"


# ─── parse_ideas: негативы ───

def test_parse_ideas_empty():
    with pytest.raises(ValueError, match="Пустой ответ"):
        bs.parse_ideas("")


def test_parse_ideas_not_json():
    with pytest.raises(ValueError, match="не является JSON"):
        bs.parse_ideas("просто текст без json")


def test_parse_ideas_missing_ideas_key():
    with pytest.raises(ValueError, match="нет массива ideas"):
        bs.parse_ideas('{"title": "не та структура"}')


def test_parse_ideas_invalid_items_only():
    with pytest.raises(ValueError, match="Нет валидных идей"):
        bs.parse_ideas('{"ideas": [{"title": ""}, {"reason": "без названия"}, 42]}')


def test_parse_ideas_partial_invalid_filtered():
    raw = '{"ideas": [{"title": "Валидная"}, {"title": ""}, "мусор"]}'
    ideas = bs.parse_ideas(raw)
    assert len(ideas) == 1
    assert ideas[0]["title"] == "Валидная"


# ─── parse_ideas: границы (BVA) ───

def test_parse_ideas_more_than_max_truncated():
    import json

    items = [{"title": f"Идея {i}"} for i in range(1, 10)]
    ideas = bs.parse_ideas(json.dumps({"ideas": items}))
    assert len(ideas) == bs.MAX_IDEAS  # 7


def test_parse_ideas_title_boundary():
    title_80 = "т" * 80
    title_81 = "т" * 81
    assert bs.parse_ideas(f'{{"ideas": [{{"title": "{title_80}"}}]}}')[0]["title"] == title_80
    assert bs.parse_ideas(f'{{"ideas": [{{"title": "{title_81}"}}]}}')[0]["title"] == title_80


# ─── build_storm_prompt ───

def test_build_storm_prompt_includes_topic_and_blocks():
    ctx = {"notes": "заметка", "palace": "ящик", "kg": "факт"}
    prompt = bs.build_storm_prompt("Фото-проект", ctx)
    assert "Тема штурма: Фото-проект" in prompt
    assert "[Заметки Apple Notes]\nзаметка" in prompt
    assert "[Записи дворца]\nящик" in prompt
    assert "[Факты графа знаний]\nфакт" in prompt


def test_build_storm_prompt_empty_context_fallback():
    prompt = bs.build_storm_prompt("Тема", {"notes": "", "palace": "", "kg": ""})
    assert "Контекст из базы знаний отсутствует" in prompt


def test_build_context_block_empty_returns_empty():
    assert bs._build_context_block("X", "  ") == ""
    assert bs._build_context_block("X", "\n\t") == ""


# ─── collect_context ───

@pytest.fixture
def mock_sources(monkeypatch):
    """Мокает search_notes и get_mcp."""

    def _set(notes=None, notes_error=False, mcp_errors=None):
        def _notes(*a, **k):
            if notes_error:
                raise AppleNotesError("TCC denied")
            return notes or []

        monkeypatch.setattr(bs, "search_notes", _notes)
        fake = FakeMCP(
            results={
                "mempalace_search": "{\"results\": []}",
                "mempalace_kg_query": "{\"facts\": []}",
            },
            errors=mcp_errors or {},
        )
        monkeypatch.setattr(bs, "get_mcp", lambda: fake)

    return _set


def test_collect_context_all_sources_ok(mock_sources):
    mock_sources(notes=[{"name": "Заметка", "body": "тело"}])
    ctx = run_async(bs.collect_context("тема"))
    assert "Заметка" in ctx["notes"]
    assert "results" in ctx["palace"]
    assert "facts" in ctx["kg"]


def test_collect_context_notes_error_is_tolerated(mock_sources):
    mock_sources(notes_error=True)
    ctx = run_async(bs.collect_context("тема"))
    assert ctx["notes"] == ""
    assert ctx["palace"]
    assert ctx["kg"]


def test_collect_context_mcp_error_is_tolerated(mock_sources):
    mock_sources(mcp_errors={
        "mempalace_search": RuntimeError("mcp down"),
        "mempalace_kg_query": RuntimeError("mcp down"),
    })
    ctx = run_async(bs.collect_context("тема"))
    assert ctx["notes"] == ""
    assert ctx["palace"] == ""
    assert ctx["kg"] == ""


# ─── Форматирование ───

def test_format_idea():
    text = bs.format_idea(1, {"title": "Т", "reason": "Р", "steps": "Ш"})
    assert "💡 1." in text
    assert "<b>Т</b>" in text
    assert "Р" in text
    assert "Ш" in text


def test_format_idea_without_reason_steps():
    text = bs.format_idea(3, {"title": "Т", "reason": "", "steps": ""})
    assert "Почему" not in text
    assert "Шаги" not in text


def test_format_ideas_text_has_topic_and_numbering():
    ideas = [{"title": "A", "reason": "", "steps": ""},
             {"title": "B", "reason": "", "steps": ""}]
    text = bs.format_ideas_text("Тема", ideas)
    assert "🧠" in text and "Тема" in text
    assert "1." in text and "2." in text


def test_ideas_to_text():
    ideas = [
        {"title": "A", "reason": "потому", "steps": "начать"},
        {"title": "B", "reason": "", "steps": ""},
    ]
    text = bs.ideas_to_text(ideas)
    assert "1. A — потому" in text
    assert "2. B" in text


# маленький хелпер для async-тестов (модуль импортирован без asyncio.run в тестах)
