"""services/photo_mechanics.py — банк фотомеханик, авто-парсинг и OCR рецептов."""

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

from config import DATA_DIR
from services.json_parser import safe_parse_llm_json

logger = logging.getLogger("PhotoMechanics")

MECHANICS_FILE_PATH = Path(DATA_DIR) / "custom_photo_mechanics.json"


@dataclass
class VisualMechanic:
    id: str
    title: str
    styles: list[str] = field(default_factory=list)
    visual_outcome: str = ""
    camera_setup: dict[str, Any] = field(default_factory=dict)
    physical_action: str = ""
    required_gear: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    source: str = "factory"  # factory / user
    added_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VisualMechanic":
        return cls(
            id=str(data.get("id", "")).strip(),
            title=str(data.get("title", "Без названия")).strip(),
            styles=[str(s).strip() for s in data.get("styles", []) if s],
            visual_outcome=str(data.get("visual_outcome", "")).strip(),
            camera_setup=(
                data.get("camera_setup", {})
                if isinstance(data.get("camera_setup"), dict) else {}
            ),
            physical_action=str(data.get("physical_action", "")).strip(),
            required_gear=[str(g).strip() for g in data.get("required_gear", []) if g],
            tags=[str(t).strip() for t in data.get("tags", []) if t],
            source=str(data.get("source", "user")),
            added_at=float(data.get("added_at", time.time())),
        )


