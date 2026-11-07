"""palace_bridge.py
Мост для MemPalace. Приоритетный поиск личных данных.
✅ Hybrid search включён по умолчанию в MemPalace 3.6+
✅ БЕЗОПАСНОСТЬ: Добавлена валидация query для предотвращения инъекций.
"""

import asyncio
import json
import logging
import os
import re
import shutil
import sys
from datetime import datetime
from typing import Literal, overload

from config import DATA_DIR
from services.circuit_breaker import (
    CircuitBreakerOpenError,
    get_mcp_circuit_breaker,
    get_palace_circuit_breaker,
)

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


def _format_sources_block(sources: list[dict]) -> str:
    """Форматирует сноски с источниками; пустой список — пустая строка."""
    if not sources:
        return ""

    lines = ["--- ИСТОЧНИКИ ---"]
    for s in sources:
        loc = f"{s['wing']}/{s['room']}" if s["wing"] or s["room"] else s["file"]
        lines.append(f"[{s['id']}] {loc} (score: {s['score']:.3f})")
    lines.append("--- КОНЕЦ ИСТОЧНИКОВ ---")
    return "\n".join(lines) + "\n"


def _format_context(text: str, sources: list[dict]) -> str:
    """Оборачивает текст поиска в блок личных записей со сносками."""
    sources_block = _format_sources_block(sources)
    if sources_block:
        text = f"{text}\n\n{sources_block}"
    return (
        "\n--- ЛИЧНЫЕ ЗАПИСИ ИЗ MEMPALACE (Приоритетный источник) ---\n"
        f"{text}\n--- КОНЕЦ ЛИЧНЫХ ЗАПИСЕЙ ---\n"
    )


@overload
async def _search_palace(
    query: str, limit: int = 5, wing: str = "", room: str = "",
    *, with_sources: Literal[False] = False,
) -> str: ...


@overload
async def _search_palace(
    query: str, limit: int = 5, wing: str = "", room: str = "",
    *, with_sources: Literal[True],
) -> tuple[str, list]: ...


async def _search_palace(
    query: str, limit: int = 5, wing: str = "", room: str = "",
    *, with_sources: bool = False,
) -> str | tuple[str, list]:
    """Единая реализация поиска по MemPalace с circuit breaker.

    ``with_sources=False`` возвращает готовый контекст для ИИ со сносками,
    ``True`` — сырой текст и список источников для UI.
    """
    cb = get_palace_circuit_breaker()
    try:
        result = await cb.call(_search_palace_context_impl, query, limit, wing, room)
    except CircuitBreakerOpenError as e:
        logger.warning(f"[PALACE] Circuit breaker OPEN: {e}")
        return ("", []) if with_sources else ""
    except Exception as e:
        logger.error(f"Error searching MemPalace: {e}", exc_info=True)
        return ("", []) if with_sources else ""

    text = result.get("text", "")
    sources = result.get("sources", [])

    if not text:
        return ("", []) if with_sources else ""

    if with_sources:
        return text, sources
    return _format_context(text, sources)


async def search_palace_context(
    query: str, limit: int = 5, wing: str = "", room: str = "",
) -> str:
    """Поиск по базе MemPalace. Возвращает блок для контекста ИИ."""
    return await _search_palace(query, limit, wing, room)


async def search_palace_with_sources(
    query: str, limit: int = 5, wing: str = "", room: str = "",
) -> tuple[str, list]:
    """Поиск по базе MemPalace. Возвращает (text, sources) для пользовательского показа."""
    return await _search_palace(query, limit, wing, room, with_sources=True)


