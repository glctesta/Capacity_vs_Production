# reporting/email_report.py
"""Daily email report. HTML + plain text. Reuses email_connector from PlanRespect."""
import logging
from datetime import date, datetime, timedelta
from typing import Dict, Tuple

from data_cache import DataCache
from data_sources.db_queries import get_email_recipients
from engine.models import DayPoint, RollingData
from engine.shift_engine import operative_day

logger = logging.getLogger("PianoTempi")

WEEKDAY_BY_NAME = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def generate_subject(prefix: str, day: date, coverage_pct: float) -> str:
    return f"{prefix} Daily report {day.isoformat()} — coverage {coverage_pct:.1f}%"


def generate_plain_body(
    yesterday: DayPoint,
    yesterday_per_phase: Dict[str, Tuple[float, float]],
    rolling: RollingData,
) -> str:
    lines = []
    lines.append(f"YESTERDAY ({yesterday.date.isoformat()})")
    lines.append("=" * 30)
    lines.append(f"Total day plan:    {yesterday.planned_h:>9.2f} h")
    lines.append(f"Total produced:    {yesterday.produced_h:>9.2f} h")
    lines.append(f"Coverage:          {yesterday.coverage_pct:>9.2f}%")
    lines.append(f"Δ vs plan:         {yesterday.produced_h - yesterday.planned_h:>+9.2f} h")
    lines.append("")
    lines.append("Per-phase breakdown:")
    for phase, (plan_h, prod_h) in sorted(yesterday_per_phase.items()):
        cov = (prod_h / plan_h * 100) if plan_h > 0 else 0
        lines.append(
            f"  {phase:<12} plan {plan_h:>6.2f}  prod {prod_h:>6.2f}  "
            f"cov {cov:>5.1f}%   Δ {prod_h - plan_h:+6.2f}"
        )
    lines.append("")

    lines.append(f"MONTH TO DATE ({yesterday.date.replace(day=1).isoformat()} → {yesterday.date.isoformat()})")
    lines.append("=" * 40)
    lines.append(f"Plan:        {rolling.month_planned_h:>11.2f} h")
    lines.append(f"Produced:    {rolling.month_produced_h:>11.2f} h")
    lines.append(f"Coverage:    {rolling.month_coverage_pct:>10.2f}%")
    lines.append(f"Working days: {rolling.working_days_month}")
    lines.append("")

    lines.append(f"YEAR TO DATE ({yesterday.date.replace(month=1, day=1).isoformat()} → {yesterday.date.isoformat()})")
    lines.append("=" * 40)
    lines.append(f"Plan:      {rolling.ytd_planned_h:>13.2f} h")
    lines.append(f"Produced:  {rolling.ytd_produced_h:>13.2f} h")
    lines.append(f"Coverage:  {rolling.ytd_coverage_pct:>12.2f}%")
    lines.append(f"Working days: {rolling.working_days_ytd}")
    return "\n".join(lines)


def generate_html_body(
    yesterday: DayPoint,
    yesterday_per_phase: Dict[str, Tuple[float, float]],
    rolling: RollingData,
) -> str:
    rows = []
    for phase, (plan_h, prod_h) in sorted(yesterday_per_phase.items()):
        cov = (prod_h / plan_h * 100) if plan_h > 0 else 0
        rows.append(
            f'<tr><td>{phase}</td>'
            f'<td style="text-align:right">{plan_h:.2f}</td>'
            f'<td style="text-align:right">{prod_h:.2f}</td>'
            f'<td style="text-align:right">{cov:.1f}%</td>'
            f'<td style="text-align:right">{prod_h - plan_h:+.2f}</td></tr>'
        )
    return f"""<!doctype html><html><body style="font-family:Arial,sans-serif;color:#222">
<h2 style="color:#3880ff">Daily report — {yesterday.date.isoformat()}</h2>
<table style="border-collapse:collapse;width:100%;max-width:680px">
  <thead><tr style="background:#f0f0f0">
    <th style="padding:6px;text-align:left">Phase</th>
    <th style="padding:6px;text-align:right">Plan h</th>
    <th style="padding:6px;text-align:right">Prod h</th>
    <th style="padding:6px;text-align:right">Cov</th>
    <th style="padding:6px;text-align:right">Δ</th>
  </tr></thead>
  <tbody>
    {''.join(rows)}
    <tr style="font-weight:bold;border-top:2px solid #333">
      <td style="padding:6px">TOTAL</td>
      <td style="padding:6px;text-align:right">{yesterday.planned_h:.2f}</td>
      <td style="padding:6px;text-align:right">{yesterday.produced_h:.2f}</td>
      <td style="padding:6px;text-align:right">{yesterday.coverage_pct:.1f}%</td>
      <td style="padding:6px;text-align:right">{yesterday.produced_h - yesterday.planned_h:+.2f}</td>
    </tr>
  </tbody>
</table>
<h3 style="margin-top:24px">Month to date ({yesterday.date.replace(day=1).isoformat()} → {yesterday.date.isoformat()})</h3>
<ul>
  <li>Plan: <b>{rolling.month_planned_h:.2f} h</b></li>
  <li>Produced: <b>{rolling.month_produced_h:.2f} h</b></li>
  <li>Coverage: <b>{rolling.month_coverage_pct:.2f}%</b></li>
  <li>Working days: <b>{rolling.working_days_month}</b></li>
</ul>
<h3>Year to date</h3>
<ul>
  <li>Plan: <b>{rolling.ytd_planned_h:.2f} h</b></li>
  <li>Produced: <b>{rolling.ytd_produced_h:.2f} h</b></li>
  <li>Coverage: <b>{rolling.ytd_coverage_pct:.2f}%</b></li>
  <li>Working days: <b>{rolling.working_days_ytd}</b></li>
</ul>
</body></html>"""