def get_factory_mechanics() -> list[VisualMechanic]:
    """Предустановленный набор проверенных фотомеханик."""
    return [
        VisualMechanic(
            id="watercolor_dark_multiexposure",
            title="Акварельная лессировка / микро-ICM",
            styles=["Импрессионизм", "Пиктореализм"],
            visual_outcome=(
                "Живописный мазок кисти, сохранение сочных цветов и "
                "плотных теней без выбивания светов"
            ),
            camera_setup={
                "Приём съёмки": "Мультиэкспозиция (2–4 кадра)",
                "Режим мультиэкспозиции": "Тёмный",
                "Выдержка": '1/6"',
                "Компенсация экспозиции (EV)": "-1.0",
                "Диафрагма": "f/5.6–f/11",
                "Имитация плёнки": "Velvia или ASTIA",
                "Тоновая кривая (Подсветка/Тень)": "Подсветка -1 / Тень +1.5",
                "Цвет": "+2",
                "Прозрачность (Clarity)": "-2",
                "Движение камеры / Руки": "Микро-тремор (микро-ICM) на месте",
            },
            physical_action=(
                "Съемка с рук без штатива. Нажатие на спуск с естественным "
                "микро-тремором на 1-2 мм между кадрами (не делать широкую проводку)."
            ),
            required_gear=["Fujifilm X-T4 или камера с режимом мультиэкспозиции Тёмный"],
            tags=["акварель", "лессировка", "листва", "вода", "осень", "парк", "импрессионизм"],
            source="factory",
        ),
        VisualMechanic(
            id="pictorial_sfumato_monocle",
            title="Пикториальный сфумато и ореол света",
            styles=["Пиктореализм"],
            visual_outcome=(
                "Мягкое свечение вокруг светлых объектов, бархатные тени, "
                "живописное размытие контуров"
            ),
            camera_setup={
                "Приём съёмки": "Мягкорисующая оптика",
                "Диафрагма": "f/1.4–f/2.8",
                "Имитация плёнки": "Classic Chrome или PRO Neg. Std",
                "Тоновая кривая (Подсветка/Тень)": "Подсветка -2 / Тень +1",
                "Прозрачность (Clarity)": "-4",
                "Эффект зерна": "Сильный+Крупное",
            },
            physical_action=(
                "Съемка сквозь дымку, софт-фильтр Black Mist или через самодельный монокль."
            ),
            required_gear=["Монокль 50mm или диффузный фильтр Black Pro-Mist"],
            tags=["сфумато", "туман", "пиктореализм", "монокль", "дымка", "бархат"],
            source="factory",
        ),
        VisualMechanic(
            id="expressionist_caligari_shadows",
            title="Экспрессионистский графичный кьяроскуро",
            styles=["Экспрессионизм"],
            visual_outcome=(
                "Острые диагональные тени, драматический эмоциональный контраст, "
                "тревожная атмосфера"
            ),
            camera_setup={
                "Приём съёмки": "Голландский угол и жесткий контраст",
                "Имитация плёнки": "ACROS (+R Красный фильтр)",
                "Тоновая кривая (Подсветка/Тень)": "Подсветка +2 / Тень +3",
                "Прозрачность (Clarity)": "+3",
                "Резкость": "+2",
                "Компенсация экспозиции (EV)": "-0.7",
            },
            physical_action=(
                "Наклон камеры на 15–25 градусов (голландский угол), поиск жестких "
                "геометрических лучей и теней."
            ),
            required_gear=["Жесткий направленный свет или контрастное солнце"],
            tags=["экспрессионизм", "чб", "контраст", "тени", "кьяроскуро", "голландский угол"],
            source="factory",
        ),
        VisualMechanic(
            id="surreal_prism_refraction",
            title="Сюрреалистическое расщепление призмой",
            styles=["Сюрреализм"],
            visual_outcome=(
                "Оптическое раздвоение пространства, наложение двух реальностей "
                "в одном физическом кадре"
            ),
            camera_setup={
                "Приём съёмки": "Съемка сквозь оптическую призму",
                "Диафрагма": "f/2.0–f/2.8",
                "Имитация плёнки": "Classic Negative",
                "Цвет": "+2",
            },
            physical_action=(
                "Удержание треугольной призмы вплотную к передней линзе объектива "
                "с поворотом грани для наложения отражения."
            ),
            required_gear=["Хрустальная призма", "Светосильный объектив"],
            tags=["призма", "сюрреализм", "преломление", "отражение", "мираж"],
            source="factory",
        ),
        VisualMechanic(
            id="center_hole_distortion",
            title="Оптическая воронка сквозь линзу с отверстием",
            styles=["Сюрреализм", "Пиктореализм"],
            visual_outcome=(
                "Бритвенно резкий фокус в центральном отверстии и сюрреалистическое "
                "вихревое искажение по краям кадра"
            ),
            camera_setup={
                "Приём съёмки": "Линза с отверстием в центре",
                "Диафрагма": "f/2.8–f/4",
                "Имитация плёнки": "Classic Chrome",
                "Тоновая кривая (Подсветка/Тень)": "Подсветка -1 / Тень +1",
                "Прозрачность (Clarity)": "-2",
            },
            physical_action=(
                "Прикрутить линзу с отверстием на объектив, точно центрировать главный "
                "сюжетный объект в прозрачной зоне."
            ),
            required_gear=[
                "Стеклянная линза с отверстием в центре",
                "Fujinon XF 18-55mm или Pentacon 29mm",
            ],
            tags=["линза с отверстием", "центр", "сюрреализм", "воронка", "осень", "листва"],
            source="factory",
        ),
        VisualMechanic(
            id="reversed_front_element_swirl",
            title="Вихревое боке перевёрнутой линзы Pentacon",
            styles=["Импрессионизм", "Экспрессионизм"],
            visual_outcome=(
                "Драматический вихревой круговорот боке на периферии кадра, живописный мазок "
                "на открытой диафрагме без цифровой обработки"
            ),
            camera_setup={
                "Приём съёмки": "Перевёрнутая передняя линза",
                "Диафрагма": "f/2.8",
                "Выдержка": '1/125"',
                "Имитация плёнки": "Velvia",
                "Цвет": "+2",
            },
            physical_action=(
                "Съёмка на Pentacon 2.8/29 с перевёрнутой передней линзой в контровом свете."
            ),
            required_gear=["Pentacon 2.8/29 с перевёрнутой передней линзой"],
            tags=[
                "перевернутая линза", "вихрь", "крученое боке", "листва",
                "импрессионизм", "осень",
            ],
            source="factory",
        ),
        VisualMechanic(
            id="kamlan_ultra_shallow_dof",
            title="Сверхмалая ГРИП и масляное боке Kamlan f/1.1",
            styles=["Пиктореализм", "Импрессионизм"],
            visual_outcome=(
                "Микроскопическая глубина резкости на f/1.1 с полным растворением "
                "фона в сливочную цветовую палитру"
            ),
            camera_setup={
                "Приём съёмки": "Сверхсветосильная оптика f/1.1",
                "Диафрагма": "f/1.1",
                "Выдержка": '1/2000"–1/8000"',
                "Имитация плёнки": "PRO Neg. Hi",
                "Эффект зерна": "Слабый+Мелкое",
            },
            physical_action=(
                "Ручная ювелирная фокусировка по пикингу на единственной акцентной детали."
            ),
            required_gear=["Kamlan 50mm F1.1"],
            tags=["f1.1", "камилан", "боке", "грип", "размытие", "листья", "пиктореализм"],
            source="factory",
        ),
        VisualMechanic(
            id="nd_silky_motion",
            title="Пластичный смаз на длинной выдержке с ND-фильтром",
            styles=["Импрессионизм", "Сюрреализм"],
            visual_outcome=(
                "Шелковистое размытие движущейся воды или колышущейся ветром листвы "
                "при абсолютной резкости статичных элементов"
            ),
            camera_setup={
                "Приём съёмки": "Длинная выдержка с ND-фильтром",
                "Выдержка": '1/2"–4"',
                "Диафрагма": "f/8–f/11",
                "Имитация плёнки": "Classic Chrome",
                "Тоновая кривая (Подсветка/Тень)": "Подсветка -1 / Тень +2",
            },
            physical_action=(
                "Установка на трёхногий штатив, плотное затемнение K&F ND 2-400, "
                "спуск по таймеру 2 с."
            ),
            required_gear=["Трёхногий штатив", "K&F ND-Filter 2-400", "Fujifilm X-T4"],
            tags=["nd фильтр", "штатив", "длинная выдержка", "вода", "ветер", "листва", "смаз"],
            source="factory",
        ),
        VisualMechanic(
            id="sheer_fabric_veil",
            title="Воздушный вейл сквозь прозрачные ткани",
            styles=["Пиктореализм", "Сюрреализм"],
            visual_outcome=(
                "Эфирная дымка, нежные оптические ореолы и осязаемая тактильная фактура "
                "на переднем плане"
            ),
            camera_setup={
                "Приём съёмки": "Съёмка сквозь прозрачную ткань",
                "Диафрагма": "f/1.4–f/2.8",
                "Имитация плёнки": "Classic Chrome или ASTIA",
                "Прозрачность (Clarity)": "-3",
            },
            physical_action=(
                "Свободно придерживать складку прозрачной ткани перед краем бленды/линзы."
            ),
            required_gear=["Набор прозрачных тканей", "Светосильный объектив"],
            tags=["ткань", "вуаль", "дымка", "фактура", "пиктореализм", "сюрреализм"],
            source="factory",
        ),
    ]


