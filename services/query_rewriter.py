"""services/query_rewriter.py — Переформулирование поисковых запросов (Query Rewriting).

Используется перед вызовом RAG/OmniSearch во Дворце памяти: преобразует
разговорные фразы с местоимениями ("А что мы решили насчёт этого?", "Как там было с БД?")
в чёткие, самостоятельные поисковые запросы на основе недавней истории чата.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger("QueryRewriter")

# Маркеры разговорных отсылок, требующих контекста
_CONVERSATIONAL_RE = re.compile(
    r"\b(это|этот|эта|эти|этого|этой|этому|этим|этих|этими|этом|"
    r"то|тот|та|те|того|той|тому|тем|тех|теми|том|"
    r"он|она|оно|они|его|него|ее|её|нее|неё|их|них|ему|нему|ей|ней|им|ним|ими|ними|нем|нём|"
    r"здесь|тут|там|туда|оттуда|отсюда|тогда|сейчас|вчера|сегодня|ранее|раньше|"
    r"еще|ещё|также|тоже|почему|как|подробнее|поясни|расскажи|напомни)\b",
    re.IGNORECASE,
)

REWRITE_SYSTEM_PROMPT = """Ты — модуль поиска по базе знаний (RAG).
Твоя задача — переформулировать вопрос с учётом диалога в чёткий поисковый запрос.

Правила:
1. Замени местоимения и отсылки конкретными терминами и названиями из контекста.
2. Сохраняй ключевые слова, технологии, имена файлов и компонентов.
3. Верни ТОЛЬКО одну строку: поисковый запрос без кавычек, вводных слов и пояснений.
4. Если вопрос уже понятен сам по себе без контекста, верни его без изменений.
"""


def is_conversational_query(query: str) -> bool:
    """Проверяет, содержит ли запрос разговорные отсылки или местоимения."""
    if not query or not query.strip():
        return False
    clean = query.strip()
    words = clean.split()
    if len(words) <= 3:
        return True
    return bool(_CONVERSATIONAL_RE.search(clean))


async def rewrite_query_for_search(
    query: str,
    recent_messages: list[dict] | None = None,
    timeout: float = 3.0,
    engine: str | None = None,
    model: str | None = None,
) -> str:
    """Переформулирует запрос пользователя с учётом недавней истории сообщений.

    Если истории нет, запрос самодостаточен или произошла ошибка/таймаут —
    возвращается исходный `query`.
    """
    clean_q = (query or "").strip()
    if not clean_q or not recent_messages:
        return clean_q

    # Если запрос достаточно длинный и не содержит отсылок — не тратим время на вызов ИИ
    if not is_conversational_query(clean_q):
        return clean_q

    # Собираем контекст из последних сообщений (до 4 реплик)
    dialog_turns: list[str] = []
    for m in recent_messages[-4:]:
        role = m.get("role", "user")
        content = (m.get("content") or "").strip()
        if content:
            # Ограничиваем длину реплики для экономии контекста
            snippet = content[:300].replace("\n", " ")
            label = "Пользователь" if role == "user" else "Ассистент"
            dialog_turns.append(f"{label}: {snippet}")

    if not dialog_turns:
        return clean_q

    history_text = "\n".join(dialog_turns)
    user_prompt = (
        f"История диалога:\n{history_text}\n\n"
        f"Текущий вопрос: {clean_q}\n\n"
        "Сформируй самостоятельный поисковый запрос (только текст запроса):"
    )

    try:
        from services.ai_engine import call_ai_async, get_current_ai

        if engine is None or model is None:
            cur_engine, cur_model = get_current_ai()
            engine = engine or cur_engine
            model = model or cur_model

        messages = [
            {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        raw = await call_ai_async(
            engine=engine,
            model=model,
            messages=messages,
            timeout=timeout,
            sampling={"timeout": timeout},
        )

        rewritten = raw.strip().strip('"\'«»`')
        # Если модель вернула ошибку (начинается с ❌ или 🧠) или пустую строку
        if not rewritten or rewritten.startswith("❌") or rewritten.startswith("🧠"):
            logger.debug("[QUERY_REWRITE] Model returned error/empty, using original query")
            return clean_q

        # Если первая строка содержит многострочный текст — берём первую строку
        lines = [line.strip() for line in rewritten.splitlines() if line.strip()]
        if lines:
            rewritten = lines[0].strip('"\'«»`')

        logger.info("[QUERY_REWRITE] '%s' -> '%s'", clean_q, rewritten)
        return rewritten

    except Exception as exc:
        logger.debug("[QUERY_REWRITE] Failed to rewrite query: %s", exc)
        return clean_q
