"""services/photographer_gear.py — арсенал фотографа, обогащение и ремикс-движок."""

import asyncio
import html
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from config import DATA_DIR
from services.json_parser import safe_parse_llm_json

logger = logging.getLogger("PhotographerGear")

GEAR_FILE_PATH = Path(DATA_DIR) / "photographer_gear.json"

CATEGORIES = ("camera", "lens", "filter", "lighting", "accessory")

CATEGORY_NAMES_RU = {
    "camera": "Камера",
    "lens": "Объектив",
    "filter": "Фильтр",
    "lighting": "Свет",
    "accessory": "Аксессуар",
}


@dataclass
class GearItem:
    name: str
    category: str = "accessory"
    optical_traits: str = ""
    what_to_do: str = ""
    expected_result: str = ""
    best_styles: list[str] = field(default_factory=list)
    notes: str = ""
    added_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GearItem":
        return cls(
            name=data.get("name", "").strip(),
            category=data.get("category", "accessory").strip().lower(),
            optical_traits=data.get("optical_traits", "").strip(),
            what_to_do=data.get("what_to_do", "").strip(),
            expected_result=data.get("expected_result", "").strip(),
            best_styles=[str(s).strip() for s in data.get("best_styles", []) if s],
            notes=data.get("notes", "").strip(),
            added_at=float(data.get("added_at", time.time())),
        )


@dataclass
class GearProfile:
    cameras: list[GearItem] = field(default_factory=list)
    lenses: list[GearItem] = field(default_factory=list)
    filters: list[GearItem] = field(default_factory=list)
    lighting: list[GearItem] = field(default_factory=list)
    accessories: list[GearItem] = field(default_factory=list)

    def all_items(self) -> list[GearItem]:
        return (
            self.cameras
            + self.lenses
            + self.filters
            + self.lighting
            + self.accessories
        )

    def add_item(self, item: GearItem) -> None:
        cat = item.category.lower()
        if cat == "camera":
            self.cameras.append(item)
        elif cat == "lens":
            self.lenses.append(item)
        elif cat == "filter":
            self.filters.append(item)
        elif cat == "lighting":
            self.lighting.append(item)
        else:
            self.accessories.append(item)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cameras": [i.to_dict() for i in self.cameras],
            "lenses": [i.to_dict() for i in self.lenses],
            "filters": [i.to_dict() for i in self.filters],
            "lighting": [i.to_dict() for i in self.lighting],
            "accessories": [i.to_dict() for i in self.accessories],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GearProfile":
        profile = cls()
        for cat in ("cameras", "lenses", "filters", "lighting", "accessories"):
            items = [GearItem.from_dict(d) for d in data.get(cat, []) if isinstance(d, dict)]
            setattr(profile, cat, items)
        return profile


def categorize_gear_name(name: str) -> str:
    """Определяет категорию по названию техники."""
    lower = name.lower()
    if any(k in lower for k in (
        "фильтр", "filtr", "filter", "mist", "nd", "cpl", "полярик", "диффуз",
        "линза с отверстием"
    )):
        return "filter"
    if any(k in lower for k in (
        "вспышк", "софтбокс", "фонар", "светильник", "godox", "свет", "flash", "strobe",
        "v1f", "v1"
    )):
        return "lighting"
    if any(k in lower for k in (
        "призма", "штатив", "зеркало", "отражатель", "тросик", "тканей", "ткани",
        "фатин", "органза", "шелк"
    )):
        return "accessory"
    if any(k in lower for k in (
        "объектив", "линз", "стекло", "монокль", "helios", "гелиос", "fujinon", "xf",
        "pentacon", "kamlan", "юпитер", "индустар", "zenit", "rokinon", "samyang",
        "ttartisan", "7artisans", "sigma", "tamron", "mm", "f/"
    )):
        return "lens"
    if any(k in lower for k in (
        "камера", "тушка", "фотокамера", "fuji", "fujifilm", "canon", "nikon",
        "sony", "leica", "lumix"
    )):
        return "camera"
    return "accessory"


