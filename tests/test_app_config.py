# tests/test_app_config.py
import json
import os
from pathlib import Path
import pytest
from app_config import load_config


def test_load_config_from_file(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({
        "server": {"host": "127.0.0.1", "port": 9000},
        "phases": {
            "monitored": ["A", "B"],
            "rotation_interval_seconds": 30,
            "manual_navigation_pause_seconds": 90
        },
        "data_sources": {
            "routing_folder": "T:\\D365 routing data",
            "routing_sheet": "Articles and phases",
            "planning_folder": "T:\\Planning",
            "planning_sheet": "PlanningMachine"
        },
        "refresh": {
            "routing_daily_at": "07:00",
            "planning_minutes": 30,
            "production_seconds": 60,
            "frontend_polling_seconds": 30
        },
        "shifts": [
            {"code": "T1", "start": "07:30", "end": "15:30"},
            {"code": "T2", "start": "15:30", "end": "23:30"},
            {"code": "T3", "start": "23:30", "end": "07:30"}
        ],
        "thresholds": {"green_min_coverage_pct": 95, "yellow_min_coverage_pct": 80},
        "email_report": {
            "enabled": True,
            "send_at": "07:31",
            "skip_weekdays": ["monday"],
            "recipients_query_attribute": "Sys_email_efficienze",
            "subject_prefix": "[Production Efficiency]"
        },
        "logo_path": "static/Logo.png"
    }), encoding="utf-8")
    cfg = load_config(str(p))
    assert cfg.server.port == 9000
    assert cfg.phases.monitored == ["A", "B"]
    assert cfg.shifts[2].code == "T3"
    assert cfg.thresholds.green_min_coverage_pct == 95
    assert cfg.email_report.skip_weekdays == ["monday"]


def test_load_config_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(str(tmp_path / "missing.json"))


def test_load_config_invalid_json_raises(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("not valid json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_config(str(p))
