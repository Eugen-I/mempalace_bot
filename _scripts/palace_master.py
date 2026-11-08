#!/usr/bin/env python3
"""palace_master.py — Единый центр управления базой знаний MemPalace.

Работает из ЛЮБОГО места в системе и сам автоматически находит:
- Корень бота: mempalace_bot
- Корень хранилища и заметок: mempalace
- Данные ChromaDB и графа: ~/.mempalace
- Окружение Python: venv
"""

import datetime
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Цвета терминала ──────────────────────────────────────────────────────────
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_CYAN = "\033[1;36m"
C_GREEN = "\033[1;32m"
C_YELLOW = "\033[1;33m"
C_RED = "\033[1;31m"
C_MAGENTA = "\033[1;35m"
C_BLUE = "\033[1;34m"
C_DIM = "\033[2m"

# ── Таксономия русских названий ──────────────────────────────────────────────
WING_LABELS = {
    # Latin keys
    "philosophy": "🏛️ Философия",
    "psychology": "🧠 Психология",
    "photography": "📷 Фотография",
    "creative": "🎨 Творчество",
    "personal": "👤 Личные мысли",
    "projects": "💼 Проекты",
    "dreams": "🌙 Сны и сновидения",
    "health": "💪 Здоровье и медицина",
    "insights": "💡 Инсайты",
    "research": "🔬 Исследования",
    "literature": "📚 Литература",
    "general": "📦 Общее",
    "my_notes": "📁 Мои заметки",
    "deutsch": "🇩🇪 Немецкий (Deutsch)",

    # Cyrillic keys (legacy or imported)
    "философия": "🏛️ Философия",
    "психология": "🧠 Психология",
    "фотография": "📷 Фотография",
    "творчество": "🎨 Творчество",
    "личные мысли": "👤 Личные мысли",
    "личные_мысли": "👤 Личные мысли",
    "проекты": "💼 Проекты",
    "сны": "🌙 Сны и сновидения",
    "сновидения": "🌙 Сны и сновидения",
    "здоровье": "💪 Здоровье и медицина",
    "инсайты": "💡 Инсайты",
    "исследования": "🔬 Исследования",
    "литература": "📚 Литература",
    "мои заметки": "📁 Мои заметки",
    "мои_заметки": "📁 Мои заметки",
    "общее": "📦 Общее",
}

ROOM_LABELS = {
    # Философия
    "cioran": "Эмиль Чоран",
    "thinking": "Методы мышления и познание",
    "brenifier": "Оскар Бренифье",
    "phenomenology": "Феноменология и бытие",
    "stoicism": "Стоицизм и Сенека",
    "nietzsche": "Фридрих Ницше",
    "spinoza": "Барух Спиноза",
    "kant": "Иммануил Кант",
    # Психология
    "archetypes": "Архетипы и Социальная Маска",
    "jung": "Карл Густав Юнг",
    "psychoanalysis": "Психоанализ и Бион",
    "frankl": "Виктор Франкл",
    "lacan": "Жак Лакан",
    "freud": "Зигмунд Фрейд",
    "vygotsky": "Лев Выготский",
    # Фотография
    "curator_texts": "Кураторские тексты",
    "explications": "Экспликации к выставкам",
    "photographers": "Фотографы и авторы",
    "therapy": "Фототрансцендентная арт-терапия",
    "aldridge": "Майлз Олдридж",
    "testino": "Марио Тестино",
    "klimt": "Густав Климт",
    "lindbergh": "Петер Линдберг",
    # Творчество
    "poetry": "Мои стихи",
    "scripts": "Сценарии и манифесты",
    "ideas": "Креативные идеи",
    # Личное
    "reflections": "Мои мысли и размышления",
    "aphorisms": "Высказывания и афоризмы",
    "books": "Мысли и цитаты из книг",
    # Проекты
    "project_mask": "Project Mask",
    "gemini_ai": "Gemini & AI",
    "tech": "IT и разработка",
    # Литература
    "classics": "Классика литературы",
    "reading_list": "Список для чтения",
    # Общее
    "general": "Общие записи",
    "journal": "Дневник сновидений",
    "_registry": "Служебный реестр",
}


def format_wing(wing: str) -> str:
    norm = str(wing).lower().strip()
    if norm in WING_LABELS:
        return WING_LABELS[norm]
    return f"🪪 {str(wing).replace('_', ' ').title()}"


