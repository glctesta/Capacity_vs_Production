# engine/kpi_builder.py
"""Builds PhaseKPI from primitives. Pure function."""
from datetime import datetime, time, timedelta
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
    """See spec: gross-hours convention. All hours rounded to 2 decimals at the end."""
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

    # 9-10: linear ramp on day (gross time elapsed since 07:30 of operative day)
    op_day = operative_day(now)
    day_start_dt = datetime.combine(op_day, time(7, 30))
    gross_elapsed_day_h = _clip(0.0, day_total_gross,
                                (now - day_start_dt).total_seconds() / 3600.0)
    planned_h_so_far_day = round(
        planned_h_day * (gross_elapsed_day_h / day_total_gross), 2,
    ) if day_total_gross > 0 else 0.0

    # 11-12: linear ramp inside current shift
    shift_curr_cfg = next(s for s in shifts if s.code == shift_curr)
    shift_start_dt, _ = shift_window(op_day, shift_curr_cfg)
    # Handle T3 wrap: if current shift is T3 and now < shift_start, the shift started
    # at op_day 23:30 (where op_day == today's calendar date when now is 00:00-07:30)
    if shift_curr == "T3" and now < shift_start_dt:
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

    # 16: curve_points (filled in sub-task 5.2)
    curve_points: List[Tuple[time, float]] = []

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
