"""services/copilot_series.py — Драматургический генератор кураторской фотосерии.

Разворачивает утверждённый фотопроект в целостную нарративную фотосерию
(триптих из 3 кадров или пентаптих из 5 кадров):
- Трехактная композиция (Вход/Локация → Завязка/Деталь → Кульминация → Эхо → Кода);
- Ритмическое чередование крупностей планов (общий, средний, крупный, макро, абстракция);
- Единство колористики (один внутрикамерный рецепт Fujifilm X-T4 на всю серию);
- Профессиональная кураторская экспликация (Curatorial Statement) для выставки / каталога;
- Согласованные нейросетевые промпты Midjourney v6.1 / Flux для каждого кадра;
- Форматирование для Telegram и пакетный экспорт в Apple Notes со статусом [Серия к съемке].
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import logging
import re
import time
from typing import Any, Literal

from services.copilot_engine import STYLE_MIDJOURNEY_KEYWORDS
from services.copilot_session import CopilotSession
from services.text_formatter import safe_html_format

logger = logging.getLogger("CopilotSeries")

SeriesFormat = Literal["triptych", "penta"]

# Каноническая драматургическая структура актов
ACT_ROLES_TRIPTYCH = [
    ("Акт I: Вход / Локация", "Общий план"),
    ("Акт II: Кульминация / Конфликт", "Кульминационный средний план"),
    ("Акт III: Эхо / Развязка", "Крупный план / Деталь"),
]

ACT_ROLES_PENTA = [
    ("Акт I: Вход / Пространство", "Общий план"),
    ("Акт II: Завязка / Деталь", "Крупный план / Макро"),
    ("Акт III: Кульминация / Конфликт", "Кульминационный средний план"),
    ("Акт IV: Эхо / След", "Средний план"),
    ("Акт V: Кода / Развязка", "Оптическая абстракция"),
]


@dataclass
class SeriesShot:
    """Один кадр кураторской фотосерии."""

    frame_index: int
    act_role: str
    shot_type: str
    title: str
    visual_description: str
    lighting_setup: str
    optics_action: str
    fuji_recipe_note: str
    midjourney_prompt: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SeriesShot:
        valid_fields = cls.__dataclass_fields__.keys()
        clean = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**clean)


@dataclass
class PhotoSeries:
    """Кураторская фотосерия (триптих или пентаптих)."""

    project_title: str
    series_format: SeriesFormat
    manifesto_core: str
    curatorial_statement: str
    shots: list[SeriesShot] = field(default_factory=list)
    fuji_recipe_summary: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["shots"] = [s.to_dict() for s in self.shots]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PhotoSeries:
        shots_raw = data.get("shots") or []
        shots = [SeriesShot.from_dict(s) if isinstance(s, dict) else s for s in shots_raw]
        clean = {
            "project_title": data.get("project_title", "Безымянная серия"),
            "series_format": data.get("series_format", "triptych"),
            "manifesto_core": data.get("manifesto_core", ""),
            "curatorial_statement": data.get("curatorial_statement", ""),
            "shots": shots,
            "fuji_recipe_summary": data.get("fuji_recipe_summary", ""),
            "created_at": data.get("created_at", time.time()),
        }
        return cls(**clean)


COPILOT_SERIES_SYSTEM = (
    "Ты — ведущий музейный куратор художественной фотографии и мастер раскадровки.\n"
    "Твоя задача — развернуть концепт арт-фотопроекта в выставочную фотосерию с драматургией.\n\n"
    "ПРАВИЛА ПОСТРОЕНИЯ СЕРИИ:\n"
    "1. ЕДИНСТВО СТИЛЯ И ЦВЕТА: Вся серия снимается на один рецепт камеры (Fujifilm X-T4).\n"
    "2. ДРАМАТУРГИЧЕСКИЙ РИТМ ПЛАНОВ:\n"
    "   - Никогда не ставь два одинаковых плана подряд.\n"
    "   - Чередуй: общий -> деталь -> кульминация -> средний -> абстракция.\n"
    "   - Триптих (3 кадра): Акт I (Вход/Общий) -> Акт II (Кульминация) -> Акт III (Эхо/Крупный).\n"
    "   - Пентаптих (5 кадров): Акт I (Вход) -> Акт II (Макро) -> Акт III (Кульминация) -> "
    "Акт IV (Эхо/Средний) -> Акт V (Кода/Абстракция).\n"
    "3. КУРАТОРСКАЯ ЭКСПЛИКАЦИЯ (Curatorial Statement):\n"
    "   - Глубокий искусствоведческий текст (120–180 слов) для стены галереи или каталога.\n"
    "   - Объясни визуальный язык серии, философский подтекст и оптику Гелиоса 44-2.\n"
    "4. КАЖДЫЙ КАДР ДОЛЖЕН ИМЕТЬ:\n"
    "   - act_role, shot_type, title, visual_description, lighting_setup, optics_action, "
    "fuji_recipe_note, midjourney_prompt.\n\n"
    "ФОРМАТ ВЫВОДА: Строго валидный JSON без markdown:\n"
    "{\n"
    '  "curatorial_statement": "Текст музейной экспликации...",\n'
    '  "fuji_recipe_summary": "Classic Chrome / Acros, DR400, H: -1.0, S: +2.0",\n'
    '  "shots": [\n'
    "    {\n"
    '      "frame_index": 1,\n'
    '      "act_role": "...",\n'
    '      "shot_type": "...",\n'
    '      "title": "...",\n'
    '      "visual_description": "...",\n'
    '      "lighting_setup": "...",\n'
    '      "optics_action": "...",\n'
    '      "fuji_recipe_note": "...",\n'
    '      "midjourney_prompt": "..."\n'
    "    }\n"
    "  ]\n"
    "}"
)


def _extract_project_meta(session_or_project: CopilotSession | dict[str, Any]) -> dict[str, Any]:
    """Извлекает метаданные проекта из сессии или словаря."""
    if isinstance(session_or_project, CopilotSession):
        session = session_or_project
        project = session.get_active_project()
        title = project.get("title") or session.topic or "Авторский фотопроект"
        manifesto = session.manifesto or project.get("manifesto", "")
        styles = session.selected_styles or ["Экспрессионизм", "Сюрреализм"]
        visual_hook = project.get("visual_hook") or session.topic
        lighting = project.get("lighting_scene") or session.tech_preferences.get("lighting", "")
        support = session.tech_preferences.get("support", "Съемка с рук (микро-ICM)")
        lens = session.tech_preferences.get("lens", "Гелиос 44-2 58mm f/2")
        filter_acc = session.tech_preferences.get("filter_accessory", "Black Pro-Mist 1/4")
    else:
        project = session_or_project
        title = project.get("title") or project.get("topic") or "Авторский фотопроект"
        manifesto = project.get("manifesto") or project.get("summary", "")
        styles = project.get("styles") or project.get("selected_styles") or ["Экспрессионизм"]
        visual_hook = project.get("visual_hook") or project.get("hook") or title
        lighting = project.get("lighting_scene") or project.get("lighting", "Контровой свет")
        support = project.get("support", "Съемка с рук")
        lens = project.get("lens", "Гелиос 44-2 58mm f/2")
        filter_acc = project.get("filter_accessory", "Black Pro-Mist 1/4")

    return {
        "title": title,
        "manifesto": manifesto,
        "styles": styles,
        "visual_hook": visual_hook,
        "lighting": lighting,
        "support": support,
        "lens": lens,
        "filter_acc": filter_acc,
    }


def _build_fallback_series(
    meta: dict[str, Any],
    series_format: SeriesFormat,
) -> PhotoSeries:
    """Надежный генератор кураторской серии на основе шаблонов высокой драматургии."""
    title = meta["title"]
    manifesto = (
        meta["manifesto"] or "Исследование внутреннего конфликта через оптические искажения."
    )
    styles = meta["styles"]
    styles_str = ", ".join(styles) if styles else "Экспрессионизм и Сюрреализм"
    lens = meta["lens"]
    filter_acc = meta["filter_acc"]

    curatorial_statement = (
        f"Серия «{title}» представляет собой фотографическое исследование на стыке {styles_str}. "
        f"Выстраивая визуальный нарратив от отчуждённого пространства к драматическому конфликту "
        f"и завершающему растворению, автор превращает оптические аберрации объектива {lens} "
        f"и диффузию {filter_acc} в метафору психологического напряжения. Единый внутрикамерный "
        f"строй эмульсии связывает дискретные кадры в целостное выставочное полотно, "
        f"где свет выступает не просто освещением, а главным драматургическим героем."
    )

    recipe_summary = (
        "Fujifilm X-T4: Classic Chrome / Acros+R, DR400, H: -1.0, S: +2.5, WB Shift R:+3 B:-4"
    )

    act_configs = ACT_ROLES_TRIPTYCH if series_format == "triptych" else ACT_ROLES_PENTA
    shots: list[SeriesShot] = []

    style_tokens = [
        STYLE_MIDJOURNEY_KEYWORDS[s] for s in styles if s in STYLE_MIDJOURNEY_KEYWORDS
    ]
    style_kw = " ".join(style_tokens) if style_tokens else (
        "dramatic chiaroscuro, cinematic fine art aesthetic"
    )

    for idx, (act_role, shot_type) in enumerate(act_configs, start=1):
        if idx == 1:
            shot_title = f"{title}: Пространство отчуждения"
            desc = (
                "Пустынное городское или природное пространство. Одинокая геометрия стен, "
                "растворяющаяся в сумерках. Субъект едва различим на заднем плане или отсутствует."
            )
            light = "Холодный рассеянный предвечерний свет с пятнами контровых натриевых ламп."
            optics = f"{lens} на диафрагме f/4.0; фильтр {filter_acc} для мягких светов."
            prompt = (
                f"wide establishing shot, vast moody cinematic urban geometry, empty space, "
                f"{style_kw}, authentic 35mm film grain, soft atmospheric halation "
                f"--ar 16:9 --style raw --v 6.1"
            )
        elif idx == 2 and series_format == "penta":
            shot_title = f"{title}: Тактильный знак"
            desc = (
                "Крупный план предмета-символа или рук персонажа (край пальто, осколок). "
                "Тактильная фактура материи, передающая внутреннее беспокойство."
            )
            light = "Одиночный косой луч света, выхватывающий рельеф кожи и фактуру предмета."
            optics = f"{lens} на открытой диафрагме f/2.0 с крученым боке на заднем плане."
            prompt = (
                f"extreme close-up detail shot of hands holding symbolic artifact, "
                f"tactile texture, swirly vintage bokeh, {style_kw}, dramatic rim lighting, "
                f"fine art photography --ar 16:9 --style raw --v 6.1"
            )
        elif (idx == 2 and series_format == "triptych") or (idx == 3 and series_format == "penta"):
            shot_title = f"{title}: Кульминация Тени"
            desc = (
                "Центральный кадр проекта: субъект в момент столкновения с теневым двойником "
                "или оптическим расколом реальности. Динамический жест, экспрессивный поворот."
            )
            light = "Жесткий контровой натриевый свет, лезвия теней-кьяроскуро, резкий контраст."
            optics = f"{lens} f/2.0, микро-тремор рук (ICM) и преломление призмы на краю кадра."
            prompt = (
                f"dramatic cinematic hero shot, split persona and shadow conflict, crystal prism, "
                f"swirly bokeh, hard chiaroscuro rim lighting, {style_kw}, fine art masterpiece "
                f"--ar 16:9 --style raw --v 6.1"
            )
        elif idx == 4 and series_format == "penta":
            shot_title = f"{title}: Эхо присутствия"
            desc = (
                "Фигура персонажа отдаляется и тает. Световой контур на сырой стене "
                "или отражение в луже. Ощущение внутренней трансформации."
            )
            light = "Глубокие провалы теней с единственной узкой полосой скользящего света."
            optics = f"{lens} f/2.8, съемка через фильтр {filter_acc} с легким смазом."
            prompt = (
                f"medium cinematic shot, fading shadowy silhouette, damp wall reflection, "
                f"{style_kw}, motion blur trail, atmospheric lighting --ar 16:9 --style raw --v 6.1"
            )
        else:
            shot_title = f"{title}: Кода и след"
            desc = (
                "Финальный кадр-развязка: пустой проулок или световой блик на мокром асфальте. "
                "Остаточный след присутствия, уходящий в темноту и абстрактную текстуру."
            )
            light = "Минималистичный свет: угасающий ореол одинокого фонаря, растворяющийся в ночи."
            optics = f"{lens} на f/2.0 в расфокусе, превращающий городские огни в диски боке."
            prompt = (
                f"abstract poetic fine art photo, dissolving light, blurred circular bokeh orbs, "
                f"deep velvety shadows, {style_kw}, quiet reflective conclusion "
                f"--ar 16:9 --style raw --v 6.1"
            )

        shot = SeriesShot(
            frame_index=idx,
            act_role=act_role,
            shot_type=shot_type,
            title=shot_title,
            visual_description=desc,
            lighting_setup=light,
            optics_action=optics,
            fuji_recipe_note="Единый рецепт серии: Classic Chrome / Acros, DR400, Tone H-1/S+2.5",
            midjourney_prompt=prompt,
        )
        shots.append(shot)

    return PhotoSeries(
        project_title=title,
        series_format=series_format,
        manifesto_core=manifesto,
        curatorial_statement=curatorial_statement,
        shots=shots,
        fuji_recipe_summary=recipe_summary,
    )


async def build_series_storyboard_async(
    session_or_project: CopilotSession | dict[str, Any],
    series_format: SeriesFormat = "triptych",
    ai_engine: Any = None,
) -> PhotoSeries:
    """Генерирует согласованную фотосерию через AI или fallback."""
    meta = _extract_project_meta(session_or_project)

    try:
        from services.ai_engine import get_ai_response_async, get_current_ai

        num_shots = 3 if series_format == "triptych" else 5
        user_prompt = (
            f"Тема: «{meta['title']}»\n"
            f"Стилистическая триада: {', '.join(meta['styles'])}\n"
            f"Манифест: {meta['manifesto']}\n"
            f"Визуальный хук: {meta['visual_hook']}\n"
            f"Оптика и арсенал: {meta['lens']}, {meta['filter_acc']}, {meta['support']}\n"
            f"Свет: {meta['lighting']}\n"
            f"Формат: {series_format} (ровно {num_shots} кадров)\n\n"
            f"Создай кураторскую экспликацию и раскадровку ровно из {num_shots} кадров."
        )

        messages = [
            {"role": "system", "content": COPILOT_SERIES_SYSTEM},
            {"role": "user", "content": user_prompt},
        ]

        engine_name, model = get_current_ai()
        sampling = {"temperature": 0.7, "max_tokens": 1200}
        raw = await get_ai_response_async(engine_name, model, messages, sampling=sampling)
        if raw and raw.strip():
            json_text = raw.strip()
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", json_text, re.DOTALL)
            if match:
                json_text = match.group(1)

            data = json.loads(json_text)
            raw_shots = data.get("shots") or []
            if len(raw_shots) >= num_shots:
                curatorial_stmt = data.get("curatorial_statement") or meta["manifesto"]
                recipe_sum = data.get("fuji_recipe_summary") or "Classic Chrome, DR400"
                act_defs = ACT_ROLES_TRIPTYCH if series_format == "triptych" else ACT_ROLES_PENTA

                shots: list[SeriesShot] = []
                for i, s_dict in enumerate(raw_shots[:num_shots], start=1):
                    act_default, shot_default = act_defs[i - 1]
                    shot = SeriesShot(
                        frame_index=i,
                        act_role=s_dict.get("act_role") or act_default,
                        shot_type=s_dict.get("shot_type") or shot_default,
                        title=s_dict.get("title") or f"Кадр {i}",
                        visual_description=s_dict.get("visual_description") or "",
                        lighting_setup=s_dict.get("lighting_setup") or meta["lighting"],
                        optics_action=(
                            s_dict.get("optics_action") or f"{meta['lens']}, {meta['filter_acc']}"
                        ),
                        fuji_recipe_note=s_dict.get("fuji_recipe_note") or recipe_sum,
                        midjourney_prompt=s_dict.get("midjourney_prompt") or "",
                    )
                    shots.append(shot)

                return PhotoSeries(
                    project_title=meta["title"],
                    series_format=series_format,
                    manifesto_core=meta["manifesto"],
                    curatorial_statement=curatorial_stmt,
                    shots=shots,
                    fuji_recipe_summary=recipe_sum,
                )
    except Exception as err:
        logger.warning("[SERIES] LLM генерация завершилась сбоем: %s, применяем fallback", err)

    return _build_fallback_series(meta, series_format)


def build_series_storyboard(
    session_or_project: CopilotSession | dict[str, Any],
    series_format: SeriesFormat = "triptych",
) -> PhotoSeries:
    """Синхронная обертка генератора кураторской серии (для тестов и синхронных хендлеров)."""
    meta = _extract_project_meta(session_or_project)
    return _build_fallback_series(meta, series_format)


def format_series_overview_card(series: PhotoSeries) -> str:
    """Форматирует сводную карточку всей фотосерии для Telegram."""
    total = len(series.shots)
    is_triptych = series.series_format == "triptych"
    fmt_title = "Триптих (3 кадра)" if is_triptych else "Пентаптих (5 кадров)"

    lines = [
        f"🎞 <b>Кураторская фотосерия: «{safe_html_format(series.project_title)}»</b>",
        f"🏛 <b>Формат экспозиции:</b> <code>{fmt_title}</code>",
        "",
        "📜 <b>Кураторская экспликация (Curatorial Statement):</b>",
        f"<blockquote>{safe_html_format(series.curatorial_statement)}</blockquote>",
        "",
        f"🎞 <b>Драматургическая раскадровка ({total} кадров):</b>",
    ]

    for shot in series.shots:
        lines.append(
            f"👉 <b>Кадр {shot.frame_index}</b> [<i>{safe_html_format(shot.shot_type)}</i>]: "
            f"«{safe_html_format(shot.title)}»\n"
            f"   🎭 <i>{safe_html_format(shot.act_role)}</i>\n"
            f"   💡 {safe_html_format(shot.lighting_setup)}"
        )

    if series.fuji_recipe_summary:
        lines.append("")
        lines.append(
            f"📷 <b>Единый строй камеры:</b> "
            f"<code>{safe_html_format(series.fuji_recipe_summary)}</code>"
        )

    lines.append("")
    lines.append("<i>Используйте кнопки ниже для детального просмотра кадров и промптов.</i>")

    return "\n".join(lines)


def format_series_shot_card(series: PhotoSeries, shot_idx: int) -> str:
    """Форматирует детальную карточку одного кадра серии для Telegram."""
    if not series.shots or shot_idx < 0 or shot_idx >= len(series.shots):
        return "<i>Кадр серии не найден.</i>"

    shot = series.shots[shot_idx]
    total = len(series.shots)

    lines = [
        f"🎞 <b>Кадр {shot.frame_index} из {total}: «{safe_html_format(shot.title)}»</b>",
        f"🏛 Проект: <i>«{safe_html_format(series.project_title)}»</i>",
        "",
        f"🎭 <b>Роль в драматургии:</b> <code>{safe_html_format(shot.act_role)}</code>",
        f"📐 <b>Крупность плана:</b> <b>{safe_html_format(shot.shot_type)}</b>",
        "",
        f"🖼 <b>Образ и композиция:</b>\n{safe_html_format(shot.visual_description)}",
        "",
        f"💡 <b>Свет и светотень:</b>\n{safe_html_format(shot.lighting_setup)}",
        "",
        f"🔍 <b>Оптика и физика съемки:</b>\n{safe_html_format(shot.optics_action)}",
        "",
        f"📷 <b>Настройка X-T4:</b> <code>{safe_html_format(shot.fuji_recipe_note)}</code>",
        "",
        "🎨 <b>Промпт для Midjourney v6.1 / Flux (тапните для копирования):</b>",
        f"<code>{safe_html_format(shot.midjourney_prompt)}</code>",
    ]

    return "\n".join(lines)


def format_series_for_notes(series: PhotoSeries) -> tuple[str, str]:
    """Формирует структурированный Markdown для Apple Notes."""
    title = f"[Серия к съемке] {series.project_title}"
    is_triptych = series.series_format == "triptych"
    fmt_title = "Триптих (3 кадра)" if is_triptych else "Пентаптих (5 кадров)"

    body_lines = [
        f"# Кураторская фотосерия: «{series.project_title}»",
        f"**Формат экспозиции:** {fmt_title}",
        f"**Дата создания:** {time.strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 📜 Кураторская экспликация (Curatorial Statement)",
        series.curatorial_statement,
        "",
        "## 🎨 Манифест серии",
        series.manifesto_core,
        "",
        "## 📷 Единый внутрикамерный рецепт (Fujifilm X-T4)",
        series.fuji_recipe_summary,
        "",
        "## 🎞 Раскадровка серии по актам",
    ]

    for shot in series.shots:
        body_lines.extend([
            f"### Кадр {shot.frame_index}: {shot.title}",
            f"- **Драматургическая роль:** {shot.act_role}",
            f"- **Крупность плана:** {shot.shot_type}",
            f"- **Визуальный образ:** {shot.visual_description}",
            f"- **Световая схема:** {shot.lighting_setup}",
            f"- **Оптика и физическое действие:** {shot.optics_action}",
            f"- **Настройки камеры:** {shot.fuji_recipe_note}",
            "- **Промпт для Midjourney / Flux:**",
            f"```text\n{shot.midjourney_prompt}\n```",
            "",
        ])

    return title, "\n".join(body_lines)


def export_series_to_apple_notes(
    series: PhotoSeries,
    folder: str = "Фотопроекты",
) -> tuple[bool, str]:
    """Экспортирует фотосерию в Apple Notes со статусом [Серия к съемке]."""
    try:
        from services.apple_notes import create_note, ensure_folder

        ensure_folder(folder)
        title, body = format_series_for_notes(series)
        note_id = create_note(title=title, body=body, folder=folder)
        logger.info(
            "[SERIES] Серия «%s» успешно экспортирована в Apple Notes (папка: %s, id: %s)",
            title, folder, note_id,
        )
        return True, note_id
    except Exception as err:
        logger.warning("[SERIES] Ошибка экспорта серии в Apple Notes: %s", err)
        return False, str(err)
