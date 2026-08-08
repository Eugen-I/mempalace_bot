"""Unit tests for services.ai_cache (per-chat LRU response cache)."""

import services.ai_cache as ai_cache


def test_cache_and_get_roundtrip():
    ai_cache._ai_msg_cache.clear()
    ai_cache.cache_ai_response(1, 10, "ответ")
    assert ai_cache.get_ai_response(1, 10) == "ответ"


def test_get_missing_chat():
    ai_cache._ai_msg_cache.clear()
    assert ai_cache.get_ai_response(999, 1) == ""


def test_get_missing_message_in_existing_chat():
    ai_cache._ai_msg_cache.clear()
    ai_cache.cache_ai_response(1, 10, "ответ")
    assert ai_cache.get_ai_response(1, 11) == ""


def test_multiple_messages_same_chat():
    ai_cache._ai_msg_cache.clear()
    ai_cache.cache_ai_response(1, 1, "a")
    ai_cache.cache_ai_response(1, 2, "b")
    assert ai_cache.get_ai_response(1, 1) == "a"
    assert ai_cache.get_ai_response(1, 2) == "b"


def test_chats_are_isolated():
    ai_cache._ai_msg_cache.clear()
    ai_cache.cache_ai_response(1, 1, "a")
    ai_cache.cache_ai_response(2, 1, "b")
    assert ai_cache.get_ai_response(1, 1) == "a"
    assert ai_cache.get_ai_response(2, 1) == "b"


def test_evicts_oldest_above_50():
    ai_cache._ai_msg_cache.clear()
    for i in range(60):
        ai_cache.cache_ai_response(1, i, f"msg{i}")
    # старейший (id 0..9) вытеснен
    assert ai_cache.get_ai_response(1, 0) == ""
    assert ai_cache.get_ai_response(1, 50) == "msg50"
    assert ai_cache.get_ai_response(1, 59) == "msg59"
    assert len(ai_cache._ai_msg_cache[1]) == 50


def test_eviction_keeps_newest_ids():
    ai_cache._ai_msg_cache.clear()
    for i in range(50):
        ai_cache.cache_ai_response(1, i, f"m{i}")
    ai_cache.cache_ai_response(1, 100, "new")
    assert ai_cache.get_ai_response(1, 0) == ""
    assert ai_cache.get_ai_response(1, 100) == "new"
    assert ai_cache.get_ai_response(1, 1) == "m1"
