"""semantic_cache.py
Кэш AI-ответов с семантическим сравнением запросов.
Позволяет избежать повторных API-вызовов на похожие вопросы.
"""

import logging
import time
from difflib import SequenceMatcher

logger = logging.getLogger("SemanticCache")


from mutmut.mutation.trampoline import wrap_in_trampoline as _mutmut_mutated, MutantDict
mutants_xǁSemanticCacheEntryǁ__init____mutmut: MutantDict = {}  # type: ignore


class SemanticCacheEntry:
    __slots__ = ("hits", "query", "response", "timestamp")

    @_mutmut_mutated(mutants_xǁSemanticCacheEntryǁ__init____mutmut)
    def __init__(self, query: str, response: str):
        self.query = query
        self.response = response
        self.timestamp = time.time()
        self.hits = 1

    def xǁSemanticCacheEntryǁ__init____mutmut_orig(self, query: str, response: str):
        self.query = query
        self.response = response
        self.timestamp = time.time()
        self.hits = 1

    def xǁSemanticCacheEntryǁ__init____mutmut_1(self, query: str, response: str):
        self.query = None
        self.response = response
        self.timestamp = time.time()
        self.hits = 1

    def xǁSemanticCacheEntryǁ__init____mutmut_2(self, query: str, response: str):
        self.query = query
        self.response = None
        self.timestamp = time.time()
        self.hits = 1

    def xǁSemanticCacheEntryǁ__init____mutmut_3(self, query: str, response: str):
        self.query = query
        self.response = response
        self.timestamp = None
        self.hits = 1

    def xǁSemanticCacheEntryǁ__init____mutmut_4(self, query: str, response: str):
        self.query = query
        self.response = response
        self.timestamp = time.time()
        self.hits = None

    def xǁSemanticCacheEntryǁ__init____mutmut_5(self, query: str, response: str):
        self.query = query
        self.response = response
        self.timestamp = time.time()
        self.hits = 2

mutants_xǁSemanticCacheEntryǁ__init____mutmut['_mutmut_orig'] = SemanticCacheEntry.xǁSemanticCacheEntryǁ__init____mutmut_orig # type: ignore # mutmut generated
mutants_xǁSemanticCacheEntryǁ__init____mutmut['xǁSemanticCacheEntryǁ__init____mutmut_1'] = SemanticCacheEntry.xǁSemanticCacheEntryǁ__init____mutmut_1 # type: ignore # mutmut generated
mutants_xǁSemanticCacheEntryǁ__init____mutmut['xǁSemanticCacheEntryǁ__init____mutmut_2'] = SemanticCacheEntry.xǁSemanticCacheEntryǁ__init____mutmut_2 # type: ignore # mutmut generated
mutants_xǁSemanticCacheEntryǁ__init____mutmut['xǁSemanticCacheEntryǁ__init____mutmut_3'] = SemanticCacheEntry.xǁSemanticCacheEntryǁ__init____mutmut_3 # type: ignore # mutmut generated
mutants_xǁSemanticCacheEntryǁ__init____mutmut['xǁSemanticCacheEntryǁ__init____mutmut_4'] = SemanticCacheEntry.xǁSemanticCacheEntryǁ__init____mutmut_4 # type: ignore # mutmut generated
mutants_xǁSemanticCacheEntryǁ__init____mutmut['xǁSemanticCacheEntryǁ__init____mutmut_5'] = SemanticCacheEntry.xǁSemanticCacheEntryǁ__init____mutmut_5 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁ__init____mutmut: MutantDict = {}  # type: ignore
mutants_xǁSemanticCacheǁ_normalize__mutmut: MutantDict = {}  # type: ignore
mutants_xǁSemanticCacheǁ_similarity__mutmut: MutantDict = {}  # type: ignore
mutants_xǁSemanticCacheǁ_evict_expired__mutmut: MutantDict = {}  # type: ignore
mutants_xǁSemanticCacheǁget__mutmut: MutantDict = {}  # type: ignore
mutants_xǁSemanticCacheǁset__mutmut: MutantDict = {}  # type: ignore
mutants_xǁSemanticCacheǁinvalidate__mutmut: MutantDict = {}  # type: ignore


