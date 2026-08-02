"""Smoke-тесты для функций-синглтонов и обёрток без прямых тестов.

Покрывает мутантов «no tests» в services-модулях.
"""
import asyncio

import pytest

from tests.test_action_bar import TEST_UID


class TestSingletonFunctions:
    def test_get_kv_store_singleton(self):
        from services.kv_store import get_kv_store

        store1 = get_kv_store()
        store2 = get_kv_store()
        assert store1 is store2

    def test_get_bus_singleton(self):
        from services.event_bus import get_bus

        bus1 = get_bus()
        bus2 = get_bus()
        assert bus1 is bus2

    def test_get_bus_reset(self):
        from services.event_bus import get_bus, reset_bus

        bus1 = get_bus()
        reset_bus()
        bus2 = get_bus()
        assert bus1 is not bus2
        reset_bus()

    def test_get_cache_singleton(self):
        from services.semantic_cache import get_cache

        cache1 = get_cache()
        cache2 = get_cache()
        assert cache1 is cache2

    def test_get_cache_reset(self):
        from services.semantic_cache import get_cache, reset_cache

        cache1 = get_cache()
        reset_cache()
        cache2 = get_cache()
        assert cache1 is not cache2
        reset_cache()

    def test_get_degradation_manager_singleton(self, monkeypatch):
        import services.graceful_degradation as gd_mod
        from services.graceful_degradation import get_degradation_manager

        monkeypatch.setattr(gd_mod, "_mgr", None)
        mgr1 = get_degradation_manager()
        mgr2 = get_degradation_manager()
        assert mgr1 is not None
        assert mgr1 is mgr2

    def test_report_failure_and_success(self):
        from services.graceful_degradation import (
            DegradationLevel,
            get_degradation_manager,
            report_failure,
            report_success,
        )

        mgr = get_degradation_manager()
        mgr.record_success("palace_mcp")
        mgr.record_success("palace_search")
        mgr.record_success("memory")
        report_failure("memory")
        assert mgr.level == DegradationLevel.MEDIUM
        report_success("memory")
        assert mgr.level == DegradationLevel.FULL

    def test_get_mcp_circuit_breaker(self, monkeypatch):
        import services.circuit_breaker as cb_mod
        from services.circuit_breaker import get_mcp_circuit_breaker

        monkeypatch.setattr(cb_mod, "_mcp_cb", None)
        cb1 = get_mcp_circuit_breaker()
        cb2 = get_mcp_circuit_breaker()
        assert cb1 is cb2
        assert cb1.name == "MCP"
        assert cb1.failure_threshold == 3
        assert cb1.recovery_timeout == 30.0
        cb1.reset()

    def test_get_palace_circuit_breaker(self, monkeypatch):
        import services.circuit_breaker as cb_mod
        from services.circuit_breaker import get_palace_circuit_breaker

        monkeypatch.setattr(cb_mod, "_palace_cb", None)
        cb1 = get_palace_circuit_breaker()
        cb2 = get_palace_circuit_breaker()
        assert cb1 is cb2
        assert cb1.name == "Palace"
        assert cb1.failure_threshold == 2
        assert cb1.recovery_timeout == 60.0
        cb1.reset()

    def test_get_kv_store_creates_instance(self, monkeypatch, tmp_path):
        import services.kv_store as kv_mod
        from services.kv_store import KVStore, get_kv_store

        monkeypatch.setattr(KVStore, "_instance", None)
        monkeypatch.setattr(kv_mod, "_DB_PATH", str(tmp_path / "kv.sqlite3"))
        store = get_kv_store()
        assert store is not None
        monkeypatch.setattr(KVStore, "_instance", None)

    def test_palace_back_cb_dispatches(self, monkeypatch):
        import handlers.palace.action_bar as ab
        import handlers.palace as palace_mod
        from tests.test_action_bar import FakeCallback

        received = []

        async def spy(cb):
            received.append(cb)

        monkeypatch.setattr(palace_mod, "cb_palace_back", spy)
        cb = FakeCallback("ab_back:whatever")
        asyncio.run(ab._palace_back_cb(cb))
        assert received == [cb]


class TestPalaceBackCallback:
    def test_cb_ab_back_no_parent_alert(self, monkeypatch):
        import config
        from handlers.palace.action_bar import Answer, answer_store, cb_ab_back
        from tests.test_action_bar import FakeCallback

        monkeypatch.setattr(config, "ALLOWED_IDS", {TEST_UID})
        sid = "b1c2d3e4"
        answer_store[sid] = Answer(sid=sid, text="т", pages=["т"], ctx={})
        cb = FakeCallback(f"ab_back:{sid}")
        asyncio.run(cb_ab_back(cb))
        assert cb.answered is not None
        assert cb.answered[0] == "Нет родительского экрана."

    def test_cb_ab_back_expired_session(self, monkeypatch):
        import config
        from handlers.palace.action_bar import cb_ab_back
        from tests.test_action_bar import FakeCallback

        monkeypatch.setattr(config, "ALLOWED_IDS", {TEST_UID})
        cb = FakeCallback("ab_back:unknown")
        asyncio.run(cb_ab_back(cb))
        assert cb.answered is not None
        assert cb.answered[0] == "Сессия истекла. Откройте заново."


@pytest.fixture(autouse=True)
def _clean_singletons():
    yield
    from services.circuit_breaker import (
        get_mcp_circuit_breaker,
        get_palace_circuit_breaker,
    )
    from services.event_bus import reset_bus
    from services.graceful_degradation import (
        get_degradation_manager,
        report_failure,
        report_success,
    )
    from services.semantic_cache import reset_cache

    get_mcp_circuit_breaker().reset()
    get_palace_circuit_breaker().reset()
    reset_bus()
    reset_cache()
    mgr = get_degradation_manager()
    for comp in ("palace_mcp", "palace_search", "memory"):
        report_success(comp)
