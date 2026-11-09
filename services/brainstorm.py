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
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Literal

import numpy as np

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
    "тёмный",
    "темный",
    "лессировк",
    "акварель",
    "пуантилизм",
    "монокль",
    "диффузи",
    "black mist",
    "pro-mist",
    "микро-icm",
    "icm",
    "трясучк",
    "тремор",
    "сфумато",
    "голландский угол",
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
        ("serendipity", "Ассоциативный мост (Serendipity)"),
        ("notes", "Заметки Apple Notes"),
        ("palace", "Записи дворца"),
        ("kg", "Факты графа знаний"),
        ("guide", "Руководство Fujifilm X-T4"),
        ("mechanics", "Банк проверенных фотомеханик"),
        ("gear", "Арсенал фотографа"),
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


def find_serendipity_pair(
    topic: str = "",
    folder: str | None = None,
    min_similarity: float = 0.10,
    max_similarity: float = 0.60,
    db_file: str | None = None,
) -> tuple[dict, dict] | None:
    """Находит контрастную пару заметок для ассоциативного моста (Serendipity).

    1. Если доступна база SQLite с эмбеддингами (notes_embeddings.sqlite):
       - Если задана тема `topic` и модель доступна:
         Находит заметку А, наиболее близкую к теме.
         Среди остальных заметок ищет заметку Б с косинусным сходством в диапазоне
         [min_similarity, max_similarity] (целевая точка контраста ~0.35).
       - Если темы нет:
         Находит пару заметок с контрастным сходством.
    2. Fallback: если база эмбеддингов пуста или недоступна:
       Использует `list_notes()`:
       - Выбирает две заметки из разных папок (или с минимальным пересечением токенов).
    3. Если найдено < 2 заметок, возвращает None.
    """
    from services.notes_embeddings import (
        DB_FILE as DEFAULT_EMBED_DB,
        EMBED_DIM,
        EMBED_MODEL,
        _call_embed,
        _cosine,
        is_model_available,
    )

    db_path = db_file or DEFAULT_EMBED_DB
    notes_with_vectors: list[dict] = []

    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            try:
                query = (
                    "SELECT note_id, name, folder, preview, vector "
                    "FROM notes_embeddings WHERE model = ?"
                )
                rows = conn.execute(query, (EMBED_MODEL,)).fetchall()
                for note_id, name, fld, prev, blob in rows:
                    try:
                        vec = np.frombuffer(blob, dtype=np.float32)
                        if len(vec) == EMBED_DIM:
                            notes_with_vectors.append({
                                "id": str(note_id),
                                "name": str(name or "Без названия"),
                                "folder": str(fld or "Заметки"),
                                "preview": str(prev or "")[:300],
                                "snippet": str(prev or "")[:300],
                                "vector": vec,
                            })
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("[SERENDIPITY] Skip unparseable vector blob: %s", exc)
                        continue
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[SERENDIPITY] SQLite read failed: %s", exc)

    if len(notes_with_vectors) >= 2:
        target_sim = (min_similarity + max_similarity) / 2.0
        topic_vec = None
        if topic.strip():
            try:
                if is_model_available(EMBED_MODEL):
                    embeds = _call_embed([topic], EMBED_MODEL)
                    if embeds and len(embeds[0]) == EMBED_DIM:
                        topic_vec = np.asarray(embeds[0], dtype=np.float32)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[SERENDIPITY] Embed topic failed: %s", exc)

        if topic_vec is not None:
            pool_a = (
                [n for n in notes_with_vectors if n["folder"] == folder]
                if folder
                else notes_with_vectors
            )
            if not pool_a:
                pool_a = notes_with_vectors

            scored_a = [(float(_cosine(topic_vec, n["vector"])), n) for n in pool_a]
            scored_a.sort(key=lambda x: x[0], reverse=True)
            note_a = scored_a[0][1]

            other_notes = [n for n in notes_with_vectors if n["id"] != note_a["id"]]
            scored_b = [
                (
                    abs(float(_cosine(note_a["vector"], n["vector"])) - target_sim),
                    float(_cosine(note_a["vector"], n["vector"])),
                    n,
                )
                for n in other_notes
            ]
            in_range = [s for s in scored_b if min_similarity <= s[1] <= max_similarity]
            best_tuple = (
                min(in_range, key=lambda x: x[0])
                if in_range
                else min(scored_b, key=lambda x: x[0])
            )
            note_b = best_tuple[2]
            sim = best_tuple[1]

            dict_a = {k: v for k, v in note_a.items() if k != "vector"}
            dict_b = {k: v for k, v in note_b.items() if k != "vector"}
            dict_b["_similarity"] = round(sim, 3)
            return (dict_a, dict_b)

        # Без темы: выбираем пару с контрастным сходством
        pool_a = (
            [n for n in notes_with_vectors if n["folder"] == folder]
            if folder
            else notes_with_vectors
        )
        note_a = pool_a[0] if pool_a else notes_with_vectors[0]
        other_notes = [n for n in notes_with_vectors if n["id"] != note_a["id"]]
        scored_b = [
            (
                abs(float(_cosine(note_a["vector"], n["vector"])) - target_sim),
                float(_cosine(note_a["vector"], n["vector"])),
                n,
            )
            for n in other_notes
        ]
        in_range = [s for s in scored_b if min_similarity <= s[1] <= max_similarity]
        best_tuple = (
            min(in_range, key=lambda x: x[0])
            if in_range
            else min(scored_b, key=lambda x: x[0])
        )
        note_b = best_tuple[2]
        sim = best_tuple[1]

        dict_a = {k: v for k, v in note_a.items() if k != "vector"}
        dict_b = {k: v for k, v in note_b.items() if k != "vector"}
        dict_b["_similarity"] = round(sim, 3)
        return (dict_a, dict_b)

    # Fallback: list_notes
    try:
        notes = list_notes(folder=folder) if folder else list_notes()
        if len(notes) < 2 and folder:
            notes = list_notes()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[SERENDIPITY] list_notes fallback failed: %s", exc)
        return None

    if not notes or len(notes) < 2:
        return None

    by_folder: dict[str, list[dict]] = {}
    for n in notes:
        fld = n.get("folder") or "Заметки"
        by_folder.setdefault(fld, []).append(n)

    if len(by_folder) >= 2:
        f_keys = list(by_folder.keys())
        note_a = by_folder[f_keys[0]][0]
        note_b = by_folder[f_keys[1]][0]
    else:
        note_a = notes[0]
        tokens_a = _significant_tokens(
            f"{note_a.get('name', '')} {note_a.get('preview', '')}",
        )
        min_overlap = float("inf")
        best_cand = notes[1]
        for cand in notes[1:]:
            tokens_c = _significant_tokens(
                f"{cand.get('name', '')} {cand.get('preview', '')}",
            )
            overlap = len(tokens_a & tokens_c)
            if overlap < min_overlap:
                min_overlap = overlap
                best_cand = cand
        note_b = best_cand

    dict_a = {
        "id": note_a.get("id", ""),
        "name": note_a.get("name", "Без названия"),
        "folder": note_a.get("folder", "Заметки"),
        "preview": (note_a.get("preview") or note_a.get("snippet") or "")[:300],
        "snippet": (note_a.get("preview") or note_a.get("snippet") or "")[:300],
    }
    dict_b = {
        "id": note_b.get("id", ""),
        "name": note_b.get("name", "Без названия"),
        "folder": note_b.get("folder", "Заметки"),
        "preview": (note_b.get("preview") or note_b.get("snippet") or "")[:300],
        "snippet": (note_b.get("preview") or note_b.get("snippet") or "")[:300],
    }
    return (dict_a, dict_b)


