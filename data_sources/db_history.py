# data_sources/db_history.py
"""SQL persistence for cycle times, plan and production history.

Tables (created automatically on first connect via create_pianotempi_tables):
  - traceability_rs.dbo.PianoTempi_Cycles       master cycle times
  - traceability_rs.dbo.PianoTempi_PlanHistory  daily snapshot of planning
  - traceability_rs.dbo.PianoTempi_ProdHistory  daily snapshot of production
  - traceability_rs.dbo.PianoTempi_Anomalies    open anomalies per operative day

All UPSERTs use the simple "delete-scope + insert" pattern (no MERGE).
"""
import logging
from datetime import date, datetime
from typing import Dict, List, Tuple

from engine.cycle_engine import minutes_to_hours, strip_revision_suffix
from engine.models import PlanRow

logger = logging.getLogger("PianoTempi")


# ----------------------------------------------------------------------
# DDL
# ----------------------------------------------------------------------

def create_pianotempi_tables(conn) -> None:
    """Create the 4 history tables if they don't exist. Idempotent.
    Called once at app startup."""
    cursor = conn.cursor()
    try:
        cursor.execute("""
            IF OBJECT_ID('traceability_rs.dbo.PianoTempi_Cycles', 'U') IS NULL
            CREATE TABLE traceability_rs.dbo.PianoTempi_Cycles (
                Id               INT IDENTITY(1,1) PRIMARY KEY,
                ProductCode      NVARCHAR(100) NOT NULL,
                PhaseName        NVARCHAR(100) NOT NULL,
                CycleTimeMinutes FLOAT NOT NULL,
                SourceFile       NVARCHAR(255),
                UpdatedAt        DATETIME DEFAULT GETDATE(),
                CONSTRAINT UQ_PianoTempi_Cycles UNIQUE (ProductCode, PhaseName)
            )
        """)
        cursor.execute("""
            IF OBJECT_ID('traceability_rs.dbo.PianoTempi_PlanHistory', 'U') IS NULL
            CREATE TABLE traceability_rs.dbo.PianoTempi_PlanHistory (
                Id               INT IDENTITY(1,1) PRIMARY KEY,
                PlanDate         DATE NOT NULL,
                OrderNumber      NVARCHAR(100) NOT NULL,
                PhaseName        NVARCHAR(100) NOT NULL,
                ProductCode      NVARCHAR(100),
                PlannedQty       INT NOT NULL,
                CycleTimeMinutes FLOAT,
                PlannedMinutes   FLOAT,
                PlannedHours     FLOAT,
                SnapshotTime     DATETIME DEFAULT GETDATE()
            )
        """)
        cursor.execute("""
            IF NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE name = 'IX_PianoTempi_PlanHistory_Date'
                  AND object_id = OBJECT_ID('traceability_rs.dbo.PianoTempi_PlanHistory')
            )
            CREATE INDEX IX_PianoTempi_PlanHistory_Date
                ON traceability_rs.dbo.PianoTempi_PlanHistory (PlanDate)
        """)
        cursor.execute("""
            IF OBJECT_ID('traceability_rs.dbo.PianoTempi_ProdHistory', 'U') IS NULL
            CREATE TABLE traceability_rs.dbo.PianoTempi_ProdHistory (
                Id                  INT IDENTITY(1,1) PRIMARY KEY,
                ProdDate            DATE NOT NULL,
                OrderNumber         NVARCHAR(100) NOT NULL,
                PhaseName           NVARCHAR(100) NOT NULL,
                ShiftCode           NVARCHAR(10) NOT NULL,
                ProductCode         NVARCHAR(100),
                TraceabilityPhaseId INT,
                ProducedQty         INT NOT NULL,
                CycleTimeMinutes    FLOAT,
                ProducedMinutes     FLOAT,
                ProducedHours       FLOAT,
                SnapshotTime        DATETIME DEFAULT GETDATE()
            )
        """)
        cursor.execute("""
            IF NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE name = 'IX_PianoTempi_ProdHistory_Date'
                  AND object_id = OBJECT_ID('traceability_rs.dbo.PianoTempi_ProdHistory')
            )
            CREATE INDEX IX_PianoTempi_ProdHistory_Date
                ON traceability_rs.dbo.PianoTempi_ProdHistory (ProdDate)
        """)
        cursor.execute("""
            IF OBJECT_ID('traceability_rs.dbo.PianoTempi_Anomalies', 'U') IS NULL
            CREATE TABLE traceability_rs.dbo.PianoTempi_Anomalies (
                Id           INT IDENTITY(1,1) PRIMARY KEY,
                AnomalyDate  DATE NOT NULL,
                Category     NVARCHAR(50) NOT NULL,
                OrderNumber  NVARCHAR(100),
                PhaseName    NVARCHAR(100),
                ProductCode  NVARCHAR(100),
                Detail       NVARCHAR(500),
                DetectedAt   DATETIME DEFAULT GETDATE()
            )
        """)
        cursor.execute("""
            IF NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE name = 'IX_PianoTempi_Anomalies_Date'
                  AND object_id = OBJECT_ID('traceability_rs.dbo.PianoTempi_Anomalies')
            )
            CREATE INDEX IX_PianoTempi_Anomalies_Date
                ON traceability_rs.dbo.PianoTempi_Anomalies (AnomalyDate, Category)
        """)
        cursor.close()
        logger.info("PianoTempi_* tables verified/created")
    except Exception as e:
        logger.error("create_pianotempi_tables failed: %s", e)


