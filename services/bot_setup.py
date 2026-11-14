from typing import cast

from aiogram import Bot, Dispatcher
from cachetools import TTLCache

from config import ALLOWED_IDS, API_TOKEN

# Кэши для временных состояний
photo_delete_cache: TTLCache[str, str] = TTLCache(maxsize=500, ttl=300)
pending_wing_search: TTLCache[int, str] = TTLCache(maxsize=100, ttl=60)
pending_room_filter: TTLCache[int, str] = TTLCache(maxsize=100, ttl=120)
pending_web_search: TTLCache[int, bool] = TTLCache(maxsize=100, ttl=120)
sync_counter: TTLCache[int, int] = TTLCache(maxsize=100, ttl=3600)
sync_in_progress: TTLCache[int, bool] = TTLCache(maxsize=100, ttl=60)
yt_waiting_url: TTLCache[int, str] = TTLCache(maxsize=50, ttl=60)
yt_quality_url: TTLCache[int, str] = TTLCache(maxsize=50, ttl=120)
yt_audio_cache: TTLCache[str, dict] = TTLCache(maxsize=50, ttl=3600)

# Garmin wizard state (profile draft, free-text prompts, last plan id)
garmin_profile_draft: TTLCache[int, dict] = TTLCache(maxsize=100, ttl=1800)
garmin_text_state: TTLCache[int, str] = TTLCache(maxsize=100, ttl=600)
garmin_last_plan: TTLCache[int, str] = TTLCache(maxsize=100, ttl=86400)

bot = Bot(token=cast(str, API_TOKEN))
dp = Dispatcher()
logger = None  # will be set by init_bot


def set_logger(log):
    global logger
    logger = log


async def security_middleware(handler, event, data):
    uid = None
    # Standard message and callback query
    if hasattr(event, "from_user") and event.from_user:
        uid = event.from_user.id
    elif hasattr(event, "message") and event.message and event.message.from_user:
        uid = event.message.from_user.id
    elif (
        hasattr(event, "callback_query")
        and event.callback_query
        and event.callback_query.from_user
    ):
        uid = event.callback_query.from_user.id
    # message_reaction events have `user` not `from_user`
    elif hasattr(event, "user") and event.user:
        uid = event.user.id
    # channel_post events have `sender_chat`
    elif hasattr(event, "sender_chat") and event.sender_chat:
        uid = event.sender_chat.id

    if uid and uid not in ALLOWED_IDS:
        if logger:
            logger.warning(f"[SECURITY] Blocked user: {uid}")
        return None
    # Если uid не определился (неизвестный тип события) — пропускаем (как было)
    # но логируем предупреждение для аудита
    if uid is None:
        if logger:
            event_type = type(event).__name__
            logger.warning(
                f"[SECURITY] Event without identifiable user (allowed): {event_type}"
            )
    return await handler(event, data)


def init_bot(log):
    global logger
    logger = log
    dp.message.middleware(security_middleware)
    dp.callback_query.middleware(security_middleware)
    return bot, dp