async def _search_palace_context_impl(
    query: str, limit: int = 5, wing: str = "", room: str = "",
) -> dict:
    """Внутренняя реализация поиска по базе MemPalace. Возвращает dict с text и sources."""
    if not query.strip():
        return {"text": "", "sources": []}

    safe_query = query.strip().replace('"', "'")[:200]

    # Try direct API first (structured results with scores)
    result = await _search_via_api(safe_query, limit, wing, room)
    if result["text"]:
        return result

    # Fallback: if wing-specific returned nothing, try global
    if wing and not result["text"]:
        logger.info(
            f"[PALACE_SEARCH] ⚠️ В крыле {wing} ничего нет, повторяю глобальный поиск",
        )
        result = await _search_via_api(safe_query, limit, "", "")
        if result["text"]:
            return result

    # Final fallback: CLI (legacy text output)
    logger.info("[PALACE_SEARCH] Прямой API недоступен, пробую CLI...")
    return await _search_via_cli(safe_query, limit, wing, room)


def _rank_hits(hits: list[dict]) -> list[dict]:
    """Rank hits by relevance.

    Combines lexical (BM25) and semantic (vector distance) signals.
    distance: lower is better (cosine distance in [0, 1]).
    bm25_score: higher is better (log-scaled count, unbounded).

    Ranking: score = 0.5 * (1 - distance) + 0.5 * bm25_norm, where bm25_norm
    is BM25 normalised against the max value within this result set. Both
    signals weigh equally, so an exact lexical hit beats a merely close
    vector neighbour and vice versa.
    """
    if not hits:
        return []

    bm25_vals: list[float] = []
    for h in hits:
        v = h.get("bm25_score")
        if v is not None:
            bm25_vals.append(float(v))
    bm25_max_f = max(bm25_vals) if bm25_vals else 0.0

    def _score(h: dict) -> float:
        dist = h.get("distance")
        bm25 = h.get("bm25_score")
        bm25_norm = 0.0
        if bm25 is not None and bm25_max_f:
            bm25_norm = bm25 / bm25_max_f
        elif bm25 is not None:
            bm25_norm = 1.0
        return (
            (0.5 * (1.0 - dist) if dist is not None else 0.0)
            + 0.5 * bm25_norm
        )

    return sorted(hits, key=_score, reverse=True)


async def _search_via_api(
    query: str, limit: int = 5, wing: str = "", room: str = "",
) -> dict:
    """Search via mempalace.searcher (structured results with scores)."""
    try:
        from mempalace.config import MempalaceConfig
        from mempalace.searcher import search_memories
    except ImportError:
        return {"text": "", "sources": []}

    try:
        config = MempalaceConfig()
        palace_path = str(config.palace_path)
        collection = config.collection_name

        result = await asyncio.get_event_loop().run_in_executor(
            None,
            search_memories,
            query,
            palace_path,
            wing or None,
            room or None,
            None,
            limit * 3,
            0.6,
            False,
            "union",
            collection,
        )

        hits = result.get("results", [])
        if not hits:
            return {"text": "", "sources": []}

        # Filter irrelevant results (BM25 score = 0.0 or distance too high)
        filtered = []
        for h in hits:
            bm25 = h.get("bm25_score")
            distance = h.get("distance")
            if bm25 is not None and bm25 == 0.0:
                continue
            if distance is not None and distance > 0.7:
                continue
            filtered.append(h)

        if not filtered:
            return {"text": "", "sources": []}

        filtered = _rank_hits(filtered)[:limit]

        lines = []
        sources = []
        for i, h in enumerate(filtered, 1):
            text = h.get("text", "")
            wing_name = h.get("wing", "")
            room_name = h.get("room", "")
            score = h.get("distance") or h.get("bm25_score") or 0
            lines.append(f"[{i}] {text[:500]}")
            sources.append({
                "id": i,
                "wing": wing_name,
                "room": room_name,
                "file": h.get("source_file", ""),
                "score": score,
            })

        return {"text": "\n\n".join(lines), "sources": sources}

    except Exception as e:
        logger.warning(f"[PALACE_SEARCH] API error: {e}", exc_info=True)
        return {"text": "", "sources": [], "error": True}


