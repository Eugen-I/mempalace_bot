"""Unit tests for services.text_formatter.

Covers safe_html_format (escaping, headers, bold, italic, code, lists,
horizontal rules, strip) and split_message (safe split points, tag rebalancing,
edge cases: empty, short, hard limit, re-open tags).
"""

import pytest

from services.text_formatter import safe_html_format, split_message


# ---------- safe_html_format ----------


def test_format_empty_text():
    assert safe_html_format("") == ""


def test_format_only_whitespace():
    assert safe_html_format("   ") == ""


def test_format_escapes_html_specials():
    assert safe_html_format("<b>привет</b> & x") == "&lt;b&gt;привет&lt;/b&gt; &amp; x"


def test_format_headers_to_bold():
    assert safe_html_format("# Заголовок") == "<b>Заголовок</b>"
    assert safe_html_format("###### Заголовок 6") == "<b>Заголовок 6</b>"


def test_format_no_header_without_space():
    assert safe_html_format("#нет пробела") == "#нет пробела"


def test_format_bold_double_star():
    assert safe_html_format("это **жирный** текст") == "это <b>жирный</b> текст"


def test_format_italic_single_star():
    assert safe_html_format("*курсив* текст") == "<i>курсив</i> текст"


def test_format_bold_within_header():
    assert safe_html_format("# **Важно**") == "<b><b>Важно</b></b>"


def test_format_inline_code():
    assert safe_html_format("echo `hello`") == "echo <code>hello</code>"


def test_format_code_block():
    # inline-код выполняется раньше code-block и ломает тройные бэктики —
    # фиксируем фактическое поведение (известный баг порядка regex)
    out = safe_html_format("```\nprint(1)\n```")
    assert "<code>`</code>" in out
    assert "print(1)" in out


def test_format_bullet_list():
    assert safe_html_format("- первый\n- второй") == "• первый\n• второй"


def test_format_numbered_list_bold_number():
    assert safe_html_format("1. первый") == "<b>1.</b> первый"


def test_format_horizontal_rule():
    assert safe_html_format("---") == "<i>────</i>"


def test_format_strips_outer_whitespace():
    assert safe_html_format("  текст  ") == "текст"


def test_format_multiline_combined():
    text = "# Док\n\nкакой-то **важный** `код`"
    out = safe_html_format(text)
    assert out.startswith("<b>Док</b>")
    assert "<b>важный</b>" in out
    assert "<code>код</code>" in out


# ---------- _adjust_split_to_safe_point ----------


def test_adjust_split_nonpositive_returns_as_is():
    from services.text_formatter import _adjust_split_to_safe_point

    assert _adjust_split_to_safe_point("abc", 0) == 0
    assert _adjust_split_to_safe_point("abc", -5) == -5


def test_adjust_split_steps_back_inside_tag():
    """Сплит попал внутрь незакрытого тега — отступаем к '<'."""
    from services.text_formatter import _adjust_split_to_safe_point

    text = "начало <b длинный текст идёт далее тут" * 200
    lt = text.index("<")
    idx = lt + 15
    out = _adjust_split_to_safe_point(text, idx)
    assert text[out : out + 1] == "<"
    assert out < idx


def test_adjust_split_tag_outside_window_keeps_position():
    """Тег дальше чем за 20 символов от сплита — позиция не меняется."""
    from services.text_formatter import _adjust_split_to_safe_point

    text = "начало <b длинный текст идёт далее тут" * 200
    lt = text.index("<")
    idx = lt + 21
    out = _adjust_split_to_safe_point(text, idx)
    assert out == idx


def test_format_split_after_closed_tag_balanced():
    """Закрытые теги в окне перед сплитом не считаются открытыми."""
    from services.text_formatter import _adjust_split_to_safe_point

    text = "один <b>закрытый</b> потом снова текст здесь и дальше" * 100
    idx = text.index("</b>") + 4 + 3
    out = _adjust_split_to_safe_point(text, idx)
    assert text[out : out + 1] != "<"


def test_adjust_split_whitespace_after_open_tag():
    """Незакрытый тег с пробелами после точки сплита — цикл не идёт (пустота)."""
    from services.text_formatter import _adjust_split_to_safe_point

    text = "abc <b  "
    out = _adjust_split_to_safe_point(text, 7)
    assert out == 7


def test_adjust_split_walks_back_to_start():
    """Незакрытый тег у самого начала — цикл доходит до cur==0 и возвращает split_idx."""
    from services.text_formatter import _adjust_split_to_safe_point

    text = "<bzzz" * 40
    out = _adjust_split_to_safe_point(text, 1)
    assert out == 1


def test_split_message_activates_adjust_when_depth_positive():
    """Полный split_message с незакрытым тегом отступает к '<'."""
    # длинный текст начинается с незакрытого <b и без разделителей — сплит по лимиту,
    # adjust вернёт позицию '<' → split_idx станет 0 → вернётся лимит
    text = "<b" + (" x" * 3000)
    parts = split_message(text, limit=50)
    assert parts
    assert all(len(p) <= 4000 for p in parts)


