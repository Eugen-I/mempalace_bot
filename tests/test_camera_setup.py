"""Unit-тесты для services.camera_setup — человекочитаемый вывод настроек X-T4.

Паттерн: happy path + негативы + границы. Проверяется, что технические
английские ключи и числовые enum-значения модели превращаются в русские
названия, а списки — в читаемые строки с подписями.
"""

from services import camera_setup as cs


# ─── happy path: полный dict из примера пользователя ───

def test_format_full_dict_russian_labels():
    setup = {
        "type_of_shoot": ["multi_exposure", "long_exposure"],
        "impressionism_film": "ETERNA Bleach Bypass",
        "dynamic_range": "DR400",
        "white_balance_type": 1,
        "color_shift_type": -2,
        "wb_shift_rb_value": [3, -5],
        "metering_mode": 2,
        "clarity_setting": 2,
        "highlight_shadow_curve": [-1, 3],
    }
    text = cs.format_camera_setup(setup)
    assert "Приём съёмки: Мультиэкспозиция, Длинная выдержка" in text
    assert "Имитация плёнки: ETERNA Bleach Bypass" in text
    assert "Динамический диапазон: DR400" in text
    assert "Тип баланса белого: Авто" in text
    assert "Цвет: -2" in text
    assert "Сдвиг баланса белого (R/B): R+3 / B-5" in text
    assert "Экспозамер: Средневзвешенный" in text
    assert "Прозрачность (Clarity): +2" in text
    assert "Тоновая кривая (Подсветка/Тень): Подсветка-1 / Тень+3" in text


def test_no_english_keys_in_output():
    setup = {
        "type_of_shoot": ["multi_exposure"],
        "impressionism_film": "Classic Chrome",
        "white_balance_type": 4,
        "wb_shift_rb_value": [3, -5],
        "metering_mode": 3,
        "clarity_setting": 2,
        "highlight_shadow_curve": [-1, 3],
    }
    text = cs.format_camera_setup(setup)
    for eng in ("type_of_shoot", "impressionism_film", "white_balance_type",
                "wb_shift_rb_value", "metering_mode", "clarity_setting",
                "highlight_shadow_curve"):
        assert eng not in text, f"английский ключ {eng} попал в вывод"


def test_no_bare_numbers_for_enums():
    setup = {
        "white_balance_type": 1,
        "metering_mode": 2,
        "color_shift_type": -2,
    }
    text = cs.format_camera_setup(setup)
    assert "white_balance_type" not in text and "metering_mode" not in text
    assert "Авто" in text  # white_balance_type: 1 → «Авто»
    assert "Средневзвешенный" in text  # metering_mode: 2
    assert "Цвет: -2" in text  # color_shift_type → «Цвет» со знаком


# ─── enum-словари: границы ───

def test_white_balance_types_boundaries():
    assert cs._format_white_balance(0) == "Авто (приоритет белого)"
    assert cs._format_white_balance(1) == "Авто"
    assert cs._format_white_balance(2) == "Приоритет среды"
    assert cs._format_white_balance(3) == "Цветовая температура"
    assert cs._format_white_balance(11) == "Под водой"
    assert cs._format_white_balance(12) == "код 12"  # вне диапазона
    assert cs._format_white_balance("Дневной свет") == "Дневной свет"


def test_metering_modes_boundaries():
    assert cs._format_metering(0) == "Мульти"
    assert cs._format_metering(3) == "Точечный"
    assert cs._format_metering(4) == "код 4"
    assert cs._format_metering("Точечный") == "Точечный"


def test_strength_boundaries():
    assert cs._strength(0) == "Выкл"
    assert cs._strength(1) == "Слабый"
    assert cs._strength(2) == "Сильный"
    assert cs._strength(3) == "+3"  # вне диапазона → число со знаком
    assert cs._strength(True) == "Сильный"
    assert cs._strength(False) == "Выкл"
    assert cs._strength("Сильный") == "Сильный"


