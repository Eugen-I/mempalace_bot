"""CLI Shared Utilities — extracted from cli_ask.py"""
import logging
import os
import re
import json
import subprocess
import tempfile
from datetime import datetime

from config import CHATS_DIR, VOICE_REPLY_CONFIG
from services.ai_engine import get_ai_response_async, get_current_ai

logger = logging.getLogger("CLI")


# 🎨 ЦВЕТОВАЯ РАЗМЕТКА И ФОРМАТИРОВАНИЕ
class C:
    WHITE = "\033[97m"
    GREEN = "\033[92m"
    L_GREEN = "\033[1;92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    L_BLUE = "\033[94m"
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
    if conv_msgs and len(conv_msgs) % 15 == 0:
        print(f"\n{C.CYAN}📝 Генерирую саммари последних 15 сообщений...{C.END}")
        engine, model = get_current_ai()
        dialog_slice = "\n".join(
            [f"{m['role']}: {m['content']}" for m in conv_msgs[-15:]],
        )
        prompt = (
            "Сделай краткое саммари последних 15 сообщений диалога. "
            f"Сохрани ключевые выводы и контекст для продолжения:\n{dialog_slice}"
        )
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


def get_bot_dir() -> str:
    return os.path.expanduser("~/Documents/mempalace_bot")


def is_noise_input(text: str) -> bool:
    """Detect accidental keyboard input (wrong layout, single chars, etc.)"""
    if not text:
        return True
    cleaned = text.strip()
    # Single character is almost always accidental
    if len(cleaned) == 1 and cleaned not in ("?", "~"):
        return True
    # Two characters that aren't known shortcuts
    if len(cleaned) == 2 and cleaned not in ("??", "!!", "#ctx"):
        return True
    # Punctuation-only
    if all(c in ".,;:!?-+=()[]{}@#$%^&*_|\\/'\"" for c in cleaned):
        return True
    return False
