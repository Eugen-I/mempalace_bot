from services.prompts import (
    get_smart_prompt,
    get_summary_prompt,
    BASE_RULES,
    FOCUS_CODE_TECH,
    FOCUS_DREAMS_JUNG,
    FOCUS_MEDICINE,
    FOCUS_PHOTO_ART,
    FOCUS_PSYCHOLOGY,
    FOCUS_PHILOSIPHY,
    FOCUS_GENERAL_EXPERT,
    PDF_CHUNK_PROMPT,
    PDF_COMBINE_PROMPT,
)


class TestGetSmartPrompt:
    def test_default_general_expert(self):
        result = get_smart_prompt(query="hello")
        assert "MemPalace" in result
        assert FOCUS_GENERAL_EXPERT in result
        assert BASE_RULES in result

    def test_with_context(self):
        result = get_smart_prompt(context="some notes about dreams", query="tell me more")
        assert "some notes about dreams" in result
        assert "ПРИОРИТЕТ" in result

    def test_dream_analysis(self):
        result = get_smart_prompt(query="мне приснился странный сон")
        assert FOCUS_DREAMS_JUNG in result

    def test_coding_mode(self):
        result = get_smart_prompt(query="напиши функцию на python")
        assert FOCUS_CODE_TECH in result

    def test_medical_query(self):
        result = get_smart_prompt(query="у меня болит голова и симптомы")
        assert FOCUS_MEDICINE in result

    def test_photo_analysis(self):
        result = get_smart_prompt(query="посмотри это фото", has_images=True)
        assert FOCUS_PHOTO_ART in result

    def test_dream_plus_photo(self):
        result = get_smart_prompt(query="мне приснился сон", has_images=True)
        assert FOCUS_DREAMS_JUNG in result
        assert FOCUS_PHOTO_ART in result

    def test_psychology_query(self):
        result = get_smart_prompt(query="расскажи про архетипы юнга")
        assert FOCUS_PSYCHOLOGY in result

    def test_empty_query_defaults_to_general(self):
        result = get_smart_prompt(query="", context="")
        assert FOCUS_GENERAL_EXPERT in result


class TestGetSummaryPrompt:
    def test_basic_summary(self):
        result = get_summary_prompt("user: hello\nassistant: hi")
        assert "РЕЗЮМЕ" in result
        assert "hello" in result

    def test_with_context_prefix(self):
        result = get_summary_prompt("dialog content", context_prefix="CONTEXT:\n")
        assert "CONTEXT" in result

    def test_large_dialog(self):
        dialog = "\n".join(f"line {i}" for i in range(100))
        result = get_summary_prompt(dialog)
        assert "РЕЗЮМЕ" in result


class TestPromptConstants:
    def test_base_rules_content(self):
        assert "ПРАВИЛА" in BASE_RULES
        assert "русском" in BASE_RULES

    def test_focus_modules_exist(self):
        assert FOCUS_CODE_TECH.startswith("💻")
        assert FOCUS_DREAMS_JUNG.startswith("🧠")
        assert FOCUS_MEDICINE.startswith("🏥")
        assert FOCUS_PHOTO_ART.startswith("📸")
        assert FOCUS_PHILOSIPHY.startswith("ФОКУС")
        assert FOCUS_GENERAL_EXPERT.startswith("🌍")
        assert FOCUS_PSYCHOLOGY.startswith("🧠")

    def test_pdf_prompts_exist(self):
        assert "Deutsch" in PDF_CHUNK_PROMPT
        assert "Teilanalysen" in PDF_COMBINE_PROMPT


class TestGetSmartPromptEdgeCases:
    def test_query_similar_to_multiple_rules(self):
        result = get_smart_prompt(query="сон анализ фото психология")
        # First matching rule wins: "Pure Dream Analysis" (because of "сон")
        assert FOCUS_DREAMS_JUNG in result

    def test_non_russian_query(self):
        result = get_smart_prompt(query="hello world how are you")
        assert FOCUS_GENERAL_EXPERT in result

    def test_very_long_query(self):
        long_q = "a" * 10000
        result = get_smart_prompt(query=long_q)
        assert result is not None
