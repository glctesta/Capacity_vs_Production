"""In-memory cache shared between scheduler and Flask routes."""
import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from app_config import AppConfig
from engine.models import PhaseKPI, PlanRow, RollingData, TotalKPI

logger = logging.getLogger("PianoTempi")


class DataCache:
    """Singleton-style cache. Not enforced as singleton (one instance built in app.py).
    All mutations should be done under self.lock().
    """

    def __init__(self, config: AppConfig):
        self._lock = threading.RLock()
        self.config = config
        # routing
        self.routing_cycles: Dict[Tuple[str, str], float] = {}
        self.routing_source_path: str = ""
        self.routing_source_mtime: Optional[datetime] = None
        # phase mapping (planning_phase_name -> traceability_phase_id)
        self.phase_mapping: Dict[str, int] = {}
        # planning
        self.today_plan: List[PlanRow] = []
        self.order_to_product: Dict[str, str] = {}
        self.order_to_id: Dict[str, int] = {}
        # production-derived
        self.phase_kpis: Dict[str, PhaseKPI] = {}
        self.total_kpi: Optional[TotalKPI] = None
        self.rolling_data: Optional[RollingData] = None
        # bookkeeping
        self.last_refresh_ts: Dict[str, datetime] = {}

    def lock(self):
        return self._lock
