"""Curated medication knowledge base for conservative training advice.

This module never suggests doses, stopping or changing medication.  It only
maps a medication name to class-level precautions and red flags, and points the
user to their prescriber.  Unknown medications produce a conservative default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .models import MedicationEntry, SafetyFlag, UserProfile


@dataclass(frozen=True)
class MedicationKnowledge:
    class_name: str
    aliases: tuple[str, ...]
    precautions: tuple[str, ...]
    red_flags: tuple[str, ...] = ()
    citations: tuple[str, ...] = ()
    sleep_effects: tuple[str, ...] = ()
    emotional_effects: tuple[str, ...] = ()
    intensity_caution: bool = False
    heat_caution: bool = False
    orthostatic_caution: bool = False
    contact_caution: bool = False
    hypoglycemia_caution: bool = False
    serotonergic: bool = False


KB: tuple[MedicationKnowledge, ...] = (
    MedicationKnowledge(
        class_name="NaSSA (норадренергический и серотонинергический антидепрессант)",
        aliases=("миртазапин", "mirtazapine", "ремерон", "remaron", "mirataz"),
        precautions=(
            "Возможна седация и снижение концентрации — начинайте с RPE 6 и "
            "избегайте резких движений.",
            "Возможна ортостатическая гипотензия: вставайте медленно, "
            "контролируйте головокружение.",
            "Может повышать аппетит и вес; тренировки не заменяют работу с "
            "питанием и сном.",
        ),
        red_flags=(
            "выраженное головокружение или обморок",
            "спутанность, тремор, лихорадка, мышечная ригидность",
        ),
        citations=("E10",),
        sleep_effects=(
            "Увеличивает общую длительность и глубину сна, но может вызывать "
            "утреннюю сонливость (инерцию сна) и яркие сновидения.",
        ),
        emotional_effects=(
            "Снижает вечернюю тревожность и гипервозбуждение; в первые недели "
            "возможна дневная вялость при субъективно низкой оценке энергии.",
        ),
        orthostatic_caution=True,
        serotonergic=True,
    ),
    MedicationKnowledge(
        class_name="SNRI (СИОЗСиН)",
        aliases=(
            "венлафаксин",
            "venlafaxine",
            "велбутрин",
            "effexor",
            "дулоксетин",
            "duloxetine",
            "милнаципран",
            "milnacipran",
        ),
        precautions=(
            "Может повышать пульс и давление — контролируйте самочувствие, "
            "особенно в жару и при интенсивных интервалах.",
            "Возможна гипонатриемия: на длинных сессиях используйте воду с "
            "электролитами, а не только воду.",
            "Не прекращайте приём резко; вопросы дозы — только к врачу.",
        ),
        red_flags=(
            "боль в груди или выраженное сердцебиение с головокружением",
            "спутанность, судороги, выраженная слабость",
            "спутанность, ажитация, тремор, лихорадка, потливость, тахикардия",
        ),
        citations=("E9",),
        sleep_effects=(
            "Может подавлять фазу REM-сна, делать сон более поверхностным или "
            "вызывать ночную потливость и ранние пробуждения.",
        ),
        emotional_effects=(
            "Стабилизирует эмоциональный фон и тонус, но из-за норадренергического "
            "эффекта может фоново повышать пульс покоя (RHR), индекс стресса Garmin "
            "и умеренно снижать базовую ВСР (HRV) без реального переутомления.",
        ),
        intensity_caution=True,
        heat_caution=True,
        serotonergic=True,
    ),
    MedicationKnowledge(
        class_name="SSRI (СИОЗС)",
        aliases=(
            "сертралин",
            "sertraline",
            "флуоксетин",
            "fluoxetine",
            "эсциталопрам",
            "escitalopram",
            "пароксетин",
            "paroxetine",
            "циталопрам",
            "citalopram",
            "флувоксамин",
            "fluvoxamine",
        ),
        precautions=(
            "Возможна гипонатриемия и повышенная потливость; следите за "
            "гидратацией и электролитами.",
            "Не меняйте дозу самостоятельно.",
        ),
        red_flags=(
            "спутанность, ажитация, тремор, лихорадка, мышечная ригидность",
            "выраженная слабость или судороги",
        ),
        citations=("E9",),
        sleep_effects=(
            "Может смещать латентность REM-сна, вызывать яркие сны или "
            "фрагментацию сна при вечернем приёме.",
        ),
        emotional_effects=(
            "Сглаживает острые эмоциональные реакции и тревожность; возможна "
            "небольшая коррекция базовой ВСР.",
        ),
        heat_caution=True,
        serotonergic=True,
    ),
    MedicationKnowledge(
        class_name="Бета-блокаторы",
        aliases=(
            "бисопролол",
            "bisoprolol",
            "метопролол",
            "metoprolol",
            "атенолол",
            "atenolol",
            "небиволол",
            "nebivolol",
            "пропранолол",
            "propranolol",
        ),
        precautions=(
            "Пульс и HR-зоны могут быть ненадёжны: ориентируйтесь на RPE и "
            "мощность, а не только на пульс.",
            "Возможны головокружение и усталость; не меняйте дозу сами.",
        ),
        red_flags=("обморок", "выраженная брадикардия с головокружением"),
        sleep_effects=(
            "Могут снижать ночную выработку мелатонина и вызывать ночные "
            "пробуждения или яркие сны.",
        ),
        emotional_effects=(
            "Снижают вегетативные проявления тревоги (тахикардию, тремор) и "
            "искусственно занижают пульс покоя и стресс-индекс Garmin.",
        ),
        intensity_caution=True,
        orthostatic_caution=True,
    ),
    MedicationKnowledge(
        class_name="Диуретики",
        aliases=(
            "фуросемид",
            "furosemide",
            "гидрохлоротиазид",
            "hydrochlorothiazide",
            "индапамид",
            "indapamide",
            "спиронолактон",
            "spironolactone",
        ),
        precautions=(
            "Возможна дегидратация и электролитные нарушения; пейте по жажде, "
            "добавляйте электролиты на длинных сессиях.",
            "Избегайте экстремальных интервалов в жару.",
        ),
        red_flags=("судороги", "выраженная слабость", "обморок"),
        sleep_effects=(
            "При вечернем приёме могут нарушать непрерывность сна из-за ночных "
            "пробуждений.",
        ),
        emotional_effects=(
            "При дефиците электролитов возможны ощущение упадка сил и "
            "раздражительность.",
        ),
        heat_caution=True,
        intensity_caution=True,
    ),
    MedicationKnowledge(
        class_name="Метформин",
        aliases=("метформин", "metformin"),
        precautions=(
            "Следите за признаками гипогликемии при комбинации с другими "
            "сахароснижающими препаратами; носите быстрые углеводы.",
        ),
        red_flags=("спутанность", "выраженная слабость", "обморок"),
        sleep_effects=("Прямого седативного эффекта нет; важна стабильность гликемии ночью.",),
        emotional_effects=("Колебания сахара в крови могут сказываться на субъективной энергии.",),
    ),
    MedicationKnowledge(
        class_name="НПВС",
        aliases=(
            "ибупрофен",
            "ibuprofen",
            "напроксен",
            "naproxen",
            "диклофенак",
            "diclofenac",
            "аспирин",
            "aspirin",
        ),
        precautions=(
            "НПВС могут маскировать боль и влиять на почки/ЖКТ; не используйте "
            "их, чтобы «дотерпеть» тренировку.",
        ),
        red_flags=("чёрный стул", "необычные синяки", "сильная боль в животе"),
        sleep_effects=(
            "Уменьшают ночной дискомфорт от боли, но могут слегка снижать "
            "выработку мелатонина.",
        ),
        emotional_effects=(
            "Могут маскировать физическое утомление и болевой сигнал при оценке "
            "готовности к нагрузке.",
        ),
    ),
    MedicationKnowledge(
        class_name="Фторхинолоны",
        aliases=(
            "ципрофлоксацин",
            "ciprofloxacin",
            "левофлоксацин",
            "levofloxacin",
            "моксифлоксацин",
            "moxifloxacin",
        ),
        precautions=(
            "Повышенный риск тендинопатии/разрыва сухожилий: избегайте "
            "рывковых и ударных нагрузок, при боли в сухожилии — стоп.",
        ),
        red_flags=("острая боль в сухожилии", "отёк или щелчок в сухожилии"),
        sleep_effects=("Могут вызывать бессонницу и поверхностный сон.",),
        emotional_effects=("Возможны повышенная тревожность и возбудимость ЦНС.",),
        intensity_caution=True,
    ),
    MedicationKnowledge(
        class_name="Антикоагулянты/антиагреганты",
        aliases=(
            "варфарин",
            "warfarin",
            "апиксабан",
            "apixaban",
            "ривароксабан",
            "rivaroxaban",
            "дабигатран",
            "dabigatran",
            "эдоксабан",
            "edoxaban",
            "клопидогрел",
            "clopidogrel",
            "тикгрелор",
            "ticagrelor",
            "прасугрел",
            "prasugrel",
        ),
        precautions=(
            "Повышен риск кровотечения и синяков: избегайте контактных видов "
            "спорта, падений и ударных нагрузок.",
            "При травме головы, кровотечении или необычных синяках — "
            "остановитесь и обратитесь к врачу.",
        ),
        red_flags=(
            "кровотечение",
            "чёрный стул",
            "необычные синяки",
            "сильная головная боль после удара",
        ),
        contact_caution=True,
    ),
    MedicationKnowledge(
        class_name="Сульфонилурея/инсулин",
        aliases=(
            "гликлазид",
            "gliclazide",
            "глимепирид",
            "glimepiride",
            "глибенкламид",
            "glibenclamide",
            "глипизид",
            "glipizide",
            "инсулин",
            "insulin",
        ),
        precautions=(
            "Возможна гипогликемия: носите быстрые углеводы, не тренируйтесь "
            "натощак и контролируйте глюкозу по рекомендации врача.",
            "При потливости, дрожи, спутанности или выраженной слабости — "
            "остановитесь и примите быстрые углеводы, если это согласовано "
            "с врачом.",
        ),
        red_flags=("спутанность", "выраженная слабость", "обморок", "судороги"),
        sleep_effects=(
            "Ночная гипогликемия после вечерней тренировки может вызывать "
            "скачки ЧСС, потливость и падение качества сна.",
        ),
        emotional_effects=(
            "Снижение глюкозы может сопровождаться резкой тревогой, тремором "
            "и упадком сил.",
        ),
        hypoglycemia_caution=True,
    ),
    MedicationKnowledge(
        class_name="Мелатонин / хронобиотики",
        aliases=("мелатонин", "melatonin", "мелаксен", "циркадин", "circadin"),
        precautions=(
            "Принимайте в одно и то же время вечером; при утренней сонливости "
            "начинайте тренировку с более длинной разминки.",
        ),
        sleep_effects=(
            "Ускоряет засыпание и стабилизирует середину сна (sleep midpoint), "
            "при избыточной дозе возможны яркие сны и утренняя вялость.",
        ),
        emotional_effects=(
            "Снижает вечернее возбуждение и помогает выровнять циркадный ритм "
            "настроения и бодрости.",
        ),
    ),
    MedicationKnowledge(
        class_name="Магний / нутрицевтики сна и нервной системы",
        aliases=(
            "магний",
            "magnesium",
            "глицинат",
            "теанин",
            "l-theanine",
            "глицин",
            "glycine",
        ),
        precautions=(
            "Учитывайте индивидуальную переносимость ЖКТ перед длительными "
            "тренировками.",
        ),
        sleep_effects=(
            "Способствует расслаблению мышц и парасимпатическому восстановлению "
            "во сне.",
        ),
        emotional_effects=(
            "Мягко снижает субъективное напряжение и вегетативный отклик на стресс.",
        ),
    ),
    MedicationKnowledge(
        class_name="Седативные антигистаминные / анксиолитики",
        aliases=(
            "доксиламин",
            "doxylamine",
            "донормил",
            "гидроксизин",
            "hydroxyzine",
            "атаракс",
            "цетиризин",
            "cetirizine",
            "супрастин",
        ),
        precautions=(
            "Возможна утренняя седация, сухость слизистых и снижение скорости "
            "реакции — избегайте технически сложных упражнений при сонливости.",
        ),
        sleep_effects=(
            "Сокращает время засыпания, но может снижать долю REM-сна и "
            "вызывать остаточную сонливость утром.",
        ),
        emotional_effects=(
            "Снижает ситуативную тревогу, но утром может ощущаться как снижение "
            "тонуса и мотивации.",
        ),
        orthostatic_caution=True,
        heat_caution=True,
    ),
    MedicationKnowledge(
        class_name="Бензодиазепины / Z-гипнотики",
        aliases=(
            "золпидем",
            "zolpidem",
            "зопиклон",
            "zopiclone",
            "залеплон",
            "феназепам",
            "алпразолам",
            "alprazolam",
            "диазепам",
            "diazepam",
            "клоназепам",
            "clonazepam",
        ),
        precautions=(
            "Возможны нарушение координации, головокружение и снижение реакции — "
            "исключите работу со свободными весами на пределе и езду по трафику "
            "при остаточной сонливости.",
        ),
        red_flags=("выраженное головокружение или обморок", "спутанность"),
        sleep_effects=(
            "Увеличивают общую длительность сна, но могут уменьшать долю "
            "глубокого медленноволнового сна.",
        ),
        emotional_effects=(
            "Подавляют острую тревогу и вегетативный стресс, но могут вызывать "
            "дневную заторможенность.",
        ),
        orthostatic_caution=True,
        intensity_caution=True,
    ),
)

_UNKNOWN = MedicationKnowledge(
    class_name="неизвестный препарат",
    aliases=(),
    precautions=(
        "Класс препарата не распознан: выберите консервативный режим и "
        "обсудите влияние на тренировки с врачом или фармацевтом.",
    ),
    sleep_effects=(
        "Учитывайте возможное влияние препарата на глубину сна, пульс покоя, "
        "ВСР и утреннюю бодрость (обсудите с лечащим врачом).",
    ),
    emotional_effects=(
        "Учитывайте возможную связь приёма препарата с динамикой настроения, "
        "субъективной энергии и вегетативного стресса.",
    ),
)

_ALIASES: dict[str, MedicationKnowledge] = {
    alias: item for item in KB for alias in item.aliases
}


def lookup(name: str) -> MedicationKnowledge:
    normalized = (name or "").strip().lower()
    if not normalized:
        return _UNKNOWN
    for alias, item in _ALIASES.items():
        if alias in normalized:
            return item
    return _UNKNOWN


def enrich(entry: MedicationEntry) -> MedicationEntry:
    """Fill class/precautions/red flags from the local knowledge base."""
    knowledge = lookup(entry.name)
    return entry.model_copy(
        update={
            "class_name": knowledge.class_name,
            "precautions": list(knowledge.precautions),
            "red_flags": list(knowledge.red_flags),
        }
    )


@dataclass
class MedicationLayer:
    entries: list[MedicationEntry] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    safety_flags: list[SafetyFlag] = field(default_factory=list)
    sleep_effects: list[str] = field(default_factory=list)
    emotional_effects: list[str] = field(default_factory=list)
    intensity_caution: bool = False
    heat_caution: bool = False
    orthostatic_caution: bool = False
    contact_caution: bool = False
    hypoglycemia_caution: bool = False

    @property
    def summary(self) -> str:
        if not self.entries:
            return "Препараты не указаны."
        return ", ".join(
            f"{entry.name} ({entry.class_name or 'класс не распознан'})"
            for entry in self.entries
        )


def build_layer(profile: UserProfile) -> MedicationLayer:
    """Enrich all medications and aggregate training, sleep and emotional effects."""
    layer = MedicationLayer()
    citations: set[str] = set()
    serotonergic_count = 0
    for raw in profile.medications:
        entry = enrich(raw)
        layer.entries.append(entry)
        knowledge = lookup(entry.name)
        citations.update(knowledge.citations)
        if knowledge.serotonergic:
            serotonergic_count += 1
        layer.intensity_caution = layer.intensity_caution or knowledge.intensity_caution
        layer.heat_caution = layer.heat_caution or knowledge.heat_caution
        layer.orthostatic_caution = (
            layer.orthostatic_caution or knowledge.orthostatic_caution
        )
        layer.contact_caution = layer.contact_caution or knowledge.contact_caution
        layer.hypoglycemia_caution = (
            layer.hypoglycemia_caution or knowledge.hypoglycemia_caution
        )
        for effect in knowledge.sleep_effects:
            text = f"{entry.name}: {effect}"
            if text not in layer.sleep_effects:
                layer.sleep_effects.append(text)
        for effect in knowledge.emotional_effects:
            text = f"{entry.name}: {effect}"
            if text not in layer.emotional_effects:
                layer.emotional_effects.append(text)
        for precaution in entry.precautions:
            layer.safety_flags.append(
                SafetyFlag(
                    code="medication_precaution",
                    severity="info",
                    text=f"{entry.name}: {precaution}",
                )
            )
    layer.citations = sorted(citations)

    names = {entry.name.lower() for entry in profile.medications}
    if len(names) >= 2 and serotonergic_count >= 1:
        layer.safety_flags.append(
            SafetyFlag(
                code="serotonergic_combination",
                severity="warning",
                text=(
                    "Комбинация серотонинергических препаратов: при новых "
                    "симптомах (ажитация, тремор, лихорадка, мышечная "
                    "ригидность, потливость, тахикардия) остановитесь и "
                    "срочно обратитесь к врачу."
                ),
            )
        )
    if layer.intensity_caution:
        layer.safety_flags.append(
            SafetyFlag(
                code="intensity_caution",
                severity="warning",
                text=(
                    "Из-за препаратов начните с RPE 5–6, без максимальных "
                    "интервалов; при необычном пульсе/давлении — стоп."
                ),
            )
        )
    if layer.heat_caution:
        layer.safety_flags.append(
            SafetyFlag(
                code="heat_caution",
                severity="info",
                text=(
                    "В жару возможны гипонатриемия и ухудшение самочувствия: "
                    "электролиты, меньше интенсивности, тренировки в прохладе."
                ),
            )
        )
    if layer.contact_caution:
        layer.safety_flags.append(
            SafetyFlag(
                code="contact_caution",
                severity="warning",
                text=(
                    "Из-за препаратов, влияющих на свёртываемость, избегайте "
                    "контактных видов спорта и падений; при травме или "
                    "кровотечении — к врачу."
                ),
            )
        )
    if layer.hypoglycemia_caution:
        layer.safety_flags.append(
            SafetyFlag(
                code="hypoglycemia_caution",
                severity="warning",
                text=(
                    "Возможна гипогликемия: носите быстрые углеводы, не "
                    "тренируйтесь натощак и обсудите контроль глюкозы с врачом."
                ),
            )
        )
    return layer


def doctor_questions(layer: MedicationLayer) -> list[str]:
    """Questions for the prescriber; never advice or dose changes."""
    questions = [
        "Есть ли ограничения по интенсивности, жаре и гидратации?",
        "Нужно ли контролировать давление, пульс, натрий или глюкозу?",
        "Как менять тренировки при изменении дозы препарата?",
        "Есть ли ограничения по силовым или ударным нагрузкам?",
    ]
    if layer.entries:
        questions.insert(
            0,
            "Влияет ли текущая комбинация препаратов на пульс, давление, "
            "сон, аппетит или баланс?",
        )
    return questions


def medication_ai_context(
    medications: Iterable[str | MedicationEntry],
) -> dict[str, Any]:
    """Build class-level pharmacological context for sleep, emotion and training AI analysis."""
    classes: list[str] = []
    sleep_effects: list[str] = []
    emotional_effects: list[str] = []
    precautions: list[str] = []
    citations: set[str] = set()
    count = 0
    for item in medications:
        name = item.name if isinstance(item, MedicationEntry) else str(item or "")
        name = name.strip()
        if not name:
            continue
        count += 1
        knowledge = lookup(name)
        if knowledge.class_name not in classes:
            classes.append(knowledge.class_name)
        citations.update(knowledge.citations)
        for effect in knowledge.sleep_effects:
            if effect not in sleep_effects:
                sleep_effects.append(effect)
        for effect in knowledge.emotional_effects:
            if effect not in emotional_effects:
                emotional_effects.append(effect)
        for precaution in knowledge.precautions:
            if precaution not in precautions:
                precautions.append(precaution)
    return {
        "has_medications": count > 0,
        "count": count,
        "classes": classes,
        "sleep_effects": sleep_effects,
        "emotional_effects": emotional_effects,
        "training_precautions": precautions,
        "citations": sorted(citations),
    }
