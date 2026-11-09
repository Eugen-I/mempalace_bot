"""services/copilot_engine.py — Движок Сократического диалога и арт-директуры копайлота.

Отвечает за:
- Живое соавторство (Сократический диалог, 1-2 острых вопроса за раз)
- Выявление скрытых смыслов, эмоционального ядра и визуальных парадоксов
- Автоматическую суммаризацию обсуждения в структурированное резюме концепта
"""

from __future__ import annotations

import logging
from typing import Any

from services.ai_engine import get_ai_response_async, get_current_ai
from services.copilot_session import CopilotSession, get_copilot_manager

logger = logging.getLogger("CopilotEngine")

COPILOT_SOCRATIC_SYSTEM = """Ты — опытный арт-директор и куратор визуальных искусств.
Твоя цель — помочь фотографу глубоко осмыслить тему арт-проекта через живой диалог.

ПРАВИЛА ДИАЛОГА:
1. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО заваливать фотографа длинным списком вопросов или анкетой.
2. В каждом ответе сначала кратко (1–2 фразы) откликнись на мысль автора: выдели метафору.
3. Затем задай ровно ОДИН (максимум два) точных, глубоких Сократических вопроса.
   Темы для исследования:
   - Эмоциональное зерно (тревога, покой, оцепенение, катарсис?).
   - Пространство и свет (бетон, туман, полумрак заброшенного дома, зеркала?).
   - Герой и телесность (одинокая фигура, только руки/детали, маска, силуэт?).
   - Скрытый парадокс (что в этой сцене ломает обыденность?).
4. Пиши лаконично (3–5 предложений на весь ответ), без клише, живым художественным языком.
5. Общайся на русском языке.
"""

COPILOT_SUMMARIZE_SYSTEM = """Ты — арт-куратор.
Извлеки из диалога фотографа и арт-директора суть и сформируй структурированное резюме.

ФОРМАТ ВЫВОДА (кратко, тезисно, без воды):
🎯 <b>Концептуальный конфликт:</b> [главная идея и психологический нерв]
💡 <b>Ключевая метафора:</b> [визуальный образ / символ]
🏛 <b>Пространство и свет:</b> [локация, качество освещения, атмосфера]
👤 <b>Герой / Объект:</b> [кто или что в кадре, телесность, пластика]
"""


def build_socratic_messages(
    topic: str, dialogue_history: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Формирует список сообщений для языковой модели Сократического диалога."""
    system_content = f"{COPILOT_SOCRATIC_SYSTEM}\n\nТЕМА ПРОЕКТА: «{topic}»."
    messages: list[dict[str, str]] = [{"role": "system", "content": system_content}]

    for entry in dialogue_history:
        role = entry.get("role", "user")
        content = entry.get("content", "").strip()
        if content:
            messages.append({"role": role, "content": content})

    return messages


async def generate_socratic_reply(session: CopilotSession, user_input: str) -> str:
    """Обрабатывает реплику пользователя и генерирует следующий вопрос/мысль арт-директора."""
    session.add_user_message(user_input)
    messages = build_socratic_messages(session.topic, session.dialogue_history)

    engine, model = get_current_ai()
    sampling = {"temperature": 0.75, "max_tokens": 500}

    try:
        raw = await get_ai_response_async(engine, model, messages, sampling=sampling)

        # Авто-fallback на локальный Qwen при ошибке квоты или сети
        is_err = (
            raw.startswith("❌")
            or "429" in raw
            or "quota" in raw.lower()
            or "resource_exhausted" in raw.lower()
        )
        if is_err and engine != "qwen":
            logger.warning(
                "[COPILOT] Engine %s failed. Fallback to local Ollama (qwen2.5:7b)...", engine,
            )
            engine, model = "qwen", "qwen2.5:7b"
            raw = await get_ai_response_async(engine, model, messages, sampling=sampling)

        reply = raw.strip()
    except Exception as exc:
        logger.error("[COPILOT] Socratic reply generation failed: %s", exc)
        reply = (
            "Это очень точный образ. Давай подумаем о пространстве: "
            "где физически разворачивается эта сцена — на открытом воздухе или в замкнутой среде?"
        )

    session.add_assistant_message(reply)
    get_copilot_manager().save_session(session)
    return reply


async def summarize_creative_dialogue(session: CopilotSession) -> str:
    """Суммаризирует диалог сессии в структурированное резюме."""
    if not session.dialogue_history:
        session.summary = f"🎯 <b>Концептуальный конфликт:</b> Исследование темы «{session.topic}»."
        get_copilot_manager().save_session(session)
        return session.summary

    # Формируем стенограмму диалога
    transcript_lines = []
    for m in session.dialogue_history:
        speaker = "Фотограф" if m.get("role") == "user" else "Арт-директор"
        transcript_lines.append(f"{speaker}: {m.get('content', '')}")
    transcript = "\n".join(transcript_lines)

    prompt = (
        f"Тема: «{session.topic}»\n\n"
        f"Стенограмма обсуждения:\n{transcript}\n\n"
        "Сформируй четкое, емкое концептуальное резюме по заданной структуре."
    )

    messages = [
        {"role": "system", "content": COPILOT_SUMMARIZE_SYSTEM},
        {"role": "user", "content": prompt},
    ]

    engine, model = get_current_ai()
    sampling = {"temperature": 0.4, "max_tokens": 600}

    try:
        raw = await get_ai_response_async(engine, model, messages, sampling=sampling)
        if raw.startswith("❌") and engine != "qwen":
            engine, model = "qwen", "qwen2.5:7b"
            raw = await get_ai_response_async(engine, model, messages, sampling=sampling)
        summary = raw.strip()
    except Exception as exc:
        logger.error("[COPILOT] summarize dialogue failed: %s", exc)
        summary = (
            f"🎯 <b>Концептуальный конфликт:</b> Исследование темы «{session.topic}».\n"
            "💡 <b>Ключевая метафора:</b> Поиск визуального нерва через свет и пластику кадра."
        )

    session.summary = summary
    get_copilot_manager().save_session(session)
    return summary


async def start_copilot_discussion(session: CopilotSession) -> str:
    """Генерирует первое вступительное слово и первый Сократический вопрос арт-директора."""
    prompt = (
        f"Фотограф выбрал тему для арт-проекта: «{session.topic}».\n"
        "Выступи как вдохновляющий арт-директор: в 1–2 фразах подчеркни потенциал темы "
        "и задай первый вопрос, определяющий эмоциональное ядро или конфликт кадра."
    )
    messages = [
        {"role": "system", "content": COPILOT_SOCRATIC_SYSTEM},
        {"role": "user", "content": prompt},
    ]

    engine, model = get_current_ai()
    sampling = {"temperature": 0.75, "max_tokens": 400}

    try:
        raw = await get_ai_response_async(engine, model, messages, sampling=sampling)
        if raw.startswith("❌") and engine != "qwen":
            engine, model = "qwen", "qwen2.5:7b"
            raw = await get_ai_response_async(engine, model, messages, sampling=sampling)
        opening = raw.strip()
    except Exception as exc:
        logger.error("[COPILOT] start discussion failed: %s", exc)
        opening = (
            f"Тема «{session.topic}» открывает простор для визуального поиска. "
            "Какое чувство должен вызвать проект: оцепенение, меланхолию или освобождение?"
        )

    session.add_assistant_message(opening)
    get_copilot_manager().save_session(session)
    return opening
