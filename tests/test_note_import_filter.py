from pathlib import Path

from services.note_import_filter import (
    _contains_meaningful_content,
    _normalize_text,
    _word_count,
    filter_notes_in_folder,
    should_import_note,
)


class TestNoteImportFilter:
    def test_title_only_note_is_filtered(self):
        decision = should_import_note("My title", title="My title")
        assert decision.should_import is False
        assert decision.reason == "title-only"

    def test_empty_note_is_filtered(self):
        decision = should_import_note("   \n\n  ", title="Untitled")
        assert decision.should_import is False
        assert decision.reason == "empty"

    def test_meaningful_note_is_kept(self):
        text = "This is a meaningful note with several words and enough context to be worth importing."
        decision = should_import_note(text, title="Meaningful note")
        assert decision.should_import is True
        assert decision.reason == "kept"

    def test_junk_with_only_urls_and_emoji_is_filtered(self):
        decision = should_import_note("https://example.com 🤷‍♂️ 🙃", title="Link")
        assert decision.should_import is False
        assert decision.reason == "low-signal"

    def test_filter_notes_in_folder_skips_obvious_junk(self, tmp_path):
        good = tmp_path / "good.md"
        good.write_text("A useful note with actual substance and clear context.", encoding="utf-8")

        junk = tmp_path / "junk.md"
        junk.write_text("Untitled", encoding="utf-8")

        result = filter_notes_in_folder(tmp_path)

        assert result["kept_count"] == 1
        assert result["skipped_count"] == 1
        assert result["skipped_paths"] == [str(junk)]
        assert any(item.path == str(good) for item in result["decisions"])

    def test_filter_notes_in_folder_supports_strict_mode(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("Short note", encoding="utf-8")

        result = filter_notes_in_folder(tmp_path, mode="strict")

        assert result["kept_count"] == 0
        assert result["skipped_count"] == 1

    # ---------- _normalize_text / _word_count ----------

    def test_normalize_text_collapses_whitespace(self):
        assert _normalize_text("  a   b  \n c ") == "a b c"

    def test_normalize_text_empty(self):
        assert _normalize_text("   ") == ""
        assert _normalize_text(None) == ""

    def test_word_count_basic(self):
        assert _word_count("one two three") == 3

    def test_word_count_empty(self):
        assert _word_count("   ") == 0

    def test_word_count_cyrillic(self):
        assert _word_count("привет мир как дела") == 4

    # ---------- _contains_meaningful_content ----------

    def test_meaningful_empty_text(self):
        assert _contains_meaningful_content("   ") is False

    def test_meaningful_short_text(self):
        assert _contains_meaningful_content("коротк") is False

    def test_meaningful_punctuation_only(self):
        assert _contains_meaningful_content("!!!  ???") is False
        # >8 символов чистой пунктуации (иначе ловит len<8 раньше)
        assert _contains_meaningful_content("!!! ??? !!!  ??") is False

    def test_meaningful_url_only(self):
        assert _contains_meaningful_content("https://example.com/very/long/url") is False

    def test_meaningful_digits_and_emoji(self):
        assert _contains_meaningful_content("12345 67890") is False
        assert _contains_meaningful_content("🎉🎉🎉") is False

    def test_meaningful_two_words_only(self):
        assert _contains_meaningful_content("hello world") is False

    def test_meaningful_special_title_word(self):
        assert _contains_meaningful_content("todo") is False
        assert _contains_meaningful_content("untitled") is False

    def test_meaningful_junk_marker(self):
        assert _contains_meaningful_content("lorem ipsum dolor sit amet") is False
        assert _contains_meaningful_content("qwerty asdf") is False
        assert _contains_meaningful_content("spam spam and junk") is False

    def test_meaningful_normal_text(self):
        assert _contains_meaningful_content("заметка про встречу завтра утром") is True

    # ---------- should_import_note: edge paths ----------

    def test_should_import_none_text(self):
        decision = should_import_note(None)
        assert decision.should_import is False
        assert decision.reason == "empty"

    def test_should_import_special_title_only(self):
        decision = should_import_note("", title="task")
        assert decision.should_import is False
        assert decision.reason == "empty"

    def test_should_import_title_equals_body(self):
        decision = should_import_note("заметка", title="заметка")
        assert decision.should_import is False
        assert decision.reason == "title-only"

    def test_should_import_low_word_count(self):
        decision = should_import_note("ab cd", title="")
        assert decision.should_import is False
        assert decision.reason == "low-signal"

    def test_should_import_score_below_threshold(self):
        # 1-2 слова без длинных слов → score < 4
        decision = should_import_note("ab cd", title="")
        assert decision.should_import is False

    def test_should_import_emoji_and_digits_penalties(self):
        # цифры/эмодзи дают штрафы в scorer, но meaningful — отклонит
        d1 = should_import_note("123 456 789", title="")
        assert d1.should_import is False
        d2 = should_import_note("🎉 123 🚀 456 🎉 789", title="")
        assert d2.should_import is False

    def test_should_import_url_penalty(self):
        # текст с url → score -= 3, но слова дают баллы
        decision = should_import_note("check this site https://example.com now please", title="")
        assert decision.reason in ("kept", "low-signal")

    def test_should_import_strict_threshold(self):
        text = "просто заметка на несколько слов"
        d_default = should_import_note(text, mode="default")
        d_strict = should_import_note(text, mode="strict")
        assert d_default.score >= 4
        assert d_strict.score < 6 or d_strict.reason == "kept"

    def test_should_import_empty_body_with_title(self):
        decision = should_import_note("", title="My Note")
        assert decision.should_import is False
        assert decision.reason == "title-only"

    # ---------- filter_notes_in_folder ----------

    def test_filter_folder_missing(self):
        result = filter_notes_in_folder("/nonexistent/path/xyz")
        assert result["kept_count"] == 0
        assert result["skipped_count"] == 0
        assert result["decisions"] == []
        assert result["skipped_paths"] == []

    def test_filter_folder_skips_directories(self, tmp_path):
        (tmp_path / "sub").mkdir()
        note = tmp_path / "good.md"
        note.write_text("a very useful note with context inside it", encoding="utf-8")
        result = filter_notes_in_folder(tmp_path)
        assert result["kept_count"] == 1

    def test_filter_folder_skips_unsupported_ext(self, tmp_path):
        note = tmp_path / "note.pdf"
        note.write_bytes(b"%PDF-1.4 fake")
        result = filter_notes_in_folder(tmp_path)
        assert result["kept_count"] == 0
        assert result["skipped_count"] == 0

    def test_filter_folder_utf8_fallback_latin1(self, tmp_path):
        note = tmp_path / "old.txt"
        note.write_bytes(b"caf\xe9")
        result = filter_notes_in_folder(tmp_path)
        assert result["skipped_count"] == 1
        assert result["kept_count"] == 0

    def test_filter_folder_unreadable_file(self, tmp_path, monkeypatch):
        note = tmp_path / "bad.md"
        note.write_text("content", encoding="utf-8")

        def selective(self, *args, **kwargs):
            # utf-8 → UnicodeDecodeError; latin-1 → также OSError (падает в except Exception)
            if kwargs.get("encoding") == "utf-8":
                raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")
            raise OSError("disk error")

        monkeypatch.setattr(Path, "read_text", selective)
        result = filter_notes_in_folder(tmp_path)
        assert result["skipped_count"] == 1

    def test_filter_folder_rtf_and_markdown_supported(self, tmp_path):
        for name in ("a.rtf", "b.markdown"):
            f = tmp_path / name
            f.write_text("заметка с достаточным содержанием для импорта", encoding="utf-8")
        result = filter_notes_in_folder(tmp_path)
        assert result["kept_count"] == 2

    def test_filter_folder_sorts_paths(self, tmp_path):
        b = tmp_path / "b.md"
        a = tmp_path / "a.md"
        a.write_text("заметка с достаточным содержанием для импорта файла", encoding="utf-8")
        b.write_text("заметка с достаточным содержанием для импорта файла", encoding="utf-8")
        result = filter_notes_in_folder(tmp_path)
        assert [d.path for d in result["decisions"]] == [str(a), str(b)]
