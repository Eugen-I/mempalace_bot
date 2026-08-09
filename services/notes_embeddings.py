"""services/notes_embeddings.py — семантический поиск по Apple Notes.

Эмбеддинги заметок (name + preview) считаются локальной моделью Ollama
(bge-m3) и хранятся в SQLite (DATA_DIR/notes_embeddings.sqlite).
Поиск — косинусная близость вектора запроса к векторам заметок.

Graceful degradation: если модель недоступна или не скачана, функции
возвращают пустые результаты — вызывающий код падает обратно на
полнотекстовый поиск (search_notes).
"""

import json
import logging
import os
import sqlite3
import urllib.error
import urllib.request

import numpy as np

from config import DATA_DIR
from services.apple_notes import AppleNotesError, list_notes

logger = logging.getLogger("NotesEmbeddings")

EMBED_MODEL = "bge-m3"
EMBED_URL = "http://localhost:11434/api/embed"
EMBED_DIM = 1024
DB_FILE = os.path.join(DATA_DIR, "notes_embeddings.sqlite")
BATCH_SIZE = 40
HTTP_TIMEOUT = 90.0
TOP_DEFAULT = 10
SNIPPET_CHARS = 120


class EmbeddingsError(Exception):
    """Ошибка семантического поиска (модель недоступна и т.п.)."""


def _call_embed(inputs: list[str], model: str = EMBED_MODEL) -> list[list[float]]:
    """Вызывает /api/embed Ollama (синхронно, urllib)."""
    if not inputs:
        return []
    payload = json.dumps({"model": model, "input": inputs}, ensure_ascii=False)
    req = urllib.request.Request(
        EMBED_URL, data=payload.encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(  # nosec B310 — URL фиксированный
                req, timeout=HTTP_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise EmbeddingsError(f"Ollama embed недоступен: {exc}") from exc
    embeddings = data.get("embeddings") if isinstance(data, dict) else None
    if not embeddings:
        raise EmbeddingsError("Ollama вернул пустые эмбеддинги.")
    return embeddings


def is_model_available(model: str = EMBED_MODEL) -> bool:
    """True, если модель эмбеддингов есть в Ollama (/api/show)."""
    payload = json.dumps({"model": model}).encode("utf-8")
    req = urllib.request.Request(
        "http://localhost:11434/api/show", data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(  # nosec B310 — URL фиксированный
                req, timeout=10.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return bool(
            isinstance(data, dict)
            and (data.get("model") or data.get("model_info"))
        )
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS notes_embeddings ("
        "note_id TEXT PRIMARY KEY, name TEXT, folder TEXT, preview TEXT, "
        "vector BLOB NOT NULL, model TEXT NOT NULL)",
    )
    return conn


def _index_matches(conn: sqlite3.Connection, model: str = EMBED_MODEL) -> bool:
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM notes_embeddings WHERE model = ?", (model,),
        ).fetchone()[0]
    except sqlite3.Error:
        return False
    return count == len(list_notes())


def build_index(force: bool = False, model: str = EMBED_MODEL) -> bool:
    """Считает эмбеддинги всех заметок и сохраняет их в SQLite.

    Возвращает False при недоступности модели или пустом индексе заметок
    (вызывающий код продолжает с полнотекстовым поиском).
    """
    if not is_model_available(model):
        logger.warning("[SEMANTIC] %s не скачана — семантический поиск выключен", model)
        return False
    if not force:
        try:
            conn = _connect()
            try:
                if _index_matches(conn, model):
                    return True
            finally:
                conn.close()
        except sqlite3.Error:
            pass
    notes = list_notes()
    if not notes:
        return False
    texts = [f"{n.get('name', '')}\n{n.get('preview', '')}" for n in notes]
    vectors: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        vectors.extend(_call_embed(texts[i:i + BATCH_SIZE], model))
    try:
        conn = _connect()
        try:
            conn.execute("DELETE FROM notes_embeddings")
            for note, vec in zip(notes, vectors):
                if len(vec) != EMBED_DIM:
                    continue
                conn.execute(
                    "INSERT OR REPLACE INTO notes_embeddings "
                    "(note_id, name, folder, preview, vector, model) VALUES (?,?,?,?,?,?)",
                    (
                        note["id"], note.get("name", ""), note.get("folder", ""),
                        (note.get("preview") or "")[:500],
                        np.asarray(vec, dtype=np.float32).tobytes(), model,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        logger.warning("[SEMANTIC] index write failed: %s", exc)
        return False
    logger.info("[SEMANTIC] index built: %d notes", len(vectors))
    return True


def _cosine(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    norm = float(np.linalg.norm(vec_a) * np.linalg.norm(vec_b))
    if norm == 0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / norm)


def search_semantic(query: str, limit: int = TOP_DEFAULT,
                    model: str = EMBED_MODEL) -> list[dict]:
    """Косинусный поиск по эмбеддингам заметок. [] при недоступности.

    Результаты: [{id, name, folder, snippet, _score}] по убыванию близости.
    """
    if limit < 1:
        raise EmbeddingsError("limit должен быть ≥ 1.")
    if not is_model_available(model):
        return []
    try:
        build_index(model=model)
    except EmbeddingsError as exc:
        logger.warning("[SEMANTIC] build failed: %s", exc)
        return []
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT note_id, name, folder, preview, vector FROM notes_embeddings "
            "WHERE model = ?", (model,),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return []
    try:
        q_vec = np.asarray(_call_embed([query], model)[0], dtype=np.float32)
    except EmbeddingsError as exc:
        logger.warning("[SEMANTIC] query embed failed: %s", exc)
        return []
    scored: list[tuple[float, dict]] = []
    for note_id, name, folder, preview, blob in rows:
        vec = np.frombuffer(blob, dtype=np.float32)
        if len(vec) != EMBED_DIM:
            continue
        score = _cosine(q_vec, vec)
        if score > 0:
            scored.append((score, {
                "id": note_id, "name": name or "?", "folder": folder or "?",
                "snippet": (preview or "")[:SNIPPET_CHARS], "_score": round(score, 4),
            }))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item for _, item in scored[:limit]]


def search_notes_hybrid(query: str, limit: int = TOP_DEFAULT) -> list[dict]:
    """Гибрид: полнотекстовый поиск + семантическое дополнение.

    Сначала полнотекстовые результаты (сниппет вокруг совпадения), затем
    семантические, отсутствующие в полнотекстовых. Каждая запись: id/name/
    folder/snippet/_score.
    """
    from services.apple_notes import search_notes

    if limit < 1:
        raise AppleNotesError("limit должен быть ≥ 1.")
    fulltext = search_notes(query, limit=limit)
    seen = {n["id"] for n in fulltext}
    try:
        semantic = search_semantic(query, limit=limit)
    except EmbeddingsError:
        semantic = []
    for item in semantic:
        if item["id"] not in seen:
            seen.add(item["id"])
            fulltext.append(item)
            if len(fulltext) >= limit:
                break
    return fulltext