def format_room(room: str) -> str:
    r = str(room).lower().strip()
    if r in ROOM_LABELS:
        return ROOM_LABELS[r]
    if r.startswith("dr_") or r.startswith("doctor_"):
        name = r.split("_", 1)[1].replace("_", " ").title()
        return f"👨‍⚕️ Доктор {name}"
    if r.startswith("book_"):
        return f"📖 Книга: {r[5:].replace('_', ' ').title()}"
    if r.startswith("phil_"):
        return f"🏛️ Философ: {r[5:].replace('_', ' ').title()}"
    if r.startswith("photo_"):
        return f"📷 Фотограф: {r[6:].replace('_', ' ').title()}"
    return str(room).replace("_", " ").strip().title()


# ── Автоопределение путей в системе ──────────────────────────────────────────
def detect_system_paths() -> dict:
    home = os.path.expanduser("~")

    # 1. BOT_DIR
    bot_candidates = [
        os.environ.get("BOT_DIR"),
        os.path.join(home, "Documents", "mempalace_bot"),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
    ]
    bot_dir = next(
        (c for c in bot_candidates if c and os.path.isfile(os.path.join(c, "config.py"))),
        None,
    )

    # 2. PALACE_DIR
    palace_candidates = [
        os.environ.get("PALACE_DIR"),
        os.path.join(home, "Documents", "mempalace"),
    ]
    palace_dir = next(
        (c for c in palace_candidates if c and os.path.isdir(os.path.join(c, "my_notes"))),
        None,
    )

    # 3. DATA_DIR
    data_dir = os.environ.get("MEMPALACE_DATA_DIR") or os.path.join(home, ".mempalace")

    # 4. CHROMA_DB
    chroma_db = os.path.join(data_dir, "palace", "chroma.sqlite3")

    # 5. KG_DB
    kg_db = os.path.join(data_dir, "knowledge_graph.sqlite3")

    # 6. VENV_PYTHON
    venv_candidates = [
        os.path.join(palace_dir, "venv", "bin", "python3") if palace_dir else None,
        os.path.join(home, "Documents", "mempalace", "venv", "bin", "python3"),
        os.path.join(bot_dir, "venv", "bin", "python3") if bot_dir else None,
    ]
    venv_python = next(
        (c for c in venv_candidates if c and os.path.isfile(c) and os.access(c, os.X_OK)),
        sys.executable,
    )

    return {
        "bot_dir": bot_dir,
        "palace_dir": palace_dir,
        "notes_dir": os.path.join(palace_dir, "my_notes") if palace_dir else None,
        "data_dir": data_dir,
        "chroma_db": chroma_db,
        "kg_db": kg_db,
        "venv_python": venv_python,
    }


PATHS = detect_system_paths()


FOLDER_WING_MAP = {
    "философия": "philosophy",
    "психология": "psychology",
    "фотография": "photography",
    "фотографы": "photography",
    "арт фототерапия как мой проект": "photography",
    "кураторский текст": "photography",
    "экспликации к фотографиям": "photography",
    "проект архитипы юнга социальная маска": "psychology",
    "архитипы": "psychology",
    "цитаты юнга по архитирам": "psychology",
    "психоаналитическая модель опыта в творчестве фотографа": "psychology",
    "мои стихи": "creative",
    "творчество": "creative",
    "мои мысли и размышления": "personal",
    "высказывание": "personal",
    "высказывания": "personal",
    "мысли из книг": "personal",
    "project mask": "projects",
    "gemini": "projects",
    "сны": "dreams",
}


