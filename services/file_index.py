"""services/file_index.py — раздельная обработка файлов Apple Notes.

Файлы (заметки-документы, экспортированные txt/md, вложения) обрабатываются
отдельно от текстовых заметок: каждый файл получает собственный file_id
(sha256), проходит чанкинг и попадает в полнотекстовый индекс (FTS5).

Схема БД (DATA_DIR/file_index.sqlite):

- files         — каталог файлов: метаданные + статус + извлечённый текст
- search_index  — FTS5-индекс по чанкам (BM25-поиск)
- embeddings    — чанк -> вектор (BLOB float32), резерв под sqlite-vec
- kg_log        — идемпотентность прокидки фактов в Knowledge Graph

Graceful degradation: если модель эмбеддингов недоступна, семантическая часть
поиска возвращает полнотекстовые результаты без векторов.

NOTE: sqlite-vec (0.1.9) ставится на Python 3.14, но CPython 3.14 удалил API
load_extension — расширение не загружается из sqlite3. Поэтому embeddings
хранятся в виде BLOB с косинусным поиском на numpy (как в notes_embeddings).
При переезде на Python <=3.13 таблица embeddings готова для sqlite-vec.
"""

import hashlib
import json
import logging
import os
import sqlite3
from typing import Any

import numpy as np

from config import DATA_DIR
from services.notes_embeddings import (
    EMBED_MODEL,
    EmbeddingsError,
    _call_embed,
    is_model_available,
)

logger = logging.getLogger("FileIndex")

DB_FILE = os.path.join(DATA_DIR, "file_index.sqlite")
CHUNK_CHARS = 800
CHUNK_OVERLAP = 80
SEARCH_DEFAULT = 10
SNIPPET_CHARS = 160
MAX_TEXT = 2_000_000

STATUSES = ("pending", "indexed", "failed")

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS files (
    file_id TEXT PRIMARY KEY,
    note_id TEXT,
    filename TEXT NOT NULL,
    folder TEXT NOT NULL DEFAULT '',
    mime TEXT,
    size INTEGER NOT NULL DEFAULT 0,
    path TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'indexed', 'failed')),
    error TEXT,
    extracted_text TEXT,
    extra TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
    file_id UNINDEXED,
    chunk_index UNINDEXED,
    text
);

CREATE TABLE IF NOT EXISTS embeddings (
    file_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    vector BLOB NOT NULL,
    model TEXT NOT NULL,
    PRIMARY KEY (file_id, chunk_index, model)
);

