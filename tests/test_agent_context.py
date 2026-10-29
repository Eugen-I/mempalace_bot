"""Unit tests for services.agent_context — lifecycle and history."""

import json

import pytest

from services import agent_context as ac
from services import chat_store
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


def _chat_file(tmp_path, monkeypatch, messages):
    monkeypatch.setattr(ac, "CHATS_DIR", str(tmp_path))
    monkeypatch.setitem(ac.user_sessions, 4242, "chat.json")
    path = tmp_path / "chat.json"
    path.write_text(
        json.dumps({"summary": "", "messages": messages}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def test_append_always_on_persists_and_reloads(store, tmp_path, monkeypatch):
    path = _chat_file(
        tmp_path, monkeypatch,
        [{"role": "user", "content": "старый вопрос"}],
    )

    store.append_always_on(4242, "assistant", "ответ агента")

    assert store.get_always_on_context(4242) == [
        {"role": "user", "content": "старый вопрос"},
        {"role": "assistant", "content": "ответ агента"},
    ]
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["messages"][-1] == {"role": "assistant", "content": "ответ агента"}
    assert ac.AgentContextStore().get_always_on_context(4242) == [
        {"role": "user", "content": "старый вопрос"},
        {"role": "assistant", "content": "ответ агента"},
    ]


def test_append_always_on_does_not_duplicate_retry(store, tmp_path, monkeypatch):
    _chat_file(tmp_path, monkeypatch, [])

    store.append_always_on(4242, "assistant", "ответ агента")
    store.append_always_on(4242, "assistant", "ответ агента")

    assert store.get_always_on_context(4242) == [
        {"role": "assistant", "content": "ответ агента"},
    ]


def test_append_always_on_without_chat_session_is_noop(store):
    store.append_always_on(4242, "assistant", "ответ агента")

    assert store.get_always_on_context(4242) == []


def test_always_on_context_uses_shared_store(store, tmp_path, monkeypatch):
    path = _chat_file(tmp_path, monkeypatch, [{"role": "user", "content": "вопрос"}])
    calls = []
    original = chat_store.load_chat

    def spy(filepath):
        calls.append(filepath)
        return original(filepath)

    monkeypatch.setattr(chat_store, "load_chat", spy)

    assert store.get_always_on_context(4242) == [
        {"role": "user", "content": "вопрос"},
    ]
    assert calls == [str(path)]


def test_append_always_on_uses_shared_store(store, tmp_path, monkeypatch):
    path = _chat_file(tmp_path, monkeypatch, [])
    calls = []

    def fake_append(filepath, role, content, **kwargs):
        calls.append((filepath, role, content, kwargs))
        return True

    monkeypatch.setattr(chat_store, "append_message", fake_append)

    store.append_always_on(4242, "assistant", "ответ")

    assert calls == [
        (str(path), "assistant", "ответ",
         {"max_messages": 50, "dedupe": True}),
    ]


def test_always_on_context_skips_malformed_messages(store, tmp_path, monkeypatch):
    _chat_file(
        tmp_path, monkeypatch,
        [
            {"role": "user", "content": "ok"},
            {"role": "assistant"},
            "not a dict",
        ],
    )

    assert store.get_always_on_context(4242) == [
        {"role": "user", "content": "ok"},
    ]
