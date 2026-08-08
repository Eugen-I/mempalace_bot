"""Тесты services/code_mode.py — сохранение кода, контекст, проект.

Покрытие: извлечение блоков кода, детект кодинга, промпт, папки, файлы.
"""
import json
import os

import pytest

import services.code_mode as cm


# ─── save_code_from_text ───


def test_save_code_empty_dir_returns_empty(tmp_path):
    assert cm.save_code_from_text("```python\nx=1\n```", str(tmp_path / "nope")) == []


def test_save_code_python_block(tmp_path):
    saved = cm.save_code_from_text(
        "```python\nprint('hi')\n```", str(tmp_path), "my_script"
    )
    assert len(saved) == 1
    assert saved[0].startswith("my_script_")
    assert saved[0].endswith(".py")
    content = (tmp_path / saved[0]).read_text(encoding="utf-8")
    assert content == "print('hi')"


def test_save_code_json_block(tmp_path):
    saved = cm.save_code_from_text("```json\n{\"a\": 1}\n```", str(tmp_path))
    assert saved[0].endswith(".json")


def test_save_code_js_block(tmp_path):
    saved = cm.save_code_from_text("```js\nlet x=1;\n```", str(tmp_path))
    assert saved[0].endswith(".js")


def test_save_code_javascript_lang_falls_back_to_py(tmp_path):
    """Факт: 'javascript' не содержит подстроку 'js' → расширение .py."""
    saved = cm.save_code_from_text("```javascript\nlet x=1;\n```", str(tmp_path))
    assert saved[0].endswith(".py")


def test_save_code_cpp_block(tmp_path):
    saved = cm.save_code_from_text("```cpp\nint main(){}\n```", str(tmp_path))
    assert saved[0].endswith(".cpp")


def test_save_code_html_block(tmp_path):
    saved = cm.save_code_from_text("```html\n<b>x</b>\n```", str(tmp_path))
    assert saved[0].endswith(".html")


def test_save_code_multiple_blocks(tmp_path):
    saved = cm.save_code_from_text(
        "```py\na=1\n```\ntext\n```js\nb=2\n```", str(tmp_path)
    )
    assert len(saved) == 2


def test_save_code_empty_block_skipped(tmp_path):
    saved = cm.save_code_from_text("```py\n   \n```", str(tmp_path))
    assert saved == []


def test_save_code_no_blocks_returns_empty(tmp_path):
    assert cm.save_code_from_text("просто текст без кода", str(tmp_path)) == []


def test_save_code_block_without_lang_defaults_py(tmp_path):
    saved = cm.save_code_from_text("```\nprint('no lang')\n```", str(tmp_path))
    assert len(saved) == 1
    assert saved[0].endswith(".py")


def test_save_code_write_error_logged(tmp_path, caplog):
    saved = cm.save_code_from_text("```py\nx=1\n```", "/не/существует/путь")
    assert saved == []


def test_save_code_write_error_in_existing_dir(tmp_path, monkeypatch, capsys):
    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr("builtins.open", boom)
    saved = cm.save_code_from_text("```py\nx=1\n```", str(tmp_path))
    assert saved == []
    assert "Ошибка сохранения" in capsys.readouterr().out


# ─── is_coding_context ───


@pytest.mark.parametrize(
    "text",
    [
        "```python\nprint(1)\n```",
        "def foo(): pass",
        "исправь ошибку в коде",
        "почему ошибка в python",
        "import os в скрипте",
        "переменная x в цикле",
        "const a = 1",
    ],
)
def test_is_coding_context_true(text):
    assert cm.is_coding_context(text) is True


@pytest.mark.parametrize(
    "text",
    ["как дела", "что пообедать", "сон про море", ""],
)
def test_is_coding_context_false(text):
    assert cm.is_coding_context(text) is False


def test_is_coding_context_from_history():
    history = [
        {"role": "user", "content": "как чинить баг в python"},
        {"role": "assistant", "content": "вот решение"},
    ]
    assert cm.is_coding_context("дальше", history) is True


def test_is_coding_context_history_ignores_assistant():
    history = [
        {"role": "assistant", "content": "баг python рефакторинг"},
    ]
    assert cm.is_coding_context("дальше", history) is False


def test_is_coding_context_empty_history():
    assert cm.is_coding_context("дальше", []) is False


# ─── load_coding_prompt ───


def test_load_coding_prompt_happy(tmp_path, monkeypatch):
    prompts = tmp_path / "pdf_prompts.json"
    prompts.write_text(
        json.dumps({"code_senior": {"prompt": "Ты сеньор"}}), encoding="utf-8"
    )
    monkeypatch.setattr(cm, "PROMPTS_FILE", str(prompts))
    assert cm.load_coding_prompt() == "Ты сеньор"


def test_load_coding_prompt_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cm, "PROMPTS_FILE", str(tmp_path / "nope.json"))
    assert "Senior Developer" in cm.load_coding_prompt()


def test_load_coding_prompt_missing_key(tmp_path, monkeypatch):
    prompts = tmp_path / "pdf_prompts.json"
    prompts.write_text(json.dumps({"other": {}}), encoding="utf-8")
    monkeypatch.setattr(cm, "PROMPTS_FILE", str(prompts))
    assert cm.load_coding_prompt() == ""


# ─── ensure_project_dir ───


def test_ensure_project_dir_creates(tmp_path, monkeypatch):
    monkeypatch.setattr(cm, "PROJECTS_DIR", str(tmp_path))
    path = cm.ensure_project_dir("мой чат!")
    assert os.path.exists(path)
    assert "мой_чат_" in path or "мой" in path


def test_ensure_project_dir_sanitizes_json_suffix(tmp_path, monkeypatch):
    monkeypatch.setattr(cm, "PROJECTS_DIR", str(tmp_path))
    path = cm.ensure_project_dir("chat.json")
    assert path == os.path.join(str(tmp_path), "chat")


# ─── save_uploaded_file ───


def test_save_uploaded_file_copies(tmp_path):
    src = tmp_path / "code.py"
    src.write_text("print(1)", encoding="utf-8")
    dest_dir = tmp_path / "proj"
    dest_dir.mkdir()
    dest = cm.save_uploaded_file(str(src), str(dest_dir))
    assert os.path.exists(dest)
    assert (dest_dir / "code.py").read_text(encoding="utf-8") == "print(1)"


# ─── read_project_files ───


def test_read_project_files_missing_dir():
    assert cm.read_project_files("/не/существует") == ""


def test_read_project_files_reads_py_and_json(tmp_path):
    (tmp_path / "a.py").write_text("print(1)", encoding="utf-8")
    (tmp_path / "b.json").write_text('{"x": 1}', encoding="utf-8")
    (tmp_path / "c.txt").write_text("не читаем", encoding="utf-8")
    context = cm.read_project_files(str(tmp_path))
    assert "a.py" in context
    assert "print(1)" in context
    assert "b.json" in context
    assert "c.txt" not in context


def test_read_project_files_recursive(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "deep.py").write_text("x=1", encoding="utf-8")
    context = cm.read_project_files(str(tmp_path))
    assert "deep.py" in context


def test_read_project_files_unreadable_skipped(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x=1", encoding="utf-8")
    os.chmod(f, 0)
    context = cm.read_project_files(str(tmp_path))
    assert "a.py" not in context
