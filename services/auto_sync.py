import logging
from services.palace_bridge import export_chat_verbatim, sync_to_palace

logger = logging.getLogger("AutoSync")

async def auto_sync_chat(uid: int, chat_name: str, chat_path: str):
    try:
        exported = export_chat_verbatim(chat_path, chat_name)
        if not exported:
            return
        result = await sync_to_palace(exported)
        logger.info(f"[AUTO_SYNC] User {uid}: {result}")
    except Exception as e:
        logger.error(f"[AUTO_SYNC] User {uid}: {e}", exc_info=True)
