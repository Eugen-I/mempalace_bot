"""services/brainstorm.py — генерация идей (штурм) с контекстом базы знаний.

Детерминированный пайплайн:
  1. collect_context(topic) — три источника контекста: Apple Notes
     (search_notes), дворец (mempalace_search), граф знаний
     (mempalace_kg_query). Каждый источник толерантен к ошибкам —
     не роняет весь штурм.
  2. build_storm_prompt(topic, context) — инструкция модели: вернуть
     строго JSON {"ideas": [{"title", "reason", "steps"}]}, 5-7 идей.
  3. parse_ideas(raw) — разбор JSON-ответа модели (граничные ветки
     покрыты unit-тестами).

Хендлер (handlers/brainstorm.py) — тонкий: только Telegram-обвязка.
"""

import logging
import re
from pathlib import Path
from typing import Literal

from services.apple_notes import AppleNotesError, list_notes, search_notes
from services.camera_setup import format_camera_setup
from services.json_parser import safe_parse_llm_json
from services.palace_mcp import get_mcp
from services.prompts.surreal_storm_prompts import (
    STORM_SYSTEM_PROMPT,
    SURREAL_STORM_SYSTEM_PROMPT,
)

logger = logging.getLogger("Brainstorm")

MAX_IDEAS = 7
MIN_IDEAS = 5
MAX_TITLE_LEN = 80
CONTEXT_SOURCE_LIMIT = 4000
GUIDE_CONTEXT_LIMIT = 24000  # гайд X-T4 — базовый справочник, входит целиком
LINK_MIN_TOKEN_LEN = 4
MAX_LINK_TEXT_LEN = 120
MAX_LINKS = 5
SOURCE_LABELS = {
    "notes": "Apple Notes",
    "palace": "Дворец",
    "kg": "Граф знаний",
}

SURREAL_SAMPLING_PARAMS = {
    "temperature": 0.95,
    "top_p": 0.95,
    "frequency_penalty": 0.5,
    "presence_penalty": 0.3,
}

_CAMERA_SETUP_KEYWORDS = (
    "имитац",
    "монохром",
    "acros",
    "тон",
    "подсвет",
    "тень",
    "clarity",
    "прозрачн",
    "wb",
    "баланс бел",
    "зерн",
    "экспозамер",
    "диафрагм",
    "выдержк",
    "резкост",
    "шумоподавлен",
    "цветной хром",
    "минимакет",
    "мини-макет",
    "частичный цвет",
    "динамический тон",
    "мягкий фокус",
    "wc/mg",
    "фильтр",
    "расширенный фильтр",
    "advanced filter",
    "toy camera",
    "miniature",
    "pop color",
    "high-key",
    "low-key",
    "dynamic tone",
    "soft focus",
    "partial color",
)


def _build_context_block(
    source_name: str, text: str, limit: int = CONTEXT_SOURCE_LIMIT,
) -> str:
    if not text.strip():
        return ""
    return f"[{source_name}]\n{text[:limit]}\n"


def build_storm_prompt(topic: str, context: dict) -> str:
    """Собирает user-промпт: тема + блоки контекста из каждого источника.

    Гайд Fujifilm X-T4 — базовый справочник настроек: для него действует
    GUIDE_CONTEXT_LIMIT (почти полный текст), прочие источники — стандартный
    CONTEXT_SOURCE_LIMIT.
    """
    blocks = [f"Тема штурма: {topic}\n"]
    for key, label in (
        ("notes", "Заметки Apple Notes"),
        ("palace", "Записи дворца"),
        ("kg", "Факты графа знаний"),
        ("guide", "Руководство Fujifilm X-T4"),
    ):
        limit = GUIDE_CONTEXT_LIMIT if key == "guide" else CONTEXT_SOURCE_LIMIT
        block = _build_context_block(label, context.get(key, ""), limit=limit)
        if block:
            blocks.append(block)
    if len(blocks) == 1:
        blocks.append("[Контекст из базы знаний отсутствует — используй общие знания]")
    return "\n".join(blocks)


# ─── Руководство Fujifilm X-T4 (контекст сюрреалистичного штурма) ───

