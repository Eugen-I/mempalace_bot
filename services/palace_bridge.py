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
from services.circuit_breaker import get_palace_circuit_breaker, get_mcp_circuit_breaker, CircuitBreakerOpenError

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
    cb = get_palace_circuit_breaker()
    try:
        result = await cb.call(_search_palace_context_impl, query, limit, wing, room)
    except CircuitBreakerOpenError as e:
        logger.warning(f"[PALACE] Circuit breaker OPEN: {e}")
        return ""
    except Exception as e:
        logger.error(f"Error searching MemPalace: {e}", exc_info=True)
        return ""

    text = result.get("text", "")
    sources = result.get("sources", [])
    
    if not text:
        return ""
    
    # Добавляем сноски с источниками
    if sources:
        source_lines = ["\n--- ИСТОЧНИКИ ---"]
        for s in sources:
            loc = f"{s['wing']}/{s['room']}" if s['wing'] or s['room'] else s['file']
            source_lines.append(f"[{s['id']}] {loc} (score: {s['score']:.3f})")
        source_lines.append("--- КОНЕЦ ИСТОЧНИКОВ ---\n")
        text += "\n" + "\n".join(source_lines)
    
    return f"\n--- ЛИЧНЫЕ ЗАПИСИ ИЗ MEMPALACE (Приоритетный источник) ---\n{text}\n--- КОНЕЦ ЛИЧНЫХ ЗАПИСЕЙ ---\n"

async def _search_palace_context_impl(query: str, limit: int = 5, wing: str = "", room: str = "") -> dict:
    """Внутренняя реализация поиска по базе MemPalace. Возвращает dict с text и sources."""
    if not query.strip():
        return {"text": "", "sources": []}
    
    safe_query = query.strip().replace('"', "'")[:200]
    if not safe_query:
        return {"text": "", "sources": []}

    async def _run(use_wing: str) -> dict:
        cmd = [sys.executable, "-m", "mempalace", "search", safe_query, "--results", str(limit), "--format", "json"]
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
            return {"text": "", "sources": []}

        result = stdout.decode("utf-8").strip()
        if not result or "No results found" in result or "Ничего не найдено" in result:
            return {"text": "", "sources": []}
        
        # Parse JSON output from mempalace
        import json
        try:
            data = json.loads(result)
            entries = data.get("entries", [])
            sources = []
            text_parts = []
            for i, e in enumerate(entries, 1):
                text_parts.append(f"[{i}] {e.get('content', '')}")
                sources.append({
                    "id": i,
                    "file": e.get("file", ""),
                    "wing": e.get("wing", ""),
                    "room": e.get("room", ""),
                    "score": e.get("score", 0)
                })
            return {"text": "\n\n".join(text_parts), "sources": sources}
        except json.JSONDecodeError:
            # Fallback for old format
            return {"text": result, "sources": []}

    try:
        result = await _run(wing)

        # Fallback: если с крылом пусто — ищем глобально
        if not result["text"] and wing:
            logger.info(f"[PALACE_SEARCH] ⚠️ В крыле {wing} ничего нет, повторяю глобальный поиск")
            result = await _run("")

        if not result["text"]:
            return {"text": "", "sources": []}

        return result
    except Exception as e:
        logger.error(f"Error searching MemPalace: {e}", exc_info=True)
        return {"text": "", "sources": []}

async def _search_connected_rooms(query: str, sources: list[dict], limit: int = 2) -> str:
    """Follow tunnels from result sources and search in connected rooms."""
    blocks = []
    seen = set()
    try:
        from services.palace_mcp import get_mcp
        mcp = get_mcp()
        await mcp.start()

        for s in sources[:3]:
            sw = s.get("wing", "")
            sr = s.get("room", "")
            key = f"{sw}/{sr}"
            if not sw or not sr or key in seen:
                continue
            seen.add(key)
            try:
                raw = await mcp.call_tool("mempalace_follow_tunnels", {"wing": sw, "room": sr})
                tunnels = json.loads(raw) if raw else []
                for t in tunnels:
                    cw = t.get("connected_wing", "")
                    cr = t.get("connected_room", "")
                    label = t.get("label", "")
                    ckey = f"{cw}/{cr}"
                    if cw and cr and ckey not in seen:
                        seen.add(ckey)
                        conn = await _search_palace_context_impl(query, limit=limit, wing=cw, room=cr)
                        if conn.get("text"):
                            tag = f"  [связь: {sw}/{sr} → {cw}/{cr}]"
                            if label:
                                tag += f" ({label})"
                            blocks.append(f"{tag}\n{conn['text']}")
            except Exception:
                continue
    except Exception:
        pass
    if blocks:
        return "\n\n--- СВЯЗИ ПО ТУННЕЛЯМ ---\n" + "\n\n".join(blocks) + "\n--- КОНЕЦ СВЯЗЕЙ ---\n"
    return ""


