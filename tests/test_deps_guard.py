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


class _FakeUrlopen:
    def __init__(self, payload, exc=None):
        self.payload = payload
        self.exc = exc

    def __enter__(self):
        if self.exc:
            raise self.exc
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.payload


class _FakeProc:
    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stderr = stderr


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


@pytest.fixture
def monkey_latest(monkeypatch):
    def _set(version_value):
        monkeypatch.setattr(dg, "_latest_version", lambda package: version_value)
    return _set


@pytest.fixture
def monkey_pip(monkeypatch):
    calls = []

    def _set(returncode=0, stderr=""):
        def _run(package, logger_):
            calls.append(package)
            return returncode == 0
        monkeypatch.setattr(dg, "_pip_upgrade", _run)
    return _set, calls


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


# ---------- _latest_version ----------


def test_latest_version_ok(monkeypatch):
    payload = b'{"info": {"version": "1.6.0"}}'
    monkeypatch.setattr(dg.urllib.request, "urlopen", lambda url, timeout: _FakeUrlopen(payload))
    assert dg._latest_version() == "1.6.0"


def test_latest_version_network_error_returns_none(monkeypatch):
    def _boom(url, timeout):
        raise TimeoutError("no net")
    monkeypatch.setattr(dg.urllib.request, "urlopen", _boom)
    assert dg._latest_version() is None


def test_latest_version_malformed_json_returns_none(monkeypatch):
    monkeypatch.setattr(
        dg.urllib.request, "urlopen",
        lambda url, timeout: _FakeUrlopen(b"not json {"),
    )
    assert dg._latest_version() is None


def test_latest_version_missing_info_key_returns_none(monkeypatch):
    monkeypatch.setattr(
        dg.urllib.request, "urlopen",
        lambda url, timeout: _FakeUrlopen(b'{"nope": {}}'),
    )
    assert dg._latest_version() is None


# ---------- _pip_upgrade ----------


def test_pip_upgrade_success(monkeypatch):
    monkeypatch.setattr(dg.subprocess, "run", lambda *a, **kw: _FakeProc(0))
    assert dg._pip_upgrade("chromadb", RecordingLogger()) is True


def test_pip_upgrade_failure(monkeypatch):
    monkeypatch.setattr(
        dg.subprocess, "run", lambda *a, **kw: _FakeProc(1, "boom")
    )
    assert dg._pip_upgrade("chromadb", RecordingLogger()) is False


def test_pip_upgrade_timeout(monkeypatch):
    def _boom(*a, **kw):
        raise dg.subprocess.TimeoutExpired("pip", 1)
    monkeypatch.setattr(dg.subprocess, "run", _boom)
    assert dg._pip_upgrade("chromadb", RecordingLogger()) is False


def test_pip_upgrade_unexpected_error(monkeypatch):
    def _boom(*a, **kw):
        raise OSError("pip is broken")
    monkeypatch.setattr(dg.subprocess, "run", _boom)
    assert dg._pip_upgrade("chromadb", RecordingLogger()) is False


def test_pip_upgrade_uses_fixed_command(monkeypatch):
    captured = {}

    def _run(cmd, **kw):
        captured["cmd"] = cmd
        return _FakeProc(0)
    monkeypatch.setattr(dg.subprocess, "run", _run)
    dg._pip_upgrade("chromadb", RecordingLogger())
    assert captured["cmd"] == [dg.sys.executable, "-m", "pip", "install", "--upgrade", "chromadb"]


# ---------- auto_update_chromadb ----------


def test_happy_path_upgrades_and_cve_closed(monkey_meta, monkey_latest, monkey_pip):
    monkey_meta(["1.5.9", "1.6.0"])
    monkey_latest("1.6.0")
    set_pip, calls = monkey_pip
    set_pip(0)
    log = RecordingLogger()
    result = dg.auto_update_chromadb(logger_=log)
    assert result["status"] == "upgraded"
    assert calls == ["chromadb"]
    assert result["installed"] == "1.5.9"
    assert result["installed_after"] == "1.6.0"
    assert not any(level == logging.WARNING for level, _ in log.records)


def test_upgrade_to_still_unfixed_version_warns(monkey_meta, monkey_latest, monkey_pip):
    monkey_meta(["1.5.8", "1.5.9"])
    monkey_latest("1.5.9")
    set_pip, calls = monkey_pip
    set_pip(0)
    log = RecordingLogger()
    result = dg.auto_update_chromadb(logger_=log)
    assert result["status"] == "upgraded"
    assert calls == ["chromadb"]
    assert any("CVE-2026-45829" in msg for level, msg in log.records if level == logging.WARNING)


def test_up_to_date_no_upgrade(monkey_meta, monkey_latest, monkey_pip):
    monkey_meta("1.6.0")
    monkey_latest("1.6.0")
    set_pip, calls = monkey_pip
    set_pip(0)
    result = dg.auto_update_chromadb(logger_=RecordingLogger())
    assert result["status"] == "up_to_date"
    assert calls == []


def test_installed_newer_than_latest_no_upgrade(monkey_meta, monkey_latest, monkey_pip):
    monkey_meta("1.7.0")
    monkey_latest("1.6.0")
    set_pip, calls = monkey_pip
    set_pip(0)
    result = dg.auto_update_chromadb(logger_=RecordingLogger())
    assert result["status"] == "up_to_date"
    assert calls == []


def test_network_failure_keeps_version_and_warns(monkey_meta, monkey_latest, monkey_pip):
    monkey_meta("1.5.9")
    monkey_latest(None)
    set_pip, calls = monkey_pip
    set_pip(0)
    log = RecordingLogger()
    result = dg.auto_update_chromadb(logger_=log)
    assert result["status"] == "check_failed"
    assert calls == []
    assert any("CVE-2026-45829" in msg for level, msg in log.records if level == logging.WARNING)


def test_pip_failure_keeps_version_and_warns(monkey_meta, monkey_latest, monkey_pip):
    monkey_meta(["1.5.9", "1.5.9"])
    monkey_latest("1.6.0")
    set_pip, calls = monkey_pip
    set_pip(1, "permission denied")
    log = RecordingLogger()
    result = dg.auto_update_chromadb(logger_=log)
    assert result["status"] == "upgrade_failed"
    assert calls == ["chromadb"]
    assert any("CVE-2026-45829" in msg for level, msg in log.records if level == logging.WARNING)


def test_not_installed_no_actions(monkey_meta, monkey_latest, monkey_pip):
    monkey_meta(None)
    monkey_latest("1.6.0")
    set_pip, calls = monkey_pip
    set_pip(0)
    result = dg.auto_update_chromadb(logger_=RecordingLogger())
    assert result["status"] == "not_installed"
    assert calls == []


def test_never_raises_on_broken_metadata(monkeypatch):
    def _boom(package):
        raise RuntimeError("broken metadata")
    monkeypatch.setattr("importlib.metadata.version", _boom)
    result = dg.auto_update_chromadb(logger_=RecordingLogger())
    assert result["status"] == "not_installed"
