# tests/test_db_history.py
from datetime import date
from unittest.mock import MagicMock
from data_sources.db_history import (
    create_pianotempi_tables,
    upsert_cycles,
    upsert_plan_history,
    upsert_prod_history,
    get_plan_history_for_date,
    get_prod_history_for_date,
    get_cycles_master,
    get_history_aggregates,
)
from engine.models import PlanRow


def _conn_with_rows(rows):
    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


def test_create_pianotempi_tables_runs_idempotent_ddl():
    conn, cursor = _conn_with_rows([])
    create_pianotempi_tables(conn)
    # 4 CREATE TABLE + 3 CREATE INDEX = 7 calls
    assert cursor.execute.call_count == 7


def test_upsert_cycles_deletes_then_inserts():
    conn, cursor = _conn_with_rows([])
    cycles = {("P1", "ASSEMBLY"): 2.5, ("P2", "FCT"): 4.0}
    upsert_cycles(conn, cycles, "/path/to/r.xlsx")
    # 1 delete + 2 inserts = 3 calls
    assert cursor.execute.call_count == 3


def test_upsert_cycles_empty_does_nothing():
    conn, cursor = _conn_with_rows([])
    upsert_cycles(conn, {}, "anywhere")
    cursor.execute.assert_not_called()


def test_upsert_plan_history_deletes_then_inserts():
    conn, cursor = _conn_with_rows([])
    plan_rows = [
        PlanRow("ORD1", "ASSEMBLY", "P1", date(2026, 5, 7), 100),
        PlanRow("ORD2", "FCT",      "P2", date(2026, 5, 7), 50),
    ]
    cycles = {("P1", "ASSEMBLY"): 2.5, ("P2", "FCT"): 4.0}
    upsert_plan_history(conn, date(2026, 5, 7), plan_rows, cycles)
    # 1 delete + 2 inserts = 3 calls
    assert cursor.execute.call_count == 3


def test_upsert_plan_history_uses_revision_fallback():
    """If a plan row has 'PROD-01' and routing has 'PROD', fallback resolves it."""
    conn, cursor = _conn_with_rows([])
    plan_rows = [PlanRow("ORD1", "ASSEMBLY", "1547-5038-01", date(2026, 5, 7), 100)]
    cycles = {("1547-5038", "ASSEMBLY"): 6.0}  # routing has the stripped form
    upsert_plan_history(conn, date(2026, 5, 7), plan_rows, cycles)
    # 1 delete + 1 insert
    assert cursor.execute.call_count == 2
    # The INSERT call should have CycleTimeMinutes=6.0 (resolved via fallback)
    insert_args = cursor.execute.call_args_list[1].args
    # args = (sql, plan_date, order_number, phase_name, product_code, qty, cycle, ...)
    assert insert_args[5] == 100         # qty
    assert insert_args[6] == 6.0         # cycle (from fallback)
    assert insert_args[7] == 600.0       # planned minutes
    assert insert_args[8] == 10.0        # planned hours


def test_upsert_prod_history_deletes_then_inserts():
    conn, cursor = _conn_with_rows([])
    produced = {
        ("ORD1", "ASSEMBLY", "T1"): 30,
        ("ORD1", "ASSEMBLY", "T2"): 50,
    }
    order_to_product = {"ORD1": "P1"}
    cycles = {("P1", "ASSEMBLY"): 2.0}
    phase_mapping = {"ASSEMBLY": [110, 112]}
    upsert_prod_history(
        conn, date(2026, 5, 7), produced,
        order_to_product, cycles, phase_mapping,
    )
    # 1 delete + 2 inserts = 3 calls
    assert cursor.execute.call_count == 3


def test_get_plan_history_returns_dicts():
    conn, cursor = _conn_with_rows([
        (date(2026, 5, 7), "ORD1", "ASSEMBLY", "P1", 100, 2.5, 250.0, 4.17),
    ])
    rows = get_plan_history_for_date(conn, date(2026, 5, 7))
    assert len(rows) == 1
    assert rows[0]["order_number"] == "ORD1"
    assert rows[0]["planned_hours"] == 4.17


def test_get_prod_history_returns_dicts():
    conn, cursor = _conn_with_rows([
        (date(2026, 5, 7), "ORD1", "ASSEMBLY", "T1", "P1", 110, 30, 2.0, 60.0, 1.0),
    ])
    rows = get_prod_history_for_date(conn, date(2026, 5, 7))
    assert len(rows) == 1
    assert rows[0]["produced_qty"] == 30
    assert rows[0]["produced_hours"] == 1.0


def test_get_cycles_master_returns_dicts():
    from datetime import datetime
    conn, cursor = _conn_with_rows([
        ("P1", "ASSEMBLY", 2.5, "/path/to/r.xlsx", datetime(2026, 5, 7, 12, 0)),
    ])
    rows = get_cycles_master(conn)
    assert len(rows) == 1
    assert rows[0]["product_code"] == "P1"
    assert rows[0]["cycle_time_minutes"] == 2.5


def test_replace_anomalies_deletes_then_inserts():
    from datetime import date
    from data_sources.db_history import replace_anomalies_for_date
    from engine.anomaly_detector import Anomaly
    conn, cursor = _conn_with_rows([])
    anomalies = [
        Anomaly("missing_cycle", "ORD1", "ASSEMBLY", "P1", "no cycle"),
        Anomaly("unresolved_order", "ORD2", "FCT", "", "order not found"),
    ]
    replace_anomalies_for_date(conn, date(2026, 5, 7), anomalies)
    # 1 delete + 2 inserts
    assert cursor.execute.call_count == 3


def test_replace_anomalies_empty_just_clears():
    from datetime import date
    from data_sources.db_history import replace_anomalies_for_date
    conn, cursor = _conn_with_rows([])
    replace_anomalies_for_date(conn, date(2026, 5, 7), [])
    # 1 delete only (no inserts)
    assert cursor.execute.call_count == 1


def test_get_anomalies_for_date_returns_dicts():
    from datetime import date, datetime
    from data_sources.db_history import get_anomalies_for_date
    conn, cursor = _conn_with_rows([
        ("missing_cycle", "ORD1", "ASSEMBLY", "P1", "no cycle", datetime(2026, 5, 7, 8, 0)),
    ])
    out = get_anomalies_for_date(conn, date(2026, 5, 7))
    assert len(out) == 1
    assert out[0]["category"] == "missing_cycle"
    assert out[0]["order_number"] == "ORD1"


def test_get_history_aggregates_combines_plan_and_prod():
    """Two day rows from PlanHistory + one matching from ProdHistory aggregate cleanly."""
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        (date(2026, 5, 5), 100.0, 0.0),  # plan-only row
        (date(2026, 5, 6), 200.0, 0.0),  # plan-only row
        (date(2026, 5, 5), 0.0, 90.0),   # prod-only row, same date as first plan
    ]
    conn = MagicMock()
    conn.cursor.return_value = cursor
    out = get_history_aggregates(conn, date(2026, 5, 1), date(2026, 5, 6))
    assert len(out) == 2
    # day 5 should be merged: plan=100, prod=90
    by_date = {r["date"]: r for r in out}
    assert by_date[date(2026, 5, 5)]["planned_h"] == 100.0
    assert by_date[date(2026, 5, 5)]["produced_h"] == 90.0
    assert by_date[date(2026, 5, 6)]["planned_h"] == 200.0
    assert by_date[date(2026, 5, 6)]["produced_h"] == 0.0
