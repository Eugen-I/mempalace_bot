"""
kv_store.py
SQLite-бэкед для TTL-кэшей и временных состояний.
Позволяет переживать рестарты бота без потери сессионных данных.
API совместим с dict/TTLCache для бесшовной замены.
"""
import json
import sqlite3
import threading
import time
import os
import logging
from typing import Any, Optional

logger = logging.getLogger("KVStore")

_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bot_state.sqlite")

class KVStore:
    _instance = None
    _lock = threading.Lock()

    def __init__(self, db_path: str = _DB_PATH):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kv_store (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                namespace TEXT NOT NULL DEFAULT 'default',
                expires_at REAL,
                created_at REAL NOT NULL DEFAULT (julianday('now'))
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_kv_namespace ON kv_store(namespace)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_kv_expires ON kv_store(expires_at)
        """)
        conn.commit()

    def _evict_expired(self):
        conn = self._get_conn()
        now = time.time()
        conn.execute("DELETE FROM kv_store WHERE expires_at IS NOT NULL AND expires_at < ?", (now,))
        conn.commit()

    def set(self, key: str, value: Any, namespace: str = "default", ttl: Optional[float] = None):
        self._evict_expired()
        conn = self._get_conn()
        expires_at = (time.time() + ttl) if ttl else None
        serialized = json.dumps(value, ensure_ascii=False)
        conn.execute(
            """INSERT OR REPLACE INTO kv_store (key, value, namespace, expires_at)
               VALUES (?, ?, ?, ?)""",
            (key, serialized, namespace, expires_at)
        )
        conn.commit()

    def get(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value, expires_at FROM kv_store WHERE key = ? AND namespace = ?",
            (key, namespace)
        ).fetchone()
        if row is None:
            return default
        value_raw, expires_at = row
        if expires_at is not None and time.time() > expires_at:
            conn.execute("DELETE FROM kv_store WHERE key = ? AND namespace = ?", (key, namespace))
            conn.commit()
            return default
        try:
            return json.loads(value_raw)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    def delete(self, key: str, namespace: str = "default"):
        conn = self._get_conn()
        conn.execute("DELETE FROM kv_store WHERE key = ? AND namespace = ?", (key, namespace))
        conn.commit()

    def pop(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        value = self.get(key, namespace, default)
        self.delete(key, namespace)
        return value

    def keys(self, namespace: str = "default") -> list[str]:
        self._evict_expired()
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT key FROM kv_store WHERE namespace = ?", (namespace,)
        ).fetchall()
        return [r[0] for r in rows]

    def clear(self, namespace: Optional[str] = None):
        conn = self._get_conn()
        if namespace:
            conn.execute("DELETE FROM kv_store WHERE namespace = ?", (namespace,))
        else:
            conn.execute("DELETE FROM kv_store")
        conn.commit()

    def cleanup(self):
        self._evict_expired()
        conn = self._get_conn()
        conn.execute("VACUUM")
        conn.commit()

    @property
    def stats(self) -> Dict:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) FROM kv_store").fetchone()
        return {"size": row[0] if row else 0}

def get_kv_store() -> KVStore:
    with KVStore._lock:
        if KVStore._instance is None:
            KVStore._instance = KVStore()
        return KVStore._instance
