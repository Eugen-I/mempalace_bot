"""services/style_fusion.py — Движок стилистического синтеза (Триада стилей).

Объединяет три художественных направления (Сюрреализм, Пиктореализм, Экспрессионизм,
Импрессионизм) в функциональные роли:
  1. Сюжет и метафора (narrative)
  2. Свет и драматургия (lighting)
  3. Оптика и фактура (optics)
"""

import html
import logging
import re
import urllib.parse
from dataclasses import asdict, dataclass, field
from typing import Any

from services.json_parser import (
    extract_partial_json_array,
    safe_parse_llm_json,
    salvage_truncated_json_object,
)

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
            "Светосильное вихревое боке (перевёрнутая линза или Kamlan f/1.1), ND-фильтр "
            "с пластичным смазом ветра, оптическая линза с отверстием или "
            "мультиэкспозиция в режиме «Тёмный» (лессировка)"
        ),
    },
}


def _normalize_style_name(raw_style: Any, default_style: str = "Сюрреализм") -> str:
    """Нормализует название стиля от LLM к каноническому из AVAILABLE_STYLES."""
    if not raw_style:
        return default_style
    s = str(raw_style).strip()
    if not s:
        return default_style
    s_low = s.lower()
    if "сюрреал" in s_low or "surreal" in s_low:
        return "Сюрреализм"
    if "пиктор" in s_low or "pictor" in s_low:
        return "Пиктореализм"
    if "экспресс" in s_low or "express" in s_low:
        return "Экспрессионизм"
    if "импресс" in s_low or "impress" in s_low:
        return "Импрессионизм"
    return s