# ── Интеллектуальный классификатор путей и текста ─────────────────────────────
def categorize_file(filepath: str, text_snippet: str = "") -> tuple[str, str]:
    """Определяет (wing, room) для заметки на основе пути, имени файла и текста.

    Поддерживает:
    1. Автоматическое определение крыльев по папкам и контексту.
    2. Автоматическое распознавание новых авторов, философов, врачей, книг.
    3. Создание динамических комнат при обнаружении новых тем.
    """
    p = filepath.lower()
    t = text_snippet.lower()
    combined = f"{p} {t}"

    fname = os.path.splitext(os.path.basename(filepath))[0]
    fname_clean = fname.replace("_", " ").strip()

    # 1. Сны и сновидения
    if any(k in combined for k in ("сон ", "сны", "сновиден", "кошмар", "dream")):
        return "dreams", "journal"

    # 2. Определение родительской папки (если есть)
    folder = ""
    parts = filepath.replace("\\", "/").split("/")
    for i, part in enumerate(parts):
        if part.lower() == "my_notes" and i + 1 < len(parts) - 1:
            folder = parts[i + 1].strip()
            break

    # 3. Определение крыла
    wing = None
    if folder and folder.lower() in FOLDER_WING_MAP:
        wing = FOLDER_WING_MAP[folder.lower()]
    elif any(k in combined for k in ("project mask", "project_mask")):
        wing = "projects"
    elif any(k in combined for k in (
        "чоран", "cioran", "ницше", "стоик", "марк аврелий", "сенека",
        "философ", "бренифье", "дьюи", "оракс", "спиноза", "кант"
    )):
        wing = "philosophy"
    elif any(k in combined for k in (
        "юнг", "jung", "фрейд", "лакан", "бион", "франкл", "выготск",
        "психолог", "архетип", "архитип", "маска"
    )):
        wing = "psychology"
    elif any(k in combined for k in (
        "фотограф", "фототерапи", "кураторск", "экспликаци", "съемк",
        "олдридж", "тестино", "климт", "линдберг"
    )):
        wing = "photography"
    elif any(k in combined for k in ("стих", "поэзи", "сценари", "манифест")):
        wing = "creative"
    elif any(k in combined for k in ("доктор", "врач", "медицин", "здоровь")):
        wing = "health"
    elif folder:
        # Новая пользовательская тематическая папка -> динамическое крыло
        wing = re.sub(r"[\s\-]+", "_", folder.lower())
        if wing not in WING_LABELS:
            WING_LABELS[wing] = f"🪪 {folder.title()}"
    else:
        wing = "personal"

    # 4. Проверка на врача / исследователя
    doc_match = re.search(r'(?:доктор|врач)\s+([а-яa-z]+)', combined)
    if doc_match:
        doc_name = doc_match.group(1).capitalize()
        room = f"dr_{doc_name.lower()}"
        ROOM_LABELS[room] = f"👨‍⚕️ Доктор {doc_name}"
        return wing, room

    # 5. Определение комнаты внутри крыла
    if wing == "philosophy":
        if "чоран" in combined or "cioran" in combined:
            return "philosophy", "cioran"
        if "ницше" in combined:
            return "philosophy", "nietzsche"
        if any(k in combined for k in ("стоик", "аврелий", "сенека")):
            return "philosophy", "stoicism"
        if "бренифье" in combined:
            return "philosophy", "brenifier"
        if any(k in combined for k in ("мышлени", "познани", "дьюи", "оракс")):
            return "philosophy", "thinking"
        if any(k in combined for k in ("феноменолог", "иллюзия я", "иллюзия «я»")):
            return "philosophy", "phenomenology"
        if "дилемма" in combined:
            return "philosophy", "thinking"
        # Динамическая комната по автору/теме
        if fname_clean and len(fname_clean) > 2 and not fname_clean.startswith("notes_"):
            r_slug = re.sub(r"[^\w]+", "_", fname_clean.lower())[:28].strip("_")
            ROOM_LABELS[r_slug] = fname_clean.title()
            return "philosophy", r_slug
        return "philosophy", "general"

    elif wing == "psychology":
        if any(k in combined for k in (
            "социальная маска", "архетип", "архитип", "персона", "тень"
        )):
            return "psychology", "archetypes"
        if "юнг" in combined or "jung" in combined:
            return "psychology", "jung"
        if any(k in combined for k in ("франкл", "логотерапи")):
            return "psychology", "frankl"
        if "лакан" in combined or "lacan" in combined:
            return "psychology", "lacan"
        if any(k in combined for k in ("психоаналит", "бион", "фрейд")):
            return "psychology", "psychoanalysis"
        if "выготск" in combined:
            return "psychology", "vygotsky"
        if fname_clean and len(fname_clean) > 2 and not fname_clean.startswith("notes_"):
            r_slug = re.sub(r"[^\w]+", "_", fname_clean.lower())[:28].strip("_")
            ROOM_LABELS[r_slug] = fname_clean.title()
            return "psychology", r_slug
        return "psychology", "general"

    elif wing == "photography":
        if "фототерапи" in combined or "арт фото" in combined:
            return "photography", "therapy"
        if "кураторск" in combined:
            return "photography", "curator_texts"
        if "экспликаци" in combined:
            return "photography", "explications"
        if "олдридж" in combined:
            return "photography", "aldridge"
        if "тестино" in combined:
            return "photography", "testino"
        if "климмт" in combined or "климт" in combined:
            return "photography", "klimt"
        if "линдберг" in combined:
            return "photography", "lindbergh"
        if "фотографы" in p and fname_clean and fname_clean.lower() not in (
            "фотографы", "general"
        ):
            r_slug = re.sub(r"[^\w]+", "_", fname_clean.lower())[:28].strip("_")
            ROOM_LABELS[r_slug] = fname_clean.title()
            return "photography", r_slug
        return "photography", "photographers"

    elif wing == "creative":
        if "стих" in combined or "поэзи" in combined:
            return "creative", "poetry"
        if any(k in combined for k in ("сценари", "манифест", "кино", "драматург")):
            return "creative", "scripts"
        return "creative", "ideas"

    elif wing == "projects":
        if "mask" in combined:
            return "projects", "project_mask"
        if "gemini" in combined or "gpt" in combined:
            return "projects", "gemini_ai"
        return "projects", "general"

    elif wing == "personal":
        if any(k in combined for k in ("мысли из книг", "книг", "конспект")):
            return "personal", "books"
        if any(k in combined for k in ("высказывани", "афоризм", "цитат")):
            return "personal", "aphorisms"
        return "personal", "reflections"

    # Для неизвестных пользовательских папок
    if fname_clean:
        r_slug = re.sub(r"[^\w]+", "_", fname_clean.lower())[:28].strip("_")
    else:
        r_slug = "general"
    return wing, r_slug