async def _search_via_cli(
    query: str, limit: int = 5, wing: str = "", room: str = "",
) -> dict:
    """Legacy fallback: search via CLI subprocess."""
    async def _run(use_wing: str) -> dict:
        cmd = [
            sys.executable,
            "-m",
            "mempalace",
            "search",
            query,
            "--results",
            str(limit),
        ]
        if use_wing:
            cmd.extend(["--wing", use_wing])
        if room:
            cmd.extend(["--room", room])

        logger.info(f"[PALACE_SEARCH] {' '.join(cmd)}")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=DATA_DIR,
            env=_get_palace_env(),
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            err = stderr.decode().strip()
            logger.warning(f"MemPalace search error: {err}")
            return {"text": "", "sources": [], "error": True}

        result = stdout.decode("utf-8").strip()
        if not result or "No results found" in result or "Ничего не найдено" in result:
            return {"text": "", "sources": []}

        return {"text": result, "sources": []}

    try:
        result = await _run(wing)

        if not result["text"] and wing:
            logger.info(
                f"[PALACE_SEARCH] ⚠️ В крыле {wing} ничего нет, повторяю глобальный поиск",
            )
            result = await _run("")

        return result
    except Exception as e:
        logger.error(f"Error searching MemPalace via CLI: {e}", exc_info=True)
        return {"text": "", "sources": [], "error": True}


async def _search_connected_rooms(
    query: str, sources: list[dict], limit: int = 2,
) -> str:
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
                raw = await mcp.call_tool(
                    "mempalace_follow_tunnels", {"wing": sw, "room": sr},
                )
                tunnels = json.loads(raw) if raw else []
                for t in tunnels:
                    cw = t.get("connected_wing", "")
                    cr = t.get("connected_room", "")
                    label = t.get("label", "")
                    ckey = f"{cw}/{cr}"
                    if cw and cr and ckey not in seen:
                        seen.add(ckey)
                        conn = await _search_palace_context_impl(
                            query, limit=limit, wing=cw, room=cr,
                        )
                        if conn.get("text"):
                            tag = f"  [связь: {sw}/{sr} → {cw}/{cr}]"
                            if label:
                                tag += f" ({label})"
                            blocks.append(f"{tag}\n{conn['text']}")
            except Exception as e:
                logger.warning(
                    "[PALACE_TUNNELS] Ошибка поиска связи %s/%s: %s", cw, cr, e,
                )
                continue
    except Exception as e:
        logger.warning("[PALACE_TUNNELS] Ошибка поиска туннелей: %s", e, exc_info=True)
    if blocks:
        return (
            "\n\n--- СВЯЗИ ПО ТУННЕЛЯМ ---\n"
            + "\n\n".join(blocks)
            + "\n--- КОНЕЦ СВЯЗЕЙ ---\n"
        )
    return ""


async def search_with_kg_status(
    query: str, limit: int = 5, wing: str = "",
) -> tuple[str, bool]:
    """Комбинированный поиск: текст + Knowledge Graph + туннели.

    Возвращает ``(text, available)``. ``available=False`` означает отказ
    backend'а (API/CLI), а пустой ``text`` при ``available=True`` — штатное
    «ничего не найдено».
    """
    try:
        result = await _search_palace_context_impl(query, limit, wing)
    except Exception as e:
        logger.error(f"[PALACE_SEARCH] Unexpected search error: {e}", exc_info=True)
        return "", False

    text = result.get("text", "")
    sources = result.get("sources", [])
    available = not result.get("error", False)

    if not text:
        return "", available

    text_block = (
        "\n--- ЛИЧНЫЕ ЗАПИСИ ИЗ MEMPALACE (Приоритетный источник) ---\n"
        f"{text}"
    )
    sources_block = _format_sources_block(sources)
    if sources_block:
        text_block += f"\n\n{sources_block}"

    kg_block = ""
    try:
        from services.palace_mcp import get_mcp

        mcp_cb = get_mcp_circuit_breaker()
        mcp = get_mcp()
        await mcp.start()

        async def _kg_query():
            return await mcp.call_tool(
                "mempalace_kg_query", {"entity": query.strip(), "direction": "both"},
            )

        kg_raw = await mcp_cb.call(_kg_query)
        kg_data = json.loads(kg_raw)
        kg_facts = kg_data.get("facts", [])
        if kg_facts:
            lines = ["\n--- СВЯЗИ ИЗ ГРАФА ЗНАНИЙ (KG) ---"]
            for f in kg_facts[:10]:
                s = f.get("subject", "?")
                p = f.get("predicate", "?")
                o = f.get("object", "?")
                label = {
                    "wrote": "написал",
                    "contains_idea": "→ идея",
                    "contains_quote": "→ цитата",
                    "topic": "тема",
                }.get(p, p)
                lines.append(f"  • {s} {label}: {o}")
            kg_block = "\n".join(lines) + "\n--- КОНЕЦ KG ---\n"
    except CircuitBreakerOpenError:
        logger.warning("[PALACE_KG] Circuit breaker OPEN, skipping KG search")
    except Exception as e:
        logger.warning("[PALACE_KG] Ошибка поиска KG: %s", e, exc_info=True)

    tunnel_block = await _search_connected_rooms(query, sources)

    combined = text_block
    if kg_block:
        combined += "\n" + kg_block
    if tunnel_block:
        combined += "\n" + tunnel_block

    return combined, True