@dataclass
class StyleAssignment:
    role: str
    style: str
    traits: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(
        cls,
        data: Any,
        default_role: str = "narrative",
        default_style: str = "Сюрреализм",
    ) -> "StyleAssignment":
        if isinstance(data, str):
            parts = re.split(r"\s*[—–:\-]\s*", data.strip(), maxsplit=1)
            style = _normalize_style_name(parts[0], default_style=default_style)
            traits = (
                parts[1].strip()
                if len(parts) > 1 and parts[1].strip()
                else STYLE_ROLE_TRAITS.get(style, {}).get(default_role, "")
            )
            return cls(role=default_role, style=style, traits=traits)

        if not isinstance(data, dict):
            return cls(
                role=default_role,
                style=default_style,
                traits=STYLE_ROLE_TRAITS.get(default_style, {}).get(default_role, ""),
            )

        role = str(data.get("role") or default_role)
        raw_style = data.get("style") or data.get("name") or default_style
        style = _normalize_style_name(raw_style, default_style=default_style)
        traits = str(data.get("traits") or data.get("description") or "")
        return cls(
            role=role,
            style=style,
            traits=traits,
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
        nar_raw = data.get("narrative") or data.get("plot") or data.get("story") or {}
        lig_raw = data.get("lighting") or data.get("light") or {}
        opt_raw = data.get("optics") or data.get("optic") or data.get("texture") or {}
        return cls(
            narrative=StyleAssignment.from_dict(
                nar_raw, default_role="narrative", default_style="Сюрреализм"
            ),
            lighting=StyleAssignment.from_dict(
                lig_raw, default_role="lighting", default_style="Экспрессионизм"
            ),
            optics=StyleAssignment.from_dict(
                opt_raw, default_role="optics", default_style="Пиктореализм"
            ),
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
    deepened_analysis: str = ""
    midjourney_prompt: str = ""
    fuji_recipe: str = ""

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

        steps_raw = data.get("shooting_steps")
        if steps_raw is None:
            steps_raw = data.get("steps", [])
        if isinstance(steps_raw, str):
            steps = [
                s.strip()
                for s in re.split(r"[\r\n;]+", steps_raw)
                if s.strip()
            ]
        elif isinstance(steps_raw, list):
            steps = [str(s).strip() for s in steps_raw if str(s).strip()]
        else:
            steps = []

        cam_raw = data.get("camera_setup")
        if cam_raw is None:
            cam_raw = data.get("settings", {})
        if isinstance(cam_raw, dict):
            camera_setup = dict(cam_raw)
        elif isinstance(cam_raw, str) and cam_raw.strip():
            camera_setup = {}
            for idx, part in enumerate(re.split(r"[;\r\n]+", cam_raw), start=1):
                if ":" in part:
                    k, v = part.split(":", 1)
                    if k.strip() and v.strip():
                        camera_setup[k.strip()] = v.strip()
                elif part.strip():
                    camera_setup[f"Параметр {idx}"] = part.strip()
        elif isinstance(cam_raw, list):
            camera_setup = {}
            for idx, item in enumerate(cam_raw, start=1):
                s_item = str(item).strip()
                if ":" in s_item:
                    k, v = s_item.split(":", 1)
                    camera_setup[k.strip()] = v.strip()
                elif s_item:
                    camera_setup[f"Параметр {idx}"] = s_item
        else:
            camera_setup = {}

        gear_raw = data.get("gear_recipe")
        if isinstance(gear_raw, dict):
            gear_recipe = dict(gear_raw)
        elif isinstance(gear_raw, str) and gear_raw.strip():
            gear_recipe = {"camera": "Fujifilm X-T4", "lens": gear_raw.strip()}
        else:
            gear_recipe = {}

        shooting_action = str(
            data.get("shooting_action")
            or data.get("physical_action")
            or data.get("action")
            or ""
        ).strip()

        return cls(
            title=str(data.get("title") or data.get("name") or "Без названия").strip(),
            triad=triad,
            manifesto=str(data.get("manifesto", "")).strip(),
            scene_description=str(data.get("scene_description", "")).strip(),
            lighting_setup=str(data.get("lighting_setup", "")).strip(),
            camera_setup=camera_setup,
            shooting_action=shooting_action,
            gear_recipe=gear_recipe,
            shooting_steps=steps,
            deepened_analysis=str(data.get("deepened_analysis", "")).strip(),
            midjourney_prompt=str(data.get("midjourney_prompt", "")).strip(),
            fuji_recipe=str(data.get("fuji_recipe", "")).strip(),
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
        "ПРАВИЛО РАЗНООБРАЗИЯ МЕХАНИК И ОПТИКИ (КРИТИЧЕСКИ ВАЖНО):\n"
        "Каждый проект ОБЯЗАН использовать РАЗНЫЕ приёмы съёмки и оптику из арсенала!\n"
        "СТРОГО ЗАПРЕЩЕНО делать мультиэкспозицию первым или одинаковым приёмом во всех проектах.\n"
        "Используй богатый арсенал техник:\n"
        "• Линза с отверстием в центре (резкий фокус в отверстии + оптическая воронка по краям)\n"
        "• Pentacon 29mm с перевёрнутой передней линзой (экстремальное вихревое боке)\n"
        "• Монокль 35mm (сфумато, светящийся ореол, мягкий фокус)\n"
        "• Kamlan 50mm f/1.1 (сверхмалая ГРИП, кремовое размытие, масляный рисунок)\n"
        "• K&F ND-фильтр 2-400 на штативе (длинная выдержка 1/2–5 с, пластичный смаз ветра/воды)\n"
        "• Набор прозрачных тканей (воздушный вейл перед объективом, текстурная дымка)\n"
        "• Вспышка Godox V1F (синхронизация по второй шторке / заморозка капель)\n"
        "• Мультиэкспозиция или микро-ICM (только как альтернатива, не дефолт для всех!)\n\n"
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
        '        "Приём съёмки": "Линза с отверстием / Перевёрнутая линза / ND-фильтр / f/1.1",\n'
        '        "Выдержка": "1/2 с / 1/125 с / 1/4000 с / ...",\n'
        '        "Диафрагма": "f/1.1 / f/2.8 / f/8 / ...",\n'
        '        "Компенсация экспозиции (EV)": "-1.0 / ...",\n'
        '        "Имитация плёнки": "Classic Chrome / Velvia / ACROS+R / ...",\n'
        '        "Тоновая кривая": "Подсветка ... / Тень ..."\n'
        "      },\n"
        '      "shooting_action": "Действие фотографа (удержание ткани, поворот линзы, штатив)",\n'
        '      "gear_recipe": {\n'
        '        "camera": "Fujifilm X-T4",\n'
        '        "lens": "Название объектива из арсенала",\n'
        '        "filter_or_accessory": "Насадка или аксессуар из арсенала"\n'
        "      },\n"
        '      "shooting_steps": [\n'
        '        "Шаг 1: ...",\n'
        '        "Шаг 2: ...",\n'
        '        "Шаг 3: ...",\n'
        '        "Шаг 4: ..."\n'
        "      ],\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "ВАЖНО ДЛЯ JSON: НЕ используй неэкранированные двойные кавычки (\") внутри "
        "строковых значений (для кавычек в русском тексте используй ёлочки «...», "
        "а выдержку в секундах пиши как \"1/6 с\", а не \"1/6\"\").\n"
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


def _repair_concept_fields(concept: FusedPhotoConcept) -> FusedPhotoConcept:
    """Дополняет частично заполненные или дублирующиеся поля концепта от локальной LLM."""
    if not concept.title or len(concept.title.strip()) < 3 or concept.title == "Без названия":
        return concept

    # 1. Гарантируем 3 уникальных стиля в триаде
    used: list[str] = []
    for role_attr, role_key in (
        ("narrative", "narrative"),
        ("lighting", "lighting"),
        ("optics", "optics"),
    ):
        assign: StyleAssignment = getattr(concept.triad, role_attr)
        norm_style = _normalize_style_name(assign.style, default_style=AVAILABLE_STYLES[0])
        if norm_style in used:
            for candidate in AVAILABLE_STYLES:
                if candidate not in used:
                    norm_style = candidate
                    break
        used.append(norm_style)
        assign.style = norm_style
        assign.role = role_key
        if not assign.traits.strip():
            assign.traits = STYLE_ROLE_TRAITS.get(norm_style, {}).get(role_key, "")

    if not concept.triad.rationale.strip():
        concept.triad.rationale = (
            f"Синтез: {concept.triad.narrative.style} (сюжет), "
            f"{concept.triad.lighting.style} (свет) и {concept.triad.optics.style} (оптика)."
        )

    # 2. Дополняем текстовые блоки при обрыве генерации
    if not concept.manifesto:
        concept.manifesto = concept.triad.rationale
    if not concept.scene_description:
        concept.scene_description = concept.triad.narrative.traits or concept.manifesto
    if not concept.lighting_setup:
        concept.lighting_setup = (
            concept.triad.lighting.traits
            or STYLE_ROLE_TRAITS.get(concept.triad.lighting.style, {}).get("lighting", "")
        )

    # 3. Гарантируем минимум 2 параметра камеры
    if len(concept.camera_setup) < 2:
        opt_trait = (
            concept.triad.optics.traits[:80]
            if concept.triad.optics.traits
            else "Художественная оптика"
        )
        defaults = {
            "Приём съёмки": opt_trait,
            "Выдержка": "1/6 с",
            "Диафрагма": "f/2.8",
            "Имитация плёнки": "Classic Chrome",
        }
        for k, v in defaults.items():
            if k not in concept.camera_setup:
                concept.camera_setup[k] = v
            if len(concept.camera_setup) >= 3:
                break

    if not concept.gear_recipe:
        concept.gear_recipe = {"camera": "Fujifilm X-T4"}

    # 4. Физическое действие и пошаговый план
    if not concept.shooting_action:
        if concept.shooting_steps:
            concept.shooting_action = concept.shooting_steps[0]
        else:
            concept.shooting_action = (
                concept.triad.optics.traits
                or "Плавная работа с оптическим рисунком и светотенью с рук"
            )

    if len(concept.shooting_steps) == 1:
        concept.shooting_steps.append(f"Шаг 2: Выполнить приём — {concept.shooting_action}")
    elif len(concept.shooting_steps) == 0:
        cam_pairs = ", ".join(
            f"{k}: {v}" for k, v in list(concept.camera_setup.items())[:2]
        )
        light_preview = (
            concept.lighting_setup[:90] or "контрастный светотеневой рисунок"
        )
        concept.shooting_steps = [
            f"Шаг 1: Настроить камеру ({cam_pairs})",
            f"Шаг 2: Выстроить свет — {light_preview}",
            f"Шаг 3: Выполнить съёмку — {concept.shooting_action[:90]}",
        ]

    return concept


def parse_fusion_concepts(raw_response: str) -> list[FusedPhotoConcept]:
    """Парсит и валидирует концепт-проекты из ответа LLM."""
    projects_raw: list[Any] = []
    parsed = safe_parse_llm_json(raw_response, expected_type=dict)
    if isinstance(parsed, dict):
        projects_raw = (
            parsed.get("projects")
            or parsed.get("ideas")
            or parsed.get("concepts")
            or parsed.get("items")
            or []
        )
        if not projects_raw and "title" in parsed and (
            "triad" in parsed or "camera_setup" in parsed or "manifesto" in parsed
        ):
            projects_raw = [parsed]
    elif not isinstance(parsed, dict):
        list_parsed = safe_parse_llm_json(raw_response, expected_type=list)
        if isinstance(list_parsed, list):
            projects_raw = list_parsed

    # Fallback 1: спасение закрытых проектов из частично обрезанного ответа (MAX_TOKENS)
    if not projects_raw:
        projects_raw = extract_partial_json_array(
            raw_response, array_keys=("projects", "ideas", "concepts"),
        )

    # Fallback 2: спасение первого незакрытого проекта, если ответ оборвался внутри него
    if not projects_raw:
        projects_raw = salvage_truncated_json_object(
            raw_response, array_keys=("projects", "ideas", "concepts"),
        )

    if not isinstance(projects_raw, list) or not projects_raw:
        logger.warning("[FUSION] Failed to parse JSON response: %s", raw_response[:200])
        return []

    valid_concepts: list[FusedPhotoConcept] = []
    for p in projects_raw:
        if not isinstance(p, dict):
            continue
        try:
            concept = _repair_concept_fields(FusedPhotoConcept.from_dict(p))
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
    - body: Полный HTML-лонгрид со всеми разделами проекта без сырого маркдауна.
    """
    clean_title = concept.title.strip()
    if clean_title.startswith("[В планах]"):
        note_title = clean_title
    else:
        note_title = f"[В планах] {clean_title}"

    html_parts = [
        f"<div><h1>{html.escape(note_title)}</h1></div>",
        "<div><p><b>Статус:</b> <code>[В планах]</code></p></div>",
        "<hr>",
        "<div><h2>🎭 Триада стилистического синтеза</h2></div>",
        "<ul>",
        f"  <li><b>Сюжет (Narrative):</b> {html.escape(concept.triad.narrative.style)} — "
        f"{html.escape(concept.triad.narrative.traits)}</li>",
        f"  <li><b>Свет и атмосфера (Lighting):</b> {html.escape(concept.triad.lighting.style)} — "
        f"{html.escape(concept.triad.lighting.traits)}</li>",
        f"  <li><b>Оптика и фактура (Optics):</b> {html.escape(concept.triad.optics.style)} — "
        f"{html.escape(concept.triad.optics.traits)}</li>",
        "</ul>",
        f"<p><b>Обоснование синергии:</b> {html.escape(concept.triad.rationale)}</p>",
    ]

    if concept.manifesto:
        html_parts.extend([
            "<div><h2>📜 Художественный манифест</h2></div>",
            f"<div><p>{html.escape(concept.manifesto.strip())}</p></div>",
        ])

    if concept.scene_description:
        html_parts.extend([
            "<div><h2>🖼 Визуальная сцена и композиция</h2></div>",
            f"<div><p>{html.escape(concept.scene_description.strip())}</p></div>",
        ])

    if concept.lighting_setup:
        html_parts.extend([
            "<div><h2>💡 Схема освещения</h2></div>",
            f"<div><p>{html.escape(concept.lighting_setup.strip())}</p></div>",
        ])

    if concept.camera_setup:
        html_parts.append("<div><h2>📷 Параметры камеры (Fujifilm X-T4)</h2></div>")
        html_parts.append("<ul>")
        for param, val in concept.camera_setup.items():
            html_parts.append(
                f"  <li><b>{html.escape(str(param))}:</b> <code>{html.escape(str(val))}</code></li>"
            )
        html_parts.append("</ul>")

    if concept.shooting_action:
        html_parts.extend([
            "<div><h2>👐 Физика съёмки (действие рук)</h2></div>",
            f"<div><p>{html.escape(concept.shooting_action.strip())}</p></div>",
        ])

    if concept.gear_recipe:
        html_parts.append("<div><h2>🎒 Рецепт оборудования</h2></div>")
        html_parts.append("<ul>")
        for k, v in concept.gear_recipe.items():
            html_parts.append(
                f"  <li><b>{html.escape(str(k))}:</b> {html.escape(str(v))}</li>"
            )
        html_parts.append("</ul>")

    if concept.shooting_steps:
        html_parts.append("<div><h2>📋 Пошаговый план съёмки</h2></div>")
        html_parts.append("<ol>")
        for step in concept.shooting_steps:
            html_parts.append(f"  <li>{html.escape(step)}</li>")
        html_parts.append("</ol>")

    # Внутрикамерный рецепт Fujifilm X-T4 под проект
    try:
        from services.fuji_recipes import build_fuji_recipe_for_concept
        fuji_rec = build_fuji_recipe_for_concept(concept)
        hl = f"{fuji_rec.highlight_tone:+.1f}" if fuji_rec.highlight_tone != 0 else "0.0"
        sh = f"{fuji_rec.shadow_tone:+.1f}" if fuji_rec.shadow_tone != 0 else "0.0"
        wbr = f"{fuji_rec.wb_shift_r:+d}" if fuji_rec.wb_shift_r != 0 else "0"
        wbb = f"{fuji_rec.wb_shift_b:+d}" if fuji_rec.wb_shift_b != 0 else "0"
        fuji_sim = html.escape(fuji_rec.film_simulation)
        fuji_wb = html.escape(fuji_rec.white_balance)
        fuji_gr = html.escape(fuji_rec.grain_effect)
        html_parts.extend([
            "<div><h2>🎛 Внутрикамерный рецепт Fujifilm X-T4 (слот C1)</h2></div>",
            "<ul>",
            f"  <li><b>Имитация плёнки:</b> {fuji_sim} ({fuji_rec.dynamic_range})</li>",
            f"  <li><b>Тоновая кривая:</b> Подсветка {hl} / Тень {sh}</li>",
            f"  <li><b>Баланс белого:</b> {fuji_wb} (R{wbr} / B{wbb})</li>",
            f"  <li><b>Эффект зерна:</b> {fuji_gr} | "
            f"<b>Чёткость:</b> {fuji_rec.clarity:+d}</li>",
            f"  <li><b>Цвет:</b> {fuji_rec.color:+d} | "
            f"<b>Резкость:</b> {fuji_rec.sharpness:+d}</li>",
            "</ul>",
        ])
    except Exception as exc:  # noqa: BLE001
        logger.debug("[FUSION] Fuji recipe export note skip: %s", exc)

    # Режиссёрское углубление образа (если производилось)
    if concept.deepened_analysis:
        from services.text_formatter import safe_html_format
        html_parts.extend([
            "<div><h2>🔍 Режиссёрское углубление художественного образа</h2></div>",
            f"<div>{safe_html_format(concept.deepened_analysis.strip())}</div>",
        ])

    # Промпт Midjourney / Flux (если генерировался)
    if concept.midjourney_prompt:
        html_parts.extend([
            "<div><h2>🎨 Промпт Midjourney / Flux.1</h2></div>",
            f"<pre><code>{html.escape(concept.midjourney_prompt.strip())}</code></pre>",
        ])

    # Кураторские референсы мастеров
    refs = get_curated_references(concept)
    if refs:
        html_parts.append("<div><h2>🌐 Художественные референсы мастеров</h2></div>")
        html_parts.append("<ul>")
        for r in refs[:5]:
            ref_s = html.escape(r['style'])
            ref_a = html.escape(r['artist'])
            ref_t = html.escape(r['technique'])
            ref_q = html.escape(r['query'])
            html_parts.append(
                f"  <li><b>[{ref_s}] {ref_a}</b> — <i>{ref_t}</i> "
                f"(поиск: <code>{ref_q}</code>)</li>"
            )
        html_parts.append("</ul>")

    lens_info = concept.gear_recipe.get("lens", "Основной объектив")
    filter_info = concept.gear_recipe.get("filter_or_accessory", "Фильтры/насадки")
    html_parts.extend([
        "<div><h2>✅ Чек-лист перед выходом</h2></div>",
        "<ul>",
        "  <li>Заряженные аккумуляторы NP-W235 (2 шт.)</li>",
        "  <li>Чистая скоростная SD-карта UHS-II</li>",
        f"  <li>Камера Fujifilm X-T4 + объектив: {html.escape(str(lens_info))}</li>",
        f"  <li>Насадки/аксессуары: {html.escape(str(filter_info))}</li>",
        "  <li>Проверить баланс белого и профиль камеры</li>",
        "  <li>Микрофибра и салфетки для оптики</li>",
        "</ul>",
    ])

    return note_title, "\n".join(html_parts)


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
    "Конструктивизм": (
        "Russian constructivism aesthetic, Alexander Rodchenko diagonal composition, "
        "dynamic industrial geometry, bold stark graphic lines"
    ),
}

ROLE_MIDJOURNEY_MODIFIERS: dict[str, dict[str, str]] = {
    "Сюрреализм": {
        "narrative": (
            "uncanny narrative staging, paradoxical scale and spatial juxtaposition, "
            "decontextualized symbolic objects"
        ),
        "lighting": (
            "paradoxical twilight luminescence, eerie directional shadow play, "
            "metaphysical nocturnal sun"
        ),
        "optics": (
            "prismatic optical refraction, double-exposure spatial displacement, "
            "mirror reflection split"
        ),
    },
    "Пиктореализм": {
        "narrative": (
            "timeless elegiac composition, solitary poetic figure in atmospheric space, "
            "quiet contemplative mood"
        ),
        "lighting": (
            "velvety sfumato light falloff, soft backlit halo rim glow, "
            "delicate silver luminance transitions"
        ),
        "optics": (
            "soft-focus pictorial lens diffusion, matte silver halide grain, "
            "smoothed micro-contrast"
        ),
    },
    "Экспрессионизм": {
        "narrative": (
            "existential psychological framing, dramatic diagonal tension, "
            "inner anxiety expressed through posture and architecture"
        ),
        "lighting": (
            "razor-sharp chiaroscuro light beam, deep graphic diagonal shadows, "
            "harsh single-source directional contrast"
        ),
        "optics": (
            "Dutch angle 20 degree tilted horizon, wide-angle perspective distortion, "
            "geometric optical imbalance"
        ),
    },
    "Импрессионизм": {
        "narrative": (
            "fleeting candid moment, dynamic atmospheric motion, "
            "shimmering breath of nature"
        ),
        "lighting": (
            "dappled sunlight reflections, shimmering chromatic shadow reflexes, "
            "dissolving contours in vibrant light"
        ),
        "optics": (
            "painterly optical bokeh swirl, layered dark-mode multiple exposure glazing, "
            "fluid motion blur"
        ),
    },
    "Конструктивизм": {
        "narrative": (
            "bold architectural geometry, extreme low or high vantage point, "
            "graphic visual rhythm"
        ),
        "lighting": (
            "stark geometric shadow grids, high-contrast directional sunlight"
        ),
        "optics": (
            "steep foreshortening, tilted diagonal framing, crisp structural edges"
        ),
    },
}

FUJI_FILM_SIM_MJ_MAPPING: dict[str, str] = {
    "Classic Chrome": (
        "Kodachrome 64 documentary slide film aesthetic, muted desaturated tones, "
        "deep slate-blue shadows, warm earthy highlights"
    ),
    "Классический Негатив": (
        "Fujicolor Superia 400 analog color negative film, high-contrast nostalgic color grading, "
        "teal-cyan shadows and warm amber highlights"
    ),
    "ACROS": (
        "Fujifilm Neopan 100 Acros black and white silver gelatin print, "
        "deep pitch-black shadows, rich tonal micro-gradation, fine organic silver halide grain"
    ),
    "ACROS (+R Красный)": (
        "Fujifilm Neopan 100 Acros black and white silver gelatin print with red contrast filter, "
        "dramatic darkened skies, high-contrast monochrome micro-texture"
    ),
    "ACROS (+Ye Желтый)": (
        "Fujifilm Neopan 100 Acros black and white silver gelatin print with yellow filter, "
        "harmonic monochrome tonal separation, natural silver halide grain"
    ),
    "ACROS (+G Зеленый)": (
        "Fujifilm Neopan 100 Acros black and white silver gelatin print with green filter, "
        "expressive skin micro-texture and foliage luminance"
    ),
    "ETERNA/Кино": (
        "Kodak Vision3 500T 35mm motion picture cinema film, soft highlight roll-off, "
        "muted cinematic color palette, logarithmic tonal range"
    ),
    "ETERNA Bleach Bypass": (
        "35mm bleach bypass silver retention process, harsh metallic contrast, "
        "desaturated cold steely palette, gritty analog texture"
    ),
    "ASTIA/Слабая": (
        "Fujichrome Astia 100F slide film, soft velvety skin tones, "
        "pastel micro-contrast, delicate luminance transitions"
    ),
    "Velvia/Яркий": (
        "Fujichrome Velvia 50 vivid slide film, rich saturated chromatic depth, "
        "deep shadows, luminous color contrast"
    ),
    "Velvia": (
        "Fujichrome Velvia 50 vivid slide film, rich saturated chromatic depth, "
        "deep shadows, luminous color contrast"
    ),
    "PROVIA/Стандартный": (
        "Fujichrome Provia 100F reversal slide film, natural true-to-life color reproduction, "
        "balanced analog tonal curve"
    ),
    "PRO Neg. Hi": (
        "Fujifilm Pro 400H portrait color negative film, crisp shadow separation, "
        "natural warm skin tones"
    ),
    "PRO Neg. Std": (
        "Fujifilm Pro 160NS medium format negative aesthetic, ultra-smooth tonal gradation, "
        "soft low-contrast pastel palette"
    ),
    "Монохромный": (
        "Ilford HP5 Plus 400 black and white 35mm film, classic documentary monochrome grain"
    ),
    "Монохромный (+R Красный)": (
        "Ilford HP5 Plus 400 black and white 35mm film with red filter, stark monochrome contrast"
    ),
    "Монохромный (+Ye Желтый)": (
        "Ilford HP5 Plus 400 black and white 35mm film with yellow filter, classic tonal balance"
    ),
    "Монохромный (+G Зеленый)": (
        "Ilford HP5 Plus 400 black and white 35mm film with green filter, rich midtone texture"
    ),
    "Сепия": (
        "vintage warm sepia-toned silver gelatin print, archival albumen warmth, "
        "aged analog paper texture"
    ),
}

_RU_TO_EN_PHOTO_TERMS: tuple[tuple[str, str], ...] = (
    ("одинокая фигура", "solitary human figure"),
    ("фигура", "human figure"),
    ("силуэт", "dramatic dark silhouette"),
    ("пальто", "dark trench coat"),
    ("бетон", "wet brutalist concrete wall texture"),
    ("асфальт", "rain-slicked dark asphalt"),
    ("туман", "dense atmospheric fog"),
    ("дымк", "misty atmospheric haze"),
    ("отражени", "mirror reflection on wet surface"),
    ("луж", "rain puddle reflection"),
    ("зеркал", "shattered mirror glass reflection"),
    ("оскол", "sharp glass shard"),
    ("тень", "deep elongated shadow"),
    ("тени", "deep dramatic shadows"),
    ("дожд", "falling rain droplets and wet surfaces"),
    ("мокр", "wet glistening surface"),
    ("окн", "light streaming through window frame"),
    ("дерев", "bare organic tree branches"),
    ("ветв", "intertwined branches"),
    ("рук", "expressive human hands with natural skin texture"),
    ("лиц", "emotive close-up face with natural skin pores"),
    ("портрет", "intimate fine art portrait"),
    ("причал", "weathered wooden pier by water"),
    ("вод", "dark rippling water surface"),
    ("лестниц", "geometric spiral staircase"),
    ("проулок", "narrow moody urban alley"),
    ("улиц", "empty nocturnal street"),
    ("небоскреб", "monumental glass skyscraper facade"),
    ("фасад", "architectural building facade"),
    ("контровой", "strong dramatic rim backlight, halo contour glow"),
    ("натриев", "warm amber sodium vapor streetlamp light"),
    ("фонар", "solitary streetlamp pool of light"),
    ("боковой", "chiaroscuro directional side lighting"),
    ("сумерк", "twilight blue hour atmosphere"),
    ("ноч", "nocturnal low-key lighting"),
    ("луч", "narrow shaft of volumetric light"),
    ("рассеян", "soft diffused ambient light"),
    ("жестк", "hard directional high-contrast light"),
)

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
        deepened_badge = " ✨ <i>[Образ углублён]</i>" if concept.deepened_analysis else ""
        lines = [
            f"🎨 <b>Проект: «{title_esc}»</b>{deepened_badge} <i>[Стр. 1/{total_pages}]</i>",
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

        # Интеграция внутрикамерного рецепта Fujifilm X-T4 под триаду стилей
        from services.fuji_recipes import build_fuji_recipe_for_concept
        recipe = build_fuji_recipe_for_concept(concept)
        hl = f"{recipe.highlight_tone:+.1f}" if recipe.highlight_tone != 0 else "0.0"
        sh = f"{recipe.shadow_tone:+.1f}" if recipe.shadow_tone != 0 else "0.0"
        wbr = f"{recipe.wb_shift_r:+d}" if recipe.wb_shift_r != 0 else "0"
        wbb = f"{recipe.wb_shift_b:+d}" if recipe.wb_shift_b != 0 else "0"
        lines.extend([
            "\n🎛 <b>Рецепт камеры (слот C1):</b>",
            f"   • Имитация плёнки: <code>{html.escape(recipe.film_simulation)}</code> "
            f"({recipe.dynamic_range})",
            f"   • Кривая: Подсветка {hl} / Тень {sh}",
            f"   • ББ: <code>{html.escape(recipe.white_balance)}</code> (R{wbr} / B{wbb})",
            f"   • Зерно: {html.escape(recipe.grain_effect)} | Четкость: {recipe.clarity:+d}",
        ])
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

    # Ряд 2: Внутрикамерный рецепт X-T4 и Углубление образа
    kb.row(
        types.InlineKeyboardButton(
            text="🎛 Рецепт X-T4",
            callback_data=f"bs_fuji_recipe:{concept_idx}",
        ),
        types.InlineKeyboardButton(
            text="🔍 Углубить образ",
            callback_data=f"bs_deepen:{concept_idx}",
        ),
    )

    # Ряд 3: Генерация промпта и Референсы
    kb.row(
        types.InlineKeyboardButton(
            text="🎨 Промпт Midjourney",
            callback_data=f"bs_prompt:{concept_idx}",
        ),
        types.InlineKeyboardButton(
            text="🌐 Референсы",
            callback_data=f"bs_refs:{concept_idx}",
        ),
    )

    # Ряд 4: Экспорт в Apple Notes и Сохранение во Дворец
    kb.row(
        types.InlineKeyboardButton(
            text="📝 В Apple Notes [В планах]",
            callback_data=f"bs_export_concept:{concept_idx}",
        ),
        types.InlineKeyboardButton(
            text="🏛 Во Дворец",
            callback_data=f"bs_save_concept:{concept_idx}",
        ),
    )

    # Ряд 5: Назад к списку проектов
    kb.row(
        types.InlineKeyboardButton(
            text="◀️ К списку проектов",
            callback_data="bs_back",
        ),
    )
    return kb


def translate_ru_photo_terms_to_en(text: str) -> str:
    """Переводит ключевые русские фотографические мотивы и свет в английские дескрипторы."""
    if not text:
        return ""
    low = text.lower()
    matched: list[str] = []
    for ru_stem, en_phrase in _RU_TO_EN_PHOTO_TERMS:
        if ru_stem in low and en_phrase not in matched:
            matched.append(en_phrase)
            if len(matched) >= 5:
                break
    return ", ".join(matched)


def build_arsenal_optics_mj_tokens(
    lens_raw: str,
    filter_raw: str,
    action_raw: str = "",
    default_lens_label: str = "Fujifilm Fujinon",
) -> list[str]:
    """Отображает полный оптический арсенал и физику съёмки в английские токены Midjourney."""
    tokens: list[str] = []
    lens = (lens_raw or "").lower()
    filt = (filter_raw or "").lower()
    act = (action_raw or "").lower()
    combined = f"{lens} {filt} {act}"

    # 1. Объектив
    if "гелиос" in lens or "helios" in lens:
        tokens.append(
            "shot on vintage Helios 44-2 58mm f/2 lens, circular swirly bokeh, "
            "organic optical vignette"
        )
    elif "kamlan" in lens or "камлан" in lens or "1.1" in lens:
        tokens.append(
            "shot on manual Kamlan 50mm f/1.1 lens wide open at f/1.1, "
            "paper-thin depth of field, creamy melting bokeh, soft spherical aberration glow"
        )
    elif "pentacon" in lens or "пентакон" in lens or "перевёрнут" in lens or "перевернут" in lens:
        tokens.append(
            "shot on modified vintage Pentacon 29mm lens with reversed front element, "
            "tack-sharp central subject surrounded by extreme radial swirly vortex bokeh "
            "and optical edge coma"
        )
    elif "монокль" in lens or "monocle" in lens:
        tokens.append(
            "shot on soft focus monocle lens, ethereal halation glow, "
            "pictorialist spherical aberration"
        )
    elif "отверсти" in lens or "center-hole" in lens:
        tokens.append(
            "shot through custom center-hole diopter filter, tack-sharp central subject "
            "framed by dreamy optical tunnel refraction blur"
        )
    else:
        tokens.append(f"shot on {default_lens_label} lens, rich microcontrast")

    # 2. Фильтры, модификаторы и вспышка
    if "призм" in filt or "prism" in filt or "призм" in act:
        tokens.append(
            "refracted through optical triangular crystal glass prism, chromatic split flare"
        )
    if "mist" in filt or "мист" in filt:
        tokens.append("Black Pro-Mist diffusion filter, soft glowing blooming highlights")
    if "отверсти" in filt and "center-hole" not in " ".join(tokens):
        tokens.append(
            "shot through custom center-hole diopter filter, tack-sharp central subject "
            "framed by dreamy optical tunnel refraction blur"
        )
    if any(w in combined for w in ("ткан", "вуаль", "тюль", "прозрачн", "veil", "tulle")):
        tokens.append(
            "shot through sheer translucent tulle fabric veil close to lens, "
            "misty tactile diffusion, veiled highlights"
        )
    if any(w in combined for w in ("nd", "k&f", "нейтрально-сер", "длинная выдержка")):
        tokens.append(
            "long exposure on tripod with variable ND filter, silky flowing motion blur "
            "contrasted against tack-sharp static elements"
        )
    if any(w in combined for w in ("godox", "вспышк", "шторк", "flash")):
        tokens.append(
            "rear-curtain sync flash photography with Godox V1F, frozen sharp subject "
            "with ambient ghost motion trails"
        )

    # 3. Физика рук, мультиэкспозиция и ICM
    if any(w in act for w in ("мульти", "icm", "лессировк", "тремор", "смаз", "двойн", "руки")):
        if "тёмный" in act or "темный" in act:
            tokens.append(
                "in-camera double exposure in Darken blend mode (silhouette filled with "
                "secondary texture), multiple exposure layering, "
                "intentional camera movement ICM watercolor blur"
            )
        elif "яркий" in act:
            tokens.append(
                "in-camera double exposure in Lighten blend mode, glowing spectral overlay, "
                "multiple exposure layering, intentional camera movement ICM watercolor blur"
            )
        else:
            tokens.append(
                "multiple exposure layering, intentional camera movement ICM watercolor blur"
            )

    if "голландск" in act or "dutch" in act or "наклон" in act:
        tokens.append("Dutch angle tilted horizon 20 degrees, dynamic off-balance framing")

    return tokens


def build_fuji_recipe_mj_tokens(
    recipe_or_sim: Any,
    include_velvia_legacy: bool = False,
) -> str:
    """Преобразует рецепт Fujifilm X-T4 в описание реальной плёночной эмульсии и зерна."""
    sim_name = "Velvia/Яркий"
    h_tone = 0.0
    s_tone = 0.0
    grain = ""
    clarity = 0
    wb_r = 0
    wb_b = 0

    if isinstance(recipe_or_sim, str) and recipe_or_sim.strip():
        sim_name = recipe_or_sim.strip()
    elif isinstance(recipe_or_sim, dict):
        sim_name = str(recipe_or_sim.get("film_simulation") or "Velvia/Яркий")
        h_tone = float(recipe_or_sim.get("highlight_tone") or 0.0)
        s_tone = float(recipe_or_sim.get("shadow_tone") or 0.0)
        grain = str(recipe_or_sim.get("grain_effect") or "")
        clarity = int(recipe_or_sim.get("clarity") or 0)
        wb_r = int(recipe_or_sim.get("wb_shift_r") or 0)
        wb_b = int(recipe_or_sim.get("wb_shift_b") or 0)
    elif recipe_or_sim is not None and hasattr(recipe_or_sim, "film_simulation"):
        sim_name = str(getattr(recipe_or_sim, "film_simulation", "Velvia/Яркий"))
        h_tone = float(getattr(recipe_or_sim, "highlight_tone", 0.0))
        s_tone = float(getattr(recipe_or_sim, "shadow_tone", 0.0))
        grain = str(getattr(recipe_or_sim, "grain_effect", ""))
        clarity = int(getattr(recipe_or_sim, "clarity", 0))
        wb_r = int(getattr(recipe_or_sim, "wb_shift_r", 0))
        wb_b = int(getattr(recipe_or_sim, "wb_shift_b", 0))

    emulsion = FUJI_FILM_SIM_MJ_MAPPING.get(sim_name)
    if not emulsion:
        for key, val in FUJI_FILM_SIM_MJ_MAPPING.items():
            if key.lower() in sim_name.lower() or sim_name.lower() in key.lower():
                emulsion = val
                break
    if not emulsion:
        emulsion = FUJI_FILM_SIM_MJ_MAPPING["Classic Chrome"]

    sub_tokens: list[str] = []
    if include_velvia_legacy and "velvia" not in sim_name.lower():
        sub_tokens.append(f"Fujifilm X-T4 film simulation Velvia / {sim_name}")
    elif "velvia" in sim_name.lower():
        sub_tokens.append("Fujifilm X-T4 film simulation Velvia")
    else:
        sub_tokens.append(f"Fujifilm X-T4 film simulation {sim_name}")

    sub_tokens.append(emulsion)

    # Тоновая кривая
    if s_tone >= 2.0:
        sub_tokens.append("crushed ink-black shadows")
    elif s_tone <= -1.0:
        sub_tokens.append("lifted matte atmospheric shadows")
    if h_tone <= -1.0:
        sub_tokens.append("soft rolled-off creamy highlights")
    elif h_tone >= 1.5:
        sub_tokens.append("crisp specular highlights")

    # Зерно и чёткость
    grain_low = grain.lower()
    if "сильный" in grain_low:
        sub_tokens.append("pronounced coarse 35mm silver halide film grain")
    elif "слабый" in grain_low:
        sub_tokens.append("fine organic 35mm film grain")
    else:
        sub_tokens.append("authentic 35mm analog film grain")

    if clarity < 0:
        sub_tokens.append("negative clarity dreamy highlight halation")

    # Цветовой сдвиг баланса белого (WB Shift R/B)
    if wb_r >= 2 and wb_b <= -2:
        sub_tokens.append("warm amber-golden analog color cast")
    elif wb_r <= -2 and wb_b >= 2:
        sub_tokens.append("cool cyan-slate nocturnal color cast")
    elif wb_r >= 2 and wb_b >= 2:
        sub_tokens.append("split-toned magenta-violet twilight cast")

    return ", ".join(sub_tokens)


def build_mj_technical_flags(aspect_ratio: str = "16:9", mode: str = "raw") -> str:
    """Формирует финальный блок параметров Midjourney v6.1 и анти-CGI защиту."""
    valid_ars = ("16:9", "4:5", "3:2", "1:1", "21:9")
    ar = aspect_ratio if aspect_ratio in valid_ars else "16:9"
    neg = "--no cgi, 3d render, digital painting, illustration, plastic airbrushed skin"
    if mode == "art":
        return f"--ar {ar} --v 6.1 --s 220 --w 35 --c 12 {neg}"
    return f"--ar {ar} --v 6.1 --style raw --s 90 {neg}"


def build_midjourney_prompt(
    concept: FusedPhotoConcept,
    aspect_ratio: str = "16:9",
    mode: str = "raw",
) -> str:
    """Генерирует фотореалистичный английский промпт для Midjourney v6.1 / Flux.1."""
    parts: list[str] = [
        "unretouched raw analog 35mm photograph, authentic optical physics, "
        "natural surface micro-texture"
    ]

    # Стилистические модификаторы триады с учётом конкретной роли каждого стиля
    role_pairs = (
        ("narrative", concept.triad.narrative.style),
        ("lighting", concept.triad.lighting.style),
        ("optics", concept.triad.optics.style),
    )
    for role_key, style in role_pairs:
        mod = STYLE_MIDJOURNEY_MODIFIERS.get(style)
        if mod and mod not in parts:
            parts.append(mod)
        role_mod = ROLE_MIDJOURNEY_MODIFIERS.get(style, {}).get(role_key)
        if role_mod and role_mod not in parts:
            parts.append(role_mod)

    # Описание сцены + автоматический англоязычный фотографический перевод
    scene = concept.scene_description.strip()
    if scene:
        en_scene = translate_ru_photo_terms_to_en(scene)
        if en_scene:
            parts.append(f"scene: {scene} ({en_scene})")
        else:
            parts.append(f"scene: {scene}")

    # Световая схема + автоматический англоязычный перевод света
    lighting = concept.lighting_setup.strip()
    if lighting:
        en_light = translate_ru_photo_terms_to_en(lighting)
        if en_light:
            parts.append(f"lighting: {lighting} ({en_light})")
        else:
            parts.append(f"lighting: {lighting}")

    # Оптика, фильтры, насадки и действие рук
    gear = concept.gear_recipe
    lens_str = str(gear.get("lens", ""))
    filt_str = str(gear.get("filter_or_accessory", ""))
    parts.extend(
        build_arsenal_optics_mj_tokens(
            lens_raw=lens_str,
            filter_raw=filt_str,
            action_raw=concept.shooting_action,
            default_lens_label="Fujifilm Fujinon",
        )
    )

    # Реальная эмульсия и рецепт плёнки Fujifilm X-T4
    try:
        from services.fuji_recipes import build_fuji_recipe_for_concept
        fuji_rec = build_fuji_recipe_for_concept(concept)
        emulsion_str = build_fuji_recipe_mj_tokens(fuji_rec, include_velvia_legacy=True)
    except Exception:  # noqa: BLE001
        cam_sim = str(concept.camera_setup.get("film_sim", "Velvia/Яркий"))
        emulsion_str = build_fuji_recipe_mj_tokens(cam_sim, include_velvia_legacy=True)

    flags = build_mj_technical_flags(aspect_ratio=aspect_ratio, mode=mode)
    parts.append(
        f"{emulsion_str}, fine art gallery photography, editorial aesthetic {flags}"
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
        "Пиши лаконично, образно, профессионально. Без пустых общих фраз. "
        "Объём ответа: до 1500–2000 символов, чтобы анализ был концентрированным."
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
    from services.text_formatter import safe_html_format

    title_esc = html.escape(concept.title)
    return (
        f"🔍 <b>Режиссёрское углубление: «{title_esc}»</b>\n\n"
        f"{safe_html_format(analysis_text.strip())}"
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
    from services.text_formatter import safe_html_format

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
        q_encoded = urllib.parse.quote(r["query"])
        google_url = f"https://www.google.com/search?tbm=isch&q={q_encoded}"
        pinterest_url = f"https://www.pinterest.com/search/pins/?q={q_encoded}"
        lines.append(
            f"• <b>[{s_esc}] {art_esc}</b>\n"
            f"  <i>{tech_esc}</i>\n"
            f"  🔍 <a href=\"{google_url}\">Google Картинки</a> • "
            f"<a href=\"{pinterest_url}\">Pinterest</a> • <code>{q_esc}</code>"
        )

    if web_snippets.strip():
        clean_snippets = web_snippets.strip()
        clean_snippets = re.sub(r"<br\s*/?>", "\n", clean_snippets, flags=re.IGNORECASE)
        clean_snippets = re.sub(r"^🌐\s*<b>Результаты поиска</b>\s*", "", clean_snippets)
        clean_snippets = re.sub(r"^🔍\s*Результаты по[^\n]*\n+", "", clean_snippets)
        clean_snippets = clean_snippets.strip()
        if clean_snippets:
            formatted_snippets = safe_html_format(clean_snippets[:700])
            lines.append(f"\n🔎 <b>Находки из сети:</b>\n{formatted_snippets}")

    lines.append(
        "\n💡 <i>Нажмите на ссылки «Google Картинки» или «Pinterest», чтобы сразу открыть "
        "визуальные референсы в браузере.</i>"
    )
    return "\n".join(lines)