# ── 1. СТАТУС И ДЕРЕВО ПАМЯТИ ────────────────────────────────────────────────
def action_status():
    print(f"\n{C_BOLD}======================================================={C_RESET}")
    print(f"  {C_CYAN}🏛️  СТАТУС И СТРУКТУРА ПАМЯТИ MEMPALACE{C_RESET}")
    print(f"{C_BOLD}======================================================={C_RESET}")

    chroma_db = PATHS["chroma_db"]
    if not os.path.isfile(chroma_db):
        print(f"{C_RED}❌ База данных ChromaDB не найдена по пути:{C_RESET} {chroma_db}")
        return

    try:
        conn = sqlite3.connect(chroma_db)
        cur = conn.cursor()
        cur.execute("""
            SELECT
                w.string_value AS wing,
                r.string_value AS room,
                count(*) AS cnt
            FROM embedding_metadata w
            JOIN embedding_metadata r ON w.id = r.id AND r.key = 'room'
            WHERE w.key = 'wing'
            GROUP BY wing, room
            ORDER BY wing, cnt DESC;
        """)
        rows = cur.fetchall()
        conn.close()
    except Exception as e:
        print(f"{C_RED}❌ Ошибка чтения ChromaDB: {e}{C_RESET}")
        return

    if not rows:
        print(f"{C_YELLOW}ℹ️ База данных пока пуста.{C_RESET}")
        return

    by_wing = {}
    total_drawers = 0
    for w, r, cnt in rows:
        by_wing.setdefault(w, []).append((r, cnt))
        total_drawers += cnt

    print(f"📊 Всего ящиков в базе: {C_GREEN}{total_drawers:,}{C_RESET}")
    print(f"🌐 Активных крыльев: {C_GREEN}{len(by_wing)}{C_RESET}\n")

    for w, rooms in sorted(by_wing.items()):
        wing_total = sum(c for _, c in rooms)
        w_title = format_wing(w)
        print(f"{C_BOLD}{w_title}{C_RESET} {C_DIM}({w}) — {wing_total} ящиков:{C_RESET}")
        for r, cnt in rooms:
            r_title = format_room(r)
            print(f"   └── 🚪 {r_title:32} {C_CYAN}{cnt:4} ящ.{C_RESET} {C_DIM}(id: {r}){C_RESET}")
        print()

    # Сводка по папке заметок
    notes_dir = PATHS["notes_dir"]
    if notes_dir and os.path.isdir(notes_dir):
        count_files = sum(
            1 for root, _, files in os.walk(notes_dir)
            for f in files if f.endswith((".txt", ".md")) and not f.startswith(".")
        )
        print(f"📁 Исходных заметок на диске ({notes_dir}): {C_GREEN}{count_files}{C_RESET}")
    print(f"{C_BOLD}======================================================={C_RESET}")


