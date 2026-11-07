"""tests/test_db_pool.py
Тесты универсального менеджера и пула подключений SQLite.
"""

import concurrent.futures
import sqlite3
import threading

import pytest

from services.db_pool import (
    DEFAULT_BUSY_TIMEOUT_MS,
    SQLiteConnectionPool,
    apply_pragmas,
    db_connection,
    db_cursor,
    get_connection,
    get_db_pool,
)


def test_apply_pragmas(tmp_path):
    db_path = str(tmp_path / "test_pragmas.sqlite")
    conn = sqlite3.connect(db_path)
    apply_pragmas(conn, busy_timeout_ms=15000)

    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode")
    jmode = cur.fetchone()[0]
    assert jmode.lower() == "wal"

    cur.execute("PRAGMA synchronous")
    sync = cur.fetchone()[0]
    # NORMAL synchronous mode in SQLite corresponds to 1
    assert sync == 1

    cur.execute("PRAGMA foreign_keys")
    fk = cur.fetchone()[0]
    assert fk == 1

    cur.execute("PRAGMA busy_timeout")
    timeout = cur.fetchone()[0]
    assert timeout == 15000
    conn.close()


def test_get_connection_and_caching(tmp_path):
    db_path = str(tmp_path / "test_cache.sqlite")
    pool = SQLiteConnectionPool()

    conn1 = pool.get_connection(db_path)
    conn2 = pool.get_connection(db_path)
    assert conn1 is conn2

    # Thread-local isolation
    other_conn = None

    def worker():
        nonlocal other_conn
        other_conn = pool.get_connection(db_path)

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    assert other_conn is not None
    assert other_conn is not conn1
    pool.close_all()


def test_context_manager_commit(tmp_path):
    db_path = str(tmp_path / "test_cm.sqlite")

    with db_cursor(db_path) as cur:
        cur.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
        cur.execute("INSERT INTO items (name) VALUES ('apple')")

    with db_cursor(db_path) as cur:
        cur.execute("SELECT name FROM items WHERE id = 1")
        row = cur.fetchone()
        assert row[0] == "apple"


def test_context_manager_rollback_on_error(tmp_path):
    db_path = str(tmp_path / "test_rollback.sqlite")

    with db_cursor(db_path) as cur:
        cur.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")

    with pytest.raises(ValueError):
        with db_cursor(db_path) as cur:
            cur.execute("INSERT INTO items (name) VALUES ('banana')")
            raise ValueError("simulated failure")

    with db_cursor(db_path) as cur:
        cur.execute("SELECT COUNT(*) FROM items")
        count = cur.fetchone()[0]
        assert count == 0


def test_reopen_stale_connection(tmp_path):
    db_path = str(tmp_path / "test_stale.sqlite")
    pool = SQLiteConnectionPool()

    conn1 = pool.get_connection(db_path)
    conn1.close()  # artificially closed

    # Should detect dead connection and create a new live one
    conn2 = pool.get_connection(db_path)
    assert conn2 is not conn1
    cur = conn2.execute("SELECT 1")
    assert cur.fetchone()[0] == 1
    pool.close_all()


def test_concurrent_multithreaded_writes(tmp_path):
    db_path = str(tmp_path / "test_concurrent.sqlite")
    pool = get_db_pool()

    with db_cursor(db_path) as cur:
        cur.execute("CREATE TABLE counter (id INTEGER PRIMARY KEY, val INTEGER)")
        cur.execute("INSERT INTO counter (id, val) VALUES (1, 0)")

    def increment(n_times: int):
        for _ in range(n_times):
            with db_cursor(db_path) as cur:
                cur.execute("UPDATE counter SET val = val + 1 WHERE id = 1")

    workers = 8
    increments_per_worker = 20

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(increment, increments_per_worker) for _ in range(workers)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    with db_cursor(db_path) as cur:
        cur.execute("SELECT val FROM counter WHERE id = 1")
        final_val = cur.fetchone()[0]
        assert final_val == workers * increments_per_worker
