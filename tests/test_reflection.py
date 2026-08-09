"""Тесты services/reflection.py — рефлексия после штурма.

Покрытие: вопрос (happy/пустая тема/длина), сохранение ответа
(happy/пустой ответ/лимит длины/границы).
"""
from services.kv_store import KVStore
from services.reflection import (
    MAX_ANSWER_LEN,
    MAX_THEME_LEN,
    REFLECTION_NS,
    build_reflection_question,
    save_reflection_answer,
)


def _kv(tmp_path):
    return KVStore(db_path=str(tmp_path / "reflection.sqlite"))


# ─── build_reflection_question ───

def test_question_with_theme(tmp_path):
    text = build_reflection_question("   Книга идей  ")
    assert "Рефлексия по теме" in text
    assert "Книга идей" in text
    assert "самой сильной и почему" in text


def test_question_empty_theme():
    text = build_reflection_question("")
    assert "Рефлексия после штурма" in text
    assert "Рефлексия по теме" not in text


def test_question_none_theme():
    text = build_reflection_question(None)
    assert "Рефлексия после штурма" in text


def test_question_theme_truncated():
    long = "Т" * 200
    text = build_reflection_question(long)
    assert "Т" * (MAX_THEME_LEN + 1) not in text
    assert "Т" * MAX_THEME_LEN in text


def test_question_theme_html_escaped():
    text = build_reflection_question("<script>")
    assert "<script>" not in text


# ─── save_reflection_answer ───

def test_save_answer_happy(tmp_path):
    kv = _kv(tmp_path)
    reply = save_reflection_answer(kv, 424242, "Сны", "Самая сильная — про полёт")
    assert reply == "💭 Спасибо, рефлексия записана!"
    keys = kv.keys(namespace=REFLECTION_NS)
    assert len(keys) == 1
    saved = kv.get(keys[0], namespace=REFLECTION_NS)
    assert saved["uid"] == 424242
    assert saved["theme"] == "Сны"
    assert saved["answer"] == "Самая сильная — про полёт"
    assert saved["ts"] > 0


def test_save_answer_empty(tmp_path):
    kv = _kv(tmp_path)
    reply = save_reflection_answer(kv, 1, "Т", "   ")
    assert reply == "Пустой ответ — рефлексия не записана."
    assert kv.keys(namespace=REFLECTION_NS) == []


def test_save_answer_none(tmp_path):
    kv = _kv(tmp_path)
    reply = save_reflection_answer(kv, 1, "Т", None)
    assert "не записана" in reply


def test_save_answer_strips_and_truncates(tmp_path):
    kv = _kv(tmp_path)
    long = "A" * (MAX_ANSWER_LEN + 500)
    save_reflection_answer(kv, 5, "Т", long)
    keys = kv.keys(namespace=REFLECTION_NS)
    saved = kv.get(keys[0], namespace=REFLECTION_NS)
    assert len(saved["answer"]) == MAX_ANSWER_LEN


def test_save_answer_theme_truncated(tmp_path):
    kv = _kv(tmp_path)
    save_reflection_answer(kv, 5, "Т" * 200, "ответ")
    keys = kv.keys(namespace=REFLECTION_NS)
    saved = kv.get(keys[0], namespace=REFLECTION_NS)
    assert len(saved["theme"]) == MAX_THEME_LEN


def test_save_answer_multiple_saved(tmp_path):
    kv = _kv(tmp_path)
    save_reflection_answer(kv, 1, "A", "первый")
    save_reflection_answer(kv, 1, "B", "второй")
    assert len(kv.keys(namespace=REFLECTION_NS)) == 2