_FUJI_GUIDE_DIR = Path(__file__).resolve().parent.parent / "docs"
_FUJI_GUIDE_NAMES = ("FUJI_XT4_CREATIVE_GUIDE.md\u2009", "FUJI_XT4_CREATIVE_GUIDE.md")
_fuji_guide_cache: str | None = None


def _load_fuji_guide() -> str:
    """Полное содержимое руководства X-T4, читается один раз и кэшируется.

    Толерантно к отсутствию файла: возвращает "" (блок контекста просто
    пропускается). Кэш — память процесса (файл не более 15-20 КБ).
    """
    global _fuji_guide_cache
    if _fuji_guide_cache is not None:
        return _fuji_guide_cache
    for name in _FUJI_GUIDE_NAMES:
        path = _FUJI_GUIDE_DIR / name
        try:
            _fuji_guide_cache = path.read_text(encoding="utf-8")
            return _fuji_guide_cache
        except OSError:
            continue
    logger.warning("[STORM] FUJI guide not found in %s", _FUJI_GUIDE_DIR)
    _fuji_guide_cache = ""
    return _fuji_guide_cache


def reset_fuji_guide_cache() -> None:
    """Сбрасывает кэш руководства (для тестов)."""
    global _fuji_guide_cache
    _fuji_guide_cache = None


def _notes_context_from_list(notes: list[dict]) -> str:
    return "\n".join(
        f"- {n.get('name', '?')}: {n.get('preview', '') or n.get('snippet', '') or ''}"
        for n in notes
    )


async def collect_context(
    topic: str,
    mode: Literal["standard", "surreal"] = "standard",
    folder: str | None = None,
) -> dict:
    """Собирает контекст для штурма.

    standard: notes + palace + kg (каждый источник толерантен к ошибкам).
    surreal: ТОЛЬКО notes (по теме или из выбранной папки) + полный текст
    руководства FUJI_XT4_CREATIVE_GUIDE.md — palace/kg не запрашиваются.
    """
    out: dict = {"notes": "", "guide": ""}

    try:
        if mode == "surreal" and folder:
            notes = list_notes(folder=folder, sort_by_updated=True, limit=5)
            out["notes"] = _notes_context_from_list(notes)
        else:
            notes = search_notes(topic, limit=5)
            out["notes"] = "\n".join(
                f"- {n.get('name', '?')}: {n.get('snippet', '') or n.get('body', '')[:200]}"
                for n in notes
            )
    except AppleNotesError as exc:
        logger.warning("[STORM] notes context failed: %s", exc)

    if mode == "surreal":
        out["guide"] = _load_fuji_guide()
        return out

    out["palace"] = ""
    out["kg"] = ""
    mcp = get_mcp()
    for key, tool, args in (
        ("palace", "mempalace_search",
         {"query": topic, "limit": 5}),
        ("kg", "mempalace_kg_query",
         {"entity": topic}),
    ):
        try:
            out[key] = await mcp.call_tool(tool, args)
        except Exception as exc:  # noqa: BLE001 — источник не должен ронять штурм
            logger.warning("[STORM] %s context failed: %s", key, exc)
    return out


def _clean_raw(raw: str) -> str:
    cleaned = (raw or "").strip()
    for prefix in ("```json", "```"):
        cleaned = cleaned.removeprefix(prefix)
    cleaned = cleaned.removesuffix("```").strip()
    return cleaned


def _camera_setup_has_parameters(text: str) -> bool:
    """Проверка, что camera_setup упоминает хотя бы один ключевой параметр.

    Не жёсткий парсер: любой из маркеров (имитация плёнки/монохром/ACROS,
    кривая/тон, подсветка/тень, Clarity/Прозрачность, WB/баланс белого,
    зерно, экспозамер, диафрагма, выдержка) считается подтверждением того,
    что идея содержит настройки камеры.
    """
    lower = (text or "").lower()
    return any(keyword in lower for keyword in _CAMERA_SETUP_KEYWORDS)


