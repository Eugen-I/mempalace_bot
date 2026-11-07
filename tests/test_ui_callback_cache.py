"""tests/test_ui_callback_cache.py
Тесты персистентного кэша UI-маппингов Telegram.
"""

import time
import pytest

from services.ui_cache import UICallbackCache


def test_ui_callback_cache_basic_crud(tmp_path):
    db_file = str(tmp_path / "test_ui.sqlite")
    cache = UICallbackCache(namespace="test_crud", db_path=db_file)

    cache["token123"] = "wing_alpha"
    assert "token123" in cache
    assert cache.get("token123") == "wing_alpha"
    assert cache["token123"] == "wing_alpha"

    # Test tuple preservation
    cache["room_tok"] = ("wing_1", "room_a")
    retrieved = cache.get("room_tok")
    assert isinstance(retrieved, tuple)
    assert retrieved == ("wing_1", "room_a")

    # Test deletion
    del cache["token123"]
    assert "token123" not in cache
    assert cache.get("token123") is None

    # Test pop
    popped = cache.pop("room_tok")
    assert popped == ("wing_1", "room_a")
    assert cache.get("room_tok") is None


def test_ui_callback_cache_ttl_expiration(tmp_path):
    db_file = str(tmp_path / "test_ui_ttl.sqlite")
    cache = UICallbackCache(namespace="test_ttl", db_path=db_file, default_ttl=0.1)

    cache["short_lived"] = "data"
    assert cache.get("short_lived") == "data"

    time.sleep(0.15)
    assert cache.get("short_lived") is None
    assert "short_lived" not in cache


def test_ui_callback_cache_namespace_isolation(tmp_path):
    db_file = str(tmp_path / "test_ui_ns.sqlite")
    cache_rooms = UICallbackCache(namespace="palace_rooms", db_path=db_file)
    cache_wings = UICallbackCache(namespace="palace_wings", db_path=db_file)

    cache_rooms["same_token"] = ("w", "r")
    cache_wings["same_token"] = "w"

    assert cache_rooms.get("same_token") == ("w", "r")
    assert cache_wings.get("same_token") == "w"


def test_ui_callback_cache_persists_across_instances(tmp_path):
    """Simulate bot restart: close instance and create new instance on same file."""
    db_file = str(tmp_path / "test_ui_restart.sqlite")

    # Instance before restart
    cache1 = UICallbackCache(namespace="palace_rooms", db_path=db_file)
    cache1["tok_abc"] = ("wing_science", "room_physics")
    del cache1

    # Instance after restart
    cache2 = UICallbackCache(namespace="palace_rooms", db_path=db_file)
    assert "tok_abc" in cache2
    val = cache2.get("tok_abc")
    assert val == ("wing_science", "room_physics")
    assert isinstance(val, tuple)
