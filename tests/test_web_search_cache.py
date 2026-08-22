"""Тесты services/web_search_cache.py — кэш результатов поиска.

Покрытие: сохранение/загрузка, TTL-очистка, список, границы.
"""
import json
import time

import pytest

import services.web_search_cache as wsc


@pytest.fixture(autouse=True)
def _cache_dir(tmp_path, monkeypatch):
    d = tmp_path / "web_search_cache"
    monkeypatch.setattr(wsc, "WEB_SEARCH_CACHE_DIR", d)
    d.mkdir()
    return d


# ─── save_web_search ───


def test_save_web_search_creates_file(_cache_dir):
    sid = wsc.save_web_search("вопрос", [{"text": "т", "url": "https://a.ru"}])
    assert (_cache_dir / f"{sid}.json").exists()
    data = json.loads((_cache_dir / f"{sid}.json").read_text(encoding="utf-8"))
    assert data["id"] == sid
    assert data["query"] == "вопрос"
    assert data["sources"][0]["text"] == "т"
    assert data["sources"][0]["title"] == ""


def test_save_web_search_with_title(_cache_dir):
    sid = wsc.save_web_search(
        "q", [{"text": "т", "url": "https://a.ru", "title": "Заголовок"}]
    )
    data = json.loads((_cache_dir / f"{sid}.json").read_text(encoding="utf-8"))
    assert data["sources"][0]["title"] == "Заголовок"


def test_save_web_search_returns_12char_id(_cache_dir):
    sid = wsc.save_web_search("q", [])
    assert len(sid) == 12


# ─── save_web_search_with_id ───


def test_save_with_id_uses_given_id(_cache_dir):
    wsc.save_web_search_with_id("abc12345", "вопрос", [{"text": "т", "url": "u"}])
    assert (_cache_dir / "abc12345.json").exists()


# ─── load_web_search ───


def test_load_web_search_ok(_cache_dir):
    sid = wsc.save_web_search("вопрос", [{"text": "т", "url": "u"}], "саммари")
    data = wsc.load_web_search(sid)
    assert data["query"] == "вопрос"
    assert data["ai_summary"] == "саммари"


def test_load_web_search_missing_returns_none(_cache_dir):
    assert wsc.load_web_search("nope") is None


def test_load_web_search_corrupt_file_returns_none(_cache_dir):
    (_cache_dir / "bad.json").write_text("{не json", encoding="utf-8")
    assert wsc.load_web_search("bad") is None


# ─── cleanup_old_cache ───


def test_cleanup_removes_old_files(_cache_dir):
    old = _cache_dir / "old.json"
    old.write_text('{}', encoding="utf-8")
    old_time = time.time() - wsc.CACHE_TTL - 10
    import os

    os.utime(old, (old_time, old_time))
    fresh = _cache_dir / "fresh.json"
    fresh.write_text('{}', encoding="utf-8")

    wsc.cleanup_old_cache()

    assert not old.exists()
    assert fresh.exists()


def test_cleanup_keeps_fresh_files(_cache_dir):
    fresh = _cache_dir / "fresh.json"
    fresh.write_text('{}', encoding="utf-8")
    wsc.cleanup_old_cache()
    assert fresh.exists()


def test_cleanup_ignores_non_json(_cache_dir):
    (_cache_dir / "note.txt").write_text("x", encoding="utf-8")
    wsc.cleanup_old_cache()
    assert (_cache_dir / "note.txt").exists()


# ─── list_cached_searches ───


def test_list_cached_searches_empty(_cache_dir):
    assert wsc.list_cached_searches() == []


def test_list_cached_searches_parses_files(_cache_dir):
    wsc.save_web_search_with_id(
        "aaa11111", "первый", [{"text": "т1", "url": "u1"}], "с"
    )
    wsc.save_web_search_with_id(
        "bbb22222", "второй", [{"text": "т1", "url": "u1"}, {"text": "т2", "url": "u2"}], "с"
    )
    result = wsc.list_cached_searches()
    assert len(result) == 2
    by_id = {r["id"]: r for r in result}
    assert by_id["aaa11111"]["query"] == "первый"
    assert by_id["aaa11111"]["source_count"] == 1
    assert by_id["bbb22222"]["source_count"] == 2


def test_list_cached_searches_sorted_by_timestamp_desc(_cache_dir):
    wsc.save_web_search_with_id("old11111", "старый", [], "")
    time.sleep(0.01)
    wsc.save_web_search_with_id("new22222", "новый", [], "")
    result = wsc.list_cached_searches()
    assert result[0]["id"] == "new22222"
    assert result[1]["id"] == "old11111"


def test_list_cached_searches_skips_corrupt(_cache_dir):
    (_cache_dir / "bad.json").write_text("мусор", encoding="utf-8")
    wsc.save_web_search_with_id("good11111", "ок", [], "")
    result = wsc.list_cached_searches()
    assert len(result) == 1
    assert result[0]["id"] == "good11111"


def test_cleanup_stat_error_ignored(_cache_dir, monkeypatch):
    class BoomFile:
        def stat(self):
            raise OSError("gone")

        def unlink(self):
            raise AssertionError("unlink must not be called")

    class FakeDir:
        def glob(self, pattern):
            return iter([BoomFile()])

    monkeypatch.setattr(wsc, "WEB_SEARCH_CACHE_DIR", FakeDir())
    wsc.cleanup_old_cache()
