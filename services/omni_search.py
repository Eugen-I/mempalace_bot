"""services/omni_search.py
Единый сервис гибридного поиска (OmniSearch).

Параллельно запрашивает:
1. 🏰 MemPalace Hybrid Search (ChromaDB + BM25)
2. 📝 Apple Notes Semantic & Text Search
3. 📁 File Index / Quick Notes (BM25 + FTS5)

И объединяет результаты через алгоритм Reciprocal Rank Fusion (RRF)
с настраиваемой приоритезацией личных источников.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
import logging
from typing import Any, Callable

logger = logging.getLogger("OmniSearch")


class OmniSource(str, Enum):
    PALACE = "palace"
    NOTES = "notes"
    FILES = "files"


SOURCE_ICONS: dict[str, str] = {
    OmniSource.PALACE.value: "🏰",
    OmniSource.NOTES.value: "📝",
    OmniSource.FILES.value: "📁",
}

SOURCE_NAMES: dict[str, str] = {
    OmniSource.PALACE.value: "Дворец",
    OmniSource.NOTES.value: "Apple Notes",
    OmniSource.FILES.value: "Файлы",
}

# RRF default parameters
DEFAULT_RRF_K = 60
DEFAULT_WEIGHTS: dict[str, float] = {
    OmniSource.PALACE.value: 1.2,
    OmniSource.NOTES.value: 1.0,
    OmniSource.FILES.value: 0.9,
}


@dataclass
class OmniSearchHit:
    """Унифицированный элемент выдачи поиска."""

    id: str
    source_type: str  # "palace" | "notes" | "files"
    title: str
    location: str
    snippet: str
    score: float = 0.0
    raw_data: dict[str, Any] = field(default_factory=dict)

    @property
    def icon(self) -> str:
        return SOURCE_ICONS.get(self.source_type, "📄")

    @property
    def source_label(self) -> str:
        return SOURCE_NAMES.get(self.source_type, self.source_type)

    def to_dict(self) -> dict[str, Any]:
        """Преобразует hit в dict для сохранения в search_result_cache."""
        d = dict(self.raw_data)
        d.update({
            "id": self.id,
            "source_type": self.source_type,
            "title": self.title,
            "location": self.location,
            "snippet": self.snippet,
            "score": self.score,
        })
        # Обеспечиваем wing/room/file для обратной совместимости с кнопками Дворца
        if self.source_type == OmniSource.PALACE.value:
            if "wing" not in d and "/" in self.location:
                parts = self.location.split("/", 1)
                d["wing"], d["room"] = parts[0], parts[1]
            if "file" not in d:
                d["file"] = self.title
        return d


def _ensure_hit(item: Any, default_source: str = "palace") -> OmniSearchHit:
    """Гарантирует приведение элемента к OmniSearchHit."""
    if isinstance(item, OmniSearchHit):
        return item
    if isinstance(item, dict):
        source = item.get("source_type") or default_source
        hit_id = str(item.get("id") or item.get("file_id") or "")
        title = item.get("title") or item.get("filename") or item.get("name") or "Документ"
        location = item.get("location") or item.get("folder") or ""
        if not location and ("wing" in item or "room" in item):
            location = f"{item.get('wing', '')}/{item.get('room', '')}"
        snippet = item.get("snippet") or item.get("content_preview") or ""
        score = float(item.get("score") or item.get("_score") or 0.0)
        return OmniSearchHit(
            id=hit_id,
            source_type=source,
            title=title,
            location=location,
            snippet=snippet,
            score=score,
            raw_data=item,
        )
    return OmniSearchHit(
        id=str(item), source_type=default_source, title=str(item), location="", snippet="",
    )


def reciprocal_rank_fusion(
    ranked_channels: dict[str, list[OmniSearchHit | dict[str, Any]]],
    *,
    k: int = DEFAULT_RRF_K,
    weights: dict[str, float] | None = None,
) -> list[OmniSearchHit]:
    """Слияние списков ранжирования по алгоритму Reciprocal Rank Fusion (RRF).

    score(d) = sum_{channel} (weight_{channel} / (k + rank_{channel}(d)))
    """
    w_map = weights or DEFAULT_WEIGHTS
    scores: dict[tuple[str, str], float] = {}
    item_lookup: dict[tuple[str, str], OmniSearchHit] = {}

    for channel_name, items in ranked_channels.items():
        w = w_map.get(channel_name, 1.0)
        for rank_idx, item in enumerate(items, start=1):
            hit = _ensure_hit(item, default_source=channel_name)
            key = (hit.source_type, str(hit.id))
            if key not in item_lookup:
                item_lookup[key] = hit
            rrf_delta = w / (k + rank_idx)
            scores[key] = scores.get(key, 0.0) + rrf_delta

    # Сортируем по итоговому RRF score
    sorted_keys = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)

    result: list[OmniSearchHit] = []
    for key in sorted_keys:
        hit = item_lookup[key]
        hit.score = round(scores[key], 6)
        result.append(hit)

    return result


async def _search_palace_channel(
    query: str,
    limit: int = 5,
    wing: str = "",
    custom_searcher: Callable[..., Any] | None = None,
) -> list[OmniSearchHit]:
    """Поиск по Дворцу (ChromaDB + BM25)."""
    try:
        if custom_searcher is not None:
            res = custom_searcher(query, limit=limit, wing=wing)
            if asyncio.iscoroutine(res):
                res = await res
            text, sources = res
        else:
            from services.palace_bridge import search_palace_with_sources
            text, sources = await search_palace_with_sources(query, limit=limit, wing=wing)

        hits: list[OmniSearchHit] = []
        for idx, s in enumerate(sources, start=1):
            w = s.get("wing", "")
            r = s.get("room", "")
            loc = f"{w}/{r}" if (w or r) else s.get("file", "Дворец")
            title = s.get("closet_name") or s.get("file") or loc
            snippet = s.get("snippet") or s.get("content_preview") or ""
            hits.append(
                OmniSearchHit(
                    id=str(s.get("id", idx)),
                    source_type=OmniSource.PALACE.value,
                    title=title,
                    location=loc,
                    snippet=snippet,
                    score=float(s.get("score", 0.0)),
                    raw_data=s,
                )
            )
        return hits
    except Exception as exc:
        logger.warning("[OmniSearch] Ошибка поиска во Дворце: %s", exc)
        return []


def _search_notes_sync(query: str, limit: int = 5) -> list[OmniSearchHit]:
    """Синхронный поиск по Apple Notes (гибридный или полнотекстовый)."""
    hits: list[OmniSearchHit] = []
    try:
        from services.notes_embeddings import search_notes_hybrid
        raw_notes = search_notes_hybrid(query, limit=limit)
    except Exception:
        try:
            from services.apple_notes import search_notes
            raw_notes = search_notes(query, limit=limit)
        except Exception as exc:
            logger.warning("[OmniSearch] Ошибка Apple Notes поиска: %s", exc)
            return []

    for item in raw_notes:
        note_id = str(item.get("id", ""))
        title = item.get("name") or "Заметка"
        folder = item.get("folder") or "Заметки"
        snippet = item.get("snippet") or ""
        score = float(item.get("_score", 0.0))
        hits.append(
            OmniSearchHit(
                id=note_id,
                source_type=OmniSource.NOTES.value,
                title=title,
                location=folder,
                snippet=snippet,
                score=score,
                raw_data=item,
            )
        )
    return hits


async def _search_notes_channel(query: str, limit: int = 5) -> list[OmniSearchHit]:
    """Асинхронная обертка для поиска по Apple Notes."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _search_notes_sync, query, limit)


