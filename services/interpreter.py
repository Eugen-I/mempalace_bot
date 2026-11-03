"""interpreter.py — словарь соответствий названий RU↔EN.

Файл пар хранится рядом с базой MemPalace (config.DATA_DIR/interpretation.json)
и автоматически пополняется системой:
- при старте бота (seed_known_pairs) — известные пары из KG_PREDICATES,
  _LOCALE_ALIASES и предикатов БД;
- при добавлении факта в граф знаний (register в cb_kg_add_confirm).

Файл не мигрирует базу MemPalace: пары используются на уровне
отображения/ввода (статистика KG показывает 'EN (RU)').
"""

import json
import logging
import os
import threading
from typing import Iterable

from config import DATA_DIR

logger = logging.getLogger(__name__)

PAIRS_FILE = os.path.join(DATA_DIR, "interpretation.json")

# Известные русские предикаты, которые встречаются в БД MemPalace.
DB_STYLE_PREDICATES = [
    ("contains_idea", "содержит_идею"),
    ("contains_quote", "содержит_цитату"),
    ("topic", "тема"),
    ("wrote", "написал"),
]

_lock = threading.Lock()
_pairs: dict[str, str] = {}
_loaded = False


def _normalize(name: object) -> str:
    return (str(name) if name is not None else "").strip().lower()


def _strip_emoji(label: str) -> str:
    text = label.strip()
    if " " in text:
        text = text.split(" ", 1)[-1].strip()
    return text


def _is_latin(name: str) -> bool:
    return bool(name) and all(ord(c) < 128 for c in name)


def _load_unlocked() -> None:
    global _loaded
    if _loaded:
        return
    file_pairs: dict[str, str] = {}
    try:
        with open(PAIRS_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            for en, ru in raw.items():
                if not isinstance(en, str) or not isinstance(ru, str):
                    continue
                en_n, ru_n = _normalize(en), _normalize(ru)
                if en_n and ru_n:
                    file_pairs[en_n] = ru_n
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    _pairs.clear()
    _pairs.update(file_pairs)
    _loaded = True


def load_pairs() -> dict[str, str]:
    """Загружает пары EN→RU из файла (пустой словарь при отсутствии/битом файле)."""
    with _lock:
        _load_unlocked()
        return dict(_pairs)


def save_pairs() -> None:
    """Атомарно записывает пары в файл."""
    tmp = PAIRS_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_pairs, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp, PAIRS_FILE)
    except OSError:
        logger.warning("Не удалось сохранить %s", PAIRS_FILE)


def register_many(pairs: Iterable[tuple[str, str]]) -> int:
    """Добавляет отсутствующие пары (существующие не перезаписывает).

    Возвращает количество добавленных пар.
    """
    added = 0
    with _lock:
        _load_unlocked()
        for en, ru in pairs:
            en_n, ru_n = _normalize(en), _normalize(ru)
            if not en_n or not ru_n or en_n == ru_n or en_n in _pairs:
                continue
            _pairs[en_n] = ru_n
            added += 1
        if added:
            save_pairs()
    return added


def register(en: str, ru: str) -> bool:
    """Добавляет одну пару EN↔RU. True, если пара была добавлена."""
    return register_many([(en, ru)]) == 1


def to_ru(name: str) -> str | None:
    """Русское имя для английского (или None, если пары нет)."""
    n = _normalize(name)
    if not n:
        return None
    with _lock:
        _load_unlocked()
        return _pairs.get(n)


def to_en(name: str) -> str | None:
    """Английское имя для русского (или None, если пары нет)."""
    n = _normalize(name)
    if not n:
        return None
    with _lock:
        _load_unlocked()
        for en, ru in _pairs.items():
            if ru == n:
                return en
    return None


def display_name(name: str) -> str:
    """Имя в формате 'EN (RU)' / 'RU (EN)', без перевода — как есть."""
    ru = to_ru(name)
    if ru:
        return f"{name} ({ru})"
    en = to_en(name)
    if en:
        return f"{en} ({name})"
    return name


def seed_known_pairs() -> int:
    """Регистрирует известные пары бота. Возвращает количество добавленных.

    Источники: KG_PREDICATES (EN-предикат + RU-лейбл), предикаты БД
    (DB_STYLE_PREDICATES) и _LOCALE_ALIASES (RU-крыло → EN-крыло).
    """
    from handlers.palace.shared import _LOCALE_ALIASES, KG_PREDICATES

    pairs: list[tuple[str, str]] = list(DB_STYLE_PREDICATES)
    for pred, label in KG_PREDICATES:
        ru = _strip_emoji(label)
        if ru:
            pairs.append((pred, ru))
    for ru, en in _LOCALE_ALIASES.items():
        if _is_latin(en) and not _is_latin(ru):
            pairs.append((en, ru))
    return register_many(pairs)
