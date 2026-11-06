#!/usr/bin/env python3
"""Build a local Garmin PDF report from imported SQLite data."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.garmin.analytics import build_report  # noqa: E402
from services.garmin.charts import render_charts  # noqa: E402
from services.garmin.coach import generate_causes  # noqa: E402
from services.garmin.config import get_config  # noqa: E402
from services.garmin.db import init_db  # noqa: E402
from services.garmin.pdf_report import build_pdf  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a Garmin health PDF")
    parser.add_argument("--user-id", type=int, default=int(os.getenv("GARMIN_USER_ID", "1")))
    parser.add_argument("--days", type=int, default=30, help="report window (1..3650)")
    parser.add_argument("--end", help="end date YYYY-MM-DD (default: today)")
    parser.add_argument("--data-dir", help="Garmin data directory")
    parser.add_argument("--db", help="SQLite path")
    parser.add_argument("--out", help="output PDF path")
    parser.add_argument("--charts-dir", help="chart PNG directory")
    parser.add_argument("--no-charts", action="store_true", help="tables only")
    parser.add_argument("--no-ai", action="store_true", help="skip local Ollama narration")
    parser.add_argument("--model", help="Ollama model (default: GARMIN_AI_MODEL)")
    parser.add_argument("--ai-timeout", type=float, help="Ollama timeout in seconds")
    args = parser.parse_args(argv)

    cfg = get_config(args.data_dir)
    cfg.ensure_dirs()
    db_path = Path(args.db).expanduser() if args.db else cfg.db_path
    conn = init_db(db_path)
    coach = None
    try:
        report = build_report(
            conn,
            user_id=args.user_id,
            days=args.days,
            end_date=args.end,
        )
        if not args.no_ai:
            coach = generate_causes(
                conn,
                report,
                model=args.model or cfg.ai_model,
                timeout=args.ai_timeout or cfg.ai_timeout,
                ai_enabled=cfg.ai_enabled,
            )
    finally:
        conn.close()

    end = report.end
    output = (
        Path(args.out).expanduser()
        if args.out
        else cfg.report_dir / f"garmin_report_{end}_{args.days}d.pdf"
    )
    charts = {}
    if not args.no_charts:
        charts = render_charts(
            report,
            Path(args.charts_dir).expanduser() if args.charts_dir else cfg.charts_dir,
            dpi=cfg.chart_dpi,
        )
    pdf = build_pdf(report, charts, output, coach=coach)

    data_days = sum(
        1
        for index in range(len(report.dates))
        if any(series.values[index] is not None for series in report.series.values())
    )
    print(f"PDF: {pdf}")
    print(
        f"Период: {report.start} — {report.end}; "
        f"дней с данными: {data_days}; confidence: {report.confidence}"
    )
    if report.flags:
        print("Флаги: " + ", ".join(flag.code for flag in report.flags))
    if coach is not None:
        print(f"AI: {coach.source}" + (f" ({coach.model})" if coach.model else ""))
        if coach.errors:
            print("AI fallback: " + "; ".join(coach.errors[:2]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
