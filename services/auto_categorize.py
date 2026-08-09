"""services/auto_categorize.py — авто-категоризация заметок Apple Notes → KG.

Детерминированный пайплайн (без AI):
  1. Индекс Apple Notes (services.apple_notes.list_notes) — id/name/folder.
  2. categorize_note(name, folder) — классификация по имени/папке
     (keyword-карта из kg_enricher): type + topics.
  3. Для каждой ещё не обработанной заметки (отметка в kv, namespace
     "categorized") добавляет в граф знаний факты
     subject=<имя заметки> predicate=topic object=<тема> через
     mempalace_kg_add (контракт из kg_enricher.add_kg_facts).

Каждый источник толерантен к ошибкам; отметка в kv ставится только
при успехе — упавшие заметки повторно обрабатываются в следующем цикле.
"""

import logging
import time

from services.kv_store import get_kv_store

logger = logging.getLogger("AutoCategorize")

CATEGORIZED_NS = "categorized"
DEFAULT_LIMIT = 20
MAX_SUBJECT_LEN = 100
SOURCE_PREFIX = "apple_notes/"


def categorize_note(name: str, folder: str) -> dict:
    """Классифицирует заметку по имени и папке: {type, topics}."""
    from services.kg_enricher import _extract_from_filename

    data = _extract_from_filename(name or "", folder or "")
    return {
        "type": data.get("type", "personal_thought"),
        "topics": list(data.get("topics", [])),
    }


async def _default_add_topic(note: dict, topic: str) -> None:
    """Добавляет факт subject=заметка → topic → тема в KG."""
    from services.palace_mcp import get_mcp

    note_name = (note.get("name") or "").strip() or "Заметка"
    mcp = get_mcp()
    await mcp.call_tool(
        "mempalace_kg_add",
        {
            "subject": note_name[:MAX_SUBJECT_LEN],
            "predicate": "topic",
            "object": topic,
            "source_closet": (
                f"{SOURCE_PREFIX}{note.get('folder', '')}/{note_name}"
            )[:200],
        },
    )


async def auto_categorize_notes(
    limit: int = DEFAULT_LIMIT,
    kv=None,
    mcp_cb=None,
    index_provider=None,
) -> dict:
    """Обрабатывает до `limit` новых заметок: категория → KG → отметка.

    Возвращает {processed, skipped, added, failed, error?}. processed —
    успешно категоризированные (с KG-фактами или без тем), skipped —
    уже обработанные ранее, failed — упавшие (повторятся в след. цикле).
    """
    kv = kv or get_kv_store()
    if index_provider is None:
        from services.apple_notes import list_notes

        index_provider = list_notes
    if mcp_cb is None:
        mcp_cb = _default_add_topic

    stats: dict[str, int] = {"processed": 0, "skipped": 0, "added": 0, "failed": 0}
    try:
        notes = index_provider()
    except Exception as exc:  # noqa: BLE001 — источник не должен ронять цикл
        logger.warning("[CATEGORIZE] notes index failed: %s", exc)
        return {**stats, "error": str(exc)}

    processed = 0
    for note in notes:
        if limit is not None and processed >= limit:
            break
        note_id = note.get("id", "")
        if not note_id:
            continue
        try:
            if kv.get(note_id, namespace=CATEGORIZED_NS):
                stats["skipped"] += 1
                continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("[CATEGORIZE] kv get failed for %s: %s", note_id, exc)

        category = categorize_note(note.get("name", ""), note.get("folder", ""))
        added_any = False
        for topic in category["topics"]:
            try:
                await mcp_cb(note, topic)
                stats["added"] += 1
                added_any = True
            except Exception as exc:  # noqa: BLE001
                logger.warning("[CATEGORIZE] kg add failed for %s: %s", note_id, exc)

        if added_any or not category["topics"]:
            try:
                kv.set(
                    note_id,
                    {
                        "type": category["type"],
                        "topics": category["topics"],
                        "ts": time.time(),
                    },
                    namespace=CATEGORIZED_NS,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("[CATEGORIZE] kv set failed for %s: %s", note_id, exc)
            stats["processed"] += 1
        else:
            stats["failed"] += 1
        processed += 1

    return stats
