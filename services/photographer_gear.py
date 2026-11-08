"""services/photographer_gear.py — арсенал фотографа, обогащение и ремикс-движок."""

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

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
    if any(k in lower for k in ("фильтр", "mist", "nd", "cpl", "полярик", "диффуз")):
        return "filter"
    if any(k in lower for k in ("вспышк", "софтбокс", "фонар", "светильник", "godox", "свет")):
        return "lighting"
    if any(k in lower for k in ("призма", "штатив", "зеркало", "отражатель", "тросик")):
        return "accessory"
    if any(k in lower for k in (
        "объектив", "линз", "стекло", "монокль", "helios", "гелиос", "fujinon", "xf", "mm", "f/"
    )):
        return "lens"
    if any(k in lower for k in (
        "камера", "тушка", "fuji", "fujifilm", "canon", "nikon", "sony", "leica"
    )):
        return "camera"
    return "accessory"


def get_default_gear_profile() -> GearProfile:
    """Базовый арсенал фотографа по умолчанию."""
    profile = GearProfile()
    profile.add_item(GearItem(
        name="Fujifilm X-T4",
        category="camera",
        optical_traits=(
            "Матричная стабилизация IBIS, встроенная мультиэкспозиция, плёночные профили"
        ),
        best_styles=["Сюрреализм", "Импрессионизм", "Экспрессионизм", "Пиктореализм"],
    ))
    profile.add_item(GearItem(
        name="Fujinon XF 18-55mm f/2.8-4 R LM OIS",
        category="lens",
        optical_traits="Универсальный зум, быстрая резкость, оптический стаб",
        best_styles=["Сюрреализм", "Экспрессионизм"],
    ))
    profile.add_item(GearItem(
        name="Гелиос 44-2 58mm f/2",
        category="lens",
        optical_traits="Закрученное боке на открытой f/2, мягкий контраст в контровом свете",
        best_styles=["Импрессионизм", "Пиктореализм"],
    ))
    profile.add_item(GearItem(
        name="Монокль 50mm",
        category="lens",
        optical_traits="Сферические аберрации, сфумато, светящийся ореол вокруг ярких деталей",
        best_styles=["Пиктореализм", "Сюрреализм"],
    ))
    profile.add_item(GearItem(
        name="Black Pro-Mist 1/4",
        category="filter",
        optical_traits="Мягкое рассеивание света вокруг источников, сохранение плотности теней",
        best_styles=["Пиктореализм", "Импрессионизм"],
    ))
    profile.add_item(GearItem(
        name="Хрустальная треугольная призма",
        category="accessory",
        optical_traits="Оптическое преломление, наложение двух пространств, спектральные радуги",
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
    engine: str | None = None,
    model: str | None = None,
) -> GearItem:
    """Обогащает единицу техники оптическими характеристиками через агентный веб-поиск."""
    from services.agent_engine import run_agent

    clean_name = item_name.strip()
    cat = category or categorize_gear_name(clean_name)
    system_prompt = (
        "Ты — эксперт по фототехнике и оптике. Найди через web_search главные "
        "художественные и оптические особенности оборудования: характер рисунка, "
        "боке, контраст, аберрации, подходящие стили (Сюрреализм, Пиктореализм, "
        "Экспрессионизм, Импрессионизм).\n"
        "Верни ТОЛЬКО валидный JSON без лишнего текста:\n"
        '{"optical_traits": "краткое описание рисунка и оптики (1-2 предложения)", '
        '"best_styles": ["Стиль1", "Стиль2"], "notes": "особенности работы"}'
    )
    user_prompt = f"Определи оптические особенности и характер рисунка для: {clean_name}"

    try:
        res = await run_agent(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            engine=engine,
            model=model,
            allowed_categories=("web", "system"),
            max_iterations=3,
        )
        answer = res.final_answer or ""
        parsed = safe_parse_llm_json(answer, expected_type=dict)
        if isinstance(parsed, dict):
            return GearItem(
                name=clean_name,
                category=cat,
                optical_traits=str(parsed.get("optical_traits", "")).strip(),
                best_styles=[str(s).strip() for s in parsed.get("best_styles", []) if s],
                notes=str(parsed.get("notes", "")).strip(),
            )
        # fallback, если ответ не JSON
        return GearItem(
            name=clean_name,
            category=cat,
            optical_traits=answer[:250].strip(),
            best_styles=["Сюрреализм", "Пиктореализм"],
        )
    except Exception as exc:
        logger.warning("[GEAR] enrich failed for %s: %s", clean_name, exc)
        return GearItem(
            name=clean_name,
            category=cat,
            optical_traits="Пользовательское оборудование",
            best_styles=["Сюрреализм"],
        )


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
    """Форматирует блок арсенала для промпта LLM."""
    prof = profile or load_gear_profile()
    lines = ["[Арсенал фотографа (доступное оборудование)] :"]
    if prof.cameras:
        cams = ", ".join(
            f"{c.name} ({c.optical_traits})" if c.optical_traits else c.name
            for c in prof.cameras
        )
        lines.append(f"- Камеры: {cams}")
    if prof.lenses:
        lens_strs = [
            f"{lens_item.name} [{lens_item.optical_traits}]"
            if lens_item.optical_traits else lens_item.name
            for lens_item in prof.lenses
        ]
        lines.append(f"- Объективы: {'; '.join(lens_strs)}")
    if prof.filters:
        f_strs = [
            f"{f.name} [{f.optical_traits}]" if f.optical_traits else f.name
            for f in prof.filters
        ]
        lines.append(f"- Фильтры: {'; '.join(f_strs)}")
    if prof.lighting:
        lines.append(f"- Свет: {', '.join(x.name for x in prof.lighting)}")
    if prof.accessories:
        lines.append(f"- Аксессуары: {', '.join(x.name for x in prof.accessories)}")
    return "\n".join(lines) + "\n"


def format_gear_card(profile: GearProfile | None = None) -> str:
    """Форматирует карточку арсенала для сообщения Telegram."""
    import html

    prof = profile or load_gear_profile()
    lines = ["🎒 <b>Арсенал фотографа</b>\n"]

    sections = [
        ("📷 <b>Камеры:</b>", prof.cameras),
        ("🔍 <b>Объективы:</b>", prof.lenses),
        ("🎞 <b>Фильтры:</b>", prof.filters),
        ("💡 <b>Свет:</b>", prof.lighting),
        ("🔮 <b>Аксессуары:</b>", prof.accessories),
    ]

    has_any = False
    for title, items in sections:
        if items:
            has_any = True
            lines.append(title)
            for item in items:
                name_esc = html.escape(item.name)
                traits_esc = ""
                if item.optical_traits:
                    traits_esc = f" — <i>{html.escape(item.optical_traits)}</i>"
                lines.append(f"• <b>{name_esc}</b>{traits_esc}")
            lines.append("")

    if not has_any:
        lines.append("<i>Арсенал пуст. Добавьте технику командой или текстом.</i>")

    return "\n".join(lines).strip()
