"""
text_formatter.py
Безопасное HTML-форматирование для Telegram, сплит ≤4000 символов.
"""
import re
import html

def safe_html_format(text: str) -> str:
    if not text: 
        return ""
    # Экранируем спецсимволы HTML
    text = html.escape(text)
    # Жирный текст
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    # Курсив
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    # Код inline
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    # Блоки кода
    text = re.sub(r'```([\s\S]*?)```', r'<pre>\1</pre>', text)
    # Заголовки
    text = re.sub(r'^#{1,3}\s+(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)
    return text.strip()

def split_message(text: str, limit: int = 4000) -> list:
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    
    parts = []
    remaining = text
    
    while remaining:
        if len(remaining) <= limit:
            parts.append(remaining)
            break
        
        # Ищем разрыв по абзацам или предложениям
        split_idx = remaining.rfind('\n\n', 0, limit)
        if split_idx == -1:
            split_idx = remaining.rfind('. ', 0, limit)
        if split_idx == -1:
            split_idx = remaining.rfind('! ', 0, limit)
        if split_idx == -1:
            split_idx = remaining.rfind('? ', 0, limit)
        
        # Если не нашли естественный разрыв, режем жестко
        if split_idx == -1:
            split_idx = limit
            
        parts.append(remaining[:split_idx].strip())
        remaining = remaining[split_idx:].strip()
        
    return parts