def is_gear_description(text: str) -> bool:
    """Проверяет, содержит ли текст описание фотооборудования или список техники."""
    if not text or len(text.strip()) < 5:
        return False
    lower = text.lower()
    gear_markers = (
        "фотокамера", "объектив", "светофильтр", "свотофильтр", "фильтр",
        "фотовспышка", "вспышк", "штатив", "линза с отверстием",
        "fujifilm", "fujinon", "pentacon", "kamlan", "монокль", "godox",
        "black pro-mist", "nd-filtr", "nd-filter", "2-400nd"
    )
    matches = sum(1 for m in gear_markers if m in lower)
    return matches >= 2 or any(
        lower.startswith(prefix) for prefix in ("фотокамера", "камера:", "объективы:", "арсенал:")
    )


def parse_gear_description(raw: str) -> list[dict[str, Any]]:
    """Парсит свободный текст со списком фотооборудования на отдельные предметы и категории."""
    items: list[dict[str, Any]] = []
    lines = [ln.strip() for ln in raw.strip().splitlines() if ln.strip()]

    for line in lines:
        subparts = re.split(
            r"(?<=\.)\s*(?=(?:объектив|камер|фильтр|свет|вспышк|аксессуар|"
            r"свотофильтр|светофильтр|фотокамер))",
            line,
            flags=re.IGNORECASE,
        )
        for sub in subparts:
            sub = sub.strip().rstrip(".")
            if not sub:
                continue

            m_header = re.match(
                r"^(фотокамера|камера|объективы|объектив|свотофильтр|светофильтр|"
                r"фильтры|фильтр|свет|вспышка|фотовспышка|аксессуары|аксессуар)"
                r"\s*[:\-]\s*(.*)$",
                sub,
                re.IGNORECASE,
            )
            if m_header:
                cat_hint = m_header.group(1).lower()
                content = m_header.group(2).strip()

                if re.search(r"(?:^|[,;])\s*\b\d+[\.\)]\s*", content):
                    pieces = re.split(r"(?:^|[,;])\s*\b\d+[\.\)]\s*", content)
                    for p in pieces:
                        p = p.strip().rstrip(",;.")
                        if not p:
                            continue
                        cat = (
                            "lens" if "объектив" in cat_hint
                            else ("camera" if "камер" in cat_hint else categorize_gear_name(p))
                        )
                        items.append({"name": p, "category": cat})
                else:
                    delim = ";" if ";" in content else ","
                    for p in content.split(delim):
                        p = p.strip().rstrip(",;.")
                        if not p:
                            continue
                        cat = (
                            categorize_gear_name(cat_hint)
                            if cat_hint else categorize_gear_name(p)
                        )
                        items.append({"name": p, "category": cat})
            else:
                # Проверка нумерованного списка без явного заголовка
                if re.search(r"(?:^|[,;])\s*\b\d+[\.\)]\s*", sub):
                    pieces = re.split(r"(?:^|[,;])\s*\b\d+[\.\)]\s*", sub)
                    for p in pieces:
                        p = p.strip().rstrip(",;.")
                        if p:
                            items.append({"name": p, "category": categorize_gear_name(p)})
                    continue

                # Проверка списка предметов через запятую (например, "Kamlan 50mm, Pentacon 29mm")
                if "," in sub:
                    pieces = [p.strip().rstrip(",;.") for p in sub.split(",") if p.strip()]
                    if len(pieces) >= 2 and all(
                        categorize_gear_name(p) in ("camera", "lens", "filter", "lighting")
                        for p in pieces
                    ):
                        for p in pieces:
                            items.append({"name": p, "category": categorize_gear_name(p)})
                        continue

                m_lead = re.match(r"^(?:фотокамера|камера)\s+(.+)$", sub, re.IGNORECASE)
                if m_lead:
                    items.append({"name": m_lead.group(1).strip(), "category": "camera"})
                else:
                    items.append({"name": sub, "category": categorize_gear_name(sub)})

    return items