def format_serendipity_bridge(note_a: dict, note_b: dict) -> str:
    """Форматирует ассоциативный мост между двумя контрастными заметками для промпта."""
    title_a = note_a.get("name") or "Заметка 1"
    title_b = note_b.get("name") or "Заметка 2"
    folder_a = note_a.get("folder") or "Заметки"
    folder_b = note_b.get("folder") or "Заметки"
    snippet_a = (note_a.get("preview") or note_a.get("snippet") or "")[:200].strip()
    snippet_b = (note_b.get("preview") or note_b.get("snippet") or "")[:200].strip()

    lines = [
        "🌉 Ассоциативный мост (Serendipity контраст):",
        f"• Концепт 1: «{title_a}» (папка: {folder_a})",
    ]
    if snippet_a:
        lines.append(f"  Суть: {snippet_a}")
    lines.append(f"• Концепт 2: «{title_b}» (папка: {folder_b})")
    if snippet_b:
        lines.append(f"  Суть: {snippet_b}")

    sim = note_b.get("_similarity")
    if sim is not None:
        lines.append(
            f"• Семантическое расстояние: сходство {int(sim * 100)}% (контрастная пара)",
        )

    lines.append(
        "Задача: создать фотопроект на неожиданном визуальном пересечении этих двух тем, "
        "воплотив их глубинную метафору через заданную триаду художественных стилей.",
    )
    return "\n".join(lines)


