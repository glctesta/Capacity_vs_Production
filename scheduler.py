# scheduler.py
"""APScheduler with 5 jobs: refresh_routing, refresh_planning, refresh_production,
daily_history_commit, daily_email_report."""
import logging
import os
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app_config import AppConfig
from data_cache import DataCache

logger = logging.getLogger("PianoTempi")


def build_scheduler(cache: DataCache, config: AppConfig, conn_factory) -> BackgroundScheduler:
    """Create and return the BackgroundScheduler with all 5 jobs registered.

    `conn_factory`: zero-arg callable that returns a context-manager DB connection
    (e.g. `lambda: DatabaseConnection(ConfigManager())`).
    """
    sched = BackgroundScheduler(timezone="Europe/Bucharest")

    def _job_routing():
        try:
            with conn_factory() as conn:
                cache.refresh_routing(conn)
        except Exception as e:
            logger.error("refresh_routing failed: %s", e)

    def _job_planning():
        try:
            with conn_factory() as conn:
                cache.refresh_planning(conn)
                _check_routing_mtime(cache, conn)
        except Exception as e:
            logger.error("refresh_planning failed: %s", e)

    def _job_production():
        try:
            with conn_factory() as conn:
                cache.refresh_production(conn)
        except Exception as e:
            logger.error("refresh_production failed: %s", e)

    def _job_daily_history():
        try:
            from engine.rolling_engine import save_day_to_history
            from engine.shift_engine import operative_day
            now = datetime.now()
            # The day that just closed is operative_day - 1 day (we run at 07:30:30,
            # so operative_day(now) is "today", but the day we just closed is yesterday).
            yesterday = operative_day(now) - timedelta(days=1)
            phases = {
                k: {"planned_h": v.planned_h_day, "produced_h": v.produced_h_day}
                for k, v in cache.phase_kpis.items()
            }
            path = os.path.join("data", f"daily_history_{yesterday.year}.json")
            save_day_to_history(path, day=yesterday, phases=phases)
            logger.info("daily history committed for %s", yesterday)
        except Exception as e:
            logger.error("daily_history_commit failed: %s", e)

    def _job_email():
        try:
            from reporting.email_report import send_daily
            with conn_factory() as conn:
                send_daily(cache, conn)
        except Exception as e:
            logger.error("daily_email_report failed: %s", e)

    routing_at = config.refresh.routing_daily_at  # "07:00"
    rh, rm = routing_at.split(":")
    sched.add_job(_job_routing, CronTrigger(hour=int(rh), minute=int(rm)),
                  id="refresh_routing", coalesce=True, max_instances=1)
    sched.add_job(_job_planning,
                  IntervalTrigger(minutes=config.refresh.planning_minutes),
                  id="refresh_planning", coalesce=True, max_instances=1)
    sched.add_job(_job_production,
                  IntervalTrigger(seconds=config.refresh.production_seconds),
                  id="refresh_production", coalesce=True, max_instances=1)
    # Daily history commit at 07:30:30 (just before email at 07:31)
    sched.add_job(_job_daily_history,
                  CronTrigger(hour=7, minute=30, second=30),
                  id="daily_history_commit", coalesce=True, max_instances=1)
    eh, em = config.email_report.send_at.split(":")
    sched.add_job(_job_email,
                  CronTrigger(hour=int(eh), minute=int(em)),
                  id="daily_email_report", coalesce=True, max_instances=1)
    return sched


def _check_routing_mtime(cache: DataCache, conn) -> None:
    """Reload routing if file mtime has changed since last load."""
    from data_sources.routing_excel import find_latest_routing_file
    src = find_latest_routing_file(cache.config.data_sources.routing_folder)
    if src is None:
        return
    try:
        mtime = datetime.fromtimestamp(os.path.getmtime(src))
    except OSError:
        return
    prev = cache.routing_source_mtime
    if prev is None or mtime > prev:
        cache.refresh_routing(conn)
