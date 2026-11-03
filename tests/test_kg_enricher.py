"""Тесты services/kg_enricher.py — обогащение заметок KG-фактами.

Покрытие: построение промпта, извлечение из имени файла, enrich_file,
add_kg_facts, enrich_all_notes (мок MCP).
"""
import asyncio
import json

import services.kg_enricher as enricher


class FakeMCP:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    async def start(self):
        pass

    async def call_tool(self, name, args):
        if self.fail:
            raise RuntimeError("mcp down")
        self.calls.append((name, args))
        return "ok"


# ─── _build_prompt ───


def test_build_prompt_includes_fields():
    prompt = enricher._build_prompt("Фауст.txt", "книги", "Текст заметки")
    assert "Фауст.txt" in prompt
    assert "книги" in prompt
    assert "Текст заметки" in prompt


def test_build_prompt_empty_content_placeholder():
    prompt = enricher._build_prompt("a.txt", "f", "")
    assert "[пусто]" in prompt


# ─── _extract_from_filename ───


def test_extract_from_filename_defaults():
    data = enricher._extract_from_filename("моя заметка.txt", "сны")
    assert data["type"] == "personal_thought"
    assert data["author"] is None
    assert data["topics"] == ["сон", "психология"]


def test_extract_from_filename_dream_type():
    data = enricher._extract_from_filename("сон 12 марта.txt", "сны")
    assert data["type"] == "dream"
    assert "сон" in data["topics"]


def test_extract_from_filename_book_with_author():
    data = enricher._extract_from_filename("Книга Фауст — Гёте.txt", "мысли_из_книг")
    assert data["type"] == "book_note"
    assert data["book"] == "Фауст"
    assert data["author"] == "Гёте.txt"


def test_extract_from_filename_book_prefix_single():
    data = enricher._extract_from_filename("Book Фауст.txt", "books")
    assert data["type"] == "book_note"
    assert data["book"] == "Фауст.txt"


def test_extract_from_filename_poem():
    data = enricher._extract_from_filename("стих о весне.txt", "стихи")
    assert data["type"] == "poem"
    assert "поэзия" in data["topics"]


def test_extract_from_filename_author_at_end():
    data = enricher._extract_from_filename("Высказывания — Иван Петров.txt", "цитаты")
    assert data["author"] is None


def test_extract_from_filename_author_no_extension():
    data = enricher._extract_from_filename("Высказывания — Иван Петров", "цитаты")
    assert data["author"] == "Иван Петров"


def test_extract_from_filename_short_author_candidate_rejected():
    data = enricher._extract_from_filename("Высказывания — А Я", "цитаты")
    assert data["author"] is None


def test_extract_from_filename_topics_from_folder():
    data = enricher._extract_from_filename("мысли.txt", "философия")
    assert data["topics"] == ["философия"]


def test_extract_from_filename_photography():
    data = enricher._extract_from_filename("фото прогулки.txt", "фото")
    assert data["topics"] == ["фотография"]


# ─── enrich_file ───


async def _enrich(tmp_path, content, fname="note.txt", folder="folder"):
    d = tmp_path / folder
    d.mkdir(exist_ok=True)
    fp = d / fname
    fp.write_text(content, encoding="utf-8")
    return await enricher.enrich_file(str(fp))


def test_enrich_file_short_content_uses_filename(tmp_path, monkeypatch):
    result = asyncio.run(_enrich(tmp_path, "короткий текст", fname="сон ночи.txt", folder="сны"))
    assert result is not None
    assert result["data"]["type"] == "dream"
    assert result["file"] == "сон ночи.txt"


def test_enrich_file_read_error_returns_none(tmp_path):
    result = asyncio.run(enricher.enrich_file(str(tmp_path / "нет_такого.txt")))
    assert result is None


def test_enrich_file_ai_happy_path(tmp_path, monkeypatch):
    import services.ai_engine as ai_engine

    async def fake_ai(engine, model, messages, **kwargs):
        return json.dumps(
            {"author": "Гёте", "book": "Фауст", "ideas": [], "quotes": [], "topics": ["литература"], "type": "book_note"},
            ensure_ascii=False,
        )

    monkeypatch.setattr(ai_engine, "get_current_ai", lambda: ("gemini", "flash"))
    monkeypatch.setattr(ai_engine, "get_ai_response_async", fake_ai)
    content = "Длинное содержание заметки о книге Фауст, не менее пятидесяти символов текста, чтобы пройти проверку длины и использовать ИИ для извлечения структурированных данных о книге и авторе произведения."
    result = asyncio.run(_enrich(tmp_path, content))
    assert result is not None
    assert result["data"]["author"] == "Гёте"
    assert result["data"]["type"] == "book_note"
    assert result["path"].startswith("my_notes/")


