# services/code_mode.py
import os
import re
import json
import shutil
from pathlib import Path

# Пути
BASE_DIR = os.path.expanduser("~/Documents/mempalace")
PROJECTS_DIR = os.path.join(BASE_DIR, "projects")
PROMPTS_FILE = os.path.join(BASE_DIR, "pdf_prompts.json")

# Ключевые слова и паттерны для авто-детекта кода
CODE_PATTERNS = re.compile(r"```|def |class |import |function |var |let |const |=>|{.*:.*}|<.*>|\.py\b|\.json\b|\.js\b")
CODE_KEYWORDS = {"код", "скрипт", "функция", "api", "debug", "ошибка", "переменная", "цикл", "python", "javascript", "json", "структура", "рефакторинг", "класс", "модуль"}

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


def is_coding_context(text: str, history: list = None) -> bool:
    """Определяет, относится ли запрос к программированию."""
    text_lower = text.lower()
    # 1. Проверка на синтаксис кода
    if CODE_PATTERNS.search(text): 
        return True
    # 2. Проверка на ключевые слова
    if any(kw in text_lower for kw in CODE_KEYWORDS): 
        return True
    # 3. Проверка истории (если последние 5 сообщений были про код)
    if history:
        recent = " ".join([m.get("content", "") for m in history[-5:] if m.get("role") == "user"]).lower()
        if any(kw in recent for kw in CODE_KEYWORDS): 
            return True
    return False

def load_coding_prompt() -> str:
    """Загружает промпт 'code_senior' из pdf_prompts.json."""
    try:
        with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Берем промпт из ключа code_senior
        prompt_data = data.get("code_senior", {})
        return prompt_data.get("prompt", "")
    except Exception as e:
        print(f"⚠️ Ошибка загрузки промпта кодинга: {e}")
        return "Ты — Senior Developer. Пиши чистый, эффективный код с комментариями."

def ensure_project_dir(chat_name: str) -> str:
    """Создает папку проекта в ~/Documents/mempalace/projects/<chat_name>."""
    safe_name = re.sub(r'[^\w\-_]', '_', chat_name.replace(".json", ""))
    path = os.path.join(PROJECTS_DIR, safe_name)
    os.makedirs(path, exist_ok=True)
    return path

def save_uploaded_file(file_path: str, project_dir: str) -> str:
    """Копирует файл в папку проекта."""
    dest = os.path.join(project_dir, os.path.basename(file_path))
    shutil.copy2(file_path, dest)
    return dest

def read_project_files(project_dir: str, extensions=(".py", ".json")) -> str:
    """Читает все файлы проекта для контекста (чтобы ИИ видел весь проект)."""
    context = ""
    if not os.path.exists(project_dir):
        return ""
        
    for ext in extensions:
        for f in Path(project_dir).rglob(f"*{ext}"):
            try:
                with open(f, "r", encoding="utf-8") as file:
                    content = file.read()
                context += f"\n📄 Файл: {f.name}\n```\n{content}\n```\n"
            except Exception:
                pass
    return context