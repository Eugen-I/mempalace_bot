"""Unit-тесты для services.brainstorm — генерация идей (штурм).

Паттерн: happy path + негативные сценарии + граничные значения (BVA).
Модель/телеграм не вызываются: тестируется чистый пайплайн
(контекст → промпт → парсинг → форматирование).
"""

import asyncio
import json

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


# ─── parse_ideas: сюрреалистичный режим (require_camera_setup) ───

def test_parse_ideas_surreal_happy():
    raw = (
        '{"ideas": ['
        '{"title": "Идея 1", "reason": "образ", "camera_setup": "ACROS, R+9", '
        '"steps": "шаг"}]}'
    )
    ideas = bs.parse_ideas(raw, require_camera_setup=True)
    assert len(ideas) == 1
    assert ideas[0]["camera_setup"] == "ACROS, R+9"


def test_parse_ideas_surreal_rejects_idea_without_camera_setup():
    raw = (
        '{"ideas": ['
        '{"title": "Без настроек", "reason": "r"},'
        '{"title": "С настройками", "camera_setup": "Мультиэкспозиция"}]}'
    )
    ideas = bs.parse_ideas(raw, require_camera_setup=True)
    assert len(ideas) == 1
    assert ideas[0]["title"] == "С настройками"


def test_parse_ideas_surreal_rejects_empty_camera_setup():
    raw = '{"ideas": [{"title": "Пустая строка", "camera_setup": "   "}]}'
    with pytest.raises(ValueError, match="Нет валидных идей"):
        bs.parse_ideas(raw, require_camera_setup=True)


def test_parse_ideas_surreal_all_rejected_raises():
    raw = '{"ideas": [{"title": "A"}, {"title": "B", "camera_setup": ""}]}'
    with pytest.raises(ValueError, match="Нет валидных идей"):
        bs.parse_ideas(raw, require_camera_setup=True)


def test_parse_ideas_standard_keeps_idea_without_camera_setup():
    """Обычный штурм не требует camera_setup — идеи без него валидны."""
    ideas = bs.parse_ideas('{"ideas": [{"title": "Обычная идея"}]}')
    assert len(ideas) == 1
    assert ideas[0]["camera_setup"] == ""


# ─── camera_setup: проверка ключевых параметров (keywords) ───

def _surreal_setup_idea(camera_setup):
    return (
        '{"ideas": ['
        + json.dumps({"title": "Идея", "reason": "р", "camera_setup": camera_setup})
        + ']}'
    )


def test_parse_ideas_keywords_accepts_film_simulation():
    ideas = bs.parse_ideas(
        _surreal_setup_idea("Имитация плёнки ACROS, тени -2"),
        require_camera_setup=True, require_camera_keywords=True,
    )
    assert len(ideas) == 1


def test_parse_ideas_keywords_accepts_tonal_curve():
    ideas = bs.parse_ideas(
        _surreal_setup_idea("Кривая: Подсветка +2, тень -2, Clarity +3"),
        require_camera_keywords=True,
    )
    assert len(ideas) == 1


def test_parse_ideas_keywords_rejects_slogan_only():
    """«Сделай сюрреалистично» без параметров камеры — отбраковывается."""
    with pytest.raises(ValueError, match="Нет валидных идей"):
        bs.parse_ideas(
            _surreal_setup_idea("Усилить сюрреализм магией"),
            require_camera_keywords=True,
        )


def test_parse_ideas_keywords_rejects_multi_exposure_only():
    """Одна мультиэкспозиция без параметров камеры — недостаточно."""
    with pytest.raises(ValueError, match="Нет валидных идей"):
        bs.parse_ideas(
            _surreal_setup_idea("Мультиэкспозиция"),
            require_camera_keywords=True,
        )


def test_parse_ideas_keywords_keeps_idea_without_setup_on_standard():
    """Без флага keywords обычная проверка camera_setup не меняется."""
    ideas = bs.parse_ideas(_surreal_setup_idea("Только текст"))
    assert len(ideas) == 1


