_ai_msg_cache: dict[int, dict[int, str]] = {}


def cache_ai_response(chat_id: int, message_id: int, text: str):
    if chat_id not in _ai_msg_cache:
        _ai_msg_cache[chat_id] = {}
    _ai_msg_cache[chat_id][message_id] = text
    if len(_ai_msg_cache[chat_id]) > 50:
        oldest_id = min(_ai_msg_cache[chat_id].keys())
        del _ai_msg_cache[chat_id][oldest_id]


def get_ai_response(chat_id: int, message_id: int) -> str:
    return _ai_msg_cache.get(chat_id, {}).get(message_id, "")
