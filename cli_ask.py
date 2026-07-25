#!/usr/bin/env python3
"""cli_ask.py v2.8
✅ ФОРМАТИРОВАНИЕ ДЛЯ ТЕРМИНАЛА: Убраны спецсимволы Markdown, добавлена поддержка ANSI (жирный/курсив).
✅ НЕБЛОКИРУЮЩАЯ ОЗВУЧКА: say запускается в фоне.
✅ УДАЛЕНО: Устаревший раздел про Hunyuan-MT переводчик.
"""

import logging
import os
import re
import sys
import tempfile

# Скрываем INFO/WARNING от всех модулей, оставляем только ERROR
logging.basicConfig(level=logging.ERROR, format="%(levelname)s: %(message)s")
logger = logging.getLogger("CLI")
logger.setLevel(logging.INFO)  # Логи самого CLI (если нужны) останутся

# 📂 Базовые пути
BASE_DIR = os.path.expanduser("~/Documents/mempalace")
BOT_DIR = os.path.expanduser("~/Documents/mempalace_bot")
VENV_DIR = os.path.join(BASE_DIR, "venv")
VENV_PYTHON = os.path.join(VENV_DIR, "bin", "python3")

# 🔄 АВТО-АКТИВАЦИЯ VENV
if sys.executable != VENV_PYTHON and os.path.exists(VENV_PYTHON):
    os.environ["VIRTUAL_ENV"] = VENV_DIR
    os.environ["PATH"] = (
        os.path.join(VENV_DIR, "bin") + os.pathsep + os.environ.get("PATH", "")
    )
    os.execv(VENV_PYTHON, [VENV_PYTHON] + sys.argv)

sys.path.insert(0, BOT_DIR)
sys.path.insert(0, BASE_DIR)

import asyncio
import atexit
import json
import readline
import subprocess
from datetime import datetime

from rich.console import Console
from rich.syntax import Syntax

from services.code_mode import (
    ensure_project_dir,
    is_coding_context,
    load_coding_prompt,
    read_project_files,
)
from services.palace_bridge import (
    export_chat_verbatim,
    palace_compact,
    palace_compress,
    palace_mcp,
    palace_repair,
    palace_status,
    palace_wake_up,
    search_palace_context,
    search_with_kg,
    sync_to_palace,
)
from services.palace_mcp import get_mcp

console = Console()

# ⬆️⬇️ ИСТОРИЯ КОМАНД
HIST_FILE = os.path.join(os.path.expanduser("~"), ".mempalace_cli_history")
try:
    readline.read_history_file(HIST_FILE)
    readline.set_history_length(200)
except FileNotFoundError:
    pass
atexit.register(readline.write_history_file, HIST_FILE)

from config import (
    CHATS_DIR,
    CONFIG_AI_FILE,
    INSIGHTS_DIR,
    MODELS_CONFIG_PATH,
    NOTES_DIR,
    PHOTOS_DIR,
    RESEARCH_DIR,
    VOICE_REPLY_CONFIG,
)
from services.ai_engine import (
    get_ai_response_async,
    get_current_ai,
    invalidate_ai_cache,
)
from services.memory import extract_and_store_facts, get_memory_context


