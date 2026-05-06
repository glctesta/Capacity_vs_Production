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
