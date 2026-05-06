"""Tests for rolling_engine: daily history persistence + rolling month/YTD."""
import json
from datetime import date
from engine.models import DayPoint
from engine.rolling_engine import (
    load_daily_history, save_day_to_history,
    compute_rolling_month, compute_y2d,
)


# ============================================================================
# Sub-task 6.1: DailyHistory loader/writer tests
# ============================================================================

def test_load_daily_history_missing_file_returns_empty(tmp_path):
    f = tmp_path / "daily_history_2026.json"
    assert load_daily_history(str(f)) == []


def test_load_daily_history_returns_day_points(tmp_path):
    f = tmp_path / "daily_history_2026.json"
    f.write_text(json.dumps({
        "year": 2026,
        "days": [
            {
                "date": "2026-05-05",
                "phases": {"ASSEMBLY": {"planned_h": 24.0, "produced_h": 22.5}},
                "totals": {"planned_h": 24.0, "produced_h": 22.5, "coverage_pct": 93.75},
            }
        ],
    }), encoding="utf-8")
    pts = load_daily_history(str(f))
    assert len(pts) == 1
    assert pts[0].date == date(2026, 5, 5)
    assert pts[0].planned_h == 24.0
    assert pts[0].produced_h == 22.5


def test_save_day_creates_file_atomic(tmp_path):
    f = tmp_path / "daily_history_2026.json"
    save_day_to_history(
        str(f),
        day=date(2026, 5, 5),
        phases={"ASSEMBLY": {"planned_h": 24.0, "produced_h": 22.5}},
    )
    assert f.exists()
    data = json.loads(f.read_text(encoding="utf-8"))
    assert data["year"] == 2026
    assert data["days"][0]["date"] == "2026-05-05"
    assert data["days"][0]["totals"]["coverage_pct"] == 93.75


def test_save_day_appends_to_existing_file(tmp_path):
    f = tmp_path / "daily_history_2026.json"
    save_day_to_history(str(f), day=date(2026, 5, 5),
                        phases={"A": {"planned_h": 10, "produced_h": 8}})
    save_day_to_history(str(f), day=date(2026, 5, 6),
                        phases={"A": {"planned_h": 10, "produced_h": 9}})
    data = json.loads(f.read_text(encoding="utf-8"))
    assert len(data["days"]) == 2


def test_save_day_replaces_existing_date(tmp_path):
    f = tmp_path / "daily_history_2026.json"
    save_day_to_history(str(f), day=date(2026, 5, 5),
                        phases={"A": {"planned_h": 10, "produced_h": 8}})
    save_day_to_history(str(f), day=date(2026, 5, 5),
                        phases={"A": {"planned_h": 10, "produced_h": 9}})
    data = json.loads(f.read_text(encoding="utf-8"))
    assert len(data["days"]) == 1
    assert data["days"][0]["totals"]["produced_h"] == 9


# ============================================================================
# Sub-task 6.2: compute_rolling_month + compute_y2d tests
# ============================================================================

def _dp(y, m, d, plan, prod):
    """Helper to create DayPoint with auto-computed coverage_pct."""
    cov = round(prod / plan * 100, 2) if plan > 0 else 0.0
    return DayPoint(date=date(y, m, d), planned_h=plan, produced_h=prod, coverage_pct=cov)


def test_compute_rolling_month_excludes_today():
    history = [
        _dp(2026, 5, 1, 100, 90),
        _dp(2026, 5, 2, 100, 95),
        _dp(2026, 5, 3, 100, 100),
        _dp(2026, 5, 6, 100, 80),  # today, must be excluded
    ]
    rd = compute_rolling_month(today=date(2026, 5, 6), history=history)
    assert rd.month_planned_h == 300.0  # 1 + 2 + 3
    assert rd.month_produced_h == 285.0  # 90 + 95 + 100
    assert rd.month_coverage_pct == 95.0
    assert rd.working_days_month == 3
    assert len(rd.days) == 3


def test_compute_rolling_month_empty_history():
    rd = compute_rolling_month(today=date(2026, 5, 6), history=[])
    assert rd.month_planned_h == 0.0
    assert rd.month_coverage_pct == 0.0
    assert rd.working_days_month == 0


def test_compute_y2d_full_year_so_far():
    history = [
        _dp(2026, 1, 5, 50, 45),
        _dp(2026, 3, 10, 80, 80),
        _dp(2026, 5, 5, 100, 95),
        _dp(2026, 5, 6, 100, 80),  # today, excluded
    ]
    rd = compute_y2d(today=date(2026, 5, 6), history=history)
    assert rd.ytd_planned_h == 230.0
    assert rd.ytd_produced_h == 220.0
    assert rd.working_days_ytd == 3
