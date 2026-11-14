"""tests/test_omni_search.py
Тесты единого гибридного поиска OmniSearch и RRF-ранжирования.
"""

import asyncio
import pytest

from services.omni_search import (
    DEFAULT_RRF_K,
    OmniSearchHit,
    OmniSource,
    format_omni_results,
    omni_search,
    reciprocal_rank_fusion,
)


def test_reciprocal_rank_fusion_basic():
    """Проверка математики и порядка сортировки RRF."""
    palace_hit = OmniSearchHit(
        id="p1",
        source_type=OmniSource.PALACE.value,
        title="Дворец: Запись 1",
        location="w/r",
        snippet="сниппет дворца",
    )
    notes_hit = OmniSearchHit(
        id="n1",
        source_type=OmniSource.NOTES.value,
        title="Заметка 1",
        location="Work",
        snippet="сниппет заметок",
    )
    files_hit = OmniSearchHit(
        id="f1",
        source_type=OmniSource.FILES.value,
        title="Файл 1",
        location="docs",
        snippet="сниппет файла",
    )

    channels = {
        "palace": [palace_hit],
        "notes": [notes_hit],
        "files": [files_hit],
    }

    # С дефолтными весами (palace=1.2, notes=1.0, files=0.9):
    # palace rank 1: 1.2 / 61 = 0.019672
    # notes rank 1:  1.0 / 61 = 0.016393
    # files rank 1:  0.9 / 61 = 0.014754
    fused = reciprocal_rank_fusion(channels, k=60)
    assert len(fused) == 3
    assert fused[0].id == "p1"
    assert fused[1].id == "n1"
    assert fused[2].id == "f1"
    assert fused[0].score > fused[1].score > fused[2].score


def test_reciprocal_rank_fusion_custom_weights():
    """Проверка влияния пользовательских весов на приоритезацию."""
    hit_palace = OmniSearchHit(id="p1", source_type="palace", title="p", location="l", snippet="s")
    hit_notes = OmniSearchHit(id="n1", source_type="notes", title="n", location="l", snippet="s")

    # Увеличиваем приоритет заметок выше дворца
    custom_weights = {"palace": 1.0, "notes": 2.5}
    fused = reciprocal_rank_fusion({"palace": [hit_palace], "notes": [hit_notes]}, weights=custom_weights)

    assert fused[0].id == "n1"
    assert fused[1].id == "p1"


def test_format_omni_results_includes_badges():
    hits = [
        OmniSearchHit(
            id="1", source_type=OmniSource.PALACE.value, title="Нейросети", location="IT/AI", snippet="Контекст"
        ),
        OmniSearchHit(
            id="2", source_type=OmniSource.NOTES.value, title="Планы", location="Личное", snippet="Список дел"
        ),
        OmniSearchHit(
            id="3", source_type=OmniSource.FILES.value, title="todo.md", location="my_notes", snippet="Файловая заметка"
        ),
    ]

    text = format_omni_results(hits, query="тест")
    assert "🏰 <b>[Дворец]</b>" in text
    assert "📝 <b>[Apple Notes]</b>" in text
    assert "📁 <b>[Файлы]</b>" in text
    assert "IT/AI" in text
    assert "Планы" in text
    assert "todo.md" in text


@pytest.mark.asyncio
async def test_omni_search_empty_query():
    text, sources = await omni_search("   ")
    assert "Пустой" in text
    assert sources == []


@pytest.mark.asyncio
async def test_omni_search_parallel_and_channel_fault_tolerance(monkeypatch):
    """Один из каналов падает с ошибкой, остальные продолжают выдавать результаты."""
    async def mock_palace(query, limit=5, wing=""):
        return "текст дворца", [{"id": "pal_1", "wing": "tech", "room": "python", "snippet": "код", "score": 0.95}]

    def mock_notes_fail(query, limit=5):
        raise RuntimeError("AppleScript bridge is dead")

    def mock_files_ok(query, limit=5):
        return [{"file_id": "file_1", "filename": "python_tips.md", "folder": "docs", "snippet": "советы", "_score": 1.5}]

    monkeypatch.setattr("services.omni_search._search_notes_sync", mock_notes_fail)
    monkeypatch.setattr("services.omni_search._search_files_sync", mock_files_ok)

    text, sources = await omni_search("python", limit=5, palace_searcher=mock_palace)

    assert len(sources) == 2
    source_types = {s["source_type"] for s in sources}
    assert source_types == {"palace", "files"}
    assert "🏰 <b>[Дворец]</b>" in text
    assert "📁 <b>[Файлы]</b>" in text


