"""services/style_fusion.py — Движок стилистического синтеза (Триада стилей).

Объединяет три художественных направления (Сюрреализм, Пиктореализм, Экспрессионизм,
Импрессионизм) в функциональные роли:
  1. Сюжет и метафора (narrative)
  2. Свет и драматургия (lighting)
  3. Оптика и фактура (optics)
"""

import html
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from services.json_parser import extract_partial_json_array, safe_parse_llm_json

logger = logging.getLogger("StyleFusion")

AVAILABLE_STYLES = (
    "Сюрреализм",
    "Пиктореализм",
    "Экспрессионизм",
    "Импрессионизм",
)

TRIAD_ROLES = ("narrative", "lighting", "optics")

ROLE_NAMES_RU = {
    "narrative": "Сюжет и метафора",
    "lighting": "Свет и драматургия",
    "optics": "Оптика и фактура",
}

STYLE_ROLE_TRAITS: dict[str, dict[str, str]] = {
    "Сюрреализм": {
        "narrative": (
            "Онейрический сюжет, разрыв бытовой логики, деконтекстуализация предметов, "
            "подсознательные архетипы (Рене Магритт, Поль Дельво)"
        ),
        "lighting": (
            "Парадоксальное «ночное солнце», неестественные тени, мерцающий сумеречный свет, "
            "метафизическое сияние"
        ),
        "optics": (
            "Оптическое расщепление треугольной призмой, зеркальные преломления, "
            "двойная экспозиция с пространственным сдвигом"
        ),
    },
    "Пиктореализм": {
        "narrative": (
            "Поэтизация повседневности, вневременное созерцание, благородная элегия "
            "(Робер Демаши, Эдвард Стайхен, Генрих Кюн)"
        ),
        "lighting": (
            "Бархатные светотеневые переходы, мягкий контровой ореол («гало») вокруг объектов, "
            "сфумато"
        ),
        "optics": (
            "Мягкорисующая оптика (монокль 50mm, Black Pro-Mist 1/4), сглаживание микроконтраста, "
            "благородное крупное плёночное зерно"
        ),
    },
    "Экспрессионизм": {
        "narrative": (
            "Экзистенциальный надлом, внутренняя тревога, психологический гротеск "
            "(немецкий киноэкспрессионизм, «Кабинет доктора Калигари»)"
        ),
        "lighting": (
            "Резкий графичный кьяроскуро, острые диагональные тени-лезвия, жесткий "
            "направленный световой пучок"
        ),
        "optics": (
            "Голландский угол (Dutch angle 15–25°), широкоугольная перспектива, "
            "динамический геометрический дисбаланс"
        ),
    },
    "Импрессионизм": {
        "narrative": (
            "Ускользающий миг, динамика атмосферы, дыхание природной стихии, трепет жизни "
            "(Клод Моне, Эдгар Дега, Огюст Ренуар)"
        ),
        "lighting": (
            "Растворение контуров в ярком свете, вибрация воздуха, цветные рефлексы в тенях, "
            "сияние солнечных бликов"
        ),
        "optics": (
            "Мультиэкспозиция (2–4 кадра) в режиме «Тёмный» (лессировка), естественный "
            "микро-тремор рук (микро-ICM) на 1/6 с, боке-пуантилизм (Гелиос 44-2 f/2)"
        ),
    },
}


@dataclass
class StyleAssignment:
    role: str
    style: str
    traits: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StyleAssignment":
        return cls(
            role=str(data.get("role", "narrative")),
            style=str(data.get("style", "Сюрреализм")),
            traits=str(data.get("traits", "")),
        )


