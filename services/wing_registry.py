"""services/wing_registry.py — единый реестр крыльев дворца.

Содержит канонические ключи, отображаемые имена и нормализацию ввода.
Все места, которым нужен whitelist крыльев или русское имя, используют
этот модуль, чтобы списки не расходились.
"""

WING_DISPLAY_NAMES: dict[str, str] = {
    "dreams": "🌙 Сны",
    "projects": "💻 Проекты",
    "philosophy": "🏛 Философия",
    "creative": "🎨 Творчество",
    "psychology": "🧠 Психология",
}

# Канонический порядок крыльев для меню и переборов.
WING_KEYS: tuple[str, ...] = tuple(WING_DISPLAY_NAMES)


def normalize_wing(value: str | None) -> str:
    """Возвращает канонический ключ крыла или ``""`` для неизвестного.

    Регистр и окружающие пробелы не важны: ``" Psychology "`` → ``"psychology"``.
    """
    if not value:
        return ""
    key = value.strip().lower()
    return key if key in WING_DISPLAY_NAMES else ""


def get_wing_display_name(value: str) -> str:
    """Возвращает отображаемое имя крыла; неизвестное значение — как есть."""
    key = normalize_wing(value)
    return WING_DISPLAY_NAMES.get(key, value)
