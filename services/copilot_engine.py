"""services/copilot_engine.py — Движок Сократического диалога и арт-директуры копайлота.

Отвечает за:
- Живое соавторство (Сократический диалог, 1-2 острых вопроса за раз)
- Выявление скрытых смыслов, эмоционального ядра и визуальных парадоксов
- Автоматическую суммаризацию обсуждения в структурированное резюме концепта
"""

from __future__ import annotations

import html
import logging
import re
import time
from typing import Any

from services.ai_engine import get_ai_response_async, get_current_ai
from services.copilot_session import CopilotSession, get_copilot_manager
from services.fuji_recipes import (
    FujiRecipe,
    build_fuji_recipe_for_project,
    format_fuji_recipe_card,
    generate_surreal_stochastic_recipe,
)
from services.json_parser import extract_json_from_text, extract_partial_json_array
from services.text_formatter import safe_html_format

logger = logging.getLogger("CopilotEngine")

COPILOT_SOCRATIC_SYSTEM = """Ты — проницательный арт-директор и режиссёр авторской фотографии.
Твоя задача — вести живой, глубокий и сжатый диалог с фотографом, переводя его
психологические мысли на язык визуальных образов, света, пластики и оптики.

ПРАВИЛА ЖИВОГО СОАВТОРСТВА:
1. НИКАКИХ ШАБЛОНОВ И ПОВТОРОВ: Категорически запрещено повторять любые фразы или
   вопросы из твоих предыдущих реплик и использовать штампы вроде
   «Это перекликается с твоим размышлением...».
2. ОТ ПСИХОЛОГИИ — К КАДРУ (1–2 предложения): Услышь парадокс в словах автора
   (например, ироничный смех как маска боли) и сразу покажи, как это выглядит
   ОПТИЧЕСКИ и ПЛАСТИЧЕСКИ в кадре (мимика, напряжение пальцев, взгляд в расфокусе,
   жёсткая вспышка, двойная экспозиция, отражение).
3. РЕАКЦИЯ НА КОРОТКОЕ СОГЛАСИЕ: Если фотограф ответил кратко («Да», «Это именно
   такая попытка», «Согласен»), не топчись на месте с абстрактными вопросами —
   сам предложи 2 конкретные контрастные мизансцены (свет, жест, деталь) и спроси,
   какая ближе.
4. РОВНО ОДИН РЕЖИССЁРСКИЙ ВОПРОС В КОНЦЕ: Спрашивай не как психотерапевт
   («что помогает тебе преодолеть депрессию?»), а как режиссёр кадра: через какую
   деталь, жест, свет или фактуру мы сделаем эту внутреннюю драму видимой зрителю?
5. ОБЪЁМ: 3–4 ёмких, образных предложения без воды. Язык — живой русский.
"""

COPILOT_SUMMARIZE_SYSTEM = """Ты — арт-куратор.
Извлеки из диалога фотографа и арт-директора суть и сформируй структурированное резюме.

ФОРМАТ ВЫВОДА (кратко, тезисно, без воды):
🎯 <b>Концептуальный конфликт:</b> [главная идея и психологический нерв]
💡 <b>Ключевая метафора:</b> [визуальный образ / символ]
🏛 <b>Пространство и свет:</b> [локация, качество освещения, атмосфера]
👤 <b>Герой / Объект:</b> [кто или что в кадре, телесность, пластика]
"""


def _normalize_sentence(sentence: str) -> str:
    """Нормализует предложение для сравнения на дубликаты."""
    return re.sub(r"\W+", " ", sentence.lower()).strip()


def _deduplicate_assistant_reply(
    reply: str,
    previous_assistant_messages: list[str],
) -> str:
    """Удаляет из нового ответа предложения, дословно повторяющие прошлые реплики ассистента."""
    clean_reply = (reply or "").strip()
    if not clean_reply or not previous_assistant_messages:
        return clean_reply

    seen_norm: set[str] = set()
    for prev in previous_assistant_messages:
        for sent in re.split(r"(?<=[.!?…])\s+", prev.strip()):
            norm = _normalize_sentence(sent)
            if len(norm) >= 12:
                seen_norm.add(norm)

    if not seen_norm:
        return clean_reply

    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?…])\s+", clean_reply)
        if s.strip()
    ]
    kept = [
        s for s in sentences
        if _normalize_sentence(s) not in seen_norm
    ]
    if kept:
        return " ".join(kept)
    return ""


