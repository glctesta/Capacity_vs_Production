# tests/test_cycle_engine.py
from datetime import date
from engine.cycle_engine import (
    minutes_to_hours,
    compute_planned_minutes_by_phase,
    compute_produced_minutes_by_phase_shift,
    strip_revision_suffix,
)
from engine.models import PlanRow


def test_strip_revision_dash_nn():
    assert strip_revision_suffix("1547-5038-01") == "1547-5038"
    assert strip_revision_suffix("1146-6058-18") == "1146-6058"
    assert strip_revision_suffix("1146-6048-19") == "1146-6048"


def test_strip_revision_pipe_n():
    assert strip_revision_suffix("PFEX+673612A02|1") == "PFEX+673612A02"
    assert strip_revision_suffix("PFSL+KCE-FCB21|1") == "PFSL+KCE-FCB21"


def test_strip_revision_pipe_then_dash():
    """Should strip both: '|' first, then '-NN'."""
    assert strip_revision_suffix("FOO-BAR-12|3") == "FOO-BAR"


def test_strip_revision_no_change_for_two_segments():
    """1146-4018 must NOT be stripped to '1146' — that would be wrong."""
    assert strip_revision_suffix("1146-4018") == "1146-4018"
    assert strip_revision_suffix("1547-5038") == "1547-5038"


def test_strip_revision_no_change_when_last_segment_is_long():
    """1146-6058-1234 stays — last segment is 4 digits, not a revision."""
    assert strip_revision_suffix("1146-6058-1234") == "1146-6058-1234"


def test_strip_revision_empty_safe():
    assert strip_revision_suffix("") == ""
    assert strip_revision_suffix("X") == "X"


def test_planned_minutes_uses_revision_fallback():
    """Plan has product '1547-5038-01' but routing has '1547-5038' — must match."""
    plan = [PlanRow("ORD1", "ASSEMBLY", "1547-5038-01", date(2026, 5, 6), 100)]
    cycles = {("1547-5038", "ASSEMBLY"): 6.0}  # routing has stripped form
    result = compute_planned_minutes_by_phase(plan, cycles)
    assert result == {"ASSEMBLY": 600.0}


def test_planned_minutes_uses_pipe_fallback():
    plan = [PlanRow("ORD1", "ASSEMBLY", "PFEX+673612A02|1", date(2026, 5, 6), 50)]
    cycles = {("PFEX+673612A02", "ASSEMBLY"): 4.0}
    result = compute_planned_minutes_by_phase(plan, cycles)
    assert result == {"ASSEMBLY": 200.0}


def test_planned_minutes_exact_match_takes_precedence():
    """If an exact-match key exists, it wins over the stripped form."""
    plan = [PlanRow("ORD1", "ASSEMBLY", "1547-5038-01", date(2026, 5, 6), 100)]
    cycles = {
        ("1547-5038-01", "ASSEMBLY"): 7.0,  # exact match
        ("1547-5038",    "ASSEMBLY"): 6.0,  # fallback
    }
    result = compute_planned_minutes_by_phase(plan, cycles)
    assert result == {"ASSEMBLY": 700.0}  # used exact, not fallback


def test_minutes_to_hours_2_decimals():
    assert minutes_to_hours(60) == 1.0
    assert minutes_to_hours(90) == 1.5
    assert minutes_to_hours(818) == 13.63
    assert minutes_to_hours(0) == 0.0
    assert minutes_to_hours(45) == 0.75


def test_planned_minutes_simple():
    plan = [
        PlanRow("ORD1", "ASSEMBLY", "P1", date(2026, 5, 6), 100),
        PlanRow("ORD2", "COATING",  "P1", date(2026, 5, 6), 50),
    ]
    cycles = {("P1", "ASSEMBLY"): 2.5, ("P1", "COATING"): 4.0}
    result = compute_planned_minutes_by_phase(plan, cycles)
    assert result == {"ASSEMBLY": 250.0, "COATING": 200.0}


def test_planned_minutes_multiple_orders_same_phase():
    plan = [
        PlanRow("ORD1", "ASSEMBLY", "P1", date(2026, 5, 6), 100),
        PlanRow("ORD2", "ASSEMBLY", "P2", date(2026, 5, 6), 50),
    ]
    cycles = {("P1", "ASSEMBLY"): 2.0, ("P2", "ASSEMBLY"): 3.0}
    result = compute_planned_minutes_by_phase(plan, cycles)
    assert result == {"ASSEMBLY": 350.0}


def test_planned_minutes_missing_cycle_skipped(caplog):
    import logging
    plan = [
        PlanRow("ORD1", "ASSEMBLY", "P1", date(2026, 5, 6), 100),
        PlanRow("ORD2", "COATING",  "P_UNKNOWN", date(2026, 5, 6), 50),
    ]
    cycles = {("P1", "ASSEMBLY"): 2.0}
    with caplog.at_level(logging.WARNING):
        result = compute_planned_minutes_by_phase(plan, cycles)
    assert result == {"ASSEMBLY": 200.0}
    assert any("missing cycle" in r.message.lower() for r in caplog.records)


def test_produced_minutes_by_phase_shift_simple():
    plan = [PlanRow("ORD1", "ASSEMBLY", "P1", date(2026, 5, 6), 100)]
    cycles = {("P1", "ASSEMBLY"): 2.5}
    produced = {
        ("ORD1", "ASSEMBLY", "T1"): 30,
        ("ORD1", "ASSEMBLY", "T2"): 50,
    }
    order_to_product = {"ORD1": "P1"}
    result = compute_produced_minutes_by_phase_shift(
        plan, cycles, produced, order_to_product,
    )
    assert result[("ASSEMBLY", "T1")] == 75.0   # 30 * 2.5
    assert result[("ASSEMBLY", "T2")] == 125.0  # 50 * 2.5


def test_produced_minutes_aggregates_two_orders_same_phase_shift():
    plan = [
        PlanRow("ORD1", "ASSEMBLY", "P1", date(2026, 5, 6), 100),
        PlanRow("ORD2", "ASSEMBLY", "P2", date(2026, 5, 6), 100),
    ]
    cycles = {("P1", "ASSEMBLY"): 2.0, ("P2", "ASSEMBLY"): 3.0}
    produced = {
        ("ORD1", "ASSEMBLY", "T1"): 10,
        ("ORD2", "ASSEMBLY", "T1"): 20,
    }
    order_to_product = {"ORD1": "P1", "ORD2": "P2"}
    result = compute_produced_minutes_by_phase_shift(
        plan, cycles, produced, order_to_product,
    )
    assert result[("ASSEMBLY", "T1")] == 80.0   # 10*2 + 20*3