def test_enrich_file_ai_answer_code_fence(tmp_path, monkeypatch):
    import services.ai_engine as ai_engine

    answer = '```json\n{"author": "Пушкин", "ideas": ["идея"], "type": "personal_thought"}\n```'

    async def fake_ai(engine, model, messages, **kwargs):
        return answer

    monkeypatch.setattr(ai_engine, "get_current_ai", lambda: ("gemini", "flash"))
    monkeypatch.setattr(ai_engine, "get_ai_response_async", fake_ai)
    content = "Содержание заметки длиной более пятидесяти символов, которое содержит рассуждения о поэзии и творчестве, достаточное для обработки ИИ и извлечения данных."
    result = asyncio.run(_enrich(tmp_path, content))
    assert result["data"]["author"] == "Пушкин"


def test_enrich_file_ai_error_prefix_fallback(tmp_path, monkeypatch):
    import services.ai_engine as ai_engine

    async def fake_ai(engine, model, messages, **kwargs):
        return "❌ Ошибка модели"

    monkeypatch.setattr(ai_engine, "get_current_ai", lambda: ("gemini", "flash"))
    monkeypatch.setattr(ai_engine, "get_ai_response_async", fake_ai)
    content = "Содержание заметки длиной более пятидесяти символов для проверки фолбэка на имя файла при ошибке ИИ и продолжения обработки дальше."
    result = asyncio.run(_enrich(tmp_path, content, fname="сон ночи.txt", folder="сны"))
    assert result["data"]["type"] == "dream"


def test_enrich_file_ai_invalid_json_fallback(tmp_path, monkeypatch):
    import services.ai_engine as ai_engine

    async def fake_ai(engine, model, messages, **kwargs):
        return "совсем не json"

    monkeypatch.setattr(ai_engine, "get_current_ai", lambda: ("gemini", "flash"))
    monkeypatch.setattr(ai_engine, "get_ai_response_async", fake_ai)
    content = "Содержание заметки длиной более пятидесяти символов для проверки обработки некорректного JSON ответа ИИ и перехода на извлечение данных из имени файла заметки."
    result = asyncio.run(_enrich(tmp_path, content, fname="стих.txt", folder="стихи"))
    assert result["data"]["type"] == "poem"


def test_enrich_file_ai_answer_json_prefix(tmp_path, monkeypatch):
    import services.ai_engine as ai_engine

    async def fake_ai(engine, model, messages, **kwargs):
        return (
            'json {"author": "Лена", "ideas": [], "quotes": [], '
            '"topics": [], "type": "personal_thought"}'
        )

    monkeypatch.setattr(ai_engine, "get_current_ai", lambda: ("gemini", "flash"))
    monkeypatch.setattr(ai_engine, "get_ai_response_async", fake_ai)
    content = "Содержание заметки длиной более пятидесяти символов для проверки обработки JSON с префиксом json от ИИ и извлечения структурированных данных."
    result = asyncio.run(_enrich(tmp_path, content))
    assert result["data"]["author"] == "Лена"


# ─── add_kg_facts ───


def test_add_kg_facts_full(monkeypatch):
    import services.palace_mcp as palace_mcp

    mcp = FakeMCP()
    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: mcp)

    enriched = {
        "file": "Книга Фауст — Гёте.txt",
        "path": "my_notes/x/Книга Фауст — Гёте.txt",
        "data": {
            "author": "Гёте",
            "book": "Фауст",
            "ideas": ["идея1", "идея2"],
            "quotes": ["цитата"],
            "topics": ["литература"],
            "type": "book_note",
        },
    }
    added = asyncio.run(enricher.add_kg_facts(enriched))
    assert added == 1 + 2 + 1 + 1
    names = [c[0] for c in mcp.calls]
    assert names.count("mempalace_kg_add") == 5


def test_add_kg_facts_mcp_failure_skipped(monkeypatch):
    import services.palace_mcp as palace_mcp

    mcp = FakeMCP(fail=True)
    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: mcp)

    enriched = {
        "file": "Книга Фауст — Гёте.txt",
        "path": "my_notes/x/Книга Фауст — Гёте.txt",
        "data": {
            "author": "Гёте",
            "book": "Фауст",
            "ideas": ["идея1"],
            "quotes": ["цитата"],
            "topics": ["литература"],
            "type": "book_note",
        },
    }
    added = asyncio.run(enricher.add_kg_facts(enriched))
    assert added == 0
    assert mcp.calls == []


