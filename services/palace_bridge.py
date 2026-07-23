"""
palace_bridge.py
Мост для MemPalace. Приоритетный поиск личных данных.
✅ Hybrid search включён по умолчанию в MemPalace 3.6+
✅ БЕЗОПАСНОСТЬ: Добавлена валидация query для предотвращения инъекций.
"""
import os
import sys
import json
import asyncio
import logging
import re
import shutil
from datetime import datetime
from config import DATA_DIR, CHATS_DIR, NOTES_DIR

logger = logging.getLogger("PalaceBridge")
PALACE_SYNC_DIR = os.path.join(DATA_DIR, "palace_sync")
os.makedirs(PALACE_SYNC_DIR, exist_ok=True)

def _get_palace_env() -> dict:
    env = os.environ.copy()
    venv_dir = os.path.join(DATA_DIR, "venv")
    env["VIRTUAL_ENV"] = venv_dir
    env["PATH"] = os.path.join(venv_dir, "bin") + os.pathsep + env.get("PATH", "")
    env["PYTHONPATH"] = DATA_DIR + os.pathsep + env.get("PYTHONPATH", "")
    return env

async def search_palace_context(query: str, limit: int = 5, wing: str = "", room: str = "") -> str:
    """Поиск по базе MemPalace. Возвращает блок для контекста ИИ."""
    if not query.strip():
        return ""
    
    safe_query = query.strip().replace('"', "'")[:200]
    if not safe_query:
        return ""

    async def _run(use_wing: str) -> str:
        cmd = [sys.executable, "-m", "mempalace", "search", safe_query, "--results", str(limit)]
        if use_wing:
            cmd.extend(["--wing", use_wing])
        if room:
            cmd.extend(["--room", room])

        logger.info(f"[PALACE_SEARCH] {' '.join(cmd)}")
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=DATA_DIR, env=_get_palace_env()
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            err = stderr.decode().strip()
            logger.warning(f"MemPalace search error: {err}")
            return ""

        result = stdout.decode("utf-8").strip()
        if not result or "No results found" in result or "Ничего не найдено" in result:
            return ""
        return result

    try:
        result = await _run(wing)

        # Fallback: если с крылом пусто — ищем глобально
        if not result and wing:
            logger.info(f"[PALACE_SEARCH] ⚠️ В крыле {wing} ничего нет, повторяю глобальный поиск")
            result = await _run("")

        if not result:
            return ""

        return f"\n--- ЛИЧНЫЕ ЗАПИСИ ИЗ MEMPALACE (Приоритетный источник) ---\n{result}\n--- КОНЕЦ ЛИЧНЫХ ЗАПИСЕЙ ---\n"
    except Exception as e:
        logger.error(f"Error searching MemPalace: {e}", exc_info=True)
        return ""

def export_chat_verbatim(chat_path: str, chat_name: str) -> str | None:
    if not os.path.exists(chat_path): return None
    with open(chat_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    msgs = data.get("messages", [])
    if not msgs: return None
    lines = [f"# Chat: {chat_name}\n# Exported: {datetime.now().isoformat()}\n"]
    for m in msgs:
        role = "USER" if m.get("role") == "user" else "AI"
        content = m.get("content", "").strip()
        if content: lines.append(f"[{role}]\n{content}\n")
    sync_file = os.path.join(PALACE_SYNC_DIR, f"{chat_name.replace('.json', '')}_verbatim.txt")
    with open(sync_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return sync_file

def export_note_verbatim(note_path: str) -> str | None:
    if not os.path.exists(note_path): return None
    dest = os.path.join(PALACE_SYNC_DIR, os.path.basename(note_path))
    shutil.copy2(note_path, dest)
    return dest

async def sync_to_palace(target_path: str = None) -> str:
    mine_target = target_path or PALACE_SYNC_DIR
    if not os.path.exists(mine_target) or (os.path.isdir(mine_target) and not os.listdir(mine_target)):
        return "ℹ️ Нет данных для синхронизации."
    try:
        cmd = [sys.executable, "-m", "mempalace", "mine", mine_target, "--mode", "convos"]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=DATA_DIR, env=_get_palace_env()
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode().strip()
            return f"❌ Ошибка синхронизации: {err}" if err else "❌ Синхронизация завершилась с ошибкой."
        if os.path.isdir(PALACE_SYNC_DIR):
            for f in os.listdir(PALACE_SYNC_DIR):
                fp = os.path.join(PALACE_SYNC_DIR, f)
                if os.path.isfile(fp): os.remove(fp)
        return "✅ Синхронизация с MemPalace завершена. Данные добавлены в базу (verbatim)."
    except Exception as e:
        return f"❌ Ошибка вызова mine: {e}"