CREATE TABLE IF NOT EXISTS kg_log (
    file_id TEXT PRIMARY KEY,
    added INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA journal_mode=WAL")
    for stmt in CREATE_SQL.split(";"):
        if stmt.strip():
            conn.execute(stmt)
    return conn


def chunk_text(text: str, chunk_chars: int = CHUNK_CHARS,
               overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Разбивает текст на чанки по chunk_chars символов с перекрытием overlap.

    Граничные случаи: пустой текст -> [], текст <= chunk_chars -> 1 чанк,
    чанк-окно целиком в пределах текста.
    """
    if not text:
        return []
    if chunk_chars < 1:
        raise ValueError("chunk_chars должен быть >= 1")
    if overlap < 0 or overlap >= chunk_chars:
        raise ValueError("overlap должен быть в [0, chunk_chars)")
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_chars, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def index_document(path: str, note_id: str | None = None,
                   folder: str = "") -> dict:
    """Индексирует один файл: чанки -> FTS5, статус indexed/failed.

    Returns: {file_id, status, chunks, added} где added=True если файл
    ранее не был в индексе (или содержимое изменилось).
    """
    with open(path, "rb") as f:
        content = f.read()
    file_id = _sha256(content)
    size = len(content)
    if size > MAX_TEXT:
        raise ValueError(f"Файл слишком большой: {size} байт (лимит {MAX_TEXT})")
    text = content.decode("utf-8", errors="replace")
    filename = os.path.basename(path)
    mime = _guess_mime(filename)
    extra = {"path": path, "mime": mime}
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT status, extracted_text FROM files WHERE file_id = ?",
            (file_id,),
        ).fetchone()
        added = row is None
        chunks = chunk_text(text)
        if added or row[1] != text:
            conn.execute("DELETE FROM files WHERE file_id = ?", (file_id,))
            conn.execute("DELETE FROM search_index WHERE file_id = ?", (file_id,))
            conn.execute("DELETE FROM embeddings WHERE file_id = ?", (file_id,))
            conn.execute(
                "INSERT INTO files (file_id, note_id, filename, folder, mime, size,"
                " path, status, extracted_text, extra, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (file_id, note_id, filename, folder, mime, size, path,
                 "indexed", text, json.dumps(extra, ensure_ascii=False),
                 _now(), _now()),
            )
            conn.executemany(
                "INSERT INTO search_index (file_id, chunk_index, text)"
                " VALUES (?,?,?)",
                [(file_id, i, c) for i, c in enumerate(chunks)],
            )
        else:
            conn.execute(
                "UPDATE files SET note_id = COALESCE(?, note_id), folder = ?,"
                " updated_at = ? WHERE file_id = ?",
                (note_id, folder, _now(), file_id),
            )
        conn.commit()
        return {"file_id": file_id, "status": "indexed",
                "chunks": len(chunks), "added": added}
    except sqlite3.Error as exc:
        conn.rollback()
        conn.close()
        try:
            conn2 = _connect()
            try:
                conn2.execute(
                    "INSERT INTO files (file_id, filename, size, status, error,"
                    " created_at, updated_at) VALUES (?,?,?,?,?,?,?)"
                    " ON CONFLICT(file_id) DO UPDATE SET status='failed', error=?,"
                    " updated_at=?",
                    (file_id, os.path.basename(path), size, "failed", str(exc),
                     _now(), _now(), str(exc), _now()),
                )
                conn2.commit()
            finally:
                conn2.close()
        except sqlite3.Error:
            logger.warning("[FILE_INDEX] не удалось записать failed-статус: %s", exc)
        return {"file_id": file_id, "status": "failed", "chunks": 0, "added": True}
    finally:
        conn.close()


def index_directory(directory: str) -> dict:
    """Индексирует все *.txt/*.md файлы в директории (без рекурсии).

    Returns: {total, added, failed: [{file_id, path, error}]}.
    """
    if not os.path.isdir(directory):
        raise FileNotFoundError(f"Директория не найдена: {directory}")
    result: dict[str, Any] = {"total": 0, "added": [], "failed": []}
    for name in sorted(os.listdir(directory)):
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        if not name.lower().endswith((".txt", ".md")):
            continue
        result["total"] += 1
        try:
            out = index_document(path, folder=os.path.basename(directory))
        except (OSError, ValueError) as exc:
            result["failed"].append({"path": path, "error": str(exc)})
            continue
        if out["status"] == "failed":
            result["failed"].append({"path": path, "error": out["status"]})
        elif out["added"]:
            result["added"].append(out["file_id"])
    return result


def search_files(query: str, limit: int = SEARCH_DEFAULT) -> list[dict]:
    """Полнотекстовый поиск по файлам (BM25), fallback на LIKE.

    Returns: [{file_id, filename, folder, snippet, _score}].
    """
    if limit < 1:
        raise ValueError("limit должен быть >= 1")
    if not query.strip():
        return []
    conn = _connect()
    try:
        try:
            rows = conn.execute(
                "SELECT f.file_id, f.filename, f.folder, s.text,"
                " bm25(search_index) AS score"
                " FROM search_index s JOIN files f ON f.file_id = s.file_id"
                " WHERE search_index MATCH ?"
                " ORDER BY score LIMIT ?",
                (query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        if not rows:
            like = f"%{query}%"
            rows = conn.execute(
                "SELECT f.file_id, f.filename, f.folder, f.extracted_text, 0.0"
                " FROM files f WHERE f.status = 'indexed'"
                " AND f.extracted_text LIKE ? ORDER BY f.updated_at DESC LIMIT ?",
                (like, limit),
            ).fetchall()
        return [{
            "file_id": r[0], "filename": r[1], "folder": r[2],
            "snippet": _snippet(r[3] or "", query), "_score": round(float(r[4]), 4),
        } for r in rows]
    finally:
        conn.close()


def search_similar(query: str, limit: int = SEARCH_DEFAULT,
                   model: str = EMBED_MODEL) -> list[dict]:
    """Гибрид: полнотекстовые результаты + семантические (косинус).

    Если модель эмбеддингов недоступна — возвращает fulltext-результаты
    (graceful degradation).
    """
    fulltext = search_files(query, limit=limit)
    if not is_model_available(model):
        return fulltext
    try:
        q_vec = np.asarray(_call_embed([query], model)[0], dtype=np.float32)
    except EmbeddingsError:
        return fulltext
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT e.file_id, e.vector FROM embeddings e WHERE e.model = ?",
            (model,),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return fulltext
    seen = {r["file_id"] for r in fulltext}
    scored: list[tuple[float, dict]] = []
    q_norm = np.linalg.norm(q_vec)
    for file_id, blob in rows:
        vec = np.frombuffer(blob, dtype=np.float32)
        norm = np.linalg.norm(vec)
        if q_norm == 0 or norm == 0:
            continue
        score = float(np.dot(q_vec, vec) / (q_norm * norm))
        if score > 0.5:
            scored.append((score, file_id))
    best: dict[str, float] = {}
    for score, file_id in sorted(scored, reverse=True):
        if file_id not in best:
            best[file_id] = score
    for file_id, score in best.items():
        if file_id in seen or len(fulltext) >= limit:
            continue
        meta = get_file(file_id)
        if meta:
            seen.add(file_id)
            fulltext.append({
                "file_id": file_id, "filename": meta["filename"],
                "folder": meta.get("folder", ""),
                "snippet": (meta.get("extracted_text") or "")[:SNIPPET_CHARS],
                "_score": round(score, 4),
            })
    return fulltext[:limit]


def build_embeddings(force: bool = False, model: str = EMBED_MODEL) -> bool:
    """Считает эмбеддинги всех чанков и сохраняет в таблицу embeddings.

    Returns False (graceful) если модель недоступна или нет чанков.
    """
    if not is_model_available(model):
        logger.warning("[FILE_INDEX] %s недоступна — эмбеддинги файлов выключены", model)
        return False
    conn = _connect()
    try:
        chunks = conn.execute(
            "SELECT file_id, chunk_index, text FROM search_index ORDER BY file_id, chunk_index"
        ).fetchall()
    finally:
        conn.close()
    if not chunks:
        return False
    texts = [row[2] for row in chunks]
    vectors: list[list[float]] = []
    try:
        for i in range(0, len(texts), 40):
            vectors.extend(_call_embed(texts[i:i + 40], model))
    except EmbeddingsError as exc:
        logger.warning("[FILE_INDEX] embed failed: %s", exc)
        return False
    if len(vectors) != len(chunks):
        logger.warning("[FILE_INDEX] размер ответа не совпал: %d != %d",
                       len(vectors), len(chunks))
        return False
    conn = _connect()
    try:
        if force:
            conn.execute("DELETE FROM embeddings WHERE model = ?", (model,))
        conn.executemany(
            "INSERT OR IGNORE INTO embeddings (file_id, chunk_index, vector, model)"
            " VALUES (?,?,?,?)",
            [(row[0], row[1], np.asarray(v, dtype=np.float32).tobytes(), model)
             for row, v in zip(chunks, vectors)],
        )
        conn.commit()
    except sqlite3.Error as exc:
        logger.warning("[FILE_INDEX] embeddings write failed: %s", exc)
        return False
    finally:
        conn.close()
    logger.info("[FILE_INDEX] embeddings built: %d chunks", len(chunks))
    return True


def file_stats() -> dict:
    conn = _connect()
    try:
        total, indexed, failed = conn.execute(
            "SELECT COUNT(*),"
            " COALESCE(SUM(status='indexed'), 0),"
            " COALESCE(SUM(status='failed'), 0) FROM files"
        ).fetchone()
        chunks = conn.execute("SELECT COUNT(*) FROM search_index").fetchone()[0]
        bytes_total = conn.execute(
            "SELECT COALESCE(SUM(size), 0) FROM files"
        ).fetchone()[0]
        embedded = conn.execute("SELECT COUNT(DISTINCT file_id) FROM embeddings").fetchone()[0]
    finally:
        conn.close()
    return {
        "total_files": int(total), "indexed": int(indexed), "failed": int(failed),
        "total_chunks": int(chunks), "size_bytes": int(bytes_total),
        "embedded_files": int(embedded),
    }


def get_file(file_id: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT file_id, note_id, filename, folder, mime, size, status,"
            " extracted_text, extra, created_at, updated_at"
            " FROM files WHERE file_id = ?", (file_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {
        "file_id": row[0], "note_id": row[1], "filename": row[2],
        "folder": row[3] or "", "mime": row[4], "size": int(row[5] or 0),
        "status": row[6], "extracted_text": row[7],
        "extra": json.loads(row[8]) if row[8] else {},
        "created_at": row[9], "updated_at": row[10],
    }


def delete_file(file_id: str) -> bool:
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM files WHERE file_id = ?", (file_id,))
        if cur.rowcount == 0:
            return False
        conn.execute("DELETE FROM search_index WHERE file_id = ?", (file_id,))
        conn.execute("DELETE FROM embeddings WHERE file_id = ?", (file_id,))
        conn.execute("DELETE FROM kg_log WHERE file_id = ?", (file_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def log_kg_facts(file_id: str, added: int, error: str | None = None) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO kg_log (file_id, added, error, created_at)"
            " VALUES (?,?,?,?)"
            " ON CONFLICT(file_id) DO UPDATE SET added = added + excluded.added,"
            " error = excluded.error, created_at = excluded.created_at",
            (file_id, added, error, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_kg_log(file_id: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT file_id, added, error, created_at FROM kg_log WHERE file_id = ?",
            (file_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {"file_id": row[0], "added": int(row[1]),
            "error": row[2], "created_at": row[3]}


def _snippet(text: str, query: str, chars: int = SNIPPET_CHARS) -> str:
    low = text.lower()
    idx = low.find(query.lower())
    if idx > chars // 2:
        text = "…" + text[idx - chars // 2:]
    return text[:chars].replace("\n", " ")


def _guess_mime(filename: str) -> str:
    lowered = filename.lower()
    if lowered.endswith(".txt"):
        return "text/plain"
    if lowered.endswith(".md"):
        return "text/markdown"
    if lowered.endswith(".pdf"):
        return "application/pdf"
    return "application/octet-stream"