EXPERT_OPTICS_KNOWLEDGE: dict[str, dict[str, Any]] = {
    "pentacon_reversed": {
        "pattern": r"pentacon.*(?:переверн|перевёрн|reverse)",
        "optical_traits": (
            "Экстремальные сферические аберрации, резкий фокусный спот строго "
            "по центру кадра и психоделический вихревой смаз фона (эффект туннеля)."
        ),
        "what_to_do": (
            "Центрированные портреты, макросъёмка мелких фактур на f/2.8, "
            "ловля контровых бликов сквозь ветви."
        ),
        "expected_result": (
            "Сновидческий живописный софт-фокус с выразительным вихревым боке "
            "и светящимися ореолами вокруг источников света."
        ),
        "best_styles": ["Сюрреализм", "Пиктореализм"],
        "notes": (
            "Фокусировка требует покачивания корпусом вперед-назад; "
            "наибольший эффект софта на f/2.8."
        ),
    },
    "pentacon": {
        "pattern": r"pentacon",
        "optical_traits": (
            "Винтажная немецкая резкость с мягким спадом к краям, сочный контраст, "
            "круглое пузырьковое боке в зоне нерезкости."
        ),
        "what_to_do": (
            "Стрит-съёмка, жанровые портреты на открытой диафрагме f/2.8, "
            "съёмка сквозь ветви или прозрачные преграды."
        ),
        "expected_result": (
            "Кинематографичная ретро-пластика, мягкая прорисовка полутонов "
            "и благородные аналоговые блики."
        ),
        "best_styles": ["Импрессионизм", "Пиктореализм"],
        "notes": (
            "Классическая оптическая схема Meyer-Optik Görlitz Orestegon; "
            "отличный микроконтраст."
        ),
    },
    "fujinon_18_55": {
        "pattern": r"(?:fujinon|xf).*(?:18-55|18-55mm)",
        "optical_traits": (
            "Высокая резкость по всему полю кадра, асферические элементы, покрытие Super EBC "
            "против паразитных засветок, оптический стабилизатор OIS."
        ),
        "what_to_do": (
            "Репортажная и пейзажная съёмка, съёмка с рук на длинных выдержках с микро-ICM, "
            "плавное зумирование в процессе экспонирования."
        ),
        "expected_result": (
            "Звенящая детализация, чистые микроконтрасты и безупречная передача фактур "
            "при устойчивой геометрии."
        ),
        "best_styles": ["Сюрреализм", "Экспрессионизм"],
        "notes": (
            "Линейный мотор LM обеспечивает бесшумную и быструю фокусировку; "
            "оптический стаб компенсирует до 3.5 стопов."
        ),
    },
    "kamlan_50": {
        "pattern": r"kamlan.*50",
        "optical_traits": (
            "Сверхсветосила f/1.1, экстремально малая глубина резкости (DOF), акварельное "
            "масляное размытие фона, мягкое свечение контуров на открытой диафрагме."
        ),
        "what_to_do": (
            "Ночная съёмка при слабом освещении (уличные фонари, свечи), глубокая изоляция "
            "объекта из темноты, съёмка в полумраке без вспышки."
        ),
        "expected_result": (
            "Масляный кинематографичный рисунок, гигантские круги нерезкости и завораживающий "
            "эффект световой лессировки."
        ),
        "best_styles": ["Импрессионизм", "Экспрессионизм"],
        "notes": (
            "На f/1.1 глубина резкости всего несколько миллиметров; "
            "для точной фокусировки рекомендуется Focus Peaking."
        ),
    },
    "monocle": {
        "pattern": r"монокль",
        "optical_traits": (
            "Однолинзовая оптическая схема: выраженные сферические и хроматические "
            "аберрации, сфумато, светящийся ореол вокруг ярких светов."
        ),
        "what_to_do": (
            "Пейзажи в тумане, съемка силуэтов против закатного солнца, контровой рассеянный "
            "свет сквозь стекло."
        ),
        "expected_result": (
            "Живописная акварельная дымка, эффект импрессионистической картины маслом, "
            "растворение резких техногенных границ."
        ),
        "best_styles": ["Пиктореализм", "Импрессионизм"],
        "notes": (
            "Светящийся ореол усиливается при ярком контровом свете; "
            "диафрагмирование снижает свечение."
        ),
    },
    "nd_var": {
        "pattern": r"(?:nd.*(?:2-400|filtr|filter)|k&f.*nd)",
        "optical_traits": (
            "Переменный фильтр нейтральной плотности (ND2–ND400, от 1 до 8.5 стопов экспозиции), "
            "плавная регулировка светопропускания."
        ),
        "what_to_do": (
            "Дневная съёмка на открытых диафрагмах (f/1.1–f/2.8) на ярком солнце, съёмка воды "
            "и облаков на выдержках 1–10 секунд, проводка ICM."
        ),
        "expected_result": (
            "Шелковистое размытие воды, динамические призрачные шлейфы людей в городе, "
            "живописный кинематографичный смаз."
        ),
        "best_styles": ["Сюрреализм", "Импрессионизм"],
        "notes": (
            "На предельных плотностях около ND400 на широком угле возможен X-эффект; "
            "рекомендуется работать в диапазоне до ND256."
        ),
    },
    "center_spot": {
        "pattern": r"(?:линза с отверстием|center.spot)",
        "optical_traits": (
            "Диафрагменная насадка: резкий незамутненный центр через сквозное отверстие "
            "и расфокусированное преломление краев через толщу стекла."
        ),
        "what_to_do": (
            "Портреты с фокусировкой точно по центру через отверстие, ловля точечных "
            "контровых лучей по ободу линзы, съемка сквозь уличные огни."
        ),
        "expected_result": (
            "Эффект тоннельного видения / портала, светящийся ореол вокруг героя кадра, "
            "калейдоскопические световые кольца."
        ),
        "best_styles": ["Сюрреализм", "Пиктореализм"],
        "notes": (
            "Прикручивается поверх светофильтра или прямо на резьбу объектива; "
            "угол падения света определяет яркость ореола."
        ),
    },
    "fabrics": {
        "pattern": r"(?:тканей|ткани|вуаль|органза|фатин)",
        "optical_traits": (
            "Мягкая волокнистая фактура передней плоскости: избирательное диффузное "
            "светорассеяние, локальное снижение контраста, преломление бликов."
        ),
        "what_to_do": (
            "Натяжение полупрозрачной ткани (органза, фатин, шелк) перед объективом, "
            "съемка сквозь складки, подсвечивание ткани фонариком."
        ),
        "expected_result": (
            "Сновидческая вуаль, эффект ностальгической дымки, призрачные полутона "
            "и таинственная многослойность кадра."
        ),
        "best_styles": ["Сюрреализм", "Пиктореализм"],
        "notes": (
            "Разные цвета ткани дают тональное тонирование; на открытой диафрагме "
            "нити превращаются в светящуюся дымку."
        ),
    },
    "tripod": {
        "pattern": r"штатив",
        "optical_traits": (
            "Трехосевая механическая стабилизация: полное устранение паразитного "
            "микротремора и сдвига оптической оси."
        ),
        "what_to_do": (
            "Серийная мультиэкспозиция с послойным наложением, брекетинг экспозиции, "
            "длинные ночные выдержки со светофильтрами ND."
        ),
        "expected_result": (
            "Кристальная попиксельная резкость неподвижных объектов при полном "
            "живописном размытии подвижной стихии."
        ),
        "best_styles": ["Сюрреализм", "Экспрессионизм"],
        "notes": (
            "Позволяет использовать таймер спуска или тросик для исключения "
            "сотрясения при нажатии кнопки."
        ),
    },
    "godox_v1": {
        "pattern": r"(?:godox.*v1|v1f|фотовспышка|вспышка)",
        "optical_traits": (
            "Импульсный свет с круглой головкой: мягкий и равномерный радиальный "
            "спад светового пятна, поддержка высокоскоростной синхронизации HSS."
        ),
        "what_to_do": (
            "Боковой жесткий импульс под углом 45° на сверхкороткой выдержке "
            "(до 1/8000s) для заморозки брызг и ткани, контровой свет с диффузором."
        ),
        "expected_result": (
            "Глубокий светотеневой контраст (кьяроскуро), острая скульптурная "
            "лепка объёма, кинематографичная заморозка динамики."
        ),
        "best_styles": ["Экспрессионизм", "Сюрреализм"],
        "notes": (
            "Магнитная система крепления насадок AK-R1 позволяет мгновенно "
            "крепить купол-диффузор, соты и цветные фильтры."
        ),
    },
    "fujifilm_xt4": {
        "pattern": r"(?:fujifilm|fuji).*x-t4",
        "optical_traits": (
            "Матрица X-Trans CMOS 4 (26.1 Мп), матричная стабилизация IBIS 6.5 стопов, "
            "фирменные симуляции плёнки (Classic Chrome, Velvia, Eterna)."
        ),
        "what_to_do": (
            "Съёмка с рук на длинных выдержках с микро-ICM, мультиэкспозиция до 9 кадров "
            "с режимами наложения (Additive, Dark, Light), ручные профили цвета."
        ),
        "expected_result": (
            "Аналоговая кинематографичная цветопередача, пластичные полутона "
            "и уникальная текстура зерна без цифровой жесткости."
        ),
        "best_styles": ["Сюрреализм", "Импрессионизм", "Экспрессионизм", "Пиктореализм"],
        "notes": (
            "Двойной слот SD UHS-II, аккумулятор NP-W235 высокой емкости; "
            "поворотный сенсорный экран для съёмки с нижних ракурсов."
        ),
    },
}


