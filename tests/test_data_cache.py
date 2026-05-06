# tests/test_data_cache.py
from datetime import datetime, time
from unittest.mock import MagicMock, patch
from data_cache import DataCache
from app_config import (
    AppConfig, ServerConfig, PhasesConfig, DataSourcesConfig,
    RefreshConfig, ShiftConfig, ThresholdsConfig, EmailReportConfig,
)


def _cfg():
    return AppConfig(
        server=ServerConfig(),
        phases=PhasesConfig(monitored=["ASSEMBLY"]),
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


def test_data_cache_initial_state():
    c = DataCache(_cfg())
    assert c.routing_cycles == {}
    assert c.today_plan == []
    assert c.phase_kpis == {}
    assert c.last_refresh_ts == {}


def test_data_cache_lock_returns_context_manager():
    c = DataCache(_cfg())
    with c.lock():
        pass  # should not raise


@patch("data_cache.load_latest_routing")
@patch("data_cache.get_phase_mapping")
def test_refresh_routing_populates_cycles_and_mapping(mock_mapping, mock_load):
    """phase_mapping is keyed by traceability_phase_name (matches routing headers
    and config.monitored). planning_to_traceability_name lets us translate
    planning Excel names to traceability namespace upstream."""
    from datetime import datetime
    mock_load.return_value = (
        {("P1", "ASSEMBLY"): 2.5}, "/tmp/r.xlsx", datetime(2026, 5, 6),
    )
    from engine.models import PhaseMap
    # Simulate real data: planning name "FINAL ASSEMBLY" maps to traceability "ASSEMBLY"
    mock_mapping.return_value = [PhaseMap("FINAL ASSEMBLY", 10, 2, "ASSEMBLY")]
    c = DataCache(_cfg())
    c.refresh_routing(conn=MagicMock())
    assert c.routing_cycles[("P1", "ASSEMBLY")] == 2.5
    # phase_mapping keyed by traceability name
    assert c.phase_mapping["ASSEMBLY"] == 2
    # translation table populated
    assert c.planning_to_traceability_name["FINAL ASSEMBLY"] == "ASSEMBLY"
    assert "routing" in c.last_refresh_ts


@patch("data_cache.load_today_plan")
@patch("data_cache.resolve_orders_to_products")
def test_refresh_planning_translates_phase_names(mock_resolve, mock_load):
    """Planning rows arrive with planning-namespace phase_name. After refresh,
    today_plan rows have traceability-namespace phase_name (translated)."""
    from datetime import date
    from engine.models import PlanRow
    mock_load.return_value = [
        PlanRow("ORD1", "FINAL ASSEMBLY", "P1", date(2026, 5, 6), 100),
        PlanRow("ORD2", "PTHM SELECTIVE", "P2", date(2026, 5, 6), 50),
        PlanRow("ORD3", "UNKNOWN_PHASE", "P3", date(2026, 5, 6), 10),
    ]
    mock_resolve.return_value = {"ORD1": (1001, "P1"), "ORD2": (1002, "P2")}
    c = DataCache(_cfg())
    # Pre-populate translation table (normally done by refresh_routing)
    c.planning_to_traceability_name = {
        "FINAL ASSEMBLY": "ASSEMBLY",
        "PTHM SELECTIVE": "PTHSEL",
    }
    c.refresh_planning(conn=MagicMock())
    # 2 rows survived translation, 1 was skipped (UNKNOWN_PHASE)
    assert len(c.today_plan) == 2
    phase_names = {r.phase_name for r in c.today_plan}
    assert phase_names == {"ASSEMBLY", "PTHSEL"}
    assert c.order_to_product["ORD1"] == "P1"
    assert "planning" in c.last_refresh_ts


@patch("data_cache.load_today_plan")
@patch("data_cache.resolve_orders_to_products")
def test_refresh_planning_passes_through_when_names_already_match(mock_resolve, mock_load):
    """If a planning row's phase_name is already in traceability namespace
    (which happens when the mapping table has identity entries like 'FCT'->'FCT'),
    it passes through unchanged."""
    from datetime import date
    from engine.models import PlanRow
    mock_load.return_value = [
        PlanRow("ORD1", "FCT", "P1", date(2026, 5, 6), 100),
    ]
    mock_resolve.return_value = {"ORD1": (1001, "P1")}
    c = DataCache(_cfg())
    c.planning_to_traceability_name = {"FCT": "FCT"}
    c.refresh_planning(conn=MagicMock())
    assert len(c.today_plan) == 1
    assert c.today_plan[0].phase_name == "FCT"


@patch("data_cache.get_production_in_window")
def test_refresh_production_builds_phase_kpis(mock_prod):
    from datetime import date
    from engine.models import PlanRow
    cfg = _cfg()
    cfg.phases.monitored = ["ASSEMBLY"]
    c = DataCache(cfg)
    c.routing_cycles = {("P1", "ASSEMBLY"): 6.0}  # 100 * 6 = 600 min = 10h
    c.phase_mapping = {"ASSEMBLY": 2}
    c.today_plan = [PlanRow("ORD1", "ASSEMBLY", "P1", date(2026, 5, 6), 100)]
    c.order_to_product = {"ORD1": "P1"}
    c.order_to_id = {"ORD1": 1001}
    mock_prod.return_value = 30  # 30 pieces produced
    c.refresh_production(conn=MagicMock())
    assert "ASSEMBLY" in c.phase_kpis
    assert c.phase_kpis["ASSEMBLY"].planned_h_day == 10.0
    # produced was returned 30 by the mock for every (order, phase, shift) combo;
    # verify the cache actually built a KPI with non-zero produced
    assert c.phase_kpis["ASSEMBLY"].produced_h_day > 0
    assert c.total_kpi is not None
    assert c.total_kpi.planned_h_day == 10.0
    assert "production" in c.last_refresh_ts
