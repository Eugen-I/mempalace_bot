"""Тесты services/wing_classifier.py — автоопределение крыла по ключевым словам.

Покрытие: каждое крыло, пустые/короткие запросы, конфликты, регистр.
"""
import pytest

import services.wing_classifier as wc


@pytest.mark.parametrize(
    "query,expected",
    [
        ("мне приснился кошмар", "dreams"),
        ("сновидение о полёте", "dreams"),
        ("толкование сна про дом", "dreams"),
        ("nightmare about stairs", "dreams"),
    ],
)
def test_classify_dreams(query, expected):
    assert wc.classify_wing(query) == expected


@pytest.mark.parametrize(
    "query,expected",
    [
        ("как написать функцию на python", "projects"),
        ("исправь баг в docker", "projects"),
        ("деплой на сервер", "projects"),
        ("git репозиторий", "projects"),
    ],
)
def test_classify_projects(query, expected):
    assert wc.classify_wing(query) == expected


@pytest.mark.parametrize(
    "query,expected",
    [
        ("что такое бытие", "philosophy"),
        ("этика и мораль", "philosophy"),
        ("ницше и свобода воли", "philosophy"),
        ("existence and consciousness", "philosophy"),
    ],
)
def test_classify_philosophy(query, expected):
    assert wc.classify_wing(query) == expected


@pytest.mark.parametrize(
    "query,expected",
    [
        ("напишу стих про осень", "creative"),
        ("метафора в рассказе", "creative"),
        ("персонаж и сюжет", "creative"),
        ("photography composition", "creative"),
    ],
)
def test_classify_creative(query, expected):
    assert wc.classify_wing(query) == expected


@pytest.mark.parametrize(
    "query,expected",
    [
        ("психотерапия и травма", "psychology"),
        ("юнгианский анализ", "psychology"),
        ("привязанность и диссоциация", "psychology"),
        ("cptsd выгорание", "psychology"),
        ("тень и архетип", "psychology"),
        ("емдр терапия", "psychology"),
        ("диалектико-поведенческая терапия", "psychology"),
    ],
)
def test_classify_psychology(query, expected):
    assert wc.classify_wing(query) == expected


# ─── границы и негативы ───


@pytest.mark.parametrize("query", ["", "   ", "аб", "x", None])
def test_classify_empty_or_short_returns_none(query):
    assert wc.classify_wing(query) is None


def test_classify_unknown_topic_returns_none():
    assert wc.classify_wing("погода сегодня хорошая") is None


def test_classify_case_insensitive():
    assert wc.classify_wing("PYTHON код") == "projects"
    assert wc.classify_wing("СОН про лето") == "dreams"


def test_classify_cyrillic_lowercase_ok():
    assert wc.classify_wing("ФУНКЦИЯ") == "projects"


def test_classify_wins_by_max_score():
    query = "сон про python и баг"
    result = wc.classify_wing(query)
    assert result == "projects"


def test_classify_single_common_word_disambiguated():
    assert wc.classify_wing("история и персонаж") == "creative"
