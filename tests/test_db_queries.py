# tests/test_db_queries.py
from datetime import datetime
from unittest.mock import MagicMock
import pytest
from data_sources.db_queries import (
    get_phase_mapping, resolve_orders_to_products,
    get_production_in_window, get_email_recipients,
)


def _conn_with_rows(rows):
    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    cursor.fetchone.return_value = rows[0] if rows else None
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


def test_get_phase_mapping_parses_rows():
    conn, cursor = _conn_with_rows([
        (2, "Assembly", 10, "ASSEMBLY"),
        (5, "Coating",  20, "COATING"),
    ])
    pm = get_phase_mapping(conn)
    assert len(pm) == 2
    assert pm[0].traceability_phase_id == 2
    assert pm[0].planning_phase_name == "ASSEMBLY"


def test_resolve_orders_to_products_batched():
    conn, cursor = _conn_with_rows([])
    cursor.fetchall.side_effect = [
        [("ORD1", 1001, "P1"), ("ORD2", 1002, "P2")],
    ]
    result = resolve_orders_to_products(conn, ["ORD1", "ORD2"])
    assert isinstance(result, dict)
    assert result.get("ORD1") == (1001, "P1") or result.get("ORD2") == (1002, "P2")


def test_get_production_in_window_returns_int():
    conn, cursor = _conn_with_rows([(42,)])
    cursor.fetchone.return_value = (42,)
    qty = get_production_in_window(
        conn, id_order=1001, traceability_phase_id=2,
        start_dt=datetime(2026, 5, 6, 7, 30),
        end_dt=datetime(2026, 5, 6, 15, 30),
    )
    assert qty == 42


def test_get_production_in_window_returns_zero_on_none():
    conn, cursor = _conn_with_rows([])
    cursor.fetchone.return_value = None
    qty = get_production_in_window(conn, 1, 2, datetime.now(), datetime.now())
    assert qty == 0


def test_get_email_recipients_splits_csv():
    conn, cursor = _conn_with_rows([])
    cursor.fetchone.return_value = ("alice@x.com,bob@x.com; carol@x.com",)
    rcpt = get_email_recipients(conn)
    assert sorted(rcpt) == ["alice@x.com", "bob@x.com", "carol@x.com"]


def test_get_email_recipients_empty_returns_empty_list():
    conn, cursor = _conn_with_rows([])
    cursor.fetchone.return_value = None
    assert get_email_recipients(conn) == []