# ----------------------------------------------------------------------
# UPSERT functions
# ----------------------------------------------------------------------

def _lookup_cycle_with_fallback(
    cycles: Dict[Tuple[str, str], float], product_code: str, phase_name: str,
) -> float:
    """Same fallback as engine.cycle_engine._lookup_cycle, returns 0.0 if missing."""
    key = (product_code, phase_name)
    if key in cycles:
        return cycles[key]
    stripped = strip_revision_suffix(product_code)
    if stripped != product_code:
        key2 = (stripped, phase_name)
        if key2 in cycles:
            return cycles[key2]
    return 0.0


def upsert_cycles(
    conn, cycles: Dict[Tuple[str, str], float], source_file: str,
) -> None:
    """Replace ALL rows in PianoTempi_Cycles with the current routing snapshot.

    Strategy: DELETE all existing rows + bulk INSERT. Simplest, ensures
    rows for products/phases removed from the routing also disappear.
    `cycles` dict must already be canonicalized (alias-applied)."""
    if not cycles:
        logger.info("upsert_cycles called with empty dict -- nothing to do")
        return
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM traceability_rs.dbo.PianoTempi_Cycles")
        for (product_code, phase_name), cycle_minutes in cycles.items():
            if not product_code or not phase_name:
                continue
            cursor.execute("""
                INSERT INTO traceability_rs.dbo.PianoTempi_Cycles
                    (ProductCode, PhaseName, CycleTimeMinutes, SourceFile, UpdatedAt)
                VALUES (?, ?, ?, ?, GETDATE())
            """, product_code, phase_name, float(cycle_minutes), source_file)
        cursor.close()
        logger.info("PianoTempi_Cycles synced: %d rows from %s", len(cycles), source_file)
    except Exception as e:
        logger.error("upsert_cycles failed: %s", e)


