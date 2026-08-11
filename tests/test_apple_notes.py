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
        items = []
        for i, entry in enumerate(notes):
            items.append({
                "id": f"id{i}", "name": entry[0], "folder": entry[1],
                "preview": entry[2] if len(entry) > 2 else "", "updated": "",
            })
        payload = json.dumps(items)
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
    fake_notes([("Идеи для проекта", "Работа", ""), ("Идеи для отпуска", "Личное", "")])
    found = an.search_notes("идеи отпуск")
    assert [n["name"] for n in found] == ["Идеи для отпуска", "Идеи для проекта"]


def test_search_matches_body_text(tmp_index, fake_notes):
    fake_notes([
        ("Покупки", "Быт", "Вчера купил Шопенгауэра в букинистике"),
        ("Список дел", "Быт", ""),
    ])
    found = an.search_notes("шопенгауэра")
    assert [n["name"] for n in found] == ["Покупки"]


def test_search_ranks_name_higher_than_body(tmp_index, fake_notes):
    fake_notes([
        ("Шопенгауэр и воля", "Философия", "Разные мысли"),
        ("Заметка 1", "Философия", "Пишу о Шопенгауэре каждый день"),
    ])
    found = an.search_notes("шопенгауэр")
    assert [n["name"] for n in found] == ["Шопенгауэр и воля", "Заметка 1"]


def test_search_more_word_hits_first(tmp_index, fake_notes):
    fake_notes([
        ("Идеи", "Личное", "Планирую отпуск в горах"),
        ("Идеи для отпуска", "Личное", ""),
    ])
    found = an.search_notes("идеи отпуск")
    assert [n["name"] for n in found] == ["Идеи для отпуска", "Идеи"]


def test_search_snippet_around_match(tmp_index, fake_notes):
    body = ("Сегодня читал про " + "очень длинное предложение о философии " * 5
            + "Шопенгауэр был прав")
    fake_notes([("Заметка", "Ф", body)])
    found = an.search_notes("шопенгауэр")
    snippet = found[0]["snippet"]
    assert "шопенгауэр" in snippet.lower()
    assert len(snippet) <= an.SNIPPET_MAX_CHARS + 2


def test_search_snippet_short_body_not_trimmed(tmp_index, fake_notes):
    fake_notes([("Заметка", "Ф", "Короткий текст про шопенгауэра")])
    found = an.search_notes("шопенгауэра")
    assert found[0]["snippet"] == "Короткий текст про шопенгауэра"


def test_search_snippet_missing_preview(tmp_index, fake_notes):
    fake_notes([("Шопенгауэр", "Ф", "")])
    found = an.search_notes("шопенгауэр")
    assert found[0]["snippet"] == ""


def test_search_preview_trimmed_to_limit(tmp_index, fake_notes):
    long_body = "слово " * 1000
    fake_notes([("Заметка", "Ф", long_body)])
    index = an.get_index()
    assert len(index["notes"][0]["preview"]) <= an.PREVIEW_MAX_CHARS


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


# ─── Graceful: превью тел не должно ломать индекс ───


def test_preview_timeout_falls_back_to_basic(tmp_index, monkeypatch):
    """Если листинг с превью упал — повторяем без превью, поиск работает."""
    scripts = []

    def fake(script, timeout=30.0):
        scripts.append(script)
        if an._JXA_LIST_NOTES in script:
            raise an.AppleNotesError("osascript превысил таймаут")
        return json.dumps([
            {"id": "id1", "name": "Шопенгауэр", "folder": "Ф", "preview": "", "updated": ""},
        ])

    monkeypatch.setattr(an, "run_osascript", fake)
    index = an.get_index()
    assert index["notes"][0]["preview"] == ""
    assert an._JXA_LIST_NOTES_BASIC in scripts[1]
    assert an.search_notes("шопенгауэр")[0]["name"] == "Шопенгауэр"


def test_fetch_skips_non_dict_items(tmp_index, monkeypatch):
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: json.dumps(
        ["мусор", {"id": "id1", "name": "Н", "folder": "Ф", "preview": "", "updated": ""}],
    ))
    index = an.get_index()
    assert [n["id"] for n in index["notes"]] == ["id1"]


