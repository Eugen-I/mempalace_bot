"""services/camera_setup.py — человекочитаемый вывод настроек камеры X-T4.

Локальные LLM (qwen2.5:7b) возвращают camera_setup не строкой, а JSON-объектом
с техническими ключами (type_of_shoot, metering_mode, ...) и числовыми
enum-значениями (white_balance_type: 1). Этот модуль превращает такой объект
в читаемый русский текст для Telegram:

    • Приём съёмки: Мультиэкспозиция, Длинная выдержка
    • Имитация плёнки: ETERNA Bleach Bypass
    • Тип баланса белого: Дневной свет
    • Сдвиг баланса белого (R/B): R+3 / B-5
    ...

Строка (старая схема) возвращается как есть. Русские ключи/значения проходят
напрямую. Терминология сверена с docs/FUJI_XT4_CREATIVE_GUIDE.md (русское
меню X-T4).
"""

from typing import Any

# ─── Русские названия ключей ───
# англ. ключ модели (и её русские варианты) → единая подпись в выводе
_KEY_LABELS: dict[str, str] = {
    # приём съёмки
    "type_of_shoot": "Приём съёмки",
    "приём съёмки": "Приём съёмки",
    "прием съемки": "Приём съёмки",
    "shooting_mode": "Приём съёмки",
    # имитация плёнки
    "impressionism_film": "Имитация плёнки",
    "имитация плёнки": "Имитация плёнки",
    "имитация пленки": "Имитация плёнки",
    "film_simulation": "Имитация плёнки",
    # динамический диапазон
    "dynamic_range": "Динамический диапазон",
    "динамический диапазон": "Динамический диапазон",
    "дд": "Динамический диапазон",
    # баланс белого
    "white_balance_type": "Тип баланса белого",
    "тип баланса белого": "Тип баланса белого",
    "баланс белого": "Тип баланса белого",
    "wb_type": "Тип баланса белого",
    "wb_kelvin": "Цветовая температура (K)",
    "цветовая температура": "Цветовая температура (K)",
    "цвет. температура": "Цветовая температура (K)",
    "wb_shift_rb_value": "Сдвиг баланса белого (R/B)",
    "сдвиг баланса белого": "Сдвиг баланса белого (R/B)",
    "wb_shift": "Сдвиг баланса белого (R/B)",
    "сдвиг бб": "Сдвиг баланса белого (R/B)",
    # цвет
    "color_shift_type": "Цвет",
    "цвет": "Цвет",
    "color": "Цвет",
    "color_level": "Цвет",
    # экспозамер
    "metering_mode": "Экспозамер",
    "экспозамер": "Экспозамер",
    "метр": "Экспозамер",
    # прозрачность / резкость / цветной хром
    "clarity_setting": "Прозрачность (Clarity)",
    "clarity": "Прозрачность (Clarity)",
    "прозрачность": "Прозрачность (Clarity)",
    "sharpness": "Резкость",
    "резкость": "Резкость",
    "color_chrome": "Цветной хром-эффект",
    "цветной хром-эффект": "Цветной хром-эффект",
    "color_chrome_fx_blue": "Хром-эффект FX Синий",
    "хром-эффект fx синий": "Хром-эффект FX Синий",
    "fx_blue": "Хром-эффект FX Синий",
    # тоновая кривая
    "highlight_shadow_curve": "Тоновая кривая (Подсветка/Тень)",
    "tonal_curve": "Тоновая кривая (Подсветка/Тень)",
    "tone_curve": "Тоновая кривая (Подсветка/Тень)",
    "тоновая кривая": "Тоновая кривая (Подсветка/Тень)",
    "тон. кривая": "Тоновая кривая (Подсветка/Тень)",
    "кривая": "Тоновая кривая (Подсветка/Тень)",
    # зерно
    "grain_effect": "Эффект зерна",
    "эффект зерна": "Эффект зерна",
    "grain": "Эффект зерна",
    "зерно": "Эффект зерна",
    # шумоподавление
    "high_iso_nr": "Шумоподавление при высоком ISO",
    "шумоподавление": "Шумоподавление при высоком ISO",
    "шумоподавление при высоком iso": "Шумоподавление при высоком ISO",
    "nr": "Шумоподавление при высоком ISO",
    # монохром/фильтры
    "monochrome_tone": "Монохромный тон (WC/MG)",
    "монохромный тон": "Монохромный тон (WC/MG)",
    "wc_mg": "Монохромный тон (WC/MG)",
    "wc/mg": "Монохромный тон (WC/MG)",
    "bw_filter": "ЧБ-фильтр",
    "цветной фильтр": "ЧБ-фильтр",
    "фильтр": "Дополнительный фильтр",
    # экспозиционный треугольник
    "aperture": "Диафрагма",
    "диафрагма": "Диафрагма",
    "shutter_speed": "Выдержка",
    "выдержка": "Выдержка",
    "iso": "ISO",
    "чувствительность": "ISO",
    "ev": "Компенсация экспозиции (EV)",
    "компенсация экспозиции": "Компенсация экспозиции (EV)",
}

