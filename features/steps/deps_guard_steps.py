"""Шаги BDD для features/deps_guard.feature.

Выполняются через реальную services.deps_guard.auto_update_chromadb
с подменой источников версий (установленная/PyPI) и pip-обновления —
детерминированно, без сети.
"""
from unittest import mock

from behave import given, then, when

import services.deps_guard as dg

_calls = []
_result = None


class _RecordingLogger:
    def __init__(self):
        self.warnings = []
        self.infos = []
        self.errors = []

    def warning(self, msg, *args):
        self.warnings.append(msg % args if args else msg)

    def info(self, msg, *args):
        self.infos.append(msg % args if args else msg)

    def error(self, msg, *args):
        self.errors.append(msg % args if args else msg)


def _install_seq(versions):
    queue = list(versions)

    def _get(package):
        return queue.pop(0) if queue else None
    return _get


@given('chromadb {installed} is installed and {latest} is the latest on PyPI')
def step_install_and_latest(context, installed, latest):
    context.patches = [
        mock.patch.object(dg, "_installed_version", side_effect=_install_seq([installed, latest])),
        mock.patch.object(dg, "_latest_version", return_value=latest),
        mock.patch.object(dg, "_pip_upgrade", side_effect=_record_pip(0)),
    ]
    for p in context.patches:
        p.start()
    context.logger = _RecordingLogger()


@given('chromadb {installed} is installed, {latest} is available and pip fails')
def step_install_latest_pip_fails(context, installed, latest):
    context.patches = [
        mock.patch.object(
            dg, "_installed_version",
            side_effect=_install_seq([installed, installed]),
        ),
        mock.patch.object(dg, "_latest_version", return_value=latest),
        mock.patch.object(dg, "_pip_upgrade", side_effect=_record_pip(1)),
    ]
    for p in context.patches:
        p.start()
    context.logger = _RecordingLogger()


@given("PyPI is unreachable")
def step_pypi_unreachable(context):
    context.patches = [
        mock.patch.object(dg, "_installed_version", return_value="1.5.9"),
        mock.patch.object(dg, "_latest_version", return_value=None),
    ]
    for p in context.patches:
        p.start()
    context.logger = _RecordingLogger()


@given("PyPI returns malformed data")
def step_pypi_malformed(context):
    context.patches = [
        mock.patch.object(dg, "_installed_version", return_value="1.5.9"),
        mock.patch.object(dg, "_latest_version", return_value=None),
    ]
    for p in context.patches:
        p.start()
    context.logger = _RecordingLogger()


@given("chromadb is not installed")
def step_chromadb_not_installed(context):
    context.patches = [
        mock.patch.object(dg, "_installed_version", return_value=None),
    ]
    for p in context.patches:
        p.start()
    context.logger = _RecordingLogger()


@when("the bot runs the chromadb auto-update check")
def step_run_check(context):
    global _result
    _calls.clear()
    _result = dg.auto_update_chromadb(logger_=context.logger)
    for p in getattr(context, "patches", []):
        p.stop()


@then("pip is asked to upgrade chromadb")
def step_pip_asked(context):
    assert _calls == ["chromadb"], f"pip called with {_calls}"


@then("no pip upgrade is attempted")
def step_pip_not_asked(context):
    assert _calls == [], f"pip unexpectedly called with {_calls}"


@then("no error is raised")
def step_no_error(context):
    assert _result is not None, "auto-update check raised an exception"


@then("the installed version is {version} after the upgrade")
def step_after_version(context, version):
    assert _result.get("installed_after") == version, _result


@then("the installed version is still {version}")
def step_still_version(context, version):
    assert _result.get("installed") == version, _result


@then("no CVE warning is logged")
def step_no_cve_warning(context):
    assert not any("CVE-2026-45829" in m for m in context.logger.warnings), context.logger.warnings


@then("a CVE warning for version below 1.6.0 is logged")
def step_cve_warning(context):
    assert any("CVE-2026-45829" in m for m in context.logger.warnings), context.logger.warnings


def _record_pip(returncode):
    def _run(package, logger_):
        _calls.append(package)
        return returncode == 0
    return _run
