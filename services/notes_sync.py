"""services/notes_sync.py — Синхронизация и обратные связи между Apple Notes и MemPalace.

Обеспечивает:
1. Хранение обратных связей между ящиками Дворца (drawer_id) и источниками (Apple Notes).
2. Автоматический подбор подходящего крыла и комнаты во Дворце по содержанию заметки.
3. Чекер обновлений: автоматическая проверка хеша (SHA-256) заметки и актуализация ящика.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import logging
from typing import Any

from config import BOT_STATE_DB_PATH
from services.db_pool import db_cursor, get_connection

logger = logging.getLogger("NotesSync")

RECOMMEND_ROOM_PROMPT = """Ты — дворецкий цифрового Дворца Памяти (MemPalace).
Твоя задача — классифицировать заметку и выбрать подходящее крыло (wing) и комнату (room).
Если ни одна комната не подходит, выбери близкое крыло и предложи лаконичную новую комнату.

Существующая таксономия Дворца:
{taxonomy}

Заметка:
Название: {title}
Текст:
{body}

Ответь строго в формате JSON без дополнительного текста:
{{
  "wing": "название_крыла",
  "room": "название_комнаты",
  "reason": "краткое объяснение в 1 предложение"
}}
"""


def init_backlinks_db(db_path: str = BOT_STATE_DB_PATH) -> None:
    """Создаёт таблицу drawer_backlinks и индексы при необходимости."""
    conn = get_connection(db_path)
    with db_cursor(conn) as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS drawer_backlinks (
                drawer_id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                source_title TEXT DEFAULT '',
                wing TEXT NOT NULL,
                room TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                last_synced_at TEXT NOT NULL
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_drawer_backlinks_source
            ON drawer_backlinks (source_type, source_id);
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_drawer_backlinks_wing_room
            ON drawer_backlinks (wing, room);
            """
        )
        conn.commit()