# ── 2. УМНЫЙ ИМПОРТ ИЗ APPLE NOTES ───────────────────────────────────────────
def action_import_apple_notes():
    print(f"\n{C_BOLD}======================================================={C_RESET}")
    print(f"  {C_CYAN}📥 УМНЫЙ ИМПОРТ ИЗ APPLE NOTES С АВТОРАЗМЕТКОЙ{C_RESET}")
    print(f"{C_BOLD}======================================================={C_RESET}")

    import_script = os.path.join(os.path.dirname(__file__), "import_notes.py")
    if not os.path.isfile(import_script):
        # Ищем в стандартных местах
        for cand in [
            os.path.join(PATHS["palace_dir"] or "", "_scripts", "import_notes.py"),
            os.path.join(PATHS["bot_dir"] or "", "_scripts", "import_notes.py"),
        ]:
            if os.path.isfile(cand):
                import_script = cand
                break

    if os.path.isfile(import_script):
        env = os.environ.copy()
        if PATHS["bot_dir"]:
            env["BOT_DIR"] = PATHS["bot_dir"]
            env["PYTHONPATH"] = PATHS["bot_dir"] + os.pathsep + env.get("PYTHONPATH", "")
        subprocess.run([PATHS["venv_python"], import_script], env=env)
    else:
        print(f"{C_RED}❌ Файл import_notes.py не найден.{C_RESET}")


# ── 3. СИНХРОНИЗАЦИЯ И МАЙНИНГ ───────────────────────────────────────────────
def action_sync_mine():
    print(f"\n{C_BOLD}======================================================={C_RESET}")
    print(f"  {C_CYAN}⚡ СИНХРОНИЗАЦИЯ И МАЙНИНГ ЗАМЕТОК ПО КРЫЛЬЯМ{C_RESET}")
    print(f"{C_BOLD}======================================================={C_RESET}")

    notes_dir = PATHS["notes_dir"]
    if not notes_dir or not os.path.isdir(notes_dir):
        print(f"{C_RED}❌ Папка заметок не найдена:{C_RESET} {notes_dir}")
        return

    palace_dir = PATHS["palace_dir"]
    venv_py = PATHS["venv_python"]

    # Карта основных подпапок -> крылья
    subfolders = [d for d in os.listdir(notes_dir) if os.path.isdir(os.path.join(notes_dir, d))]
    print(f"📂 Найдено тематических папок: {len(subfolders)}\n")

    for sf in sorted(subfolders):
        fpath = os.path.join(notes_dir, sf)
        wing, _ = categorize_file(fpath)
        print(f"⛏️  Майнинг: {C_BOLD}{sf}{C_RESET} → Крыло: {C_GREEN}{wing}{C_RESET}")
        cmd = [
            venv_py, "-m", "mempalace", "mine", fpath,
            "--wing", wing,
            "--mode", "projects",
        ]
        res = subprocess.run(cmd, cwd=palace_dir, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"   {C_RED}⚠️ Ошибка:{C_RESET} {res.stderr.strip()[:150]}")
        else:
            print(f"   {C_GREEN}✅ Успешно замайнено{C_RESET}")

    # Корневые файлы my_notes
    root_files = [
        f for f in os.listdir(notes_dir)
        if os.path.isfile(os.path.join(notes_dir, f)) and f.endswith((".txt", ".md"))
    ]
    if root_files:
        print(f"\n⛏️  Майнинг корневых файлов my_notes ({len(root_files)} шт.)...")
        cmd = [
            venv_py, "-m", "mempalace", "mine", notes_dir,
            "--wing", "personal",
            "--mode", "projects",
        ]
        subprocess.run(cmd, cwd=palace_dir)

    print(f"\n{C_GREEN}✅ Синхронизация завершена!{C_RESET}")
    action_status()