def test_search_snippet_trimmed_both_sides(tmp_index, fake_notes):
    body = "начало " + "x" * 500 + " Шопенгауэр " + "y" * 500 + " конец"
    fake_notes([("Заметка", "Ф", body)])
    snippet = an.search_notes("шопенгауэр")[0]["snippet"]
    assert snippet.startswith("…") and snippet.endswith("…")


# ─── detect_and_validate_language ───


def test_lang_detects_ru():
    assert an.detect_and_validate_language("Обычная заметка на русском") == "ru"


def test_lang_detects_de_by_diacritics():
    assert an.detect_and_validate_language("Schöne Grüße aus München") == "de"
    assert an.detect_and_validate_language("die Äpfel und Öl") == "de"


def test_lang_rejects_chinese():
    with pytest.raises(an.AppleNotesError, match="азиатские"):
        an.detect_and_validate_language("这是一条中文笔记")


def test_lang_rejects_japanese():
    with pytest.raises(an.AppleNotesError, match="азиатские"):
        an.detect_and_validate_language("こんにちは")
    with pytest.raises(an.AppleNotesError, match="азиатские"):
        an.detect_and_validate_language("カタカナ")


def test_lang_rejects_korean():
    with pytest.raises(an.AppleNotesError, match="азиатские"):
        an.detect_and_validate_language("한국어 메모")


def test_lang_rejects_cjk_mixed_with_ru():
    with pytest.raises(an.AppleNotesError, match="азиатские"):
        an.detect_and_validate_language("Заметка с 中文 символами")


def test_lang_empty_and_non_str():
    assert an.detect_and_validate_language("") == "ru"
    with pytest.raises(an.AppleNotesError, match="строкой"):
        an.detect_and_validate_language(123)


# ─── create_note ───


def test_create_note_ok(tmp_index, monkeypatch):
    def fake(script, timeout=30.0):
        assert "{target}" not in script and "{title}" not in script and "{body}" not in script
        assert 'name: "Моя заметка"' in script
        assert "app.notes" in script
        return json.dumps({"id": "new1", "name": "Моя заметка"})

    monkeypatch.setattr(an, "run_osascript", fake)
    assert an.create_note("Моя заметка", "Текст") == "new1"


def test_create_note_escapes_quotes_and_newlines(tmp_index, monkeypatch):
    def fake(script, timeout=30.0):
        assert 'name: "Заметка \\"важная\\""' in script
        assert 'body: "строка 1\\nстрока 2"' in script
        return json.dumps({"id": "n1", "name": "x"})

    monkeypatch.setattr(an, "run_osascript", fake)
    assert an.create_note('Заметка "важная"', "строка 1\nстрока 2") == "n1"


def test_create_note_in_folder(tmp_index, monkeypatch):
    def fake(script, timeout=30.0):
        assert 'app.folders.byName("Философия")' in script
        return json.dumps({"id": "n1", "name": "x"})

    monkeypatch.setattr(an, "run_osascript", fake)
    assert an.create_note("Название", folder="Философия") == "n1"


def test_create_note_empty_title(tmp_index):
    with pytest.raises(an.AppleNotesError, match="заголовок"):
        an.create_note("   ")
    with pytest.raises(an.AppleNotesError, match="заголовок"):
        an.create_note(None)


def test_create_note_empty_folder(tmp_index):
    with pytest.raises(an.AppleNotesError, match="папки"):
        an.create_note("Название", folder="   ")


def test_create_note_rejects_cjk(tmp_index):
    with pytest.raises(an.AppleNotesError, match="азиатские"):
        an.create_note("中文标题", "текст")


def test_create_note_jxa_error(tmp_index, monkeypatch):
    monkeypatch.setattr(
        an, "run_osascript",
        lambda *a, **k: json.dumps({"error": "Can't find folder"}),
    )
    with pytest.raises(an.AppleNotesError, match="создать"):
        an.create_note("Название", folder="Нет такой")


