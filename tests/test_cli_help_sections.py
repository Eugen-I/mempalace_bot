"""Unit tests for cli/help_sections.py"""

import pytest

import cli.help_sections as hs
from cli.utils import C


@pytest.fixture(autouse=True)
def _fake_ai(monkeypatch):
    monkeypatch.setattr(
        hs, "get_current_ai", lambda: ("ollama", "deepseek-r1:14b"),
    )


def test_help_sections_structure():
    assert "1" in hs.HELP_SECTIONS
    assert len(hs.HELP_SECTIONS) == 6
    for key, sec in hs.HELP_SECTIONS.items():
        assert sec["title"]
        assert all(len(item) == 2 for item in sec["items"])


def test_show_help(capsys):
    hs.show_help()
    out = capsys.readouterr().out
    assert "MemPalace CLI | Справка" in out
    assert "Модель: deepseek-r1:14b (ollama)" in out
    assert "Запись и библиотека" in out
    assert "Вся справка разом" in out


def test_show_section_valid(capsys):
    hs.show_section("1")
    out = capsys.readouterr().out
    assert "Запись и библиотека" in out
    assert "Быстрая заметка в my_notes" in out


def test_show_section_unknown_no_output(capsys):
    hs.show_section("99")
    assert capsys.readouterr().out == ""


def test_show_all_help(capsys):
    hs.show_all_help()
    out = capsys.readouterr().out
    assert "Модель: deepseek-r1:14b (ollama)" in out
    for key, sec in hs.HELP_SECTIONS.items():
        assert sec["title"] in out