def get_expert_traits_fallback(name: str, category: str, notes: str = "") -> dict[str, Any]:
    """Возвращает экспертные оптические характеристики и приёмы для известных моделей."""
    search_target = f"{name} {notes}".strip().lower()
    for item_data in EXPERT_OPTICS_KNOWLEDGE.values():
        pat = item_data.get("pattern", "")
        if pat and re.search(pat, search_target, flags=re.IGNORECASE):
            return {
                "optical_traits": item_data.get("optical_traits", ""),
                "what_to_do": item_data.get("what_to_do", ""),
                "expected_result": item_data.get("expected_result", ""),
                "best_styles": list(item_data.get("best_styles", ["Сюрреализм"])),
                "notes": item_data.get("notes", notes),
            }
    return {}


def get_default_gear_profile() -> GearProfile:
    """Базовый арсенал фотографа по умолчанию."""
    profile = GearProfile()
    profile.add_item(GearItem(
        name="Fujifilm X-T4",
        category="camera",
        optical_traits="Матричная стабилизация IBIS, мультиэкспозиция, плёночные профили",
        what_to_do="Мультиэкспозиция с рук на длинных выдержках с микро-ICM, ручные профили",
        expected_result="Пластичные полутона, кинематографичный колорит и аналоговое зерно",
        best_styles=["Сюрреализм", "Импрессионизм", "Экспрессионизм", "Пиктореализм"],
    ))
    profile.add_item(GearItem(
        name="Fujinon XF 18-55mm f/2.8-4 R LM OIS",
        category="lens",
        optical_traits="Универсальный зум, быстрая резкость, оптический стаб",
        what_to_do="Съемка в динамике, микро-ICM со стабилизатором, зумирование на спуске",
        expected_result="Звенящая резкость по центру и чистая геометрия кадра",
        best_styles=["Сюрреализм", "Экспрессионизм"],
    ))
    profile.add_item(GearItem(
        name="Гелиос 44-2 58mm f/2",
        category="lens",
        optical_traits="Закрученное боке на открытой f/2, мягкий контраст в контровом свете",
        what_to_do="Портреты на открытой f/2 против солнца, съемка сквозь кроны деревьев",
        expected_result="Вихревое боке и мягкие светящиеся ореолы вокруг ярких светов",
        best_styles=["Импрессионизм", "Пиктореализм"],
    ))
    profile.add_item(GearItem(
        name="Монокль 50mm",
        category="lens",
        optical_traits="Сферические аберрации, сфумато, светящийся ореол вокруг ярких деталей",
        what_to_do="Съемка в контровом рассеянном свете, пейзажи в тумане, съемка силуэтов",
        expected_result="Акварельная дымка, сфумато и живописное растворение жестких контуров",
        best_styles=["Пиктореализм", "Сюрреализм"],
    ))
    profile.add_item(GearItem(
        name="Black Pro-Mist 1/4",
        category="filter",
        optical_traits="Мягкое рассеивание света вокруг источников, сохранение плотности теней",
        what_to_do="Съемка источников света (фонари, гирлянды, свечи), портреты в полумраке",
        expected_result="Мягкий ореол вокруг бликов при сохранении глубины теней",
        best_styles=["Пиктореализм", "Импрессионизм"],
    ))
    profile.add_item(GearItem(
        name="Хрустальная треугольная призма",
        category="accessory",
        optical_traits="Оптическое преломление, наложение двух пространств, спектральные радуги",
        what_to_do="Размещение ребра призмы перед передней линзой, поворот под углом к свету",
        expected_result="Спектральные радужные блики и наложение двух пространств в одном кадре",
        best_styles=["Сюрреализм"],
    ))
    return profile


