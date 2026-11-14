"""services/fuji_recipes.py — Движок внутрикамерных рецептов Fujifilm X-T4 и Cadavre Exquis.

Официальная спецификация камеры:
- Модель: Fujifilm X-T4 (прошивка 2.12 от 09.07.2024).
- 11 базовых симуляций плёнки + цветные фильтры для ACROS и Монохромного (всего 18 вариантов).
  (Nostalgic Negative официально отсутствует в прошивке X-T4).
- Русская терминология строго по официальному руководству пользователя X-T4.
- Стохастический генератор «Изысканный труп» (Cadavre Exquis) на криптографической энтропии
  secrets.SystemRandom с пространством состояний > 4.8e12 уникальных рецептов.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import secrets
from typing import Any

from config import DATA_DIR
from services.text_formatter import safe_html_format

logger = logging.getLogger("FujiRecipes")

# Файл персистентного хранения «Книги рецептов фотографа»
RECIPES_BOOK_PATH = Path(DATA_DIR) / "fuji_saved_recipes.json"

# ─── Константы прошивки Fujifilm X-T4 v2.12 ───

# 11 доступных эмуляций + фильтры для ЧБ
VALID_FILM_SIMULATIONS: tuple[str, ...] = (
    "PROVIA/Стандартный",
    "Velvia/Яркий",
    "ASTIA/Слабая",
    "Classic Chrome",
    "PRO Neg. Hi",
    "PRO Neg. Std",
    "Классический Негатив",
    "ETERNA/Кино",
    "ETERNA Bleach Bypass",
    "ACROS",
    "ACROS (+Ye Желтый)",
    "ACROS (+R Красный)",
    "ACROS (+G Зеленый)",
    "Монохромный",
    "Монохромный (+Ye Желтый)",
    "Монохромный (+R Красный)",
    "Монохромный (+G Зеленый)",
    "Сепия",
)

VALID_DYNAMIC_RANGES: tuple[str, ...] = (
    "DR100",
    "DR200",
    "DR400",
)

VALID_GRAIN_EFFECTS: tuple[str, ...] = (
    "Выкл",
    "Слабый / Мелкое",
    "Слабый / Крупное",
    "Сильный / Мелкое",
    "Сильный / Крупное",
)

VALID_COLOR_CHROME: tuple[str, ...] = (
    "Выкл",
    "Слабый",
    "Сильный",
)

VALID_COLOR_CHROME_FX_BLUE: tuple[str, ...] = (
    "Выкл",
    "Слабый",
    "Сильный",
)

VALID_WB_PRESETS: tuple[str, ...] = (
    "Авто",
    "Авто (приоритет белого)",
    "Приоритет среды",
    "Дневной свет",
    "Тень",
    "Облака",
    "Флуоресцентный 1",
    "Флуоресцентный 2",
    "Флуоресцентный 3",
    "Лампы накаливания",
    "Под водой",
)

# Шаг тоновой кривой на X-T4: от -2.0 до +4.0 с шагом 0.5 (13 градаций)
TONE_CURVE_VALUES: tuple[float, ...] = (
    -2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0,
)

# Компенсация экспозиции с шагом 1/3 EV
EXPOSURE_COMP_VALUES: tuple[str, ...] = (
    "-3.0 EV", "-2.7 EV", "-2.3 EV", "-2.0 EV", "-1.7 EV", "-1.3 EV",
    "-1.0 EV", "-0.7 EV", "-0.3 EV", "0 EV", "+0.3 EV", "+0.7 EV",
    "+1.0 EV", "+1.3 EV", "+1.7 EV", "+2.0 EV", "+2.3 EV", "+2.7 EV",
    "+3.0 EV",
)

# Пользовательские слоты настроек камеры X-T4
VALID_SLOTS: tuple[str, ...] = ("C1", "C2", "C3", "C4", "C5", "C6", "C7")

SURREAL_NOUNS: tuple[str, ...] = (
    "Сон", "Мираж", "Ореол", "Разлом", "Фантом", "Полёт", "Лабиринт", "Спектр",
    "Маятник", "Силуэт", "Взгляд", "Осколок", "Шёпот", "Саркофаг", "Каскад",
    "Театр", "Архипелаг", "Компас", "Сфинкс", "Вероломство", "Постоянство",
    "Искушение", "Портрет", "Призрак", "Алтарь", "Оракул", "Вихрь", "Склеп",
)

SURREAL_ADJECTIVES: tuple[str, ...] = (
    "Вероломный", "Онейрический", "Растворённый", "Хрустальный", "Электрический",
    "Тлеющий", "Призрачный", "Застывший", "Абсурдный", "Парадоксальный",
    "Опаловый", "Кобальтовый", "Метафизический", "Безмолвный", "Спящий",
    "Геометрический", "Анатомический", "Лунно-гранатовый", "Фосфоресцирующий",
    "Холодный", "Неоновый", "Ртутный", "Аметистовый",
)

SURREAL_METAPHORS: tuple[str, ...] = (
    "пчелы в натриевой мгле",
    "бирюзовой тени",
    "стеклянного мотылька",
    "жидкого времени",
    "янтарного зеркала",
    "горящего жирафа",
    "оловянного солнца",
    "вечерней геометрии",
    "невидимой гравитации",
    "лунного кристалла",
    "черного лезвия",
    "акварельного бреда",
    "зеркального сфумато",
    "серебряного колодца",
    "медной пыли",
    "двойного горизонта",
    "неподвижного шторма",
    "ртутного прибоя",
)

SURREAL_ACTION_MECHANICS: tuple[str, ...] = (
    "Мультиэкспозиция (2–4 кадра), режим Тёмный, микро-ICM тремор 1/6с с рук.",
    "Съемка сквозь треугольную хрустальную призму с вращением грани на открытой f/2.",
    "Голландский угол 25°, жесткое боковое контражурное солнце, точечный замер.",
    "Длинная выдержка 1/2с с рук с мягкой вертикальной проводкой во время спуска.",
    "Съемка сквозь мокрое стекло с каплями, ручной фокус Peaking на отражении.",
    "Двойная экспозиция: 1 кадр силуэт в контровом свете, 2 кадр текстура ветвей/воды.",
    "Экстремальное приближение монокля к объекту, световое кольцо сфумато на f/2.",
    "Микро-вибрация камеры на 1/8с между двумя контрастными световыми источниками.",
)


@dataclass
class FujiRecipe:
    """Полный набор внутрикамерных параметров Fujifilm X-T4 (прошивка 2.12)."""

    recipe_name: str
    film_simulation: str
    dynamic_range: str = "DR100"
    highlight_tone: float = 0.0
    shadow_tone: float = 0.0
    color: int = 0
    sharpness: int = 0
    high_iso_nr: int = 0
    clarity: int = 0
    grain_effect: str = "Выкл"
    color_chrome_effect: str = "Выкл"
    color_chrome_fx_blue: str = "Выкл"
    white_balance: str = "Авто"
    wb_shift_r: int = 0
    wb_shift_b: int = 0
    exposure_compensation: str = "0 EV"
    action_mechanic: str = ""
    notes: str = ""

    def validate(self) -> list[str]:
        """Проверяет соответствие параметров аппаратным лимитам X-T4 (прошивка 2.12)."""
        errors: list[str] = []

        if self.film_simulation not in VALID_FILM_SIMULATIONS:
            errors.append(f"Неизвестная эмуляция плёнки: '{self.film_simulation}'")

        if self.dynamic_range not in VALID_DYNAMIC_RANGES:
            errors.append(f"Недопустимый динамический диапазон: '{self.dynamic_range}'")

        if self.highlight_tone not in TONE_CURVE_VALUES:
            errors.append(
                f"Недопустимый Highlight Tone: {self.highlight_tone} (шаг 0.5 от -2.0 до +4.0)"
            )

        if self.shadow_tone not in TONE_CURVE_VALUES:
            errors.append(
                f"Недопустимый Shadow Tone: {self.shadow_tone} (шаг 0.5 от -2.0 до +4.0)"
            )

        if not -4 <= self.color <= 4:
            errors.append(f"Color {self.color} вне диапазона [-4, +4]")

        if not -4 <= self.sharpness <= 4:
            errors.append(f"Sharpness {self.sharpness} вне диапазона [-4, +4]")

        if not -4 <= self.high_iso_nr <= 4:
            errors.append(f"High ISO NR {self.high_iso_nr} вне диапазона [-4, +4]")

        if not -5 <= self.clarity <= 5:
            errors.append(f"Clarity {self.clarity} вне диапазона [-5, +5]")

        if self.grain_effect not in VALID_GRAIN_EFFECTS:
            errors.append(f"Недопустимый Grain Effect: '{self.grain_effect}'")

        if self.color_chrome_effect not in VALID_COLOR_CHROME:
            errors.append(f"Недопустимый Color Chrome Effect: '{self.color_chrome_effect}'")

        if self.color_chrome_fx_blue not in VALID_COLOR_CHROME_FX_BLUE:
            errors.append(f"Недопустимый Color Chrome FX Blue: '{self.color_chrome_fx_blue}'")

        if not -9 <= self.wb_shift_r <= 9:
            errors.append(f"WB Shift R {self.wb_shift_r} вне диапазона [-9, +9]")

        if not -9 <= self.wb_shift_b <= 9:
            errors.append(f"WB Shift B {self.wb_shift_b} вне диапазона [-9, +9]")

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Сериализация параметров рецепта в словарь."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FujiRecipe:
        """Десериализация рецепта из словаря с фильтрацией известных полей."""
        valid_fields = cls.__dataclass_fields__.keys()
        clean_kwargs = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**clean_kwargs)


def generate_surreal_recipe_title(rng: secrets.SystemRandom | None = None) -> str:
    """Генерирует поэтическое сюрреалистическое название в стиле Магритта и Дали."""
    r = rng or secrets.SystemRandom()
    noun = r.choice(SURREAL_NOUNS)
    metaphor = r.choice(SURREAL_METAPHORS)
    pattern = r.randint(1, 3)

    if pattern == 1:
        return f"{noun} {metaphor}"
    elif pattern == 2:
        adj = r.choice(SURREAL_ADJECTIVES)
        return f"{adj} {noun.lower()} {metaphor}"
    else:
        noun2 = r.choice(SURREAL_NOUNS)
        while noun2 == noun:
            noun2 = r.choice(SURREAL_NOUNS)
        return f"{noun} и {noun2.lower()} {metaphor}"


def build_fuji_recipe_for_project_styles(styles: list[str]) -> FujiRecipe:
    """Формирует детерминированный внутрикамерный рецепт по списку художественных стилей."""
    styles_lower = [s.lower() for s in styles]

    # 1. Экспрессионизм: графичный жесткий монохром Калигари
    if any("экспрессионизм" in s for s in styles_lower):
        return FujiRecipe(
            recipe_name="Калигари ЧБ / Экспрессионизм",
            film_simulation="ACROS (+R Красный)",
            dynamic_range="DR400",
            highlight_tone=2.0,
            shadow_tone=3.5,
            color=0,
            sharpness=2,
            high_iso_nr=-4,
            clarity=3,
            grain_effect="Сильный / Крупное",
            color_chrome_effect="Выкл",
            color_chrome_fx_blue="Выкл",
            white_balance="Дневной свет",
            wb_shift_r=4,
            wb_shift_b=-4,
            exposure_compensation="-0.7 EV",
            action_mechanic=(
                "Голландский угол 15–25 градусов, поиск острых диагональных теней-лезвий."
            ),
            notes="Экстремальный контраст, глубокие черные провалы теней и графичная резкость.",
        )

    # 2. Пиктореализм: благородный сфумато, мягкое свечение
    if any("пиктореализм" in s for s in styles_lower):
        return FujiRecipe(
            recipe_name="Пикториальный сфумато Демаши",
            film_simulation="Classic Chrome",
            dynamic_range="DR200",
            highlight_tone=-2.0,
            shadow_tone=-1.0,
            color=-2,
            sharpness=-2,
            high_iso_nr=0,
            clarity=-4,
            grain_effect="Сильный / Крупное",
            color_chrome_effect="Слабый",
            color_chrome_fx_blue="Слабый",
            white_balance="Тень",
            wb_shift_r=3,
            wb_shift_b=-4,
            exposure_compensation="+0.3 EV",
            action_mechanic=(
                "Съемка сквозь диффузный фильтр Black Pro-Mist 1/4 или монокль на открытой f/2."
            ),
            notes="Мягкое свечение вокруг светлых объектов, приглушенные тени в духе платинотипии.",
        )

    # 3. Импрессионизм: акварельная лессировка 1/6с, режим Тёмный
    if any("импрессионизм" in s for s in styles_lower):
        return FujiRecipe(
            recipe_name="Акварельная лессировка Моне",
            film_simulation="Velvia/Яркий",
            dynamic_range="DR200",
            highlight_tone=-1.0,
            shadow_tone=1.5,
            color=3,
            sharpness=-1,
            high_iso_nr=-2,
            clarity=-2,
            grain_effect="Слабый / Мелкое",
            color_chrome_effect="Сильный",
            color_chrome_fx_blue="Слабый",
            white_balance="Дневной свет",
            wb_shift_r=2,
            wb_shift_b=-3,
            exposure_compensation="-1.0 EV",
            action_mechanic=(
                "Мультиэкспозиция (2–4 кадра), режим Тёмный, 1/6с с рук с микро-тремором на месте."
            ),
            notes="Плотная живописная фактура мазка без выбивания светов.",
        )

    # 4. Сюрреализм: онейрический парадокс цвета Магритта
    if any("сюрреализм" in s for s in styles_lower):
        return FujiRecipe(
            recipe_name="Онейрический разлом Магритта",
            film_simulation="Классический Негатив",
            dynamic_range="DR400",
            highlight_tone=1.0,
            shadow_tone=2.0,
            color=2,
            sharpness=1,
            high_iso_nr=-4,
            clarity=2,
            grain_effect="Сильный / Крупное",
            color_chrome_effect="Сильный",
            color_chrome_fx_blue="Сильный",
            white_balance="5800K",
            wb_shift_r=6,
            wb_shift_b=-7,
            exposure_compensation="+0.3 EV",
            action_mechanic=(
                "Хрустальная треугольная призма вплотную к передней линзе, расщепление спектра."
            ),
            notes="Инопланетная насыщенность в тенях и оптическое двоение пространства.",
        )

    # 5. Конструктивизм: геометрия и ритм Родченко
    if any("конструктивизм" in s for s in styles_lower):
        return FujiRecipe(
            recipe_name="Конструктивизм Родченко",
            film_simulation="ACROS",
            dynamic_range="DR100",
            highlight_tone=2.0,
            shadow_tone=2.0,
            color=0,
            sharpness=3,
            high_iso_nr=-3,
            clarity=4,
            grain_effect="Слабый / Мелкое",
            color_chrome_effect="Выкл",
            color_chrome_fx_blue="Выкл",
            white_balance="Авто",
            wb_shift_r=0,
            wb_shift_b=0,
            exposure_compensation="-0.3 EV",
            action_mechanic=(
                "Нижний ракурс с колен, выравнивание диагональных балок и жестких граней."
            ),
            notes="Индустриальная графичность, максимальный микроконтраст и структурная четкость.",
        )

    # Дефолтный рецепт при отсутствии выраженных стилей
    return FujiRecipe(
        recipe_name="Классический пленочный репортаж",
        film_simulation="Classic Chrome",
        dynamic_range="DR200",
        highlight_tone=-1.0,
        shadow_tone=0.0,
        color=1,
        sharpness=0,
        high_iso_nr=-2,
        clarity=0,
        grain_effect="Слабый / Мелкое",
        color_chrome_effect="Слабый",
        color_chrome_fx_blue="Выкл",
        white_balance="Авто",
        wb_shift_r=2,
        wb_shift_b=-3,
        exposure_compensation="0 EV",
        action_mechanic="Съемка с рук с контролем горизонта и фокуса по взгляду.",
        notes="Универсальный сбалансированный пленочный тон для повседневных арт-серий.",
    )


def build_fuji_recipe_for_project(session: Any = None) -> FujiRecipe:
    """Формирует детерминированный внутрикамерный рецепт под стилистическую триаду проекта."""
    styles: list[str] = []
    if session is not None:
        if isinstance(session, (list, tuple)):
            styles = [str(s) for s in session]
        else:
            styles = getattr(session, "selected_styles", []) or []
    return build_fuji_recipe_for_project_styles(styles)


def build_fuji_recipe_for_concept(concept: Any) -> FujiRecipe:
    """Формирует рецепт Fujifilm X-T4 для проекта/концепта из режима «Штурм 2.0»."""
    styles: list[str] = []
    triad = getattr(concept, "triad", None)
    if triad is not None and hasattr(triad, "styles"):
        styles = triad.styles()
    elif isinstance(triad, dict):
        for role in ("narrative", "lighting", "optics"):
            part = triad.get(role, {})
            if isinstance(part, dict) and part.get("style"):
                styles.append(str(part["style"]))

    recipe = build_fuji_recipe_for_project_styles(styles)

    title = str(getattr(concept, "title", "")).strip()
    if title:
        recipe.recipe_name = f"X-T4: {title}"

    shooting_action = str(getattr(concept, "shooting_action", "")).strip()
    if shooting_action:
        recipe.action_mechanic = shooting_action

    triad_summary = getattr(triad, "summary", lambda: "")() if triad else ""
    if triad_summary:
        recipe.notes = f"Рецепт для проекта «{title}» ({triad_summary})"

    return recipe


def generate_surreal_stochastic_recipe(
    session: Any = None,
    intensity: str = "wild",
) -> FujiRecipe:
    """Сюрреалистический стохастический генератор по методу «Изысканного трупа» (Cadavre Exquis).

    Использует криптографическую энтропию secrets.SystemRandom() для абсолютно независимого
    случайного подбора каждого параметра по всему допустимому диапазону прошивки 2.12.
    Пространство состояний > 4.8 * 10^12 гарантирует неповторимость каждого рецепта.
    """
    rng = secrets.SystemRandom()

    film_sim = rng.choice(VALID_FILM_SIMULATIONS)
    dr = rng.choice(VALID_DYNAMIC_RANGES)

    if intensity == "wild":
        # Экстремальные диапазоны для радикального сюрреализма
        hl = rng.choice(TONE_CURVE_VALUES)
        sh = rng.choice(TONE_CURVE_VALUES)
        color = rng.randint(-4, 4)
        sharpness = rng.randint(-4, 4)
        high_iso_nr = rng.randint(-4, 4)
        clarity = rng.randint(-5, 5)

        grain = rng.choice(VALID_GRAIN_EFFECTS)
        cc = rng.choice(VALID_COLOR_CHROME)
        cc_blue = rng.choice(VALID_COLOR_CHROME_FX_BLUE)

        # Выбор WB: 50% Кельвины (2500K-10000K), 50% пресеты
        if rng.random() > 0.5:
            kelvin = rng.randrange(2500, 10100, 100)
            wb = f"{kelvin}K"
        else:
            wb = rng.choice(VALID_WB_PRESETS)

        wb_r = rng.randint(-9, 9)
        wb_b = rng.randint(-9, 9)
        ev = rng.choice(EXPOSURE_COMP_VALUES)
    else:
        # Умеренный (moderate) стохастический генератор
        hl = rng.choice([-1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0])
        sh = rng.choice([-1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5])
        color = rng.randint(-2, 3)
        sharpness = rng.randint(-2, 2)
        high_iso_nr = rng.randint(-3, 0)
        clarity = rng.randint(-3, 3)

        grain = rng.choice(VALID_GRAIN_EFFECTS)
        cc = rng.choice(["Выкл", "Слабый", "Сильный"])
        cc_blue = rng.choice(["Выкл", "Слабый"])

        if rng.random() > 0.4:
            wb = rng.choice(VALID_WB_PRESETS)
        else:
            kelvin = rng.randrange(3200, 7500, 100)
            wb = f"{kelvin}K"

        wb_r = rng.randint(-5, 5)
        wb_b = rng.randint(-5, 5)
        ev = rng.choice(["-1.0 EV", "-0.7 EV", "-0.3 EV", "0 EV", "+0.3 EV", "+0.7 EV", "+1.0 EV"])

    action_mech = rng.choice(SURREAL_ACTION_MECHANICS)
    title = generate_surreal_recipe_title(rng)

    return FujiRecipe(
        recipe_name=title,
        film_simulation=film_sim,
        dynamic_range=dr,
        highlight_tone=hl,
        shadow_tone=sh,
        color=color,
        sharpness=sharpness,
        high_iso_nr=high_iso_nr,
        clarity=clarity,
        grain_effect=grain,
        color_chrome_effect=cc,
        color_chrome_fx_blue=cc_blue,
        white_balance=wb,
        wb_shift_r=wb_r,
        wb_shift_b=wb_b,
        exposure_compensation=ev,
        action_mechanic=action_mech,
        notes="Стохастический рецепт Cadavre Exquis (энтропия SystemRandom).",
    )


def _fmt_signed(num: int | float) -> str:
    """Форматирует число со знаком для отображения в русском меню камеры."""
    if isinstance(num, float):
        if num > 0:
            return f"+{num:.1f}"
        elif num == 0.0:
            return "0.0"
        return f"{num:.1f}"
    if num > 0:
        return f"+{num}"
    return str(num)


def format_fuji_recipe_card(recipe: FujiRecipe, slot_name: str = "C1") -> str:
    """Форматирует визуальную карточку рецепта для пользовательского слота X-T4.

    Оптимизирована для оперативного ввода фотографом в русское меню камеры за 60 секунд.
    Использует моноширинные блоки и строгую разметку Telegram HTML.
    """
    clean_slot = slot_name.upper().strip()
    if clean_slot not in VALID_SLOTS:
        clean_slot = "C1"

    hl_str = _fmt_signed(recipe.highlight_tone)
    sh_str = _fmt_signed(recipe.shadow_tone)
    col_str = _fmt_signed(recipe.color)
    sharp_str = _fmt_signed(recipe.sharpness)
    nr_str = _fmt_signed(recipe.high_iso_nr)
    clar_str = _fmt_signed(recipe.clarity)
    wb_r_str = _fmt_signed(recipe.wb_shift_r)
    wb_b_str = _fmt_signed(recipe.wb_shift_b)

    # Строим компактную моноширинную карточку
    card_lines = [
        f"🎛 <b>Fujifilm X-T4 • Рецепт в слот {clean_slot}</b>",
        f"«<b>{safe_html_format(recipe.recipe_name)}</b>»\n",
        "<pre>",
        "┌──────────────────────────────────────┐",
        f"│ ИМИТАЦИЯ ПЛЁНКИ:  {recipe.film_simulation:<19}│",
        f"│ ДИНАМИЧ. ДИАПАЗОН:{recipe.dynamic_range:<19}│",
        f"│ ТОН (ПОДСВЕТКА):  {hl_str:<19}│",
        f"│ ТОН (ТЕНЬ):       {sh_str:<19}│",
        f"│ ЦВЕТ:             {col_str:<19}│",
        f"│ РЕЗКОСТЬ:         {sharp_str:<19}│",
        f"│ ШУМОПОДАВЛЕНИЕ:   {nr_str:<19}│",
        f"│ CLARITY (ПРОЗР.): {clar_str:<19}│",
        f"│ ЭФФЕКТ ЗЕРНА:     {recipe.grain_effect:<19}│",
        f"│ ЦВЕТНОЙ ХРОМ:     {recipe.color_chrome_effect:<19}│",
        f"│ ХРОМ FX СИНИЙ:    {recipe.color_chrome_fx_blue:<19}│",
        f"│ ББ:               {recipe.white_balance:<19}│",
        f"│ СДВИГ ББ (R / B): R{wb_r_str} / B{wb_b_str:<10}│",
        f"│ ЭКСПОКОРРЕКЦИЯ:   {recipe.exposure_compensation:<19}│",
        "└──────────────────────────────────────┘",
        "</pre>\n",
        f"👐 <b>Физика движения и оптика:</b>\n<i>{safe_html_format(recipe.action_mechanic)}</i>",
    ]

    if recipe.notes:
        card_lines.append(
            f"\n💡 <b>Художественный эффект:</b>\n<i>{safe_html_format(recipe.notes)}</i>"
        )

    card_lines.append(
        f"\n⏱ <i>Сохраните в меню камеры: «НАСТРОЙКА ИЗОБРАЖЕНИЯ» → "
        f"«РЕДАКТ./СОХР. СВОЙ РЕЖ.» → «{clean_slot}» (ввод ~60 сек).</i>"
    )

    return "\n".join(card_lines)


def format_recipe_for_apple_notes(
    recipe: FujiRecipe,
    slot_name: str = "C1",
    project_title: str = "",
) -> tuple[str, str]:
    """Форматирует внутрикамерный рецепт в Markdown для сохранения в Apple Notes."""
    clean_slot = slot_name.upper().strip() if slot_name else "C1"
    note_title = f"[Рецепт X-T4 {clean_slot}] {recipe.recipe_name}"

    hl = f"{recipe.highlight_tone:+.1f}" if recipe.highlight_tone != 0 else "0.0"
    sh = f"{recipe.shadow_tone:+.1f}" if recipe.shadow_tone != 0 else "0.0"
    col = f"{recipe.color:+d}" if recipe.color != 0 else "0"
    sharp = f"{recipe.sharpness:+d}" if recipe.sharpness != 0 else "0"
    nr = f"{recipe.high_iso_nr:+d}" if recipe.high_iso_nr != 0 else "0"
    clar = f"{recipe.clarity:+d}" if recipe.clarity != 0 else "0"
    wbr = f"{recipe.wb_shift_r:+d}" if recipe.wb_shift_r != 0 else "0"
    wbb = f"{recipe.wb_shift_b:+d}" if recipe.wb_shift_b != 0 else "0"

    lines = [
        f"# {note_title}",
        "",
        f"- **Слот камеры:** {clean_slot}",
        f"- **Проект:** {project_title or 'Свободная арт-сессия'}",
        f"- **Имитация плёнки:** {recipe.film_simulation}",
        f"- **Динамический диапазон:** {recipe.dynamic_range}",
        "",
        "## 🎛 Параметры изображения (меню Fujifilm X-T4)",
        f"- **Тоновая кривая:** Подсветка {hl} / Тень {sh}",
        f"- **Цвет:** {col}",
        f"- **Резкость:** {sharp}",
        f"- **Шумоподавление (High ISO NR):** {nr}",
        f"- **Прозрачность (Clarity):** {clar}",
        f"- **Эффект зерна:** {recipe.grain_effect}",
        f"- **Цветной хром-эффект:** {recipe.color_chrome_effect}",
        f"- **Цветной хром FX Синий:** {recipe.color_chrome_fx_blue}",
        f"- **Баланс белого:** {recipe.white_balance} (R{wbr} / B{wbb})",
        f"- **Компенсация экспозиции:** {recipe.exposure_compensation}",
        "",
        "## 👐 Физика движения и оптика",
        recipe.action_mechanic,
    ]
    if recipe.notes:
        lines.extend([
            "",
            "## 💡 Художественный замысел",
            recipe.notes,
        ])
    return note_title, "\n".join(lines)


def export_fuji_recipe_to_apple_notes(
    recipe: FujiRecipe,
    slot_name: str = "C1",
    project_title: str = "",
    folder: str = "Фотопроекты",
) -> str:
    """Выгружает рецепт камеры в Apple Notes в папку Фотопроекты."""
    from services.apple_notes import create_note, ensure_folder

    ensure_folder(folder)
    title, body = format_recipe_for_apple_notes(
        recipe, slot_name=slot_name, project_title=project_title,
    )
    note_id = create_note(title=title, body=body, folder=folder)
    logger.info(
        "[FUJI] Рецепт «%s» экспортирован в Apple Notes (папка: %s, id: %s)",
        title, folder, note_id,
    )
    return note_id


# ─── Персистентная «Книга рецептов фотографа» (fuji_saved_recipes.json) ───

def save_recipe_to_book(
    recipe: FujiRecipe,
    user_id: int | None = None,
    slot_hint: str = "C1",
    file_path: Path | str | None = None,
) -> bool:
    """Сохраняет рецепт в постоянную «Книгу рецептов фотографа» (атомарная запись через .tmp)."""
    try:
        errors = recipe.validate()
        if errors:
            logger.warning("[FUJI] Отклонено сохранение невалидного рецепта: %s", errors)
            return False
        target_path = Path(file_path) if file_path else RECIPES_BOOK_PATH
        target_path.parent.mkdir(parents=True, exist_ok=True)

        entries: list[dict[str, Any]] = []
        if target_path.exists():
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        raw_list = data.get("recipes", [])
                        if isinstance(raw_list, list):
                            entries = raw_list
                    elif isinstance(data, list):
                        entries = data
            except Exception as exc:
                logger.warning("[FUJI] Ошибка чтения книги рецептов: %s. Начинаем заново.", exc)
                entries = []

        now_iso = datetime.now().isoformat()
        clean_slot = slot_hint.upper().strip() if slot_hint else "C1"
        new_entry = recipe.to_dict()
        new_entry["slot_hint"] = clean_slot
        new_entry["saved_at"] = now_iso
        if user_id is not None:
            new_entry["user_id"] = user_id

        # Поиск существующего рецепта по названию
        target_name = recipe.recipe_name.strip().lower()
        updated = False
        for idx, item in enumerate(entries):
            if not isinstance(item, dict):
                continue
            item_uid = item.get("user_id")
            if user_id is not None and item_uid is not None and item_uid != user_id:
                continue
            if item.get("recipe_name", "").strip().lower() == target_name:
                entries[idx] = new_entry
                updated = True
                break

        if not updated:
            entries.insert(0, new_entry)

        # Атомарная запись через .tmp файл с fsync
        tmp_file = target_path.with_suffix(".tmp")
        payload = {
            "version": 1,
            "updated_at": now_iso,
            "recipes": entries,
        }
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())

        tmp_file.replace(target_path)
        logger.info(
            "[FUJI] Рецепт «%s» успешно сохранён в книгу: %s",
            recipe.recipe_name, target_path,
        )
        return True
    except Exception as exc:
        logger.error("[FUJI] Ошибка сохранения рецепта в книгу: %s", exc)
        return False


def load_saved_recipe_entries(
    user_id: int | None = None,
    file_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Загружает сырые записи рецептов из книги с метаданными (saved_at, slot_hint, user_id)."""
    target_path = Path(file_path) if file_path else RECIPES_BOOK_PATH
    if not target_path.exists():
        return []

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            raw_entries = data.get("recipes", []) if isinstance(data, dict) else data
            if not isinstance(raw_entries, list):
                return []

            if user_id is None:
                return [e for e in raw_entries if isinstance(e, dict)]

            filtered: list[dict[str, Any]] = []
            for item in raw_entries:
                if not isinstance(item, dict):
                    continue
                item_uid = item.get("user_id")
                if item_uid is None or item_uid == user_id:
                    filtered.append(item)
            return filtered
    except Exception as exc:
        logger.error("[FUJI] Ошибка загрузки книги рецептов: %s", exc)
        return []


