"""Load runtime config from JSON into typed dataclasses."""
import json
from dataclasses import dataclass, field
from datetime import time as dtime
from pathlib import Path
from typing import Dict, List


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8087


@dataclass
class PhasesConfig:
    monitored: List[str] = field(default_factory=list)
    rotation_interval_seconds: int = 20
    manual_navigation_pause_seconds: int = 60
    # Translation table: any non-canonical phase name → canonical name.
    # Applied to routing Excel column headers and planning Excel column E values.
    # Identity mappings (X → X) can be omitted; missing entries pass through unchanged.
    aliases: Dict[str, str] = field(default_factory=dict)


@dataclass
class DataSourcesConfig:
    routing_folder: str = "T:\\D365 routing data"
    routing_sheet: str = "Articles and phases"
    planning_folder: str = "T:\\Planning"
    planning_sheet: str = "PlanningMachine"


@dataclass
class RefreshConfig:
    routing_daily_at: str = "07:00"
    planning_minutes: int = 30
    production_seconds: int = 60
    rolling_minutes: int = 5
    frontend_polling_seconds: int = 30


@dataclass
class ShiftConfig:
    code: str
    start: dtime
    end: dtime


@dataclass
class ThresholdsConfig:
    green_min_coverage_pct: int = 95
    yellow_min_coverage_pct: int = 80


@dataclass
class EmailReportConfig:
    enabled: bool = True
    send_at: str = "07:31"
    skip_weekdays: List[str] = field(default_factory=lambda: ["monday"])
    recipients_query_attribute: str = "Sys_email_efficienze"
    subject_prefix: str = "[Production Efficiency]"


@dataclass
class AppConfig:
    server: ServerConfig
    phases: PhasesConfig
    data_sources: DataSourcesConfig
    refresh: RefreshConfig
    shifts: List[ShiftConfig]
    thresholds: ThresholdsConfig
    email_report: EmailReportConfig
    logo_path: str = "static/Logo.png"


def _parse_time(s: str) -> dtime:
    h, m = s.strip().split(":")
    return dtime(int(h), int(m))


def load_config(path: str = "config.json") -> AppConfig:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with p.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    return AppConfig(
        server=ServerConfig(**raw.get("server", {})),
        phases=PhasesConfig(**raw.get("phases", {})),
        data_sources=DataSourcesConfig(**raw.get("data_sources", {})),
        refresh=RefreshConfig(**raw.get("refresh", {})),
        shifts=[
            ShiftConfig(code=s["code"],
                        start=_parse_time(s["start"]),
                        end=_parse_time(s["end"]))
            for s in raw.get("shifts", [])
        ],
        thresholds=ThresholdsConfig(**raw.get("thresholds", {})),
        email_report=EmailReportConfig(**raw.get("email_report", {})),
        logo_path=raw.get("logo_path", "static/Logo.png"),
    )
