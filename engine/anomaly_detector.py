# engine/anomaly_detector.py
"""Pure anomaly detection: given current cycles + plan + production data,
return a list of detected anomalies."""
from dataclasses import dataclass
from typing import Dict, List, Tuple

from engine.cycle_engine import strip_revision_suffix
from engine.models import PlanRow


@dataclass(frozen=True)
class Anomaly:
    category: str            # 'missing_cycle' | 'unknown_planning_phase' | 'unresolved_order'
    order_number: str        # may be empty if not applicable
    phase_name: str          # canonical when known
    product_code: str        # may be empty if not resolved
    detail: str              # human-readable


def detect_anomalies(
    plan_rows: List[PlanRow],
    cycles: Dict[Tuple[str, str], float],
    order_to_product: Dict[str, str],
    aliases: Dict[str, str],
    raw_planning_phase_names: List[str],   # all planning Excel phase_name values seen today (raw)
) -> List[Anomaly]:
    """
    Detect three categories of anomaly:

    1. missing_cycle — a plan row has no cycle in routing for its
       (product, canonical_phase), even after revision-suffix fallback.
    2. unknown_planning_phase — a planning phase appeared in raw input but
       has no alias entry AND it's not directly present in cycles
       (i.e. the user probably needs to add an alias).
    3. unresolved_order — a plan row's order_number is missing from
       order_to_product (DB lookup failed for it).
    """
    anomalies: List[Anomaly] = []

    # 1. missing_cycle and 3. unresolved_order
    for r in plan_rows:
        if r.order_number not in order_to_product:
            anomalies.append(Anomaly(
                category="unresolved_order",
                order_number=r.order_number,
                phase_name=r.phase_name,
                product_code=r.product_code or "",
                detail=f"Order '{r.order_number}' not found in Traceability_rs.Orders",
            ))
            # If unresolved we can't check the cycle either, skip this row
            continue
        # try cycle lookup with fallback
        key = (r.product_code, r.phase_name)
        if key not in cycles:
            stripped = strip_revision_suffix(r.product_code)
            if stripped == r.product_code or (stripped, r.phase_name) not in cycles:
                anomalies.append(Anomaly(
                    category="missing_cycle",
                    order_number=r.order_number,
                    phase_name=r.phase_name,
                    product_code=r.product_code,
                    detail=(
                        f"No cycle time in routing for product='{r.product_code}' "
                        f"phase='{r.phase_name}' (qty={r.planned_qty})"
                    ),
                ))

    # 2. unknown_planning_phase — phases seen in raw input that don't have
    # an alias (canonicalize is identity) AND are not present as a key in any cycle.
    cycle_phases = {p for (_, p) in cycles.keys()}
    for raw_name in set(raw_planning_phase_names):
        # If aliased, it's known — skip
        if raw_name in aliases:
            continue
        # If the raw name itself appears as a phase header in routing, also known
        if raw_name in cycle_phases:
            continue
        anomalies.append(Anomaly(
            category="unknown_planning_phase",
            order_number="",
            phase_name=raw_name,
            product_code="",
            detail=(
                f"Planning phase '{raw_name}' has no alias entry in config.json "
                f"and no matching column in routing Excel"
            ),
        ))

    return anomalies