@pytest.mark.asyncio
async def test_omni_search_with_wing_filters_to_palace():
    """Если указано конкретное крыло, поиск ведется строго по Дворцу."""
    captured = {}

    async def mock_palace(query, limit=5, wing=""):
        captured["wing"] = wing
        return "палас", [{"id": "p1", "wing": wing, "room": "r1", "snippet": "s"}]

    text, sources = await omni_search(
        "запрос", wing="science", palace_searcher=mock_palace, include_channels=("palace", "notes", "files")
    )

    assert captured.get("wing") == "science"
    assert len(sources) == 1
    assert sources[0]["source_type"] == "palace"


@pytest.mark.asyncio
async def test_cmd_search_omni_integration(monkeypatch):
    """Интеграция cmd_search с omni_search и генерация кнопок со значками."""
    from handlers import search as sh

    class FakeUser:
        id = 4242

    class FakeMsg:
        from_user = FakeUser()
        text = "/search архитектура"
        answers = []

        async def answer(self, text, parse_mode=None, reply_markup=None):
            self.answers.append((text, parse_mode, reply_markup))
            return self

        async def delete(self):
            pass

    async def mock_omni(query, limit=5, wing="", palace_searcher=None):
        hits = [
            {"id": "p_1", "source_type": "palace", "wing": "it", "room": "arch", "title": "it/arch"},
            {"id": "n_1", "source_type": "notes", "title": "Заметка про микросервисы", "location": "Tech"},
            {"id": "f_1", "source_type": "files", "title": "rag_plan.md", "location": "docs"},
        ]
        return "🏰 [Дворец] it/arch\n📝 [Apple Notes] Заметка\n📁 [Файлы] rag_plan.md", hits

    monkeypatch.setattr("services.omni_search.omni_search", mock_omni)
    monkeypatch.setattr(sh, "split_message", lambda t: [t])
    monkeypatch.setattr("config.ALLOWED_IDS", {4242})

    msg = FakeMsg()
    await sh.cmd_search(msg)

    # Проверяем, что в search_result_cache сохранены все источники
    assert len(sh.search_result_cache[4242]) == 3

    # Проверяем кнопки разметки
    markup = msg.answers[-1][2]
    buttons = [b for row in markup.inline_keyboard for b in row]
    callbacks = [b.callback_data for b in buttons]

    assert "p_src:p_1" in callbacks
    assert "p_notesrc:n_1" in callbacks
    assert "p_filesrc:f_1" in callbacks

    # Проверяем бейджи на кнопках
    button_texts = [b.text for b in buttons]
    assert any("📄 Читать [p_1]" in t for t in button_texts)
    assert any("📝 Читать [n_1]" in t for t in button_texts)
    assert any("📁 Читать [f_1]" in t for t in button_texts)


@pytest.mark.asyncio
async def test_cb_search_source_note(monkeypatch):
    """Проверка открытия Apple Note по клику на кнопку."""
    from handlers import search as sh

    class FakeMsg:
        edits = []

        async def edit_text(self, text, parse_mode=None):
            self.edits.append(text)

    class FakeCb:
        data = "p_notesrc:note_999"
        message = FakeMsg()
        answered = False
        from_user = type("U", (), {"id": 4242})()

        async def answer(self):
            self.answered = True

    def fake_read_note(nid):
        assert nid == "note_999"
        return {"name": "План тренировок", "folder": "Здоровье", "body": "Бег 5км"}

    monkeypatch.setattr("services.apple_notes.read_note", fake_read_note)
    monkeypatch.setattr("config.ALLOWED_IDS", {4242})

    cb = FakeCb()
    await sh.cb_search_source_note(cb)
    assert cb.answered is True
    assert "План тренировок" in cb.message.edits[-1]
    assert "Бег 5км" in cb.message.edits[-1]


@pytest.mark.asyncio
async def test_cb_search_source_file(monkeypatch):
    """Проверка открытия локального файла по клику на кнопку."""
    from handlers import search as sh

    class FakeMsg:
        edits = []

        async def edit_text(self, text, parse_mode=None):
            self.edits.append(text)

    class FakeCb:
        data = "p_filesrc:file_77"
        message = FakeMsg()
        answered = False
        from_user = type("U", (), {"id": 4242})()

        async def answer(self):
            self.answered = True

    def fake_get_file(fid):
        assert fid == "file_77"
        return {"filename": "config.yaml", "folder": "configs", "extracted_text": "api_key: secret"}

    monkeypatch.setattr("services.file_index.get_file", fake_get_file)
    monkeypatch.setattr("config.ALLOWED_IDS", {4242})

    cb = FakeCb()
    await sh.cb_search_source_file(cb)
    assert cb.answered is True
    assert "config.yaml" in cb.message.edits[-1]
    assert "api_key: secret" in cb.message.edits[-1]
