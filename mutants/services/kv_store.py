"""kv_store.py
SQLite-бэкед для TTL-кэшей и временных состояний.
Позволяет переживать рестарты бота без потери сессионных данных.
API совместим с dict/TTLCache для бесшовной замены.
"""

import json
import logging
import os
import sqlite3
import threading
import time
from typing import Any

logger = logging.getLogger("KVStore")

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bot_state.sqlite",
)


from mutmut.mutation.trampoline import wrap_in_trampoline as _mutmut_mutated, MutantDict
mutants_xǁKVStoreǁ__init____mutmut: MutantDict = {}  # type: ignore
mutants_xǁKVStoreǁ_get_conn__mutmut: MutantDict = {}  # type: ignore
mutants_xǁKVStoreǁ_init_db__mutmut: MutantDict = {}  # type: ignore
mutants_xǁKVStoreǁ_evict_expired__mutmut: MutantDict = {}  # type: ignore
mutants_xǁKVStoreǁset__mutmut: MutantDict = {}  # type: ignore
mutants_xǁKVStoreǁget__mutmut: MutantDict = {}  # type: ignore
mutants_xǁKVStoreǁdelete__mutmut: MutantDict = {}  # type: ignore
mutants_xǁKVStoreǁpop__mutmut: MutantDict = {}  # type: ignore
mutants_xǁKVStoreǁkeys__mutmut: MutantDict = {}  # type: ignore
mutants_xǁKVStoreǁclear__mutmut: MutantDict = {}  # type: ignore
mutants_xǁKVStoreǁcleanup__mutmut: MutantDict = {}  # type: ignore


