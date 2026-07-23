"""
classify_and_mine.py
Одноразовый скрипт: ИИ классифицирует все заметки по крыльям
и майнит их в MemPalace с соответствующим --wing.
"""
import os
import sys
import asyncio
import logging
import tempfile
import shutil

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ClassifyAndMine")

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BOT_DIR)

from config import NOTES_DIR, INSIGHTS_DIR, RESEARCH_DIR, PDF_ARCHIVE_DIR, DATA_DIR
from services.ai_engine import get_current_ai, get_ai_response_async

WING_NAMES = ["dreams", "projects", "philosophy", "creative", "psychology"]

CLASSIFY_PROMPT = """Ты — классификатор заметок по крыльям базы знаний MemPalace.

Крылья:
- dreams — сны, сновидения, ночные образы, подсознание
- projects — проекты, код, разработка, работа, технические заметки
- philosophy — философия, размышления, смыслы, идеи, рефлексия
- creative — творчество, искусство, стихи, креативные идеи
- psychology — психология, саморазвитие, эмоции, состояния, отношения

Прочитай заметку и ответь ОДНИМ СЛОВОМ — названием крыла.
Не пиши ничего кроме одного слова."""

def collect_files() -> list[tuple[str, str]]:
    """Собирает (путь_к_файлу, имя_файла) из всех папок."""
    files = []
    for folder in [NOTES_DIR, INSIGHTS_DIR, RESEARCH_DIR]:
        if os.path.isdir(folder):
            for fname in sorted(os.listdir(folder)):
                fpath = os.path.join(folder, fname)
                if os.path.isfile(fpath) and fname.endswith(".txt"):
                    files.append((fpath, fname))
    if os.path.isdir(PDF_ARCHIVE_DIR):
        for fname in os.listdir(PDF_ARCHIVE_DIR):
            fpath = os.path.join(PDF_ARCHIVE_DIR, fname)
            if os.path.isfile(fpath) and fname.endswith(".txt"):
                files.append((fpath, fname))
    return files

async def classify_file(engine: str, model: str, fpath: str) -> str:
    """Определяет крыло файла через ИИ."""
    try:
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read().strip()
        if not content:
            return "unknown"
        content = content[:1000]
        msg = [{"role": "system", "content": CLASSIFY_PROMPT},
               {"role": "user", "content": f"Заметка:\n{content}"}]
        answer = await get_ai_response_async(engine, model, msg, context="")
        answer = answer.strip().lower().rstrip(".!,")
        if answer in WING_NAMES:
            return answer
        logger.warning(f"  ⚠️ Неожиданный ответ ИИ: '{answer}' для {os.path.basename(fpath)}")
        return "unknown"
    except Exception as e:
        logger.error(f"  ❌ Ошибка классификации {os.path.basename(fpath)}: {e}")
        return "unknown"

async def main():
    print("\n🧠 MemPalace — Классификация по крыльям\n")

    files = collect_files()
    if not files:
        print("❌ Нет .txt файлов для классификации.")
        return
    print(f"📄 Найдено файлов: {len(files)}")

    engine, model = get_current_ai()
    print(f"🤖 Модель: {model} ({engine})\n")

    # Классифицируем каждый файл
    wing_files: dict[str, list[str]] = {w: [] for w in WING_NAMES}
    wing_files["unknown"] = []

    for i, (fpath, fname) in enumerate(files, 1):
        print(f"  [{i}/{len(files)}] {fname}...")
        wing = await classify_file(engine, model, fpath)
        wing_files[wing].append(fpath)
        print(f"    → {wing}")

    # Итоги классификации
    print(f"\n{'='*50}")
    print("📊 Итоги классификации:")
    for w in WING_NAMES:
        print(f"  {w}: {len(wing_files[w])} файлов")
    print(f"  unknown: {len(wing_files['unknown'])} файлов")
    print(f"{'='*50}\n")

    # Майним по крыльям
    for wing in WING_NAMES:
        files_to_mine = wing_files[wing]
        if not files_to_mine:
            continue

        tmpdir = tempfile.mkdtemp(prefix=f"mempalace_{wing}_")
        try:
            for fpath in files_to_mine:
                dst = os.path.join(tmpdir, os.path.basename(fpath))
                shutil.copy2(fpath, dst)

            print(f"⛏️ Майню крыло '{wing}' ({len(files_to_mine)} файлов)...")
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "mempalace", "mine", tmpdir,
                "--wing", wing,
                "--mode", "projects",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=DATA_DIR,
                env=_get_palace_env()
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.error(f"  ❌ Ошибка майнинга {wing}: {stderr.decode().strip()}")
            else:
                print(f"  ✅ Крыло '{wing}' замайнено")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # Unknown майним без крыла
    if wing_files["unknown"]:
        tmpdir = tempfile.mkdtemp(prefix="mempalace_unknown_")
        try:
            for fpath in wing_files["unknown"]:
                shutil.copy2(fpath, os.path.join(tmpdir, os.path.basename(fpath)))
            print(f"⛏️ Майню 'unknown' ({len(wing_files['unknown'])} файлов) без крыла...")
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "mempalace", "mine", tmpdir,
                "--mode", "projects",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=DATA_DIR,
                env=_get_palace_env()
            )
            await proc.communicate()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    print(f"\n✅ Готово! Все файлы классифицированы и замайнены.")
    print(f"Теперь можешь искать с крыльями: /search --wing dreams <текст>")

def _get_palace_env() -> dict:
    env = os.environ.copy()
    venv_dir = os.path.join(DATA_DIR, "venv")
    env["VIRTUAL_ENV"] = venv_dir
    env["PATH"] = os.path.join(venv_dir, "bin") + os.pathsep + env.get("PATH", "")
    env["PYTHONPATH"] = DATA_DIR + os.pathsep + env.get("PYTHONPATH", "")
    return env

if __name__ == "__main__":
    asyncio.run(main())
