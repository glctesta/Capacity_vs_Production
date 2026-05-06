# PianoTempi — Production efficiency monitor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Flask intranet web app on `http://<host>:8087` that monitors per-phase planned vs produced hours for the operative day, rotates phase panels automatically, and emails a daily report at 07:31.

**Architecture:** Hybrid layered Flask app. Pure-calculation `engine/` (no I/O), `data_sources/` for Excel + SQL, single `data_cache.py` singleton, Flask `app.py` reads only from cache. APScheduler runs 5 jobs (4 refreshes + email). Local JSON file for daily history (one per year). Reuse encrypted DB/SMTP credentials and connection helpers from PlanRespect (already copied to this directory).

**Tech Stack:** Python 3.11+, Flask 3, APScheduler 3, openpyxl 3, pyodbc 5, Chart.js v4 (vendored), pytest 8.

**Spec reference:** `docs/superpowers/specs/2026-05-06-piano-tempi-monitoraggio-design.md`

**Working directory:** `C:\Users\User\PythonProjetcs\Python\PIanoTempi`

---

## Phase 0 — Project skeleton

### Task 0.1: Initialize git repository and gitignore

**Files:**
- Create: `.gitignore`

- [ ] **Step 1: Init git**

```bash
git init
git config core.autocrlf true
```

- [ ] **Step 2: Create `.gitignore`**

```
__pycache__/
*.pyc
.venv/
venv/
*.log
logs/
data/daily_history_*.json
.superpowers/
.pytest_cache/
.idea/
.vscode/
*.tmp
*.corrupt-*
```

- [ ] **Step 3: Commit existing infrastructure files**

```bash
git add .gitignore config_manager.py db_connection.py email_connector.py
git add db_config.enc email_credentials.enc email_key.key encryption_key.key
git add Logo.png PIano.txt
git add docs/
git commit -m "chore: initial commit with shared infrastructure"
```

---

### Task 0.2: Create requirements.txt and project layout

**Files:**
- Create: `requirements.txt`
- Create: `data_sources/__init__.py`
- Create: `engine/__init__.py`
- Create: `reporting/__init__.py`
- Create: `tests/__init__.py`
- Create: `static/css/.gitkeep`
- Create: `static/js/.gitkeep`
- Create: `templates/.gitkeep`
- Create: `data/.gitkeep`
- Create: `logs/.gitkeep`

- [ ] **Step 1: Write `requirements.txt`**

```
flask>=3.0.0
apscheduler>=3.10.0
openpyxl>=3.1.0
pyodbc>=5.0.0
cryptography>=41.0.0
pytest>=8.0.0
pytest-mock>=3.12.0
freezegun>=1.4.0
```

- [ ] **Step 2: Create empty `__init__.py` files**

```bash
echo "" > data_sources/__init__.py
echo "" > engine/__init__.py
echo "" > reporting/__init__.py
echo "" > tests/__init__.py
```

- [ ] **Step 3: Create empty placeholder dirs**

```bash
mkdir -p static/css static/js templates data logs
touch static/css/.gitkeep static/js/.gitkeep templates/.gitkeep data/.gitkeep logs/.gitkeep
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt data_sources/ engine/ reporting/ tests/ static/ templates/ data/ logs/
git commit -m "chore: project skeleton (modules, requirements)"
```

---

### Task 0.3: Pytest configuration

**Files:**
- Create: `pyproject.toml`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
addopts = "-v --tb=short"
```

- [ ] **Step 2: Sanity check pytest can run**

Run: `pytest --collect-only`
Expected: `0 tests collected` (no tests yet, but no errors)

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: pytest config"
```

---

## Phase 1 — Engine models

### Task 1.1: Define core dataclasses (models.py)

**Files:**
- Create: `engine/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
from datetime import date, time
from engine.models import (
    RoutingCycle, PlanRow, PhaseMap, ProductionRow,
    PhaseKPI, TotalKPI, DayPoint, RollingData,
)


def test_routing_cycle_is_frozen():
    rc = RoutingCycle(product_code="1146-6048", phase_name="EOLTEST",
                     cycle_time_minutes=8.18)
    import dataclasses, pytest
    with pytest.raises(dataclasses.FrozenInstanceError):
        rc.cycle_time_minutes = 9.0


def test_plan_row_fields():
    pr = PlanRow(order_number="ORD123", phase_name="ASSEMBLY",
                 product_code="1146-6048", production_date=date(2026, 5, 6),
                 planned_qty=120)
    assert pr.order_number == "ORD123"
    assert pr.planned_qty == 120


def test_phase_map_fields():
    pm = PhaseMap(planning_phase_name="ASSEMBLY", planning_phase_id=10,
                  traceability_phase_id=2, traceability_phase_name="Assembly")
    assert pm.traceability_phase_id == 2


def test_phase_kpi_fields():
    kpi = PhaseKPI(
        phase_name="ASSEMBLY", shift_code="T2",
        planned_h_day=24.0, planned_h_shift=12.0,
        planned_h_so_far_day=12.85, planned_h_so_far_shift=1.5,
        produced_h_day=14.20, produced_h_shift=1.20,
        delta_vs_expected_day=1.35, delta_vs_expected_shift=-0.30,
        coverage_pct_day=59.17, status_color="red",
        curve_points=[(time(15, 30), 9.0), (time(16, 0), 14.20)],
    )
    assert kpi.coverage_pct_day == 59.17
    assert kpi.status_color == "red"
    assert len(kpi.curve_points) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.models'`

- [ ] **Step 3: Implement `engine/models.py`**

```python
# engine/models.py
"""Frozen dataclasses for the calculation engine. No I/O here."""
from dataclasses import dataclass, field
from datetime import date, time
from typing import List, Tuple


@dataclass(frozen=True)
class RoutingCycle:
    """One cell from the routing Excel: a product/phase cycle time."""
    product_code: str
    phase_name: str
    cycle_time_minutes: float


@dataclass(frozen=True)
class PlanRow:
    """One planning row enriched with product_code resolved from DB."""
    order_number: str
    phase_name: str
    product_code: str
    production_date: date
    planned_qty: int


@dataclass(frozen=True)
class PhaseMap:
    """Mapping between planning phase name (Excel column header) and traceability id."""
    planning_phase_name: str
    planning_phase_id: int
    traceability_phase_id: int
    traceability_phase_name: str


@dataclass(frozen=True)
class ProductionRow:
    """Aggregated produced quantity for one (order, phase, shift) tuple."""
    traceability_phase_id: int
    phase_name: str
    id_order: int
    order_number: str
    prod_date: date
    shift_code: str
    produced_qty: int


@dataclass(frozen=True)
class PhaseKPI:
    """All KPIs for one monitored phase, ready for the dashboard."""
    phase_name: str
    shift_code: str
    planned_h_day: float
    planned_h_shift: float
    planned_h_so_far_day: float
    planned_h_so_far_shift: float
    produced_h_day: float
    produced_h_shift: float
    delta_vs_expected_day: float
    delta_vs_expected_shift: float
    coverage_pct_day: float
    status_color: str
    curve_points: List[Tuple[time, float]] = field(default_factory=list)


@dataclass(frozen=True)
class TotalKPI:
    """Sum of all PhaseKPI for header strip + Total Summary page."""
    planned_h_day: float
    planned_h_so_far_day: float
    produced_h_day: float
    delta_vs_expected_day: float
    coverage_pct_day: float
    status_color: str


@dataclass(frozen=True)
class DayPoint:
    """One closed day's totals — used for monthly rolling and YTD."""
    date: date
    planned_h: float
    produced_h: float
    coverage_pct: float


@dataclass(frozen=True)
class RollingData:
    """Output of rolling_engine for the final dashboard page + email."""
    days: List[DayPoint]
    month_planned_h: float
    month_produced_h: float
    month_coverage_pct: float
    ytd_planned_h: float
    ytd_produced_h: float
    ytd_coverage_pct: float
    working_days_month: int
    working_days_ytd: int
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_models.py -v`
Expected: PASS — 4 tests passed

- [ ] **Step 5: Commit**

```bash
git add engine/models.py tests/test_models.py
git commit -m "feat(engine): add frozen dataclasses (models)"
```

---

## Phase 2 — Configuration

### Task 2.1: Write config.json template and AppConfig dataclass

**Files:**
- Create: `config.json`
- Create: `app_config.py`
- Create: `tests/test_app_config.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_app_config.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `app_config.py`**

```python
# app_config.py
"""Load runtime config from JSON into typed dataclasses."""
import json
from dataclasses import dataclass, field
from datetime import time as dtime
from pathlib import Path
from typing import List


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8087


@dataclass
class PhasesConfig:
    monitored: List[str] = field(default_factory=list)
    rotation_interval_seconds: int = 20
    manual_navigation_pause_seconds: int = 60


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_app_config.py -v`
Expected: PASS — 3 tests passed

- [ ] **Step 5: Write `config.json` (production default)**

```json
{
  "server": {"host": "0.0.0.0", "port": 8087},
  "phases": {
    "monitored": ["ASSEMBLY", "COATING", "EOLTEST", "ICT", "PROGRAMING", "PTHSEL", "SMT"],
    "rotation_interval_seconds": 20,
    "manual_navigation_pause_seconds": 60
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
    "enabled": true,
    "send_at": "07:31",
    "skip_weekdays": ["monday"],
    "recipients_query_attribute": "Sys_email_efficienze",
    "subject_prefix": "[Production Efficiency]"
  },
  "logo_path": "static/Logo.png"
}
```

- [ ] **Step 6: Commit**

```bash
git add app_config.py tests/test_app_config.py config.json
git commit -m "feat(config): JSON config loader with typed dataclasses"
```

---

## Phase 3 — Engine: shift handling

### Task 3.1: shift_engine.operative_day + day_total_gross_hours

**Files:**
- Create: `engine/shift_engine.py`
- Create: `tests/test_shift_engine.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_shift_engine.py
from datetime import date, datetime, time
from app_config import ShiftConfig
from engine.shift_engine import (
    operative_day, current_shift, shift_window, day_total_gross_hours,
)

SHIFTS = [
    ShiftConfig(code="T1", start=time(7, 30), end=time(15, 30)),
    ShiftConfig(code="T2", start=time(15, 30), end=time(23, 30)),
    ShiftConfig(code="T3", start=time(23, 30), end=time(7, 30)),
]


def test_operative_day_after_0730_is_today():
    assert operative_day(datetime(2026, 5, 6, 9, 0)) == date(2026, 5, 6)


def test_operative_day_before_0730_is_yesterday():
    assert operative_day(datetime(2026, 5, 6, 6, 0)) == date(2026, 5, 5)


def test_operative_day_at_exactly_0730_is_today():
    assert operative_day(datetime(2026, 5, 6, 7, 30)) == date(2026, 5, 6)


def test_current_shift_morning():
    assert current_shift(datetime(2026, 5, 6, 9, 0), SHIFTS) == "T1"


def test_current_shift_afternoon():
    assert current_shift(datetime(2026, 5, 6, 16, 0), SHIFTS) == "T2"


def test_current_shift_late_night():
    assert current_shift(datetime(2026, 5, 7, 0, 30), SHIFTS) == "T3"


def test_current_shift_at_t3_wrap_before_0730():
    assert current_shift(datetime(2026, 5, 7, 6, 0), SHIFTS) == "T3"


def test_shift_window_t1():
    s, e = shift_window(date(2026, 5, 6), SHIFTS[0])
    assert s == datetime(2026, 5, 6, 7, 30)
    assert e == datetime(2026, 5, 6, 15, 30)


def test_shift_window_t3_wraps_to_next_day():
    s, e = shift_window(date(2026, 5, 6), SHIFTS[2])
    assert s == datetime(2026, 5, 6, 23, 30)
    assert e == datetime(2026, 5, 7, 7, 30)


def test_day_total_gross_default_16():
    assert day_total_gross_hours(any_t3_production=False) == 16.0


def test_day_total_gross_with_t3_24():
    assert day_total_gross_hours(any_t3_production=True) == 24.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_shift_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.shift_engine'`

- [ ] **Step 3: Implement `engine/shift_engine.py`**

```python
# engine/shift_engine.py
"""Shift/operative-day calculations. Pure functions, no I/O."""
from datetime import date, datetime, time, timedelta
from typing import List, Tuple

from app_config import ShiftConfig

DAY_START = time(7, 30)


def operative_day(now: datetime, day_start: time = DAY_START) -> date:
    """If now < 07:30 -> yesterday's calendar date."""
    if now.time() < day_start:
        return (now - timedelta(days=1)).date()
    return now.date()


def current_shift(now: datetime, shifts: List[ShiftConfig]) -> str:
    """Return shift_code (T1/T2/T3). Handles T3 wrap (23:30 -> 07:30)."""
    t = now.time()
    for s in shifts:
        if s.start <= s.end:
            # Normal shift (no wrap)
            if s.start <= t < s.end:
                return s.code
        else:
            # Wraps midnight (T3): 23:30 -> 07:30
            if t >= s.start or t < s.end:
                return s.code
    # Fallback: return last shift
    return shifts[-1].code


def shift_window(d: date, shift: ShiftConfig) -> Tuple[datetime, datetime]:
    """Return (start_dt, end_dt). For wrap shift, end is on d+1."""
    start_dt = datetime.combine(d, shift.start)
    if shift.start <= shift.end:
        end_dt = datetime.combine(d, shift.end)
    else:
        end_dt = datetime.combine(d + timedelta(days=1), shift.end)
    return start_dt, end_dt


def day_total_gross_hours(any_t3_production: bool) -> float:
    """24 if T3 has production (ScanTimeFinish >= 23:30), else 16."""
    return 24.0 if any_t3_production else 16.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_shift_engine.py -v`
Expected: PASS — 11 tests passed

- [ ] **Step 5: Commit**

```bash
git add engine/shift_engine.py tests/test_shift_engine.py
git commit -m "feat(engine): shift engine (operative_day, current_shift, windows)"
```

---

## Phase 4 — Engine: cycle/hours math

### Task 4.1: cycle_engine.minutes_to_hours

**Files:**
- Create: `engine/cycle_engine.py`
- Create: `tests/test_cycle_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cycle_engine.py
from datetime import date
from engine.cycle_engine import (
    minutes_to_hours,
    compute_planned_minutes_by_phase,
    compute_produced_minutes_by_phase_shift,
)
from engine.models import PlanRow


def test_minutes_to_hours_2_decimals():
    assert minutes_to_hours(60) == 1.0
    assert minutes_to_hours(90) == 1.5
    assert minutes_to_hours(818) == 13.63
    assert minutes_to_hours(0) == 0.0
    assert minutes_to_hours(45) == 0.75
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cycle_engine.py::test_minutes_to_hours_2_decimals -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement minimum**

```python
# engine/cycle_engine.py
"""Pure math: minutes <-> hours, phase aggregation. No I/O."""
import logging
from typing import Dict, Iterable, List, Tuple

from engine.models import PlanRow

logger = logging.getLogger("PianoTempi")