def load_gear_profile(path: Path | None = None) -> GearProfile:
    """Загружает профиль арсенала из JSON-файла."""
    target_path = path or GEAR_FILE_PATH
    if not target_path.exists():
        default_prof = get_default_gear_profile()
        save_gear_profile(default_prof, target_path)
        return default_prof
    try:
        data = json.loads(target_path.read_text(encoding="utf-8"))
        return GearProfile.from_dict(data)
    except Exception as exc:
        logger.warning("[GEAR] Ошибка чтения профиля %s: %s, отдаём дефолт", target_path, exc)
        return get_default_gear_profile()


def save_gear_profile(profile: GearProfile, path: Path | None = None) -> None:
    """Сохраняет профиль арсенала в JSON-файл."""
    target_path = path or GEAR_FILE_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_suffix(".tmp")
    data = profile.to_dict()
    temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(target_path)


async def enrich_gear_item(
    item_name: str,
    category: str | None = None,
    raw_notes: str = "",
    engine: str | None = None,
    model: str | None = None,
) -> GearItem:
    """Обогащает единицу техники оптическими характеристиками через агентный поиск."""
    from services.agent_engine import run_agent

    clean_name = item_name.strip()
    cat = category or categorize_gear_name(clean_name)
    expert_fallback = get_expert_traits_fallback(clean_name, cat, raw_notes)

    system_prompt = (
        "Ты — ведущий эксперт по фототехнике, оптике и художественной фотографии. "
        "Твоя задача — исследовать единицу оборудования через web_search и вернуть "
        "ТОЛЬКО валидный JSON без лишнего текста:\n"
        "{\n"
        '  "optical_traits": "описание рисунка, резкости, боке и аберраций (1-2 предл.)",\n'
        '  "what_to_do": "конкретные приёмы съёмки и настройки: что делать (1-2 предл.)",\n'
        '  "expected_result": "какого результата ожидать в кадре (1-2 предл.)",\n'
        '  "best_styles": ["Стиль1", "Стиль2"],\n'
        '  "notes": "особенности работы или практический совет"\n'
        "}"
    )
    user_prompt = (
        f"Определи оптические особенности, приёмы (что делать) "
        f"и ожидаемый результат для: {clean_name}"
    )
    if raw_notes:
        user_prompt += f" (особенности/модификация: {raw_notes})"

    try:
        res = await asyncio.wait_for(
            run_agent(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                engine=engine,
                model=model,
                allowed_categories=("web", "system"),
                max_iterations=3,
            ),
            timeout=12.0,
        )
        answer = res.final_answer or ""
        parsed = safe_parse_llm_json(answer, expected_type=dict)
        if isinstance(parsed, dict):
            opt_traits = (
                str(parsed.get("optical_traits", "")).strip()
                or expert_fallback.get("optical_traits", "")
            )
            w_to_do = (
                str(parsed.get("what_to_do", "")).strip()
                or expert_fallback.get("what_to_do", "")
            )
            exp_res = (
                str(parsed.get("expected_result", "")).strip()
                or expert_fallback.get("expected_result", "")
            )
            styles = (
                [str(s).strip() for s in parsed.get("best_styles", []) if s]
                or expert_fallback.get("best_styles", ["Сюрреализм"])
            )
            notes_text = (
                str(parsed.get("notes", "")).strip()
                or expert_fallback.get("notes", raw_notes)
            )
            return GearItem(
                name=clean_name,
                category=cat,
                optical_traits=opt_traits,
                what_to_do=w_to_do,
                expected_result=exp_res,
                best_styles=styles,
                notes=notes_text,
            )
        # fallback, если ответ не JSON
        return GearItem(
            name=clean_name,
            category=cat,
            optical_traits=answer[:250].strip() or expert_fallback.get("optical_traits", ""),
            what_to_do=expert_fallback.get("what_to_do", ""),
            expected_result=expert_fallback.get("expected_result", ""),
            best_styles=expert_fallback.get("best_styles", ["Сюрреализм", "Пиктореализм"]),
            notes=expert_fallback.get("notes", raw_notes),
        )
    except Exception as exc:
        logger.warning("[GEAR] enrich failed for %s: %s", clean_name, exc)
        return GearItem(
            name=clean_name,
            category=cat,
            optical_traits=expert_fallback.get("optical_traits", "Пользовательское оборудование"),
            what_to_do=expert_fallback.get("what_to_do", ""),
            expected_result=expert_fallback.get("expected_result", ""),
            best_styles=expert_fallback.get("best_styles", ["Сюрреализм"]),
            notes=expert_fallback.get("notes", raw_notes),
        )