def compute_content_hash(text: str) -> str:
    """Возвращает стабильный SHA-256 хеш нормализованного текста."""
    normalized = (text or "").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def record_backlink(
    drawer_id: str,
    source_type: str,
    source_id: str,
    wing: str,
    room: str,
    content: str,
    title: str = "",
    db_path: str = BOT_STATE_DB_PATH,
) -> dict[str, Any]:
    """Сохраняет или обновляет обратную связь между ящиком и источником."""
    init_backlinks_db(db_path)
    c_hash = compute_content_hash(content)
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = get_connection(db_path)
    with db_cursor(conn) as cur:
        cur.execute(
            """
            INSERT OR REPLACE INTO drawer_backlinks
            (drawer_id, source_type, source_id, source_title, wing, room,
             content_hash, last_synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (drawer_id, source_type, str(source_id), title or "", wing, room, c_hash, now_iso),
        )
        conn.commit()
    logger.info("Recorded backlink %s -> %s:%s", drawer_id, source_type, source_id)
    return {
        "drawer_id": drawer_id,
        "source_type": source_type,
        "source_id": str(source_id),
        "source_title": title or "",
        "wing": wing,
        "room": room,
        "content_hash": c_hash,
        "last_synced_at": now_iso,
    }


def get_backlink_by_drawer(
    drawer_id: str, db_path: str = BOT_STATE_DB_PATH,
) -> dict[str, Any] | None:
    """Возвращает информацию об источнике по drawer_id."""
    init_backlinks_db(db_path)
    conn = get_connection(db_path)
    with db_cursor(conn) as cur:
        cur.execute(
            """
            SELECT drawer_id, source_type, source_id, source_title, wing, room,
                   content_hash, last_synced_at
            FROM drawer_backlinks
            WHERE drawer_id = ?
            """,
            (drawer_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "drawer_id": row[0],
            "source_type": row[1],
            "source_id": row[2],
            "source_title": row[3],
            "wing": row[4],
            "room": row[5],
            "content_hash": row[6],
            "last_synced_at": row[7],
        }


def get_backlinks_by_source(
    source_type: str,
    source_id: str,
    db_path: str = BOT_STATE_DB_PATH,
) -> list[dict[str, Any]]:
    """Возвращает все ящики, привязанные к данному источнику."""
    init_backlinks_db(db_path)
    conn = get_connection(db_path)
    with db_cursor(conn) as cur:
        cur.execute(
            """
            SELECT drawer_id, source_type, source_id, source_title, wing, room,
                   content_hash, last_synced_at
            FROM drawer_backlinks
            WHERE source_type = ? AND source_id = ?
            """,
            (source_type, str(source_id)),
        )
        rows = cur.fetchall()
        return [
            {
                "drawer_id": r[0],
                "source_type": r[1],
                "source_id": r[2],
                "source_title": r[3],
                "wing": r[4],
                "room": r[5],
                "content_hash": r[6],
                "last_synced_at": r[7],
            }
            for r in rows
        ]


def delete_backlink(drawer_id: str, db_path: str = BOT_STATE_DB_PATH) -> None:
    """Удаляет связь при удалении ящика."""
    init_backlinks_db(db_path)
    conn = get_connection(db_path)
    with db_cursor(conn) as cur:
        cur.execute("DELETE FROM drawer_backlinks WHERE drawer_id = ?", (drawer_id,))
        conn.commit()


def list_all_backlinks(
    source_type: str | None = None,
    db_path: str = BOT_STATE_DB_PATH,
) -> list[dict[str, Any]]:
    """Список всех обратных связей."""
    init_backlinks_db(db_path)
    conn = get_connection(db_path)
    with db_cursor(conn) as cur:
        if source_type:
            cur.execute(
                """
                SELECT drawer_id, source_type, source_id, source_title, wing, room,
                       content_hash, last_synced_at
                FROM drawer_backlinks WHERE source_type = ?
                """,
                (source_type,),
            )
        else:
            cur.execute(
                """
                SELECT drawer_id, source_type, source_id, source_title, wing, room,
                       content_hash, last_synced_at
                FROM drawer_backlinks
                """
            )
        rows = cur.fetchall()
        return [
            {
                "drawer_id": r[0],
                "source_type": r[1],
                "source_id": r[2],
                "source_title": r[3],
                "wing": r[4],
                "room": r[5],
                "content_hash": r[6],
                "last_synced_at": r[7],
            }
            for r in rows
        ]


async def recommend_room_for_note(
    title: str,
    body: str,
    taxonomy: dict | None = None,
) -> dict[str, str]:
    """Автоподбор подходящего крыла и комнаты во Дворце через LLM с fallback."""
    if taxonomy is None:
        try:
            from services.palace_mcp import get_mcp
            tax_raw = await get_mcp().call_tool("mempalace_get_taxonomy")
            data = json.loads(tax_raw) if tax_raw else {}
            taxonomy = data.get("taxonomy", {})
        except Exception as e:
            logger.warning("[NotesSync] Failed to fetch taxonomy from MCP: %s", e)
            taxonomy = {}

    tax_summary_lines = []
    if isinstance(taxonomy, dict):
        for wing_name, rooms in taxonomy.items():
            if isinstance(rooms, dict):
                room_keys = list(rooms.keys())
            elif isinstance(rooms, list):
                room_keys = rooms
            else:
                room_keys = []
            tax_summary_lines.append(f"- {wing_name}: {', '.join(room_keys[:12])}")
    tax_text = "\n".join(tax_summary_lines) or "Крылья: my_notes, личные_мысли, projects"

    prompt_body = (body or "")[:1500]
    prompt_text = RECOMMEND_ROOM_PROMPT.format(
        taxonomy=tax_text,
        title=title or "Без названия",
        body=prompt_body,
    )

    try:
        from services.ai_engine import get_ai_response_async, get_current_ai

        engine, model = get_current_ai()
        raw = await get_ai_response_async(
            engine,
            model,
            [
                {"role": "user", "content": prompt_text},
            ],
        )
        cleaned = raw.strip()
        for pfx in ("```json", "```"):
            cleaned = cleaned.removeprefix(pfx)
        cleaned = cleaned.removesuffix("```").strip()
        parsed = json.loads(cleaned)
        wing = str(parsed.get("wing") or "my_notes").strip()
        room = str(parsed.get("room") or "inbox").strip()
        reason = str(parsed.get("reason") or "По смыслу заметки").strip()
        return {"wing": wing, "room": room, "reason": reason}
    except Exception as exc:
        logger.warning("[NotesSync] LLM classification error: %s. Using heuristic.", exc)
        from services.wing_classifier import classify_wing
        query = f"{title} {body[:200]}".strip()
        wing = classify_wing(query) or "my_notes"
        return {
            "wing": wing,
            "room": "inbox",
            "reason": "Автоподбор по ключевым словам",
        }


async def check_and_sync_note_updates(
    note_id: str | None = None,
    db_path: str = BOT_STATE_DB_PATH,
) -> dict[str, Any]:
    """Проверяет обновления в Apple Notes и обновляет соответствующие ящики во Дворце."""
    from services.apple_notes import read_note
    from services.palace_mcp import get_mcp

    links = (
        get_backlinks_by_source("apple_notes", str(note_id), db_path=db_path)
        if note_id
        else list_all_backlinks("apple_notes", db_path=db_path)
    )

    if not links:
        return {"checked": 0, "updated": 0, "drawers": []}

    updated_drawers = []
    mcp = get_mcp()

    for link in links:
        n_id = link["source_id"]
        drawer_id = link["drawer_id"]
        try:
            loop = asyncio.get_running_loop()
            note_data = await loop.run_in_executor(None, read_note, n_id)
            if not note_data:
                continue

            name = note_data.get("name") or link.get("source_title") or "Заметка"
            body = note_data.get("body") or ""
            full_text = f"📄 {name}\n\n{body}" if body else name
            curr_hash = compute_content_hash(full_text)

            if curr_hash != link["content_hash"]:
                logger.info(
                    "[NotesSync] Detected change in note %s (drawer %s). Updating...",
                    n_id,
                    drawer_id,
                )
                raw_res = await mcp.call_tool(
                    "mempalace_update_drawer",
                    {
                        "drawer_id": drawer_id,
                        "content": full_text,
                        "content_hash": curr_hash,
                        "source_id": n_id,
                        "source_type": "apple_notes",
                    },
                )
                now_iso = datetime.now(timezone.utc).isoformat()
                conn = get_connection(db_path)
                with db_cursor(conn) as cur:
                    cur.execute(
                        """
                        UPDATE drawer_backlinks
                        SET content_hash = ?, source_title = ?, last_synced_at = ?
                        WHERE drawer_id = ?
                        """,
                        (curr_hash, name, now_iso, drawer_id),
                    )
                    conn.commit()

                updated_drawers.append(
                    {
                        "drawer_id": drawer_id,
                        "source_id": n_id,
                        "title": name,
                        "wing": link["wing"],
                        "room": link["room"],
                        "mcp_result": raw_res,
                    }
                )
        except Exception as exc:
            logger.warning(
                "[NotesSync] Error syncing note %s / drawer %s: %s",
                n_id,
                drawer_id,
                exc,
            )

    return {
        "checked": len(links),
        "updated": len(updated_drawers),
        "drawers": updated_drawers,
    }
