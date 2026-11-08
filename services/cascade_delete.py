"""services/cascade_delete.py — Сквозное каскадное удаление заметок из всех БД и с диска.

Удаляет запись из:
1. ChromaDB (mempalace_drawers, mempalace_closets, mempalace_compressed)
2. Локального диска (my_notes/...) с проверкой безопасности пути
3. SQLite (notes_embeddings.sqlite)
4. JSON кэша (notes_index.json)
5. Бэклинков (drawer_backlinks)
"""

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

from config import DATA_DIR, NOTES_DIR, PALACE_DIR
from services.notes_sync import delete_backlink
from services.palace_mcp import get_mcp

logger = logging.getLogger("CascadeDelete")


def delete_from_disk(
    file_path: str | Path | None = None,
    source_file: str | None = None,
) -> tuple[bool, str]:
    """Безопасно удаляет файл заметки с диска, если он находится в NOTES_DIR."""
    notes_root = Path(NOTES_DIR).resolve()
    candidates: list[Path] = []

    if file_path:
        candidates.append(Path(file_path))
    if source_file:
        candidates.append(Path(source_file))
        candidates.append(notes_root / source_file)
        candidates.append(notes_root / os.path.basename(source_file))

    # Поиск файла среди кандидатов
    found_path: Path | None = None
    for cand in candidates:
        try:
            if cand.is_file():
                found_path = cand
                break
        except Exception:
            continue

    # Если не найден напрямую, пробуем поиск по имени в my_notes
    if not found_path and source_file:
        bname = os.path.basename(source_file)
        if bname and bname != ".":
            for root, _, files in os.walk(notes_root):
                if bname in files:
                    found_path = Path(root) / bname
                    break

    if not found_path or not found_path.exists():
        return False, "file_not_found"

    try:
        resolved = found_path.resolve()
        # Проверка безопасности: путь обязан быть внутри NOTES_DIR
        resolved.relative_to(notes_root)
    except ValueError:
        logger.warning("Безопасность: попытка удалить файл вне NOTES_DIR: %s", found_path)
        return False, "forbidden_path"

    try:
        resolved.unlink()
        logger.info("Удалён файл с диска: %s", resolved)
        return True, str(resolved)
    except Exception as e:
        logger.error("Ошибка при удалении файла %s: %s", resolved, e)
        return False, str(e)


def delete_from_sqlite_embeddings(
    source_id: str | None = None,
    name: str | None = None,
    file_basename: str | None = None,
) -> int:
    """Удаляет эмбеддинги заметки из SQLite notes_embeddings.sqlite."""
    db_path = os.path.join(DATA_DIR, "notes_embeddings.sqlite")
    if not os.path.exists(db_path):
        return 0

    deleted = 0
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        clauses = []
        params = []

        if source_id:
            clauses.append("note_id = ?")
            params.append(source_id)
        if name:
            clauses.append("name = ?")
            params.append(name)
            clauses.append("name LIKE ?")
            params.append(f"%{name}%")
        if file_basename:
            clauses.append("name LIKE ?")
            params.append(f"%{file_basename}%")

        if clauses:
            query = f"DELETE FROM notes_embeddings WHERE {' OR '.join(clauses)}"
            cur.execute(query, params)
            deleted = cur.rowcount
            conn.commit()
            if deleted > 0:
                logger.info("Удалено %d строк из notes_embeddings.sqlite", deleted)
        conn.close()
    except Exception as e:
        logger.warning("Ошибка при удалении из notes_embeddings.sqlite: %s", e)

    return deleted


def delete_from_notes_index(
    source_id: str | None = None,
    name: str | None = None,
    file_basename: str | None = None,
) -> int:
    """Удаляет запись из кэша notes_index.json."""
    index_path = os.path.join(DATA_DIR, "notes_index.json")
    if not os.path.exists(index_path):
        return 0

    deleted = 0
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        notes = data.get("notes", [])
        orig_count = len(notes)

        def _should_remove(note: dict) -> bool:
            nid = note.get("id", "")
            nname = note.get("name", "")
            if source_id and (source_id == nid or source_id in nid):
                return True
            if name and (name == nname or name in nname):
                return True
            if file_basename and (file_basename in nname or file_basename in nid):
                return True
            return False

        new_notes = [n for n in notes if not _should_remove(n)]
        deleted = orig_count - len(new_notes)

        if deleted > 0:
            data["notes"] = new_notes
            tmp_path = index_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, index_path)
            logger.info("Удалено %d записей из notes_index.json", deleted)

            try:
                from services.apple_notes import invalidate_index
                invalidate_index()
            except Exception:
                pass
    except Exception as e:
        logger.warning("Ошибка при обновлении notes_index.json: %s", e)

    return deleted


