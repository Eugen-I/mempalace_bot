#!/usr/bin/env python3
"""
cli_ask.py v2.8
✅ ФОРМАТИРОВАНИЕ ДЛЯ ТЕРМИНАЛА: Убраны спецсимволы Markdown, добавлена поддержка ANSI (жирный/курсив).
✅ НЕБЛОКИРУЮЩАЯ ОЗВУЧКА: say запускается в фоне.
✅ УДАЛЕНО: Устаревший раздел про Hunyuan-MT переводчик.
"""
import os
import sys
import re
import logging
# Скрываем INFO/WARNING от всех модулей, оставляем только ERROR
logging.basicConfig(level=logging.ERROR, format='%(levelname)s: %(message)s')
logger = logging.getLogger("CLI")
logger.setLevel(logging.INFO) # Логи самого CLI (если нужны) останутся

# 📂 Базовые пути
BASE_DIR = os.path.expanduser("~/Documents/mempalace")
BOT_DIR = os.path.expanduser("~/Documents/mempalace_bot")
VENV_DIR = os.path.join(BASE_DIR, "venv")
VENV_PYTHON = os.path.join(VENV_DIR, "bin", "python3")

# 🔄 АВТО-АКТИВАЦИЯ VENV
if sys.executable != VENV_PYTHON and os.path.exists(VENV_PYTHON):
    os.environ["VIRTUAL_ENV"] = VENV_DIR
    os.environ["PATH"] = os.path.join(VENV_DIR, "bin") + os.pathsep + os.environ.get("PATH", "")
    os.execv(VENV_PYTHON, [VENV_PYTHON] + sys.argv)

sys.path.insert(0, BOT_DIR)
sys.path.insert(0, BASE_DIR)

import json
import asyncio
import subprocess
import readline
import atexit
from datetime import datetime
from typing import List, Dict, Optional
from rich.console import Console
from rich.syntax import Syntax
from services.code_mode import is_coding_context, load_coding_prompt, ensure_project_dir, read_project_files
from services.palace_bridge import search_palace_context, export_chat_verbatim, sync_to_palace

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
    CHATS_DIR, NOTES_DIR, INSIGHTS_DIR, RESEARCH_DIR,
    CONFIG_AI_FILE, MODELS_CONFIG_PATH, VOICE_REPLY_CONFIG, DATA_DIR, PHOTOS_DIR
)
from services.ai_engine import get_current_ai, get_ai_response_async, invalidate_ai_cache
from services.multimodal import check_capability
from services.palace_bridge import search_palace_context, export_chat_verbatim, sync_to_palace
from services.memory import get_memory_context, extract_and_store_facts

