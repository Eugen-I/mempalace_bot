import os
import sqlite3
import tempfile
import time

import pytest

from services.kv_store import KVStore


@pytest.fixture
def kv():
    db = tempfile.mktemp(suffix=".sqlite")
    store = KVStore(db_path=db)
    yield store
    store.close()
    for suffix in ("", "-wal", "-shm"):
        path = db + suffix
        if os.path.exists(path):
            os.unlink(path)


class TestKVStore:
    def test_set_and_get(self, kv):
        kv.set("key1", "value1")
        assert kv.get("key1") == "value1"

    def test_get_missing_returns_default(self, kv):
        assert kv.get("nonexistent", default="fallback") == "fallback"

    def test_get_missing_no_default(self, kv):
        assert kv.get("nonexistent") is None

    def test_delete(self, kv):
        kv.set("key1", "value1")
        kv.delete("key1")
        assert kv.get("key1") is None

    def test_pop(self, kv):
        kv.set("key1", "value1")
        result = kv.pop("key1")
        assert result == "value1"
        assert kv.get("key1") is None

    def test_pop_nonexistent(self, kv):
        result = kv.pop("nope", default="missing")
        assert result == "missing"

    def test_namespace_isolation(self, kv):
        kv.set("key1", "ns1_value", namespace="ns1")
        kv.set("key1", "ns2_value", namespace="ns2")
        assert kv.get("key1", namespace="ns1") == "ns1_value"
        assert kv.get("key1", namespace="ns2") == "ns2_value"

    def test_ttl_eviction(self, kv):
        kv.set("ephemeral", "data", ttl=0)
        time.sleep(0.01)
        assert kv.get("ephemeral") is None

    def test_expired_value_is_deleted_and_default_returned(self, kv):
        kv.set("expired", "data", ttl=0)
        time.sleep(0.01)
        assert kv.get("expired", default="fallback") == "fallback"
        assert kv.keys() == []

    def test_ttl_not_expired(self, kv):
        kv.set("persistent", "data", ttl=60)
        assert kv.get("persistent") == "data"

    def test_keys_by_namespace(self, kv):
        kv.set("a", "1", namespace="ns1")
        kv.set("b", "2", namespace="ns1")
        kv.set("c", "3", namespace="ns2")
        keys = kv.keys("ns1")
        assert sorted(keys) == ["a", "b"]

    def test_keys_default_namespace(self, kv):
        kv.set("a", "1", namespace="ns1")
        kv.set("plain", "2")
        assert kv.keys() == ["plain"]

    def test_evict_expired_removes_rows_on_keys(self, kv):
        kv.set("ephemeral", "data", ttl=0)
        time.sleep(0.01)
        assert kv.keys() == []

    def test_clear_all(self, kv):
        kv.set("a", "1")
        kv.set("b", "2")
        kv.clear()
        assert kv.get("a") is None
        assert kv.get("b") is None

    def test_clear_namespace(self, kv):
        kv.set("a", "1", namespace="ns1")
        kv.set("b", "2", namespace="ns2")
        kv.clear(namespace="ns1")
        assert kv.get("a", namespace="ns1") is None
        assert kv.get("b", namespace="ns2") == "2"

    def test_complex_value_serialization(self, kv):
        data = {"nested": [1, 2, 3], "flag": True}
        kv.set("complex", data)
        assert kv.get("complex") == data

    def test_unicode_value_round_trip(self, kv):
        data = {"text": "Привет 🌍", "emoji": "🙂"}
        kv.set("unicode", data)
        assert kv.get("unicode") == data

    def test_stats(self, kv):
        kv.set("a", "1")
        kv.set("b", "2")
        assert kv.stats["size"] == 2

    def test_close_closes_sqlite_connection(self, kv):
        conn = kv._get_conn()
        kv.close()
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_cleanup(self, kv):
        kv.set("a", "1")
        kv.cleanup()
        assert kv.get("a") == "1"


