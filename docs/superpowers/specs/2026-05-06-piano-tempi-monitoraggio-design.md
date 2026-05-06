# PianoTempi — Production efficiency monitor — Design

- **Date:** 2026-05-06
- **Status:** Approved (brainstorming complete, ready for implementation plan)
- **Project:** `C:\Users\User\PythonProjetcs\Python\PIanoTempi`
- **Sibling projects referenced:**
  - `C:\Users\User\PythonProjetcs\Python\PlanRespect`
  - `C:\Users\User\PythonProjetcs\PythonProject\Python\Cyclic_monitor_check_Products`
  - `C:\Users\User\PythonProjetcs\Python\ProductionValue` (out of MVP scope)

---

## 1. Goal & Scope

### 1.1 Goal

A web intranet service on `http://<host>:8087` that, for each monitored production phase, displays the comparison between **planned hours** and **produced hours** for the operative day (07:30 → 07:30 next day), broken down by 3 shifts and rotating automatically across phases. At day end (07:31 next day) it sends an email report with previous-day consummative, month-to-date rolling and year-to-date rolling.

### 1.2 Unit of measure

All quantities expressed in **hours with 2 decimals** (e.g. `13.63 h`). No intermediate rounding: aggregate minutes first, divide by 60 at the end.

### 1.3 Operative day

From `07:30:00` of one calendar day to `07:29:59` of the next. Three shifts:

| Code | Wall-clock window | Gross duration | Net duration (info only) |
|---|---|---|---|
| T1 | 07:30 – 15:30 | 8 h | 7.5 h (8 h − 0.5 h unpaid break) |
| T2 | 15:30 – 23:30 | 8 h | 7.5 h |
| T3 | 23:30 – 07:30 | 8 h | 7.5 h — included only if production after 23:30 |

**`day_total_gross_h`** = `16 h` by default (T1+T2). Becomes `24 h` if production query records `ScanTimeFinish ≥ 23:30:00`. Determined data-driven at every refresh.

KPI math uses gross hours throughout (see §5.1). Net hours are recorded here for context (operator productivity calculations in Phase 2) but not used in MVP KPI formulas.

### 1.4 Data sources

| Source | Path/DB | Refresh frequency |
|---|---|---|
| Routing Excel (cycle times) | `T:\D365 routing data\<latest>.xlsx`, sheet `Articles and phases` | 1×/day at 07:00 + on-change watcher |
| Planning Excel | `T:\Planning\<latest>.xlsx`, sheet `PlanningMachine` | every 30 min |
| SQL production | DB `Traceability_rs` (queries reused/extended from PlanRespect / Cyclic_monitor) | every 60 sec |
| SQL phase mapping | `Employee.dbo.CdcSubLinkTraces + TraceabilityPlanning_RS.dbo.Phase + traceability_rs.dbo.Phases` | at every routing refresh |
| SQL email recipients | `traceability_rs.dbo.settings WHERE Attribute='Sys_email_efficienze'` | at every email send |

### 1.5 Out of MVP scope (deferred to Phase 2)

- Workforce theoretical capacity (per shift)
- Workforce actual presence (per shift)
- Efficiency presence → production
- Machine capacity (pieces/hour)
- Economic value (€) of produced/planned
- Historical day navigation (date picker) — only "today" supported in MVP

---

## 2. Configuration — `config.json`

