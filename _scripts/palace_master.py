#!/usr/bin/env python3
"""palace_master.py — Единый центр управления базой знаний MemPalace.

Работает из ЛЮБОГО места в системе и сам автоматически находит:
- Корень бота: mempalace_bot
- Корень хранилища и заметок: mempalace
- Данные ChromaDB и графа: ~/.mempalace
- Окружение Python: venv
"""

import datetime
import json
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
        if PATHS["palace_dir"]:
            env["MEMPALACE_DIR"] = PATHS["palace_dir"]
        try:
            subprocess.run([PATHS["venv_python"], import_script], env=env)
        except KeyboardInterrupt:
            print(f"\n{C_YELLOW}↩️ Возврат в меню MemPalace...{C_RESET}")
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
    print(f"  {C_CYAN}🕸️  ГРАФ ЗНАНИЙ И ТУННЕЛИ MEMPALACE{C_RESET}")
    print(f"{C_BOLD}======================================================={C_RESET}")

    kg_db = PATHS["kg_db"]
    if not os.path.isfile(kg_db):
        print(f"{C_YELLOW}ℹ️ База Knowledge Graph не найдена по пути: {kg_db}{C_RESET}")
        return

    try:
        conn = sqlite3.connect(kg_db)
        cur = conn.cursor()

        cur.execute("SELECT count(*) FROM entities;")
        ent_count = cur.fetchone()[0]

        cur.execute("SELECT count(*) FROM triples;")
        triple_count = cur.fetchone()[0]

        print(f"📊 Концептов и сущностей (Entities): {C_GREEN}{ent_count:,}{C_RESET}")
        print(f"🔗 Смысловых связей (Triples / Tunnels): {C_GREEN}{triple_count:,}{C_RESET}\n")

        # Примеры сущностей
        cur.execute("SELECT name, type FROM entities ORDER BY created_at DESC LIMIT 10;")
        recent_ents = cur.fetchall()
        if recent_ents:
            print(f"{C_BOLD}Примеры сущностей:{C_RESET}")
            for name, etype in recent_ents:
                type_badge = f"{C_DIM}[{etype}]{C_RESET}" if etype and etype != "unknown" else ""
                print(f"  • {C_BOLD}{name}{C_RESET} {type_badge}")
            print()

        # Примеры связей
        cur.execute("""
            SELECT subject, predicate, object
            FROM triples
            ORDER BY extracted_at DESC
            LIMIT 6;
        """)
        sample_triples = cur.fetchall()
        if sample_triples:
            print(f"{C_BOLD}Примеры семантических связей (Туннелей):{C_RESET}")
            for s, p, o in sample_triples:
                rel = f"{C_CYAN}{s}{C_RESET} ─({C_YELLOW}{p}{C_RESET})─▶ {C_GREEN}{o}{C_RESET}"
                print(f"  • {rel}")
            print()

        # Интерактивный поиск связей
        while True:
            q = input(
                f"\n{C_BOLD}Поиск связей сущности (или Enter для выхода): {C_RESET}"
            ).strip()
            if not q:
                break

            cur.execute("""
                SELECT subject, predicate, object
                FROM triples
                WHERE subject LIKE ? OR object LIKE ? OR predicate LIKE ?
                LIMIT 15;
            """, (f"%{q}%", f"%{q}%", f"%{q}%"))
            results = cur.fetchall()

            if results:
                print(f"\n{C_GREEN}Найдено связей: {len(results)}{C_RESET}")
                for s, p, o in results:
                    rel = f"{C_CYAN}{s}{C_RESET} ─({C_YELLOW}{p}{C_RESET})─▶ {C_GREEN}{o}{C_RESET}"
                    print(f"  • {rel}")
            else:
                print(f"{C_YELLOW}Связей по запросу '{q}' не найдено.{C_RESET}")

        conn.close()
    except Exception as e:
        print(f"{C_RED}❌ Ошибка чтения Knowledge Graph: {e}{C_RESET}")


# ── 7. УПРАВЛЕНИЕ МОДЕЛЯМИ ИИ (OLLAMA & CLOUD) ──────────────────────────────
def _get_models_json_path() -> str:
    p_dir = PATHS["palace_dir"] or os.path.expanduser("~/Documents/mempalace")
    return os.path.join(p_dir, "models.json")


def _get_current_ai_path() -> str:
    p_dir = PATHS["palace_dir"] or os.path.expanduser("~/Documents/mempalace")
    return os.path.join(p_dir, ".current_ai")


def load_models_config() -> dict:
    fpath = _get_models_json_path()
    if not os.path.isfile(fpath):
        return {"ollama": [], "openai": [], "gemini": []}
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {"ollama": [], "openai": [], "gemini": []}
            data.setdefault("ollama", [])
            data.setdefault("openai", [])
            data.setdefault("gemini", [])
            return data
    except Exception as e:
        print(f"{C_RED}Ошибка чтения models.json: {e}{C_RESET}")
        return {"ollama": [], "openai": [], "gemini": []}