class SemanticCache:
    @_mutmut_mutated(mutants_xǁSemanticCacheǁ__init____mutmut)
    def __init__(self, ttl: int = 300, max_size: int = 200, threshold: float = 0.82):
        self.ttl = ttl
        self.max_size = max_size
        self.threshold = threshold
        self._entries: dict[str, SemanticCacheEntry] = {}
    def xǁSemanticCacheǁ__init____mutmut_orig(self, ttl: int = 300, max_size: int = 200, threshold: float = 0.82):
        self.ttl = ttl
        self.max_size = max_size
        self.threshold = threshold
        self._entries: dict[str, SemanticCacheEntry] = {}
    def xǁSemanticCacheǁ__init____mutmut_1(self, ttl: int = 301, max_size: int = 200, threshold: float = 0.82):
        self.ttl = ttl
        self.max_size = max_size
        self.threshold = threshold
        self._entries: dict[str, SemanticCacheEntry] = {}
    def xǁSemanticCacheǁ__init____mutmut_2(self, ttl: int = 300, max_size: int = 201, threshold: float = 0.82):
        self.ttl = ttl
        self.max_size = max_size
        self.threshold = threshold
        self._entries: dict[str, SemanticCacheEntry] = {}
    def xǁSemanticCacheǁ__init____mutmut_3(self, ttl: int = 300, max_size: int = 200, threshold: float = 1.8199999999999998):
        self.ttl = ttl
        self.max_size = max_size
        self.threshold = threshold
        self._entries: dict[str, SemanticCacheEntry] = {}
    def xǁSemanticCacheǁ__init____mutmut_4(self, ttl: int = 300, max_size: int = 200, threshold: float = 0.82):
        self.ttl = None
        self.max_size = max_size
        self.threshold = threshold
        self._entries: dict[str, SemanticCacheEntry] = {}
    def xǁSemanticCacheǁ__init____mutmut_5(self, ttl: int = 300, max_size: int = 200, threshold: float = 0.82):
        self.ttl = ttl
        self.max_size = None
        self.threshold = threshold
        self._entries: dict[str, SemanticCacheEntry] = {}
    def xǁSemanticCacheǁ__init____mutmut_6(self, ttl: int = 300, max_size: int = 200, threshold: float = 0.82):
        self.ttl = ttl
        self.max_size = max_size
        self.threshold = None
        self._entries: dict[str, SemanticCacheEntry] = {}
    def xǁSemanticCacheǁ__init____mutmut_7(self, ttl: int = 300, max_size: int = 200, threshold: float = 0.82):
        self.ttl = ttl
        self.max_size = max_size
        self.threshold = threshold
        self._entries: dict[str, SemanticCacheEntry] = None

    @_mutmut_mutated(mutants_xǁSemanticCacheǁ_normalize__mutmut)
    def _normalize(self, text: str) -> str:
        return " ".join(text.lower().split())

    def xǁSemanticCacheǁ_normalize__mutmut_orig(self, text: str) -> str:
        return " ".join(text.lower().split())

    def xǁSemanticCacheǁ_normalize__mutmut_1(self, text: str) -> str:
        return " ".join(None)

    def xǁSemanticCacheǁ_normalize__mutmut_2(self, text: str) -> str:
        return "XX XX".join(text.lower().split())

    def xǁSemanticCacheǁ_normalize__mutmut_3(self, text: str) -> str:
        return " ".join(text.upper().split())

    @_mutmut_mutated(mutants_xǁSemanticCacheǁ_similarity__mutmut)
    def _similarity(self, a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio()

    def xǁSemanticCacheǁ_similarity__mutmut_orig(self, a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio()

    def xǁSemanticCacheǁ_similarity__mutmut_1(self, a: str, b: str) -> float:
        return SequenceMatcher(None, None, b).ratio()

    def xǁSemanticCacheǁ_similarity__mutmut_2(self, a: str, b: str) -> float:
        return SequenceMatcher(None, a, None).ratio()

    def xǁSemanticCacheǁ_similarity__mutmut_3(self, a: str, b: str) -> float:
        return SequenceMatcher(a, b).ratio()

    def xǁSemanticCacheǁ_similarity__mutmut_4(self, a: str, b: str) -> float:
        return SequenceMatcher(None, b).ratio()

    def xǁSemanticCacheǁ_similarity__mutmut_5(self, a: str, b: str) -> float:
        return SequenceMatcher(None, a, ).ratio()

    @_mutmut_mutated(mutants_xǁSemanticCacheǁ_evict_expired__mutmut)
    def _evict_expired(self):
        now = time.time()
        expired = [k for k, v in self._entries.items() if now - v.timestamp > self.ttl]
        for k in expired:
            del self._entries[k]
        if expired:
            logger.debug(f"Evicted {len(expired)} expired cache entries")

    def xǁSemanticCacheǁ_evict_expired__mutmut_orig(self):
        now = time.time()
        expired = [k for k, v in self._entries.items() if now - v.timestamp > self.ttl]
        for k in expired:
            del self._entries[k]
        if expired:
            logger.debug(f"Evicted {len(expired)} expired cache entries")

    def xǁSemanticCacheǁ_evict_expired__mutmut_1(self):
        now = None
        expired = [k for k, v in self._entries.items() if now - v.timestamp > self.ttl]
        for k in expired:
            del self._entries[k]
        if expired:
            logger.debug(f"Evicted {len(expired)} expired cache entries")

    def xǁSemanticCacheǁ_evict_expired__mutmut_2(self):
        now = time.time()
        expired = None
        for k in expired:
            del self._entries[k]
        if expired:
            logger.debug(f"Evicted {len(expired)} expired cache entries")

    def xǁSemanticCacheǁ_evict_expired__mutmut_3(self):
        now = time.time()
        expired = [k for k, v in self._entries.items() if now + v.timestamp > self.ttl]
        for k in expired:
            del self._entries[k]
        if expired:
            logger.debug(f"Evicted {len(expired)} expired cache entries")

    def xǁSemanticCacheǁ_evict_expired__mutmut_4(self):
        now = time.time()
        expired = [k for k, v in self._entries.items() if now - v.timestamp >= self.ttl]
        for k in expired:
            del self._entries[k]
        if expired:
            logger.debug(f"Evicted {len(expired)} expired cache entries")

    def xǁSemanticCacheǁ_evict_expired__mutmut_5(self):
        now = time.time()
        expired = [k for k, v in self._entries.items() if now - v.timestamp > self.ttl]
        for k in expired:
            del self._entries[k]
        if expired:
            logger.debug(None)

    @_mutmut_mutated(mutants_xǁSemanticCacheǁget__mutmut)
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

    def xǁSemanticCacheǁget__mutmut_orig(self, query: str) -> str | None:
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

    def xǁSemanticCacheǁget__mutmut_1(self, query: str) -> str | None:
        self._evict_expired()
        normalized = None

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

    def xǁSemanticCacheǁget__mutmut_2(self, query: str) -> str | None:
        self._evict_expired()
        normalized = self._normalize(None)

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

    def xǁSemanticCacheǁget__mutmut_3(self, query: str) -> str | None:
        self._evict_expired()
        normalized = self._normalize(query)

        best_match = ""
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

    def xǁSemanticCacheǁget__mutmut_4(self, query: str) -> str | None:
        self._evict_expired()
        normalized = self._normalize(query)

        best_match = None
        best_score = None

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

    def xǁSemanticCacheǁget__mutmut_5(self, query: str) -> str | None:
        self._evict_expired()
        normalized = self._normalize(query)

        best_match = None
        best_score = 1.0

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

    def xǁSemanticCacheǁget__mutmut_6(self, query: str) -> str | None:
        self._evict_expired()
        normalized = self._normalize(query)

        best_match = None
        best_score = 0.0

        for key, entry in self._entries.items():
            score = None
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

    def xǁSemanticCacheǁget__mutmut_7(self, query: str) -> str | None:
        self._evict_expired()
        normalized = self._normalize(query)

        best_match = None
        best_score = 0.0

        for key, entry in self._entries.items():
            score = self._similarity(None, key)
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

    def xǁSemanticCacheǁget__mutmut_8(self, query: str) -> str | None:
        self._evict_expired()
        normalized = self._normalize(query)

        best_match = None
        best_score = 0.0

        for key, entry in self._entries.items():
            score = self._similarity(normalized, None)
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

    def xǁSemanticCacheǁget__mutmut_9(self, query: str) -> str | None:
        self._evict_expired()
        normalized = self._normalize(query)

        best_match = None
        best_score = 0.0

        for key, entry in self._entries.items():
            score = self._similarity(key)
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

    def xǁSemanticCacheǁget__mutmut_10(self, query: str) -> str | None:
        self._evict_expired()
        normalized = self._normalize(query)

        best_match = None
        best_score = 0.0

        for key, entry in self._entries.items():
            score = self._similarity(normalized, )
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

    def xǁSemanticCacheǁget__mutmut_11(self, query: str) -> str | None:
        self._evict_expired()
        normalized = self._normalize(query)

        best_match = None
        best_score = 0.0

        for key, entry in self._entries.items():
            score = self._similarity(normalized, key)
            if score >= best_score:
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

    def xǁSemanticCacheǁget__mutmut_12(self, query: str) -> str | None:
        self._evict_expired()
        normalized = self._normalize(query)

        best_match = None
        best_score = 0.0

        for key, entry in self._entries.items():
            score = self._similarity(normalized, key)
            if score > best_score:
                best_score = None
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

    def xǁSemanticCacheǁget__mutmut_13(self, query: str) -> str | None:
        self._evict_expired()
        normalized = self._normalize(query)

        best_match = None
        best_score = 0.0

        for key, entry in self._entries.items():
            score = self._similarity(normalized, key)
            if score > best_score:
                best_score = score
                best_match = None

        if best_match and best_score >= self.threshold:
            best_match.hits += 1
            best_match.timestamp = time.time()
            logger.info(
                f"[CACHE_HIT] similarity={best_score:.3f} "
                f"hits={best_match.hits} query='{query[:60]}'",
            )
            return best_match.response

        return None

    def xǁSemanticCacheǁget__mutmut_14(self, query: str) -> str | None:
        self._evict_expired()
        normalized = self._normalize(query)

        best_match = None
        best_score = 0.0

        for key, entry in self._entries.items():
            score = self._similarity(normalized, key)
            if score > best_score:
                best_score = score
                best_match = entry

        if best_match or best_score >= self.threshold:
            best_match.hits += 1
            best_match.timestamp = time.time()
            logger.info(
                f"[CACHE_HIT] similarity={best_score:.3f} "
                f"hits={best_match.hits} query='{query[:60]}'",
            )
            return best_match.response

        return None

    def xǁSemanticCacheǁget__mutmut_15(self, query: str) -> str | None:
        self._evict_expired()
        normalized = self._normalize(query)

        best_match = None
        best_score = 0.0

        for key, entry in self._entries.items():
            score = self._similarity(normalized, key)
            if score > best_score:
                best_score = score
                best_match = entry

        if best_match and best_score > self.threshold:
            best_match.hits += 1
            best_match.timestamp = time.time()
            logger.info(
                f"[CACHE_HIT] similarity={best_score:.3f} "
                f"hits={best_match.hits} query='{query[:60]}'",
            )
            return best_match.response

        return None

    def xǁSemanticCacheǁget__mutmut_16(self, query: str) -> str | None:
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
            best_match.hits = 1
            best_match.timestamp = time.time()
            logger.info(
                f"[CACHE_HIT] similarity={best_score:.3f} "
                f"hits={best_match.hits} query='{query[:60]}'",
            )
            return best_match.response

        return None

    def xǁSemanticCacheǁget__mutmut_17(self, query: str) -> str | None:
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
            best_match.hits -= 1
            best_match.timestamp = time.time()
            logger.info(
                f"[CACHE_HIT] similarity={best_score:.3f} "
                f"hits={best_match.hits} query='{query[:60]}'",
            )
            return best_match.response

        return None

    def xǁSemanticCacheǁget__mutmut_18(self, query: str) -> str | None:
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
            best_match.hits += 2
            best_match.timestamp = time.time()
            logger.info(
                f"[CACHE_HIT] similarity={best_score:.3f} "
                f"hits={best_match.hits} query='{query[:60]}'",
            )
            return best_match.response

        return None

    def xǁSemanticCacheǁget__mutmut_19(self, query: str) -> str | None:
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
            best_match.timestamp = None
            logger.info(
                f"[CACHE_HIT] similarity={best_score:.3f} "
                f"hits={best_match.hits} query='{query[:60]}'",
            )
            return best_match.response

        return None

    def xǁSemanticCacheǁget__mutmut_20(self, query: str) -> str | None:
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
                None,
            )
            return best_match.response

        return None

    def xǁSemanticCacheǁget__mutmut_21(self, query: str) -> str | None:
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
                f"hits={best_match.hits} query='{query[:61]}'",
            )
            return best_match.response

        return None

    @_mutmut_mutated(mutants_xǁSemanticCacheǁset__mutmut)
    def set(self, query: str, response: str):
        if not query or not response:
            return
        self._evict_expired()
        normalized = self._normalize(query)

        if len(self._entries) >= self.max_size:
            oldest = min(self._entries.keys(), key=lambda k: self._entries[k].timestamp)
            del self._entries[oldest]

        self._entries[normalized] = SemanticCacheEntry(normalized, response)

    def xǁSemanticCacheǁset__mutmut_orig(self, query: str, response: str):
        if not query or not response:
            return
        self._evict_expired()
        normalized = self._normalize(query)

        if len(self._entries) >= self.max_size:
            oldest = min(self._entries.keys(), key=lambda k: self._entries[k].timestamp)
            del self._entries[oldest]

        self._entries[normalized] = SemanticCacheEntry(normalized, response)

    def xǁSemanticCacheǁset__mutmut_1(self, query: str, response: str):
        if not query and not response:
            return
        self._evict_expired()
        normalized = self._normalize(query)

        if len(self._entries) >= self.max_size:
            oldest = min(self._entries.keys(), key=lambda k: self._entries[k].timestamp)
            del self._entries[oldest]

        self._entries[normalized] = SemanticCacheEntry(normalized, response)

    def xǁSemanticCacheǁset__mutmut_2(self, query: str, response: str):
        if query or not response:
            return
        self._evict_expired()
        normalized = self._normalize(query)

        if len(self._entries) >= self.max_size:
            oldest = min(self._entries.keys(), key=lambda k: self._entries[k].timestamp)
            del self._entries[oldest]

        self._entries[normalized] = SemanticCacheEntry(normalized, response)

    def xǁSemanticCacheǁset__mutmut_3(self, query: str, response: str):
        if not query or response:
            return
        self._evict_expired()
        normalized = self._normalize(query)

        if len(self._entries) >= self.max_size:
            oldest = min(self._entries.keys(), key=lambda k: self._entries[k].timestamp)
            del self._entries[oldest]

        self._entries[normalized] = SemanticCacheEntry(normalized, response)

    def xǁSemanticCacheǁset__mutmut_4(self, query: str, response: str):
        if not query or not response:
            return
        self._evict_expired()
        normalized = None

        if len(self._entries) >= self.max_size:
            oldest = min(self._entries.keys(), key=lambda k: self._entries[k].timestamp)
            del self._entries[oldest]

        self._entries[normalized] = SemanticCacheEntry(normalized, response)

    def xǁSemanticCacheǁset__mutmut_5(self, query: str, response: str):
        if not query or not response:
            return
        self._evict_expired()
        normalized = self._normalize(None)

        if len(self._entries) >= self.max_size:
            oldest = min(self._entries.keys(), key=lambda k: self._entries[k].timestamp)
            del self._entries[oldest]

        self._entries[normalized] = SemanticCacheEntry(normalized, response)

    def xǁSemanticCacheǁset__mutmut_6(self, query: str, response: str):
        if not query or not response:
            return
        self._evict_expired()
        normalized = self._normalize(query)

        if len(self._entries) > self.max_size:
            oldest = min(self._entries.keys(), key=lambda k: self._entries[k].timestamp)
            del self._entries[oldest]

        self._entries[normalized] = SemanticCacheEntry(normalized, response)

    def xǁSemanticCacheǁset__mutmut_7(self, query: str, response: str):
        if not query or not response:
            return
        self._evict_expired()
        normalized = self._normalize(query)

        if len(self._entries) >= self.max_size:
            oldest = None
            del self._entries[oldest]

        self._entries[normalized] = SemanticCacheEntry(normalized, response)

    def xǁSemanticCacheǁset__mutmut_8(self, query: str, response: str):
        if not query or not response:
            return
        self._evict_expired()
        normalized = self._normalize(query)

        if len(self._entries) >= self.max_size:
            oldest = min(None, key=lambda k: self._entries[k].timestamp)
            del self._entries[oldest]

        self._entries[normalized] = SemanticCacheEntry(normalized, response)

    def xǁSemanticCacheǁset__mutmut_9(self, query: str, response: str):
        if not query or not response:
            return
        self._evict_expired()
        normalized = self._normalize(query)

        if len(self._entries) >= self.max_size:
            oldest = min(self._entries.keys(), key=None)
            del self._entries[oldest]

        self._entries[normalized] = SemanticCacheEntry(normalized, response)

    def xǁSemanticCacheǁset__mutmut_10(self, query: str, response: str):
        if not query or not response:
            return
        self._evict_expired()
        normalized = self._normalize(query)

        if len(self._entries) >= self.max_size:
            oldest = min(key=lambda k: self._entries[k].timestamp)
            del self._entries[oldest]

        self._entries[normalized] = SemanticCacheEntry(normalized, response)

    def xǁSemanticCacheǁset__mutmut_11(self, query: str, response: str):
        if not query or not response:
            return
        self._evict_expired()
        normalized = self._normalize(query)

        if len(self._entries) >= self.max_size:
            oldest = min(self._entries.keys(), )
            del self._entries[oldest]

        self._entries[normalized] = SemanticCacheEntry(normalized, response)

    def xǁSemanticCacheǁset__mutmut_12(self, query: str, response: str):
        if not query or not response:
            return
        self._evict_expired()
        normalized = self._normalize(query)

        if len(self._entries) >= self.max_size:
            oldest = min(self._entries.keys(), key=lambda k: None)
            del self._entries[oldest]

        self._entries[normalized] = SemanticCacheEntry(normalized, response)

    def xǁSemanticCacheǁset__mutmut_13(self, query: str, response: str):
        if not query or not response:
            return
        self._evict_expired()
        normalized = self._normalize(query)

        if len(self._entries) >= self.max_size:
            oldest = min(self._entries.keys(), key=lambda k: self._entries[k].timestamp)
            del self._entries[oldest]

        self._entries[normalized] = None

    def xǁSemanticCacheǁset__mutmut_14(self, query: str, response: str):
        if not query or not response:
            return
        self._evict_expired()
        normalized = self._normalize(query)

        if len(self._entries) >= self.max_size:
            oldest = min(self._entries.keys(), key=lambda k: self._entries[k].timestamp)
            del self._entries[oldest]

        self._entries[normalized] = SemanticCacheEntry(None, response)

    def xǁSemanticCacheǁset__mutmut_15(self, query: str, response: str):
        if not query or not response:
            return
        self._evict_expired()
        normalized = self._normalize(query)

        if len(self._entries) >= self.max_size:
            oldest = min(self._entries.keys(), key=lambda k: self._entries[k].timestamp)
            del self._entries[oldest]

        self._entries[normalized] = SemanticCacheEntry(normalized, None)

    def xǁSemanticCacheǁset__mutmut_16(self, query: str, response: str):
        if not query or not response:
            return
        self._evict_expired()
        normalized = self._normalize(query)

        if len(self._entries) >= self.max_size:
            oldest = min(self._entries.keys(), key=lambda k: self._entries[k].timestamp)
            del self._entries[oldest]

        self._entries[normalized] = SemanticCacheEntry(response)

    def xǁSemanticCacheǁset__mutmut_17(self, query: str, response: str):
        if not query or not response:
            return
        self._evict_expired()
        normalized = self._normalize(query)

        if len(self._entries) >= self.max_size:
            oldest = min(self._entries.keys(), key=lambda k: self._entries[k].timestamp)
            del self._entries[oldest]

        self._entries[normalized] = SemanticCacheEntry(normalized, )

    @_mutmut_mutated(mutants_xǁSemanticCacheǁinvalidate__mutmut)
    def invalidate(self, query: str = ""):
        if query:
            self._entries.pop(self._normalize(query), None)
        else:
            self._entries.clear()
            logger.info("Semantic cache cleared")

    def xǁSemanticCacheǁinvalidate__mutmut_orig(self, query: str = ""):
        if query:
            self._entries.pop(self._normalize(query), None)
        else:
            self._entries.clear()
            logger.info("Semantic cache cleared")

    def xǁSemanticCacheǁinvalidate__mutmut_1(self, query: str = "XXXX"):
        if query:
            self._entries.pop(self._normalize(query), None)
        else:
            self._entries.clear()
            logger.info("Semantic cache cleared")

    def xǁSemanticCacheǁinvalidate__mutmut_2(self, query: str = ""):
        if query:
            self._entries.pop(None, None)
        else:
            self._entries.clear()
            logger.info("Semantic cache cleared")

    def xǁSemanticCacheǁinvalidate__mutmut_3(self, query: str = ""):
        if query:
            self._entries.pop(None)
        else:
            self._entries.clear()
            logger.info("Semantic cache cleared")

    def xǁSemanticCacheǁinvalidate__mutmut_4(self, query: str = ""):
        if query:
            self._entries.pop(self._normalize(query), )
        else:
            self._entries.clear()
            logger.info("Semantic cache cleared")

    def xǁSemanticCacheǁinvalidate__mutmut_5(self, query: str = ""):
        if query:
            self._entries.pop(self._normalize(None), None)
        else:
            self._entries.clear()
            logger.info("Semantic cache cleared")

    def xǁSemanticCacheǁinvalidate__mutmut_6(self, query: str = ""):
        if query:
            self._entries.pop(self._normalize(query), None)
        else:
            self._entries.clear()
            logger.info(None)

    def xǁSemanticCacheǁinvalidate__mutmut_7(self, query: str = ""):
        if query:
            self._entries.pop(self._normalize(query), None)
        else:
            self._entries.clear()
            logger.info("XXSemantic cache clearedXX")

    def xǁSemanticCacheǁinvalidate__mutmut_8(self, query: str = ""):
        if query:
            self._entries.pop(self._normalize(query), None)
        else:
            self._entries.clear()
            logger.info("semantic cache cleared")

    def xǁSemanticCacheǁinvalidate__mutmut_9(self, query: str = ""):
        if query:
            self._entries.pop(self._normalize(query), None)
        else:
            self._entries.clear()
            logger.info("SEMANTIC CACHE CLEARED")

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