async def search_with_kg(query: str, limit: int = 5, wing: str = "") -> str:
    """Совместимая обёртка: возвращает только текст результата."""
    text, _available = await search_with_kg_status(query, limit, wing)
    return text


def export_chat_verbatim(chat_path: str, chat_name: str) -> str | None:
    if not os.path.exists(chat_path):
        return None
    with open(chat_path, encoding="utf-8") as f:
        data = json.load(f)
    msgs = data.get("messages", [])
    if not msgs:
        return None
    lines = [f"# Chat: {chat_name}\n# Exported: {datetime.now().isoformat()}\n"]
    for m in msgs:
        role = "USER" if m.get("role") == "user" else "AI"
        content = m.get("content", "").strip()
        if content:
            lines.append(f"[{role}]\n{content}\n")
    sync_file = os.path.join(
        PALACE_SYNC_DIR, f"{chat_name.replace('.json', '')}_verbatim.txt",
    )
    with open(sync_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return sync_file


def export_note_verbatim(note_path: str) -> str | None:
    if not os.path.exists(note_path):
        return None
    dest = os.path.join(PALACE_SYNC_DIR, os.path.basename(note_path))
    shutil.copy2(note_path, dest)
    return dest


async def _run_mempalace(args: list[str]) -> str:
    cb = get_palace_circuit_breaker()
    try:
        return await cb.call(_run_mempalace_impl, args)
    except CircuitBreakerOpenError as e:
        logger.warning(f"[PALACE] Circuit breaker OPEN: {e}")
        return "❌ Сервис дворца временно недоступен. Попробуйте позже."
    except Exception as e:
        logger.error("[PALACE] Ошибка run_mempalace: %s", e, exc_info=True)
        return f"❌ Ошибка: {e}"


async def _run_mempalace_impl(args: list[str]) -> str:
    cmd = [sys.executable, "-m", "mempalace"] + args
    logger.info(f"[MEMPalace] {' '.join(cmd)}")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=DATA_DIR,
        env=_get_palace_env(),
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = stderr.decode().strip()
        return f"❌ {err}" if err else "❌ Ошибка выполнения команды."
    return stdout.decode("utf-8").strip()


def _wing_emoji(name: str) -> str:
    """Подбирает подходящий эмодзи для крыла."""
    low = name.lower()
    if "phil" in low or "филос" in low:
        return "🧠"
    if "gen" in low or "общ" in low:
        return "🌐"
    if "proj" in low or "проект" in low:
        return "🚀"
    if "творч" in low or "арт" in low:
        return "🎨"
    if "лит" in low or "книг" in low:
        return "📚"
    if "псих" in low or "psych" in low:
        return "🧩"
    if "фот" in low or "photo" in low:
        return "📷"
    if "инсайт" in low or "insight" in low:
        return "💡"
    if "сон" in low or "сны" in low:
        return "🌙"
    if "раб" in low or "work" in low:
        return "💼"
    if "личн" in low:
        return "💭"
    if "deutsch" in low or "нем" in low:
        return "🇩🇪"
    return "🏛️"


def format_palace_status_dashboard(raw: str) -> str:
    """Преобразует CLI-вывод 'mempalace status' в структурированный HTML-дашборд."""
    if not raw or "WING:" not in raw:
        return raw

    match = re.search(r"MemPalace Status — (\d+) drawers", raw, re.IGNORECASE)
    total_drawers = int(match.group(1)) if match else 0

    wings: dict[str, int] = {}
    current_wing: str | None = None
    total_rooms = 0

    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("WING:"):
            current_wing = line[5:].strip()
            if current_wing not in wings:
                wings[current_wing] = 0
        elif line.startswith("ROOM:") and current_wing:
            rm = re.match(r"ROOM:\s+(.*?)\s+(\d+)\s+drawers?", line, re.IGNORECASE)
            if rm:
                count = int(rm.group(2))
                wings[current_wing] += count
                total_rooms += 1

    if not wings:
        return raw

    if total_drawers == 0:
        total_drawers = sum(wings.values())

    sorted_wings = sorted(wings.items(), key=lambda x: x[1], reverse=True)
    total_wings = len(sorted_wings)

    lines = [
        "🏰 <b>Чертоги Разума — Сводка</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"📦 <b>Всего записей:</b> <code>{total_drawers:,}</code>",
        f"🏛️ <b>Крыльев:</b> <code>{total_wings}</code> | "
        f"🚪 <b>Комнат:</b> <code>{total_rooms}</code>",
        "━━━━━━━━━━━━━━━━━━━━",
        "📊 <b>Распределение по разделам:</b>",
    ]

    limit = 8
    displayed = sorted_wings[:limit]
    remaining = sorted_wings[limit:]

    for wing, count in displayed:
        pct = (count / total_drawers * 100) if total_drawers else 0
        emoji = _wing_emoji(wing)
        lines.append(f"{emoji} <b>{wing}:</b> {count:,} <i>({pct:.1f}%)</i>")

    if remaining:
        rem_count = sum(c for _, c in remaining)
        lines.append(
            f"<i>… и ещё {len(remaining)} разделов ({rem_count:,} записей)</i>"
        )

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Выберите действие ниже для перехода или экспорта:</i>")
    return "\n".join(lines)


async def palace_status() -> str:
    raw = await _run_mempalace(["status"])
    return format_palace_status_dashboard(raw)


async def palace_mcp() -> str:
    """Показать команду настройки MCP."""
    return await _run_mempalace(["mcp"])


async def palace_wake_up() -> str:
    return await _run_mempalace(["wake-up"])


async def palace_split(path: str = "") -> str:
    cmd = ["split"]
    if path:
        cmd.append(path)
    return await _run_mempalace(cmd)


async def palace_compress() -> str:
    return await _run_mempalace(["compress"])


async def palace_compact() -> str:
    return await _run_mempalace(["compact"])


async def palace_repair() -> str:
    return await _run_mempalace(["repair", "--yes"])


async def palace_instructions() -> str:
    return (
        "<b>📖 Как работать с Дворцом MemPalace</b>\n\n"
        "<b>🏰 Что такое Дворец?</b>\n"
        "Это ваша база знаний и «второй мозг». Все заметки, файлы и диалоги "
        "раскладываются по <b>крыльям</b> и <b>комнатам</b>.\n\n"
        "<b>⚡ Интерактивные команды:</b>\n"
        "• /palace — главное меню Чертогов Разума\n"
        "• /search — сквозной поиск OmniSearch\n"
        "• /notes — управление и синхронизация Apple Notes\n"
        "• /settings — смена AI-модели (Ollama, Gemini, OpenAI)\n\n"
        "<b>🏛️ Структура Дворца:</b>\n"
        "• <b>Крылья</b> — макро-разделы (философия, проекты, творчество, психология)\n"
        "• <b>Комнаты</b> — тематические разделы внутри каждого крыла\n"
        "• <b>Записи (drawers)</b> — атомарные карточки знаний и цитат\n\n"
        "<b>🔍 OmniSearch (сквозной поиск):</b>\n"
        "Объединённый поиск по трём слоям: ChromaDB, Графу знаний (KG) "
        "и Apple Notes в едином окне. Доступен по /search.\n\n"
        "<b>🗺️ 3D/2D Карта Дворца (.html):</b>\n"
        "Экспорт интерактивной карты в формате .html. Откройте в любом браузере: "
        "доступен 3D-граф, 2D-схема и фильтрация связей.\n\n"
        "<b>📝 Apple Notes & Бэклинки:</b>\n"
        "Двусторонняя синхронизация: заметки отправляются во Дворец, а в Apple Notes "
        "проставляются кликабельные бэклинки вида <code>mempalace://</code>.\n\n"
        "<b>🔄 Туннели между крыльями:</b>\n"
        "Связывают пересекающиеся темы из разных крыльев. ИИ анализирует туннели "
        "и помогает генерировать синтетические обзоры.\n\n"
        "<b>🧠 Граф знаний (KG):</b>\n"
        "Сеть структурированных фактов: «Сущность → Отношение → Значение». "
        "Позволяет находить скрытые взаимосвязи между авторами и идеями.\n\n"
        "<b>🤖 Автономный агент Дворца:</b>\n"
        "Интеллектуальный помощник: выявляет дубли, предлагает слияние или разделение "
        "комнат и оптимизирует структуру Чертогов.\n\n"
        "<b>🔧 Обслуживание:</b>\n"
        "• Статус — актуальная сводка записей и визуальное распределение\n"
        "• Сжать БД (compact) — очистка неиспользуемых сегментов ChromaDB\n"
        "• Сжать текст — дедупликация и объединение родственных заметок\n"
        "• Перестроить индекс — обновление поискового индекса после синхронизации\n\n"
        "<b>💡 Советы:</b>\n"
        "• Скачивайте карту (.html) для наглядного обзора всего Дворца\n"
        "• Используйте OmniSearch для комплексных запросов по всем базам\n"
        "• Запускайте Сжать БД раз в месяц для оптимальной скорости\n"
    )


async def sync_to_palace(target_path: str | None = None) -> str:
    cb = get_palace_circuit_breaker()
    try:
        return await cb.call(_sync_to_palace_impl, target_path)
    except CircuitBreakerOpenError as e:
        logger.warning(f"[PALACE] Circuit breaker OPEN during sync: {e}")
        return "❌ Синхронизация временно недоступна."
    except Exception as e:
        logger.error("[PALACE] Ошибка синхронизации: %s", e, exc_info=True)
        return f"❌ Ошибка синхронизации: {e}"


async def _sync_to_palace_impl(target_path: str | None = None) -> str:
    mine_target = target_path or PALACE_SYNC_DIR
    if not os.path.exists(mine_target) or (
        os.path.isdir(mine_target) and not os.listdir(mine_target)
    ):
        return "ℹ️ Нет данных для синхронизации."
    try:
        cmd = [
            sys.executable,
            "-m",
            "mempalace",
            "mine",
            mine_target,
            "--mode",
            "convos",
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=DATA_DIR,
            env=_get_palace_env(),
        )
        _stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode().strip()
            return (
                f"❌ Ошибка синхронизации: {err}"
                if err
                else "❌ Синхронизация завершилась с ошибкой."
            )
        if os.path.isdir(PALACE_SYNC_DIR):
            for f in os.listdir(PALACE_SYNC_DIR):
                fp = os.path.join(PALACE_SYNC_DIR, f)
                if os.path.isfile(fp):
                    os.remove(fp)
        return "✅ Синхронизация с MemPalace завершена. Данные добавлены в базу (verbatim)."
    except Exception as e:
        logger.error("[PALACE] Ошибка вызова mine: %s", e, exc_info=True)
        return f"❌ Ошибка вызова mine: {e}"
