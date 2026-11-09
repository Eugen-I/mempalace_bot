"""services/fuji_multiexposure.py — Движок симуляции мультиэкспозиции Fujifilm X-T4 (ST-1).

Официальные спецификации Fujifilm X-T4 (прошивка 2.12, русское меню):
- Режимы наложения (Blend Modes):
  • ADDITIVE (Сложение) — прямое суммирование экспозиций, требует поправки EV -1..-2.
  • AVERAGE (Усреднение) — авто-усреднение по кадрам, идеален для призрачного сюрреализма.
  • BRIGHT (Яркий) — оставляет максимальную яркость пикселей (Lighten Priority).
  • DARK (Тёмный) — оставляет минимальную яркость (Darken Priority, акварель 1/6с).
- Лимиты: от 2 до 9 кадров в одном RAW/JPG файле.
- Послойные сценарии съемки: контражурный силуэт -> заполняющая текстура -> цветовой сдвиг.
- SOOC (Straight Out Of Camera) без постобработки в Photoshop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import secrets
from typing import TYPE_CHECKING, Any

from services.text_formatter import safe_html_format

if TYPE_CHECKING:
    from services.copilot_session import CopilotSession  # noqa: F401

logger = logging.getLogger("FujiMultiExposure")

# Режимы наложения X-T4 с русскими названиями и оптическим смыслом
BLEND_MODES = {
    "DARK": {
        "name_ru": "ТЁМНЫЙ (Dark / Сравнительно тёмный)",
        "logic": "Оставляет самый тёмный пиксель из всех кадров (Darken Priority).",
        "creative_use": "Акварельная лессировка 1/6с, силуэты с текстурой, сюрреализм.",
        "ev_rec": "-1.0 EV",
    },
    "BRIGHT": {
        "name_ru": "ЯРКИЙ (Bright / Сравнительно светлый)",
        "logic": "Оставляет самый яркий пиксель из всех кадров (Lighten Priority).",
        "creative_use": "Световые призраки, неон в темных фигурах, прорастание светом.",
        "ev_rec": "-0.5 EV",
    },
    "AVERAGE": {
        "name_ru": "УСРЕДНЕНИЕ (Average)",
        "logic": "Автоматически делит экспозицию поровну между всеми слоями.",
        "creative_use": "Мягкий призрачный дрим-эффект, силуэты в движении, расфокус.",
        "ev_rec": "0.0 EV",
    },
    "ADDITIVE": {
        "name_ru": "СЛОЖЕНИЕ (Additive / Аддитивный)",
        "logic": "Прямое сложение света всех кадров (требует ручного занижения EV).",
        "creative_use": "Светящиеся силуэты на черном, луна/звезды в ночном кадре, светографика.",
        "ev_rec": "-1.5 EV",
    },
}


@dataclass
class MultiExposureLayer:
    """Параметры отдельного слоя мультиэкспозиции."""

    layer_idx: int
    role: str  # Базовый силуэт, Фактурный слой, Цветовой акцент
    film_simulation: str
    shutter_speed: str
    aperture: str
    ev_offset: str
    physics_action: str
    instructions: str


@dataclass
class MultiExposurePlan:
    """Полный сценарий мультиэкспозиции для съемки на Fujifilm X-T4."""

    title: str
    blend_mode: str  # DARK, BRIGHT, AVERAGE, ADDITIVE
    blend_mode_ru: str
    frames_count: int  # 2..9
    total_ev_compensation: str
    layers: list[MultiExposureLayer] = field(default_factory=list)
    creative_intent: str = ""
    camera_steps: list[str] = field(default_factory=list)


def build_multiexposure_plan(
    session: Any = None,
    blend_mode: str | None = None,
    frames_count: int = 2,
    session_or_concept: Any = None,
) -> MultiExposurePlan:
    """Синтезирует съемочный сценарий мультиэкспозиции под тему и стили проекта."""
    target = session if session is not None else session_or_concept
    frames_count = max(2, min(9, int(frames_count or 2)))

    # Извлечение темы и стилей
    title = "Сюрреалистический кадр"
    styles_list: list[str] = []

    if hasattr(target, "topic") and target.topic:
        title = target.topic.strip()
        selected_styles = getattr(target, "selected_styles", []) or []
        for s in selected_styles:
            name = s.get("name") if isinstance(s, dict) else str(s)
            if name:
                styles_list.append(name.lower())
    elif isinstance(target, dict):
        title = target.get("title") or target.get("name") or title
        for s in target.get("styles", []):
            name = s.get("name") if isinstance(s, dict) else str(s)
            if name:
                styles_list.append(name.lower())

    styles_text = " ".join(styles_list)

    # 1. Автоматический подбор режима наложения, если не задан явно
    if not blend_mode or blend_mode.upper() not in BLEND_MODES:
        if "импрессионизм" in styles_text:
            blend_mode = "DARK"
        elif "пикториализм" in styles_text:
            blend_mode = "AVERAGE"
        elif "экспрессионизм" in styles_text:
            blend_mode = "ADDITIVE"
        elif any(w in title.lower() for w in ["призрак", "свет", "сияние", "неон"]):
            blend_mode = "BRIGHT"
        else:
            blend_mode = "DARK"  # Канонический режим для сюрреализма Магритта

    clean_mode = blend_mode.upper()
    mode_info = BLEND_MODES[clean_mode]

    # 2. Послойный сценарий съемки
    layers: list[MultiExposureLayer] = []

    if clean_mode == "DARK":
        # Сценарий «Акварельная лессировка / Текстурный силуэт»
        layers.append(MultiExposureLayer(
            layer_idx=1,
            role="Контражурный контур / Силуэт",
            film_simulation="Classic Neg",
            shutter_speed="1/60s" if "импрессионизм" not in styles_text else "1/6s",
            aperture="f/4.0",
            ev_offset="-1.0 EV",
            physics_action="Статичный ракурс. Фокус на геометрии фигуры или темных ветвях.",
            instructions="Снимите темный силуэт на фоне светлого неба или окна.",
        ))
        layers.append(MultiExposureLayer(
            layer_idx=2,
            role="Заполняющая текстура / Лессировка",
            film_simulation="Velvia" if "импрессионизм" in styles_text else "ACROS+R",
            shutter_speed="1/6s",
            aperture="f/8.0",
            ev_offset="-0.7 EV",
            physics_action="Микро-ICM (легкое круговое покачивание камеры в руках во время 1/6с).",
            instructions="Фактура проявится только внутри темных участков первого слоя.",
        ))
        if frames_count >= 3:
            layers.append(MultiExposureLayer(
                layer_idx=3,
                role="Атмосферный акцент / Световая вуаль",
                film_simulation="ETERNA",
                shutter_speed="1/15s",
                aperture="f/2.0",
                ev_offset="-1.3 EV",
                physics_action="Расфокус объектива (мягкое масляное пятно боке).",
                instructions="Добавляет живописную цветовую дымку в полутона.",
            ))

    elif clean_mode == "BRIGHT":
        # Сценарий «Световой призрак / Неоновое свечение»
        layers.append(MultiExposureLayer(
            layer_idx=1,
            role="Темное окружение / Ночной ландшафт",
            film_simulation="Classic Chrome",
            shutter_speed="1/30s",
            aperture="f/2.8",
            ev_offset="-0.7 EV",
            physics_action="Плотная фиксация камеры на уровне пояса.",
            instructions="Экспонируйте глубокие тени и приглушенный фон.",
        ))
        layers.append(MultiExposureLayer(
            layer_idx=2,
            role="Световой силуэт / Призрак",
            film_simulation="ASTIA",
            shutter_speed="1/8s",
            aperture="f/1.4",
            ev_offset="+0.3 EV",
            physics_action="Шаг вперед со смещением оси видоискателя на 15 градусов.",
            instructions="Яркие световые рефлексы врежутся в темные участки первого кадра.",
        ))
        if frames_count >= 3:
            layers.append(MultiExposureLayer(
                layer_idx=3,
                role="Импульсный след / Блик",
                film_simulation="Velvia",
                shutter_speed="1/2s",
                aperture="f/5.6",
                ev_offset="0.0 EV",
                physics_action="Линейный смаз вдоль источников света.",
                instructions="Создает динамические световые росчерки поверх композиции.",
            ))

    elif clean_mode == "ADDITIVE":
        # Сценарий «Сложение света на черном»
        layers.append(MultiExposureLayer(
            layer_idx=1,
            role="Графическая форма / Контур",
            film_simulation="ACROS+R",
            shutter_speed="1/125s",
            aperture="f/5.6",
            ev_offset="-1.5 EV",
            physics_action="Точечный замер по яркому. Фон должен уйти в абсолютный черный.",
            instructions="Снимите первый объект так, чтобы вокруг была кромешная тьма.",
        ))
        layers.append(MultiExposureLayer(
            layer_idx=2,
            role="Совмещенная структура / Зеркало",
            film_simulation="ETERNA Bleach Bypass",
            shutter_speed="1/60s",
            aperture="f/4.0",
            ev_offset="-1.5 EV",
            physics_action="Поворот камеры на 90 градусов (вертикаль на горизонталь).",
            instructions="Второй светящийся объект наложится на первый без пересвета.",
        ))

    else:
        # AVERAGE (Усреднение)
        layers.append(MultiExposureLayer(
            layer_idx=1,
            role="Резкий фокус / Структура",
            film_simulation="Classic Chrome",
            shutter_speed="1/60s",
            aperture="f/4.0",
            ev_offset="0.0 EV",
            physics_action="Штатив или упор о плечо. Бритвенно резкий кадр.",
            instructions="Фиксирует четкие архитектурные или портретные линии.",
        ))
        layers.append(MultiExposureLayer(
            layer_idx=2,
            role="Мягкий расфокус / Дрим-эффект",
            film_simulation="PRO Neg. Std",
            shutter_speed="1/30s",
            aperture="f/1.4",
            ev_offset="0.0 EV",
            physics_action="Плавный ручной увод геликоида фокусировки в полный расфокус.",
            instructions="Дает пикториальный ореол свечения вокруг резких контуров первого слоя.",
        ))

    # Дополнение слоев при запросе более 2 кадров (до 9)
    while len(layers) < frames_count:
        curr_idx = len(layers) + 1
        layers.append(MultiExposureLayer(
            layer_idx=curr_idx,
            role=f"Экспериментальный слой #{curr_idx}",
            film_simulation="PROVIA",
            shutter_speed="1/15s",
            aperture="f/4.0",
            ev_offset="-0.5 EV",
            physics_action="Свободный сдвиг перспективы.",
            instructions="Дополнительное наслоение плотности на матрицу X-T4.",
        ))

    # 3. Пошаговые действия в меню X-T4
    camera_steps = [
        "1. Переведите диск привода в положение <b>MULTI</b> или в меню: "
        "<code>НАСТРОЙКА СЪЕМКИ ➔ МУЛЬТИЭКСПОЗИЦИЯ ➔ ВКЛ</code>.",
        f"2. Выберите режим наложения: <b>{mode_info['name_ru']}</b>.",
        f"3. Установите экспокоррекцию EV: <b>{mode_info['ev_rec']}</b> для защиты от пересвета.",
        "4. Сделайте <b>Кадр 1</b>. На экране X-T4 появится полупрозрачный предпросмотр слоя.",
        "5. Наведите камеру на второй сюжет: сквозь полупрозрачный слой совместите кадр.",
        "6. Спустите затвор для <b>Кадра 2</b> (кнопка <code>BACK</code> — повтор слоя).",
    ]

    creative_intent = (
        f"Режим {clean_mode} выбран для проекта «{title}»: {mode_info['creative_use'].lower()} "
        f"{mode_info['logic']}"
    )

    return MultiExposurePlan(
        title=title,
        blend_mode=clean_mode,
        blend_mode_ru=mode_info["name_ru"],
        frames_count=frames_count,
        total_ev_compensation=mode_info["ev_rec"],
        layers=layers,
        creative_intent=creative_intent,
        camera_steps=camera_steps,
    )


def generate_surreal_multiexposure(
    session: Any = None,
    session_or_concept: Any = None,
) -> MultiExposurePlan:
    """Генерирует непредсказуемый сюрреалистический сценарий наложения (Cadavre Exquis)."""
    target = session if session is not None else session_or_concept
    rng = secrets.SystemRandom()
    modes = list(BLEND_MODES.keys())
    chosen_mode = rng.choice(modes)
    chosen_frames = rng.choice([2, 3, 4])

    plan = build_multiexposure_plan(
        session=target,
        blend_mode=chosen_mode,
        frames_count=chosen_frames,
    )
    plan.title = f"Сюрреалистический комбо: {plan.title}"
    return plan


def format_multiexposure_card(plan: MultiExposurePlan) -> str:
    """Форматирует визуальную шпаргалку для Telegram UI (HTML safety: code, b, blockquote)."""
    title = safe_html_format(plan.title)
    mode_ru = safe_html_format(plan.blend_mode_ru)
    ev_comp = safe_html_format(plan.total_ev_compensation)
    intent = safe_html_format(plan.creative_intent)

    lines = [
        f"🎞 <b>Мультиэкспозиция X-T4 • «{title}»</b>",
        "",
        "⚙️ <b>Параметры прошивки камеры 2.12:</b>",
        f"  • Режим наложения: <b>{mode_ru}</b>",
        f"  • Число наложений: <b>{plan.frames_count} кадра</b> (лимит до 9)",
        f"  • Общая поправка EV: <code>{ev_comp}</code>",
        "",
        f"<blockquote>{intent}</blockquote>",
        "",
        "🎬 <b>Послойный сценарий съемки:</b>",
    ]

    for layer in plan.layers:
        r_role = safe_html_format(layer.role)
        r_sim = safe_html_format(layer.film_simulation)
        r_phys = safe_html_format(layer.physics_action)
        r_inst = safe_html_format(layer.instructions)

        lines.extend([
            f"<b>[ Слой {layer.layer_idx}/{plan.frames_count} — {r_role} ]</b>",
            f"  • Настройки: <code>{r_sim}</code> | <code>{layer.shutter_speed}</code> | "
            f"<code>{layer.aperture}</code> (EV {layer.ev_offset})",
            f"  • Физика: <i>{r_phys}</i>",
            f"  • Совет: {r_inst}",
            "",
        ])

    lines.extend([
        "📋 <b>Порядок действий на камере X-T4:</b>",
    ])
    for step in plan.camera_steps:
        lines.append(f"  {step}")

    return "\n".join(lines)
