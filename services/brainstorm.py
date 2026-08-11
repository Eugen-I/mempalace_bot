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
from services.json_parser import safe_parse_llm_json
from services.palace_mcp import get_mcp

logger = logging.getLogger("Brainstorm")

MAX_IDEAS = 7
MIN_IDEAS = 5
MAX_TITLE_LEN = 80
CONTEXT_SOURCE_LIMIT = 4000
LINK_MIN_TOKEN_LEN = 4
MAX_LINK_TEXT_LEN = 120
MAX_LINKS = 5
SOURCE_LABELS = {
    "notes": "Apple Notes",
    "palace": "Дворец",
    "kg": "Граф знаний",
}

STORM_SYSTEM_PROMPT = (
    "Ты — генератор идей в личном пространстве MemPalace. Отвечай на русском.\n"
    "Правила:\n"
    "- На основе контекста из базы знаний пользователя придумай 5-7 конкретных "
    "идей по теме. Идеи должны быть практичными, развивать личный опыт "
    "пользователя, а не быть абстрактными.\n"
    "- У каждой идеи: title — название до 60 символов; reason — 1-2 предложения "
    "обоснования с опорой на факты из контекста; steps — 1-3 первых шага "
    "реализации (одним предложением).\n"
    "- Не выдумывай факты о пользователе, которых нет в контексте.\n"
    "- Верни ТОЛЬКО JSON вида "
    '{"ideas": [{"title": "...", "reason": "...", "steps": "..."}]}.\n'
    "- Никакого текста вне JSON."
)

SURREAL_STORM_SYSTEM_PROMPT = (
    "Ты — генератор сюрреалистичных фотоидей в личном пространстве MemPalace. "
    "Отвечай на русском.\n"
    "Стиль пользователя — сюрреализм. Твоя задача — полный полёт фантазии, "
    "разрыв с бытовой реальностью, неожиданные образы и сочетания на основе "
    "контекста из заметок пользователя.\n"
    "Правила:\n"
    "- Придумай 5-7 конкретных фотоидей. Идеи должны быть смелыми, "
    "нестандартными, ломающими привычную композицию/реализм.\n"
    "- Опирайся на образы из контекста, но свободно комбинируй, искажай "
    "масштаб, смешивай несовместимые объекты и сцены.\n"
    "- К КАЖДОЙ идее ОБЯЗАТЕЛЬНО приложи один или ДВА СОВМЕЩЁННЫХ приёма "
    "съёмки на Fujifilm X-T4 (мультиэкспозиция + искажённый баланс белого, "
    "длинная выдержка + экстремальная эмуляция плёнки, и т.п.) — комбинация "
    "приёмов ПРИВЕТСТВУЕТСЯ и усиливает сюрреалистичность результата.\n"
    "- Используй ТОЛЬКО значения настроек из FUJI_XT4_CREATIVE_GUIDE.md "
    "(включая раздел «Комбинации для сюрреализма»), не выдумывай числа.\n"
    "- Никогда не давай идею без приложенных настроек камеры.\n"
    "- У каждой идеи: title (до 60 символов); reason (1-2 предложения о "
    "сюрреалистичном образе); camera_setup (приём(ы) + точные настройки, "
    "2-4 предложения); steps (1-3 первых шага).\n"
    "- Не выдумывай факты о пользователе, образы — придумывай свободно.\n"
    "- Верни ТОЛЬКО JSON: "
    '{"ideas": [{"title": "...", "reason": "...", "camera_setup": "...", '
    '"steps": "..."}]}.\n'
    "- Никакого текста вне JSON."
)


def _build_context_block(source_name: str, text: str) -> str:
    if not text.strip():
        return ""
    return f"[{source_name}]\n{text[:CONTEXT_SOURCE_LIMIT]}\n"


def build_storm_prompt(topic: str, context: dict) -> str:
    """Собирает user-промпт: тема + блоки контекста из каждого источника."""
    blocks = [f"Тема штурма: {topic}\n"]
    for key, label in (
        ("notes", "Заметки Apple Notes"),
        ("palace", "Записи дворца"),
        ("kg", "Факты графа знаний"),
        ("guide", "Руководство Fujifilm X-T4"),
    ):
        block = _build_context_block(label, context.get(key, ""))
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


def _validate_idea(item, require_camera_setup: bool = False) -> dict | None:
    if not isinstance(item, dict):
        return None
    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        return None
    camera_setup = item.get("camera_setup")
    if require_camera_setup and (
        not isinstance(camera_setup, str) or not camera_setup.strip()
    ):
        return None
    return {
        "title": title.strip()[:MAX_TITLE_LEN],
        "reason": str(item.get("reason") or "").strip(),
        "camera_setup": str(camera_setup or "").strip(),
        "steps": str(item.get("steps") or "").strip(),
    }


def parse_ideas(raw: str, require_camera_setup: bool = False) -> list[dict]:
    """Разбирает JSON-ответ модели в список идей (title/reason/camera_setup/steps).

    require_camera_setup=True — идея без непустого camera_setup отбраковывается
    (правило «никогда без настроек камеры» на уровне кода).

    Raises:
        ValueError: если JSON не валиден, не содержит массива ideas
            или после фильтрации не осталось ни одной валидной идеи.
    """
    cleaned = _clean_raw(raw)
    if not cleaned:
        raise ValueError("Пустой ответ модели.")
    data = safe_parse_llm_json(cleaned, expected_type=dict)
    if data is None:
        raise ValueError("Ответ модели не является JSON.")
    if not isinstance(data, dict) or not isinstance(data.get("ideas"), list):
        raise ValueError("В ответе нет массива ideas.")
    ideas = [
        idea for idea in (_validate_idea(i, require_camera_setup) for i in data["ideas"])
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
    if idea.get("reason"):
        lines.append(
            f"🎭 <b>Почему сюрреалистично:</b> {safe_html_format(idea['reason'])}",
        )
    if idea.get("camera_setup"):
        lines.append(
            f"📷 <b>Настройки камеры:</b>\n<code>{safe_html_format(idea['camera_setup'])}</code>",
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
