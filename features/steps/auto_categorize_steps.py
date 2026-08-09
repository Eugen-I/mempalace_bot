"""Шаги BDD для features/auto_categorize.feature.

Реализуют сценарии через реальный код services.auto_categorize с
фейковыми kv_store и источником индекса заметок (без живого MCP).
"""
import asyncio
import os
import tempfile

from behave import given, then, when

import services.auto_categorize as ac
from services.kv_store import KVStore


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class FakeKG:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    async def call_tool(self, note, topic):
        if self.fail:
            raise RuntimeError("kg down")
        self.calls.append((note["name"], topic))


def _setup(context):
    context.tmpdir = tempfile.mkdtemp(prefix="auto_categorize_bdd_")
    context.kv = KVStore(db_path=os.path.join(context.tmpdir, "categorize.sqlite"))
    context.kg = FakeKG()
    context.notes = []
    context.index_fail = False
    context.result = None


def _index_provider(context):
    def impl():
        if context.index_fail:
            raise RuntimeError("index down")
        return list(context.notes)

    return impl


# ─── Given ───

@given("хранилище KV пустое и без отметок")
def given_kv_empty(context):
    _setup(context)


@given('индекс Apple Notes содержит заметки "{first}" и "{second}"')
def given_notes_list(context, first, second):
    context.notes.append({"id": first, "name": first, "folder": "сны"})
    context.notes.append({"id": second, "name": second, "folder": "сны"})


@given('индекс Apple Notes содержит заметку "{name}"')
def given_notes_one(context, name):
    context.notes.append({"id": name, "name": name, "folder": "сны"})


@given("индекс Apple Notes содержит {n:d} заметки о снах")
def given_notes_n(context, n):
    for i in range(n):
        context.notes.append(
            {"id": f"n{i}", "name": f"Сон {i}", "folder": "сны"},
        )


@given('заметка "{name}" уже отмечена как обработанная')
def given_note_marked(context, name):
    context.kv.set(
        name, {"type": "dream", "topics": ["сон"]}, namespace=ac.CATEGORIZED_NS,
    )


@given("граф знаний недоступен")
def given_kg_down(context):
    context.kg.fail = True


@given("индекс Apple Notes недоступен")
def given_index_down(context):
    context.index_fail = True


# ─── When ───

@when("запускается авто-категоризация с лимитом {limit:d}")
def when_run_categorize(context, limit):
    context.result = _run(
        ac.auto_categorize_notes(
            limit=limit,
            kv=context.kv,
            mcp_cb=context.kg.call_tool,
            index_provider=_index_provider(context),
        ),
    )


# ─── Then ───

@then('в KG добавлены факты topic для заметки "{name}"')
def then_kg_facts_added(context, name):
    names = {note_name for note_name, _ in context.kg.calls}
    assert name in names, f"нет фактов для {name}, вызовы: {context.kg.calls}"


@then("в KG не добавлено ни одного факта")
def then_no_kg_facts(context):
    assert context.kg.calls == []


@then("обе заметки отмечены как обработанные")
def then_both_marked(context):
    for note in context.notes:
        assert context.kv.get(
            note["id"], namespace=ac.CATEGORIZED_NS,
        ) is not None, f"{note['id']} не отмечена"


@then('заметка "{name}" не отмечена как обработанная')
def then_note_not_marked(context, name):
    assert context.kv.get(name, namespace=ac.CATEGORIZED_NS) is None


@then("третья заметка не отмечена как обработанная")
def then_third_not_marked(context):
    assert context.kv.get("n2", namespace=ac.CATEGORIZED_NS) is None


@then("статистика: {processed:d} обработано, {skipped:d} пропущено, {failed:d} ошибок")
@then("статистика: {processed:d} обработано, {skipped:d} пропущено, {failed:d} ошибка")
def then_stats(context, processed, skipped, failed):
    stats = context.result
    assert stats["processed"] == processed, stats
    assert stats["skipped"] == skipped, stats
    assert stats["failed"] == failed, stats


@then("в результат добавлено сообщение об ошибке индекса")
def then_index_error_in_result(context):
    assert "error" in context.result
    assert context.result["error"] == "index down"