mutants_xǁSemanticCacheǁ__init____mutmut['_mutmut_orig'] = SemanticCache.xǁSemanticCacheǁ__init____mutmut_orig # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁ__init____mutmut['xǁSemanticCacheǁ__init____mutmut_1'] = SemanticCache.xǁSemanticCacheǁ__init____mutmut_1 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁ__init____mutmut['xǁSemanticCacheǁ__init____mutmut_2'] = SemanticCache.xǁSemanticCacheǁ__init____mutmut_2 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁ__init____mutmut['xǁSemanticCacheǁ__init____mutmut_3'] = SemanticCache.xǁSemanticCacheǁ__init____mutmut_3 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁ__init____mutmut['xǁSemanticCacheǁ__init____mutmut_4'] = SemanticCache.xǁSemanticCacheǁ__init____mutmut_4 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁ__init____mutmut['xǁSemanticCacheǁ__init____mutmut_5'] = SemanticCache.xǁSemanticCacheǁ__init____mutmut_5 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁ__init____mutmut['xǁSemanticCacheǁ__init____mutmut_6'] = SemanticCache.xǁSemanticCacheǁ__init____mutmut_6 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁ__init____mutmut['xǁSemanticCacheǁ__init____mutmut_7'] = SemanticCache.xǁSemanticCacheǁ__init____mutmut_7 # type: ignore # mutmut generated

