import os, sys, json, asyncio, logging, re
from datetime import datetime

logger = logging.getLogger("KGEnricher")

EXTRACT_PROMPT_TPL = """Analyze the filename, folder, and content of this note.
Extract structured information as JSON.

Respond ONLY with valid JSON (no extra text):
{
  "author": "author name or null",
  "book": "book title or null",
  "ideas": ["key idea 1", "key idea 2"],
  "quotes": ["quote 1"],
  "topics": ["topic 1"],
  "type": "book_note|personal_thought|poem|dream|other"
}

Rules:
- author: extract from filename, folder or text. E.g. 'Фауст Гёте' -> author='Гёте', 'Высказывания Лены' -> author='Лена'
- book: book title from filename or text
- ideas: key ideas (max 3). If text empty, infer from title
- quotes: direct quotes in quotation marks
- topics: 2-3 general topics (e.g. psychology, photography, jungian, dream, poetry)
- type: book_note if about a book, dream if a dream, poem if poetry, personal_thought if own thoughts

File: %(fname)s
Folder: %(folder)s
Content:
%(content)s"""

def _build_prompt(fname: str, folder: str, content: str) -> str:
    return EXTRACT_PROMPT_TPL % {"fname": fname, "folder": folder, "content": content or "[пусто]"}

def _extract_from_filename(fname: str, folder: str) -> dict:
    result = {"author": None, "book": None, "ideas": [], "quotes": [], "topics": [], "type": "personal_thought"}

    author_patterns = [
        (r'[—–-]\s*([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+)$', 1),
        (r'\b([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+)$', 0),
    ]

    topic_map = {
        "сон": "dream", "сны": "dream", "sns": "dream",
        "книг": "book_note", "цитат": "book_note", "book": "book_note",
        "стих": "poem", "поэз": "poem", "poem": "poem",
        "философ": "philosophy", "психо": "psychology", "юнг": "jungian",
        "фото": "photography", "art": "art", "искусств": "art",
    }

    fname_lower = fname.lower()

    # Detect note type from filename
    for keyword, ntype in topic_map.items():
        if keyword in fname_lower:
            if ntype in ("dream", "book_note", "poem", "philosophy", "psychology", "jungian",
                         "photography", "art"):
                result["type"] = ntype if ntype in ("dream", "book_note", "poem") else "personal_thought"
            if ntype == "dream":
                result["type"] = "dream"
                result["topics"].append("сон")
            elif ntype in ("book_note",):
                result["type"] = "book_note"
            elif ntype == "poem":
                result["type"] = "poem"
                result["topics"].append("поэзия")

    # Try to extract author
    for pattern, group in author_patterns:
        m = re.search(pattern, fname)
        if m:
            candidate = m.group(group).strip()
            if len(candidate) > 3 and any(c.isalpha() for c in candidate):
                result["author"] = candidate
                break

    # If filename contains "Книга" or "Book", try to extract title
    if "книг" in fname_lower or "book" in fname_lower:
        result["type"] = "book_note"
        # Extract after "Книга" or "Book"
        for prefix in ["Книга ", "Book "]:
            if fname.startswith(prefix):
                title = fname[len(prefix):].strip()
                # Try to split author at —
                parts = re.split(r'\s+[—–-]\s+', title, maxsplit=1)
                result["book"] = parts[0].strip()
                if len(parts) > 1:
                    result["author"] = parts[1].strip()

    # Default topic from folder
    folder_topics = {
        "сны": ["сон", "психология"],
        "мысли_из_книг": ["книги", "цитаты"],
        "философия": ["философия"],
        "стихи": ["поэзия"],
        "психолог": ["психология"],
        "фото": ["фотография"],
    }
    for kw, topics in folder_topics.items():
        if kw in folder.lower().replace(" ", "_"):
            result["topics"] = topics
            break

    return result