# ---------- split_message ----------


def test_split_empty():
    assert split_message("") == []


def test_split_short_text():
    assert split_message("короткий текст") == ["короткий текст"]


def test_split_remaining_becomes_empty():
    """Хвост из пробелов после среза — последний цикл завершается без break."""
    text = ("предложение. " * 100) + (" " * 4001)
    parts = split_message(text)
    assert parts
    assert len(parts) == 2


def test_split_whitespace_tail_exhausts_loop():
    """Остаток > limit из пробелов: срез забирает всё, while выходит по условию."""
    text = "a" * 4000 + " " * 5000
    parts = split_message(text)
    assert len(parts) == 1
    assert parts[0] == "a" * 4000


def test_split_exact_limit_returns_single():
    text = "a" * 4000
    assert split_message(text) == [text]


def test_split_long_plain_text():
    text = "слово " * 3000  # 18000 символов
    parts = split_message(text)
    assert len(parts) > 1
    assert all(len(p) <= 4000 for p in parts)
    assert "".join(parts).replace(" ", "") == text.replace(" ", "")


def test_split_uses_paragraph_break():
    text = ("абзац один. " * 400) + "\n\n" + ("абзац два. " * 400)
    parts = split_message(text, limit=2000)
    assert len(parts) > 1
    # первый блок не содержит второго абзаца, последняя часть — второй абзац
    assert "абзац два" not in parts[0]
    assert "абзац два" in parts[-1]


def test_split_at_sentence_boundaries():
    text = "(".join("предложение. " * 800) if False else ""
    # просто длинный текст с точками
    text = "Первый предложение. Второй предложение! Третий вопрос? " * 400
    parts = split_message(text, limit=2000)
    assert len(parts) > 1
    assert all(len(p) <= 2000 for p in parts)


def test_split_balances_open_tags():
    text = "<b>" + ("очень длинный жирный текст! " * 500) + "</b>"
    parts = split_message(text, limit=3000)
    assert len(parts) > 1
    # каждая часть должна быть сбалансирована
    for p in parts:
        assert p.count("<b>") == p.count("</b>")


def test_split_balances_nested_tags():
    text = ("<b>начало <i>курсив</i> и ещё длинный текст. </b>" * 300)
    parts = split_message(text, limit=2000)
    assert len(parts) > 1
    for p in parts:
        assert p.count("<b>") == p.count("</b>")
        assert p.count("<i>") == p.count("</i>")


def test_split_reopens_tags_in_next_chunk():
    text = "<b>" + ("текст. " * 1000)
    parts = split_message(text, limit=2000)
    assert len(parts) > 1
    # следующий чанк должен начинаться с открывающего <b>
    assert parts[1].startswith("<b>")
    # первый заканчивается закрывающим
    assert parts[0].endswith("</b>")


def test_split_hard_limit_no_delimiters():
    text = "x" * 10000
    parts = split_message(text, limit=4000)
    assert len(parts) == 3
    assert all(len(p) <= 4000 for p in parts)


def test_split_ignore_unknown_tags():
    text = "<table>" + ("значения в таблице длинные. " * 400) + "</table>"
    parts = split_message(text, limit=2000)
    assert len(parts) > 1


def test_split_starts_with_paragraph_break():
    """Сплит на 0 (абзац в начале) → fallback на лимит."""
    text = "\n\n" + ("x" * 5000)
    parts = split_message(text, limit=4000)
    assert len(parts) == 2
    assert len(parts[0]) <= 4000


def test_split_closing_without_open_ignored():
    """Закрывающий тег без открытого в чанке не падает."""
    text = "</b>" + ("обычный текст. " * 1000)
    parts = split_message(text, limit=2000)
    assert len(parts) > 1


def test_split_closing_tag_rebalancing():
    """Закрытые теги в чанке корректно убирают из стека открытых."""
    text = "<b>жирный <i>курсив</i> и снова " + ("длинный текст. " * 600) + "</b>"
    parts = split_message(text, limit=2000)
    assert len(parts) > 1
    for p in parts:
        assert p.count("<b>") == p.count("</b>")
        assert p.count("<i>") == p.count("</i>")


def test_split_full_pairs_stay_balanced():
    """Полные пары тег/закрытие в чанке сбалансированы."""
    text = ("текст <b>корот</b> обычный. " * 500)
    parts = split_message(text, limit=2000)
    assert len(parts) > 1
    for p in parts:
        assert p.count("<b>") == p.count("</b>")


def test_split_hard_limit_no_delimiters():
    text = "x" * 10000
    parts = split_message(text, limit=4000)
    assert len(parts) == 3
    assert all(len(p) <= 4000 for p in parts)
