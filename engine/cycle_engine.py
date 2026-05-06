# engine/cycle_engine.py
"""Pure math: minutes <-> hours, phase aggregation. No I/O."""
import logging
from typing import Dict, List, Optional, Tuple

from engine.models import PlanRow

logger = logging.getLogger("PianoTempi")


def minutes_to_hours(m: float) -> float:
    """Convert minutes to hours rounded to 2 decimals."""
    return round(m / 60.0, 2)


def strip_revision_suffix(code: str) -> str:
    """Remove revision suffixes from a product code so it matches the routing.

    Recognized patterns:
      - '|N'  (any digits after '|')          -> drop everything from '|'
      - trailing '-NN' (1-3 digits) with at
        least 3 hyphen-separated segments     -> drop the last segment

    Examples:
      '1547-5038-01'        -> '1547-5038'
      'PFEX+673612A02|1'    -> 'PFEX+673612A02'
      'PFSL+KCE-FCB21|1'    -> 'PFSL+KCE-FCB21'
      '1146-4018'           -> '1146-4018'   (no change, only 2 segments)
    """
    if not code:
        return code
    # 1. Strip after first '|'
    if "|" in code:
        code = code.split("|", 1)[0]
    # 2. Strip trailing '-NN' if 3+ segments and last is 1-3 digits
    parts = code.split("-")
    if len(parts) >= 3 and parts[-1].isdigit() and 1 <= len(parts[-1]) <= 3:
        code = "-".join(parts[:-1])
    return code


def _lookup_cycle(
    cycles: Dict[Tuple[str, str], float],
    product_code: str,
    phase_name: str,
) -> Optional[float]:
    """Try `cycles[(product, phase)]` first; if missing, try with revision suffix
    stripped from `product_code`. Returns None if neither matches."""
    key = (product_code, phase_name)
    if key in cycles:
        return cycles[key]
    stripped = strip_revision_suffix(product_code)
    if stripped != product_code:
        key2 = (stripped, phase_name)
        if key2 in cycles:
            return cycles[key2]
    return None


def compute_planned_minutes_by_phase(
    plan: List[PlanRow],
    cycles: Dict[Tuple[str, str], float],
) -> Dict[str, float]:
    """For each plan row: minutes = qty * cycle_lookup(product, phase).
    Aggregate by phase_name. Missing cycle -> log warning + skip."""
    result: Dict[str, float] = {}
    for row in plan:
        cycle = _lookup_cycle(cycles, row.product_code, row.phase_name)
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
    """Multiply each produced (order, phase, shift) by cycle_lookup(product, phase).
    Aggregate by (phase, shift). Returns {(phase_name, shift_code): minutes}."""
    result: Dict[Tuple[str, str], float] = {}
    for (order_number, phase_name, shift_code), qty in produced.items():
        product_code = order_to_product.get(order_number)
        if product_code is None:
            logger.warning("produced row has unknown order_number=%s -- skipped", order_number)
            continue
        cycle = _lookup_cycle(cycles, product_code, phase_name)
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
