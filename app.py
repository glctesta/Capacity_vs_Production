# app.py
"""Flask app + lifecycle wiring (lifecycle done in Task 14.1)."""
import logging
import os
import sys
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler

from flask import Flask, jsonify, render_template

from data_cache import DataCache


def setup_logging() -> logging.Logger:
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger("PianoTempi")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)
    fh = RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8",
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


def _kpi_to_dict(kpi):
    return {
        "phase_name": kpi.phase_name,
        "shift_code": kpi.shift_code,
        "planned_h_day": kpi.planned_h_day,
        "planned_h_shift": kpi.planned_h_shift,
        "planned_h_so_far_day": kpi.planned_h_so_far_day,
        "planned_h_so_far_shift": kpi.planned_h_so_far_shift,
        "produced_h_day": kpi.produced_h_day,
        "produced_h_shift": kpi.produced_h_shift,
        "delta_vs_expected_day": kpi.delta_vs_expected_day,
        "delta_vs_expected_shift": kpi.delta_vs_expected_shift,
        "coverage_pct_day": kpi.coverage_pct_day,
        "status_color": kpi.status_color,
        "curve_points": [
            {"time": t.isoformat(timespec="seconds"), "h": h}
            for t, h in kpi.curve_points
        ],
    }


def build_flask_app(cache: DataCache) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")

    @app.route("/")
    def index():
        return render_template(
            "dashboard.html",
            polling_seconds=cache.config.refresh.frontend_polling_seconds,
            rotation_seconds=cache.config.phases.rotation_interval_seconds,
            manual_pause_seconds=cache.config.phases.manual_navigation_pause_seconds,
            monitored_phases=cache.config.phases.monitored,
        )

    @app.route("/api/health")
    def health():
        now = datetime.now()
        out = {"now": now.isoformat(), "last_refresh": {}, "stale": {}}
        prod_threshold = timedelta(seconds=cache.config.refresh.production_seconds * 2)
        for source, ts in cache.last_refresh_ts.items():
            out["last_refresh"][source] = ts.isoformat()
            out["stale"][source] = (now - ts) > prod_threshold
        return jsonify(out)

    @app.route("/api/phases")
    def phases():
        with cache.lock():
            return jsonify({
                "phases": {n: _kpi_to_dict(k) for n, k in cache.phase_kpis.items()},
            })

    @app.route("/api/totals")
    def totals():
        with cache.lock():
            t = cache.total_kpi
            if t is None:
                return jsonify({})
            return jsonify({
                "planned_h_day": t.planned_h_day,
                "planned_h_so_far_day": t.planned_h_so_far_day,
                "produced_h_day": t.produced_h_day,
                "delta_vs_expected_day": t.delta_vs_expected_day,
                "coverage_pct_day": t.coverage_pct_day,
                "status_color": t.status_color,
            })

    @app.route("/api/rolling-month")
    def rolling_month():
        with cache.lock():
            r = cache.rolling_data
            if r is None:
                return jsonify({})
            return jsonify({
                "days": [
                    {"date": d.date.isoformat(),
                     "planned_h": d.planned_h,
                     "produced_h": d.produced_h,
                     "coverage_pct": d.coverage_pct}
                    for d in r.days
                ],
                "month_planned_h": r.month_planned_h,
                "month_produced_h": r.month_produced_h,
                "month_coverage_pct": r.month_coverage_pct,
                "ytd_planned_h": r.ytd_planned_h,
                "ytd_produced_h": r.ytd_produced_h,
                "ytd_coverage_pct": r.ytd_coverage_pct,
                "working_days_month": r.working_days_month,
                "working_days_ytd": r.working_days_ytd,
            })

    return app