mutants_xǁSemanticCacheǁ_normalize__mutmut['_mutmut_orig'] = SemanticCache.xǁSemanticCacheǁ_normalize__mutmut_orig # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁ_normalize__mutmut['xǁSemanticCacheǁ_normalize__mutmut_1'] = SemanticCache.xǁSemanticCacheǁ_normalize__mutmut_1 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁ_normalize__mutmut['xǁSemanticCacheǁ_normalize__mutmut_2'] = SemanticCache.xǁSemanticCacheǁ_normalize__mutmut_2 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁ_normalize__mutmut['xǁSemanticCacheǁ_normalize__mutmut_3'] = SemanticCache.xǁSemanticCacheǁ_normalize__mutmut_3 # type: ignore # mutmut generated

mutants_xǁSemanticCacheǁ_similarity__mutmut['_mutmut_orig'] = SemanticCache.xǁSemanticCacheǁ_similarity__mutmut_orig # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁ_similarity__mutmut['xǁSemanticCacheǁ_similarity__mutmut_1'] = SemanticCache.xǁSemanticCacheǁ_similarity__mutmut_1 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁ_similarity__mutmut['xǁSemanticCacheǁ_similarity__mutmut_2'] = SemanticCache.xǁSemanticCacheǁ_similarity__mutmut_2 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁ_similarity__mutmut['xǁSemanticCacheǁ_similarity__mutmut_3'] = SemanticCache.xǁSemanticCacheǁ_similarity__mutmut_3 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁ_similarity__mutmut['xǁSemanticCacheǁ_similarity__mutmut_4'] = SemanticCache.xǁSemanticCacheǁ_similarity__mutmut_4 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁ_similarity__mutmut['xǁSemanticCacheǁ_similarity__mutmut_5'] = SemanticCache.xǁSemanticCacheǁ_similarity__mutmut_5 # type: ignore # mutmut generated

