"""Smart filtering for notes imported from folders.

The goal is to avoid importing low-value notes such as empty title-only notes,
placeholder content, or junk that does not add useful information.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImportDecision:
    """Decision for a single note candidate."""

    path: str
    should_import: bool
    reason: str
    score: int


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _word_count(text: str) -> int:
    normalized = _normalize_text(text)
    return len(re.findall(r"\b\w+\b", normalized)) if normalized else 0


def _contains_meaningful_content(text: str) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return False

    if len(normalized) < 8:
        return False

    if re.fullmatch(r"[\W_]+", normalized):
        return False

    if re.fullmatch(r"(?:https?://|www\.)\S+", normalized):
        return False

    if re.fullmatch(r"(?:[\W_\d]+|[\u2600-\u27BF\U0001F300-\U0001FAFF]+)+", normalized):
        return False

    if _word_count(normalized) <= 2:
        return False

    lowered = normalized.lower()
    if lowered in {"untitled", "title", "note", "notes", "todo", "task"}:
        return False

    junk_markers = [
        "lorem ipsum",
        "asdf",
        "qwerty",
        "test test",
        "placeholder",
        "sample text",
        "dummy",
        "junk",
        "spam",
        "bla bla",
        "foo bar",
        "todo todo",
    ]
    if any(marker in lowered for marker in junk_markers):
        return False

    return True


def should_import_note(
    text: str, title: str | None = None, mode: str = "default",
) -> ImportDecision:
    """Return whether a note should be imported.

    Rules:
    - Empty / whitespace-only content is skipped.
    - Title-only notes are skipped.
    - Very short or low-signal content is skipped.
    - In strict mode, more content is required.
    """

    title_text = (title or "").strip()
    body_text = _normalize_text(text or "")
    combined = f"{title_text} {body_text}".strip()

    if not title_text and not body_text:
        return ImportDecision(path="", should_import=False, reason="empty", score=0)

    if not body_text and title_text:
        if title_text.lower() in {"untitled", "title", "note", "notes", "todo", "task", ""}:
            return ImportDecision(path="", should_import=False, reason="empty", score=0)
        return ImportDecision(path="", should_import=False, reason="title-only", score=0)

    if not body_text and not title_text:
        return ImportDecision(path="", should_import=False, reason="empty", score=0)

    if title_text and body_text and title_text.lower() == body_text.lower():
        return ImportDecision(path="", should_import=False, reason="title-only", score=0)

    if not combined:
        return ImportDecision(path="", should_import=False, reason="empty", score=0)

    score = 0
    score += min(6, _word_count(body_text))

    if re.search(r"[\w]{4,}", body_text):
        score += 2

    common_words = (
        r"\b(?:the|and|with|for|this|that|from|your|have|note|today|tomorrow|"
        r"meeting|task|idea|plan|project|remember|review|decision|reason|"
        r"context|action|next step)\b"
    )
    if re.search(common_words, body_text.lower()):
        score += 2

    if re.search(r"https?://|www\.", body_text):
        score -= 3

    if re.fullmatch(r"[\W_\d]+", body_text):
        score -= 5

    if re.fullmatch(r"(?:[\W_\d]+|[\u2600-\u27BF\U0001F300-\U0001FAFF]+)+", body_text):
        score -= 4

    if mode == "strict":
        threshold = 6
    else:
        threshold = 4

    if not _contains_meaningful_content(body_text):
        return ImportDecision(path="", should_import=False, reason="low-signal", score=score)

    if score < threshold:
        return ImportDecision(path="", should_import=False, reason="low-signal", score=score)

    return ImportDecision(path="", should_import=True, reason="kept", score=score)


def filter_notes_in_folder(folder: str | Path, mode: str = "default") -> dict:
    """Filter notes in a folder and return a summary.

    Supported file extensions: .md, .txt, .markdown, .rtf.
    """

    folder_path = Path(folder)
    if not folder_path.exists() or not folder_path.is_dir():
        return {
            "kept_count": 0,
            "skipped_count": 0,
            "decisions": [],
            "skipped_paths": [],
        }

    supported_suffixes = {".md", ".txt", ".markdown", ".rtf"}
    decisions: list[ImportDecision] = []
    skipped_paths: list[str] = []

    for path in sorted(folder_path.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in supported_suffixes:
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                text = path.read_text(encoding="latin-1")
            except Exception:
                text = ""

        decision = should_import_note(text, title=path.stem, mode=mode)
        decision = ImportDecision(
            path=str(path),
            should_import=decision.should_import,
            reason=decision.reason,
            score=decision.score,
        )
        decisions.append(decision)
        if not decision.should_import:
            skipped_paths.append(str(path))

    kept_count = sum(1 for decision in decisions if decision.should_import)
    skipped_count = sum(1 for decision in decisions if not decision.should_import)

    return {
        "kept_count": kept_count,
        "skipped_count": skipped_count,
        "decisions": decisions,
        "skipped_paths": skipped_paths,
    }
