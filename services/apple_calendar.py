"""services/apple_calendar.py — работа с Apple Calendar через osascript.

Создание события — AppleScript (стабильно при программной записи).
Список ближайших событий — AppleScript-перебор; на некоторых машинах
чтение календаря может временно блокироваться, пока в календаре есть
свежие программно созданные события (переиндексация EventKit) —
в этом случае поднимается AppleCalendarError с понятным сообщением.

TCC/таймаут/синтаксис osascript → AppleCalendarError.
"""

import logging
import subprocess
from datetime import datetime, timedelta

logger = logging.getLogger("AppleCalendar")

OSASCRIPT_TIMEOUT = 20.0
OSASCRIPT_LIST_TIMEOUT = 45.0
DEFAULT_DURATION_MINUTES = 15
DEFAULT_LIST_DAYS = 7

_ERROR_MARKERS = ("TCC", "not authorized", "unable to access", "not allowed",
                  "application isn't running", "can't get", "command not found")


class AppleCalendarError(Exception):
    """Ошибка работы с Apple Calendar (TCC, таймаут, osascript)."""


def _looks_like_error(combined: str) -> bool:
    lower = combined.lower()
    return any(marker.lower() in lower for marker in _ERROR_MARKERS)


def _run_applescript(script: str, timeout: float = OSASCRIPT_TIMEOUT) -> str:
    """Запускает osascript в режиме AppleScript."""
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise AppleCalendarError("osascript не найден на этой системе.") from exc
    except subprocess.TimeoutExpired as exc:
        raise AppleCalendarError(
            f"Apple Calendar не ответил за {timeout:g}с (возможно, синхронизация)."
        ) from exc
    combined = f"{proc.stdout}\n{proc.stderr}"
    if proc.returncode != 0 or _looks_like_error(combined):
        raise AppleCalendarError(
            f"Apple Calendar не выполнил команду: {proc.stderr[:200]}"
        )
    return proc.stdout.strip()


def _date_as(dt: datetime) -> str:
    """Форматирует дату для AppleScript (локальное время, dd.mm.yyyy HH:MM:SS)."""
    return dt.strftime("%d.%m.%Y %H:%M:%S")


def create_calendar_event(
    title: str,
    start_ts: float,
    duration_minutes: int = DEFAULT_DURATION_MINUTES,
    notes: str = "",
    calendar_index: int = 1,
) -> str:
    """Создаёт событие в первом (по умолчанию) календаре Apple Calendar.

    Возвращает id созданного события. Экранирует кавычки в title/notes.
    AppleScript собирается в одну строку (osascript -e падает на переносах
    внутри properties).
    """
    title_safe = (title or "").replace("\\", "").replace('"', '\\"')
    notes_safe = (notes or "").replace("\\", "").replace('"', '\\"')
    start_dt = datetime.fromtimestamp(start_ts)
    end_dt = start_dt + timedelta(minutes=max(1, int(duration_minutes)))
    props = (
        f'summary:"{title_safe}", '
        f'start date:date "{_date_as(start_dt)}", '
        f'end date:date "{_date_as(end_dt)}", '
        f'description:"{notes_safe}"'
    )
    script = (
        f'tell application "Calendar" to tell calendar {int(calendar_index)} to '
        f"set newEvent to make new event at end with properties {{{props}}}\n"
        f'tell application "Calendar" to tell calendar {int(calendar_index)} to '
        "return id of newEvent"
    )
    return _run_applescript(script)


_AS_LIST_EVENTS = """
tell application "Calendar"
  tell calendar {cal_index}
    set evs to (every event whose start date > (current date) and start date < ((current date) + {days} * days))  # noqa: E501
    set res to ""
    repeat with ev in evs
      try
        set res to res & (id of ev) & "|" & (summary of ev) & "|" & ((start date of ev) as string) & "|" & ((end date of ev) as string) & linefeed  # noqa: E501
      on error e
        set res to res & "ERR: " & e & linefeed
      end try
    end repeat
    return res
  end tell
end tell
"""


def list_upcoming_events(
    days: int = DEFAULT_LIST_DAYS,
    limit: int = 20,
    calendar_index: int = 1,
) -> list[dict]:
    """Список ближайших событий первого календаря (id/summary/start/end).

    Строки вида: id|summary|start date|end date — по одной на событие.
    """
    script = _AS_LIST_EVENTS.format(
        cal_index=int(calendar_index), days=max(1, int(days)),
    )
    raw = _run_applescript(script, timeout=OSASCRIPT_LIST_TIMEOUT)
    events: list[dict] = []
    for line in raw.splitlines():
        if not line.strip() or line.startswith("ERR:"):
            continue
        parts = line.split("|")
        if len(parts) < 4:
            continue
        ev_id, summary, start_raw, end_raw = parts[:4]
        start_dt = _parse_as_date(start_raw.strip())
        end_dt = _parse_as_date(end_raw.strip())
        events.append({
            "id": ev_id.strip(),
            "summary": summary.strip(),
            "start": start_dt.isoformat() if start_dt else "",
            "end": end_dt.isoformat() if end_dt else "",
        })
    events.sort(key=lambda e: e["start"])
    return events[: max(1, int(limit))]


def _parse_as_date(raw: str) -> datetime | None:
    """Парсит дату AppleScript (локальное время: dd.mm.yyyy HH:MM:SS)."""
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw.strip(), fmt)
        except ValueError:
            continue
    return None
