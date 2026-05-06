# engine/cycle_engine.py
"""Pure math: minutes <-> hours, phase aggregation. No I/O."""
import logging
from typing import Dict, List, Tuple

from engine.models import PlanRow

logger = logging.getLogger("PianoTempi")


def minutes_to_hours(m: float) -> float:
    """Convert minutes to hours rounded to 2 decimals."""
    return round(m / 60.0, 2)


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
