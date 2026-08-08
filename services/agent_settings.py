"""services/agent_settings.py — per-user настройки агентного режима.

Хранилище: DATA_DIR/agent_settings.json (атомарная запись через tempfile+rename).
По умолчанию агентный режим ВЫКЛЮЧЕН (agent_enabled=False) — включается в /settings.
Кнопка запуска агента для отдельной задачи доступна ВСЕГДА, независимо от флага.
"""

import json
import logging
import os
import tempfile

from config import DATA_DIR

logger = logging.getLogger("AgentSettings")

AGENT_SETTINGS_FILE = os.path.join(DATA_DIR, "agent_settings.json")
DEFAULT_AGENT_ENABLED = False


def _load_settings() -> dict:
    """Загружает файл настроек; при повреждении — пустой словарь."""
    if not os.path.exists(AGENT_SETTINGS_FILE):
        return {}
    try:
        with open(AGENT_SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("[AGENT] settings load failed: %s", e)
        return {}


def get_agent_enabled(user_id: int) -> bool:
    """True, если агентный режим включён для пользователя (по умолчанию OFF)."""
    settings = _load_settings()
    value = settings.get(str(user_id), {}).get("enabled")
    if not isinstance(value, bool):
        return DEFAULT_AGENT_ENABLED
    return value


def set_agent_enabled(user_id: int, enabled: bool) -> None:
    """Включает/выключает агентный режим для пользователя (атомарно)."""
    if not isinstance(enabled, bool):
        raise TypeError(f"enabled должен быть bool, получено: {type(enabled).__name__}")
    settings = _load_settings()
    user_cfg = settings.setdefault(str(user_id), {})
    user_cfg["enabled"] = enabled
    tmp_dir = os.path.dirname(AGENT_SETTINGS_FILE) or "."
    os.makedirs(tmp_dir, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=tmp_dir, encoding="utf-8") as tmp:
        json.dump(settings, tmp, indent=2, ensure_ascii=False)
        tmp_path = tmp.name
    os.replace(tmp_path, AGENT_SETTINGS_FILE)


def toggle_agent_enabled(user_id: int) -> bool:
    """Переключает флаг и возвращает новое значение."""
    new_value = not get_agent_enabled(user_id)
    set_agent_enabled(user_id, new_value)
    return new_value