Located at project root. **All runtime parameters live here**; no magic values hard-coded in code. Credentials remain in encrypted files (`db_config.enc`, `email_credentials.enc`).

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 8087
  },
  "phases": {
    "monitored": [
      "ASSEMBLY", "COATING", "EOLTEST", "ICT",
      "PROGRAMING", "PTHSEL", "SMT"
    ],
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
  "thresholds": {
    "green_min_coverage_pct": 95,
    "yellow_min_coverage_pct": 80
  },
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

### 2.1 Notes on config behaviour

- `phases.monitored` is an ordered list of phase names matching column-B+ headers in the routing Excel. Rotation pages: `[1,2]`, `[3,4]`, `[5,6]`, `[7]` (single full-width if odd).
- `thresholds` drives the day-coverage badge color: green ≥95%, yellow 80–94.99%, red <80%.
- `refresh.routing_daily_at` is the cron time; an additional on-change check runs at every `planning` refresh (compare `mtime` of latest file).
- `email_report.skip_weekdays` is extensible to future holidays. MVP: `["monday"]` only.
- `phases.manual_navigation_pause_seconds = 60` — when user clicks prev/next/dot/combo, auto-rotation pauses this long before resuming.

---

## 3. Architecture & Project Structure

### 3.1 Approach

**Hybrid (chosen)**: standalone Flask app, separates I/O from pure-calculation modules but keeps top level flat. Reuses code from `PlanRespect` and `Cyclic_monitor_check_Products` by **copying** specific functions/queries (not by importing across project boundaries).

### 3.2 File tree

```
PIanoTempi/
├── app.py                       # Flask + lifecycle + scheduler bootstrap
├── scheduler.py                 # APScheduler: 4 jobs
├── config.json                  # runtime config (all params)
├── app_config.py                # JSON parser + dataclass config
├── data_cache.py                # in-memory cache (singleton)
├── db_connection.py             # already present (copied from PlanRespect)
├── config_manager.py            # already present (encrypted creds)
├── email_connector.py           # already present (SMTP)
├── data_sources/                # all external I/O
│   ├── __init__.py
│   ├── routing_excel.py         # T:\D365 routing data parser
│   ├── planning_excel.py        # T:\Planning parser (reuse parse_last_phase)
│   └── db_queries.py            # all SQL queries (one module)
├── engine/                      # pure-calculation, zero I/O, fully testable
│   ├── __init__.py
│   ├── models.py                # frozen dataclasses
│   ├── cycle_engine.py          # qty × cycle_time → minutes → hours
│   ├── shift_engine.py          # operative_day, current_shift, shift_window
│   ├── kpi_builder.py           # build PhaseKPI from inputs
│   └── rolling_engine.py        # month-to-date + YTD rolling
├── reporting/
│   ├── __init__.py
│   └── email_report.py          # daily 07:31 report
├── data/                        # local persistence
│   ├── daily_history_2026.json  # one file per year
│   └── ...
├── templates/
│   └── dashboard.html
├── static/
│   ├── Logo.png
│   ├── css/dashboard.css
│   └── js/
│       ├── rotation.js          # auto-rotation + manual nav
│       ├── dashboard.js         # /api polling + DOM updates
│       └── charts.js            # Chart.js factory
├── tests/
│   ├── test_cycle_engine.py
│   ├── test_shift_engine.py
│   ├── test_kpi_builder.py
│   └── test_rolling_engine.py
├── logs/
│   ├── app.log
│   └── scheduler.log
├── requirements.txt
├── start.bat
└── docs/
    └── superpowers/specs/...
```

---

## 4. Data Model & Module Contracts

All UI strings, JSON keys, dataclass fields, log messages: **English**.

### 4.1 Core dataclasses (`engine/models.py`)

```python
@dataclass(frozen=True)
class RoutingCycle:
    product_code: str          # e.g. "1146-6048"
    phase_name: str            # e.g. "EOLTEST" — matches routing column header
    cycle_time_minutes: float  # e.g. 8.18

@dataclass(frozen=True)
class PlanRow:
    order_number: str          # column K (planning)
    phase_name: str            # column E (planning) — = MachineName
    product_code: str          # resolved via Orders+Products lookup, cached
    production_date: date
    planned_qty: int

@dataclass(frozen=True)
class PhaseMap:
    planning_phase_name: str       # = tp.PhaseName, MATCHES routing Excel header
    planning_phase_id: int         # = cs.PhasePlanningId
    traceability_phase_id: int     # = cs.PhaseTraceId, key for production queries
    traceability_phase_name: str   # = p.PhaseName

@dataclass(frozen=True)
class ProductionRow:
    traceability_phase_id: int
    phase_name: str            # planning_phase_name (denormalized for convenience)
    id_order: int
    order_number: str
    prod_date: date            # operative day
    shift_code: str            # "T1" | "T2" | "T3"
    produced_qty: int

@dataclass(frozen=True)
class PhaseKPI:
    phase_name: str
    shift_code: str                 # current shift
    planned_h_day: float
    planned_h_shift: float          # pro-rata: planned_h_day × (7.5 / day_total_h)
    planned_h_so_far_day: float     # linear ramp at "now"
    planned_h_so_far_shift: float   # linear ramp inside current shift
    produced_h_day: float           # cumulative across all shifts
    produced_h_shift: float         # current shift only
    delta_vs_expected_day: float    # produced_h_day - planned_h_so_far_day
    delta_vs_expected_shift: float
    coverage_pct_day: float         # produced_h_day / planned_h_day × 100
    status_color: str               # "green" | "yellow" | "red"
    curve_points: List[Tuple[time, float]]   # cumulative produced_h at end of T1, T2, T3, now

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
    date: date
    planned_h: float
    produced_h: float
    coverage_pct: float

@dataclass(frozen=True)
class RollingData:
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

### 4.2 Module contracts

#### `data_sources/routing_excel.py`

```python
def load_latest_routing(folder: str, sheet: str) -> Tuple[Dict[Tuple[str, str], float], str, datetime]:
    """
    Returns: (cycles_map, source_filename, mtime)
    - Picks the most recent .xlsx by mtime.
    - Skips cells equal to "x" (case-insensitive).
    - Skips non-numeric cells with a warning log.
    - Logs anomalies but never raises (returns empty dict on total failure).
    """
```

#### `data_sources/planning_excel.py`

```python
def load_today_plan(
    folder: str, sheet: str, target_date: date, conn
) -> List[PlanRow]:
    """
    Wraps PlanRespect's parse_last_phase, then enriches each row with
    product_code via resolve_orders_to_products (cached).
    """
```

#### `data_sources/db_queries.py`

```python
def get_phase_mapping(conn) -> List[PhaseMap]:
    """SQL: SELECT cs.PhaseTraceId, p.PhaseName, cs.PhasePlanningId, tp.PhaseName
       FROM Employee.dbo.CdcSubLinkTraces cs
       JOIN TraceabilityPlanning_RS.dbo.Phase tp ON tp.PhaseId = cs.PhasePlanningId
       JOIN traceability_rs.dbo.Phases p ON p.IdPhase = cs.PhaseTraceId"""

def resolve_orders_to_products(conn, order_numbers: Iterable[str]) -> Dict[str, Tuple[int, str]]:
    """{order_number: (id_order, product_code)} — reuses PlanRespect resolve_order, batched."""

def get_production_in_window(
    conn, id_order: int, traceability_phase_id: int, start_dt: datetime, end_dt: datetime
) -> int:
    """Adapted from PlanRespect.get_past_production with arbitrary time window.
    Returns produced qty (DISTINCT BoardLabels) for that order/phase in the window.
    Filter: Scannings.IsPass = 1 (only good pieces).
    Window: Scannings.ScanTimeFinish BETWEEN start_dt AND end_dt (start inclusive, end exclusive
    via end_dt = window_end + 1 microsecond, or use < end_dt in the SQL)."""

def get_email_recipients(conn) -> List[str]:
    """SELECT Value FROM traceability_rs.dbo.settings WHERE Attribute='Sys_email_efficienze'.
    If multiple rows exist for that Attribute, takes the first row only.
    Value is split on both ',' and ';'. Empty/whitespace tokens are dropped.
    Returns [] if no row matches (caller logs error and skips send)."""
```

#### `engine/cycle_engine.py`

```python
def minutes_to_hours(m: float) -> float:
    return round(m / 60.0, 2)

def compute_planned_minutes_by_phase(
    plan: List[PlanRow],
    cycles: Dict[Tuple[str, str], float]
) -> Dict[str, float]:
    """For each plan row: minutes = qty × cycles[(product_code, phase_name)].
    Aggregate by phase_name. Missing (product, phase) → log warning, skip."""

def compute_produced_minutes_by_phase_shift(
    plan: List[PlanRow],
    cycles: Dict[Tuple[str, str], float],
    produced: Dict[Tuple[int, int, str], int],   # (id_order, traceability_phase_id, shift) -> qty
    order_to_product: Dict[str, str]
) -> Dict[Tuple[str, str], float]:
    """{(phase_name, shift_code): minutes} — multiplies each (order, phase, shift)
    by the cycle time of (product_code, phase_name). Aggregates by (phase, shift)."""
```

#### `engine/shift_engine.py`

```python
def operative_day(now: datetime, day_start: time = time(7, 30)) -> date:
    """If now < 07:30 → previous calendar day."""

def current_shift(now: datetime, shifts: List[ShiftConfig]) -> str:
    """Returns 'T1' | 'T2' | 'T3' handling T3 wrap."""

def shift_window(d: date, shift: ShiftConfig) -> Tuple[datetime, datetime]:
    """For T3, end is on d+1."""

def day_total_gross_hours(any_t3_production: bool) -> float:
    """24.0 if any T3 production exists (ScanTimeFinish >= 23:30), otherwise 16.0.
    Used as the day denominator for pro-rata and 'by now' linear ramp."""
```

#### `engine/kpi_builder.py`

```python
def build_phase_kpi(
    phase_name: str,
    plan: List[PlanRow],
    cycles: Dict[Tuple[str, str], float],
    produced: Dict[Tuple[int, int, str], int],
    order_to_product: Dict[str, str],
    now: datetime,
    shifts: List[ShiftConfig],
    thresholds: ThresholdsConfig
) -> PhaseKPI:
    """Pipeline (uses GROSS hours throughout — see §5.1):
    1.  planned_min_day = compute_planned_minutes_by_phase(plan, cycles)[phase_name]
    2.  planned_h_day   = planned_min_day / 60
    3.  shift_curr      = current_shift(now, shifts)
    4.  day_total_gross = 16h if no T3 production, else 24h
    5.  planned_h_shift = planned_h_day × (8 / day_total_gross)
    6.  produced_by_phase_shift = compute_produced_minutes_by_phase_shift(...)
    7.  produced_h_day   = sum across all shifts of produced_by_phase_shift[(phase, *)] / 60
    8.  produced_h_shift = produced_by_phase_shift[(phase, shift_curr)] / 60
    9.  gross_elapsed_day   = clip(0, day_total_gross, (now − 07:30 of operative_day) in hours)
    10. planned_h_so_far_day = planned_h_day × (gross_elapsed_day / day_total_gross)
    11. gross_elapsed_shift  = clip(0, 8, (now − shift_start_curr) in hours)
    12. planned_h_so_far_shift = planned_h_shift × (gross_elapsed_shift / 8)
    13. delta_vs_expected_day   = produced_h_day   − planned_h_so_far_day
        delta_vs_expected_shift = produced_h_shift − planned_h_so_far_shift
    14. coverage_pct_day = (produced_h_day / planned_h_day × 100) if planned_h_day > 0 else 0
    15. status_color: green ≥ green_min_coverage_pct, yellow ≥ yellow_min_coverage_pct, else red
    16. curve_points: at most 4 points
        (T1_end_time, cumul_h_at_T1_end) if now > T1_end
        (T2_end_time, cumul_h_at_T2_end) if now > T2_end
        (T3_end_time, cumul_h_at_T3_end) if now > T3_end (i.e. operative day done)
        (now, produced_h_day) — current cumul, always included if any shift open
    All hours rounded to 2 decimals at the final step.
    """
```

#### `engine/rolling_engine.py`

```python
def compute_rolling_month(today: date, history: DailyHistory) -> RollingData:
    """Sum days from 1st of month to yesterday. Today excluded (in progress)."""

def compute_y2d(today: date, history: DailyHistory) -> YTDTotals:
    """Sum days from 2026-01-01 to yesterday."""
```

### 4.3 Cache (`data_cache.py`)

Single `DataCache` singleton holding:

| Field | Type | Refreshed by |
|---|---|---|
| `routing_cycles` | `Dict[Tuple[str,str], float]` | `refresh_routing` job (07:00 + on-change) |
| `phase_mapping` | `Dict[str, int]` (planning_phase_name → traceability_phase_id) | with routing |
| `today_plan` | `List[PlanRow]` | `refresh_planning` job (every 30 min) |
| `phase_kpis` | `Dict[str, PhaseKPI]` | `refresh_production` job (every 60 sec) |
| `total_kpi` | `TotalKPI` | derived from phase_kpis at same refresh |
| `rolling_data` | `RollingData` | every 5 min (cached separately) |
| `last_refresh_ts` | `Dict[str, datetime]` | per-source timestamps for `/api/health` |

Frontend polling reads only from cache; never triggers I/O.

### 4.4 Anomalies tracked

- Product in planning but not in routing → log warning, row skipped, panel shows warning icon
- Phase in `phases.monitored` but not in routing → panel shows "no data"
- Routing/planning file missing → `last_refresh_ts` becomes stale, frontend shows red banner
- SQL query fails → cache untouched, KPIs continue showing with "stale" badge

---

## 5. Engine of calculation — implementation notes

(Already covered in Section 4 contracts.)

### 5.1 Gross vs net hours — convention

KPI math uses **gross wall-clock hours** consistently. Net hours (7.5 per shift) are documented in §1.3 for context but NOT used in KPI calculations. Reasoning: the chart x-axis is wall-clock (07:30 → 07:30) and using gross everywhere keeps the numeric KPIs aligned with the chart visualization.

| Constant | Value | Used in |
|---|---|---|
| `shift_gross_h` | 8 (always) | shift pro-rata, "by now" calc inside shift |
| `day_total_gross_h` | 16 if T3 inactive, 24 if T3 active | day pro-rata, "by now" calc on day |

Pro-rata formula:
```
planned_h_shift = planned_h_day × (shift_gross_h / day_total_gross_h)
```

Linear ramp ("by now") formula:
```
gross_elapsed_day = max(0, min(day_total_gross_h, (now − 07:30 of operative_day) in hours))
planned_h_so_far_day = planned_h_day × (gross_elapsed_day / day_total_gross_h)

gross_elapsed_shift = max(0, min(shift_gross_h, (now − shift_start) in hours))
planned_h_so_far_shift = planned_h_shift × (gross_elapsed_shift / shift_gross_h)
```

The 30-minute break is absorbed implicitly by the linear approximation — we don't model it explicitly.

### 5.2 Test plan (`tests/`)

- **`test_cycle_engine.py`**: 1 product/1 phase; 2 products same phase; missing (product, phase) → warning; empty plan; empty cycles
- **`test_shift_engine.py`**: 06:00 → operative_day=yesterday, current_shift=T3; 09:00 → T1; 23:45 → T3 with wrap; T3 active vs inactive
- **`test_kpi_builder.py`**: green/yellow/red coverage; T3 inactive vs active; planning empty; produced empty; delta positive/negative; curve_points generation at various times
- **`test_rolling_engine.py`**: multi-day history; gaps (holidays); month boundary; YTD across years

---

## 6. API & Dashboard

### 6.1 Endpoints

| Method | Path | Use |
|---|---|---|
| `GET` | `/` | Dashboard HTML |
| `GET` | `/api/phases` | All `PhaseKPI` for current operative day |
| `GET` | `/api/totals` | `TotalKPI` (header strip + Total Summary page) |
| `GET` | `/api/rolling-month` | `RollingData` (Monthly Rolling + YTD page) |
| `GET` | `/api/health` | `last_refresh_ts` per source + stale flags |
| `GET` | `/static/...` | assets (Logo, css, js, Chart.js) |

All responses JSON. Cache-only reads; no I/O during request.

### 6.2 Dashboard layout

```
┌───────────────────────────────────────────────────────────────────┐
│ [Logo]   PRODUCTION EFFICIENCY    Wed 06/05/2026 14:23:08  ●data ok│
├───────────────────────────────────────────────────────────────────┤
│ Day plan 168h│ Produced 68.5h│ Δ -2.9h│ Day coverage 40.8%        │
├──────────────────────────────┬────────────────────────────────────┤
│ ASSEMBLY                     │ COATING                            │
│ [cumulative chart]           │ [cumulative chart]                 │
│ T2 plan / T2 produced /      │ T2 plan / T2 produced /            │
│ Day plan / Day produced /    │ Day plan / Day produced /          │
│ Δ vs expected (day)          │ Δ vs expected (day)                │
├──────────────────────────────┴────────────────────────────────────┤
│ ◀ ⏸ ▶  [Go to page ▾]   • • • • • •     page 1/6 · auto in 14s   │
└───────────────────────────────────────────────────────────────────┘
```

### 6.3 Page sequence

1. Phases 1+2
2. Phases 3+4
3. Phases 5+6
4. Phase 7 (full width if odd count)
5. **Total Summary** — large global KPIs + cumulative chart of all phases summed
6. **Monthly Rolling + YTD** — daily curves (planned vs produced) from 1st of month + YTD totals box

Loop back to page 1.

### 6.4 Charts

**Phase panel intra-day chart:**
- X-axis: 07:30 of operative day → 07:30 of next day (with shift dividers)
- Y-axis: cumulative hours (0 → planned_h_day)
- Blue straight line: planned ramp (0 → planned_h_day)
- Green curve: cumulative produced (real curve_points up to now)
- Blue dot at "now" position on planned line, with numeric label
- Green dot at "now" position on produced curve, with numeric label
- Yellow/green vertical segment between the two = visual delta

**Monthly Rolling chart (final page):**
- X-axis: days from 1st of month
- Two real curves: planned (blue) and produced (green)
- Per-day points connected with straight segments
- YTD totals shown in a separate box below the chart

### 6.5 Frontend tech

- Vanilla HTML/CSS/JS + **Chart.js v4** (bundled in `static/js/chartjs.min.js`)
- One `templates/dashboard.html` with all pages in DOM, `.active` class rotates
- `static/js/rotation.js`: timer + manual nav (◀ ⏸ ▶ + dropdown + dot click) + 60s pause-on-manual
- `static/js/dashboard.js`: polls `/api/phases` + `/api/totals` every 30 s, updates DOM/charts (`chart.update('none')` to avoid jarring animations)
- `static/js/charts.js`: factory functions for the 3 chart types

### 6.6 Stale state visual feedback

- 🟢 sources fresh (within 2× refresh interval)
- 🟡 sources stale but KPIs usable (>2× refresh) — yellow badge on header
- 🔴 critical (e.g. routing missing) — red full-width banner at top

---

## 7. Scheduler & Email Report

### 7.1 Scheduler jobs (APScheduler `BackgroundScheduler`)

| Job ID | Trigger | Function |
|---|---|---|
| `refresh_routing` | cron `07:00` daily + on-change check | `routing_excel.load_latest_routing()` → cache |
| `refresh_planning` | interval 30 min | `planning_excel.load_today_plan()` → cache; also re-checks routing mtime |
| `refresh_production` | interval 60 sec | full pipeline: per-order DB queries → `kpi_builder.build_phase_kpi()` → cache |
| `daily_history_commit` | cron `07:30:30` daily | append yesterday's totals to `daily_history_<year>.json` |
| `daily_email_report` | cron `07:31` daily | `email_report.send_daily()` (skip Monday) |

APScheduler config: `coalesce=True, max_instances=1` per job to avoid pile-up. Errors logged to `logs/scheduler.log` but never propagate.

### 7.2 Daily history persistence

File: `data/daily_history_<year>.json` (one per year, atomic write via tmp + os.replace).

Format:
```json
{
  "year": 2026,
  "days": [
    {
      "date": "2026-05-05",
      "phases": {
        "ASSEMBLY": {"planned_h": 24.00, "produced_h": 22.50},
        "COATING":  {"planned_h": 16.00, "produced_h": 15.80}
      },
      "totals": {"planned_h": 168.00, "produced_h": 154.30, "coverage_pct": 91.8}
    }
  ]
}
```

If file is corrupt: rename to `daily_history_<year>.json.corrupt-<ts>` and recreate.

### 7.3 Email report (`reporting/email_report.py`)

**Trigger**: cron `07:31` daily.
**Skip logic**: if `today.weekday()` matches an entry in `email_report.skip_weekdays`, log "skipped" and exit.
**Recipients**: SQL `SELECT Value FROM traceability_rs.dbo.settings WHERE Attribute='Sys_email_efficienze'`. `Value` is CSV (`,` or `;`). Empty → log error + skip send.

**Subject**: `[Production Efficiency] Daily report 2026-05-05 — coverage 91.8%`

**Body** (HTML + plain-text fallback, inline CSS, Outlook-compatible):

```
YESTERDAY (2026-05-05)
======================
Total day plan:      168.00 h
Total produced:      154.30 h
Coverage:             91.8%
Δ vs plan:           -13.70 h

Per-phase breakdown:
  ASSEMBLY    plan 24.00  prod 22.50  cov 93.7%   Δ -1.50
  COATING    plan 16.00  prod 15.80  cov 98.7%   Δ -0.20
  ...

MONTH TO DATE (2026-05-01 → 2026-05-05)
=======================================
Plan:        720.00 h
Produced:    668.40 h
Coverage:     92.8%
Working days: 4

YEAR TO DATE (2026-01-01 → 2026-05-05)
======================================
Plan:      18'240.00 h
Produced:  16'893.50 h
Coverage:     92.6%
Working days: 87
```

Logo embedded as `cid:logo` if `logo_path` valid.

**Data sourcing**:
1. Yesterday → just-written entry in `daily_history`
2. MTD → sum of entries from 1st of month to yesterday (today excluded — in progress)
3. YTD → sum of all entries from 2026-01-01 to yesterday

**Working days** = number of `days` entries in `daily_history` where `planned_h > 0`.

**SMTP**: reuse `email_connector.py` from PlanRespect; credentials in `email_credentials.enc`.

### 7.4 App lifecycle

```python
# app.py
def create_app():
    config = load_config("config.json")
    cache = DataCache(config)

    cache.refresh_routing()      # blocking initial load
    cache.refresh_planning()
    cache.refresh_production()

    scheduler = build_scheduler(cache, config)
    scheduler.start()

    flask_app = build_flask_app(cache)
    atexit.register(lambda: scheduler.shutdown(wait=True))
    return flask_app
```

---

## 8. Anomaly handling matrix

| Anomaly | Behaviour |
|---|---|
| Routing file missing | Log error + empty cache → panels show "no data" + red banner |
| Planning file missing | Log error + empty plan → KPIs show 0 + red banner |
| DB unreachable | Log error + cache untouched → KPIs marked "stale" |
| Settings table empty (`Sys_email_efficienze`) | Log error + skip email |
| `daily_history.json` corrupt | Rename to `.corrupt-<ts>` + recreate fresh |
| Job runtime > interval | APScheduler `coalesce=True, max_instances=1` prevents pile-up |
| Product in planning, not in routing | Log warning, row skipped, panel warning icon |
| Phase in `phases.monitored`, not in routing | Panel shows "no data" |

---

## 9. Decisions log

| # | Decision | Rationale |
|---|---|---|
| 1 | Standalone app (not extension of PlanRespect) | PlanRespect is in production with active alerts; isolation prevents regression risk |
| 2 | Hours with 2 decimals (no integer rounding) | User decision; avoids ambiguity on rounding rule |
| 3 | Aggregate minutes first, divide at end | Avoids per-piece rounding accumulation |
| 4 | Planning source = `T:\Planning` + `PlanningMachine` (PlanRespect's source) | User clarified; reuse `parse_last_phase` |
| 5 | Routing source = `T:\D365 routing data` + `Articles and phases` | User specification |
| 6 | Phase mapping via `Employee.dbo.CdcSubLinkTraces` | User-provided query (replaces 3-level resolve_phase from PlanRespect) |
| 7 | Produced hours = qty (DB) × cycle time (Excel), per (order, phase, shift) | Approach C (loop per order) — reuses `get_past_production` adapted to time window |
| 8 | Shift duration net = 7.5 h (8 h gross − 30 min break) | Original plan + user confirmation |
| 9 | T3 active only if production after 23:30 (data-driven) | User specification; avoids inflated denominators on 2-shift days |
| 10 | Pro-rata planned per shift (linear, gross time) | User-confirmed; simple and matches chart visualization |
| 11 | Status thresholds: green ≥95% / yellow 80–95% / red <80% | User-confirmed |
| 12 | Cumulative line chart per phase (replaces pie chart) | User suggestion: planned = ramp, produced = real curve |
| 13 | "By now" linear ramp + Δ vs expected | User addition; complements the chart |
| 14 | Manual page navigation (◀ ⏸ ▶ + dropdown + clickable dots) + auto-resume after 60 s | User addition |
| 15 | All UI labels in English (also JSON keys, dataclass fields) | User decision |
| 16 | Email report at 07:31, skip Monday | User decision |
| 17 | Daily history persisted in `daily_history_<year>.json` (one file per year) | Simple, no new DB schema; user-confirmed |
| 18 | Pre-step at 07:30:30 commits yesterday before email at 07:31 | Avoids race with production refresh |
| 19 | Email subject: `[Production Efficiency] Daily report YYYY-MM-DD — coverage XX.X%` | User-confirmed |
| 20 | Refresh strategy: routing 1×/day + on-change, planning 30 min, SQL 60 s, FE polling 30 s | Approach A — matches PlanRespect cadence |
| 21 | JSON config (not YAML) | User decision |
| 22 | Server port 8087 (PlanRespect uses 8085) | User decision |
| 23 | Today-only display (no historical date picker in MVP) | User decision; historical data in email report |
| 24 | No presence/efficiency/capacity KPIs in MVP | User scope cut |
| 25 | No economic value KPIs in MVP | User scope cut (Phase 2 — `ProductionValue` integration) |

---

## 10. Open points (deferred — not blocking MVP)

- **Workforce presence query** — when available, integrate as new `data_sources.db_queries.get_presence_by_phase_shift()` and add presence ramp to chart
- **Workforce theoretical capacity query** — same pattern
- **Machine capacity (pieces/hour)** — distinct logic from man-hours, separate KPI layer
- **Economic value** — integrate `ProductionValue` services as new optional layer (toggle "hours" / "€" view)
- **Historical day picker** — add `?date=YYYY-MM-DD` parameter to `/api/*` endpoints
- **Holiday-aware email skip** — extend `skip_weekdays` to a list of dates
