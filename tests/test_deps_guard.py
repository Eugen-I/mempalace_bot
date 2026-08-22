"""Unit-тесты services/deps_guard.py.

Паттерн: happy path + негативы + границы (BVA), всё через monkeypatch —
без сети и без реального pip.
"""

import logging

import pytest

import services.deps_guard as dg


class _FakeMeta:
    def __init__(self, value):
        self.value = value

    def version(self, package):
        if self.value is None:
            raise dg.PackageNotFoundError(package)
        return self.value


class RecordingLogger(logging.Logger):
    def __init__(self):
        super().__init__("rec")
        self.records = []

    def _log(self, level, msg, args, exc_info=None, extra=None, **kwargs):
        self.records.append((level, msg % args if args else msg))

    def warning(self, msg, *args, **kwargs):
        self._log(logging.WARNING, msg, args)

    def info(self, msg, *args, **kwargs):
        self._log(logging.INFO, msg, args)

    def error(self, msg, *args, **kwargs):
        self._log(logging.ERROR, msg, args)


@pytest.fixture
def monkey_meta(monkeypatch):
    """Подмена установленной версии chromadb; строкой — одна версия,
    списком — последовательность версий (имитация эффекта обновления)."""
    def _set(versions):
        if isinstance(versions, str) or versions is None:
            versions = [versions]
        versions = list(versions)

        def _get(package):
            return versions.pop(0) if versions else None
        monkeypatch.setattr(dg, "_installed_version", _get)
    return _set


# ---------- _parse_version (BVA) ----------


def test_parse_version_plain():
    assert dg._parse_version("1.5.9") == (1, 5, 9)


def test_parse_version_empty_returns_oldest():
    assert dg._parse_version("") == (0, 0, 0)


def test_parse_version_garbage_returns_oldest():
    assert dg._parse_version("unknown") == (0, 0, 0)


def test_parse_version_dev_suffix():
    assert dg._parse_version("1.6.0.dev1") == (1, 6, 0, 1)


def test_parse_version_compare_newer():
    assert dg._parse_version("1.6.0") > dg._parse_version("1.5.9")
    assert dg._parse_version("1.5.10") > dg._parse_version("1.5.9")


# ---------- _installed_version ----------


def test_installed_version_ok(monkeypatch):
    monkeypatch.setattr(
        "importlib.metadata.version", _FakeMeta("1.5.9").version
    )
    assert dg._installed_version() == "1.5.9"


def test_installed_version_not_installed(monkeypatch):
    monkeypatch.setattr(
        "importlib.metadata.version", _FakeMeta(None).version
    )
    assert dg._installed_version() is None


def test_installed_version_metadata_crash_returns_none(monkeypatch):
    def _boom(package):
        raise RuntimeError("metadata broken")
    monkeypatch.setattr("importlib.metadata.version", _boom)
    assert dg._installed_version() is None


# ---------- _parse_version edge cases ----------


def test_parse_version_single_number():
    assert dg._parse_version("123") == (123,)


def test_parse_version_dots_only():
    assert dg._parse_version("...") == (0, 0, 0)


# ---------- check_chromadb_version (replaces auto_update_chromadb) ----------


def test_happy_path_vulnerable_version_warns(monkey_meta):
    """Установлена уязвимая версия < 1.6.0 — логируется предупреждение."""
    monkey_meta("1.5.9")
    log = RecordingLogger()
    result = dg.check_chromadb_version(logger_=log)
    assert result["status"] == "vulnerable"
    assert result["installed"] == "1.5.9"
    assert any("CVE-2026-45829" in msg for level, msg in log.records if level == logging.WARNING)


def test_cve_fixed_version_ok(monkey_meta):
    """Установлена версия >= 1.6.0 — OK, предупреждения нет."""
    monkey_meta("1.6.0")
    log = RecordingLogger()
    result = dg.check_chromadb_version(logger_=log)
    assert result["status"] == "ok"
    assert result["installed"] == "1.6.0"
    assert not any(level == logging.WARNING for level, _ in log.records)


def test_newer_version_ok(monkey_meta):
    """Установлена версия новее 1.6.0 — OK."""
    monkey_meta("1.7.0")
    log = RecordingLogger()
    result = dg.check_chromadb_version(logger_=log)
    assert result["status"] == "ok"
    assert result["installed"] == "1.7.0"


def test_not_installed_no_warning(monkey_meta):
    """chromadb не установлен — пропускаем без предупреждений."""
    monkey_meta(None)
    log = RecordingLogger()
    result = dg.check_chromadb_version(logger_=log)
    assert result["status"] == "not_installed"
    assert result["installed"] is None
    assert not any(level == logging.WARNING for level, _ in log.records)


def test_metadata_crash_returns_not_installed(monkeypatch):
    """Сломанные метаданные не ломают запуск бота."""
    def _boom(package):
        raise RuntimeError("broken metadata")
    monkeypatch.setattr("importlib.metadata.version", _boom)
    result = dg.check_chromadb_version(logger_=RecordingLogger())
    assert result["status"] == "not_installed"


def test_dev_suffix_version_parsed():
    """Dev-версии корректно парсятся для сравнения."""
    assert dg._parse_version("1.6.0.dev1") == (1, 6, 0, 1)
    assert dg._parse_version("1.6.0.dev1") > dg._parse_version("1.5.9")