mutants_xǁSemanticCacheǁ_evict_expired__mutmut['_mutmut_orig'] = SemanticCache.xǁSemanticCacheǁ_evict_expired__mutmut_orig # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁ_evict_expired__mutmut['xǁSemanticCacheǁ_evict_expired__mutmut_1'] = SemanticCache.xǁSemanticCacheǁ_evict_expired__mutmut_1 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁ_evict_expired__mutmut['xǁSemanticCacheǁ_evict_expired__mutmut_2'] = SemanticCache.xǁSemanticCacheǁ_evict_expired__mutmut_2 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁ_evict_expired__mutmut['xǁSemanticCacheǁ_evict_expired__mutmut_3'] = SemanticCache.xǁSemanticCacheǁ_evict_expired__mutmut_3 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁ_evict_expired__mutmut['xǁSemanticCacheǁ_evict_expired__mutmut_4'] = SemanticCache.xǁSemanticCacheǁ_evict_expired__mutmut_4 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁ_evict_expired__mutmut['xǁSemanticCacheǁ_evict_expired__mutmut_5'] = SemanticCache.xǁSemanticCacheǁ_evict_expired__mutmut_5 # type: ignore # mutmut generated

mutants_xǁSemanticCacheǁget__mutmut['_mutmut_orig'] = SemanticCache.xǁSemanticCacheǁget__mutmut_orig # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁget__mutmut['xǁSemanticCacheǁget__mutmut_1'] = SemanticCache.xǁSemanticCacheǁget__mutmut_1 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁget__mutmut['xǁSemanticCacheǁget__mutmut_2'] = SemanticCache.xǁSemanticCacheǁget__mutmut_2 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁget__mutmut['xǁSemanticCacheǁget__mutmut_3'] = SemanticCache.xǁSemanticCacheǁget__mutmut_3 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁget__mutmut['xǁSemanticCacheǁget__mutmut_4'] = SemanticCache.xǁSemanticCacheǁget__mutmut_4 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁget__mutmut['xǁSemanticCacheǁget__mutmut_5'] = SemanticCache.xǁSemanticCacheǁget__mutmut_5 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁget__mutmut['xǁSemanticCacheǁget__mutmut_6'] = SemanticCache.xǁSemanticCacheǁget__mutmut_6 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁget__mutmut['xǁSemanticCacheǁget__mutmut_7'] = SemanticCache.xǁSemanticCacheǁget__mutmut_7 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁget__mutmut['xǁSemanticCacheǁget__mutmut_8'] = SemanticCache.xǁSemanticCacheǁget__mutmut_8 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁget__mutmut['xǁSemanticCacheǁget__mutmut_9'] = SemanticCache.xǁSemanticCacheǁget__mutmut_9 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁget__mutmut['xǁSemanticCacheǁget__mutmut_10'] = SemanticCache.xǁSemanticCacheǁget__mutmut_10 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁget__mutmut['xǁSemanticCacheǁget__mutmut_11'] = SemanticCache.xǁSemanticCacheǁget__mutmut_11 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁget__mutmut['xǁSemanticCacheǁget__mutmut_12'] = SemanticCache.xǁSemanticCacheǁget__mutmut_12 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁget__mutmut['xǁSemanticCacheǁget__mutmut_13'] = SemanticCache.xǁSemanticCacheǁget__mutmut_13 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁget__mutmut['xǁSemanticCacheǁget__mutmut_14'] = SemanticCache.xǁSemanticCacheǁget__mutmut_14 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁget__mutmut['xǁSemanticCacheǁget__mutmut_15'] = SemanticCache.xǁSemanticCacheǁget__mutmut_15 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁget__mutmut['xǁSemanticCacheǁget__mutmut_16'] = SemanticCache.xǁSemanticCacheǁget__mutmut_16 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁget__mutmut['xǁSemanticCacheǁget__mutmut_17'] = SemanticCache.xǁSemanticCacheǁget__mutmut_17 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁget__mutmut['xǁSemanticCacheǁget__mutmut_18'] = SemanticCache.xǁSemanticCacheǁget__mutmut_18 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁget__mutmut['xǁSemanticCacheǁget__mutmut_19'] = SemanticCache.xǁSemanticCacheǁget__mutmut_19 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁget__mutmut['xǁSemanticCacheǁget__mutmut_20'] = SemanticCache.xǁSemanticCacheǁget__mutmut_20 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁget__mutmut['xǁSemanticCacheǁget__mutmut_21'] = SemanticCache.xǁSemanticCacheǁget__mutmut_21 # type: ignore # mutmut generated