def test_create_note_non_dict_response(tmp_index, monkeypatch):
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: "[1, 2]")
    with pytest.raises(an.AppleNotesError, match="формат ответа"):
        an.create_note("Название")


def test_create_note_invalidates_index(tmp_index, fake_notes, monkeypatch):
    fake_notes([("Старая", "Ф")])
    an.get_index()
    assert tmp_index.exists()
    monkeypatch.setattr(
        an, "run_osascript",
        lambda *a, **k: json.dumps({"id": "n9", "name": "x"}),
    )
    an.create_note("Новая")
    assert not tmp_index.exists()


# ─── update_note ───


def _update_osascript(current_body="Старый текст"):
    def fake(script, timeout=30.0):
        if "plaintext()" in script:
            return json.dumps({"name": "Заметка", "body": current_body})
        return json.dumps({"id": "n1", "name": "Заметка"})

    return fake


def test_update_note_append_ok(tmp_index, monkeypatch):
    monkeypatch.setattr(an, "run_osascript", _update_osascript("Старый текст"))
    result = an.update_note("n1", append_text="Дополнение")
    assert result["body"] == "Старый текст\nДополнение"
    assert result["id"] == "n1"


def test_update_note_append_escapes_body(tmp_index, monkeypatch):
    captured = {}

    def fake(script, timeout=30.0):
        if "plaintext()" in script:
            return json.dumps({"name": "N", "body": "база"})
        captured["script"] = script
        return json.dumps({"id": "n1", "name": "N"})

    monkeypatch.setattr(an, "run_osascript", fake)
    an.update_note("n1", append_text='дозапись "важная"')
    assert 'n.body = "база\\nдозапись \\"важная\\""' in captured["script"]


def test_update_note_replace_ok(tmp_index, monkeypatch):
    def fake(script, timeout=30.0):
        assert an._JXA_READ_NOTE not in script
        return json.dumps({"id": "n1", "name": "N"})

    monkeypatch.setattr(an, "run_osascript", fake)
    result = an.update_note("n1", replace_text="Полностью новый текст")
    assert result["body"] == "Полностью новый текст"


def test_update_note_both_modes_rejected(tmp_index):
    with pytest.raises(an.AppleNotesError, match="только один"):
        an.update_note("n1", append_text="a", replace_text="b")


def test_update_note_no_text_rejected(tmp_index):
    with pytest.raises(an.AppleNotesError, match="дозаписи"):
        an.update_note("n1")


def test_update_note_empty_append_rejected(tmp_index):
    with pytest.raises(an.AppleNotesError, match="не должен быть пустым"):
        an.update_note("n1", append_text="  ")


def test_update_note_rejects_cjk(tmp_index):
    with pytest.raises(an.AppleNotesError, match="азиатские"):
        an.update_note("n1", append_text="追加テキスト")
    with pytest.raises(an.AppleNotesError, match="азиатские"):
        an.update_note("n1", replace_text="新文本")


def test_update_note_empty_id(tmp_index):
    with pytest.raises(an.AppleNotesError, match="корректный ID"):
        an.update_note("")


def test_update_note_missing_note(tmp_index, monkeypatch):
    def fake(script, timeout=30.0):
        if "plaintext()" in script:
            return json.dumps({"error": "Can't find object"})
        return json.dumps({"id": "n1"})

    monkeypatch.setattr(an, "run_osascript", fake)
    with pytest.raises(an.AppleNotesError, match="не найдена"):
        an.update_note("missing", append_text="x")


def test_update_note_jxa_error(tmp_index, monkeypatch):
    monkeypatch.setattr(
        an, "run_osascript",
        lambda *a, **k: json.dumps({"error": "Can't set body"}),
    )
    with pytest.raises(an.AppleNotesError, match="обновить"):
        an.update_note("n1", replace_text="x")


def test_update_note_invalidates_index(tmp_index, fake_notes, monkeypatch):
    fake_notes([("Заметка", "Ф")])
    an.get_index()
    monkeypatch.setattr(an, "run_osascript", _update_osascript())
    an.update_note("n1", append_text="x")
    assert not tmp_index.exists()