def test_format_signed_boundaries():
    # BVA-границы: значение 1 не должно попадать в ветку ">0" с сдвигом на 1
    assert cs._format_signed(1) == "+1"
    assert cs._format_signed(0) == "0"
    assert cs._format_signed(-1) == "-1"
    # float: целое конвертируется в int, нецелое остаётся как есть
    assert cs._format_signed(3.0) == "+3"
    assert cs._format_signed(-4.0) == "-4"
    assert cs._format_signed(3.5) == "+3.5"
    assert cs._format_signed(0.0) == "0"


def test_size_boundaries():
    assert cs._size(0) == "Мелкое"
    assert cs._size(1) == "Крупное"
    assert cs._size(2) == "2"  # вне диапазона
    assert cs._size("Мелкое") == "Мелкое"


# ─── списки с подписями ───

def test_wb_shift_formats_with_signs():
    assert cs._format_label_value(
        "wb_shift_rb_value", [3, -5],
    ) == "Сдвиг баланса белого (R/B): R+3 / B-5"
    assert cs._format_label_value(
        "wb_shift_rb_value", [0, 0],
    ) == "Сдвиг баланса белого (R/B): R0 / B0"
    assert cs._format_label_value(
        "wb_shift_rb_value", [-9, 9],
    ) == "Сдвиг баланса белого (R/B): R-9 / B+9"
    assert cs._format_label_value(
        "wb_shift_rb_value", {"R": 2, "B": -3},
    ) == "Сдвиг баланса белого (R/B): R+2 / B-3"


def test_wb_shift_fallback_branches():
    # lowercase ключи r/b и русские «сдвиг…»/«сдвиг_rb»
    assert cs._format_label_value(
        "wb_shift_rb_value", {"r": 1, "b": -1},
    ) == "Сдвиг баланса белого (R/B): R+1 / B-1"
    # только одно из двух полей → второе падает на дефолт "0"
    assert cs._format_label_value(
        "wb_shift_rb_value", {"R": 2},
    ) == "Сдвиг баланса белого (R/B): R+2 / B0"
    assert cs._format_label_value(
        "wb_shift_rb_value", {"B": 3},
    ) == "Сдвиг баланса белого (R/B): R0 / B+3"
    # список из одного элемента → формат через список
    assert cs._format_label_value(
        "wb_shift_rb_value", [1],
    ) == "Сдвиг баланса белого (R/B): +1"
    # скаляр
    assert cs._format_label_value(
        "wb_shift_rb_value", 2,
    ) == "Сдвиг баланса белого (R/B): +2"


def test_curve_formats_with_labels():
    assert cs._format_label_value(
        "highlight_shadow_curve", [-1, 3],
    ) == "Тоновая кривая (Подсветка/Тень): Подсветка-1 / Тень+3"
    assert cs._format_label_value(
        "highlight_shadow_curve", {"highlight": -2, "shadow": 4},
    ) == "Тоновая кривая (Подсветка/Тень): Подсветка-2 / Тень+4"


def test_curve_fallback_branches():
    # русские ключи «подсветка»/«тень»
    assert cs._format_label_value(
        "highlight_shadow_curve", {"подсветка": -1, "тень": 2},
    ) == "Тоновая кривая (Подсветка/Тень): Подсветка-1 / Тень+2"
    # одиночные H/S
    assert cs._format_label_value(
        "highlight_shadow_curve", {"H": 1, "S": -2},
    ) == "Тоновая кривая (Подсветка/Тень): Подсветка+1 / Тень-2"
    # неполный dict → passthrough dict
    assert cs._format_label_value(
        "highlight_shadow_curve", {"highlight": 1},
    ) == "Тоновая кривая (Подсветка/Тень): {'highlight': 1}"
    # список из одного элемента → passthrough
    assert cs._format_label_value(
        "highlight_shadow_curve", [1],
    ) == "Тоновая кривая (Подсветка/Тень): [1]"


