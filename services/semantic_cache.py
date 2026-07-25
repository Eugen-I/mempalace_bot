"""semantic_cache.py
Кэш AI-ответов с семантическим сравнением запросов.
Позволяет избежать повторных API-вызовов на похожие вопросы.
"""

import logging
import time
from difflib import SequenceMatcher

logger = logging.getLogger("SemanticCache")


class SemanticCacheEntry:
    __slots__ = ("hits", "query", "response", "timestamp")

    def __init__(self, query: str, response: str):
        self.query = query
        self.response = response
        self.timestamp = time.time()
        self.hits = 1


class SemanticCache:
    def __init__(self, ttl: int = 300, max_size: int = 200, threshold: float = 0.82):
        self.ttl = ttl
        self.max_size = max_size
        self.threshold = threshold
        self._entries: dict[str, SemanticCacheEntry] = {}

    def _normalize(self, text: str) -> str:
        return " ".join(text.lower().split())

    def _similarity(self, a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio()

    def _evict_expired(self):
        now = time.time()
        expired = [k for k, v in self._entries.items() if now - v.timestamp > self.ttl]
        for k in expired:
            del self._entries[k]
        if expired:
            logger.debug(f"Evicted {len(expired)} expired cache entries")

    def get(self, query: str) -> str | None:
        self._evict_expired()
        normalized = self._normalize(query)

        best_match = None
        best_score = 0.0

        for key, entry in self._entries.items():
            score = self._similarity(normalized, key)
            if score > best_score:
                best_score = score
                best_match = entry

        if best_match and best_score >= self.threshold:
            best_match.hits += 1
            best_match.timestamp = time.time()
            logger.info(
                f"[CACHE_HIT] similarity={best_score:.3f} "
                f"hits={best_match.hits} query='{query[:60]}'",
            )
            return best_match.response

        return None

    def set(self, query: str, response: str):
        if not query or not response:
            return
        self._evict_expired()
        normalized = self._normalize(query)

        if len(self._entries) >= self.max_size:
            oldest = min(self._entries.keys(), key=lambda k: self._entries[k].timestamp)
            del self._entries[oldest]

        self._entries[normalized] = SemanticCacheEntry(normalized, response)

    def invalidate(self, query: str = ""):
        if query:
            self._entries.pop(self._normalize(query), None)
        else:
            self._entries.clear()
            logger.info("Semantic cache cleared")

    @property
    def stats(self) -> dict:
        self._evict_expired()
        total_hits = sum(e.hits for e in self._entries.values())
        return {
            "size": len(self._entries),
            "total_hits": total_hits,
            "ttl_seconds": self.ttl,
            "threshold": self.threshold,
        }


_cache: SemanticCache | None = None


def get_cache() -> SemanticCache:
    global _cache
    if _cache is None:
        _cache = SemanticCache()
    return _cache


def reset_cache():
    global _cache
    _cache = None
