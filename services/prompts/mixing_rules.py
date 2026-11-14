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

CREATIVE_PHOTO_KEYWORDS = [
    # Фототехника и оптика
    "фото", "фотографи", "снимок", "кадр", "съемк", "съёмк", "камер",
    "объектив", "линз", "диафрагм", "выдержк", "экспозици", "боке",
    "фокус", "светофильтр", "фильтр", "вспышк", "штатив", "fuji", "fujifilm",
    "x-t4", "pentacon", "fujinon", "kamlan", "монокль", "гелиос", "godox",
    "призм", "ткани", "рецепт", "пленк", "плёнк", "зерно",
    # Творчество, арт и стили
    "арт", "искусств", "штурм", "идеи", "идея", "сюжет", "концепт",
    "замысел", "образ", "стиль", "сюрреал", "пиктореал", "импрессион",
    "экспрессион", "конструктивизм", "кьяроскуро", "сфумато", "композици",
    "ракурс", "галере", "выставк", "эстетик", "визуал", "живопис",
    # Световые и природные визуальные мотивы / жанры
    "свет", "тень", "блик", "лучи", "отражен", "силуэт", "текстур",
    "портрет", "пейзаж", "натюрморт", "стрит", "макро", "локаци",
    "листья", "лист", "осень", "осенн", "весна", "весенн", "зима", "зимн",
    "лето", "летн", "туман", "дождь", "закат", "рассвет", "сумерк",
    "небо", "облака", "вода", "город", "природ", "лес", "деревь",
]

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
        "glue": (
            "\nВАЖНО: Дай название фото. Свяжи визуальные символы на фото с "
            "архетипами из снов по Юнгу. Найди пересечения между визуальным рядом "
            "и внутренними переживаниями. Задай уточняющие вопросы для углубления "
            "идей и мыслей."
        ),
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
        "glue": (
            "Задай уточняющие вопросы для углубления идей и мыслей. Анализируй "
            "сон по Юнгу и его учеников. Найди образы, символы и архетипы "
            "и объясни их связь со сном и жизнью."
        ),
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
        "glue": (
            "\nВАЖНО: Основывай диалог и ответы на трудах философов прошлого. "
            "Давай глубокие ответы, цитаты из трудов философов. Задай глубокие "
            "вопросы для углубления идей и мыслей. Не будь поверхностным, углубляй "
            "свои ответы."
        ),
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
        "glue": (
            "Не придумывай болезни, давай объяснения медицинских терминов доступно. "
            "Не делай рекомендаций, противоречащих доказательной медицине."
        ),
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
        "glue": (
            "Используй понятия и термины психологии. Основывайся на личных "
            "заметках пользователя и общих знаниях."
        ),
    },
    {
        "name": "Photo & Creative Art Focus",
        "condition": lambda q, has_img: (
            has_img or any(kw in q.lower() for kw in CREATIVE_PHOTO_KEYWORDS)
        ),
        "parts": [FOCUS_PHOTO_ART],
        "glue": (
            "Ты — опытный арт-директор и фотограф-художник. Анализируй визуальные "
            "образы, световую драматургию, художественные стили и технические приёмы "
            "съёмки на Fujifilm X-T4 с творческой оптикой и фильтрами. "
            "Предлагай нетривиальные метафоры, ракурсы, настройки и идеи для съёмки."
        ),
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
        if active_rule.get("name") in (
            "Photo & Creative Art Focus",
            "Dream + Photo Hybrid",
        ):
            try:
                from services.photographer_gear import format_gear_context
                gear_ctx = format_gear_context()
                if gear_ctx:
                    prompt_parts.append(gear_ctx)
            except Exception as exc:  # noqa: BLE001
                logger.debug("[PROMPT_ENGINE] gear context skipped: %s", exc)

    from services.prompts.base_rules import BASE_RULES

    prompt_parts.append(BASE_RULES)
    if active_rule:
        logger.info(f"[PROMPT_ENGINE] Selected rule: {active_rule['name']}")

    return "\n".join(prompt_parts)
