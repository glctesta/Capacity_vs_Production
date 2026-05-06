# data_sources/planning_excel.py
"""Public planning Excel API: find latest, parse, enrich with product_code."""
import logging
from datetime import date
from typing import List

from data_sources._planning_excel_parser import _PlanRowRaw, parse_last_phase
from data_sources.routing_excel import find_latest_routing_file
from engine.models import PlanRow

logger = logging.getLogger("PianoTempi")


def resolve_orders_to_products(conn, order_numbers):
    """Lazy import — keeps test patching simple."""
    from data_sources.db_queries import resolve_orders_to_products as _impl
    return _impl(conn, order_numbers)


def load_today_plan(folder: str, sheet: str, target_date: date, conn) -> List[PlanRow]:
    """Load planning rows for `target_date`, enriched with product_code."""
    src = find_latest_routing_file(folder)
    if src is None:
        logger.error("planning file not found in %s", folder)
        return []

    raw_rows = parse_last_phase(src, sheet)
    today_raw = [r for r in raw_rows if r.production_date == target_date]
    if not today_raw:
        return []

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
