import importlib.util
from pathlib import Path


def load_import_notes_module():
    module_path = Path('/Users/evg.pit/Documents/mempalace/import_notes.py')
    spec = importlib.util.spec_from_file_location('import_notes', module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, text):
        self._text = text

    def read(self):
        return self._text.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _fake_urlopen(monkeypatch, answer_json):
    import urllib.request

    def urlopen(req, timeout=60):
        return FakeResponse(answer_json)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)


def test_parse_ai_answer_extracts_json_from_code_fence(monkeypatch):
    module = load_import_notes_module()
    answer = '''```json
{
  "author": "Гёте",
  "book": null,
  "ideas": [],
  "quotes": [],
  "topics": ["literature"],
  "type": "book_note"
}
```'''
    _fake_urlopen(monkeypatch, '{"response": "%s"}' % answer.replace('"', '\\"').replace("\n", "\\n"))

    parsed = module.ai_enrich("note.txt", "some_folder", "Содержимое заметки.")

    assert parsed['author'] == 'Гёте'
    assert parsed['type'] == 'book_note'


def test_ai_enrich_returns_none_on_network_error(monkeypatch):
    import urllib.request

    module = load_import_notes_module()

    def urlopen(req, timeout=60):
        raise ConnectionError("ollama offline")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    parsed = module.ai_enrich("note.txt", "some_folder", "Содержимое.")

    assert parsed is None


def test_ai_enrich_returns_none_on_invalid_json(monkeypatch):
    module = load_import_notes_module()
    _fake_urlopen(monkeypatch, '{"response": "не json ответ"}')

    parsed = module.ai_enrich("note.txt", "some_folder", "Содержимое.")

    assert parsed is None


def test_ai_enrich_strips_json_prefix(monkeypatch):
    module = load_import_notes_module()
    _fake_urlopen(
        monkeypatch,
        '{"response": "JSON {\\"author\\": \\"Пушкин\\", \\"type\\": \\"book_note\\"}"}',
    )

    parsed = module.ai_enrich("note.txt", "some_folder", "Содержимое.")

    assert parsed['author'] == 'Пушкин'