def build_socratic_messages(
    topic: str,
    dialogue_history: list[dict[str, Any]],
    palace_resonances: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Формирует список сообщений для языковой модели Сократического диалога."""
    system_content = f"{COPILOT_SOCRATIC_SYSTEM}\n\nТЕМА ПРОЕКТА: «{topic}»."
    if palace_resonances:
        from services.copilot_palace_bridge import format_palace_resonances_context

        res_ctx = format_palace_resonances_context(palace_resonances)
        if res_ctx:
            system_content += f"\n\n{res_ctx}"

    user_msgs = [
        str(e.get("content", "")).strip()
        for e in dialogue_history
        if e.get("role") == "user" and str(e.get("content", "")).strip()
    ]
    assistant_msgs = [
        str(e.get("content", "")).strip()
        for e in dialogue_history
        if e.get("role") == "assistant" and str(e.get("content", "")).strip()
    ]

    turn_num = len(user_msgs)
    if turn_num == 1:
        system_content += (
            "\n\nФОКУС ТЕКУЩЕГО ШАГА (Шаг 1 — Пластика, жест и деталь в кадре):\n"
            "Переведи психологическую мысль фотографа в зримый пластический образ "
            "(мимика, руки, взгляд, маска, предмет-триггер, крупность плана). "
            "Задай 1 вопрос о том, какая визуальная деталь в кадре выдаст этот внутренний конфликт."
        )
    elif turn_num == 2:
        system_content += (
            "\n\nФОКУС ТЕКУЩЕГО ШАГА (Шаг 2 — Светотень, среда и оптика):\n"
            "Предложи решение через свет и оптическую фактуру (жёсткий рисующий луч, "
            "контровой силуэт, отражение в стекле/воде, смаз на длинной выдержке "
            "или вихревое боке). "
            "Задай 1 вопрос о пространстве и характере света в этой сцене."
        )
    elif turn_num >= 3:
        system_content += (
            "\n\nФОКУС ТЕКУЩЕГО ШАГА (Шаг 3 — Сборка мизансцены):\n"
            "Собери найденные образы в цельную мизансцену кадра, предложи конкретный "
            "композиционный акцент и уточни финальный штрих перед переходом к выбору стилей."
        )

    if user_msgs and len(user_msgs[-1].split()) <= 7:
        system_content += (
            f"\n\nВАЖНО: Фотограф дал краткое согласие («{user_msgs[-1]}»). "
            "НЕ задавай абстрактных вопросов! Предложи 2 конкретных контрастных визуальных "
            "решения этого кадра (Вариант 1 и Вариант 2: жест, свет, оптика) и спроси, какой ближе."
        )

    if assistant_msgs:
        system_content += (
            "\n\nЗАПРЕТ НА САМОПОВТОРЫ: НИКОГДА не повторяй и не начинай ответ с фраз, "
            "которые ты уже произносил в прошлых репликах. Пиши только новую мысль в ответ на "
            "последнее сообщение фотографа."
        )

    messages: list[dict[str, str]] = [{"role": "system", "content": system_content}]

    # Гарантируем чередование user -> assistant для корректной работы chat-шаблона Qwen/Ollama
    non_empty = [
        (str(e.get("role", "user")), str(e.get("content", "")).strip())
        for e in dialogue_history
        if str(e.get("content", "")).strip()
    ]
    if non_empty and non_empty[0][0] == "assistant":
        messages.append({
            "role": "user",
            "content": f"Тема моего фотопроекта: «{topic}». Помоги раскрыть её визуально.",
        })

    for role, content in non_empty:
        messages.append({"role": role, "content": content})

    return messages


async def generate_socratic_reply(session: CopilotSession, user_input: str) -> str:
    """Обрабатывает реплику пользователя и генерирует следующий вопрос/мысль арт-директора."""
    previous_assistant = [
        str(m.get("content", "")).strip()
        for m in session.dialogue_history
        if m.get("role") == "assistant" and str(m.get("content", "")).strip()
    ]
    session.add_user_message(user_input)
    from services.copilot_palace_bridge import get_or_find_session_resonances

    resonances = get_or_find_session_resonances(session)
    messages = build_socratic_messages(
        session.topic, session.dialogue_history, palace_resonances=resonances,
    )

    engine, model = get_current_ai()
    sampling = {"temperature": 0.7, "max_tokens": 500}

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

        reply = _deduplicate_assistant_reply(raw.strip(), previous_assistant)
        if not reply:
            reply = (
                f"Если перевести мысль «{user_input[:60]}» в плоскость кадра, "
                "то возникает выбор между двумя приёмами: застывшая маска лица в жёстком "
                "контрастном свете или раздвоение фигуры через отражение и длинную выдержку. "
                "Какое из этих двух визуальных решений точнее передаёт твой замысел?"
            )
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
    from services.copilot_palace_bridge import (
        format_palace_resonances_context,
        get_or_find_session_resonances,
    )

    resonances = get_or_find_session_resonances(session)
    system_content = COPILOT_SOCRATIC_SYSTEM
    if resonances:
        res_ctx = format_palace_resonances_context(resonances)
        if res_ctx:
            system_content += f"\n\n{res_ctx}"

    prompt = (
        f"Фотограф выбрал тему для арт-проекта: «{session.topic}».\n"
        "В 1–2 ёмких предложениях вскрой внутренний визуальный парадокс или драматургическое "
        "напряжение этой темы (без шаблонных вступлений) и задай ровно один точный вопрос, "
        "который поможет увидеть главный конфликт будущего кадра."
    )
    messages = [
        {"role": "system", "content": system_content},
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


# ─── Шаг 11: Контрастная дивергенция вариантов и интерактивный выбор ───

COPILOT_VARIANTS_SYSTEM = (
    "Ты — главный куратор визуального искусства и арт-директор фотопроектов.\n"
    "Твоя задача — сгенерировать ровно 3 диаметрально противоположных, контрастных "
    "художественных концепт-проекта на основе темы, манифеста и сетапа автора.\n\n"
    "ПРАВИЛО КОНТРАСТА (3 разных вектора):\n"
    "1. Вектор «Интимный / Камерный»: психологический портрет, деталь, отражение в стекле, "
    "закрученное боке, мягкое свечение.\n"
    "2. Вектор «Монументальный / Геометрический»: пространство города/интерьера, жесткий свет, "
    "силуэт человека в масштабе среды, графичные тени-лезвия.\n"
    "3. Вектор «Экспериментальный / Оптический»: оптическое расщепление, призма, "
    "мультиэкспозиция, микро-ICM лессировка, сновидческая деконструкция формы.\n\n"
    "Верни ответ СТРОГО в виде JSON-массива из 3 объектов:\n"
    "[\n"
    "  {\n"
    '    "id": 1,\n'
    '    "title": "Название проекта",\n'
    '    "vector": "Интимный / Камерный",\n'
    '    "visual_hook": "Точное описание главного визуального кадра (образ, герой, деталь)",\n'
    '    "lighting_scene": "Световая схема и атмосфера кадра",\n'
    '    "camera_setup": "Камера, выдержка, диафрагма, ISO, пленочный профиль",\n'
    '    "shooting_action": "Физическое действие фотографа (микро-тремор, призма, проводка)",\n'
    '    "gear_summary": "Связка техники (камера + объектив + фильтр)",\n'
    '    "shooting_steps": ["Шаг 1...", "Шаг 2...", "Шаг 3..."]\n'
    "  }\n"
    "]"
)


def _build_fallback_contrast_variants(session: CopilotSession) -> list[dict[str, Any]]:
    """Надежные кураторские шаблоны проектов при недоступности внешних моделей."""
    tech = session.tech_preferences or {}
    cam = tech.get("camera", "Fujifilm X-T4")
    lens = tech.get("lens", "Гелиос 44-2 58mm f/2")
    sim = tech.get("film_sim", "Classic Chrome")
    shutter = tech.get("shutter_speed", '1/6"')
    aperture = tech.get("aperture", "f/2")

    return [
        {
            "id": 1,
            "title": f"«Зеркальная тень: {session.topic}»",
            "vector": "Интимный / Камерный",
            "visual_hook": (
                "Крупный план человека в профиль на фоне мокрого оконного стекла в полумраке. "
                "В отражении проступает второй силуэт, олицетворяющий скрытую суть."
            ),
            "lighting_scene": (
                "Мягкий контровой свет фонаря, бархатное гало хайлайтов от Black Pro-Mist 1/4."
            ),
            "camera_setup": f"{cam} • {lens} • {aperture} • {shutter} • ISO 400 • {sim}",
            "shooting_action": (
                "Съемка с рук с легким микро-тремором на выдержке 1/6s "
                "для мягкого размытия фонового боке."
            ),
            "gear_summary": f"{cam} + {lens} + Black Pro-Mist 1/4",
            "shooting_steps": [
                "Расположите героя у зеркала или витрины с контровым фонарным светом",
                f"Выставьте выдержку {shutter} и открытую диафрагму {aperture}",
                "Сделайте серию кадров с микро-смещением камеры между дублями",
            ],
        },
        {
            "id": 2,
            "title": f"«Монумент пустоты: {session.topic}»",
            "vector": "Монументальный / Геометрический",
            "visual_hook": (
                "Одинокая фигура в глубине холодного бетонного вестибюля. "
                "Резкий луч света рассекает пол по диагонали, отбрасывая острую тень-лезвие."
            ),
            "lighting_scene": (
                "Жесткий направленный боковой луч света, глубокие провалы теней (кьяроскуро)."
            ),
            "camera_setup": f"{cam} • Fujinon XF 18-55mm • f/4 • 1/15\" • ISO 800 • Monochrome",
            "shooting_action": (
                "Съемка со штатива с выверенным геометрическим горизонтом "
                "и фиксацией резкости по кромке тени."
            ),
            "gear_summary": f"{cam} + Fujinon XF 18-55mm + Штатив",
            "shooting_steps": [
                "Найдите локацию с ритмичными архитектурными колоннами или арками",
                "Зафиксируйте камеру на штативе на уровне пояса",
                "Дождитесь прохождения силуэта через световой клин и сделайте кадр",
            ],
        },
        {
            "id": 3,
            "title": f"«Оптический разлом: {session.topic}»",
            "vector": "Экспериментальный / Оптический",
            "visual_hook": (
                "Лицо и руки героя двоятся и преломляются сквозь грани стеклянной призмы. "
                "Цветовые спектры и микро-ICM превращают фон в вибрирующую живописную абстракцию."
            ),
            "lighting_scene": "Контровой свет витрин, цветные рефлексы в гранях призмы.",
            "camera_setup": f"{cam} • {lens} • {aperture} • {shutter} • ISO 320 • Velvia",
            "shooting_action": (
                "Удержание призмы вплотную к передней линзе левой рукой "
                "с плавным вращением при нажатии на спуск."
            ),
            "gear_summary": f"{cam} + {lens} + Хрустальная призма",
            "shooting_steps": [
                "Поднесите треугольную призму ребром к краю передней линзы",
                "Поймайте преломленный блик контрового источника света",
                "Включите режим мультиэкспозиции (2 кадра) для наложения спектров",
            ],
        },
    ]


async def generate_contrast_variants(session: CopilotSession) -> list[dict[str, Any]]:
    """Генерирует 2–3 контрастных проектных вектора под тему, манифест и сетап автора."""
    tech = session.tech_preferences or {}
    styles_str = (
        ", ".join(session.selected_styles) if session.selected_styles else "Свободный синтез"
    )

    prompt = (
        f"Тема проекта: «{session.topic}».\n"
        f"Выбранные стили: {styles_str}.\n"
        f"Концептуальное резюме:\n{session.summary}\n"
        f"Манифест:\n{session.manifesto}\n"
        f"Съемочный сетап X-T4:\n"
        f"- Камера: {tech.get('camera')}\n"
        f"- Объектив: {tech.get('lens')}\n"
        f"- Метод: {tech.get('support')}\n"
        f"- Параметры: {tech.get('shutter_speed')}, {tech.get('aperture')}, "
        f"{tech.get('film_sim')}\n"
        f"- Свет: {tech.get('lighting')}\n"
        f"- Оптика/Фильтр: {tech.get('filter_accessory')}\n"
        f"- Почерк автора: {tech.get('handwriting_notes')}\n\n"
        "Сгенерируй ровно 3 контрастных проекта (Интимный, Монументальный, Экспериментальный) "
        "в формате JSON-массива."
    )

    messages = [
        {"role": "system", "content": COPILOT_VARIANTS_SYSTEM},
        {"role": "user", "content": prompt},
    ]

    engine_name, model = get_current_ai()
    sampling = {"temperature": 0.8, "max_tokens": 1200}

    projects: list[dict[str, Any]] = []

    try:
        raw = await get_ai_response_async(engine_name, model, messages, sampling=sampling)
        if raw.startswith("❌") and engine_name != "qwen":
            engine_name, model = "qwen", "qwen2.5:7b"
            raw = await get_ai_response_async(engine_name, model, messages, sampling=sampling)

        parsed = extract_json_from_text(raw)
        if isinstance(parsed, list) and len(parsed) >= 2:
            projects = parsed
        elif (
            isinstance(parsed, dict)
            and "projects" in parsed
            and isinstance(parsed["projects"], list)
        ):
            projects = parsed["projects"]
        else:
            partial = extract_partial_json_array(
                raw, array_keys=["projects", "variants", "items"],
            )
            if partial and len(partial) >= 2:
                projects = partial
    except Exception as exc:
        logger.error("[COPILOT] generate variants failed: %s", exc)

    if not projects or len(projects) < 2:
        projects = _build_fallback_contrast_variants(session)

    normalized: list[dict[str, Any]] = []
    default_vectors = [
        "Интимный / Камерный",
        "Монументальный / Средовой",
        "Экспериментальный / Оптический",
    ]
    for i, p in enumerate(projects[:3]):
        if isinstance(p, dict):
            p["id"] = i + 1
            if "title" not in p:
                p["title"] = f"Проект {i + 1}"
            if "vector" not in p:
                p["vector"] = default_vectors[min(i, 2)]
            normalized.append(p)

    if not normalized:
        normalized = _build_fallback_contrast_variants(session)

    session.candidate_projects = normalized
    session.stage = "variants"
    get_copilot_manager().save_session(session)
    return normalized


def format_single_variant_card(session: CopilotSession, idx: int = 0) -> str:
    """Форматирует карточку конкретного варианта проекта для Telegram."""
    projects = session.candidate_projects or []
    if not projects:
        return "<i>Варианты проектов еще не сформированы.</i>"

    idx = max(0, min(idx, len(projects) - 1))
    p = projects[idx]
    total = len(projects)

    title = p.get("title", f"Проект {idx + 1}")
    vector = p.get("vector", "Авторский вектор")
    hook = p.get("visual_hook", "")
    light = p.get("lighting_scene", "")
    camera = p.get("camera_setup", "")
    action = p.get("shooting_action", "")
    gear = p.get("gear_summary", "")
    steps = p.get("shooting_steps", [])

    steps_fmt = "\n".join(f"  👉 <i>{safe_html_format(s)}</i>" for s in steps) if steps else ""

    is_selected = (session.selected_project_idx == idx)
    status_badge = " ⭐️ <b>[ГЛАВНЫЙ ВЫБОР]</b>" if is_selected else ""

    return (
        f"🎨 <b>Проект {idx + 1} из {total}: «{safe_html_format(title)}»</b>{status_badge}\n"
        f"🎯 <b>Вектор:</b> <i>{safe_html_format(vector)}</i>\n\n"
        f"🖼 <b>Визуальный образ кадра:</b>\n<blockquote>{safe_html_format(hook)}</blockquote>\n\n"
        f"💡 <b>Свет и сцена:</b> {safe_html_format(light)}\n"
        f"🎒 <b>Арсенал:</b> <code>{safe_html_format(gear)}</code>\n"
        f"📷 <b>Параметры съёмки:</b> <code>{safe_html_format(camera)}</code>\n\n"
        f"👐 <b>Физика действия:</b>\n{safe_html_format(action)}\n\n"
        + (f"📋 <b>Шаги реализации:</b>\n{steps_fmt}\n\n" if steps_fmt else "")
        + "<i>Переключайте проекты вкладками ниже или утвердите вариант кнопкой:</i>"
    )


async def refine_active_variant(session: CopilotSession, user_input: str, idx: int = 0) -> str:
    """Точечно дорабатывает проект по замечанию или идее автора."""
    projects = session.candidate_projects or []
    if not projects:
        await generate_contrast_variants(session)
        projects = session.candidate_projects or []

    idx = max(0, min(idx, len(projects) - 1))
    p = projects[idx]

    prompt = (
        f"Тема: «{session.topic}».\n"
        f"Проект: «{p.get('title')}» ({p.get('vector')}).\n"
        f"Текущий главный кадр: {p.get('visual_hook')}\n"
        f"Свет: {p.get('lighting_scene')}\n\n"
        f"Пожелание автора по доработке: «{user_input}»\n\n"
        "Обнови описание главного кадра (visual_hook) и света (lighting_scene). "
        "Верни ответ кратко в формате:\n"
        "КАДР: [обновленный образ]\n"
        "СВЕТ: [обновленный свет]\n"
        "СОВЕТ: [краткий комментарий арт-директора]"
    )

    messages = [
        {
            "role": "system",
            "content": "Ты — арт-директор. Доработай концепцию кадра по правке автора.",
        },
        {"role": "user", "content": prompt},
    ]

    engine_name, model = get_current_ai()
    sampling = {"temperature": 0.75, "max_tokens": 400}

    try:
        raw = await get_ai_response_async(engine_name, model, messages, sampling=sampling)
        if raw.startswith("❌") and engine_name != "qwen":
            engine_name, model = "qwen", "qwen2.5:7b"
            raw = await get_ai_response_async(engine_name, model, messages, sampling=sampling)

        hook_match = re.search(r"КАДР:\s*(.+?)(?=\nСВЕТ:|$)", raw, re.DOTALL | re.IGNORECASE)
        light_match = re.search(r"СВЕТ:\s*(.+?)(?=\nСОВЕТ:|$)", raw, re.DOTALL | re.IGNORECASE)
        advice_match = re.search(r"СОВЕТ:\s*(.+?)$", raw, re.DOTALL | re.IGNORECASE)

        if hook_match:
            p["visual_hook"] = hook_match.group(1).strip()
        if light_match:
            p["lighting_scene"] = light_match.group(1).strip()
        advice = advice_match.group(1).strip() if advice_match else "Правки внесены в проект."
    except Exception as exc:
        logger.error("[COPILOT] refine variant failed: %s", exc)
        p["visual_hook"] = f"{p.get('visual_hook')} (Учтено: {user_input[:80]})"
        advice = f"Учтено пожелание автора: {user_input[:80]}"

    session.candidate_projects[idx] = p
    get_copilot_manager().save_session(session)
    return advice


# ─── Шаг 12 (CP-6): Полевой ассистент, Midjourney-эскизы и Apple Notes ───

STYLE_MIDJOURNEY_KEYWORDS: dict[str, str] = {
    "Сюрреализм": (
        "surrealism aesthetic, dreamlike metaphysical composition, "
        "subconscious symbolism, Rene Magritte mood"
    ),
    "Пиктореализм": (
        "pictorialism photo, soft-focus pictorial glow, painterly tonalism, "
        "fine art vintage texture"
    ),
    "Экспрессионизм": (
        "German expressionist cinema aesthetic, dramatic chiaroscuro lighting, "
        "deep sharp angular shadows, psychological tension"
    ),
    "Импрессионизм": (
        "impressionistic photography, luminous color vibration, "
        "watercolor brush wash effect, intentional camera movement ICM blur"
    ),
    "Конструктивизм": (
        "Russian constructivism aesthetic, Alexander Rodchenko diagonal composition, "
        "dynamic industrial geometry, bold stark graphic lines"
    ),
}


def build_raw_midjourney_prompt(
    session: CopilotSession,
    aspect_ratio: str = "16:9",
    mode: str = "raw",
) -> str:
    """Генерирует чистый англоязычный промпт для Midjourney v6.1 / Flux."""
    from services.style_fusion import (
        build_arsenal_optics_mj_tokens,
        build_fuji_recipe_mj_tokens,
        build_mj_technical_flags,
        translate_ru_photo_terms_to_en,
    )

    project = session.get_active_project()
    hook = project.get("visual_hook") or session.topic
    parts: list[str] = [
        "unretouched raw analog 35mm photograph, authentic optical physics, "
        "natural surface micro-texture"
    ]

    # Стилистические ключевые слова
    for st in session.selected_styles:
        mod = STYLE_MIDJOURNEY_KEYWORDS.get(st)
        if mod:
            parts.append(mod)

    # Визуальный хук/сцена + англоязычный фотографический перевод
    if hook:
        en_hook = translate_ru_photo_terms_to_en(hook)
        if en_hook:
            parts.append(f"cinematic shot of {hook} ({en_hook})")
        else:
            parts.append(f"cinematic shot of {hook}")

    # Свет
    light = project.get("lighting_scene") or session.tech_preferences.get("lighting", "")
    if light:
        light_lower = light.lower()
        en_light = translate_ru_photo_terms_to_en(light)
        if "контровой" in light_lower:
            parts.append("strong dramatic rim backlight, cinematic halo lighting")
        elif "импульс" in light_lower or "лезви" in light_lower:
            parts.append("hard razor-sharp directional shadow lines, harsh contrast lighting")
        elif "рассеян" in light_lower:
            parts.append("soft diffused atmospheric ambient glow")
        else:
            parts.append(f"dramatic artistic lighting: {light[:60]}")
        if en_light and en_light not in " ".join(parts):
            parts.append(en_light)

    # Оптика, насадки, фильтры и метод съемки
    tech = session.tech_preferences or {}
    lens_str = str(tech.get("lens") or "")
    filt_str = str(tech.get("filter_accessory") or "")
    supp_str = str(tech.get("support") or "")
    act_str = f"{supp_str} {project.get('shooting_action', '')}".strip()

    parts.extend(
        build_arsenal_optics_mj_tokens(
            lens_raw=lens_str,
            filter_raw=filt_str,
            action_raw=act_str,
            default_lens_label="Fujinon",
        )
    )
    if any(w in supp_str.lower() for w in ("руки", "icm", "тремор")):
        parts.append(
            "subtle intentional camera movement ICM blur, layered exposure watercolor feel"
        )

    # Внутрикамерный рецепт и эмульсия плёнки Fujifilm X-T4
    saved_rec = tech.get("fuji_recipe")
    film_sim_pref = tech.get("film_sim")
    if isinstance(saved_rec, dict):
        emulsion_str = build_fuji_recipe_mj_tokens(saved_rec, include_velvia_legacy=True)
    elif film_sim_pref:
        emulsion_str = build_fuji_recipe_mj_tokens(str(film_sim_pref), include_velvia_legacy=True)
    else:
        try:
            recipe = build_fuji_recipe_for_project(session)
            emulsion_str = build_fuji_recipe_mj_tokens(recipe, include_velvia_legacy=True)
        except Exception:  # noqa: BLE001
            emulsion_str = build_fuji_recipe_mj_tokens("Velvia/Яркий", include_velvia_legacy=True)

    flags = build_mj_technical_flags(aspect_ratio=aspect_ratio, mode=mode)
    parts.append(
        f"{emulsion_str}, fine art gallery photography, editorial aesthetic, "
        f"35mm film grain {flags}"
    )

    return ", ".join(parts)


def generate_midjourney_prompt(
    session: CopilotSession,
    aspect_ratio: str = "16:9",
    mode: str = "raw",
) -> str:
    """Форматирует сообщение с Midjourney-промптом для Telegram с кликабельным <code> блоком."""
    raw_prompt = build_raw_midjourney_prompt(
        session, aspect_ratio=aspect_ratio, mode=mode
    )
    project = session.get_active_project()
    title = project.get("title", session.topic)
    mode_label = (
        "📷 Фотореализм (Raw)" if mode == "raw" else "🖼 Галерейный арт (Art)"
    )

    return (
        f"🎨 <b>Эскизный промпт для нейросетей (Midjourney v6.1 / Flux)</b>\n"
        f"Проект: «{safe_html_format(title)}»\n"
        f"Режим: <b>{mode_label}</b> | Формат: <code>--ar {aspect_ratio}</code>\n\n"
        f"<i>Используйте этот промпт для генерации раскадровки сцены перед съемкой:</i>\n\n"
        f"<code>{html.escape(raw_prompt)}</code>\n\n"
        f"💡 <i>Нажмите на блок с кодом выше, чтобы скопировать промпт в один клик.</i>"
    )


def get_or_create_fuji_recipe(
    session: CopilotSession,
    stochastic: bool = False,
    intensity: str = "wild",
) -> FujiRecipe:
    """Возвращает сохраненный или генерирует внутрикамерный рецепт Fujifilm X-T4 для сессии."""
    tech = session.tech_preferences or {}
    saved_recipe_dict = tech.get("fuji_recipe")

    if not stochastic and isinstance(saved_recipe_dict, dict):
        return FujiRecipe.from_dict(saved_recipe_dict)

    if stochastic:
        recipe = generate_surreal_stochastic_recipe(session, intensity=intensity)
    else:
        recipe = build_fuji_recipe_for_project(session)

    tech["fuji_recipe"] = recipe.to_dict()
    tech["film_sim"] = recipe.film_simulation
    session.tech_preferences = tech
    get_copilot_manager().save_session(session)
    return recipe


def format_copilot_recipe_card(
    session: CopilotSession,
    slot_name: str = "C1",
    stochastic: bool = False,
) -> str:
    """Форматирует визуальную карточку внутрикамерного рецепта для вывода в Telegram."""
    recipe = get_or_create_fuji_recipe(session, stochastic=stochastic)
    return format_fuji_recipe_card(recipe, slot_name=slot_name)


def generate_field_assistant_checklist(session: CopilotSession) -> str:
    """Форматирует карманную шпаргалку / чек-лист перед съемкой для Telegram."""
    project = session.get_active_project()
    title = project.get("title", session.topic or "Фотопроект")
    vector = project.get("vector", "Авторский вектор")
    styles_str = (
        ", ".join(session.selected_styles)
        if session.selected_styles
        else "Стиль автора"
    )

    tech = session.tech_preferences or {}
    lens = tech.get("lens", "Гелиос 44-2 58mm f/2")
    filt = tech.get("filter_accessory", "Black Pro-Mist 1/4")
    supp = tech.get("support", "Съемка с рук (микро-ICM)")
    light = project.get("lighting_scene") or tech.get("lighting", "Естественный / Контровой")
    cam_setup = project.get(
        "camera_setup", "1/15 с, f/2, ISO 160, Velvia, Тоновая кривая: -1/+1"
    )
    action = project.get(
        "shooting_action", "Фиксация камеры, микро-смещение в момент экспозиции"
    )
    steps = project.get("shooting_steps") or [
        "Оценить геометрию локации и направление основного источника света",
        "Установить объектив и насадку, выставить базовые параметры X-T4",
        "Проверить Focus Peaking по главному объекту",
        "Сделать тестовый кадр, скорректировать экспозицию по гистограмме",
        "Выполнить серию из 3-5 кадров с контролем физики движения",
    ]

    hook = project.get("visual_hook", "")
    recipe = get_or_create_fuji_recipe(session)

    lines = [
        f"🎒 <b>Полевой ассистент съемки: «{safe_html_format(title)}»</b>\n",
        f"📌 <b>Тема:</b> {safe_html_format(session.topic)}",
        f"🎭 <b>Стили:</b> <i>{safe_html_format(styles_str)}</i>",
        f"🎯 <b>Вектор:</b> <i>{safe_html_format(vector)}</i>\n",
    ]

    if hook:
        lines.append(
            f"🖼 <b>Главный кадр:</b>\n<blockquote>{safe_html_format(hook)}</blockquote>\n"
        )

    lines.extend([
        "✅ <b>Чек-лист перед выходом:</b>",
        "   ▫️ Камера: <b>Fujifilm X-T4</b>",
        f"   ▫️ Объектив: <code>{safe_html_format(lens)}</code>",
        f"   ▫️ Насадка / фильтр: <code>{safe_html_format(filt)}</code>",
        "   ▫️ Аккумуляторы: 2x NP-W235 (полный заряд)",
        "   ▫️ SD-карта: UHS-II (проверен слот 1, свободное место)",
        "   ▫️ Микрофибра и груша для чистки оптики",
    ])

    if "штатив" in supp.lower():
        lines.append("   ▫️ Опора: Штатив и устойчивая площадка")
    else:
        lines.append("   ▫️ Опора: Съемка с рук (без тяжелого штатива)")

    lines.extend([
        "",
        "⚙️ <b>Параметры Fujifilm X-T4:</b>",
        (
            f"   ▫️ Рецепт: <code>{safe_html_format(recipe.recipe_name)} "
            f"({recipe.film_simulation})</code>"
        ),
        f"   ▫️ Настройки: <code>{safe_html_format(cam_setup)}</code>",
        f"   ▫️ Метод стабилизации: <i>{safe_html_format(supp)}</i>",
        "",
        "💡 <b>Свет и атмосфера:</b>",
        f"   ▫️ {safe_html_format(light)}",
        "",
        "👐 <b>Физика съемки (действие фотографа):</b>",
        f"   ▫️ {safe_html_format(action)}",
        "",
        "📋 <b>План действий на локации:</b>",
    ])

    for i, s in enumerate(steps, start=1):
        lines.append(f"   {i}. {safe_html_format(s)}")

    lines.extend([
        "",
        "<i>Используйте кнопки ниже для генерации Midjourney-промпта "
        "или экспорта в Apple Notes.</i>",
    ])

    return "\n".join(lines)


def format_copilot_project_for_notes(
    session: CopilotSession,
) -> tuple[str, str]:
    """Форматирует проект копайлота в Markdown для Apple Notes со статусом [К съемке]."""
    project = session.get_active_project()
    title = project.get("title", session.topic or "Фотопроект")
    note_title = f"[К съемке] {title}"

    styles_str = (
        ", ".join(session.selected_styles)
        if session.selected_styles
        else "Авторский стиль"
    )
    vector = project.get("vector", "Кураторский вектор")
    created_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(session.updated_at))

    tech = session.tech_preferences or {}
    lens = tech.get("lens", "Гелиос 44-2 58mm f/2")
    filt = tech.get("filter_accessory", "Black Pro-Mist 1/4")
    supp = tech.get("support", "Съемка с рук (микро-ICM)")
    light = project.get("lighting_scene") or tech.get("lighting", "Естественный / Контровой")
    cam_setup = project.get("camera_setup", "1/15 с, f/2, ISO 160, Velvia")
    action = project.get(
        "shooting_action", "Фиксация камеры, микро-смещение в момент экспозиции"
    )
    steps = project.get("shooting_steps") or [
        "Оценить геометрию локации и направление основного света",
        "Установить объектив и насадку, выставить базовые параметры X-T4",
        "Проверить Focus Peaking по главному объекту",
        "Сделать тестовый кадр, скорректировать экспозицию",
        "Выполнить серию кадров с контролем физики движения",
    ]
    hook = project.get("visual_hook", "")
    manifesto = session.manifesto or "Художественное кредо проекта."
    summary = session.summary or "Обсуждение темы зафиксировано автором."
    mj_prompt = build_raw_midjourney_prompt(session)
    recipe = get_or_create_fuji_recipe(session)
    r_hl = f"{recipe.highlight_tone:+.1f}" if recipe.highlight_tone != 0 else "0.0"
    r_sh = f"{recipe.shadow_tone:+.1f}" if recipe.shadow_tone != 0 else "0.0"
    r_col = f"+{recipe.color}" if recipe.color > 0 else str(recipe.color)
    r_sharp = f"+{recipe.sharpness}" if recipe.sharpness > 0 else str(recipe.sharpness)
    r_nr = f"+{recipe.high_iso_nr}" if recipe.high_iso_nr > 0 else str(recipe.high_iso_nr)
    r_clar = f"+{recipe.clarity}" if recipe.clarity > 0 else str(recipe.clarity)
    r_wbr = f"+{recipe.wb_shift_r}" if recipe.wb_shift_r > 0 else str(recipe.wb_shift_r)
    r_wbb = f"+{recipe.wb_shift_b}" if recipe.wb_shift_b > 0 else str(recipe.wb_shift_b)

    supp_item = (
        "- [ ] Штатив и устойчивая площадка"
        if "штатив" in supp.lower()
        else "- [ ] Проверить баланс стабилизации для съемки с рук"
    )

    steps_md = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, start=1))

    body_lines = [
        f"# {note_title}",
        "",
        f"- **Тема:** {session.topic}",
        f"- **Стилистическая триада:** {styles_str}",
        f"- **Кураторский вектор:** {vector}",
        f"- **Дата фиксации:** {created_str}",
        "",
        "## 📜 Художественный манифест",
        f"> {manifesto}",
        "",
        "## 🖼 Визуальный образ кадра",
        hook,
        "",
        "## 💡 Схема освещения",
        light,
        "",
        "## 📷 Параметры съёмки (Fujifilm X-T4)",
        "- **Камера:** Fujifilm X-T4",
        f"- **Объектив:** {lens}",
        f"- **Фильтр / Насадка:** {filt}",
        f"- **Метод стабилизации:** {supp}",
        f"- **Экспопараметры:** `{cam_setup}`",
        "",
        "## 🎛 Внутрикамерный рецепт (слот C1)",
        f"- **Рецепт:** {recipe.recipe_name}",
        f"- **Имитация плёнки:** {recipe.film_simulation}",
        f"- **Динамический диапазон:** {recipe.dynamic_range}",
        f"- **Тоновая кривая:** Подсветка {r_hl} / Тень {r_sh}",
        f"- **Цвет:** {r_col} | **Резкость:** {r_sharp} | **Шумоподавление:** {r_nr}",
        f"- **Clarity (Прозрачность):** {r_clar}",
        f"- **Эффект зерна:** {recipe.grain_effect}",
        f"- **Цветной хром:** {recipe.color_chrome_effect} | "
        f"**Хром FX Синий:** {recipe.color_chrome_fx_blue}",
        f"- **Баланс белого:** {recipe.white_balance} (R{r_wbr} / B{r_wbb})",
        f"- **Экспокоррекция:** {recipe.exposure_compensation}",
        "",
        "## 👐 Физика съёмки (действие фотографа)",
        action,
        "",
        "## 📋 Пошаговый план на локации",
        steps_md,
        "",
        "## ✅ Чек-лист перед выходом",
        "- [ ] Заряженные аккумуляторы NP-W235 (2 шт.)",
        "- [ ] Чистая скоростная SD-карта UHS-II (проверен слот 1)",
        f"- [ ] Камера Fujifilm X-T4 + объектив: {lens}",
        f"- [ ] Насадка / фильтр: {filt}",
        "- [ ] Микрофибра и салфетки для оптики",
        supp_item,
        "",
        "## 🎨 Эскизный промпт (Midjourney v6.1 / Flux)",
        f"`{mj_prompt}`",
        "",
        "## 💬 Резюме смыслового поиска автора",
        summary,
    ]

    return note_title, "\n".join(body_lines)


def export_copilot_project_to_apple_notes(
    session: CopilotSession,
    folder: str = "Фотопроекты",
) -> str:
    """Выгружает финализированный проект копайлота в Apple Notes со статусом [К съемке]."""
    from services.apple_notes import create_note, ensure_folder

    ensure_folder(folder)
    title, body = format_copilot_project_for_notes(session)
    note_id = create_note(title=title, body=body, folder=folder)
    logger.info(
        "[COPILOT] Проект «%s» экспортирован в Apple Notes (папка: %s, id: %s)",
        title, folder, note_id,
    )
    return note_id