def test_camera_setup_has_parameters_variants():
    assert bs._camera_setup_has_parameters("WB Shift R+9")
    assert bs._camera_setup_has_parameters("Эффект зерна: сильный")
    assert bs._camera_setup_has_parameters("баланс белого 3200K")
    assert not bs._camera_setup_has_parameters("")
    assert not bs._camera_setup_has_parameters("сюрреализм, свет, движение")


def test_camera_setup_keywords_accept_new_prompt_vocabulary():
    """Маркеры новых требований промпта: монохром, ACROS, экспозамер и т.д."""
    assert bs._camera_setup_has_parameters("Монохромный режим ACROS R, фильтр +R")
    assert bs._camera_setup_has_parameters("ACROS +Ye, зерно крупное")
    assert bs._camera_setup_has_parameters("Экспозамер: точечный")
    assert bs._camera_setup_has_parameters("Диафрагма f/8, выдержка 1/1000")
    assert not bs._camera_setup_has_parameters("ночь, туман, полёт")
    assert not bs._camera_setup_has_parameters("black and white, dream")


def test_parse_ideas_keywords_accepts_monochrome_only_setup():
    """Идея в монохромном режиме без слова «имитация плёнки» — валидна."""
    ideas = bs.parse_ideas(
        _surreal_setup_idea("ACROS, фильтр +G, тень -3, баланс белого 5500K"),
        require_camera_setup=True, require_camera_keywords=True,
    )
    assert len(ideas) == 1


def test_surreal_prompt_includes_new_required_fields():
    p = bs.SURREAL_STORM_SYSTEM_PROMPT
    assert "WB Shift" in p and "−9 до +9" in p
    assert "экспозамер" in p.lower()
    assert "флуоресцентный" in p.lower()
    assert "диафрагм" in p.lower() and "выдержк" in p.lower() and "iso" in p.lower()
    assert "монохромного режима" in p and "WC/MG" in p
    assert "Резкость" in p and "Мелкое/Крупное" in p


def test_parse_ideas_non_string_camera_setup_rejected():
    raw = '{"ideas": [{"title": "T", "camera_setup": 42}]}'
    with pytest.raises(ValueError, match="Нет валидных идей"):
        bs.parse_ideas(raw, require_camera_setup=True)


def test_parse_ideas_dict_camera_setup_and_list_steps():
    """qwen2.5:7b возвращает camera_setup объектом и steps массивом —
    оба варианта нормализуются в читаемый текст и проходят валидацию."""
    raw = ('{"ideas": [{"title": "Тень Юнга", "reason": "р", "camera_setup": '
           '{"имитация плёнки": "Classic Chrome", "Тон.кривая (Подсветка/Тень)": "-2 / -1", '
           '"Эффект зерна": "Слабый+Мелкое"}, '
           '"steps": ["Шаг 1", "Шаг 2"]}]}')
    ideas = bs.parse_ideas(
        raw, require_camera_setup=True, require_camera_keywords=True,
    )
    assert len(ideas) == 1
    assert ideas[0]["title"] == "Тень Юнга"
    assert "Classic Chrome" in ideas[0]["camera_setup"]
    assert "Эффект зерна: Слабый+Мелкое" in ideas[0]["camera_setup"]
    assert ideas[0]["steps"] == "Шаг 1\nШаг 2"


def test_parse_ideas_dict_camera_setup_without_keywords_rejected():
    """Объект без ключевых параметров (только приём съёмки) — отбраковывается."""
    raw = ('{"ideas": [{"title": "Т", "camera_setup": '
           '{"приём": "Мультиэкспозиция"}}]}')
    with pytest.raises(ValueError, match="Нет валидных идей"):
        bs.parse_ideas(
            raw, require_camera_setup=True, require_camera_keywords=True,
        )