# 🎨 ЦВЕТОВАЯ РАЗМЕТКА И ФОРМАТИРОВАНИЕ
class C:
    WHITE = "\033[97m"
    GREEN = "\033[92m"
    L_GREEN = "\033[1;92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    PURPLE = "\033[95m"
    BOLD = "\033[1m"  # Жирный
    ITALIC = "\033[3m"  # Курсив (поддерживается не всеми терминалами, но стандартен)
    UNDERLINE = "\033[4m"  # Подчеркнутый
    END = "\033[0m"

    # Алиасы
    W = WHITE
    G = GREEN
    Y = YELLOW
    R = RED
    C = CYAN
    B = BOLD
    M = PURPLE
    E = END


def format_for_terminal(text: str) -> str:
    """Очищает текст от Markdown символов и заменяет их на ANSI коды для терминала.
    **bold** -> Жирный
    *italic* -> Курсив
    __underline__ -> Подчеркнутый (если используется такой синтаксис, но обычно в MD это bold)
    `code` -> Моноширинный (обычно просто убираем бэктики или делаем цветом)
    """
    if not text:
        return ""

    # 1. Заменяем Жирный (**text**)
    # Используем регулярку с non-greedy matching
    text = re.sub(r"\*\*(.+?)\*\*", f"{C.BOLD}\\1{C.END}", text)

    # 2. Заменяем Курсив (*text*)
    # Важно: делать после жирного, чтобы не задеть звездочки внутри жирного
    text = re.sub(r"\*(.+?)\*", f"{C.ITALIC}\\1{C.END}", text)

    # 3. Заменяем Код (`text`)
    # Можно сделать его другим цветом, например Cyan, или просто убрать бэктики
    text = re.sub(r"`(.+?)`", f"{C.CYAN}\\1{C.END}", text)

    # 4. Заголовки (# Header)
    # Делаем их жирными и возможно другого цвета
    text = re.sub(
        r"^#{1,3}\s+(.+)$", f"{C.BOLD}{C.YELLOW}\\1{C.END}", text, flags=re.MULTILINE,
    )

    # 5. Списки (- item или * item)
    # Просто оставляем как есть, или можно добавить отступ

    # 6. Ссылки [text](url) -> просто text (url часто шумит в терминале)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)

    return text


# 🔒 Безопасная НЕБЛОКИРУЮЩАЯ озвучка
def speak_text(
    text: str, speed: int = 160, voice: str = "Milena", enabled: bool = True,
) -> None:
    if not enabled or not text:
        return
    try:
        subprocess.Popen(
            ["say", "-v", voice, "-r", str(speed), text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        print(f"{C.RED}⚠️ Ошибка озвучки: {e}{C.END}")


# 💾 Работа с чатами
def load_chat(path: str) -> dict:
    if not os.path.exists(path):
        return {"summary": "", "messages": [], "summaries": []}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        data = {"summary": "", "messages": data, "summaries": []}
        save_chat(path, data)
    return data


# Находить блоки кода в ответе ИИ (или в вашем запросе, если вы вставили код туда).
# Сохранять их как .py файлы в папку проекта.
def save_code_from_text(
    text: str, project_dir: str, filename_hint: str = "script",
) -> list:
    """Ищет блоки кода в тексте и сохраняет их в папку проекта.
    Возвращает список сохраненных файлов.
    """
    if not project_dir or not os.path.exists(project_dir):
        return []

    saved_files = []
    # Регулярка для поиска блоков кода ```python ... ```
    pattern = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)
    matches = pattern.findall(text)

    for lang, code in matches:
        if not code.strip():
            continue

        # Определяем расширение
        ext = ".py"
        if lang:
            lang_lower = lang.lower().strip()
            if "json" in lang_lower:
                ext = ".json"
            elif "js" in lang_lower:
                ext = ".js"
            elif "cpp" in lang_lower:
                ext = ".cpp"
            elif "html" in lang_lower:
                ext = ".html"

        # Генерируем имя файла
        timestamp = datetime.now().strftime("%H%M%S")
        fname = f"{filename_hint}_{timestamp}{ext}"
        fpath = os.path.join(project_dir, fname)

        try:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(code.strip())
            saved_files.append(fname)
            print(f"{C.GREEN}💾 Код сохранен: {fname}{C.END}")
        except Exception as e:
            print(f"{C.RED}❌ Ошибка сохранения файла {fname}: {e}{C.END}")

    return saved_files


def save_chat(path: str, data: dict) -> None:
    try:
        dirpath = os.path.dirname(path)
        with tempfile.NamedTemporaryFile(
            "w", dir=dirpath, delete=False, encoding="utf-8",
        ) as tmp:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp_path = tmp.name
        os.replace(tmp_path, path)
    except Exception as e:
        print(f"❌ Ошибка сохранения чата {path}: {e}")


def list_chats() -> list[str]:
    if not os.path.exists(CHATS_DIR):
        return []
    return sorted(
        [f for f in os.listdir(CHATS_DIR) if f.endswith(".json")],
        key=lambda x: os.path.getmtime(os.path.join(CHATS_DIR, x)),
        reverse=True,
    )


# ⚙️ Голосовые настройки
def get_cli_voice() -> dict:
    cfg = {}
    if os.path.exists(VOICE_REPLY_CONFIG):
        with open(VOICE_REPLY_CONFIG) as f:
            cfg = json.load(f)
    return cfg.get("cli", {"enabled": True, "speed": 160, "voice": "Milena"})


def set_cli_voice(key: str, value) -> None:
    cfg = {}
    if os.path.exists(VOICE_REPLY_CONFIG):
        with open(VOICE_REPLY_CONFIG) as f:
            cfg = json.load(f)
    cfg.setdefault("cli", {"enabled": True, "speed": 160, "voice": "Milena"})[key] = (
        value
    )
    with open(VOICE_REPLY_CONFIG, "w") as f:
        json.dump(cfg, f, indent=2)


# 📜 Генерация саммари
async def generate_summary_if_needed(
    messages: list[dict], chat_data: dict, chat_path: str,
) -> str | None:
    conv_msgs = [m for m in messages if m.get("role") in ["user", "assistant"]]
    if len(conv_msgs) > 0 and len(conv_msgs) % 15 == 0:
        print(f"\n{C.CYAN}📝 Генерирую саммари последних 15 сообщений...{C.END}")
        engine, model = get_current_ai()
        dialog_slice = "\n".join(
            [f"{m['role']}: {m['content']}" for m in conv_msgs[-15:]],
        )
        prompt = f"Сделай краткое саммари последних 15 сообщений диалога. Сохрани ключевые выводы и контекст для продолжения:\n{dialog_slice}"
        try:
            summary = await get_ai_response_async(
                engine, model, [{"role": "user", "content": prompt}], context="",
            )
            messages.append({"role": "system", "type": "summary", "content": summary})
            chat_data["messages"] = messages
            chat_data.setdefault("summaries", []).append(summary)
            save_chat(chat_path, chat_data)
            print(f"{C.GREEN}✅ Саммари сохранено.{C.END}\n")
            return summary
        except Exception as e:
            print(f"{C.RED}❌ Ошибка саммари: {e}{C.END}")
    return None


# 📤 Экспорт в Markdown
def export_chat_to_md(chat_path: str) -> str:
    data = load_chat(chat_path)
    msgs = data.get("messages", [])
    export_dir = os.path.join(CHATS_DIR, "exports")
    os.makedirs(export_dir, exist_ok=True)
    base_name = os.path.basename(chat_path).replace(".json", "")
    md_path = os.path.join(export_dir, f"{base_name}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# 💬 Диалог: {base_name}\n")
        for m in msgs:
            role = m.get("role", "user")
            if role == "system" and m.get("type") == "summary":
                f.write(f"\n---\n### 📜 Саммари этапа\n{m['content']}\n---\n")
            elif role in ["user", "assistant"]:
                icon = "👤 Вы" if role == "user" else "🤖 ИИ"
                f.write(f"\n### {icon}\n{m['content']}\n")
    return md_path

    # 📖 Справка (Обновленная)


HELP_SECTIONS = {
    "1": {
        "title": "📝 Запись и библиотека",
        "items": [
            ("! текст", "Быстрая заметка в my_notes"),
            ("!!", "Сохранить последний ответ ИИ в Insights"),
            ("???", "Сохранить в Research"),
            ("/transkript", "Список транскриптов YouTube"),
            ("/transkript N", "Прочитать транскрипт по номеру"),
        ],
    },
    "2": {
        "title": "💬 Управление чатами",
        "items": [
            ("/history", "Показать историю текущего чата"),
            ("/export", "Экспорт чата в .md"),
            ("~ / #ctx", "Показать последнее саммари"),
            ("/new", "Новый чат"),
            ("/del", "Удалить текущий чат"),
            ("/chats", "Вернуться в меню чатов"),
        ],
    },
    "3": {
        "title": "🔍 Поиск и синхронизация",
        "items": [
            ("/search <запрос>", "Поиск по всей базе MemPalace"),
            ("/search --wing dreams ...", "Поиск по конкретному крылу"),
            ("sync", "Синхронизировать чат с MemPalace"),
            ("/photos", "Список фото"),
            ("/analyze_photo", "Анализ фото ИИ"),
        ],
    },
    "4": {
        "title": "🎬 Медиа (YouTube, PDF, напоминания)",
        "items": [
            ("/yt <url> [кач]", "Скачать видео с YouTube"),
            ("/ytaudio <url>", "Скачать аудио + транскрипция"),
            ("/pdfs [N]", "Список/просмотр PDF"),
            ("/remind <текст>", "Создать напоминание"),
        ],
    },
    "5": {
        "title": "🏰 Дворец знаний",
        "items": [
            ("/palace", "Список команд дворца"),
            ("/status", "Статистика MemPalace"),
            ("/wings", "Список крыльев"),
            ("/rooms [крыло]", "Комнаты крыла"),
            ("/taxonomy", "Полная таксономия"),
            ("/graph", "Статистика графа"),
            ("/traverse <комната> [шаги]", "Обход графа"),
            ("/tunnels", "Туннели между крыльями"),
            ("/follow <крыло> <комната>", "Пройти туннели из комнаты"),
            ("/kg <сущность>", "Поиск в графе знаний"),
            ("/kgadd суб пред об", "Добавить факт"),
            ("/kgstats", "Статистика KG"),
            ("/enrich", "Enrichment заметок → KG"),
            ("/mcp", "Инструкция MCP"),
            ("/wakeup", "Загрузить дворец в контекст"),
            ("/repair", "Перестроить индекс"),
            ("/compact", "Сжать БД"),
            ("/compress", "Сжать текст"),
        ],
    },
    "6": {
        "title": "⚙️ Системные",
        "items": [
            ("/settings", "Сменить модель ИИ"),
            ("Звук", "Вкл/Выкл озвучку"),
            ("Звук-150", "Скорость голоса (100-300)"),
            ("q / й / Ctrl+C", "Выход с сохранением"),
        ],
    },
}


def show_help():
    print(f"{C.CYAN}==========================================================")
    print(f"    🦾 MemPalace CLI | Справка")
    print(f"=========================================================={C.END}")
    for key, sec in HELP_SECTIONS.items():
        print(f"  {C.YELLOW}{key}. {sec['title']}{C.END}")
    print(f"\n  {C.PURPLE}0) {C.END}Вся справка разом")
    print(f"  {C.YELLOW}h) {C.END}Это меню")
    print(f"  {C.CYAN}=========================================================={C.END}")
    print(f"  Введите номер раздела для подробностей.")


def show_section(key: str):
    sec = HELP_SECTIONS.get(key)
    if not sec:
        return
    print(f"\n{C.YELLOW}--- {sec['title']} ---{C.END}")
    for cmd, desc in sec["items"]:
        print(f"  {C.GREEN}{cmd}{C.END}")
        print(f"    {desc}")


def show_all_help():
    for key in sorted(HELP_SECTIONS):
        show_section(key)
    print()


# 🧠 Ядро диалога
async def chat_loop(chat_path: str):
    data = load_chat(chat_path)
    messages = data.get("messages", [])
    voice_cfg = get_cli_voice()
    engine, model = get_current_ai()

    print(
        f"\n{C.CYAN}=========================================================={C.END}",
    )
    print(f"{C.CYAN}💬 Активен чат: {C.BOLD}{os.path.basename(chat_path)}{C.END}")
    print(
        f"{C.GREEN}🤖 Модель: {model} ({engine}) | 🎤 Голос: {'Вкл' if voice_cfg['enabled'] else 'Выкл'} ({voice_cfg['voice']}, {voice_cfg['speed']} wpm){C.END}",
    )
    print(f"{C.YELLOW}Введите h для справки. q или й для выхода.{C.END}")
    print(
        f"{C.CYAN}==========================================================\n{C.END}",
    )

    while True:
        try:
            user_input = input(f"{C.YELLOW}Вы: {C.END}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{C.RED}👋 Завершение...{C.END}")
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        # 🔍 ОБРАБОТКА КОМАНД ДЛЯ ФОТО (ДОЛЖНА БЫТЬ ПЕРВОЙ!)
        if cmd == "/photos":
            from services.multimodal import list_photos

            # print(f"{C.CYAN}[DEBUG] Проверяю папку: {PHOTOS_DIR}{C.END}")
            photos = list_photos()
            if not photos:
                print(f"{C.YELLOW}📁 Папка photos пуста.{C.END}")
            else:
                print(f"{C.CYAN}📸 Фото в базе ({len(photos)}):{C.END}")
                for i, p in enumerate(photos, 1):
                    print(f"  {i}) {p}")
            continue

        if cmd == "/analyze_photo":
            from services.multimodal import (
                check_capability,
                encode_image_to_base64,
                list_photos,
            )

            # 1. Проверка поддержки модели
            if not check_capability(model, "multimodal"):
                print(
                    f"{C.RED}⚠️ Модель {model} не поддерживает анализ фото. Переключитесь на Gemma 4.{C.END}",
                )
                continue

            # 2. Получение списка фото
            photos = list_photos()
            if not photos:
                print(f"{C.RED}❌ Нет фото для анализа. Папка: {PHOTOS_DIR}{C.END}")
                continue

            print(f"{C.CYAN}🔍 Анализирую последние фото...{C.END}")

            # 3. Кодирование фото (безопасно, только print)
            imgs = []
            for p in photos[:2]:
                try:
                    b64 = encode_image_to_base64(os.path.join(PHOTOS_DIR, p))
                    if b64:
                        imgs.append(b64)
                except Exception as e:
                    print(f"{C.YELLOW}⚠️ Ошибка кодирования {p}: {e}{C.END}")

            if not imgs:
                print(
                    f"{C.RED}❌ Не удалось подготовить ни одно фото для отправки.{C.END}",
                )
                continue

            # 4. Формирование контекста (ИНИЦИАЛИЗИРУЕТСЯ ЗДЕСЬ, ДО ВЫЗОВА ИИ)
            palace_context = await search_palace_context(
                "фото сон сюрреализм пиктореализм психология идеи образы", limit=7,
            )

from services.prompts import get_smart_prompt

            photo_sys = get_smart_prompt(
                context=palace_context,
                query="анализ фотографии, символика, связь с заметками",
                has_images=True,
            )

            photo_ctx = [{"role": "system", "content": photo_sys}]
            photo_ctx.extend(messages[-10:] if len(messages) > 10 else messages)
            photo_ctx.append(
                {
                    "role": "user",
                    "content": "Проанализируй прикрепленные фотографии. Есть ли здесь связь с моими снами или заметками?",
                },
            )

            # 5. Отправка запроса
            try:
                answer = await get_ai_response_async(
                    engine, model, photo_ctx, context="", images=imgs,
                )
                print(f"\n{C.GREEN}AI (Photo): {format_for_terminal(answer)}{C.END}\n")
            except Exception as e:
                print(f"{C.RED}❌ Ошибка анализа: {e}{C.END}")
                import traceback

                traceback.print_exc()
            continue

        # 🔊 БЫСТРОЕ УПРАВЛЕНИЕ ОЗВУЧКОЙ
        if cmd == "звук":
            vc = get_cli_voice()
            new_state = not vc.get("enabled", True)
            set_cli_voice("enabled", new_state)
            print(f"{C.GREEN}🔊 Озвучка: {'Вкл' if new_state else 'Выкл'}{C.END}")
            continue

        if cmd.startswith("звук-"):
            try:
                spd = int(cmd.split("-", 1)[1])
                spd = max(100, min(300, spd))
                set_cli_voice("speed", spd)
                print(f"{C.GREEN}🔊 Скорость голоса: {spd} wpm{C.END}")
            except (ValueError, IndexError):
                print(
                    f"{C.RED}❌ Неверный формат. Используйте: Звук-150 (100-300){C.END}",
                )
            continue

        # 🚪 Выход
        if cmd in ["q", "й", "quit", "exit", "выход"]:
            print(f"{C.GREEN}💾 Сохраняю диалог...{C.END}")
            save_chat(chat_path, data)
            break

        # 📖 Справка
        if cmd in ["/help", "/h", "-h", "h", "help"]:
            show_help()
            continue

        if cmd.startswith("h ") or cmd.startswith("help "):
            key = user_input.split(maxsplit=1)[1]
            if key in HELP_SECTIONS:
                show_section(key)
            elif key == "0":
                show_all_help()
            else:
                print(f"{C.RED}Неизвестный раздел. Введите h для списка.{C.END}")
            continue

        # 📜 История
        if cmd == "/history":
            print(f"\n{C.CYAN}📜 История чата:{C.END}")
            for m in messages:
                if m.get("role") == "system" and m.get("type") == "summary":
                    print(f"\n{C.PURPLE}{'─' * 40}{C.END}")
                    print(
                        f"{C.PURPLE}📜 САММАРИ ЭТАПА:{C.END}\n{format_for_terminal(m['content'])}",
                    )
                    print(f"{C.PURPLE}{'─' * 40}{C.END}\n")
                elif m["role"] in ["user", "assistant"]:
                    role_tag = (
                        f"{C.YELLOW}👤 Вы:{C.END}"
                        if m["role"] == "user"
                        else f"{C.GREEN}🤖 ИИ:{C.END}"
                    )
                    content_preview = m["content"][:200] + (
                        "..." if len(m["content"]) > 200 else ""
                    )
                    print(f"{role_tag} {format_for_terminal(content_preview)}")
            print()
            continue

        # 📤 Экспорт
        if cmd == "/export":
            md_path = export_chat_to_md(chat_path)
            print(f"{C.GREEN}✅ Экспортировано в: {md_path}{C.END}")
            continue

        # 🔍 Поиск
        if cmd.startswith("/search "):
            query_raw = user_input[8:].strip()
            if not query_raw:
                print(
                    f"{C.RED}❌ Укажите запрос: /search <текст> или /search --wing dreams <текст>{C.END}",
                )
                continue
            wing = ""
            search_text = query_raw
            wing_match = re.match(r"^--wing\s+(\w+)\s+(.*)", query_raw)
            if wing_match:
                wing = wing_match.group(1).lower()
                search_text = wing_match.group(2)
                if wing not in [
                    "dreams",
                    "projects",
                    "philosophy",
                    "creative",
                    "psychology",
                ]:
                    print(
                        f"{C.YELLOW}⚠️ Неизвестное крыло: {wing}. Ищу глобально.{C.END}",
                    )
                    wing = ""
            print(
                f"{C.CYAN}🔍 Ищу в MemPalace{' (крыло: ' + wing + ')' if wing else ''}...{C.END}",
            )
            res = await search_palace_context(search_text, limit=3, wing=wing)
            print(f"\n{C.GREEN}{format_for_terminal(res)}{C.END}\n")
            continue

        # 🏰 Дворец — команды управления MemPalace
        if cmd == "/status":
            print(f"{C.CYAN}🏰 Получаю статус MemPalace...{C.END}")
            res = await palace_status()
            print(f"{C.GREEN}{format_for_terminal(res)}{C.END}\n")
            continue

        if cmd == "/mcp":
            print(f"{C.CYAN}🔌 Получаю команду настройки MCP...{C.END}")
            res = await palace_mcp()
            print(f"{C.GREEN}{format_for_terminal(res)}{C.END}\n")
            continue

        if cmd == "/wakeup":
            print(f"{C.CYAN}🌙 Загружаю дворец в контекст...{C.END}")
            res = await palace_wake_up()
            print(f"{C.GREEN}{format_for_terminal(res)}{C.END}\n")
            continue

        if cmd == "/repair":
            print(
                f"{C.YELLOW}⚠️ Перестройка векторного индекса может занять время...{C.END}",
            )
            print(f"{C.CYAN}🔁 Запускаю repair...{C.END}")
            res = await palace_repair()
            print(f"{C.GREEN}{format_for_terminal(res)}{C.END}\n")
            continue

        if cmd == "/compact":
            print(f"{C.CYAN}🗜️ Запускаю compact (очистка сегментов БД)...{C.END}")
            res = await palace_compact()
            print(f"{C.GREEN}{format_for_terminal(res)}{C.END}\n")
            continue

        if cmd == "/compress":
            print(f"{C.CYAN}📦 Сжимаю текст хранилища...{C.END}")
            res = await palace_compress()
            print(f"{C.GREEN}{format_for_terminal(res)}{C.END}\n")
            continue

        if cmd == "/palace":
            print(f"{C.CYAN}🏰 Дворец MemPalace — команды:{C.END}")
            for line in [
                "/status     — статистика дворца (крылья, комнаты, записи)",
                "/wings      — список всех крыльев",
                "/rooms      — список комнат",
                "/taxonomy   — полная таксономия",
                "/graph      — статистика графа",
                "/traverse   — траверс графа из комнаты",
                "/tunnels    — туннели между крыльями",
                "/follow     — пройти туннели из комнаты",
                "/kg         — поиск в графе знаний",
                "/kgstats    — статистика KG",
                "/mcp        — инструкция MCP",
                "/wakeup     — загрузить дворец в контекст",
                "/repair     — перестроить индекс",
                "/compact    — сжать БД (очистить старые сегменты)",
                "/compress   — сжать текст (AAAK Dialect)",
            ]:
                print(f"  {C.YELLOW}{line}{C.END}")
            print()
            continue

        # 🕸️ Список крыльев
        if cmd == "/wings":
            print(f"{C.CYAN}🕸️ Загружаю список крыльев...{C.END}")
            try:
                mcp = get_mcp()
                await mcp.start()
                raw = await mcp.call_tool("mempalace_list_wings")
                import json as _json

                parsed = _json.loads(raw)
                wings = parsed.get("wings", {})
                for name, count in sorted(wings.items(), key=lambda x: -x[1]):
                    display = name.replace("mempalace_", "").replace("_", " ").title()
                    print(f"  {C.GREEN}{display}:{C.END} {count} записей")
            except Exception as e:
                print(f"{C.RED}❌ Ошибка: {e}{C.END}")
            print()
            continue

        # 🪪 Комнаты
        if cmd.startswith("/rooms"):
            parts = cmd.split(maxsplit=1)
            wing = parts[1] if len(parts) > 1 else None
            print(
                f"{C.CYAN}🪪 Загружаю комнаты{' крыла ' + wing if wing else ''}...{C.END}",
            )
            try:
                mcp = get_mcp()
                await mcp.start()
                args = {"wing": wing} if wing else {}
                raw = await mcp.call_tool("mempalace_list_rooms", args)
                import json as _json

                parsed = _json.loads(raw)
                rooms = parsed.get("rooms", {})
                wing_name = parsed.get("wing", wing or "все")
                print(f"  {C.BOLD}{C.YELLOW}Комнаты «{wing_name}»:{C.END}\n")
                for idx, (room, count) in enumerate(sorted(rooms.items()), 1):
                    print(f"  {idx}. {C.BOLD}{room}{C.END} — {count}")
            except Exception as e:
                print(f"{C.RED}❌ Ошибка: {e}{C.END}")
            print()
            continue

        # 🏛️ Таксономия
        if cmd == "/taxonomy":
            print(f"{C.CYAN}🏛️ Загружаю таксономию...{C.END}")
            try:
                mcp = get_mcp()
                await mcp.start()
                raw = await mcp.call_tool("mempalace_get_taxonomy")
                import json as _json

                parsed = _json.loads(raw)
                tax = parsed.get("taxonomy", {})
                for wing, rooms in sorted(tax.items()):
                    display = wing.replace("_", " ").title()
                    total = sum(rooms.values())
                    print(
                        f"  {C.YELLOW}{display}:{C.END} {total} записей, {len(rooms)} комнат",
                    )
            except Exception as e:
                print(f"{C.RED}❌ Ошибка: {e}{C.END}")
            print()
            continue

        # 📊 Граф
        if cmd == "/graph":
            print(f"{C.CYAN}📊 Загружаю статистику графа...{C.END}")
            try:
                mcp = get_mcp()
                await mcp.start()
                raw = await mcp.call_tool("mempalace_graph_stats")
                import json as _json

                parsed = _json.loads(raw)
                print(f"  {C.GREEN}Комнат всего:{C.END} {parsed.get('total_rooms', 0)}")
                print(
                    f"  {C.GREEN}Комнат с туннелями:{C.END} {parsed.get('tunnel_rooms', 0)}",
                )
                print(f"  {C.GREEN}Связей:{C.END} {parsed.get('total_edges', 0)}")
            except Exception as e:
                print(f"{C.RED}❌ Ошибка: {e}{C.END}")
            print()
            continue

        # 🔀 Траверс
        if cmd.startswith("/traverse"):
            parts = cmd.split(maxsplit=2)
            if len(parts) < 2:
                print(f"{C.RED}❌ Укажите комнату: /traverse <комната> [шаги]{C.END}")
                continue
            room = parts[1]
            hops = int(parts[2]) if len(parts) > 2 else 2
            print(f"{C.CYAN}🔀 Траверс из комнаты «{room}» ({hops} шагов)...{C.END}")
            try:
                mcp = get_mcp()
                await mcp.start()
                raw = await mcp.call_tool(
                    "mempalace_traverse", {"start_room": room, "max_hops": hops},
                )
                print(f"{C.GREEN}{format_for_terminal(raw)}{C.END}")
            except Exception as e:
                print(f"{C.RED}❌ Ошибка: {e}{C.END}")
            print()
            continue

        # 🔄 Туннели
        if cmd.startswith("/tunnels"):
            parts = cmd.split(maxsplit=2)
            wing_a = parts[1] if len(parts) > 1 else None
            wing_b = parts[2] if len(parts) > 2 else None
            print(f"{C.CYAN}🔄 Ищу туннели...{C.END}")
            try:
                mcp = get_mcp()
                await mcp.start()
                args = {}
                if wing_a:
                    args["wing_a"] = wing_a
                if wing_b:
                    args["wing_b"] = wing_b
                raw = await mcp.call_tool("mempalace_find_tunnels", args)
                print(f"{C.GREEN}{format_for_terminal(raw)}{C.END}")
            except Exception as e:
                print(f"{C.RED}❌ Ошибка: {e}{C.END}")
            print()
            continue

        # ➡️ Follow tunnels
        if cmd.startswith("/follow"):
            parts = cmd.split(maxsplit=2)
            if len(parts) < 3:
                print(
                    f"{C.RED}❌ Укажите крыло и комнату: /follow <крыло> <комната>{C.END}",
                )
                continue
            wing, room = parts[1], parts[2]
            print(f"{C.CYAN}➡️ Следую туннелям из {wing}/{room}...{C.END}")
            try:
                mcp = get_mcp()
                await mcp.start()
                raw = await mcp.call_tool(
                    "mempalace_follow_tunnels", {"wing": wing, "room": room},
                )
                print(f"{C.GREEN}{format_for_terminal(raw)}{C.END}")
            except Exception as e:
                print(f"{C.RED}❌ Ошибка: {e}{C.END}")
            print()
            continue

        # 🧠 Знания
        if cmd.startswith("/kg ") and not cmd.startswith("/kgstats"):
            from handlers.palace import _normalize_query

            entity = _normalize_query(cmd.split(maxsplit=1)[1])
            print(f"{C.CYAN}🧠 Ищу «{entity}» в графе знаний...{C.END}")
            try:
                mcp = get_mcp()
                await mcp.start()
                raw = await mcp.call_tool("mempalace_kg_query", {"entity": entity})
                import json as _json

                parsed = _json.loads(raw)
                facts = parsed if isinstance(parsed, list) else parsed.get("facts", [])
                if not facts:
                    print(f"{C.YELLOW}Нет фактов о «{entity}» в графе знаний.{C.END}")
                else:
                    for f in facts:
                        if isinstance(f, dict):
                            line = f"  • {f.get('subject', '?')} → {f.get('predicate', '?')} → {f.get('object', '?')}"
                            if f.get("valid_from"):
                                line += f" (с {f['valid_from']})"
                            print(f"{C.GREEN}{line}{C.END}")
                        else:
                            print(f"  • {f}")
            except Exception as e:
                print(f"{C.RED}❌ Ошибка: {e}{C.END}")
            print()
            continue

        # 📚 Enrichment: добавить связи в KG из заметок
        if cmd == "/enrich":
            notes_count = sum(
                1
                for r, d, fs in os.walk(NOTES_DIR)
                for f in fs
                if f.endswith((".txt", ".md"))
            )
            print(
                f"{C.YELLOW}⚡ Запускаю enrichment заметок в Knowledge Graph...{C.END}",
            )
            print(
                f"{C.YELLOW}⚠️ Найдено {notes_count} файлов. Продолжить? (y/n):{C.END}",
            )
            try:
                confirm = input().strip().lower()
                if confirm != "y":
                    print(f"{C.RED}Отменено.{C.END}")
                    continue
            except:
                continue
            from services.kg_enricher import enrich_all_notes

            print(f"{C.CYAN}📚 Обогащаю заметки...{C.END}")

            async def _progress(curr, total, stats):
                print(
                    f"{C.CYAN}  [{curr}/{total}] {stats['processed']} обработано, {stats['kg_added']} фактов добавлено{C.END}",
                )

            try:
                result = await enrich_all_notes(_progress)
                if "error" in result:
                    print(f"{C.RED}❌ {result['error']}{C.END}")
                else:
                    print(f"\n{C.GREEN}✅ Enrichment завершён:{C.END}")
                    print(f"  • Обработано файлов: {result['processed']}")
                    print(f"  • Не удалось: {result['failed']}")
                    print(f"  • Фактов добавлено в KG: {result['kg_added']}")
                    print(f"  • Найдено авторов: {len(result.get('authors', []))}")
                    print(f"  • Найдено книг: {len(result.get('books', []))}")
                    for a in result.get("authors", [])[:5]:
                        print(f"    - {a}")
                    if len(result.get("authors", [])) > 5:
                        print(f"    ... и ещё {len(result['authors']) - 5}")
            except Exception as e:
                print(f"{C.RED}❌ Ошибка: {e}{C.END}")
            continue

        if cmd == "/kgstats":
            print(f"{C.CYAN}📊 Загружаю статистику графа знаний...{C.END}")
            try:
                mcp = get_mcp()
                await mcp.start()
                raw = await mcp.call_tool("mempalace_kg_stats")
                import json as _json

                parsed = _json.loads(raw)
                print(f"  {C.GREEN}Сущностей:{C.END} {parsed.get('entities', 0)}")
                print(f"  {C.GREEN}Связей:{C.END} {parsed.get('triples', 0)}")
                print(
                    f"  {C.GREEN}Актуальных фактов:{C.END} {parsed.get('current_facts', 0)}",
                )
                print(
                    f"  {C.GREEN}Устаревших фактов:{C.END} {parsed.get('expired_facts', 0)}",
                )
            except Exception as e:
                print(f"{C.RED}❌ Ошибка: {e}{C.END}")
            print()
            continue

        # 🔄 Синхронизация с MemPalace
        if cmd in ["sync", "/sync"]:
            print(f"{C.CYAN}🔄 Подготовка verbatim-экспорта текущего чата...{C.END}")
            exported = export_chat_verbatim(chat_path, os.path.basename(chat_path))
            if not exported:
                print(f"{C.YELLOW}ℹ️ Чат пуст или не найден.{C.END}")
                continue
            print(f"{C.CYAN}⛏️ Запускаю mempalace mine...{C.END}")
            result = await sync_to_palace(exported)
            print(f"{C.GREEN}{format_for_terminal(result)}{C.END}")
            continue

        # 📝 Напоминания
        if cmd == "/remind":
            from cli_extras import cli_remind
            result = await cli_remind(user_input, 0)
            print(f"{C.GREEN}{result}{C.END}")
            continue

        # 📄 PDF
        if cmd == "/pdfs":
            from cli_extras import cli_pdfs
            args = user_input[5:].strip()
            result = await cli_pdfs(args)
            if result:
                print(f"{C.CYAN}{result}{C.END}")
            continue

        # 📜 Транскрипты
        if cmd == "/transkript":
            from cli_extras import cli_transkript
            args = user_input[12:].strip()
            result = await cli_transkript(args)
            if result:
                print(f"{C.CYAN}{result}{C.END}")
            continue

        # 📹 YouTube
        if cmd == "/yt":
            from cli_extras import cli_yt
            url = user_input[3:].strip()
            result = await cli_yt(url, "video")
            print(f"{C.CYAN}{result}{C.END}")
            continue

        if cmd == "/ytaudio":
            from cli_extras import cli_yt
            url = user_input[8:].strip()
            result = await cli_yt(url, "audio")
            print(f"{C.CYAN}{result}{C.END}")
            continue

        # 🔗 Туннели
        if cmd.startswith("/tunnels "):
            from cli_extras import cli_tunnels
            sub = user_input[9:].strip()
            result = await cli_tunnels(sub)
            print(f"{C.CYAN}{result}{C.END}")
            continue

        # 🧠 Добавить факт в KG
        if cmd.startswith("/kgadd "):
            from cli_extras import cli_kgadd
            args = user_input[7:].strip()
            result = await cli_kgadd(args)
            print(f"{C.CYAN}{result}{C.END}")
            continue

        # ⚙️ Настройки модели
        if cmd == "/settings":
            if not os.path.exists(MODELS_CONFIG_PATH):
                print(f"{C.RED}❌ models.json не найден.{C.END}")
                continue
            with open(MODELS_CONFIG_PATH) as f:
                models = json.load(f)
            all_m = [
                (m.get("name", m["tag"]), m["tag"])
                for eng in ["ollama", "openai", "gemini"]
                for m in models.get(eng, [])
            ]
            print(f"\n{C.CYAN}📋 Модели:{C.END}")
            for i, (n, t) in enumerate(all_m, 1):
                print(f"  {i}) {n} ({t})")
            print("  0) Отмена")
            try:
                ch = int(input(f"{C.YELLOW}Выбор: {C.END}"))
                if ch == 0:
                    continue
                if 1 <= ch <= len(all_m):
                    with open(CONFIG_AI_FILE, "w") as f:
                        f.write(all_m[ch - 1][1])
                    invalidate_ai_cache()
                    engine, model = get_current_ai()
                    print(f"{C.GREEN}✅ Модель: {model}{C.END}")
            except ValueError:
                print(f"{C.RED}❌ Неверный ввод.{C.END}")
            continue

        # 🗑️ Удаление / 🆕 Новый / 📂 Список
        if cmd == "/del":
            if os.path.exists(chat_path):
                os.remove(chat_path)
                print(f"{C.GREEN}🗑️ Чат удален. Возврат в меню...{C.END}")
                return "deleted"
        if cmd == "/new":
            return "new"
        if cmd == "/chats":
            return "chats"

        # 📝 Префиксы заметок
        prefix = next(
            (
                p
                for p in ["!!!", "!!", "!", "???", "??", "?"]
                if user_input.startswith(p)
            ),
            "",
        )
        clean_q = user_input[len(prefix) :].strip() if prefix else user_input

        if user_input.startswith("!") and not user_input.startswith("!!"):
            if clean_q:
                fn = f"nt_cli_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
                note_path = os.path.join(NOTES_DIR, fn)

                with open(note_path, "w", encoding="utf-8") as f:
                    f.write(clean_q)

                print(f"{C.GREEN}💾 Сохранено в my_notes.{C.END}")

                # ✅ ИСПРАВЛЕНО: Синхронный запуск связывания
                try:
                    from services.note_linker import link_note_async

                    print(f"{C.YELLOW}🔗 Поиск связанных записей...{C.END}")
                    await link_note_async(note_path, clean_q, prefix="!")
                    print(f"{C.GREEN}✅ Связывание завершено.{C.END}")
                except Exception as e:
                    print(f"{C.YELLOW}⚠️ Ошибка связывания: {e}{C.END}")

                continue

        # 1. 🔍 ПРИОРИТЕТНЫЙ ПОИСК В MEMPALACE С АВТО-КРЫЛОМ
        # print(f"{C.CYAN}🔍 Проверяю личные записи в MemPalace...{C.END}")
        target_wing = None

        # Явное указание имеет приоритет (например, /dreams: вопрос)
        explicit_match = re.match(r"^/(\w+):\s*(.+)", clean_q)
        if explicit_match:
            possible_wing = explicit_match.group(1).lower()
            if possible_wing in [
                "dreams",
                "projects",
                "philosophy",
                "creative",
                "psychology",
            ]:
                target_wing = possible_wing
                clean_q = explicit_match.group(2)  # Убираем префикс из запроса
                print(f"{C.CYAN}🎯 Явное крыло: {target_wing}{C.END}")

        # Автоопределение, если явного нет
        if not target_wing:
            from services.wing_classifier import classify_wing

            auto_wing = classify_wing(clean_q)
            if auto_wing:
                target_wing = auto_wing
                print(f"{C.CYAN}🔍 Авто-крыло: {target_wing}{C.END}")

        palace_context = await search_with_kg(clean_q, limit=3, wing=target_wing)
        latest_summary = data.get("summaries", [])[-1] if data.get("summaries") else ""

        # 2. 🔍 АВТО-ДЕТЕКЦИЯ РЕЖИМА КОДИНГА
        is_code = is_coding_context(clean_q, messages)
        if is_code and not data.get("is_coding_mode"):
            data["is_coding_mode"] = True
            data["project_dir"] = ensure_project_dir(os.path.basename(chat_path))
            save_chat(chat_path, data)
            print(
                f"\n{C.YELLOW}⚡ Активирован режим программирования. Проект: {data['project_dir']}{C.END}",
            )

        # 3. 🧠 ГИБРИДНЫЙ СИСТЕМНЫЙ ПРОМПТ (Сохраняет контекст MemPalace!)
        from services.prompts import get_smart_prompt

        # Проверяем, есть ли фото в последних сообщениях или в явном запросе
        # Для CLI фото обычно передаются через /analyze_photo, но можно проверить msgs
        # 1. Определяем наличие фото (для CLI обычно false, если не /analyze_photo)
        has_images_cli = False

        # 2. Генерируем умный промпт
        from services.prompts import get_smart_prompt

        system_instruction = get_smart_prompt(
            context=palace_context, query=clean_q, has_images=has_images_cli,
        )

        if latest_summary:
            system_instruction += f"\n📜 Контекст текущего диалога:\n{latest_summary}"

        # 📌 Долговременная память (релевантные факты из прошлых диалогов)
        try:
            uid = hash(chat_path)
            memory_ctx = get_memory_context(clean_q, uid)
            if memory_ctx:
                system_instruction += "\n" + memory_ctx
        except Exception:
            pass

        if data.get("is_coding_mode"):
            system_instruction += (
                f"\n👨‍💻 СПЕЦИАЛИЗАЦИЯ: РАЗРАБОТКА\n{load_coding_prompt()}"
            )
            proj_files = read_project_files(data.get("project_dir"))
            if proj_files:
                system_instruction += f"\n📂 Файлы текущего проекта:\n{proj_files}"

        # Формируем итоговый список сообщений
        context_msgs = [{"role": "system", "content": system_instruction}]
        context_msgs.extend(
            list(messages[-10:]) if len(messages) > 10 else list(messages),
        )
        context_msgs.append({"role": "user", "content": clean_q})

        # ✅ ФОТО — ТОЛЬКО ПРИ ЯВНОМ ЗАПРОСЕ (как в боте)
        photo_keywords = [
            "фото",
            "фотку",
            "картинк",
            "изображен",
            "снимок",
            "визуал",
            "проанализируй фото",
            "что на фото",
            "опиши фото",
            "разбор фото",
            "photo",
            "image",
            "picture",
            "analyze photo",
        ]
        wants_photo = any(kw in clean_q.lower() for kw in photo_keywords)
        if wants_photo and check_capability(model, "multimodal"):
            from services.multimodal import encode_image_to_base64, list_photos

            recent_photos = list_photos()[:1]
            for p in recent_photos:
                b64 = encode_image_to_base64(os.path.join(PHOTOS_DIR, p))
                if b64:
                    for m in reversed(context_msgs):
                        if m["role"] == "user" and isinstance(m["content"], str):
                            m["content"] = [
                                {"type": "text", "text": m["content"]},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{b64}",
                                    },
                                },
                            ]
                            break
                    break
        print(f"{C.CYAN}⏳ {model} думает...{C.END}")
        try:
            answer = await get_ai_response_async(
                engine, model, context_msgs, context="",
            )

            # ✅ УМНЫЙ ВЫВОД: Разделяем код и текст
            console = Console()
            if "```" in answer:
                parts = answer.split("```")
                for i, part in enumerate(parts):
                    if (
                        i % 2 == 1
                    ):  # Это блок кода -> используем rich для подсветки синтаксиса
                        lines = part.split("\n", 1)
                        lang = lines[0].strip() if lines else ""
                        code_body = lines[1] if len(lines) > 1 else part
                        console.print(
                            Syntax(
                                code_body,
                                lang or "python",
                                theme="monokai",
                                line_numbers=True,
                            ),
                        )
                    else:
                        if part.strip():
                            # ✅ Используем обычный print, чтобы macOS-терминал корректно отрисовал ANSI-цвета
                            print(format_for_terminal(part), end="")
                        print()  # Перенос строки после текстового блока
            else:
                # ✅ Обычный print для текстовых ответов + применяем форматирование
                print(f"\n{C.GREEN}AI: {C.END}{format_for_terminal(answer)}\n")

            voice_cfg = get_cli_voice()
            speak_text(
                answer,
                speed=voice_cfg["speed"],
                voice=voice_cfg["voice"],
                enabled=voice_cfg["enabled"],
            )

            # 💾 Сохранение
            messages.append({"role": "user", "content": clean_q})
            messages.append({"role": "assistant", "content": answer})
            data["messages"] = messages
            save_chat(chat_path, data)
            await generate_summary_if_needed(messages, data, chat_path)

            # 📌 Фоновое извлечение фактов в долговременную память
            if clean_q and answer:
                uid = hash(chat_path)
                asyncio.create_task(extract_and_store_facts(uid, clean_q, answer))

            if prefix and len(messages) >= 4:
                target_dir = RESEARCH_DIR if "?" in prefix else INSIGHTS_DIR
                fn = f"ext_cli_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
                ext_path = os.path.join(target_dir, fn)
                with open(ext_path, "w") as f:
                    f.write(
                        f"{prefix.upper()}\nИсточник: CLI\nВОПРОС: {clean_q}\nИТОГ: {answer}\n",
                    )
                    # Фоновое связывание
                    from services.note_linker import schedule_linking

                    schedule_linking(ext_path, answer, prefix=prefix)
                print(
                    f"{C.YELLOW}📌 Сохранено в {os.path.basename(target_dir)}.{C.END}",
                )

        except Exception as e:
            print(f"\n{C.RED}❌ Ошибка ИИ/Поиска: {e}{C.END}")
            import traceback

            traceback.print_exc()
            continue