def _search_files_sync(query: str, limit: int = 5) -> list[OmniSearchHit]:
    """Синхронный поиск по локальным Markdown/файлам через file_index."""
    hits: list[OmniSearchHit] = []
    try:
        from services.file_index import search_files
        raw_files = search_files(query, limit=limit)
    except Exception as exc:
        logger.warning("[OmniSearch] Ошибка поиска файлов: %s", exc)
        return []

    for item in raw_files:
        fid = str(item.get("file_id", ""))
        fname = item.get("filename") or "Файл"
        folder = item.get("folder") or "Файлы"
        snippet = item.get("snippet") or ""
        score = float(item.get("_score", 0.0))
        hits.append(
            OmniSearchHit(
                id=fid,
                source_type=OmniSource.FILES.value,
                title=fname,
                location=folder,
                snippet=snippet,
                score=score,
                raw_data=item,
            )
        )
    return hits


async def _search_files_channel(query: str, limit: int = 5) -> list[OmniSearchHit]:
    """Асинхронная обертка для поиска по файлам."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _search_files_sync, query, limit)


def format_omni_results(hits: list[OmniSearchHit], query: str = "") -> str:
    """Форматирует выдачу OmniSearch для Telegram с HTML-разметкой и бейджами."""
    if not hits:
        return "Ничего не найдено."

    lines: list[str] = [f"🔍 <b>Результаты поиска по запросу «{query}»:</b>\n"]

    for idx, hit in enumerate(hits, start=1):
        icon = hit.icon
        label = hit.source_label
        title = hit.title
        loc = hit.location
        snippet = hit.snippet.strip().replace("<", "&lt;").replace(">", "&gt;")

        lines.append(f"{idx}. {icon} <b>[{label}]</b> <code>{loc}</code>")
        if title and title != loc:
            lines.append(f"   📌 <b>{title}</b>")
        if snippet:
            short_snippet = snippet[:140] + ("…" if len(snippet) > 140 else "")
            lines.append(f"   <i>«{short_snippet}»</i>")
        lines.append("")

    return "\n".join(lines).strip()


async def omni_search(
    query: str,
    *,
    limit: int = 5,
    wing: str = "",
    weights: dict[str, float] | None = None,
    palace_searcher: Callable[..., Any] | None = None,
    include_channels: tuple[str, ...] = ("palace", "notes", "files"),
) -> tuple[str, list[dict[str, Any]]]:
    """Основная точка входа единого поиска.

    Параллельно запрашивает выбранные источники, объединяет их через RRF
    и возвращает (formatted_text, sources_dicts).
    """
    clean_query = query.strip()
    if not clean_query:
        return "❌ Пустой поисковый запрос.", []

    tasks = []
    task_channel_names = []

    # 1. Дворец
    if "palace" in include_channels:
        tasks.append(_search_palace_channel(
            clean_query, limit=limit, wing=wing, custom_searcher=palace_searcher,
        ))
        task_channel_names.append("palace")

    # 2. Apple Notes (только если не задано конкретное крыло дворца)
    if "notes" in include_channels and not wing:
        tasks.append(_search_notes_channel(clean_query, limit=limit))
        task_channel_names.append("notes")

    # 3. File Index (только если не задано конкретное крыло дворца)
    if "files" in include_channels and not wing:
        tasks.append(_search_files_channel(clean_query, limit=limit))
        task_channel_names.append("files")

    results = await asyncio.gather(*tasks, return_exceptions=True)

    ranked_channels: dict[str, list[OmniSearchHit]] = {}
    for ch_name, res in zip(task_channel_names, results):
        if isinstance(res, Exception):
            logger.warning("[OmniSearch] Ошибка в канале %s: %s", ch_name, res)
            ranked_channels[ch_name] = []
        elif isinstance(res, list):
            ranked_channels[ch_name] = res

    # RRF ранжирование
    fused_hits = reciprocal_rank_fusion(ranked_channels, weights=weights)
    top_hits = fused_hits[:limit]

    formatted_text = format_omni_results(top_hits, query=clean_query)
    sources_dicts = [h.to_dict() for h in top_hits]

    return formatted_text, sources_dicts
