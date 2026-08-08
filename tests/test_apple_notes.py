"""Unit-тесты для services.apple_notes — JXA-мост и кэш-индекс.

Паттерн: happy path + негативные сценарии + граничные значения (BVA).
osascript замокан; INDEX_FILE перенаправляется в tmp_path.
"""

import json
import time
from types import SimpleNamespace

import pytest

from services import apple_notes as an


def _osascript_ok(stdout):
    return SimpleNamespace(returncode=0, stdout=stdout, stderr="")


def _osascript_fail(stderr):
    return SimpleNamespace(returncode=1, stdout="", stderr=stderr)


@pytest.fixture
def tmp_index(monkeypatch, tmp_path):
    index_file = tmp_path / "notes_index.json"
    monkeypatch.setattr(an, "INDEX_FILE", str(index_file))
    return index_file


@pytest.fixture
def fake_notes(monkeypatch):
    """Заменяет живой список заметок детерминированным JSON."""

    def _make(notes):
        payload = json.dumps([
            {"id": f"id{i}", "name": name, "folder": folder, "updated": ""}
            for i, (name, folder) in enumerate(notes)
        ])
        monkeypatch.setattr(an, "run_osascript", lambda script, timeout=30.0: payload)
        return payload

    return _make


# ─── run_osascript (обёртка subprocess) ───


def test_run_osascript_ok(monkeypatch):
    monkeypatch.setattr(
        an.subprocess, "run", lambda *a, **k: _osascript_ok("результат"),
    )
    assert an.run_osascript("script") == "результат"


def test_run_osascript_nonzero_exit(monkeypatch):
    monkeypatch.setattr(
        an.subprocess, "run", lambda *a, **k: _osascript_fail("execution error: -1743"),
    )
    with pytest.raises(an.AppleNotesError, match="не выполнился"):
        an.run_osascript("script")


def test_run_osascript_tcc_denied(monkeypatch):
    monkeypatch.setattr(
        an.subprocess, "run",
        lambda *a, **k: _osascript_fail("not authorized"),
    )
    with pytest.raises(an.AppleNotesError, match="TCC"):
        an.run_osascript("script")


def test_run_osascript_timeout(monkeypatch):
    def boom(*a, **k):
        raise subprocess_timeout()

    monkeypatch.setattr(an.subprocess, "run", boom)
    with pytest.raises(an.AppleNotesError, match="таймаут"):
        an.run_osascript("script")


def subprocess_timeout():
    import subprocess
    return subprocess.TimeoutExpired("osascript", 30)


def test_run_osascript_oserror(monkeypatch):
    def boom(*a, **k):
        raise OSError("no osascript binary")

    monkeypatch.setattr(an.subprocess, "run", boom)
    with pytest.raises(an.AppleNotesError, match="osascript"):
        an.run_osascript("script")


def test_run_osascript_stdout_error_marker(monkeypatch):
    """returncode=0, но в выводе маркер ошибки — считается ошибкой."""
    monkeypatch.setattr(
        an.subprocess, "run",
        lambda *a, **k: _osascript_ok("can't get note 123"),
    )
    with pytest.raises(an.AppleNotesError, match="не выполнился"):
        an.run_osascript("script")


def test_parse_invalid_json(tmp_index, monkeypatch):
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: "не json вовсе")
    with pytest.raises(an.AppleNotesError, match="Неожиданный ответ"):
        an.refresh_index()


def test_fetch_note_list_non_list_response(tmp_index, monkeypatch):
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: "{}")
    with pytest.raises(an.AppleNotesError, match="формат ответа"):
        an.refresh_index()


def test_is_index_stale_on_getmtime_oserror(tmp_index, fake_notes, monkeypatch):
    fake_notes([("Н", "Ф")])
    an.get_index()

    def boom(path):
        raise OSError("gone")

    monkeypatch.setattr(an.os.path, "getmtime", boom)
    assert an.is_index_stale() is True


def test_read_note_non_dict_response(tmp_index, monkeypatch):
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: "[1, 2]")
    with pytest.raises(an.AppleNotesError, match="формат ответа"):
        an.read_note("id1")


# ─── Кэш-индекс: hit / miss / stale ───


def test_cache_hit_no_osascript_call(tmp_index, fake_notes, monkeypatch):
    fake_notes([("Заметка А", "Папка")])
    assert an.get_index()["notes"][0]["name"] == "Заметка А"
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("osascript не должен вызываться при cache hit"),
    ))
    index = an.get_index()
    assert index["notes"][0]["name"] == "Заметка А"
    assert index["notes"][0]["folder"] == "Папка"
    assert index["notes"][0]["id"] == "id0"


def test_cache_miss_triggers_refresh(tmp_index, fake_notes, monkeypatch):
    calls = []

    def counting(script, timeout=30.0):
        calls.append(script)
        return json.dumps([{"id": "id1", "name": "Н", "folder": "Ф", "updated": ""}])

    monkeypatch.setattr(an, "run_osascript", counting)
    assert an.is_index_stale() is True
    an.get_index()
    assert len(calls) == 1
    assert tmp_index.exists()
    assert json.loads(tmp_index.read_text(encoding="utf-8"))["notes"][0]["name"] == "Н"


def test_stale_index_refreshed(tmp_index, fake_notes, monkeypatch):
    fake_notes([("Старая", "Ф")])
    an.get_index()
    old_mtime = tmp_index.stat().st_mtime
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: json.dumps(
        [{"id": "id9", "name": "Новая", "folder": "Ф", "updated": ""}],
    ))
    an.invalidate_index()
    assert an.is_index_stale() is True
    index = an.get_index()
    assert index["notes"][0]["name"] == "Новая"
    assert old_mtime < tmp_index.stat().st_mtime


