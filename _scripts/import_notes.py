#!/usr/bin/env python3
"""Умный импорт заметок из Apple Notes в MemPalace с авторазметкой и извлечением PDF.

Поддерживает:
1. Автоматическое определение путей MemPalace, venv и mempalace_bot из любой точки системы.
2. Фильтрацию папок (автоматическое исключение «Недавно удаленные»).
3. Импорт ВСЕХ заметок, импорт ВСЕХ КРОМЕ указанных, либо конкретной папки.
4. Извлечение текста из вложенных PDF-файлов с помощью PyMuPDF (fitz) и индексацию в базу.
5. AI-разметку (Ollama / qwen2.5) и добавление фактов в Граф Знаний (MCP mempalace_kg_add).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ── ДИНАМИЧЕСКИЙ ПОИСК ПУТЕЙ В СИСТЕМЕ ────────────────────────────────────────
def _find_dir(target_name: str, indicators: list[str]) -> str | None:
    env_val = os.environ.get(f"{target_name.upper()}_DIR")
    if env_val and os.path.isdir(env_val):
        return os.path.abspath(env_val)

    cur = os.path.abspath(os.path.dirname(__file__))
    for _ in range(4):
        if os.path.basename(cur) == target_name:
            if all(os.path.exists(os.path.join(cur, ind)) for ind in indicators):
                return cur
        cand = os.path.join(cur, target_name)
        if os.path.isdir(cand) and all(
            os.path.exists(os.path.join(cand, ind)) for ind in indicators
        ):
            return cand
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent

    home = os.path.expanduser("~")
    for base in [os.path.join(home, "Documents"), home, os.getcwd()]:
        cand = os.path.join(base, target_name)
        if os.path.isdir(cand) and all(
            os.path.exists(os.path.join(cand, ind)) for ind in indicators
        ):
            return cand
    return None


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MEMPALACE_DIR = _find_dir("mempalace", ["my_notes"]) or os.path.expanduser("~/Documents/mempalace")
BOT_DIR = _find_dir("mempalace_bot", ["handlers", "services"]) or os.path.expanduser(
    "~/Documents/mempalace_bot"
)
NOTES_DIR = os.path.join(MEMPALACE_DIR, "my_notes")
os.makedirs(NOTES_DIR, exist_ok=True)

if BOT_DIR and BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)

try:
    from services.ollama_process import OllamaProcessManager
except ImportError:
    OllamaProcessManager = None

OLLAMA_URL = "http://localhost:11434/api/generate"
AI_MODEL = "qwen2.5:7b"


# ── ЧТЕНИЕ APPLE NOTES И ВЛОЖЕНИЙ ─────────────────────────────────────────────
def get_apple_notes_folders() -> list[str]:
    script = 'tell application "Notes" to get name of folders'
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        folders_str = proc.stdout
    except Exception as e:
        print(f"⚠️ Ошибка получения папок Apple Notes: {e}")
        return []

    raw = [f.strip() for f in folders_str.split(",") if f.strip()]
    seen = set()
    cleaned = []
    ignored = {"recently deleted", "недавно удаленные", "недавно удалённые"}
    for f in raw:
        if f.lower() in ignored:
            continue
        if f not in seen:
            seen.add(f)
            cleaned.append(f)
    return cleaned


def get_notes_in_folder(folder_name: str) -> list[str]:
    safe_folder = folder_name.replace("\\", "\\\\").replace('"', '\\"')
    script = f'tell application "Notes" to get name of notes in folder "{safe_folder}"'
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=25,
        )
        notes = proc.stdout
        if not notes.strip() or "error" in notes.lower():
            return []
        return [n.strip() for n in notes.split(",") if n.strip()]
    except Exception as e:
        print(f"⚠️ Ошибка получения заметок из папки '{folder_name}': {e}")
        return []


def get_note_body(folder_name: str, note_name: str) -> str:
    safe_folder = folder_name.replace("\\", "\\\\").replace('"', '\\"')
    safe_note = note_name.replace("\\", "\\\\").replace('"', '\\"')
    script = (
        f'tell application "Notes" to get body of note "{safe_note}" '
        f'in folder "{safe_folder}"'
    )
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        content = proc.stdout
        return re.sub(r"<[^<]+?>", "", content)
    except Exception as e:
        print(f"⚠️ Ошибка чтения тела заметки '{note_name}': {e}")
        return ""


def get_note_attachments(folder_name: str, note_name: str) -> list[dict]:
    """Retrieve attachment metadata (name and disk path) for a note in Notes.app."""
    safe_folder = folder_name.replace("\\", "\\\\").replace('"', '\\"')
    safe_note = note_name.replace("\\", "\\\\").replace('"', '\\"')

    # 1. Direct JXA query for precise paths
    jxa = f"""
    (() => {{
        try {{
            const app = Application("Notes");
            const folder = app.folders.byName("{safe_folder}");
            if (!folder) return "[]";
            const note = folder.notes.byName("{safe_note}");
            if (!note) return "[]";
            const atts = note.attachments();
            const res = [];
            for (let a of atts) {{
                try {{
                    const c = a.contents();
                    if (c) {{
                        res.push({{
                            name: a.name() || "",
                            path: c.toString()
                        }});
                    }}
                }} catch(e) {{}}
            }}
            return JSON.stringify(res);
        }} catch(err) {{
            return "[]";
        }}
    }})()
    """
    try:
        proc = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", jxa],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
        )
        out = proc.stdout.strip()
        if out and out.startswith("["):
            return json.loads(out)
    except Exception:
        pass

    # 2. AppleScript fallback
    as_code = f"""
    tell application "Notes"
        set pathsList to {{}}
        try
            set n to note "{safe_note}" of folder "{safe_folder}"
            repeat with att in attachments of n
                try
                    set p to properties of att
                    set pth to POSIX path of (contents of p)
                    set end of pathsList to pth
                end try
            end repeat
        end try
        return pathsList
    end tell
    """
    try:
        proc = subprocess.run(
            ["osascript", "-e", as_code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
        )
        out = proc.stdout.strip()
        if out:
            paths = [p.strip() for p in out.split(",") if p.strip()]
            return [{"name": os.path.basename(p), "path": p} for p in paths]
    except Exception:
        pass

    return []


def extract_pdf_text(pdf_path: str, max_pages: int = 30) -> str:
    """Extract text from PDF using PyMuPDF (fitz) with OCR fallback (Hybrid Option 3).

    1. Attempts fast native text extraction via PyMuPDF (fitz).
    2. If native text is absent or sparse (< 100 chars total, or pages have < 30 chars),
       falls back to OCR using pdf2image + pytesseract (deu+rus+eng, psm 6).
    """
    if not os.path.isfile(pdf_path):
        return ""

    filename = os.path.basename(pdf_path)
    pages_native: list[tuple[int, str]] = []
    scanned_page_nums: list[int] = []

    try:
        import fitz

        doc = fitz.open(pdf_path)
        total_pages = min(len(doc), max_pages)
        for i in range(total_pages):
            page_num = i + 1
            text = doc[i].get_text().strip()
            pages_native.append((page_num, text))
            if len(text) < 30:
                scanned_page_nums.append(page_num)
        doc.close()
    except Exception as e:
        print(f"  ⚠️ Ошибка PyMuPDF ({filename}): {e}")
        total_pages = 0

    total_native_len = sum(len(txt) for _, txt in pages_native)

    # If all pages have sufficient native text (no scans and total len >= 100)
    if not scanned_page_nums and total_native_len >= 100:
        parts = [f"--- Страница {p} ---\n{txt}" for p, txt in pages_native if txt]
        return "\n\n".join(parts)

    # Hybrid Fallback: Attempt OCR for empty/sparse pages or full document if native is low
    try:
        from pdf2image import convert_from_path
        import pytesseract

        ocr_map: dict[int, str] = {}
        all_scanned = total_native_len < 100

        if all_scanned:
            limit = total_pages if total_pages > 0 else max_pages
            print(f"  🔍 Запуск OCR для сканированного PDF: {filename} (до {limit} стр.)...")
            images = convert_from_path(
                pdf_path,
                dpi=200,
                first_page=1,
                last_page=limit,
                thread_count=2,
            )
            for idx, img in enumerate(images, 1):
                txt = pytesseract.image_to_string(
                    img,
                    lang="deu+rus+eng",
                    config="--psm 6",
                ).strip()
                if txt:
                    ocr_map[idx] = txt
        else:
            print(
                f"  🔍 Запуск выборочного OCR ({len(scanned_page_nums)} стр.) "
                f"для: {filename}..."
            )
            for p_num in scanned_page_nums:
                try:
                    images = convert_from_path(
                        pdf_path,
                        dpi=200,
                        first_page=p_num,
                        last_page=p_num,
                        thread_count=2,
                    )
                    if images:
                        txt = pytesseract.image_to_string(
                            images[0],
                            lang="deu+rus+eng",
                            config="--psm 6",
                        ).strip()
                        if txt:
                            ocr_map[p_num] = txt
                except Exception as page_err:
                    print(f"  ⚠️ Ошибка OCR на стр. {p_num}: {page_err}")

        merged_pages: list[str] = []
        if pages_native:
            for p_num, native_txt in pages_native:
                ocr_txt = ocr_map.get(p_num, "")
                if ocr_txt and (len(ocr_txt) > len(native_txt) or len(native_txt) < 30):
                    merged_pages.append(f"--- Страница {p_num} (OCR) ---\n{ocr_txt}")
                elif native_txt:
                    merged_pages.append(f"--- Страница {p_num} ---\n{native_txt}")
        else:
            for p_num in sorted(ocr_map.keys()):
                merged_pages.append(f"--- Страница {p_num} (OCR) ---\n{ocr_map[p_num]}")

        if merged_pages:
            return "\n\n".join(merged_pages)

    except Exception as ocr_err:
        print(f"  ⚠️ OCR-распознавание недоступно для {filename}: {ocr_err}")

    if pages_native:
        parts = [f"--- Страница {p} ---\n{txt}" for p, txt in pages_native if txt]
        return "\n\n".join(parts)

    return ""


# ── СТРУКТУРИРОВАННАЯ РАЗМЕТКА И AI-АНАЛИЗ ──────────────────────────────────
STRUCTURED_PATTERNS = {
    "author": re.compile(r"^Автор[ы]?\s*:\s*(.+)$", re.MULTILINE | re.IGNORECASE),
    "book": re.compile(r"^Книг[аи]?\s*:\s*(.+)$", re.MULTILINE | re.IGNORECASE),
    "source": re.compile(r"^Источник\s*:\s*(.+)$", re.MULTILINE | re.IGNORECASE),
}

MULTI_PATTERNS = {
    "ideas": re.compile(r"^Иде[яи]?\s*:\s*(.+)$", re.MULTILINE | re.IGNORECASE),
    "quotes": re.compile(r"^Цитат[аы]?\s*:\s*(.+)$", re.MULTILINE | re.IGNORECASE),
    "topics": re.compile(r"^Тем[аы]?\s*:\s*(.+)$", re.MULTILINE | re.IGNORECASE),
}


def parse_structured_metadata(text: str) -> dict:
    result = {
        "author": None,
        "book": None,
        "source": None,
        "ideas": [],
        "quotes": [],
        "topics": [],
        "_structured": False,
    }
    for key, pat in STRUCTURED_PATTERNS.items():
        m = pat.search(text)
        if m:
            result[key] = m.group(1).strip()
    for key, pat in MULTI_PATTERNS.items():
        m = pat.search(text)
        if m:
            raw = m.group(1).strip()
            items = re.split(r"[;,\n]|(?:\s*[•\-*]\s*)", raw)
            quotes_to_strip = "\u00ab\u00bb\"'\u201c\u201d"
            result[key] = [i.strip().strip(quotes_to_strip) for i in items if i.strip()]
    if result["author"] or result["book"] or result["ideas"] or result["quotes"]:
        result["_structured"] = True
    return result


EXTRACT_PROMPT = """Analyze the filename, folder, and content of this note.
Extract structured information as JSON.

