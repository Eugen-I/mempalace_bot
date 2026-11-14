"""services/copilot_palace_bridge.py — Семантический мост между арт-копайлотом и Дворцом Памяти.

Функционал (Фаза 3, Шаг B1 / MP-1):
- Поиск ассоциативных резонансов в Apple Notes и личной памяти по теме арт-проекта.
- Обогащение Сократического диалога скрытыми контекстами, цитатами и снами автора.
- Форматирование визуальной карточки резонансов для Telegram UI с цитатами в blockquote.
- Полная изоляция ошибок (graceful degradation при пустой базе или отсутствии сервисов).
"""

from __future__ import annotations

import logging
from typing import Any

from services.text_formatter import safe_html_format

logger = logging.getLogger("CopilotPalaceBridge")


def find_palace_resonances(
    topic: str,
    user_id: int | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Ищет семантически близкие заметки и факты в Дворце Памяти по теме арт-проекта.

    Возвращает список словарей:
        [
            {
                "id": str,
                "title": str,
                "snippet": str,
                "source": str,  # 'Apple Notes' | 'Личная память' | 'Дворец'
                "score": float,
            },
            ...
        ]
    """
    clean_topic = (topic or "").strip()
    if not clean_topic:
        return []

    resonances: list[dict[str, Any]] = []
    seen_snippets: set[str] = set()

    # 1. Поиск в Apple Notes (семантический гибрид)
    try:
        from services.notes_embeddings import search_notes_hybrid

        notes = search_notes_hybrid(clean_topic, limit=limit)
        for n in notes:
            snippet = str(n.get("snippet", "")).strip()
            title = str(n.get("name", "Заметка")).strip()
            if not snippet or snippet in seen_snippets:
                continue
            seen_snippets.add(snippet)
            score = float(n.get("_score", 0.0))
            resonances.append({
                "id": str(n.get("id", "")),
                "title": title,
                "snippet": snippet,
                "source": "Apple Notes",
                "score": score,
            })
    except Exception as exc:
        logger.debug("[PALACE_BRIDGE] Apple Notes hybrid search skipped: %s", exc)

    # 2. Поиск в личной памяти (memory_embeddings)
    if user_id is not None and len(resonances) < limit:
        try:
            from services.memory_embeddings import search_similar

            facts = search_similar(clean_topic, user_id=user_id, limit=limit)
            for f in facts:
                snippet = str(f.get("snippet", f.get("fact", ""))).strip()
                title = str(f.get("name", f.get("title", "Мысль"))).strip()
                if not snippet or snippet in seen_snippets:
                    continue
                seen_snippets.add(snippet)
                score = float(f.get("_score", 0.0))
                resonances.append({
                    "id": str(f.get("id", "")),
                    "title": title or "Память автора",
                    "snippet": snippet,
                    "source": "Личная память",
                    "score": score,
                })
        except Exception as exc:
            logger.debug("[PALACE_BRIDGE] Memory embeddings search skipped: %s", exc)

    # Сортируем по релевантности и ограничиваем лимитом
    resonances.sort(key=lambda item: item["score"], reverse=True)
    return resonances[:limit]


def format_palace_resonances_context(resonances: list[dict[str, Any]]) -> str:
    """Формирует инструкцию и контекст резонансов для системного промпта арт-директора."""
    if not resonances:
        return ""

    lines = [
        "АССОЦИАТИВНЫЕ РЕЗОНАНСЫ ИЗ ДВОРЦА ПАМЯТИ АВТОРА:",
        "У автора есть следующие мысли, сны или заметки, перекликающиеся с темой:",
    ]
    for idx, r in enumerate(resonances, start=1):
        title = r.get("title", "Заметка")
        snippet = r.get("snippet", "").replace("\n", " ")
        lines.append(f"{idx}. «{title}»: \"{snippet}\"")

    lines.extend([
        "",
        "ИНСТРУКЦИЯ КУРАТОРА ПО РЕЗОНАНСАМ:",
        "- Используй эти записи лишь как скрытый ассоциативный фон "
        "(не более одного раза за весь диалог).",
        "- СТРОГО ЗАПРЕЩЕНО использовать шаблонные фразы "
        "(«Это перекликается с твоим размышлением...», «Как ты видишь эту связь в кадре?») "
        "и повторять отсылки к заметкам в следующих репликах.",
        "- Всегда отталкивайся прежде всего от живых слов автора в текущей реплике, "
        "переводя их в конкретный зрительный образ кадра.",
    ])
    return "\n".join(lines)


def format_palace_resonances_card(
    resonances: list[dict[str, Any]],
    topic: str = "",
) -> str:
    """Форматирует визуальную карточку резонансов Дворца Памяти для Telegram."""
    topic_esc = safe_html_format(topic) if topic else "Арт-проект"

    if not resonances:
        return (
            f"🏛 <b>Дворец Памяти • Ассоциативные мосты</b>\n"
            f"<i>Тема: «{topic_esc}»</i>\n\n"
            "В чертогах Дворца пока не найдено прямых записей по этой теме. "
            "Арт-директор опирается на визуальные архетипы и чистую интуицию."
        )

    lines = [
        "🏛 <b>Дворец Памяти • Ассоциативные мосты</b>",
        f"<i>Тема: «{topic_esc}»</i>\n",
        "Мысли, сны и заметки из твоих чертогов, резонирующие с этой темой:\n",
    ]

    for idx, r in enumerate(resonances, start=1):
        title = safe_html_format(str(r.get("title", f"Запись #{idx}")))
        source = safe_html_format(str(r.get("source", "Дворец")))
        snippet = safe_html_format(str(r.get("snippet", "")))

        lines.append(f"{idx}. <b>{title}</b> <i>[{source}]</i>")
        lines.append(f"<blockquote>{snippet}</blockquote>\n")

    lines.append(
        "💡 <i>Арт-директор учитывает этот внутренний контекст при поиске метафор кадра.</i>"
    )
    return "\n".join(lines)


def get_or_find_session_resonances(
    session: Any,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Извлекает кэшированные резонансы из сессии или выполняет поиск с сохранением."""
    if not hasattr(session, "tech_preferences"):
        return []

    cached = session.tech_preferences.get("palace_resonances")
    if isinstance(cached, list):
        return cached

    user_id = getattr(session, "user_id", None)
    topic = getattr(session, "topic", "")
    resonances = find_palace_resonances(topic=topic, user_id=user_id, limit=limit)

    session.tech_preferences["palace_resonances"] = resonances
    try:
        from services.copilot_session import get_copilot_manager

        get_copilot_manager().save_session(session)
    except Exception as exc:
        logger.debug("[PALACE_BRIDGE] Failed to save session with resonances: %s", exc)

    return resonances
