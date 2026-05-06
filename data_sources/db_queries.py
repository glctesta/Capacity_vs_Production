# data_sources/db_queries.py
"""All SQL queries for the application. Single module, easy to scan."""
import logging
import re
from datetime import datetime
from typing import Dict, Iterable, List, Tuple

from engine.models import PhaseMap

logger = logging.getLogger("PianoTempi")


def get_phase_mapping(conn) -> List[PhaseMap]:
    """Phase mapping query (spec §1.4 / §3 / §4.2).
    Returns one PhaseMap per row.
    """
    sql = """
        SELECT cs.PhaseTraceId       AS Traceability_PhaseId,
               p.PhaseName            AS Traceability_PhaseName,
               cs.PhasePlanningId     AS Planning_PhaseId,
               tp.PhaseName            AS Planning_PhaseName
        FROM Employee.dbo.CdcSubLinkTraces cs
        INNER JOIN TraceabilityPlanning_RS.dbo.Phase tp
            ON tp.PhaseId = cs.PhasePlanningId
        INNER JOIN traceability_rs.dbo.Phases p
            ON p.IdPhase = cs.PhaseTraceId
    """
    cursor = conn.cursor()
    cursor.execute(sql)
    rows = cursor.fetchall()
    cursor.close()
    out: List[PhaseMap] = []
    for r in rows:
        if r[0] is None or r[3] is None:
            continue
        out.append(PhaseMap(
            planning_phase_name=str(r[3]).strip(),
            planning_phase_id=int(r[2]) if r[2] is not None else 0,
            traceability_phase_id=int(r[0]),
            traceability_phase_name=str(r[1]).strip() if r[1] else "",
        ))
    return out


def resolve_orders_to_products(
    conn, order_numbers: Iterable[str],
) -> Dict[str, Tuple[int, str]]:
    """Returns {order_number: (id_order, product_code)} for the requested orders.
    Batched in chunks of 500 to avoid SQL Server parameter limits."""
    order_list = list({o for o in order_numbers if o})
    if not order_list:
        return {}
    out: Dict[str, Tuple[int, str]] = {}
    chunk_size = 500
    for i in range(0, len(order_list), chunk_size):
        chunk = order_list[i:i + chunk_size]
        placeholders = ",".join("?" for _ in chunk)
        sql = f"""
            SELECT o.OrderNumber, o.IdOrder, p.ProductCode
            FROM Traceability_rs.dbo.Orders o
            INNER JOIN traceability_rs.dbo.Products p ON o.IdProduct = p.IdProduct
            WHERE o.OrderNumber IN ({placeholders})
        """
        cursor = conn.cursor()
        cursor.execute(sql, *chunk)
        for row in cursor.fetchall():
            out[str(row[0]).strip()] = (int(row[1]), str(row[2]).strip())
        cursor.close()
    return out


def get_production_in_window(
    conn, id_order: int, traceability_phase_id: int,
    start_dt: datetime, end_dt: datetime,
) -> int:
    """Returns produced qty (DISTINCT BoardLabels) for (order, phase) in [start, end).
    Adapted from PlanRespect.get_past_production with arbitrary window.
    Filter: Scannings.IsPass = 1 (only good pieces)."""
    sql = """
        SELECT COUNT(DISTINCT Traceability_rs.dbo.BoardLabels(Scannings.IDBoard)) AS Qty
        FROM Traceability_rs.dbo.Scannings
        INNER JOIN Traceability_rs.dbo.OrderPhases
            ON Scannings.IDOrderPhase = OrderPhases.IDOrderPhase
        INNER JOIN Traceability_rs.dbo.Orders
            ON OrderPhases.IDOrder = Orders.IDOrder
        INNER JOIN Traceability_rs.dbo.Phases
            ON OrderPhases.IDPhase = Phases.IDPhase
        INNER JOIN Traceability_rs.dbo.Boards
            ON Boards.IDBoard = Scannings.IDBoard
        WHERE Scannings.ScanTimeFinish >= ?
          AND Scannings.ScanTimeFinish < ?
          AND Scannings.IsPass = 1
          AND Orders.IdOrder = ?
          AND Phases.IdPhase = ?
    """
    cursor = conn.cursor()
    cursor.execute(sql, start_dt, end_dt, id_order, traceability_phase_id)
    row = cursor.fetchone()
    cursor.close()
    if row is None or row[0] is None:
        return 0
    return int(row[0])


def get_email_recipients(conn) -> List[str]:
    """Reads first row of settings.Value for Attribute='Sys_email_efficienze',
    splits on ',' and ';'. Empty list if no row matches."""
    sql = """
        SELECT TOP 1 Value FROM traceability_rs.dbo.settings
        WHERE Attribute = 'Sys_email_efficienze'
    """
    cursor = conn.cursor()
    cursor.execute(sql)
    row = cursor.fetchone()
    cursor.close()
    if row is None or row[0] is None:
        return []
    raw = str(row[0])
    tokens = [t.strip() for t in re.split(r"[,;]", raw) if t.strip()]
    return tokens
