"""config.py
Централизованная конфигурация, пути, проверка доступа.
Жесткая привязка к вашей базе данных mempalace.

Порядок загрузки `.env`:
1. `.env` в корне проекта (приоритет);
2. legacy-файл `~/Documents/mempalace/.env`.

Уже заданные переменные окружения не перезаписываются.
"""

import functools
import os

from aiogram import types
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ENV_PATH = os.path.join(PROJECT_ROOT, ".env")

# Явный путь к вашей базе данных (автоматически подставляет имя пользователя)
DEFAULT_DATA_DIR = os.path.expanduser("~/Documents/mempalace")
LEGACY_ENV_PATH = os.path.join(DEFAULT_DATA_DIR, ".env")

# Корневой .env имеет приоритет над legacy: загружаем его первым,
# а load_dotenv(override=False) не перетирает уже заданные значения.
ENV_PATHS = (PROJECT_ENV_PATH, LEGACY_ENV_PATH)

TEST_TOKEN = "test-token"


def _load_env_files(paths: tuple[str, ...] | None = None) -> list[str]:
    """Загружает существующие .env-файлы, не перетирая окружение."""
    candidates = ENV_PATHS if paths is None else paths
    loaded: list[str] = []
    for path in candidates:
        if os.path.isfile(path):
            load_dotenv(dotenv_path=path, override=False)
            loaded.append(path)
    if not loaded:
        expected = " или ".join(candidates)
        print(
            f"⚠️ .env не найден. Ожидались: {expected}. "
            "Используются переменные окружения системы.",
        )
    return loaded


_load_env_files()


def _is_test_environment() -> bool:
    if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("PYTEST_VERSION"):
        return True
    flag = (os.getenv("MEMPALACE_ALLOW_TEST_TOKEN") or "").strip().lower()
    return flag in ("1", "true", "yes", "on")


def _resolve_api_token(
    raw_token: str | None,
    *,
    test_environment: bool | None = None,
) -> str:
    token = (raw_token or "").strip()
    if token:
        return token
    if test_environment is None:
        test_environment = _is_test_environment()
    return TEST_TOKEN if test_environment else ""


def validate_config() -> None:
    """Проверяет обязательные настройки перед запуском бота."""
    token = (API_TOKEN or "").strip()
    token_location = (
        f"Укажите TELEGRAM_BOT_TOKEN в {PROJECT_ENV_PATH} "
        f"или в legacy-файле {LEGACY_ENV_PATH}, либо задайте "
        "переменную окружения TELEGRAM_BOT_TOKEN."
    )
    if not token:
        raise RuntimeError(f"TELEGRAM_BOT_TOKEN не задан. {token_location}")
    if token == "your_telegram_bot_token":
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN содержит пример значения "
            f"'your_telegram_bot_token'. {token_location}",
        )
    if token == TEST_TOKEN and not _is_test_environment():
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN содержит тестовый fallback 'test-token'. "
            f"{token_location}",
        )
    if ADMIN_ID == 0:
        raise RuntimeError(
            "ADMIN_ID не задан или равен 0. Укажите ADMIN_ID в "
            f"{PROJECT_ENV_PATH} или {LEGACY_ENV_PATH}.",
        )


# 🔑 Доступ
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
ALLOWED_USERS = [
    int(uid.strip()) for uid in os.getenv("ALLOWED_USERS", "").split(",") if uid.strip()
]
ALLOWED_IDS = {ADMIN_ID} | set(ALLOWED_USERS)

# 🤖 Telegram Bot Token: fallback допустим только в тестовом окружении.
API_TOKEN = _resolve_api_token(os.getenv("TELEGRAM_BOT_TOKEN"))
if not API_TOKEN:
    print(
        "⚠️ TELEGRAM_BOT_TOKEN не задан. Бот не сможет запуститься; "
        f"проверьте {PROJECT_ENV_PATH} или {LEGACY_ENV_PATH}.",
    )
elif API_TOKEN == TEST_TOKEN and not (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip():
    print("⚠️ TELEGRAM_BOT_TOKEN не найден, для тестов используется fallback test-token")

# 🔍 Search API Keys
GOOGLE_CSE_API_KEY = os.getenv("GOOGLE_CSE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
BING_SEARCH_API_KEY = os.getenv("BING_SEARCH_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# 📂 Пути к данным (с защитой от битых .env строк)
raw_dir = os.getenv("MEMPALACE_DATA_DIR", "~/Documents/mempalace")

# 🧹 Авто-очистка: если переменная считалась как "KEY=VALUE", берем только VALUE
if "=" in raw_dir:
    raw_dir = raw_dir.split("=", 1)[1]

DATA_DIR = os.path.expanduser(raw_dir.strip())

# 🔒 Privacy: auto-attach photos to AI context (default: False)
AUTO_ATTACH_PHOTOS = os.getenv("AUTO_ATTACH_PHOTOS", "false").lower() in ("1", "true", "yes", "on")

CHATS_DIR = os.path.join(DATA_DIR, "chats")
NOTES_DIR = os.path.join(DATA_DIR, "my_notes")
INSIGHTS_DIR = os.path.join(DATA_DIR, "insights")
RESEARCH_DIR = os.path.join(DATA_DIR, "research")
PDF_ARCHIVE_DIR = os.path.join(DATA_DIR, "pdf_archive")
VOICE_OUTPUT_DIR = os.path.join(DATA_DIR, "voice_replies")
TEMP_DIR = os.path.join(DATA_DIR, "temp_media")
CONFIG_AI_FILE = os.path.join(DATA_DIR, ".current_ai")
MODELS_CONFIG_PATH = os.path.join(DATA_DIR, "models.json")
VOICE_REPLY_CONFIG = os.path.join(DATA_DIR, ".voice_reply_users.json")
PROMPTS_FILE = os.path.join(DATA_DIR, "pdf_prompts.json")
TRANSKRIPT_DIR = os.path.join(DATA_DIR, "transkript")
PHOTOS_DIR = os.path.join(DATA_DIR, "photos")

# 🛠️ Создание папок при старте
for d in [
    CHATS_DIR,
    NOTES_DIR,
    INSIGHTS_DIR,
    RESEARCH_DIR,
    PDF_ARCHIVE_DIR,
    VOICE_OUTPUT_DIR,
    TEMP_DIR,
    PHOTOS_DIR,
    TRANSKRIPT_DIR,
]:
    os.makedirs(d, exist_ok=True)


# 🛡️ Декораторы доступа
def allowed_only(func):
    @functools.wraps(func)
    async def wrapper(message: types.Message, *args, **kwargs):
        if message.from_user.id not in ALLOWED_IDS:
            return None
        return await func(message, *args, **kwargs)

    return wrapper


def allowed_callback(func):
    @functools.wraps(func)
    async def wrapper(callback: types.CallbackQuery, *args, **kwargs):
        if callback.from_user.id not in ALLOWED_IDS:
            await callback.answer("❌ Нет доступа", show_alert=True)
            return None
        return await func(callback, *args, **kwargs)

    return wrapper
