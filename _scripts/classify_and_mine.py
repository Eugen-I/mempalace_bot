"""classify_and_mine.py
Одноразовый скрипт: ИИ классифицирует все заметки по крыльям
и майнит их в MemPalace с соответствующим --wing.
"""

import asyncio
import logging
import os
import shutil
import sys
import tempfile

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

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("ClassifyAndMine")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Ищем корень проекта mempalace_bot (где лежит config.py)
BOT_DIR = None

# 1. Из переменной окружения
env_bot = os.environ.get("BOT_DIR")
if env_bot and os.path.isfile(os.path.join(env_bot, "config.py")):
    BOT_DIR = os.path.abspath(env_bot)

# 2. Из текущей рабочей директории (если запущено из BOT_DIR)
if not BOT_DIR:
    cwd = os.getcwd()
    if os.path.isfile(os.path.join(cwd, "config.py")):
        BOT_DIR = cwd

# 3. Стандартный путь проекта бота
if not BOT_DIR:
    default_bot = os.path.expanduser("~/Documents/mempalace_bot")
    if os.path.isfile(os.path.join(default_bot, "config.py")):
        BOT_DIR = default_bot

# 4. Поиск вверх по дереву каталогов от директории скрипта
if not BOT_DIR:
    candidate = SCRIPT_DIR
    for _ in range(6):
        if os.path.isfile(os.path.join(candidate, "config.py")):
            BOT_DIR = candidate
            break
        parent = os.path.dirname(candidate)
        if parent == candidate:
            break
        candidate = parent

if not BOT_DIR or not os.path.isfile(os.path.join(BOT_DIR, "config.py")):
    raise RuntimeError(
        "Не удалось найти директорию проекта mempalace_bot с файлом config.py. "
        "Убедитесь, что mempalace_bot находится в ~/Documents/mempalace_bot "
        "или задайте переменную BOT_DIR."
    )

if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)

from config import (  # noqa: E402
    DATA_DIR,
    INSIGHTS_DIR,
    NOTES_DIR,
    PDF_ARCHIVE_DIR,
    RESEARCH_DIR,
)
from services.ai_engine import (  # noqa: E402
    get_ai_response_async,
    get_current_ai,
)

WING_NAMES = ["dreams", "projects", "philosophy", "creative", "psychology"]

RUSSIAN_WING_MAP = {
    "сны": "dreams",
    "сновидения": "dreams",
    "сон": "dreams",
    "dreams": "dreams",
    "проекты": "projects",
    "проект": "projects",
    "разработка": "projects",
    "работа": "projects",
    "projects": "projects",
    "философия": "philosophy",
    "размышления": "philosophy",
    "philosophy": "philosophy",
    "творчество": "creative",
    "искусство": "creative",
    "creative": "creative",
    "психология": "psychology",
    "саморазвитие": "psychology",
    "psychology": "psychology",
}

CLASSIFY_PROMPT = """Ты — классификатор заметок по крыльям базы знаний MemPalace.

Крылья:
- dreams — сны, сновидения, ночные образы, подсознание
- projects — проекты, код, разработка, работа, технические заметки
- philosophy — философия, размышления, смыслы, идеи, рефлексия
- creative — творчество, искусство, стихи, креативные идеи
- psychology — психология, саморазвитие, эмоции, состояния, отношения

Прочитай заметку и ответь ОДНИМ СЛОВОМ — названием крыла:
(philosophy, projects, dreams, creative, psychology).
Не пиши ничего кроме одного слова."""


def collect_files() -> list[tuple[str, str]]:
    """Собирает (путь_к_файлу, относительное_имя) из всех папок рекурсивно."""
    files = []
    seen = set()
    for folder in [NOTES_DIR, INSIGHTS_DIR, RESEARCH_DIR, PDF_ARCHIVE_DIR]:
        if not os.path.isdir(folder):
            continue
        for root, _dirs, fnames in os.walk(folder):
            for fname in sorted(fnames):
                if fname.startswith("."):
                    continue
                if fname.endswith((".txt", ".md")):
                    fpath = os.path.join(root, fname)
                    if fpath not in seen and os.path.isfile(fpath):
                        seen.add(fpath)
                        rel_name = os.path.relpath(fpath, folder)
                        files.append((fpath, rel_name))
    return files


