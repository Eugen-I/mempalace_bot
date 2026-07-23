import re
import os
import asyncio
import logging
from services.palace_bridge import search_palace_context

logger = logging.getLogger("NoteLinker")

NOTES_DIRS = {
    "!": "my_notes",
    "!!": "insights",
    "???": "research"
}

def escape_markdown_v2(text: str) -> str:
    """Экранирует спецсимволы для Telegram MarkdownV2."""
    if not text:
        return ""
    # Список символов, которые нужно экранировать в MarkdownV2
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

async def link_note_async(note_path: str, note_content: str, prefix: str = "!"):
    """Асинхронный поиск и привязка семантически близких заметок."""
    try:
        query = note_content[:200].replace("\n", " ").strip()
        if len(query) < 10:
            logger.debug(f"[LINKER] Заметка слишком короткая для связывания: {note_path}")
            return

        # Ищем похожие записи по релевантности в лимит 12
        raw_results = await search_palace_context(query, limit=12)
        
        if not raw_results or "Ничего не найдено" in raw_results:
            logger.info(f"[LINKER] Нет связанных записей для: {os.path.basename(note_path)}")
            return

        # Парсим результаты MemPalace
        # Формат обычно: 
        # [1] path/to/file.txt
        # snippet text...
        # ---
        lines = raw_results.split("\n")
        related_items = []
        current_item = None
        
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            
            # Если строка начинается с [число], это новый результат
            match = re.match(r'^\[(\d+)\]\s+(.+)', line_stripped)
            if match:
                if current_item:
                    related_items.append(current_item)
                # Извлекаем путь/имя файла
                file_info = match.group(2).strip()
                # Берем только имя файла, если есть путь
                filename = os.path.basename(file_info) if '/' in file_info else file_info
                current_item = {"filename": filename, "snippet": ""}
            elif current_item and not line_stripped.startswith("---"):
                # Это продолжение сниппета
                current_item["snippet"] += " " + line_stripped
        
        if current_item:
            related_items.append(current_item)

        # Фильтруем саму себя и берем топ-3
        own_filename = os.path.basename(note_path)
        #Вывод количество релевантных связанностей 6
        related_items = [item for item in related_items if item["filename"] != own_filename][:6]
        
        if not related_items:
            return

        # Формируем блок связей БЕЗОПАСНО
        link_block = "\n\n## 🔗 Связанные записи\n"
        for item in related_items:
            safe_name = escape_markdown_v2(item["filename"])
            # Обрезаем сниппет до 100 символов и экранируем
            safe_snippet = escape_markdown_v2(item["snippet"][:100].strip())
            
            # Используем простой дефис, без жирного шрифта и курсива, чтобы избежать ошибок парсинга
            link_block += f"- {safe_name}: {safe_snippet}\n"

        # Дописываем в файл
        with open(note_path, "a", encoding="utf-8") as f:
            f.write(link_block)
            
        logger.info(f"[LINKER] ✅ Добавлено {len(related_items)} связей в {own_filename}")

    except Exception as e:
        logger.error(f"[LINKER] Ошибка связывания {note_path}: {e}", exc_info=True)


def schedule_linking(note_path: str, note_content: str, prefix: str = "!"):
    """Запускает связывание в фоне."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(link_note_async(note_path, note_content, prefix))
        else:
            loop.run_until_complete(link_note_async(note_path, note_content, prefix))
    except RuntimeError:
        asyncio.run(link_note_async(note_path, note_content, prefix))