async def enrich_gear_profile(
    items_data: list[dict[str, Any]],
    status_cb: Callable[[int, int, str], Awaitable[None]] | None = None,
    engine: str | None = None,
    model: str | None = None,
) -> GearProfile:
    """Создаёт профиль оборудования, обогащая каждый предмет индивидуальным исследованием."""
    profile = GearProfile()
    total = len(items_data)
    for idx, it in enumerate(items_data, 1):
        name = it["name"]
        cat = it.get("category")
        notes = it.get("notes", "")
        if status_cb:
            await status_cb(idx, total, name)
        enriched_item = await enrich_gear_item(
            item_name=name,
            category=cat,
            raw_notes=notes,
            engine=engine,
            model=model,
        )
        profile.add_item(enriched_item)
    return profile


def remix_gear_for_concept(
    concept_styles: list[str],
    profile: GearProfile | None = None,
) -> dict[str, Any]:
    """Подбирает гармоничную связку из арсенала под заданную триаду стилей."""
    prof = profile or load_gear_profile()
    styles_lower = [s.lower() for s in concept_styles]

    # Выбор камеры
    camera = prof.cameras[0].name if prof.cameras else "Fujifilm X-T4"

    # Выбор объектива
    best_lens = None
    for lens in prof.lenses:
        lens_styles = [s.lower() for s in lens.best_styles]
        if any(s in lens_styles for s in styles_lower):
            best_lens = lens
            break
    if not best_lens and prof.lenses:
        best_lens = prof.lenses[0]
    lens_name = best_lens.name if best_lens else "Стандартный объектив"
    lens_traits = best_lens.optical_traits if best_lens else ""

    # Выбор фильтра/аксессуара
    accessory_picks: list[str] = []
    for filt in prof.filters:
        if any(s in [st.lower() for st in filt.best_styles] for s in styles_lower):
            accessory_picks.append(filt.name)
            break
    for acc in prof.accessories:
        if any(s in [st.lower() for st in acc.best_styles] for s in styles_lower):
            accessory_picks.append(acc.name)
            break

    return {
        "camera": camera,
        "lens": lens_name,
        "lens_traits": lens_traits,
        "accessories": accessory_picks,
        "summary": (
            f"{camera} + {lens_name}"
            + (f" + {', '.join(accessory_picks)}" if accessory_picks else "")
        ),
    }