mutants_xǁSemanticCacheǁset__mutmut['_mutmut_orig'] = SemanticCache.xǁSemanticCacheǁset__mutmut_orig # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁset__mutmut['xǁSemanticCacheǁset__mutmut_1'] = SemanticCache.xǁSemanticCacheǁset__mutmut_1 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁset__mutmut['xǁSemanticCacheǁset__mutmut_2'] = SemanticCache.xǁSemanticCacheǁset__mutmut_2 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁset__mutmut['xǁSemanticCacheǁset__mutmut_3'] = SemanticCache.xǁSemanticCacheǁset__mutmut_3 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁset__mutmut['xǁSemanticCacheǁset__mutmut_4'] = SemanticCache.xǁSemanticCacheǁset__mutmut_4 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁset__mutmut['xǁSemanticCacheǁset__mutmut_5'] = SemanticCache.xǁSemanticCacheǁset__mutmut_5 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁset__mutmut['xǁSemanticCacheǁset__mutmut_6'] = SemanticCache.xǁSemanticCacheǁset__mutmut_6 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁset__mutmut['xǁSemanticCacheǁset__mutmut_7'] = SemanticCache.xǁSemanticCacheǁset__mutmut_7 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁset__mutmut['xǁSemanticCacheǁset__mutmut_8'] = SemanticCache.xǁSemanticCacheǁset__mutmut_8 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁset__mutmut['xǁSemanticCacheǁset__mutmut_9'] = SemanticCache.xǁSemanticCacheǁset__mutmut_9 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁset__mutmut['xǁSemanticCacheǁset__mutmut_10'] = SemanticCache.xǁSemanticCacheǁset__mutmut_10 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁset__mutmut['xǁSemanticCacheǁset__mutmut_11'] = SemanticCache.xǁSemanticCacheǁset__mutmut_11 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁset__mutmut['xǁSemanticCacheǁset__mutmut_12'] = SemanticCache.xǁSemanticCacheǁset__mutmut_12 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁset__mutmut['xǁSemanticCacheǁset__mutmut_13'] = SemanticCache.xǁSemanticCacheǁset__mutmut_13 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁset__mutmut['xǁSemanticCacheǁset__mutmut_14'] = SemanticCache.xǁSemanticCacheǁset__mutmut_14 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁset__mutmut['xǁSemanticCacheǁset__mutmut_15'] = SemanticCache.xǁSemanticCacheǁset__mutmut_15 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁset__mutmut['xǁSemanticCacheǁset__mutmut_16'] = SemanticCache.xǁSemanticCacheǁset__mutmut_16 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁset__mutmut['xǁSemanticCacheǁset__mutmut_17'] = SemanticCache.xǁSemanticCacheǁset__mutmut_17 # type: ignore # mutmut generated