# ── 4. AI-РЕОРГАНИЗАЦИЯ БАЗЫ (DRY RUN & APPLY) ───────────────────────────────
def action_reorganize_palace():
    print(f"\n{C_BOLD}======================================================={C_RESET}")
    print(f"  {C_CYAN}🧠 AI-РЕОРГАНИЗАЦИЯ И РАЗМЕТКА ДВОРЦА ПАМЯТИ{C_RESET}")
    print(f"  {C_DIM}Распределяет все 1400+ ящиков по осмысленным комнатам и крыльям{C_RESET}")
    print(f"{C_BOLD}======================================================={C_RESET}")

    chroma_db = PATHS["chroma_db"]
    if not os.path.isfile(chroma_db):
        print(f"{C_RED}❌ База данных не найдена: {chroma_db}{C_RESET}")
        return

    conn = sqlite3.connect(chroma_db)
    cur = conn.cursor()

    # Запрашиваем все ящики с их source_file, wing, room
    cur.execute("""
        SELECT
            e.id,
            COALESCE(sf.string_value, '') AS source_file,
            COALESCE(w.string_value, 'my_notes') AS cur_wing,
            COALESCE(r.string_value, 'general') AS cur_room
        FROM embeddings e
        LEFT JOIN embedding_metadata sf ON e.id = sf.id AND sf.key = 'source_file'
        LEFT JOIN embedding_metadata w ON e.id = w.id AND w.key = 'wing'
        LEFT JOIN embedding_metadata r ON e.id = r.id AND r.key = 'room';
    """)
    rows = cur.fetchall()

    if not rows:
        print(f"{C_YELLOW}ℹ️ Ящиков в базе не обнаружено.{C_RESET}")
        conn.close()
        return

    print(f"🔍 Найдено ящиков для анализа: {C_GREEN}{len(rows):,}{C_RESET}\n")

    reclassifications = []
    summary = {}

    for row_id, sfile, cur_w, cur_r in rows:
        # Читаем текст фрагмента если нужно
        new_w, new_r = categorize_file(sfile)
        summary.setdefault(new_w, {}).setdefault(new_r, 0)
        summary[new_w][new_r] += 1
        reclassifications.append((row_id, new_w, new_r, cur_w, cur_r))

    print(f"{C_BOLD}📊 ПРЕДПРОСМОТР НОВОЙ СТРУКТУРЫ (DRY RUN):{C_RESET}")
    print("-------------------------------------------------------")
    for w, rooms in sorted(summary.items()):
        w_title = format_wing(w)
        w_total = sum(rooms.values())
        print(f"\n{C_BOLD}{w_title}{C_RESET} {C_DIM}({w}) — {w_total} ящиков:{C_RESET}")
        for r, cnt in sorted(rooms.items(), key=lambda x: x[1], reverse=True):
            r_title = format_room(r)
            print(f"   └── 🚪 {r_title:32} {C_CYAN}{cnt:4} ящ.{C_RESET} {C_DIM}(id: {r}){C_RESET}")

    print("\n-------------------------------------------------------")
    print(
        f"{C_YELLOW}⚠️ Внимание:{C_RESET} Метаданные {len(reclassifications)} "
        "ящиков будут обновлены прямо в базе."
    )
    prompt_text = f"\n{C_BOLD}Применить эту структуру к базе данных? (y/N): {C_RESET}"
    confirm = input(prompt_text).strip().lower()

    if confirm != "y":
        print(f"{C_DIM}ℹ️ Реорганизация отменена пользователем.{C_RESET}")
        conn.close()
        return

    print("\n💾 Применяю изменения в ChromaDB...")
    try:
        cur.execute("BEGIN TRANSACTION;")
        updated = 0
        for row_id, new_w, new_r, cur_w, cur_r in reclassifications:
            # Обновляем или вставляем wing
            cur.execute("""
                INSERT INTO embedding_metadata (id, key, string_value)
                VALUES (?, 'wing', ?)
                ON CONFLICT(id, key) DO UPDATE SET string_value = excluded.string_value;
            """, (row_id, new_w))

            # Обновляем или вставляем room
            cur.execute("""
                INSERT INTO embedding_metadata (id, key, string_value)
                VALUES (?, 'room', ?)
                ON CONFLICT(id, key) DO UPDATE SET string_value = excluded.string_value;
            """, (row_id, new_r))
            updated += 1

        conn.commit()
        print(f"{C_GREEN}✅ Успешно обновлено {updated:,} ящиков!{C_RESET}")
    except Exception as e:
        conn.rollback()
        print(f"{C_RED}❌ Ошибка записи в БД: {e}{C_RESET}")
    finally:
        conn.close()

    print("\n🎉 Дворец Памяти успешно реорганизован!")
    action_status()


