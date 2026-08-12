"""services/apple_notes.py — чтение и запись Apple Notes через JXA (osascript).

JXA-скрипты выполняются в дочернем процессе osascript. Для работы нужен доступ
к приложению Notes (TCC): macOS запросит разрешение при первом вызове.

Индекс заметок (id/name/folder/updated) кэшируется в
DATA_DIR/notes_index.json. TTL по умолчанию 1 час; чтение тела заметки —
всегда живой вызов (тела в индекс не кладутся).

Запись: create_note/update_note/delete_note/move_note — живые вызовы;
после каждого успешного изменения индекс инвалидируется (invalidate_index),
чтобы следующий list_notes не отдавал устаревшие данные. Удаление — штатное
поведение Notes.app: заметка перемещается в «Recently Deleted» (восстановима
30 дней), а не удаляется безвозвратно. Текст перед записью проходит языковую
валидацию detect_and_validate_language (запрет азиатских скриптов).
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
OSASCRIPT_LIST_TIMEOUT = 120.0  # листинг с превью тел — тяжелее
PREVIEW_MAX_CHARS = 1500
SNIPPET_MAX_CHARS = 120

_JXA_LIST_NOTES = """
const app = Application("Notes");
const out = [];
for (const f of app.folders()) {
  try {
    if (String(f.name()) === "Recently Deleted") continue;
    const names = f.notes.name();
    const ids = f.notes.id();
    const texts = f.notes.plaintext();
    const updated = f.notes.modificationDate();
    const fname = String(f.name());
    for (let i = 0; i < names.length; i++) {
      out.push({
        id: String(ids[i]),
        name: String(names[i]),
        folder: fname,
        preview: String(texts[i] || ""),
        updated: updated[i] ? String(updated[i]) : ""
      });
    }
  } catch (e) {
    out.push({error: String(e)});
  }
}
JSON.stringify(out);
"""

_JXA_LIST_NOTES_BASIC = """
const app = Application("Notes");
const out = [];
for (const f of app.folders()) {
  try {
    if (String(f.name()) === "Recently Deleted") continue;
    const names = f.notes.name();
    const ids = f.notes.id();
    const updated = f.notes.modificationDate();
    const fname = String(f.name());
    for (let i = 0; i < names.length; i++) {
      out.push({
        id: String(ids[i]),
        name: String(names[i]),
        folder: fname,
        preview: "",
        updated: updated[i] ? String(updated[i]) : ""
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

_JXA_CREATE_NOTE = """
const app = Application("Notes");
try {
  const target = {target};
  const props = {name: {title}, body: {body}};
  const note = target ? app.make({new: "note", at: target, withProperties: props})
                      : app.make({new: "note", withProperties: props});
  JSON.stringify({id: String(note.id()), name: String(note.name())});
} catch (e) {
  JSON.stringify({error: String(e)});
}
"""

_JXA_UPDATE_NOTE = """
const app = Application("Notes");
try {
  const n = app.notes.byId("{note_id}");
  n.body = {body};
  JSON.stringify({id: String(n.id()), name: String(n.name())});
} catch (e) {
  JSON.stringify({error: String(e)});
}
"""

_JXA_DELETE_NOTE = """
const app = Application("Notes");
try {
  const n = app.notes.byId("{note_id}");
  n.move({to: app.folders.byName("Recently Deleted")});
  JSON.stringify({id: String(n.id()), deleted: true});
} catch (e) {
  JSON.stringify({error: String(e)});
}
"""

_JXA_LIST_FOLDERS = """
const app = Application("Notes");
const out = [];
for (const f of app.folders()) {
  const name = String(f.name());
  if (name === "Recently Deleted") continue;
  out.push(name);
}
JSON.stringify(out);
"""

_AS_MOVE_NOTE = """
set nid to "{note_id}"
set fname to "{folder}"
tell application "Notes"
  set n to note id nid
  move n to folder fname
  return "{\\"id\\":\\"" & nid & "\\", \\"folder\\":\\"" & fname & "\\"}"
end tell
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


def run_applescript(script: str, timeout: float = OSASCRIPT_TIMEOUT) -> str:
    """Выполняет AppleScript-скрипт через osascript и возвращает stdout.

    JXA-перемещение заметок (app.make/move с объектами) падает с
    «Typen können nicht konvertiert werden» на ряде машин — для move_note
    используется AppleScript (тот же подход, что в apple_calendar).
    """
    try:
        proc = subprocess.run(  # nosec — osascript фиксированный, без shell
            ["osascript", "-e", script],
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
    if proc.returncode != 0 or _looks_like_error(stdout, stderr):
        detail = stderr or stdout or "без вывода"
        if "not authorized" in (stderr + stdout).lower():
            raise AppleNotesError(
                "Нет доступа к Apple Notes (TCC). Разрешите доступ в "
                "«Системные настройки → Конфиденциальность → Автоматизация».",
            )
        raise AppleNotesError(f"osascript не выполнился: {detail}")
    return stdout


def _parse_json_out(stdout: str) -> Any:
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise AppleNotesError(f"Неожиданный ответ osascript: {stdout[:200]}") from exc


def _fetch_note_list() -> list[dict]:
    """Живой запрос списка заметок у Apple Notes (без кэша).

    Тяжёлое чтение превью тел (bulk plaintext) идёт первым вызовом с
    увеличенным таймаутом; если оно падает — повторяем без превью,
    чтобы поиск по названиям продолжал работать.
    """
    try:
        data = _parse_json_out(
            run_osascript(_JXA_LIST_NOTES, timeout=OSASCRIPT_LIST_TIMEOUT),
        )
    except AppleNotesError:
        data = _parse_json_out(run_osascript(_JXA_LIST_NOTES_BASIC))
        logger.warning("[NOTES] previews skipped — index without bodies")
    if not isinstance(data, list):
        raise AppleNotesError(f"Неожиданный формат ответа Notes: {data!r}")
    for item in data:
        if isinstance(item, dict) and "error" in item:
            raise AppleNotesError(f"Apple Notes вернул ошибку: {item['error']}")
    notes = []
    for item in data:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        preview = (item.get("preview") or "").strip()
        notes.append({
            "id": item["id"],
            "name": item.get("name", ""),
            "folder": item.get("folder", ""),
            "preview": preview[:PREVIEW_MAX_CHARS],
            "updated": item.get("updated", ""),
        })
    return notes


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


def list_notes(
    folder: str | None = None,
    force_refresh: bool = False,
    sort_by_updated: bool = False,
    limit: int | None = None,
) -> list[dict]:
    """Список заметок из индекса.

    sort_by_updated=True — сортировка по дате изменения (свежие первыми,
    заметки без даты — в конец). limit — ограничить количество.
    """
    notes = list_notes_all(folder=folder, force_refresh=force_refresh)
    if sort_by_updated:
        notes = sorted(
            notes,
            key=lambda n: n.get("updated") or "",
            reverse=True,
        )
    if limit is not None:
        notes = notes[:limit]
    return notes


def list_notes_all(
    folder: str | None = None,
    force_refresh: bool = False,
) -> list[dict]:
    """Полный список заметок из индекса (без сортировки и лимита)."""
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


# ─── Валидация языка (запрет азиатских скриптов) ───

# Диапазоны Unicode азиатских скриптов, запрещённых для записи
_CJK_RANGES = (
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs (китайский/японские кандзи)
    (0x3040, 0x30FF),  # Hiragana + Katakana (японский)
    (0xAC00, 0xD7A3),  # Hangul (корейский)
)
_DE_MARKS = set("äöüßÄÖÜ")


def detect_and_validate_language(text: str) -> str:
    """Определяет язык заметки: "ru" или "de"; CJK-символы запрещены.

    Явный запрет на китайский/японский/корейский скрипты: при обнаружении
    любого символа из _CJK_RANGES бросает AppleNotesError с понятным
    сообщением. Язык определяется эвристикой: немецкие диакритики äöüß → de,
    иначе — ru (основной язык пользователя).
    """
    if not isinstance(text, str):
        raise AppleNotesError("Текст заметки должен быть строкой.")
    for ch in text:
        code = ord(ch)
        for low, high in _CJK_RANGES:
            if low <= code <= high:
                raise AppleNotesError(
                    "Заметка содержит азиатские символы (китайский/японский/"
                    "корейский) — создание и обновление таких заметок запрещено.",
                )
    return "de" if any(ch in _DE_MARKS for ch in text) else "ru"


# ─── Запись: create / update / delete / move ───


def _js_literal(text: str) -> str:
    """Безопасный JS-строковый литерал для вставки в JXA-скрипт.

    json.dumps экранирует кавычки, бэкслеши, переводы строк и спецсимволы —
    значение становится валидным литералом двойных кавычек JavaScript.
    """
    return json.dumps(text, ensure_ascii=False)


def _as_literal(text: str) -> str:
    """Экранирует строку для вставки в AppleScript-литерал двойных кавычек.

    AppleScript экранирует кавычки удвоением («""»), бэкслеши — без спец-
    обработки в строках; переносы строк внутри имён папок недопустимы.
    """
    return str(text).replace('"', '""')


def _safe_note_id(note_id: str) -> str:
    return note_id.replace("\\", "").replace('"', "")


def _unwrap_note_result(data: Any, action: str) -> dict:
    """Разбирает ответ write-скрипта: dict или AppleNotesError."""
    if not isinstance(data, dict):
        raise AppleNotesError(f"Неожиданный формат ответа Notes: {data!r}")
    if "error" in data:
        raise AppleNotesError(f"Не удалось {action}: {data['error']}")
    return data


def create_note(title: str, body: str = "", folder: str | None = None) -> str:
    """Создаёт заметку в указанной папке (по умолчанию — все заметки).

    Возвращает id созданной заметки. После успеха — invalidate_index(),
    чтобы следующий list_notes не отдавал стейл-данные.
    """
    if not isinstance(title, str) or not title.strip():
        raise AppleNotesError("Укажите заголовок заметки.")
    detect_and_validate_language(f"{title}\n{body}")
    if folder is None:
        target = "null"
    else:
        folder = folder.strip()
        if not folder:
            raise AppleNotesError("Укажите имя папки.")
        target = f"app.folders.byName({_js_literal(folder)})"
    script = _JXA_CREATE_NOTE.replace("{target}", target)
    script = script.replace("{title}", _js_literal(title.strip()))
    script = script.replace("{body}", _js_literal(body))
    data = _unwrap_note_result(_parse_json_out(run_osascript(script)), "создать заметку")
    invalidate_index()
    return data["id"]


def update_note(
    note_id: str,
    append_text: str | None = None,
    replace_text: str | None = None,
) -> dict:
    """Обновляет заметку: дозапись в конец (append_text) или полная замена.

    Возвращает {id, name, body}. Текст нового тела проходит языковую
    валидацию. После успеха — invalidate_index().
    """
    if not note_id or not isinstance(note_id, str):
        raise AppleNotesError("Укажите корректный ID заметки.")
    if append_text is not None and replace_text is not None:
        raise AppleNotesError(
            "Укажите только один режим обновления: append_text или replace_text.",
        )
    if append_text is None and replace_text is None:
        raise AppleNotesError(
            "Укажите текст для дозаписи (append_text) или замены (replace_text).",
        )
    if append_text is not None:
        if not isinstance(append_text, str) or not append_text.strip():
            raise AppleNotesError("Дозаписываемый текст не должен быть пустым.")
        detect_and_validate_language(append_text)
        current = read_note(note_id)
        new_body = (current.get("body") or "").rstrip("\n") + "\n" + append_text
    else:
        if not isinstance(replace_text, str) or not replace_text.strip():
            raise AppleNotesError("Заменяющий текст не должен быть пустым.")
        detect_and_validate_language(replace_text)
        new_body = replace_text
    script = _JXA_UPDATE_NOTE.replace("{note_id}", _safe_note_id(note_id))
    script = script.replace("{body}", _js_literal(new_body))
    data = _unwrap_note_result(_parse_json_out(run_osascript(script)), "обновить заметку")
    invalidate_index()
    return {
        "id": data.get("id", note_id),
        "name": data.get("name", ""),
        "body": new_body,
    }


def delete_note(note_id: str) -> bool:
    """Удаляет заметку: перемещает в «Recently Deleted» (восстановима 30 дней).

    Возвращает True при успехе. После успеха — invalidate_index().
    """
    if not note_id or not isinstance(note_id, str):
        raise AppleNotesError("Укажите корректный ID заметки.")
    script = _JXA_DELETE_NOTE.replace("{note_id}", _safe_note_id(note_id))
    data = _unwrap_note_result(_parse_json_out(run_osascript(script)), "удалить заметку")
    invalidate_index()
    return bool(data.get("deleted"))


def list_folders() -> list[str]:
    """Список имён папок Notes (без «Recently Deleted»)."""
    data = _parse_json_out(run_osascript(_JXA_LIST_FOLDERS))
    if not isinstance(data, list):
        raise AppleNotesError(f"Неожиданный формат ответа Notes: {data!r}")
    return [str(item) for item in data if isinstance(item, str) and item]


def move_note(note_id: str, target_folder: str) -> dict:
    """Перемещает заметку в другую папку. Возвращает {id, folder}."""
    if not note_id or not isinstance(note_id, str):
        raise AppleNotesError("Укажите корректный ID заметки.")
    if not isinstance(target_folder, str) or not target_folder.strip():
        raise AppleNotesError("Укажите папку назначения.")
    folder = target_folder.strip()
    if folder == "Recently Deleted":
        raise AppleNotesError(
            "Перемещение в «Recently Deleted» запрещено — используйте удаление заметки.",
        )
    script = _AS_MOVE_NOTE.replace("{note_id}", _safe_note_id(note_id))
    script = script.replace("{folder}", _as_literal(folder))
    data = _unwrap_note_result(_parse_json_out(run_applescript(script)), "переместить заметку")
    invalidate_index()
    return {"id": data.get("id", note_id), "folder": data.get("folder", folder)}


def _make_snippet(note: dict, words: list[str]) -> str:
    """Фрагмент текста вокруг первого совпадения (~SNIPPET_MAX_CHARS)."""
    preview = note.get("preview") or ""
    if not preview or not words:
        return ""
    low = preview.lower()
    pos = min((low.find(w) for w in words if low.find(w) >= 0), default=-1)
    if pos < 0:
        return preview[:SNIPPET_MAX_CHARS]
    start = max(0, pos - SNIPPET_MAX_CHARS // 3)
    end = min(len(preview), start + SNIPPET_MAX_CHARS)
    snippet = preview[start:end].strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(preview):
        snippet = snippet + "…"
    return snippet


def search_notes(query: str, limit: int = 10, force_refresh: bool = False) -> list[dict]:
    """Поиск по индексу (name/folder/preview, без учёта регистра).

    Совпадение слов ищется в названии, папке и тексте заметки. Результаты
    ранжируются: слово в названии важнее, чем в тексте; заметки с большим
    числом совпавших слов — выше. Каждая запись дополняется snippet —
    фрагментом текста вокруг первого совпадения. limit — максимум результатов.
    """
    if limit < 1:
        raise AppleNotesError("limit должен быть ≥ 1.")
    words = [w.lower() for w in re.split(r"\s+", query.strip()) if w]
    if not words:
        raise AppleNotesError("Пустой поисковый запрос.")
    notes = list_notes(force_refresh=force_refresh)
    scored = []
    for note in notes:
        name = (note.get("name", "") or "").lower()
        folder = (note.get("folder", "") or "").lower()
        preview = (note.get("preview") or "").lower()
        name_hits = sum(1 for w in words if w in name)
        folder_hits = sum(1 for w in words if w in folder)
        preview_hits = sum(1 for w in words if w in preview)
        score = 3 * name_hits + 1 * folder_hits + 1 * preview_hits
        if score > 0:
            scored.append((score, note))
    scored.sort(key=lambda item: item[0], reverse=True)
    found = []
    for score, note in scored:
        result = dict(note)
        result["snippet"] = _make_snippet(note, words)
        result["_score"] = score
        found.append(result)
        if len(found) >= limit:
            break
    return found
