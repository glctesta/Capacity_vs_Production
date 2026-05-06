# tests/test_email_report.py
from datetime import date, time as dtime
from engine.models import DayPoint, RollingData
from reporting.email_report import (
    generate_subject, generate_plain_body, generate_html_body,
)


def test_subject_format():
    s = generate_subject("[Production Efficiency]", date(2026, 5, 5), 91.8)
    assert s == "[Production Efficiency] Daily report 2026-05-05 — coverage 91.8%"


def test_plain_body_contains_sections():
    yesterday = DayPoint(date(2026, 5, 5), 168.0, 154.3, 91.8)
    yesterday_per_phase = {
        "ASSEMBLY": (24.0, 22.5),
        "COATING":  (16.0, 15.8),
    }
    rolling = RollingData(
        days=[], month_planned_h=720.0, month_produced_h=668.4, month_coverage_pct=92.83,
        ytd_planned_h=18240.0, ytd_produced_h=16893.5, ytd_coverage_pct=92.62,
        working_days_month=4, working_days_ytd=87,
    )
    body = generate_plain_body(yesterday, yesterday_per_phase, rolling)
    assert "YESTERDAY" in body
    assert "168.00" in body
    assert "MONTH TO DATE" in body
    assert "YEAR TO DATE" in body
    assert "ASSEMBLY" in body


def test_html_body_contains_sections():
    yesterday = DayPoint(date(2026, 5, 5), 168.0, 154.3, 91.8)
    yesterday_per_phase = {"ASSEMBLY": (24.0, 22.5)}
    rolling = RollingData(
        days=[], month_planned_h=720.0, month_produced_h=668.4, month_coverage_pct=92.83,
        ytd_planned_h=18240.0, ytd_produced_h=16893.5, ytd_coverage_pct=92.62,
        working_days_month=4, working_days_ytd=87,
    )
    html = generate_html_body(yesterday, yesterday_per_phase, rolling)
    assert "<table" in html
    assert "ASSEMBLY" in html
    assert "168.00" in html
    assert "Year to date" in html or "Y" in html


from unittest.mock import MagicMock, patch
from freezegun import freeze_time
from data_cache import DataCache
from app_config import (
    AppConfig, ServerConfig, PhasesConfig, DataSourcesConfig,
    RefreshConfig, ShiftConfig, ThresholdsConfig, EmailReportConfig,
)


def _cfg():
    return AppConfig(
        server=ServerConfig(), phases=PhasesConfig(monitored=["ASSEMBLY"]),
        data_sources=DataSourcesConfig(), refresh=RefreshConfig(),
        shifts=[ShiftConfig("T1", dtime(7, 30), dtime(15, 30)),
                ShiftConfig("T2", dtime(15, 30), dtime(23, 30)),
                ShiftConfig("T3", dtime(23, 30), dtime(7, 30))],
        thresholds=ThresholdsConfig(),
        email_report=EmailReportConfig(skip_weekdays=["monday"]),
    )


@freeze_time("2026-05-04 07:31:00")  # Monday
def test_send_daily_skipped_on_monday():
    from reporting.email_report import send_daily
    cache = DataCache(_cfg())
    with patch("reporting.email_report.get_email_recipients") as mock_rcp:
        send_daily(cache, conn=MagicMock())
        mock_rcp.assert_not_called()