mutants_xǁSemanticCacheǁinvalidate__mutmut['_mutmut_orig'] = SemanticCache.xǁSemanticCacheǁinvalidate__mutmut_orig # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁinvalidate__mutmut['xǁSemanticCacheǁinvalidate__mutmut_1'] = SemanticCache.xǁSemanticCacheǁinvalidate__mutmut_1 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁinvalidate__mutmut['xǁSemanticCacheǁinvalidate__mutmut_2'] = SemanticCache.xǁSemanticCacheǁinvalidate__mutmut_2 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁinvalidate__mutmut['xǁSemanticCacheǁinvalidate__mutmut_3'] = SemanticCache.xǁSemanticCacheǁinvalidate__mutmut_3 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁinvalidate__mutmut['xǁSemanticCacheǁinvalidate__mutmut_4'] = SemanticCache.xǁSemanticCacheǁinvalidate__mutmut_4 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁinvalidate__mutmut['xǁSemanticCacheǁinvalidate__mutmut_5'] = SemanticCache.xǁSemanticCacheǁinvalidate__mutmut_5 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁinvalidate__mutmut['xǁSemanticCacheǁinvalidate__mutmut_6'] = SemanticCache.xǁSemanticCacheǁinvalidate__mutmut_6 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁinvalidate__mutmut['xǁSemanticCacheǁinvalidate__mutmut_7'] = SemanticCache.xǁSemanticCacheǁinvalidate__mutmut_7 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁinvalidate__mutmut['xǁSemanticCacheǁinvalidate__mutmut_8'] = SemanticCache.xǁSemanticCacheǁinvalidate__mutmut_8 # type: ignore # mutmut generated
mutants_xǁSemanticCacheǁinvalidate__mutmut['xǁSemanticCacheǁinvalidate__mutmut_9'] = SemanticCache.xǁSemanticCacheǁinvalidate__mutmut_9 # type: ignore # mutmut generated