async def enrich_file(filepath: str) -> dict | None:
    from services.ai_engine import get_ai_response_async, get_current_ai

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read().strip()
    except Exception as e:
        logger.warning(f"Не могу прочитать {filepath}: {e}")
        return None

    fname = os.path.basename(filepath)
    parent = os.path.basename(os.path.dirname(filepath))

    rel_path = os.path.relpath(filepath, os.path.expanduser("~/Documents/mempalace/my_notes"))
    source = f"my_notes/{rel_path}"

    if not content or len(content) < 50:
        data = _extract_from_filename(fname, parent)
        return {"file": fname, "folder": parent, "path": source, "data": data}

    try:
        engine, model = get_current_ai()
        answer = await get_ai_response_async(
            engine, model,
            [{"role": "user", "content": _build_prompt(fname, parent, content[:3000])}],
            context=""
        )
        if answer.startswith("❌"):
            logger.warning(f"AI error for {fname}: {answer[:100]}")
            data = _extract_from_filename(fname, parent)
            return {"file": fname, "folder": parent, "path": source, "data": data}

        answer = answer.strip()
        if answer.startswith("```"):
            lines = answer.split("\n")
            answer = "\n".join(lines[1:-1])
        if answer.startswith("json") or answer.startswith("JSON"):
            answer = answer[4:].strip()

        data = json.loads(answer)
    except Exception as e:
        logger.warning(f"AI parse failed for {fname}: {e}, falling back to filename")
        data = _extract_from_filename(fname, parent)

    return {"file": fname, "folder": parent, "path": source, "data": data}

async def add_kg_facts(enriched: dict):
    from services.palace_mcp import get_mcp

    mcp = get_mcp()
    data = enriched["data"]
    fname = enriched["file"]
    source = enriched["path"]
    author = data.get("author")
    book = data.get("book")
    ideas = data.get("ideas", [])
    quotes = data.get("quotes", [])
    topics = data.get("topics", [])

    added = 0

    if author and book:
        try:
            await mcp.call_tool("mempalace_kg_add", {
                "subject": author, "predicate": "wrote",
                "object": book, "source_closet": source
            })
            added += 1
        except Exception as e:
            logger.warning(f"KG add author→book: {e}")

    entity = book or author or fname.replace(".txt", "").replace("_", " ")

    for idea in ideas[:3]:
        try:
            await mcp.call_tool("mempalace_kg_add", {
                "subject": entity, "predicate": "contains_idea",
                "object": idea[:200], "source_closet": source
            })
            added += 1
        except Exception:
            pass

    for quote in quotes[:3]:
        try:
            await mcp.call_tool("mempalace_kg_add", {
                "subject": entity, "predicate": "contains_quote",
                "object": quote[:200], "source_closet": source
            })
            added += 1
        except Exception:
            pass

    for topic in topics:
        try:
            await mcp.call_tool("mempalace_kg_add", {
                "subject": entity, "predicate": "topic",
                "object": topic, "source_closet": source
            })
            added += 1
        except Exception:
            pass

    return added

async def enrich_all_notes(progress_callback=None) -> dict:
    notes_dir = os.path.expanduser("~/Documents/mempalace/my_notes")
    files = []
    for root, dirs, fnames in os.walk(notes_dir):
        for f in fnames:
            if f.endswith(".txt") or f.endswith(".md"):
                files.append(os.path.join(root, f))

    if not files:
        return {"error": "Нет .txt/.md файлов в my_notes"}

    logger.info(f"Найдено {len(files)} файлов для enrichment")

    from services.palace_mcp import get_mcp
    mcp = get_mcp()
    try:
        await mcp.start()
    except Exception as e:
        return {"error": f"MCP start failed: {e}"}

    stats = {"total": len(files), "processed": 0, "failed": 0, "kg_added": 0, "authors": set(), "books": set()}

    for i, fp in enumerate(files):
        enriched = await enrich_file(fp)
        if enriched and enriched.get("data"):
            kg_count = await add_kg_facts(enriched)
            stats["processed"] += 1
            stats["kg_added"] += kg_count
            if enriched["data"].get("author"):
                stats["authors"].add(enriched["data"]["author"])
            if enriched["data"].get("book"):
                stats["books"].add(enriched["data"]["book"])
        else:
            stats["failed"] += 1

        if progress_callback:
            await progress_callback(i + 1, len(files), stats)

        if (i + 1) % 10 == 0:
            logger.info(f"Progress: {i+1}/{len(files)} — KG facts added: {stats['kg_added']}")

    stats["authors"] = list(stats["authors"])
    stats["books"] = list(stats["books"])
    return stats