async def collect_context(
    topic: str,
    mode: Literal["standard", "surreal", "fusion"] = "standard",
    folder: str | None = None,
) -> dict:
    """Собирает контекст для штурма.

    standard: notes + palace + kg (каждый источник толерантен к ошибкам).
    surreal / fusion: ТОЛЬКО notes (по теме или из выбранной папки) + полный текст
    руководства FUJI_XT4_CREATIVE_GUIDE.md + банк фотомеханик + арсенал техники.
    В режиме fusion также генерируется триада стилей (Сюжет + Свет + Оптика).
    """
    out: dict = {"notes": "", "guide": ""}

    try:
        if (mode in ("surreal", "fusion")) and folder:
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

    if mode in ("surreal", "fusion"):
        out["guide"] = _load_fuji_guide()
        try:
            pair = find_serendipity_pair(topic=topic, folder=folder)
            if pair:
                out["serendipity_pair"] = pair
                out["serendipity"] = format_serendipity_bridge(pair[0], pair[1])
        except Exception as exc:  # noqa: BLE001
            logger.warning("[STORM] serendipity context failed: %s", exc)

        try:
            from services.photo_mechanics import (
                format_mechanics_context,
                get_relevant_mechanics,
            )
            mechs = get_relevant_mechanics(topic=topic, limit=2)
            if mechs:
                out["mechanics"] = format_mechanics_context(mechs)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[STORM] mechanics context failed: %s", exc)

        try:
            from services.photographer_gear import (
                format_gear_context,
                load_gear_profile,
            )
            prof = load_gear_profile()
            out["gear"] = format_gear_context(prof)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[STORM] gear context failed: %s", exc)

        if mode == "fusion":
            try:
                from services.style_fusion import (
                    build_fusion_user_prompt,
                    generate_style_triad,
                )
                triad = generate_style_triad(theme=topic)
                out["triad"] = triad
                out["fusion_prompt"] = build_fusion_user_prompt(
                    topic=topic,
                    triad=triad,
                    gear_context=out.get("gear", ""),
                    mechanics_context=out.get("mechanics", ""),
                    notes_context=out.get("notes", ""),
                    serendipity_context=out.get("serendipity", ""),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("[STORM] fusion triad context failed: %s", exc)

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
    """Системный промпт для штурма по режиму: standard, surreal или fusion."""
    if mode == "fusion":
        from services.style_fusion import build_fusion_system_prompt

        return build_fusion_system_prompt()
    if mode == "surreal":
        return SURREAL_STORM_SYSTEM_PROMPT
    return STORM_SYSTEM_PROMPT


def storm_sampling_params(mode: str) -> dict:
    """Параметры выборки модели для штурма по режиму.

    surreal и fusion — более креативная выборка (высокая температура, штрафы за
    повторения), чтобы идеи не были однотипными. standard — пусто (клиент
    использует свои дефолты, поведение обычного агента не меняется).
    """
    if mode in ("surreal", "fusion"):
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


def parse_fusion_ideas(raw: str) -> list[Any]:
    """Разбирает ответ модели в концепт-проекты режима fusion."""
    from services.style_fusion import parse_fusion_concepts

    concepts = parse_fusion_concepts(raw)
    if not concepts:
        raise ValueError("Нет валидных концепт-проектов в ответе модели.")
    return concepts


def format_fusion_ideas_text(topic: str, concepts: list[Any]) -> str:
    """Полный текст сообщения с концепт-проектами триады стилей."""
    from services.style_fusion import format_fusion_concept_card
    from services.text_formatter import safe_html_format

    lines = [
        f"⚡️ <b>Творческая лаборатория (Триада стилей):</b> {safe_html_format(topic)}\n"
    ]
    for i, concept in enumerate(concepts, start=1):
        card = format_fusion_concept_card(concept)
        lines.append(f"<b>--- Проект {i} ---</b>\n{card}\n")
    return "\n".join(lines).strip()


def ideas_to_text(ideas: list) -> str:
    """Склеивает выбранные идеи в текст для сохранения во Дворец."""
    lines = []
    for i, idea in enumerate(ideas, start=1):
        if hasattr(idea, "title"):
            title = idea.title
            parts = [f"{i}. {title}"]
            triad = getattr(idea, "triad", None)
            if triad and hasattr(triad, "summary"):
                parts.append(f"🎭 Триада стилей: {triad.summary()}")
                if getattr(triad, "rationale", ""):
                    parts.append(f"Обоснование синергии: {triad.rationale}")
            manifesto = getattr(idea, "manifesto", "")
            if manifesto:
                parts.append(f"📜 Манифест:\n{manifesto}")
            scene = getattr(idea, "scene_description", "")
            if scene:
                parts.append(f"Сюжет: {scene}")
            lighting = getattr(idea, "lighting_setup", "")
            if lighting:
                parts.append(f"💡 Свет: {lighting}")
            cam = getattr(idea, "camera_setup", {})
            if cam:
                cam_str = "; ".join(f"{k}: {v}" for k, v in cam.items())
                parts.append(f"📷 Камера: {cam_str}")
            action = getattr(idea, "shooting_action", "")
            if action:
                parts.append(f"👐 Физика съёмки: {action}")
            gear = getattr(idea, "gear_recipe", {})
            if gear:
                gear_str = "; ".join(f"{k}: {v}" for k, v in gear.items())
                parts.append(f"🎒 Арсенал: {gear_str}")
            steps = getattr(idea, "shooting_steps", [])
            if steps:
                parts.append(f"Шаги: {'; '.join(steps)}")
            deepened = getattr(idea, "deepened_analysis", "")
            if deepened:
                parts.append(f"🔍 Режиссёрское углубление:\n{deepened}")
            mj = getattr(idea, "midjourney_prompt", "")
            if mj:
                parts.append(f"🎨 Промпт Midjourney:\n{mj}")
            fuji = getattr(idea, "fuji_recipe", "")
            if fuji:
                parts.append(f"🎛 Рецепт Fujifilm:\n{fuji}")
            lines.append("\n\n".join(parts))
        elif isinstance(idea, dict):
            block = f"{i}. {idea.get('title', 'Без названия')}"
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
