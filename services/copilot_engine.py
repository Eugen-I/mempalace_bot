"""services/copilot_engine.py — Движок Сократического диалога и арт-директуры копайлота.

Отвечает за:
- Живое соавторство (Сократический диалог, 1-2 острых вопроса за раз)
- Выявление скрытых смыслов, эмоционального ядра и визуальных парадоксов
- Автоматическую суммаризацию обсуждения в структурированное резюме концепта
"""

from __future__ import annotations

import logging
from typing import Any

from services.ai_engine import get_ai_response_async, get_current_ai
from services.copilot_session import CopilotSession, get_copilot_manager
from services.text_formatter import safe_html_format

logger = logging.getLogger("CopilotEngine")

COPILOT_SOCRATIC_SYSTEM = """Ты — опытный арт-директор и куратор визуальных искусств.
Твоя цель — помочь фотографу глубоко осмыслить тему арт-проекта через живой диалог.

ПРАВИЛА ДИАЛОГА:
1. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО заваливать фотографа длинным списком вопросов или анкетой.
2. В каждом ответе сначала кратко (1–2 фразы) откликнись на мысль автора: выдели метафору.
3. Затем задай ровно ОДИН (максимум два) точных, глубоких Сократических вопроса.
   Темы для исследования:
   - Эмоциональное зерно (тревога, покой, оцепенение, катарсис?).
   - Пространство и свет (бетон, туман, полумрак заброшенного дома, зеркала?).
   - Герой и телесность (одинокая фигура, только руки/детали, маска, силуэт?).
   - Скрытый парадокс (что в этой сцене ломает обыденность?).
4. Пиши лаконично (3–5 предложений на весь ответ), без клише, живым художественным языком.
5. Общайся на русском языке.
"""

COPILOT_SUMMARIZE_SYSTEM = """Ты — арт-куратор.
Извлеки из диалога фотографа и арт-директора суть и сформируй структурированное резюме.

ФОРМАТ ВЫВОДА (кратко, тезисно, без воды):
🎯 <b>Концептуальный конфликт:</b> [главная идея и психологический нерв]
💡 <b>Ключевая метафора:</b> [визуальный образ / символ]
🏛 <b>Пространство и свет:</b> [локация, качество освещения, атмосфера]
👤 <b>Герой / Объект:</b> [кто или что в кадре, телесность, пластика]
"""