def send_daily(cache: DataCache, conn) -> None:
    """Send the daily report. Skips if today's weekday is in skip_weekdays
    or if recipients are empty. Reads from SQL history tables."""
    cfg = cache.config.email_report
    if not cfg.enabled:
        logger.info("email report disabled in config")
        return

    today_weekday = datetime.now().weekday()
    skip_indices = {WEEKDAY_BY_NAME[d.lower()] for d in cfg.skip_weekdays
                    if d.lower() in WEEKDAY_BY_NAME}
    if today_weekday in skip_indices:
        logger.info("email report skipped: today is in skip_weekdays")
        return

    yesterday_date = operative_day(datetime.now()) - timedelta(days=1)

    from data_sources.db_history import (
        get_plan_history_for_date, get_prod_history_for_date,
        get_history_aggregates,
    )
    plan_rows = get_plan_history_for_date(conn, yesterday_date)
    prod_rows = get_prod_history_for_date(conn, yesterday_date)
    if not plan_rows and not prod_rows:
        logger.error("no SQL history for %s -- email skipped", yesterday_date)
        return

    # Aggregate per phase
    per_phase: Dict[str, Tuple[float, float]] = {}
    plan_total = prod_total = 0.0
    for r in plan_rows:
        p = r["phase_name"]
        cur = per_phase.get(p, (0.0, 0.0))
        per_phase[p] = (cur[0] + float(r.get("planned_hours") or 0.0), cur[1])
        plan_total += float(r.get("planned_hours") or 0.0)
    for r in prod_rows:
        p = r["phase_name"]
        cur = per_phase.get(p, (0.0, 0.0))
        per_phase[p] = (cur[0], cur[1] + float(r.get("produced_hours") or 0.0))
        prod_total += float(r.get("produced_hours") or 0.0)
    coverage = round(prod_total / plan_total * 100.0, 2) if plan_total > 0 else 0.0
    yesterday_dp = DayPoint(
        date=yesterday_date,
        planned_h=round(plan_total, 2),
        produced_h=round(prod_total, 2),
        coverage_pct=coverage,
    )

    # Month-to-date and YTD
    month_start = yesterday_date.replace(day=1)
    year_start = yesterday_date.replace(month=1, day=1)
    mtd_days = get_history_aggregates(conn, month_start, yesterday_date)
    ytd_days = get_history_aggregates(conn, year_start, yesterday_date)

    def _rd_totals(days):
        plan = round(sum(d["planned_h"] for d in days), 2)
        prod = round(sum(d["produced_h"] for d in days), 2)
        cov = round(prod / plan * 100.0, 2) if plan > 0 else 0.0
        wdays = len([d for d in days if d["planned_h"] > 0])
        return plan, prod, cov, wdays

    m_plan, m_prod, m_cov, m_wdays = _rd_totals(mtd_days)
    y_plan, y_prod, y_cov, y_wdays = _rd_totals(ytd_days)

    rolling = RollingData(
        days=[],
        month_planned_h=m_plan, month_produced_h=m_prod, month_coverage_pct=m_cov,
        ytd_planned_h=y_plan, ytd_produced_h=y_prod, ytd_coverage_pct=y_cov,
        working_days_month=m_wdays, working_days_ytd=y_wdays,
    )

    rcpts = get_email_recipients(conn)
    if not rcpts:
        logger.error("no email recipients (settings.Sys_email_efficienze) -- skipped")
        return

    subject = generate_subject(cfg.subject_prefix, yesterday_date, yesterday_dp.coverage_pct)
    plain = generate_plain_body(yesterday_dp, per_phase, rolling)
    html = generate_html_body(yesterday_dp, per_phase, rolling)

    try:
        from email_connector import EmailConnector
        ec = EmailConnector()
        try:
            ec.send_email(to=rcpts, subject=subject, body_plain=plain, body_html=html)
        except TypeError:
            for r in rcpts:
                ec.send_email(r, subject, html)
        logger.info("email report sent to %d recipients", len(rcpts))
    except Exception as e:
        logger.error("email send failed: %s", e)
