"""deps_guard.py — проверка версии chromadb при старте бота.

Закрывает CVE-2026-45829 (PYSEC-2026-311, критическая): уязвимы версии
1.0.0…1.5.9. В этой конфигурации векторы атаки (REST-API pre-auth и отравленная
конфигурация коллекции) недостижимы (chromadb работает embedded через
PersistentClient без HTTP-сервера), но пакет остаётся единственным
остатком pip-audit.

Модуль НЕ выполняет автообновление (supply-chain риск). Только проверяет
версию при старте и логирует предупреждение, если версия уязвима.
Версия зафиксирована в requirements.txt (chromadb==1.5.9).
Когда выйдет версия >= 1.6.0 — обновить pin в requirements.txt.
"""

import logging
import re
from importlib.metadata import PackageNotFoundError
from typing import Optional

PACKAGE = "chromadb"
CVE_FIXED_VERSION = (1, 6, 0)

logger = logging.getLogger("DepsGuard")


def _parse_version(raw: str) -> tuple:
    """Разбирает строку версии в кортеж чисел для сравнения.

    Берутся только последовательности цифр («1.6.0.dev1» → (1, 6, 0, 1)).
    Пустая/мусорная строка даёт (0, 0, 0) — такая версия считается древней.
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


def _warn_if_cve_unfixed(installed: str, logger_: logging.Logger) -> None:
    """Предупреждает в логе, если установленная версия всё ещё уязвима."""
    if _parse_version(installed) < CVE_FIXED_VERSION:
        logger_.warning(
            "chromadb %s < 1.6.0: известная критическая CVE-2026-45829 "
            "(PYSEC-2026-311); вектор атаки недостижим в embedded-режиме, "
            "но рекомендуется обновить до >= 1.6.0 когда выйдет",
            installed,
        )
    else:
        logger_.info("chromadb %s — CVE-2026-45829 закрыта", installed)


def check_chromadb_version(logger_: Optional[logging.Logger] = None) -> dict:
    """Проверяет версию chromadb и логирует предупреждение при уязвимости.

    Вызывается при старте бота. Никогда не бросает исключений; возвращает
    dict со статусом для логов и тестов.
    """
    log = logger_ or logger

    installed = _installed_version(PACKAGE)
    if installed is None:
        log.info("chromadb не установлен — проверка пропущена")
        return {"status": "not_installed", "installed": None}

    if _parse_version(installed) < CVE_FIXED_VERSION:
        log.warning(
            "chromadb %s < 1.6.0: известная CVE-2026-45829; "
            "в embedded-режиме вектор недостижим, но обновите pin в requirements.txt "
            "на >= 1.6.0 когда выйдет релиз",
            installed,
        )
        return {"status": "vulnerable", "installed": installed}

    log.info("chromadb %s — CVE-2026-45829 закрыта", installed)
    return {"status": "ok", "installed": installed}
