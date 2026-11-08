"""Tests for autonomic regulation quadrants (HRV x RHR cross-analysis)."""

from services.garmin.quadrants import (
    QUADRANT_Q1,
    QUADRANT_Q2,
    QUADRANT_Q3,
    QUADRANT_Q4,
    QUADRANT_UNKNOWN,
    assess_autonomic_quadrants,
    classify_single_day,
    compute_baseline_and_swc,
    render_ascii_quadrant_matrix,
)


def test_compute_baseline_and_swc_insufficient_data():
    base, sd, swc = compute_baseline_and_swc([50.0, 52.0], min_days=7)
    assert base == 51.0
    assert sd is None
    assert swc == 5.1  # fallback 10%


def test_compute_baseline_and_swc_sufficient_data():
    vals = [50.0, 52.0, 48.0, 55.0, 49.0, 51.0, 50.0, 53.0]
    base, sd, swc = compute_baseline_and_swc(vals, min_days=7)
    assert base is not None
    assert sd is not None
    assert swc is not None
    assert swc >= 0.5 * sd


def test_classify_single_day_q1():
    # HRV elevated, RHR low
    q = classify_single_day(hrv=65, rhr=48, hrv_base=50, rhr_base=52, hrv_swc=4, rhr_swc=2)
    assert q == QUADRANT_Q1


def test_classify_single_day_q2():
    # HRV low, RHR high
    q = classify_single_day(hrv=38, rhr=60, hrv_base=50, rhr_base=52, hrv_swc=4, rhr_swc=2)
    assert q == QUADRANT_Q2


def test_classify_single_day_q3():
    # HRV low, RHR low
    q = classify_single_day(hrv=38, rhr=47, hrv_base=50, rhr_base=52, hrv_swc=4, rhr_swc=2)
    assert q == QUADRANT_Q3


def test_classify_single_day_q4():
    # HRV high, RHR high
    q = classify_single_day(hrv=65, rhr=58, hrv_base=50, rhr_base=52, hrv_swc=4, rhr_swc=2)
    assert q == QUADRANT_Q4


def test_assess_autonomic_quadrants_empty():
    res = assess_autonomic_quadrants([], [])
    assert res.quadrant == QUADRANT_UNKNOWN
    assert res.readiness_modifier == "green"


def test_assess_autonomic_quadrants_q1_green():
    hrvs = [50.0] * 10 + [62.0]
    rhrs = [52.0] * 10 + [48.0]
    res = assess_autonomic_quadrants(hrvs, rhrs)
    assert res.quadrant == QUADRANT_Q1
    assert res.readiness_modifier == "green"
    assert res.emoji == "🟢"
    assert "вагусный" in res.description.lower() or "восстанов" in res.description.lower()


def test_assess_autonomic_quadrants_q2_streak_escalation():
    # 1 day of Q2 -> amber
    hrvs_1 = [50.0] * 10 + [35.0]
    rhrs_1 = [50.0] * 10 + [58.0]
    res_1 = assess_autonomic_quadrants(hrvs_1, rhrs_1)
    assert res_1.quadrant == QUADRANT_Q2
    assert res_1.streak_days == 1
    assert res_1.readiness_modifier == "amber"

    # 3 days of Q2 -> red (escalated to deload warning)
    hrvs_3 = [50.0] * 10 + [36.0, 35.0, 34.0]
    rhrs_3 = [50.0] * 10 + [57.0, 58.0, 59.0]
    res_3 = assess_autonomic_quadrants(hrvs_3, rhrs_3)
    assert res_3.quadrant == QUADRANT_Q2
    assert res_3.streak_days == 3
    assert res_3.readiness_modifier == "red"
    assert any("3+ дня" in f for f in res_3.flags)


def test_assess_autonomic_quadrants_q3_saturation_with_load():
    hrvs = [50.0] * 10 + [38.0]
    rhrs = [50.0] * 10 + [45.0]
    res = assess_autonomic_quadrants(hrvs, rhrs, acute_load_high=True)
    assert res.quadrant == QUADRANT_Q3
    assert res.readiness_modifier == "amber"
    assert any("сатураци" in f.lower() for f in res.flags)


def test_assess_autonomic_quadrants_q4_illness_risk():
    hrvs = [50.0] * 10 + [65.0]
    rhrs = [50.0] * 10 + [60.0]
    res = assess_autonomic_quadrants(hrvs, rhrs, skin_temp_high=True)
    assert res.quadrant == QUADRANT_Q4
    assert res.readiness_modifier == "red"
    assert any("продромальн" in f.lower() or "температур" in f.lower() for f in res.flags)


def test_render_ascii_quadrant_matrix():
    matrix = render_ascii_quadrant_matrix(QUADRANT_Q1, streak=2)
    assert "Q1" in matrix
    assert "Q2" in matrix
    assert "[2д]" in matrix