# ─── Enum-словари «код → русское название» ───
# Порядок индексов — по русскому меню X-T4 (см. гайд, раздел «Соответствие
# терминов»). Используется как запасной вариант: промпт требует от модели
# текстовые значения, числа встречаются при невыполнении инструкции.

_WHITE_BALANCE_TYPES: dict[int | str, str] = {
    0: "Авто (приоритет белого)",
    1: "Авто",
    2: "Приоритет среды",
    3: "Цветовая температура",
    4: "Дневной свет",
    5: "Тень",
    6: "Облака",
    7: "Флуоресцентный 1",
    8: "Флуоресцентный 2",
    9: "Флуоресцентный 3",
    10: "Лампы накаливания",
    11: "Под водой",
}

_METERING_MODES: dict[int | str, str] = {
    0: "Мульти",
    1: "Центровзвешенный",
    2: "Средневзвешенный",
    3: "Точечный",
}

_STRENGTH_LEVELS: dict[int | str, str] = {
    0: "Выкл",
    1: "Слабый",
    2: "Сильный",
}

_GAIN_SIZE: dict[int | str, str] = {
    0: "Мелкое",
    1: "Крупное",
}

_BW_FILTERS: dict[str, str] = {
    "none": "Без фильтра",
    "off": "Без фильтра",
    "выкл": "Без фильтра",
    "ye": "+Ye",
    "r": "+R",
    "g": "+G",
}

_SHOOT_TYPES: dict[str, str] = {
    "multi_exposure": "Мультиэкспозиция",
    "long_exposure": "Длинная выдержка",
    "длинная выдержка": "Длинная выдержка",
    "мультиэкспозиция": "Мультиэкспозиция",
    "extreme_clarity": "Экстремально заниженная Clarity",
    "advanced_filter": "Расширенный фильтр",
    "расширенный фильтр": "Расширенный фильтр",
    "broad_filter": "Расширенный фильтр",
    "панорама": "Панорама",
    "panorama": "Панорама",
}

_ADVANCED_FILTERS: dict[str, str] = {
    "toy": "Мини-макет",
    "miniature": "Мини-макет",
    "миникомакет": "Мини-макет",
    "partial_color": "Частичный цвет",
    "частичный цвет": "Частичный цвет",
    "dynamic_tone": "Динамический тон",
    "динамический тон": "Динамический тон",
    "soft_focus": "Мягкий фокус",
    "мягкий фокус": "Мягкий фокус",
}

# ─── Служебные форматы значений по имени ключа ───
_CURVE_KEYS = {"Тоновая кривая (Подсветка/Тень)", "Highlight", "Shadow"}
_WB_SHIFT_KEYS = {"Сдвиг баланса белого (R/B)", "R", "B"}


def _translate(key: str, canonical: str) -> str:
    """Код/русское имя → человекочитаемое имя поля (canonical уже русское)."""
    return canonical


