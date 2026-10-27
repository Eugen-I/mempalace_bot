"""Unit tests for services.agent_context — lifecycle button-сессии."""

import pytest

from services import agent_context as ac
from services.kv_store import KVStore


@pytest.fixture
def store(monkeypatch, tmp_path):
    kv = KVStore(db_path=str(tmp_path / "agent_context.sqlite"))
    monkeypatch.setattr(ac, "get_kv_store", lambda: kv)
    yield ac.AgentContextStore()
    kv.close()


def test_empty_button_session_is_active(store):
    session_id = store.create_button_session("answer-1")
    store.bind_button_session_to_uid(4242, session_id)

    assert store.get_button_context(session_id) == []
    assert store.has_active_button_session(4242) == session_id


def test_unbound_uid_has_no_active_session(store):
    assert store.has_active_button_session(4242) is None


def test_ended_session_is_inactive(store):
    session_id = store.create_button_session("answer-1")
    store.bind_button_session_to_uid(4242, session_id)

    store.end_button_session(session_id)

    assert store.has_active_button_session(4242) is None


def test_none_session_value_is_inactive(store):
    session_id = store.create_button_session("answer-1")
    store.bind_button_session_to_uid(4242, session_id)
    store._kv.set(
        store._session_key(session_id),
        None,
        namespace=ac.AGENT_CTX_NAMESPACE,
    )

    assert store.has_active_button_session(4242) is None


def test_followup_before_first_assistant_reply(store):
    session_id = store.create_button_session("answer-1")
    store.bind_button_session_to_uid(4242, session_id)

    store.append_button_context(session_id, "user", "продолжай")

    assert store.has_active_button_session(4242) == session_id
    assert store.get_button_context(session_id) == [
        {"role": "user", "content": "продолжай"},
    ]