def test_parse_ideas_dict_camera_setup_without_keywords_kept_on_standard():
    """Обычный штурм: объект camera_setup нормализуется без keywords-фильтра."""
    raw = ('{"ideas": [{"title": "Т", "camera_setup": '
           '{"приём": "Мультиэкспозиция"}}]}')
    ideas = bs.parse_ideas(raw, require_camera_setup=True)
    assert len(ideas) == 1
    assert ideas[0]["camera_setup"] == "приём: Мультиэкспозиция"


# ─── storm_system_prompt: выбор промпта по mode ───

def test_storm_system_prompt_standard():
    assert bs.storm_system_prompt("standard") == bs.STORM_SYSTEM_PROMPT
    assert bs.storm_system_prompt("") == bs.STORM_SYSTEM_PROMPT


def test_storm_system_prompt_surreal():
    assert bs.storm_system_prompt("surreal") == bs.SURREAL_STORM_SYSTEM_PROMPT
    assert bs.SURREAL_STORM_SYSTEM_PROMPT is not bs.STORM_SYSTEM_PROMPT
    assert "camera_setup" in bs.SURREAL_STORM_SYSTEM_PROMPT
    assert "FUJI_XT4_CREATIVE_GUIDE.md" in bs.SURREAL_STORM_SYSTEM_PROMPT
    assert "имитац" in bs.SURREAL_STORM_SYSTEM_PROMPT.lower()


def test_storm_sampling_params():
    assert bs.storm_sampling_params("standard") == {}
    assert bs.storm_sampling_params("") == {}
    surreal = bs.storm_sampling_params("surreal")
    assert surreal["temperature"] >= 0.9
    assert surreal["top_p"] >= 0.9
    assert 0.4 <= surreal["frequency_penalty"] <= 0.7
    assert surreal == bs.SURREAL_SAMPLING_PARAMS
    assert surreal is not bs.SURREAL_SAMPLING_PARAMS  # копия, не ссылка


# ─── collect_context: mode="surreal" ───

def test_collect_context_surreal_no_palace_kg(monkeypatch):
    """При surreal palace/kg НЕ запрашиваются (нет ключей в контексте)."""

    def _notes(*a, **k):
        return [{"name": "Сон", "snippet": "ночные тени"}]

    monkeypatch.setattr(bs, "search_notes", _notes)

    def _boom(*a, **k):
        raise AssertionError("get_mcp не должен вызываться при surreal")

    monkeypatch.setattr(bs, "get_mcp", _boom)
    ctx = run_async(bs.collect_context("сон", mode="surreal"))
    assert "palace" not in ctx
    assert "kg" not in ctx
    assert ctx["notes"]
    assert "Сон" in ctx["notes"]


def test_collect_context_surreal_uses_list_notes_with_folder(monkeypatch):
    """surreal + folder → list_notes(folder=...), не search_notes."""

    def _boom(*a, **k):
        raise AssertionError("search_notes не должен вызываться при folder")

    monkeypatch.setattr(bs, "search_notes", _boom)

    def _list_notes(folder=None, sort_by_updated=False, limit=None):
        assert folder == "Фото"
        return [{"name": "Кадр", "preview": "свет"}]

    monkeypatch.setattr(bs, "list_notes", _list_notes)
    ctx = run_async(bs.collect_context("тема", mode="surreal", folder="Фото"))
    assert "Кадр" in ctx["notes"]


def test_collect_context_surreal_guide_loaded(mock_sources, monkeypatch):
    """surreal → в контексте полный текст FUJI-гайда (кэш в памяти)."""
    mock_sources()
    monkeypatch.setattr(bs, "_load_fuji_guide", lambda: "РУКОВОДСТВО X-T4")
    ctx = run_async(bs.collect_context("тема", mode="surreal"))
    assert ctx["guide"] == "РУКОВОДСТВО X-T4"