def _format_signed(value: int | float) -> str:
    """Число со знаком: 2 → "+2", -2 → "-2", 0 → "0"."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if value > 0:
        return f"+{value}"
    return str(value)


def _format_number_list(items: list) -> str:
    """Список чисел → строка: 2 → "+2", [3, -4] → "+3 / -4"."""
    if not items:
        return ""
    return " / ".join(_format_signed(v) if isinstance(v, (int, float)) else str(v)
                      for v in items)


def _format_list_with_labels(items: list) -> str:
    """Список значений (в т.ч. enum) → строка через запятую."""
    return ", ".join(str(v) for v in items)


def _format_grain(value: Any) -> str:
    """Эффект зерна: число/строка/список [сила, размер] → «Слабый+Мелкое»."""
    if isinstance(value, dict):
        strength = value.get("strength", value.get("сила", ""))
        size = value.get("size", value.get("размер", ""))
        return _join_strength_size(strength, size)
    if isinstance(value, (list, tuple)):
        if len(value) >= 2:
            return _join_strength_size(value[0], value[1])
        return _strength(value[0]) if value else ""
    return _strength(value)


def _join_strength_size(strength: Any, size: Any) -> str:
    s = _strength(strength)
    z = _size(size)
    return s + ("+" + z if z and s and s != "Выкл" else "")


def _strength(value: Any) -> str:
    if isinstance(value, bool):
        return "Выкл" if not value else "Сильный"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _STRENGTH_LEVELS.get(int(value), _format_signed(int(value)))
    return str(value)


def _size(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _GAIN_SIZE.get(int(value), str(value))
    return str(value)


def _format_white_balance(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _WHITE_BALANCE_TYPES.get(int(value), f"код {int(value)}")
    return str(value)


def _format_metering(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _METERING_MODES.get(int(value), f"код {int(value)}")
    return str(value)


def _format_label_value(key: str, value: Any) -> str:
    """Форматирует пару «ключ: значение» в строку вывода (без маркеров)."""
    label = _KEY_LABELS.get(key, key)

    # Списки с явными подписями осей
    if label == "Сдвиг баланса белого (R/B)":
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            return f"{label}: R{_format_signed(value[0])} / B{_format_signed(value[1])}"
        if isinstance(value, (list, tuple)):
            return f"{label}: {_format_number_list(list(value))}"
        if isinstance(value, dict):
            r = value.get("R", value.get("r", 0))
            b = value.get("B", value.get("b", 0))
            return f"{label}: R{_format_signed(r)} / B{_format_signed(b)}"
        return f"{label}: {_format_number_list([value])}"

    if label == "Тоновая кривая (Подсветка/Тень)":
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            return f"{label}: Подсветка{_format_signed(value[0])} / Тень{_format_signed(value[1])}"
        if isinstance(value, dict):
            h = value.get("highlight", value.get("подсветка", value.get("H")))
            s = value.get("shadow", value.get("тень", value.get("S")))
            if h is not None and s is not None:
                return f"{label}: Подсветка{_format_signed(h)} / Тень{_format_signed(s)}"
            return f"{label}: {value}"
        return f"{label}: {value}"

    # Эффект зерна — специальная обработка сила+размер
    if label == "Эффект зерна":
        return f"{label}: {_format_grain(value)}"

    # Приём съёмки — список кодов переводится в русские названия
    if label == "Приём съёмки":
        if isinstance(value, (list, tuple)):
            names = [_SHOOT_TYPES.get(str(v).lower(), str(v)) for v in value]
            return f"{label}: {_format_list_with_labels(names)}"
        return f"{label}: {_SHOOT_TYPES.get(str(value).lower(), str(value))}"

    # Enum-поля: числа → русские названия
    if label == "Тип баланса белого":
        return f"{label}: {_format_white_balance(value)}"
    if label == "Экспозамер":
        return f"{label}: {_format_metering(value)}"
    if label == "Дополнительный фильтр":
        return f"{label}: {_ADVANCED_FILTERS.get(str(value).lower(), str(value))}"
    if label == "ЧБ-фильтр":
        return f"{label}: {_BW_FILTERS.get(str(value).lower(), str(value))}"
    if label in ("Прозрачность (Clarity)", "Резкость", "Цвет",
                 "Шумоподавление при высоком ISO", "Компенсация экспозиции (EV)",
                 "Монохромный тон (WC/MG)", "Хром-эффект FX Синий"):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if label == "Монохромный тон (WC/MG)" and int(value) == 0:
                return f"{label}: нейтр."
            return f"{label}: {_format_signed(value)}"
        return f"{label}: {value}"
    if label == "Цветной хром-эффект":
        return f"{label}: {_strength(value)}"

    # Обычное значение
    if isinstance(value, (list, tuple)):
        return f"{label}: {_format_number_list(list(value))}"
    if isinstance(value, dict):
        parts = [f"{k}: {v}" for k, v in value.items()]
        return f"{label}: {"; ".join(parts)}"
    return f"{label}: {value}"


def format_camera_setup(setup: Any) -> str:
    """Превращает camera_setup (dict со схемой модели/строка/прочее) в текст.

    - dict → переводит ключи и enum-значения в русские названия;
    - str → возвращает как есть (старая схема — уже текстовые настройки);
    - None/прочее → "" .
    """
    if isinstance(setup, str):
        return setup
    if not isinstance(setup, dict):
        return ""
    lines = []
    for key, value in setup.items():
        if value is None or value == "":
            continue
        line = _format_label_value(key, value)
        if line:
            lines.append(f"• {line}")
    return "\n".join(lines)