def test_corrupted_index_trigger_refresh(tmp_index, fake_notes):
    tmp_index.write_text("{not json", encoding="utf-8")
    assert an.is_index_stale() is True
    fake_notes([("Восстановлена", "Ф")])
    index = an.get_index()
    assert index["notes"][0]["name"] == "Восстановлена"


def test_invalidate_index_removes_file(tmp_index, fake_notes):
    fake_notes([("Н", "Ф")])
    an.get_index()
    assert an.invalidate_index() is True
    assert not tmp_index.exists()
    assert an.invalidate_index() is False


def test_list_notes_folder_filter(tmp_index, fake_notes):
    fake_notes([("А", "Крыло1"), ("Б", "Крыло2"), ("В", "Крыло1")])
    names = [n["name"] for n in an.list_notes(folder="Крыло1")]
    assert names == ["А", "В"]


# ─── read_note ───


def test_read_note_returns_body(tmp_index, monkeypatch):
    def fake(script, timeout=30.0):
        assert 'byId("abc-123")' in script
        return json.dumps({"name": "Заметка", "body": "Текст заметки"})

    monkeypatch.setattr(an, "run_osascript", fake)
    data = an.read_note("abc-123")
    assert data == {"name": "Заметка", "body": "Текст заметки"}


def test_read_note_missing_note(tmp_index, monkeypatch):
    monkeypatch.setattr(
        an, "run_osascript",
        lambda *a, **k: json.dumps({"error": "Can't find object"}),
    )
    with pytest.raises(an.AppleNotesError, match="не найдена"):
        an.read_note("missing")


def test_read_note_empty_id(tmp_index):
    with pytest.raises(an.AppleNotesError, match="корректный ID"):
        an.read_note("")
    with pytest.raises(an.AppleNotesError, match="корректный ID"):
        an.read_note(None)


def test_read_note_escapes_quotes(tmp_index, monkeypatch):
    def fake(script, timeout=30.0):
        assert 'byId("evilid")' in script
        return json.dumps({"name": "N", "body": "B"})

    monkeypatch.setattr(an, "run_osascript", fake)
    an.read_note('evil"id')


# ─── search_notes (BVA) ───


def test_search_matches_name_and_folder_case_insensitive(tmp_index, fake_notes):
    fake_notes([("Шопенгауэр и воля", "Философия"), ("Покупки", "Быт")])
    found = an.search_notes("шопенгауэр")
    assert len(found) == 1
    assert found[0]["name"] == "Шопенгауэр и воля"


def test_search_matches_folder(tmp_index, fake_notes):
    fake_notes([("Заметка 1", "Философия"), ("Заметка 2", "Быт")])
    found = an.search_notes("Философия")
    assert [n["name"] for n in found] == ["Заметка 1"]


def test_search_all_words_required(tmp_index, fake_notes):
    fake_notes([("Идеи для проекта", "Работа"), ("Идеи для отпуска", "Личное")])
    found = an.search_notes("идеи отпуск")
    assert [n["name"] for n in found] == ["Идеи для отпуска"]


def test_search_limit(tmp_index, fake_notes):
    fake_notes([("А1", "Ф"), ("А2", "Ф"), ("А3", "Ф")])
    assert len(an.search_notes("а", limit=2)) == 2


def test_search_empty_query(tmp_index, fake_notes):
    fake_notes([("А", "Ф")])
    with pytest.raises(an.AppleNotesError, match="Пустой"):
        an.search_notes("   ")


def test_search_limit_zero(tmp_index, fake_notes):
    fake_notes([("А", "Ф")])
    with pytest.raises(an.AppleNotesError, match="limit"):
        an.search_notes("а", limit=0)


def test_search_no_results(tmp_index, fake_notes):
    fake_notes([("А", "Ф")])
    assert an.search_notes("ничего_такого") == []


# ─── Форс-обновление и ошибки индекса ───


def test_force_refresh_skips_cache(tmp_index, fake_notes, monkeypatch):
    fake_notes([("Первая", "Ф")])
    an.get_index()
    calls = []

    def counting(script, timeout=30.0):
        calls.append(1)
        return json.dumps([{"id": "id2", "name": "Вторая", "folder": "Ф", "updated": ""}])

    monkeypatch.setattr(an, "run_osascript", counting)
    index = an.get_index(force_refresh=True)
    assert index["notes"][0]["name"] == "Вторая"
    assert len(calls) == 1


def test_jxa_error_payload_raises(tmp_index, fake_notes, monkeypatch):
    monkeypatch.setattr(
        an, "run_osascript",
        lambda *a, **k: json.dumps([{"error": "app not running"}]),
    )
    with pytest.raises(an.AppleNotesError, match="app not running"):
        an.refresh_index()


def test_index_ttl_boundary(tmp_index, fake_notes):
    """BVA: индекс ровно ttl секунд — stale (возраст не < ttl)."""
    fake_notes([("Н", "Ф")])
    an.get_index()
    now = time.time()
    monkeypatch_set_mtime = _set_mtime(tmp_index, now - an.INDEX_TTL_SECONDS)
    assert an.is_index_stale() is True
    monkeypatch_set_mtime()


def _set_mtime(path, ts):
    def apply():
        import os
        os.utime(path, (ts, ts))
    apply()
    return lambda: None