def build_socratic_messages(
    topic: str, dialogue_history: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Формирует список сообщений для языковой модели Сократического диалога."""
    system_content = f"{COPILOT_SOCRATIC_SYSTEM}\n\nТЕМА ПРОЕКТА: «{topic}»."
    messages: list[dict[str, str]] = [{"role": "system", "content": system_content}]

    for entry in dialogue_history:
        role = entry.get("role", "user")
        content = entry.get("content", "").strip()
        if content:
            messages.append({"role": role, "content": content})

    return messages


async def generate_socratic_reply(session: CopilotSession, user_input: str) -> str:
    """Обрабатывает реплику пользователя и генерирует следующий вопрос/мысль арт-директора."""
    session.add_user_message(user_input)
    messages = build_socratic_messages(session.topic, session.dialogue_history)

    engine, model = get_current_ai()
    sampling = {"temperature": 0.75, "max_tokens": 500}

    try:
        raw = await get_ai_response_async(engine, model, messages, sampling=sampling)

        # Авто-fallback на локальный Qwen при ошибке квоты или сети
        is_err = (
            raw.startswith("❌")
            or "429" in raw
            or "quota" in raw.lower()
            or "resource_exhausted" in raw.lower()
        )
        if is_err and engine != "qwen":
            logger.warning(
                "[COPILOT] Engine %s failed. Fallback to local Ollama (qwen2.5:7b)...", engine,
            )
            engine, model = "qwen", "qwen2.5:7b"
            raw = await get_ai_response_async(engine, model, messages, sampling=sampling)

        reply = raw.strip()
    except Exception as exc:
        logger.error("[COPILOT] Socratic reply generation failed: %s", exc)
        reply = (
            "Это очень точный образ. Давай подумаем о пространстве: "
            "где физически разворачивается эта сцена — на открытом воздухе или в замкнутой среде?"
        )

    session.add_assistant_message(reply)
    get_copilot_manager().save_session(session)
    return reply


async def summarize_creative_dialogue(session: CopilotSession) -> str:
    """Суммаризирует диалог сессии в структурированное резюме."""
    if not session.dialogue_history:
        session.summary = f"🎯 <b>Концептуальный конфликт:</b> Исследование темы «{session.topic}»."
        get_copilot_manager().save_session(session)
        return session.summary

    # Формируем стенограмму диалога
    transcript_lines = []
    for m in session.dialogue_history:
        speaker = "Фотограф" if m.get("role") == "user" else "Арт-директор"
        transcript_lines.append(f"{speaker}: {m.get('content', '')}")
    transcript = "\n".join(transcript_lines)

    prompt = (
        f"Тема: «{session.topic}»\n\n"
        f"Стенограмма обсуждения:\n{transcript}\n\n"
        "Сформируй четкое, емкое концептуальное резюме по заданной структуре."
    )

    messages = [
        {"role": "system", "content": COPILOT_SUMMARIZE_SYSTEM},
        {"role": "user", "content": prompt},
    ]

    engine, model = get_current_ai()
    sampling = {"temperature": 0.4, "max_tokens": 600}

    try:
        raw = await get_ai_response_async(engine, model, messages, sampling=sampling)
        if raw.startswith("❌") and engine != "qwen":
            engine, model = "qwen", "qwen2.5:7b"
            raw = await get_ai_response_async(engine, model, messages, sampling=sampling)
        summary = raw.strip()
    except Exception as exc:
        logger.error("[COPILOT] summarize dialogue failed: %s", exc)
        summary = (
            f"🎯 <b>Концептуальный конфликт:</b> Исследование темы «{session.topic}».\n"
            "💡 <b>Ключевая метафора:</b> Поиск визуального нерва через свет и пластику кадра."
        )

    session.summary = summary
    get_copilot_manager().save_session(session)
    return summary


async def start_copilot_discussion(session: CopilotSession) -> str:
    """Генерирует первое вступительное слово и первый Сократический вопрос арт-директора."""
    prompt = (
        f"Фотограф выбрал тему для арт-проекта: «{session.topic}».\n"
        "Выступи как вдохновляющий арт-директор: в 1–2 фразах подчеркни потенциал темы "
        "и задай первый вопрос, определяющий эмоциональное ядро или конфликт кадра."
    )
    messages = [
        {"role": "system", "content": COPILOT_SOCRATIC_SYSTEM},
        {"role": "user", "content": prompt},
    ]

    engine, model = get_current_ai()
    sampling = {"temperature": 0.75, "max_tokens": 400}

    try:
        raw = await get_ai_response_async(engine, model, messages, sampling=sampling)
        if raw.startswith("❌") and engine != "qwen":
            engine, model = "qwen", "qwen2.5:7b"
            raw = await get_ai_response_async(engine, model, messages, sampling=sampling)
        opening = raw.strip()
    except Exception as exc:
        logger.error("[COPILOT] start discussion failed: %s", exc)
        opening = (
            f"Тема «{session.topic}» открывает простор для визуального поиска. "
            "Какое чувство должен вызвать проект: оцепенение, меланхолию или освобождение?"
        )

    session.add_assistant_message(opening)
    get_copilot_manager().save_session(session)
    return opening


# ─── Шаг 8: Стилистический конструктор ───

COPILOT_STYLES: dict[str, dict[str, str]] = {
    "Сюрреализм": {
        "icon": "👁",
        "desc": "Онейрический сюжет, парадоксы, подсознание, метафоры",
    },
    "Пиктореализм": {
        "icon": "🌫",
        "desc": "Живописная мягкость, диффузия, монокль, бархатные тени",
    },
    "Экспрессионизм": {
        "icon": "⚡️",
        "desc": "Жесткие тени, экзистенциальный надлом, контраст, драма",
    },
    "Импрессионизм": {
        "icon": "🎨",
        "desc": "Акварельная лессировка, свет, микро-тремор, цветные тени",
    },
    "Конструктивизм": {
        "icon": "📐",
        "desc": "Геометрия ракурсов, ритм линий, диагонали, минимализм",
    },
}

STYLE_PRESETS: list[tuple[str, str, list[str]]] = [
    ("preset_drama", "🎭 Драма и тайна", ["Сюрреализм", "Экспрессионизм"]),
    ("preset_pictorial", "🌫 Живописная элегия", ["Пиктореализм", "Импрессионизм"]),
    ("preset_triad", "🏛 Классическая триада", ["Сюрреализм", "Экспрессионизм", "Пиктореализм"]),
]


def get_random_style_synergy(count: int = 2) -> list[str]:
    """Генерирует случайную гармоничную комбинацию из 2 или 3 стилей."""
    import secrets
    all_styles = list(COPILOT_STYLES.keys())
    k = max(1, min(count, len(all_styles)))
    return secrets.SystemRandom().sample(all_styles, k)


def format_styles_selection_card(session: CopilotSession) -> str:
    """Форматирует карточку выбора стилей для Telegram."""
    sel_count = len(session.selected_styles)
    styles_list_text = []

    for name, info in COPILOT_STYLES.items():
        is_sel = name in session.selected_styles
        mark = "✅" if is_sel else "▫️"
        styles_list_text.append(f"{mark} <b>{info['icon']} {name}</b> — <i>{info['desc']}</i>")

    styles_block = "\n".join(styles_list_text)

    summary_preview = session.summary.strip()
    if not summary_preview:
        summary_preview = f"🎯 <b>Тема:</b> {session.topic}"

    status_line = (
        f"Выбрано: <b>{sel_count}/3</b>"
        if sel_count > 0
        else "<i>Стили не выбраны. Нажмите на кнопки ниже (от 1 до 3).</i>"
    )

    return (
        f"🎨 <b>Стилистический конструктор арт-копайлота</b>\n\n"
        f"{summary_preview}\n\n"
        f"<b>Палитра доступных стилей:</b>\n"
        f"{styles_block}\n\n"
        f"📌 {status_line}"
    )


def append_styles_to_summary(session: CopilotSession) -> str:
    """Добавляет выбранные стили к концептуальному резюме проекта."""
    if not session.selected_styles:
        return session.summary

    styles_str = ", ".join(
        f"{COPILOT_STYLES.get(s, {}).get('icon', '🎨')} {s}" for s in session.selected_styles
    )
    styles_section = f"\n🎭 <b>Выбранные стили синтеза:</b> {styles_str}"

    if styles_section not in session.summary:
        session.summary = f"{session.summary.strip()}\n{styles_section}"

    get_copilot_manager().save_session(session)
    return session.summary


# ─── Шаг 9: Соавторство манифеста ───

COPILOT_MANIFESTO_SYSTEM = """Ты — куратор выставок и автор художественных манифестов.
Твоя задача — сформулировать плотный авторский манифест фотопроекта (2–4 предложения).

ТРЕБОВАНИЯ:
1. Манифест выражает философское и визуальное кредо серии снимков.
2. Он соединяет концептуальный конфликт темы и выбранные стили визуального языка.
3. Без штампов, живой поэтический язык с акцентом на оптику, свет и психологию кадра.
4. Вывод: только текст самого манифеста, без вступительных слов и без кавычек.
"""


async def generate_initial_manifesto(session: CopilotSession) -> str:
    """Генерирует первый вариант манифеста на основе саммари и выбранных стилей."""
    styles_str = (
        ", ".join(session.selected_styles) if session.selected_styles else "Свободный синтез"
    )
    prompt = (
        f"Тема проекта: «{session.topic}».\n"
        f"Выбранные стили: {styles_str}.\n"
        f"Концептуальное резюме:\n{session.summary}\n\n"
        "Напиши сильный авторский манифест (2–4 предложения)."
    )

    messages = [
        {"role": "system", "content": COPILOT_MANIFESTO_SYSTEM},
        {"role": "user", "content": prompt},
    ]

    engine_name, model = get_current_ai()
    sampling = {"temperature": 0.75, "max_tokens": 400}

    try:
        raw = await get_ai_response_async(engine_name, model, messages, sampling=sampling)
        if raw.startswith("❌") and engine_name != "qwen":
            engine_name, model = "qwen", "qwen2.5:7b"
            raw = await get_ai_response_async(engine_name, model, messages, sampling=sampling)
        manifesto = raw.strip().strip('"').strip('«»')
    except Exception as exc:
        logger.error("[COPILOT] generate manifesto failed: %s", exc)
        manifesto = (
            f"В проекте «{session.topic}» мы исследуем невидимые слои реальности "
            f"через синтез стилей {styles_str}. "
            "Кадр становится пространством, где свет ломает привычные формы, "
            "а тень обнажает скрытую суть человека."
        )

    session.manifesto = manifesto
    get_copilot_manager().save_session(session)
    return manifesto


async def refine_manifesto(session: CopilotSession, instruction: str) -> str:
    """Модифицирует существующий манифест по указанию или кастомному тексту автора."""
    current_manifesto = session.manifesto.strip()
    styles_str = (
        ", ".join(session.selected_styles) if session.selected_styles else "Свободный синтез"
    )

    instruction_map = {
        "darker": "Сделай манифест более мрачным, экзистенциальным, тревожным и контрастным.",
        "metaphoric": "Сделай манифест более метафоричным, поэтичным, сновидческим и воздушным.",
        "shorter": "Сократи манифест до ровно 2 предельно плотных и афористичных предложений.",
        "reroll": "Предложи совершенно другой ракурс и художественную метафору в манифесте.",
    }
    action_text = instruction_map.get(instruction, instruction)

    prompt = (
        f"Тема: «{session.topic}».\n"
        f"Стили: {styles_str}.\n"
        f"Текущий манифест:\n{current_manifesto}\n\n"
        f"Задача: перепиши манифест с учетом пожелания автора:\n"
        f"«{action_text}»\n\n"
        "Верни только обновленный текст манифеста (2–4 предложения)."
    )

    messages = [
        {"role": "system", "content": COPILOT_MANIFESTO_SYSTEM},
        {"role": "user", "content": prompt},
    ]

    engine_name, model = get_current_ai()
    sampling = {"temperature": 0.75, "max_tokens": 400}

    try:
        raw = await get_ai_response_async(engine_name, model, messages, sampling=sampling)
        if raw.startswith("❌") and engine_name != "qwen":
            engine_name, model = "qwen", "qwen2.5:7b"
            raw = await get_ai_response_async(engine_name, model, messages, sampling=sampling)
        manifesto = raw.strip().strip('"').strip('«»')
    except Exception as exc:
        logger.error("[COPILOT] refine manifesto failed: %s", exc)
        manifesto = current_manifesto

    session.manifesto = manifesto
    get_copilot_manager().save_session(session)
    return manifesto


def format_manifesto_card(session: CopilotSession) -> str:
    """Форматирует карточку манифеста для Telegram."""
    styles_str = ", ".join(
        f"{COPILOT_STYLES.get(s, {}).get('icon', '🎨')} <b>{s}</b>"
        for s in session.selected_styles
    ) if session.selected_styles else "<i>Свободный синтез</i>"

    manifesto_body = session.manifesto or "<i>Манифест формируется…</i>"

    return (
        f"📜 <b>Художественный манифест проекта</b>\n"
        f"Тема: «<b>{safe_html_format(session.topic)}</b>»\n"
        f"Стили: {styles_str}\n\n"
        f"<blockquote>{safe_html_format(manifesto_body)}</blockquote>\n\n"
        "<i>Скорректируйте тональность кнопками ниже "
        "или отправьте пожелание текстом/голосом:</i>"
    )


# ─── Шаг 10: Технический сетап и консультации арт-технолога ───

SUPPORT_PRESETS: dict[str, dict[str, str]] = {
    "handheld": {
        "name": "С рук (микро-ICM)",
        "shutter_speed": '1/6"',
        "notes": "Микро-тремор 1–2 мм между кадрами для живописного мазка",
    },
    "tripod": {
        "name": "Штатив (статика)",
        "shutter_speed": '1/15"',
        "notes": "Четкий контур неподвижных объектов, управляемый смаз",
    },
}

LENS_PRESETS: dict[str, dict[str, str]] = {
    "helios": {
        "name": "Гелиос 44-2 58mm f/2",
        "aperture": "f/2",
        "notes": "Закрученное боке на открытой, мягкий контраст",
    },
    "fuji": {
        "name": "Fujinon XF 18-55mm f/2.8-4 R LM OIS",
        "aperture": "f/2.8–f/4",
        "notes": "Оптический стаб OIS, быстрая резкость",
    },
}

FILTER_PRESETS: dict[str, str] = {
    "mist": "Black Pro-Mist 1/4 (ореол светов)",
    "prism": "Хрустальная треугольная призма",
    "none": "Без фильтра (чистая оптика)",
}

LIGHTING_PRESETS: dict[str, str] = {
    "backlight": "Контровой свет фонаря / силуэт",
    "flash": "Импульсный свет / жесткое боковое лезвие",
    "ambient": "Естественный рассеянный полумрак",
}

COPILOT_TECH_SYSTEM = (
    "Ты — опытный оператор и технолог художественной фотографии Fujifilm X-T4.\n"
    "Твоя цель — помочь фотографу адаптировать съемочные параметры камеры и арсенала "
    "под конкретные условия и творческий замысел.\n"
    "Отвечай лаконично (2–4 предложения): дай конкретный практический совет по выдержке, "
    "диафрагме, свету и положению камеры (руки vs штатив).\n"
    "Общайся на русском языке уважительно и профессионально."
)


def init_tech_preferences(session: CopilotSession) -> dict[str, Any]:
    """Инициализирует базовые технические параметры съемки на основе выбранных стилей и арсенала."""
    styles_lower = [s.lower() for s in session.selected_styles]

    if any(s in styles_lower for s in ("импрессионизм", "пиктореализм")):
        tech = {
            "camera": "Fujifilm X-T4",
            "lens": LENS_PRESETS["helios"]["name"],
            "support": SUPPORT_PRESETS["handheld"]["name"],
            "shutter_speed": '1/6"',
            "aperture": "f/2",
            "iso": "320",
            "film_sim": "Velvia" if "импрессионизм" in styles_lower else "Classic Chrome",
            "filter_accessory": FILTER_PRESETS["mist"],
            "lighting": LIGHTING_PRESETS["backlight"],
            "handwriting_notes": "Живописная лессировка, микро-тремор на 1/6s, мягкие света",
        }
    elif "экспрессионизм" in styles_lower:
        tech = {
            "camera": "Fujifilm X-T4",
            "lens": LENS_PRESETS["helios"]["name"],
            "support": SUPPORT_PRESETS["handheld"]["name"],
            "shutter_speed": '1/15"',
            "aperture": "f/2",
            "iso": "800",
            "film_sim": "Monochrome",
            "filter_accessory": FILTER_PRESETS["none"],
            "lighting": LIGHTING_PRESETS["flash"],
            "handwriting_notes": "Жесткий графичный контраст, тени-лезвия, эмоциональный накал",
        }
    else:
        tech = {
            "camera": "Fujifilm X-T4",
            "lens": LENS_PRESETS["fuji"]["name"],
            "support": SUPPORT_PRESETS["handheld"]["name"],
            "shutter_speed": '1/15"',
            "aperture": "f/2.8",
            "iso": "400",
            "film_sim": "Classic Chrome",
            "filter_accessory": FILTER_PRESETS["prism"],
            "lighting": LIGHTING_PRESETS["backlight"],
            "handwriting_notes": "Геометрические преломления, двойная экспозиция, сложная оптика",
        }

    session.tech_preferences = tech
    get_copilot_manager().save_session(session)
    return tech


def update_tech_preference(session: CopilotSession, key: str, value: str) -> None:
    """Обновляет отдельный параметр технического сетапа по кнопке."""
    if not session.tech_preferences:
        init_tech_preferences(session)

    tech = session.tech_preferences

    if key == "support":
        preset = SUPPORT_PRESETS.get(value, SUPPORT_PRESETS["handheld"])
        tech["support"] = preset["name"]
        tech["shutter_speed"] = preset["shutter_speed"]
    elif key == "lens":
        preset = LENS_PRESETS.get(value, LENS_PRESETS["helios"])
        tech["lens"] = preset["name"]
        tech["aperture"] = preset["aperture"]
    elif key == "filter":
        tech["filter_accessory"] = FILTER_PRESETS.get(value, FILTER_PRESETS["mist"])
    elif key == "light":
        tech["lighting"] = LIGHTING_PRESETS.get(value, LIGHTING_PRESETS["backlight"])

    session.tech_preferences = tech
    get_copilot_manager().save_session(session)


async def consult_tech_parameters(session: CopilotSession, user_input: str) -> str:
    """Консультирует автора по съемочным параметрам с учетом его пожеланий и обновляет настройки."""
    if not session.tech_preferences:
        init_tech_preferences(session)

    tech = session.tech_preferences
    user_lower = user_input.lower()

    if "штатив" in user_lower:
        tech["support"] = SUPPORT_PRESETS["tripod"]["name"]
        tech["shutter_speed"] = '1/15"'
    elif "рук" in user_lower or "тремор" in user_lower:
        tech["support"] = SUPPORT_PRESETS["handheld"]["name"]
        tech["shutter_speed"] = '1/6"'

    if "гелиос" in user_lower or "helios" in user_lower:
        tech["lens"] = LENS_PRESETS["helios"]["name"]
        tech["aperture"] = "f/2"
    elif "xf" in user_lower or "18-55" in user_lower:
        tech["lens"] = LENS_PRESETS["fuji"]["name"]
        tech["aperture"] = "f/2.8"

    if "призм" in user_lower:
        tech["filter_accessory"] = FILTER_PRESETS["prism"]
    elif "mist" in user_lower or "мист" in user_lower:
        tech["filter_accessory"] = FILTER_PRESETS["mist"]

    if "velvia" in user_lower or "вельвия" in user_lower:
        tech["film_sim"] = "Velvia"
    elif "монохром" in user_lower or "чб" in user_lower or "acros" in user_lower:
        tech["film_sim"] = "Monochrome"
    elif "хром" in user_lower or "chrome" in user_lower:
        tech["film_sim"] = "Classic Chrome"

    clean_note = user_input.strip()
    if clean_note:
        tech["handwriting_notes"] = clean_note[:120]

    prompt = (
        f"Тема: «{session.topic}».\n"
        f"Манифест: {session.manifesto}\n"
        f"Камера: {tech.get('camera')}, Объектив: {tech.get('lens')}, "
        f"Метод: {tech.get('support')}.\n"
        f"Выдержка: {tech.get('shutter_speed')}, Диафрагма: {tech.get('aperture')}, "
        f"ISO: {tech.get('iso')}, Пленка: {tech.get('film_sim')}.\n"
        f"Свет: {tech.get('lighting')}, Оптика: {tech.get('filter_accessory')}.\n\n"
        f"Пожелание/вопрос фотографа: «{user_input}»\n\n"
        "Дай короткий практический совет оператора (2–3 предложения) "
        "по реализации на Fujifilm X-T4."
    )

    messages = [
        {"role": "system", "content": COPILOT_TECH_SYSTEM},
        {"role": "user", "content": prompt},
    ]

    engine_name, model = get_current_ai()
    sampling = {"temperature": 0.7, "max_tokens": 300}

    try:
        raw = await get_ai_response_async(engine_name, model, messages, sampling=sampling)
        if raw.startswith("❌") and engine_name != "qwen":
            engine_name, model = "qwen", "qwen2.5:7b"
            raw = await get_ai_response_async(engine_name, model, messages, sampling=sampling)
        advice = raw.strip()
    except Exception as exc:
        logger.error("[COPILOT] consult tech failed: %s", exc)
        advice = (
            f"Для работы с «{tech.get('lens')}» на Fujifilm X-T4 рекомендую "
            f"зафиксировать выдержку {tech.get('shutter_speed')} "
            f"и диафрагму {tech.get('aperture')}. "
            "Используйте ручную фокусировку (Focus Peaking) для контроля микро-контраста."
        )

    session.tech_preferences = tech
    get_copilot_manager().save_session(session)
    return advice


def format_tech_card(session: CopilotSession, advice: str = "") -> str:
    """Форматирует карточку технических параметров съемки для Telegram."""
    tech = session.tech_preferences or {}
    camera = tech.get("camera", "Fujifilm X-T4")
    lens = tech.get("lens", "Гелиос 44-2 58mm f/2")
    support = tech.get("support", "С рук (микро-ICM)")
    filter_acc = tech.get("filter_accessory", "Black Pro-Mist 1/4")
    lighting = tech.get("lighting", "Контровой свет фонаря")
    shutter = tech.get("shutter_speed", '1/6"')
    aperture = tech.get("aperture", "f/2")
    iso = tech.get("iso", "400")
    film_sim = tech.get("film_sim", "Classic Chrome")
    notes = tech.get("handwriting_notes", "Микро-тремор рук, сочные тени")

    styles_str = ", ".join(
        f"{COPILOT_STYLES.get(s, {}).get('icon', '🎨')} <b>{s}</b>"
        for s in session.selected_styles
    ) if session.selected_styles else "<i>Свободный синтез</i>"

    lines = [
        "⚙️ <b>Съемочный сетап и почерк автора</b>",
        f"Тема: «<b>{safe_html_format(session.topic)}</b>»",
        f"Стили: {styles_str}\n",
        f"📷 <b>Камера:</b> {safe_html_format(camera)}",
        f"🔍 <b>Объектив:</b> <b>{safe_html_format(lens)}</b>",
        f"👐 <b>Метод съемки:</b> <b>{safe_html_format(support)}</b>",
        f"🔮 <b>Фильтр/Оптика:</b> {safe_html_format(filter_acc)}",
        f"💡 <b>Свет:</b> {safe_html_format(lighting)}\n",
        "⏱ <b>Параметры экспозиции:</b>",
        f"• Выдержка: <code>{safe_html_format(shutter)}</code>",
        f"• Диафрагма: <code>{safe_html_format(aperture)}</code>",
        f"• ISO: <code>{safe_html_format(iso)}</code>",
        f"• Профиль плёнки: <code>{safe_html_format(film_sim)}</code>\n",
        f"✍️ <b>Почерк и приём:</b> <i>{safe_html_format(notes)}</i>",
    ]

    if advice:
        lines.append(
            f"\n💡 <b>Совет оператора:</b>\n"
            f"<blockquote>{safe_html_format(advice)}</blockquote>"
        )

    lines.append(
        "\n<i>Переключайте сетап кнопками ниже "
        "или напишите условия съемки текстом/голосом:</i>"
    )
    return "\n".join(lines)
