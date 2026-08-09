"""services/reflection.py — рефлексия после штурма.

После сохранения идей штурма в Дворец бот задаёт вопрос
«какая идея самая сильная и почему?»; ответ сохраняется
в kv (namespace "reflection") — детерминированный журнал
рефлексий по темам штурмов.
"""

import time

from services.text_formatter import safe_html_format

REFLECTION_NS = "reflection"
MAX_ANSWER_LEN = 2000
MAX_THEME_LEN = 80


def build_reflection_question(theme: str) -> str:
    """Текст вопроса о рефлексии после штурма (HTML-safe)."""
    theme = (theme or "").strip()[:MAX_THEME_LEN]
    if theme:
        header = f"Рефлексия по теме «{safe_html_format(theme)}»"
    else:
        header = "Рефлексия после штурма"
    return (
        f"🤔 <b>{header}</b>\n\n"
        "Какая идея показалась самой сильной и почему?\n"
        "Напишите ответ одним сообщением."
    )


def save_reflection_answer(kv, uid: int, theme: str, answer: str) -> str:
    """Сохраняет ответ рефлексии в kv и возвращает ответ пользователю."""
    answer = (answer or "").strip()
    if not answer:
        return "Пустой ответ — рефлексия не записана."
    answer = answer[:MAX_ANSWER_LEN]
    theme = (theme or "").strip()[:MAX_THEME_LEN]
    seq = len(kv.keys(namespace=REFLECTION_NS))
    key = f"ref_{uid}_{seq}_{int(time.time())}"
    kv.set(
        key,
        {
            "uid": uid,
            "theme": theme,
            "answer": answer,
            "ts": time.time(),
        },
        namespace=REFLECTION_NS,
    )
    return "💭 Спасибо, рефлексия записана!"
