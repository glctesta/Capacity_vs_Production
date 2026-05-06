"""Rolling month + YTD calculations + daily history persistence."""
import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List

from engine.models import DayPoint, RollingData

logger = logging.getLogger("PianoTempi")


def load_daily_history(path: str) -> List[DayPoint]:
    """Load daily history from JSON file; return empty list if missing or corrupt.

    File format:
    {
        "year": 2026,
        "days": [
            {
                "date": "2026-05-05",
                "phases": {"ASSEMBLY": {"planned_h": 24.0, "produced_h": 22.5}},
                "totals": {"planned_h": 24.0, "produced_h": 22.5, "coverage_pct": 93.75}
            },
            ...
        ]
    }
    """
    p = Path(path)
    if not p.exists():
        return []

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.error("daily history file corrupt or unreadable %s: %s -- recreating", path, e)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            p.rename(p.with_name(f"{p.stem}.corrupt-{ts}{p.suffix}"))
        except OSError:
            pass
        return []

    pts: List[DayPoint] = []
    for d in data.get("days", []):
        try:
            pts.append(DayPoint(
                date=date.fromisoformat(d["date"]),
                planned_h=float(d["totals"]["planned_h"]),
                produced_h=float(d["totals"]["produced_h"]),
                coverage_pct=float(d["totals"]["coverage_pct"]),
            ))
        except (KeyError, ValueError) as e:
            logger.warning("skipping malformed daily history row: %s -- %s", d, e)
    return pts


def save_day_to_history(
    path: str, day: date, phases: Dict[str, Dict[str, float]],
) -> None:
    """Atomically append/replace one day in daily_history_<year>.json.

    `phases` is {phase_name: {"planned_h": float, "produced_h": float}}.
    Computes totals automatically. Writes to .tmp then os.replace for atomicity.
    """
    p = Path(path)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {"year": day.year, "days": []}
    else:
        data = {"year": day.year, "days": []}

    total_plan = round(sum(v["planned_h"] for v in phases.values()), 2)
    total_prod = round(sum(v["produced_h"] for v in phases.values()), 2)
    coverage = round(total_prod / total_plan * 100.0, 2) if total_plan > 0 else 0.0

    new_entry = {
        "date": day.isoformat(),
        "phases": phases,
        "totals": {"planned_h": total_plan, "produced_h": total_prod, "coverage_pct": coverage},
    }

    data["year"] = day.year
    days = [d for d in data.get("days", []) if d.get("date") != day.isoformat()]
    days.append(new_entry)
    days.sort(key=lambda d: d["date"])
    data["days"] = days

    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def _coverage(plan: float, prod: float) -> float:
    """Compute coverage percentage, safe for zero plan."""
    return round(prod / plan * 100.0, 2) if plan > 0 else 0.0


def compute_rolling_month(today: date, history: List[DayPoint]) -> RollingData:
    """Sum days from 1st of `today.month` to yesterday (today excluded).

    Also computes YTD numbers (year start to yesterday).
    Returns RollingData with both month and YTD fields populated.
    """
    month_start = today.replace(day=1)
    days = [d for d in history if month_start <= d.date < today]
    days.sort(key=lambda d: d.date)

    plan = round(sum(d.planned_h for d in days), 2)
    prod = round(sum(d.produced_h for d in days), 2)

    year_start = today.replace(month=1, day=1)
    ytd_days = [d for d in history if year_start <= d.date < today]
    ytd_plan = round(sum(d.planned_h for d in ytd_days), 2)
    ytd_prod = round(sum(d.produced_h for d in ytd_days), 2)

    return RollingData(
        days=days,
        month_planned_h=plan,
        month_produced_h=prod,
        month_coverage_pct=_coverage(plan, prod),
        ytd_planned_h=ytd_plan,
        ytd_produced_h=ytd_prod,
        ytd_coverage_pct=_coverage(ytd_plan, ytd_prod),
        working_days_month=len([d for d in days if d.planned_h > 0]),
        working_days_ytd=len([d for d in ytd_days if d.planned_h > 0]),
    )


def compute_y2d(today: date, history: List[DayPoint]) -> RollingData:
    """Convenience wrapper: same as compute_rolling_month.

    Caller cares only about YTD numbers, but we return the full RollingData.
    Month fields are also populated.
    """
    return compute_rolling_month(today, history)
