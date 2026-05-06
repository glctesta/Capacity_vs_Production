# tests/test_kpi_builder.py
from datetime import date, datetime, time
from app_config import ShiftConfig, ThresholdsConfig
from engine.kpi_builder import build_phase_kpi
from engine.models import PlanRow

SHIFTS = [
    ShiftConfig("T1", time(7, 30), time(15, 30)),
    ShiftConfig("T2", time(15, 30), time(23, 30)),
    ShiftConfig("T3", time(23, 30), time(7, 30)),
]
THRESH = ThresholdsConfig(green_min_coverage_pct=95, yellow_min_coverage_pct=80)


def test_build_phase_kpi_at_t1_simple():
    """At 11:30 (4h into T1), planned 24h day, produced 4h."""
    plan = [PlanRow("ORD1", "ASSEMBLY", "P1", date(2026, 5, 6), 480)]
    cycles = {("P1", "ASSEMBLY"): 3.0}  # 480 * 3 = 1440 min = 24h
    produced = {("ORD1", "ASSEMBLY", "T1"): 80}  # 80 * 3 = 240 min = 4h
    order_to_product = {"ORD1": "P1"}
    now = datetime(2026, 5, 6, 11, 30)
    kpi = build_phase_kpi(
        phase_name="ASSEMBLY",
        plan=plan, cycles=cycles, produced=produced,
        order_to_product=order_to_product,
        now=now, shifts=SHIFTS, thresholds=THRESH,
        any_t3_production=False,
    )
    assert kpi.phase_name == "ASSEMBLY"
    assert kpi.shift_code == "T1"
    assert kpi.planned_h_day == 24.0
    # planned_h_shift = 24 * 8/16 = 12
    assert kpi.planned_h_shift == 12.0
    # gross_elapsed_day = 4h, total = 16h -> 24 * 4/16 = 6
    assert kpi.planned_h_so_far_day == 6.0
    # gross_elapsed_shift = 4h, total = 8h -> 12 * 4/8 = 6
    assert kpi.planned_h_so_far_shift == 6.0
    assert kpi.produced_h_day == 4.0
    assert kpi.produced_h_shift == 4.0
    # delta = produced - expected
    assert kpi.delta_vs_expected_day == round(4.0 - 6.0, 2)
    # coverage = 4/24*100 = 16.67
    assert kpi.coverage_pct_day == 16.67
    assert kpi.status_color == "red"


def test_build_phase_kpi_green_status():
    plan = [PlanRow("ORD1", "ASSEMBLY", "P1", date(2026, 5, 6), 100)]
    cycles = {("P1", "ASSEMBLY"): 6.0}  # 600 min = 10h
    produced = {
        ("ORD1", "ASSEMBLY", "T1"): 50,  # 5h
        ("ORD1", "ASSEMBLY", "T2"): 50,  # 5h, total 10h
    }
    order_to_product = {"ORD1": "P1"}
    now = datetime(2026, 5, 6, 23, 0)  # near end of T2
    kpi = build_phase_kpi(
        phase_name="ASSEMBLY", plan=plan, cycles=cycles,
        produced=produced, order_to_product=order_to_product,
        now=now, shifts=SHIFTS, thresholds=THRESH, any_t3_production=False,
    )
    assert kpi.coverage_pct_day == 100.0
    assert kpi.status_color == "green"


def test_build_phase_kpi_yellow_status():
    """75% coverage = red, but we just verify status logic with low value."""
    plan = [PlanRow("ORD1", "ASSEMBLY", "P1", date(2026, 5, 6), 100)]
    cycles = {("P1", "ASSEMBLY"): 6.0}  # 10h
    produced = {("ORD1", "ASSEMBLY", "T1"): 75}  # 7.5h
    order_to_product = {"ORD1": "P1"}
    now = datetime(2026, 5, 6, 23, 0)
    kpi = build_phase_kpi(
        phase_name="ASSEMBLY", plan=plan, cycles=cycles,
        produced=produced, order_to_product=order_to_product,
        now=now, shifts=SHIFTS, thresholds=THRESH, any_t3_production=False,
    )
    assert kpi.coverage_pct_day == 75.0  # 7.5/10
    assert kpi.status_color == "red"  # 75% < 80%


def test_build_phase_kpi_zero_planned_no_division_error():
    plan = []
    cycles = {}
    produced = {}
    order_to_product = {}
    now = datetime(2026, 5, 6, 11, 30)
    kpi = build_phase_kpi(
        phase_name="ASSEMBLY", plan=plan, cycles=cycles,
        produced=produced, order_to_product=order_to_product,
        now=now, shifts=SHIFTS, thresholds=THRESH, any_t3_production=False,
    )
    assert kpi.planned_h_day == 0.0
    assert kpi.coverage_pct_day == 0.0
    assert kpi.status_color == "red"


def test_curve_points_during_t1():
    """At 11:30, only 'now' point should be included (no shift completed yet)."""
    plan = [PlanRow("ORD1", "ASSEMBLY", "P1", date(2026, 5, 6), 100)]
    cycles = {("P1", "ASSEMBLY"): 6.0}  # 10h
    produced = {("ORD1", "ASSEMBLY", "T1"): 30}  # 3h
    order_to_product = {"ORD1": "P1"}
    now = datetime(2026, 5, 6, 11, 30)
    kpi = build_phase_kpi(
        phase_name="ASSEMBLY", plan=plan, cycles=cycles,
        produced=produced, order_to_product=order_to_product,
        now=now, shifts=SHIFTS, thresholds=THRESH, any_t3_production=False,
    )
    assert len(kpi.curve_points) == 1
    assert kpi.curve_points[0][0] == time(11, 30)
    assert kpi.curve_points[0][1] == 3.0


def test_curve_points_after_t1_complete():
    """At 16:00, T1 finished (cumul at end of T1 included) + 'now'."""
    plan = [PlanRow("ORD1", "ASSEMBLY", "P1", date(2026, 5, 6), 100)]
    cycles = {("P1", "ASSEMBLY"): 6.0}
    produced = {
        ("ORD1", "ASSEMBLY", "T1"): 60,  # 6h
        ("ORD1", "ASSEMBLY", "T2"): 5,   # 0.5h
    }
    order_to_product = {"ORD1": "P1"}
    now = datetime(2026, 5, 6, 16, 0)
    kpi = build_phase_kpi(
        phase_name="ASSEMBLY", plan=plan, cycles=cycles,
        produced=produced, order_to_product=order_to_product,
        now=now, shifts=SHIFTS, thresholds=THRESH, any_t3_production=False,
    )
    assert len(kpi.curve_points) == 2
    assert kpi.curve_points[0] == (time(15, 30), 6.0)
    assert kpi.curve_points[1] == (time(16, 0), 6.5)