@dataclass
class StyleTriad:
    narrative: StyleAssignment
    lighting: StyleAssignment
    optics: StyleAssignment
    rationale: str = ""

    def styles(self) -> list[str]:
        return [self.narrative.style, self.lighting.style, self.optics.style]

    def summary(self) -> str:
        return (
            f"{self.narrative.style} [сюжет] + "
            f"{self.lighting.style} [свет] + "
            f"{self.optics.style} [оптика]"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "narrative": self.narrative.to_dict(),
            "lighting": self.lighting.to_dict(),
            "optics": self.optics.to_dict(),
            "rationale": self.rationale,
            "summary": self.summary(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StyleTriad":
        return cls(
            narrative=StyleAssignment.from_dict(data.get("narrative", {})),
            lighting=StyleAssignment.from_dict(data.get("lighting", {})),
            optics=StyleAssignment.from_dict(data.get("optics", {})),
            rationale=str(data.get("rationale", "")),
        )


@dataclass
class FusedPhotoConcept:
    title: str
    triad: StyleTriad
    manifesto: str = ""
    scene_description: str = ""
    lighting_setup: str = ""
    camera_setup: dict[str, Any] = field(default_factory=dict)
    shooting_action: str = ""
    gear_recipe: dict[str, Any] = field(default_factory=dict)
    shooting_steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        res = asdict(self)
        res["triad"] = self.triad.to_dict()
        return res

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FusedPhotoConcept":
        triad_data = data.get("triad", {})
        if isinstance(triad_data, dict):
            triad = StyleTriad.from_dict(triad_data)
        else:
            triad = generate_style_triad()

        steps_raw = data.get("shooting_steps", [])
        steps = [str(s).strip() for s in steps_raw if str(s).strip()]

        return cls(
            title=str(data.get("title", "Без названия")).strip(),
            triad=triad,
            manifesto=str(data.get("manifesto", "")).strip(),
            scene_description=str(data.get("scene_description", "")).strip(),
            lighting_setup=str(data.get("lighting_setup", "")).strip(),
            camera_setup=(
                data.get("camera_setup", {})
                if isinstance(data.get("camera_setup"), dict) else {}
            ),
            shooting_action=str(data.get("shooting_action", "")).strip(),
            gear_recipe=(
                data.get("gear_recipe", {})
                if isinstance(data.get("gear_recipe"), dict) else {}
            ),
            shooting_steps=steps,
        )


def generate_style_triad(
    theme: str = "",
    preferred_styles: list[str] | None = None,
) -> StyleTriad:
    """Генерирует гармоничную триаду стилей под заданную тему съёмки."""
    theme_lower = (theme or "").lower()

    # Стили по умолчанию
    narrative_style = "Сюрреализм"
    lighting_style = "Экспрессионизм"
    optics_style = "Пиктореализм"

    if preferred_styles and len(preferred_styles) >= 3:
        # Берём первые 3 уникальных
        unique_pref: list[str] = []
        for s in preferred_styles:
            clean = s.strip()
            if clean in AVAILABLE_STYLES and clean not in unique_pref:
                unique_pref.append(clean)
        if len(unique_pref) >= 3:
            narrative_style = unique_pref[0]
            lighting_style = unique_pref[1]
            optics_style = unique_pref[2]
    else:
        # Эвристический подбор по ключевым словам темы
        if any(w in theme_lower for w in ("парк", "вода", "дождь", "воздух", "осень", "акварель")):
            optics_style = "Импрессионизм"
            lighting_style = "Пиктореализм"
            narrative_style = "Сюрреализм"
        elif any(
            w in theme_lower
            for w in ("ночь", "страх", "тревога", "контраст", "тень", "стена")
        ):
            lighting_style = "Экспрессионизм"
            narrative_style = "Сюрреализм"
            optics_style = "Пиктореализм"
        elif any(w in theme_lower for w in ("портрет", "старина", "память", "туман", "бархат")):
            optics_style = "Пиктореализм"
            narrative_style = "Сюрреализм"
            lighting_style = "Экспрессионизм"
        elif any(w in theme_lower for w in ("свет", "солнце", "утро", "весна", "ветер")):
            lighting_style = "Импрессионизм"
            narrative_style = "Сюрреализм"
            optics_style = "Экспрессионизм"

    # Гарантируем уникальность всех трёх стилей
    selected = [narrative_style]
    if lighting_style in selected:
        for s in AVAILABLE_STYLES:
            if s not in selected:
                lighting_style = s
                break
    selected.append(lighting_style)

    if optics_style in selected:
        for s in AVAILABLE_STYLES:
            if s not in selected:
                optics_style = s
                break

    narrative_assign = StyleAssignment(
        role="narrative",
        style=narrative_style,
        traits=STYLE_ROLE_TRAITS.get(narrative_style, {}).get("narrative", ""),
    )
    lighting_assign = StyleAssignment(
        role="lighting",
        style=lighting_style,
        traits=STYLE_ROLE_TRAITS.get(lighting_style, {}).get("lighting", ""),
    )
    optics_assign = StyleAssignment(
        role="optics",
        style=optics_style,
        traits=STYLE_ROLE_TRAITS.get(optics_style, {}).get("optics", ""),
    )

    rationale = (
        f"Синтез строится на контрасте: онейрический смысл ({narrative_style}) "
        f"проявляется через драматический светотеневой рисунок ({lighting_style}) "
        f"и визуализируется через тонкую фактурную оптику ({optics_style})."
    )

    return StyleTriad(
        narrative=narrative_assign,
        lighting=lighting_assign,
        optics=optics_assign,
        rationale=rationale,
    )


def build_fusion_system_prompt() -> str:
    """Системный промпт для режима генерации концепт-проектов (Fusion Lab)."""
    return (
        "Ты — арт-директор и ведущий фото-технолог творческой лаборатории MemPalace.\n"
        "Твоя задача — сгенерировать ровно 2–3 законченных авторских концепт-проекта для съёмки.\n"
        "Формулируй мысли ёмко, пластично и конкретно, избегая лишней воды, "
        "чтобы ответ полностью уложился в JSON без обрезания токенов.\n"
        "Каждый проект обязан строго следовать ТРИАДЕ СТИЛЕЙ: соединять 3 направления искусства "
        "(Сюрреализм, Пиктореализм, Экспрессионизм, Импрессионизм), распределённых по ролям:\n"
        "1. Сюжет и метафора (narrative)\n"
        "2. Свет и драматургия (lighting)\n"
        "3. Оптика и фактура (optics)\n\n"
        "СТРОГАЯ СХЕМА JSON ОТВЕТА:\n"
        "{\n"
        '  "projects": [\n'
        "    {\n"
        '      "title": "Название арт-проекта",\n'
        '      "triad": {\n'
        '        "narrative": {"role": "narrative", "style": "...", "traits": "..."},\n'
        '        "lighting": {"role": "lighting", "style": "...", "traits": "..."},\n'
        '        "optics": {"role": "optics", "style": "...", "traits": "..."},\n'
        '        "rationale": "Обоснование синергии трёх стилей"\n'
        "      },\n"
        '      "manifesto": "Философия и художественный манифест серии (1-2 абзаца)",\n'
        '      "scene_description": "Локация, сюжет, предметы, акценты (конкретно и образно)",\n'
        '      "lighting_setup": "Схема света: источники, направление, жесткость, тени",\n'
        '      "camera_setup": {\n'
        '        "Приём съёмки": "Мультиэкспозиция / Монокль / Голландский угол / Призма",\n'
        '        "Выдержка": "1/6 с / 1/125 с / ...",\n'
        '        "Диафрагма": "f/2 / f/5.6 / ...",\n'
        '        "Компенсация экспозиции (EV)": "-1.0 / ...",\n'
        '        "Имитация плёнки": "Velvia / Classic Chrome / ACROS+R / ...",\n'
        '        "Тоновая кривая": "Подсветка ... / Тень ...",\n'
        '        "Режим мультиэкспозиции": "Тёмный (если мультиэкспозиция)",\n'
        '        "Количество кадров": "2-4 (если мультиэкспозиция)"\n'
        "      },\n"
        '      "shooting_action": "Физическое действие фотографа (микро-ICM, призма, поворот)",\n'
        '      "gear_recipe": {\n'
        '        "camera": "Fujifilm X-T4",\n'
        '        "lens": "Гелиос 44-2 58mm f/2",\n'
        '        "filter_or_accessory": "Black Pro-Mist 1/4 или Треугольная призма"\n'
        "      },\n"
        '      "shooting_steps": [\n'
        '        "Шаг 1: ...",\n'
        '        "Шаг 2: ...",\n'
        '        "Шаг 3: ...",\n'
        '        "Шаг 4: ..."\n'
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "Верни ТОЛЬКО валидный JSON без markdown-блоков и текста до/после."
    )


def build_fusion_user_prompt(
    topic: str,
    triad: StyleTriad,
    gear_context: str = "",
    mechanics_context: str = "",
    notes_context: str = "",
    serendipity_context: str = "",
) -> str:
    """Собирает пользовательский промпт со всеми блоками контекста."""
    blocks = [f"Тема творческого штурма: {topic}\n"]

    triad_desc = (
        f"[Заданная триада стилистического синтеза]:\n"
        f"• Сюжет: {triad.narrative.style} — {triad.narrative.traits}\n"
        f"• Свет: {triad.lighting.style} — {triad.lighting.traits}\n"
        f"• Оптика: {triad.optics.style} — {triad.optics.traits}\n"
        f"Обоснование: {triad.rationale}\n"
    )
    blocks.append(triad_desc)

    if serendipity_context.strip():
        blocks.append(f"{serendipity_context.strip()}\n")

    if notes_context.strip():
        blocks.append(f"[Импульс из заметок пользователя]:\n{notes_context.strip()}\n")

    if gear_context.strip():
        blocks.append(f"{gear_context.strip()}\n")

    if mechanics_context.strip():
        blocks.append(f"{mechanics_context.strip()}\n")

    blocks.append(
        "Создай детальные авторские фотопроекты, строго реализующие синтез этих 3 стилей "
        "с использованием доступного оборудования и проверенных фотомеханик."
    )
    return "\n".join(blocks)


def validate_fusion_concept(concept: FusedPhotoConcept) -> tuple[bool, str]:
    """Проверяет полноту и валидность концепт-проекта."""
    if not concept.title or len(concept.title.strip()) < 3:
        return False, "Слишком короткое название проекта"

    styles = set(concept.triad.styles())
    if len(styles) < 3:
        return False, f"В триаде должно быть минимум 3 различных стиля (найдено {len(styles)})"

    if not concept.camera_setup or len(concept.camera_setup) < 2:
        return False, "Отсутствуют технические параметры камеры (camera_setup)"

    if len(concept.shooting_steps) < 2:
        return False, "Пошаговый план съёмки должен содержать минимум 2 конкретных шага"

    if not concept.shooting_action:
        return False, "Не указано физическое действие фотографа при съёмке"

    return True, "OK"


def parse_fusion_concepts(raw_response: str) -> list[FusedPhotoConcept]:
    """Парсит и валидирует концепт-проекты из ответа LLM."""
    projects_raw: list[Any] = []
    parsed = safe_parse_llm_json(raw_response, expected_type=dict)
    if isinstance(parsed, dict):
        projects_raw = parsed.get("projects") or parsed.get("ideas") or []
    elif not isinstance(parsed, dict):
        list_parsed = safe_parse_llm_json(raw_response, expected_type=list)
        if isinstance(list_parsed, list):
            projects_raw = list_parsed

    # Fallback: спасение закрытых проектов из частично обрезанного ответа (MAX_TOKENS)
    if not projects_raw:
        projects_raw = extract_partial_json_array(raw_response, array_keys=("projects", "ideas"))

    if not isinstance(projects_raw, list) or not projects_raw:
        logger.warning("[FUSION] Failed to parse JSON response: %s", raw_response[:200])
        return []

    valid_concepts: list[FusedPhotoConcept] = []
    for p in projects_raw:
        if not isinstance(p, dict):
            continue
        try:
            concept = FusedPhotoConcept.from_dict(p)
            ok, reason = validate_fusion_concept(concept)
            if ok:
                valid_concepts.append(concept)
            else:
                logger.info("[FUSION] Отбракован проект «%s»: %s", concept.title, reason)
        except Exception as exc:
            logger.warning("[FUSION] Ошибка преобразования проекта: %s", exc)

    return valid_concepts


def format_fusion_concept_card(concept: FusedPhotoConcept) -> str:
    """Форматирует карточку концепт-проекта для Telegram (HTML-safe)."""
    title_esc = html.escape(concept.title)
    triad_summary = html.escape(concept.triad.summary())
    lines = [
        f"🎨 <b>Проект: «{title_esc}»</b>",
        f"🎭 <b>Триада:</b> <i>{triad_summary}</i>\n",
    ]

    if concept.manifesto:
        lines.append(f"📜 <b>Манифест:</b>\n{html.escape(concept.manifesto)}\n")

    if concept.scene_description:
        lines.append(f"🖼 <b>Образ и локация:</b>\n{html.escape(concept.scene_description)}\n")

    if concept.lighting_setup:
        lines.append(f"💡 <b>Свет:</b> {html.escape(concept.lighting_setup)}")

    if concept.camera_setup:
        lines.append("\n📷 <b>Параметры съёмки:</b>")
        for k, v in concept.camera_setup.items():
            lines.append(f"   • {html.escape(str(k))}: <code>{html.escape(str(v))}</code>")

    if concept.shooting_action:
        lines.append(f"\n👐 <b>Физика съёмки:</b> {html.escape(concept.shooting_action)}")

    if concept.gear_recipe:
        recipe_parts = [
            f"{html.escape(str(k))}: {html.escape(str(v))}"
            for k, v in concept.gear_recipe.items()
        ]
        lines.append(f"🎒 <b>Арсенал:</b> {'; '.join(recipe_parts)}")

    if concept.shooting_steps:
        lines.append("\n📋 <b>План съёмки:</b>")
        for step in concept.shooting_steps:
            lines.append(f"   👉 {html.escape(step)}")

    return "\n".join(lines)


def format_concept_for_apple_notes(concept: FusedPhotoConcept) -> tuple[str, str]:
    """Форматирует фотопроект для выгрузки в Apple Notes в папку «Фотопроекты».

    Возвращает (title, body):
    - title: [В планах] {concept.title}
    - body: Полный markdown-лонгрид со всеми разделами проекта.
    """
    clean_title = concept.title.strip()
    if clean_title.startswith("[В планах]"):
        note_title = clean_title
    else:
        note_title = f"[В планах] {clean_title}"

    body_lines = [
        f"# {note_title}\n",
        "**Статус:** `[В планах]`\n",
        "## 🎭 Триада стилистического синтеза",
        f"- **Сюжет (Narrative):** {concept.triad.narrative.style} — "
        f"{concept.triad.narrative.traits}",
        f"- **Свет и атмосфера (Lighting):** {concept.triad.lighting.style} — "
        f"{concept.triad.lighting.traits}",
        f"- **Оптика и фактура (Optics):** {concept.triad.optics.style} — "
        f"{concept.triad.optics.traits}",
        f"- **Обоснование синергии:** {concept.triad.rationale}\n",
    ]

    if concept.manifesto:
        body_lines.extend([
            "## 📜 Художественный манифест",
            concept.manifesto.strip(),
            "",
        ])

    if concept.scene_description:
        body_lines.extend([
            "## 🖼 Визуальная сцена и композиция",
            concept.scene_description.strip(),
            "",
        ])

    if concept.lighting_setup:
        body_lines.extend([
            "## 💡 Схема освещения",
            concept.lighting_setup.strip(),
            "",
        ])

    if concept.camera_setup:
        body_lines.append("## 📷 Параметры камеры (Fujifilm X-T4)")
        for param, val in concept.camera_setup.items():
            body_lines.append(f"- **{param}:** `{val}`")
        body_lines.append("")

    if concept.shooting_action:
        body_lines.extend([
            "## 👐 Физика съёмки (действие рук)",
            concept.shooting_action.strip(),
            "",
        ])

    if concept.gear_recipe:
        body_lines.append("## 🎒 Рецепт оборудования")
        for k, v in concept.gear_recipe.items():
            body_lines.append(f"- **{k}:** {v}")
        body_lines.append("")

    if concept.shooting_steps:
        body_lines.append("## 📋 Пошаговый план съёмки")
        for i, step in enumerate(concept.shooting_steps, start=1):
            body_lines.append(f"{i}. {step}")
        body_lines.append("")

    lens_info = concept.gear_recipe.get("lens", "Основной объектив")
    filter_info = concept.gear_recipe.get("filter_or_accessory", "Фильтры/насадки")
    body_lines.extend([
        "## ✅ Чек-лист перед выходом",
        "- [ ] Заряженные аккумуляторы NP-W235 (2 шт.)",
        "- [ ] Чистая скоростная SD-карта UHS-II",
        f"- [ ] Камера Fujifilm X-T4 + объектив: {lens_info}",
        f"- [ ] Насадки: {filter_info}",
        "- [ ] Проверить баланс белого и режим мультиэкспозиции",
        "- [ ] Микрофибра и салфетки для оптики",
    ])

    return note_title, "\n".join(body_lines)


def export_concept_to_apple_notes(
    concept: FusedPhotoConcept,
    folder: str = "Фотопроекты",
) -> str:
    """Выгружает фотопроект в Apple Notes в папку `Фотопроекты` со статусом `[В планах]`.

    Создаёт папку через ensure_folder(), если её нет.
    Возвращает ID созданной заметки.
    """
    from services.apple_notes import create_note, ensure_folder

    ensure_folder(folder)
    title, body = format_concept_for_apple_notes(concept)
    note_id = create_note(title=title, body=body, folder=folder)
    logger.info(
        "[FUSION] Концепт «%s» экспортирован в Apple Notes (папка: %s, id: %s)",
        concept.title, folder, note_id,
    )
    return note_id


# ─── Интерактивная фотолаборатория: пагинация и микро-действия (Шаг 5) ───

STYLE_MIDJOURNEY_MODIFIERS: dict[str, str] = {
    "Сюрреализм": (
        "surrealism aesthetic, dreamlike paradoxical atmosphere, "
        "Rene Magritte inspired metaphysical composition, subconscious symbolism"
    ),
    "Пиктореализм": (
        "pictorialism photo, soft-focus pictorial glow, painterly tonalism, "
        "Robert Demachy aesthetic, artistic fine art texture"
    ),
    "Экспрессионизм": (
        "German expressionist cinema aesthetic, dramatic chiaroscuro lighting, "
        "deep sharp angular shadows, psychological tension, The Cabinet of Dr. Caligari mood"
    ),
    "Импрессионизм": (
        "impressionistic photography, luminous color vibration, Claude Monet palette, "
        "watercolor brush wash effect, intentional camera movement ICM blur, layered light"
    ),
}

STYLE_CURATED_REFERENCES: dict[str, list[dict[str, str]]] = {
    "Сюрреализм": [
        {
            "artist": "Man Ray (Ман Рэй)",
            "technique": "Соляризация, рейографии, онейрический портрет",
            "query": "Man Ray solarization rayograph surrealist photography",
        },
        {
            "artist": "René Magritte (Рене Магритт)",
            "technique": "Парадоксальное сопоставление масштабов и предметов",
            "query": "Rene Magritte surrealism paintings composition",
        },
        {
            "artist": "Jerry Uelsmann (Джерри Уэльсманн)",
            "technique": "Многослойная аналоговая мультиэкспозиция в тёмной комнате",
            "query": "Jerry Uelsmann multiple exposure darkroom photography",
        },
    ],
    "Пиктореализм": [
        {
            "artist": "Robert Demachy (Робер Демаши)",
            "technique": "Масляный процесс, гуммибихромат, живописное сфумато",
            "query": "Robert Demachy pictorialism oil print photography",
        },
        {
            "artist": "Edward Steichen (Эдвард Стейхен)",
            "technique": "Живописный тонализм, лунный свет, мягкорисующая оптика",
            "query": "Edward Steichen The Pond Moonlight pictorialism",
        },
        {
            "artist": "Alfred Stieglitz (Альфред Стиглиц)",
            "technique": "Атмосферный свет, туман, дождь, патина времени",
            "query": "Alfred Stieglitz pictorialism early photography",
        },
    ],
    "Экспрессионизм": [
        {
            "artist": "Karl Freund / Robert Wiene",
            "technique": "Немецкий киноэкспрессионизм, острые диагонали, кьяроскуро",
            "query": "The Cabinet of Dr Caligari expressionism cinematography",
        },
        {
            "artist": "Bill Brandt (Билл Брандт)",
            "technique": "Контрастная светотень, широкоугольная деформация ракурса",
            "query": "Bill Brandt perspective distortion chiaroscuro photography",
        },
        {
            "artist": "David Lynch (Дэвид Линч)",
            "technique": "Индустриальная фактура, мистические световые колодцы",
            "query": "David Lynch photography industrial surrealism dark",
        },
    ],
    "Импрессионизм": [
        {
            "artist": "Ernst Haas (Эрнст Хаас)",
            "technique": "Пионер ICM (микро-смаз), цветовая вибрация и лессировка",
            "query": "Ernst Haas motion blur ICM color photography",
        },
        {
            "artist": "Claude Monet (Клод Моне)",
            "technique": "Акварельная прозрачность, серийность света, кувшинки",
            "query": "Claude Monet water lilies impressionism color vibration",
        },
        {
            "artist": "Saul Leiter (Сол Лейтер)",
            "technique": "Капли дождя на стекле, приглушенная цветовая палитра",
            "query": "Saul Leiter through window rain photography",
        },
    ],
}


def format_concept_page(
    concept: FusedPhotoConcept,
    page: int = 1,
    total_pages: int = 4,
) -> str:
    """Форматирует одну из страниц проекта для Telegram (HTML-safe, без <!-- -->).

    Стр. 1: Манифест и философия синтеза стилей.
    Стр. 2: Визуальная раскадровка и световая схема.
    Стр. 3: Сетап Fujifilm X-T4, арсенал и действие рук.
    Стр. 4: Полевой шутинг-лист и чек-лист оборудования.
    """
    title_esc = html.escape(concept.title)
    triad_summary = html.escape(concept.triad.summary())

    if page == 1:
        lines = [
            f"🎨 <b>Проект: «{title_esc}»</b> <i>[Стр. 1/{total_pages}]</i>",
            f"🎭 <b>Триада синтеза:</b> <i>{triad_summary}</i>\n",
            f"• <b>Сюжет:</b> {html.escape(concept.triad.narrative.style)} — "
            f"{html.escape(concept.triad.narrative.traits)}",
            f"• <b>Свет:</b> {html.escape(concept.triad.lighting.style)} — "
            f"{html.escape(concept.triad.lighting.traits)}",
            f"• <b>Оптика:</b> {html.escape(concept.triad.optics.style)} — "
            f"{html.escape(concept.triad.optics.traits)}",
            f"• <b>Синергия стилей:</b> {html.escape(concept.triad.rationale)}\n",
            "📜 <b>Художественный манифест:</b>\n"
            f"{html.escape(concept.manifesto or 'Манифест визуального синтеза.')}",
        ]
        return "\n".join(lines)

    if page == 2:
        lines = [
            f"🎨 <b>Проект: «{title_esc}»</b> <i>[Стр. 2/{total_pages}]</i>\n",
            "🖼 <b>Визуальный образ и композиция:</b>\n"
            f"{html.escape(concept.scene_description or 'Описание композиционной сцены.')}\n",
            "💡 <b>Световая схема:</b>\n"
            f"{html.escape(concept.lighting_setup or 'Естественное и контровое освещение.')}",
        ]
        return "\n".join(lines)

    if page == 3:
        lines = [
            f"🎨 <b>Проект: «{title_esc}»</b> <i>[Стр. 3/{total_pages}]</i>\n",
            "📷 <b>Параметры съёмки (Fujifilm X-T4):</b>",
        ]
        if concept.camera_setup:
            for k, v in concept.camera_setup.items():
                lines.append(f"   • {html.escape(str(k))}: <code>{html.escape(str(v))}</code>")
        else:
            lines.append("   • Базовый профиль Fujifilm X-T4")

        lines.append(
            f"\n👐 <b>Физика съёмки (действие рук):</b>\n"
            f"{html.escape(concept.shooting_action or 'Фиксация камеры в руках.')}"
        )

        if concept.gear_recipe:
            lines.append("\n🎒 <b>Рецепт техники:</b>")
            for k, v in concept.gear_recipe.items():
                lines.append(f"   • {html.escape(str(k))}: {html.escape(str(v))}")
        return "\n".join(lines)

    if page == 4:
        lines = [
            f"🎨 <b>Проект: «{title_esc}»</b> <i>[Стр. 4/{total_pages}]</i>\n",
            "📋 <b>Пошаговый план съёмки:</b>",
        ]
        if concept.shooting_steps:
            for i, step in enumerate(concept.shooting_steps, start=1):
                lines.append(f"   {i}. {html.escape(step)}")
        else:
            lines.append("   1. Подготовить сетап и выполнить кадр.")

        lens_info = concept.gear_recipe.get("lens", "Основной объектив")
        filter_info = concept.gear_recipe.get("filter_or_accessory", "Фильтры/насадки")
        lines.extend([
            "\n✅ <b>Чек-лист перед выходом:</b>",
            "   ▫️ Аккумуляторы NP-W235 (2 шт.)",
            "   ▫️ Скоростная SD-карта UHS-II",
            f"   ▫️ Камера Fujifilm X-T4 + объектив: {html.escape(str(lens_info))}",
            f"   ▫️ Насадки: {html.escape(str(filter_info))}",
            "   ▫️ Проверить баланс белого и режим мультиэкспозиции",
            "   ▫️ Микрофибра и салфетки для оптики",
        ])
        return "\n".join(lines)

    return format_concept_page(concept, page=1, total_pages=total_pages)


def build_concept_navigation_kb(
    concept_idx: int,
    page: int = 1,
    total_pages: int = 4,
):
    """Строит inline-клавиатуру пагинации и микро-действий под проектом."""
    from aiogram import types
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()

    # Ряд 1: Навигация страниц
    nav_row = []
    if page > 1:
        prev_labels = {2: "1/4 Манифест", 3: "2/4 Раскадровка", 4: "3/4 Сетап X-T4"}
        nav_row.append(
            types.InlineKeyboardButton(
                text=f"⬅️ {prev_labels.get(page, f'{page - 1}/4')}",
                callback_data=f"bs_page:{concept_idx}:{page - 1}",
            )
        )
    if page < total_pages:
        next_labels = {1: "Раскадровка 2/4 ➡️", 2: "Сетап X-T4 3/4 ➡️", 3: "Шутинг-лист 4/4 ➡️"}
        nav_row.append(
            types.InlineKeyboardButton(
                text=f"{next_labels.get(page, f'{page + 1}/4 ➡️')}",
                callback_data=f"bs_page:{concept_idx}:{page + 1}",
            )
        )
    elif page == total_pages:
        nav_row.append(
            types.InlineKeyboardButton(
                text="🔄 В начало (1/4)",
                callback_data=f"bs_page:{concept_idx}:1",
            )
        )
    if nav_row:
        kb.row(*nav_row)

    # Ряд 2: Микро-действия (Углубление и Референсы)
    kb.row(
        types.InlineKeyboardButton(
            text="🔍 Углубить образ",
            callback_data=f"bs_deepen:{concept_idx}",
        ),
        types.InlineKeyboardButton(
            text="🌐 Референсы",
            callback_data=f"bs_refs:{concept_idx}",
        ),
    )

    # Ряд 3: Генерация промпта и Экспорт в Apple Notes
    kb.row(
        types.InlineKeyboardButton(
            text="🎨 Промпт Midjourney",
            callback_data=f"bs_prompt:{concept_idx}",
        ),
        types.InlineKeyboardButton(
            text="📝 В Apple Notes [В планах]",
            callback_data=f"bs_export_concept:{concept_idx}",
        ),
    )

    # Ряд 4: Сохранение во Дворец и Назад к списку
    kb.row(
        types.InlineKeyboardButton(
            text="🏛 Во Дворец",
            callback_data=f"bs_save_concept:{concept_idx}",
        ),
        types.InlineKeyboardButton(
            text="◀️ К списку проектов",
            callback_data="bs_back",
        ),
    )
    return kb


def build_midjourney_prompt(concept: FusedPhotoConcept) -> str:
    """Генерирует готовый английский промпт для Midjourney v6 / Flux.1."""
    parts = []

    # Стилистические модификаторы триады
    for style in concept.triad.styles():
        mod = STYLE_MIDJOURNEY_MODIFIERS.get(style)
        if mod:
            parts.append(mod)

    # Описание сцены
    scene = concept.scene_description.strip()
    if scene:
        parts.append(f"scene: {scene}")

    # Световая схема
    lighting = concept.lighting_setup.strip()
    if lighting:
        parts.append(f"lighting: {lighting}")

    # Оптика и насадки
    gear = concept.gear_recipe
    lens = str(gear.get("lens", "")).lower()
    if "гелиос" in lens or "helios" in lens:
        parts.append("shot on vintage Helios 44-2 58mm f/2 lens, circular swirly bokeh")
    elif "монокль" in lens or "monocle" in lens:
        parts.append("shot on soft focus monocle lens, ethereal halation glow")
    else:
        parts.append("shot on Fujifilm Fujinon lens, rich microcontrast")

    filter_name = str(gear.get("filter_or_accessory", "")).lower()
    if "призм" in filter_name or "prism" in filter_name:
        parts.append("refracted through optical triangular crystal glass prism, chromatic split")
    elif "mist" in filter_name or "мист" in filter_name:
        parts.append("Black Pro-Mist diffusion filter, soft glowing blooming highlights")

    # Действие и мультиэкспозиция
    action = concept.shooting_action.lower()
    if "мульти" in action or "icm" in action or "лессировк" in action or "тремор" in action:
        parts.append("multiple exposure layering, intentional camera movement ICM watercolor blur")

    # Технические флаги
    parts.append(
        "Fujifilm X-T4 film simulation Velvia, fine art gallery photography, "
        "8k resolution, editorial aesthetic --ar 16:9 --v 6.1 --style raw"
    )

    return ", ".join(parts)


def build_deepen_system_prompt() -> str:
    """Системный промпт для режиссёрского углубления художественного образа."""
    return (
        "Ты — арт-директор авторской арт-фотографии и режиссёр визуальных искусств.\n"
        "Твоя задача — глубоко проработать художественный образ фотопроекта, "
        "созданного в синтезе трёх стилей.\n"
        "Дай конкретные, образные и реализуемые указания для съёмки:\n"
        "1. 🎭 Скрытый символизм и подтекст (3 конкретные визуальные метафоры).\n"
        "2. 🎬 Режиссура модели и пластика в кадре (напряжение тела, жест, взгляд, дыхание).\n"
        "3. 🎨 Цветовая драматургия (колористика светов, полутонов и теней).\n"
        "4. 📐 Композиционный нерв (диагонали, глубина планов, точки скрытого напряжения).\n"
        "Пиши лаконично, образно, профессионально. Без пустых общих фраз."
    )


def build_deepen_user_prompt(concept: FusedPhotoConcept) -> str:
    """Пользовательский запрос на углубление образа проекта."""
    return (
        f"Проект: «{concept.title}»\n"
        f"Триада стилей: {concept.triad.summary()}\n"
        f"Манифест: {concept.manifesto}\n"
        f"Визуальная сцена: {concept.scene_description}\n"
        f"Свет: {concept.lighting_setup}\n"
        f"Оборудование: {concept.gear_recipe}\n\n"
        "Дай исчерпывающий режиссёрский анализ и углубление образа для этой съёмки."
    )


def format_deepen_card(concept: FusedPhotoConcept, analysis_text: str) -> str:
    """Форматирует карточку режиссёрского углубления образа (HTML-safe)."""
    title_esc = html.escape(concept.title)
    return (
        f"🔍 <b>Режиссёрское углубление: «{title_esc}»</b>\n\n"
        f"{html.escape(analysis_text.strip())}"
    )


def get_curated_references(concept: FusedPhotoConcept) -> list[dict[str, str]]:
    """Возвращает канонические референсы мастеров по стилям триады."""
    refs: list[dict[str, str]] = []
    seen = set()
    for style in concept.triad.styles():
        for r in STYLE_CURATED_REFERENCES.get(style, []):
            if r["artist"] not in seen:
                seen.add(r["artist"])
                refs.append({"style": style, **r})
    return refs


def format_references_card(concept: FusedPhotoConcept, web_snippets: str = "") -> str:
    """Форматирует карточку художественных референсов для Telegram (HTML-safe)."""
    title_esc = html.escape(concept.title)
    triad_esc = html.escape(concept.triad.summary())
    lines = [
        f"🌐 <b>Художественные референсы: «{title_esc}»</b>",
        f"🎭 <i>Триада: {triad_esc}</i>\n",
        "🏛 <b>Мастера для визуального изучения:</b>",
    ]

    refs = get_curated_references(concept)
    for r in refs[:5]:
        s_esc = html.escape(r["style"])
        art_esc = html.escape(r["artist"])
        tech_esc = html.escape(r["technique"])
        q_esc = html.escape(r["query"])
        lines.append(
            f"• <b>[{s_esc}] {art_esc}</b>\n  <i>{tech_esc}</i>\n  🔍 <code>{q_esc}</code>"
        )

    if web_snippets.strip():
        lines.append(f"\n🔎 <b>Находки из сети:</b>\n{html.escape(web_snippets.strip()[:600])}")

    lines.append(
        "\n💡 <i>Совет: скопируйте поисковый запрос (в теге кода) в Pinterest или Google Images "
        "для изучения световых схем и композиций.</i>"
    )
    return "\n".join(lines)
