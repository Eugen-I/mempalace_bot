"""Unit tests for services.pdf_engine.

Covers prompt loading, PDF extraction (text and OCR paths), token estimation,
comparison prompt building, chunking, large-document analysis and PDF archive
helpers.
"""

import asyncio
import json

import pytest

import services.pdf_engine as pdf_engine


@pytest.fixture(autouse=True)
def no_real_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_engine, "PDF_ARCHIVE_DIR", str(tmp_path / "archive"))
    monkeypatch.setattr(pdf_engine, "PROMPTS_FILE", str(tmp_path / "pdf_prompts.json"))
    yield


# ---------- load_prompts ----------


def test_load_prompts_creates_defaults(tmp_path):
    file = tmp_path / "pdf_prompts.json"
    monkeypatch = _monkeypatch()
    monkeypatch.setattr(pdf_engine, "PROMPTS_FILE", str(file))
    out = pdf_engine.load_prompts()
    assert file.exists()
    assert out["general"]["name"] == "📄 Общий анализ"
    assert "medical" in out
    assert "scientific" in out


def test_load_prompts_reads_file(tmp_path):
    file = tmp_path / "my_prompts.json"
    file.write_text(json.dumps({"custom": {"name": "Мой", "prompt": "х"}}), encoding="utf-8")
    monkeypatch = _monkeypatch()
    monkeypatch.setattr(pdf_engine, "PROMPTS_FILE", str(file))
    out = pdf_engine.load_prompts()
    assert out == {"custom": {"name": "Мой", "prompt": "х"}}


def _monkeypatch():
    import pytest

    return pytest.MonkeyPatch()


# ---------- _sync_extract_pdf ----------


def test_extract_sync_missing_file():
    assert pdf_engine._sync_extract_pdf("/nonexistent/x.pdf") == ("", "failed")


