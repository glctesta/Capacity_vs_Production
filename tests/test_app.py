# tests/test_app.py
from datetime import datetime, time
from unittest.mock import MagicMock
from app import build_flask_app
from data_cache import DataCache
from app_config import (
    AppConfig, ServerConfig, PhasesConfig, DataSourcesConfig,
    RefreshConfig, ShiftConfig, ThresholdsConfig, EmailReportConfig,
)


def _cfg():
    return AppConfig(
        server=ServerConfig(),
        phases=PhasesConfig(monitored=["ASSEMBLY"]),
        data_sources=DataSourcesConfig(), refresh=RefreshConfig(),
        shifts=[
            ShiftConfig("T1", time(7, 30), time(15, 30)),
            ShiftConfig("T2", time(15, 30), time(23, 30)),
            ShiftConfig("T3", time(23, 30), time(7, 30)),
        ],
        thresholds=ThresholdsConfig(), email_report=EmailReportConfig(),
    )


def test_health_endpoint():
    cache = DataCache(_cfg())
    cache.last_refresh_ts["routing"] = datetime(2026, 5, 6, 10, 0)
    cache.last_refresh_ts["planning"] = datetime(2026, 5, 6, 10, 30)
    cache.last_refresh_ts["production"] = datetime(2026, 5, 6, 10, 31)
    app = build_flask_app(cache)
    client = app.test_client()
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "last_refresh" in data
    assert "routing" in data["last_refresh"]


def test_phases_endpoint_returns_kpis():
    cache = DataCache(_cfg())
    from engine.models import PhaseKPI
    cache.phase_kpis = {
        "ASSEMBLY": PhaseKPI(
            phase_name="ASSEMBLY", shift_code="T1",
            planned_h_day=24.0, planned_h_shift=12.0,
            planned_h_so_far_day=6.0, planned_h_so_far_shift=6.0,
            produced_h_day=4.0, produced_h_shift=4.0,
            delta_vs_expected_day=-2.0, delta_vs_expected_shift=-2.0,
            coverage_pct_day=16.67, status_color="red",
            curve_points=[],
        )
    }
    app = build_flask_app(cache)
    resp = app.test_client().get("/api/phases")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "phases" in data
    assert data["phases"]["ASSEMBLY"]["planned_h_day"] == 24.0
    assert data["phases"]["ASSEMBLY"]["status_color"] == "red"


def test_totals_endpoint():
    from engine.models import TotalKPI
    cache = DataCache(_cfg())
    cache.total_kpi = TotalKPI(
        planned_h_day=168.0, planned_h_so_far_day=71.4, produced_h_day=68.5,
        delta_vs_expected_day=-2.9, coverage_pct_day=40.8, status_color="red",
    )
    app = build_flask_app(cache)
    resp = app.test_client().get("/api/totals")
    assert resp.status_code == 200
    assert resp.get_json()["planned_h_day"] == 168.0


def test_rolling_endpoint():
    from engine.models import RollingData
    cache = DataCache(_cfg())
    cache.rolling_data = RollingData(
        days=[], month_planned_h=720.0, month_produced_h=668.4,
        month_coverage_pct=92.83, ytd_planned_h=18240.0, ytd_produced_h=16893.5,
        ytd_coverage_pct=92.62, working_days_month=4, working_days_ytd=87,
    )
    app = build_flask_app(cache)
    resp = app.test_client().get("/api/rolling-month")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["month_planned_h"] == 720.0
    assert data["working_days_ytd"] == 87