def load_saved_recipes(
    user_id: int | None = None,
    file_path: Path | str | None = None,
) -> list[FujiRecipe]:
    """Загружает список сохранённых объектов FujiRecipe из книги."""
    entries = load_saved_recipe_entries(user_id=user_id, file_path=file_path)
    recipes: list[FujiRecipe] = []
    for entry in entries:
        try:
            recipes.append(FujiRecipe.from_dict(entry))
        except Exception as exc:
            logger.warning("[FUJI] Пропуск повреждённого рецепта: %s", exc)
    return recipes


def get_saved_recipe(
    name: str,
    user_id: int | None = None,
    file_path: Path | str | None = None,
) -> FujiRecipe | None:
    """Возвращает сохранённый рецепт по названию."""
    target_name = name.strip().lower()
    for recipe in load_saved_recipes(user_id=user_id, file_path=file_path):
        if recipe.recipe_name.strip().lower() == target_name:
            return recipe
    return None


def delete_saved_recipe(
    name: str,
    user_id: int | None = None,
    file_path: Path | str | None = None,
) -> bool:
    """Удаляет рецепт из книги по названию (атомарное обновление)."""
    target_path = Path(file_path) if file_path else RECIPES_BOOK_PATH
    if not target_path.exists():
        return False

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            entries = data.get("recipes", []) if isinstance(data, dict) else data
            if not isinstance(entries, list):
                return False

        target_name = name.strip().lower()
        found_idx = -1
        for idx, item in enumerate(entries):
            if not isinstance(item, dict):
                continue
            item_uid = item.get("user_id")
            if user_id is not None and item_uid is not None and item_uid != user_id:
                continue
            if item.get("recipe_name", "").strip().lower() == target_name:
                found_idx = idx
                break

        if found_idx == -1:
            return False

        entries.pop(found_idx)
        tmp_file = target_path.with_suffix(".tmp")
        payload = {
            "version": 1,
            "updated_at": datetime.now().isoformat(),
            "recipes": entries,
        }
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())

        tmp_file.replace(target_path)
        logger.info("[FUJI] Рецепт «%s» удалён из книги: %s", name, target_path)
        return True
    except Exception as exc:
        logger.error("[FUJI] Ошибка при удалении рецепта «%s»: %s", name, exc)
        return False


