import asyncio
import logging
import time

from services.kv_store import get_kv_store

logger = logging.getLogger("ReminderScheduler")
REMINDER_NS = "reminders"

_scheduler_task: asyncio.Task | None = None


async def _run_scheduler(bot):
    logger.info("[REMINDER] Scheduler started")
    kv = get_kv_store()
    while True:
        try:
            now = time.time()
            keys = kv.keys(namespace=REMINDER_NS)
            for key in keys:
                data = kv.get(key, namespace=REMINDER_NS)
                if not data:
                    continue
                remind_at = data.get("remind_at", 0)
                if remind_at <= now:
                    text = data.get("text", "")
                    user_id = data.get("user_id", 0)
                    chat_id = data.get("chat_id", 0)
                    try:
                        from services.text_formatter import safe_html_format

                        await bot.send_message(
                            chat_id,
                            f"⏰ <b>Напоминание!</b>\n\n{safe_html_format(text)}",
                            parse_mode="HTML",
                        )
                        logger.info(f"[REMINDER] Sent to user {user_id}: {text[:50]}")
                    except Exception as e:
                        logger.warning(f"[REMINDER] Send failed for {user_id}: {e}")
                    kv.delete(key, namespace=REMINDER_NS)
        except Exception as e:
            logger.error(f"[REMINDER] Scheduler error: {e}", exc_info=True)
        await asyncio.sleep(30)


def start_scheduler(bot):
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(_run_scheduler(bot))


def stop_scheduler():
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        _scheduler_task = None