async def classify_file(engine: str, model: str, fpath: str) -> str:
    """Определяет крыло файла через ИИ."""
    try:
        with open(fpath, encoding="utf-8", errors="ignore") as f:
            content = f.read().strip()
        if not content:
            return "unknown"
        content = content[:1000]
        msg = [
            {"role": "system", "content": CLASSIFY_PROMPT},
            {"role": "user", "content": f"Заметка:\n{content}"},
        ]
        answer = await get_ai_response_async(engine, model, msg, context="")
        answer = answer.strip().lower().rstrip(".!,:;\"'")
        if answer in WING_NAMES:
            return answer
        if answer in RUSSIAN_WING_MAP:
            return RUSSIAN_WING_MAP[answer]
        for w in WING_NAMES:
            if w in answer:
                return w
        for ru_w, en_w in RUSSIAN_WING_MAP.items():
            if ru_w in answer:
                return en_w
        logger.warning(
            f"  ⚠️ Неожиданный ответ ИИ: '{answer}' для {os.path.basename(fpath)}",
        )
        return "unknown"
    except Exception as e:
        logger.error(f"  ❌ Ошибка классификации {os.path.basename(fpath)}: {e}")
        return "unknown"


async def main():
    print("\n🧠 MemPalace — Классификация по крыльям\n")

    files = collect_files()
    if not files:
        print("❌ Нет .txt или .md файлов для классификации.")
        return
    print(f"📄 Найдено файлов: {len(files)}")

    engine, model = get_current_ai()
    print(f"🤖 Модель: {model} ({engine})\n")

    # Классифицируем каждый файл
    wing_files: dict[str, list[tuple[str, str]]] = {w: [] for w in WING_NAMES}
    wing_files["unknown"] = []

    for i, (fpath, fname) in enumerate(files, 1):
        print(f"  [{i}/{len(files)}] {fname}...")
        wing = await classify_file(engine, model, fpath)
        wing_files[wing].append((fpath, fname))
        print(f"    → {wing}")

    # Итоги классификации
    print(f"\n{'=' * 50}")
    print("📊 Итоги классификации:")
    for w in WING_NAMES:
        print(f"  {w}: {len(wing_files[w])} файлов")
    print(f"  unknown: {len(wing_files['unknown'])} файлов")
    print(f"{'=' * 50}\n")

    # Майним по крыльям
    for wing in WING_NAMES:
        files_to_mine = wing_files[wing]
        if not files_to_mine:
            continue

        tmpdir = tempfile.mkdtemp(prefix=f"mempalace_{wing}_")
        try:
            for fpath, rel_name in files_to_mine:
                safe_name = rel_name.replace(os.sep, "__")
                dst = os.path.join(tmpdir, safe_name)
                shutil.copy2(fpath, dst)

            print(f"⛏️ Майню крыло '{wing}' ({len(files_to_mine)} файлов)...")
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "mempalace",
                "mine",
                tmpdir,
                "--wing",
                wing,
                "--mode",
                "projects",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=DATA_DIR,
                env=_get_palace_env(),
            )
            _stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                err_msg = stderr.decode().strip()
                logger.error(f"  ❌ Ошибка майнинга {wing}: {err_msg}")
            else:
                print(f"  ✅ Крыло '{wing}' замайнено")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # Unknown майним без крыла
    if wing_files["unknown"]:
        tmpdir = tempfile.mkdtemp(prefix="mempalace_unknown_")
        try:
            for fpath, rel_name in wing_files["unknown"]:
                safe_name = rel_name.replace(os.sep, "__")
                dst = os.path.join(tmpdir, safe_name)
                shutil.copy2(fpath, dst)
            print(
                f"⛏️ Майню 'unknown' ({len(wing_files['unknown'])} файлов) без крыла...",
            )
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "mempalace",
                "mine",
                tmpdir,
                "--mode",
                "projects",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=DATA_DIR,
                env=_get_palace_env(),
            )
            await proc.communicate()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    print("\n✅ Готово! Все файлы классифицированы и замайнены.")
    print("Теперь можешь искать с крыльями: /search --wing dreams <текст>")


def _get_palace_env() -> dict:
    env = os.environ.copy()
    venv_dir = os.path.join(DATA_DIR, "venv")
    env["VIRTUAL_ENV"] = venv_dir
    env["PATH"] = os.path.join(venv_dir, "bin") + os.pathsep + env.get("PATH", "")
    env["PYTHONPATH"] = DATA_DIR + os.pathsep + env.get("PYTHONPATH", "")
    return env


if __name__ == "__main__":
    asyncio.run(main())