async def search_with_kg(query: str, limit: int = 5, wing: str = "") -> str:
    """Комбинированный поиск: текст + Knowledge Graph + туннели."""
    result = await _search_palace_context_impl(query, limit, wing)
    text = result.get("text", "")
    sources = result.get("sources", [])

    if not text:
        return ""

    source_lines = ["\n--- ИСТОЧНИКИ ---"]
    for s in sources:
        loc = f"{s['wing']}/{s['room']}" if s['wing'] or s['room'] else s['file']
        source_lines.append(f"[{s['id']}] {loc} (score: {s['score']:.3f})")
    source_lines.append("--- КОНЕЦ ИСТОЧНИКОВ ---\n")
    text_block = f"\n--- ЛИЧНЫЕ ЗАПИСИ ИЗ MEMPALACE (Приоритетный источник) ---\n{text}\n" + "\n".join(source_lines)

    kg_block = ""
    try:
        from services.palace_mcp import get_mcp
        mcp_cb = get_mcp_circuit_breaker()
        mcp = get_mcp()
        await mcp.start()

        async def _kg_query():
            return await mcp.call_tool("mempalace_kg_query", {"entity": query.strip(), "direction": "both"})

        kg_raw = await mcp_cb.call(_kg_query)
        kg_data = json.loads(kg_raw)
        kg_facts = kg_data.get("facts", [])
        if kg_facts:
            lines = ["\n--- СВЯЗИ ИЗ ГРАФА ЗНАНИЙ (KG) ---"]
            for f in kg_facts[:10]:
                s = f.get("subject", "?")
                p = f.get("predicate", "?")
                o = f.get("object", "?")
                label = {"wrote": "написал", "contains_idea": "→ идея", "contains_quote": "→ цитата", "topic": "тема"}.get(p, p)
                lines.append(f"  • {s} {label}: {o}")
            kg_block = "\n".join(lines) + "\n--- КОНЕЦ KG ---\n"
    except CircuitBreakerOpenError:
        logger.warning("[PALACE_KG] Circuit breaker OPEN, skipping KG search")
    except Exception:
        pass

    tunnel_block = await _search_connected_rooms(query, sources)

    combined = text_block
    if kg_block:
        combined += "\n" + kg_block
    if tunnel_block:
        combined += "\n" + tunnel_block

    return combined

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

async def _run_mempalace(args: list[str]) -> str:
    cb = get_palace_circuit_breaker()
    try:
        return await cb.call(_run_mempalace_impl, args)
    except CircuitBreakerOpenError as e:
        logger.warning(f"[PALACE] Circuit breaker OPEN: {e}")
        return f"❌ Сервис дворца временно недоступен. Попробуйте позже."
    except Exception as e:
        return f"❌ Ошибка: {e}"

async def _run_mempalace_impl(args: list[str]) -> str:
    cmd = [sys.executable, "-m", "mempalace"] + args
    logger.info(f"[MEMPalace] {' '.join(cmd)}")
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        cwd=DATA_DIR, env=_get_palace_env()
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = stderr.decode().strip()
        return f"❌ {err}" if err else "❌ Ошибка выполнения команды."
    return stdout.decode("utf-8").strip()

async def palace_status() -> str:
    return await _run_mempalace(["status"])

async def palace_mcp() -> str:
    """Показать команду настройки MCP."""
    return await _run_mempalace(["mcp"])

async def palace_wake_up() -> str:
    return await _run_mempalace(["wake-up"])

async def palace_split(path: str = "") -> str:
    cmd = ["split"]
    if path: cmd.append(path)
    return await _run_mempalace(cmd)

async def palace_compress() -> str:
    return await _run_mempalace(["compress"])

async def palace_compact() -> str:
    return await _run_mempalace(["compact"])