def test_curve_empty_kept():
    assert cs._format_label_value("highlight_shadow_curve", "контраст") == \
        "Тоновая кривая (Подсветка/Тень): контраст"


# ─── зерно ───

def test_grain_formats_strength_and_size():
    assert cs._format_label_value("grain_effect", [1, 0]) == "Эффект зерна: Слабый+Мелкое"
    assert cs._format_label_value("grain_effect", [2, 1]) == "Эффект зерна: Сильный+Крупное"
    assert cs._format_label_value("grain_effect", [0, 0]) == "Эффект зерна: Выкл"
    assert cs._format_label_value("grain_effect", {"strength": 2, "size": 1}) == \
        "Эффект зерна: Сильный+Крупное"
    assert cs._format_label_value("grain_effect", "Сильный") == "Эффект зерна: Сильный"


def test_grain_fallback_branches():
    # список из одного элемента (ветка len<2)
    assert cs._format_label_value("grain_effect", [2]) == "Эффект зерна: Сильный"
    assert cs._format_label_value("grain_effect", []) == "Эффект зерна: "
    # русские ключи как fallback для strength/size
    assert cs._format_label_value("grain_effect", {"сила": 2, "размер": 1}) == \
        "Эффект зерна: Сильный+Крупное"
    assert cs._format_label_value("grain_effect", {"сила": 1}) == "Эффект зерна: Слабый"
    # dict с неизвестными ключами → пустая строка (строка-строка фильтруется)
    assert cs._format_grain({"foo": 1, "bar": 0}) == ""


# ─── приём съёмки ───

def test_shoot_type_translated():
    assert cs._format_label_value("type_of_shoot", "multi_exposure") == \
        "Приём съёмки: Мультиэкспозиция"
    assert cs._format_label_value("type_of_shoot", "long_exposure") == \
        "Приём съёмки: Длинная выдержка"
    assert cs._format_label_value("type_of_shoot", "Мультиэкспозиция") == \
        "Приём съёмки: Мультиэкспозиция"
    assert cs._format_label_value("type_of_shoot", ["multi_exposure"]) == \
        "Приём съёмки: Мультиэкспозиция"


# ─── дополнительные фильтры / ЧБ-фильтр / монохром ───

def test_advanced_filter_translated():
    assert cs._format_label_value(
        "фильтр", "toy",
    ) == "Дополнительный фильтр: Мини-макет"
    assert cs._format_label_value(
        "фильтр", "partial_color",
    ) == "Дополнительный фильтр: Частичный цвет"
    assert cs._format_label_value(
        "фильтр", "dynamic_tone",
    ) == "Дополнительный фильтр: Динамический тон"
    assert cs._format_label_value(
        "фильтр", "soft_focus",
    ) == "Дополнительный фильтр: Мягкий фокус"


def test_bw_filter_translated():
    assert cs._format_label_value("bw_filter", "ye") == "ЧБ-фильтр: +Ye"
    assert cs._format_label_value("bw_filter", "r") == "ЧБ-фильтр: +R"
    assert cs._format_label_value("bw_filter", "g") == "ЧБ-фильтр: +G"
    assert cs._format_label_value("bw_filter", "none") == "ЧБ-фильтр: Без фильтра"


def test_monochrome_tone_signed():
    assert cs._format_label_value("wc_mg", 2) == "Монохромный тон (WC/MG): +2"
    assert cs._format_label_value("wc_mg", 0) == "Монохромный тон (WC/MG): нейтр."
    assert cs._format_label_value("wc_mg", -3) == "Монохромный тон (WC/MG): -3"


# ─── русские ключи проходят напрямую ───

def test_russian_keys_passed_through():
    setup = {"Имитация плёнки": "ACROS", "Экспозамер": "Точечный"}
    text = cs.format_camera_setup(setup)
    assert "• Имитация плёнки: ACROS" in text
    assert "• Экспозамер: Точечный" in text
    # точный join (перенос строки, а не другой разделитель)
    assert text == "• Имитация плёнки: ACROS\n• Экспозамер: Точечный"


