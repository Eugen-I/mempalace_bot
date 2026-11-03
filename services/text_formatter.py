"""text_formatter.py
Безопасное HTML-форматирование для Telegram, сплит ≤4000 символов.
"""

import html
import re

ALLOWED_TAGS = {"b", "i", "code", "pre", "u", "s", "a", "blockquote", "tg-spoiler"}

# Единственное определение на модуль: используется и sanitizer'ом, и split_message.
_TAG_RE = re.compile(r"</?([a-zA-Z][a-zA-Z0-9-]*)(?:\s+([^>]*))?>")
_HREF_RE = re.compile(
    r"""\bhref\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""",
    re.IGNORECASE,
)
_SAFE_HREF_RE = re.compile(r"^(?:https?://|tg://|mailto:)", re.IGNORECASE)

# Код вынимаем до markdown-преобразований, чтобы ** и * внутри него не форматировались.
# Язык распознаём только в первой строке fence'а; без перевода строки это уже код.
_CODE_BLOCK_RE = re.compile(r"```[ \t]*(?:[^\s`]+[ \t]*\r?\n)?([\s\S]*?)```")
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_CODE_TOKEN_RE = re.compile("\ue000(\\d+)\ue001")


def _normalize_open_tag(tag: str, attrs: str) -> str | None:
    """Возвращает безопасный открывающий тег или None, если тег запрещён."""
    if tag != "a":
        # Остальные разрешённые теги не нуждаются в атрибутах.
        return f"<{tag}>"

    match = _HREF_RE.search(attrs)
    if not match:
        return None
    href = next((g for g in match.groups() if g is not None), "").strip()
    if not href or not _SAFE_HREF_RE.match(href):
        return None
    return f'<a href="{html.escape(href, quote=True)}">'


def _escape_outside_allowed_tags(text: str) -> str:
    """Экранирует HTML вне whitelist и балансирует разрешённые теги.

    Разрешённые теги нормализуются (атрибуты отбрасываются, кроме безопасного
    href у ссылок). Неизвестные теги и «висячие» закрывающие теги экранируются.
    Незакрытые разрешённые теги закрываются в конце.
    """
    if not text:
        return ""

    result: list[str] = []
    open_tags: list[str] = []
    last_end = 0

    for match in _TAG_RE.finditer(text):
        start, end = match.span()
        if start > last_end:
            result.append(html.escape(text[last_end:start]))

        raw = match.group(0)
        tag = match.group(1).lower()
        is_closing = raw.startswith("</")

        if tag not in ALLOWED_TAGS:
            result.append(html.escape(raw))
        elif is_closing:
            if tag in open_tags:
                while open_tags and open_tags[-1] != tag:
                    result.append(f"</{open_tags.pop()}>")
                result.append(f"</{tag}>")
                open_tags.pop()
            else:
                result.append(html.escape(raw))
        else:
            normalized = _normalize_open_tag(tag, match.group(2) or "")
            if normalized is None:
                result.append(html.escape(raw))
            else:
                result.append(normalized)
                open_tags.append(tag)

        last_end = end

    result.append(html.escape(text[last_end:]))
    result.extend(f"</{tag}>" for tag in reversed(open_tags))
    return "".join(result)


def _stash_code(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Заменяет code fence/inline code на placeholder'ы до markdown-обработки."""
    code_parts: list[tuple[str, str]] = []

    def stash_block(match: re.Match) -> str:
        code_parts.append(("block", match.group(1).strip("\r\n")))
        return f"\ue000{len(code_parts) - 1}\ue001"

    def stash_inline(match: re.Match) -> str:
        code_parts.append(("inline", match.group(1)))
        return f"\ue000{len(code_parts) - 1}\ue001"

    text = _CODE_BLOCK_RE.sub(stash_block, text)
    text = _INLINE_CODE_RE.sub(stash_inline, text)
    return text, code_parts


def _restore_code(text: str, code_parts: list[tuple[str, str]]) -> str:
    """Возвращает code-фрагменты уже экранированными, вне markdown-разметки."""
    def restore(match: re.Match) -> str:
        idx = int(match.group(1))
        if idx >= len(code_parts):
            return match.group(0)
        kind, content = code_parts[idx]
        escaped = html.escape(content)
        if kind == "block":
            return f"<pre><code>{escaped}</code></pre>"
        return f"<code>{escaped}</code>"

    return _CODE_TOKEN_RE.sub(restore, text)


def safe_html_format(text: str | None) -> str:
    if not text:
        return ""

    text, code_parts = _stash_code(text)
    text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    text = re.sub(r"^\s*[-*]\s+(.+)$", r"• \1", text, flags=re.MULTILINE)
    text = re.sub(r"^(\s*)(\d+)\.\s+(.+)$", r"\1<b>\2.</b> \3", text, flags=re.MULTILINE)
    text = re.sub(r"^---+$", r"<i>────</i>", text, flags=re.MULTILINE)
    text = _escape_outside_allowed_tags(text)
    text = _restore_code(text, code_parts)
    return text.strip()


def _adjust_split_to_safe_point(text: str, split_idx: int) -> int:
    """Отступаем назад, чтобы не разрезать HTML-тег."""
    if split_idx <= 0:
        return split_idx
    before = text[max(0, split_idx - 20) : split_idx + 5]
    depth = 0
    for ch in before:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
    if depth > 0:
        cur = split_idx
        while cur > 0 and text[cur : cur + 5].strip():
            if text[cur : cur + 1] == "<":
                break
            cur -= 1
        if cur > 0:
            return cur
    return split_idx


def split_message(text: str, limit: int = 4000) -> list:
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    parts = []
    remaining = text
    BALANCE_TAGS = {"b", "i", "code", "pre", "u", "s"}

    while remaining:
        if len(remaining) <= limit:
            parts.append(remaining)
            break

        split_idx = remaining.rfind("\n\n", 0, limit)
        if split_idx == -1:
            split_idx = remaining.rfind(". ", 0, limit)
        if split_idx == -1:
            split_idx = remaining.rfind("! ", 0, limit)
        if split_idx == -1:
            split_idx = remaining.rfind("? ", 0, limit)
        if split_idx == -1:
            split_idx = limit

        split_idx = _adjust_split_to_safe_point(remaining, split_idx)
        if split_idx <= 0:
            split_idx = limit

        chunk = remaining[:split_idx].strip()
        remaining = remaining[split_idx:].strip()

        open_tags: list[str] = []
        for m in _TAG_RE.finditer(chunk):
            t = m.group(1)
            if t not in BALANCE_TAGS:
                continue
            if m.group(0).startswith("</"):
                if open_tags and open_tags[-1] == t:
                    open_tags.pop()
            else:
                open_tags.append(t)

        if open_tags:
            chunk += "".join(f"</{t}>" for t in reversed(open_tags))
            reopen = "".join(f"<{t}>" for t in open_tags)
            remaining = reopen + remaining

        parts.append(chunk)

    return parts
