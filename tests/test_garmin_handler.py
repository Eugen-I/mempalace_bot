"""Tests for the Garmin Telegram UI: plan PDF, weekly review, doctor sheet."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramBadRequest
from cryptography.fernet import Fernet

from handlers import garmin
from services.garmin.db import init_db
from services.garmin.models import Checkin, MedicationEntry, UserProfile
from services.garmin.plan_engine import build_skeleton
from services.garmin.plan_review import (
    PlanReview,
    get_review,
    save_review,
)
from services.garmin.plan_store import latest_plan, save_plan
from services.garmin.profile_store import (
    load_profile,
    save_checkin,
    save_profile,
)
from services.garmin.repository import upsert_daily
from services.garmin.status import DataStatus

UID = 4242


class FakeStatusMessage:
    def __init__(self, owner: "FakeMessage"):
        self.owner = owner
        self.edits: list[tuple] = []
        self.deleted = 0

    async def edit_text(self, text=None, **kwargs):
        self.edits.append((text, kwargs))
        self.owner.status_edits.append((text, kwargs))

    async def delete(self):
        self.deleted += 1
        self.owner.status_deleted += 1


class FakeMessage:
    def __init__(self, uid: int = UID, text: str = ""):
        self.from_user = SimpleNamespace(id=uid)
        self.text = text
        self.message_id = 1
        self.bot = SimpleNamespace()
        self.document = None
        self.answers: list[tuple] = []
        self.edits: list[tuple] = []
        self.documents: list[tuple] = []
        self.status_edits: list[tuple] = []
        self.status_deleted = 0

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))
        return FakeStatusMessage(self)

    async def edit_text(self, text=None, **kwargs):
        self.edits.append((text, kwargs))

    async def answer_document(self, document, caption=None, **kwargs):
        self.documents.append((document, caption, kwargs))

    async def delete(self):
        self.status_deleted += 1


class FakeCb:
    def __init__(self, uid: int = UID, data: str = ""):
        self.from_user = SimpleNamespace(id=uid)
        self.data = data
        self.message = FakeMessage(uid)
        self.answered: list[tuple] = []

    async def answer(self, text=None, show_alert=None):
        self.answered.append((text, show_alert))


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {UID})
    monkeypatch.setenv("GARMIN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    directories = {
        "data_dir": tmp_path,
        "import_dir": tmp_path / "import",
        "report_dir": tmp_path / "reports",
        "raw_dir": tmp_path / "raw",
        "charts_dir": tmp_path / "charts",
        "tmp_dir": tmp_path / "tmp",
        "quarantine_dir": tmp_path / "quarantine",
    }
    for path in directories.values():
        Path(path).mkdir(parents=True, exist_ok=True)
    cfg = SimpleNamespace(
        db_path=tmp_path / "garmin.sqlite",
        ai_model="test-model",
        ai_timeout=5.0,
        ai_fallback_model="fallback",
        ai_fallback_timeout=3.0,
        ai_enabled=False,
        plan_horizon_weeks=6,
        retention_days=365,
        online_enabled=False,
        max_sync_days=7,
        request_delay=2.0,
        chart_dpi=80,
        pdf_max_mb=45,
        sleep_target_h=7.5,
        **directories,
    )
    monkeypatch.setattr(garmin, "_cfg", lambda: cfg)
    garmin.garmin_profile_draft.clear()
    garmin.garmin_text_state.clear()
    garmin.garmin_last_plan.clear()
    return cfg


def _status(ready: bool = True) -> DataStatus:
    return DataStatus(
        days=30,
        sleep_days=30,
        hrv_days=30,
        rhr_days=30,
        activities=5,
        activity_days=5,
        has_profile=True,
        ready_for_plan=ready,
        missing=[] if ready else ["HRV: 2/14 дней"],
    )


def _profile(**kwargs) -> UserProfile:
    return UserProfile(**kwargs)


def _seed_profile(cfg, profile: UserProfile | None = None, uid: int = UID):
    conn = init_db(cfg.db_path)
    try:
        return save_profile(conn, uid, profile or _profile())
    finally:
        conn.close()


def _seed_plan(cfg, uid: int = UID, start: date | None = None):
    conn = init_db(cfg.db_path)
    try:
        stored = load_profile(conn, uid)
        plan = build_skeleton(
            stored.profile,
            _status(),
            start_date=start or date.today(),
        )
        save_plan(
            conn,
            uid,
            plan,
            profile_version=stored.version,
            validation_errors=[],
        )
        return plan
    finally:
        conn.close()


def _save_review(cfg, plan, *, decision: str = "reduce", uid: int = UID) -> int:
    conn = init_db(cfg.db_path)
    try:
        review = PlanReview(
            plan_id=plan.plan_id,
            user_id=uid,
            week_index=1,
            review_date=date.today().isoformat(),
            readiness="amber",
            decision=decision,
            changes=[{"action": "reduce_volume", "percent": 30}],
            rationale="тест",
            metrics={"adherence_pct": 50},
        )
        return save_review(conn, uid, review)
    finally:
        conn.close()


def _buttons(markup) -> list:
    return [button for row in markup.inline_keyboard for button in row]


def _callback_ids(markup) -> set[str]:
    return {
        button.callback_data
        for button in _buttons(markup)
        if button.callback_data is not None
    }


# ---------------------------------------------------------------------------
# plan PDF


@pytest.mark.asyncio
async def test_cb_plan_pdf_sends_document(env, monkeypatch):
    _seed_profile(env)
    plan = _seed_plan(env)
    captured: dict = {}

    def fake_build(plan_arg, profile_arg, output, **kwargs):
        captured["plan"] = plan_arg
        captured["profile"] = profile_arg
        captured["checkins"] = kwargs.get("checkins")
        captured["events"] = kwargs.get("events")
        path = Path(output)
        path.write_bytes(b"%PDF-1.4 fake")
        captured["output"] = path
        return path

    monkeypatch.setattr(garmin, "build_plan_pdf", fake_build)
    cb = FakeCb(data="garmin:plan:pdf")

    await garmin.cb_plan_pdf(cb)

    assert cb.answered[0][0] == "Собираю PDF..."
    assert captured["plan"].plan_id == plan.plan_id
    assert captured["output"].is_file()
    assert cb.message.status_deleted == 1
    assert cb.message.documents
    _, caption, _ = cb.message.documents[0]
    assert "План на 6 недель" in caption
    assert "снижение веса" in caption
    assert "уверенность" in caption


@pytest.mark.asyncio
async def test_cb_plan_pdf_without_plan_explains(env):
    _seed_profile(env)
    cb = FakeCb(data="garmin:plan:pdf")

    await garmin.cb_plan_pdf(cb)

    assert cb.message.answers
    assert "Сначала постройте план" in cb.message.answers[0][0]
    assert cb.message.documents == []


@pytest.mark.asyncio
async def test_cb_plan_pdf_failure_is_reported(env, monkeypatch):
    _seed_profile(env)
    _seed_plan(env)

    def fail(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(garmin, "build_plan_pdf", fail)
    cb = FakeCb(data="garmin:plan:pdf")

    await garmin.cb_plan_pdf(cb)

    assert cb.message.status_edits
    text = cb.message.status_edits[0][0]
    assert "Не удалось собрать PDF плана" in text
    assert "RuntimeError" in text


# ---------------------------------------------------------------------------
# safety gate


@pytest.mark.asyncio
async def test_cb_plan_build_blocks_on_chest_pain(env):
    _seed_profile(env)
    conn = init_db(env.db_path)
    try:
        save_checkin(
            conn,
            UID,
            Checkin(
                date=date.today().isoformat(),
                notes="Во время нагрузки появилась боль в груди",
            ),
        )
    finally:
        conn.close()
    cb = FakeCb(data="garmin:plan:build")

    await garmin.cb_plan_build(cb)

    assert cb.answered[0][0] == "Строю план..."
    text, kwargs = cb.message.answers[0]
    assert "Стоп" in text
    assert "103" in text
    assert "garmin:doctor" in _callback_ids(kwargs["reply_markup"])
    conn = init_db(env.db_path)
    try:
        assert latest_plan(conn, UID) is None
    finally:
        conn.close()
    assert UID not in garmin.garmin_last_plan


@pytest.mark.asyncio
async def test_cb_plan_build_warns_but_saves_plan(env):
    _seed_profile(env, _profile(conditions=["беременность"]))
    cb = FakeCb(data="garmin:plan:build")

    await garmin.cb_plan_build(cb)

    text = cb.message.edits[0][0]
    assert "Ограничения безопасности" in text
    assert "План на 6 недель" in text
    conn = init_db(env.db_path)
    try:
        plan = latest_plan(conn, UID)
    finally:
        conn.close()
    assert plan is not None
    assert any(flag.code == "medical_conditions" for flag in plan.safety_flags)


@pytest.mark.asyncio
async def test_checkin_red_flag_escalates_without_readiness_advice(env):
    _seed_profile(env)
    message = FakeMessage()
    checkin = Checkin(
        date=date.today().isoformat(),
        sleep_h=7.0,
        notes="Был обморок после тренировки",
    )

    await garmin._save_and_show_checkin(message, UID, checkin, edit=False)

    text, kwargs = message.answers[0]
    assert "Стоп" in text
    assert "103" in text
    assert "Готовность:" not in text
    assert "garmin:doctor" in _callback_ids(kwargs["reply_markup"])
    conn = init_db(env.db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM garmin_checkins WHERE user_id = ?",
            (UID,),
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == 1


@pytest.mark.asyncio
async def test_checkin_warning_keeps_advice_and_shows_limits(env):
    _seed_profile(env)
    message = FakeMessage()
    checkin = Checkin(
        date=date.today().isoformat(),
        sleep_h=4.5,
        pain_score=2,
        pain_location="колено",
    )

    await garmin._save_and_show_checkin(message, UID, checkin, edit=False)

    text = message.answers[0][0]
    assert "Готовность:" in text
    assert "Ограничения безопасности" in text
    assert "Чек-ин сохранён" in text


@pytest.mark.asyncio
async def test_plan_screen_asks_clarifying_questions(env):
    _seed_profile(env)
    message = FakeMessage()

    await garmin._plan_screen(message, UID)

    text = message.answers[0][0]
    assert "Уточните, пожалуйста" in text
    assert "дни недели" in text


# ---------------------------------------------------------------------------
# doctor sheet


@pytest.mark.asyncio
async def test_cb_profile_days_same_value_ignores_not_modified(env):
    cb = FakeCb(data="garmin:profile:days:3")

    async def not_modified(text=None, **kwargs):
        raise TelegramBadRequest(
            method="editMessageText",
            message="Bad Request: message is not modified: specified new "
            "message content and reply markup are exactly the same",
        )

    cb.message.edit_text = not_modified

    await garmin.cb_profile_days(cb)

    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_safe_edit_reraises_other_bad_request(env):
    message = FakeMessage()

    async def other_error(text=None, **kwargs):
        raise TelegramBadRequest(
            method="editMessageText",
            message="Bad Request: message to edit not found",
        )

    message.edit_text = other_error

    with pytest.raises(TelegramBadRequest):
        await garmin._safe_edit(message, "text")


@pytest.mark.asyncio
async def test_cb_doctor_lists_questions_and_pdf_button(env):
    _seed_profile(
        env,
        _profile(
            medications=[
                MedicationEntry(name="миртазапин"),
                MedicationEntry(name="венлафаксин"),
            ]
        ),
    )
    cb = FakeCb(data="garmin:doctor")

    await garmin.cb_doctor(cb)

    text, kwargs = cb.message.answers[0]
    assert "Вопросы врачу" in text
    assert "Влияет ли текущая комбинация препаратов" in text
    assert "Красные флаги" in text
    assert "Это не диагноз и не назначение." in text
    assert "garmin:doctor:pdf" in _callback_ids(kwargs["reply_markup"])


@pytest.mark.asyncio
async def test_cb_doctor_without_profile_still_answers(env):
    cb = FakeCb(data="garmin:doctor")

    await garmin.cb_doctor(cb)

    text, kwargs = cb.message.answers[0]
    assert "Вопросы врачу" in text
    assert "Есть ли ограничения по интенсивности" in text
    assert "Влияет ли текущая комбинация" not in text
    assert "garmin:doctor:pdf" in _callback_ids(kwargs["reply_markup"])


@pytest.mark.asyncio
async def test_cb_doctor_pdf_sends_document(env, monkeypatch):
    _seed_profile(
        env,
        _profile(medications=[MedicationEntry(name="миртазапин", dose="15 мг")]),
    )
    plan = _seed_plan(env)
    captured: dict = {}

    def fake_build(profile_arg, output, **kwargs):
        captured["profile"] = profile_arg
        captured["plan"] = kwargs.get("plan")
        captured["checkins"] = kwargs.get("checkins")
        captured["events"] = kwargs.get("events")
        path = Path(output)
        path.write_bytes(b"%PDF-1.4 doctor")
        captured["output"] = path
        return path

    monkeypatch.setattr(garmin, "build_doctor_pdf", fake_build)
    cb = FakeCb(data="garmin:doctor:pdf")

    await garmin.cb_doctor_pdf(cb)

    assert cb.answered[0][0] == "Собираю PDF..."
    assert captured["plan"].plan_id == plan.plan_id
    assert captured["output"].is_file()
    assert cb.message.status_deleted == 1
    assert cb.message.documents
    _, caption, _ = cb.message.documents[0]
    assert "Doctor sheet" in caption


@pytest.mark.asyncio
async def test_cb_doctor_pdf_without_profile_explains(env):
    cb = FakeCb(data="garmin:doctor:pdf")

    await garmin.cb_doctor_pdf(cb)

    assert "Сначала заполните профиль" in cb.message.answers[0][0]
    assert cb.message.documents == []


@pytest.mark.asyncio
async def test_cb_doctor_pdf_failure_is_reported(env, monkeypatch):
    _seed_profile(env)

    def fail(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(garmin, "build_doctor_pdf", fail)
    cb = FakeCb(data="garmin:doctor:pdf")

    await garmin.cb_doctor_pdf(cb)

    assert cb.message.status_edits
    text = cb.message.status_edits[0][0]
    assert "Не удалось собрать doctor sheet" in text
    assert "RuntimeError" in text


# ---------------------------------------------------------------------------
# weekly review


@pytest.mark.asyncio
async def test_cb_plan_review_keep_flow(env):
    _seed_profile(env)
    plan = _seed_plan(env)
    cb = FakeCb(data="garmin:plan:review")

    await garmin.cb_plan_review(cb)

    assert cb.answered[0][0] == "Считаю неделю..."
    text, kwargs = cb.message.answers[0]
    assert "Недельный обзор" in text
    assert "оставить план без изменений" in text
    assert any(
        item.startswith("garmin:plan:review:accept:")
        for item in _callback_ids(kwargs["reply_markup"])
    )
    conn = init_db(env.db_path)
    try:
        row = conn.execute(
            "SELECT decision, applied FROM garmin_plan_reviews"
            " WHERE plan_id = ?",
            (plan.plan_id,),
        ).fetchone()
    finally:
        conn.close()
    assert row["decision"] == "keep"
    assert row["applied"] == 0


@pytest.mark.asyncio
async def test_cb_plan_review_medical_blocks_adaptation(env):
    _seed_profile(env)
    plan = _seed_plan(env)
    conn = init_db(env.db_path)
    try:
        save_checkin(
            conn,
            UID,
            Checkin(
                date=date.today().isoformat(),
                pain_score=5,
                pain_location="колено",
                mood=3,
            ),
        )
    finally:
        conn.close()
    cb = FakeCb(data="garmin:plan:review")

    await garmin.cb_plan_review(cb)

    text, kwargs = cb.message.answers[0]
    assert "Автоматическая адаптация заблокирована" in text
    assert "garmin:doctor" in _callback_ids(kwargs["reply_markup"])
    assert not any(
        item.startswith("garmin:plan:review:accept:")
        for item in _callback_ids(kwargs["reply_markup"])
    )
    conn = init_db(env.db_path)
    try:
        row = conn.execute(
            "SELECT decision FROM garmin_plan_reviews WHERE plan_id = ?",
            (plan.plan_id,),
        ).fetchone()
    finally:
        conn.close()
    assert row["decision"] == "medical"


@pytest.mark.asyncio
async def test_cb_plan_review_accept_applies_and_saves(env):
    _seed_profile(env)
    plan = _seed_plan(env)
    review_id = _save_review(env, plan)
    cb = FakeCb(data=f"garmin:plan:review:accept:{review_id}")

    await garmin.cb_plan_review_accept(cb)

    assert cb.answered[0][0] == "Применяю..."
    text = cb.message.edits[0][0]
    assert "План адаптирован по недельному обзору" in text
    assert "План на 6 недель" in text
    conn = init_db(env.db_path)
    try:
        row = get_review(conn, review_id)
        adapted = latest_plan(conn, UID)
    finally:
        conn.close()
    assert row["applied"] == 1
    assert adapted is not None
    assert adapted.plan_id != plan.plan_id
    assert garmin.garmin_last_plan[UID] == adapted.plan_id


@pytest.mark.asyncio
async def test_cb_plan_review_keep_leaves_plan(env):
    _seed_profile(env)
    plan = _seed_plan(env)
    review_id = _save_review(env, plan)
    cb = FakeCb(data=f"garmin:plan:review:keep:{review_id}")

    await garmin.cb_plan_review_keep(cb)

    assert cb.answered[0][0] == "Оставляю план"
    assert "План оставлен без изменений" in cb.message.edits[0][0]
    conn = init_db(env.db_path)
    try:
        row = get_review(conn, review_id)
        current = latest_plan(conn, UID)
    finally:
        conn.close()
    assert row["applied"] == 0
    assert current.plan_id == plan.plan_id


@pytest.mark.asyncio
async def test_cb_plan_review_accept_medical_is_blocked(env):
    _seed_profile(env)
    plan = _seed_plan(env)
    review_id = _save_review(env, plan, decision="medical")
    cb = FakeCb(data=f"garmin:plan:review:accept:{review_id}")

    await garmin.cb_plan_review_accept(cb)

    assert "План не меняю" in cb.message.edits[0][0]
    conn = init_db(env.db_path)
    try:
        row = get_review(conn, review_id)
        current = latest_plan(conn, UID)
    finally:
        conn.close()
    assert row["applied"] == 0
    assert current.plan_id == plan.plan_id


@pytest.mark.asyncio
async def test_cb_plan_review_accept_invalid_id(env):
    cb = FakeCb(data="garmin:plan:review:accept:not-a-number")

    await garmin.cb_plan_review_accept(cb)

    assert cb.answered == [("Некорректный обзор", True)]
    assert cb.message.edits == []


@pytest.mark.asyncio
async def test_cb_plan_review_accept_missing_review(env):
    cb = FakeCb(data="garmin:plan:review:accept:9999")

    await garmin.cb_plan_review_accept(cb)

    assert "Обзор не найден" in cb.message.edits[0][0]


@pytest.mark.asyncio
async def test_cb_plan_review_accept_foreign_review_is_rejected(env):
    _seed_profile(env)
    plan = _seed_plan(env)
    review_id = _save_review(env, plan, uid=999)
    cb = FakeCb(data=f"garmin:plan:review:accept:{review_id}")

    await garmin.cb_plan_review_accept(cb)

    assert "Обзор не найден" in cb.message.edits[0][0]


@pytest.mark.asyncio
async def test_cb_plan_review_keep_invalid_id(env):
    cb = FakeCb(data="garmin:plan:review:keep:oops")

    await garmin.cb_plan_review_keep(cb)

    assert cb.answered == [("Некорректный обзор", True)]


# ---------------------------------------------------------------------------
# settings and retention


@pytest.mark.asyncio
async def test_cb_settings_shows_storage_and_privacy(env):
    cb = FakeCb(data="garmin:settings")

    await garmin.cb_settings(cb)

    text, kwargs = cb.message.edits[0]
    assert "Garmin: настройки" in text
    assert "Хранение: 365 дней" in text
    assert "Импорт только ручной" in text
    assert "Пароль Garmin не хранится" in text
    assert "Онлайн-режим: выключен" in text
    callbacks = _callback_ids(kwargs["reply_markup"])
    assert "garmin:retention:extend" in callbacks
    assert "garmin:retention:purge" in callbacks
    assert "garmin:delete" in callbacks


@pytest.mark.asyncio
async def test_cb_settings_warns_when_year_is_due(env):
    conn = init_db(env.db_path)
    try:
        upsert_daily(
            conn,
            {"user_id": UID, "date": "2024-01-01", "sleep_hours": 7.0},
            source="manual",
        )
    finally:
        conn.close()
    cb = FakeCb(data="garmin:settings")

    await garmin.cb_settings(cb)

    text = cb.message.edits[0][0]
    assert "Данным исполняется год" in text


@pytest.mark.asyncio
async def test_cb_retention_extend_sets_future_date(env):
    cb = FakeCb(data="garmin:retention:extend")

    await garmin.cb_retention_extend(cb)

    assert cb.answered
    assert cb.answered[0][0].startswith("Хранение продлено до ")
    text = cb.message.edits[0][0]
    assert "Хранение: 365 дней · до" in text
    conn = init_db(env.db_path)
    try:
        row = conn.execute(
            "SELECT retention_until FROM garmin_settings WHERE user_id = ?",
            (UID,),
        ).fetchone()
    finally:
        conn.close()
    assert row["retention_until"] is not None
    assert date.fromisoformat(row["retention_until"]) > date.today()


@pytest.mark.asyncio
async def test_cb_retention_purge_asks_for_confirmation(env):
    cb = FakeCb(data="garmin:retention:purge")

    await garmin.cb_retention_purge(cb)

    text, kwargs = cb.message.answers[0]
    assert "Удалить Garmin-данные старше" in text
    assert "Профиль, препараты и планы останутся" in text
    assert "garmin:retention:purge:confirm" in _callback_ids(
        kwargs["reply_markup"]
    )


@pytest.mark.asyncio
async def test_cb_retention_purge_confirm_removes_old_rows(env):
    conn = init_db(env.db_path)
    try:
        upsert_daily(
            conn,
            {"user_id": UID, "date": "2020-01-01", "sleep_hours": 6.0},
            source="manual",
        )
        upsert_daily(
            conn,
            {"user_id": UID, "date": date.today().isoformat(), "sleep_hours": 7.0},
            source="manual",
        )
    finally:
        conn.close()
    cb = FakeCb(data="garmin:retention:purge:confirm")

    await garmin.cb_retention_purge_confirm(cb)

    assert cb.answered[0][0] == "Удаляю..."
    text = cb.message.edits[0][0]
    assert "Удалено строк: 1" in text
    conn = init_db(env.db_path)
    try:
        dates = [
            row["date"]
            for row in conn.execute(
                "SELECT date FROM garmin_daily WHERE user_id = ?", (UID,)
            )
        ]
    finally:
        conn.close()
    assert dates == [date.today().isoformat()]


# ---------------------------------------------------------------------------
# import result formatting


def test_format_import_result_ok_with_rows_and_period():
    result = SimpleNamespace(
        status="ok",
        files_total=2,
        files_ok=2,
        files_failed=0,
        days=["2026-11-01", "2026-11-02", "2026-11-01"],
        rows_total=5,
        rows_ok=4,
        rows_skipped=1,
        rows_failed=0,
        issues=[],
    )

    text = garmin._format_import_result(result)

    assert "✅ <b>Импорт завершён</b>" in text
    assert "Файлов: 2, успешно: 2, ошибок: 0" in text
    assert "Дней с данными: 2" in text
    assert "Строк: 5, активностей: 4, пропущено: 1, ошибок: 0" in text
    assert "Период: 01.11.2026 — 02.11.2026" in text


def test_format_import_result_partial_lists_first_issues():
    issues = [SimpleNamespace(error=f"bad {index}") for index in range(4)]
    result = SimpleNamespace(
        status="partial",
        files_total=3,
        files_ok=2,
        files_failed=1,
        days=[],
        rows_total=0,
        issues=issues,
    )

    text = garmin._format_import_result(result)

    assert "⚠️ <b>Импорт частичный</b>" in text
    assert "Первые проблемы:" in text
    assert "bad 0" in text
    assert "bad 2" in text
    assert "bad 3" not in text


def test_format_import_result_failed_escapes_issue_text():
    result = SimpleNamespace(
        status="failed",
        files_total=1,
        files_ok=0,
        files_failed=1,
        days=[],
        issues=[SimpleNamespace(error="<script> & boom")],
    )

    text = garmin._format_import_result(result)

    assert "❌ <b>Импорт не удался</b>" in text
    assert "&lt;script&gt; &amp; boom" in text
    assert "<script>" not in text


def test_format_import_result_deduplicates_period_days():
    result = SimpleNamespace(
        status="ok",
        files_total=1,
        files_ok=1,
        files_failed=0,
        days=["2026-11-02", "2026-11-01", "2026-11-02"],
        issues=[],
    )

    text = garmin._format_import_result(result)

    assert "Дней с данными: 2" in text
    assert "Период: 01.11.2026 — 02.11.2026" in text