Respond ONLY with valid JSON (no extra text):
{{
  "author": "author name or null",
  "book": "book title or null",
  "ideas": ["key idea 1", "key idea 2"],
  "quotes": ["quote 1"],
  "topics": ["topic 1"],
  "type": "book_note|personal_thought|poem|dream|other"
}}

Rules:
- author: extract from filename, folder or text. E.g. 'Фауст Гёте' -> author='Гёте'
- book: book title from filename or text
- ideas: key ideas (max 3). If text empty, infer from title
- quotes: direct quotes in quotation marks
- topics: 2-3 general topics (e.g. psychology, photography, dream, poetry)
- type: book_note, dream, poem, personal_thought, or other

File: {fname}
Folder: {folder}
Content:
{content}"""


def ai_enrich(fname: str, folder: str, content: str) -> dict | None:
    prompt = EXTRACT_PROMPT.format(
        fname=fname,
        folder=folder,
        content=(content[:3000] if content else "[пусто]"),
    )
    payload = {
        "model": AI_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1},
    }
    try:
        req = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            answer = json.loads(raw).get("response", "").strip()
    except Exception as e:
        print(f"  ⚠️ AI error: {e}")
        return None
    if answer.startswith("```"):
        lines = answer.split("\n")
        answer = "\n".join(lines[1:-1])
    if answer.upper().startswith("JSON"):
        answer = answer[4:].strip()
    try:
        return json.loads(answer)
    except json.JSONDecodeError:
        print(f"  ⚠️ AI response not valid JSON: {answer[:100]}")
        return None


# ── СИНХРОННЫЙ КЛИЕНТ MCP (ДЛЯ KNOWLEDGE GRAPH) ──────────────────────────────
class SyncMCPClient:
    def __init__(self):
        self._proc = None
        self._seq = 0

    def __enter__(self):
        venv_python = os.path.join(MEMPALACE_DIR, "venv", "bin", "python3")
        env = os.environ.copy()
        env["VIRTUAL_ENV"] = os.path.join(MEMPALACE_DIR, "venv")
        env["PATH"] = (
            os.path.join(MEMPALACE_DIR, "venv", "bin")
            + os.pathsep
            + env.get("PATH", "")
        )
        if not os.path.exists(venv_python):
            venv_python = sys.executable
        self._proc = subprocess.Popen(
            [venv_python, "-m", "mempalace.mcp_server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            cwd=MEMPALACE_DIR,
        )
        init_resp = self._rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "import-notes", "version": "1.0"},
            },
        )
        if "result" not in init_resp:
            raise RuntimeError(f"MCP handshake failed: {init_resp}")
        self._notify("notifications/initialized")
        return self

    def __exit__(self, *args):
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()
            self._proc = None

    def _send(self, msg: dict):
        if not self._proc or not self._proc.stdin:
            raise RuntimeError("MCP not running")
        self._proc.stdin.write(json.dumps(msg) + "\n")
        self._proc.stdin.flush()

    def _recv(self) -> dict:
        line = self._proc.stdout.readline()
        if not line:
            raise RuntimeError("MCP connection closed")
        return json.loads(line)

    def _notify(self, method: str):
        self._send({"jsonrpc": "2.0", "method": method})

    def _rpc(self, method: str, params: dict = None) -> dict:
        self._seq += 1
        msg = {"jsonrpc": "2.0", "id": self._seq, "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)
        return self._recv()

    def call_tool(self, name: str, arguments: dict = None) -> dict:
        resp = self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        if "error" in resp:
            raise RuntimeError(f"MCP error: {resp['error']}")
        return resp


def add_facts_for_note(mcp: SyncMCPClient, rel_path: str, data: dict) -> int:
    added = 0
    author = data.get("author")
    book = data.get("book")
    ideas = data.get("ideas", []) or []
    quotes = data.get("quotes", []) or []
    topics = data.get("topics", []) or []

    if author and book:
        try:
            mcp.call_tool(
                "mempalace_kg_add",
                {
                    "subject": author,
                    "predicate": "wrote",
                    "object": book,
                    "source_closet": rel_path,
                },
            )
            added += 1
        except Exception as e:
            print(f"  ⚠️ KG add error (author→book): {e}")

    entity = (
        book or author or os.path.basename(rel_path).replace(".txt", "").replace("_", " ")
    )
    for idea in ideas[:3]:
        try:
            mcp.call_tool(
                "mempalace_kg_add",
                {
                    "subject": entity,
                    "predicate": "contains_idea",
                    "object": idea[:200],
                    "source_closet": rel_path,
                },
            )
            added += 1
        except Exception:
            pass
    for quote in quotes[:3]:
        try:
            mcp.call_tool(
                "mempalace_kg_add",
                {
                    "subject": entity,
                    "predicate": "contains_quote",
                    "object": quote[:200],
                    "source_closet": rel_path,
                },
            )
            added += 1
        except Exception:
            pass
    for topic in topics:
        try:
            mcp.call_tool(
                "mempalace_kg_add",
                {
                    "subject": entity,
                    "predicate": "topic",
                    "object": topic,
                    "source_closet": rel_path,
                },
            )
            added += 1
        except Exception:
            pass
    return added


def import_note(folder_name: str, note_name: str, mcp: SyncMCPClient | None) -> int:
    target_dir = os.path.join(NOTES_DIR, folder_name)
    os.makedirs(target_dir, exist_ok=True)
    content = get_note_body(folder_name, note_name)

    # Check for embedded attachments (especially PDF)
    attachments = get_note_attachments(folder_name, note_name)
    pdf_count = 0
    for att in attachments:
        att_path = att.get("path", "")
        att_name = att.get("name") or os.path.basename(att_path)
        if att_path.lower().endswith(".pdf") or att_name.lower().endswith(".pdf"):
            pdf_text = extract_pdf_text(att_path)
            if pdf_text:
                pdf_count += 1
                header = (
                    f"\n\n{'=' * 50}\n"
                    f"📎 ВЛОЖЕННЫЙ ДОКУМЕНТ (PDF): {att_name}\n"
                    f"{'=' * 50}\n\n"
                )
                content += header + pdf_text
                print(f"  📄 Извлечён текст из PDF: {att_name} ({len(pdf_text)} симв.)")

    safe_name = re.sub(r'[\\/*?:"<>|]', "", note_name)
    file_path = os.path.join(target_dir, f"{safe_name}.txt")
    rel_path = f"my_notes/{folder_name}/{safe_name}.txt"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    structured = parse_structured_metadata(content)
    data = None
    source = "—"

    if structured["_structured"]:
        data = structured
        source = "📋 структура"
        print("  📋 Структурированный формат — парсинг напрямую")
    else:
        print("  🤖 AI-анализ (Ollama)...")
        result = ai_enrich(f"{safe_name}.txt", folder_name, content)
        if result:
            data = result
            source = "AI"
        else:
            data = {"author": None, "book": None, "ideas": [], "quotes": [], "topics": []}

    kg_count = add_facts_for_note(mcp, rel_path, data) if mcp else 0

    parts = []
    if data.get("author"):
        parts.append(f"автор: {data['author']}")
    if data.get("book"):
        parts.append(f"книга: {data['book']}")
    if data.get("ideas"):
        parts.append(f"идеи: {len(data['ideas'])}")
    if data.get("quotes"):
        parts.append(f"цитаты: {len(data['quotes'])}")
    if data.get("topics"):
        parts.append(f"темы: {', '.join(data['topics'][:3])}")
    if pdf_count > 0:
        parts.append(f"PDF: {pdf_count}")
    meta_str = f" ({'; '.join(parts)})" if parts else ""
    kg_str = f" → KG: +{kg_count}" if kg_count else ""
    print(f"  ✓ {source}{meta_str}{kg_str}")
    return kg_count


# ── ГЛАВНОЕ МЕНЮ И УПРАВЛЕНИЕ ИМПОРТОМ ─────────────────────────────────────────
def main():
    print("\n" + "=" * 58)
    print("   📥  УМНЫЙ ИМПОРТ ИЗ APPLE NOTES В MEMPALACE")
    print("   + Авто-парсинг: Автор:, Книга:, Идеи: и др.")
    print("   + Извлечение текста из вложенных PDF-файлов (fitz)")
    print("   + AI-анализ (Ollama) для обычных заметок")
    print("   + Факты в Knowledge Graph через MCP")
    print("=" * 58)
    print(f"  Папка сохранения: {NOTES_DIR}")

    folders = get_apple_notes_folders()
    if not folders:
        print("❌ Не найдено папок в Apple Notes.")
        return

    print("\n[1] 🌟 Импортировать ВСЕ заметки из ВСЕХ папок")
    print("[2] 🛡️  Импортировать ВСЕ заметки КРОМЕ... (выбор папок/заметок)")
    print("[3] 📂 Выбрать КОНКРЕТНУЮ папку")
    print("[0] 🚪 Отмена")

    choice = input("\nВыберите режим (0-3): ").strip()
    if choice in ("0", "q", "exit", ""):
        print("Отмена.")
        return

    items_to_import: list[tuple[str, str]] = []  # (folder, note_name)

    if choice == "1":
        print("\n⏳ Сканирую все заметки во всех папках...")
        for f in folders:
            notes = get_notes_in_folder(f)
            for n in notes:
                items_to_import.append((f, n))
        print(f"  Найдено {len(items_to_import)} заметок в {len(folders)} папках.")
        confirm = input("Начать импорт? (Y/n): ").strip().lower()
        if confirm == "n":
            print("Отмена.")
            return

    elif choice == "2":
        print("\n=== ПАПКИ В APPLE NOTES ===")
        for i, f in enumerate(folders, 1):
            print(f"  {i}. {f}")
        excl_str = input(
            "\nВведите номера папок для ИСКЛЮЧЕНИЯ через запятую (напр. 2, 5) "
            "или Enter: "
        ).strip()
        excluded_folder_indices = set()
        if excl_str:
            for part in excl_str.split(","):
                part = part.strip()
                if part.isdigit():
                    excluded_folder_indices.add(int(part) - 1)

        allowed_folders = [
            f for i, f in enumerate(folders) if i not in excluded_folder_indices
        ]
        n_allow = len(allowed_folders)
        n_excl = len(excluded_folder_indices)
        print(f"\nВыбрано папок: {n_allow} (исключено: {n_excl})")

        print("⏳ Загружаю список заметок из выбранных папок...")
        all_candidates: list[tuple[str, str]] = []
        for f in allowed_folders:
            notes = get_notes_in_folder(f)
            for n in notes:
                all_candidates.append((f, n))

        ask_notes = input(
            f"Найдено {len(all_candidates)} заметок. Хотите исключить отдельные заметки? (y/N): "
        ).strip().lower()
        if ask_notes == "y":
            print("\nСписок заметок:")
            for idx, (f, n) in enumerate(all_candidates, 1):
                print(f"  {idx}. [{f}] {n}")
            excl_notes_str = input(
                "Введите номера заметок для исключения через запятую (напр. 1, 4): "
            ).strip()
            excluded_note_indices = set()
            if excl_notes_str:
                for part in excl_notes_str.split(","):
                    part = part.strip()
                    if part.isdigit():
                        excluded_note_indices.add(int(part) - 1)
            items_to_import = [
                item for i, item in enumerate(all_candidates) if i not in excluded_note_indices
            ]
        else:
            items_to_import = all_candidates

    elif choice == "3":
        print("\n=== ПАПКИ В APPLE NOTES ===")
        for i, folder in enumerate(folders, 1):
            print(f"  {i}. {folder}")
        try:
            f_idx = int(input("\nВыберите номер папки: ")) - 1
            selected_folder = folders[f_idx]
        except (ValueError, IndexError):
            print("❌ Ошибка выбора папки.")
            return

        notes = get_notes_in_folder(selected_folder)
        if not notes:
            print(f"❌ В папке '{selected_folder}' не найдено заметок.")
            return

        print(f"\n📂 Папка: {selected_folder} ({len(notes)} заметок)")
        print("1. Импортировать ВСЕ заметки")
        print("2. Импортировать ВСЕ КРОМЕ указанных")
        print("3. Выбрать КОНКРЕТНЫЕ заметки")
        sub_mode = input("\nВаш выбор (1-3): ").strip()

        if sub_mode == "1":
            items_to_import = [(selected_folder, n) for n in notes]
        elif sub_mode == "2":
            print("\nСписок заметок:")
            for i, note in enumerate(notes, 1):
                print(f"  {i}. {note}")
            choices = input("\nВведите номера для ИСКЛЮЧЕНИЯ (напр. 1, 3): ")
            try:
                indices = {int(x.strip()) - 1 for x in choices.split(",") if x.strip().isdigit()}
                items_to_import = [
                    (selected_folder, notes[i]) for i in range(len(notes)) if i not in indices
                ]
            except Exception:
                print("❌ Ошибка ввода номеров.")
                return
        elif sub_mode == "3":
            print("\nСписок заметок:")
            for i, note in enumerate(notes, 1):
                print(f"  {i}. {note}")
            choices = input("\nВведите номера заметок через запятую (напр. 1, 3, 5): ")
            try:
                indices = [int(x.strip()) - 1 for x in choices.split(",") if x.strip().isdigit()]
                items_to_import = [
                    (selected_folder, notes[i]) for i in indices if 0 <= i < len(notes)
                ]
            except Exception:
                print("❌ Ошибка ввода номеров.")
                return
        else:
            print("❌ Неверный выбор.")
            return

    if not items_to_import:
        print("❌ Нет заметок для импорта.")
        return

    print(f"\n{'-' * 58}")
    print(f"  Импортирую {len(items_to_import)} заметок...")
    print(f"{'-' * 58}")

    mcp = None
    ollama_manager = None
    try:
        mcp = SyncMCPClient().__enter__()
        print("  ✅ MCP подключен к MemPalace")
    except Exception as e:
        print(f"  ⚠️ MCP не запущен ({e}) — факты в KG будут пропущены")

    if OllamaProcessManager is not None:
        try:
            print(f"\n🔄 Проверка Ollama с моделью {AI_MODEL}...")
            ollama_manager = OllamaProcessManager(model=AI_MODEL)
            ollama_manager.ensure_running()
            print("  ✅ Ollama готова")
        except Exception as e:
            print(f"  ⚠️ Ollama не запущена: {e}")

    total_kg = 0
    imported = 0
    skipped = 0

    try:
        for folder_name, note in items_to_import:
            safe_name = re.sub(r'[\\/*?:"<>|]', "", note)
            file_path = os.path.join(NOTES_DIR, folder_name, f"{safe_name}.txt")
            if os.path.exists(file_path):
                print(f"  ⏩ [{folder_name}] {note} (уже существует)")
                skipped += 1
                continue
            print(f"\n📄 [{folder_name}] {note}")
            try:
                kg_added = import_note(folder_name, note, mcp)
                total_kg += kg_added
                imported += 1
            except KeyboardInterrupt:
                print("\n\n⚠️ Импорт прерван пользователем.")
                break
            except Exception as e:
                print(f"  ❌ Ошибка: {e}")
                continue
    finally:
        if mcp:
            try:
                mcp.__exit__()
            except Exception:
                pass
        if ollama_manager is not None:
            try:
                ollama_manager.stop()
            except Exception:
                pass

    print(f"\n{'-' * 58}")
    print(f"  ✅ Импортировано: {imported}")
    if skipped:
        print(f"  ⏩ Пропущено (уже есть): {skipped}")
    if mcp:
        print(f"  🧠 Добавлено в KG: {total_kg} связей")
    print(f"{'-' * 58}")

    if imported > 0:
        try:
            do_mine = input(
                "\nСинхронизировать с векторной базой (mempalace mine)? (Y/n): "
            ).strip().lower()
            if do_mine != "n":
                print("\n⏳ Синхронизация и майнинг...")
                venv_py = os.path.join(MEMPALACE_DIR, "venv", "bin", "python3")
                if not os.path.isfile(venv_py):
                    venv_py = sys.executable
                res = subprocess.run(
                    [venv_py, "-m", "mempalace", "mine", "my_notes"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=MEMPALACE_DIR,
                )
                if res.returncode == 0:
                    print(f"  ✅ {res.stdout.strip() or 'Готово'}")
                else:
                    print(f"  ⚠️ {res.stderr.strip() or 'Ошибка синхронизации'}")
        except KeyboardInterrupt:
            print("\nСинхронизация пропущена.")

    print("\n✅ Готово!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🚪 Выход из импорта Apple Notes.")
        sys.exit(0)