def format_gear_context(profile: GearProfile | None = None) -> str:
    """Форматирует блок арсенала для промпта LLM с приёмами и ожидаемыми эффектами."""
    prof = profile or load_gear_profile()
    lines = ["[Арсенал фотографа (доступное оборудование)] :"]
    if prof.cameras:
        cams = ", ".join(
            f"{c.name} ({c.optical_traits})" if c.optical_traits else c.name
            for c in prof.cameras
        )
        lines.append(f"- Камеры: {cams}")
    if prof.lenses:
        lens_strs = []
        for lens_it in prof.lenses:
            details = []
            if lens_it.optical_traits:
                details.append(lens_it.optical_traits)
            if getattr(lens_it, "what_to_do", ""):
                details.append(f"Приём: {lens_it.what_to_do}")
            if getattr(lens_it, "expected_result", ""):
                details.append(f"Эффект: {lens_it.expected_result}")
            d_str = f" [{'; '.join(details)}]" if details else ""
            lens_strs.append(f"{lens_it.name}{d_str}")
        lines.append(f"- Объективы: {'; '.join(lens_strs)}")
    if prof.filters:
        f_strs = []
        for f in prof.filters:
            details = []
            if f.optical_traits:
                details.append(f.optical_traits)
            if getattr(f, "what_to_do", ""):
                details.append(f"Приём: {f.what_to_do}")
            d_str = f" [{'; '.join(details)}]" if details else ""
            f_strs.append(f"{f.name}{d_str}")
        lines.append(f"- Фильтры: {'; '.join(f_strs)}")
    if prof.lighting:
        lines.append(f"- Свет: {', '.join(x.name for x in prof.lighting)}")
    if prof.accessories:
        lines.append(f"- Аксессуары: {', '.join(x.name for x in prof.accessories)}")
    return "\n".join(lines) + "\n"