def load_mechanics(path: Path | None = None) -> list[VisualMechanic]:
    """Загружает список фотомеханик из JSON-файла."""
    target_path = path or MECHANICS_FILE_PATH
    if not target_path.exists():
        factory = get_factory_mechanics()
        save_mechanics(factory, target_path)
        return factory
    try:
        data = json.loads(target_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [VisualMechanic.from_dict(d) for d in data if isinstance(d, dict)]
        return get_factory_mechanics()
    except Exception as exc:
        logger.warning("[MECHANICS] Ошибка чтения %s: %s, отдаём заводские", target_path, exc)
        return get_factory_mechanics()


def save_mechanics(mechanics: list[VisualMechanic], path: Path | None = None) -> None:
    """Сохраняет список фотомеханик в JSON-файл."""
    target_path = path or MECHANICS_FILE_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_suffix(".tmp")
    data = [m.to_dict() for m in mechanics]
    temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(target_path)


def add_user_mechanic(mechanic: VisualMechanic, path: Path | None = None) -> None:
    """Добавляет пользовательскую механику в базу."""
    current = load_mechanics(path)
    # Удаляем дубликат по id если есть
    filtered = [m for m in current if m.id != mechanic.id]
    filtered.append(mechanic)
    save_mechanics(filtered, path)


def extract_text_from_image(image_input: bytes | str | Path) -> str:
    """Извлекает текст из изображения (скриншот рецепта/настроек) через pytesseract."""
    try:
        from PIL import Image
        import pytesseract

        if isinstance(image_input, (str, Path)):
            img = Image.open(image_input)
        elif isinstance(image_input, bytes):
            img = Image.open(BytesIO(image_input))
        else:
            return ""
        text = pytesseract.image_to_string(img, lang="rus+eng")
        return text.strip()
    except Exception as exc:
        logger.warning("[MECHANICS] OCR failed: %s", exc)
        return ""


async def parse_mechanic_from_text(
    raw_text: str,
    engine: str | None = None,
    model: str | None = None,
) -> VisualMechanic | None:
    """Парсит неструктурированное описание фотоприёма в объект VisualMechanic через LLM."""
    from services.ai_engine import get_ai_response_async, get_current_ai

    text = raw_text.strip()
    if not text:
        return None

    eng = engine
    mdl = model
    if not eng or not mdl:
        eng, mdl = get_current_ai()

    system_prompt = (
        "Ты — технический эксперт по фотографии. Твоя задача — извлечь параметры "
        "фотографического приёма/рецепта из текста и структурировать их в JSON.\n"
        "Схема ответа строго в формате JSON:\n"
        "{\n"
        '  "title": "Краткое название приёма",\n'
        '  "styles": ["Стиль1", "Стиль2"],  // Сюрреализм/Пикто/Экспрес/Импрес\n'
        '  "visual_outcome": "Какой визуальный эффект получается (1-2 предложения)",\n'
        '  "camera_setup": {\n'
        '    "Приём съёмки": "...",\n'
        '    "Режим мультиэкспозиции": "...",\n'
        '    "Выдержка": "...",\n'
        '    "Диафрагма": "...",\n'
        '    "Компенсация экспозиции (EV)": "...",\n'
        '    "Имитация плёнки": "...",\n'
        '    "Тоновая кривая (Подсветка/Тень)": "...",\n'
        '    "Движение камеры / Руки": "..."\n'
        "  },\n"
        '  "physical_action": "Что физически делать фотографу руками/камерой",\n'
        '  "required_gear": ["список необходимой техники"],\n'
        '  "tags": ["тег1", "тег2"]\n'
        "}\n"
        "Верни ТОЛЬКО валидный JSON, без пояснений."
    )

    msgs = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Извлеки фотоприём из текста:\n{text}"},
    ]

    try:
        raw_res = await get_ai_response_async(eng, mdl, msgs)
        parsed = safe_parse_llm_json(raw_res, expected_type=dict)
        if not isinstance(parsed, dict) or not parsed.get("title"):
            return None
        mech_id = f"user_{int(time.time())}"
        parsed["id"] = mech_id
        parsed["source"] = "user"
        return VisualMechanic.from_dict(parsed)
    except Exception as exc:
        logger.warning("[MECHANICS] parse failed: %s", exc)
        return None


