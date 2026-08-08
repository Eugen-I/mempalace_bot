"""services/digest.py — утренний дайджест MemPalace.

Три блока:
  1. Напоминания дня — из kv_store (namespace "reminders"), remind_at
     попадает в сегодняшние сутки (локальное время).
  2. Заметки вчера — файлы .txt/.md в NOTES_DIR, изменённые вчера
     (mtime ∈ [вчера 00:00, сегодня 00:00)).
  3. Сводка графа знаний — через MCP-инструмент mempalace_kg_stats
     (реальный контракт из cli/commands.py: entities/triples/current_facts).

Каждый источник толерантен к ошибкам — не роняет весь дайджест.
Автозапуск: в окне [DIGEST_START_HOUR, DIGEST_END_HOUR) один раз в день
(отметка last_send_ymd в kv_store, namespace "digest").
"""

import json
import logging
import os
from datetime import datetime, timedelta

from services.kv_store import get_kv_store

logger = logging.getLogger("Digest")

DIGEST_NS = "digest"
REMINDER_NS = "reminders"
LAST_SEND_KEY = "last_send_ymd"
NOTE_EXTS = (".txt", ".md")
MAX_REMINDERS = 10
MAX_NOTES = 5
DIGEST_START_HOUR = 8
DIGEST_END_HOUR = 10
DIGEST_TITLE = "☀️ <b>Утренний дайджест</b>\n"


def _day_bounds(now_ts: float | None = None) -> tuple[float, float]:
    """[начало сегодняшних суток, начало завтрашних суток) в локальном времени."""
    now = datetime.fromtimestamp(now_ts) if now_ts else datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.timestamp(), (start + timedelta(days=1)).timestamp()


def _yesterday_bounds(now_ts: float | None = None) -> tuple[float, float]:
    start, _ = _day_bounds(now_ts)
    return start - timedelta(days=1).total_seconds(), start


def collect_today_reminders(
    now_ts: float | None = None, kv=None,
) -> list[dict]:
    """Напоминания на сегодня, отсортированные по remind_at (максимум MAX_REMINDERS)."""
    kv = kv or get_kv_store()
    start, end = _day_bounds(now_ts)
    try:
        keys = kv.keys(namespace=REMINDER_NS)
    except Exception as exc:  # noqa: BLE001 — источник не должен ронять дайджест
        logger.warning("[DIGEST] kv keys failed: %s", exc)
        return []
    out = []
    for key in keys:
        try:
            data = kv.get(key, namespace=REMINDER_NS)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[DIGEST] kv get failed for %s: %s", key, exc)
            continue
        if not isinstance(data, dict):
            continue
        ts = data.get("remind_at", 0)
        if start <= ts < end:
            out.append(data)
    out.sort(key=lambda d: d.get("remind_at", 0))
    return out[:MAX_REMINDERS]


def collect_yesterday_notes(
    now_ts: float | None = None, notes_dir: str | None = None,
) -> list[dict]:
    """Файлы .txt/.md, изменённые вчера. Возвращает {name, path, mtime} по имени."""
    if notes_dir is None:
        from config import NOTES_DIR

        notes_dir = NOTES_DIR
    start, end = _yesterday_bounds(now_ts)
    if not os.path.isdir(notes_dir):
        return []
    out = []
    for name in sorted(os.listdir(notes_dir)):
        if not name.lower().endswith(NOTE_EXTS):
            continue
        path = os.path.join(notes_dir, name)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if start <= mtime < end:
            out.append({"name": name, "path": path, "mtime": mtime})
    return out[:MAX_NOTES]


async def collect_kg_summary(mcp_cb=None) -> dict:
    """Сводка графа знаний (mempalace_kg_stats). Толерантно к ошибкам."""
    if mcp_cb is None:
        async def _default_cb() -> str:
            from services.palace_mcp import get_mcp

            mcp = get_mcp()
            return await mcp.call_tool("mempalace_kg_stats")

        mcp_cb = _default_cb
    try:
        raw = await mcp_cb()
        parsed = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[DIGEST] kg summary failed: %s", exc)
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {k: v for k, v in parsed.items() if isinstance(v, (int, float))}


