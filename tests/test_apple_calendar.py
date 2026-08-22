"""Unit-тесты для services.apple_calendar — Apple Calendar через osascript.

Паттерн: happy path + негативные сценарии + граничные значения (BVA).
subprocess замокан; проверяются создание события, экранирование,
обработка таймаутов/TCC и парсинг списка событий.
"""

import subprocess

import pytest

from services import apple_calendar as ac


def _proc(rc=0, stdout="", stderr=""):
    return type("P", (), {
        "returncode": rc, "stdout": stdout, "stderr": stderr,
    })()


def _mock_run(monkeypatch, result=None, side_effect=None):
    def _run(cmd, **kw):
        if side_effect:
            raise side_effect
        return result

    monkeypatch.setattr(ac.subprocess, "run", _run)


# ─── create_calendar_event ───

def test_create_happy(monkeypatch):
    _mock_run(monkeypatch, _proc(stdout="EVENT-123"))
    ev_id = ac.create_calendar_event("Напоминание", 1700000000.0, notes="n")
    assert ev_id == "EVENT-123"


def test_create_escapes_quotes(monkeypatch):
    captured = {}

    def _run(cmd, **kw):
        captured["cmd"] = cmd
        return _proc(stdout="EV-1")

    monkeypatch.setattr(ac.subprocess, "run", _run)
    ac.create_calendar_event('Текст "с кавычками"', 1700000000.0)
    script = captured["cmd"][-1]
    # AppleScript экранирует кавычки удвоением: " -> ""
    assert 'summary:"Текст ""с кавычками"""' in script


def test_create_min_duration_clamped(monkeypatch):
    captured = {}

    def _run(cmd, **kw):
        captured["cmd"] = cmd
        return _proc(stdout="EV-1")

    monkeypatch.setattr(ac.subprocess, "run", _run)
    ac.create_calendar_event("T", 1700000000.0, duration_minutes=0)
    script = captured["cmd"][-1]
    assert "end date:date" in script  # 1 минута вместо 0


def test_create_timeout(monkeypatch):
    _mock_run(
        monkeypatch,
        side_effect=subprocess.TimeoutExpired("osascript", 20),
    )
    with pytest.raises(ac.AppleCalendarError, match="не ответил"):
        ac.create_calendar_event("T", 1700000000.0)


def test_create_file_not_found(monkeypatch):
    _mock_run(monkeypatch, side_effect=FileNotFoundError("no osascript"))
    with pytest.raises(ac.AppleCalendarError, match="не найден"):
        ac.create_calendar_event("T", 1700000000.0)


def test_create_nonzero_exit(monkeypatch):
    _mock_run(monkeypatch, _proc(rc=1, stderr="syntax error at line 3"))
    with pytest.raises(ac.AppleCalendarError, match="не выполнил"):
        ac.create_calendar_event("T", 1700000000.0)


def test_create_tcc_marker_in_stderr(monkeypatch):
    _mock_run(monkeypatch, _proc(rc=0, stderr="osascript не авторизован TCC"))
    with pytest.raises(ac.AppleCalendarError):
        ac.create_calendar_event("T", 1700000000.0)


# ─── list_upcoming_events ───

_LIST_SAMPLE = (
    "ID-B|Встреча B|08.08.2026 14:00:00|08.08.2026 15:00:00\n"
    "ID-A|Встреча A|08.08.2026 10:00:00|08.08.2026 11:00:00\n"
)


def test_list_happy_sorted(monkeypatch):
    _mock_run(monkeypatch, _proc(stdout=_LIST_SAMPLE))
    evs = ac.list_upcoming_events(days=7)
    assert [e["summary"] for e in evs] == ["Встреча A", "Встреча B"]
    assert evs[0]["id"] == "ID-A"
    assert evs[0]["start"] == "2026-08-08T10:00:00"


def test_list_empty(monkeypatch):
    _mock_run(monkeypatch, _proc(stdout=""))
    assert ac.list_upcoming_events() == []


def test_list_skips_error_lines(monkeypatch):
    out = "ID-A|Ок|08.08.2026 10:00:00|08.08.2026 11:00:00\n" \
          "ERR: что-то сломалось\n" \
          "ID-B|Битый|недата|недата2\n" \
          "короткая_строка\n"
    _mock_run(monkeypatch, _proc(stdout=out))
    evs = ac.list_upcoming_events()
    assert len(evs) == 2  # ERR- и битые строки пропущены, "Битый" с пустой датой есть
    by_summary = {e["summary"]: e for e in evs}
    assert by_summary["Ок"]["start"] == "2026-08-08T10:00:00"
    assert by_summary["Битый"]["start"] == ""


def test_list_bad_date_yields_empty_iso(monkeypatch):
    out = "ID-B|Битый|недата|недата2\n"
    _mock_run(monkeypatch, _proc(stdout=out))
    evs = ac.list_upcoming_events()
    assert evs[0]["start"] == ""
    assert evs[0]["end"] == ""


def test_list_limit_clamped(monkeypatch):
    out = _LIST_SAMPLE
    _mock_run(monkeypatch, _proc(stdout=out))
    assert len(ac.list_upcoming_events(limit=0)) == 1
    assert len(ac.list_upcoming_events(limit=1)) == 1


def test_list_days_clamped(monkeypatch):
    captured = {}

    def _run(cmd, **kw):
        captured["cmd"] = cmd
        return _proc(stdout="")

    monkeypatch.setattr(ac.subprocess, "run", _run)
    ac.list_upcoming_events(days=0)
    assert "0 * days" not in captured["cmd"][-1]


def test_list_timeout(monkeypatch):
    _mock_run(
        monkeypatch,
        side_effect=subprocess.TimeoutExpired("osascript", 45),
    )
    with pytest.raises(ac.AppleCalendarError, match="не ответил"):
        ac.list_upcoming_events()


# ─── _parse_as_date ───

def test_parse_as_date_formats():
    from datetime import datetime

    assert ac._parse_as_date("08.08.2026 10:00:00") == datetime(2026, 8, 8, 10, 0, 0)
    assert ac._parse_as_date("08.08.2026") == datetime(2026, 8, 8)
    assert ac._parse_as_date("мусор") is None
    assert ac._parse_as_date("") is None


# ─── _looks_like_error ───

def test_looks_like_error_markers():
    assert ac._looks_like_error("TCC: not authorized")
    assert ac._looks_like_error("application isn't running")
    assert not ac._looks_like_error("ok output")
    assert not ac._looks_like_error("")
