import json
import time
import uuid
from pathlib import Path

from config import DATA_DIR

# Временная папка для сохранения результатов поиска
WEB_SEARCH_CACHE_DIR = Path(DATA_DIR) / "web_search_cache"
WEB_SEARCH_CACHE_DIR.mkdir(exist_ok=True)

# TTL для кэша (24 часа)
CACHE_TTL = 24 * 60 * 60


def save_web_search(query: str, sources: list[dict], ai_summary: str = "") -> str:
    """Сохранить результаты поиска во временный файл."""
    search_id = uuid.uuid4().hex[:12]
    cache_file = WEB_SEARCH_CACHE_DIR / f"{search_id}.json"

    data = {
        "id": search_id,
        "query": query,
        "sources": [
            {"text": s["text"], "url": s["url"], "title": s.get("title", "")}
            for s in sources
        ],
        "ai_summary": ai_summary,
        "timestamp": time.time(),
    }

    cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return search_id


def save_web_search_with_id(
    search_id: str, query: str, sources: list[dict], ai_summary: str = "",
) -> str:
    """Сохранить результаты поиска с указанным ID."""
    cache_file = WEB_SEARCH_CACHE_DIR / f"{search_id}.json"

    data = {
        "id": search_id,
        "query": query,
        "sources": [
            {"text": s["text"], "url": s["url"], "title": s.get("title", "")}
            for s in sources
        ],
        "ai_summary": ai_summary,
        "timestamp": time.time(),
    }

    cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return search_id


def load_web_search(search_id: str) -> dict | None:
    """Загрузить сохранённый поиск."""
    cache_file = WEB_SEARCH_CACHE_DIR / f"{search_id}.json"
    if not cache_file.exists():
        return None
    try:
        return json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def cleanup_old_cache():
    """Удалить старые файлы кэша (старше 24 часов)."""
    now = time.time()
    for f in WEB_SEARCH_CACHE_DIR.glob("*.json"):
        try:
            if now - f.stat().st_mtime > CACHE_TTL:
                f.unlink()
        except Exception:
            pass


def list_cached_searches() -> list[dict]:
    """Список сохранённых поисков (для очистки/просмотра)."""
    searches = []
    for f in WEB_SEARCH_CACHE_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            searches.append({
                "id": data.get("id"),
                "query": data.get("query"),
                "source_count": len(data.get("sources", [])),
                "timestamp": data.get("timestamp"),
            })
        except Exception:
            pass
    return sorted(searches, key=lambda x: x.get("timestamp", 0), reverse=True)
