"""In-memory cache shared between scheduler and Flask routes."""
import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from app_config import AppConfig
from data_sources.db_queries import (
    get_phase_mapping, get_production_in_window, resolve_orders_to_products,
)
from data_sources.planning_excel import load_today_plan
from data_sources.routing_excel import load_latest_routing
from engine.kpi_builder import build_phase_kpi
from engine.models import PhaseKPI, PlanRow, RollingData, TotalKPI
from engine.shift_engine import operative_day, shift_window

logger = logging.getLogger("PianoTempi")


class DataCache:
    """Singleton-style cache. Not enforced as singleton (one instance built in app.py).
    All mutations should be done under self.lock().
    """

    def __init__(self, config: AppConfig):
        self._lock = threading.RLock()
        self.config = config
        # routing
        self.routing_cycles: Dict[Tuple[str, str], float] = {}
        self.routing_source_path: str = ""
        self.routing_source_mtime: Optional[datetime] = None
        # phase mapping — keyed by traceability_phase_name (matches routing headers
        # AND config.phases.monitored). Plan rows are translated upstream so they
        # also use traceability names.
        self.phase_mapping: Dict[str, int] = {}
        # Planning -> traceability name translation (e.g. "FINAL ASSEMBLY" -> "ASSEMBLY")
        self.planning_to_traceability_name: Dict[str, str] = {}
        # planning (after translation, phase_name uses traceability namespace)
        self.today_plan: List[PlanRow] = []
        self.order_to_product: Dict[str, str] = {}
        self.order_to_id: Dict[str, int] = {}
        # production-derived
        self.phase_kpis: Dict[str, PhaseKPI] = {}
        self.total_kpi: Optional[TotalKPI] = None
        self.rolling_data: Optional[RollingData] = None
        # bookkeeping
        self.last_refresh_ts: Dict[str, datetime] = {}

    def lock(self):
        return self._lock

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
                # phase_mapping keyed by traceability name (matches routing headers
                # and config.monitored after the planning->traceability translation).
                self.phase_mapping = {
                    pm.traceability_phase_name: pm.traceability_phase_id
                    for pm in mapping if pm.traceability_phase_name
                }
                # Translation table: planning name (Excel column E) -> traceability name
                self.planning_to_traceability_name = {
                    pm.planning_phase_name: pm.traceability_phase_name
                    for pm in mapping
                    if pm.planning_phase_name and pm.traceability_phase_name
                }
                logger.info(
                    "phase mapping loaded: %d entries (%d planning->traceability translations)",
                    len(self.phase_mapping), len(self.planning_to_traceability_name),
                )
            except Exception as e:
                logger.error("phase mapping query failed: %s -- keeping previous", e)
            self.last_refresh_ts["routing"] = datetime.now()

    def refresh_planning(self, conn) -> None:
        with self._lock:
            today = operative_day(datetime.now())
            raw_plan = load_today_plan(
                self.config.data_sources.planning_folder,
                self.config.data_sources.planning_sheet,
                target_date=today, conn=conn,
            )
            # Translate each row's phase_name from planning namespace to traceability
            # namespace so it matches routing Excel headers and config.monitored.
            translated: List[PlanRow] = []
            unknown: Dict[str, int] = {}
            for r in raw_plan:
                tname = self.planning_to_traceability_name.get(r.phase_name)
                if tname is None:
                    unknown[r.phase_name] = unknown.get(r.phase_name, 0) + 1
                    continue
                translated.append(PlanRow(
                    order_number=r.order_number,
                    phase_name=tname,
                    product_code=r.product_code,
                    production_date=r.production_date,
                    planned_qty=r.planned_qty,
                ))
            if unknown:
                logger.warning(
                    "%d planning rows skipped due to unknown phase name (no mapping): %s",
                    sum(unknown.values()), unknown,
                )
            self.today_plan = translated
            logger.info(
                "today_plan: %d rows after planning->traceability translation (from %d raw)",
                len(translated), len(raw_plan),
            )
            order_numbers = {r.order_number for r in translated}
            resolved = resolve_orders_to_products(conn, order_numbers)
            self.order_to_product = {k: v[1] for k, v in resolved.items()}
            self.order_to_id = {k: v[0] for k, v in resolved.items()}
            self.last_refresh_ts["planning"] = datetime.now()

    def refresh_production(self, conn) -> None:
        with self._lock:
            now = datetime.now()
            op_day = operative_day(now)
            shifts = self.config.shifts
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
                    if s_start > now:
                        continue
                    q_end = min(s_end, now)
                    qty = get_production_in_window(conn, id_order, trace_id, s_start, q_end)
                    if qty > 0:
                        key = (plan_row.order_number, phase_name, shift.code)
                        produced[key] = produced.get(key, 0) + qty
                        if shift.code == "T3":
                            any_t3_production = True

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
