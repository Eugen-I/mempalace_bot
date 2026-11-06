"""Deterministic safety gate for Garmin coaching and training plans.

The gate runs before any plan or AI narration.  It never diagnoses, never
changes medication doses, and never tries to make a dangerous situation
"trainable".  Critical red flags stop plan generation and point the user to
medical help; warnings keep the plan conservative and are shown in the UI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Literal

from .analytics import ReportData
from .medications import build_layer, lookup
from .models import Checkin, Event, SafetyFlag, UserProfile
from .readiness import assess_readiness

Severity = Literal["info", "warning", "critical"]


@dataclass(frozen=True)
class SafetySignal:
    code: str
    severity: Severity
    text: str
    source: str = ""


MEDICAL_DISCLAIMER = (
    "Это не диагноз и не медицинская рекомендация. Бот не меняет дозы, "
    "не отменяет препараты и не заменяет врача."
)

ESCALATION_TEXT = (
    "Остановитесь и не выполняйте тренировку. При боли в груди, обмороке, "
    "выраженной одышке, новых неврологических симптомах или мыслях о "
    "самоповреждении срочно обратитесь за медицинской помощью "
    "(в России — 103 или 112)."
)

_NEGATION = re.compile(
    r"(?i)(?:\bнет|\bне\s+было|\bбез|\bотрицает|\bне\s+беспокоит|"
    r"\bисключ\w*|\bno|\bnot|\bdenies)\s*$"
)

_INJECTION = re.compile(
    r"(?i)("
    r"игнорируй\w*|"
    r"проигнорируй\w*|"
    r"забудь\w*|"
    r"обойди\w*|"
    r"отключи\w*\s+(?:правил|ограничен|фильтр)|"
    r"ignore\s+(?:all\s+)?(?:previous|prior|the)\s+instructions|"
    r"disregard\s+(?:all\s+)?(?:previous|prior|the)|"
    r"system\s+prompt|системн\w*\s+промпт|"
    r"developer\s+message|jailbreak|\bDAN\b|prompt\s+injection"
    r")"
)

_DOSE_REQUEST = re.compile(
    r"(?i)("
    r"измен\w*\s+доз|"
    r"увелич\w*\s+доз|"
    r"уменьш\w*\s+доз|"
    r"снизь\w*\s+доз|"
    r"подбер\w*\s+доз|"
    r"сколько\s+(?:мг|таблет)|"
    r"отмен\w*|"
    r"прекрат\w*\s+приним|"
    r"смен\w*\s+препарат|"
    r"назнач\w*\s+(?:мне|себе|препарат|лекарств)|"
    r"change\s+(?:my\s+)?dose|stop\s+(?:my\s+)?medication"
    r")"
)

_PRESSURE = re.compile(
    r"(?i)("
    r"вс[её]\s+равно\s+(?:дай|давай|построй|сделай)|"
    r"несмотря\s+на\s+(?:боль|симптом|самочувств|врач)|"
    r"плевать\s+на\s+(?:боль|симптом|врач)|"
    r"дай\s+план\s+любой\s+ценой|"
    r"just\s+give\s+me\s+the\s+plan"
    r")"
)

_DIAGNOSIS_REQUEST = re.compile(
    r"(?i)(?:поставь\w*\s+(?:мне\s+)?диагноз|что\s+у\s+меня\s+за\s+болезн|"
    r"diagnose\s+me)"
)

# Each entry is (code, regex, severity, user-facing text).  The regexes are
# intentionally narrow enough to avoid matching a denial such as "нет боли".
_RED_FLAG_PATTERNS: tuple[tuple[str, str, Severity, str], ...] = (
    (
        "chest_pain",
        r"(?:боль|болит|давит|тяжест|жжен|сжима)\w*[^.!?\n]{0,35}"
        r"(?:в\s+груд|за\s+грудин|сердц)|"
        r"(?:в\s+груд|за\s+грудин)[^.!?\n]{0,25}"
        r"(?:боль|давит|жжен|сжима)|"
        r"chest\s+(?:pain|pressure)|pain\s+in\s+(?:the\s+)?chest",
        "critical",
        "Боль/давление в груди или за грудиной — тренировку не начинать.",
    ),
    (
        "syncope",
        r"обморок|потеря\w*\s+сознани|упал\w*\s+в\s+обморок|"
        r"faint(?:ed|ing)?|passed\s+out|blackout",
        "critical",
        "Обморок или потеря сознания — нужна срочная оценка врача.",
    ),
    (
        "severe_dizziness",
        r"(?:сильн|выраженн|резк)\w*\s+головокруж|"
        r"кружит\w*\s+голов|не\s+могу\s+стоять|"
        r"severe\s+dizziness|vertigo",
        "critical",
        "Выраженное головокружение — не тренируйтесь и не ведите машину.",
    ),
    (
        "severe_dyspnea",
        r"(?:сильн|выраженн)\w*\s+одышк|"
        r"не\s+хватает\s+воздух|задыха\w*|"
        r"одышк\w*\s+в\s+покое|"
        r"severe\s+shortness\s+of\s+breath|can'?t\s+breathe",
        "critical",
        "Выраженная одышка или нехватка воздуха — срочно к врачу.",
    ),
    (
        "suicidal_ideation",
        r"суицид|не\s+хочу\s+жить|покончить\s+с\s+собой|"
        r"самоповрежд|хочу\s+умереть|suicid|self[- ]?harm",
        "critical",
        "Мысли о самоповреждении — не оставайтесь один; обратитесь за "
        "срочной помощью или к близкому человеку.",
    ),
    (
        "new_neurological",
        r"онемени|слабость\s+в\s+(?:руке|ноге)|перекос\s+лица|"
        r"нарушени\w*\s+речи|потеря\s+зрения|инсульт|"
        r"нов\w*\s+неврологическ|stroke|transient\s+ischemic",
        "critical",
        "Новые неврологические симптомы — срочно обратитесь за помощью.",
    ),
    (
        "uncontrolled_bp",
        r"(?:давлени\w*|\bад)\s*(?:18[0-9]|19[0-9]|2[0-4][0-9])|"
        r"180\s*/\s*120|гипертоническ\w*\s+криз|"
        r"неконтролируем\w*\s+(?:давлени|гипертенз)|"
        r"hypertensive\s+crisis",
        "critical",
        "Очень высокое или неконтролируемое давление — тренировку "
        "отложить и связаться с врачом.",
    ),
    (
        "seizure",
        r"судорог|приступ\s+эпилепс|seizure|convulsion",
        "critical",
        "Судороги — срочная медицинская помощь.",
    ),
    (
        "bleeding",
        r"кровотечени|кровь\s+в\s+(?:стуле|моче)|черн\w*\s+стул|"
        r"рвот\w*\s+с\s+кров|blood\s+in\s+(?:stool|urine)|bleeding",
        "critical",
        "Кровотечение или кровь в стуле/моче — срочно к врачу.",
    ),
    (
        "acute_tendon_pain",
        r"остр\w*\s+боль[^.!?\n]{0,35}(?:сухожил|ахилл)|"
        r"разрыв[^.!?\n]{0,20}сухожил|"
        r"tendon\s+(?:rupture|pain)",
        "critical",
        "Острая боль в сухожилии — остановитесь; нужна оценка врача.",
    ),
    (
        "acute_illness",
        r"температур\w*\s*(?:3[89]|4[0-2])|лихорад|озноб|"
        r"инфекц|temperature\s*(?:38|39|40)|fever|chills",
        "critical",
        "Температура/инфекция — тренировки отложить до выздоровления.",
    ),
)

_WARNING_PATTERNS: tuple[tuple[str, str, Severity, str], ...] = (
    (
        "dizziness",
        r"головокруж|потемнело\s+в\s+глазах|ортостат|"
        r"dizziness|light[- ]?headed",
        "warning",
        "Головокружение/ортостатика: вставайте медленно, пейте воду, при "
        "повторении — к врачу.",
    ),
    (
        "palpitations",
        r"сердцебиени|перебои\s+в\s+сердц|palpitation|heart\s+racing",
        "warning",
        "Необычное сердцебиение: снизьте интенсивность; при головокружении "
        "или боли в груди — стоп и врач.",
    ),
    (
        "elevated_bp",
        r"(?:давлени\w*|\bад)\s*(?:14[0-9]|15[0-9]|16[0-9]|17[0-9])|"
        r"повышенн\w*\s+давлени|hypertension",
        "warning",
        "Повышенное давление: тренировку сделать лёгкой, измерить давление "
        "в покое и обсудить с врачом.",
    ),
    (
        "hypoglycemia",
        r"сахар\s*[0-3](?:[.,]\d)?|гипоглик|hypoglyc",
        "warning",
        "Признаки низкого сахара: остановитесь, примите быстрые углеводы, "
        "если это согласовано с врачом, и не тренируйтесь до стабилизации.",
    ),
    (
        "pregnancy_postpartum",
        r"беременн|послеродов|pregnan|postpartum",
        "warning",
        "Беременность/послеродовой период: нужен индивидуальный план с "
        "врачом, без интенсивных интервалов и перегрева.",
    ),
    (
        "migraine",
        r"мигрен|migraine",
        "warning",
        "Мигрень: тренировка только при хорошем самочувствии, без "
        "обезвоживания и резких скачков нагрузки.",
    ),
    (
        "diabetes",
        r"диабет|diabet|инсулин|сульфонилу|гликлазид|глимепирид|"
        r"гипоглик|hypoglyc",
        "warning",
        "Диабет/сахароснижающие препараты: носите быстрые углеводы, "
        "контролируйте глюкозу и обсудите нагрузку с врачом.",
    ),
    (
        "anticoagulant",
        r"антикоагулянт|варфарин|апиксабан|ривароксабан|дабигатран|"
        r"клопидогрел|тикгрелор|anticoagulant|warfarin|apixaban|"
        r"rivaroxaban|dabigatran|clopidogrel",
        "warning",
        "Препараты, влияющие на свёртываемость: избегайте контактных видов "
        "спорта и падений; при травме — к врачу.",
    ),
    (
        "beta_blocker",
        r"бета[- ]?блок|бисопролол|метопролол|небиволол|bisoprolol|"
        r"metoprolol|nebivolol",
        "warning",
        "Бета-блокаторы могут искажать пульс и HR-зоны: ориентируйтесь на "
        "RPE и мощность.",
    ),
    (
        "pain_moderate",
        r"\bболь\b[^.!?\n]{0,15}\b([1-3])\s*(?:/|из)\s*10|"
        r"\bpain\b[^.!?\n]{0,15}\b([1-3])\s*(?:/|of)\s*10",
        "warning",
        "Боль 1–3/10: уменьшите объём и избегайте движений, которые её "
        "усиливают.",
    ),
    (
        "pain_high_text",
        r"\bболь\b[^.!?\n]{0,15}\b([4-9]|10)\s*(?:/|из)\s*10|"
        r"\bpain\b[^.!?\n]{0,15}\b([4-9]|10)\s*(?:/|of)\s*10",
        "critical",
        "Боль 4/10 или сильнее — тренировку не выполнять, обсудить с врачом.",
    ),
    (
        "shortness_of_breath",
        r"одышк|shortness\s+of\s+breath",
        "warning",
        "Одышка: снизьте темп; если не проходит в покое — к врачу.",
    ),
)

_COMBINATION_CHECKS: tuple[tuple[str, tuple[str, ...], Severity, str], ...] = (
    (
        "possible_serotonin_syndrome",
        ("ажитац", "спутан", "тремор", "лихорад", "ригидност", "потливост", "тахикард"),
        "critical",
        "Ажитация/спутанность/тремор/лихорадка/ригидность на "
        "серотонинергических препаратах — стоп и срочно к врачу.",
    ),
    (
        "palpitations_with_dizziness",
        ("сердцебиен", "головокруж"),
        "critical",
        "Сердцебиение с головокружением — остановитесь и обратитесь к врачу.",
    ),
)


def _normalize(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("ё", "е")).strip().lower()


def _is_negated(text: str, start: int) -> bool:
    prefix = text[max(0, start - 30) : start]
    return bool(_NEGATION.search(prefix))


def _scan_text(text: str | None, *, source: str = "") -> list[SafetySignal]:
    normalized = _normalize(text)
    if not normalized:
        return []
    signals: list[SafetySignal] = []
    seen: set[str] = set()

    for code, pattern, severity, message in _RED_FLAG_PATTERNS:
        for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
            if _is_negated(normalized, match.start()):
                continue
            if code not in seen:
                signals.append(
                    SafetySignal(code=code, severity=severity, text=message, source=source)
                )
                seen.add(code)
            break

    for code, pattern, severity, message in _WARNING_PATTERNS:
        for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
            if _is_negated(normalized, match.start()):
                continue
            if code not in seen:
                signals.append(
                    SafetySignal(code=code, severity=severity, text=message, source=source)
                )
                seen.add(code)
            break

    for code, tokens, severity, message in _COMBINATION_CHECKS:
        present = {token for token in tokens if token in normalized}
        if len(present) >= 2 and code not in seen:
            signals.append(
                SafetySignal(code=code, severity=severity, text=message, source=source)
            )
    return signals


def _add(signals: list[SafetySignal], signal: SafetySignal) -> None:
    if any(
        item.code == signal.code and item.text == signal.text for item in signals
    ):
        return
    signals.append(signal)


def _checkin_signals(checkin: Checkin) -> list[SafetySignal]:
    signals: list[SafetySignal] = []
    if checkin.pain_score is not None:
        if checkin.pain_score >= 4:
            location = f" ({checkin.pain_location})" if checkin.pain_location else ""
            _add(
                signals,
                SafetySignal(
                    code="pain_high",
                    severity="critical",
                    text=f"Боль {checkin.pain_score}/10{location}: тренировку не "
                    "выполнять, обсудить с врачом.",
                    source="checkin",
                ),
            )
        elif checkin.pain_score >= 1:
            _add(
                signals,
                SafetySignal(
                    code="pain_moderate",
                    severity="warning",
                    text=f"Боль {checkin.pain_score}/10: снизить объём и убрать "
                    "движения, усиливающие боль.",
                    source="checkin",
                ),
            )
    if checkin.soreness is not None and checkin.soreness >= 7:
        _add(
            signals,
            SafetySignal(
                code="soreness_high",
                severity="warning",
                text=f"Выраженная болезненность {checkin.soreness}/10: сегодня "
                "отдых или лёгкая мобильность.",
                source="checkin",
            ),
        )
    if checkin.sleep_h is not None and checkin.sleep_h < 5.0:
        _add(
            signals,
            SafetySignal(
                code="sleep_very_short",
                severity="warning",
                text=f"Сон {checkin.sleep_h:.1f} ч: не компенсируйте недосып "
                "тяжёлой тренировкой.",
                source="checkin",
            ),
        )
    if checkin.mood is not None and checkin.mood <= 2:
        _add(
            signals,
            SafetySignal(
                code="low_mood",
                severity="warning",
                text="Низкое настроение: снизьте требования к себе; если "
                "появились мысли о самоповреждении — срочно обратитесь за "
                "помощью.",
                source="checkin",
            ),
        )
    if checkin.stress is not None and checkin.stress >= 5:
        _add(
            signals,
            SafetySignal(
                code="stress_high_subjective",
                severity="warning",
                text="Очень высокий субъективный стресс: нагрузка только "
                "лёгкая, приоритет — сон и восстановление.",
                source="checkin",
            ),
        )
    signals.extend(_scan_text(checkin.notes, source="checkin"))
    return signals


def _profile_signals(profile: UserProfile | None) -> list[SafetySignal]:
    if profile is None:
        return []
    signals: list[SafetySignal] = []
    if profile.doctor_clearance == "no":
        _add(
            signals,
            SafetySignal(
                code="doctor_clearance_no",
                severity="critical",
                text="В профиле указано, что разрешения врача на нагрузку нет. "
                "План не строится до консультации.",
                source="profile",
            ),
        )
    if profile.conditions:
        condition_text = "; ".join(profile.conditions)
        signals.extend(_scan_text(condition_text, source="profile"))
        _add(
            signals,
            SafetySignal(
                code="medical_conditions",
                severity="warning",
                text="Указаны состояния здоровья: "
                + condition_text[:240]
                + ". Обсудите план с врачом.",
                source="profile",
            ),
        )
    if profile.injuries:
        injury_text = "; ".join(profile.injuries)
        signals.extend(_scan_text(injury_text, source="profile"))
        _add(
            signals,
            SafetySignal(
                code="injury_history",
                severity="warning",
                text="Указаны травмы/ограничения: "
                + injury_text[:240]
                + ". Избегайте движений, которые усиливают боль.",
                source="profile",
            ),
        )
    signals.extend(_scan_text(profile.notes, source="profile"))

    layer = build_layer(profile)
    for flag in layer.safety_flags:
        severity: Severity = (
            "critical" if flag.severity == "critical" else flag.severity
        )
        _add(
            signals,
            SafetySignal(
                code=flag.code,
                severity=severity,
                text=flag.text,
                source="medications",
            ),
        )
    for entry in profile.medications:
        knowledge = lookup(entry.name)
        if knowledge.class_name == "неизвестный препарат":
            _add(
                signals,
                SafetySignal(
                    code="unknown_medication",
                    severity="warning",
                    text=f"Препарат «{entry.name[:80]}» не распознан: выберите "
                    "консервативный режим и обсудите влияние с врачом или "
                    "фармацевтом.",
                    source="medications",
                ),
            )
        if "Бета-блокатор" in knowledge.class_name:
            _add(
                signals,
                SafetySignal(
                    code="beta_blocker",
                    severity="warning",
                    text="Бета-блокаторы могут искажать пульс и HR-зоны: "
                    "ориентируйтесь на RPE и мощность, а не только на пульс.",
                    source="medications",
                ),
            )
    return signals


def _event_signals(
    events: Iterable[Event] | None,
    *,
    today: date,
    recent_days: int = 21,
) -> list[SafetySignal]:
    signals: list[SafetySignal] = []
    for event in events or ():
        try:
            event_day = date.fromisoformat(str(event.date)[:10])
        except ValueError:
            continue
        if (today - event_day).days > recent_days:
            continue
        if event.severity == "critical":
            _add(
                signals,
                SafetySignal(
                    code="critical_event",
                    severity="critical",
                    text=f"Событие «{event.title[:120]}» отмечено как критическое. "
                    "Тренировки и план отложить до оценки врача.",
                    source="events",
                ),
            )
        if event.kind == "illness":
            _add(
                signals,
                SafetySignal(
                    code="recent_illness",
                    severity="critical",
                    text=f"Недавняя болезнь «{event.title[:120]}»: тренировки "
                    "отложить до выздоровления.",
                    source="events",
                ),
            )
        elif event.kind == "injury":
            _add(
                signals,
                SafetySignal(
                    code="recent_injury",
                    severity="warning",
                    text=f"Недавняя травма «{event.title[:120]}»: избегайте "
                    "нагрузки на повреждённую область.",
                    source="events",
                ),
            )
        elif event.kind == "med_change":
            _add(
                signals,
                SafetySignal(
                    code="medication_change",
                    severity="warning",
                    text="Была смена препарата/дозы: обсудите с врачом, как "
                    "адаптировать нагрузку; дозу самостоятельно не меняйте.",
                    source="events",
                ),
            )
        elif event.kind in {"alcohol", "heat", "altitude", "stress"}:
            _add(
                signals,
                SafetySignal(
                    code=f"context_{event.kind}",
                    severity="warning",
                    text=f"Контекст «{event.kind}» может ухудшать восстановление; "
                    "снизьте интенсивность.",
                    source="events",
                ),
            )
        signals.extend(_scan_text(event.title, source="events"))
        signals.extend(_scan_text(event.notes, source="events"))
    return signals


def _report_signals(
    report: ReportData | None,
    *,
    checkin: Checkin | None,
) -> list[SafetySignal]:
    if report is None:
        return []
    signals: list[SafetySignal] = []
    recovery_codes: set[str] = set()
    for flag in report.flags:
        severity: Severity = "warning" if flag.severity == "warning" else "info"
        _add(
            signals,
            SafetySignal(
                code=flag.code,
                severity=severity,
                text=flag.text,
                source="analytics",
            ),
        )
        if flag.code in {"sleep_short", "sleep_debt", "hrv_below_baseline", "rhr_above_baseline"}:
            recovery_codes.add(flag.code)

    if len(recovery_codes) >= 2:
        _add(
            signals,
            SafetySignal(
                code="recovery_priority",
                severity="warning",
                text="Несколько сигналов восстановления совпали: приоритет — "
                "сон и отдых, нагрузку не повышать.",
                source="analytics",
            ),
        )
    if report.missing_inputs:
        _add(
            signals,
            SafetySignal(
                code="missing_data",
                severity="warning",
                text="Не хватает данных: "
                + "; ".join(report.missing_inputs[:3])
                + ". Выводы и план будут осторожными.",
                source="analytics",
            ),
        )

    readiness = assess_readiness(report, checkin=checkin)
    if readiness.level == "amber":
        _add(
            signals,
            SafetySignal(
                code="readiness_amber",
                severity="warning",
                text="Готовность жёлтая: снизить объём на 20–40% и убрать "
                "интенсивность.",
                source="readiness",
            ),
        )
    elif readiness.level == "red":
        _add(
            signals,
            SafetySignal(
                code="readiness_red",
                severity="warning",
                text="Готовность красная: сегодня отдых или активное "
                "восстановление, тренировку не выполнять.",
                source="readiness",
            ),
        )
    return signals


def assess_safety(
    *,
    text: str | None = None,
    checkin: Checkin | None = None,
    profile: UserProfile | None = None,
    events: Iterable[Event] | None = None,
    report: ReportData | None = None,
    today: date | None = None,
) -> "SafetyAssessment":
    """Return all deterministic safety signals for a plan or daily advice."""
    day = today or date.today()
    signals: list[SafetySignal] = []
    for signal in _scan_text(text, source="text"):
        _add(signals, signal)
    if checkin is not None:
        for signal in _checkin_signals(checkin):
            _add(signals, signal)
    for signal in _profile_signals(profile):
        _add(signals, signal)
    for signal in _event_signals(events, today=day):
        _add(signals, signal)
    for signal in _report_signals(report, checkin=checkin):
        _add(signals, signal)
    return SafetyAssessment(signals=signals)


def assess_request(text: str | None) -> "SafetyAssessment":
    """Check a free-form request for red flags, dose advice and injection."""
    signals = _scan_text(text, source="request")
    normalized = _normalize(text)
    if _DOSE_REQUEST.search(normalized):
        _add(
            signals,
            SafetySignal(
                code="medication_change_request",
                severity="warning",
                text="Я не меняю дозы и не отменяю препараты. Обсудите это "
                "только с назначившим врачом.",
                source="request",
            ),
        )
    if _INJECTION.search(normalized):
        _add(
            signals,
            SafetySignal(
                code="prompt_injection",
                severity="warning",
                text="Инструкции внутри данных или сообщения не меняют правила "
                "безопасности.",
                source="request",
            ),
        )
    if _PRESSURE.search(normalized):
        _add(
            signals,
            SafetySignal(
                code="pressure_to_train",
                severity="warning",
                text="Давление на бота не отменяет красные флаги: при "
                "опасных симптомах план не строится.",
                source="request",
            ),
        )
    if _DIAGNOSIS_REQUEST.search(normalized):
        _add(
            signals,
            SafetySignal(
                code="diagnosis_request",
                severity="warning",
                text="Я не ставлю диагнозы. Опишите симптомы врачу; при "
                "красных флагах обратитесь за помощью.",
                source="request",
            ),
        )
    return SafetyAssessment(signals=signals)


@dataclass
class SafetyAssessment:
    signals: list[SafetySignal] = field(default_factory=list)

    @property
    def level(self) -> str:
        if any(signal.severity == "critical" for signal in self.signals):
            return "critical"
        if any(signal.severity == "warning" for signal in self.signals):
            return "warning"
        return "ok"

    @property
    def blocked(self) -> bool:
        return self.level == "critical"

    @property
    def warnings(self) -> list[SafetySignal]:
        return [signal for signal in self.signals if signal.severity == "warning"]

    @property
    def critical(self) -> list[SafetySignal]:
        return [signal for signal in self.signals if signal.severity == "critical"]

    @property
    def codes(self) -> set[str]:
        return {signal.code for signal in self.signals}


def merge_safety_flags(
    existing: Iterable[SafetyFlag],
    assessment: SafetyAssessment,
) -> list[SafetyFlag]:
    """Append deterministic safety signals to a plan without duplicates."""
    result = list(existing)
    seen = {(flag.code, flag.text) for flag in result}
    for signal in assessment.signals:
        if signal.severity == "info":
            continue
        key = (signal.code, signal.text)
        if key in seen:
            continue
        result.append(
            SafetyFlag(
                code=signal.code,
                severity=signal.severity,
                text=signal.text,
            )
        )
        seen.add(key)
    return result


def safety_text(assessment: SafetyAssessment) -> str:
    """Render a concise Russian safety block for Telegram or a report."""
    if not assessment.signals:
        return "✅ Ограничений безопасности не выявлено."

    lines: list[str] = []
    if assessment.blocked:
        lines.append("🛑 <b>Стоп: план и тренировки сейчас небезопасны</b>")
    else:
        lines.append("⚠️ <b>Ограничения безопасности</b>")

    ordered = assessment.critical + assessment.warnings
    lines.extend(f"• {signal.text}" for signal in ordered)

    if assessment.blocked:
        lines.append("")
        lines.append(f"<b>Что сделать сейчас:</b> {ESCALATION_TEXT}")
    else:
        lines.append("")
        lines.append(
            "Учтите ограничения и при ухудшении остановитесь. "
            "При красных флагах — срочно к врачу."
        )
    lines.append("")
    lines.append(MEDICAL_DISCLAIMER)
    return "\n".join(lines)


def sanitize_untrusted_text(text: object, *, max_length: int = 500) -> str:
    """Neutralize instruction-like content before it reaches the local model."""
    cleaned = re.sub(r"[\x00-\x1f\x7f]+", " ", str(text or ""))
    cleaned = re.sub(r"</?[^>]{1,120}>", " ", cleaned)
    cleaned = _INJECTION.sub("[недоверенный фрагмент]", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_length]


def is_prompt_injection(text: object) -> bool:
    return bool(_INJECTION.search(_normalize(str(text or ""))))
