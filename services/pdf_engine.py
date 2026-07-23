"""
pdf_engine.py
Асинхронная обработка PDF: текст, OCR, чанкинг, промпты, сравнение.
"""
import os, re, json, asyncio, logging
from typing import List, Tuple
from concurrent.futures import ProcessPoolExecutor
import fitz, tiktoken, pytesseract
from pdf2image import convert_from_path
from config import TEMP_DIR, PROMPTS_FILE, PDF_ARCHIVE_DIR
from services.prompts import PDF_CHUNK_PROMPT, PDF_COMBINE_PROMPT

logger = logging.getLogger("PDF_Engine")

DEFAULT_PROMPTS = {
    "general": {"name": "📄 Общий анализ", "prompt": "Проанализируй документ. Выдели ключевые идеи, темы и сделай краткое саммари."},
    "medical": {"name": "🏥 Медицина / Анализы", "prompt": "Проанализируй медицинские данные. Выдели показатели, отклонения, рекомендации."},
    "psychology": {"name": "🧠 Психология / Юнг", "prompt": "Проанализируй текст через призму аналитической психологии. Найди архетипы, символы, инсайты."},
    "literature": {"name": "📚 Литература / Книги", "prompt": "Суммаризируй текст книги. Выдели сюжет, персонажей, главные мысли."},
    "programming": {"name": "💻 Программирование", "prompt": "Проанализируй технический текст или код. Объясни логику, найди ошибки."},
    "language": {"name": "🌍 Изучение языков", "prompt": "Выдели полезные фразы, грамматические конструкции и словарный запас."},
    "sport_diet": {"name": "🏃 Спорт / Диетология", "prompt": "Проанализируй план тренировок или питания. Выдели нагрузку, БЖУ, рекомендации."},
    "contradiction": {"name": "⚖️ Поиск противоречий", "prompt": "Найди логические нестыковки, конфликтующие факты или противоречия внутри текста."},
    "scientific": {"name": "🔬 Научная проверка", "prompt": "Проверь утверждения на соответствие научным данным. Укажи спорные моменты."}
}

def load_prompts() -> dict:
    if not os.path.exists(PROMPTS_FILE):
        with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_PROMPTS, f, ensure_ascii=False, indent=2)
        return DEFAULT_PROMPTS
    with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def _sync_extract_pdf(pdf_path: str) -> Tuple[str, str]:
    logger.info(f"Opening PDF: {pdf_path}")
    if not os.path.exists(pdf_path):
        logger.error(f"File not found: {pdf_path}")
        return "", "failed"

    try:
        doc = fitz.open(pdf_path)
        text_parts = []
        for page in doc:
            t = page.get_text()
            if t:
                text_parts.append(t.strip())
        doc.close()
        full = re.sub(r'\s+', ' ', '\n\n'.join(text_parts)).strip()
        if len(full) > 150:
            return full, "text"
    except Exception as e:
        logger.warning(f"PyMuPDF fail: {e}")

    try:
        images = convert_from_path(pdf_path, dpi=200, last_page=15)
        ocr_parts = []
        for i, img in enumerate(images):
            txt = pytesseract.image_to_string(img, lang="deu+rus+eng", config="--psm 6")
            if txt:
                ocr_parts.append(f"--- Стр. {i+1} ---\n{txt}")
        ocr_full = re.sub(r'\s+', ' ', '\n\n'.join(ocr_parts)).strip()
        if len(ocr_full) > 100:
            return ocr_full, "ocr"
    except Exception as e:
        logger.error(f"OCR fail: {e}")

    return "", "failed"

async def extract_pdf_async(pdf_path: str) -> Tuple[str, str]:
    loop = asyncio.get_event_loop()
    with ProcessPoolExecutor() as pool:
        return await loop.run_in_executor(pool, _sync_extract_pdf, pdf_path)

def estimate_tokens(text: str) -> int:
    try: return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except: return len(text) // 4

def build_comparison_prompt(text_a: str, text_b: str) -> str:
    return (
        "⚖️ ЗАДАЧА: СРАВНЕНИЕ ДВУХ ДОКУМЕНТОВ\n\n"
        "1. Выяви прямые противоречия и нестыковки в фактах, выводах или рекомендациях.\n"
        "2. Отметь общие идеи и точки пересечения.\n"
        "3. Укажи, чем документы дополняют друг друга.\n"
        "4. Структурируй ответ четко по пунктам.\n\n"
        f"📄 ДОКУМЕНТ А:\n{text_a}\n\n📄 ДОКУМЕНТ Б:\n{text_b}"
    )

CHUNK_MAX_CHARS = 25000
CHUNK_OVERLAP = 1500

