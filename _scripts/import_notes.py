#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import textwrap
import urllib.error
import urllib.request

sys.path.insert(0, "/Users/evg.pit/Documents/mempalace_bot")
from services.ollama_process import OllamaProcessManager

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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MEMPALACE_DIR = os.environ.get("MEMPALACE_DIR") or SCRIPT_DIR
NOTES_DIR = os.path.join(MEMPALACE_DIR, "my_notes")
OLLAMA_URL = "http://localhost:11434/api/generate"
AI_MODEL = "qwen2.5:7b"

os.makedirs(NOTES_DIR, exist_ok=True)

def get_apple_notes_folders():
    script = 'tell application "Notes" to get name of folders'
    folders = subprocess.run(
        ['osascript', '-e', script],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
    ).stdout
    return [f.strip() for f in folders.split(',')]

def get_notes_in_folder(folder_name):
    script = f'tell application "Notes" to get name of notes in folder "{folder_name}"'
    notes = subprocess.run(
        ['osascript', '-e', script],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
    ).stdout
    if not notes.strip() or "error" in notes.lower():
        return []
    return [n.strip() for n in notes.split(',')]

def get_note_body(folder_name, note_name):
    script = f'tell application "Notes" to get body of note "{note_name}" in folder "{folder_name}"'
    content = subprocess.run(
        ['osascript', '-e', script],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
    ).stdout
    return re.sub('<[^<]+?>', '', content)

STRUCTURED_PATTERNS = {
    "author": re.compile(r'^Автор[ы]?\s*:\s*(.+)$', re.MULTILINE | re.IGNORECASE),
    "book":   re.compile(r'^Книг[аи]?\s*:\s*(.+)$', re.MULTILINE | re.IGNORECASE),
    "source": re.compile(r'^Источник\s*:\s*(.+)$', re.MULTILINE | re.IGNORECASE),
}

MULTI_PATTERNS = {
    "ideas":  re.compile(r'^Иде[яи]?\s*:\s*(.+)$', re.MULTILINE | re.IGNORECASE),
    "quotes": re.compile(r'^Цитат[аы]?\s*:\s*(.+)$', re.MULTILINE | re.IGNORECASE),
    "topics": re.compile(r'^Тем[аы]?\s*:\s*(.+)$', re.MULTILINE | re.IGNORECASE),
}

def parse_structured_metadata(text):
    result = {"author": None, "book": None, "source": None, "ideas": [], "quotes": [], "topics": [], "_structured": False}
    for key, pat in STRUCTURED_PATTERNS.items():
        m = pat.search(text)
        if m:
            result[key] = m.group(1).strip()
    for key, pat in MULTI_PATTERNS.items():
        m = pat.search(text)
        if m:
            raw = m.group(1).strip()
            items = re.split(r'[;,\n]|(?:\s*[•\-*]\s*)', raw)
            result[key] = [i.strip().strip('\u00ab\u00bb""\u0027') for i in items if i.strip()]
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
- topics: 2-3 general topics (e.g. psychology, photography, jungian, dream, poetry)
- type: book_note if about a book, dream if a dream, poem if poetry, personal_thought if own thoughts

