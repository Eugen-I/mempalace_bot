import logging
import os

from services.kv_store import get_kv_store
from services.palace_bridge import palace_status, palace_compress, palace_repair
from services.palace_bridge import palace_compact, palace_wake_up
from services.palace_mcp import get_mcp
from services.pdf_engine import extract_pdf_async, list_archived_pdfs
from services.youtube import download_video, download_audio, transcribe_audio

logger = logging.getLogger("CLIExtras")


# ── Reminders ────────────────────────────────────────────────────────────────
async def cli_remind(text: str, user_id: int = 0):
    from handlers.reminder import _is_reminder, _parse_reminder

    clean = text.replace("/remind", "", 1).strip()
    if not clean:
        return (
            "❌ Укажите: /remind <текст>\n"
            "  Например: /remind завтра в 15:00 позвонить маме\n"
            "  /remind через 2 часа выключить духовку"
        )
    if not _is_reminder(clean):
        return "❌ Не похоже на напоминание. Используйте: /remind через 2 часа <действие>"

    parsed = await _parse_reminder(clean)
    if not parsed:
        return "❌ Не удалось разобрать время/текст напоминания."

    kv = get_kv_store()
    reminders = kv.get("reminders") or []
    reminders.append(parsed)
    kv.set("reminders", reminders)
    return f"✅ Напоминание создано: {parsed.get('text', clean)} — в {parsed.get('time_str', '?')}"


# ── PDF ──────────────────────────────────────────────────────────────────────
async def cli_pdfs(args: str = ""):
    parts = args.strip().split()
    if not parts or parts[0] == "":
        pdfs = list_archived_pdfs()
        if not pdfs:
            return "📄 Архив PDF пуст."
        lines = [f"📄 Архив PDF ({len(pdfs)}):"]
        for i, p in enumerate(pdfs, 1):
            lines.append(f"  {i}) {p.get('original_name', p['id'])}")
        return "\n".join(lines)

    if parts[0].isdigit():
        pdfs = list_archived_pdfs()
        idx = int(parts[0])
        if not pdfs or idx < 1 or idx > len(pdfs):
            return "❌ Неверный номер PDF."
        pdf = pdfs[idx - 1]
        text, meta = await extract_pdf_async(pdf["path"])
        if not text:
            return "❌ Не удалось извлечь текст."
        preview = text[:2000]
        return (
            f"📄 {pdf.get('original_name', pdf['id'])}\n"
            f"   {len(text)} символов, {meta or ''}\n\n{preview}"
        )

    if parts[0] == "analyze" and len(parts) > 1 and parts[1].isdigit():
        pdfs = list_archived_pdfs()
        idx = int(parts[1])
        if not pdfs or idx < 1 or idx > len(pdfs):
            return "❌ Неверный номер PDF."
        pdf = pdfs[idx - 1]
        text, meta = await extract_pdf_async(pdf["path"])
        return (
            f"📄 {pdf.get('original_name', pdf['id'])}\n"
            f"   Текст извлечён ({len(text)} символов)\n"
            f"   Первые 1000: {text[:1000]}..."
        )

    return None


# ── YouTube ──────────────────────────────────────────────────────────────────
async def cli_yt(url: str, mode: str = "video"):
    if not url or not url.startswith("http"):
        return (
            "❌ Укажите URL:\n"
            "  /yt <youtube_url> [480|720] — скачать видео\n"
            "  /ytaudio <url> — скачать аудио + транскрипция"
        )

    url_parts = url.split()
    clean_url = url_parts[0]
    quality = url_parts[1] if len(url_parts) > 1 and url_parts[1].isdigit() else "720"

    if mode == "audio":
        result = await download_audio(clean_url)
        if not result:
            return "❌ Не удалось скачать аудио."
        audio_path, _ = result if isinstance(result, tuple) else (result, "")
        trans_path = await transcribe_audio(audio_path, os.path.basename(audio_path))
        trans_text = ""
        if trans_path and os.path.exists(trans_path):
            with open(trans_path) as f:
                trans_text = f.read()
        preview = trans_text[:1000] if trans_text else "(транскрипция не удалась)"
        trans_len = len(trans_text or '')
        return f"🎵 Аудио: {audio_path}\n📝 Транскрипция ({trans_len} символов):\n{preview}"
    else:
        path = await download_video(clean_url, quality)
        if not path:
            return "❌ Не удалось скачать видео."
        return f"📹 Видео: {path}"


# ── Tunnels ──────────────────────────────────────────────────────────────────
async def cli_tunnels(subcmd: str = "list"):
    mcp = get_mcp()
    parts = subcmd.split()

    if not parts or parts[0] == "list":
        result = await mcp.call_tool("mempalace_list_tunnels")
        if not result or result == "[]":
            return "🔄 Туннелей пока нет."
        lines = ["🔄 Туннели:"]
        try:
            import json
            data = json.loads(result)
            for i, t in enumerate(data, 1):
                src = t.get("source", f"{t.get('wing_a', '?')}/{t.get('room_a', '?')}")
                dst = t.get("target", f"{t.get('wing_b', '?')}/{t.get('room_b', '?')}")
                label = t.get("label", "")
                lines.append(f"  {i}) {src} ↔ {dst}" + (f" — {label}" if label else ""))
        except Exception:
            lines.append(f"  {result[:500]}")
        return "\n".join(lines)

    if parts[0] == "create" and len(parts) >= 5:
        wing_a, room_a, wing_b, room_b = parts[1:5]
        label = " ".join(parts[5:]) if len(parts) > 5 else ""
        result = await mcp.call_tool("mempalace_create_tunnel", {
            "wing_a": wing_a, "room_a": room_a,
            "wing_b": wing_b, "room_b": room_b,
            "label": label,
        })
        return f"✅ Туннель создан: {wing_a}/{room_a} ↔ {wing_b}/{room_b}" if result else "❌ Ошибка."

    if parts[0] == "delete" and len(parts) >= 2:
        result = await mcp.call_tool("mempalace_delete_tunnel", {"tunnel_id": parts[1]})
        return f"🗑️ Туннель {parts[1]} удалён." if result else "❌ Ошибка."

    if parts[0] == "analyze":
        tunnels = await mcp.call_tool("mempalace_list_tunnels")
        count = len(tunnels) if tunnels else 0
        return f"🔗 Туннелей в базе: {count}\nДля AI-анализа: /tunnels list"

    return (
        "ℹ️ /tunnels list — показать все\n"
        "  /tunnels create wing_a room_a wing_b room_b [label]\n"
        "  /tunnels delete <id>\n"
        "  /tunnels analyze"
    )


# ── KG ───────────────────────────────────────────────────────────────────────
async def cli_kgadd(args: str):
    parts = args.split(maxsplit=2)
    if len(parts) < 3:
        return "❌ /kgadd <субъект> <предикат> <объект>"
    subject, predicate, obj = parts[0], parts[1], parts[2]
    mcp = get_mcp()
    result = await mcp.call_tool("mempalace_add_fact", {
        "subject": subject, "predicate": predicate, "object": obj,
    })
    return f"✅ Факт: {subject} → {predicate} → {obj}" if result else "❌ Ошибка."


# ── Palace status helpers ────────────────────────────────────────────────────
async def cli_palace_cmd(cmd: str):
    if cmd == "status":
        return await palace_status()
    if cmd == "repair":
        return await palace_repair()
    if cmd == "compact":
        return await palace_compact()
    if cmd == "compress":
        return await palace_compress()
    if cmd == "wakeup":
        return await palace_wake_up()
    return None