def _normalize_field_value(value) -> str | None:
    """Приводит значение поля идеи к строке.

    Локальные LLM иногда возвращают camera_setup JSON-объектом, а steps —
    массивом (вместо строки из инструкции). Нормализуем в читаемый текст:
    dict → "ключ: значение" по строкам, list → строки через перенос.
    None — для типов, которые не могут быть осмысленным текстом (int и т.п.).
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(f"{k}: {v}" for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return "\n".join(str(v) for v in value)
    if value is None:
        return None
    return None


def _validate_idea(
    item,
    require_camera_setup: bool = False,
    require_camera_keywords: bool = False,
) -> dict | None:
    if not isinstance(item, dict):
        return None
    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        return None
    raw_camera_setup = item.get("camera_setup")
    camera_setup = _normalize_field_value(raw_camera_setup)
    if camera_setup is None:
        camera_setup = ""
    if require_camera_setup and not camera_setup.strip():
        return None
    if require_camera_keywords and not _camera_setup_has_parameters(camera_setup):
        return None
    reason = _normalize_field_value(item.get("reason")) or ""
    steps = _normalize_field_value(item.get("steps")) or ""
    description = _normalize_field_value(item.get("description")) or ""
    return {
        "title": title.strip()[:MAX_TITLE_LEN],
        "description": description.strip(),
        "reason": reason.strip(),
        "camera_setup": camera_setup.strip(),
        "camera_setup_raw": raw_camera_setup,
        "steps": steps.strip(),
    }


def parse_ideas(
    raw: str,
    require_camera_setup: bool = False,
    require_camera_keywords: bool = False,
) -> list[dict]:
    """Разбирает JSON-ответ модели в список идей (title/reason/camera_setup/steps).

    require_camera_setup=True — идея без непустого camera_setup отбраковывается
    (правило «никогда без настроек камеры» на уровне кода).

    require_camera_keywords=True — идея также отбраковывается, если camera_setup
    не упоминает ни одного ключевого параметра (имитация плёнки, кривая,
    Clarity, WB, зерно и т.п.) — защита от пустых отговорок вроде «сделай
    сюрреалистично».

    Raises:
        ValueError: если JSON не валиден, не содержит массива ideas
            или после фильтрации не осталось ни одной валидной идеи.
    """
    cleaned = _clean_raw(raw)
    if not cleaned:
        logger.error("[STORM] parse_ideas: пустой ответ модели")
        raise ValueError("Пустой ответ модели.")
    data = safe_parse_llm_json(cleaned, expected_type=dict)
    if data is None:
        logger.error("[STORM] parse_ideas: ответ не является JSON, фрагмент: %r", cleaned[:300])
        raise ValueError("Ответ модели не является JSON.")
    if not isinstance(data, dict) or not isinstance(data.get("ideas"), list):
        logger.error(
            "[STORM] parse_ideas: нет массива ideas, фрагмент: %r", cleaned[:300],
        )
        raise ValueError("В ответе нет массива ideas.")
    ideas = [
        idea for idea in (
            _validate_idea(i, require_camera_setup, require_camera_keywords)
            for i in data["ideas"]
        )
        if idea is not None
    ]
    if not ideas:
        raise ValueError("Нет валидных идей в ответе модели.")
    return ideas[:MAX_IDEAS]


def storm_system_prompt(mode: str) -> str:
    """Системный промпт для штурма по режиму: standard или surreal."""
    if mode == "surreal":
        return SURREAL_STORM_SYSTEM_PROMPT
    return STORM_SYSTEM_PROMPT


def storm_sampling_params(mode: str) -> dict:
    """Параметры выборки модели для штурма по режиму.

    surreal — более креативная выборка (высокая температура, штрафы за
    повторения), чтобы идеи не были однотипными. standard — пусто (клиент
    использует свои дефолты, поведение обычного агента не меняется).
    """
    if mode == "surreal":
        return dict(SURREAL_SAMPLING_PARAMS)
    return {}


def format_idea(index: int, idea: dict) -> str:
    """Форматирует одну идею для сообщения (индекс — с 1)."""
    lines = [f"💡 {index}. <b>{idea['title']}</b>"]
    if idea.get("reason"):
        lines.append(f"   <i>Почему:</i> {idea['reason']}")
    if idea.get("steps"):
        lines.append(f"   <i>Шаги:</i> {idea['steps']}")
    return "\n".join(lines)


def format_surreal_card(index: int, idea: dict) -> str:
    """Карточка сюрреалистичной идеи: Идея / Почему / Настройки камеры / Шаги."""
    from services.text_formatter import safe_html_format

    lines = [f"💡 <b>Идея {index}: {safe_html_format(idea['title'])}</b>"]
    if idea.get("description"):
        lines.append(
            f"🎨 <b>Образ:</b> {safe_html_format(idea['description'])}",
        )
    if idea.get("reason"):
        lines.append(
            f"🎭 <b>Почему сюрреалистично:</b> {safe_html_format(idea['reason'])}",
        )
    camera_setup = idea.get("camera_setup_raw", idea.get("camera_setup"))
    if camera_setup:
        text = format_camera_setup(camera_setup)
        if text:
            lines.append(
                f"📷 <b>Настройки камеры:</b>\n<code>{safe_html_format(text)}</code>",
            )
    if idea.get("steps"):
        lines.append(f"➡️ <b>Первые шаги:</b> {safe_html_format(idea['steps'])}")
    return "\n".join(lines)


def format_surreal_ideas_text(topic: str, ideas: list[dict]) -> str:
    """Полный текст сообщения со всеми сюрреалистичными идеями."""
    from services.text_formatter import safe_html_format

    lines = [f"🌪 <b>Сюрреалистичный штурм:</b> {safe_html_format(topic)}\n"]
    for i, idea in enumerate(ideas, start=1):
        lines.append(format_surreal_card(i, idea))
    return "\n".join(lines)


def format_ideas_text(topic: str, ideas: list[dict]) -> str:
    """Полный текст сообщения со всеми идеями."""
    lines = [f"🧠 <b>Штурм:</b> {topic}\n"]
    for i, idea in enumerate(ideas, start=1):
        lines.append(format_idea(i, idea))
    return "\n".join(lines)


def ideas_to_text(ideas: list[dict]) -> str:
    """Склеивает выбранные идеи в текст для сохранения во Дворец."""
    lines = []
    for i, idea in enumerate(ideas, start=1):
        block = f"{i}. {idea['title']}"
        if idea.get("reason"):
            block += f" — {idea['reason']}"
        if idea.get("steps"):
            block += f" Шаги: {idea['steps']}"
        lines.append(block)
    return "\n\n".join(lines)


def _significant_tokens(text: str) -> set[str]:
    """Значащие токены: слова длиной ≥ LINK_MIN_TOKEN_LEN, без чисел."""
    out = set()
    for word in re.findall(r"[а-яёa-z0-9]+", (text or "").lower()):
        if len(word) >= LINK_MIN_TOKEN_LEN and not word.isdigit():
            out.add(word)
    return out


def find_linked(ideas_text: str, context: dict, limit: int = MAX_LINKS) -> list[dict]:
    """Записи контекста, пересекающиеся с текстом идей (для «Связано с:»).

    Каждая строка блока контекста — кандидат; запись попадает в результат,
    если у неё есть хотя бы один общий значащий токен с идеями. Сортировка —
    по числу совпадений (убывание), затем по названию источника.
    """
    ideas_tokens = _significant_tokens(ideas_text)
    if not ideas_tokens:
        return []
    found: list[dict] = []
    for source, label in SOURCE_LABELS.items():
        block = context.get(source, "")
        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue
            overlap = ideas_tokens & _significant_tokens(line)
            if overlap:
                found.append({
                    "source": source,
                    "label": label,
                    "text": line[:MAX_LINK_TEXT_LEN],
                    "score": len(overlap),
                })
    found.sort(key=lambda item: (-item["score"], item["label"]))
    return found[:max(limit, 0)]


def format_linked(linked: list[dict]) -> str:
    """Форматирует блок «Связано с:» (HTML). Без записей — один заголовок."""
    from services.text_formatter import safe_html_format

    lines = ["🔗 <b>Связано с:</b>"]
    for item in linked:
        lines.append(
            f"• <b>{safe_html_format(item['label'])}</b>: "
            f"{safe_html_format(item['text'])}",
        )
    return "\n".join(lines)