class TestKVStoreMutants:
    def test_get_conn_reuses_connection(self, kv):
        conn1 = kv._get_conn()
        conn2 = kv._get_conn()
        assert conn1 is conn2

    def test_pop_with_namespace(self, kv):
        kv.set("key1", "value1", namespace="ns1")
        assert kv.pop("key1", namespace="ns2") is None
        assert kv.get("key1", namespace="ns1") == "value1"

    def test_expired_value_deleted_from_db(self, kv):
        kv.set("k", "v", ttl=0)
        time.sleep(0.01)
        assert kv.get("k") is None
        kv.set("k", "data2")
        assert kv.get("k") == "data2"

    def test_get_deletes_row_expiring_between_evict_and_check(self, monkeypatch, kv):
        con = kv._get_conn()
        con.execute(
            "INSERT OR REPLACE INTO kv_store (key, value, namespace, expires_at) "
            "VALUES (?, ?, ?, ?)",
            ("k", '"v"', "default", 100.5),
        )
        con.commit()
        import unittest.mock as mock

        monkeypatch.setattr(
            "services.kv_store.time.time",
            mock.Mock(side_effect=[100.0, 101.0]),
        )
        assert kv.get("k", default="fallback") == "fallback"

    def test_get_non_json_value_returns_raw(self, kv):
        con = kv._get_conn()
        con.execute(
            "INSERT OR REPLACE INTO kv_store (key, value, namespace) VALUES (?, ?, ?)",
            ("raw", "not-json", "default"),
        )
        con.commit()
        assert kv.get("raw") == "not-json"


class _FakeConn:
    def __init__(self):
        self.sqls = []
        self._row = None

    def execute(self, sql, params=()):
        self.sqls.append(sql)
        return self

    def fetchone(self):
        return self._row

    def fetchall(self):
        return []

    def commit(self):
        pass

    def close(self):
        pass


class TestKVStoreSQLLiterals:
    def _make(self, tmp_path, monkeypatch, fake_conn=None):
        import services.kv_store as kv_mod

        monkeypatch.setattr(
            "sqlite3.connect",
            lambda path, check_same_thread: fake_conn or _FakeConn(),
        )
        store = kv_mod.KVStore(db_path=str(tmp_path / "t.sqlite"))
        if fake_conn is None:
            fake_conn = store._get_conn()
        return store, fake_conn

    def test_init_runs_pragma_wal(self, tmp_path, monkeypatch):
        fake = _FakeConn()
        store, _ = self._make(tmp_path, monkeypatch, fake)
        try:
            assert fake.sqls.count("PRAGMA journal_mode=WAL") == 1
            assert fake.sqls.count("PRAGMA synchronous=NORMAL") == 1
        finally:
            store.close()

    def test_connect_uses_check_same_thread_false(self, tmp_path, monkeypatch):
        import services.kv_store as kv_mod

        captured = {}

        def fake_connect(path, check_same_thread):
            captured["check"] = check_same_thread
            return _FakeConn()

        monkeypatch.setattr("services.kv_store.sqlite3.connect", fake_connect)
        store = kv_mod.KVStore(db_path=str(tmp_path / "t.sqlite"))
        try:
            assert captured.get("check") is False
        finally:
            store.close()

    def test_reconnect_after_close_ok(self, tmp_path, monkeypatch):
        fake = _FakeConn()
        store, _ = self._make(tmp_path, monkeypatch, fake)
        store.close()
        store._get_conn()
        store.close()

    def test_close_without_conn_ok(self, kv):
        kv.close()
        del kv._local.conn
        kv.close()

    def test_set_exact_sql(self, tmp_path, monkeypatch):
        fake = _FakeConn()
        store, _ = self._make(tmp_path, monkeypatch, fake)
        try:
            store.set("k", 1)
            assert ("INSERT OR REPLACE INTO kv_store "
                    "(key, value, namespace, expires_at)") in fake.sqls[-1]
        finally:
            store.close()

    def test_get_exact_sql(self, tmp_path, monkeypatch):
        fake = _FakeConn()
        store, _ = self._make(tmp_path, monkeypatch, fake)
        try:
            store.get("k", namespace="ns")
            assert fake.sqls[-1] == ("SELECT value, expires_at FROM kv_store "
                                     "WHERE key = ? AND namespace = ?")
        finally:
            store.close()

    def test_delete_exact_sql(self, tmp_path, monkeypatch):
        fake = _FakeConn()
        store, _ = self._make(tmp_path, monkeypatch, fake)
        try:
            store.delete("k", namespace="ns")
            assert fake.sqls[-1] == "DELETE FROM kv_store WHERE key = ? AND namespace = ?"
        finally:
            store.close()

    def test_evict_expired_exact_sql(self, tmp_path, monkeypatch):
        fake = _FakeConn()
        store, _ = self._make(tmp_path, monkeypatch, fake)
        try:
            store.set("k", 1)
            assert ("DELETE FROM kv_store WHERE expires_at IS NOT NULL "
                    "AND expires_at < ?") in fake.sqls
        finally:
            store.close()

    def test_stats_exact_sql(self, tmp_path, monkeypatch):
        fake = _FakeConn()
        store, _ = self._make(tmp_path, monkeypatch, fake)
        try:
            store.stats
            assert fake.sqls[-1] == "SELECT COUNT(*) FROM kv_store"
        finally:
            store.close()

    def test_cleanup_exact_sql(self, tmp_path, monkeypatch):
        fake = _FakeConn()
        store, _ = self._make(tmp_path, monkeypatch, fake)
        try:
            store.cleanup()
            assert fake.sqls[-1] == "VACUUM"
        finally:
            store.close()

    def test_expired_row_triggers_delete_via_fetchone(self, tmp_path, monkeypatch):
        import json as json_mod

        fake = _FakeConn()
        fake._row = (json_mod.dumps("v"), 0.0)
        store, _ = self._make(tmp_path, monkeypatch, fake)
        try:
            assert store.get("k") is None
            assert fake.sqls[-1] == "DELETE FROM kv_store WHERE key = ? AND namespace = ?"
        finally:
            store.close()


