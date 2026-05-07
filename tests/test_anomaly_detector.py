# tests/test_anomaly_detector.py
from datetime import date
from engine.anomaly_detector import detect_anomalies, Anomaly
from engine.models import PlanRow


def test_detect_missing_cycle():
    plan = [PlanRow("ORD1", "ASSEMBLY", "P_NEW", date(2026, 5, 7), 100)]
    cycles = {("P_OTHER", "ASSEMBLY"): 2.5}  # P_NEW not in routing
    order_to_product = {"ORD1": "P_NEW"}
    result = detect_anomalies(plan, cycles, order_to_product, {}, [])
    assert len(result) == 1
    assert result[0].category == "missing_cycle"
    assert result[0].order_number == "ORD1"
    assert result[0].product_code == "P_NEW"


def test_detect_missing_cycle_uses_revision_fallback():
    """If revision strip resolves the cycle, no anomaly."""
    plan = [PlanRow("ORD1", "ASSEMBLY", "1547-5038-01", date(2026, 5, 7), 100)]
    cycles = {("1547-5038", "ASSEMBLY"): 6.0}
    order_to_product = {"ORD1": "1547-5038-01"}
    result = detect_anomalies(plan, cycles, order_to_product, {}, [])
    # No anomaly — fallback resolves
    assert result == []


def test_detect_unresolved_order():
    plan = [PlanRow("ORD_MISSING", "ASSEMBLY", "P1", date(2026, 5, 7), 100)]
    cycles = {("P1", "ASSEMBLY"): 2.5}
    order_to_product = {}  # no orders resolved
    result = detect_anomalies(plan, cycles, order_to_product, {}, [])
    assert len(result) == 1
    assert result[0].category == "unresolved_order"
    assert result[0].order_number == "ORD_MISSING"


def test_detect_unknown_planning_phase():
    """A raw planning phase name that isn't aliased AND isn't in cycles."""
    plan = []
    cycles = {("P1", "ASSEMBLY"): 2.5}
    order_to_product = {}
    aliases = {"FINAL ASSEMBLY": "ASSEMBLY"}
    raw_names = ["FINAL ASSEMBLY", "MYSTERY PHASE", "ASSEMBLY"]
    result = detect_anomalies(plan, cycles, order_to_product, aliases, raw_names)
    # FINAL ASSEMBLY is aliased -> known. ASSEMBLY is in cycles -> known.
    # MYSTERY PHASE is neither -> anomaly.
    cats = [a.category for a in result]
    phases = [a.phase_name for a in result]
    assert "unknown_planning_phase" in cats
    assert "MYSTERY PHASE" in phases


def test_detect_no_anomalies_when_clean():
    plan = [PlanRow("ORD1", "ASSEMBLY", "P1", date(2026, 5, 7), 100)]
    cycles = {("P1", "ASSEMBLY"): 2.5}
    order_to_product = {"ORD1": "P1"}
    aliases = {}
    raw_names = ["ASSEMBLY"]
    result = detect_anomalies(plan, cycles, order_to_product, aliases, raw_names)
    assert result == []
