"""Unit tests for services.conversation_fsm (per-user FSM with TTL)."""

import time

import pytest

from services.conversation_fsm import ConversationFSM, ConversationState


class _FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    c = _FakeClock()
    monkeypatch.setattr("services.conversation_fsm.time.monotonic", c)
    return c


def test_initial_state_idle():
    fsm = ConversationFSM()
    assert fsm.get_state(42) == ConversationState.IDLE


def test_initial_data_empty():
    fsm = ConversationFSM()
    assert fsm.get_data(42) == {}


def test_set_and_get_state():
    fsm = ConversationFSM()
    fsm.set_state(1, ConversationState.MCP_INPUT, {"step": 1})
    assert fsm.get_state(1) == ConversationState.MCP_INPUT
    assert fsm.get_data(1) == {"step": 1}


def test_state_expires(clock):
    fsm = ConversationFSM(ttl=10)
    fsm.set_state(1, ConversationState.SEARCH_WING)
    clock.now += 20
    assert fsm.get_state(1) == ConversationState.IDLE


def test_get_refreshes_ttl(clock):
    fsm = ConversationFSM(ttl=10)
    fsm.set_state(1, ConversationState.QUOTE_WAITING)
    clock.now += 8
    assert fsm.get_state(1) == ConversationState.QUOTE_WAITING
    clock.now += 8  # ещё 8 сек после refresh → не истёк
    assert fsm.get_state(1) == ConversationState.QUOTE_WAITING


def test_update_data_existing(clock):
    fsm = ConversationFSM()
    fsm.set_state(1, ConversationState.PERSONAL_NOTE, {"a": 1})
    fsm.update_data(1, b=2)
    data = fsm.get_data(1)
    assert data == {"a": 1, "b": 2}
    assert fsm.get_state(1) == ConversationState.PERSONAL_NOTE


def test_update_data_new_user(clock):
    fsm = ConversationFSM()
    fsm.update_data(9, key="val")
    assert fsm.get_data(9) == {"key": "val"}
    assert fsm.get_state(9) == ConversationState.IDLE


def test_update_data_expired_creates_new(clock):
    fsm = ConversationFSM(ttl=10)
    fsm.set_state(1, ConversationState.MCP_INPUT)
    clock.now += 50
    fsm.update_data(1, fresh=1)
    assert fsm.get_data(1) == {"fresh": 1}


def test_pop_data_existing(clock):
    fsm = ConversationFSM()
    fsm.set_state(1, ConversationState.MCP_INPUT, {"q": "запрос"})
    assert fsm.pop_data(1, "q") == "запрос"
    assert "q" not in fsm.get_data(1)


def test_pop_data_missing_default(clock):
    fsm = ConversationFSM()
    assert fsm.pop_data(1, "none", "def") == "def"


def test_pop_data_no_user(clock):
    fsm = ConversationFSM()
    assert fsm.pop_data(999, "x") is None


def test_pop_data_expired(clock):
    fsm = ConversationFSM(ttl=10)
    fsm.set_state(1, ConversationState.IDLE, {"x": 1})
    clock.now += 20
    assert fsm.pop_data(1, "x", "def") == "def"


def test_clear(clock):
    fsm = ConversationFSM()
    fsm.set_state(1, ConversationState.MCP_INPUT)
    assert 1 in fsm
    fsm.clear(1)
    assert 1 not in fsm
    fsm.clear(1)  # повтор — не падает


def test_contains_handles_expiry(clock):
    fsm = ConversationFSM(ttl=10)
    fsm.set_state(1, ConversationState.IDLE)
    clock.now += 20
    assert 1 not in fsm


def test_contains_handles_ttl_refresh(clock):
    fsm = ConversationFSM(ttl=10)
    fsm.set_state(1, ConversationState.IDLE)
    clock.now += 8
    assert 1 in fsm


def test_setdefault_existing(clock):
    fsm = ConversationFSM()
    fsm.setdefault(1, "a", "val")
    assert fsm.setdefault(1, "a", "other") == "val"


def test_setdefault_new_user(clock):
    fsm = ConversationFSM()
    assert fsm.setdefault(8, "w", "v") == "v"
    assert fsm.get_data(8) == {"w": "v"}


def test_setdefault_expired(clock):
    fsm = ConversationFSM(ttl=10)
    fsm.set_state(1, ConversationState.IDLE, {"old": 1})
    clock.now += 20
    assert fsm.setdefault(1, "new", "x") == "x"
    assert fsm.get_data(1) == {"new": "x"}


def test_active_count(clock):
    fsm = ConversationFSM(ttl=10)
    fsm.set_state(1, ConversationState.IDLE)
    fsm.set_state(2, ConversationState.MCP_INPUT)
    clock.now += 5
    assert fsm.active_count == 2
    clock.now += 10
    assert fsm.active_count == 0


def test_default_ttl(clock):
    fsm = ConversationFSM()
    assert fsm._ttl == 86400

def test_get_refreshes_missing_uid_noop(clock):
    from services.conversation_fsm import ConversationFSM, ConversationState

    fsm = ConversationFSM(ttl=10)
    fsm._refresh(999)
    assert fsm.get_state(999) == ConversationState.IDLE