def test_load_fuji_guide_cached_once(monkeypatch, tmp_path):
    """Руководство читается с диска один раз, далее — из кэша."""
    calls = []

    class FakePath:
        def __init__(self, name):
            self._name = name

        def read_text(self, encoding=None):
            calls.append(self._name)
            return "ГАЙД"

    monkeypatch.setattr(bs, "_FUJI_GUIDE_NAMES", ("guide.md",))
    monkeypatch.setattr(
        bs, "_FUJI_GUIDE_DIR", type("D", (), {"__truediv__": lambda self, n: FakePath(n)})(),
    )
    bs.reset_fuji_guide_cache()
    try:
        assert bs._load_fuji_guide() == "ГАЙД"
        assert bs._load_fuji_guide() == "ГАЙД"
        assert len(calls) == 1
    finally:
        bs.reset_fuji_guide_cache()


def test_load_fuji_guide_missing_file_tolerated(monkeypatch):
    """Нет файла руководства → "" (блок просто пропускается)."""
    class MissingPath:
        def read_text(self, encoding=None):
            raise OSError("нет файла")

    monkeypatch.setattr(
        bs, "_FUJI_GUIDE_DIR", type("D", (), {"__truediv__": lambda self, n: MissingPath()})(),
    )
    bs.reset_fuji_guide_cache()
    try:
        assert bs._load_fuji_guide() == ""
    finally:
        bs.reset_fuji_guide_cache()


def test_build_storm_prompt_includes_guide_block():
    ctx = {"notes": "заметка", "guide": "ГАЙД X-T4"}
    prompt = bs.build_storm_prompt("Тема", ctx)
    assert "[Руководство Fujifilm X-T4]\nГАЙД X-T4" in prompt


def test_build_storm_prompt_standard_skips_missing_guide():
    prompt = bs.build_storm_prompt("Тема", {"notes": "n", "palace": "", "kg": ""})
    assert "Руководство Fujifilm" not in prompt


def test_build_storm_prompt_guide_uses_wider_limit():
    """Гайд больше стандартного лимита входит в промпт (GUIDE_CONTEXT_LIMIT)."""
    guide = "рецепт " * 4000  # 28000 символов — длиннее GUIDE_CONTEXT_LIMIT
    ctx = {"notes": "заметка", "guide": guide}
    prompt = bs.build_storm_prompt("Тема", ctx)
    block = prompt.split("[Руководство Fujifilm X-T4]\n", 1)[1]
    assert len(block) == bs.GUIDE_CONTEXT_LIMIT + 1, \
        "гайд обрезается по GUIDE_CONTEXT_LIMIT, а не по CONTEXT_SOURCE_LIMIT"
    assert bs.GUIDE_CONTEXT_LIMIT > bs.CONTEXT_SOURCE_LIMIT


def test_build_storm_prompt_guide_shorter_than_limit_full():
    ctx = {"notes": "заметка", "guide": "полный текст гайда"}
    prompt = bs.build_storm_prompt("Тема", ctx)
    assert "[Руководство Fujifilm X-T4]\nполный текст гайда" in prompt


def test_build_storm_prompt_notes_still_uses_standard_limit():
    """Прочие источники не затронуты отдельным лимитом гайда."""
    ctx = {"notes": "н" * 5000, "palace": "п" * 5000, "kg": "", "guide": "г"}
    prompt = bs.build_storm_prompt("Тема", ctx)
    notes_block = prompt.split("[Заметки Apple Notes]\n", 1)[1].split("\n[", 1)[0]
    palace_block = prompt.split("[Записи дворца]\n", 1)[1].split("\n[", 1)[0]
    assert len(notes_block.rstrip("\n")) == bs.CONTEXT_SOURCE_LIMIT
    assert len(palace_block.rstrip("\n")) == bs.CONTEXT_SOURCE_LIMIT


def test_format_surreal_card():
    idea = {
        "title": "Сон во сне",
        "reason": "двойная реальность",
        "camera_setup": "ACROS, R+9 B-9",
        "steps": "взять камеру",
    }
    text = bs.format_surreal_card(1, idea)
    assert "💡" in text and "Сон во сне" in text
    assert "🎭" in text and "двойная реальность" in text
    assert "📷" in text and "<code>ACROS, R+9 B-9</code>" in text
    assert "➡️" in text and "взять камеру" in text