# ── 5. ИНТЕРАКТИВНЫЙ ПОИСК ───────────────────────────────────────────────────
def action_search():
    print(f"\n{C_BOLD}======================================================={C_RESET}")
    print(f"  {C_CYAN}🔍 ПОИСК ПО ДВОРЦУ ПАМЯТИ{C_RESET}")
    print(f"{C_BOLD}======================================================={C_RESET}")

    query = input(f"{C_BOLD}Введите поисковый запрос (или Enter для отмены): {C_RESET}").strip()
    if not query:
        return

    print("\nВыберите фильтр по крылу:")
    print("  0. 🌐 Все крылья")
    print("  1. 🏛️ Философия (philosophy)")
    print("  2. 🧠 Психология (psychology)")
    print("  3. 📷 Фотография (photography)")
    print("  4. 🎨 Творчество (creative)")
    print("  5. 👤 Личные мысли (personal)")
    print("  6. 💼 Проекты (projects)")

    wing_choice = input(f"{C_BOLD}Ваш выбор (0-6): {C_RESET}").strip()
    wing_map = {
        "1": "philosophy",
        "2": "psychology",
        "3": "photography",
        "4": "creative",
        "5": "personal",
        "6": "projects",
    }
    wing = wing_map.get(wing_choice)

    palace_dir = PATHS["palace_dir"]
    venv_py = PATHS["venv_python"]
    cmd = [venv_py, "-m", "mempalace", "search", query, "--results", "8"]
    if wing:
        cmd.extend(["--wing", wing])

    print(f"\n{C_DIM}Выполняю поиск...{C_RESET}\n")
    res = subprocess.run(cmd, cwd=palace_dir, capture_output=True, text=True)
    if res.stdout:
        print(res.stdout)
    else:
        print(f"{C_YELLOW}По запросу ничего не найдено.{C_RESET}")


# ── 6. ГРАФ ЗНАНИЙ (KNOWLEDGE GRAPH) ─────────────────────────────────────────
def action_knowledge_graph():
    print(f"\n{C_BOLD}======================================================={C_RESET}")
    print(f"  {C_CYAN}🕸️  ГРАФ ЗНАНИЙ И СУЩНОСТИ MEMPALACE{C_RESET}")
    print(f"{C_BOLD}======================================================={C_RESET}")

    kg_db = PATHS["kg_db"]
    if not os.path.isfile(kg_db):
        print(f"{C_YELLOW}ℹ️ База Knowledge Graph не найдена.{C_RESET}")
        return

    try:
        conn = sqlite3.connect(kg_db)
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM facts;")
        fact_count = cur.fetchone()[0]
        cur.execute("SELECT DISTINCT subject FROM facts LIMIT 25;")
        entities = [r[0] for r in cur.fetchall()]
        conn.close()

        print(f"📊 Всего связей (фактов) в графе: {C_GREEN}{fact_count:,}{C_RESET}")
        print(f"\n{C_BOLD}Примеры сущностей и авторов:{C_RESET}")
        for e in entities:
            print(f"  • {e}")
    except Exception as e:
        print(f"{C_RED}❌ Ошибка чтения Knowledge Graph: {e}{C_RESET}")


# ── 7. УПРАВЛЕНИЕ TELEGRAM-БОТОМ ─────────────────────────────────────────────
def action_bot_manager():
    print(f"\n{C_BOLD}======================================================={C_RESET}")
    print(f"  {C_CYAN}🤖 УПРАВЛЕНИЕ TELEGRAM-БОТОМ MEMPALACE{C_RESET}")
    print(f"{C_BOLD}======================================================={C_RESET}")

    bot_cmd = os.path.join(os.path.dirname(__file__), "PalaceManager_TelegrammBot.command")
    if not os.path.isfile(bot_cmd):
        cmd_name = "PalaceManager_TelegrammBot.command"
        for cand in [
            os.path.join(PATHS["palace_dir"] or "", "_scripts", cmd_name),
            os.path.join(PATHS["bot_dir"] or "", "_scripts", cmd_name),
        ]:
            if os.path.isfile(cand):
                bot_cmd = cand
                break

    if os.path.isfile(bot_cmd):
        subprocess.run(["bash", bot_cmd])
    else:
        print(f"{C_RED}❌ Скрипт PalaceManager_TelegrammBot.command не найден.{C_RESET}")


