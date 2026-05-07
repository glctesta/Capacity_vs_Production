# tests/test_email_anomalies.py
from datetime import date as _date, datetime, time as dtime
from unittest.mock import MagicMock, patch
from freezegun import freeze_time
from app_config import (
    AppConfig, ServerConfig, PhasesConfig, DataSourcesConfig,
    RefreshConfig, ShiftConfig, ThresholdsConfig, EmailReportConfig,
)
from data_cache import DataCache
from reporting.email_anomalies import (
    generate_anomaly_subject, generate_anomaly_plain_body, generate_anomaly_html_body,
    send_anomaly_alert,
)


def _cfg():
    return AppConfig(
        server=ServerConfig(), phases=PhasesConfig(monitored=["ASSEMBLY"]),
        data_sources=DataSourcesConfig(), refresh=RefreshConfig(),
        shifts=[
            ShiftConfig("T1", dtime(7, 30), dtime(15, 30)),
            ShiftConfig("T2", dtime(15, 30), dtime(23, 30)),
            ShiftConfig("T3", dtime(23, 30), dtime(7, 30)),
        ],
        thresholds=ThresholdsConfig(), email_report=EmailReportConfig(),
    )


def test_subject_format():
    subj = generate_anomaly_subject(
        "[Production Efficiency]", "T1", _date(2026, 5, 7), 5,
    )
    assert "T1" in subj
    assert "2026-05-07" in subj
    assert "5 issue" in subj


def test_plain_body_groups_by_category():
    anomalies = [
        {"category": "missing_cycle", "order_number": "ORD1",
         "phase_name": "ASSEMBLY", "product_code": "P1",
         "detail": "no cycle"},
        {"category": "unresolved_order", "order_number": "ORD2",
         "phase_name": "FCT", "product_code": "",
         "detail": "order not found"},
    ]
    body = generate_anomaly_plain_body(_date(2026, 5, 7), "T1", anomalies)
    assert "MISSING_CYCLE (1)" in body
    assert "UNRESOLVED_ORDER (1)" in body
    assert "ORD1" in body and "ORD2" in body


def test_html_body_renders():
    anomalies = [
        {"category": "missing_cycle", "order_number": "ORD1",
         "phase_name": "ASSEMBLY", "product_code": "P1",
         "detail": "no cycle"},
    ]
    html = generate_anomaly_html_body(_date(2026, 5, 7), "T1", anomalies)
    assert "<table" in html
    assert "ORD1" in html


@freeze_time("2026-05-07 07:32:00")
def test_send_anomaly_alert_skips_when_no_anomalies():
    cache = DataCache(_cfg())
    with patch("reporting.email_anomalies.get_anomalies_for_date", return_value=[]), \
         patch("reporting.email_anomalies.get_email_recipients") as mock_rcp:
        send_anomaly_alert(cache, conn=MagicMock())
        mock_rcp.assert_not_called()


@freeze_time("2026-05-07 07:32:00")
def test_send_anomaly_alert_skips_when_no_recipients():
    cache = DataCache(_cfg())
    with patch("reporting.email_anomalies.get_anomalies_for_date") as mock_anom, \
         patch("reporting.email_anomalies.get_email_recipients", return_value=[]):
        mock_anom.return_value = [
            {"category": "missing_cycle", "order_number": "X",
             "phase_name": "ASSEMBLY", "product_code": "P", "detail": "x"},
        ]
        # Should not raise; just logs and returns
        send_anomaly_alert(cache, conn=MagicMock())