def upsert_plan_history(
    conn, plan_date: date,
    plan_rows: List[PlanRow],
    cycles: Dict[Tuple[str, str], float],
) -> None:
    """Replace today's snapshot in PianoTempi_PlanHistory with the current plan.

    Strategy: DELETE WHERE PlanDate = plan_date + INSERT the current rows.
    Past dates are untouched."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM traceability_rs.dbo.PianoTempi_PlanHistory WHERE PlanDate = ?",
            plan_date,
        )
        for row in plan_rows:
            cycle = _lookup_cycle_with_fallback(cycles, row.product_code, row.phase_name)
            planned_min = row.planned_qty * cycle
            planned_h = minutes_to_hours(planned_min)
            cursor.execute("""
                INSERT INTO traceability_rs.dbo.PianoTempi_PlanHistory
                    (PlanDate, OrderNumber, PhaseName, ProductCode,
                     PlannedQty, CycleTimeMinutes, PlannedMinutes, PlannedHours,
                     SnapshotTime)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
            """,
                plan_date, row.order_number, row.phase_name, row.product_code,
                int(row.planned_qty), float(cycle), float(planned_min), float(planned_h),
            )
        cursor.close()
        logger.info("PianoTempi_PlanHistory synced for %s: %d rows", plan_date, len(plan_rows))
    except Exception as e:
        logger.error("upsert_plan_history failed: %s", e)


def upsert_prod_history(
    conn, prod_date: date,
    produced: Dict[Tuple[str, str, str], int],   # (order, phase, shift) -> qty
    order_to_product: Dict[str, str],
    cycles: Dict[Tuple[str, str], float],
    phase_mapping: Dict[str, List[int]],          # canonical -> [trace_ids]
) -> None:
    """Replace today's snapshot in PianoTempi_ProdHistory.

    Strategy: DELETE WHERE ProdDate = prod_date + INSERT current rows."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM traceability_rs.dbo.PianoTempi_ProdHistory WHERE ProdDate = ?",
            prod_date,
        )
        for (order_number, phase_name, shift_code), qty in produced.items():
            product_code = order_to_product.get(order_number, "")
            cycle = _lookup_cycle_with_fallback(cycles, product_code, phase_name)
            prod_min = qty * cycle
            prod_h = minutes_to_hours(prod_min)
            trace_ids = phase_mapping.get(phase_name, [])
            trace_id = trace_ids[0] if trace_ids else None
            cursor.execute("""
                INSERT INTO traceability_rs.dbo.PianoTempi_ProdHistory
                    (ProdDate, OrderNumber, PhaseName, ShiftCode, ProductCode,
                     TraceabilityPhaseId, ProducedQty, CycleTimeMinutes,
                     ProducedMinutes, ProducedHours, SnapshotTime)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
            """,
                prod_date, order_number, phase_name, shift_code, product_code,
                trace_id, int(qty), float(cycle), float(prod_min), float(prod_h),
            )
        cursor.close()
        logger.info("PianoTempi_ProdHistory synced for %s: %d rows", prod_date, len(produced))
    except Exception as e:
        logger.error("upsert_prod_history failed: %s", e)


# ----------------------------------------------------------------------
# Read helpers (will be used by Excel export and email report in later dispatches)
# ----------------------------------------------------------------------

def get_plan_history_for_date(conn, plan_date: date) -> List[Dict]:
    """Return list of dicts (one per row) for PianoTempi_PlanHistory on plan_date."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT PlanDate, OrderNumber, PhaseName, ProductCode,
               PlannedQty, CycleTimeMinutes, PlannedMinutes, PlannedHours
        FROM traceability_rs.dbo.PianoTempi_PlanHistory
        WHERE PlanDate = ?
        ORDER BY PhaseName, OrderNumber
    """, plan_date)
    cols = ["plan_date", "order_number", "phase_name", "product_code",
            "planned_qty", "cycle_time_minutes", "planned_minutes", "planned_hours"]
    rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
    cursor.close()
    return rows


def get_prod_history_for_date(conn, prod_date: date) -> List[Dict]:
    """Return list of dicts (one per row) for PianoTempi_ProdHistory on prod_date."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ProdDate, OrderNumber, PhaseName, ShiftCode, ProductCode,
               TraceabilityPhaseId, ProducedQty, CycleTimeMinutes,
               ProducedMinutes, ProducedHours
        FROM traceability_rs.dbo.PianoTempi_ProdHistory
        WHERE ProdDate = ?
        ORDER BY PhaseName, ShiftCode, OrderNumber
    """, prod_date)
    cols = ["prod_date", "order_number", "phase_name", "shift_code", "product_code",
            "traceability_phase_id", "produced_qty", "cycle_time_minutes",
            "produced_minutes", "produced_hours"]
    rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
    cursor.close()
    return rows


