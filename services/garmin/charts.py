"""Matplotlib charts for Garmin PDF reports.

All rendering uses the non-interactive Agg backend.  Missing values remain
gaps; charts never fabricate or interpolate data.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

from .analytics import ReportData  # noqa: E402

COLORS = {
    "sleep_hours": "#3b6ea8",
    "sleep_score": "#4f8f6f",
    "hrv": "#7a5aa6",
    "resting_hr": "#c05a4a",
    "stress_avg": "#c08a3e",
    "steps": "#3f8f8a",
    "weight_kg": "#6b6b6b",
    "readiness_score": "#2f7f5f",
    "body_battery_morning": "#8a6d3b",
}


def _as_float(value):
    return float(value) if value is not None else float("nan")


def render_charts(
    report: ReportData,
    out_dir: str | Path,
    *,
    dpi: int = 200,
    force: bool = True,
) -> dict[str, Path]:
    """Render one PNG per available metric and return key → path."""
    output = Path(out_dir).expanduser()
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    dates = [date.fromisoformat(day) for day in report.dates]
    paths: dict[str, Path] = {}

    for key, series in report.series.items():
        if not any(value is not None for value in series.values):
            continue
        target = output / f"chart_{key}.png"
        if target.exists() and not force:
            paths[key] = target
            continue

        fig, ax = plt.subplots(figsize=(8.0, 2.55))
        values = [_as_float(value) for value in series.values]
        ax.plot(
            dates,
            values,
            color=COLORS.get(key, "#3b6ea8"),
            linewidth=1.7,
            marker="o",
            markersize=3,
            label=series.label,
        )
        if series.baseline is not None:
            ax.axhline(
                series.baseline,
                color="#999999",
                linewidth=1,
                linestyle="--",
                label=f"baseline {series.baseline:g}",
            )
        if series.target is not None:
            ax.axhline(
                series.target,
                color="#4f8f6f",
                linewidth=1,
                linestyle=":",
                label=f"цель {series.target:g}",
            )
        ax.set_title(f"{series.label}, {series.unit}", loc="left", fontsize=10)
        ax.set_ylabel(series.unit, fontsize=8)
        ax.grid(axis="y", alpha=0.25)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
        ax.xaxis.set_major_locator(MaxNLocator(nbins=10))
        ax.tick_params(axis="both", labelsize=7)
        fig.autofmt_xdate(rotation=0, ha="center")
        ax.legend(fontsize=7, loc="best", frameon=False)
        fig.tight_layout(pad=0.4)
        fig.savefig(target, dpi=dpi, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        paths[key] = target

    return paths
