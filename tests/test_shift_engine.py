from datetime import date, datetime, time
from app_config import ShiftConfig
from engine.shift_engine import (
    operative_day, current_shift, shift_window, day_total_gross_hours,
)

SHIFTS = [
    ShiftConfig(code="T1", start=time(7, 30), end=time(15, 30)),
    ShiftConfig(code="T2", start=time(15, 30), end=time(23, 30)),
    ShiftConfig(code="T3", start=time(23, 30), end=time(7, 30)),
]


def test_operative_day_after_0730_is_today():
    assert operative_day(datetime(2026, 5, 6, 9, 0)) == date(2026, 5, 6)


def test_operative_day_before_0730_is_yesterday():
    assert operative_day(datetime(2026, 5, 6, 6, 0)) == date(2026, 5, 5)


def test_operative_day_at_exactly_0730_is_today():
    assert operative_day(datetime(2026, 5, 6, 7, 30)) == date(2026, 5, 6)


def test_current_shift_morning():
    assert current_shift(datetime(2026, 5, 6, 9, 0), SHIFTS) == "T1"


def test_current_shift_afternoon():
    assert current_shift(datetime(2026, 5, 6, 16, 0), SHIFTS) == "T2"


def test_current_shift_late_night():
    assert current_shift(datetime(2026, 5, 7, 0, 30), SHIFTS) == "T3"


def test_current_shift_at_t3_wrap_before_0730():
    assert current_shift(datetime(2026, 5, 7, 6, 0), SHIFTS) == "T3"


def test_shift_window_t1():
    s, e = shift_window(date(2026, 5, 6), SHIFTS[0])
    assert s == datetime(2026, 5, 6, 7, 30)
    assert e == datetime(2026, 5, 6, 15, 30)


def test_shift_window_t3_wraps_to_next_day():
    s, e = shift_window(date(2026, 5, 6), SHIFTS[2])
    assert s == datetime(2026, 5, 6, 23, 30)
    assert e == datetime(2026, 5, 7, 7, 30)


def test_day_total_gross_default_16():
    assert day_total_gross_hours(any_t3_production=False) == 16.0


def test_day_total_gross_with_t3_24():
    assert day_total_gross_hours(any_t3_production=True) == 24.0