def get_cycles_master(conn) -> List[Dict]:
    """Return current contents of PianoTempi_Cycles."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ProductCode, PhaseName, CycleTimeMinutes, SourceFile, UpdatedAt
        FROM traceability_rs.dbo.PianoTempi_Cycles
        ORDER BY ProductCode, PhaseName
    """)
    cols = ["product_code", "phase_name", "cycle_time_minutes", "source_file", "updated_at"]
    rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
    cursor.close()
    return rows


def replace_anomalies_for_date(conn, anomaly_date: date, anomalies) -> None:
    """Replace today's anomalies snapshot. Strategy: DELETE WHERE AnomalyDate=...
    then INSERT all current. Past dates untouched.

    `anomalies` is a list of engine.anomaly_detector.Anomaly instances."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM traceability_rs.dbo.PianoTempi_Anomalies WHERE AnomalyDate = ?",
            anomaly_date,
        )
        for a in anomalies:
            cursor.execute("""
                INSERT INTO traceability_rs.dbo.PianoTempi_Anomalies
                    (AnomalyDate, Category, OrderNumber, PhaseName,
                     ProductCode, Detail, DetectedAt)
                VALUES (?, ?, ?, ?, ?, ?, GETDATE())
            """,
                anomaly_date, a.category, a.order_number, a.phase_name,
                a.product_code, a.detail,
            )
        cursor.close()
    except Exception as e:
        logger.error("replace_anomalies_for_date failed: %s", e)


def get_anomalies_for_date(conn, anomaly_date: date) -> List[Dict]:
    cursor = conn.cursor()
    cursor.execute("""
        SELECT Category, OrderNumber, PhaseName, ProductCode, Detail, DetectedAt
        FROM traceability_rs.dbo.PianoTempi_Anomalies
        WHERE AnomalyDate = ?
        ORDER BY Category, PhaseName, OrderNumber
    """, anomaly_date)
    cols = ["category", "order_number", "phase_name", "product_code", "detail", "detected_at"]
    rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
    cursor.close()
    return rows


def get_history_aggregates(conn, start_date: date, end_date: date) -> List[Dict]:
    """Aggregate plan + prod hours per day across [start_date, end_date].
    Returns list of {'date', 'planned_h', 'produced_h', 'coverage_pct'}."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT PlanDate AS d, SUM(PlannedHours) AS plan_h, 0.0 AS prod_h
        FROM traceability_rs.dbo.PianoTempi_PlanHistory
        WHERE PlanDate BETWEEN ? AND ?
        GROUP BY PlanDate
        UNION ALL
        SELECT ProdDate AS d, 0.0 AS plan_h, SUM(ProducedHours) AS prod_h
        FROM traceability_rs.dbo.PianoTempi_ProdHistory
        WHERE ProdDate BETWEEN ? AND ?
        GROUP BY ProdDate
    """, start_date, end_date, start_date, end_date)
    by_day: Dict[date, Dict[str, float]] = {}
    for row in cursor.fetchall():
        d = row[0]
        if d is None:
            continue
        agg = by_day.setdefault(d, {"plan": 0.0, "prod": 0.0})
        agg["plan"] += float(row[1] or 0.0)
        agg["prod"] += float(row[2] or 0.0)
    cursor.close()
    out = []
    for d in sorted(by_day.keys()):
        plan = round(by_day[d]["plan"], 2)
        prod = round(by_day[d]["prod"], 2)
        cov = round(prod / plan * 100.0, 2) if plan > 0 else 0.0
        out.append({"date": d, "planned_h": plan, "produced_h": prod, "coverage_pct": cov})
    return out
