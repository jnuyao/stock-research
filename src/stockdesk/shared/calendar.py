"""交易日历。切片 1 只有美股；港股日历在切片 2 加入。"""

from __future__ import annotations

from datetime import date, timedelta

# 纽交所休市日（2026 年、2027 年）
NYSE_HOLIDAYS = {
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3), date(2026, 5, 25),
    date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7), date(2026, 11, 26), date(2026, 12, 25),
    date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26), date(2027, 5, 31),
    date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6), date(2027, 11, 25), date(2027, 12, 24),
}


def is_trading_day(day: date, market: str = "US") -> bool:
    if market != "US":
        raise NotImplementedError("港股交易日历在切片 2 加入")
    return day.weekday() < 5 and day not in NYSE_HOLIDAYS


def last_trading_day(on_or_before: date, market: str = "US") -> date:
    day = on_or_before
    while not is_trading_day(day, market):
        day -= timedelta(days=1)
    return day
