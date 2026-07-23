"""
config.py
Централизованная конфигурация, пути, проверка доступа.
Жесткая привязка к вашей базе данных mempalace.
"""
import os
import functools
from dotenv import load_dotenv
from aiogram import types

# Явный путь к вашей базе данных (автоматически подставляет имя пользователя)
DEFAULT_DATA_DIR = os.path.expanduser("~/Documents/mempalace")
dotenv_path = os.path.join(DEFAULT_DATA_DIR, ".env")

if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
else:
    print(f"⚠️ .env не найден в {DEFAULT_DATA_DIR}. Используются переменные окружения системы.")

# 🔑 Доступ
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
ALLOWED_USERS = [int(uid.strip()) for uid in os.getenv("ALLOWED_USERS", "").split(",") if uid.strip()]
ALLOWED_IDS = {ADMIN_ID} | set(ALLOWED_USERS)

# 🤖 Telegram Bot Token
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not API_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден в .env файле!")

# 📂 Пути к данным (с защитой от битых .env строк)
raw_dir = os.getenv("MEMPALACE_DATA_DIR", "~/Documents/mempalace")

# 🧹 Авто-очистка: если переменная считалась как "KEY=VALUE", берем только VALUE
if "=" in raw_dir:
    raw_dir = raw_dir.split("=", 1)[1]

DATA_DIR = os.path.expanduser(raw_dir.strip())

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
PHOTOS_DIR = os.path.join(DATA_DIR, "photos")
TRANSKRIPT_DIR = os.path.join(DATA_DIR, "transkript")

# 🛠️ Создание папок при старте
for d in [CHATS_DIR, NOTES_DIR, INSIGHTS_DIR, RESEARCH_DIR, 
          PDF_ARCHIVE_DIR, VOICE_OUTPUT_DIR, TEMP_DIR, PHOTOS_DIR,
          TRANSKRIPT_DIR]:
    os.makedirs(d, exist_ok=True)

# 🛡️ Декораторы доступа
def allowed_only(func):
    @functools.wraps(func)
    async def wrapper(message: types.Message, *args, **kwargs):
        if message.from_user.id not in ALLOWED_IDS:
            return
        return await func(message, *args, **kwargs)
    return wrapper

def allowed_callback(func):
    @functools.wraps(func)
    async def wrapper(callback: types.CallbackQuery, *args, **kwargs):
        if callback.from_user.id not in ALLOWED_IDS:
            await callback.answer("❌ Нет доступа", show_alert=True)
            return
        return await func(callback, *args, **kwargs)
    return wrapper


# 📸 Папка для общих фотографий (CLI + Bot)
PHOTOS_DIR = os.path.join(DATA_DIR, "photos")
os.makedirs(PHOTOS_DIR, exist_ok=True)

# 🔒 Строгий кэш разрешенных ID (без fallback на 0)
def get_allowed_ids():
    admin = int(os.getenv("ADMIN_ID", "0"))
    users_str = os.getenv("ALLOWED_USERS", "")
    allowed = {uid.strip() for uid in users_str.split(",") if uid.strip()}
    allowed.add(str(admin))
    return {int(uid) for uid in allowed if uid.isdigit()}

ALLOWED_IDS = get_allowed_ids()