def chunk_text(text: str) -> List[str]:
    if len(text) <= CHUNK_MAX_CHARS:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_MAX_CHARS
        if end >= len(text):
            chunks.append(text[start:])
            break
        split_at = text.rfind(". ", start + CHUNK_MAX_CHARS - CHUNK_OVERLAP, end)
        if split_at < start + CHUNK_MAX_CHARS - CHUNK_OVERLAP:
            split_at = text.rfind("\n", start + CHUNK_MAX_CHARS - CHUNK_OVERLAP, end)
        if split_at < start + CHUNK_MAX_CHARS - CHUNK_OVERLAP:
            split_at = end
        else:
            split_at += 1
        chunks.append(text[start:split_at])
        start = split_at
    return chunks

async def analyze_large_document(engine: str, model: str, full_text: str, prompt_tpl: str, msg) -> str:
    from services.ai_engine import get_ai_response_async

    if not full_text.strip():
        return "❌ Нет текста для анализа."

    chars = len(full_text)
    if chars < CHUNK_MAX_CHARS:
        full_prompt = f"{prompt_tpl}\n\nДОКУМЕНТ:\n{full_text}"
        try:
            await msg.edit_text(f"🧠 <code>{model}</code> анализирует... (~{estimate_tokens(full_text)//1000}k токенов)", parse_mode="HTML")
        except:
            pass
        return await get_ai_response_async(engine, model, [{"role": "user", "content": full_prompt}])

    chunks = chunk_text(full_text)
    num_chunks = len(chunks)
    chunk_analyses = []

    try:
        await msg.edit_text(f"📄 Документ большой ({chars//1000}k символов). Анализирую по частям ({num_chunks} частей)...", parse_mode="HTML")
    except:
        pass

    for i, chunk in enumerate(chunks, 1):
        try:
            await msg.edit_text(f"📄 Часть {i}/{num_chunks} (~{len(chunk)//1000}k символов)...", parse_mode="HTML")
        except:
            pass

        part_prompt = f"{prompt_tpl}\n\n{PDF_CHUNK_PROMPT}\n\nТЕКСТ ЧАСТИ {i}/{num_chunks}:\n{chunk}"
        answer = await get_ai_response_async(engine, model, [{"role": "user", "content": part_prompt}])
        if answer and not answer.startswith("❌"):
            chunk_analyses.append(f"=== ЧАСТЬ {i}/{num_chunks} ===\n{answer}")
        else:
            chunk_analyses.append(f"=== ЧАСТЬ {i}/{num_chunks} ===\n[Ошибка анализа этой части]")
            logger.warning(f"Chunk {i}/{num_chunks} analysis failed: {answer}")

    try:
        await msg.edit_text(f"🧠 Собираю итоговый анализ из {num_chunks} частей...", parse_mode="HTML")
    except:
        pass

    combine_prompt = PDF_COMBINE_PROMPT.format(chunks="\n\n".join(chunk_analyses))
    final = await get_ai_response_async(engine, model, [{"role": "user", "content": combine_prompt}])
    if not final or final.startswith("❌"):
        final = "\n\n".join(chunk_analyses)

    return final

def save_pdf_original(src_path: str, original_name: str) -> str:
    safe_name = re.sub(r'[^\w\.\-]', '_', original_name)
    ts = __import__('datetime').datetime.now().strftime("%Y%m%d_%H%M%S")
    dst_name = f"{ts}_{safe_name}"
    dst_path = os.path.join(PDF_ARCHIVE_DIR, dst_name)
    try:
        import shutil
        shutil.copy2(src_path, dst_path)
        index = []
        idx_path = os.path.join(PDF_ARCHIVE_DIR, ".index.json")
        if os.path.exists(idx_path):
            with open(idx_path, "r", encoding="utf-8") as f:
                index = json.load(f)
        index.append({
            "id": dst_name,
            "original_name": original_name,
            "path": dst_path,
            "uploaded": __import__('datetime').datetime.now().isoformat()
        })
        with open(idx_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        return dst_name
    except Exception as e:
        logger.error(f"Failed to save original PDF: {e}")
        return ""

def list_archived_pdfs() -> List[dict]:
    idx_path = os.path.join(PDF_ARCHIVE_DIR, ".index.json")
    if not os.path.exists(idx_path):
        return []
    try:
        with open(idx_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def remove_pdf_from_index(pdf_id: str):
    idx_path = os.path.join(PDF_ARCHIVE_DIR, ".index.json")
    if not os.path.exists(idx_path):
        return
    try:
        with open(idx_path, "r", encoding="utf-8") as f:
            index = json.load(f)
        index = [e for e in index if e.get("id") != pdf_id]
        with open(idx_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
    except:
        pass