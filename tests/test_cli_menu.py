"""Unit tests for cli/menu.py"""

import json
import os

import pytest

import cli.menu as menu


@pytest.fixture
def chats_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(menu, "CHATS_DIR", str(tmp_path / "chats"))
    os.makedirs(menu.CHATS_DIR, exist_ok=True)
    return menu.CHATS_DIR


def test_list_chats_no_dir(chats_dir):
    assert menu.list_chats() == []


def test_list_chats_missing_dir(monkeypatch):
    monkeypatch.setattr(menu, "CHATS_DIR", "/nonexistent_xyz")
    assert menu.list_chats() == []


def test_list_chats_sorted_by_mtime_desc(chats_dir, monkeypatch):
    for name in ("b.json", "a.json", "x.txt"):
        p = os.path.join(chats_dir, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write("{}")
    b = os.path.join(chats_dir, "b.json")
    a = os.path.join(chats_dir, "a.json")
    os.utime(b, (1000, 1000))
    os.utime(a, (2000, 2000))
    assert menu.list_chats() == ["a.json", "b.json"]


def test_load_chat_missing_returns_empty():
    assert menu.load_chat("/nonexistent/chat.json") == {
        "summary": "", "messages": [], "summaries": [],
    }


def test_load_chat_dict(tmp_path):
    path = tmp_path / "chat.json"
    path.write_text(json.dumps({"summary": "s", "messages": [], "summaries": []}))
    assert menu.load_chat(str(path))["summary"] == "s"


def test_load_chat_list_migrates(tmp_path):
    path = tmp_path / "chat.json"
    path.write_text(json.dumps([{"role": "user", "content": "hi"}]))
    data = menu.load_chat(str(path))
    assert data == {
        "summary": "", "messages": [{"role": "user", "content": "hi"}],
        "summaries": [],
    }
    assert json.loads(path.read_text())["messages"] == [{"role": "user", "content": "hi"}]


def test_save_chat_ok(tmp_path):
    path = tmp_path / "chat.json"
    menu.save_chat(str(path), {"summary": "x"})
    assert json.loads(path.read_text(encoding="utf-8")) == {"summary": "x"}


def test_save_chat_error(capsys):
    menu.save_chat("/nonexistent_dir_xyz/chat.json", {})
    out = capsys.readouterr().out
    assert "Ошибка сохранения чата" in out


def test_create_new_chat_auto_name(chats_dir, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    path = menu.create_new_chat()
    assert os.path.basename(path).startswith("ch_chat_")
    assert os.path.exists(path)


def test_create_new_chat_custom_name(chats_dir, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda prompt: "My Chat")
    path = menu.create_new_chat()
    assert os.path.basename(path) == "ch_My_Chat.json"
    assert os.path.exists(path)
    assert "Создан чат" in capsys.readouterr().out
