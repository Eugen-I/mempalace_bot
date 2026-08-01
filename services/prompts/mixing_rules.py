import logging
from typing import Any

from services.prompts.focus_modules import (
    FOCUS_CODE_TECH,
    FOCUS_DREAMS_JUNG,
    FOCUS_GENERAL_EXPERT,
    FOCUS_MEDICINE,
    FOCUS_PHOTO_ART,
    FOCUS_PSYCHOLOGY,
)

logger = logging.getLogger("PromptsEngine")

PROMPT_MIXING_RULES: list[dict[str, Any]] = [
    {
        "name": "Dream + Photo Hybrid",
        "condition": lambda q, has_img: (
            any(
                kw in q.lower()
                for kw in ["сон", "сна", "снов", "сновидение", "приснилось"]
            )
            and has_img
        ),
        "parts": [FOCUS_DREAMS_JUNG, FOCUS_PHOTO_ART],
        "glue": "\nВАЖНО:Дай название фото. Свяжи визуальные символы на фото с архетипами из снов по Юнгу. Найди пересечения между визуальным рядом и внутренними переживаниями.Задай уточняющие вопросы для углубления идей и мыслей. ",  # noqa: E501
    },
    {
        "name": "Pure Dream Analysis",
        "condition": lambda q, has_img: any(
            kw in q.lower()
            for kw in [
                "сон",
                "сна",
                "снов",
                "сновидение",
                "сновидения",
                "сновидений",
                "анализ сна",
                "разбор сна",
                "приснилось",
                "кошмар",
            ]
        ),
        "parts": [FOCUS_DREAMS_JUNG],
        "glue": "Задай уточняющие вопросы для углубления идей и мыслей. Анализируй сон по Юнгу и его учеников. Найди образы, символы и архетипы и объясни их связь с сном и жизнью.",  # noqa: E501
    },
    {
        "name": "Philosophy + Dialektika",
        "condition": lambda q, has_img: (
            any(
                kw in q.lower()
                for kw in [
                    "филосовия",
                    "философы",
                    "философ",
                    "размышление",
                    "размышления о жизни",
                    "дискуссии",
                    "этика",
                    "познание",
                ]
            )
            and has_img
        ),
        "parts": [FOCUS_DREAMS_JUNG, FOCUS_PHOTO_ART],
        "glue": "\nВАЖНО:Основывай диалог и ответы на трудах философов прошого. Давай глубокие ответы,цитаты из трудов философов.Задай глубокие вопросы для углубления идей и мыслей. Не будь поверхностным, углубляй свои ответы. ",  # noqa: E501
    },
    {
        "name": "Photo Art Analysis",
        "condition": lambda q, has_img: (
            has_img
            or any(
                kw in q.lower()
                for kw in [
                    "фото",
                    "фотография",
                    "снимок",
                    "image",
                    "картинка",
                    "визуал",
                ]
            )
        ),
        "parts": [FOCUS_PHOTO_ART],
        "glue": "Оцени фото с точки зрения Галериста, Искусства. Дай короткую куратоскую фразу на фотоработу. Будь объективен, критику пиши прямо.",  # noqa: E501
    },
    {
        "name": "Coding Mode",
        "condition": lambda q, has_img: any(
            kw in q.lower()
            for kw in [
                "код",
                "скрипт",
                "C/C++",
                "python",
                "ошибка",
                "функция",
                "api",
                "debug",
            ]
        ),
        "parts": [FOCUS_CODE_TECH],
        "glue": "",
    },
    {
        "name": "Medical Advice",
        "condition": lambda q, has_img: any(
            kw in q.lower()
            for kw in [
                "болезнь",
                "симптом",
                "депрессия",
                "психотерапевт",
                "психотерапия",
                "анамнез",
                "врач",
                "здоровье",
            ]
        ),
        "parts": [FOCUS_MEDICINE],
        "glue": "Не придумывай болезни, давай объяснения медицинских терминов доступно. Неделай рекомендаций противоречащих доказательной медицины.",  # noqa: E501
    },
    {
        "name": "Psychology Focus",
        "condition": lambda q, has_img: any(
            kw in q.lower()
            for kw in [
                "психолог",
                "юнг",
                "фрейд",
                "архетип",
                "тень",
                "бессознательное",
                "психоанализ",
                "психика",
                "личность",
                "самость",
                "индивидуация",
                "терапия",
                "травма",
            ]
        ),
        "parts": [FOCUS_PSYCHOLOGY],
        "glue": "Используй понятия и термины психологии. Основывайся на личных заметках пользователя и общих знаниях.",  # noqa: E501
    },
    {
        "name": "General Expert",
        "condition": lambda q, has_img: True,
        "parts": [FOCUS_GENERAL_EXPERT],
        "glue": "",
    },
]


def get_smart_prompt(
    context: str = "", query: str = "", has_images: bool = False,
) -> str:
    prompt_parts = []

    prompt_parts.append("Ты — аналитический ИИ-помощник MemPalace.\n")

    if context.strip():
        prompt_parts.append(
            f"Контекст из личных заметок MemPalace:\n{context}\nЭти данные имеют ПРИОРИТЕТ над общими знаниями.\n",  # noqa: E501
        )

    active_rule = None
    for rule in PROMPT_MIXING_RULES:
        if rule["condition"](query, has_images):
            active_rule = rule
            break

    if active_rule:
        for part in active_rule["parts"]:
            prompt_parts.append(part)
        if active_rule.get("glue"):
            prompt_parts.append(active_rule["glue"])

    from services.prompts.base_rules import BASE_RULES

    prompt_parts.append(BASE_RULES)
    if active_rule:
        logger.info(f"[PROMPT_ENGINE] Selected rule: {active_rule['name']}")

    return "\n".join(prompt_parts)
