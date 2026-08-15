"""deps_guard.py — автообновление chromadb при старте бота.

Закрывает CVE-2026-45829 (PYSEC-2026-311, критическая): уязвимы версии
1.0.0…1.5.9, фикс ещё не выпущен (issue chroma-core/chroma#6717 открыт).
При старте бот сверяет установленную версию chromadb с последней на PyPI
и, если есть более новый релиз, устанавливает его автоматически — когда
фикс выйдет, он подтянется без ручного вмешательства. Пока фикса нет —
логирует предупреждение о незакрытой CVE.

Векторы атаки (REST-API pre-auth и отравленная конфигурация коллекции) в
этой конфигурации недостижимы (chromadb работает embedded через
PersistentClient без HTTP-сервера), но пакет остаётся единственным
остатком pip-audit, поэтому автообновление — дешёвая защита на будущее.

Модуль никогда не бросает исключений: все сбои (сеть, pip, метаданные)
превращаются в записи лога и не мешают старту бота.
"""

import json
import logging
import re
import subprocess  # nosec B404 — обновление пакета фиксированным списком аргументов
import sys
import urllib.request
from importlib.metadata import PackageNotFoundError
from typing import Optional

PACKAGE = "chromadb"
PYPI_URL = "https://pypi.org/pypi/{package}/json"
HTTP_TIMEOUT_SECONDS = 8
PIP_TIMEOUT_SECONDS = 240
CVE_FIXED_VERSION = (1, 6, 0)

logger = logging.getLogger("DepsGuard")


def _parse_version(raw: str) -> tuple:
    """Разбирает строку версии в кортеж чисел для сравнения.

    Берутся только последовательности цифр («1.6.0.dev1» → (1, 6, 0, 1)).
    Пустая/мусорная строка даёт (0, 0, 0) — такая версия считается
    древней, автообновление попытается её обновить.
    """
    parts = tuple(int(seg) for seg in re.findall(r"\d+", raw))
    return parts if parts else (0, 0, 0)


def _installed_version(package: str = PACKAGE) -> Optional[str]:
    """Возвращает установленную версию пакета или None, если его нет."""
    try:
        from importlib.metadata import version

        return version(package)
    except PackageNotFoundError:
        return None
    except Exception:
        return None


def _latest_version(package: str = PACKAGE) -> Optional[str]:
    """Возвращает последнюю версию пакета с PyPI или None при сбое."""
    try:
        with urllib.request.urlopen(  # nosec B310 — фиксированный https-адрес PyPI
            PYPI_URL.format(package=package), timeout=HTTP_TIMEOUT_SECONDS
        ) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data["info"]["version"]
    except Exception:
        return None


def _pip_upgrade(package: str, logger_: logging.Logger) -> bool:
    """Устанавливает последнюю версию пакета через pip. True при успехе."""
    try:
        proc = subprocess.run(  # nosec B603 — список аргументов фиксирован, shell=False
            [sys.executable, "-m", "pip", "install", "--upgrade", package],
            capture_output=True,
            text=True,
            timeout=PIP_TIMEOUT_SECONDS,
        )
        if proc.returncode == 0:
            return True
        logger_.error(
            "pip upgrade of %s failed: %s", package, proc.stderr.strip()[:500]
        )
        return False
    except subprocess.TimeoutExpired:
        logger_.error("pip upgrade of %s timed out after %ss", package, PIP_TIMEOUT_SECONDS)
        return False
    except Exception as exc:
        logger_.error("pip upgrade of %s failed: %s", package, exc)
        return False


def _warn_if_cve_unfixed(installed: str, logger_: logging.Logger) -> None:
    """Предупреждает в логе, если установленная версия всё ещё уязвима."""
    if _parse_version(installed) < CVE_FIXED_VERSION:
        logger_.warning(
            "chromadb %s < 1.6.0: известная критическая CVE-2026-45829 "
            "(PYSEC-2026-311), фикс ещё не выпущен; автообновление установит "
            "его, как только релиз появится на PyPI",
            installed,
        )
    else:
        logger_.info("chromadb %s — CVE-2026-45829 закрыта", installed)


def auto_update_chromadb(logger_: Optional[logging.Logger] = None) -> dict:
    """Сверяет версию chromadb с PyPI и при наличии новее — обновляет.

    Вызывается при старте бота. Никогда не бросает исключений; возвращает
    dict со статусом для логов и тестов.
    """
    log = logger_ or logger

    installed = _installed_version(PACKAGE)
    if installed is None:
        log.info("chromadb не установлен — автообновление не требуется")
        return {"status": "not_installed", "installed": None}

    latest = _latest_version(PACKAGE)
    if latest is None:
        log.warning(
            "не удалось проверить последнюю версию chromadb (сеть недоступна?)"
        )
        _warn_if_cve_unfixed(installed, log)
        return {"status": "check_failed", "installed": installed, "latest": None}

    if _parse_version(latest) <= _parse_version(installed):
        log.info("chromadb %s — актуальная версия", installed)
        _warn_if_cve_unfixed(installed, log)
        return {"status": "up_to_date", "installed": installed, "latest": latest}

    log.info("доступна новая версия chromadb: %s → %s — обновляю", installed, latest)
    upgraded = _pip_upgrade(PACKAGE, log)
    after = _installed_version(PACKAGE)
    if upgraded and after is not None and _parse_version(after) > _parse_version(installed):
        log.info("chromadb обновлён: %s → %s", installed, after)
        _warn_if_cve_unfixed(after, log)
        return {
            "status": "upgraded",
            "installed": installed,
            "latest": latest,
            "installed_after": after,
        }

    log.error(
        "не удалось обновить chromadb с %s до %s — остаётся текущая версия",
        installed,
        latest,
    )
    _warn_if_cve_unfixed(after or installed, log)
    return {
        "status": "upgrade_failed",
        "installed": installed,
        "latest": latest,
        "installed_after": after,
    }
