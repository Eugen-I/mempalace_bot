"""Шаги BDD для features/memory_hybrid.feature.

Выполняются через реальный services.memory.retrieve_facts с фейковым
семантическим слоем (services.memory_embeddings.search_similar) и
временной папкой памяти.
"""
import json
import tempfile

from behave import given, then, when

import services.memory as mem
import services.memory_embeddings as me

TEST_UID = 424242


def _reset(context):
    context.mem_dir = tempfile.mkdtemp(prefix="mem_bdd_")
    mem._memory_dir = lambda: context.mem_dir
    me.search_similar = lambda query, user_id, limit=5: []
    context.results = None


def _write_facts(context, facts):
    path = f"{context.mem_dir}/mem_{TEST_UID}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump([{"fact": f} for f in facts], f, ensure_ascii=False)


def _install_search(context, items, fail=False):
    def _search(query, user_id, limit=5):
        if fail:
            raise RuntimeError("embed down")
        context.search_calls = (query, user_id, limit)
        return list(items)

    me.search_similar = _search


# ─── Given ───

@given('у пользователя {uid} в памяти есть факт "{fact}"')
def given_memory_fact(context, uid, fact):
    _reset(context)
    _write_facts(context, [fact])


@given('у пользователя {uid} в памяти есть факты "{facts}"')
def given_memory_facts(context, uid, facts):
    _reset(context)
    _write_facts(context, facts.split("|"))


@given('семантический слой возвращает факт "{fact}" со score {score}')
def given_semantic_returns_fact(context, fact, score):
    _install_search(context, [{"fact": fact, "_score": float(score)}])


@given('семантический слой возвращает факты "{facts}"')
def given_semantic_returns_facts(context, facts):
    _install_search(
        context,
        [{"fact": f, "_score": 0.8 - i * 0.1} for i, f in enumerate(facts.split("|"))],
    )


@given("семантический слой недоступен")
def given_semantic_unavailable(context):
    _install_search(context, [])


@given("семантический слой падает с ошибкой")
def given_semantic_fails(context):
    _install_search(context, [], fail=True)


# ─── When ───

@when('происходит поиск фактов по запросу "{query}"')
def when_search_facts(context, query):
    context.results = mem.retrieve_facts(query, TEST_UID)


@when('происходит поиск фактов по запросу "{query}" с лимитом {limit}')
def when_search_facts_limited(context, query, limit):
    context.results = mem.retrieve_facts(query, TEST_UID, max_results=int(limit))


@when("происходит поиск фактов по пустому запросу")
def when_search_facts_empty(context):
    context.results = mem.retrieve_facts("", TEST_UID)


# ─── Then ───

@then('в результатах есть "{fact}"')
def then_results_contain(context, fact):
    assert context.results is not None, "поиск не выполнялся"
    assert fact in context.results, f"{fact} not in {context.results}"


@then("семантический слой вызывается с лимитом {limit}")
def then_semantic_called_with_limit(context, limit):
    assert context.search_calls is not None, "семантика не вызывалась"
    assert context.search_calls[2] == int(limit), context.search_calls


@then('результаты содержат только "{fact}"')
def then_results_only(context, fact):
    assert context.results is not None, "поиск не выполнялся"
    assert context.results == [fact], context.results


@then("результаты пустые")
def then_results_empty(context):
    assert context.results == [], context.results


@then('"{fact}" встречается в результатах ровно один раз')
def then_fact_once(context, fact):
    count = context.results.count(fact)
    assert count == 1, f"count={count}, results={context.results}"


@then("в результатах ровно {count} факта")
def then_results_count(context, count):
    assert len(context.results) == int(count), context.results
