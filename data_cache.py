"""In-memory cache shared between scheduler and Flask routes."""
import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from app_config import AppConfig
from data_sources.db_history import (
    get_history_aggregates,
    upsert_cycles, upsert_plan_history, upsert_prod_history,
    replace_anomalies_for_date,
)
from engine.anomaly_detector import detect_anomalies
from data_sources.db_queries import (
    get_phase_mapping,
    get_production_by_phase_in_window,
    resolve_orders_to_products,
)
from data_sources.planning_excel import load_today_plan
from data_sources.routing_excel import load_latest_routing
from engine.kpi_builder import build_phase_kpi
from engine.models import DayPoint, PhaseKPI, PlanRow, RollingData, TotalKPI
from engine.rolling_engine import compute_rolling_month
from engine.shift_engine import operative_day, shift_window

logger = logging.getLogger("PianoTempi")


def canonicalize(name: str, aliases: Dict[str, str]) -> str:
    """Translate a phase name to its canonical form.
    Returns the alias target if present, else the input unchanged.
    """
    if name is None:
        return ""
    return aliases.get(name, name)


class DataCache:
    """In-memory cache. Single instance built in app.py.
    All mutations done under self.lock() (RLock — reentrant).
    """

    def __init__(self, config: AppConfig):
        self._lock = threading.RLock()
        self.config = config
        # routing — keys are CANONICAL phase names
        self.routing_cycles: Dict[Tuple[str, str], float] = {}
        self.routing_source_path: str = ""
        self.routing_source_mtime: Optional[datetime] = None
        # phase mapping — canonical name -> list of traceability_phase_id
        # (one canonical phase may map to multiple traceability ids,
        # e.g. ASSEMBLY = FINAL ASSEMBLY (110) + PROGRAMARE (112))
        self.phase_mapping: Dict[str, List[int]] = {}
        # planning — phase_name is CANONICAL after canonicalize()
        self.today_plan: List[PlanRow] = []
        self.order_to_product: Dict[str, str] = {}
        self.order_to_id: Dict[str, int] = {}
        # production-derived
        self.phase_kpis: Dict[str, PhaseKPI] = {}
        self.total_kpi: Optional[TotalKPI] = None
        self.rolling_data: Optional[RollingData] = None
        # Raw planning phase names (pre-alias) of last refresh — used for anomaly detection
        self.raw_planning_phase_names: List[str] = []
        # bookkeeping
        self.last_refresh_ts: Dict[str, datetime] = {}

    def lock(self):
        return self._lock

    def refresh_routing(self, conn) -> None:
        with self._lock:
            aliases = self.config.phases.aliases
            cycles_raw, src, mtime = load_latest_routing(
                self.config.data_sources.routing_folder,
                self.config.data_sources.routing_sheet,
            )
            # Canonicalize phase header in cycle keys
            cycles_canon: Dict[Tuple[str, str], float] = {}
            for (product_code, phase_raw), cycle_minutes in cycles_raw.items():
                phase_canon = canonicalize(phase_raw, aliases)
                cycles_canon[(product_code, phase_canon)] = cycle_minutes
            self.routing_cycles = cycles_canon
            self.routing_source_path = src
            self.routing_source_mtime = mtime

            try:
                upsert_cycles(conn, cycles_canon, src or "")
            except Exception as e:
                logger.error("upsert_cycles wrap failed: %s", e)

            try:
                mapping_rows = get_phase_mapping(conn)
                # Build canonical -> [traceability_phase_id, ...]
                canon_to_ids: Dict[str, List[int]] = {}
                for pm in mapping_rows:
                    if not pm.planning_phase_name:
                        continue
                    canon = canonicalize(pm.planning_phase_name, aliases)
                    if pm.traceability_phase_id not in canon_to_ids.setdefault(canon, []):
                        canon_to_ids[canon].append(pm.traceability_phase_id)
                self.phase_mapping = canon_to_ids
                logger.info(
                    "phase mapping loaded: %d canonical phases (%s)",
                    len(self.phase_mapping),
                    {k: v for k, v in self.phase_mapping.items()},
                )
            except Exception as e:
                logger.error("phase mapping query failed: %s -- keeping previous", e)
            self.last_refresh_ts["routing"] = datetime.now()

    def refresh_planning(self, conn) -> None:
        with self._lock:
            aliases = self.config.phases.aliases
            today = operative_day(datetime.now())
            raw_plan = load_today_plan(
                self.config.data_sources.planning_folder,
                self.config.data_sources.planning_sheet,
                target_date=today, conn=conn,
            )
            # Capture raw phase names before canonicalization (for anomaly detection)
            self.raw_planning_phase_names = [r.phase_name for r in raw_plan]
            # Canonicalize phase_name on each row
            canonicalized: List[PlanRow] = []
            translation_summary: Dict[str, str] = {}
            for r in raw_plan:
                canon = canonicalize(r.phase_name, aliases)
                if r.phase_name != canon:
                    translation_summary[r.phase_name] = canon
                canonicalized.append(PlanRow(
                    order_number=r.order_number,
                    phase_name=canon,
                    product_code=r.product_code,
                    production_date=r.production_date,
                    planned_qty=r.planned_qty,
                ))
            if translation_summary:
                logger.info(
                    "planning phase aliases applied: %s", translation_summary,
                )
            self.today_plan = canonicalized
            logger.info("today_plan: %d rows after alias normalization", len(canonicalized))

            try:
                upsert_plan_history(conn, today, canonicalized, self.routing_cycles)
            except Exception as e:
                logger.error("upsert_plan_history wrap failed: %s", e)

            order_numbers = {r.order_number for r in canonicalized}
            resolved = resolve_orders_to_products(conn, order_numbers)
            self.order_to_product = {k: v[1] for k, v in resolved.items()}
            self.order_to_id = {k: v[0] for k, v in resolved.items()}
            self.last_refresh_ts["planning"] = datetime.now()

            try:
                anomalies = detect_anomalies(
                    plan_rows=self.today_plan,
                    cycles=self.routing_cycles,
                    order_to_product=self.order_to_product,
                    aliases=self.config.phases.aliases,
                    raw_planning_phase_names=self.raw_planning_phase_names,
                )
                replace_anomalies_for_date(conn, today, anomalies)
                logger.info("anomalies snapshot for %s: %d entries", today, len(anomalies))
            except Exception as e:
                logger.error("anomaly snapshot failed: %s", e)

    def refresh_production(self, conn) -> None:
        """Query production for ALL orders (not just today's plan) per monitored phase
        and shift window. Resolves any new orders to products, then computes KPIs.
        """
        with self._lock:
            now = datetime.now()
            op_day = operative_day(now)
            shifts = self.config.shifts
            produced: Dict[Tuple[str, str, str], int] = {}
            any_t3_production = False
            seen_order_numbers: set = set()

            # 1. Iterate by monitored canonical phase + shift + traceability id
            for canonical_phase in self.config.phases.monitored:
                trace_ids = self.phase_mapping.get(canonical_phase, [])
                if not trace_ids:
                    # No traceability mapping → can't query; planned hours still work.
                    continue
                for shift in shifts:
                    s_start, s_end = shift_window(op_day, shift)
                    if s_start > now:
                        continue
                    q_end = min(s_end, now)
                    for trace_id in trace_ids:
                        try:
                            rows = get_production_by_phase_in_window(
                                conn, trace_id, s_start, q_end,
                            )
                        except Exception as e:
                            logger.error(
                                "production query failed (trace_id=%d shift=%s): %s",
                                trace_id, shift.code, e,
                            )
                            continue
                        for (id_order, order_number, qty) in rows:
                            if qty <= 0:
                                continue
                            seen_order_numbers.add(order_number)
                            # Cache id_order even before resolving the product
                            self.order_to_id[order_number] = id_order
                            key = (order_number, canonical_phase, shift.code)
                            produced[key] = produced.get(key, 0) + qty
                            if shift.code == "T3":
                                any_t3_production = True

            # 2. Resolve any orders not yet in the product cache (out-of-plan orders).
            unresolved = seen_order_numbers - set(self.order_to_product.keys())
            if unresolved:
                try:
                    new_resolved = resolve_orders_to_products(conn, unresolved)
                    for ord_num, (id_ord, prod_code) in new_resolved.items():
                        self.order_to_product[ord_num] = prod_code
                        self.order_to_id[ord_num] = id_ord
                    logger.info(
                        "resolved %d new out-of-plan order(s) to products",
                        len(new_resolved),
                    )
                except Exception as e:
                    logger.error("resolve out-of-plan orders failed: %s", e)

            # 3. Build PhaseKPI for each monitored phase
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

            try:
                upsert_prod_history(
                    conn, op_day, produced,
                    self.order_to_product, self.routing_cycles, self.phase_mapping,
                )
            except Exception as e:
                logger.error("upsert_prod_history wrap failed: %s", e)

            self.last_refresh_ts["production"] = datetime.now()

    def refresh_rolling(self, conn, now: Optional[datetime] = None) -> None:
        """Refresh Monthly Rolling + YTD aggregates from SQL history.

        Reads PianoTempi_PlanHistory / PianoTempi_ProdHistory via
        get_history_aggregates and stores the resulting RollingData in
        self.rolling_data. Today is excluded by compute_rolling_month
        (rolling/YTD always reflect closed days only).
        """
        with self._lock:
            now = now or datetime.now()
            today = operative_day(now)
            year_start = today.replace(month=1, day=1)
            try:
                agg = get_history_aggregates(conn, year_start, today)
            except Exception as e:
                logger.error("get_history_aggregates failed: %s", e)
                agg = []
            history = [
                DayPoint(
                    date=row["date"],
                    planned_h=float(row["planned_h"]),
                    produced_h=float(row["produced_h"]),
                    coverage_pct=float(row["coverage_pct"]),
                )
                for row in agg
            ]
            self.rolling_data = compute_rolling_month(today, history)
            self.last_refresh_ts["rolling"] = datetime.now()
            logger.info(
                "rolling refreshed: month_plan=%.2fh month_prod=%.2fh "
                "ytd_plan=%.2fh ytd_prod=%.2fh (%d working days month, %d ytd)",
                self.rolling_data.month_planned_h,
                self.rolling_data.month_produced_h,
                self.rolling_data.ytd_planned_h,
                self.rolling_data.ytd_produced_h,
                self.rolling_data.working_days_month,
                self.rolling_data.working_days_ytd,
            )

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
