# tests/test_data_cache.py
from datetime import datetime, time
from unittest.mock import MagicMock, patch
from data_cache import DataCache, canonicalize
from app_config import (
    AppConfig, ServerConfig, PhasesConfig, DataSourcesConfig,
    RefreshConfig, ShiftConfig, ThresholdsConfig, EmailReportConfig,
)


def _cfg(aliases=None):
    return AppConfig(
        server=ServerConfig(),
        phases=PhasesConfig(monitored=["ASSEMBLY"], aliases=aliases or {}),
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


def test_canonicalize_with_alias():
    aliases = {"FINAL ASSEMBLY": "ASSEMBLY", "PTHM SELECTIVE": "PTHSEL"}
    assert canonicalize("FINAL ASSEMBLY", aliases) == "ASSEMBLY"
    assert canonicalize("PTHM SELECTIVE", aliases) == "PTHSEL"


def test_canonicalize_passthrough_when_no_alias():
    aliases = {"FINAL ASSEMBLY": "ASSEMBLY"}
    assert canonicalize("FCT", aliases) == "FCT"
    assert canonicalize("UNKNOWN_PHASE", aliases) == "UNKNOWN_PHASE"


def test_canonicalize_handles_none():
    assert canonicalize(None, {}) == ""


def test_data_cache_initial_state():
    c = DataCache(_cfg())
    assert c.routing_cycles == {}
    assert c.today_plan == []
    assert c.phase_kpis == {}
    assert c.last_refresh_ts == {}
    assert c.phase_mapping == {}


def test_data_cache_lock_returns_context_manager():
    c = DataCache(_cfg())
    with c.lock():
        pass


@patch("data_cache.upsert_cycles")
@patch("data_cache.load_latest_routing")
@patch("data_cache.get_phase_mapping")
def test_refresh_routing_canonicalizes_cycles_and_builds_multi_id_mapping(
    mock_mapping, mock_load, mock_upsert_cycles,
):
    """Cycle keys are canonicalized; phase_mapping is canonical -> [trace_ids]."""
    mock_load.return_value = (
        # Routing has raw header "FINAL ASSEMBLY" — alias rewrites to "ASSEMBLY"
        {("P1", "FINAL ASSEMBLY"): 2.5, ("P1", "FCT"): 4.0},
        "/tmp/r.xlsx", datetime(2026, 5, 6),
    )
    from engine.models import PhaseMap
    # Same Planning_PhaseName "FINAL ASSEMBLY" maps to TWO trace ids: 110 + 112
    mock_mapping.return_value = [
        PhaseMap("FINAL ASSEMBLY", 7, 110, "FINAL ASSEMBLY"),
        PhaseMap("FINAL ASSEMBLY", 7, 112, "PROGRAMARE"),
        PhaseMap("FCT", 4, 103, "FCT"),
    ]
    c = DataCache(_cfg(aliases={"FINAL ASSEMBLY": "ASSEMBLY"}))
    c.refresh_routing(conn=MagicMock())
    # Cycles canonicalized
    assert c.routing_cycles[("P1", "ASSEMBLY")] == 2.5
    assert c.routing_cycles[("P1", "FCT")] == 4.0
    # Multi-id mapping under canonical key
    assert sorted(c.phase_mapping["ASSEMBLY"]) == [110, 112]
    assert c.phase_mapping["FCT"] == [103]


@patch("data_cache.replace_anomalies_for_date")
@patch("data_cache.upsert_plan_history")
@patch("data_cache.load_today_plan")
@patch("data_cache.resolve_orders_to_products")
def test_refresh_planning_canonicalizes_phase_names(mock_resolve, mock_load, mock_upsert_plan, mock_anom):
    """Plan rows arrive with raw planning names; after refresh, all are canonical."""
    from datetime import date
    from engine.models import PlanRow
    mock_load.return_value = [
        PlanRow("ORD1", "FINAL ASSEMBLY", "P1", date(2026, 5, 6), 100),
        PlanRow("ORD2", "CONFORMAL COATING", "P2", date(2026, 5, 6), 50),
        PlanRow("ORD3", "FCT", "P3", date(2026, 5, 6), 30),
    ]
    mock_resolve.return_value = {
        "ORD1": (1001, "P1"), "ORD2": (1002, "P2"), "ORD3": (1003, "P3"),
    }
    c = DataCache(_cfg(aliases={
        "FINAL ASSEMBLY": "ASSEMBLY",
        "CONFORMAL COATING": "COATING",
    }))
    c.refresh_planning(conn=MagicMock())
    phase_names = {r.phase_name for r in c.today_plan}
    assert phase_names == {"ASSEMBLY", "COATING", "FCT"}
    assert len(c.today_plan) == 3  # nothing dropped — passthrough for FCT
    assert "planning" in c.last_refresh_ts


@patch("data_cache.upsert_prod_history")
@patch("data_cache.get_production_by_phase_in_window")
def test_refresh_production_sums_across_multi_id_mapping(mock_prod, mock_upsert_prod):
    """If a canonical phase maps to multiple trace_ids, production is summed
    across all of them."""
    from datetime import date
    from engine.models import PlanRow
    cfg = _cfg(aliases={"FINAL ASSEMBLY": "ASSEMBLY"})
    cfg.phases.monitored = ["ASSEMBLY"]
    c = DataCache(cfg)
    c.routing_cycles = {("P1", "ASSEMBLY"): 6.0}  # 100 * 6 = 600 min = 10h
    c.phase_mapping = {"ASSEMBLY": [110, 112]}  # 2 trace ids for ASSEMBLY
    c.today_plan = [PlanRow("ORD1", "ASSEMBLY", "P1", date(2026, 5, 6), 100)]
    c.order_to_product = {"ORD1": "P1"}
    c.order_to_id = {"ORD1": 1001}
    # mock returns 30 pieces produced for ORD1 on every call
    mock_prod.return_value = [(1001, "ORD1", 30)]
    c.refresh_production(conn=MagicMock())
    assert "ASSEMBLY" in c.phase_kpis
    assert c.phase_kpis["ASSEMBLY"].planned_h_day == 10.0
    # Multiple trace_ids per shift → multiple calls → produced_h_day > 0
    assert c.phase_kpis["ASSEMBLY"].produced_h_day > 0
    assert c.total_kpi.planned_h_day == 10.0
    assert "production" in c.last_refresh_ts


@patch("data_cache.upsert_prod_history")
@patch("data_cache.get_production_by_phase_in_window")
def test_refresh_production_planned_visible_without_mapping(mock_prod, mock_upsert_prod):
    """A canonical phase with NO traceability mapping still shows planned hours
    (produced stays 0). Critical for phases like COATING where the planning
    has rows but the mapping table has no Planning_PhaseName=CONFORMAL COATING."""
    from datetime import date
    from engine.models import PlanRow
    cfg = _cfg(aliases={"CONFORMAL COATING": "COATING"})
    cfg.phases.monitored = ["COATING"]
    c = DataCache(cfg)
    c.routing_cycles = {("P1", "COATING"): 3.0}  # 50 * 3 = 150 min = 2.5h
    c.phase_mapping = {}  # NO mapping for COATING
    c.today_plan = [PlanRow("ORD1", "COATING", "P1", date(2026, 5, 6), 50)]
    c.order_to_product = {"ORD1": "P1"}
    c.order_to_id = {"ORD1": 1001}
    c.refresh_production(conn=MagicMock())
    assert c.phase_kpis["COATING"].planned_h_day == 2.5
    assert c.phase_kpis["COATING"].produced_h_day == 0.0
    # Production query never called for unmapped phase
    mock_prod.assert_not_called()


@patch("data_cache.get_history_aggregates")
def test_refresh_rolling_populates_cache_from_sql_history(mock_agg):
    """refresh_rolling must read SQL history aggregates and store a RollingData
    in cache.rolling_data. Today is excluded; only past days contribute to MTD/YTD."""
    from datetime import date, datetime
    c = DataCache(_cfg())
    # Today is 2026-05-13. Year-to-date should include 2026-04-30 (April, YTD only)
    # plus 2026-05-06, 2026-05-12 (May, both MTD and YTD).
    # Today itself (2026-05-13) is filtered out by compute_rolling_month.
    mock_agg.return_value = [
        {"date": date(2026, 4, 30), "planned_h": 100.0, "produced_h": 90.0, "coverage_pct": 90.0},
        {"date": date(2026, 5, 6),  "planned_h": 128.5, "produced_h": 120.0, "coverage_pct": 93.39},
        {"date": date(2026, 5, 12), "planned_h": 150.0, "produced_h": 140.0, "coverage_pct": 93.33},
        {"date": date(2026, 5, 13), "planned_h": 200.0, "produced_h": 10.0,  "coverage_pct": 5.0},
    ]
    c.refresh_rolling(conn=MagicMock(), now=datetime(2026, 5, 13, 10, 0))
    rd = c.rolling_data
    assert rd is not None
    # Month-to-date: only May days strictly before 2026-05-13
    assert rd.month_planned_h == 278.5      # 128.5 + 150
    assert rd.month_produced_h == 260.0     # 120 + 140
    assert rd.working_days_month == 2
    # Year-to-date: all days strictly before 2026-05-13
    assert rd.ytd_planned_h == 378.5        # 100 + 128.5 + 150
    assert rd.ytd_produced_h == 350.0       # 90 + 120 + 140
    assert rd.working_days_ytd == 3
    # `days` contains the day-by-day current-month series for the chart
    assert len(rd.days) == 2
    assert rd.days[0].date == date(2026, 5, 6)
    assert rd.days[1].date == date(2026, 5, 12)
    # Bookkeeping
    assert "rolling" in c.last_refresh_ts


@patch("data_cache.get_history_aggregates")
def test_refresh_rolling_handles_empty_history(mock_agg):
    """No SQL history yet: rolling_data is set with all zeros, never None."""
    from datetime import datetime
    c = DataCache(_cfg())
    mock_agg.return_value = []
    c.refresh_rolling(conn=MagicMock(), now=datetime(2026, 5, 13, 10, 0))
    rd = c.rolling_data
    assert rd is not None
    assert rd.month_planned_h == 0.0
    assert rd.month_produced_h == 0.0
    assert rd.month_coverage_pct == 0.0
    assert rd.ytd_planned_h == 0.0
    assert rd.working_days_month == 0
    assert rd.working_days_ytd == 0


@patch("data_cache.upsert_prod_history")
@patch("data_cache.get_production_by_phase_in_window")
@patch("data_cache.resolve_orders_to_products")
def test_refresh_production_includes_out_of_plan_orders(mock_resolve, mock_prod, mock_upsert_prod):
    """If an order is producing on SMT but not in today's plan, it must still
    appear in the SMT KPI. The out-of-plan order gets resolved to its product
    so its hours can be computed via cycle_time × qty."""
    from datetime import date
    from engine.models import PlanRow
    cfg = _cfg(aliases={"AOI": "SMT"})
    cfg.phases.monitored = ["SMT"]
    c = DataCache(cfg)
    c.routing_cycles = {("PROD_X", "SMT"): 0.5}  # 0.5 min/piece
    c.phase_mapping = {"SMT": [2]}  # AOI traceability id
    # Today's plan is empty for SMT
    c.today_plan = []
    c.order_to_product = {}  # empty — out-of-plan order needs resolution
    c.order_to_id = {}
    # Production query returns an order that's NOT in today's plan
    mock_prod.return_value = [(9999, "OUT_OF_PLAN_ORD", 120)]  # 120 pieces
    # resolve_orders_to_products returns the product for the out-of-plan order
    mock_resolve.return_value = {"OUT_OF_PLAN_ORD": (9999, "PROD_X")}
    c.refresh_production(conn=MagicMock())
    # SMT panel shows produced hours from out-of-plan production
    # 120 pieces × 0.5 min × 2 shifts (T1+T2 active) = 120 min = 2.0h
    # (queries fire for each shift+trace_id combination)
    assert c.phase_kpis["SMT"].produced_h_day > 0
    # Plan stays at 0 (no plan rows)
    assert c.phase_kpis["SMT"].planned_h_day == 0.0
    # The out-of-plan order was added to the cache
    assert c.order_to_product["OUT_OF_PLAN_ORD"] == "PROD_X"
