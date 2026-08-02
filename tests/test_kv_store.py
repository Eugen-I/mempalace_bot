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