_cache: SemanticCache | None = None
mutants_x_get_cache__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_get_cache__mutmut)
def get_cache() -> SemanticCache:
    global _cache
    if _cache is None:
        _cache = SemanticCache()
    return _cache


def x_get_cache__mutmut_orig() -> SemanticCache:
    global _cache
    if _cache is None:
        _cache = SemanticCache()
    return _cache


def x_get_cache__mutmut_1() -> SemanticCache:
    global _cache
    if _cache is not None:
        _cache = SemanticCache()
    return _cache


def x_get_cache__mutmut_2() -> SemanticCache:
    global _cache
    if _cache is None:
        _cache = None
    return _cache

mutants_x_get_cache__mutmut['_mutmut_orig'] = x_get_cache__mutmut_orig # type: ignore # mutmut generated
mutants_x_get_cache__mutmut['x_get_cache__mutmut_1'] = x_get_cache__mutmut_1 # type: ignore # mutmut generated
mutants_x_get_cache__mutmut['x_get_cache__mutmut_2'] = x_get_cache__mutmut_2 # type: ignore # mutmut generated
mutants_x_reset_cache__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_reset_cache__mutmut)
def reset_cache():
    global _cache
    _cache = None


def x_reset_cache__mutmut_orig():
    global _cache
    _cache = None


def x_reset_cache__mutmut_1():
    global _cache
    _cache = ""

mutants_x_reset_cache__mutmut['_mutmut_orig'] = x_reset_cache__mutmut_orig # type: ignore # mutmut generated
mutants_x_reset_cache__mutmut['x_reset_cache__mutmut_1'] = x_reset_cache__mutmut_1 # type: ignore # mutmut generated
