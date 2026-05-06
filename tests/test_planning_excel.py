# tests/test_planning_excel.py
from datetime import date
from unittest.mock import MagicMock, patch
from data_sources.planning_excel import load_today_plan, _PlanRowRaw


@patch("data_sources.planning_excel.find_latest_routing_file")
@patch("data_sources.planning_excel.parse_last_phase")
@patch("data_sources.planning_excel.resolve_orders_to_products")
def test_load_today_plan_filters_today_and_enriches(
    mock_resolve, mock_parse, mock_find, tmp_path,
):
    mock_find.return_value = str(tmp_path / "plan.xlsx")
    mock_parse.return_value = [
        _PlanRowRaw("ORD1", "ASSEMBLY", date(2026, 5, 6), 100),
        _PlanRowRaw("ORD2", "COATING",  date(2026, 5, 7), 50),  # not today
        _PlanRowRaw("ORD3", "ASSEMBLY", date(2026, 5, 6), 30),
    ]
    mock_resolve.return_value = {"ORD1": (1001, "P1"), "ORD3": (1003, "P3")}

    rows = load_today_plan(str(tmp_path), "PlanningMachine",
                           target_date=date(2026, 5, 6), conn=MagicMock())
    assert len(rows) == 2
    order_codes = {r.order_number: r.product_code for r in rows}
    assert order_codes == {"ORD1": "P1", "ORD3": "P3"}


@patch("data_sources.planning_excel.find_latest_routing_file")
def test_load_today_plan_no_file_returns_empty(mock_find, tmp_path):
    mock_find.return_value = None
    rows = load_today_plan(str(tmp_path), "PlanningMachine",
                           target_date=date(2026, 5, 6), conn=MagicMock())
    assert rows == []