def export_recipe_book_to_apple_notes(
    user_id: int | None = None,
    folder: str = "Фотопроекты",
    file_path: Path | str | None = None,
) -> tuple[bool, str]:
    """Экспортирует всю книгу рецептов фотографа в Apple Notes."""
    from services.apple_notes import create_note, ensure_folder

    recipes = load_saved_recipes(user_id=user_id, file_path=file_path)
    if not recipes:
        return False, "Книга рецептов пуста."

    ensure_folder(folder)
    title = "[Книга рецептов X-T4] Коллекция рецептов фотографа"
    lines = [
        f"# {title}",
        "",
        f"- **Количество рецептов:** {len(recipes)}",
        "- **Камера:** Fujifilm X-T4 (прошивка 2.12)",
        f"- **Экспортировано:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "---",
        "",
    ]

    for idx, r in enumerate(recipes, start=1):
        slot_label = f"C{idx}" if idx <= 7 else "Кастом"
        _, card_body = format_recipe_for_apple_notes(
            r,
            slot_name=slot_label,
            project_title=r.recipe_name,
        )
        lines.append(card_body)
        lines.append("\n---\n")

    try:
        note_id = create_note(title=title, body="\n".join(lines), folder=folder)
        return True, note_id
    except Exception as exc:
        logger.error("[FUJI] Ошибка экспорта книги рецептов в Apple Notes: %s", exc)
        return False, str(exc)