def test_signed_label_value_branches():
    # ветка label in (...): Резкость, Шумоподавление, EV, FX Синий
    assert cs._format_label_value("sharpness", 2) == "Резкость: +2"
    assert cs._format_label_value("high_iso_nr", -4) == \
        "Шумоподавление при высоком ISO: -4"
    assert cs._format_label_value("ev", -1) == "Компенсация экспозиции (EV): -1"
    assert cs._format_label_value("fx_blue", 1) == "Хром-эффект FX Синий: +1"
    # Цветной хром-эффект — strength-шкала
    assert cs._format_label_value("color_chrome", 2) == \
        "Цветной хром-эффект: Сильный"
    assert cs._format_label_value("color_chrome", "Слабый") == \
        "Цветной хром-эффект: Слабый"
    # текст в этой ветке (не число) проходит как есть
    assert cs._format_label_value("sharpness", "soft") == "Резкость: soft"
    # положительные значения — знак «+» отличим от str() (для попадания в ветку)
    assert cs._format_label_value("color_shift_type", 2) == "Цвет: +2"
    assert cs._format_label_value("high_iso_nr", 4) == \
        "Шумоподавление при высоком ISO: +4"
    assert cs._format_label_value("ev", 3) == "Компенсация экспозиции (EV): +3"


def test_unknown_shoot_type_and_filters_fallback():
    # незнакомый приём съёмки → passthrough исходного значения
    assert cs._format_label_value("type_of_shoot", "psychedelic") == \
        "Приём съёмки: psychedelic"
    assert cs._format_label_value(
        "type_of_shoot", ["psychedelic"],
    ) == "Приём съёмки: psychedelic"
    # незнакомые фильтры → passthrough
    assert cs._format_label_value("фильтр", "vignette") == \
        "Дополнительный фильтр: vignette"
    assert cs._format_label_value("bw_filter", "orange") == "ЧБ-фильтр: orange"


def test_number_list_variants():
    # пустой список → пусто
    assert cs._format_label_value("iso", []) == "ISO: "
    # один элемент — без разделителя
    assert cs._format_label_value("iso", [100]) == "ISO: +100"
    # несколько элементов — разделитель " / "
    assert cs._format_label_value("iso", [100, 200, -3]) == \
        "ISO: +100 / +200 / -3"
    # не-числа в списке проходят через str()
    assert cs._format_label_value("iso", ["auto"]) == "ISO: auto"


def test_camera_setup_skips_empty_after_valid():
    # пустое значение ПОСЛЕ валидного не должно прерывать цикл (continue, а не break)
    setup = {"Имитация плёнки": "ACROS", "Цвет": "", "Экспозамер": "Точечный"}
    text = cs.format_camera_setup(setup)
    assert "Имитация плёнки: ACROS" in text
    assert "Экспозамер: Точечный" in text


# ─── негативные сценарии ───

def test_string_setup_passthrough():
    assert cs.format_camera_setup("ACROS, R+9 B-9") == "ACROS, R+9 B-9"


def test_none_and_other_types():
    assert cs.format_camera_setup(None) == ""
    assert cs.format_camera_setup(42) == ""
    assert cs.format_camera_setup([]) == ""


def test_empty_dict_and_none_values_skipped():
    assert cs.format_camera_setup({}) == ""
    setup = {"Имитация плёнки": None, "Цвет": ""}
    assert cs.format_camera_setup(setup) == ""


# ─── незнакомый ключ остаётся, но не ломает вывод ───

def test_unknown_key_kept_as_is():
    setup = {"some_new_field": "значение"}
    text = cs.format_camera_setup(setup)
    assert "• some_new_field: значение" in text


def test_label_value_non_scalar_dict():
    text = cs._format_label_value("custom", {"a": 1, "b": 2})
    assert "custom: a: 1; b: 2" in text
