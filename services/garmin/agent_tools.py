"""Read-only Garmin tools for the conversational AI agent.

These tools expose deterministic Garmin summaries, event/illness correlations,
recent workouts, and the active training plan to the local agent loop without
allowing any write operations or exposing secrets/PII.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from services.agent_tools import CAT_SYSTEM, register_tool, unregister_tool

from .analytics import build_report, workout_comparison
from .config import get_config
from .db import init_db
from .errors import GarminError
from .medications import medication_ai_context
from .plan_engine import plan_summary, week_detail_text
from .plan_store import latest_plan
from .profile_store import load_profile, recent_checkins
from .readiness import assess_readiness


def _resolve_user_id(conn: sqlite3.Connection, explicit: int | None = None) -> int:
    if explicit is not None:
        return int(explicit)
    for table, col in (
        ("garmin_daily", "updated_at"),
        ("garmin_events", "created_at"),
        ("garmin_activities", "updated_at"),
        ("garmin_profile", "updated_at"),
    ):
        row = conn.execute(
            f"SELECT user_id FROM {table} ORDER BY {col} DESC LIMIT 1"  # nosec B608
        ).fetchone()
        if row is not None:
            return int(row["user_id"])
    return 1


def register_garmin_agent_tools() -> None:
    """Idempotently register read-only Garmin tools in the agent registry."""
    for tool_name in (
        "garmin_health_summary",
        "garmin_recent_workouts",
        "garmin_training_plan",
        "garmin_correlate_period",
    ):
        unregister_tool(tool_name)

    @register_tool(
        "garmin_health_summary",
        "Сводка показателей здоровья и восстановления Garmin за последние N дней "
        "(сон, HRV, пульс покоя, стресс, Body Battery, дыхание, SpO2, VO2max, "
        "готовность к нагрузке, отмеченные болезни/простуды и их связь с метриками).",
        schema={
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Период анализа в днях (по умолчанию 14)",
                    "minimum": 1,
                    "maximum": 365,
                },
            },
        },
        category=CAT_SYSTEM,
        is_write=False,
    )
    def _garmin_health_summary(args: dict) -> str:
        days = int(args.get("days") or 14)
        cfg = get_config()
        conn = init_db(cfg.db_path)
        try:
            uid = _resolve_user_id(conn)
            report = build_report(conn, user_id=uid, days=days)
            checkins = recent_checkins(conn, uid, limit=7)
            try:
                stored = load_profile(conn, uid)
                meds = stored.profile.medications if stored else []
            except GarminError:
                meds = []
            readiness = assess_readiness(
                report, checkin=checkins[0] if checkins else None
            )
        finally:
            conn.close()

        lines = [
            f"Период: {report.start} — {report.end} ({days} дн.), "
            f"достоверность: {report.confidence}",
            f"Готовность: {readiness.emoji} {readiness.level} — {readiness.advice}",
        ]
        if readiness.reasons:
            lines.append("Причины готовности: " + "; ".join(readiness.reasons))

        lines.append("\nКлючевые метрики:")
        for key, item in report.series.items():
            if item.latest is None and item.avg_7d is None:
                continue
            parts = [f"{item.label}: посл. {item.latest} {item.unit}"]
            if item.avg_7d is not None:
                parts.append(f"7д ср. {item.avg_7d}")
            if item.baseline is not None:
                parts.append(f"baseline {item.baseline}")
            lines.append("- " + " · ".join(parts))

        if report.extended_metrics:
            ext_parts = []
            for k, val in report.extended_metrics.items():
                if k in {"sleep_architecture", "sleep_consistency", "workout_to_sleep_lag"}:
                    continue
                if isinstance(val, dict):
                    ext_parts.append(f"{k}: ср. {val.get('avg')} (посл. {val.get('latest')})")
                else:
                    ext_parts.append(f"{k}: {val}")
            if ext_parts:
                lines.append("\nДоп. физиология: " + "; ".join(ext_parts))

            arch = report.extended_metrics.get("sleep_architecture")
            if isinstance(arch, dict):
                arch_parts = []
                if arch.get("deep_pct_avg") is not None:
                    arch_parts.append(f"глубокий {arch['deep_pct_avg']}%")
                if arch.get("rem_pct_avg") is not None:
                    arch_parts.append(f"REM {arch['rem_pct_avg']}%")
                if arch.get("awake_min_avg") is not None:
                    arch_parts.append(f"пробуждения {arch['awake_min_avg']} мин")
                if arch_parts:
                    lines.append("Структура сна (ср.): " + ", ".join(arch_parts))

            cons = report.extended_metrics.get("sleep_consistency")
            if isinstance(cons, dict) and cons.get("avg_midpoint"):
                stdev_txt = (
                    f" (±{cons['midpoint_stdev_min']} мин)"
                    if cons.get("midpoint_stdev_min") is not None
                    else ""
                )
                lines.append(
                    f"Регулярность сна: середина сна {cons['avg_midpoint']}{stdev_txt}"
                )

            lag = report.extended_metrics.get("workout_to_sleep_lag")
            if isinstance(lag, dict) and lag.get("summary"):
                lines.append("Лаг-эффект тренировок: " + str(lag["summary"]))

        if checkins:
            moods = [c.mood for c in checkins if c.mood is not None]
            stresses = [c.stress for c in checkins if c.stress is not None]
            parts_chk = []
            if moods:
                parts_chk.append(f"настроение ср. {sum(moods)/len(moods):.1f}/5")
            if stresses:
                parts_chk.append(f"субъект. стресс ср. {sum(stresses)/len(stresses):.1f}/5")
            if parts_chk:
                lines.append("\nЭмоциональное состояние (чек-ины): " + ", ".join(parts_chk))

        med_ctx = medication_ai_context(meds)
        if med_ctx["has_medications"]:
            lines.append(
                "\nУчёт терапии (классы): " + ", ".join(med_ctx["classes"])
            )
            if med_ctx["sleep_effects"]:
                lines.append("Влияние на сон: " + " ".join(med_ctx["sleep_effects"]))
            if med_ctx["emotional_effects"]:
                lines.append(
                    "Влияние на эмоции и ВНС: "
                    + " ".join(med_ctx["emotional_effects"])
                )

        if report.event_correlations:
            lines.append("\nСобытия и связь с состоянием (болезнь/простуда/стресс):")
            for corr in report.event_correlations[-5:]:
                lines.append(f"- [{corr['kind']}/{corr['severity']}] {corr['summary']}")

        if report.flags:
            lines.append("\nФлаги:")
            for flag in report.flags:
                lines.append(f"- [{flag.severity}] {flag.text}")

        if report.causes:
            lines.append("\nДетерминированные гипотезы:")
            for cause in report.causes:
                lines.append(f"- {cause}")

        return "\n".join(lines)

    @register_tool(
        "garmin_recent_workouts",
        "Список последних тренировок и активностей Garmin (тип, длительность, "
        "дистанция, пульс, тренировочная нагрузка) за последние дни.",
        schema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Количество последних тренировок (по умолчанию 10)",
                    "minimum": 1,
                    "maximum": 30,
                },
            },
        },
        category=CAT_SYSTEM,
        is_write=False,
    )
    def _garmin_recent_workouts(args: dict) -> str:
        limit = int(args.get("limit") or 10)
        cfg = get_config()
        conn = init_db(cfg.db_path)
        try:
            uid = _resolve_user_id(conn)
            rows = conn.execute(
                "SELECT start_time, activity_type, name, duration_min, distance_m,"
                " avg_hr, max_hr, training_load, aerobic_te, anaerobic_te"
                " FROM garmin_activities WHERE user_id = ?"
                " ORDER BY start_time DESC LIMIT ?",
                (uid, limit),
            ).fetchall()
            comp = (
                workout_comparison(conn, user_id=uid, activity_row=rows[0])
                if rows
                else None
            )
        finally:
            conn.close()

        if not rows:
            return "Импортированных тренировок в базе Garmin пока нет."

        lines = [f"Последние тренировки (показано {len(rows)}):"]
        for row in rows:
            day = str(row["start_time"] or "")[:16].replace("T", " ")
            atype = row["activity_type"] or "other"
            name = row["name"] or atype
            dur = f"{float(row['duration_min']):.0f} мин" if row["duration_min"] else "—"
            dist = (
                f", {float(row['distance_m']) / 1000.0:.2f} км"
                if row["distance_m"]
                else ""
            )
            hr = f", ЧСС ср. {int(row['avg_hr'])}" if row["avg_hr"] else ""
            load = (
                f", нагрузка {float(row['training_load']):.0f}"
                if row["training_load"]
                else ""
            )
            lines.append(f"- {day} · {atype} ({name}): {dur}{dist}{hr}{load}")
        if comp and comp.get("summary"):
            lines.append("\nПост-тренировочный разбор (посл. сессия): " + str(comp["summary"]))
        return "\n".join(lines)

    @register_tool(
        "garmin_training_plan",
        "Текущий тренировочный план Garmin, адаптации по болезни/самочувствию "
        "и расписание сессий на текущую неделю.",
        schema={"type": "object", "properties": {}},
        category=CAT_SYSTEM,
        is_write=False,
    )
    def _garmin_training_plan(_args: dict) -> str:
        cfg = get_config()
        conn = init_db(cfg.db_path)
        try:
            uid = _resolve_user_id(conn)
            plan = latest_plan(conn, uid)
        finally:
            conn.close()

        if plan is None:
            return "Активный тренировочный план пока не создан."

        today_iso = date.today().isoformat()
        week_num = 1
        for week in plan.weeks:
            dates = [s.date for s in week.sessions]
            if dates and min(dates) <= today_iso <= max(dates):
                week_num = week.week
                break
        return plan_summary(plan) + "\n\n" + week_detail_text(plan, week_num)

    @register_tool(
        "garmin_correlate_period",
        "Кросс-доменный срез физиологии Garmin, тренировок, чек-инов и событий "
        "(болезнь/простуда/стресс) за произвольный интервал дат [start_date, end_date] "
        "для сопоставления с заметками Apple Notes и записями MemPalace.",
        schema={
            "type": "object",
            "required": ["start_date", "end_date"],
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Начальная дата в формате YYYY-MM-DD",
                },
                "end_date": {
                    "type": "string",
                    "description": "Конечная дата в формате YYYY-MM-DD",
                },
            },
        },
        category=CAT_SYSTEM,
        is_write=False,
    )
    def _garmin_correlate_period(args: dict) -> str:
        start_raw = str(args.get("start_date") or "").strip()[:10]
        end_raw = str(args.get("end_date") or "").strip()[:10]
        try:
            start_dt = date.fromisoformat(start_raw)
            end_dt = date.fromisoformat(end_raw)
        except ValueError:
            return "Ошибка: укажите start_date и end_date в формате YYYY-MM-DD."
        if end_dt < start_dt:
            start_dt, end_dt = end_dt, start_dt
        days = min(max((end_dt - start_dt).days + 1, 1), 365)

        cfg = get_config()
        conn = init_db(cfg.db_path)
        try:
            uid = _resolve_user_id(conn)
            report = build_report(
                conn, user_id=uid, days=days, end_date=end_dt.isoformat()
            )
            daily_rows = conn.execute(
                "SELECT date, sleep_hours, sleep_score, hrv, resting_hr,"
                " stress_avg, body_battery_morning, steps"
                " FROM garmin_daily WHERE user_id = ? AND date BETWEEN ? AND ?"
                " ORDER BY date",
                (uid, start_dt.isoformat(), end_dt.isoformat()),
            ).fetchall()
            act_rows = conn.execute(
                "SELECT start_time, activity_type, name, duration_min, training_load"
                " FROM garmin_activities"
                " WHERE user_id = ? AND date(start_time) BETWEEN ? AND ?"
                " ORDER BY start_time",
                (uid, start_dt.isoformat(), end_dt.isoformat()),
            ).fetchall()
        finally:
            conn.close()

        lines = [
            f"Срез Garmin за период {report.start} — {report.end} "
            f"(дней с данными: {len(daily_rows)}, тренировок: {len(act_rows)}):"
        ]
        for key, item in report.series.items():
            present = [v for v in item.values if v is not None]
            if not present:
                continue
            avg_val = round(sum(present) / len(present), 1)
            base_txt = (
                f" (baseline {item.baseline})" if item.baseline is not None else ""
            )
            lines.append(
                f"- {item.label}: ср. {avg_val} {item.unit}, "
                f"мин {min(present)}, макс {max(present)}{base_txt}"
            )

        lag = report.extended_metrics.get("workout_to_sleep_lag")
        if isinstance(lag, dict) and lag.get("summary"):
            lines.append("Лаг-связь тренировок со сном: " + str(lag["summary"]))

        if report.event_correlations:
            lines.append("События в периоде:")
            for corr in report.event_correlations:
                lines.append(f"- {corr['summary']}")

        if daily_rows:
            lines.append("Посуточная динамика (до 14 дней):")
            for r in daily_rows[-14:]:
                d_parts = [str(r["date"])]
                if r["sleep_hours"] is not None:
                    d_parts.append(f"сон {float(r['sleep_hours']):.1f}ч")
                if r["hrv"] is not None:
                    d_parts.append(f"HRV {int(r['hrv'])}")
                if r["resting_hr"] is not None:
                    d_parts.append(f"ЧСС {int(r['resting_hr'])}")
                if r["stress_avg"] is not None:
                    d_parts.append(f"стресс {int(r['stress_avg'])}")
                lines.append("  · " + ", ".join(d_parts))
        return "\n".join(lines)


register_garmin_agent_tools()
