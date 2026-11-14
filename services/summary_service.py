"""services/summary_service.py — единая генерация summary для чатов и заметок.

Режимы сохраняют осознанные различия:
- CHAT: краткое резюме диалога по последним 20 сообщениям, с учётом
  предыдущего саммари, системная инструкция, ограничение 50 слов;
- CHAT_PERIODIC: фоновое саммари по последним 15 сообщениям, user-инструкция,
  ограничение 40 слов;
- INSIGHT: краткое саммари одного ответа для сохранения инсайта/исследования;
- ROOM: структурированное саммари всех записей комнаты дворца.
"""

from enum import Enum

from services.ai_engine import call_ai_async
from services.prompts import get_summary_prompt


class SummaryMode(Enum):
    CHAT = "chat"
    CHAT_PERIODIC = "chat_periodic"
    INSIGHT = "insight"
    ROOM = "room"


def _chat_prompt(
    messages: list[dict],
    existing_summary: str,
    *,
    limit: int,
    with_context: bool,
) -> str:
    dialog_slice = "\n".join(
        f"{m['role']}: {m['content']}" for m in messages[-limit:]
    )
    context_prefix = ""
    if (
        with_context
        and existing_summary
        and len(existing_summary.strip()) > 10
    ):
        context_prefix = (
            f"ПРЕДЫДУЩЕЕ САММАРИ:\n{existing_summary}\n\nТЕКУЩИЙ ДИАЛОГ:\n"
        )
    return get_summary_prompt(
        dialog_slice=dialog_slice, context_prefix=context_prefix,
    )


def _room_messages(wing: str, room: str, notes_text: str) -> list[dict]:
    step1_prompt = (
        f"Ниже — все записи из комнаты {wing}/{room}.\n"
        "Сделай две вещи:\n"
        "1) Для каждой записи напиши краткую саммари (2–3 предложения).\n"
        "2) После этого составь ОБЩУЮ структурированную саммари по всей комнате — "
        "сгруппируй темы, выдели главное, свяжи между собой.\n\n"
        f"Записи комнаты:\n{notes_text}"
    )
    return [
        {
            "role": "system",
            "content": (
                "Ты — аналитик. Составляешь саммари по заметкам. "
                "Отвечай на русском языке."
            ),
        },
        {"role": "user", "content": step1_prompt},
    ]


def _truncate(summary: str, max_words: int) -> str:
    words = summary.split()
    if len(words) > max_words:
        return " ".join(words[:max_words]) + "..."
    return summary


async def generate_summary(
    mode: SummaryMode,
    *,
    engine: str,
    model: str,
    messages: list[dict] | None = None,
    existing_summary: str = "",
    text: str = "",
    wing: str = "",
    room: str = "",
) -> str:
    """Генерирует summary в выбранном режиме.

    Ошибки AI-вызова пробрасываются вызывающему: режимы по-разному решают,
    показать ошибку пользователю, вернуть fallback или пропустить обновление.
    """
    if mode in (SummaryMode.CHAT, SummaryMode.CHAT_PERIODIC):
        if not messages:
            return "Чат пуст."

        if mode is SummaryMode.CHAT:
            prompt = _chat_prompt(
                messages, existing_summary, limit=20, with_context=True,
            )
            ai_messages = [{"role": "system", "content": prompt}]
            max_words = 50
        else:
            prompt = _chat_prompt(
                messages, "", limit=15, with_context=False,
            )
            ai_messages = [{"role": "user", "content": prompt}]
            max_words = 40

        summary = await call_ai_async(engine, model, ai_messages)
        summary = _truncate(summary, max_words)
        return summary.strip() if mode is SummaryMode.CHAT else summary

    if mode is SummaryMode.INSIGHT:
        summary = await call_ai_async(
            engine,
            model,
            [{"role": "user", "content": f"Суммаризируй: {text}"}],
        )
        return summary

    if mode is SummaryMode.ROOM:
        return await call_ai_async(engine, model, _room_messages(wing, room, text))

    raise ValueError(f"Неизвестный режим summary: {mode}")