def test_extract_sync_text_path(monkeypatch, tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")

    class FakePage:
        def __init__(self, text):
            self._text = text

        def get_text(self):
            return self._text

    class FakeDoc:
        def __init__(self, pages):
            self._pages = pages
            self.closed = False

        def __iter__(self):
            return iter(self._pages)

        def close(self):
            self.closed = True

    def fake_open(path):
        return FakeDoc([FakePage("Страница один. " * 60), FakePage("Страница два. " * 60)])

    monkeypatch.setattr(pdf_engine.fitz, "open", fake_open)
    full, mode = pdf_engine._sync_extract_pdf(str(pdf))
    assert mode == "text"
    assert "Страница один" in full


def test_extract_sync_text_too_short_uses_ocr(monkeypatch, tmp_path):
    pdf = tmp_path / "b.pdf"
    pdf.write_bytes(b"%PDF")

    class FakePage:
        def get_text(self):
            return "короткий"

    class FakeDoc:
        def __iter__(self):
            return iter([FakePage()])

        def close(self):
            pass

    def fake_convert(path, dpi=200, last_page=15):
        return [object()]

    def fake_ocr(img, lang="", config=""):
        return "OCR содержимое длинное " * 20

    monkeypatch.setattr(pdf_engine.fitz, "open", lambda p: FakeDoc())
    monkeypatch.setattr(pdf_engine, "convert_from_path", fake_convert)
    monkeypatch.setattr(pdf_engine.pytesseract, "image_to_string", fake_ocr)
    full, mode = pdf_engine._sync_extract_pdf(str(pdf))
    assert mode == "ocr"
    assert "OCR содержимое" in full
    assert "Стр. 1" in full


def test_extract_sync_fitz_error_then_ocr(monkeypatch, tmp_path):
    pdf = tmp_path / "c.pdf"
    pdf.write_bytes(b"%PDF")

    def fake_open(path):
        raise RuntimeError("fitz broken")

    def fake_convert(path, dpi=200, last_page=15):
        return [object()]

    def fake_ocr(img, lang="", config=""):
        return " только текст " * 30

    monkeypatch.setattr(pdf_engine.fitz, "open", fake_open)
    monkeypatch.setattr(pdf_engine, "convert_from_path", fake_convert)
    monkeypatch.setattr(pdf_engine.pytesseract, "image_to_string", fake_ocr)
    full, mode = pdf_engine._sync_extract_pdf(str(pdf))
    assert mode == "ocr"
    assert "только текст" in full


def test_extract_sync_all_fail(monkeypatch, tmp_path):
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(b"%PDF")

    class FakePage:
        def get_text(self):
            return "короткий текст"

    class FakeDoc:
        def __iter__(self):
            return iter([FakePage()])

        def close(self):
            pass

    monkeypatch.setattr(pdf_engine.fitz, "open", lambda p: FakeDoc())

    def fake_ocr(img, lang="", config=""):
        raise RuntimeError("tesseract fail")

    monkeypatch.setattr(
        pdf_engine, "convert_from_path",
        lambda path, dpi=200, last_page=15: [object()],
    )
    monkeypatch.setattr(pdf_engine.pytesseract, "image_to_string", fake_ocr)
    assert pdf_engine._sync_extract_pdf(str(pdf)) == ("", "failed")


def test_extract_sync_skips_empty_pages(monkeypatch, tmp_path):
    pdf = tmp_path / "e.pdf"
    pdf.write_bytes(b"%PDF")

    class FakePage:
        def __init__(self, text):
            self._text = text

        def get_text(self):
            return self._text

    class FakeDoc:
        def __iter__(self):
            return iter([FakePage(""), FakePage("Страница с текстом. " * 60)])

        def close(self):
            pass

    monkeypatch.setattr(pdf_engine.fitz, "open", lambda p: FakeDoc())
    full, mode = pdf_engine._sync_extract_pdf(str(pdf))
    assert mode == "text"
    assert "Страница с текстом" in full


def test_extract_sync_ocr_skips_empty_results(monkeypatch, tmp_path):
    pdf = tmp_path / "f.pdf"
    pdf.write_bytes(b"%PDF")

    class FakePage:
        def get_text(self):
            return "короткий"

    class FakeDoc:
        def __iter__(self):
            return iter([FakePage(), FakePage()])

        def close(self):
            pass

    ocr_results = ["", "OCR длинное содержимое " * 20]

    def fake_ocr(img, lang="", config=""):
        return ocr_results.pop(0)

    monkeypatch.setattr(pdf_engine.fitz, "open", lambda p: FakeDoc())
    monkeypatch.setattr(
        pdf_engine, "convert_from_path",
        lambda path, dpi=200, last_page=15: [object(), object()],
    )
    monkeypatch.setattr(pdf_engine.pytesseract, "image_to_string", fake_ocr)
    full, mode = pdf_engine._sync_extract_pdf(str(pdf))
    assert mode == "ocr"
    assert "OCR длинное содержимое" in full


def test_extract_sync_ocr_too_short_fails(monkeypatch, tmp_path):
    pdf = tmp_path / "g.pdf"
    pdf.write_bytes(b"%PDF")

    class FakePage:
        def get_text(self):
            return "короткий"

    class FakeDoc:
        def __iter__(self):
            return iter([FakePage()])

        def close(self):
            pass

    def fake_ocr(img, lang="", config=""):
        return "маленький"

    monkeypatch.setattr(pdf_engine.fitz, "open", lambda p: FakeDoc())
    monkeypatch.setattr(
        pdf_engine, "convert_from_path",
        lambda path, dpi=200, last_page=15: [object()],
    )
    monkeypatch.setattr(pdf_engine.pytesseract, "image_to_string", fake_ocr)
    assert pdf_engine._sync_extract_pdf(str(pdf)) == ("", "failed")


# ---------- extract_pdf_async ----------


def _fake_sync_extract(pdf_path: str) -> tuple[str, str]:
    return "текст", "text"


def test_extract_pdf_async(monkeypatch):
    class FakePool:
        def __init__(self):
            self.calls = []

        def submit(self, *args, **kwargs):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    async def fake_run_in_executor(pool, fn, *args, **kwargs):
        return _fake_sync_extract(args[0])

    monkeypatch.setattr(pdf_engine, "_sync_extract_pdf", _fake_sync_extract)
    monkeypatch.setattr(
        pdf_engine, "ProcessPoolExecutor", lambda: FakePool(),
    )
    monkeypatch.setattr(
        pdf_engine.asyncio, "get_event_loop",
        lambda: _FakeLoop(fake_run_in_executor),
    )
    out = asyncio.run(pdf_engine.extract_pdf_async("/tmp/e.pdf"))
    assert out == ("текст", "text")


class _FakeLoop:
    def __init__(self, runner):
        self._runner = runner

    def run_in_executor(self, *args, **kwargs):
        return self._runner(*args, **kwargs)


# ---------- estimate_tokens ----------


def test_estimate_tokens_uses_tiktoken():
    n = pdf_engine.estimate_tokens("hello world " * 20)
    assert n > 0


def test_estimate_tokens_fallback(monkeypatch):
    monkeypatch.setattr(pdf_engine.tiktoken, "get_encoding", lambda name: (_ for _ in ()).throw(RuntimeError("no")))
    text = "абв" * 40
    assert pdf_engine.estimate_tokens(text) == len(text) // 4


# ---------- build_comparison_prompt ----------


def test_build_comparison_prompt_contains_both():
    out = pdf_engine.build_comparison_prompt("текст А", "текст Б")
    assert "ДОКУМЕНТ А" in out
    assert "текст А" in out
    assert "текст Б" in out
    assert "СРАВНЕНИЕ" in out


# ---------- chunk_text ----------


def test_chunk_text_short_single():
    assert pdf_engine.chunk_text("маленький текст") == ["маленький текст"]


def test_chunk_text_empty():
    assert pdf_engine.chunk_text("") == [""]


def test_chunk_text_splits_on_sentence():
    text = ("Число слово. " * 2000).strip()
    chunks = pdf_engine.chunk_text(text)
    assert len(chunks) >= 2
    assert all(len(c) <= pdf_engine.CHUNK_MAX_CHARS for c in chunks)
    assert "".join(chunks).replace(" ", "") == text.replace(" ", "")


def test_chunk_text_splits_on_newline():
    text = ("Строка\n" * 8000).strip()
    chunks = pdf_engine.chunk_text(text)
    assert len(chunks) >= 2
    assert all(c for c in chunks)


def test_chunk_text_hard_split_at_end():
    text = "x" * 60000
    chunks = pdf_engine.chunk_text(text)
    assert len(chunks) >= 2
    assert "".join(chunks) == text


# ---------- analyze_large_document ----------


@pytest.mark.asyncio
async def test_analyze_document_empty_text():
    msg = _FakeMsg()
    out = await pdf_engine.analyze_large_document("gemini", "m", "", "промпт", msg)
    assert out == "❌ Нет текста для анализа."
    assert msg.edits == []


@pytest.mark.asyncio
async def test_analyze_document_small_direct(monkeypatch):
    msg = _FakeMsg()
    calls = {}

    async def fake_ai(engine, model, messages, **kwargs):
        calls["p"] = messages[0]["content"]
        return "прямой ответ"

    monkeypatch.setattr(
        pdf_engine, "get_ai_response_async", fake_ai,
    ) if hasattr(pdf_engine, "get_ai_response_async") else None
    monkeypatch.setattr("services.ai_engine.get_ai_response_async", fake_ai)
    out = await pdf_engine.analyze_large_document(
        "gemini", "gemini-pro", "небольшой текст", "ПРОМПТ", msg,
    )
    assert out == "прямой ответ"
    assert "ДОКУМЕНТ" in calls["p"]
    assert len(msg.edits) == 1


@pytest.mark.asyncio
async def test_analyze_document_chunked_happy(monkeypatch):
    msg = _FakeMsg()
    responses = iter(["ответ 1", "ответ 2", "финал"])

    async def fake_ai(engine, model, messages, **kwargs):
        return next(responses)

    monkeypatch.setattr("services.ai_engine.get_ai_response_async", fake_ai)
    out = await pdf_engine.analyze_large_document(
        "gemini", "m", "слово. " * 5000, "ПРОМПТ", msg,
    )
    assert "финал" in out
    assert "ЧАСТЬ 1" not in out  # final wins
    assert len(msg.edits) >= 3


@pytest.mark.asyncio
async def test_analyze_document_chunked_all_fail(monkeypatch):
    msg = _FakeMsg()

    async def fake_ai(engine, model, messages, **kwargs):
        return "❌ БД упала"

    monkeypatch.setattr("services.ai_engine.get_ai_response_async", fake_ai)
    out = await pdf_engine.analyze_large_document(
        "gemini", "m", "слово. " * 5000, "ПРОМПТ", msg,
    )
    assert "ЧАСТЬ 1" in out
    assert "[Ошибка анализа этой части]" in out


@pytest.mark.asyncio
async def test_analyze_document_final_fails_uses_parts(monkeypatch):
    msg = _FakeMsg()
    responses = iter(["часть А", "часть Б", "❌ финал плохой"])

    async def fake_ai(engine, model, messages, **kwargs):
        return next(responses)

    monkeypatch.setattr("services.ai_engine.get_ai_response_async", fake_ai)
    out = await pdf_engine.analyze_large_document(
        "gemini", "m", "слово. " * 5000, "ПРОМПТ", msg,
    )
    assert "часть А" in out
    assert "часть Б" in out
    assert "финал" not in out


@pytest.mark.asyncio
async def test_analyze_document_empty_parts(monkeypatch):
    msg = _FakeMsg()

    async def fake_ai(engine, model, messages, **kwargs):
        return "❌ пусто"

    monkeypatch.setattr("services.ai_engine.get_ai_response_async", fake_ai)
    out = await pdf_engine.analyze_large_document(
        "gemini", "m", "", "ПРОМПТ", msg,
    )
    assert out == "❌ Нет текста для анализа."


@pytest.mark.asyncio
async def test_analyze_document_three_chunks(monkeypatch):
    msg = _FakeMsg()
    responses = iter(["ч1", "ч2", "ч3", "финал"])

    async def fake_ai(engine, model, messages, **kwargs):
        return next(responses)

    monkeypatch.setattr("services.ai_engine.get_ai_response_async", fake_ai)
    text = "слово. " * 10000  # 70000 chars -> 3 chunks
    out = await pdf_engine.analyze_large_document("gemini", "m", text, "ПРОМПТ", msg)
    assert out == "финал"
    assert len(msg.edits) >= 4


class _FakeMsg:
    def __init__(self):
        self.edits = []

    async def edit_text(self, text, **kwargs):
        self.edits.append(text)


class _BoomMsg:
    async def edit_text(self, text, **kwargs):
        raise RuntimeError("edit failed")


@pytest.mark.asyncio
async def test_analyze_document_small_edit_fail(monkeypatch):
    async def fake_ai(engine, model, messages, **kwargs):
        return "ответ несмотря на edit"

    monkeypatch.setattr("services.ai_engine.get_ai_response_async", fake_ai)
    out = await pdf_engine.analyze_large_document(
        "gemini", "gemini-pro", "небольшой текст", "ПРОМПТ", _BoomMsg(),
    )
    assert out == "ответ несмотря на edit"


@pytest.mark.asyncio
async def test_analyze_document_chunked_edit_fail(monkeypatch):
    responses = iter(["ч1", "ч2", "финал"])

    async def fake_ai(engine, model, messages, **kwargs):
        return next(responses)

    monkeypatch.setattr("services.ai_engine.get_ai_response_async", fake_ai)
    out = await pdf_engine.analyze_large_document(
        "gemini", "m", "слово. " * 5000, "ПРОМПТ", _BoomMsg(),
    )
    assert out == "финал"


# ---------- save_pdf_original ----------


def test_save_pdf_original_success(tmp_path):
    src = tmp_path / "src.pdf"
    src.write_bytes(b"%PDF")
    archive = tmp_path / "archive"
    archive.mkdir()
    monkeypatch = _monkeypatch()
    monkeypatch.setattr(pdf_engine, "PDF_ARCHIVE_DIR", str(archive))
    dst = pdf_engine.save_pdf_original(str(src), "Отчёт 2024!?.pdf")
    assert dst
    idx = json.loads((archive / ".index.json").read_text(encoding="utf-8"))
    assert idx[0]["original_name"] == "Отчёт 2024!?.pdf"
    assert idx[0]["id"] == dst
    assert (archive / dst).exists()


def test_save_pdf_original_copy_error(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    monkeypatch = _monkeypatch()
    monkeypatch.setattr(pdf_engine, "PDF_ARCHIVE_DIR", str(archive))
    assert pdf_engine.save_pdf_original(str(tmp_path / "missing.pdf"), "doc.pdf") == ""


def test_save_pdf_original_appends_to_existing_index(tmp_path):
    src = tmp_path / "src.pdf"
    src.write_bytes(b"%PDF")
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / ".index.json").write_text(
        json.dumps([{"id": "старый", "original_name": "старый.pdf"}]),
        encoding="utf-8",
    )
    monkeypatch = _monkeypatch()
    monkeypatch.setattr(pdf_engine, "PDF_ARCHIVE_DIR", str(archive))
    pdf_engine.save_pdf_original(str(src), "второй.pdf")
    idx = json.loads((archive / ".index.json").read_text(encoding="utf-8"))
    assert len(idx) == 2
    assert idx[0]["id"] == "старый"


# ---------- list_archived_pdfs ----------


def test_list_archived_pdfs_no_index(tmp_path):
    assert pdf_engine.list_archived_pdfs() == []


def test_list_archived_pdfs_happy(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / ".index.json").write_text(json.dumps([{"id": "a"}]), encoding="utf-8")
    monkeypatch = _monkeypatch()
    monkeypatch.setattr(pdf_engine, "PDF_ARCHIVE_DIR", str(archive))
    assert pdf_engine.list_archived_pdfs() == [{"id": "a"}]


def test_list_archived_pdfs_broken_json(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / ".index.json").write_text("{broken", encoding="utf-8")
    monkeypatch = _monkeypatch()
    monkeypatch.setattr(pdf_engine, "PDF_ARCHIVE_DIR", str(archive))
    assert pdf_engine.list_archived_pdfs() == []


# ---------- remove_pdf_from_index ----------


def test_remove_pdf_from_index_no_file(tmp_path):
    assert pdf_engine.remove_pdf_from_index("x") is None


def test_remove_pdf_from_index_removes_entry(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / ".index.json").write_text(
        json.dumps([{"id": "keep"}, {"id": "drop"}]),
        encoding="utf-8",
    )
    monkeypatch = _monkeypatch()
    monkeypatch.setattr(pdf_engine, "PDF_ARCHIVE_DIR", str(archive))
    pdf_engine.remove_pdf_from_index("drop")
    idx = json.loads((archive / ".index.json").read_text(encoding="utf-8"))
    assert idx == [{"id": "keep"}]


def test_remove_pdf_from_index_broken_json(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / ".index.json").write_text("{bad", encoding="utf-8")
    monkeypatch = _monkeypatch()
    monkeypatch.setattr(pdf_engine, "PDF_ARCHIVE_DIR", str(archive))
    assert pdf_engine.remove_pdf_from_index("x") is None