# ── 8. ОБСЛУЖИВАНИЕ И РЕЗЕРВНАЯ КОПИЯ ─────────────────────────────────────────
def action_maintenance():
    print(f"\n{C_BOLD}======================================================={C_RESET}")
    print(f"  {C_CYAN}🧹 ОБСЛУЖИВАНИЕ И РЕЗЕРВНОЕ КОПИРОВАНИЕ{C_RESET}")
    print(f"{C_BOLD}======================================================={C_RESET}")

    data_dir = PATHS["data_dir"]
    palace_dir = os.path.join(data_dir, "palace")

    print("1. 📦 Создать резервную копию базы (Backup .tar.gz)")
    print("2. 🧹 Очистить временные кэши и логи")
    print("0. ◀️ Назад")

    sub = input(f"\n{C_BOLD}Ваш выбор (0-2): {C_RESET}").strip()
    if sub == "1":
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.expanduser(f"~/Documents/mempalace_backup_{ts}.tar.gz")
        print(f"📦 Архивирую {palace_dir}...")
        try:
            with tarfile.open(backup_file, "w:gz") as tar:
                tar.add(palace_dir, arcname="palace")
            print(f"{C_GREEN}✅ Резервная копия создана:{C_RESET} {backup_file}")
        except Exception as e:
            print(f"{C_RED}❌ Ошибка создания бэкапа: {e}{C_RESET}")
    elif sub == "2":
        print("🧹 Очищаю кэши...")
        for cache_folder in [
            os.path.join(PATHS["palace_dir"] or "", "web_search_cache"),
            os.path.join(PATHS["palace_dir"] or "", "temp_media"),
        ]:
            if os.path.isdir(cache_folder):
                shutil.rmtree(cache_folder, ignore_errors=True)
                os.makedirs(cache_folder, exist_ok=True)
        print(f"{C_GREEN}✅ Временные файлы очищены.{C_RESET}")


# ── ГЛАВНОЕ МЕНЮ ─────────────────────────────────────────────────────────────
def main_menu():
    while True:
        border = f"{C_CYAN}" + "=" * 55 + f"{C_RESET}"
        print(f"\n{border}")
        print(f"  {C_BOLD}🏰  MEMPALACE MASTER STUDIO — Центр Управления{C_RESET}")
        print(f"{border}")
        palace_p = PATHS["palace_dir"] or "Не найдена"
        bot_p = PATHS["bot_dir"] or "Не найден"
        print(f"{C_DIM}  Папка: {palace_p} | Бот: {bot_p}{C_RESET}\n")

        print(f"  {C_GREEN}[1]{C_RESET} 📊 {C_BOLD}Статус и Дерево Памяти{C_RESET}")
        print(f"  {C_GREEN}[2]{C_RESET} 📥 {C_BOLD}Умный импорт из Apple Notes{C_RESET}")
        print(f"  {C_GREEN}[3]{C_RESET} ⚡ {C_BOLD}Быстрая синхронизация и майнинг{C_RESET}")
        print(f"  {C_GREEN}[4]{C_RESET} 🧠 {C_BOLD}AI-Реорганизация базы (Комнаты){C_RESET}")
        print(f"  {C_GREEN}[5]{C_RESET} 🔍 {C_BOLD}Интерактивный поиск по Дворцу{C_RESET}")
        print(f"  {C_GREEN}[6]{C_RESET} 🕸️  {C_BOLD}Граф Знаний (Tunnels, сущности){C_RESET}")
        print(f"  {C_GREEN}[7]{C_RESET} 🤖 {C_BOLD}Управление Telegram-Ботом{C_RESET}")
        print(f"  {C_GREEN}[8]{C_RESET} 🧹 {C_BOLD}Обслуживание и Резервная копия{C_RESET}")
        print(f"  {C_RED}[0]{C_RESET} 🚪 {C_BOLD}Выход{C_RESET}\n")

        choice = input(f"{C_BOLD}Выберите пункт (0-8): {C_RESET}").strip()

        if choice == "1":
            action_status()
        elif choice == "2":
            action_import_apple_notes()
        elif choice == "3":
            action_sync_mine()
        elif choice == "4":
            action_reorganize_palace()
        elif choice == "5":
            action_search()
        elif choice == "6":
            action_knowledge_graph()
        elif choice == "7":
            action_bot_manager()
        elif choice == "8":
            action_maintenance()
        elif choice in ("0", "exit", "q"):
            print(f"\n{C_CYAN}До встречи в Дворце Памяти! 👋{C_RESET}\n")
            break
        else:
            print(f"{C_RED}⚠️ Неверный пункт меню, попробуйте ещё раз.{C_RESET}")

        input(f"\n{C_DIM}Нажмите Enter, чтобы вернуться в меню...{C_RESET}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower().strip()
        if arg in ("status", "1"):
            action_status()
        elif arg in ("import", "2"):
            action_import_apple_notes()
        elif arg in ("sync", "mine", "3"):
            action_sync_mine()
        elif arg in ("reorganize", "audit", "4"):
            action_reorganize_palace()
        elif arg in ("search", "find", "5"):
            action_search()
        elif arg in ("graph", "tunnels", "6"):
            action_knowledge_graph()
        elif arg in ("bot", "7"):
            action_bot_manager()
        elif arg in ("maintenance", "backup", "8"):
            action_maintenance()
        else:
            main_menu()
    else:
        main_menu()
