"""text_formatter.py
Безопасное HTML-форматирование для Telegram, сплит ≤4000 символов.
"""

import html
import re

ALLOWED_TAGS = {"b", "i", "code", "pre", "u", "s", "a", "blockquote", "tg-spoiler"}

_TAG_RE = re.compile(r"</?([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>")


def _escape_outside_allowed_tags(text: str) -> str:
    """Escape HTML special chars except inside allowed tags."""
    if not text:
        return ""
    result = []
    last_end = 0
    for match in _TAG_RE.finditer(text):
        try:
            tag_name = match.group(1)
        except IndexError:
            continue
        if not tag_name:
            continue
        tag_name = tag_name.lower()
        start, end = match.span()
        if start > last_end:
            result.append(html.escape(text[last_end:start]))
        if tag_name in ALLOWED_TAGS:
            result.append(text[start:end])
        else:
            result.append(html.escape(text[start:end]))
        last_end = end
    if last_end < len(text):
        result.append(html.escape(text[last_end:]))
    return "".join(result)


def safe_html_format(text: str) -> str:
    if not text:
        return ""
    has_allowed_tags = any(
        f"<{tag}" in text.lower() or f"</{tag}" in text.lower()
        for tag in ALLOWED_TAGS
    )
    if has_allowed_tags:
        text = _escape_outside_allowed_tags(text)
    else:
        text = html.escape(text)
    text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    text = re.sub(r"```([\s\S]*?)```", r"<pre>\1</pre>", text)
    text = re.sub(r"^\s*[-*]\s+(.+)$", r"• \1", text, flags=re.MULTILINE)
    text = re.sub(r"^(\s*)(\d+)\.\s+(.+)$", r"\1<b>\2.</b> \3", text, flags=re.MULTILINE)
    text = re.sub(r"^---+$", r"<i>────</i>", text, flags=re.MULTILINE)
    return text.strip()


_TAG_RE = re.compile(r"<[^>]+>")


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
    TAG_PATTERN = re.compile(r"</?(\w+)[^>]*>")
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
        for m in TAG_PATTERN.finditer(chunk):
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