# ─── delete_note ───


def test_delete_note_ok(tmp_index, monkeypatch):
    def fake(script, timeout=30.0):
        assert 'byName("Recently Deleted")' in script
        return json.dumps({"id": "n1", "deleted": True})

    monkeypatch.setattr(an, "run_osascript", fake)
    assert an.delete_note("n1") is True


def test_delete_note_empty_id(tmp_index):
    with pytest.raises(an.AppleNotesError, match="корректный ID"):
        an.delete_note("")


def test_delete_note_jxa_error(tmp_index, monkeypatch):
    monkeypatch.setattr(
        an, "run_osascript",
        lambda *a, **k: json.dumps({"error": "Can't find note"}),
    )
    with pytest.raises(an.AppleNotesError, match="удалить"):
        an.delete_note("nope")


def test_delete_note_invalidates_index(tmp_index, fake_notes, monkeypatch):
    fake_notes([("Заметка", "Ф")])
    an.get_index()
    monkeypatch.setattr(
        an, "run_osascript",
        lambda *a, **k: json.dumps({"id": "n1", "deleted": True}),
    )
    an.delete_note("n1")
    assert not tmp_index.exists()


# ─── list_folders ───


def test_list_folders_ok(tmp_index, monkeypatch):
    monkeypatch.setattr(
        an, "run_osascript",
        lambda *a, **k: json.dumps(["Философия", "Личное", "Быт"]),
    )
    assert an.list_folders() == ["Философия", "Личное", "Быт"]


def test_list_folders_filters_recently_deleted_in_script(tmp_index, monkeypatch):
    def fake(script, timeout=30.0):
        assert 'name === "Recently Deleted"' in script
        return json.dumps(["Философия"])

    monkeypatch.setattr(an, "run_osascript", fake)
    assert an.list_folders() == ["Философия"]


def test_list_folders_non_list_response(tmp_index, monkeypatch):
    monkeypatch.setattr(an, "run_osascript", lambda *a, **k: "{}")
    with pytest.raises(an.AppleNotesError, match="формат ответа"):
        an.list_folders()


# ─── move_note ───


def test_move_note_ok(tmp_index, monkeypatch):
    def fake(script, timeout=30.0):
        assert 'app.folders.byName("Личное")' in script
        return json.dumps({"id": "n1", "folder": "Личное"})

    monkeypatch.setattr(an, "run_osascript", fake)
    assert an.move_note("n1", "Личное") == {"id": "n1", "folder": "Личное"}


def test_move_note_escapes_folder(tmp_index, monkeypatch):
    def fake(script, timeout=30.0):
        assert 'byName("Папка \\"особая\\"")' in script
        return json.dumps({"id": "n1", "folder": "x"})

    monkeypatch.setattr(an, "run_osascript", fake)
    an.move_note("n1", 'Папка "особая"')


def test_move_note_empty_folder(tmp_index):
    with pytest.raises(an.AppleNotesError, match="папку назначения"):
        an.move_note("n1", "  ")


def test_move_note_to_recently_deleted_blocked(tmp_index):
    with pytest.raises(an.AppleNotesError, match="удаление заметки"):
        an.move_note("n1", "Recently Deleted")


def test_move_note_jxa_error(tmp_index, monkeypatch):
    monkeypatch.setattr(
        an, "run_osascript",
        lambda *a, **k: json.dumps({"error": "Can't find folder"}),
    )
    with pytest.raises(an.AppleNotesError, match="переместить"):
        an.move_note("n1", "Нет такой")


def test_move_note_invalidates_index(tmp_index, fake_notes, monkeypatch):
    fake_notes([("Заметка", "Ф")])
    an.get_index()
    monkeypatch.setattr(
        an, "run_osascript",
        lambda *a, **k: json.dumps({"id": "n1", "folder": "Другая"}),
    )
    an.move_note("n1", "Другая")
    assert not tmp_index.exists()