def test_add_kg_facts_minimal(monkeypatch):
    import services.palace_mcp as palace_mcp

    mcp = FakeMCP()
    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: mcp)

    enriched = {
        "file": "заметка.txt",
        "path": "my_notes/заметка.txt",
        "data": {"author": None, "book": None, "ideas": [], "quotes": [], "topics": [], "type": "personal_thought"},
    }
    added = asyncio.run(enricher.add_kg_facts(enriched))
    assert added == 0


def test_add_kg_facts_entity_from_filename(monkeypatch):
    import services.palace_mcp as palace_mcp

    mcp = FakeMCP()
    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: mcp)

    enriched = {
        "file": "моя_заметка.txt",
        "path": "my_notes/моя_заметка.txt",
        "data": {"author": None, "book": None, "ideas": ["идея"], "quotes": [], "topics": [], "type": "personal_thought"},
    }
    asyncio.run(enricher.add_kg_facts(enriched))
    subject = mcp.calls[0][1]["subject"]
    assert subject == "моя заметка"


# ─── enrich_all_notes ───


def test_enrich_all_notes_no_files(tmp_path, monkeypatch):
    monkeypatch.setattr(
        enricher.os.path, "expanduser", lambda p: str(tmp_path / "mempalace")
    )
    result = asyncio.run(enricher.enrich_all_notes())
    assert "error" in result


def test_enrich_all_notes_happy_path(tmp_path, monkeypatch):
    import services.palace_mcp as palace_mcp

    notes_dir = tmp_path / "my_notes"
    (notes_dir / "a").mkdir(parents=True)
    (notes_dir / "a" / "сон.txt").write_text("короткий", encoding="utf-8")
    (notes_dir / "b.txt").write_text("тоже короткий", encoding="utf-8")

    monkeypatch.setattr(enricher.os.path, "expanduser", lambda p: str(tmp_path))
    mcp = FakeMCP()
    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: mcp)

    result = asyncio.run(enricher.enrich_all_notes())
    assert result["total"] == 2
    assert result["processed"] == 2
    assert result["failed"] == 0
    assert isinstance(result["authors"], list)
    assert isinstance(result["books"], list)


def test_enrich_all_notes_mcp_start_fails(tmp_path, monkeypatch):
    import services.palace_mcp as palace_mcp

    class FailingMCP(FakeMCP):
        async def start(self):
            raise RuntimeError("no server")

    (tmp_path / "my_notes").mkdir(exist_ok=True)
    (tmp_path / "my_notes" / "a.txt").write_text("х", encoding="utf-8")
    monkeypatch.setattr(enricher.os.path, "expanduser", lambda p: str(tmp_path))
    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: FailingMCP())

    result = asyncio.run(enricher.enrich_all_notes())
    assert "error" in result


def test_enrich_all_notes_skips_non_txt_and_progress(tmp_path, monkeypatch):
    import services.palace_mcp as palace_mcp

    notes_dir = tmp_path / "my_notes"
    notes_dir.mkdir(exist_ok=True)
    for i in range(10):
        (notes_dir / f"n{i:02d}.txt").write_text("х" * 60, encoding="utf-8")
    (notes_dir / "pic.png").write_bytes(b"x")

    monkeypatch.setattr(enricher.os.path, "expanduser", lambda p: str(tmp_path))
    mcp = FakeMCP()
    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: mcp)

    async def fake_enrich(fp):
        if "n03" in fp:
            return None
        data = {
            "author": None,
            "book": None,
            "ideas": [],
            "quotes": [],
            "topics": [],
            "type": "personal_thought",
        }
        if "n05" in fp:
            data["author"] = "Гёте"
            data["book"] = "Фауст"
        return {
            "file": "note.txt",
            "folder": "my_notes",
            "path": "my_notes/note.txt",
            "data": data,
        }

    monkeypatch.setattr(enricher, "enrich_file", fake_enrich)

    calls = []

    async def progress(done, total, stats):
        calls.append((done, total))

    result = asyncio.run(enricher.enrich_all_notes(progress_callback=progress))
    assert result["processed"] == 9
    assert result["failed"] == 1
    assert result["authors"] == ["Гёте"]
    assert result["books"] == ["Фауст"]
    assert calls[-1] == (10, 10)