def format_gear_summary_card(profile: GearProfile | None = None) -> str:
    """Форматирует краткую сводку арсенала по категориям, умещающуюся в лимит Telegram."""
    prof = profile or load_gear_profile()
    all_items = prof.all_items()
    lines = [f"🎒 <b>Арсенал фотографа (всего {len(all_items)} предм.)</b>\n"]

    sections = [
        ("📷 <b>Камеры</b>", prof.cameras),
        ("🔍 <b>Объективы</b>", prof.lenses),
        ("🎞 <b>Фильтры</b>", prof.filters),
        ("💡 <b>Свет</b>", prof.lighting),
        ("🔮 <b>Аксессуары</b>", prof.accessories),
    ]

    has_any = False
    for title, items in sections:
        if not items:
            continue
        has_any = True
        lines.append(f"{title} ({len(items)}):")
        for item in items:
            name_esc = html.escape(item.name)
            short_trait = ""
            if item.optical_traits:
                parts = re.split(
                    r"(?<=[a-zA-Zа-яА-Я0-9])\.\s+|,\s*",
                    item.optical_traits,
                )
                first_phrase = parts[0].strip() if parts else ""
                if first_phrase:
                    short_trait = f" — <i>{html.escape(first_phrase[:90])}</i>"
            lines.append(f"• <b>{name_esc}</b>{short_trait}")
        lines.append("")

    if not has_any:
        lines.append("<i>Арсенал пуст. Добавьте технику командой или текстом.</i>\n")
    else:
        lines.append(
            "<i>💡 Выберите категорию на кнопках ниже для просмотра приёмов съёмки "
            "и оптических свойств каждого предмета:</i>"
        )

    return "\n".join(lines).strip()


def format_gear_card(
    profile: GearProfile | None = None,
    category: str | None = None,
) -> str:
    """Форматирует карточку арсенала: полностью или для заданной категории."""
    prof = profile or load_gear_profile()
    lines = ["🎒 <b>Арсенал фотографа</b>\n"]

    cat_raw = (category or "").strip().lower()
    if cat_raw in ("camera", "cameras", "камера", "камеры"):
        target_cat = "camera"
    elif cat_raw in ("lens", "lenses", "объектив", "объективы"):
        target_cat = "lens"
    elif cat_raw in ("filter", "filters", "фильтр", "фильтры"):
        target_cat = "filter"
    elif cat_raw in ("lighting", "свет", "вспышка", "вспышки", "flash"):
        target_cat = "lighting"
    elif cat_raw in ("accessory", "accessories", "аксессуар", "аксессуары"):
        target_cat = "accessory"
    else:
        target_cat = None

    sections = [
        ("camera", "📷 <b>Камеры:</b>", prof.cameras),
        ("lens", "🔍 <b>Объективы:</b>", prof.lenses),
        ("filter", "🎞 <b>Фильтры:</b>", prof.filters),
        ("lighting", "💡 <b>Свет:</b>", prof.lighting),
        ("accessory", "🔮 <b>Аксессуары:</b>", prof.accessories),
    ]

    has_any = False
    for cat_key, title, items in sections:
        if target_cat and cat_key != target_cat:
            continue
        if items:
            has_any = True
            lines.append(title)
            for item in items:
                name_esc = html.escape(item.name)
                lines.append(f"• <b>{name_esc}</b>")
                if item.optical_traits:
                    lines.append(f"  ✨ <i>Оптика:</i> {html.escape(item.optical_traits)}")
                if getattr(item, "what_to_do", ""):
                    lines.append(f"  🎯 <i>Что делать:</i> {html.escape(item.what_to_do)}")
                if getattr(item, "expected_result", ""):
                    lines.append(f"  🔮 <i>Результат:</i> {html.escape(item.expected_result)}")
            lines.append("")

    if not has_any:
        if target_cat:
            lines.append("<i>В выбранной категории техника пока не добавлена.</i>")
        else:
            lines.append("<i>Арсенал пуст. Добавьте технику командой или текстом.</i>")

    return "\n".join(lines).strip()


def format_safe_gear_card(
    profile: GearProfile | None = None,
    category: str | None = None,
    max_len: int = 3800,
) -> str:
    """Возвращает карточку арсенала, гарантированно не превышающую лимит длины сообщения."""
    prof = profile or load_gear_profile()
    if category:
        return format_gear_card(prof, category=category)
    full_card = format_gear_card(prof)
    if len(full_card) <= max_len:
        return full_card
    return format_gear_summary_card(prof)
