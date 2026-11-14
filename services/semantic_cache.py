"""semantic_cache.py
Кэш AI-ответов с семантическим сравнением запросов.
Позволяет избежать повторных API-вызовов на похожие вопросы.

Кэш контекстный: без chat_id, wing, model и prompt_version запись не
создаётся и не ищется. Это исключает попадания между чатами, крыльями,
моделями и режимами промпта.
"""

import logging
import time
from difflib import SequenceMatcher
from threading import RLock

logger = logging.getLogger("SemanticCache")

ScopeKey = tuple[str, str, str, str, str]
EntryKey = tuple[ScopeKey, str]


class SemanticCacheEntry:
    __slots__ = ("hits", "query", "response", "scope", "timestamp")

    def __init__(
        self,
        query: str,
        response: str,
        scope: ScopeKey | None = None,
    ):
        self.query = query
        self.response = response
        self.scope = scope
        self.timestamp = time.time()
        self.hits = 1


class SemanticCache:
    def __init__(self, ttl: int = 300, max_size: int = 200, threshold: float = 0.82):
        self.ttl = ttl
        self.max_size = max_size
        self.threshold = threshold
        self._entries: dict[EntryKey, SemanticCacheEntry] = {}
        self._lock = RLock()

    def _normalize(self, text: str) -> str:
        return " ".join(text.lower().split())

    def _similarity(self, a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio()

    def _scope_key(
        self,
        *,
        chat_id: int | str | None,
        wing: str | None,
        model: str | None,
        prompt_version: str | None,
        mode: str | None,
    ) -> ScopeKey | None:
        if chat_id is None:
            return None

        chat_key = str(chat_id).strip()
        wing_key = (wing or "").strip().casefold()
        model_key = (model or "").strip()
        prompt_key = (prompt_version or "").strip()
        mode_key = (mode or "").strip().casefold()

        # Неполный контекст нельзя заменять глобальным ключом: лучше
        # промах, чем ответ из другого чата/крыла/модели.
        if not chat_key or not wing_key or not model_key or not prompt_key:
            return None
        return (chat_key, wing_key, model_key, prompt_key, mode_key)

    def _evict_expired(self):
        now = time.time()
        expired = [
            key for key, entry in self._entries.items()
            if now - entry.timestamp > self.ttl
        ]
        for key in expired:
            del self._entries[key]
        if expired:
            logger.debug(f"Evicted {len(expired)} expired cache entries")

    def get(
        self,
        query: str,
        *,
        chat_id: int | str | None = None,
        wing: str | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
        mode: str | None = "",
    ) -> str | None:
        scope = self._scope_key(
            chat_id=chat_id,
            wing=wing,
            model=model,
            prompt_version=prompt_version,
            mode=mode,
        )
        if scope is None or not query:
            return None

        normalized = self._normalize(query)
        with self._lock:
            self._evict_expired()

            best_match = None
            best_score = 0.0

            for (entry_scope, entry_query), entry in self._entries.items():
                if entry_scope != scope:
                    continue
                score = self._similarity(normalized, entry_query)
                if score > best_score:
                    best_score = score
                    best_match = entry

            if best_match and best_score >= self.threshold:
                best_match.hits += 1
                best_match.timestamp = time.time()
                logger.info(
                    f"[CACHE_HIT] similarity={best_score:.3f} "
                    f"hits={best_match.hits} chat={scope[0]} "
                    f"wing={scope[1]} model={scope[2]} mode={scope[4]} "
                    f"query='{query[:60]}'",
                )
                return best_match.response

        return None

    def set(
        self,
        query: str,
        response: str,
        *,
        chat_id: int | str | None = None,
        wing: str | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
        mode: str | None = "",
    ):
        if not query or not response:
            return

        scope = self._scope_key(
            chat_id=chat_id,
            wing=wing,
            model=model,
            prompt_version=prompt_version,
            mode=mode,
        )
        if scope is None:
            return

        normalized = self._normalize(query)
        if not normalized:
            return

        key = (scope, normalized)
        with self._lock:
            self._evict_expired()

            if key not in self._entries and len(self._entries) >= self.max_size:
                oldest = min(
                    self._entries,
                    key=lambda entry_key: self._entries[entry_key].timestamp,
                )
                del self._entries[oldest]

            self._entries[key] = SemanticCacheEntry(normalized, response, scope)

    def invalidate(self, query: str = ""):
        with self._lock:
            if query:
                normalized = self._normalize(query)
                keys = [
                    key for key in self._entries
                    if key[1] == normalized
                ]
                for key in keys:
                    del self._entries[key]
            else:
                self._entries.clear()
                logger.info("Semantic cache cleared")

    def invalidate_model(self, model: str) -> int:
        """Удаляет все записи указанной модели; возвращает их количество."""
        model_key = (model or "").strip()
        if not model_key:
            return 0

        with self._lock:
            keys = [
                key for key, entry in self._entries.items()
                if entry.scope is not None and entry.scope[2] == model_key
            ]
            for key in keys:
                del self._entries[key]

        if keys:
            logger.info(
                "Semantic cache invalidated for model %s (%d entries)",
                model_key,
                len(keys),
            )
        return len(keys)

    @property
    def stats(self) -> dict:
        with self._lock:
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
