"""services/db_pool.py
Универсальный менеджер и пул подключений к SQLite.

Обеспечивает:
- Режим WAL (Write-Ahead Logging) для параллельного чтения и записи.
- synchronous = NORMAL (оптимальный баланс надежности и скорости в WAL).
- busy_timeout = 15000 (15с ожидания освобождения блокировки вместо 'database is locked').
- foreign_keys = ON (целостность связей).
- Потокобезопасность через thread-local хранилище соединений.
- Контекстные менеджеры для транзакций и курсоров.
"""

from __future__ import annotations

import contextlib
import logging
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any, Callable, Generator

logger = logging.getLogger("DBPool")

DEFAULT_BUSY_TIMEOUT_MS = 15000


def apply_pragmas(
    conn: sqlite3.Connection,
    *,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    foreign_keys: bool = True,
    journal_mode: str = "WAL",
    synchronous: str = "NORMAL",
) -> None:
    """Применяет стандартные production-прагмы SQLite к соединению."""
    # Для in-memory баз WAL режим может не применяться или возвращать 'memory'
    try:
        conn.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
        if foreign_keys:
            conn.execute("PRAGMA foreign_keys=ON")
        if journal_mode:
            conn.execute(f"PRAGMA journal_mode={journal_mode}")
        if synchronous:
            conn.execute(f"PRAGMA synchronous={synchronous}")
    except sqlite3.Error as exc:
        logger.warning("Ошибка применения SQLite PRAGMA: %s", exc)


class SQLiteConnectionPool:
    """Пул потокобезопасных соединений SQLite с thread-local кэшированием."""

    def __init__(self, busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS) -> None:
        self.busy_timeout_ms = busy_timeout_ms
        self._local = threading.local()
        self._all_pools_lock = threading.Lock()
        self._all_conns: list[sqlite3.Connection] = []

    def _get_thread_map(self) -> dict[str, sqlite3.Connection]:
        if not hasattr(self._local, "connections"):
            self._local.connections = {}
        return self._local.connections

    def _normalize_path(self, db_path: str | Path) -> str:
        s = str(db_path)
        if s == ":memory:" or s.startswith("file:"):
            return s
        return os.path.abspath(os.path.expanduser(s))

    def get_connection(
        self,
        db_path: str | Path,
        *,
        row_factory: Any | None = None,
        init_hook: Callable[[sqlite3.Connection], None] | None = None,
    ) -> sqlite3.Connection:
        """Возвращает валидное SQLite соединение для текущего потока."""
        norm_path = self._normalize_path(db_path)
        thread_conns = self._get_thread_map()

        conn = thread_conns.get(norm_path)
        is_live = False
        if conn is not None:
            try:
                # Проверка жизнеспособности соединения
                conn.execute("SELECT 1")
                is_live = True
            except (sqlite3.Error, Exception):
                is_live = False
                try:
                    conn.close()
                except Exception:
                    pass
                thread_conns.pop(norm_path, None)

        if not is_live or conn is None:
            if norm_path != ":memory:" and not norm_path.startswith("file:"):
                os.makedirs(os.path.dirname(norm_path), exist_ok=True)

            conn = sqlite3.connect(
                norm_path,
                check_same_thread=False,
                timeout=self.busy_timeout_ms / 1000.0,
            )
            apply_pragmas(conn, busy_timeout_ms=self.busy_timeout_ms)

            if init_hook:
                init_hook(conn)

            thread_conns[norm_path] = conn
            with self._all_pools_lock:
                self._all_conns.append(conn)

        if row_factory is not None:
            conn.row_factory = row_factory

        return conn

    def close_connection(self, db_path: str | Path) -> None:
        """Закрывает соединение текущего потока для указанного пути."""
        norm_path = self._normalize_path(db_path)
        thread_conns = self._get_thread_map()
        conn = thread_conns.pop(norm_path, None)
        if conn is not None:
            try:
                conn.close()
            except Exception as exc:
                logger.debug("Ошибка при закрытии соединения %s: %s", norm_path, exc)
            with self._all_pools_lock:
                if conn in self._all_conns:
                    self._all_conns.remove(conn)

    def close_thread_connections(self) -> None:
        """Закрывает все соединения текущего потока."""
        thread_conns = self._get_thread_map()
        for path in list(thread_conns.keys()):
            self.close_connection(path)

    def close_all(self) -> None:
        """Закрывает все отслеживаемые соединения (например, при завершении работы)."""
        with self._all_pools_lock:
            for conn in list(self._all_conns):
                try:
                    conn.close()
                except Exception:
                    pass
            self._all_conns.clear()
        if hasattr(self._local, "connections"):
            self._local.connections.clear()


# Глобальный синглтон пула
_DEFAULT_POOL = SQLiteConnectionPool()


def get_db_pool() -> SQLiteConnectionPool:
    """Возвращает стандартный экземпляр SQLiteConnectionPool."""
    return _DEFAULT_POOL


def get_connection(
    db_path: str | Path,
    *,
    row_factory: Any | None = None,
    init_hook: Callable[[sqlite3.Connection], None] | None = None,
) -> sqlite3.Connection:
    """Удобная функция для получения потокобезопасного соединения."""
    return _DEFAULT_POOL.get_connection(
        db_path, row_factory=row_factory, init_hook=init_hook
    )


@contextlib.contextmanager
def db_connection(
    db_path: str | Path | sqlite3.Connection,
    *,
    row_factory: Any | None = None,
    commit: bool = True,
) -> Generator[sqlite3.Connection, None, None]:
    """Контекстный менеджер соединения.

    Автоматически выполняет commit при успешном завершении блока и rollback при ошибке.
    """
    if isinstance(db_path, sqlite3.Connection):
        conn = db_path
        if row_factory is not None:
            conn.row_factory = row_factory
    else:
        conn = get_connection(db_path, row_factory=row_factory)
    try:
        yield conn
        if commit:
            conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise


@contextlib.contextmanager
def db_cursor(
    db_path: str | Path,
    *,
    row_factory: Any | None = None,
    commit: bool = True,
) -> Generator[sqlite3.Cursor, None, None]:
    """Контекстный менеджер курсора с автоматическим управлением транзакцией."""
    with db_connection(db_path, row_factory=row_factory, commit=commit) as conn:
        cursor = conn.cursor()
        try:
            yield cursor
        finally:
            cursor.close()