def get_relevant_mechanics(
    topic: str,
    styles: list[str] | None = None,
    limit: int = 3,
    path: Path | None = None,
) -> list[VisualMechanic]:
    """Возвращает наиболее релевантные фотомеханики по стилям и теме."""
    all_mechs = load_mechanics(path)
    if not all_mechs:
        return []

    styles_set = {s.lower() for s in (styles or [])}
    topic_lower = (topic or "").lower()

    scored: list[tuple[int, VisualMechanic]] = []
    for m in all_mechs:
        score = 0
        m_styles = {s.lower() for s in m.styles}
        if styles_set and m_styles.intersection(styles_set):
            score += 3
        for tag in m.tags:
            if tag.lower() in topic_lower:
                score += 2
        if any(w in m.title.lower() for w in topic_lower.split()):
            score += 2
        scored.append((score, m))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:limit]]


def format_mechanics_context(mechanics: list[VisualMechanic]) -> str:
    """Форматирует блок контекста механик для инъекции в промпт штурма."""
    if not mechanics:
        return ""
    lines = ["[Банк проверенных фотомеханик (используй подходящую)]:"]
    for i, m in enumerate(mechanics, start=1):
        lines.append(f"{i}. «{m.title}» (Стили: {', '.join(m.styles)}):")
        lines.append(f"   Эффект: {m.visual_outcome}")
        if m.camera_setup:
            parts = [
                f"{k}: {str(v).replace('\"', ' с').strip()}"
                for k, v in m.camera_setup.items()
            ]
            lines.append(f"   Настройки: {'; '.join(parts)}")
        if m.physical_action:
            lines.append(f"   Действие: {m.physical_action}")
    return "\n".join(lines) + "\n"


def format_mechanic_card(mech: VisualMechanic) -> str:
    """Форматирует превью фотомеханики для сообщения в Telegram."""
    import html

    title_esc = html.escape(mech.title)
    lines = [f"🎨 <b>Фотоприём: {title_esc}</b>\n"]
    if mech.styles:
        styles_esc = html.escape(", ".join(mech.styles))
        lines.append(f"🎭 <b>Стили:</b> {styles_esc}")
    if mech.visual_outcome:
        outcome_esc = html.escape(mech.visual_outcome)
        lines.append(f"✨ <b>Эффект:</b> {outcome_esc}")
    if mech.camera_setup:
        lines.append("📷 <b>Параметры:</b>")
        for k, v in mech.camera_setup.items():
            lines.append(f"   • {html.escape(str(k))}: {html.escape(str(v))}")
    if mech.physical_action:
        lines.append(f"👐 <b>Физика съёмки:</b> {html.escape(mech.physical_action)}")
    if mech.required_gear:
        lines.append(f"🎒 <b>Техника:</b> {html.escape(', '.join(mech.required_gear))}")
    return "\n".join(lines)


def format_mechanics_list(mechanics: list[VisualMechanic]) -> str:
    """Форматирует список фотомеханик для Telegram."""
    import html

    if not mechanics:
        return "<i>Банк фотомеханик пуст.</i>"

    lines = [f"📚 <b>Банк фотомеханик ({len(mechanics)} приёмов)</b>\n"]
    for i, m in enumerate(mechanics, start=1):
        title = html.escape(m.title)
        styles = html.escape(", ".join(m.styles)) if m.styles else "Общий"
        src_icon = "⭐" if m.source == "factory" else "👤"
        lines.append(f"{i}. {src_icon} <b>{title}</b> (<i>{styles}</i>)")
        if m.visual_outcome:
            preview = html.escape(m.visual_outcome[:90])
            if len(m.visual_outcome) > 90:
                preview += "…"
            lines.append(f"   └ {preview}")
    return "\n".join(lines)
