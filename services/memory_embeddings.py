"""services/memory_embeddings.py — семантический поиск по долговременной памяти.

Тот же принцип, что в notes_embeddings.py: эмбеддинги фактов памяти
считаются локальной моделью Ollama (bge-m3) и хранятся в SQLite
(DATA_DIR/memory_embeddings.sqlite). Поиск — косинусная близость вектора
запроса к векторам фактов конкретного пользователя.

Graceful degradation: если модель недоступна или не скачана, функции
возвращают пустые результаты — вызывающий код (retrieve_facts) остаётся
на полнотекстовом keyword-поиске.
"""

import logging
import os
import sqlite3

import numpy as np

from config import DATA_DIR
from services.notes_embeddings import (
    EMBED_DIM,
    EMBED_MODEL,
    EmbeddingsError,
    _call_embed,
    _cosine,
    is_model_available,
)

logger = logging.getLogger("MemoryEmbeddings")

DB_FILE = os.path.join(DATA_DIR, "memory_embeddings.sqlite")
BATCH_SIZE = 40
TOP_DEFAULT = 5


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS memory_embeddings ("
        "user_id INTEGER NOT NULL, fact TEXT NOT NULL, vector BLOB NOT NULL, "
        "model TEXT NOT NULL, PRIMARY KEY (user_id, fact))",
    )
    return conn


def _facts_of(user_id: int) -> list[str]:
    from services.memory import _load_memories

    return [m.get("fact", "") for m in _load_memories(user_id) if m.get("fact")]


def _index_matches(conn: sqlite3.Connection, user_id: int,
                   model: str = EMBED_MODEL) -> bool:
    """True, если в индексе ровно столько фактов юзера, сколько на диске."""
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM memory_embeddings WHERE user_id = ? AND model = ?",
            (user_id, model),
        ).fetchone()[0]
    except sqlite3.Error:
        return False
    return count == len(_facts_of(user_id))


def build_index(user_id: int, force: bool = False,
                model: str = EMBED_MODEL) -> bool:
    """Считает эмбеддинги фактов памяти юзера и сохраняет их в SQLite.

    Возвращает False при недоступности модели или пустом наборе фактов
    (вызывающий код продолжает с keyword-поиском).
    """
    if not is_model_available(model):
        logger.warning("[MEMORY-SEMANTIC] %s не скачана — семантика выключена", model)
        return False
    facts = _facts_of(user_id)
    if not facts:
        return False
    if not force:
        try:
            conn = _connect()
            try:
                if _index_matches(conn, user_id, model):
                    return True
            finally:
                conn.close()
        except sqlite3.Error:
            pass
    vectors: list[list[float]] = []
    for i in range(0, len(facts), BATCH_SIZE):
        vectors.extend(_call_embed(facts[i:i + BATCH_SIZE], model))
    try:
        conn = _connect()
        try:
            conn.execute(
                "DELETE FROM memory_embeddings WHERE user_id = ?", (user_id,),
            )
            for fact, vec in zip(facts, vectors):
                if len(vec) != EMBED_DIM:
                    continue
                conn.execute(
                    "INSERT OR REPLACE INTO memory_embeddings "
                    "(user_id, fact, vector, model) VALUES (?,?,?,?)",
                    (
                        user_id, fact,
                        np.asarray(vec, dtype=np.float32).tobytes(), model,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        logger.warning("[MEMORY-SEMANTIC] index write failed: %s", exc)
        return False
    logger.info("[MEMORY-SEMANTIC] index built: %d facts for user %d",
                len(vectors), user_id)
    return True


def search_similar(query: str, user_id: int, limit: int = TOP_DEFAULT,
                   model: str = EMBED_MODEL) -> list[dict]:
    """Косинусный поиск по эмбеддингам фактов памяти. [] при недоступности.

    Индекс юзера пересобирается автоматически, если набор фактов изменился.
    Результаты: [{fact, _score}] по убыванию близости.
    """
    if limit < 1:
        raise EmbeddingsError("limit должен быть ≥ 1.")
    if not query or not query.strip():
        return []
    if not is_model_available(model):
        return []
    try:
        build_index(user_id, model=model)
    except EmbeddingsError as exc:
        logger.warning("[MEMORY-SEMANTIC] build failed: %s", exc)
        return []
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT fact, vector FROM memory_embeddings "
            "WHERE user_id = ? AND model = ?", (user_id, model),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return []
    try:
        q_vec = np.asarray(_call_embed([query], model)[0], dtype=np.float32)
    except EmbeddingsError as exc:
        logger.warning("[MEMORY-SEMANTIC] query embed failed: %s", exc)
        return []
    scored: list[tuple[float, dict]] = []
    for fact, blob in rows:
        try:
            vec = np.frombuffer(blob, dtype=np.float32)
        except ValueError:
            continue
        if len(vec) != EMBED_DIM:
            continue
        score = _cosine(q_vec, vec)
        if score > 0:
            scored.append((score, {"fact": fact, "_score": round(score, 4)}))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item for _, item in scored[:limit]]