class KVStore:
    _instance = None
    _lock = threading.Lock()

    @_mutmut_mutated(mutants_xǁKVStoreǁ__init____mutmut)
    def __init__(self, db_path: str = _DB_PATH):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def xǁKVStoreǁ__init____mutmut_orig(self, db_path: str = _DB_PATH):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def xǁKVStoreǁ__init____mutmut_1(self, db_path: str = _DB_PATH):
        self.db_path = None
        self._local = threading.local()
        self._init_db()

    def xǁKVStoreǁ__init____mutmut_2(self, db_path: str = _DB_PATH):
        self.db_path = db_path
        self._local = None
        self._init_db()

    @_mutmut_mutated(mutants_xǁKVStoreǁ_get_conn__mutmut)
    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def xǁKVStoreǁ_get_conn__mutmut_orig(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def xǁKVStoreǁ_get_conn__mutmut_1(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") and self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def xǁKVStoreǁ_get_conn__mutmut_2(self) -> sqlite3.Connection:
        if hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def xǁKVStoreǁ_get_conn__mutmut_3(self) -> sqlite3.Connection:
        if not hasattr(None, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def xǁKVStoreǁ_get_conn__mutmut_4(self) -> sqlite3.Connection:
        if not hasattr(self._local, None) or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def xǁKVStoreǁ_get_conn__mutmut_5(self) -> sqlite3.Connection:
        if not hasattr("conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def xǁKVStoreǁ_get_conn__mutmut_6(self) -> sqlite3.Connection:
        if not hasattr(self._local, ) or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def xǁKVStoreǁ_get_conn__mutmut_7(self) -> sqlite3.Connection:
        if not hasattr(self._local, "XXconnXX") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def xǁKVStoreǁ_get_conn__mutmut_8(self) -> sqlite3.Connection:
        if not hasattr(self._local, "CONN") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def xǁKVStoreǁ_get_conn__mutmut_9(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is not None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def xǁKVStoreǁ_get_conn__mutmut_10(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = None
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def xǁKVStoreǁ_get_conn__mutmut_11(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(None, check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def xǁKVStoreǁ_get_conn__mutmut_12(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=None)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def xǁKVStoreǁ_get_conn__mutmut_13(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def xǁKVStoreǁ_get_conn__mutmut_14(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, )
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def xǁKVStoreǁ_get_conn__mutmut_15(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=True)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def xǁKVStoreǁ_get_conn__mutmut_16(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.execute(None)
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def xǁKVStoreǁ_get_conn__mutmut_17(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.execute("XXPRAGMA journal_mode=WALXX")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def xǁKVStoreǁ_get_conn__mutmut_18(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.execute("pragma journal_mode=wal")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def xǁKVStoreǁ_get_conn__mutmut_19(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.execute("PRAGMA JOURNAL_MODE=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def xǁKVStoreǁ_get_conn__mutmut_20(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute(None)
        return self._local.conn

    def xǁKVStoreǁ_get_conn__mutmut_21(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("XXPRAGMA synchronous=NORMALXX")
        return self._local.conn

    def xǁKVStoreǁ_get_conn__mutmut_22(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("pragma synchronous=normal")
        return self._local.conn

    def xǁKVStoreǁ_get_conn__mutmut_23(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA SYNCHRONOUS=NORMAL")
        return self._local.conn

    @_mutmut_mutated(mutants_xǁKVStoreǁ_init_db__mutmut)
    def _init_db(self):
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kv_store (
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                namespace TEXT NOT NULL DEFAULT 'default',
                expires_at REAL,
                created_at REAL NOT NULL DEFAULT (julianday('now')),
                PRIMARY KEY (key, namespace)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_kv_namespace ON kv_store(namespace)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_kv_expires ON kv_store(expires_at)
        """)
        conn.commit()

    def xǁKVStoreǁ_init_db__mutmut_orig(self):
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kv_store (
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                namespace TEXT NOT NULL DEFAULT 'default',
                expires_at REAL,
                created_at REAL NOT NULL DEFAULT (julianday('now')),
                PRIMARY KEY (key, namespace)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_kv_namespace ON kv_store(namespace)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_kv_expires ON kv_store(expires_at)
        """)
        conn.commit()

    def xǁKVStoreǁ_init_db__mutmut_1(self):
        conn = None
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kv_store (
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                namespace TEXT NOT NULL DEFAULT 'default',
                expires_at REAL,
                created_at REAL NOT NULL DEFAULT (julianday('now')),
                PRIMARY KEY (key, namespace)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_kv_namespace ON kv_store(namespace)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_kv_expires ON kv_store(expires_at)
        """)
        conn.commit()

    def xǁKVStoreǁ_init_db__mutmut_2(self):
        conn = self._get_conn()
        conn.execute(None)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_kv_namespace ON kv_store(namespace)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_kv_expires ON kv_store(expires_at)
        """)
        conn.commit()

    def xǁKVStoreǁ_init_db__mutmut_3(self):
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kv_store (
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                namespace TEXT NOT NULL DEFAULT 'default',
                expires_at REAL,
                created_at REAL NOT NULL DEFAULT (julianday('now')),
                PRIMARY KEY (key, namespace)
            )
        """)
        conn.execute(None)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_kv_expires ON kv_store(expires_at)
        """)
        conn.commit()

    def xǁKVStoreǁ_init_db__mutmut_4(self):
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kv_store (
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                namespace TEXT NOT NULL DEFAULT 'default',
                expires_at REAL,
                created_at REAL NOT NULL DEFAULT (julianday('now')),
                PRIMARY KEY (key, namespace)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_kv_namespace ON kv_store(namespace)
        """)
        conn.execute(None)
        conn.commit()

    @_mutmut_mutated(mutants_xǁKVStoreǁ_evict_expired__mutmut)
    def _evict_expired(self):
        conn = self._get_conn()
        now = time.time()
        conn.execute(
            "DELETE FROM kv_store WHERE expires_at IS NOT NULL AND expires_at < ?",
            (now,),
        )
        conn.commit()

    def xǁKVStoreǁ_evict_expired__mutmut_orig(self):
        conn = self._get_conn()
        now = time.time()
        conn.execute(
            "DELETE FROM kv_store WHERE expires_at IS NOT NULL AND expires_at < ?",
            (now,),
        )
        conn.commit()

    def xǁKVStoreǁ_evict_expired__mutmut_1(self):
        conn = None
        now = time.time()
        conn.execute(
            "DELETE FROM kv_store WHERE expires_at IS NOT NULL AND expires_at < ?",
            (now,),
        )
        conn.commit()

    def xǁKVStoreǁ_evict_expired__mutmut_2(self):
        conn = self._get_conn()
        now = None
        conn.execute(
            "DELETE FROM kv_store WHERE expires_at IS NOT NULL AND expires_at < ?",
            (now,),
        )
        conn.commit()

    def xǁKVStoreǁ_evict_expired__mutmut_3(self):
        conn = self._get_conn()
        now = time.time()
        conn.execute(
            None,
            (now,),
        )
        conn.commit()

    def xǁKVStoreǁ_evict_expired__mutmut_4(self):
        conn = self._get_conn()
        now = time.time()
        conn.execute(
            "DELETE FROM kv_store WHERE expires_at IS NOT NULL AND expires_at < ?",
            None,
        )
        conn.commit()

    def xǁKVStoreǁ_evict_expired__mutmut_5(self):
        conn = self._get_conn()
        now = time.time()
        conn.execute(
            (now,),
        )
        conn.commit()

    def xǁKVStoreǁ_evict_expired__mutmut_6(self):
        conn = self._get_conn()
        now = time.time()
        conn.execute(
            "DELETE FROM kv_store WHERE expires_at IS NOT NULL AND expires_at < ?",
            )
        conn.commit()

    def xǁKVStoreǁ_evict_expired__mutmut_7(self):
        conn = self._get_conn()
        now = time.time()
        conn.execute(
            "XXDELETE FROM kv_store WHERE expires_at IS NOT NULL AND expires_at < ?XX",
            (now,),
        )
        conn.commit()

    def xǁKVStoreǁ_evict_expired__mutmut_8(self):
        conn = self._get_conn()
        now = time.time()
        conn.execute(
            "delete from kv_store where expires_at is not null and expires_at < ?",
            (now,),
        )
        conn.commit()

    def xǁKVStoreǁ_evict_expired__mutmut_9(self):
        conn = self._get_conn()
        now = time.time()
        conn.execute(
            "DELETE FROM KV_STORE WHERE EXPIRES_AT IS NOT NULL AND EXPIRES_AT < ?",
            (now,),
        )
        conn.commit()

    @_mutmut_mutated(mutants_xǁKVStoreǁset__mutmut)
    def set(
        self, key: str, value: Any, namespace: str = "default", ttl: float | None = None,
    ):
        self._evict_expired()
        conn = self._get_conn()
        expires_at = (time.time() + ttl) if ttl is not None else None
        serialized = json.dumps(value, ensure_ascii=False)
        conn.execute(
            """INSERT OR REPLACE INTO kv_store (key, value, namespace, expires_at)
               VALUES (?, ?, ?, ?)""",
            (key, serialized, namespace, expires_at),
        )
        conn.commit()

    def xǁKVStoreǁset__mutmut_orig(
        self, key: str, value: Any, namespace: str = "default", ttl: float | None = None,
    ):
        self._evict_expired()
        conn = self._get_conn()
        expires_at = (time.time() + ttl) if ttl is not None else None
        serialized = json.dumps(value, ensure_ascii=False)
        conn.execute(
            """INSERT OR REPLACE INTO kv_store (key, value, namespace, expires_at)
               VALUES (?, ?, ?, ?)""",
            (key, serialized, namespace, expires_at),
        )
        conn.commit()

    def xǁKVStoreǁset__mutmut_1(
        self, key: str, value: Any, namespace: str = "XXdefaultXX", ttl: float | None = None,
    ):
        self._evict_expired()
        conn = self._get_conn()
        expires_at = (time.time() + ttl) if ttl is not None else None
        serialized = json.dumps(value, ensure_ascii=False)
        conn.execute(
            """INSERT OR REPLACE INTO kv_store (key, value, namespace, expires_at)
               VALUES (?, ?, ?, ?)""",
            (key, serialized, namespace, expires_at),
        )
        conn.commit()

    def xǁKVStoreǁset__mutmut_2(
        self, key: str, value: Any, namespace: str = "DEFAULT", ttl: float | None = None,
    ):
        self._evict_expired()
        conn = self._get_conn()
        expires_at = (time.time() + ttl) if ttl is not None else None
        serialized = json.dumps(value, ensure_ascii=False)
        conn.execute(
            """INSERT OR REPLACE INTO kv_store (key, value, namespace, expires_at)
               VALUES (?, ?, ?, ?)""",
            (key, serialized, namespace, expires_at),
        )
        conn.commit()

    def xǁKVStoreǁset__mutmut_3(
        self, key: str, value: Any, namespace: str = "default", ttl: float | None = None,
    ):
        self._evict_expired()
        conn = None
        expires_at = (time.time() + ttl) if ttl is not None else None
        serialized = json.dumps(value, ensure_ascii=False)
        conn.execute(
            """INSERT OR REPLACE INTO kv_store (key, value, namespace, expires_at)
               VALUES (?, ?, ?, ?)""",
            (key, serialized, namespace, expires_at),
        )
        conn.commit()

    def xǁKVStoreǁset__mutmut_4(
        self, key: str, value: Any, namespace: str = "default", ttl: float | None = None,
    ):
        self._evict_expired()
        conn = self._get_conn()
        expires_at = None
        serialized = json.dumps(value, ensure_ascii=False)
        conn.execute(
            """INSERT OR REPLACE INTO kv_store (key, value, namespace, expires_at)
               VALUES (?, ?, ?, ?)""",
            (key, serialized, namespace, expires_at),
        )
        conn.commit()

    def xǁKVStoreǁset__mutmut_5(
        self, key: str, value: Any, namespace: str = "default", ttl: float | None = None,
    ):
        self._evict_expired()
        conn = self._get_conn()
        expires_at = (time.time() - ttl) if ttl is not None else None
        serialized = json.dumps(value, ensure_ascii=False)
        conn.execute(
            """INSERT OR REPLACE INTO kv_store (key, value, namespace, expires_at)
               VALUES (?, ?, ?, ?)""",
            (key, serialized, namespace, expires_at),
        )
        conn.commit()

    def xǁKVStoreǁset__mutmut_6(
        self, key: str, value: Any, namespace: str = "default", ttl: float | None = None,
    ):
        self._evict_expired()
        conn = self._get_conn()
        expires_at = (time.time() + ttl) if ttl is None else None
        serialized = json.dumps(value, ensure_ascii=False)
        conn.execute(
            """INSERT OR REPLACE INTO kv_store (key, value, namespace, expires_at)
               VALUES (?, ?, ?, ?)""",
            (key, serialized, namespace, expires_at),
        )
        conn.commit()

    def xǁKVStoreǁset__mutmut_7(
        self, key: str, value: Any, namespace: str = "default", ttl: float | None = None,
    ):
        self._evict_expired()
        conn = self._get_conn()
        expires_at = (time.time() + ttl) if ttl is not None else None
        serialized = None
        conn.execute(
            """INSERT OR REPLACE INTO kv_store (key, value, namespace, expires_at)
               VALUES (?, ?, ?, ?)""",
            (key, serialized, namespace, expires_at),
        )
        conn.commit()

    def xǁKVStoreǁset__mutmut_8(
        self, key: str, value: Any, namespace: str = "default", ttl: float | None = None,
    ):
        self._evict_expired()
        conn = self._get_conn()
        expires_at = (time.time() + ttl) if ttl is not None else None
        serialized = json.dumps(None, ensure_ascii=False)
        conn.execute(
            """INSERT OR REPLACE INTO kv_store (key, value, namespace, expires_at)
               VALUES (?, ?, ?, ?)""",
            (key, serialized, namespace, expires_at),
        )
        conn.commit()

    def xǁKVStoreǁset__mutmut_9(
        self, key: str, value: Any, namespace: str = "default", ttl: float | None = None,
    ):
        self._evict_expired()
        conn = self._get_conn()
        expires_at = (time.time() + ttl) if ttl is not None else None
        serialized = json.dumps(value, ensure_ascii=None)
        conn.execute(
            """INSERT OR REPLACE INTO kv_store (key, value, namespace, expires_at)
               VALUES (?, ?, ?, ?)""",
            (key, serialized, namespace, expires_at),
        )
        conn.commit()

    def xǁKVStoreǁset__mutmut_10(
        self, key: str, value: Any, namespace: str = "default", ttl: float | None = None,
    ):
        self._evict_expired()
        conn = self._get_conn()
        expires_at = (time.time() + ttl) if ttl is not None else None
        serialized = json.dumps(ensure_ascii=False)
        conn.execute(
            """INSERT OR REPLACE INTO kv_store (key, value, namespace, expires_at)
               VALUES (?, ?, ?, ?)""",
            (key, serialized, namespace, expires_at),
        )
        conn.commit()

    def xǁKVStoreǁset__mutmut_11(
        self, key: str, value: Any, namespace: str = "default", ttl: float | None = None,
    ):
        self._evict_expired()
        conn = self._get_conn()
        expires_at = (time.time() + ttl) if ttl is not None else None
        serialized = json.dumps(value, )
        conn.execute(
            """INSERT OR REPLACE INTO kv_store (key, value, namespace, expires_at)
               VALUES (?, ?, ?, ?)""",
            (key, serialized, namespace, expires_at),
        )
        conn.commit()

    def xǁKVStoreǁset__mutmut_12(
        self, key: str, value: Any, namespace: str = "default", ttl: float | None = None,
    ):
        self._evict_expired()
        conn = self._get_conn()
        expires_at = (time.time() + ttl) if ttl is not None else None
        serialized = json.dumps(value, ensure_ascii=True)
        conn.execute(
            """INSERT OR REPLACE INTO kv_store (key, value, namespace, expires_at)
               VALUES (?, ?, ?, ?)""",
            (key, serialized, namespace, expires_at),
        )
        conn.commit()

    def xǁKVStoreǁset__mutmut_13(
        self, key: str, value: Any, namespace: str = "default", ttl: float | None = None,
    ):
        self._evict_expired()
        conn = self._get_conn()
        expires_at = (time.time() + ttl) if ttl is not None else None
        serialized = json.dumps(value, ensure_ascii=False)
        conn.execute(
            None,
            (key, serialized, namespace, expires_at),
        )
        conn.commit()

    def xǁKVStoreǁset__mutmut_14(
        self, key: str, value: Any, namespace: str = "default", ttl: float | None = None,
    ):
        self._evict_expired()
        conn = self._get_conn()
        expires_at = (time.time() + ttl) if ttl is not None else None
        serialized = json.dumps(value, ensure_ascii=False)
        conn.execute(
            """INSERT OR REPLACE INTO kv_store (key, value, namespace, expires_at)
               VALUES (?, ?, ?, ?)""",
            None,
        )
        conn.commit()

    def xǁKVStoreǁset__mutmut_15(
        self, key: str, value: Any, namespace: str = "default", ttl: float | None = None,
    ):
        self._evict_expired()
        conn = self._get_conn()
        expires_at = (time.time() + ttl) if ttl is not None else None
        serialized = json.dumps(value, ensure_ascii=False)
        conn.execute(
            (key, serialized, namespace, expires_at),
        )
        conn.commit()

    def xǁKVStoreǁset__mutmut_16(
        self, key: str, value: Any, namespace: str = "default", ttl: float | None = None,
    ):
        self._evict_expired()
        conn = self._get_conn()
        expires_at = (time.time() + ttl) if ttl is not None else None
        serialized = json.dumps(value, ensure_ascii=False)
        conn.execute(
            """INSERT OR REPLACE INTO kv_store (key, value, namespace, expires_at)
               VALUES (?, ?, ?, ?)""",
            )
        conn.commit()

    @_mutmut_mutated(mutants_xǁKVStoreǁget__mutmut)
    def get(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value, expires_at FROM kv_store WHERE key = ? AND namespace = ?",
            (key, namespace),
        ).fetchone()
        if row is None:
            return default
        value_raw, expires_at = row
        if expires_at is not None and time.time() > expires_at:
            conn.execute(
                "DELETE FROM kv_store WHERE key = ? AND namespace = ?", (key, namespace),
            )
            conn.commit()
            return default
        try:
            return json.loads(value_raw)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    def xǁKVStoreǁget__mutmut_orig(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value, expires_at FROM kv_store WHERE key = ? AND namespace = ?",
            (key, namespace),
        ).fetchone()
        if row is None:
            return default
        value_raw, expires_at = row
        if expires_at is not None and time.time() > expires_at:
            conn.execute(
                "DELETE FROM kv_store WHERE key = ? AND namespace = ?", (key, namespace),
            )
            conn.commit()
            return default
        try:
            return json.loads(value_raw)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    def xǁKVStoreǁget__mutmut_1(self, key: str, namespace: str = "XXdefaultXX", default: Any = None) -> Any:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value, expires_at FROM kv_store WHERE key = ? AND namespace = ?",
            (key, namespace),
        ).fetchone()
        if row is None:
            return default
        value_raw, expires_at = row
        if expires_at is not None and time.time() > expires_at:
            conn.execute(
                "DELETE FROM kv_store WHERE key = ? AND namespace = ?", (key, namespace),
            )
            conn.commit()
            return default
        try:
            return json.loads(value_raw)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    def xǁKVStoreǁget__mutmut_2(self, key: str, namespace: str = "DEFAULT", default: Any = None) -> Any:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value, expires_at FROM kv_store WHERE key = ? AND namespace = ?",
            (key, namespace),
        ).fetchone()
        if row is None:
            return default
        value_raw, expires_at = row
        if expires_at is not None and time.time() > expires_at:
            conn.execute(
                "DELETE FROM kv_store WHERE key = ? AND namespace = ?", (key, namespace),
            )
            conn.commit()
            return default
        try:
            return json.loads(value_raw)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    def xǁKVStoreǁget__mutmut_3(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        self._evict_expired()
        conn = None
        row = conn.execute(
            "SELECT value, expires_at FROM kv_store WHERE key = ? AND namespace = ?",
            (key, namespace),
        ).fetchone()
        if row is None:
            return default
        value_raw, expires_at = row
        if expires_at is not None and time.time() > expires_at:
            conn.execute(
                "DELETE FROM kv_store WHERE key = ? AND namespace = ?", (key, namespace),
            )
            conn.commit()
            return default
        try:
            return json.loads(value_raw)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    def xǁKVStoreǁget__mutmut_4(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        self._evict_expired()
        conn = self._get_conn()
        row = None
        if row is None:
            return default
        value_raw, expires_at = row
        if expires_at is not None and time.time() > expires_at:
            conn.execute(
                "DELETE FROM kv_store WHERE key = ? AND namespace = ?", (key, namespace),
            )
            conn.commit()
            return default
        try:
            return json.loads(value_raw)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    def xǁKVStoreǁget__mutmut_5(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute(
            None,
            (key, namespace),
        ).fetchone()
        if row is None:
            return default
        value_raw, expires_at = row
        if expires_at is not None and time.time() > expires_at:
            conn.execute(
                "DELETE FROM kv_store WHERE key = ? AND namespace = ?", (key, namespace),
            )
            conn.commit()
            return default
        try:
            return json.loads(value_raw)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    def xǁKVStoreǁget__mutmut_6(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value, expires_at FROM kv_store WHERE key = ? AND namespace = ?",
            None,
        ).fetchone()
        if row is None:
            return default
        value_raw, expires_at = row
        if expires_at is not None and time.time() > expires_at:
            conn.execute(
                "DELETE FROM kv_store WHERE key = ? AND namespace = ?", (key, namespace),
            )
            conn.commit()
            return default
        try:
            return json.loads(value_raw)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    def xǁKVStoreǁget__mutmut_7(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute(
            (key, namespace),
        ).fetchone()
        if row is None:
            return default
        value_raw, expires_at = row
        if expires_at is not None and time.time() > expires_at:
            conn.execute(
                "DELETE FROM kv_store WHERE key = ? AND namespace = ?", (key, namespace),
            )
            conn.commit()
            return default
        try:
            return json.loads(value_raw)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    def xǁKVStoreǁget__mutmut_8(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value, expires_at FROM kv_store WHERE key = ? AND namespace = ?",
            ).fetchone()
        if row is None:
            return default
        value_raw, expires_at = row
        if expires_at is not None and time.time() > expires_at:
            conn.execute(
                "DELETE FROM kv_store WHERE key = ? AND namespace = ?", (key, namespace),
            )
            conn.commit()
            return default
        try:
            return json.loads(value_raw)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    def xǁKVStoreǁget__mutmut_9(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute(
            "XXSELECT value, expires_at FROM kv_store WHERE key = ? AND namespace = ?XX",
            (key, namespace),
        ).fetchone()
        if row is None:
            return default
        value_raw, expires_at = row
        if expires_at is not None and time.time() > expires_at:
            conn.execute(
                "DELETE FROM kv_store WHERE key = ? AND namespace = ?", (key, namespace),
            )
            conn.commit()
            return default
        try:
            return json.loads(value_raw)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    def xǁKVStoreǁget__mutmut_10(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute(
            "select value, expires_at from kv_store where key = ? and namespace = ?",
            (key, namespace),
        ).fetchone()
        if row is None:
            return default
        value_raw, expires_at = row
        if expires_at is not None and time.time() > expires_at:
            conn.execute(
                "DELETE FROM kv_store WHERE key = ? AND namespace = ?", (key, namespace),
            )
            conn.commit()
            return default
        try:
            return json.loads(value_raw)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    def xǁKVStoreǁget__mutmut_11(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT VALUE, EXPIRES_AT FROM KV_STORE WHERE KEY = ? AND NAMESPACE = ?",
            (key, namespace),
        ).fetchone()
        if row is None:
            return default
        value_raw, expires_at = row
        if expires_at is not None and time.time() > expires_at:
            conn.execute(
                "DELETE FROM kv_store WHERE key = ? AND namespace = ?", (key, namespace),
            )
            conn.commit()
            return default
        try:
            return json.loads(value_raw)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    def xǁKVStoreǁget__mutmut_12(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value, expires_at FROM kv_store WHERE key = ? AND namespace = ?",
            (key, namespace),
        ).fetchone()
        if row is not None:
            return default
        value_raw, expires_at = row
        if expires_at is not None and time.time() > expires_at:
            conn.execute(
                "DELETE FROM kv_store WHERE key = ? AND namespace = ?", (key, namespace),
            )
            conn.commit()
            return default
        try:
            return json.loads(value_raw)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    def xǁKVStoreǁget__mutmut_13(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value, expires_at FROM kv_store WHERE key = ? AND namespace = ?",
            (key, namespace),
        ).fetchone()
        if row is None:
            return default
        value_raw, expires_at = None
        if expires_at is not None and time.time() > expires_at:
            conn.execute(
                "DELETE FROM kv_store WHERE key = ? AND namespace = ?", (key, namespace),
            )
            conn.commit()
            return default
        try:
            return json.loads(value_raw)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    def xǁKVStoreǁget__mutmut_14(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value, expires_at FROM kv_store WHERE key = ? AND namespace = ?",
            (key, namespace),
        ).fetchone()
        if row is None:
            return default
        value_raw, expires_at = row
        if expires_at is not None or time.time() > expires_at:
            conn.execute(
                "DELETE FROM kv_store WHERE key = ? AND namespace = ?", (key, namespace),
            )
            conn.commit()
            return default
        try:
            return json.loads(value_raw)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    def xǁKVStoreǁget__mutmut_15(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value, expires_at FROM kv_store WHERE key = ? AND namespace = ?",
            (key, namespace),
        ).fetchone()
        if row is None:
            return default
        value_raw, expires_at = row
        if expires_at is None and time.time() > expires_at:
            conn.execute(
                "DELETE FROM kv_store WHERE key = ? AND namespace = ?", (key, namespace),
            )
            conn.commit()
            return default
        try:
            return json.loads(value_raw)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    def xǁKVStoreǁget__mutmut_16(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value, expires_at FROM kv_store WHERE key = ? AND namespace = ?",
            (key, namespace),
        ).fetchone()
        if row is None:
            return default
        value_raw, expires_at = row
        if expires_at is not None and time.time() >= expires_at:
            conn.execute(
                "DELETE FROM kv_store WHERE key = ? AND namespace = ?", (key, namespace),
            )
            conn.commit()
            return default
        try:
            return json.loads(value_raw)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    def xǁKVStoreǁget__mutmut_17(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value, expires_at FROM kv_store WHERE key = ? AND namespace = ?",
            (key, namespace),
        ).fetchone()
        if row is None:
            return default
        value_raw, expires_at = row
        if expires_at is not None and time.time() > expires_at:
            conn.execute(
                None, (key, namespace),
            )
            conn.commit()
            return default
        try:
            return json.loads(value_raw)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    def xǁKVStoreǁget__mutmut_18(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value, expires_at FROM kv_store WHERE key = ? AND namespace = ?",
            (key, namespace),
        ).fetchone()
        if row is None:
            return default
        value_raw, expires_at = row
        if expires_at is not None and time.time() > expires_at:
            conn.execute(
                "DELETE FROM kv_store WHERE key = ? AND namespace = ?", None,
            )
            conn.commit()
            return default
        try:
            return json.loads(value_raw)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    def xǁKVStoreǁget__mutmut_19(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value, expires_at FROM kv_store WHERE key = ? AND namespace = ?",
            (key, namespace),
        ).fetchone()
        if row is None:
            return default
        value_raw, expires_at = row
        if expires_at is not None and time.time() > expires_at:
            conn.execute(
                (key, namespace),
            )
            conn.commit()
            return default
        try:
            return json.loads(value_raw)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    def xǁKVStoreǁget__mutmut_20(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value, expires_at FROM kv_store WHERE key = ? AND namespace = ?",
            (key, namespace),
        ).fetchone()
        if row is None:
            return default
        value_raw, expires_at = row
        if expires_at is not None and time.time() > expires_at:
            conn.execute(
                "DELETE FROM kv_store WHERE key = ? AND namespace = ?", )
            conn.commit()
            return default
        try:
            return json.loads(value_raw)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    def xǁKVStoreǁget__mutmut_21(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value, expires_at FROM kv_store WHERE key = ? AND namespace = ?",
            (key, namespace),
        ).fetchone()
        if row is None:
            return default
        value_raw, expires_at = row
        if expires_at is not None and time.time() > expires_at:
            conn.execute(
                "XXDELETE FROM kv_store WHERE key = ? AND namespace = ?XX", (key, namespace),
            )
            conn.commit()
            return default
        try:
            return json.loads(value_raw)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    def xǁKVStoreǁget__mutmut_22(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value, expires_at FROM kv_store WHERE key = ? AND namespace = ?",
            (key, namespace),
        ).fetchone()
        if row is None:
            return default
        value_raw, expires_at = row
        if expires_at is not None and time.time() > expires_at:
            conn.execute(
                "delete from kv_store where key = ? and namespace = ?", (key, namespace),
            )
            conn.commit()
            return default
        try:
            return json.loads(value_raw)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    def xǁKVStoreǁget__mutmut_23(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value, expires_at FROM kv_store WHERE key = ? AND namespace = ?",
            (key, namespace),
        ).fetchone()
        if row is None:
            return default
        value_raw, expires_at = row
        if expires_at is not None and time.time() > expires_at:
            conn.execute(
                "DELETE FROM KV_STORE WHERE KEY = ? AND NAMESPACE = ?", (key, namespace),
            )
            conn.commit()
            return default
        try:
            return json.loads(value_raw)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    def xǁKVStoreǁget__mutmut_24(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value, expires_at FROM kv_store WHERE key = ? AND namespace = ?",
            (key, namespace),
        ).fetchone()
        if row is None:
            return default
        value_raw, expires_at = row
        if expires_at is not None and time.time() > expires_at:
            conn.execute(
                "DELETE FROM kv_store WHERE key = ? AND namespace = ?", (key, namespace),
            )
            conn.commit()
            return default
        try:
            return json.loads(None)
        except (json.JSONDecodeError, TypeError):
            return value_raw

    @_mutmut_mutated(mutants_xǁKVStoreǁdelete__mutmut)
    def delete(self, key: str, namespace: str = "default"):
        conn = self._get_conn()
        conn.execute(
            "DELETE FROM kv_store WHERE key = ? AND namespace = ?", (key, namespace),
        )
        conn.commit()

    def xǁKVStoreǁdelete__mutmut_orig(self, key: str, namespace: str = "default"):
        conn = self._get_conn()
        conn.execute(
            "DELETE FROM kv_store WHERE key = ? AND namespace = ?", (key, namespace),
        )
        conn.commit()

    def xǁKVStoreǁdelete__mutmut_1(self, key: str, namespace: str = "XXdefaultXX"):
        conn = self._get_conn()
        conn.execute(
            "DELETE FROM kv_store WHERE key = ? AND namespace = ?", (key, namespace),
        )
        conn.commit()

    def xǁKVStoreǁdelete__mutmut_2(self, key: str, namespace: str = "DEFAULT"):
        conn = self._get_conn()
        conn.execute(
            "DELETE FROM kv_store WHERE key = ? AND namespace = ?", (key, namespace),
        )
        conn.commit()

    def xǁKVStoreǁdelete__mutmut_3(self, key: str, namespace: str = "default"):
        conn = None
        conn.execute(
            "DELETE FROM kv_store WHERE key = ? AND namespace = ?", (key, namespace),
        )
        conn.commit()

    def xǁKVStoreǁdelete__mutmut_4(self, key: str, namespace: str = "default"):
        conn = self._get_conn()
        conn.execute(
            None, (key, namespace),
        )
        conn.commit()

    def xǁKVStoreǁdelete__mutmut_5(self, key: str, namespace: str = "default"):
        conn = self._get_conn()
        conn.execute(
            "DELETE FROM kv_store WHERE key = ? AND namespace = ?", None,
        )
        conn.commit()

    def xǁKVStoreǁdelete__mutmut_6(self, key: str, namespace: str = "default"):
        conn = self._get_conn()
        conn.execute(
            (key, namespace),
        )
        conn.commit()

    def xǁKVStoreǁdelete__mutmut_7(self, key: str, namespace: str = "default"):
        conn = self._get_conn()
        conn.execute(
            "DELETE FROM kv_store WHERE key = ? AND namespace = ?", )
        conn.commit()

    def xǁKVStoreǁdelete__mutmut_8(self, key: str, namespace: str = "default"):
        conn = self._get_conn()
        conn.execute(
            "XXDELETE FROM kv_store WHERE key = ? AND namespace = ?XX", (key, namespace),
        )
        conn.commit()

    def xǁKVStoreǁdelete__mutmut_9(self, key: str, namespace: str = "default"):
        conn = self._get_conn()
        conn.execute(
            "delete from kv_store where key = ? and namespace = ?", (key, namespace),
        )
        conn.commit()

    def xǁKVStoreǁdelete__mutmut_10(self, key: str, namespace: str = "default"):
        conn = self._get_conn()
        conn.execute(
            "DELETE FROM KV_STORE WHERE KEY = ? AND NAMESPACE = ?", (key, namespace),
        )
        conn.commit()

    @_mutmut_mutated(mutants_xǁKVStoreǁpop__mutmut)
    def pop(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        value = self.get(key, namespace, default)
        self.delete(key, namespace)
        return value

    def xǁKVStoreǁpop__mutmut_orig(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        value = self.get(key, namespace, default)
        self.delete(key, namespace)
        return value

    def xǁKVStoreǁpop__mutmut_1(self, key: str, namespace: str = "XXdefaultXX", default: Any = None) -> Any:
        value = self.get(key, namespace, default)
        self.delete(key, namespace)
        return value

    def xǁKVStoreǁpop__mutmut_2(self, key: str, namespace: str = "DEFAULT", default: Any = None) -> Any:
        value = self.get(key, namespace, default)
        self.delete(key, namespace)
        return value

    def xǁKVStoreǁpop__mutmut_3(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        value = None
        self.delete(key, namespace)
        return value

    def xǁKVStoreǁpop__mutmut_4(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        value = self.get(None, namespace, default)
        self.delete(key, namespace)
        return value

    def xǁKVStoreǁpop__mutmut_5(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        value = self.get(key, None, default)
        self.delete(key, namespace)
        return value

    def xǁKVStoreǁpop__mutmut_6(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        value = self.get(key, namespace, None)
        self.delete(key, namespace)
        return value

    def xǁKVStoreǁpop__mutmut_7(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        value = self.get(namespace, default)
        self.delete(key, namespace)
        return value

    def xǁKVStoreǁpop__mutmut_8(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        value = self.get(key, default)
        self.delete(key, namespace)
        return value

    def xǁKVStoreǁpop__mutmut_9(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        value = self.get(key, namespace, )
        self.delete(key, namespace)
        return value

    def xǁKVStoreǁpop__mutmut_10(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        value = self.get(key, namespace, default)
        self.delete(None, namespace)
        return value

    def xǁKVStoreǁpop__mutmut_11(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        value = self.get(key, namespace, default)
        self.delete(key, None)
        return value

    def xǁKVStoreǁpop__mutmut_12(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        value = self.get(key, namespace, default)
        self.delete(namespace)
        return value

    def xǁKVStoreǁpop__mutmut_13(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        value = self.get(key, namespace, default)
        self.delete(key, )
        return value

    @_mutmut_mutated(mutants_xǁKVStoreǁkeys__mutmut)
    def keys(self, namespace: str = "default") -> list[str]:
        self._evict_expired()
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT key FROM kv_store WHERE namespace = ?", (namespace,),
        ).fetchall()
        return [r[0] for r in rows]

    def xǁKVStoreǁkeys__mutmut_orig(self, namespace: str = "default") -> list[str]:
        self._evict_expired()
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT key FROM kv_store WHERE namespace = ?", (namespace,),
        ).fetchall()
        return [r[0] for r in rows]

    def xǁKVStoreǁkeys__mutmut_1(self, namespace: str = "XXdefaultXX") -> list[str]:
        self._evict_expired()
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT key FROM kv_store WHERE namespace = ?", (namespace,),
        ).fetchall()
        return [r[0] for r in rows]

    def xǁKVStoreǁkeys__mutmut_2(self, namespace: str = "DEFAULT") -> list[str]:
        self._evict_expired()
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT key FROM kv_store WHERE namespace = ?", (namespace,),
        ).fetchall()
        return [r[0] for r in rows]

    def xǁKVStoreǁkeys__mutmut_3(self, namespace: str = "default") -> list[str]:
        self._evict_expired()
        conn = None
        rows = conn.execute(
            "SELECT key FROM kv_store WHERE namespace = ?", (namespace,),
        ).fetchall()
        return [r[0] for r in rows]

    def xǁKVStoreǁkeys__mutmut_4(self, namespace: str = "default") -> list[str]:
        self._evict_expired()
        conn = self._get_conn()
        rows = None
        return [r[0] for r in rows]

    def xǁKVStoreǁkeys__mutmut_5(self, namespace: str = "default") -> list[str]:
        self._evict_expired()
        conn = self._get_conn()
        rows = conn.execute(
            None, (namespace,),
        ).fetchall()
        return [r[0] for r in rows]

    def xǁKVStoreǁkeys__mutmut_6(self, namespace: str = "default") -> list[str]:
        self._evict_expired()
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT key FROM kv_store WHERE namespace = ?", None,
        ).fetchall()
        return [r[0] for r in rows]

    def xǁKVStoreǁkeys__mutmut_7(self, namespace: str = "default") -> list[str]:
        self._evict_expired()
        conn = self._get_conn()
        rows = conn.execute(
            (namespace,),
        ).fetchall()
        return [r[0] for r in rows]

    def xǁKVStoreǁkeys__mutmut_8(self, namespace: str = "default") -> list[str]:
        self._evict_expired()
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT key FROM kv_store WHERE namespace = ?", ).fetchall()
        return [r[0] for r in rows]

    def xǁKVStoreǁkeys__mutmut_9(self, namespace: str = "default") -> list[str]:
        self._evict_expired()
        conn = self._get_conn()
        rows = conn.execute(
            "XXSELECT key FROM kv_store WHERE namespace = ?XX", (namespace,),
        ).fetchall()
        return [r[0] for r in rows]

    def xǁKVStoreǁkeys__mutmut_10(self, namespace: str = "default") -> list[str]:
        self._evict_expired()
        conn = self._get_conn()
        rows = conn.execute(
            "select key from kv_store where namespace = ?", (namespace,),
        ).fetchall()
        return [r[0] for r in rows]

    def xǁKVStoreǁkeys__mutmut_11(self, namespace: str = "default") -> list[str]:
        self._evict_expired()
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT KEY FROM KV_STORE WHERE NAMESPACE = ?", (namespace,),
        ).fetchall()
        return [r[0] for r in rows]

    def xǁKVStoreǁkeys__mutmut_12(self, namespace: str = "default") -> list[str]:
        self._evict_expired()
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT key FROM kv_store WHERE namespace = ?", (namespace,),
        ).fetchall()
        return [r[1] for r in rows]

    @_mutmut_mutated(mutants_xǁKVStoreǁclear__mutmut)
    def clear(self, namespace: str | None = None):
        conn = self._get_conn()
        if namespace:
            conn.execute("DELETE FROM kv_store WHERE namespace = ?", (namespace,))
        else:
            conn.execute("DELETE FROM kv_store")
        conn.commit()

    def xǁKVStoreǁclear__mutmut_orig(self, namespace: str | None = None):
        conn = self._get_conn()
        if namespace:
            conn.execute("DELETE FROM kv_store WHERE namespace = ?", (namespace,))
        else:
            conn.execute("DELETE FROM kv_store")
        conn.commit()

    def xǁKVStoreǁclear__mutmut_1(self, namespace: str | None = None):
        conn = None
        if namespace:
            conn.execute("DELETE FROM kv_store WHERE namespace = ?", (namespace,))
        else:
            conn.execute("DELETE FROM kv_store")
        conn.commit()

    def xǁKVStoreǁclear__mutmut_2(self, namespace: str | None = None):
        conn = self._get_conn()
        if namespace:
            conn.execute(None, (namespace,))
        else:
            conn.execute("DELETE FROM kv_store")
        conn.commit()

    def xǁKVStoreǁclear__mutmut_3(self, namespace: str | None = None):
        conn = self._get_conn()
        if namespace:
            conn.execute("DELETE FROM kv_store WHERE namespace = ?", None)
        else:
            conn.execute("DELETE FROM kv_store")
        conn.commit()

    def xǁKVStoreǁclear__mutmut_4(self, namespace: str | None = None):
        conn = self._get_conn()
        if namespace:
            conn.execute((namespace,))
        else:
            conn.execute("DELETE FROM kv_store")
        conn.commit()

    def xǁKVStoreǁclear__mutmut_5(self, namespace: str | None = None):
        conn = self._get_conn()
        if namespace:
            conn.execute("DELETE FROM kv_store WHERE namespace = ?", )
        else:
            conn.execute("DELETE FROM kv_store")
        conn.commit()

    def xǁKVStoreǁclear__mutmut_6(self, namespace: str | None = None):
        conn = self._get_conn()
        if namespace:
            conn.execute("XXDELETE FROM kv_store WHERE namespace = ?XX", (namespace,))
        else:
            conn.execute("DELETE FROM kv_store")
        conn.commit()

    def xǁKVStoreǁclear__mutmut_7(self, namespace: str | None = None):
        conn = self._get_conn()
        if namespace:
            conn.execute("delete from kv_store where namespace = ?", (namespace,))
        else:
            conn.execute("DELETE FROM kv_store")
        conn.commit()

    def xǁKVStoreǁclear__mutmut_8(self, namespace: str | None = None):
        conn = self._get_conn()
        if namespace:
            conn.execute("DELETE FROM KV_STORE WHERE NAMESPACE = ?", (namespace,))
        else:
            conn.execute("DELETE FROM kv_store")
        conn.commit()

    def xǁKVStoreǁclear__mutmut_9(self, namespace: str | None = None):
        conn = self._get_conn()
        if namespace:
            conn.execute("DELETE FROM kv_store WHERE namespace = ?", (namespace,))
        else:
            conn.execute(None)
        conn.commit()

    def xǁKVStoreǁclear__mutmut_10(self, namespace: str | None = None):
        conn = self._get_conn()
        if namespace:
            conn.execute("DELETE FROM kv_store WHERE namespace = ?", (namespace,))
        else:
            conn.execute("XXDELETE FROM kv_storeXX")
        conn.commit()

    def xǁKVStoreǁclear__mutmut_11(self, namespace: str | None = None):
        conn = self._get_conn()
        if namespace:
            conn.execute("DELETE FROM kv_store WHERE namespace = ?", (namespace,))
        else:
            conn.execute("delete from kv_store")
        conn.commit()

    def xǁKVStoreǁclear__mutmut_12(self, namespace: str | None = None):
        conn = self._get_conn()
        if namespace:
            conn.execute("DELETE FROM kv_store WHERE namespace = ?", (namespace,))
        else:
            conn.execute("DELETE FROM KV_STORE")
        conn.commit()

    @_mutmut_mutated(mutants_xǁKVStoreǁcleanup__mutmut)
    def cleanup(self):
        self._evict_expired()
        conn = self._get_conn()
        conn.execute("VACUUM")
        conn.commit()

    def xǁKVStoreǁcleanup__mutmut_orig(self):
        self._evict_expired()
        conn = self._get_conn()
        conn.execute("VACUUM")
        conn.commit()

    def xǁKVStoreǁcleanup__mutmut_1(self):
        self._evict_expired()
        conn = None
        conn.execute("VACUUM")
        conn.commit()

    def xǁKVStoreǁcleanup__mutmut_2(self):
        self._evict_expired()
        conn = self._get_conn()
        conn.execute(None)
        conn.commit()

    def xǁKVStoreǁcleanup__mutmut_3(self):
        self._evict_expired()
        conn = self._get_conn()
        conn.execute("XXVACUUMXX")
        conn.commit()

    def xǁKVStoreǁcleanup__mutmut_4(self):
        self._evict_expired()
        conn = self._get_conn()
        conn.execute("vacuum")
        conn.commit()

    @property
    def stats(self) -> dict:
        self._evict_expired()
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) FROM kv_store").fetchone()
        return {"size": row[0] if row else 0}

mutants_xǁKVStoreǁ__init____mutmut['_mutmut_orig'] = KVStore.xǁKVStoreǁ__init____mutmut_orig # type: ignore # mutmut generated
mutants_xǁKVStoreǁ__init____mutmut['xǁKVStoreǁ__init____mutmut_1'] = KVStore.xǁKVStoreǁ__init____mutmut_1 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ__init____mutmut['xǁKVStoreǁ__init____mutmut_2'] = KVStore.xǁKVStoreǁ__init____mutmut_2 # type: ignore # mutmut generated

mutants_xǁKVStoreǁ_get_conn__mutmut['_mutmut_orig'] = KVStore.xǁKVStoreǁ_get_conn__mutmut_orig # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_get_conn__mutmut['xǁKVStoreǁ_get_conn__mutmut_1'] = KVStore.xǁKVStoreǁ_get_conn__mutmut_1 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_get_conn__mutmut['xǁKVStoreǁ_get_conn__mutmut_2'] = KVStore.xǁKVStoreǁ_get_conn__mutmut_2 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_get_conn__mutmut['xǁKVStoreǁ_get_conn__mutmut_3'] = KVStore.xǁKVStoreǁ_get_conn__mutmut_3 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_get_conn__mutmut['xǁKVStoreǁ_get_conn__mutmut_4'] = KVStore.xǁKVStoreǁ_get_conn__mutmut_4 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_get_conn__mutmut['xǁKVStoreǁ_get_conn__mutmut_5'] = KVStore.xǁKVStoreǁ_get_conn__mutmut_5 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_get_conn__mutmut['xǁKVStoreǁ_get_conn__mutmut_6'] = KVStore.xǁKVStoreǁ_get_conn__mutmut_6 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_get_conn__mutmut['xǁKVStoreǁ_get_conn__mutmut_7'] = KVStore.xǁKVStoreǁ_get_conn__mutmut_7 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_get_conn__mutmut['xǁKVStoreǁ_get_conn__mutmut_8'] = KVStore.xǁKVStoreǁ_get_conn__mutmut_8 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_get_conn__mutmut['xǁKVStoreǁ_get_conn__mutmut_9'] = KVStore.xǁKVStoreǁ_get_conn__mutmut_9 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_get_conn__mutmut['xǁKVStoreǁ_get_conn__mutmut_10'] = KVStore.xǁKVStoreǁ_get_conn__mutmut_10 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_get_conn__mutmut['xǁKVStoreǁ_get_conn__mutmut_11'] = KVStore.xǁKVStoreǁ_get_conn__mutmut_11 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_get_conn__mutmut['xǁKVStoreǁ_get_conn__mutmut_12'] = KVStore.xǁKVStoreǁ_get_conn__mutmut_12 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_get_conn__mutmut['xǁKVStoreǁ_get_conn__mutmut_13'] = KVStore.xǁKVStoreǁ_get_conn__mutmut_13 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_get_conn__mutmut['xǁKVStoreǁ_get_conn__mutmut_14'] = KVStore.xǁKVStoreǁ_get_conn__mutmut_14 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_get_conn__mutmut['xǁKVStoreǁ_get_conn__mutmut_15'] = KVStore.xǁKVStoreǁ_get_conn__mutmut_15 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_get_conn__mutmut['xǁKVStoreǁ_get_conn__mutmut_16'] = KVStore.xǁKVStoreǁ_get_conn__mutmut_16 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_get_conn__mutmut['xǁKVStoreǁ_get_conn__mutmut_17'] = KVStore.xǁKVStoreǁ_get_conn__mutmut_17 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_get_conn__mutmut['xǁKVStoreǁ_get_conn__mutmut_18'] = KVStore.xǁKVStoreǁ_get_conn__mutmut_18 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_get_conn__mutmut['xǁKVStoreǁ_get_conn__mutmut_19'] = KVStore.xǁKVStoreǁ_get_conn__mutmut_19 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_get_conn__mutmut['xǁKVStoreǁ_get_conn__mutmut_20'] = KVStore.xǁKVStoreǁ_get_conn__mutmut_20 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_get_conn__mutmut['xǁKVStoreǁ_get_conn__mutmut_21'] = KVStore.xǁKVStoreǁ_get_conn__mutmut_21 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_get_conn__mutmut['xǁKVStoreǁ_get_conn__mutmut_22'] = KVStore.xǁKVStoreǁ_get_conn__mutmut_22 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_get_conn__mutmut['xǁKVStoreǁ_get_conn__mutmut_23'] = KVStore.xǁKVStoreǁ_get_conn__mutmut_23 # type: ignore # mutmut generated

mutants_xǁKVStoreǁ_init_db__mutmut['_mutmut_orig'] = KVStore.xǁKVStoreǁ_init_db__mutmut_orig # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_init_db__mutmut['xǁKVStoreǁ_init_db__mutmut_1'] = KVStore.xǁKVStoreǁ_init_db__mutmut_1 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_init_db__mutmut['xǁKVStoreǁ_init_db__mutmut_2'] = KVStore.xǁKVStoreǁ_init_db__mutmut_2 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_init_db__mutmut['xǁKVStoreǁ_init_db__mutmut_3'] = KVStore.xǁKVStoreǁ_init_db__mutmut_3 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_init_db__mutmut['xǁKVStoreǁ_init_db__mutmut_4'] = KVStore.xǁKVStoreǁ_init_db__mutmut_4 # type: ignore # mutmut generated

mutants_xǁKVStoreǁ_evict_expired__mutmut['_mutmut_orig'] = KVStore.xǁKVStoreǁ_evict_expired__mutmut_orig # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_evict_expired__mutmut['xǁKVStoreǁ_evict_expired__mutmut_1'] = KVStore.xǁKVStoreǁ_evict_expired__mutmut_1 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_evict_expired__mutmut['xǁKVStoreǁ_evict_expired__mutmut_2'] = KVStore.xǁKVStoreǁ_evict_expired__mutmut_2 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_evict_expired__mutmut['xǁKVStoreǁ_evict_expired__mutmut_3'] = KVStore.xǁKVStoreǁ_evict_expired__mutmut_3 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_evict_expired__mutmut['xǁKVStoreǁ_evict_expired__mutmut_4'] = KVStore.xǁKVStoreǁ_evict_expired__mutmut_4 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_evict_expired__mutmut['xǁKVStoreǁ_evict_expired__mutmut_5'] = KVStore.xǁKVStoreǁ_evict_expired__mutmut_5 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_evict_expired__mutmut['xǁKVStoreǁ_evict_expired__mutmut_6'] = KVStore.xǁKVStoreǁ_evict_expired__mutmut_6 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_evict_expired__mutmut['xǁKVStoreǁ_evict_expired__mutmut_7'] = KVStore.xǁKVStoreǁ_evict_expired__mutmut_7 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_evict_expired__mutmut['xǁKVStoreǁ_evict_expired__mutmut_8'] = KVStore.xǁKVStoreǁ_evict_expired__mutmut_8 # type: ignore # mutmut generated
mutants_xǁKVStoreǁ_evict_expired__mutmut['xǁKVStoreǁ_evict_expired__mutmut_9'] = KVStore.xǁKVStoreǁ_evict_expired__mutmut_9 # type: ignore # mutmut generated

mutants_xǁKVStoreǁset__mutmut['_mutmut_orig'] = KVStore.xǁKVStoreǁset__mutmut_orig # type: ignore # mutmut generated
mutants_xǁKVStoreǁset__mutmut['xǁKVStoreǁset__mutmut_1'] = KVStore.xǁKVStoreǁset__mutmut_1 # type: ignore # mutmut generated
mutants_xǁKVStoreǁset__mutmut['xǁKVStoreǁset__mutmut_2'] = KVStore.xǁKVStoreǁset__mutmut_2 # type: ignore # mutmut generated
mutants_xǁKVStoreǁset__mutmut['xǁKVStoreǁset__mutmut_3'] = KVStore.xǁKVStoreǁset__mutmut_3 # type: ignore # mutmut generated
mutants_xǁKVStoreǁset__mutmut['xǁKVStoreǁset__mutmut_4'] = KVStore.xǁKVStoreǁset__mutmut_4 # type: ignore # mutmut generated
mutants_xǁKVStoreǁset__mutmut['xǁKVStoreǁset__mutmut_5'] = KVStore.xǁKVStoreǁset__mutmut_5 # type: ignore # mutmut generated
mutants_xǁKVStoreǁset__mutmut['xǁKVStoreǁset__mutmut_6'] = KVStore.xǁKVStoreǁset__mutmut_6 # type: ignore # mutmut generated
mutants_xǁKVStoreǁset__mutmut['xǁKVStoreǁset__mutmut_7'] = KVStore.xǁKVStoreǁset__mutmut_7 # type: ignore # mutmut generated
mutants_xǁKVStoreǁset__mutmut['xǁKVStoreǁset__mutmut_8'] = KVStore.xǁKVStoreǁset__mutmut_8 # type: ignore # mutmut generated
mutants_xǁKVStoreǁset__mutmut['xǁKVStoreǁset__mutmut_9'] = KVStore.xǁKVStoreǁset__mutmut_9 # type: ignore # mutmut generated
mutants_xǁKVStoreǁset__mutmut['xǁKVStoreǁset__mutmut_10'] = KVStore.xǁKVStoreǁset__mutmut_10 # type: ignore # mutmut generated
mutants_xǁKVStoreǁset__mutmut['xǁKVStoreǁset__mutmut_11'] = KVStore.xǁKVStoreǁset__mutmut_11 # type: ignore # mutmut generated
mutants_xǁKVStoreǁset__mutmut['xǁKVStoreǁset__mutmut_12'] = KVStore.xǁKVStoreǁset__mutmut_12 # type: ignore # mutmut generated
mutants_xǁKVStoreǁset__mutmut['xǁKVStoreǁset__mutmut_13'] = KVStore.xǁKVStoreǁset__mutmut_13 # type: ignore # mutmut generated
mutants_xǁKVStoreǁset__mutmut['xǁKVStoreǁset__mutmut_14'] = KVStore.xǁKVStoreǁset__mutmut_14 # type: ignore # mutmut generated
mutants_xǁKVStoreǁset__mutmut['xǁKVStoreǁset__mutmut_15'] = KVStore.xǁKVStoreǁset__mutmut_15 # type: ignore # mutmut generated
mutants_xǁKVStoreǁset__mutmut['xǁKVStoreǁset__mutmut_16'] = KVStore.xǁKVStoreǁset__mutmut_16 # type: ignore # mutmut generated

mutants_xǁKVStoreǁget__mutmut['_mutmut_orig'] = KVStore.xǁKVStoreǁget__mutmut_orig # type: ignore # mutmut generated
mutants_xǁKVStoreǁget__mutmut['xǁKVStoreǁget__mutmut_1'] = KVStore.xǁKVStoreǁget__mutmut_1 # type: ignore # mutmut generated
mutants_xǁKVStoreǁget__mutmut['xǁKVStoreǁget__mutmut_2'] = KVStore.xǁKVStoreǁget__mutmut_2 # type: ignore # mutmut generated
mutants_xǁKVStoreǁget__mutmut['xǁKVStoreǁget__mutmut_3'] = KVStore.xǁKVStoreǁget__mutmut_3 # type: ignore # mutmut generated
mutants_xǁKVStoreǁget__mutmut['xǁKVStoreǁget__mutmut_4'] = KVStore.xǁKVStoreǁget__mutmut_4 # type: ignore # mutmut generated
mutants_xǁKVStoreǁget__mutmut['xǁKVStoreǁget__mutmut_5'] = KVStore.xǁKVStoreǁget__mutmut_5 # type: ignore # mutmut generated
mutants_xǁKVStoreǁget__mutmut['xǁKVStoreǁget__mutmut_6'] = KVStore.xǁKVStoreǁget__mutmut_6 # type: ignore # mutmut generated
mutants_xǁKVStoreǁget__mutmut['xǁKVStoreǁget__mutmut_7'] = KVStore.xǁKVStoreǁget__mutmut_7 # type: ignore # mutmut generated
mutants_xǁKVStoreǁget__mutmut['xǁKVStoreǁget__mutmut_8'] = KVStore.xǁKVStoreǁget__mutmut_8 # type: ignore # mutmut generated
mutants_xǁKVStoreǁget__mutmut['xǁKVStoreǁget__mutmut_9'] = KVStore.xǁKVStoreǁget__mutmut_9 # type: ignore # mutmut generated
mutants_xǁKVStoreǁget__mutmut['xǁKVStoreǁget__mutmut_10'] = KVStore.xǁKVStoreǁget__mutmut_10 # type: ignore # mutmut generated
mutants_xǁKVStoreǁget__mutmut['xǁKVStoreǁget__mutmut_11'] = KVStore.xǁKVStoreǁget__mutmut_11 # type: ignore # mutmut generated
mutants_xǁKVStoreǁget__mutmut['xǁKVStoreǁget__mutmut_12'] = KVStore.xǁKVStoreǁget__mutmut_12 # type: ignore # mutmut generated
mutants_xǁKVStoreǁget__mutmut['xǁKVStoreǁget__mutmut_13'] = KVStore.xǁKVStoreǁget__mutmut_13 # type: ignore # mutmut generated
mutants_xǁKVStoreǁget__mutmut['xǁKVStoreǁget__mutmut_14'] = KVStore.xǁKVStoreǁget__mutmut_14 # type: ignore # mutmut generated
mutants_xǁKVStoreǁget__mutmut['xǁKVStoreǁget__mutmut_15'] = KVStore.xǁKVStoreǁget__mutmut_15 # type: ignore # mutmut generated
mutants_xǁKVStoreǁget__mutmut['xǁKVStoreǁget__mutmut_16'] = KVStore.xǁKVStoreǁget__mutmut_16 # type: ignore # mutmut generated
mutants_xǁKVStoreǁget__mutmut['xǁKVStoreǁget__mutmut_17'] = KVStore.xǁKVStoreǁget__mutmut_17 # type: ignore # mutmut generated
mutants_xǁKVStoreǁget__mutmut['xǁKVStoreǁget__mutmut_18'] = KVStore.xǁKVStoreǁget__mutmut_18 # type: ignore # mutmut generated
mutants_xǁKVStoreǁget__mutmut['xǁKVStoreǁget__mutmut_19'] = KVStore.xǁKVStoreǁget__mutmut_19 # type: ignore # mutmut generated
mutants_xǁKVStoreǁget__mutmut['xǁKVStoreǁget__mutmut_20'] = KVStore.xǁKVStoreǁget__mutmut_20 # type: ignore # mutmut generated
mutants_xǁKVStoreǁget__mutmut['xǁKVStoreǁget__mutmut_21'] = KVStore.xǁKVStoreǁget__mutmut_21 # type: ignore # mutmut generated
mutants_xǁKVStoreǁget__mutmut['xǁKVStoreǁget__mutmut_22'] = KVStore.xǁKVStoreǁget__mutmut_22 # type: ignore # mutmut generated
mutants_xǁKVStoreǁget__mutmut['xǁKVStoreǁget__mutmut_23'] = KVStore.xǁKVStoreǁget__mutmut_23 # type: ignore # mutmut generated
mutants_xǁKVStoreǁget__mutmut['xǁKVStoreǁget__mutmut_24'] = KVStore.xǁKVStoreǁget__mutmut_24 # type: ignore # mutmut generated

mutants_xǁKVStoreǁdelete__mutmut['_mutmut_orig'] = KVStore.xǁKVStoreǁdelete__mutmut_orig # type: ignore # mutmut generated
mutants_xǁKVStoreǁdelete__mutmut['xǁKVStoreǁdelete__mutmut_1'] = KVStore.xǁKVStoreǁdelete__mutmut_1 # type: ignore # mutmut generated
mutants_xǁKVStoreǁdelete__mutmut['xǁKVStoreǁdelete__mutmut_2'] = KVStore.xǁKVStoreǁdelete__mutmut_2 # type: ignore # mutmut generated
mutants_xǁKVStoreǁdelete__mutmut['xǁKVStoreǁdelete__mutmut_3'] = KVStore.xǁKVStoreǁdelete__mutmut_3 # type: ignore # mutmut generated
mutants_xǁKVStoreǁdelete__mutmut['xǁKVStoreǁdelete__mutmut_4'] = KVStore.xǁKVStoreǁdelete__mutmut_4 # type: ignore # mutmut generated
mutants_xǁKVStoreǁdelete__mutmut['xǁKVStoreǁdelete__mutmut_5'] = KVStore.xǁKVStoreǁdelete__mutmut_5 # type: ignore # mutmut generated
mutants_xǁKVStoreǁdelete__mutmut['xǁKVStoreǁdelete__mutmut_6'] = KVStore.xǁKVStoreǁdelete__mutmut_6 # type: ignore # mutmut generated
mutants_xǁKVStoreǁdelete__mutmut['xǁKVStoreǁdelete__mutmut_7'] = KVStore.xǁKVStoreǁdelete__mutmut_7 # type: ignore # mutmut generated
mutants_xǁKVStoreǁdelete__mutmut['xǁKVStoreǁdelete__mutmut_8'] = KVStore.xǁKVStoreǁdelete__mutmut_8 # type: ignore # mutmut generated
mutants_xǁKVStoreǁdelete__mutmut['xǁKVStoreǁdelete__mutmut_9'] = KVStore.xǁKVStoreǁdelete__mutmut_9 # type: ignore # mutmut generated
mutants_xǁKVStoreǁdelete__mutmut['xǁKVStoreǁdelete__mutmut_10'] = KVStore.xǁKVStoreǁdelete__mutmut_10 # type: ignore # mutmut generated

mutants_xǁKVStoreǁpop__mutmut['_mutmut_orig'] = KVStore.xǁKVStoreǁpop__mutmut_orig # type: ignore # mutmut generated
mutants_xǁKVStoreǁpop__mutmut['xǁKVStoreǁpop__mutmut_1'] = KVStore.xǁKVStoreǁpop__mutmut_1 # type: ignore # mutmut generated
mutants_xǁKVStoreǁpop__mutmut['xǁKVStoreǁpop__mutmut_2'] = KVStore.xǁKVStoreǁpop__mutmut_2 # type: ignore # mutmut generated
mutants_xǁKVStoreǁpop__mutmut['xǁKVStoreǁpop__mutmut_3'] = KVStore.xǁKVStoreǁpop__mutmut_3 # type: ignore # mutmut generated
mutants_xǁKVStoreǁpop__mutmut['xǁKVStoreǁpop__mutmut_4'] = KVStore.xǁKVStoreǁpop__mutmut_4 # type: ignore # mutmut generated
mutants_xǁKVStoreǁpop__mutmut['xǁKVStoreǁpop__mutmut_5'] = KVStore.xǁKVStoreǁpop__mutmut_5 # type: ignore # mutmut generated
mutants_xǁKVStoreǁpop__mutmut['xǁKVStoreǁpop__mutmut_6'] = KVStore.xǁKVStoreǁpop__mutmut_6 # type: ignore # mutmut generated
mutants_xǁKVStoreǁpop__mutmut['xǁKVStoreǁpop__mutmut_7'] = KVStore.xǁKVStoreǁpop__mutmut_7 # type: ignore # mutmut generated
mutants_xǁKVStoreǁpop__mutmut['xǁKVStoreǁpop__mutmut_8'] = KVStore.xǁKVStoreǁpop__mutmut_8 # type: ignore # mutmut generated
mutants_xǁKVStoreǁpop__mutmut['xǁKVStoreǁpop__mutmut_9'] = KVStore.xǁKVStoreǁpop__mutmut_9 # type: ignore # mutmut generated
mutants_xǁKVStoreǁpop__mutmut['xǁKVStoreǁpop__mutmut_10'] = KVStore.xǁKVStoreǁpop__mutmut_10 # type: ignore # mutmut generated
mutants_xǁKVStoreǁpop__mutmut['xǁKVStoreǁpop__mutmut_11'] = KVStore.xǁKVStoreǁpop__mutmut_11 # type: ignore # mutmut generated
mutants_xǁKVStoreǁpop__mutmut['xǁKVStoreǁpop__mutmut_12'] = KVStore.xǁKVStoreǁpop__mutmut_12 # type: ignore # mutmut generated
mutants_xǁKVStoreǁpop__mutmut['xǁKVStoreǁpop__mutmut_13'] = KVStore.xǁKVStoreǁpop__mutmut_13 # type: ignore # mutmut generated

mutants_xǁKVStoreǁkeys__mutmut['_mutmut_orig'] = KVStore.xǁKVStoreǁkeys__mutmut_orig # type: ignore # mutmut generated
mutants_xǁKVStoreǁkeys__mutmut['xǁKVStoreǁkeys__mutmut_1'] = KVStore.xǁKVStoreǁkeys__mutmut_1 # type: ignore # mutmut generated
mutants_xǁKVStoreǁkeys__mutmut['xǁKVStoreǁkeys__mutmut_2'] = KVStore.xǁKVStoreǁkeys__mutmut_2 # type: ignore # mutmut generated
mutants_xǁKVStoreǁkeys__mutmut['xǁKVStoreǁkeys__mutmut_3'] = KVStore.xǁKVStoreǁkeys__mutmut_3 # type: ignore # mutmut generated
mutants_xǁKVStoreǁkeys__mutmut['xǁKVStoreǁkeys__mutmut_4'] = KVStore.xǁKVStoreǁkeys__mutmut_4 # type: ignore # mutmut generated
mutants_xǁKVStoreǁkeys__mutmut['xǁKVStoreǁkeys__mutmut_5'] = KVStore.xǁKVStoreǁkeys__mutmut_5 # type: ignore # mutmut generated
mutants_xǁKVStoreǁkeys__mutmut['xǁKVStoreǁkeys__mutmut_6'] = KVStore.xǁKVStoreǁkeys__mutmut_6 # type: ignore # mutmut generated
mutants_xǁKVStoreǁkeys__mutmut['xǁKVStoreǁkeys__mutmut_7'] = KVStore.xǁKVStoreǁkeys__mutmut_7 # type: ignore # mutmut generated
mutants_xǁKVStoreǁkeys__mutmut['xǁKVStoreǁkeys__mutmut_8'] = KVStore.xǁKVStoreǁkeys__mutmut_8 # type: ignore # mutmut generated
mutants_xǁKVStoreǁkeys__mutmut['xǁKVStoreǁkeys__mutmut_9'] = KVStore.xǁKVStoreǁkeys__mutmut_9 # type: ignore # mutmut generated
mutants_xǁKVStoreǁkeys__mutmut['xǁKVStoreǁkeys__mutmut_10'] = KVStore.xǁKVStoreǁkeys__mutmut_10 # type: ignore # mutmut generated
mutants_xǁKVStoreǁkeys__mutmut['xǁKVStoreǁkeys__mutmut_11'] = KVStore.xǁKVStoreǁkeys__mutmut_11 # type: ignore # mutmut generated
mutants_xǁKVStoreǁkeys__mutmut['xǁKVStoreǁkeys__mutmut_12'] = KVStore.xǁKVStoreǁkeys__mutmut_12 # type: ignore # mutmut generated

mutants_xǁKVStoreǁclear__mutmut['_mutmut_orig'] = KVStore.xǁKVStoreǁclear__mutmut_orig # type: ignore # mutmut generated
mutants_xǁKVStoreǁclear__mutmut['xǁKVStoreǁclear__mutmut_1'] = KVStore.xǁKVStoreǁclear__mutmut_1 # type: ignore # mutmut generated
mutants_xǁKVStoreǁclear__mutmut['xǁKVStoreǁclear__mutmut_2'] = KVStore.xǁKVStoreǁclear__mutmut_2 # type: ignore # mutmut generated
mutants_xǁKVStoreǁclear__mutmut['xǁKVStoreǁclear__mutmut_3'] = KVStore.xǁKVStoreǁclear__mutmut_3 # type: ignore # mutmut generated
mutants_xǁKVStoreǁclear__mutmut['xǁKVStoreǁclear__mutmut_4'] = KVStore.xǁKVStoreǁclear__mutmut_4 # type: ignore # mutmut generated
mutants_xǁKVStoreǁclear__mutmut['xǁKVStoreǁclear__mutmut_5'] = KVStore.xǁKVStoreǁclear__mutmut_5 # type: ignore # mutmut generated
mutants_xǁKVStoreǁclear__mutmut['xǁKVStoreǁclear__mutmut_6'] = KVStore.xǁKVStoreǁclear__mutmut_6 # type: ignore # mutmut generated
mutants_xǁKVStoreǁclear__mutmut['xǁKVStoreǁclear__mutmut_7'] = KVStore.xǁKVStoreǁclear__mutmut_7 # type: ignore # mutmut generated
mutants_xǁKVStoreǁclear__mutmut['xǁKVStoreǁclear__mutmut_8'] = KVStore.xǁKVStoreǁclear__mutmut_8 # type: ignore # mutmut generated
mutants_xǁKVStoreǁclear__mutmut['xǁKVStoreǁclear__mutmut_9'] = KVStore.xǁKVStoreǁclear__mutmut_9 # type: ignore # mutmut generated
mutants_xǁKVStoreǁclear__mutmut['xǁKVStoreǁclear__mutmut_10'] = KVStore.xǁKVStoreǁclear__mutmut_10 # type: ignore # mutmut generated
mutants_xǁKVStoreǁclear__mutmut['xǁKVStoreǁclear__mutmut_11'] = KVStore.xǁKVStoreǁclear__mutmut_11 # type: ignore # mutmut generated
mutants_xǁKVStoreǁclear__mutmut['xǁKVStoreǁclear__mutmut_12'] = KVStore.xǁKVStoreǁclear__mutmut_12 # type: ignore # mutmut generated

mutants_xǁKVStoreǁcleanup__mutmut['_mutmut_orig'] = KVStore.xǁKVStoreǁcleanup__mutmut_orig # type: ignore # mutmut generated
mutants_xǁKVStoreǁcleanup__mutmut['xǁKVStoreǁcleanup__mutmut_1'] = KVStore.xǁKVStoreǁcleanup__mutmut_1 # type: ignore # mutmut generated
mutants_xǁKVStoreǁcleanup__mutmut['xǁKVStoreǁcleanup__mutmut_2'] = KVStore.xǁKVStoreǁcleanup__mutmut_2 # type: ignore # mutmut generated
mutants_xǁKVStoreǁcleanup__mutmut['xǁKVStoreǁcleanup__mutmut_3'] = KVStore.xǁKVStoreǁcleanup__mutmut_3 # type: ignore # mutmut generated
mutants_xǁKVStoreǁcleanup__mutmut['xǁKVStoreǁcleanup__mutmut_4'] = KVStore.xǁKVStoreǁcleanup__mutmut_4 # type: ignore # mutmut generated
mutants_x_get_kv_store__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_get_kv_store__mutmut)
def get_kv_store() -> KVStore:
    with KVStore._lock:
        if KVStore._instance is None:
            KVStore._instance = KVStore()
        return KVStore._instance


def x_get_kv_store__mutmut_orig() -> KVStore:
    with KVStore._lock:
        if KVStore._instance is None:
            KVStore._instance = KVStore()
        return KVStore._instance


def x_get_kv_store__mutmut_1() -> KVStore:
    with KVStore._lock:
        if KVStore._instance is not None:
            KVStore._instance = KVStore()
        return KVStore._instance


def x_get_kv_store__mutmut_2() -> KVStore:
    with KVStore._lock:
        if KVStore._instance is None:
            KVStore._instance = None
        return KVStore._instance

mutants_x_get_kv_store__mutmut['_mutmut_orig'] = x_get_kv_store__mutmut_orig # type: ignore # mutmut generated
mutants_x_get_kv_store__mutmut['x_get_kv_store__mutmut_1'] = x_get_kv_store__mutmut_1 # type: ignore # mutmut generated
mutants_x_get_kv_store__mutmut['x_get_kv_store__mutmut_2'] = x_get_kv_store__mutmut_2 # type: ignore # mutmut generated
