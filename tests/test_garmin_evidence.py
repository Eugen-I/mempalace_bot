"""Tests for the curated evidence whitelist."""

from __future__ import annotations

from services.garmin.evidence import (
    CITATION_IDS,
    EVIDENCE,
    citations_for_flags,
    format_citations,
    get_evidence,
)


def test_registry_contains_e1_to_e12():
    assert CITATION_IDS == {f"E{number}" for number in range(1, 13)}
    assert set(EVIDENCE) == CITATION_IDS


def test_every_card_has_a_source_and_url():
    for item in EVIDENCE.values():
        assert item.title
        assert item.source
        assert item.url.startswith("https://")
        assert item.key_finding
        assert item.use_for


def test_flag_mapping_is_subset_of_whitelist():
    citations = citations_for_flags(
        ["sleep_short", "hrv_below_baseline", "no_activities", "unknown"]
    )
    assert citations
    assert set(citations) <= CITATION_IDS
    assert "E3" in citations
    assert "E4" in citations


def test_unknown_flags_get_default_citations():
    citations = citations_for_flags(["something_new"])
    assert citations == ["E3", "E4"]


def test_format_citations_deduplicates_and_ignores_unknown():
    lines = format_citations(["E3", "E3", "E99"])
    assert len(lines) == 1
    assert "Kong" in lines[0]
    assert get_evidence("E3").id == "E3"