File: {fname}
Folder: {folder}
Content:
{content}"""

def ai_enrich(fname, folder, content):
    prompt = EXTRACT_PROMPT.format(fname=fname, folder=folder, content=(content[:3000] if content else "[пусто]"))
    payload = {"model": AI_MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0.1}}
    try:
        req = urllib.request.Request(OLLAMA_URL, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            answer = json.loads(raw).get("response", "").strip()
    except Exception as e:
        print(f"  \u26a0\ufe0f AI error: {e}")
        return None
    if answer.startswith("```"):
        lines = answer.split("\n")
        answer = "\n".join(lines[1:-1])
    if answer.upper().startswith("JSON"):
        answer = answer[4:].strip()
    try:
        return json.loads(answer)
    except json.JSONDecodeError:
        print(f"  \u26a0\ufe0f AI response not valid JSON: {answer[:100]}")
        return None

class SyncMCPClient:
    def __init__(self):
        self._proc = None
        self._seq = 0

    def __enter__(self):
        venv_python = os.path.join(MEMPALACE_DIR, "venv", "bin", "python3")
        env = os.environ.copy()
        env["VIRTUAL_ENV"] = os.path.join(MEMPALACE_DIR, "venv")
        env["PATH"] = os.path.join(MEMPALACE_DIR, "venv", "bin") + os.pathsep + env.get("PATH", "")
        if not os.path.exists(venv_python):
            venv_python = sys.executable
        self._proc = subprocess.Popen(
            [venv_python, "-m", "mempalace.mcp_server"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, text=True, cwd=MEMPALACE_DIR
        )
        init_resp = self._rpc("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "import-notes", "version": "1.0"}
        })
        if "result" not in init_resp:
            raise RuntimeError(f"MCP handshake failed: {init_resp}")
        self._notify("notifications/initialized")
        return self

    def __exit__(self, *args):
        if self._proc:
            self._proc.terminate()
            try: self._proc.wait(timeout=5)
            except: self._proc.kill()
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

def add_facts_for_note(mcp, rel_path, data):
    added = 0
    author = data.get("author")
    book = data.get("book")
    ideas = data.get("ideas", []) or []
    quotes = data.get("quotes", []) or []
    topics = data.get("topics", []) or []
    if author and book:
        try:
            mcp.call_tool("mempalace_kg_add", {"subject": author, "predicate": "wrote", "object": book, "source_closet": rel_path})
            added += 1
        except Exception as e:
            print(f"  \u26a0\ufe0f KG add error (author\u2192book): {e}")
    entity = book or author or os.path.basename(rel_path).replace(".txt", "").replace("_", " ")
    for idea in ideas[:3]:
        try:
            mcp.call_tool("mempalace_kg_add", {"subject": entity, "predicate": "contains_idea", "object": idea[:200], "source_closet": rel_path})
            added += 1
        except Exception:
            pass
    for quote in quotes[:3]:
        try:
            mcp.call_tool("mempalace_kg_add", {"subject": entity, "predicate": "contains_quote", "object": quote[:200], "source_closet": rel_path})
            added += 1
        except Exception:
            pass
    for topic in topics:
        try:
            mcp.call_tool("mempalace_kg_add", {"subject": entity, "predicate": "topic", "object": topic, "source_closet": rel_path})
            added += 1
        except Exception:
            pass
    return added

def import_note(folder_name, note_name, mcp):
    target_dir = os.path.join(NOTES_DIR, folder_name)
    os.makedirs(target_dir, exist_ok=True)
    content = get_note_body(folder_name, note_name)
    safe_name = re.sub(r'[\\/*?:"<>|]', "", note_name)
    file_path = os.path.join(target_dir, f"{safe_name}.txt")
    rel_path = f"my_notes/{folder_name}/{safe_name}.txt"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    structured = parse_structured_metadata(content)
    data = None
    source = "\u2014"

    if structured["_structured"]:
        data = structured
        source = "\ud83d\udccb \u0441\u0442\u0440\u0443\u043a\u0442\u0443\u0440\u0430"
        print(f"  \ud83d\udccb \u0421\u0442\u0440\u0443\u043a\u0442\u0443\u0440\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u044b\u0439 \u0444\u043e\u0440\u043c\u0430\u0442 \u2014 \u043f\u0430\u0440\u0441\u0438\u043d\u0433 \u043d\u0430\u043f\u0440\u044f\u043c\u0443\u044e")
    else:
        print(f"  \ud83e\udd16 AI-\u0430\u043d\u0430\u043b\u0438\u0437 (Ollama)...")
        result = ai_enrich(f"{safe_name}.txt", folder_name, content)
        if result:
            data = result
            source = "AI"
        else:
            data = {"author": None, "book": None, "ideas": [], "quotes": [], "topics": []}

    kg_count = add_facts_for_note(mcp, rel_path, data) if mcp else 0

    parts = []
    if data.get("author"): parts.append(f"\u0430\u0432\u0442\u043e\u0440: {data['author']}")
    if data.get("book"):   parts.append(f"\u043a\u043d\u0438\u0433\u0430: {data['book']}")
    if data.get("ideas"):  parts.append(f"\u0438\u0434\u0435\u0438: {len(data['ideas'])}")
    if data.get("quotes"): parts.append(f"\u0446\u0438\u0442\u0430\u0442\u044b: {len(data['quotes'])}")
    if data.get("topics"): parts.append(f"\u0442\u0435\u043c\u044b: {', '.join(data['topics'][:3])}")
    meta_str = f" ({'; '.join(parts)})" if parts else ""
    kg_str = f" \u2192 KG: +{kg_count}" if kg_count else ""
    print(f"  \u2713 {source}{meta_str}{kg_str}")
    return kg_count

def main():
    folders = get_apple_notes_folders()

    print("\n" + "=" * 56)
    print("   \ud83d\udce5 \u0423\u041c\u041d\u042b\u0419 \u0418\u041c\u041f\u041e\u0420\u0422 \u0418\u0417 APPLE NOTES")
    print("   + \u0410\u0432\u0442\u043e-\u043f\u0430\u0440\u0441\u0438\u043d\u0433: \u0410\u0432\u0442\u043e\u0440:, \u041a\u043d\u0438\u0433\u0430:, \u0418\u0434\u0435\u0438: \u0438 \u0442.\u0434.")
    print("   + AI-\u0430\u043d\u0430\u043b\u0438\u0437 (Ollama) \u0434\u043b\u044f \u043e\u0431\u044b\u0447\u043d\u044b\u0445 \u0437\u0430\u043c\u0435\u0442\u043e\u043a")
    print("   + \u0421\u0432\u044f\u0437\u0438 \u0432 Knowledge Graph \u0447\u0435\u0440\u0435\u0437 MCP")
    print("=" * 56)

    print("\n=== \u041f\u0410\u041f\u041a\u0418 \u0412 APPLE NOTES ===")
    for i, folder in enumerate(folders, 1):
        print(f"  {i}. {folder}")

    try:
        f_idx = int(input("\n\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u043d\u043e\u043c\u0435\u0440 \u043f\u0430\u043f\u043a\u0438: ")) - 1
        selected_folder = folders[f_idx]
    except (ValueError, IndexError):
        print("\u274c \u041e\u0448\u0438\u0431\u043a\u0430 \u0432\u044b\u0431\u043e\u0440\u0430 \u043f\u0430\u043f\u043a\u0438.")
        return

    notes = get_notes_in_folder(selected_folder)
    if not notes:
        print(f"\u274c \u0412 \u043f\u0430\u043f\u043a\u0435 '{selected_folder}' \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e \u0437\u0430\u043c\u0435\u0442\u043e\u043a.")
        return

    print(f"\n\ud83d\udcc2 \u041f\u0430\u043f\u043a\u0430: {selected_folder} ({len(notes)} \u0437\u0430\u043c\u0435\u0442\u043e\u043a)")
    print("1. \u0418\u043c\u043f\u043e\u0440\u0442\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0412\u0421\u0415 \u0437\u0430\u043c\u0435\u0442\u043a\u0438")
    print("2. \u0412\u044b\u0431\u0440\u0430\u0442\u044c \u041a\u041e\u041d\u041a\u0420\u0415\u0422\u041d\u042b\u0415 \u0437\u0430\u043c\u0435\u0442\u043a\u0438")
    mode = input("\n\u0412\u0430\u0448 \u0432\u044b\u0431\u043e\u0440 (1/2): ")

    if mode == "1":
        selected_notes = notes
    elif mode == "2":
        print("\n\u0421\u043f\u0438\u0441\u043e\u043a \u0437\u0430\u043c\u0435\u0442\u043e\u043a:")
        for i, note in enumerate(notes, 1):
            print(f"  {i}. {note}")
        choices = input("\n\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043d\u043e\u043c\u0435\u0440\u0430 \u0447\u0435\u0440\u0435\u0437 \u0437\u0430\u043f\u044f\u0442\u0443\u044e (\u043d\u0430\u043f\u0440. 1,3,5): ")
        try:
            indices = [int(x.strip()) - 1 for x in choices.split(',')]
            selected_notes = [notes[i] for i in indices if 0 <= i < len(notes)]
        except ValueError:
            print("\u274c \u041e\u0448\u0438\u0431\u043a\u0430: \u0432\u0432\u043e\u0434\u0438\u0442\u0435 \u0442\u043e\u043b\u044c\u043a\u043e \u0446\u0438\u0444\u0440\u044b \u0438 \u0437\u0430\u043f\u044f\u0442\u044b\u0435.")
            return
    else:
        print("\u274c \u041d\u0435\u0432\u0435\u0440\u043d\u044b\u0439 \u0432\u044b\u0431\u043e\u0440.")
        return

    if not selected_notes:
        print("\u274c \u041d\u0435\u0442 \u0437\u0430\u043c\u0435\u0442\u043e\u043a \u0434\u043b\u044f \u0438\u043c\u043f\u043e\u0440\u0442\u0430.")
        return

    print(f"\n{'\u2500' * 56}")
    print(f"  \u0418\u043c\u043f\u043e\u0440\u0442\u0438\u0440\u0443\u044e {len(selected_notes)} \u0437\u0430\u043c\u0435\u0442\u043e\u043a \u0441 KG-\u043e\u0431\u043e\u0433\u0430\u0449\u0435\u043d\u0438\u0435\u043c...")
    print(f"{'\u2500' * 56}")

    mcp = None
    ollama_manager = None
    try:
        mcp = SyncMCPClient().__enter__()
        print(f"  \u2705 MCP \u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d")
    except Exception as e:
        print(f"  \u26a0\ufe0f MCP \u043d\u0435 \u0437\u0430\u043f\u0443\u0449\u0435\u043d ({e}) \u2014 KG \u043f\u0440\u043e\u043f\u0443\u0449\u0435\u043d")

    try:
        print("\n\uD83D\uDD04 \u0417\u0430\u043f\u0443\u0441\u043a\u0430\u044e Ollama \u0441 \u043c\u043e\u0434\u0435\u043b\u044c\u044e qwen2.5...")
        ollama_manager = OllamaProcessManager(model=AI_MODEL)
        ollama_manager.ensure_running()
        print("  \u2705 Ollama ready")
    except Exception as e:
        print(f"  \u26a0\ufe0f Ollama not started: {e}")

    total_kg = 0
    imported = 0
    skipped = 0
    try:
        for note in selected_notes:
            safe_name = re.sub(r'[\\/*?:"<>|]', "", note)
            file_path = os.path.join(NOTES_DIR, selected_folder, f"{safe_name}.txt")
            if os.path.exists(file_path):
                print(f"  \u23ed\ufe0f {note} (\u0443\u0436\u0435 \u0441\u0443\u0449\u0435\u0441\u0442\u0432\u0443\u0435\u0442)")
                skipped += 1
                continue
            print(f"\n\ud83d\udcc4 {note}")
            try:
                kg_added = import_note(selected_folder, note, mcp)
                total_kg += kg_added
                imported += 1
            except Exception as e:
                print(f"  \u274c \u041e\u0448\u0438\u0431\u043a\u0430: {e}")
                continue
    finally:
        if mcp:
            mcp.__exit__()
        if ollama_manager is not None:
            ollama_manager.stop()

    print(f"\n{'\u2500' * 56}")
    print(f"  \u2705 \u0418\u043c\u043f\u043e\u0440\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u043e: {imported}")
    if skipped:
        print(f"  \u23ed\ufe0f \u041f\u0440\u043e\u043f\u0443\u0449\u0435\u043d\u043e (\u0443\u0436\u0435 \u0435\u0441\u0442\u044c): {skipped}")
    if mcp:
        print(f"  \ud83e\udde0 \u0414\u043e\u0431\u0430\u0432\u043b\u0435\u043d\u043e \u0432 KG: {total_kg} \u0441\u0432\u044f\u0437\u0435\u0439")
    print(f"{'\u2500' * 56}")

    if imported > 0:
        do_mine = input("\n\u0421\u0438\u043d\u0445\u0440\u043e\u043d\u0438\u0437\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0441 \u0432\u0435\u043a\u0442\u043e\u0440\u043d\u043e\u0439 \u0431\u0430\u0437\u043e\u0439 (mempalace mine)? (Y/n): ")
        if do_mine.lower() != 'n':
            print("\n\u23f3 \u0421\u0438\u043d\u0445\u0440\u043e\u043d\u0438\u0437\u0430\u0446\u0438\u044f...")
            result = subprocess.run(
                [sys.executable, "-m", "mempalace", "mine", "my_notes"],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                cwd=MEMPALACE_DIR,
            )
            if result.returncode == 0:
                out = result.stdout.strip()
                print(f"  \u2705 {out or '\u0413\u043e\u0442\u043e\u0432\u043e'}")
            else:
                err = result.stderr.strip()
                print(f"  \u26a0\ufe0f {err or '\u041e\u0448\u0438\u0431\u043a\u0430'}"  )

    print("\n\u2705 \u0413\u043e\u0442\u043e\u0432\u043e!")

if __name__ == "__main__":
    main()
