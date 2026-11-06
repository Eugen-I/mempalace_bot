"""Curated medication knowledge base for conservative training advice.

This module never suggests doses, stopping or changing medication.  It only
maps a medication name to class-level precautions and red flags, and points the
user to their prescriber.  Unknown medications produce a conservative default.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import MedicationEntry, SafetyFlag, UserProfile


@dataclass(frozen=True)
class MedicationKnowledge:
    class_name: str
    aliases: tuple[str, ...]
    precautions: tuple[str, ...]
    red_flags: tuple[str, ...] = ()
    citations: tuple[str, ...] = ()
    intensity_caution: bool = False
    heat_caution: bool = False
    orthostatic_caution: bool = False
    contact_caution: bool = False
    hypoglycemia_caution: bool = False


KB: tuple[MedicationKnowledge, ...] = (
    MedicationKnowledge(
        class_name="NaSSA (миртазапин)",
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
        orthostatic_caution=True,
    ),
    MedicationKnowledge(
        class_name="SNRI (венлафаксин)",
        aliases=("венлафаксин", "venlafaxine", "велбутрин", "effexor"),
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
        intensity_caution=True,
        heat_caution=True,
    ),
    MedicationKnowledge(
        class_name="SSRI",
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
        heat_caution=True,
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
        ),
        precautions=(
            "Пульс и HR-зоны могут быть ненадёжны: ориентируйтесь на RPE и "
            "мощность, а не только на пульс.",
            "Возможны головокружение и усталость; не меняйте дозу сами.",
        ),
        red_flags=("обморок", "выраженная брадикардия с головокружением"),
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
        hypoglycemia_caution=True,
    ),
)

_UNKNOWN = MedicationKnowledge(
    class_name="неизвестный препарат",
    aliases=(),
    precautions=(
        "Класс препарата не распознан: выберите консервативный режим и "
        "обсудите влияние на тренировки с врачом или фармацевтом.",
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
    """Enrich all medications and aggregate training precautions."""
    layer = MedicationLayer()
    citations: set[str] = set()
    for raw in profile.medications:
        entry = enrich(raw)
        layer.entries.append(entry)
        knowledge = lookup(entry.name)
        citations.update(knowledge.citations)
        layer.intensity_caution = layer.intensity_caution or knowledge.intensity_caution
        layer.heat_caution = layer.heat_caution or knowledge.heat_caution
        layer.orthostatic_caution = (
            layer.orthostatic_caution or knowledge.orthostatic_caution
        )
        layer.contact_caution = layer.contact_caution or knowledge.contact_caution
        layer.hypoglycemia_caution = (
            layer.hypoglycemia_caution or knowledge.hypoglycemia_caution
        )
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
    serotonergic = any(
        token in name
        for name in names
        for token in ("миртазапин", "mirtazapine", "венлафаксин", "venlafaxine")
    )
    if len(names) >= 2 and serotonergic:
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
