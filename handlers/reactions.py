import logging
import os
from datetime import datetime

from aiogram import Router
from aiogram.types import MessageReactionUpdated, ReactionTypeEmoji

from config import ALLOWED_IDS, INSIGHTS_DIR, NOTES_DIR, RESEARCH_DIR
from services.ai_cache import _ai_msg_cache

logger = logging.getLogger("Reactions")
router = Router()


@router.message_reaction()
async def handle_ai_reaction(event: MessageReactionUpdated):
    """Обрабатывает реакции на сообщения бота и сохраняет контент в папки."""
    if not event.user or event.user.id not in ALLOWED_IDS:
        return
    if not event.new_reaction:
        return

    def normalize_emoji(e: str) -> str:
        return (
            e.replace("\ufe0f", "")
            .replace("\u200d", "")
            .replace("\u2642", "")
            .replace("\u2640", "")
            .strip()
        )

    action_map = {
        "👍": "note",
        "❤": "insight",
        "🤷": "research",
    }

    action = None
    for react in event.new_reaction:
        if isinstance(react, ReactionTypeEmoji):
            norm = normalize_emoji(react.emoji)
            if norm in action_map:
                action = action_map[norm]
                logger.info(
                    f"[REACTION] Detected {react.emoji} -> normalized: {norm} -> action: {action}",
                )
                break

    if not action:
        return

    chat_id = event.chat.id
    msg_id = event.message_id
    ai_text = _ai_msg_cache.get(chat_id, {}).get(msg_id)

    if not ai_text:
        await event.bot.send_message(
            chat_id, "⚠️ Сообщение не найдено в кэше. Используйте !! или ? вручную.",
        )
        return

    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        if action == "note":
            fn = f"nt_react_{ts}.txt"
            path = os.path.join(NOTES_DIR, fn)
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"[Реакция 👍]\n{ai_text}")
            await event.bot.send_message(
                chat_id, f"💾 Сохранено в `my_notes`: `{fn}`", parse_mode="Markdown",
            )

        elif action == "insight":
            fn = f"ext_react_{ts}.txt"
            path = os.path.join(INSIGHTS_DIR, fn)
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"!! [Реакция ❤️]\nИсточник: msg_{msg_id}\nИТОГ:\n{ai_text}")
            await event.bot.send_message(
                chat_id, f"💡 Сохранено в `Insights`: `{fn}`", parse_mode="Markdown",
            )

        elif action == "research":
            fn = f"ext_react_{ts}.txt"
            path = os.path.join(RESEARCH_DIR, fn)
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"? [Реакция 🤷‍♂️]\nИсточник: msg_{msg_id}\nИТОГ:\n{ai_text}")
            await event.bot.send_message(
                chat_id, f"🔍 Сохранено в `Research`: `{fn}`", parse_mode="Markdown",
            )

    except Exception as e:
        logger.error(f"[REACTION_SAVE] Error: {e}", exc_info=True)
        await event.bot.send_message(chat_id, f"❌ Ошибка сохранения: {str(e)[:100]}")
