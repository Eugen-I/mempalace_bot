"""Unit tests for services.chat_store — shared chat JSON I/O."""

import json
import os
from concurrent.futures import ThreadPoolExecutor

from services import chat_store


def _messages(path):
    return json.loads(path.read_text(encoding="utf-8"))["messages"]


def test_handlers_chat_reuses_shared_store():
    from handlers import chat

    assert chat.load_chat is chat_store.load_chat
    assert chat.save_chat is chat_store.save_chat


def test_list_chat_files_missing_dir_returns_empty(tmp_path):
    assert chat_store.list_chat_files(str(tmp_path / "missing")) == []


def test_list_chat_files_sorts_newest_first_and_limits(tmp_path):
    for name, mtime in (("old.json", 1000), ("new.json", 3000), ("mid.json", 2000)):
        path = tmp_path / name
        path.write_text("{}", encoding="utf-8")
        os.utime(path, (mtime, mtime))
    (tmp_path / "note.txt").write_text("x", encoding="utf-8")

    assert chat_store.list_chat_files(str(tmp_path)) == [
        "new.json", "mid.json", "old.json",
    ]
    assert chat_store.list_chat_files(str(tmp_path), limit=2) == [
        "new.json", "mid.json",
    ]
    assert chat_store.list_chat_files(str(tmp_path), limit=1) == ["new.json"]


def test_list_chat_files_puts_unstatable_last(tmp_path, monkeypatch):
    (tmp_path / "good.json").write_text("{}", encoding="utf-8")
    (tmp_path / "bad.json").write_text("{}", encoding="utf-8")
    real_getmtime = chat_store.os.path.getmtime

    def fake_getmtime(path):
        if path.endswith("bad.json"):
            raise OSError("stat failed")
        return real_getmtime(path)

    monkeypatch.setattr(chat_store.os.path, "getmtime", fake_getmtime)

    assert chat_store.list_chat_files(str(tmp_path)) == ["good.json", "bad.json"]


def test_load_chat_missing_returns_independent_empty(tmp_path):
    first = chat_store.load_chat(str(tmp_path / "nope.json"))
    second = chat_store.load_chat(str(tmp_path / "nope.json"))

    first["messages"].append({"role": "user", "content": "x"})

    assert second == {"summary": "", "messages": []}


def test_load_chat_migrates_plain_list(tmp_path):
    path = tmp_path / "chat.json"
    path.write_text(
        json.dumps([{"role": "user", "content": "hi"}], ensure_ascii=False),
        encoding="utf-8",
    )

    data = chat_store.load_chat(str(path))

    assert data["messages"] == [{"role": "user", "content": "hi"}]
    assert json.loads(path.read_text(encoding="utf-8"))["summary"] == ""


def test_load_chat_read_error_returns_empty(tmp_path, caplog):
    assert chat_store.load_chat(str(tmp_path)) == {"summary": "", "messages": []}
    assert "Не удалось прочитать чат" in caplog.text


def test_save_chat_roundtrip(tmp_path):
    path = tmp_path / "chat.json"

    assert chat_store.save_chat(str(path), {"summary": "s", "messages": []}) is True
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "summary": "s", "messages": [],
    }


def test_save_chat_cleanup_failure_is_safe(tmp_path, monkeypatch, caplog):
    path = tmp_path / "chat.json"
    tmp_file = tmp_path / "pending.tmp"
    tmp_file.write_text("data", encoding="utf-8")

    class FakeTmp:
        name = str(tmp_file)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def write(self, text):
            pass

    def fail(*args, **kwargs):
        raise OSError("replace failed")

    monkeypatch.setattr(
        chat_store.tempfile, "NamedTemporaryFile", lambda *a, **kw: FakeTmp(),
    )
    monkeypatch.setattr(chat_store.os, "replace", fail)
    monkeypatch.setattr(chat_store.os, "unlink", fail)

    assert chat_store.save_chat(str(path), {"messages": []}) is False
    assert "Не удалось сохранить чат" in caplog.text
    assert "Не удалось удалить временный файл" in caplog.text


def test_append_message_roundtrip(tmp_path):
    path = tmp_path / "chat.json"

    assert chat_store.append_message(str(path), "user", "привет") is True
    assert _messages(path) == [{"role": "user", "content": "привет"}]


def test_append_message_dedupes_identical_retry(tmp_path):
    path = tmp_path / "chat.json"

    chat_store.append_message(str(path), "assistant", "ответ")
    chat_store.append_message(str(path), "assistant", "ответ")

    assert _messages(path) == [{"role": "assistant", "content": "ответ"}]


def test_append_message_truncates_to_max(tmp_path):
    path = tmp_path / "chat.json"

    for i in range(5):
        chat_store.append_message(str(path), "user", f"m{i}", max_messages=3)

    assert [m["content"] for m in _messages(path)] == ["m2", "m3", "m4"]


def test_append_message_replaces_non_list_messages(tmp_path):
    path = tmp_path / "chat.json"
    path.write_text(
        json.dumps({"summary": "s", "messages": "oops"}), encoding="utf-8",
    )

    assert chat_store.append_message(str(path), "user", "x") is True
    assert _messages(path) == [{"role": "user", "content": "x"}]


def test_append_message_concurrent_writes_preserve_all(tmp_path):
    path = tmp_path / "chat.json"

    def append(i):
        return chat_store.append_message(
            str(path), "user", f"m{i}", max_messages=100,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(append, range(20)))

    assert all(results)
    messages = _messages(path)
    assert len(messages) == 20
    assert {m["content"] for m in messages} == {f"m{i}" for i in range(20)}


def test_append_message_creates_missing_file(tmp_path):
    path = tmp_path / "new_chat.json"

    assert chat_store.append_message(str(path), "user", "x") is True
    assert _messages(path) == [{"role": "user", "content": "x"}]
