from aiogram import Bot, Dispatcher
from cachetools import TTLCache

from config import ALLOWED_IDS, API_TOKEN


# Кэши для временных состояний
photo_delete_cache: TTLCache[str, str] = TTLCache(maxsize=500, ttl=300)
pending_wing_search: TTLCache[int, str] = TTLCache(maxsize=100, ttl=60)
sync_counter: TTLCache[int, int] = TTLCache(maxsize=100, ttl=3600)
sync_in_progress: TTLCache[int, bool] = TTLCache(maxsize=100, ttl=60)
yt_waiting_url: TTLCache[int, str] = TTLCache(maxsize=50, ttl=60)
yt_quality_url: TTLCache[int, str] = TTLCache(maxsize=50, ttl=120)
yt_audio_cache: TTLCache[str, dict] = TTLCache(maxsize=50, ttl=3600)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
logger = None  # will be set by init_bot


def set_logger(log):
    global logger
    logger = log


async def security_middleware(handler, event, data):
    uid = None
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

    if uid and uid not in ALLOWED_IDS:
        if logger:
            logger.warning(f"[SECURITY] Blocked user: {uid}")
        return None
    return await handler(event, data)


def init_bot(log):
    global logger
    logger = log
    dp.message.middleware(security_middleware)
    dp.callback_query.middleware(security_middleware)
    return bot, dp