def _fmt_reminder(reminder: dict) -> str:
    ts = reminder.get("remind_at", 0)
    try:
        time_str = datetime.fromtimestamp(ts).strftime("%H:%M")
    except (OverflowError, OSError, ValueError):
        time_str = "?"
    text = reminder.get("text", "")
    return f"⏰ {time_str} — {text}"


def build_digest_text(
    reminders: list[dict],
    notes: list[dict],
    kg_summary: dict,
    now_ts: float | None = None,
) -> str:
    """Формирует текст дайджеста (HTML). Возвращает "" если блоков нет."""
    from services.text_formatter import safe_html_format

    now = datetime.fromtimestamp(now_ts) if now_ts else datetime.now()
    date_str = now.strftime("%d.%m.%Y")
    lines: list[str] = [f"☀️ <b>Утренний дайджест</b> — {date_str}\n"]

    if reminders:
        lines.append("📅 <b>Напоминания на сегодня:</b>")
        for r in reminders:
            lines.append(safe_html_format(_fmt_reminder(r)))
        lines.append("")

    if notes:
        lines.append("📝 <b>Заметки вчера:</b>")
        for n in notes:
            lines.append(f"• {safe_html_format(n['name'])}")
        lines.append("")

    if kg_summary:
        parts = [
            f"{interpreter_name(k)}: {v}"
            for k, v in kg_summary.items()
            if v > 0
        ]
        if parts:
            lines.append("🧠 <b>Граф знаний:</b>")
            lines.append("  " + " | ".join(parts))
            lines.append("")

    text = "\n".join(lines).strip()
    return "" if text == f"☀️ <b>Утренний дайджест</b> — {date_str}" else text


def interpreter_name(key: str) -> str:
    """Человекочитаемое имя ключа статистики KG (fallback — сам ключ)."""
    try:
        from services.interpreter import display_name

        return display_name(key)
    except Exception:  # noqa: BLE001
        return key


async def send_digest_to_chat(bot, chat_id: int, now_ts: float | None = None, kv=None) -> bool:
    """Собирает и отправляет дайджест в чат. Возвращает True, если отправлено."""
    kv = kv or get_kv_store()
    reminders = collect_today_reminders(now_ts, kv=kv)
    notes = collect_yesterday_notes(now_ts)
    kg = await collect_kg_summary()
    text = build_digest_text(reminders, notes, kg, now_ts)
    if not text:
        return False
    await bot.send_message(chat_id, text, parse_mode="HTML")
    return True


def _digest_window_open(now_ts: float | None = None) -> bool:
    now = datetime.fromtimestamp(now_ts) if now_ts else datetime.now()
    return DIGEST_START_HOUR <= now.hour < DIGEST_END_HOUR


async def maybe_send_daily_digest(bot, now_ts: float | None = None, kv=None) -> bool:
    """Автозапуск: в утреннем окне шлёт дайджест один раз в день.

    Отправляет в уникальные chat_id из напоминаний. Отметка ставится всегда
    при попытке в окне, чтобы ошибка отправки не спамила каждые 5 минут.
    """
    kv = kv or get_kv_store()
    now = datetime.fromtimestamp(now_ts) if now_ts else datetime.now()
    if not _digest_window_open(now_ts):
        return False
    ymd = now.strftime("%Y-%m-%d")
    try:
        if kv.get(LAST_SEND_KEY, namespace=DIGEST_NS) == ymd:
            return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("[DIGEST] last_send check failed: %s", exc)
    reminders = collect_today_reminders(now_ts, kv=kv)
    chat_ids = sorted({
        int(r.get("chat_id")) for r in reminders if r.get("chat_id") is not None
    })
    for chat_id in chat_ids:
        try:
            await send_digest_to_chat(bot, chat_id, now_ts, kv=kv)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[DIGEST] send to %s failed: %s", chat_id, exc)
    try:
        kv.set(LAST_SEND_KEY, ymd, namespace=DIGEST_NS, ttl=None)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[DIGEST] last_send mark failed: %s", exc)
    return True
