"""Unit tests for services/interpreter.py."""

import json
import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from services import interpreter


@pytest.fixture(autouse=True)
def _fresh_state(tmp_path, monkeypatch):
    monkeypatch.setattr(
        interpreter, "PAIRS_FILE", str(tmp_path / "interpretation.json"),
    )
    interpreter._pairs.clear()
    interpreter._loaded = False
    yield
    interpreter._pairs.clear()
    interpreter._loaded = False


# ---------- register / load / save ----------


def test_register_and_load_roundtrip():
    assert interpreter.register("philosophy", "философия") is True
    assert interpreter.load_pairs() == {"philosophy": "философия"}
    with open(interpreter.PAIRS_FILE, "r", encoding="utf-8") as f:
        assert json.load(f) == {"philosophy": "философия"}


def test_register_keeps_first_value():
    assert interpreter.register("philosophy", "философия") is True
    assert interpreter.register("philosophy", "другое") is False
    assert interpreter.load_pairs() == {"philosophy": "философия"}


def test_register_normalizes_names():
    assert interpreter.register(" Philosophy ", " Философия ") is True
    assert interpreter.load_pairs() == {"philosophy": "философия"}


@pytest.mark.parametrize(
    "en, ru",
    [("", "философия"), ("philosophy", ""), ("philosophy", "philosophy")],
)
def test_register_rejects_bad_pairs(en, ru):
    assert interpreter.register(en, ru) is False
    assert interpreter.load_pairs() == {}


def test_register_many_count_and_idempotence():
    pairs = [("a", "а"), ("b", "б"), ("a", "повтор"), ("", "пусто"), ("c", "c")]
    assert interpreter.register_many(pairs) == 2
    assert interpreter.register_many([("a", "а")]) == 0
    assert interpreter.load_pairs() == {"a": "а", "b": "б"}


def test_save_pairs_atomic_replaces_file():
    interpreter.register("a", "а")
    first = interpreter.PAIRS_FILE + ".tmp"
    assert not os.path.exists(first)
    assert os.path.exists(interpreter.PAIRS_FILE)
    interpreter.register("b", "б")
    assert not os.path.exists(first)


# ---------- load from file ----------


def test_load_pairs_missing_file():
    assert interpreter.load_pairs() == {}


def test_load_pairs_corrupt_file():
    with open(interpreter.PAIRS_FILE, "w", encoding="utf-8") as f:
        f.write("{ это не json")
    assert interpreter.load_pairs() == {}


def test_load_pairs_invalid_entries_skipped():
    with open(interpreter.PAIRS_FILE, "w", encoding="utf-8") as f:
        json.dump({"a": 1, "b": "", "c": "ц", "": "пусто"}, f)
    assert interpreter.load_pairs() == {"c": "ц"}


def test_load_pairs_caches_until_reload():
    with open(interpreter.PAIRS_FILE, "w", encoding="utf-8") as f:
        json.dump({"a": "а"}, f)
    assert interpreter.load_pairs() == {"a": "а"}
    with open(interpreter.PAIRS_FILE, "w", encoding="utf-8") as f:
        json.dump({"b": "б"}, f)
    assert interpreter.load_pairs() == {"a": "а"}


# ---------- to_en / to_ru / display_name ----------


def test_to_en_and_to_ru():
    interpreter.register("philosophy", "философия")
    assert interpreter.to_ru("philosophy") == "философия"
    assert interpreter.to_ru("PHILOSOPHY") == "философия"
    assert interpreter.to_en("Философия") == "philosophy"
    assert interpreter.to_en("философия") == "philosophy"


def test_to_en_and_to_ru_unknown():
    assert interpreter.to_ru("unknown") is None
    assert interpreter.to_en("неизвестно") is None


def test_to_en_and_to_ru_empty():
    assert interpreter.to_ru("") is None
    assert interpreter.to_ru("   ") is None
    assert interpreter.to_en(None) is None


def test_display_name_en():
    interpreter.register("philosophy", "философия")
    assert interpreter.display_name("philosophy") == "philosophy (философия)"


def test_display_name_ru():
    interpreter.register("philosophy", "философия")
    assert interpreter.display_name("Философия") == "philosophy (Философия)"


def test_display_name_unknown_unchanged():
    assert interpreter.display_name("что_то_новое") == "что_то_новое"


# ---------- concurrency ----------


def test_concurrent_registers_are_all_saved():
    def worker(i):
        return interpreter.register(f"key{i}", f"значение{i}")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(worker, range(20)))
    assert results == [True] * 20
    pairs = interpreter.load_pairs()
    assert len(pairs) == 20
    for i in range(20):
        assert pairs[f"key{i}"] == f"значение{i}"
    with open(interpreter.PAIRS_FILE, "r", encoding="utf-8") as f:
        assert len(json.load(f)) == 20


# ---------- seed_known_pairs ----------


def test_seed_known_pairs(monkeypatch):
    from handlers.palace import shared as sh

    monkeypatch.setattr(
        sh, "KG_PREDICATES", [("wrote", "✍️ написал"), ("topic", "📌 тема")],
    )
    monkeypatch.setattr(
        sh, "_LOCALE_ALIASES",
        {
            "философия": "philosophy",
            "мои заметки": "my_notes",
            "сны и отрывки": "сны_и_отрывки_снов",
        },
    )
    added = interpreter.seed_known_pairs()
    assert added == 6  # 2 KG + 2 латинских алиаса + 4 DB, минус дубли (тема, написал)
    assert interpreter.to_ru("wrote") == "написал"
    assert interpreter.to_en("философия") == "philosophy"
    assert interpreter.to_en("мои заметки") == "my_notes"
    assert interpreter.to_en("сны и отрывки") is None  # значение не латиница
    assert interpreter.to_en("содержит_идею") == "contains_idea"
    assert interpreter.seed_known_pairs() == 0
