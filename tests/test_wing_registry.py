"""Unit tests for services.wing_registry — single wing registry."""

import pytest

from services import wing_registry

EXPECTED_DISPLAY_NAMES = {
    "dreams": "🌙 Сны",
    "projects": "💻 Проекты",
    "philosophy": "🏛 Философия",
    "creative": "🎨 Творчество",
    "psychology": "🧠 Психология",
}


def test_display_names_and_order_are_canonical():
    assert wing_registry.WING_DISPLAY_NAMES == EXPECTED_DISPLAY_NAMES
    assert wing_registry.WING_KEYS == tuple(EXPECTED_DISPLAY_NAMES)
    assert len(set(wing_registry.WING_DISPLAY_NAMES.values())) == len(
        wing_registry.WING_DISPLAY_NAMES,
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("dreams", "dreams"),
        ("DREAMS", "dreams"),
        (" Psychology ", "psychology"),
        ("\tcreative\n", "creative"),
        ("unknown", ""),
        ("сны", ""),
        ("", ""),
        ("   ", ""),
        (None, ""),
    ],
)
def test_normalize_wing(raw, expected):
    assert wing_registry.normalize_wing(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("dreams", "🌙 Сны"),
        ("PROJECTS", "💻 Проекты"),
        (" psychology ", "🧠 Психология"),
        ("unknown", "unknown"),
        ("Сны", "Сны"),
        ("", ""),
    ],
)
def test_get_wing_display_name(raw, expected):
    assert wing_registry.get_wing_display_name(raw) == expected