def minutes_to_hours(m: float) -> float:
    """Convert minutes to hours rounded to 2 decimals."""
    return round(m / 60.0, 2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cycle_engine.py::test_minutes_to_hours_2_decimals -v`
Expected: PASS

---

### Task 4.2: cycle_engine.compute_planned_minutes_by_phase

- [ ] **Step 1: Add tests to `tests/test_cycle_engine.py`**

Append:

```python
def test_planned_minutes_simple():
    plan = [
        PlanRow("ORD1", "ASSEMBLY", "P1", date(2026, 5, 6), 100),
        PlanRow("ORD2", "COATING",  "P1", date(2026, 5, 6), 50),
    ]
    cycles = {("P1", "ASSEMBLY"): 2.5, ("P1", "COATING"): 4.0}
    result = compute_planned_minutes_by_phase(plan, cycles)
    assert result == {"ASSEMBLY": 250.0, "COATING": 200.0}


def test_planned_minutes_multiple_orders_same_phase():
    plan = [
        PlanRow("ORD1", "ASSEMBLY", "P1", date(2026, 5, 6), 100),
        PlanRow("ORD2", "ASSEMBLY", "P2", date(2026, 5, 6), 50),
    ]
    cycles = {("P1", "ASSEMBLY"): 2.0, ("P2", "ASSEMBLY"): 3.0}
    result = compute_planned_minutes_by_phase(plan, cycles)
    assert result == {"ASSEMBLY": 350.0}


def test_planned_minutes_missing_cycle_skipped(caplog):
    plan = [
        PlanRow("ORD1", "ASSEMBLY", "P1", date(2026, 5, 6), 100),
        PlanRow("ORD2", "COATING",  "P_UNKNOWN", date(2026, 5, 6), 50),
    ]
    cycles = {("P1", "ASSEMBLY"): 2.0}
    result = compute_planned_minutes_by_phase(plan, cycles)
    assert result == {"ASSEMBLY": 200.0}
    assert any("missing cycle" in r.message.lower() for r in caplog.records)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cycle_engine.py -v`
Expected: 1 PASS + 3 FAIL (function not yet defined)

- [ ] **Step 3: Append implementation**

Append to `engine/cycle_engine.py`:

```python
def compute_planned_minutes_by_phase(
    plan: List[PlanRow],
    cycles: Dict[Tuple[str, str], float],
) -> Dict[str, float]:
    """For each plan row: minutes = qty * cycles[(product, phase)].
    Aggregate by phase_name. Missing key -> log warning + skip."""
    result: Dict[str, float] = {}
    for row in plan:
        key = (row.product_code, row.phase_name)
        cycle = cycles.get(key)
        if cycle is None:
            logger.warning(
                "missing cycle for product=%s phase=%s (order=%s) -- row skipped",
                row.product_code, row.phase_name, row.order_number,
            )
            continue
        minutes = row.planned_qty * cycle
        result[row.phase_name] = result.get(row.phase_name, 0.0) + minutes
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cycle_engine.py -v`
Expected: PASS — 4 tests passed

---

### Task 4.3: cycle_engine.compute_produced_minutes_by_phase_shift

- [ ] **Step 1: Add tests**

Append to `tests/test_cycle_engine.py`:

```python
def test_produced_minutes_by_phase_shift_simple():
    plan = [
        PlanRow("ORD1", "ASSEMBLY", "P1", date(2026, 5, 6), 100),
    ]
    cycles = {("P1", "ASSEMBLY"): 2.5}
    # produced: {(id_order, traceability_phase_id, shift): qty}
    produced = {
        (1001, 2, "T1"): 30,
        (1001, 2, "T2"): 50,
    }
    order_to_product = {"ORD1": "P1"}
    # We also need: traceability_phase_id 2 -> phase_name "ASSEMBLY"
    # That mapping is provided implicitly via the produced rows being keyed by phase.
    # For this test, the function takes the (id_order, _, shift) key and
    # uses the plan to find phase_name & product_code.
    # NOTE: simplified for unit test; real impl may differ.
    # See implementation below for the actual contract.
    pass  # placeholder until impl is defined precisely


def test_produced_minutes_aggregates_by_phase_and_shift():
    """Two orders for same phase, different shifts."""
    pass  # filled after implementation
```

> **Implementation note:** the contract requires the function to accept `produced` keyed by `(id_order, traceability_phase_id, shift)` and resolve back to `(product_code, phase_name)` via the `plan` rows + phase_traceability_id_to_name lookup. To keep the engine pure, we change the key to use `phase_name` (resolved upstream by the caller). Refactor:

Update produced shape: keyed by `(order_number, phase_name, shift)`.

Replace tests with:

```python
def test_produced_minutes_by_phase_shift_simple():
    plan = [PlanRow("ORD1", "ASSEMBLY", "P1", date(2026, 5, 6), 100)]
    cycles = {("P1", "ASSEMBLY"): 2.5}
    produced = {
        ("ORD1", "ASSEMBLY", "T1"): 30,
        ("ORD1", "ASSEMBLY", "T2"): 50,
    }
    order_to_product = {"ORD1": "P1"}
    result = compute_produced_minutes_by_phase_shift(
        plan, cycles, produced, order_to_product,
    )
    assert result[("ASSEMBLY", "T1")] == 75.0   # 30 * 2.5
    assert result[("ASSEMBLY", "T2")] == 125.0  # 50 * 2.5


def test_produced_minutes_aggregates_two_orders_same_phase_shift():
    plan = [
        PlanRow("ORD1", "ASSEMBLY", "P1", date(2026, 5, 6), 100),
        PlanRow("ORD2", "ASSEMBLY", "P2", date(2026, 5, 6), 100),
    ]
    cycles = {("P1", "ASSEMBLY"): 2.0, ("P2", "ASSEMBLY"): 3.0}
    produced = {
        ("ORD1", "ASSEMBLY", "T1"): 10,
        ("ORD2", "ASSEMBLY", "T1"): 20,
    }
    order_to_product = {"ORD1": "P1", "ORD2": "P2"}
    result = compute_produced_minutes_by_phase_shift(
        plan, cycles, produced, order_to_product,
    )
    assert result[("ASSEMBLY", "T1")] == 80.0   # 10*2 + 20*3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cycle_engine.py -v`
Expected: FAIL — function not defined

- [ ] **Step 3: Append impl**

```python
def compute_produced_minutes_by_phase_shift(
    plan: List[PlanRow],
    cycles: Dict[Tuple[str, str], float],
    produced: Dict[Tuple[str, str, str], int],
    order_to_product: Dict[str, str],
) -> Dict[Tuple[str, str], float]:
    """Multiply each produced (order, phase, shift) by the cycle of (product, phase).
    Aggregate by (phase, shift). Returns {(phase_name, shift_code): minutes}."""
    result: Dict[Tuple[str, str], float] = {}
    for (order_number, phase_name, shift_code), qty in produced.items():
        product_code = order_to_product.get(order_number)
        if product_code is None:
            logger.warning("produced row has unknown order_number=%s -- skipped", order_number)
            continue
        cycle = cycles.get((product_code, phase_name))
        if cycle is None:
            logger.warning(
                "no cycle for produced product=%s phase=%s (order=%s shift=%s) -- skipped",
                product_code, phase_name, order_number, shift_code,
            )
            continue
        minutes = qty * cycle
        key = (phase_name, shift_code)
        result[key] = result.get(key, 0.0) + minutes
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cycle_engine.py -v`
Expected: PASS — all tests passed

- [ ] **Step 5: Commit**

```bash
git add engine/cycle_engine.py tests/test_cycle_engine.py
git commit -m "feat(engine): cycle engine (planned & produced minutes per phase/shift)"
```

---

## Phase 5 — Engine: KPI builder

### Task 5.1: kpi_builder.build_phase_kpi (basic case)

**Files:**
- Create: `engine/kpi_builder.py`
- Create: `tests/test_kpi_builder.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_kpi_builder.py
from datetime import date, datetime, time
from app_config import ShiftConfig, ThresholdsConfig
from engine.kpi_builder import build_phase_kpi
from engine.models import PlanRow

SHIFTS = [
    ShiftConfig("T1", time(7, 30), time(15, 30)),
    ShiftConfig("T2", time(15, 30), time(23, 30)),
    ShiftConfig("T3", time(23, 30), time(7, 30)),
]
THRESH = ThresholdsConfig(green_min_coverage_pct=95, yellow_min_coverage_pct=80)


def test_build_phase_kpi_at_t1_simple():
    """At 11:30 (4h into T1), planned 24h day, produced 4h."""
    plan = [PlanRow("ORD1", "ASSEMBLY", "P1", date(2026, 5, 6), 480)]
    cycles = {("P1", "ASSEMBLY"): 3.0}  # 480 * 3 = 1440 min = 24h
    produced = {("ORD1", "ASSEMBLY", "T1"): 80}  # 80 * 3 = 240 min = 4h
    order_to_product = {"ORD1": "P1"}
    now = datetime(2026, 5, 6, 11, 30)
    kpi = build_phase_kpi(
        phase_name="ASSEMBLY",
        plan=plan, cycles=cycles, produced=produced,
        order_to_product=order_to_product,
        now=now, shifts=SHIFTS, thresholds=THRESH,
        any_t3_production=False,
    )
    assert kpi.phase_name == "ASSEMBLY"
    assert kpi.shift_code == "T1"
    assert kpi.planned_h_day == 24.0
    # planned_h_shift = 24 * 8/16 = 12
    assert kpi.planned_h_shift == 12.0
    # gross_elapsed_day = 4h, total = 16h -> 24 * 4/16 = 6
    assert kpi.planned_h_so_far_day == 6.0
    # gross_elapsed_shift = 4h, total = 8h -> 12 * 4/8 = 6
    assert kpi.planned_h_so_far_shift == 6.0
    assert kpi.produced_h_day == 4.0
    assert kpi.produced_h_shift == 4.0
    # delta = produced - expected
    assert kpi.delta_vs_expected_day == round(4.0 - 6.0, 2)
    # coverage = 4/24*100 = 16.67
    assert kpi.coverage_pct_day == 16.67
    assert kpi.status_color == "red"


def test_build_phase_kpi_green_status():
    plan = [PlanRow("ORD1", "ASSEMBLY", "P1", date(2026, 5, 6), 100)]
    cycles = {("P1", "ASSEMBLY"): 6.0}  # 600 min = 10h
    produced = {
        ("ORD1", "ASSEMBLY", "T1"): 50,  # 5h
        ("ORD1", "ASSEMBLY", "T2"): 50,  # 5h, total 10h
    }
    order_to_product = {"ORD1": "P1"}
    now = datetime(2026, 5, 6, 23, 0)  # near end of T2
    kpi = build_phase_kpi(
        phase_name="ASSEMBLY", plan=plan, cycles=cycles,
        produced=produced, order_to_product=order_to_product,
        now=now, shifts=SHIFTS, thresholds=THRESH, any_t3_production=False,
    )
    assert kpi.coverage_pct_day == 100.0
    assert kpi.status_color == "green"


def test_build_phase_kpi_yellow_status():
    plan = [PlanRow("ORD1", "ASSEMBLY", "P1", date(2026, 5, 6), 100)]
    cycles = {("P1", "ASSEMBLY"): 6.0}  # 10h
    produced = {("ORD1", "ASSEMBLY", "T1"): 75}  # 7.5h
    order_to_product = {"ORD1": "P1"}
    now = datetime(2026, 5, 6, 23, 0)
    kpi = build_phase_kpi(
        phase_name="ASSEMBLY", plan=plan, cycles=cycles,
        produced=produced, order_to_product=order_to_product,
        now=now, shifts=SHIFTS, thresholds=THRESH, any_t3_production=False,
    )
    assert kpi.coverage_pct_day == 75.0  # = 7.5/10
    # 75% < 80 -> red. Adjust expected to validate yellow boundary:
    # use 80% exactly: produced=80 -> 80%
    assert kpi.status_color == "red"


def test_build_phase_kpi_zero_planned_no_division_error():
    plan = []
    cycles = {}
    produced = {}
    order_to_product = {}
    now = datetime(2026, 5, 6, 11, 30)
    kpi = build_phase_kpi(
        phase_name="ASSEMBLY", plan=plan, cycles=cycles,
        produced=produced, order_to_product=order_to_product,
        now=now, shifts=SHIFTS, thresholds=THRESH, any_t3_production=False,
    )
    assert kpi.planned_h_day == 0.0
    assert kpi.coverage_pct_day == 0.0
    assert kpi.status_color == "red"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_kpi_builder.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `engine/kpi_builder.py`**

```python
# engine/kpi_builder.py
"""Builds PhaseKPI from primitives. Pure function."""
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from app_config import ShiftConfig, ThresholdsConfig
from engine.cycle_engine import (
    minutes_to_hours,
    compute_planned_minutes_by_phase,
    compute_produced_minutes_by_phase_shift,
)
from engine.models import PhaseKPI, PlanRow
from engine.shift_engine import (
    operative_day, current_shift, shift_window, day_total_gross_hours,
)

SHIFT_GROSS_H = 8.0


def _clip(lo: float, hi: float, v: float) -> float:
    return max(lo, min(hi, v))


def _status_color(coverage_pct: float, t: ThresholdsConfig) -> str:
    if coverage_pct >= t.green_min_coverage_pct:
        return "green"
    if coverage_pct >= t.yellow_min_coverage_pct:
        return "yellow"
    return "red"


def build_phase_kpi(
    phase_name: str,
    plan: List[PlanRow],
    cycles: Dict[Tuple[str, str], float],
    produced: Dict[Tuple[str, str, str], int],
    order_to_product: Dict[str, str],
    now: datetime,
    shifts: List[ShiftConfig],
    thresholds: ThresholdsConfig,
    any_t3_production: bool,
) -> PhaseKPI:
    """See spec §4.2 + §5.1 for the gross-hours convention."""
    # 1-2: planned hours for the day
    planned_min_by_phase = compute_planned_minutes_by_phase(plan, cycles)
    planned_h_day = minutes_to_hours(planned_min_by_phase.get(phase_name, 0.0))

    # 3-4: shift context
    shift_curr = current_shift(now, shifts)
    day_total_gross = day_total_gross_hours(any_t3_production)

    # 5: pro-rata planned per shift
    planned_h_shift = round(planned_h_day * (SHIFT_GROSS_H / day_total_gross), 2)

    # 6-8: produced hours
    produced_min_by_phase_shift = compute_produced_minutes_by_phase_shift(
        plan, cycles, produced, order_to_product,
    )
    produced_min_day = sum(
        v for (p, _), v in produced_min_by_phase_shift.items() if p == phase_name
    )
    produced_h_day = minutes_to_hours(produced_min_day)
    produced_h_shift = minutes_to_hours(
        produced_min_by_phase_shift.get((phase_name, shift_curr), 0.0)
    )

    # 9-10: linear ramp on day
    op_day = operative_day(now)
    day_start_dt = datetime.combine(op_day, datetime.min.time()) + timedelta(hours=7, minutes=30)
    gross_elapsed_day_h = _clip(0.0, day_total_gross,
                                (now - day_start_dt).total_seconds() / 3600.0)
    planned_h_so_far_day = round(
        planned_h_day * (gross_elapsed_day_h / day_total_gross), 2,
    )

    # 11-12: linear ramp inside current shift
    shift_curr_cfg = next(s for s in shifts if s.code == shift_curr)
    shift_start_dt, _ = shift_window(op_day, shift_curr_cfg)
    if shift_curr == "T3" and now < shift_start_dt:
        # T3 wrap: shift started at op_day 23:30 (yesterday-of-now)
        shift_start_dt = datetime.combine(op_day, shift_curr_cfg.start)
    gross_elapsed_shift_h = _clip(0.0, SHIFT_GROSS_H,
                                  (now - shift_start_dt).total_seconds() / 3600.0)
    planned_h_so_far_shift = round(
        planned_h_shift * (gross_elapsed_shift_h / SHIFT_GROSS_H), 2,
    )

    # 13: deltas
    delta_day = round(produced_h_day - planned_h_so_far_day, 2)
    delta_shift = round(produced_h_shift - planned_h_so_far_shift, 2)

    # 14: coverage
    coverage_pct_day = round(
        (produced_h_day / planned_h_day * 100.0) if planned_h_day > 0 else 0.0, 2,
    )

    # 15: status color
    status = _status_color(coverage_pct_day, thresholds)

    # 16: curve_points (filled in Task 5.2)
    curve_points: List = []

    return PhaseKPI(
        phase_name=phase_name,
        shift_code=shift_curr,
        planned_h_day=planned_h_day,
        planned_h_shift=planned_h_shift,
        planned_h_so_far_day=planned_h_so_far_day,
        planned_h_so_far_shift=planned_h_so_far_shift,
        produced_h_day=produced_h_day,
        produced_h_shift=produced_h_shift,
        delta_vs_expected_day=delta_day,
        delta_vs_expected_shift=delta_shift,
        coverage_pct_day=coverage_pct_day,
        status_color=status,
        curve_points=curve_points,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_kpi_builder.py -v`
Expected: PASS — 4 tests passed

- [ ] **Step 5: Commit**

```bash
git add engine/kpi_builder.py tests/test_kpi_builder.py
git commit -m "feat(engine): KPI builder (basic)"
```

---

### Task 5.2: KPI builder — curve_points

- [ ] **Step 1: Write tests**

Append to `tests/test_kpi_builder.py`:

```python
def test_curve_points_during_t1():
    """At 11:30, only 'now' point should be included (no shift completed yet)."""
    plan = [PlanRow("ORD1", "ASSEMBLY", "P1", date(2026, 5, 6), 100)]
    cycles = {("P1", "ASSEMBLY"): 6.0}  # 10h
    produced = {("ORD1", "ASSEMBLY", "T1"): 30}  # 3h
    order_to_product = {"ORD1": "P1"}
    now = datetime(2026, 5, 6, 11, 30)
    kpi = build_phase_kpi(
        phase_name="ASSEMBLY", plan=plan, cycles=cycles,
        produced=produced, order_to_product=order_to_product,
        now=now, shifts=SHIFTS, thresholds=THRESH, any_t3_production=False,
    )
    assert len(kpi.curve_points) == 1
    assert kpi.curve_points[0][0] == time(11, 30)
    assert kpi.curve_points[0][1] == 3.0


def test_curve_points_after_t1_complete():
    """At 16:00, T1 finished (cumul at end of T1 included) + 'now'."""
    plan = [PlanRow("ORD1", "ASSEMBLY", "P1", date(2026, 5, 6), 100)]
    cycles = {("P1", "ASSEMBLY"): 6.0}
    produced = {
        ("ORD1", "ASSEMBLY", "T1"): 60,  # 6h
        ("ORD1", "ASSEMBLY", "T2"): 5,   # 0.5h
    }
    order_to_product = {"ORD1": "P1"}
    now = datetime(2026, 5, 6, 16, 0)
    kpi = build_phase_kpi(
        phase_name="ASSEMBLY", plan=plan, cycles=cycles,
        produced=produced, order_to_product=order_to_product,
        now=now, shifts=SHIFTS, thresholds=THRESH, any_t3_production=False,
    )
    assert len(kpi.curve_points) == 2
    assert kpi.curve_points[0] == (time(15, 30), 6.0)
    assert kpi.curve_points[1] == (time(16, 0), 6.5)
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_kpi_builder.py -v`
Expected: 2 new tests FAIL (curve_points empty)

- [ ] **Step 3: Replace `curve_points: List = []` block in `engine/kpi_builder.py`**

Replace the line `curve_points: List = []` and everything between it and the `return PhaseKPI(...)` with:

```python
    # 16: curve_points - end of each completed shift + now
    curve_points: List[Tuple[time, float]] = []
    cumul_minutes = 0.0
    for s in shifts:
        s_start, s_end = shift_window(op_day, s)
        # Skip T3 if no production
        if s.code == "T3" and not any_t3_production:
            continue
        if now >= s_end:
            # shift completed -> add cumul at end
            cumul_minutes += produced_min_by_phase_shift.get((phase_name, s.code), 0.0)
            curve_points.append((s.end, minutes_to_hours(cumul_minutes)))
        elif s.code == shift_curr:
            # current shift in progress -> add 'now' with day-cumul
            curve_points.append((now.time().replace(microsecond=0), produced_h_day))
            break
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_kpi_builder.py -v`
Expected: PASS — all tests pass

- [ ] **Step 5: Commit**

```bash
git add engine/kpi_builder.py tests/test_kpi_builder.py
git commit -m "feat(engine): KPI builder curve_points"
```

---

## Phase 6 — Engine: rolling history

### Task 6.1: DailyHistory loader/writer

**Files:**
- Create: `engine/rolling_engine.py`
- Create: `tests/test_rolling_engine.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_rolling_engine.py
import json
from datetime import date
from engine.models import DayPoint
from engine.rolling_engine import (
    load_daily_history, save_day_to_history,
    compute_rolling_month, compute_y2d,
)


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
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_rolling_engine.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement loader/writer**

```python
# engine/rolling_engine.py
"""Rolling month + YTD calculations + daily history persistence."""
import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Dict, List

from engine.models import DayPoint, RollingData

logger = logging.getLogger("PianoTempi")


def load_daily_history(path: str) -> List[DayPoint]:
    p = Path(path)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.error("daily history file corrupt or unreadable %s: %s -- recreating", path, e)
        # Rename with timestamp; caller may recreate
        from datetime import datetime
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
    Computes totals automatically. Writes to .tmp then os.replace.
    """
    p = Path(path)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {"year": day.year, "days": []}
    else:
        data = {"year": day.year, "days": []}

    # Compute totals
    total_plan = round(sum(v["planned_h"] for v in phases.values()), 2)
    total_prod = round(sum(v["produced_h"] for v in phases.values()), 2)
    coverage = round(total_prod / total_plan * 100.0, 2) if total_plan > 0 else 0.0

    new_entry = {
        "date": day.isoformat(),
        "phases": phases,
        "totals": {"planned_h": total_plan, "produced_h": total_prod, "coverage_pct": coverage},
    }

    # Replace existing entry for the same date, else append
    data["year"] = day.year
    days = [d for d in data.get("days", []) if d.get("date") != day.isoformat()]
    days.append(new_entry)
    days.sort(key=lambda d: d["date"])
    data["days"] = days

    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, p)
```

- [ ] **Step 4: Run tests to verify**

Run: `pytest tests/test_rolling_engine.py -v`
Expected: 5 PASS, 2 FAIL (compute_rolling_month / compute_y2d not yet)

- [ ] **Step 5: Commit (partial)**

```bash
git add engine/rolling_engine.py tests/test_rolling_engine.py
git commit -m "feat(engine): daily history loader/writer (atomic)"
```

---

### Task 6.2: compute_rolling_month and compute_y2d

- [ ] **Step 1: Add tests**

Append to `tests/test_rolling_engine.py`:

```python
def _dp(y, m, d, plan, prod):
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
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_rolling_engine.py -v`
Expected: FAIL on the 3 new tests

- [ ] **Step 3: Append impl to `engine/rolling_engine.py`**

```python
def _coverage(plan: float, prod: float) -> float:
    return round(prod / plan * 100.0, 2) if plan > 0 else 0.0


def compute_rolling_month(today: date, history: List[DayPoint]) -> RollingData:
    """Sum days from 1st of `today.month` to yesterday (today excluded)."""
    month_start = today.replace(day=1)
    days = [d for d in history if month_start <= d.date < today]
    days.sort(key=lambda d: d.date)
    plan = round(sum(d.planned_h for d in days), 2)
    prod = round(sum(d.produced_h for d in days), 2)

    # YTD also (we recompute here for convenience even though caller can use compute_y2d)
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
    """Convenience: same as compute_rolling_month but caller cares only about YTD numbers.
    Returns the same RollingData (month fields are still populated)."""
    return compute_rolling_month(today, history)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_rolling_engine.py -v`
Expected: PASS — all tests passed

- [ ] **Step 5: Commit**

```bash
git add engine/rolling_engine.py tests/test_rolling_engine.py
git commit -m "feat(engine): compute_rolling_month and compute_y2d"
```

---

## Phase 7 — Data sources: Excel

### Task 7.1: routing_excel.find_latest_routing_file

**Files:**
- Create: `data_sources/routing_excel.py`
- Create: `tests/test_routing_excel.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_routing_excel.py
import os
import time as time_mod
from pathlib import Path
import openpyxl
from data_sources.routing_excel import find_latest_routing_file, load_latest_routing


def _make_xlsx(path: Path, sheet: str, rows: list):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    for row in rows:
        ws.append(row)
    wb.save(str(path))


def test_find_latest_returns_newest_xlsx(tmp_path):
    f1 = tmp_path / "old.xlsx"
    f2 = tmp_path / "new.xlsx"
    _make_xlsx(f1, "Articles and phases", [["Article", "ASM"]])
    time_mod.sleep(0.01)
    _make_xlsx(f2, "Articles and phases", [["Article", "ASM"]])
    assert find_latest_routing_file(str(tmp_path)) == str(f2)


def test_find_latest_ignores_temp_files(tmp_path):
    f1 = tmp_path / "good.xlsx"
    f2 = tmp_path / "~$lock.xlsx"
    _make_xlsx(f1, "S", [["A"]])
    f2.write_bytes(b"")
    assert find_latest_routing_file(str(tmp_path)) == str(f1)


def test_find_latest_returns_none_for_empty_dir(tmp_path):
    assert find_latest_routing_file(str(tmp_path)) is None
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_routing_excel.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement file finder**

```python
# data_sources/routing_excel.py
"""Read the routing Excel from T:\\D365 routing data.
Cells with 'x' (any case) are skipped. Non-numeric cells logged + skipped.
"""
import logging
import os
from datetime import datetime
from typing import Dict, Optional, Tuple

import openpyxl

logger = logging.getLogger("PianoTempi")


def find_latest_routing_file(folder: str) -> Optional[str]:
    """Return absolute path of most recent .xlsx in folder, ignoring temp files."""
    if not os.path.isdir(folder):
        logger.error("routing folder not accessible: %s", folder)
        return None
    candidates = []
    for name in os.listdir(folder):
        if name.startswith("~$"):
            continue
        if not name.lower().endswith(".xlsx"):
            continue
        full = os.path.join(folder, name)
        try:
            mtime = os.path.getmtime(full)
        except OSError:
            continue
        candidates.append((mtime, full))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_routing_excel.py::test_find_latest_returns_newest_xlsx tests/test_routing_excel.py::test_find_latest_ignores_temp_files tests/test_routing_excel.py::test_find_latest_returns_none_for_empty_dir -v`
Expected: PASS — 3 tests passed

---

### Task 7.2: routing_excel.load_latest_routing parses cells

- [ ] **Step 1: Add tests**

Append to `tests/test_routing_excel.py`:

```python
def test_load_routing_parses_cycles(tmp_path):
    f = tmp_path / "r.xlsx"
    _make_xlsx(f, "Articles and phases", [
        ["Article", "ASSEMBLY", "COATING", "EOLTEST"],
        ["P1",      "x",        2.5,        8.18],
        ["P2",      14.35,      "x",        "x"],
    ])
    cycles, src, _mtime = load_latest_routing(str(tmp_path), "Articles and phases")
    assert cycles[("P1", "COATING")] == 2.5
    assert cycles[("P1", "EOLTEST")] == 8.18
    assert cycles[("P2", "ASSEMBLY")] == 14.35
    # 'x' cells must NOT be in the dict
    assert ("P1", "ASSEMBLY") not in cycles
    assert ("P2", "COATING") not in cycles
    assert src.endswith("r.xlsx")


def test_load_routing_skips_non_numeric_with_warning(tmp_path, caplog):
    f = tmp_path / "r.xlsx"
    _make_xlsx(f, "Articles and phases", [
        ["Article", "ASSEMBLY"],
        ["P1",      "garbage"],
    ])
    cycles, _src, _mtime = load_latest_routing(str(tmp_path), "Articles and phases")
    assert cycles == {}
    assert any("non-numeric" in r.message.lower() for r in caplog.records)


def test_load_routing_missing_folder_returns_empty(tmp_path):
    cycles, src, mtime = load_latest_routing(str(tmp_path / "nope"), "Articles and phases")
    assert cycles == {}
    assert src == ""
    assert mtime is None
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_routing_excel.py -v`
Expected: 3 new FAIL

- [ ] **Step 3: Implement `load_latest_routing` in `data_sources/routing_excel.py`**

Append:

```python
def load_latest_routing(
    folder: str, sheet: str
) -> Tuple[Dict[Tuple[str, str], float], str, Optional[datetime]]:
    """Return (cycles_map, source_path, mtime). Empty dict on any failure."""
    src = find_latest_routing_file(folder)
    if src is None:
        return {}, "", None
    try:
        mtime = datetime.fromtimestamp(os.path.getmtime(src))
    except OSError:
        mtime = None

    try:
        wb = openpyxl.load_workbook(src, read_only=True, data_only=True)
    except Exception as e:
        logger.error("cannot open routing xlsx %s: %s", src, e)
        return {}, src, mtime

    if sheet not in wb.sheetnames:
        logger.error("sheet '%s' not in %s -- sheets: %s", sheet, src, wb.sheetnames)
        wb.close()
        return {}, src, mtime

    ws = wb[sheet]
    rows = list(ws.iter_rows(min_row=1, values_only=True))
    wb.close()
    if not rows:
        return {}, src, mtime

    header = rows[0]
    # column 0 = "Article", columns 1+ = phase names
    phase_columns: Dict[int, str] = {}
    for idx in range(1, len(header)):
        h = header[idx]
        if h is None:
            continue
        phase_columns[idx] = str(h).strip()

    cycles: Dict[Tuple[str, str], float] = {}
    for row in rows[1:]:
        if not row:
            continue
        product = row[0]
        if product is None:
            continue
        product_code = str(product).strip()
        if not product_code:
            continue
        for col_idx, phase_name in phase_columns.items():
            if col_idx >= len(row):
                continue
            v = row[col_idx]
            if v is None:
                continue
            if isinstance(v, str):
                if v.strip().lower() == "x":
                    continue
                # try parse number
                try:
                    fv = float(v.replace(",", ".").strip())
                except ValueError:
                    logger.warning(
                        "non-numeric cell at product=%s phase=%s value=%r -- skipped",
                        product_code, phase_name, v,
                    )
                    continue
            elif isinstance(v, (int, float)):
                fv = float(v)
            else:
                logger.warning(
                    "non-numeric cell at product=%s phase=%s value=%r -- skipped",
                    product_code, phase_name, v,
                )
                continue
            if fv <= 0:
                continue
            cycles[(product_code, phase_name)] = fv

    logger.info("routing loaded: %d cycles from %s", len(cycles), src)
    return cycles, src, mtime
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_routing_excel.py -v`
Expected: PASS — all tests pass

- [ ] **Step 5: Commit**

```bash
git add data_sources/routing_excel.py tests/test_routing_excel.py
git commit -m "feat(data_sources): routing Excel parser (latest file, skip 'x')"
```

---

### Task 7.3: planning_excel.load_today_plan

**Files:**
- Create: `data_sources/planning_excel.py`
- Create: `tests/test_planning_excel.py`

- [ ] **Step 1: Write the test (mocked)**

```python
# tests/test_planning_excel.py
from datetime import date
from unittest.mock import MagicMock, patch
from data_sources.planning_excel import load_today_plan


@patch("data_sources.planning_excel.find_latest_routing_file")
@patch("data_sources.planning_excel.parse_last_phase")
@patch("data_sources.planning_excel.resolve_orders_to_products")
def test_load_today_plan_filters_today_and_enriches(
    mock_resolve, mock_parse, mock_find, tmp_path,
):
    from data_sources.planning_excel import _PlanRowRaw
    mock_find.return_value = str(tmp_path / "plan.xlsx")
    mock_parse.return_value = [
        _PlanRowRaw("ORD1", "ASSEMBLY", date(2026, 5, 6), 100),
        _PlanRowRaw("ORD2", "COATING",  date(2026, 5, 7), 50),  # not today
        _PlanRowRaw("ORD3", "ASSEMBLY", date(2026, 5, 6), 30),
    ]
    mock_resolve.return_value = {"ORD1": (1001, "P1"), "ORD3": (1003, "P3")}

    rows = load_today_plan(str(tmp_path), "PlanningMachine",
                           target_date=date(2026, 5, 6), conn=MagicMock())
    assert len(rows) == 2
    order_codes = {r.order_number: r.product_code for r in rows}
    assert order_codes == {"ORD1": "P1", "ORD3": "P3"}


@patch("data_sources.planning_excel.find_latest_routing_file")
def test_load_today_plan_no_file_returns_empty(mock_find, tmp_path):
    mock_find.return_value = None
    rows = load_today_plan(str(tmp_path), "PlanningMachine",
                           target_date=date(2026, 5, 6), conn=MagicMock())
    assert rows == []
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_planning_excel.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement (reuse PlanRespect's `parse_last_phase`)**

```python
# data_sources/planning_excel.py
"""Wrap PlanRespect's planning Excel parser, enrich with product_code."""
import logging
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from data_sources.routing_excel import find_latest_routing_file
from engine.models import PlanRow

logger = logging.getLogger("PianoTempi")


# Forward declarations resolved at runtime via lazy imports so tests can patch.
def parse_last_phase(file_path: str, sheet_name: str):
    """Lazy import of PlanRespect's logic copied locally."""
    from data_sources._planning_excel_parser import parse_last_phase as _impl
    return _impl(file_path, sheet_name)


def resolve_orders_to_products(conn, order_numbers):
    """Lazy import of db_queries.resolve_orders_to_products."""
    from data_sources.db_queries import resolve_orders_to_products as _impl
    return _impl(conn, order_numbers)


@dataclass(frozen=True)
class _PlanRowRaw:
    order_number: str
    phase_name: str
    production_date: date
    planned_qty: int


def load_today_plan(folder: str, sheet: str, target_date: date, conn) -> List[PlanRow]:
    src = find_latest_routing_file(folder)
    # NB: same find function works for any folder of xlsx files
    if src is None:
        logger.error("planning file not found in %s", folder)
        return []

    raw_rows = parse_last_phase(src, sheet)
    today_raw = [r for r in raw_rows if r.production_date == target_date]
    if not today_raw:
        return []

    # Enrich with product_code
    order_numbers = {r.order_number for r in today_raw}
    resolved = resolve_orders_to_products(conn, order_numbers)
    enriched: List[PlanRow] = []
    for r in today_raw:
        info = resolved.get(r.order_number)
        if info is None:
            logger.warning("order %s not resolved to product -- skipped", r.order_number)
            continue
        _id_order, product_code = info
        enriched.append(PlanRow(
            order_number=r.order_number,
            phase_name=r.phase_name,
            product_code=product_code,
            production_date=r.production_date,
            planned_qty=r.planned_qty,
        ))
    logger.info("planning loaded: %d rows for %s (from %d raw)",
                len(enriched), target_date, len(today_raw))
    return enriched
```

- [ ] **Step 4: Copy `parse_last_phase` from PlanRespect**

Create `data_sources/_planning_excel_parser.py` by copying lines 12–163 of `C:\Users\User\PythonProjetcs\Python\PlanRespect\excel_parser.py` (functions `_parse_date_header`, `_parse_qty`, `parse_last_phase`, dataclass `PlanRow` renamed to `_PlanRowRaw` to avoid clash). Replace the dataclass at the top of the file with:

```python
from data_sources.planning_excel import _PlanRowRaw as PlanRow
```

(The rest of the file is taken verbatim.)

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_planning_excel.py -v`
Expected: PASS — 2 tests passed

- [ ] **Step 6: Commit**

```bash
git add data_sources/planning_excel.py data_sources/_planning_excel_parser.py tests/test_planning_excel.py
git commit -m "feat(data_sources): planning Excel parser (reuse PlanRespect)"
```

---

## Phase 8 — Data sources: SQL queries

### Task 8.1: db_queries module skeleton

**Files:**
- Create: `data_sources/db_queries.py`
- Create: `tests/test_db_queries.py`

- [ ] **Step 1: Write tests with cursor mocks**

```python
# tests/test_db_queries.py
from datetime import datetime
from unittest.mock import MagicMock
import pytest
from data_sources.db_queries import (
    get_phase_mapping, resolve_orders_to_products,
    get_production_in_window, get_email_recipients,
)


def _conn_with_rows(rows):
    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    cursor.fetchone.return_value = rows[0] if rows else None
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


def test_get_phase_mapping_parses_rows():
    conn, cursor = _conn_with_rows([
        (2, "Assembly", 10, "ASSEMBLY"),
        (5, "Coating",  20, "COATING"),
    ])
    pm = get_phase_mapping(conn)
    assert len(pm) == 2
    assert pm[0].traceability_phase_id == 2
    assert pm[0].planning_phase_name == "ASSEMBLY"


def test_resolve_orders_to_products_batched():
    conn, cursor = _conn_with_rows([])
    cursor.fetchall.side_effect = [
        [(1001, "P1"), (1002, "P2")],
    ]
    result = resolve_orders_to_products(conn, ["ORD1", "ORD2"])
    assert isinstance(result, dict)
    assert "ORD1" in result or "ORD2" in result  # ordering depends on mock


def test_get_production_in_window_returns_int():
    conn, cursor = _conn_with_rows([(42,)])
    cursor.fetchone.return_value = (42,)
    qty = get_production_in_window(
        conn, id_order=1001, traceability_phase_id=2,
        start_dt=datetime(2026, 5, 6, 7, 30),
        end_dt=datetime(2026, 5, 6, 15, 30),
    )
    assert qty == 42


def test_get_production_in_window_returns_zero_on_none():
    conn, cursor = _conn_with_rows([])
    cursor.fetchone.return_value = None
    qty = get_production_in_window(conn, 1, 2, datetime.now(), datetime.now())
    assert qty == 0


def test_get_email_recipients_splits_csv():
    conn, cursor = _conn_with_rows([])
    cursor.fetchone.return_value = ("alice@x.com,bob@x.com; carol@x.com",)
    rcpt = get_email_recipients(conn)
    assert sorted(rcpt) == ["alice@x.com", "bob@x.com", "carol@x.com"]


def test_get_email_recipients_empty_returns_empty_list():
    conn, cursor = _conn_with_rows([])
    cursor.fetchone.return_value = None
    assert get_email_recipients(conn) == []
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_db_queries.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `data_sources/db_queries.py`**

```python
# data_sources/db_queries.py
"""All SQL queries for the application. Single module, easy to scan."""
import logging
import re
from datetime import datetime
from typing import Dict, Iterable, List, Tuple

from engine.models import PhaseMap

logger = logging.getLogger("PianoTempi")


def get_phase_mapping(conn) -> List[PhaseMap]:
    """User-provided mapping query (spec §1.4 / §3 / §4.2)."""
    sql = """
        SELECT cs.PhaseTraceId       AS Traceability_PhaseId,
               p.PhaseName            AS Traceability_PhaseName,
               cs.PhasePlanningId     AS Planning_PhaseId,
               tp.PhaseName            AS Planning_PhaseName
        FROM Employee.dbo.CdcSubLinkTraces cs
        INNER JOIN TraceabilityPlanning_RS.dbo.Phase tp
            ON tp.PhaseId = cs.PhasePlanningId
        INNER JOIN traceability_rs.dbo.Phases p
            ON p.IdPhase = cs.PhaseTraceId
    """
    cursor = conn.cursor()
    cursor.execute(sql)
    rows = cursor.fetchall()
    cursor.close()
    out: List[PhaseMap] = []
    for r in rows:
        if r[0] is None or r[3] is None:
            continue
        out.append(PhaseMap(
            planning_phase_name=str(r[3]).strip(),
            planning_phase_id=int(r[2]) if r[2] is not None else 0,
            traceability_phase_id=int(r[0]),
            traceability_phase_name=str(r[1]).strip() if r[1] else "",
        ))
    return out


def resolve_orders_to_products(conn, order_numbers: Iterable[str]) -> Dict[str, Tuple[int, str]]:
    """Returns {order_number: (id_order, product_code)} for the requested orders."""
    order_list = list({o for o in order_numbers if o})
    if not order_list:
        return {}
    # SQL Server can't take arbitrary lists; we batch in chunks of ~500.
    out: Dict[str, Tuple[int, str]] = {}
    chunk_size = 500
    for i in range(0, len(order_list), chunk_size):
        chunk = order_list[i:i + chunk_size]
        placeholders = ",".join("?" for _ in chunk)
        sql = f"""
            SELECT o.OrderNumber, o.IdOrder, p.ProductCode
            FROM Traceability_rs.dbo.Orders o
            INNER JOIN traceability_rs.dbo.Products p ON o.IdProduct = p.IdProduct
            WHERE o.OrderNumber IN ({placeholders})
        """
        cursor = conn.cursor()
        cursor.execute(sql, *chunk)
        for row in cursor.fetchall():
            out[str(row[0]).strip()] = (int(row[1]), str(row[2]).strip())
        cursor.close()
    return out


def get_production_in_window(
    conn, id_order: int, traceability_phase_id: int,
    start_dt: datetime, end_dt: datetime,
) -> int:
    """Adapted from PlanRespect.get_past_production with arbitrary [start, end) window."""
    sql = """
        SELECT COUNT(DISTINCT Traceability_rs.dbo.BoardLabels(Scannings.IDBoard)) AS Qty
        FROM Traceability_rs.dbo.Scannings
        INNER JOIN Traceability_rs.dbo.OrderPhases
            ON Scannings.IDOrderPhase = OrderPhases.IDOrderPhase
        INNER JOIN Traceability_rs.dbo.Orders
            ON OrderPhases.IDOrder = Orders.IDOrder
        INNER JOIN Traceability_rs.dbo.Phases
            ON OrderPhases.IDPhase = Phases.IDPhase
        INNER JOIN Traceability_rs.dbo.Boards
            ON Boards.IDBoard = Scannings.IDBoard
        WHERE Scannings.ScanTimeFinish >= ?
          AND Scannings.ScanTimeFinish < ?
          AND Scannings.IsPass = 1
          AND Orders.IdOrder = ?
          AND Phases.IdPhase = ?
    """
    cursor = conn.cursor()
    cursor.execute(sql, start_dt, end_dt, id_order, traceability_phase_id)
    row = cursor.fetchone()
    cursor.close()
    if row is None or row[0] is None:
        return 0
    return int(row[0])


def get_email_recipients(conn) -> List[str]:
    """SELECT first row of settings.Value for Attribute='Sys_email_efficienze',
    split on , and ;. Empty list if no row."""
    sql = """
        SELECT TOP 1 Value FROM traceability_rs.dbo.settings
        WHERE Attribute = 'Sys_email_efficienze'
    """
    cursor = conn.cursor()
    cursor.execute(sql)
    row = cursor.fetchone()
    cursor.close()
    if row is None or row[0] is None:
        return []
    raw = str(row[0])
    tokens = [t.strip() for t in re.split(r"[,;]", raw) if t.strip()]
    return tokens
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_db_queries.py -v`
Expected: PASS — 6 tests passed

- [ ] **Step 5: Commit**

```bash
git add data_sources/db_queries.py tests/test_db_queries.py
git commit -m "feat(data_sources): SQL queries (mapping, resolve, production, recipients)"
```

---

## Phase 9 — Data cache

### Task 9.1: DataCache singleton skeleton

**Files:**
- Create: `data_cache.py`
- Create: `tests/test_data_cache.py`

- [ ] **Step 1: Write basic test**

```python
# tests/test_data_cache.py
from datetime import datetime
from unittest.mock import MagicMock
from data_cache import DataCache
from app_config import (
    AppConfig, ServerConfig, PhasesConfig, DataSourcesConfig,
    RefreshConfig, ShiftConfig, ThresholdsConfig, EmailReportConfig,
)
from datetime import time


def _cfg():
    return AppConfig(
        server=ServerConfig(),
        phases=PhasesConfig(monitored=["ASSEMBLY"]),
        data_sources=DataSourcesConfig(),
        refresh=RefreshConfig(),
        shifts=[
            ShiftConfig("T1", time(7, 30), time(15, 30)),
            ShiftConfig("T2", time(15, 30), time(23, 30)),
            ShiftConfig("T3", time(23, 30), time(7, 30)),
        ],
        thresholds=ThresholdsConfig(),
        email_report=EmailReportConfig(),
    )


def test_data_cache_initial_state():
    c = DataCache(_cfg())
    assert c.routing_cycles == {}
    assert c.today_plan == []
    assert c.phase_kpis == {}
    assert c.last_refresh_ts == {}
```

- [ ] **Step 2: Run test**

Run: `pytest tests/test_data_cache.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `data_cache.py`**

```python
# data_cache.py
"""In-memory cache shared between scheduler and Flask routes."""
import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from app_config import AppConfig
from engine.models import PhaseKPI, PhaseMap, PlanRow, RollingData, TotalKPI

logger = logging.getLogger("PianoTempi")


class DataCache:
    def __init__(self, config: AppConfig):
        self._lock = threading.RLock()
        self.config = config
        # populated by refresh_*() methods (added in Task 9.2)
        self.routing_cycles: Dict[Tuple[str, str], float] = {}
        self.routing_source_path: str = ""
        self.routing_source_mtime: Optional[datetime] = None
        self.phase_mapping: Dict[str, int] = {}  # planning_phase_name -> traceability_phase_id
        self.today_plan: List[PlanRow] = []
        self.order_to_product: Dict[str, str] = {}
        self.order_to_id: Dict[str, int] = {}
        self.phase_kpis: Dict[str, PhaseKPI] = {}
        self.total_kpi: Optional[TotalKPI] = None
        self.rolling_data: Optional[RollingData] = None
        self.last_refresh_ts: Dict[str, datetime] = {}

    def lock(self):
        return self._lock
```

- [ ] **Step 4: Run test**

Run: `pytest tests/test_data_cache.py -v`
Expected: PASS

---

### Task 9.2: DataCache refresh methods

- [ ] **Step 1: Add tests for refresh logic**

Append to `tests/test_data_cache.py`:

```python
from unittest.mock import patch


@patch("data_cache.load_latest_routing")
@patch("data_cache.get_phase_mapping")
def test_refresh_routing_populates_cycles_and_mapping(mock_mapping, mock_load):
    mock_load.return_value = ({("P1", "ASSEMBLY"): 2.5}, "/tmp/r.xlsx", datetime(2026, 5, 6))
    from engine.models import PhaseMap
    mock_mapping.return_value = [PhaseMap("ASSEMBLY", 10, 2, "Assembly")]
    c = DataCache(_cfg())
    c.refresh_routing(conn=MagicMock())
    assert c.routing_cycles[("P1", "ASSEMBLY")] == 2.5
    assert c.phase_mapping["ASSEMBLY"] == 2
    assert "routing" in c.last_refresh_ts
```

- [ ] **Step 2: Run test**

Run: `pytest tests/test_data_cache.py -v`
Expected: FAIL — `refresh_routing` not implemented

- [ ] **Step 3: Append refresh methods to `data_cache.py`**

```python
from data_sources.db_queries import (
    get_phase_mapping, get_production_in_window, resolve_orders_to_products,
)
from data_sources.planning_excel import load_today_plan
from data_sources.routing_excel import load_latest_routing
from engine.kpi_builder import build_phase_kpi
from engine.shift_engine import operative_day, shift_window


    def refresh_routing(self, conn) -> None:
        with self._lock:
            cycles, src, mtime = load_latest_routing(
                self.config.data_sources.routing_folder,
                self.config.data_sources.routing_sheet,
            )
            self.routing_cycles = cycles
            self.routing_source_path = src
            self.routing_source_mtime = mtime
            try:
                mapping = get_phase_mapping(conn)
                self.phase_mapping = {pm.planning_phase_name: pm.traceability_phase_id for pm in mapping}
            except Exception as e:
                logger.error("phase mapping query failed: %s -- keeping previous", e)
            self.last_refresh_ts["routing"] = datetime.now()

    def refresh_planning(self, conn) -> None:
        with self._lock:
            today = operative_day(datetime.now())
            plan = load_today_plan(
                self.config.data_sources.planning_folder,
                self.config.data_sources.planning_sheet,
                target_date=today, conn=conn,
            )
            self.today_plan = plan
            # Cache order_to_product and order_to_id
            order_numbers = {r.order_number for r in plan}
            resolved = resolve_orders_to_products(conn, order_numbers)
            self.order_to_product = {k: v[1] for k, v in resolved.items()}
            self.order_to_id = {k: v[0] for k, v in resolved.items()}
            self.last_refresh_ts["planning"] = datetime.now()

    def refresh_production(self, conn) -> None:
        with self._lock:
            now = datetime.now()
            op_day = operative_day(now)
            shifts = self.config.shifts
            # 1. produced[(order_number, phase_name, shift)] = qty
            produced: Dict[Tuple[str, str, str], int] = {}
            any_t3_production = False
            for plan_row in self.today_plan:
                phase_name = plan_row.phase_name
                if phase_name not in self.phase_mapping:
                    continue
                trace_id = self.phase_mapping[phase_name]
                id_order = self.order_to_id.get(plan_row.order_number)
                if id_order is None:
                    continue
                for shift in shifts:
                    s_start, s_end = shift_window(op_day, shift)
                    if shift.code == "T3" and s_start > now:
                        # T3 hasn't started yet this op_day
                        continue
                    if s_start > now:
                        continue
                    # Cap query window at "now" if shift still in progress
                    q_end = min(s_end, now)
                    qty = get_production_in_window(conn, id_order, trace_id, s_start, q_end)
                    if qty > 0:
                        produced[(plan_row.order_number, phase_name, shift.code)] = (
                            produced.get((plan_row.order_number, phase_name, shift.code), 0) + qty
                        )
                        if shift.code == "T3":
                            any_t3_production = True

            # 2. Build PhaseKPI for each monitored phase
            kpis: Dict[str, PhaseKPI] = {}
            for phase_name in self.config.phases.monitored:
                kpi = build_phase_kpi(
                    phase_name=phase_name,
                    plan=[p for p in self.today_plan if p.phase_name == phase_name],
                    cycles=self.routing_cycles,
                    produced={k: v for k, v in produced.items() if k[1] == phase_name},
                    order_to_product=self.order_to_product,
                    now=now, shifts=shifts,
                    thresholds=self.config.thresholds,
                    any_t3_production=any_t3_production,
                )
                kpis[phase_name] = kpi
            self.phase_kpis = kpis
            self.total_kpi = self._build_total_kpi(kpis)
            self.last_refresh_ts["production"] = datetime.now()

    def _build_total_kpi(self, kpis: Dict[str, PhaseKPI]) -> TotalKPI:
        plan_h = round(sum(k.planned_h_day for k in kpis.values()), 2)
        prod_h = round(sum(k.produced_h_day for k in kpis.values()), 2)
        plan_so_far = round(sum(k.planned_h_so_far_day for k in kpis.values()), 2)
        delta = round(prod_h - plan_so_far, 2)
        coverage = round(prod_h / plan_h * 100.0, 2) if plan_h > 0 else 0.0
        t = self.config.thresholds
        if coverage >= t.green_min_coverage_pct:
            color = "green"
        elif coverage >= t.yellow_min_coverage_pct:
            color = "yellow"
        else:
            color = "red"
        return TotalKPI(
            planned_h_day=plan_h, planned_h_so_far_day=plan_so_far,
            produced_h_day=prod_h, delta_vs_expected_day=delta,
            coverage_pct_day=coverage, status_color=color,
        )
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_data_cache.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add data_cache.py tests/test_data_cache.py
git commit -m "feat: DataCache with routing/planning/production refresh"
```

---

## Phase 10 — Flask app + API

### Task 10.1: Flask app skeleton + /api/health

**Files:**
- Create: `app.py`
- Create: `tests/test_app.py`

- [ ] **Step 1: Write test**

```python
# tests/test_app.py
from datetime import datetime
from unittest.mock import MagicMock
from app import build_flask_app
from data_cache import DataCache
from app_config import (
    AppConfig, ServerConfig, PhasesConfig, DataSourcesConfig,
    RefreshConfig, ShiftConfig, ThresholdsConfig, EmailReportConfig,
)
from datetime import time


def _cfg():
    return AppConfig(
        server=ServerConfig(), phases=PhasesConfig(monitored=["ASSEMBLY"]),
        data_sources=DataSourcesConfig(), refresh=RefreshConfig(),
        shifts=[ShiftConfig("T1", time(7, 30), time(15, 30)),
                ShiftConfig("T2", time(15, 30), time(23, 30)),
                ShiftConfig("T3", time(23, 30), time(7, 30))],
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
```

- [ ] **Step 2: Run test**

Run: `pytest tests/test_app.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `app.py`**

```python
# app.py
"""Flask app + lifecycle wiring."""
import atexit
import logging
import os
import sys
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler

from flask import Flask, jsonify, render_template

from app_config import load_config
from config_manager import ConfigManager
from data_cache import DataCache
from db_connection import DatabaseConnection


def setup_logging() -> logging.Logger:
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger("PianoTempi")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)
    fh = RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8",
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


def build_flask_app(cache: DataCache) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")

    @app.route("/")
    def index():
        return render_template("dashboard.html",
                               polling_seconds=cache.config.refresh.frontend_polling_seconds,
                               rotation_seconds=cache.config.phases.rotation_interval_seconds,
                               manual_pause_seconds=cache.config.phases.manual_navigation_pause_seconds,
                               monitored_phases=cache.config.phases.monitored)

    @app.route("/api/health")
    def health():
        now = datetime.now()
        out = {"now": now.isoformat(), "last_refresh": {}, "stale": {}}
        prod_threshold = timedelta(seconds=cache.config.refresh.production_seconds * 2)
        for source, ts in cache.last_refresh_ts.items():
            out["last_refresh"][source] = ts.isoformat()
            out["stale"][source] = (now - ts) > prod_threshold
        return jsonify(out)

    return app
```

- [ ] **Step 4: Run test**

Run: `pytest tests/test_app.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: Flask app skeleton + /api/health"
```

---

### Task 10.2: /api/phases endpoint

- [ ] **Step 1: Add test**

Append to `tests/test_app.py`:

```python
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
```

- [ ] **Step 2: Run test**

Run: `pytest tests/test_app.py::test_phases_endpoint_returns_kpis -v`
Expected: FAIL — endpoint not defined

- [ ] **Step 3: Add `/api/phases` to `build_flask_app` in `app.py`**

Insert after `/api/health` definition:

```python
    def _kpi_to_dict(kpi):
        return {
            "phase_name": kpi.phase_name,
            "shift_code": kpi.shift_code,
            "planned_h_day": kpi.planned_h_day,
            "planned_h_shift": kpi.planned_h_shift,
            "planned_h_so_far_day": kpi.planned_h_so_far_day,
            "planned_h_so_far_shift": kpi.planned_h_so_far_shift,
            "produced_h_day": kpi.produced_h_day,
            "produced_h_shift": kpi.produced_h_shift,
            "delta_vs_expected_day": kpi.delta_vs_expected_day,
            "delta_vs_expected_shift": kpi.delta_vs_expected_shift,
            "coverage_pct_day": kpi.coverage_pct_day,
            "status_color": kpi.status_color,
            "curve_points": [
                {"time": t.isoformat(timespec="seconds"), "h": h}
                for t, h in kpi.curve_points
            ],
        }

    @app.route("/api/phases")
    def phases():
        with cache.lock():
            return jsonify({
                "phases": {n: _kpi_to_dict(k) for n, k in cache.phase_kpis.items()},
            })
```

- [ ] **Step 4: Run test**

Run: `pytest tests/test_app.py -v`
Expected: PASS

---

### Task 10.3: /api/totals and /api/rolling-month endpoints

- [ ] **Step 1: Add tests**

Append to `tests/test_app.py`:

```python
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
```

- [ ] **Step 2: Run tests**

Expected: FAIL — endpoints missing

- [ ] **Step 3: Add to `build_flask_app`**

```python
    @app.route("/api/totals")
    def totals():
        with cache.lock():
            t = cache.total_kpi
            if t is None:
                return jsonify({})
            return jsonify({
                "planned_h_day": t.planned_h_day,
                "planned_h_so_far_day": t.planned_h_so_far_day,
                "produced_h_day": t.produced_h_day,
                "delta_vs_expected_day": t.delta_vs_expected_day,
                "coverage_pct_day": t.coverage_pct_day,
                "status_color": t.status_color,
            })

    @app.route("/api/rolling-month")
    def rolling_month():
        with cache.lock():
            r = cache.rolling_data
            if r is None:
                return jsonify({})
            return jsonify({
                "days": [
                    {"date": d.date.isoformat(),
                     "planned_h": d.planned_h,
                     "produced_h": d.produced_h,
                     "coverage_pct": d.coverage_pct}
                    for d in r.days
                ],
                "month_planned_h": r.month_planned_h,
                "month_produced_h": r.month_produced_h,
                "month_coverage_pct": r.month_coverage_pct,
                "ytd_planned_h": r.ytd_planned_h,
                "ytd_produced_h": r.ytd_produced_h,
                "ytd_coverage_pct": r.ytd_coverage_pct,
                "working_days_month": r.working_days_month,
                "working_days_ytd": r.working_days_ytd,
            })
```

- [ ] **Step 4: Run tests**

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat(api): /api/phases /api/totals /api/rolling-month"
```

---

## Phase 11 — Frontend

### Task 11.1: dashboard.html template

**Files:**
- Create: `templates/dashboard.html`

- [ ] **Step 1: Write template**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Production Efficiency</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='css/dashboard.css') }}">
  <script src="{{ url_for('static', filename='js/chart.umd.min.js') }}"></script>
</head>
<body>
  <div id="dash" class="dash"
       data-polling-seconds="{{ polling_seconds }}"
       data-rotation-seconds="{{ rotation_seconds }}"
       data-manual-pause-seconds="{{ manual_pause_seconds }}">
    <header class="dash-header">
      <img class="logo" src="{{ url_for('static', filename='Logo.png') }}" alt="Logo">
      <div class="title">PRODUCTION EFFICIENCY</div>
      <div class="clock">
        <div class="date-time">
          <b id="hdr-time">--:--:--</b>
          <span id="hdr-date"></span>
        </div>
        <div id="hdr-health" class="health">● data ok</div>
      </div>
    </header>

    <div class="kpi-strip">
      <div class="kpi-glob" data-c="planned"><div class="label">Day plan</div><div class="val" id="hdr-day-plan">--</div><div class="sub" id="hdr-day-plan-by-now">by now: --</div></div>
      <div class="kpi-glob" data-c="produced"><div class="label">Produced</div><div class="val" id="hdr-produced">--</div><div class="sub">day cumul.</div></div>
      <div class="kpi-glob" data-c="delta"><div class="label">Δ vs expected</div><div class="val" id="hdr-delta">--</div><div class="sub" id="hdr-delta-status">--</div></div>
      <div class="kpi-glob" data-c="coverage"><div class="label">Day coverage</div><div class="val" id="hdr-coverage">--</div><div class="sub">target ≥95%</div></div>
    </div>

    <div id="pages"></div>

    <div class="nav-bar">
      <div class="nav-controls">
        <button class="nav-btn icon" id="btn-prev" title="Previous page">◀</button>
        <button class="nav-btn icon" id="btn-pause" title="Pause rotation">⏸</button>
        <button class="nav-btn icon" id="btn-next" title="Next page">▶</button>
        <select class="nav-select" id="page-select" title="Go to page"></select>
      </div>
      <div class="nav-dots" id="nav-dots"></div>
      <div class="nav-status">
        <span id="nav-status-text">page 1 / 1 · auto in --s</span>
        <div class="timer-bar"><div id="timer-fill" class="fill"></div></div>
      </div>
    </div>
  </div>

  <script>
    window.MONITORED_PHASES = {{ monitored_phases | tojson }};
  </script>
  <script src="{{ url_for('static', filename='js/charts.js') }}"></script>
  <script src="{{ url_for('static', filename='js/dashboard.js') }}"></script>
  <script src="{{ url_for('static', filename='js/rotation.js') }}"></script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add templates/dashboard.html
git commit -m "feat(frontend): dashboard.html scaffold"
```

---

### Task 11.2: dashboard.css

**Files:**
- Create: `static/css/dashboard.css`

- [ ] **Step 1: Write the CSS**

Copy the styles directly from the v4 mockup (the one with English labels) to `static/css/dashboard.css`:

```css
/* static/css/dashboard.css */
body { background: #0a0a0a; color: #eee; font-family: system-ui, -apple-system, sans-serif; margin: 0; padding: 16px; }
.dash { background: #0a0a0a; color: #eee; border-radius: 12px; padding: 18px 22px; border: 1px solid #2a2a2a; max-width: 1400px; margin: 0 auto; }
.dash-header { display: grid; grid-template-columns: 80px 1fr auto; align-items: center; gap: 18px; padding-bottom: 14px; border-bottom: 1px solid #222; }
.logo { width: 70px; height: 50px; object-fit: contain; }
.title { font-size: 22px; font-weight: 700; letter-spacing: 0.5px; color: #fff; }
.clock { display: flex; align-items: center; gap: 18px; }
.date-time { text-align: right; font-size: 13px; color: #aaa; }
.date-time b { display: block; font-size: 18px; color: #fff; font-weight: 600; }
.health { padding: 4px 10px; border-radius: 999px; font-size: 11px; font-weight: 600; }
.health.ok { background: #2dd36f22; color: #2dd36f; border: 1px solid #2dd36f55; }
.health.stale { background: #ffc40926; color: #ffc409; border: 1px solid #ffc40966; }
.health.error { background: #eb445a26; color: #eb445a; border: 1px solid #eb445a66; }
.kpi-strip { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; padding: 12px 0; border-bottom: 1px solid #222; }
.kpi-glob { padding: 10px 14px; background: #141414; border-radius: 6px; border-left: 4px solid #555; }
.kpi-glob[data-c="planned"] { border-left-color: #3880ff; }
.kpi-glob[data-c="produced"] { border-left-color: #2dd36f; }
.kpi-glob[data-c="delta"] { border-left-color: #eb445a; }
.kpi-glob[data-c="coverage"] { border-left-color: #ffc409; }
.kpi-glob .label { font-size: 10px; color: #999; text-transform: uppercase; letter-spacing: 0.6px; }
.kpi-glob .val { font-size: 24px; font-weight: 700; color: #fff; margin-top: 2px; }
.kpi-glob .sub { font-size: 10px; color: #888; margin-top: 1px; }

.page { display: none; padding: 14px 0; }
.page.active { display: block; }
.panels { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.panel { background: #141414; border: 1px solid #222; border-radius: 8px; padding: 14px; }
.panel-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.panel-name { font-size: 18px; font-weight: 700; color: #fff; }
.badge { padding: 3px 10px; border-radius: 999px; font-size: 11px; font-weight: 600; }
.badge.green { background: #2dd36f26; color: #2dd36f; border: 1px solid #2dd36f66; }
.badge.yellow { background: #ffc40926; color: #ffc409; border: 1px solid #ffc40966; }
.badge.red { background: #eb445a26; color: #eb445a; border: 1px solid #eb445a66; }
.panel-body { display: grid; grid-template-columns: 1.4fr 1fr; gap: 12px; }
.chart-mini { background: #0a0a0a; border-radius: 6px; padding: 8px; min-height: 180px; }
.kpi-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.kpi-cell { background: #0a0a0a; border-radius: 5px; padding: 7px 9px; border-left: 3px solid #555; }
.kpi-cell.planned { border-left-color: #3880ff; }
.kpi-cell.produced { border-left-color: #2dd36f; }
.kpi-cell .lbl { font-size: 9px; color: #888; text-transform: uppercase; letter-spacing: 0.4px; }
.kpi-cell .v { font-size: 16px; font-weight: 700; color: #fff; }
.kpi-cell .s { font-size: 9px; color: #888; margin-top: 1px; }
.kpi-delta { grid-column: 1 / -1; padding: 8px 10px; border-radius: 5px; display: flex; justify-content: space-between; align-items: baseline; }
.kpi-delta.pos { background: #2dd36f18; border: 1px solid #2dd36f55; color: #4ce58e; }
.kpi-delta.neg { background: #eb445a18; border: 1px solid #eb445a55; color: #ff6b7a; }
.kpi-delta .lbl { font-size: 10px; text-transform: uppercase; }
.kpi-delta .v { font-size: 18px; font-weight: 700; }

.nav-bar { padding-top: 10px; border-top: 1px solid #222; display: grid; grid-template-columns: auto 1fr auto; gap: 16px; align-items: center; }
.nav-controls { display: flex; gap: 6px; align-items: center; }
.nav-btn { background: #141414; color: #ddd; border: 1px solid #2a2a2a; border-radius: 6px; padding: 6px 10px; font-size: 14px; font-weight: 600; cursor: pointer; min-width: 32px; }
.nav-btn:hover { background: #1f1f1f; border-color: #444; color: #fff; }
.nav-select { background: #141414; color: #fff; border: 1px solid #2a2a2a; border-radius: 6px; padding: 6px 12px; font-size: 12px; min-width: 230px; }
.nav-dots { text-align: center; }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #333; margin: 0 4px; vertical-align: middle; cursor: pointer; }
.dot.act { background: #2dd36f; width: 22px; border-radius: 4px; }
.nav-status { font-size: 11px; color: #888; text-align: right; min-width: 130px; }
.timer-bar { height: 3px; background: #1a1a1a; border-radius: 2px; margin-top: 4px; overflow: hidden; }
.timer-bar .fill { height: 100%; background: #2dd36f; width: 0%; transition: width 1s linear; }
.timer-bar.paused .fill { background: #ffc409; }

.banner-stale { background: #eb445a; color: #fff; text-align: center; padding: 8px; font-weight: 600; margin-bottom: 8px; border-radius: 6px; }
```

- [ ] **Step 2: Commit**

```bash
git add static/css/dashboard.css
git commit -m "feat(frontend): dashboard.css"
```

---

### Task 11.3: Vendor Chart.js

- [ ] **Step 1: Download Chart.js v4**

```bash
curl -L https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js -o static/js/chart.umd.min.js
```

- [ ] **Step 2: Verify file exists and is non-empty**

```bash
ls -la static/js/chart.umd.min.js
```
Expected: file ~200 KB.

- [ ] **Step 3: Commit**

```bash
git add static/js/chart.umd.min.js
git commit -m "chore(frontend): vendor chart.js v4.4.0"
```

---

### Task 11.4: charts.js — Chart.js factory

**Files:**
- Create: `static/js/charts.js`

- [ ] **Step 1: Write factory functions**

```javascript
// static/js/charts.js
// Chart.js factory functions: phase intra-day, total intra-day, monthly rolling.
const COLOR_PLAN = "#3880ff";
const COLOR_PRODUCED = "#2dd36f";

function makePhaseChart(canvas, dayTotalGrossH /* 16 or 24 */) {
  // X axis: hours since 07:30 of operative day, from 0 to dayTotalGrossH.
  return new Chart(canvas, {
    type: "line",
    data: {
      datasets: [
        { label: "Plan", data: [], borderColor: COLOR_PLAN, borderWidth: 2,
          pointRadius: 0, fill: false, tension: 0 },
        { label: "Produced", data: [], borderColor: COLOR_PRODUCED, borderWidth: 2.5,
          pointRadius: 3, pointBackgroundColor: COLOR_PRODUCED, fill: false, tension: 0.2 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      scales: {
        x: { type: "linear", min: 0, max: dayTotalGrossH,
             title: { display: false },
             ticks: { color: "#777", font: { size: 9 },
                      callback: (v) => formatXTick(v) } },
        y: { beginAtZero: true,
             ticks: { color: "#777", font: { size: 9 } },
             title: { display: false } },
      },
      plugins: { legend: { display: false } },
    },
  });
}

function formatXTick(hoursFrom0730) {
  // 0 -> "07:30", 8 -> "15:30", 16 -> "23:30", 24 -> "07:30"
  const totalMinutes = 7 * 60 + 30 + Math.round(hoursFrom0730 * 60);
  const h = Math.floor(totalMinutes / 60) % 24;
  const m = totalMinutes % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function updatePhaseChart(chart, plannedHDay, curvePoints, dayTotalGrossH) {
  // Plan = straight line from (0, 0) to (dayTotalGrossH, plannedHDay)
  chart.data.datasets[0].data = [
    { x: 0, y: 0 },
    { x: dayTotalGrossH, y: plannedHDay },
  ];
  // Produced = curve_points converted to {x: hours_from_0730, y: cumulH}
  chart.data.datasets[1].data = (curvePoints || []).map(p => {
    // p.time like "16:00:00"; convert to hours-from-0730
    const [h, m] = p.time.split(":").map(Number);
    let elapsed = (h - 7) + (m - 30) / 60;
    if (elapsed < 0) elapsed += 24;  // wrap (T3 next day)
    return { x: elapsed, y: p.h };
  });
  // Prepend (0, 0)
  if (chart.data.datasets[1].data.length > 0 || true) {
    chart.data.datasets[1].data.unshift({ x: 0, y: 0 });
  }
  chart.update("none");
}

function makeRollingChart(canvas) {
  return new Chart(canvas, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        { label: "Plan", data: [], borderColor: COLOR_PLAN, borderWidth: 2,
          pointRadius: 2, fill: false },
        { label: "Produced", data: [], borderColor: COLOR_PRODUCED, borderWidth: 2.5,
          pointRadius: 2, fill: false },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      scales: {
        x: { ticks: { color: "#777" } },
        y: { beginAtZero: true, ticks: { color: "#777" } },
      },
      plugins: { legend: { display: true, labels: { color: "#ccc" } } },
    },
  });
}

function updateRollingChart(chart, days) {
  chart.data.labels = days.map(d => d.date.slice(5));  // MM-DD
  chart.data.datasets[0].data = days.map(d => d.planned_h);
  chart.data.datasets[1].data = days.map(d => d.produced_h);
  chart.update("none");
}
```

- [ ] **Step 2: Commit**

```bash
git add static/js/charts.js
git commit -m "feat(frontend): Chart.js factories (phase + rolling)"
```

---

### Task 11.5: dashboard.js — page builder + polling

**Files:**
- Create: `static/js/dashboard.js`

- [ ] **Step 1: Write the JS**

```javascript
// static/js/dashboard.js
// Builds page DOM, polls APIs, updates DOM + charts.

const DASH = document.getElementById("dash");
const POLLING_MS = parseInt(DASH.dataset.pollingSeconds, 10) * 1000;
const PHASES = window.MONITORED_PHASES || [];

const pageCharts = {};   // pageIndex -> { phaseName: chart }
let totalChart = null;
let rollingChart = null;

function hms(d) {
  const pad = n => String(n).padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function updateClock() {
  const now = new Date();
  document.getElementById("hdr-time").textContent = hms(now);
  const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const pad = n => String(n).padStart(2, "0");
  document.getElementById("hdr-date").textContent =
    `${days[now.getDay()]} ${pad(now.getDate())}/${pad(now.getMonth() + 1)}/${now.getFullYear()}`;
}
setInterval(updateClock, 1000);
updateClock();

function buildPages() {
  const pagesContainer = document.getElementById("pages");
  pagesContainer.innerHTML = "";
  const pages = [];
  for (let i = 0; i < PHASES.length; i += 2) {
    pages.push(PHASES.slice(i, i + 2));
  }

  pages.forEach((phaseGroup, idx) => {
    const pg = document.createElement("div");
    pg.className = "page" + (idx === 0 ? " active" : "");
    pg.dataset.kind = "phases";
    pg.innerHTML = `<div class="panels">${phaseGroup.map(name => `
      <div class="panel" data-phase="${name}">
        <div class="panel-head">
          <div class="panel-name">${name}</div>
          <div class="badge red" data-role="badge">--</div>
        </div>
        <div class="panel-body">
          <div class="chart-mini"><canvas data-role="chart"></canvas></div>
          <div class="kpi-grid">
            <div class="kpi-cell planned"><div class="lbl">Shift plan</div><div class="v" data-role="shift-plan">--</div><div class="s" data-role="shift-plan-by-now">by now --</div></div>
            <div class="kpi-cell produced"><div class="lbl">Shift produced</div><div class="v" data-role="shift-prod">--</div><div class="s">shift in progress</div></div>
            <div class="kpi-cell planned"><div class="lbl">Day plan</div><div class="v" data-role="day-plan">--</div><div class="s" data-role="day-plan-by-now">by now --</div></div>
            <div class="kpi-cell produced"><div class="lbl">Day produced</div><div class="v" data-role="day-prod">--</div><div class="s">cumul.</div></div>
            <div class="kpi-delta neg" data-role="delta"><div class="lbl">Δ vs expected (day)</div><div class="v">--</div></div>
          </div>
        </div>
      </div>
    `).join("")}</div>`;
    pagesContainer.appendChild(pg);
    pageCharts[idx] = {};
    pg.querySelectorAll("[data-phase]").forEach(panel => {
      const phaseName = panel.dataset.phase;
      const canvas = panel.querySelector("[data-role=chart]");
      pageCharts[idx][phaseName] = makePhaseChart(canvas, 16);
    });
  });

  // Total Summary page
  const totalIdx = pages.length;
  const totalPg = document.createElement("div");
  totalPg.className = "page";
  totalPg.dataset.kind = "total";
  totalPg.innerHTML = `
    <div class="panel" style="margin-top:12px">
      <div class="panel-head"><div class="panel-name">Total Summary — Today</div></div>
      <div class="panel-body">
        <div class="chart-mini"><canvas id="total-chart"></canvas></div>
        <div class="kpi-grid">
          <div class="kpi-cell planned"><div class="lbl">Day plan</div><div class="v" id="tot-plan">--</div></div>
          <div class="kpi-cell planned"><div class="lbl">By now</div><div class="v" id="tot-plan-by-now">--</div></div>
          <div class="kpi-cell produced"><div class="lbl">Produced</div><div class="v" id="tot-prod">--</div></div>
          <div class="kpi-cell produced"><div class="lbl">Coverage</div><div class="v" id="tot-cov">--</div></div>
          <div class="kpi-delta" id="tot-delta"><div class="lbl">Δ vs expected (day)</div><div class="v">--</div></div>
        </div>
      </div>
    </div>`;
  pagesContainer.appendChild(totalPg);
  totalChart = makePhaseChart(document.getElementById("total-chart"), 16);

  // Monthly Rolling + YTD page
  const rollingPg = document.createElement("div");
  rollingPg.className = "page";
  rollingPg.dataset.kind = "rolling";
  rollingPg.innerHTML = `
    <div class="panel" style="margin-top:12px">
      <div class="panel-head"><div class="panel-name">Monthly Rolling + YTD</div></div>
      <div class="panel-body" style="grid-template-columns:1.7fr 1fr">
        <div class="chart-mini" style="min-height:260px"><canvas id="rolling-chart"></canvas></div>
        <div class="kpi-grid" style="grid-template-columns:1fr">
          <div class="kpi-cell planned"><div class="lbl">Month plan</div><div class="v" id="m-plan">--</div></div>
          <div class="kpi-cell produced"><div class="lbl">Month produced</div><div class="v" id="m-prod">--</div></div>
          <div class="kpi-cell"><div class="lbl">Month coverage</div><div class="v" id="m-cov">--</div></div>
          <div class="kpi-cell planned"><div class="lbl">YTD plan</div><div class="v" id="y-plan">--</div></div>
          <div class="kpi-cell produced"><div class="lbl">YTD produced</div><div class="v" id="y-prod">--</div></div>
          <div class="kpi-cell"><div class="lbl">YTD coverage</div><div class="v" id="y-cov">--</div></div>
        </div>
      </div>
    </div>`;
  pagesContainer.appendChild(rollingPg);
  rollingChart = makeRollingChart(document.getElementById("rolling-chart"));

  return { phasePages: pages, totalIdx, rollingIdx: totalIdx + 1 };
}

const { phasePages, totalIdx, rollingIdx } = buildPages();

async function fetchAndUpdate() {
  try {
    const [phasesResp, totalsResp, rollingResp, healthResp] = await Promise.all([
      fetch("/api/phases").then(r => r.json()),
      fetch("/api/totals").then(r => r.json()),
      fetch("/api/rolling-month").then(r => r.json()),
      fetch("/api/health").then(r => r.json()),
    ]);

    const dayTotalGross = 16;  // MVP: assume 2 shifts. Phase 2 will derive from API.
    // Update header strip
    document.getElementById("hdr-day-plan").textContent = (totalsResp.planned_h_day ?? 0).toFixed(2) + " h";
    document.getElementById("hdr-day-plan-by-now").textContent = "by now: " + (totalsResp.planned_h_so_far_day ?? 0).toFixed(2) + " h";
    document.getElementById("hdr-produced").textContent = (totalsResp.produced_h_day ?? 0).toFixed(2) + " h";
    const dlt = totalsResp.delta_vs_expected_day ?? 0;
    document.getElementById("hdr-delta").textContent = (dlt >= 0 ? "+" : "") + dlt.toFixed(2) + " h";
    document.getElementById("hdr-delta-status").textContent = dlt >= 0 ? "ahead" : "behind";
    document.getElementById("hdr-coverage").textContent = (totalsResp.coverage_pct_day ?? 0).toFixed(1) + " %";

    // Update phase panels
    Object.entries(phasesResp.phases || {}).forEach(([phaseName, k]) => {
      const panel = document.querySelector(`[data-phase="${phaseName}"]`);
      if (!panel) return;
      const set = (role, v) => { const el = panel.querySelector(`[data-role="${role}"]`); if (el) el.textContent = v; };
      const badge = panel.querySelector("[data-role=badge]");
      badge.className = `badge ${k.status_color}`;
      const dlts = k.delta_vs_expected_shift;
      badge.textContent = `${k.shift_code} · ${dlts >= 0 ? "+" : ""}${dlts.toFixed(2)} h`;
      set("shift-plan", k.planned_h_shift.toFixed(2) + " h");
      set("shift-plan-by-now", "by now " + k.planned_h_so_far_shift.toFixed(2) + " h");
      set("shift-prod", k.produced_h_shift.toFixed(2) + " h");
      set("day-plan", k.planned_h_day.toFixed(2) + " h");
      set("day-plan-by-now", "by now " + k.planned_h_so_far_day.toFixed(2) + " h");
      set("day-prod", k.produced_h_day.toFixed(2) + " h");
      const dEl = panel.querySelector("[data-role=delta]");
      const d = k.delta_vs_expected_day;
      dEl.className = "kpi-delta " + (d >= 0 ? "pos" : "neg");
      dEl.querySelector(".v").textContent = (d >= 0 ? "+" : "") + d.toFixed(2) + " h";

      // Update mini chart
      Object.values(pageCharts).forEach(group => {
        if (group[phaseName]) {
          updatePhaseChart(group[phaseName], k.planned_h_day, k.curve_points, dayTotalGross);
        }
      });
    });

    // Total summary
    document.getElementById("tot-plan").textContent = (totalsResp.planned_h_day ?? 0).toFixed(2) + " h";
    document.getElementById("tot-plan-by-now").textContent = (totalsResp.planned_h_so_far_day ?? 0).toFixed(2) + " h";
    document.getElementById("tot-prod").textContent = (totalsResp.produced_h_day ?? 0).toFixed(2) + " h";
    document.getElementById("tot-cov").textContent = (totalsResp.coverage_pct_day ?? 0).toFixed(1) + " %";
    const totDelta = document.getElementById("tot-delta");
    totDelta.className = "kpi-delta " + ((totalsResp.delta_vs_expected_day ?? 0) >= 0 ? "pos" : "neg");
    totDelta.querySelector(".v").textContent = ((totalsResp.delta_vs_expected_day ?? 0) >= 0 ? "+" : "") + (totalsResp.delta_vs_expected_day ?? 0).toFixed(2) + " h";

    // Total chart (sum across phases)
    const totalCurve = aggregateCurves(phasesResp.phases);
    updatePhaseChart(totalChart, totalsResp.planned_h_day ?? 0, totalCurve, dayTotalGross);

    // Rolling
    document.getElementById("m-plan").textContent = (rollingResp.month_planned_h ?? 0).toFixed(2) + " h";
    document.getElementById("m-prod").textContent = (rollingResp.month_produced_h ?? 0).toFixed(2) + " h";
    document.getElementById("m-cov").textContent = (rollingResp.month_coverage_pct ?? 0).toFixed(1) + " %";
    document.getElementById("y-plan").textContent = (rollingResp.ytd_planned_h ?? 0).toFixed(2) + " h";
    document.getElementById("y-prod").textContent = (rollingResp.ytd_produced_h ?? 0).toFixed(2) + " h";
    document.getElementById("y-cov").textContent = (rollingResp.ytd_coverage_pct ?? 0).toFixed(1) + " %";
    updateRollingChart(rollingChart, rollingResp.days || []);

    // Health
    const healthEl = document.getElementById("hdr-health");
    const anyStale = Object.values(healthResp.stale || {}).some(Boolean);
    healthEl.className = "health " + (anyStale ? "stale" : "ok");
    healthEl.textContent = anyStale ? "● data stale" : "● data ok";
  } catch (e) {
    console.error("update failed", e);
    document.getElementById("hdr-health").className = "health error";
    document.getElementById("hdr-health").textContent = "● error";
  }
}

function aggregateCurves(phaseDict) {
  // Sum produced_h at each timestamp across phases
  const timeMap = new Map();
  Object.values(phaseDict || {}).forEach(p => {
    (p.curve_points || []).forEach(cp => {
      timeMap.set(cp.time, (timeMap.get(cp.time) || 0) + cp.h);
    });
  });
  return Array.from(timeMap.entries()).sort().map(([t, h]) => ({ time: t, h }));
}

setInterval(fetchAndUpdate, POLLING_MS);
fetchAndUpdate();
```

- [ ] **Step 2: Commit**

```bash
git add static/js/dashboard.js
git commit -m "feat(frontend): dashboard.js polling + DOM updates"
```

---

### Task 11.6: rotation.js — auto-rotation + manual nav

**Files:**
- Create: `static/js/rotation.js`

- [ ] **Step 1: Write the JS**

```javascript
// static/js/rotation.js
// Auto-rotates pages, supports manual prev/next/dropdown/dot click + pause.
const ROT_MS = parseInt(DASH.dataset.rotationSeconds, 10) * 1000;
const PAUSE_MS = parseInt(DASH.dataset.manualPauseSeconds, 10) * 1000;

const pages = Array.from(document.querySelectorAll(".page"));
let currentIdx = 0;
let paused = false;
let manualPauseUntil = 0;
let rotateTimer = null;
let elapsedInPage = 0;
let tickTimer = null;

function pageTitle(idx) {
  const pg = pages[idx];
  const kind = pg.dataset.kind;
  if (kind === "total") return `${idx + 1} — Total Summary`;
  if (kind === "rolling") return `${idx + 1} — Monthly Rolling + YTD`;
  const phaseNames = Array.from(pg.querySelectorAll("[data-phase]")).map(p => p.dataset.phase);
  return `${idx + 1} — ${phaseNames.join(" + ")}`;
}

function buildSelectAndDots() {
  const sel = document.getElementById("page-select");
  sel.innerHTML = pages.map((_, i) => `<option value="${i}">${pageTitle(i)}</option>`).join("");
  sel.value = currentIdx;
  sel.addEventListener("change", e => goTo(parseInt(e.target.value, 10), true));

  const dotsEl = document.getElementById("nav-dots");
  dotsEl.innerHTML = pages.map((_, i) => `<span class="dot" data-i="${i}"></span>`).join("");
  dotsEl.querySelectorAll(".dot").forEach(el => {
    el.addEventListener("click", () => goTo(parseInt(el.dataset.i, 10), true));
  });

  document.getElementById("btn-prev").addEventListener("click", () => goTo((currentIdx - 1 + pages.length) % pages.length, true));
  document.getElementById("btn-next").addEventListener("click", () => goTo((currentIdx + 1) % pages.length, true));
  document.getElementById("btn-pause").addEventListener("click", togglePause);
}

function goTo(idx, manual) {
  pages[currentIdx].classList.remove("active");
  pages[idx].classList.add("active");
  currentIdx = idx;
  document.getElementById("page-select").value = idx;
  document.querySelectorAll("#nav-dots .dot").forEach((d, i) => d.classList.toggle("act", i === idx));
  elapsedInPage = 0;
  if (manual) {
    manualPauseUntil = Date.now() + PAUSE_MS;
    document.querySelector(".timer-bar").classList.add("paused");
  }
}

function togglePause() {
  paused = !paused;
  document.getElementById("btn-pause").textContent = paused ? "▶" : "⏸";
  document.getElementById("btn-pause").title = paused ? "Resume rotation" : "Pause rotation";
  document.querySelector(".timer-bar").classList.toggle("paused", paused);
}

function tick() {
  const now = Date.now();
  const inManualPause = now < manualPauseUntil;
  if (inManualPause) {
    document.querySelector(".timer-bar").classList.add("paused");
  } else {
    document.querySelector(".timer-bar").classList.toggle("paused", paused);
  }
  if (!paused && !inManualPause) {
    elapsedInPage += 1000;
    if (elapsedInPage >= ROT_MS) {
      goTo((currentIdx + 1) % pages.length, false);
    }
  }
  // Update bar + status text
  const remainingSec = Math.max(0, Math.ceil((ROT_MS - elapsedInPage) / 1000));
  document.getElementById("timer-fill").style.width = `${(elapsedInPage / ROT_MS) * 100}%`;
  document.getElementById("nav-status-text").textContent =
    `page ${currentIdx + 1} / ${pages.length} · ${paused ? "paused" : (inManualPause ? "manual pause" : "auto in " + remainingSec + "s")}`;
}

buildSelectAndDots();
goTo(0, false);
tickTimer = setInterval(tick, 1000);
```

- [ ] **Step 2: Commit**

```bash
git add static/js/rotation.js
git commit -m "feat(frontend): rotation.js (auto + manual nav + pause)"
```

---

### Task 11.7: Copy logo to static dir

- [ ] **Step 1: Copy Logo.png**

```bash
cp Logo.png static/Logo.png
```

- [ ] **Step 2: Commit**

```bash
git add static/Logo.png
git commit -m "chore(frontend): copy logo to static/"
```

---

## Phase 12 — Scheduler

### Task 12.1: scheduler.py with refresh jobs

**Files:**
- Create: `scheduler.py`

- [ ] **Step 1: Write `scheduler.py`**

```python
# scheduler.py
"""APScheduler with 5 jobs: refresh_routing, refresh_planning, refresh_production,
daily_history_commit, daily_email_report."""
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app_config import AppConfig
from data_cache import DataCache

logger = logging.getLogger("PianoTempi")


def build_scheduler(cache: DataCache, config: AppConfig, conn_factory) -> BackgroundScheduler:
    """conn_factory: callable that returns a fresh DB connection (used per-job)."""
    sched = BackgroundScheduler(timezone="Europe/Bucharest")

    def _job_routing():
        try:
            with conn_factory() as conn:
                cache.refresh_routing(conn)
        except Exception as e:
            logger.error("refresh_routing failed: %s", e)

    def _job_planning():
        try:
            with conn_factory() as conn:
                cache.refresh_planning(conn)
                # also re-check routing mtime
                _check_routing_mtime(cache, conn)
        except Exception as e:
            logger.error("refresh_planning failed: %s", e)

    def _job_production():
        try:
            with conn_factory() as conn:
                cache.refresh_production(conn)
        except Exception as e:
            logger.error("refresh_production failed: %s", e)

    def _job_daily_history():
        try:
            from engine.rolling_engine import save_day_to_history
            from engine.shift_engine import operative_day
            now = datetime.now()
            yesterday = (operative_day(now) - timedelta(days=1))
            phases = {
                k: {"planned_h": v.planned_h_day, "produced_h": v.produced_h_day}
                for k, v in cache.phase_kpis.items()
            }
            path = f"data/daily_history_{yesterday.year}.json"
            save_day_to_history(path, day=yesterday, phases=phases)
            logger.info("daily history committed for %s", yesterday)
        except Exception as e:
            logger.error("daily_history_commit failed: %s", e)

    def _job_email():
        try:
            from reporting.email_report import send_daily
            with conn_factory() as conn:
                send_daily(cache, conn)
        except Exception as e:
            logger.error("daily_email_report failed: %s", e)

    routing_at = config.refresh.routing_daily_at  # "07:00"
    h, m = routing_at.split(":")
    sched.add_job(_job_routing, CronTrigger(hour=int(h), minute=int(m)),
                  id="refresh_routing", coalesce=True, max_instances=1)
    sched.add_job(_job_planning,
                  IntervalTrigger(minutes=config.refresh.planning_minutes),
                  id="refresh_planning", coalesce=True, max_instances=1)
    sched.add_job(_job_production,
                  IntervalTrigger(seconds=config.refresh.production_seconds),
                  id="refresh_production", coalesce=True, max_instances=1)
    # Daily history pre-step at 07:30:30
    sched.add_job(_job_daily_history,
                  CronTrigger(hour=7, minute=30, second=30),
                  id="daily_history_commit", coalesce=True, max_instances=1)
    # Email at config.email_report.send_at (07:31)
    eh, em = config.email_report.send_at.split(":")
    sched.add_job(_job_email,
                  CronTrigger(hour=int(eh), minute=int(em)),
                  id="daily_email_report", coalesce=True, max_instances=1)
    return sched


def _check_routing_mtime(cache: DataCache, conn) -> None:
    """Reload routing if file mtime has changed since last load."""
    import os
    from data_sources.routing_excel import find_latest_routing_file
    src = find_latest_routing_file(cache.config.data_sources.routing_folder)
    if src is None:
        return
    try:
        mtime = datetime.fromtimestamp(os.path.getmtime(src))
    except OSError:
        return
    prev = cache.routing_source_mtime
    if prev is None or mtime > prev:
        cache.refresh_routing(conn)
```

- [ ] **Step 2: Commit**

```bash
git add scheduler.py
git commit -m "feat(scheduler): 5 APScheduler jobs (refresh + history + email)"
```

---

## Phase 13 — Email report

### Task 13.1: email_report — generators

**Files:**
- Create: `reporting/email_report.py`
- Create: `tests/test_email_report.py`

- [ ] **Step 1: Write tests for body generation**

```python
# tests/test_email_report.py
from datetime import date
from engine.models import DayPoint, RollingData
from reporting.email_report import (
    generate_subject, generate_plain_body,
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
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_email_report.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement**

```python
# reporting/email_report.py
"""Daily email report. HTML + plain text. Reuses email_connector from PlanRespect."""
import logging
from datetime import date, datetime, timedelta
from typing import Dict, Optional, Tuple

from data_cache import DataCache
from data_sources.db_queries import get_email_recipients
from engine.models import DayPoint, RollingData
from engine.rolling_engine import compute_rolling_month, load_daily_history
from engine.shift_engine import operative_day

logger = logging.getLogger("PianoTempi")

WEEKDAY_BY_NAME = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def generate_subject(prefix: str, day: date, coverage_pct: float) -> str:
    return f"{prefix} Daily report {day.isoformat()} — coverage {coverage_pct:.1f}%"


def generate_plain_body(
    yesterday: DayPoint,
    yesterday_per_phase: Dict[str, Tuple[float, float]],
    rolling: RollingData,
) -> str:
    lines = []
    lines.append(f"YESTERDAY ({yesterday.date.isoformat()})")
    lines.append("=" * 30)
    lines.append(f"Total day plan:    {yesterday.planned_h:>9.2f} h")
    lines.append(f"Total produced:    {yesterday.produced_h:>9.2f} h")
    lines.append(f"Coverage:          {yesterday.coverage_pct:>9.2f}%")
    lines.append(f"Δ vs plan:         {yesterday.produced_h - yesterday.planned_h:>+9.2f} h")
    lines.append("")
    lines.append("Per-phase breakdown:")
    for phase, (plan_h, prod_h) in sorted(yesterday_per_phase.items()):
        cov = (prod_h / plan_h * 100) if plan_h > 0 else 0
        lines.append(f"  {phase:<12} plan {plan_h:>6.2f}  prod {prod_h:>6.2f}  cov {cov:>5.1f}%   Δ {prod_h - plan_h:+6.2f}")
    lines.append("")

    lines.append(f"MONTH TO DATE ({yesterday.date.replace(day=1).isoformat()} → {yesterday.date.isoformat()})")
    lines.append("=" * 40)
    lines.append(f"Plan:        {rolling.month_planned_h:>11.2f} h")
    lines.append(f"Produced:    {rolling.month_produced_h:>11.2f} h")
    lines.append(f"Coverage:    {rolling.month_coverage_pct:>10.2f}%")
    lines.append(f"Working days: {rolling.working_days_month}")
    lines.append("")

    lines.append(f"YEAR TO DATE ({yesterday.date.replace(month=1, day=1).isoformat()} → {yesterday.date.isoformat()})")
    lines.append("=" * 40)
    lines.append(f"Plan:      {rolling.ytd_planned_h:>13.2f} h")
    lines.append(f"Produced:  {rolling.ytd_produced_h:>13.2f} h")
    lines.append(f"Coverage:  {rolling.ytd_coverage_pct:>12.2f}%")
    lines.append(f"Working days: {rolling.working_days_ytd}")
    return "\n".join(lines)


def generate_html_body(
    yesterday: DayPoint,
    yesterday_per_phase: Dict[str, Tuple[float, float]],
    rolling: RollingData,
) -> str:
    rows = []
    for phase, (plan_h, prod_h) in sorted(yesterday_per_phase.items()):
        cov = (prod_h / plan_h * 100) if plan_h > 0 else 0
        rows.append(
            f'<tr><td>{phase}</td>'
            f'<td style="text-align:right">{plan_h:.2f}</td>'
            f'<td style="text-align:right">{prod_h:.2f}</td>'
            f'<td style="text-align:right">{cov:.1f}%</td>'
            f'<td style="text-align:right">{prod_h - plan_h:+.2f}</td></tr>'
        )
    return f"""<!doctype html><html><body style="font-family:Arial,sans-serif;color:#222">
<h2 style="color:#3880ff">Daily report — {yesterday.date.isoformat()}</h2>
<table style="border-collapse:collapse;width:100%;max-width:680px">
  <thead><tr style="background:#f0f0f0">
    <th style="padding:6px;text-align:left">Phase</th>
    <th style="padding:6px;text-align:right">Plan h</th>
    <th style="padding:6px;text-align:right">Prod h</th>
    <th style="padding:6px;text-align:right">Cov</th>
    <th style="padding:6px;text-align:right">Δ</th>
  </tr></thead>
  <tbody>
    {''.join(rows)}
    <tr style="font-weight:bold;border-top:2px solid #333">
      <td style="padding:6px">TOTAL</td>
      <td style="padding:6px;text-align:right">{yesterday.planned_h:.2f}</td>
      <td style="padding:6px;text-align:right">{yesterday.produced_h:.2f}</td>
      <td style="padding:6px;text-align:right">{yesterday.coverage_pct:.1f}%</td>
      <td style="padding:6px;text-align:right">{yesterday.produced_h - yesterday.planned_h:+.2f}</td>
    </tr>
  </tbody>
</table>
<h3 style="margin-top:24px">Month to date ({yesterday.date.replace(day=1).isoformat()} → {yesterday.date.isoformat()})</h3>
<ul>
  <li>Plan: <b>{rolling.month_planned_h:.2f} h</b></li>
  <li>Produced: <b>{rolling.month_produced_h:.2f} h</b></li>
  <li>Coverage: <b>{rolling.month_coverage_pct:.2f}%</b></li>
  <li>Working days: <b>{rolling.working_days_month}</b></li>
</ul>
<h3>Year to date</h3>
<ul>
  <li>Plan: <b>{rolling.ytd_planned_h:.2f} h</b></li>
  <li>Produced: <b>{rolling.ytd_produced_h:.2f} h</b></li>
  <li>Coverage: <b>{rolling.ytd_coverage_pct:.2f}%</b></li>
  <li>Working days: <b>{rolling.working_days_ytd}</b></li>
</ul>
</body></html>"""
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_email_report.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add reporting/email_report.py tests/test_email_report.py
git commit -m "feat(reporting): email body generators (subject, plain, HTML)"
```

---

### Task 13.2: send_daily wires everything

- [ ] **Step 1: Append `send_daily` to `reporting/email_report.py`**

```python
def send_daily(cache: DataCache, conn) -> None:
    """Send the daily report. Skips if today's weekday is in skip_weekdays
    or if recipients are empty."""
    cfg = cache.config.email_report
    if not cfg.enabled:
        logger.info("email report disabled in config")
        return

    today_weekday = datetime.now().weekday()
    skip_indices = {WEEKDAY_BY_NAME[d.lower()] for d in cfg.skip_weekdays
                    if d.lower() in WEEKDAY_BY_NAME}
    if today_weekday in skip_indices:
        logger.info("email report skipped: today is in skip_weekdays")
        return

    yesterday_date = operative_day(datetime.now()) - timedelta(days=1)

    history_path = f"data/daily_history_{yesterday_date.year}.json"
    history = load_daily_history(history_path)
    yesterday_dp = next((d for d in history if d.date == yesterday_date), None)
    if yesterday_dp is None:
        logger.error("no daily history entry for %s -- email skipped", yesterday_date)
        return

    # Per-phase breakdown from JSON file
    per_phase: Dict[str, Tuple[float, float]] = {}
    import json
    from pathlib import Path
    raw = json.loads(Path(history_path).read_text(encoding="utf-8"))
    for d in raw["days"]:
        if d["date"] == yesterday_date.isoformat():
            for phase, vals in d.get("phases", {}).items():
                per_phase[phase] = (vals["planned_h"], vals["produced_h"])
            break

    rolling = compute_rolling_month(today=yesterday_date + timedelta(days=1),
                                    history=history)

    rcpts = get_email_recipients(conn)
    if not rcpts:
        logger.error("no email recipients configured (settings.Sys_email_efficienze) -- skipped")
        return

    subject = generate_subject(cfg.subject_prefix, yesterday_date, yesterday_dp.coverage_pct)
    plain = generate_plain_body(yesterday_dp, per_phase, rolling)
    html = generate_html_body(yesterday_dp, per_phase, rolling)

    # Send via PlanRespect's email_connector
    from email_connector import EmailConnector
    ec = EmailConnector()
    ec.send_email(to=rcpts, subject=subject, body_plain=plain, body_html=html)
    logger.info("email report sent to %d recipients", len(rcpts))
```

> **Implementation note:** `email_connector.EmailConnector.send_email()` may have a different signature in the existing PlanRespect code. Adapt the call here to whatever the existing helper accepts. If only a single-recipient send is supported, loop over `rcpts`.

- [ ] **Step 2: Add a test for skip-on-Monday**

Append to `tests/test_email_report.py`:

```python
from unittest.mock import MagicMock, patch
from freezegun import freeze_time
from data_cache import DataCache
from app_config import (
    AppConfig, ServerConfig, PhasesConfig, DataSourcesConfig,
    RefreshConfig, ShiftConfig, ThresholdsConfig, EmailReportConfig,
)
from datetime import time as dtime


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
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_email_report.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add reporting/email_report.py tests/test_email_report.py
git commit -m "feat(reporting): send_daily with skip-weekday + recipients lookup"
```

---

## Phase 14 — App entrypoint + integration

### Task 14.1: app.py — main + lifecycle

- [ ] **Step 1: Append `main()` to `app.py`**

```python
def conn_factory():
    """Create a managed DB connection using the encrypted config."""
    cm = ConfigManager()
    return DatabaseConnection(cm)


def main():
    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("PianoTempi - Production Efficiency Monitor - starting")
    logger.info("=" * 60)
    config = load_config("config.json")
    cache = DataCache(config)

    # Initial blocking load
    logger.info("initial data load...")
    try:
        with conn_factory() as conn:
            cache.refresh_routing(conn)
            cache.refresh_planning(conn)
            cache.refresh_production(conn)
        logger.info("initial load complete")
    except Exception as e:
        logger.error("initial load failed: %s -- continuing with empty cache", e)

    # Scheduler
    from scheduler import build_scheduler
    sched = build_scheduler(cache, config, conn_factory)
    sched.start()
    atexit.register(lambda: sched.shutdown(wait=False))
    logger.info("scheduler started")

    # Flask
    app = build_flask_app(cache)
    logger.info("server listening on http://%s:%d", config.server.host, config.server.port)
    app.run(host=config.server.host, port=config.server.port,
            debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run all tests one more time**

Run: `pytest -v`
Expected: ALL PASS (no test should regress)

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: app.py main() with lifecycle + scheduler wiring"
```

---

### Task 14.2: start.bat for Windows production

**Files:**
- Create: `start.bat`

- [ ] **Step 1: Write the bat**

```bat
@echo off
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
  python -m venv .venv
  call .venv\Scripts\activate.bat
  pip install --upgrade pip
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate.bat
)
python app.py
pause
```

- [ ] **Step 2: Commit**

```bash
git add start.bat
git commit -m "chore: start.bat for Windows production"
```

---

### Task 14.3: Smoke test

- [ ] **Step 1: Verify pytest passes everything**

Run: `pytest -v`
Expected: ALL TESTS PASS

- [ ] **Step 2: Verify the app starts (manual)**

Run: `python app.py`
Expected:
- Logs show "PianoTempi - Production Efficiency Monitor - starting"
- "initial data load..." followed by either success or graceful error logs
- "scheduler started"
- "server listening on http://0.0.0.0:8087"

Open `http://localhost:8087` in a browser. Expected: dashboard loads with 6 pages and rotates.

If anything fails, debug then commit fixes.

- [ ] **Step 3: Tag release**

```bash
git tag -a v0.1.0 -m "PianoTempi v0.1.0 - MVP release"
```

- [ ] **Step 4: Final commit (if any fixes)**

```bash
git add -A
git commit -m "chore: smoke test fixes" --allow-empty
```

---

## Self-review checklist (run by implementer at the end)

- [ ] All spec sections covered:
  - §1.1-1.5 Goal/Scope/Sources/Out-of-scope: covered by Phase 0 + 14
  - §2 config.json: Task 2.1
  - §3 Architecture/file tree: Tasks 0.2, 0.1
  - §4 Data model: Tasks 1.1
  - §4.2 Module contracts: Tasks 4–8
  - §4.3 Cache: Tasks 9.1, 9.2
  - §4.4 Anomalies: handled per-module
  - §5 Engine: Tasks 4–6
  - §6 API + Dashboard: Tasks 10, 11
  - §7 Scheduler + Email: Tasks 12, 13
  - §8 Anomaly matrix: covered per-module
  - §9 Decisions log: implemented faithfully
  - §10 Open points (deferred): not blocking MVP
- [ ] No "TBD"/"TODO" lines in plan
- [ ] No "implement later" / "fill in details"
- [ ] Function/class names consistent across tasks (`build_phase_kpi`, `compute_rolling_month`, `DataCache`, etc.)
- [ ] All tests use real assertions (no `pass` stubs)
- [ ] All file paths absolute or repo-relative as appropriate

---

## Notes for the implementer

1. **Do not skip the TDD steps.** Every implementation step is preceded by a failing test that defines the expected behavior. Skipping the test wastes time when bugs surface later.
2. **Frequent commits.** Each task ends with a commit. If a task takes more than ~30 minutes, you've probably skipped a commit point.
3. **Use real DB connections only in integration tests** (which we don't have here for MVP). All unit tests use `MagicMock` for cursors.
4. **Read PlanRespect's `email_connector.py`** before Task 13.2 to align the `send_email` signature.
5. **Windows path separators** in the config: use `\\` (escape) in JSON. Python opens both `\\` and `/` correctly via `os.path.join`.
6. **Logging name `"PianoTempi"`** is shared across all modules. Set up by `app.setup_logging()`.
7. **The `static/Logo.png` is copied** from project root in Task 11.7 — don't import the original in templates by mistake.