async def palace_repair() -> str:
    return await _run_mempalace(["repair"])

async def palace_instructions() -> str:
    return (
        "<b>📖 Как работать с Дворцом MemPalace</b>\n\n"
        "<b>🏰 Что такое Дворец?</b>\n"
        "Это твоя база знаний. Все заметки, файлы и диалоги "
        "раскладываются по <b>крыльям</b> и <b>комнатам</b>.\n\n"
        "<b>🕸️ Крылья</b> — большие разделы (проекты, люди, темы).\n"
        "  Пример: «my_notes», «projects», «chats».\n\n"
        "<b>🪪 Комнаты</b> — подтемы внутри крыла.\n"
        "  Пример: в крыле «my_notes»: «философия», «архетипы», «daily».\n\n"
        "<b>🏛️ Структура:</b>\n"
        "  Крыло → Комната → Записи (каждая запись — фрагмент текста)\n\n"
        "<b>Навигация по комнатам:</b>\n"
        "  Дворец → Все комнаты → выбери крыло → кликни на комнату →\n"
        "  увидишь список записей. У каждой записи кнопка «Получить запись».\n"
        "  Длинные записи (>3500 символов) разбиты на части.\n\n"
        "<b>🔗 Связанные записи:</b>\n"
        "  Когда читаешь запись — нажми «🔗 Связано».\n"
        "  Бот покажет комнаты, связанные через туннели с этой записью.\n\n"
        "<b>📡 Чтение с туннелями:</b>\n"
        "  В списке записей комнаты — кнопка «📡 Читать с туннелями».\n"
        "  Собирает записи из текущей и всех связанных комнат в один поток.\n"
        "  Внизу — кнопка «🤖 Статья»: ИИ составит связный текст.\n\n"
        "<b>🔄 Туннели</b> — связи между комнатами РАЗНЫХ крыльев.\n"
        "  Если тема «интегралы» есть и в «math», и в «physics» — "
        "возникает туннель.\n"
        "  В меню туннелей:\n"
        "  • «📋 Список» — все туннели, кликабельные для детального просмотра\n"
        "  • «🤖 Анализ туннелей» — ИИ находит пересекающиеся темы\n"
        "  • «🔍 Между крыльями» — общие темы двух крыльев\n"
        "  • «➡️ Пройти» — обход от комнаты\n"
        "  • «➕ Создать» — 4-шаговый мастер\n"
        "  В детальном просмотре туннеля можно читать записи из обеих комнат.\n\n"
        "<b>🧠 Граф знаний (KG)</b> — база фактов.\n"
        "  Связи: «Сущность → отношение → значение».\n"
        "  Пример: «Max → работает_над → MemPalace».\n"
        "  Поиск по сущности покажет все связанные факты.\n\n"
        "<b>⏰ Напоминания</b>\n"
        "  Напиши «напомни завтра в 15:00 позвонить маме» —\n"
        "  бот разберёт время и текст через ИИ, покажет подтверждение\n"
        "  и отправит напоминание в заданное время.\n"
        "  Если данных не хватает — бот сам спросит.\n\n"
        "<b>🔧 Обслуживание:</b>\n"
        "  • Перестроить индекс — после ручного добавления файлов\n"
        "  • Сжать БД — очистить старые сегменты ChromaDB (compact)\n"
        "  • Сжать текст — удалить дубликаты и объединить похожее\n"
        "  • Загрузить в контекст — подгрузить крыло в память\n\n"
        "<b>💡 Советы:</b>\n"
        "  • После майнинга проверь Статус — увидишь новые крылья\n"
        "  • Найди пересечения через Туннели → Между крыльями\n"
        "  • Ищи факты в KG — там выводы ИИ\n"
        "  • Если база тормозит — запусти Сжать БД (compact)\n"
    )

async def sync_to_palace(target_path: str = None) -> str:
    cb = get_palace_circuit_breaker()
    try:
        return await cb.call(_sync_to_palace_impl, target_path)
    except CircuitBreakerOpenError as e:
        logger.warning(f"[PALACE] Circuit breaker OPEN during sync: {e}")
        return f"❌ Синхронизация временно недоступна."
    except Exception as e:
        return f"❌ Ошибка синхронизации: {e}"

async def _sync_to_palace_impl(target_path: str = None) -> str:
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