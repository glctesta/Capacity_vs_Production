"""Shift/operative-day calculations. Pure functions, no I/O."""
from datetime import date, datetime, time, timedelta
from typing import List, Tuple

from app_config import ShiftConfig

DAY_START = time(7, 30)


def operative_day(now: datetime, day_start: time = DAY_START) -> date:
    """If now < 07:30 -> yesterday's calendar date."""
    if now.time() < day_start:
        return (now - timedelta(days=1)).date()
    return now.date()


def current_shift(now: datetime, shifts: List[ShiftConfig]) -> str:
    """Return shift_code (T1/T2/T3). Handles T3 wrap (23:30 -> 07:30)."""
    t = now.time()
    for s in shifts:
        if s.start <= s.end:
            # Normal shift (no wrap)
            if s.start <= t < s.end:
                return s.code
        else:
            # Wraps midnight (T3): 23:30 -> 07:30
            if t >= s.start or t < s.end:
                return s.code
    # Fallback: return last shift
    return shifts[-1].code


def shift_window(d: date, shift: ShiftConfig) -> Tuple[datetime, datetime]:
    """Return (start_dt, end_dt). For wrap shift, end is on d+1."""
    start_dt = datetime.combine(d, shift.start)
    if shift.start <= shift.end:
        end_dt = datetime.combine(d, shift.end)
    else:
        end_dt = datetime.combine(d + timedelta(days=1), shift.end)
    return start_dt, end_dt


def day_total_gross_hours(any_t3_production: bool) -> float:
    """24 if T3 has production (ScanTimeFinish >= 23:30), else 16."""
    return 24.0 if any_t3_production else 16.0