# 🖥️ Главное меню
async def main_menu():
    header = f"{C.CYAN}| Номер чата для продолжения. | Выход Q или Й. | Удалить чат d и номер чата для удаления. | h для справки. |{C.END}"
    separator = f"{C.CYAN}--------------------------------------------------{C.END}"

    while True:
        chats = list_chats()
        print(f"\n{header}")
        print(separator)
        print(f"{C.YELLOW}Выберите чаты:{C.END}")
        print("  0) Создать новый")
        for i, f in enumerate(chats, 1):
            display_name = f.replace("ch_", "").replace(".json", "").replace("_", " ")
            print(f"  {i}) {display_name}")

        try:
            choice = input(f"\n{C.PURPLE}Ваш выбор: {C.END}").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{C.RED}👋 Завершение работы...{C.END}")
            break

        if not choice:
            continue

        if choice in ["q", "й", "quit", "exit", "выход"]:
            print(f"{C.RED}👋 Завершение работы...{C.END}")
            try:
                await get_mcp().stop()
            except:
                pass
            break

        if choice in ["h", "help", "/help", "-h"]:
            show_help()
            continue

        if choice == "0":
            name = (
                input(f"{C.YELLOW}Название нового чата: {C.END}")
                .strip()
                .replace(" ", "_")
            )
            if not name:
                name = f"auto_{datetime.now().strftime('%Y%m%d_%H%M')}"
            fname = f"ch_{name}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
            path = os.path.join(CHATS_DIR, fname)
            save_chat(path, {"summary": "", "messages": [], "summaries": []})
            print(f"{C.GREEN}✅ Чат создан: {fname}{C.END}")
            await chat_loop(path)
            continue

        if choice.startswith("d") and len(choice) > 1:
            try:
                idx = int(choice[1:])
                if 1 <= idx <= len(chats):
                    target_file = chats[idx - 1]
                    target_path = os.path.join(CHATS_DIR, target_file)
                    if os.path.exists(target_path):
                        os.remove(target_path)
                        print(f"{C.GREEN}🗑️ Чат удален: {target_file}{C.END}")
                    else:
                        print(f"{C.RED}❌ Файл не найден.{C.END}")
                else:
                    print(f"{C.RED}❌ Неверный номер чата.{C.END}")
            except ValueError:
                print(f"{C.RED}❌ Формат удаления: d<номер> (напр. d1){C.END}")
            continue

        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(chats):
                target_file = chats[idx - 1]
                target_path = os.path.join(CHATS_DIR, target_file)
                print(f"{C.CYAN}💬 Загрузка чата: {target_file}...{C.END}")
                await chat_loop(target_path)
            else:
                print(f"{C.RED}❌ Неверный номер чата.{C.END}")
            continue

        print(
            f"{C.RED}❌ Неизвестная команда. Введите номер, d<номер>, 0, h или q.{C.END}",
        )


if __name__ == "__main__":
    try:
        asyncio.run(main_menu())
    except KeyboardInterrupt:
        print(f"\n{C.RED}👋 Остановлено.{C.END}")
        try:
            import asyncio as _aio

            _aio.run(get_mcp().stop())
        except:
            pass