def cleanup_chroma_collections(
    drawer_id: str | None = None,
    source_file: str | None = None,
) -> int:
    """Прямая зачистка связей в коллекциях ChromaDB (closets, compressed)."""
    try:
        import chromadb
        client = chromadb.PersistentClient(path=PALACE_DIR)
        deleted_count = 0
        bname = os.path.basename(source_file) if source_file else None

        for col_name in ["mempalace_drawers", "mempalace_closets", "mempalace_compressed"]:
            try:
                col = client.get_collection(col_name)
                all_data = col.get(include=["metadatas"])
                ids_to_del = []
                for cid, meta in zip(all_data.get("ids", []), all_data.get("metadatas", [])):
                    if drawer_id and cid == drawer_id:
                        ids_to_del.append(cid)
                        continue
                    if meta:
                        m_src = str(meta.get("source_file", ""))
                        if source_file and (source_file == m_src or (bname and bname in m_src)):
                            ids_to_del.append(cid)
                        elif drawer_id and drawer_id in str(meta):
                            ids_to_del.append(cid)
                if ids_to_del:
                    col.delete(ids=ids_to_del)
                    deleted_count += len(ids_to_del)
                    logger.info("ChromaDB %s: удалено %d записей", col_name, len(ids_to_del))
            except Exception:
                continue
        return deleted_count
    except Exception as e:
        logger.debug("cleanup_chroma_collections: %s", e)
        return 0


async def cascade_delete_note(
    drawer_id: str = "",
    file_path: str = "",
    source_id: str = "",
    title: str = "",
    source_file: str = "",
) -> dict[str, Any]:
    """Выполняет полное сквозное удаление заметки во всех 4 хранилищах.

    Не падает, если ящик уже был удален из ChromaDB («Drawer not found»),
    а завершает удаление файла с диска, из SQLite и JSON.
    """
    results: dict[str, Any] = {
        "success": False,
        "chroma_deleted": False,
        "file_deleted": False,
        "file_path": "",
        "sqlite_deleted": 0,
        "json_deleted": 0,
        "backlink_deleted": False,
        "error": None,
    }

    # 1. Попытка удаления через MCP
    if drawer_id:
        try:
            mcp = get_mcp()
            raw = await mcp.call_tool("mempalace_delete_drawer", {"drawer_id": drawer_id})
            parsed = json.loads(raw) if raw else {}
            if parsed.get("success"):
                results["chroma_deleted"] = True
            else:
                err = parsed.get("error", "")
                logger.info("MCP delete_drawer вернул статус: %s", err)
        except Exception as e:
            logger.warning("Ошибка вызова MCP delete_drawer: %s", e)

    # Дополнительная прямая зачистка коллекций ChromaDB (closets, compressed)
    chroma_direct = cleanup_chroma_collections(
        drawer_id=drawer_id,
        source_file=source_file or file_path,
    )
    if chroma_direct > 0:
        results["chroma_deleted"] = True

    # 2. Удаление физического файла с диска
    file_ok, f_res = delete_from_disk(file_path=file_path, source_file=source_file)
    results["file_deleted"] = file_ok
    if file_ok:
        results["file_path"] = f_res

    # 3. Удаление из SQLite
    bname = os.path.basename(source_file or file_path) if (source_file or file_path) else None
    sqlite_del = delete_from_sqlite_embeddings(
        source_id=source_id,
        name=title,
        file_basename=bname,
    )
    results["sqlite_deleted"] = sqlite_del

    # 4. Удаление из JSON индекса
    json_del = delete_from_notes_index(
        source_id=source_id,
        name=title,
        file_basename=bname,
    )
    results["json_deleted"] = json_del

    # 5. Удаление бэклинка
    if drawer_id:
        try:
            delete_backlink(drawer_id)
            results["backlink_deleted"] = True
        except Exception:
            pass

    # Успех, если хотя бы в одном месте было произведено удаление,
    # либо если файл или ящик уже отсутствовали
    results["success"] = (
        results["chroma_deleted"]
        or results["file_deleted"]
        or (sqlite_del > 0)
        or (json_del > 0)
        or bool(drawer_id or file_path or source_file)
    )

    return results
