# tests/test_models.py
from datetime import date, time
from engine.models import (
    RoutingCycle, PlanRow, PhaseMap, ProductionRow,
    PhaseKPI, TotalKPI, DayPoint, RollingData,
)


def test_routing_cycle_is_frozen():
    rc = RoutingCycle(product_code="1146-6048", phase_name="EOLTEST",
                     cycle_time_minutes=8.18)
    import dataclasses, pytest
    with pytest.raises(dataclasses.FrozenInstanceError):
        rc.cycle_time_minutes = 9.0


def test_plan_row_fields():
    pr = PlanRow(order_number="ORD123", phase_name="ASSEMBLY",
                 product_code="1146-6048", production_date=date(2026, 5, 6),
                 planned_qty=120)
    assert pr.order_number == "ORD123"
    assert pr.planned_qty == 120


def test_phase_map_fields():
    pm = PhaseMap(planning_phase_name="ASSEMBLY", planning_phase_id=10,
                  traceability_phase_id=2, traceability_phase_name="Assembly")
    assert pm.traceability_phase_id == 2


def test_phase_kpi_fields():
    kpi = PhaseKPI(
        phase_name="ASSEMBLY", shift_code="T2",
        planned_h_day=24.0, planned_h_shift=12.0,
        planned_h_so_far_day=12.85, planned_h_so_far_shift=1.5,
        produced_h_day=14.20, produced_h_shift=1.20,
        delta_vs_expected_day=1.35, delta_vs_expected_shift=-0.30,
        coverage_pct_day=59.17, status_color="red",
        curve_points=[(time(15, 30), 9.0), (time(16, 0), 14.20)],
    )
    assert kpi.coverage_pct_day == 59.17
    assert kpi.status_color == "red"
    assert len(kpi.curve_points) == 2
