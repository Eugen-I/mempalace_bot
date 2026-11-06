"""Curated evidence registry for Garmin coaching text.

The local model may only cite IDs from this registry.  It cannot browse and it
must not invent references.  E9/E10 are medication references, not dosing
advice; E11/E12 are implementation references, not clinical evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Evidence:
    id: str
    year: str
    type: str
    title: str
    source: str
    url: str
    key_finding: str
    use_for: tuple[str, ...]
    caveats: tuple[str, ...] = ()


EVIDENCE: dict[str, Evidence] = {
    "E1": Evidence(
        id="E1",
        year="2024",
        type="systematic_review_network_meta_analysis",
        title="Effect of exercise for depression: systematic review and network meta-analysis",
        source="Noetel M, et al. BMJ 2024;384:e075847",
        url="https://www.bmj.com/content/384/bmj-2023-075847",
        key_finding=(
            "Exercise is effective for depression; walking/running, yoga and "
            "resistance training show meaningful effects, with dose/intensity "
            "mattering."
        ),
        use_for=("exercise modality", "depression context", "activity"),
        caveats=("heterogeneity", "not a substitute for treatment"),
    ),
    "E2": Evidence(
        id="E2",
        year="2025",
        type="systematic_review_meta_analysis",
        title="Resistance training for depression: systematic review and meta-analysis",
        source="Chang Y, et al. Front Psychol 2025;16:1655855",
        url="https://doi.org/10.3389/fpsyg.2025.1655855",
        key_finding=(
            "Resistance training reduces depressive symptoms in adults, with "
            "high heterogeneity; moderate intensity is a reasonable default."
        ),
        use_for=("strength training", "depression context"),
        caveats=("high heterogeneity", "not a substitute for treatment"),
    ),
    "E3": Evidence(
        id="E3",
        year="2025",
        type="systematic_review_meta_analysis",
        title="Effects of sleep deprivation on sports performance and perceived exertion",
        source="Kong Y, et al. Front Physiol 2025;16:1544286",
        url="https://doi.org/10.3389/fphys.2025.1544286",
        key_finding=(
            "Sleep deprivation impairs aerobic/anaerobic performance, explosive "
            "strength, speed and skill control, and raises perceived exertion."
        ),
        use_for=("sleep", "intensity", "recovery"),
        caveats=("acute sleep deprivation differs from chronic restriction",),
    ),
    "E4": Evidence(
        id="E4",
        year="2025",
        type="narrative_review",
        title="Monitoring training adaptation and recovery with HRV via mobile devices",
        source="Esco MR, et al. Sensors 2026;26(1):3 (online 2025)",
        url="https://doi.org/10.3390/s26010003",
        key_finding=(
            "HRV is most useful with near-daily measurements and individual "
            "baselines; use weekly averages/CV rather than a single night."
        ),
        use_for=("HRV", "recovery", "readiness"),
        caveats=("measurement artefacts", "individual baseline required"),
    ),
    "E5": Evidence(
        id="E5",
        year="2025",
        type="systematic_review_meta_analysis",
        title="Acute to chronic workload ratio (ACWR) for predicting sports injury risk",
        source="Qin W, et al. BMC Sports Sci Med Rehabil 2025",
        url="https://doi.org/10.1186/s13102-025-01332-x",
        key_finding=(
            "ACWR has a modest association with injury, but it is not an "
            "accurate standalone predictor."
        ),
        use_for=("load", "injury context"),
        caveats=("not a prediction tool", "combine with wellness and pain"),
    ),
    "E6": Evidence(
        id="E6",
        year="2024",
        type="systematic_review",
        title="ACWR for injury prevention among professional soccer players",
        source="Michailidis Y, et al. Applied Sciences 2024;14(11):4449",
        url="https://doi.org/10.3390/app14114449",
        key_finding=(
            "The ACWR-injury relationship remains inconclusive and thresholds "
            "are not established."
        ),
        use_for=("load", "injury context"),
        caveats=("professional soccer population", "inconclusive"),
    ),
    "E7": Evidence(
        id="E7",
        year="2025",
        type="scoping_review",
        title="Evaluation strategies for large language model-based AI coaches",
        source="Lai X, et al. J Med Internet Res 2025;27:e79217",
        url="https://doi.org/10.2196/79217",
        key_finding=(
            "LLM coaching needs systematic evaluation, not just plausible-looking "
            "answers."
        ),
        use_for=("AI safety", "evaluation"),
        caveats=("implementation reference",),
    ),
    "E8": Evidence(
        id="E8",
        year="2026",
        type="expert_evaluation",
        title="AI-generated exercise prescriptions for at-risk populations",
        source="Choi M, et al. J Clin Med 2026;15(6):2457",
        url="https://doi.org/10.3390/jcm15062457",
        key_finding=(
            "AI plans can be structurally complete but experts disagree; "
            "guideline-based prompting and expert review improve safety."
        ),
        use_for=("AI safety", "plan validation"),
        caveats=("expert review required", "not a substitute for clinical care"),
    ),
    "E9": Evidence(
        id="E9",
        year="2024",
        type="medication_reference",
        title="Venlafaxine",
        source="StatPearls 2024",
        url="https://www.ncbi.nlm.nih.gov/books/NBK535363/",
        key_finding=(
            "Venlafaxine can increase blood pressure/heart rate; caution with "
            "cardiac disease, hyperthyroidism, recent MI, hyponatremia and "
            "withdrawal."
        ),
        use_for=("medication precaution", "blood pressure", "heart rate"),
        caveats=("not dosing advice", "discuss with prescriber"),
    ),
    "E10": Evidence(
        id="E10",
        year="2024",
        type="medication_reference",
        title="Mirtazapine",
        source="StatPearls 2024",
        url="https://www.ncbi.nlm.nih.gov/books/NBK519059/",
        key_finding=(
            "Mirtazapine can cause sedation, increased appetite/weight gain, "
            "orthostatic hypotension and dry mouth."
        ),
        use_for=("medication precaution", "appetite", "orthostasis", "sleep"),
        caveats=("not dosing advice", "discuss with prescriber"),
    ),
    "E11": Evidence(
        id="E11",
        year="2026",
        type="implementation_reference",
        title="Section 11: deterministic AI coaching protocol",
        source="CrankAddict/section-11 (MIT)",
        url="https://github.com/CrankAddict/section-11",
        key_finding=(
            "Dossier, readiness gates, validation and audit make coaching more "
            "deterministic and inspectable."
        ),
        use_for=("architecture", "audit"),
        caveats=("implementation reference", "not clinical evidence"),
    ),
    "E12": Evidence(
        id="E12",
        year="2026",
        type="implementation_reference",
        title="Behind the guardrails: evaluating generative AI at Oura",
        source="Oura, 2026",
        url="https://www.oura.com/blog/",
        key_finding=(
            "Scope, boundaries, escalation, data-use rules, tone and clinical "
            "grounding need explicit evaluation."
        ),
        use_for=("AI safety", "guardrails"),
        caveats=("implementation reference", "not clinical evidence"),
    ),
}

CITATION_IDS = frozenset(EVIDENCE)


def get_evidence(citation_id: str) -> Evidence:
    return EVIDENCE[citation_id]


def citations_for_flags(flag_codes: Iterable[str]) -> list[str]:
    """Pick a small, relevant citation set for deterministic fallback text."""
    codes = set(flag_codes)
    citations: list[str] = []
    if codes & {"sleep_short", "sleep_debt", "stress_high"}:
        citations.append("E3")
    if codes & {"hrv_below_baseline", "rhr_above_baseline"}:
        citations.append("E4")
    if codes & {"no_activities", "weight_change"}:
        citations.extend(["E1", "E2"])
    if not citations:
        citations.extend(["E3", "E4"])
    return list(dict.fromkeys(citations))


def format_citation(citation_id: str) -> str:
    item = EVIDENCE[citation_id]
    return f"[{item.id}] {item.source}. {item.title}. {item.url}"


def format_citations(citation_ids: Iterable[str]) -> list[str]:
    return [format_citation(cid) for cid in dict.fromkeys(citation_ids) if cid in EVIDENCE]