class TestKVStoreBoundaryMutants:
    def test_get_exact_expiry_boundary_returns_value(self, monkeypatch):
        import services.kv_store as kv_mod

        fake_now = [1000.0]
        monkeypatch.setattr("services.kv_store.time.time", lambda: fake_now[0])
        store = kv_mod.KVStore(db_path=":memory:")
        try:
            store.set("k", "v", ttl=0)
            assert store.get("k", default="fallback") == "v"
        finally:
            store.close()

    def test_pop_from_one_namespace_leaves_others_intact(self, kv):
        kv.set("k", "default-value", namespace="default")
        kv.set("k", "docs-value", namespace="docs")
        assert kv.pop("k", namespace="docs") == "docs-value"
        assert kv.get("k", namespace="default") == "default-value"
        assert kv.get("k", namespace="docs") is None


class TestKVStoreSQLLiteralsExtra:
    def test_keys_exact_sql(self, tmp_path, monkeypatch):
        fake = _FakeConn()
        monkeypatch.setattr("sqlite3.connect", lambda path, check_same_thread: fake)
        store = KVStore(db_path=str(tmp_path / "t.sqlite"))
        try:
            store.keys("ns")
            assert fake.sqls[-1] == "SELECT key FROM kv_store WHERE namespace = ?"
        finally:
            store.close()

    def test_clear_exact_sql(self, tmp_path, monkeypatch):
        fake = _FakeConn()
        monkeypatch.setattr("sqlite3.connect", lambda path, check_same_thread: fake)
        store = KVStore(db_path=str(tmp_path / "t.sqlite"))
        try:
            store.clear("ns")
            assert fake.sqls[-1] == "DELETE FROM kv_store WHERE namespace = ?"
            store.clear()
            assert fake.sqls[-1] == "DELETE FROM kv_store"
        finally:
            store.close()

    def test_set_keeps_cyrillic_unescaped(self, kv):
        kv.set("key", "значение")
        con = kv._get_conn()
        raw = con.execute(
            "SELECT value FROM kv_store WHERE key = ?", ("key",),
        ).fetchone()[0]
        assert "значение" in raw
        assert "\\u" not in raw