# 🎨 ЦВЕТОВАЯ РАЗМЕТКА И ФОРМАТИРОВАНИЕ
class C:
    WHITE = '\033[97m'
    GREEN = '\033[92m'
    L_GREEN = '\033[1;92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    PURPLE = '\033[95m'
    BOLD = '\033[1m'      # Жирный
    ITALIC = '\033[3m'    # Курсив (поддерживается не всеми терминалами, но стандартен)
    UNDERLINE = '\033[4m' # Подчеркнутый
    END = '\033[0m'
    
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
    """
    Очищает текст от Markdown символов и заменяет их на ANSI коды для терминала.
    **bold** -> Жирный
    *italic* -> Курсив
    __underline__ -> Подчеркнутый (если используется такой синтаксис, но обычно в MD это bold)
    `code` -> Моноширинный (обычно просто убираем бэктики или делаем цветом)
    """
    if not text:
        return ""
        
    # 1. Заменяем Жирный (**text**)
    # Используем регулярку с non-greedy matching
    text = re.sub(r'\*\*(.+?)\*\*', f'{C.BOLD}\\1{C.END}', text)
    
    # 2. Заменяем Курсив (*text*)
    # Важно: делать после жирного, чтобы не задеть звездочки внутри жирного
    text = re.sub(r'\*(.+?)\*', f'{C.ITALIC}\\1{C.END}', text)
    
    # 3. Заменяем Код (`text`)
    # Можно сделать его другим цветом, например Cyan, или просто убрать бэктики
    text = re.sub(r'`(.+?)`', f'{C.CYAN}\\1{C.END}', text)
    
    # 4. Заголовки (# Header)
    # Делаем их жирными и возможно другого цвета
    text = re.sub(r'^#{1,3}\s+(.+)$', f'{C.BOLD}{C.YELLOW}\\1{C.END}', text, flags=re.MULTILINE)
    
    # 5. Списки (- item или * item)
    # Просто оставляем как есть, или можно добавить отступ
    
    # 6. Ссылки [text](url) -> просто text (url часто шумит в терминале)
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    
    return text

# 🔒 Безопасная НЕБЛОКИРУЮЩАЯ озвучка
def speak_text(text: str, speed: int = 160, voice: str = "Milena", enabled: bool = True) -> None:
    if not enabled or not text:
        return
    try:
        subprocess.Popen(
            ["say", "-v", voice, "-r", str(speed), text],
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL, 
            start_new_session=True
        )
    except Exception as e:
        print(f"{C.RED}⚠️ Ошибка озвучки: {e}{C.END}")

# 💾 Работа с чатами
def load_chat(path: str) -> Dict:
    if not os.path.exists(path):
        return {"summary": "", "messages": [], "summaries": []}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        data = {"summary": "", "messages": data, "summaries": []}
        save_chat(path, data)
    return data

#Находить блоки кода в ответе ИИ (или в вашем запросе, если вы вставили код туда).
#Сохранять их как .py файлы в папку проекта.
def save_code_from_text(text: str, project_dir: str, filename_hint: str = "script") -> list:
    """
    Ищет блоки кода в тексте и сохраняет их в папку проекта.
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
            if "json" in lang_lower: ext = ".json"
            elif "js" in lang_lower: ext = ".js"
            elif "cpp" in lang_lower: ext = ".cpp"
            elif "html" in lang_lower: ext = ".html"
            
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


def save_chat(path: str, data: Dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def list_chats() -> List[str]:
    if not os.path.exists(CHATS_DIR):
        return []
    return sorted(
        [f for f in os.listdir(CHATS_DIR) if f.endswith(".json")],
        key=lambda x: os.path.getmtime(os.path.join(CHATS_DIR, x)), reverse=True
    )

# ⚙️ Голосовые настройки
def get_cli_voice() -> Dict:
    cfg = {}
    if os.path.exists(VOICE_REPLY_CONFIG):
        with open(VOICE_REPLY_CONFIG, "r") as f:
            cfg = json.load(f)
    return cfg.get("cli", {"enabled": True, "speed": 160, "voice": "Milena"})

def set_cli_voice(key: str, value) -> None:
    cfg = {}
    if os.path.exists(VOICE_REPLY_CONFIG):
        with open(VOICE_REPLY_CONFIG, "r") as f:
            cfg = json.load(f)
    cfg.setdefault("cli", {"enabled": True, "speed": 160, "voice": "Milena"})[key] = value
    with open(VOICE_REPLY_CONFIG, "w") as f:
        json.dump(cfg, f, indent=2)

# 📜 Генерация саммари
async def generate_summary_if_needed(messages: List[Dict], chat_data: Dict, chat_path: str) -> Optional[str]:
    conv_msgs = [m for m in messages if m.get("role") in ["user", "assistant"]]
    if len(conv_msgs) > 0 and len(conv_msgs) % 15 == 0:
        print(f"\n{C.CYAN}📝 Генерирую саммари последних 15 сообщений...{C.END}")
        engine, model = get_current_ai()
        dialog_slice = "\n".join([f"{m['role']}: {m['content']}" for m in conv_msgs[-15:]])
        prompt = f"Сделай краткое саммари последних 15 сообщений диалога. Сохрани ключевые выводы и контекст для продолжения:\n{dialog_slice}"
        try:
            summary = await get_ai_response_async(engine, model, [{"role": "user", "content": prompt}], context="")
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
HELP_TEXT = f"""{C.CYAN}==========================================================
    🦾 MemPalace CLI | Справка
    =========================================================={C.END}
    {C.YELLOW}🔊 БЫСТРОЕ УПРАВЛЕНИЕ ЗВУКОМ:{C.END}
    Звук           → Вкл/Выкл озвучку (неблокирующая)
    Звук-150       → Установить скорость (100-300)
    {C.YELLOW}📝 ЗАПИСЬ И БИБЛИОТЕКА:{C.END}
    ! текст          → Быстрая заметка в my_notes
    !!               → Сохранить последний ответ ИИ в Insights
    ???              → Сохранить в Research
    {C.YELLOW}💬 УПРАВЛЕНИЕ ЧАТАМИ:{C.END}
    /history         → Показать историю текущего чата
    /export          → Экспорт чата в .md (папка chats/exports/)
    ~ или #ctx       → Показать последнее саммари чата
    {C.YELLOW}🔍 ПОИСК И СИНХРОНИЗАЦИЯ:{C.END}
    /search <запрос> → Поиск по всей базе MemPalace
    /search --wing dreams <запрос> → Поиск по крылу (dreams, projects, philosophy, creative, psychology)
    sync             → Синхронизировать текущий чат с MemPalace (verbatim)
    /photos          - Список фото в папке
    /analyze_photo   - Анализ фото ИИ
    {C.YELLOW}⚙️ СИСТЕМНЫЕ:{C.END}
    /settings        → Сменить модель ИИ
    q, й, Ctrl+C     → Выход с сохранением
    {C.CYAN}=========================================================={C.END}"""

def show_help():
    print(HELP_TEXT)

# 🧠 Ядро диалога
async def chat_loop(chat_path: str):
    data = load_chat(chat_path)
    messages = data.get("messages", [])
    voice_cfg = get_cli_voice()
    engine, model = get_current_ai()
    
    print(f"\n{C.CYAN}=========================================================={C.END}")
    print(f"{C.CYAN}💬 Активен чат: {C.BOLD}{os.path.basename(chat_path)}{C.END}")
    print(f"{C.GREEN}🤖 Модель: {model} ({engine}) | 🎤 Голос: {'Вкл' if voice_cfg['enabled'] else 'Выкл'} ({voice_cfg['voice']}, {voice_cfg['speed']} wpm){C.END}")
    print(f"{C.YELLOW}Введите h для справки. q или й для выхода.{C.END}")
    print(f"{C.CYAN}==========================================================\n{C.END}")

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
            #print(f"{C.CYAN}[DEBUG] Проверяю папку: {PHOTOS_DIR}{C.END}")
            photos = list_photos()
            if not photos:
                print(f"{C.YELLOW}📁 Папка photos пуста.{C.END}")
            else:
                print(f"{C.CYAN}📸 Фото в базе ({len(photos)}):{C.END}")
                for i, p in enumerate(photos, 1):
                    print(f"  {i}) {p}")
            continue

        if cmd == "/analyze_photo":
            from services.multimodal import list_photos, encode_image_to_base64, check_capability

            # 1. Проверка поддержки модели
            if not check_capability(model, "multimodal"):
                print(f"{C.RED}⚠️ Модель {model} не поддерживает анализ фото. Переключитесь на Gemma 4.{C.END}")
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
                print(f"{C.RED}❌ Не удалось подготовить ни одно фото для отправки.{C.END}")
                continue

            # 4. Формирование контекста (ИНИЦИАЛИЗИРУЕТСЯ ЗДЕСЬ, ДО ВЫЗОВА ИИ)
            palace_context = await search_palace_context("фото сон сюрреализм пиктореализм психология идеи образы", limit=7)
            
            from services.prompts import get_smart_prompt
            photo_sys = get_smart_prompt(
                context=palace_context,
                query="анализ фотографии, символика, связь с заметками",
                has_images=True
            )

            photo_ctx = [{"role": "system", "content": photo_sys}]
            photo_ctx.extend(messages[-10:] if len(messages) > 10 else messages)
            photo_ctx.append({"role": "user", "content": "Проанализируй прикрепленные фотографии. Есть ли здесь связь с моими снами или заметками?"})

            # 5. Отправка запроса
            try:
                answer = await get_ai_response_async(engine, model, photo_ctx, context="", images=imgs)
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
                print(f"{C.RED}❌ Неверный формат. Используйте: Звук-150 (100-300){C.END}")
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

        # 📜 История
        if cmd == "/history":
            print(f"\n{C.CYAN}📜 История чата:{C.END}")
            for m in messages:
                if m.get("role") == "system" and m.get("type") == "summary":
                    print(f"\n{C.PURPLE}{'─'*40}{C.END}")
                    print(f"{C.PURPLE}📜 САММАРИ ЭТАПА:{C.END}\n{format_for_terminal(m['content'])}")
                    print(f"{C.PURPLE}{'─'*40}{C.END}\n")
                elif m["role"] in ["user", "assistant"]:
                    role_tag = f"{C.YELLOW}👤 Вы:{C.END}" if m["role"] == "user" else f"{C.GREEN}🤖 ИИ:{C.END}"
                    content_preview = m['content'][:200] + ('...' if len(m['content'])>200 else '')
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
                print(f"{C.RED}❌ Укажите запрос: /search <текст> или /search --wing dreams <текст>{C.END}")
                continue
            wing = ""
            search_text = query_raw
            wing_match = re.match(r'^--wing\s+(\w+)\s+(.*)', query_raw)
            if wing_match:
                wing = wing_match.group(1).lower()
                search_text = wing_match.group(2)
                if wing not in ["dreams", "projects", "philosophy", "creative", "psychology"]:
                    print(f"{C.YELLOW}⚠️ Неизвестное крыло: {wing}. Ищу глобально.{C.END}")
                    wing = ""
            print(f"{C.CYAN}🔍 Ищу в MemPalace{' (крыло: ' + wing + ')' if wing else ''}...{C.END}")
            res = await search_palace_context(search_text, limit=3, wing=wing)
            print(f"\n{C.GREEN}{format_for_terminal(res)}{C.END}\n")
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

        # ⚙️ Настройки модели
        if cmd == "/settings":
            if not os.path.exists(MODELS_CONFIG_PATH):
                print(f"{C.RED}❌ models.json не найден.{C.END}")
                continue
            with open(MODELS_CONFIG_PATH, "r") as f:
                models = json.load(f)
            all_m = [(m.get("name", m["tag"]), m["tag"]) for eng in ["ollama", "openai", "gemini"] for m in models.get(eng, [])]
            print(f"\n{C.CYAN}📋 Модели:{C.END}")
            for i, (n, t) in enumerate(all_m, 1):
                print(f"  {i}) {n} ({t})")
            print(f"  0) Отмена")
            try:
                ch = int(input(f"{C.YELLOW}Выбор: {C.END}"))
                if ch == 0:
                    continue
                if 1 <= ch <= len(all_m):
                    with open(CONFIG_AI_FILE, "w") as f:
                        f.write(all_m[ch-1][1])
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
        prefix = next((p for p in ["!!!", "!!", "!", "???", "??", "?"] if user_input.startswith(p)), "")
        clean_q = user_input[len(prefix):].strip() if prefix else user_input
        
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
        #print(f"{C.CYAN}🔍 Проверяю личные записи в MemPalace...{C.END}")
        target_wing = None
        
        # Явное указание имеет приоритет (например, /dreams: вопрос)
        explicit_match = re.match(r'^/(\w+):\s*(.+)', clean_q)
        if explicit_match:
            possible_wing = explicit_match.group(1).lower()
            if possible_wing in ["dreams", "projects", "philosophy", "creative", "psychology"]:
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
        
        palace_context = await search_palace_context(clean_q, limit=3, wing=target_wing)
        latest_summary = data.get("summaries", [])[-1] if data.get("summaries") else ""

        # 2. 🔍 АВТО-ДЕТЕКЦИЯ РЕЖИМА КОДИНГА
        is_code = is_coding_context(clean_q, messages)
        if is_code and not data.get("is_coding_mode"):
            data["is_coding_mode"] = True
            data["project_dir"] = ensure_project_dir(os.path.basename(chat_path))
            save_chat(chat_path, data)
            print(f"\n{C.YELLOW}⚡ Активирован режим программирования. Проект: {data['project_dir']}{C.END}")

        # 3. 🧠 ГИБРИДНЫЙ СИСТЕМНЫЙ ПРОМПТ (Сохраняет контекст MemPalace!)
        from services.prompts import get_smart_prompt
    
        # Проверяем, есть ли фото в последних сообщениях или в явном запросе
        # Для CLI фото обычно передаются через /analyze_photo, но можно проверить msgs
        # 1. Определяем наличие фото (для CLI обычно false, если не /analyze_photo)
        has_images_cli = False 
    
        # 2. Генерируем умный промпт
        from services.prompts import get_smart_prompt
        system_instruction = get_smart_prompt(
            context=palace_context, 
            query=clean_q, 
            has_images=has_images_cli
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
            system_instruction += f"\n👨‍💻 СПЕЦИАЛИЗАЦИЯ: РАЗРАБОТКА\n{load_coding_prompt()}"
            proj_files = read_project_files(data.get("project_dir"))
            if proj_files:
                system_instruction += f"\n📂 Файлы текущего проекта:\n{proj_files}"

        # Формируем итоговый список сообщений
        context_msgs = [{"role": "system", "content": system_instruction}]
        context_msgs.extend(list(messages[-10:]) if len(messages) > 10 else list(messages))
        context_msgs.append({"role": "user", "content": clean_q})

        # ✅ ФОТО — ТОЛЬКО ПРИ ЯВНОМ ЗАПРОСЕ (как в боте)
        photo_keywords = [
            "фото", "фотку", "картинк", "изображен", "снимок", "визуал",
            "проанализируй фото", "что на фото", "опиши фото", "разбор фото",
            "photo", "image", "picture", "analyze photo"
        ]
        wants_photo = any(kw in clean_q.lower() for kw in photo_keywords)
        if wants_photo and check_capability(model, "multimodal"):
            from services.multimodal import list_photos, encode_image_to_base64
            recent_photos = list_photos()[:1]
            for p in recent_photos:
                b64 = encode_image_to_base64(os.path.join(PHOTOS_DIR, p))
                if b64:
                    for m in reversed(context_msgs):
                        if m["role"] == "user" and isinstance(m["content"], str):
                            m["content"] = [
                                {"type": "text", "text": m["content"]},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                            ]
                            break
                    break
        print(f"{C.CYAN}⏳ {model} думает...{C.END}")
        try:
            answer = await get_ai_response_async(engine, model, context_msgs, context="")
            
            # ✅ УМНЫЙ ВЫВОД: Разделяем код и текст
            console = Console()
            if "```" in answer:
                parts = answer.split("```")
                for i, part in enumerate(parts):
                    if i % 2 == 1:  # Это блок кода -> используем rich для подсветки синтаксиса
                        lines = part.split("\n", 1)
                        lang = lines[0].strip() if lines else ""
                        code_body = lines[1] if len(lines) > 1 else part
                        console.print(Syntax(code_body, lang or "python", theme="monokai", line_numbers=True))
                    else:
                        if part.strip():
                            # ✅ Используем обычный print, чтобы macOS-терминал корректно отрисовал ANSI-цвета
                            print(format_for_terminal(part), end="")
                        print()  # Перенос строки после текстового блока
            else:
                # ✅ Обычный print для текстовых ответов + применяем форматирование
                print(f"\n{C.GREEN}AI: {C.END}{format_for_terminal(answer)}\n")


            voice_cfg = get_cli_voice()
            speak_text(answer, speed=voice_cfg["speed"], voice=voice_cfg["voice"], enabled=voice_cfg["enabled"])
            
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
                    f.write(f"{prefix.upper()}\nИсточник: CLI\nВОПРОС: {clean_q}\nИТОГ: {answer}\n")
                    #Фоновое связывание
                    from services.note_linker import schedule_linking
                    schedule_linking(ext_path, answer, prefix=prefix)
                print(f"{C.YELLOW}📌 Сохранено в {os.path.basename(target_dir)}.{C.END}")
                
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
        print(f"  0) Создать новый")
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
            break
            
        if choice in ["h", "help", "/help", "-h"]:
            show_help()
            continue
            
        if choice == "0":
            name = input(f"{C.YELLOW}Название нового чата: {C.END}").strip().replace(" ", "_")
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
                    target_file = chats[idx-1]
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
                target_file = chats[idx-1]
                target_path = os.path.join(CHATS_DIR, target_file)
                print(f"{C.CYAN}💬 Загрузка чата: {target_file}...{C.END}")
                await chat_loop(target_path)
            else:
                print(f"{C.RED}❌ Неверный номер чата.{C.END}")
            continue
            
        print(f"{C.RED}❌ Неизвестная команда. Введите номер, d<номер>, 0, h или q.{C.END}")

if __name__ == "__main__":
    try:
        asyncio.run(main_menu())
    except KeyboardInterrupt:
        print(f"\n{C.RED}👋 Остановлено.{C.END}")