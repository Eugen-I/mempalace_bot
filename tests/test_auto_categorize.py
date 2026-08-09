"""Тесты services/auto_categorize.py — авто-категоризация Apple Notes → KG.

Покрытие: классификация (happy/границы), пайплайн с kv-отметками,
лимиты, толерантность к ошибкам источника/KG/kv.
"""
import pytest

import services.auto_categorize as ac
from services.kv_store import KVStore


@pytest.fixture
def kv(monkeypatch, tmp_path):
    store = KVStore(db_path=str(tmp_path / "categorize.sqlite"))
    monkeypatch.setattr(ac, "get_kv_store", lambda: store)
    return store


def _note(nid, name="Книга Фауст — Гёте", folder="книги"):
    return {"id": nid, "name": name, "folder": folder}


class FakeMCP:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    async def call_tool(self, note, topic):
        if self.fail:
            raise RuntimeError("mcp down")
        self.calls.append({"name": note.get("name", ""), "topic": topic})


# ─── categorize_note ───

def test_categorize_note_book():
    cat = ac.categorize_note("Книга Фауст — Гёте", "мысли_из_книг")
    assert cat["type"] == "book_note"
    assert "книги" in cat["topics"] and "цитаты" in cat["topics"]


def test_categorize_note_dream():
    cat = ac.categorize_note("Сон про полёт", "сны")
    assert cat["type"] == "dream"
    assert "сон" in cat["topics"]


def test_categorize_note_poem():
    cat = ac.categorize_note("Стихи о море", "стихи")
    assert cat["type"] == "poem"
    assert "поэзия" in cat["topics"]


def test_categorize_note_default_personal():
    cat = ac.categorize_note("Список покупок", "прочее")
    assert cat["type"] == "personal_thought"
    assert cat["topics"] == []


def test_categorize_note_empty_name():
    cat = ac.categorize_note("", "")
    assert cat["type"] == "personal_thought"


def test_categorize_note_returns_fresh_lists():
    cat1 = ac.categorize_note("Сон про полёт", "сны")
    cat1["topics"].append("мусор")
    cat2 = ac.categorize_note("Сон про полёт", "сны")
    assert "мусор" not in cat2["topics"]


# ─── auto_categorize_notes ───

async def test_auto_categorize_happy(kv):
    mcp = FakeMCP()
    notes = [
        _note("n1", "Сон про полёт", "сны"),
        _note("n2", "Список покупок", "прочее"),
    ]
    stats = await ac.auto_categorize_notes(
        kv=kv, mcp_cb=mcp.call_tool, index_provider=lambda: notes,
    )
    assert stats["processed"] == 2
    assert stats["skipped"] == 0
    assert stats["failed"] == 0
    assert stats["added"] == len(mcp.calls) == 2
    assert {c["topic"] for c in mcp.calls} == {"сон", "психология"}
    assert kv.get("n1", namespace=ac.CATEGORIZED_NS)["type"] == "dream"
    assert kv.get("n2", namespace=ac.CATEGORIZED_NS)["type"] == "personal_thought"


async def test_auto_categorize_skips_already_done(kv):
    mcp = FakeMCP()
    kv.set("n1", {"type": "dream"}, namespace=ac.CATEGORIZED_NS)
    stats = await ac.auto_categorize_notes(
        kv=kv, mcp_cb=mcp.call_tool, index_provider=lambda: [_note("n1")],
    )
    assert stats["processed"] == 0
    assert stats["skipped"] == 1
    assert mcp.calls == []


async def test_auto_categorize_limit(kv):
    mcp = FakeMCP()
    notes = [_note(f"n{i}") for i in range(5)]
    stats = await ac.auto_categorize_notes(
        limit=2, kv=kv, mcp_cb=mcp.call_tool, index_provider=lambda: notes,
    )
    assert stats["processed"] == 2
    stats2 = await ac.auto_categorize_notes(
        limit=0, kv=kv, mcp_cb=mcp.call_tool, index_provider=lambda: notes,
    )
    assert stats2["processed"] == 0


async def test_auto_categorize_kg_failure_no_mark(kv, caplog):
    mcp = FakeMCP(fail=True)
    stats = await ac.auto_categorize_notes(
        kv=kv, mcp_cb=mcp.call_tool, index_provider=lambda: [_note("n1", "Сон X", "сны")],
    )
    assert stats["failed"] == 1
    assert stats["processed"] == 0
    assert kv.get("n1", namespace=ac.CATEGORIZED_NS) is None
    assert "kg add failed" in caplog.text


async def test_auto_categorize_retries_after_failure(kv):
    notes = [_note("n1", "Сон X", "сны")]
    first = await ac.auto_categorize_notes(
        kv=kv, mcp_cb=FakeMCP(fail=True).call_tool, index_provider=lambda: notes,
    )
    assert first["processed"] == 0
    assert first["failed"] == 1
    assert kv.get("n1", namespace=ac.CATEGORIZED_NS) is None
    mcp = FakeMCP()
    second = await ac.auto_categorize_notes(
        kv=kv, mcp_cb=mcp.call_tool, index_provider=lambda: notes,
    )
    assert second["processed"] == 1
    assert second["skipped"] == 0
    assert kv.get("n1", namespace=ac.CATEGORIZED_NS) is not None


async def test_auto_categorize_empty_index(kv):
    mcp = FakeMCP()
    stats = await ac.auto_categorize_notes(
        kv=kv, mcp_cb=mcp.call_tool, index_provider=lambda: [],
    )
    assert stats == {"processed": 0, "skipped": 0, "added": 0, "failed": 0}


async def test_auto_categorize_index_error(kv, caplog):
    def boom():
        raise RuntimeError("notes down")

    stats = await ac.auto_categorize_notes(
        kv=kv, mcp_cb=None, index_provider=boom,
    )
    assert stats["error"]
    assert "notes index failed" in caplog.text


async def test_auto_categorize_default_mcp(monkeypatch, kv):
    class FakeMCP2:
        def __init__(self):
            self.calls = []

        async def call_tool(self, name, args):
            self.calls.append((name, args))

    mcp = FakeMCP2()
    monkeypatch.setattr("services.palace_mcp.get_mcp", lambda: mcp)
    stats = await ac.auto_categorize_notes(
        kv=kv, index_provider=lambda: [_note("n1", "Сон X", "сны")],
    )
    assert stats["processed"] == 1
    assert mcp.calls[0][0] == "mempalace_kg_add"
    args = mcp.calls[0][1]
    assert args["predicate"] == "topic"
    assert args["source_closet"].startswith("apple_notes/")


async def test_auto_categorize_subject_truncated(kv):
    mcp = FakeMCP()
    long_name = "Книга " + "о" * 300
    stats = await ac.auto_categorize_notes(
        kv=kv, mcp_cb=mcp.call_tool,
        index_provider=lambda: [_note("n1", long_name, "книги")],
    )
    assert stats["processed"] == 1
    for c in mcp.calls:
        assert len(c["name"]) <= ac.MAX_SUBJECT_LEN


async def test_auto_categorize_kv_down_tolerant(monkeypatch, caplog):
    class BrokenKV:
        def get(self, *a, **k):
            raise RuntimeError("kv get boom")

        def set(self, *a, **k):
            raise RuntimeError("kv set boom")

    mcp = FakeMCP()
    stats = await ac.auto_categorize_notes(
        kv=BrokenKV(), mcp_cb=mcp.call_tool,
        index_provider=lambda: [_note("n1", "Сон X", "сны")],
    )
    assert stats["processed"] == 1
    assert mcp.calls != []