def save_models_config(cfg: dict) -> bool:
    fpath = _get_models_json_path()
    try:
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"{C_RED}Ошибка записи models.json: {e}{C_RESET}")
        return False


def get_current_ai_model() -> str:
    fpath = _get_current_ai_path()
    if os.path.isfile(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
    return "Не установлена"


def set_current_ai_model(tag: str) -> bool:
    fpath = _get_current_ai_path()
    try:
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(tag.strip() + "\n")
        return True
    except Exception as e:
        print(f"{C_RED}Ошибка сохранения .current_ai: {e}{C_RESET}")
        return False


def get_ollama_installed_tags() -> list[str]:
    try:
        res = subprocess.run(["ollama", "list"], capture_output=True, text=True)
        if res.returncode != 0:
            return []
        lines = res.stdout.strip().split("\n")
        tags = []
        for line in lines[1:]:
            parts = line.split()
            if parts:
                tags.append(parts[0])
        return tags
    except Exception:
        return []


def action_manage_ai_models():
    while True:
        cfg = load_models_config()
        current_ai = get_current_ai_model()

        print(f"\n{C_BOLD}======================================================={C_RESET}")
        print(f"  {C_CYAN}🎛️  УПРАВЛЕНИЕ МОДЕЛЯМИ ИИ (Ollama & Cloud){C_RESET}")
        print(f"{C_BOLD}======================================================={C_RESET}")
        print(f"Текущая активная модель: {C_GREEN}{C_BOLD}{current_ai}{C_RESET}\n")

        print("1. 🎯 Переключить активную модель")
        print("2. ⬇️  Скачать и установить модель Ollama (ollama pull)")
        print("3. 🔄 Синхронизировать с 'ollama list' (найти неучтённые)")
        print("4. ➕ Добавить облачную модель (Gemini / OpenAI)")
        print("5. 🗑️  Удалить модель из списка (и опционально с диска)")
        print("0. ◀️ Назад")

        choice = input(f"\n{C_BOLD}Выберите действие (0-5): {C_RESET}").strip()
        if choice in ("0", ""):
            break

        # 1. Переключение
        if choice == "1":
            all_models = []
            for m in cfg.get("ollama", []):
                all_models.append((f"🦙 Ollama: {m.get('name', m['tag'])}", m["tag"]))
            for m in cfg.get("gemini", []):
                all_models.append((f"💎 Gemini: {m.get('name', m['tag'])}", m["tag"]))
            for m in cfg.get("openai", []):
                all_models.append((f"🟢 OpenAI: {m.get('name', m['tag'])}", m["tag"]))

            if not all_models:
                print(f"{C_YELLOW}Список моделей пуст.{C_RESET}")
                continue

            print(f"\n{C_BOLD}Доступные модели:{C_RESET}")
            for idx, (label, tag) in enumerate(all_models, 1):
                active = f" {C_GREEN}◀ [АКТИВНА]{C_RESET}" if tag == current_ai else ""
                print(f"  {idx:2d}) {label} {C_DIM}({tag}){C_RESET}{active}")

            c = input(f"\n{C_BOLD}Выберите номер (1-{len(all_models)}): {C_RESET}").strip()
            if c.isdigit() and 1 <= int(c) <= len(all_models):
                chosen_tag = all_models[int(c) - 1][1]
                if set_current_ai_model(chosen_tag):
                    print(f"\n{C_GREEN}✅ Активная модель переключена на: {chosen_tag}{C_RESET}")

        # 2. Ollama pull
        elif choice == "2":
            print(f"\n{C_BOLD}Рекомендуемые модели для скачивания:{C_RESET}")
            recs = [
                ("qwen2.5:7b", "Быстрая, отличный русский язык, 4.7 GB"),
                ("qwen2.5:14b", "Глубокое мышление, высокая точность, 9.0 GB"),
                ("llama3.2:3b", "Сверхлёгкая, моментальный отклик, 2.0 GB"),
                ("mistral:7b", "Классика открытых моделей, 4.1 GB"),
                ("phi4:14b", "Сильная логика и рассуждения от Microsoft, 9.1 GB"),
            ]
            for idx, (rtag, rdesc) in enumerate(recs, 1):
                print(f"  {idx}) {C_CYAN}{rtag:14}{C_RESET} — {rdesc}")
            print("  0) Ввести другой тег вручную")

            r_choice = input(f"\n{C_BOLD}Ваш выбор (0-{len(recs)}): {C_RESET}").strip()
            if r_choice.isdigit() and 1 <= int(r_choice) <= len(recs):
                tag_to_pull = recs[int(r_choice) - 1][0]
            else:
                prompt_tag = f"{C_BOLD}Введите тег Ollama (напр., llama3.2:latest): {C_RESET}"
                tag_to_pull = input(prompt_tag).strip()

            if not tag_to_pull:
                continue

            print(f"\n⬇️  Запускаю скачивание {C_BOLD}{tag_to_pull}{C_RESET} через Ollama...")
            res = subprocess.run(["ollama", "pull", tag_to_pull])
            if res.returncode == 0:
                print(f"\n{C_GREEN}✅ Модель {tag_to_pull} успешно скачана!{C_RESET}")
                existing_tags = [m["tag"] for m in cfg.get("ollama", [])]
                if tag_to_pull not in existing_tags:
                    name_input = input(f"Название для меню (Enter = '{tag_to_pull}'): ").strip()
                    cfg["ollama"].append({
                        "name": name_input or tag_to_pull,
                        "tag": tag_to_pull,
                        "desc": "Загружено через PalaceMaster",
                    })
                    save_models_config(cfg)
                act = input("Сделать эту модель активной прямо сейчас? (Y/n): ").strip().lower()
                if act in ("y", "yes", ""):
                    set_current_ai_model(tag_to_pull)
                    print(f"{C_GREEN}✅ Модель {tag_to_pull} установлена активной!{C_RESET}")
            else:
                print(f"{C_RED}❌ Ошибка скачивания модели {tag_to_pull}.{C_RESET}")

        # 3. Синхронизация с ollama list
        elif choice == "3":
            installed = get_ollama_installed_tags()
            if not installed:
                print(f"{C_YELLOW}Ollama не запущена или список моделей пуст.{C_RESET}")
                continue

            existing_tags = set(m["tag"] for m in cfg.get("ollama", []))
            untracked = [t for t in installed if t not in existing_tags]

            if not untracked:
                total_cnt = len(installed)
                print(f"{C_GREEN}✅ Все модели Ollama ({total_cnt} шт.) уже есть в меню.{C_RESET}")
            else:
                total_u = len(untracked)
                print(
                    f"\n{C_BOLD}Найдено моделей на диске, отсутствующих в меню "
                    f"({total_u} шт.):{C_RESET}"
                )
                for idx, t in enumerate(untracked, 1):
                    print(f"  {idx}) {t}")
                add_all = input("\nДобавить все эти модели в меню? (Y/n): ").strip().lower()
                if add_all in ("y", "yes", ""):
                    for t in untracked:
                        cfg["ollama"].append({
                            "name": t,
                            "tag": t,
                            "desc": "Обнаружено через ollama list",
                        })
                    save_models_config(cfg)
                    print(f"{C_GREEN}✅ Добавлено {len(untracked)} моделей в меню!{C_RESET}")

        # 4. Добавление облачной модели
        elif choice == "4":
            print("\n1. 💎 Google Gemini")
            print("2. 🟢 OpenAI / ChatGPT")
            provider_ch = input("Выберите провайдера (1-2): ").strip()
            group = "gemini" if provider_ch == "1" else "openai" if provider_ch == "2" else None
            if not group:
                continue

            name = input("Название модели (например, 'Gemini 3 Flash'): ").strip()
            prompt_c_tag = "Тег модели (например, 'gemini-3.1-pro-preview'): "
            tag = input(prompt_c_tag).strip()
            if name and tag:
                cfg[group].append({
                    "name": name,
                    "tag": tag,
                    "desc": "Облачная модель",
                })
                save_models_config(cfg)
                print(f"{C_GREEN}✅ Модель {name} ({tag}) добавлена!{C_RESET}")
                act = input("Сделать её активной сейчас? (Y/n): ").strip().lower()
                if act in ("y", "yes", ""):
                    set_current_ai_model(tag)

        # 5. Удаление модели
        elif choice == "5":
            all_entries = []
            for m in cfg.get("ollama", []):
                all_entries.append(("ollama", m))
            for m in cfg.get("gemini", []):
                all_entries.append(("gemini", m))
            for m in cfg.get("openai", []):
                all_entries.append(("openai", m))

            if not all_entries:
                print(f"{C_YELLOW}Список моделей пуст.{C_RESET}")
                continue

            print(f"\n{C_BOLD}Какую модель удалить из меню?{C_RESET}")
            for idx, (group, m) in enumerate(all_entries, 1):
                print(f"  {idx}) [{group.upper()}] {m.get('name', m['tag'])} ({m['tag']})")

            del_ch = input(f"\nВыберите номер (1-{len(all_entries)}, 0 для отмены): ").strip()
            if del_ch.isdigit() and 1 <= int(del_ch) <= len(all_entries):
                group, m = all_entries[int(del_ch) - 1]
                tag = m["tag"]
                cfg[group] = [x for x in cfg[group] if x.get("tag") != tag]
                save_models_config(cfg)
                print(f"{C_GREEN}✅ Модель {tag} удалена из меню.{C_RESET}")

                if group == "ollama":
                    rm_disk_prompt = (
                        f"Удалить также файл весов с диска через 'ollama rm {tag}'? (y/N): "
                    )
                    rm_disk = input(rm_disk_prompt).strip().lower()
                    if rm_disk == "y":
                        subprocess.run(["ollama", "rm", tag])
                        print(f"{C_GREEN}✅ Модель {tag} удалена с диска.{C_RESET}")


# ── 8. АРХИВАЦИЯ ЧАТОВ И ДОБАВЛЕНИЕ МЫСЛЕЙ В БАЗУ ────────────────────────────
def action_chats_and_thoughts():
    while True:
        print(f"\n{C_BOLD}======================================================={C_RESET}")
        print(f"  {C_CYAN}💬 АРХИВАЦИЯ ЧАТОВ И ДОБАВЛЕНИЕ МЫСЛЕЙ В БАЗУ{C_RESET}")
        print(f"{C_BOLD}======================================================={C_RESET}")

        print("1. 💬 Архивировать Telegram-чат в заметку Дворца")
        print("2. 💡 Быстрая запись мысли / инсайта в Дворец Памяти")
        print("3. 📦 Перенести обработанные JSON-чаты в архив")
        print("0. ◀️ Назад")

        sub = input(f"\n{C_BOLD}Ваш выбор (0-3): {C_RESET}").strip()
        if sub in ("0", ""):
            break
        elif sub == "1":
            _archive_chat_dialog()
        elif sub == "2":
            _quick_add_thought()
        elif sub == "3":
            _archive_raw_chats()


def _archive_chat_dialog():
    chats_dir = os.path.join(PATHS["palace_dir"] or "", "chats")
    notes_dir = PATHS["notes_dir"] or os.path.join(PATHS["palace_dir"] or "", "my_notes")

    if not os.path.isdir(chats_dir):
        print(f"{C_YELLOW}Папка чатов не найдена: {chats_dir}{C_RESET}")
        return

    json_files = [f for f in os.listdir(chats_dir) if f.endswith(".json")]
    if not json_files:
        print(f"{C_YELLOW}В папке chats пока нет JSON-файлов диалогов.{C_RESET}")
        return

    json_files.sort(key=lambda x: -os.path.getmtime(os.path.join(chats_dir, x)))

    print(f"\n{C_BOLD}Найденные диалоги:{C_RESET}")
    for idx, jf in enumerate(json_files[:15], 1):
        fpath = os.path.join(chats_dir, jf)
        size_kb = os.path.getsize(fpath) / 1024
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%d %H:%M")
        print(f"  {idx:2d}) {jf:35} {C_CYAN}{size_kb:5.1f} KB{C_RESET} {C_DIM}({mtime}){C_RESET}")

    c = input(f"\n{C_BOLD}Выберите номер чата (1-{min(15, len(json_files))}): {C_RESET}").strip()
    if not c.isdigit() or not (1 <= int(c) <= min(15, len(json_files))):
        return

    chosen_file = json_files[int(c) - 1]
    chosen_path = os.path.join(chats_dir, chosen_file)

    try:
        with open(chosen_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        print(f"{C_RED}Ошибка чтения {chosen_file}: {e}{C_RESET}")
        return

    if isinstance(raw, dict):
        messages = raw.get("messages", [])
    elif isinstance(raw, list):
        messages = raw
    else:
        messages = []

    if not messages:
        print(f"{C_YELLOW}В выбранном чате нет сообщений.{C_RESET}")
        return

    out_lines = [
        f"--- АРХИВ ДИАЛОГА: {chosen_file} ---",
        f"Дата переноса: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Всего реплик: {len(messages)}",
        "",
    ]
    for msg in messages:
        role = msg.get("role", "unknown")
        role_label = "ВЫ" if role in ("user", "human") else "AI"
        content = msg.get("content", "").strip()
        out_lines.append(f"[{role_label}]:\n{content}\n" + "-" * 30 + "\n")

    target_sub = os.path.join(notes_dir, "Мои мысли и размышления")
    os.makedirs(target_sub, exist_ok=True)
    target_name = f"Диалог_{os.path.splitext(chosen_file)[0]}.txt"
    target_path = os.path.join(target_sub, target_name)

    with open(target_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines))

    print(f"\n{C_GREEN}✅ Диалог успешно сохранён в заметку:{C_RESET} {target_path}")

    archive_dir = os.path.join(chats_dir, "archive")
    os.makedirs(archive_dir, exist_ok=True)
    shutil.move(chosen_path, os.path.join(archive_dir, chosen_file))
    print(f"{C_DIM}📁 Исходный JSON перемещён в chats/archive/{chosen_file}{C_RESET}")

    mine_now = input("\nЗамайнить эту заметку в память Дворца? (Y/n): ").strip().lower()
    if mine_now in ("y", "yes", ""):
        venv_py = PATHS["venv_python"]
        palace_dir = PATHS["palace_dir"]
        cmd = [
            venv_py, "-m", "mempalace", "mine", target_path,
            "--wing", "personal",
            "--mode", "projects",
        ]
        subprocess.run(cmd, cwd=palace_dir)
        print(f"{C_GREEN}✅ Память обновлена!{C_RESET}")


def _quick_add_thought():
    print(f"\n{C_BOLD}💡 БЫСТРАЯ ЗАПИСЬ МЫСЛИ / ИНСАЙТА В ДВОРЕЦ ПАМЯТИ{C_RESET}")
    print(f"{C_DIM}Заметка будет сохранена и автоматически замайнена в нужную комнату.{C_RESET}\n")

    title = input(f"{C_BOLD}Заголовок мысли (например, 'О природе сознания'): {C_RESET}").strip()
    if not title:
        print(f"{C_YELLOW}Заголовок не может быть пустым.{C_RESET}")
        return

    print(f"{C_BOLD}Текст мысли (введите текст, пустая строка для завершения):{C_RESET}")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == "":
            break
        lines.append(line)

    text = "\n".join(lines).strip()
    if not text:
        print(f"{C_YELLOW}Текст пуст, запись отменена.{C_RESET}")
        return

    print("\nВыберите категорию заметки:")
    print("  1. 👤 Личные мысли и размышления (personal)")
    print("  2. 🏛️ Философия (philosophy)")
    print("  3. 🧠 Психология и архетипы (psychology)")
    print("  4. 📷 Фотография и визуальное искусство (photography)")
    print("  5. 🎨 Творчество и сценарии (creative)")
    print("  6. 💡 Инсайт (insights)")

    c = input(f"{C_BOLD}Ваш выбор (1-6, Enter = 1): {C_RESET}").strip()
    cat_map = {
        "1": ("personal", "Мои мысли и размышления"),
        "2": ("philosophy", "Философия"),
        "3": ("psychology", "Проект Архитипы Юнга Социальная Маска"),
        "4": ("photography", "Фотографы"),
        "5": ("creative", "Мои стихи"),
        "6": ("insights", "insights"),
    }
    wing, folder = cat_map.get(c, ("personal", "Мои мысли и размышления"))

    notes_dir = PATHS["notes_dir"] or os.path.join(PATHS["palace_dir"] or "", "my_notes")
    if folder != "insights":
        target_dir = os.path.join(notes_dir, folder)
    else:
        target_dir = os.path.join(PATHS["palace_dir"] or "", "insights")
    os.makedirs(target_dir, exist_ok=True)

    safe_title = re.sub(r'[^\w\s\-]', '', title).strip()
    target_file = os.path.join(target_dir, f"{safe_title}.txt")

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    content = f"# {title}\nДата: {now_str}\nКатегория: {wing}\n\n{text}\n"

    with open(target_file, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"\n{C_GREEN}✅ Мысль сохранена в файл:{C_RESET} {target_file}")

    mine_now = input("Добавить в память Дворца Памяти прямо сейчас? (Y/n): ").strip().lower()
    if mine_now in ("y", "yes", ""):
        venv_py = PATHS["venv_python"]
        palace_dir = PATHS["palace_dir"]
        cmd = [
            venv_py, "-m", "mempalace", "mine", target_file,
            "--wing", wing,
            "--mode", "projects",
        ]
        subprocess.run(cmd, cwd=palace_dir)
        print(f"{C_GREEN}✅ Мысль оцифрована и добавлена во Дворец!{C_RESET}")


def _archive_raw_chats():
    chats_dir = os.path.join(PATHS["palace_dir"] or "", "chats")
    if not os.path.isdir(chats_dir):
        print(f"{C_YELLOW}Папка чатов не найдена.{C_RESET}")
        return

    json_files = [f for f in os.listdir(chats_dir) if f.endswith(".json")]
    if not json_files:
        print(f"{C_GREEN}Все чаты уже перемещены в архив.{C_RESET}")
        return

    archive_dir = os.path.join(chats_dir, "archive")
    os.makedirs(archive_dir, exist_ok=True)
    for jf in json_files:
        shutil.move(os.path.join(chats_dir, jf), os.path.join(archive_dir, jf))
    print(f"{C_GREEN}✅ Перемещено {len(json_files)} файлов чатов в chats/archive/{C_RESET}")


# ── 9. ОЧИСТКА, СЖАТИЕ И ОПТИМИЗАЦИЯ ПАМЯТИ ──────────────────────────────────
def action_memory_cleanup_and_optimize():
    while True:
        print(f"\n{C_BOLD}======================================================={C_RESET}")
        print(f"  {C_CYAN}🧹 ОЧИСТКА, СЖАТИЕ И ОПТИМИЗАЦИЯ ПАМЯТИ{C_RESET}")
        print(f"{C_BOLD}======================================================={C_RESET}")

        print("1. 🗜️  Сжатие базы данных (SQLite VACUUM) — экономит 30-50% места")
        print("2. 🧼 Санитарная чистка текстовой базы — удаление 0-байтных файлов")
        print("3. 🎯 Очистить ТОЛЬКО векторную базу — заметки в my_notes НЕ трогаются")
        print("4. 🗂️  Архивировать и очистить my_notes (с обязательным бэкапом)")
        print("5. 💣 Полный сброс всей памяти MemPalace (с автобэкапом)")
        print("6. 🧹 Очистить временные кэши и логи")
        print("7. 📦 Создать полную резервную копию базы (.tar.gz)")
        print("0. ◀️ Назад")

        sub = input(f"\n{C_BOLD}Ваш выбор (0-7): {C_RESET}").strip()
        if sub in ("0", ""):
            break
        elif sub == "1":
            _vacuum_databases()
        elif sub == "2":
            _clean_empty_and_system_files()
        elif sub == "3":
            _wipe_vector_db_only()
        elif sub == "4":
            _archive_and_wipe_notes()
        elif sub == "5":
            _full_reset_palace()
        elif sub == "6":
            _clean_temp_caches()
        elif sub == "7":
            _create_full_backup()


def _vacuum_databases():
    print(f"\n{C_BOLD}🗜️  СЖАТИЕ БАЗ ДАННЫХ (SQLITE VACUUM)...{C_RESET}")
    dbs = [PATHS["chroma_db"], PATHS["kg_db"]]
    total_saved = 0

    for db_path in dbs:
        if not os.path.isfile(db_path):
            continue
        fname = os.path.basename(db_path)
        size_before = os.path.getsize(db_path)
        try:
            conn = sqlite3.connect(db_path)
            conn.execute("VACUUM;")
            conn.close()
            size_after = os.path.getsize(db_path)
            diff = size_before - size_after
            total_saved += max(0, diff)
            pct = (diff / size_before * 100) if size_before else 0
            b_mb = size_before / 1024 / 1024
            a_mb = size_after / 1024 / 1024
            print(
                f"  • {fname:25}: {b_mb:5.1f} MB ➔ "
                f"{C_GREEN}{a_mb:5.1f} MB{C_RESET} "
                f"({C_CYAN}сжато на {pct:.1f}%{C_RESET})"
            )
        except Exception as e:
            print(f"  • {fname}: {C_RED}Ошибка: {e}{C_RESET}")

    saved_mb = total_saved / 1024 / 1024
    print(f"\n{C_GREEN}✅ Сжатие завершено! Освобождено: {saved_mb:.1f} MB.{C_RESET}")


def _clean_empty_and_system_files():
    notes_dir = PATHS["notes_dir"]
    if not notes_dir or not os.path.isdir(notes_dir):
        print(f"{C_RED}Папка my_notes не найдена.{C_RESET}")
        return

    empty_files = []
    junk_files = []

    for root, _, files in os.walk(notes_dir):
        for f in files:
            p = os.path.join(root, f)
            if f in (".DS_Store", "Thumbs.db") or f.startswith("._"):
                junk_files.append(p)
            elif os.path.isfile(p) and os.path.getsize(p) == 0:
                empty_files.append(p)

    total_junk = len(empty_files) + len(junk_files)
    if total_junk == 0:
        print(f"{C_GREEN}✅ База заметок чиста! Пустых и мусорных файлов не обнаружено.{C_RESET}")
        return

    print(f"\n{C_BOLD}Найдено для санитарной очистки:{C_RESET}")
    print(f"  • Пустых файлов (0 байт): {C_YELLOW}{len(empty_files)}{C_RESET}")
    print(f"  • Системного мусора (.DS_Store): {C_YELLOW}{len(junk_files)}{C_RESET}")

    if empty_files:
        print(f"\n{C_DIM}Примеры пустых файлов (0 байт):{C_RESET}")
        for p in empty_files[:5]:
            print(f"  • {os.path.relpath(p, notes_dir)}")

    confirm = input(
        f"\n{C_BOLD}Удалить эти {total_junk} пустых/мусорных файлов? (y/N): {C_RESET}"
    ).strip().lower()

    if confirm == "y":
        deleted = 0
        for p in empty_files + junk_files:
            try:
                os.remove(p)
                deleted += 1
            except Exception:
                pass
        print(f"{C_GREEN}✅ Удалено {deleted} файлов. Текстовая база оптимизирована!{C_RESET}")
    else:
        print(f"{C_DIM}Очистка отменена.{C_RESET}")


def _wipe_vector_db_only():
    palace_vector_dir = os.path.join(PATHS["data_dir"], "palace")
    print(f"\n{C_YELLOW}⚠️  ВНИМАНИЕ: Очистка ТОЛЬКО векторной базы{C_RESET}")
    print(f"Путь: {palace_vector_dir}")
    print(f"{C_GREEN}Заметки в my_notes НЕ пострадают и останутся нетронутыми.{C_RESET}")

    confirm = input(f"\n{C_BOLD}Сбросить векторную базу ChromaDB? (y/N): {C_RESET}").strip().lower()
    if confirm == "y":
        if os.path.isdir(palace_vector_dir):
            shutil.rmtree(palace_vector_dir, ignore_errors=True)
            print(f"{C_GREEN}✅ Векторная база сброшена.{C_RESET}")
            remine = input("Запустить быстрый майнинг my_notes заново? (Y/n): ").strip().lower()
            if remine in ("y", "yes", ""):
                action_sync_mine()


def _archive_and_wipe_notes():
    notes_dir = PATHS["notes_dir"]
    if not notes_dir or not os.path.isdir(notes_dir):
        print(f"{C_RED}Папка my_notes не найдена.{C_RESET}")
        return

    print(f"\n{C_RED}{C_BOLD}⚠️  ВНИМАНИЕ: ОЧИСТКА ПАПКИ MY_NOTES!{C_RESET}")
    print("Перед очисткой будет АВТОМАТИЧЕСКИ создан полный архив всех заметок.")

    prompt_wipe = f"{C_BOLD}Архивировать и очистить my_notes? (y/N): {C_RESET}"
    confirm = input(prompt_wipe).strip().lower()
    if confirm != "y":
        print(f"{C_DIM}Отменено.{C_RESET}")
        return

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_tar = os.path.expanduser(f"~/Documents/my_notes_archive_{ts}.tar.gz")

    print(f"📦 Создаю резервный архив в {backup_tar}...")
    try:
        with tarfile.open(backup_tar, "w:gz") as tar:
            tar.add(notes_dir, arcname="my_notes")
        print(f"{C_GREEN}✅ Резервный архив создан успешно!{C_RESET}")
    except Exception as e:
        print(f"{C_RED}❌ Ошибка создания архива: {e}. Очистка отменена.{C_RESET}")
        return

    for item in os.listdir(notes_dir):
        p = os.path.join(notes_dir, item)
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
        else:
            try:
                os.remove(p)
            except Exception:
                pass

    print(f"{C_GREEN}✅ Папка my_notes очищена. Архив сохранён в:{C_RESET} {backup_tar}")


def _full_reset_palace():
    data_dir = PATHS["data_dir"]
    print(f"\n{C_RED}{C_BOLD}💣 ПОЛНЫЙ СБРОС ВСЕЙ ПАМЯТИ MEMPALACE (~/.mempalace){C_RESET}")
    print("Будут удалены ChromaDB, Knowledge Graph и системные кэши.")

    phrase = input(f"Для подтверждения введите слово '{C_BOLD}RESET{C_RESET}': ").strip()
    if phrase != "RESET":
        print(f"{C_DIM}Сброс отменён.{C_RESET}")
        return

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.expanduser(f"~/Documents/mempalace_full_backup_{ts}.tar.gz")
    print(f"📦 Создаю полный защитный архив в {backup_file}...")
    try:
        with tarfile.open(backup_file, "w:gz") as tar:
            tar.add(data_dir, arcname=".mempalace")
        print(f"{C_GREEN}✅ Защитный архив создан.{C_RESET}")
    except Exception as e:
        print(f"{C_RED}❌ Ошибка архивации: {e}. Сброс отменён ради безопасности.{C_RESET}")
        return

    shutil.rmtree(data_dir, ignore_errors=True)
    os.makedirs(data_dir, exist_ok=True)
    print(f"{C_GREEN}✅ Все данные MemPalace сброшены. Память чиста.{C_RESET}")


def _clean_temp_caches():
    print("🧹 Очищаю кэши...")
    for cache_folder in [
        os.path.join(PATHS["palace_dir"] or "", "web_search_cache"),
        os.path.join(PATHS["palace_dir"] or "", "temp_media"),
    ]:
        if os.path.isdir(cache_folder):
            shutil.rmtree(cache_folder, ignore_errors=True)
            os.makedirs(cache_folder, exist_ok=True)
    print(f"{C_GREEN}✅ Временные файлы очищены.{C_RESET}")


def _create_full_backup():
    data_dir = PATHS["data_dir"]
    palace_dir = os.path.join(data_dir, "palace")
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.expanduser(f"~/Documents/mempalace_backup_{ts}.tar.gz")
    print(f"📦 Архивирую {palace_dir}...")
    try:
        with tarfile.open(backup_file, "w:gz") as tar:
            tar.add(palace_dir, arcname="palace")
        print(f"{C_GREEN}✅ Резервная копия создана:{C_RESET} {backup_file}")
    except Exception as e:
        print(f"{C_RED}❌ Ошибка создания бэкапа: {e}{C_RESET}")


# ── 10. УПРАВЛЕНИЕ TELEGRAM-БОТОМ ────────────────────────────────────────────
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
        try:
            subprocess.run(["bash", bot_cmd])
        except KeyboardInterrupt:
            print(f"\n{C_YELLOW}↩️ Возврат в меню MemPalace...{C_RESET}")
    else:
        print(f"{C_RED}❌ Скрипт PalaceManager_TelegrammBot.command не найден.{C_RESET}")


# ── ГЛАВНОЕ МЕНЮ ─────────────────────────────────────────────────────────────
def main_menu():
    while True:
        try:
            border = f"{C_CYAN}" + "=" * 55 + f"{C_RESET}"
            print(f"\n{border}")
            print(f"  {C_BOLD}🏰  MEMPALACE MASTER STUDIO — Центр Управления{C_RESET}")
            print(f"{border}")
            palace_p = PATHS["palace_dir"] or "Не найдена"
            bot_p = PATHS["bot_dir"] or "Не найден"
            cur_ai = get_current_ai_model()
            print(f"{C_DIM}  Папка: {palace_p} | Бот: {bot_p}{C_RESET}")
            print(f"{C_DIM}  Активная модель: {C_GREEN}{cur_ai}{C_RESET}\n")

            print(f"  {C_GREEN}[1]{C_RESET}  📊 {C_BOLD}Статус и Дерево Памяти{C_RESET}")
            print(f"  {C_GREEN}[2]{C_RESET}  📥 {C_BOLD}Умный импорт из Apple Notes{C_RESET}")
            print(f"  {C_GREEN}[3]{C_RESET}  ⚡ {C_BOLD}Быстрая синхронизация и майнинг{C_RESET}")
            print(f"  {C_GREEN}[4]{C_RESET}  🧠 {C_BOLD}AI-Реорганизация базы (Комнаты){C_RESET}")
            print(f"  {C_GREEN}[5]{C_RESET}  🔍 {C_BOLD}Интерактивный поиск по Дворцу{C_RESET}")
            print(f"  {C_GREEN}[6]{C_RESET}  🕸️  {C_BOLD}Граф Знаний (Tunnels, сущности){C_RESET}")
            print(f"  {C_GREEN}[7]{C_RESET}  🎛️  {C_BOLD}Модели ИИ (Ollama & Cloud){C_RESET}")
            print(f"  {C_GREEN}[8]{C_RESET}  💬 {C_BOLD}Архивация чатов и мысли в базу{C_RESET}")
            print(f"  {C_GREEN}[9]{C_RESET}  🧹 {C_BOLD}Очистка и Оптимизация памяти{C_RESET}")
            print(f"  {C_GREEN}[10]{C_RESET} 🤖 {C_BOLD}Управление Telegram-Ботом{C_RESET}")
            print(f"  {C_RED}[0]{C_RESET}  🚪 {C_BOLD}Выход{C_RESET}\n")

            choice = input(f"{C_BOLD}Выберите пункт (0-10): {C_RESET}").strip()
        except KeyboardInterrupt:
            print(f"\n\n{C_CYAN}🚪 Выход из MemPalace Studio. До встречи! 👋{C_RESET}\n")
            break

        try:
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
                action_manage_ai_models()
            elif choice == "8":
                action_chats_and_thoughts()
            elif choice == "9":
                action_memory_cleanup_and_optimize()
            elif choice == "10":
                action_bot_manager()
            elif choice in ("0", "exit", "q"):
                print(f"\n{C_CYAN}До встречи в Дворце Памяти! 👋{C_RESET}\n")
                break
            else:
                print(f"{C_RED}⚠️ Неверный пункт меню, попробуйте ещё раз.{C_RESET}")
        except KeyboardInterrupt:
            print(f"\n{C_YELLOW}↩️ Действие отменено пользователем.{C_RESET}")

        try:
            input(f"\n{C_DIM}Нажмите Enter, чтобы вернуться в меню...{C_RESET}")
        except KeyboardInterrupt:
            print()
            continue


if __name__ == "__main__":
    try:
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
            elif arg in ("models", "ai", "7"):
                action_manage_ai_models()
            elif arg in ("chats", "thoughts", "8"):
                action_chats_and_thoughts()
            elif arg in ("cleanup", "clean", "vacuum", "9"):
                action_memory_cleanup_and_optimize()
            elif arg in ("bot", "10"):
                action_bot_manager()
            else:
                main_menu()
        else:
            main_menu()
    except KeyboardInterrupt:
        print(f"\n\n{C_CYAN}🚪 Выход из MemPalace Studio. До встречи! 👋{C_RESET}\n")
        sys.exit(0)
