"""services/ui_cache.py
Устойчивый SQLite-кэш для UI/callback маппингов Telegram-ботов.

Хранит callback-токены кнопок навигации, пагинации и состояний в SQLite таблице
`ui_callback_cache` (по умолчанию в bot_state.sqlite).
Предоставляет dict-совместимый интерфейс для бесшовной замены in-memory TtlDict,
гарантируя сохранение работоспособности кнопок после перезапуска бота.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Iterator

from services.db_pool import get_connection

logger = logging.getLogger("UICallbackCache")

# Default TTL: 7 days for UI callback tokens
DEFAULT_UI_TTL = 7 * 86400.0


def _get_default_db_path() -> str:
    try:
        from config import BOT_STATE_DB_PATH
        return BOT_STATE_DB_PATH
    except (ImportError, AttributeError):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_dir, "bot_state.sqlite")


def _serialize_value(val: Any) -> str:
    """Сериализует значение в JSON с сохранением кортежей."""
    if isinstance(val, tuple):
        return json.dumps({"__type__": "tuple", "data": list(val)}, ensure_ascii=False)
    return json.dumps(val, ensure_ascii=False)


def _deserialize_value(raw: str) -> Any:
    """Десериализует значение из JSON с восстановлением кортежей."""
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("__type__") == "tuple":
            return tuple(data.get("data", []))
        return data
    except (json.JSONDecodeError, TypeError):
        return raw


class UICallbackCache:
    """Dict-совместимый интерфейс к таблице ui_callback_cache в SQLite."""

    def __init__(
        self,
        namespace: str = "default",
        db_path: str | Path | None = None,
        default_ttl: float | None = DEFAULT_UI_TTL,
    ) -> None:
        self.namespace = namespace
        self.db_path = str(db_path) if db_path else _get_default_db_path()
        self.default_ttl = default_ttl
        self._last_evict = 0.0
        self._evict_interval = 60.0  # сек
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        return get_connection(self.db_path)

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ui_callback_cache (
                key TEXT NOT NULL,
                namespace TEXT NOT NULL DEFAULT 'default',
                value TEXT NOT NULL,
                expires_at REAL,
                created_at REAL NOT NULL DEFAULT (julianday('now')),
                PRIMARY KEY (key, namespace)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ui_cb_namespace
            ON ui_callback_cache(namespace)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ui_cb_expires
            ON ui_callback_cache(expires_at)
        """)
        conn.commit()

    def _evict_expired(self, force: bool = False) -> None:
        now = time.time()
        if not force and (now - self._last_evict < self._evict_interval):
            return
        self._last_evict = now
        try:
            conn = self._get_conn()
            conn.execute(
                "DELETE FROM ui_callback_cache WHERE expires_at IS NOT NULL AND expires_at < ?",
                (now,),
            )
            conn.commit()
        except sqlite3.Error as exc:
            logger.debug("Ошибка очистки протухших callback: %s", exc)

    def set(self, key: str, value: Any, ttl: float | None = ...) -> None:
        """Сохраняет значение с TTL."""
        self._evict_expired()
        conn = self._get_conn()
        actual_ttl = self.default_ttl if ttl is ... else ttl
        expires_at = (time.time() + actual_ttl) if actual_ttl is not None else None
        serialized = _serialize_value(value)

        conn.execute(
            """INSERT OR REPLACE INTO ui_callback_cache (key, namespace, value, expires_at)
               VALUES (?, ?, ?, ?)""",
            (str(key), self.namespace, serialized, expires_at),
        )
        conn.commit()

    def get(self, key: str, default: Any = None) -> Any:
        """Получает значение по ключу, учитывая TTL."""
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value, expires_at FROM ui_callback_cache WHERE key = ? AND namespace = ?",
            (str(key), self.namespace),
        ).fetchone()

        if row is None:
            return default

        value_raw, expires_at = row
        if expires_at is not None and time.time() > expires_at:
            conn.execute(
                "DELETE FROM ui_callback_cache WHERE key = ? AND namespace = ?",
                (str(key), self.namespace),
            )
            conn.commit()
            return default

        return _deserialize_value(value_raw)

    def delete(self, key: str) -> bool:
        """Удаляет ключ из кэша."""
        conn = self._get_conn()
        cur = conn.execute(
            "DELETE FROM ui_callback_cache WHERE key = ? AND namespace = ?",
            (str(key), self.namespace),
        )
        conn.commit()
        return cur.rowcount > 0

    def pop(self, key: str, default: Any = None) -> Any:
        val = self.get(key, default=None)
        if val is None:
            return default
        self.delete(key)
        return val

    def clear(self) -> None:
        """Очищает все ключи текущего namespace."""
        conn = self._get_conn()
        conn.execute(
            "DELETE FROM ui_callback_cache WHERE namespace = ?",
            (self.namespace,),
        )
        conn.commit()

    def keys(self) -> list[str]:
        self._evict_expired()
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT key FROM ui_callback_cache WHERE namespace = ?",
            (self.namespace,),
        ).fetchall()
        return [r[0] for r in rows]

    def stats(self) -> dict[str, Any]:
        self._evict_expired(force=True)
        conn = self._get_conn()
        row = conn.execute(
            "SELECT COUNT(*) FROM ui_callback_cache WHERE namespace = ?",
            (self.namespace,),
        ).fetchone()
        return {"size": row[0] if row else 0, "namespace": self.namespace}

    # Dict-like methods for seamless drop-in compatibility with TtlDict
    def __getitem__(self, key: str) -> Any:
        val = self.get(key)
        if val is None:
            raise KeyError(key)
        return val

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    def __delitem__(self, key: str) -> None:
        if not self.delete(key):
            raise KeyError(key)

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None

    def __len__(self) -> int:
        return self.stats()["size"]

    def __iter__(self) -> Iterator[str]:
        return iter(self.keys())
