import os
import json
import re
import logging
from datetime import datetime
from typing import List, Dict

logger = logging.getLogger("MemoryService")


def _memory_dir() -> str:
    from config import DATA_DIR
    d = os.path.join(DATA_DIR, "memory_store")
    os.makedirs(d, exist_ok=True)
    return d


def _memory_path(user_id: int) -> str:
    return os.path.join(_memory_dir(), f"mem_{user_id}.json")


def _load_memories(user_id: int) -> List[Dict]:
    path = _memory_path(user_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def _save_memories(user_id: int, memories: List[Dict]):
    path = _memory_path(user_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(memories, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"[MEMORY] Save error: {e}")


def retrieve_facts(query: str, user_id: int, max_results: int = 5) -> List[str]:
    memories = _load_memories(user_id)
    if not memories or not query:
        return []

    words = set(re.findall(r'(?ui)[\wа-яё]+', query))
    if not words:
        return []

    scored = []
    for m in memories:
        fact_text = m.get("fact", "")
        if not fact_text:
            continue
        score = sum(1 for w in words if w.lower() in fact_text.lower())
        if score > 0:
            priority = m.get("priority", 0)
            access = m.get("access_count", 0)
            scored.append((score + priority * 0.3, access, fact_text))

    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [f[2] for f in scored[:max_results]]


def get_memory_context(query: str, user_id: int) -> str:
    facts = retrieve_facts(query, user_id)
    if not facts:
        return ""
    return "📌 Долговременные факты (из предыдущих диалогов):\n" + "\n".join(
        f"• {f}" for f in facts
    )


async def extract_and_store_facts(user_id: int, user_query: str, ai_answer: str):
    try:
        facts = await _extract_facts(user_query, ai_answer)
        if not facts:
            return
        memories = _load_memories(user_id)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        for fact in facts:
            memories.append({
                "id": f"mem_{ts}_{hash(fact) % 10000:04d}",
                "timestamp": datetime.now().isoformat(),
                "fact": fact,
                "source_query": user_query[:200],
                "priority": 0,
                "access_count": 0,
            })
        _save_memories(user_id, memories[-500:])
        logger.info(f"[MEMORY] Stored {len(facts)} facts for user {user_id}")
    except Exception as e:
        logger.error(f"[MEMORY] extract error: {e}", exc_info=True)


async def _extract_facts(user_query: str, ai_answer: str) -> List[str]:
    from services.ai_engine import get_ai_response_async, get_current_ai

    prompt = (
        "Extract 1-3 key factual statements from this exchange "
        "that are worth remembering long-term. "
        "Be specific and concrete. "
        "Return ONLY a JSON array of strings, e.g. [\"fact 1\", \"fact 2\"]. "
        "No other text.\n\n"
        f"User: {user_query[:500]}\n"
        f"AI: {ai_answer[:1000]}"
    )

    engine, model = get_current_ai()
    result = await get_ai_response_async(
        engine, model,
        [{"role": "user", "content": prompt}],
        context="",
        user_query="",
    )

    match = re.search(r'\[.*?\]', result, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except:
            pass
    return []
