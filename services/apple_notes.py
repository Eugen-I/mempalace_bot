"""services/apple_notes.py — чтение Apple Notes через JXA (osascript) + кэш-индекс.

JXA-скрипты выполняются в дочернем процессе osascript. Для работы нужен доступ
к приложению Notes (TCC): macOS запросит разрешение при первом вызове.

Индекс заметок (id/name/folder/updated) кэшируется в
DATA_DIR/notes_index.json. TTL по умолчанию 1 час; чтение тела заметки —
всегда живой вызов (тела в индекс не кладутся).
"""

import json
import logging
import os
import re
import subprocess
import tempfile
import time
from typing import Any

from config import DATA_DIR

logger = logging.getLogger("AppleNotes")

INDEX_FILE = os.path.join(DATA_DIR, "notes_index.json")
INDEX_TTL_SECONDS = 3600
OSASCRIPT_TIMEOUT = 30.0

_JXA_LIST_NOTES = """
const app = Application("Notes");
const out = [];
for (const f of app.folders()) {
  try {
    if (String(f.name()) === "Recently Deleted") continue;
    const names = f.notes.name();
    const ids = f.notes.id();
    const fname = String(f.name());
    for (let i = 0; i < names.length; i++) {
      out.push({
        id: String(ids[i]),
        name: String(names[i]),
        folder: fname,
        updated: ""
      });
    }
  } catch (e) {
    out.push({error: String(e)});
  }
}
JSON.stringify(out);
"""

_JXA_READ_NOTE = """
const app = Application("Notes");
try {
  const n = app.notes.byId("{note_id}");
  JSON.stringify({name: String(n.name()), body: String(n.plaintext())});
} catch (e) {
  JSON.stringify({error: String(e)});
}
"""


class AppleNotesError(Exception):
    """Ошибка доступа к Apple Notes (TCC, osascript, таймаут)."""


def run_osascript(jxa_script: str, timeout: float = OSASCRIPT_TIMEOUT) -> str:
    """Выполняет JXA-скрипт через osascript и возвращает stdout."""
    try:
        proc = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", jxa_script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise AppleNotesError("osascript превысил таймаут — Notes не отвечает.") from exc
    except OSError as exc:
        raise AppleNotesError(f"Не удалось запустить osascript: {exc}") from exc
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0 or not stdout or _looks_like_error(stdout, stderr):
        detail = stderr or stdout or "без вывода"
        if "not authorized" in (stderr + stdout).lower():
            raise AppleNotesError(
                "Нет доступа к Apple Notes (TCC). Разрешите доступ в "
                "«Системные настройки → Конфиденциальность → Автоматизация».",
            )
        raise AppleNotesError(f"osascript не выполнился: {detail}")
    return stdout


def _looks_like_error(stdout: str, stderr: str) -> bool:
    combined = (stdout + " " + stderr).lower()
    for marker in ("execution error", "osascript error", "not authorized",
                   "application isn't running", "can't get"):
        if marker in combined:
            return True
    return False


def _parse_json_out(stdout: str) -> Any:
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise AppleNotesError(f"Неожиданный ответ osascript: {stdout[:200]}") from exc


def _fetch_note_list() -> list[dict]:
    """Живой запрос списка заметок у Apple Notes (без кэша)."""
    data = _parse_json_out(run_osascript(_JXA_LIST_NOTES))
    if not isinstance(data, list):
        raise AppleNotesError(f"Неожиданный формат ответа Notes: {data!r}")
    for item in data:
        if isinstance(item, dict) and "error" in item:
            raise AppleNotesError(f"Apple Notes вернул ошибку: {item['error']}")
    return [item for item in data if isinstance(item, dict) and item.get("id")]


# ─── Кэш-индекс ───


def _write_index(payload: dict) -> None:
    """Атомарная запись индекса (tempfile + os.replace)."""
    os.makedirs(os.path.dirname(INDEX_FILE), exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", delete=False, dir=os.path.dirname(INDEX_FILE),
        encoding="utf-8",
    ) as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2)
        tmp_path = tmp.name
    os.replace(tmp_path, INDEX_FILE)


def is_index_stale(ttl: int = INDEX_TTL_SECONDS) -> bool:
    """True, если индекс отсутствует, пуст или старше ttl секунд."""
    if not os.path.exists(INDEX_FILE):
        return True
    try:
        age = time.time() - os.path.getmtime(INDEX_FILE)
    except OSError:
        return True
    if age > ttl:
        return True
    try:
        with open(INDEX_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return True
    return not isinstance(data, dict) or not data.get("notes")


def refresh_index() -> dict:
    """Обновляет индекс: живой запрос Notes → атомарная запись файла."""
    notes = _fetch_note_list()
    payload = {
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "notes": notes,
    }
    _write_index(payload)
    logger.info("[NOTES] index refreshed: %d notes", len(notes))
    return payload


def get_index(force_refresh: bool = False) -> dict:
    """Возвращает индекс (кэш); при устаревании/отсутствии — обновляет."""
    if force_refresh or is_index_stale():
        return refresh_index()
    with open(INDEX_FILE, encoding="utf-8") as f:
        return json.load(f)


def invalidate_index() -> bool:
    """Удаляет кэш-индекс. Возвращает True, если файл существовал."""
    if os.path.exists(INDEX_FILE):
        os.remove(INDEX_FILE)
        logger.info("[NOTES] index invalidated")
        return True
    return False


def list_notes(folder: str | None = None, force_refresh: bool = False) -> list[dict]:
    """Список заметок из индекса (необязательно фильтр по папке)."""
    index = get_index(force_refresh=force_refresh)
    notes = index.get("notes", [])
    if folder:
        notes = [n for n in notes if n.get("folder") == folder]
    return notes


def read_note(note_id: str) -> dict:
    """Читает тело заметки (живой вызов). Возвращает {name, body}."""
    if not note_id or not isinstance(note_id, str):
        raise AppleNotesError("Укажите корректный ID заметки.")
    safe_id = note_id.replace("\\", "").replace('"', "")
    data = _parse_json_out(run_osascript(_JXA_READ_NOTE.replace("{note_id}", safe_id)))
    if not isinstance(data, dict):
        raise AppleNotesError(f"Неожиданный формат ответа Notes: {data!r}")
    if "error" in data:
        raise AppleNotesError(f"Заметка не найдена или недоступна: {data['error']}")
    return data


def search_notes(query: str, limit: int = 10, force_refresh: bool = False) -> list[dict]:
    """Поиск по индексу (name/folder, без учёта регистра).

    Строгий подзапрос по всем словам запроса. limit — максимум результатов.
    """
    if limit < 1:
        raise AppleNotesError("limit должен быть ≥ 1.")
    words = [w.lower() for w in re.split(r"\s+", query.strip()) if w]
    if not words:
        raise AppleNotesError("Пустой поисковый запрос.")
    notes = list_notes(force_refresh=force_refresh)
    found = []
    for note in notes:
        haystack = f"{note.get('name', '')} {note.get('folder', '')}".lower()
        if all(w in haystack for w in words):
            found.append(note)
            if len(found) >= limit:
                break
    return found
