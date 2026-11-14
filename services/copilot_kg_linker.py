"""services/copilot_kg_linker.py — Привязка фотопроектов к Графу Знаний и Дворцу Памяти (MP-2).

Реализует:
- Извлечение ключевых сущностей из проекта (стили, оптика/техника, механики, концепты, референсы).
- Генерацию нормализованных триплетов Графа Знаний (Subject -> Predicate -> Object).
- Интеллектуальное определение крыла (Wing) и комнаты (Room) Дворца Памяти.
- Сохранение фактов в Граф Знаний через MemPalace MCP (с graceful degradation).
- Форматирование визуальной карточки привязки для Telegram UI (HTML safety: blockquote, code, b).
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from services.text_formatter import safe_html_format
from services.wing_registry import get_wing_display_name

if TYPE_CHECKING:
    from services.copilot_session import CopilotSession  # noqa: F401

logger = logging.getLogger("CopilotKGLinker")

# Допустимые предикаты графа знаний для фотопроектов
KG_PHOTO_PREDICATES = {
    "has_style": "имеет стиль",
    "uses_gear": "использует технику",
    "applies_technique": "применяет приём",
    "explores_concept": "исследует концепт",
    "references_artist": "отсылает к автору",
    "located_in_wing": "размещён в крыле",
    "located_in_room": "находится в комнате",
}

# Известные художники, фотографы и референсы для авто-распознавания
KNOWN_ARTISTS = [
    "Рене Магритт",
    "Магритт",
    "Сальвадор Дали",
    "Дали",
    "Эдвард Хоппер",
    "Хоппер",
    "Робер Демаши",
    "Демаши",
    "Ман Рэй",
    "Альфред Стиглиц",
    "Стиглиц",
    "Георг Гросс",
    "Эгон Шиле",
    "Клод Моне",
    "Моне",
    "Эдгар Дега",
    "Дега",
    "Картье-Брессон",
    "Брессон",
    "Сол Лейтер",
    "Лейтер",
    "Франческа Вудман",
    "Вудман",
]


def extract_project_kg_entities(session_or_concept: Any) -> dict[str, list[str]]:
    """Извлекает структурированные сущности из сессии копайлота или концепта Штурма."""
    entities: dict[str, list[str]] = {
        "styles": [],
        "gear": [],
        "mechanics": [],
        "concepts": [],
        "references": [],
    }

    text_corpus_parts: list[str] = []

    # 1. Извлечение из CopilotSession
    if hasattr(session_or_concept, "topic"):
        topic = str(session_or_concept.topic or "").strip()
        if topic:
            text_corpus_parts.append(topic)
            entities["concepts"].append(topic)

        selected_styles = getattr(session_or_concept, "selected_styles", []) or []
        for s in selected_styles:
            name = s.get("name") if isinstance(s, dict) else str(s)
            if name and name not in entities["styles"]:
                entities["styles"].append(name)

        manifesto = getattr(session_or_concept, "manifesto_text", "") or ""
        if manifesto:
            text_corpus_parts.append(manifesto)

        tech_prefs = getattr(session_or_concept, "tech_preferences", {}) or {}
        if isinstance(tech_prefs, dict):
            for val in tech_prefs.values():
                if isinstance(val, str) and val.strip():
                    text_corpus_parts.append(val)
                    gear_words = [
                        "гелиос", "fujifilm", "xf", "объектив",
                        "камера", "фильтр", "про-мист", "свет",
                    ]
                    if any(w in val.lower() for w in gear_words):
                        entities["gear"].append(val.strip())
                    elif any(w in val.lower() for w in ["icm", "выдержка", "мульти", "смаз"]):
                        entities["mechanics"].append(val.strip())

        # Главный выбранный вариант проекта
        variants = getattr(session_or_concept, "project_variants", []) or []
        sel_idx = getattr(session_or_concept, "selected_project_idx", None)
        active_variant = None
        if sel_idx is not None and 0 <= sel_idx < len(variants):
            active_variant = variants[sel_idx]
        elif variants:
            active_variant = variants[0]

        if isinstance(active_variant, dict):
            v_title = active_variant.get("title", "")
            if v_title and v_title not in entities["concepts"]:
                entities["concepts"].append(v_title)
            v_gear = active_variant.get("gear", "")
            if v_gear and v_gear not in entities["gear"]:
                entities["gear"].append(v_gear)
            v_mech = active_variant.get("action_mechanic", "")
            if v_mech and v_mech not in entities["mechanics"]:
                entities["mechanics"].append(v_mech)
            text_corpus_parts.append(str(active_variant))

    # 2. Извлечение из словарного концепта (Штурм 2.0)
    elif isinstance(session_or_concept, dict):
        title = session_or_concept.get("title") or session_or_concept.get("name") or ""
        if title:
            text_corpus_parts.append(title)
            entities["concepts"].append(title)
        for st in session_or_concept.get("styles", []):
            st_name = st.get("name") if isinstance(st, dict) else str(st)
            if st_name and st_name not in entities["styles"]:
                entities["styles"].append(st_name)
        gear = session_or_concept.get("gear") or session_or_concept.get("camera_setup")
        if gear and str(gear) not in entities["gear"]:
            entities["gear"].append(str(gear))
        mech = session_or_concept.get("action_mechanic") or session_or_concept.get("mechanic")
        if mech and str(mech) not in entities["mechanics"]:
            entities["mechanics"].append(str(mech))
        text_corpus_parts.append(str(session_or_concept))

    full_text = " ".join(text_corpus_parts)

    # 3. Распознавание художников и референсов по корпусу
    for artist in KNOWN_ARTISTS:
        pattern = r"\b" + re.escape(artist) + r"\b"
        if re.search(pattern, full_text, flags=re.IGNORECASE):
            if artist not in entities["references"]:
                entities["references"].append(artist)

    # 4. Базовые значения по умолчанию для пустых полей
    if not entities["gear"]:
        entities["gear"].append("Fujifilm X-T4")

    return entities


def classify_palace_room_for_project(session_or_concept: Any) -> dict[str, str]:
    """Определяет оптимальное крыло (Wing) и комнату (Room) Дворца для проекта."""
    entities = extract_project_kg_entities(session_or_concept)

    # Нормализация текста для эвристики
    text_corpus = " ".join(
        entities["concepts"] + entities["styles"] + entities["mechanics"] + entities["references"]
    ).lower()

    # Определение крыла
    wing_key = "creative"
    dream_kw = [
        "сон", "сновидени", "сюрреализм", "бессознательн",
        "мираж", "греза", "дали", "магритт",
    ]
    psych_kw = [
        "архетип", "юнг", "тень", "психолог",
        "травма", "эмоци", "страх", "меланхоли",
    ]
    phil_kw = [
        "бытие", "экзистенци", "философи", "время",
        "смерть", "смысл", "пустота",
    ]
    if any(w in text_corpus for w in dream_kw):
        wing_key = "dreams"
    elif any(w in text_corpus for w in psych_kw):
        wing_key = "psychology"
    elif any(w in text_corpus for w in phil_kw):
        wing_key = "philosophy"

    # Определение тематической комнаты
    room_name = "Фотолаборатория"
    if "dreams" in wing_key:
        room_name = "Комната Сюрреализма"
    elif "psychology" in wing_key:
        room_name = "Зал Архетипов и Теней"
    elif "philosophy" in wing_key:
        room_name = "Галерея Экзистенции"
    else:
        # Для крыла creative смотрим на преобладающий стиль
        styles_str = " ".join(entities["styles"]).lower()
        if "пикториализм" in styles_str:
            room_name = "Пикториальная Мастерская"
        elif "экспрессионизм" in styles_str:
            room_name = "Экспрессионистский Салон"
        elif "импрессионизм" in styles_str:
            room_name = "Акварельная Студия Света"
        elif entities["concepts"]:
            room_name = f"Проект: {entities['concepts'][0][:30]}"

    return {
        "wing_key": wing_key,
        "wing_display": get_wing_display_name(wing_key),
        "room": room_name,
    }


def build_project_kg_triplets(session_or_concept: Any) -> list[tuple[str, str, str]]:
    """Генерирует нормализованные триплеты (Субъект, Предикат, Объект)."""
    entities = extract_project_kg_entities(session_or_concept)
    classification = classify_palace_room_for_project(session_or_concept)

    # Определение субъекта проекта
    subject = "Фотопроект"
    if hasattr(session_or_concept, "topic") and session_or_concept.topic:
        subject = session_or_concept.topic.strip()
    elif isinstance(session_or_concept, dict):
        subject = session_or_concept.get("title") or session_or_concept.get("name") or "Фотопроект"

    triplets: list[tuple[str, str, str]] = []

    # 1. Привязка к топологии Дворца
    triplets.append((subject, "located_in_wing", classification["wing_display"]))
    triplets.append((subject, "located_in_room", classification["room"]))

    # 2. Привязка стилей
    for style in entities["styles"]:
        triplets.append((subject, "has_style", style))

    # 3. Привязка техники и оптики
    for gear in entities["gear"][:3]:  # Ограничение до 3 ключевых элементов
        triplets.append((subject, "uses_gear", gear))

    # 4. Привязка фотомеханик
    for mech in entities["mechanics"][:3]:
        triplets.append((subject, "applies_technique", mech))

    # 5. Привязка художников и референсов
    for ref in entities["references"]:
        triplets.append((subject, "references_artist", ref))

    # 6. Ключевые концепты
    for concept in entities["concepts"]:
        if concept != subject:
            triplets.append((subject, "explores_concept", concept))

    return triplets


def link_project_to_palace_kg(session_or_concept: Any) -> dict[str, Any]:
    """Сводный интерфейс привязки концепта к Графу Знаний и Дворцу Памяти."""
    entities = extract_project_kg_entities(session_or_concept)
    classification = classify_palace_room_for_project(session_or_concept)
    triplets = build_project_kg_triplets(session_or_concept)

    subject = "Фотопроект"
    if hasattr(session_or_concept, "topic") and session_or_concept.topic:
        subject = session_or_concept.topic.strip()
    elif isinstance(session_or_concept, dict):
        subject = session_or_concept.get("title") or session_or_concept.get("name") or "Фотопроект"

    return {
        "project_title": subject,
        "wing_key": classification["wing_key"],
        "wing_display": classification["wing_display"],
        "room": classification["room"],
        "entities": entities,
        "triplets": triplets,
        "status": "ready",
    }


async def save_project_to_kg(
    session_or_concept: Any,
    mcp_client: Any = None,
) -> tuple[int, list[str]]:
    """Асинхронно сохраняет триплеты проекта в Граф Знаний через MemPalace MCP.

    Returns:
        tuple (успешно_сохраненных_триплетов, список_сообщений_или_ошибок)
    """
    triplets = build_project_kg_triplets(session_or_concept)
    if not triplets:
        return 0, ["Нет триплетов для сохранения."]

    if mcp_client is None:
        try:
            from services.palace_mcp import get_mcp
            mcp_client = get_mcp()
        except Exception as exc:
            logger.warning("[KG_LINKER] Не удалось получить MCP-клиент: %s", exc)
            return 0, [f"MCP клиент недоступен: {exc}"]

    saved_count = 0
    errors: list[str] = []

    for subj, pred, obj in triplets:
        try:
            await mcp_client.call_tool(
                "mempalace_kg_add",
                {
                    "subject": subj,
                    "predicate": pred,
                    "object": obj,
                },
            )
            saved_count += 1
        except Exception as err:
            logger.debug(
                "[KG_LINKER] Ошибка сохранения триплета (%s, %s, %s): %s",
                subj, pred, obj, err,
            )
            errors.append(f"({subj} -> {pred} -> {obj}): {err}")

    return saved_count, errors


def format_kg_link_card(link_data: dict[str, Any]) -> str:
    """Форматирует визуальную карточку привязки к Графу Знаний для Telegram UI."""
    title = safe_html_format(str(link_data.get("project_title", "Фотопроект")))
    wing = safe_html_format(str(link_data.get("wing_display", "🎨 Творчество")))
    room = safe_html_format(str(link_data.get("room", "Фотолаборатория")))
    triplets = link_data.get("triplets", [])

    lines = [
        f"🧠 <b>Граф Знаний • Привязка проекта «{title}»</b>",
        "",
        "🏛 <b>Локация во Дворце Памяти:</b>",
        f"  • Крыло: <b>{wing}</b>",
        f"  • Чертог: <b>{room}</b>",
        "",
        f"🔗 <b>Сгенерированные триплеты графа ({len(triplets)}):</b>",
    ]

    for subj, pred, obj in triplets:
        pred_label = KG_PHOTO_PREDICATES.get(pred, pred)
        s_subj = safe_html_format(str(subj))
        s_obj = safe_html_format(str(obj))
        lines.append(f"  • <code>{s_subj}</code> ➔ <i>{pred_label}</i> ➔ <b>{s_obj}</b>")

    lines.extend([
        "",
        (
            "<blockquote>Факты связывают концепт с вашей долговременной базой знаний "
            "и отображаются на интерактивной карте Дворца.</blockquote>"
        ),
    ])

    return "\n".join(lines)