def test_format_surreal_card_without_camera_setup():
    text = bs.format_surreal_card(2, {"title": "Т", "reason": "", "steps": ""})
    assert "📷" not in text
    assert "🎭" not in text and "➡️" not in text


def test_format_surreal_card_escapes_html():
    idea = {"title": "<b>Т</b>", "camera_setup": "WB <script>"}
    text = bs.format_surreal_card(1, idea)
    assert "<b>Т</b>" not in text
    assert "&lt;script&gt;" in text


def test_format_surreal_ideas_text_header():
    ideas = [{"title": "A", "camera_setup": "X", "reason": "", "steps": ""}]
    text = bs.format_surreal_ideas_text("ночные сны", ideas)
    assert "🌪" in text and "Сюрреалистичный штурм" in text
    assert "ночные сны" in text


# ─── Связывание идей («Связано с: …») ───

def test_significant_tokens_empty():
    assert bs._significant_tokens("") == set()
    assert bs._significant_tokens(None) == set()


def test_significant_tokens_filters_short_and_digits():
    tokens = bs._significant_tokens("Кот 1234 Парк парк 2024")
    assert tokens == {"парк"}


def test_significant_tokens_case_insensitive():
    assert bs._significant_tokens("ФОТОСЕРИЯ") == {"фотосерия"}


def test_find_linked_happy():
    context = {
        "notes": "- План съёмки: полевая фотосерия в парке",
        "palace": "запись про фотосерию в парке",
        "kg": "нет совпадений",
    }
    linked = bs.find_linked("Идея: фотосерия в парке", context)
    assert len(linked) == 2
    assert linked[0]["score"] >= linked[1]["score"]
    assert {item["source"] for item in linked} == {"notes", "palace"}


def test_find_linked_no_overlap():
    context = {"notes": "- Совсем другое", "palace": "", "kg": ""}
    assert bs.find_linked("фотосерия в парке", context) == []


def test_find_linked_empty_context():
    assert bs.find_linked("фотосерия", {"notes": "", "palace": "", "kg": ""}) == []
    assert bs.find_linked("фотосерия", {}) == []


def test_find_linked_empty_ideas_text():
    context = {"notes": "- фотосерия"}
    assert bs.find_linked("", context) == []
    assert bs.find_linked("   ", context) == []


def test_find_linked_limit_boundary():
    lines = "\n".join(f"- строка номер {i} фотосерия" for i in range(1, 8))
    context = {"notes": lines, "palace": "", "kg": ""}
    linked = bs.find_linked("фотосерия", context)
    assert len(linked) == bs.MAX_LINKS
    linked_one = bs.find_linked("фотосерия", context, limit=1)
    assert len(linked_one) == 1
    linked_zero = bs.find_linked("фотосерия", context, limit=0)
    assert linked_zero == []


def test_find_linked_sorted_by_score():
    context = {
        "notes": "- только фотосерия\n- фотосерия и парке вместе",
        "palace": "",
        "kg": "",
    }
    linked = bs.find_linked("фотосерия в парке", context)
    assert linked[0]["text"].startswith("- фотосерия и парке")
    assert linked[0]["score"] == 2
    assert linked[1]["score"] == 1


def test_find_linked_truncates_long_line():
    long_line = "- фотосерия " + "x" * 500
    linked = bs.find_linked("фотосерия", {"notes": long_line})
    assert len(linked) == 1
    assert len(linked[0]["text"]) == bs.MAX_LINK_TEXT_LEN


def test_format_linked_happy():
    linked = [{"source": "notes", "label": "Apple Notes",
               "text": "текст <b>заметки</b>", "score": 1}]
    text = bs.format_linked(linked)
    assert text.startswith("🔗 <b>Связано с:</b>")
    assert "Apple Notes" in text
    assert "&lt;b&gt;заметки&lt;/b&gt;" in text


def test_format_linked_empty():
    assert bs.format_linked([]) == "🔗 <b>Связано с:</b>"


# маленький хелпер для async-тестов (модуль импортирован без asyncio.run в тестах)
