# reporting/email_anomalies.py
"""Send an email at the start of each shift listing currently-open anomalies."""
import logging
from datetime import datetime
from typing import Dict, List

from data_cache import DataCache
from data_sources.db_history import get_anomalies_for_date
from data_sources.db_queries import get_email_recipients
from engine.shift_engine import operative_day, current_shift

logger = logging.getLogger("PianoTempi")


def _group_by_category(anomalies: List[Dict]) -> Dict[str, List[Dict]]:
    out: Dict[str, List[Dict]] = {}
    for a in anomalies:
        out.setdefault(a["category"], []).append(a)
    return out


def generate_anomaly_subject(prefix: str, shift_code: str, op_day, n_issues: int) -> str:
    return (f"{prefix} Anomaly alert - shift {shift_code} - "
            f"{op_day.isoformat()} - {n_issues} issue(s)")


def generate_anomaly_plain_body(
    op_day, shift_code: str, anomalies: List[Dict],
) -> str:
    lines = []
    lines.append(f"Operative day: {op_day.isoformat()}")
    lines.append(f"Shift: {shift_code}")
    lines.append(f"Total open anomalies: {len(anomalies)}")
    lines.append("")
    grouped = _group_by_category(anomalies)
    for cat in sorted(grouped.keys()):
        items = grouped[cat]
        lines.append(f"== {cat.upper()} ({len(items)}) ==")
        for a in items:
            order = a.get("order_number") or "-"
            phase = a.get("phase_name") or "-"
            product = a.get("product_code") or "-"
            detail = a.get("detail") or ""
            lines.append(f"  order={order:<20s} phase={phase:<20s} product={product:<20s}")
            lines.append(f"    {detail}")
        lines.append("")
    lines.append("Resolve by adding missing cycle times to the routing Excel,")
    lines.append("adding aliases to config.json, or correcting the planning data.")
    return "\n".join(lines)


def generate_anomaly_html_body(
    op_day, shift_code: str, anomalies: List[Dict],
) -> str:
    grouped = _group_by_category(anomalies)
    sections = []
    for cat in sorted(grouped.keys()):
        items = grouped[cat]
        rows = []
        for a in items:
            rows.append(
                f'<tr><td>{a.get("order_number") or ""}</td>'
                f'<td>{a.get("phase_name") or ""}</td>'
                f'<td>{a.get("product_code") or ""}</td>'
                f'<td>{a.get("detail") or ""}</td></tr>'
            )
        sections.append(f"""
<h3 style="color:#3880ff;margin-top:20px">{cat.upper()} ({len(items)})</h3>
<table style="border-collapse:collapse;width:100%;max-width:900px">
  <thead><tr style="background:#f0f0f0">
    <th style="padding:6px;text-align:left">Order</th>
    <th style="padding:6px;text-align:left">Phase</th>
    <th style="padding:6px;text-align:left">Product</th>
    <th style="padding:6px;text-align:left">Detail</th>
  </tr></thead>
  <tbody>{''.join(rows)}</tbody>
</table>""")
    return f"""<!doctype html><html><body style="font-family:Arial,sans-serif;color:#222">
<h2 style="color:#eb445a">Anomaly alert — shift {shift_code} — {op_day.isoformat()}</h2>
<p><b>{len(anomalies)} open issue(s)</b> detected during the last refresh.</p>
{''.join(sections)}
<p style="margin-top:24px;color:#666">Resolve by adding missing cycle times to the routing Excel,
adding aliases to <code>config.json</code>, or correcting the planning data.</p>
</body></html>"""


def send_anomaly_alert(cache: DataCache, conn) -> None:
    """Read anomalies for the current operative day and email them.
    No-op (no email) if no anomalies. Skips if email_report.enabled is False."""
    cfg = cache.config.email_report
    if not cfg.enabled:
        logger.info("email disabled in config -- skipping anomaly alert")
        return

    now = datetime.now()
    op_day = operative_day(now)
    shift_code = current_shift(now, cache.config.shifts)

    anomalies = get_anomalies_for_date(conn, op_day)
    if not anomalies:
        logger.info("no anomalies for %s shift %s -- email skipped", op_day, shift_code)
        return

    rcpts = get_email_recipients(conn)
    if not rcpts:
        logger.error("no recipients for anomaly alert -- email skipped")
        return

    subject = generate_anomaly_subject(
        cfg.subject_prefix, shift_code, op_day, len(anomalies),
    )
    plain = generate_anomaly_plain_body(op_day, shift_code, anomalies)
    html = generate_anomaly_html_body(op_day, shift_code, anomalies)

    try:
        from email_connector import EmailConnector
        ec = EmailConnector()
        try:
            ec.send_email(to=rcpts, subject=subject, body_plain=plain, body_html=html)
        except TypeError:
            for r in rcpts:
                ec.send_email(r, subject, html)
        logger.info(
            "anomaly alert sent to %d recipient(s): %d issue(s) for shift %s",
            len(rcpts), len(anomalies), shift_code,
        )
    except Exception as e:
        logger.error("anomaly email send failed: %s", e)
