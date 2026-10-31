"""交易日历：美股（纽交所）和港股（港交所）。

休市日来源：纽交所官网假期表；香港政府公布的公众假期（教育局 2026/27 学年假期表）。
2024-07 至 2026-10 的两份日历都用 Yahoo 日线核对过：有日线的工作日都是交易日，没日线的工作日都在表里。
表外的年份会报错，提醒补日历，而不是默认当作交易日。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .errors import ErrorCode, StockdeskError


def _d(*days: str) -> set[date]:
    return {date.fromisoformat(x) for x in days}


NYSE_HOLIDAYS = _d(
    "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27", "2024-06-19", "2024-07-04",
    "2024-09-02", "2024-11-28", "2024-12-25",
    "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26", "2025-06-19",
    "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25",
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03",
    "2026-09-07", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18", "2027-07-05",
    "2027-09-06", "2027-11-25", "2027-12-24",
)

# 港股休市日（只列工作日）。2024-09-06 是台风“摩羯”停市，不是公众假期。
HKEX_HOLIDAYS = _d(
    "2024-07-01", "2024-09-06", "2024-09-18", "2024-10-01", "2024-10-11", "2024-12-25", "2024-12-26",
    "2025-01-01", "2025-01-29", "2025-01-30", "2025-01-31", "2025-04-04", "2025-04-18", "2025-04-21",
    "2025-05-01", "2025-05-05", "2025-07-01", "2025-10-01", "2025-10-07", "2025-10-29", "2025-12-25",
    "2025-12-26",
    "2026-01-01", "2026-02-17", "2026-02-18", "2026-02-19", "2026-04-03", "2026-04-06", "2026-04-07",
    "2026-05-01", "2026-05-25", "2026-06-19", "2026-07-01", "2026-10-01", "2026-10-19", "2026-12-25",
    "2027-01-01", "2027-02-08", "2027-02-09", "2027-03-26", "2027-03-29", "2027-04-05", "2027-05-13",
    "2027-06-09", "2027-07-01",
)

KNOWN = {
    "US": (date(2024, 1, 1), date(2027, 12, 31), NYSE_HOLIDAYS),
    "HK": (date(2024, 1, 1), date(2027, 8, 31), HKEX_HOLIDAYS),
}

# 收盘时间（当地时间）：美东 16:00；香港 16:10（收市竞价结束）
MARKET_TZ = {"US": ZoneInfo("America/New_York"), "HK": ZoneInfo("Asia/Hong_Kong")}
MARKET_CLOSE = {"US": time(16, 0), "HK": time(16, 10)}


def market_of(ticker: str) -> str:
    return "HK" if ticker.upper().endswith(".HK") else "US"


def is_trading_day(day: date, market: str = "US") -> bool:
    if market not in KNOWN:
        raise StockdeskError(ErrorCode.BAD_INPUT, f"不认识的市场 {market}，目前只有 US 和 HK")
    start, end, holidays = KNOWN[market]
    if not start <= day <= end:
        raise StockdeskError(
            ErrorCode.BAD_INPUT, f"{market} 交易日历只覆盖到 {start}–{end}，{day} 不在表里",
            {"market": market, "day": day.isoformat()},
        )
    return day.weekday() < 5 and day not in holidays


def last_trading_day(on_or_before: date, market: str = "US") -> date:
    day = on_or_before
    while not is_trading_day(day, market):
        day -= timedelta(days=1)
    return day


def previous_trading_day(day: date, market: str = "US") -> date:
    return last_trading_day(day - timedelta(days=1), market)


def trading_days_between(start: date, end: date, market: str = "US") -> int:
    """start 之后到 end（含）之间有几个交易日。"""
    n, day = 0, start
    while day < end:
        day += timedelta(days=1)
        if is_trading_day(day, market):
            n += 1
    return n


def is_week_close(day: date, market: str = "US") -> bool:
    """day 是不是那一周最后一个交易日（周五休市时是周四，依此类推）。"""
    nxt = day + timedelta(days=1)
    while nxt.weekday() < 5 and not is_trading_day(nxt, market):
        nxt += timedelta(days=1)
    return nxt.weekday() >= 5


def market_today(now: datetime, market: str = "US") -> date:
    """now（带时区）在该市场当地是哪一天。"""
    return now.astimezone(MARKET_TZ[market]).date()


def session_closed(day: date, now: datetime, market: str = "US") -> bool:
    """day 这一天的交易是否已经收盘（盘中抓到的当天日线还不是收盘价）。"""
    local = now.astimezone(MARKET_TZ[market])
    if day < local.date():
        return True
    return day == local.date() and local.time() >= MARKET_CLOSE[market]


def last_closed_session(now: datetime, market: str = "US") -> date:
    """到 now 为止最近一个已经收盘的交易日。"""
    day = last_trading_day(market_today(now, market), market)
    return day if session_closed(day, now, market) else previous_trading_day(day, market)


def fiscal_quarter(period_end: date, fiscal_year_end: int = 12) -> str:
    """季度末日期 → 季度名。财年和日历年一致时写 2026Q3，否则写 FY2027Q1（财年按结束那年命名）。

    季度末常落在月底前后几天（英特尔 2026-09-27），先往前挪 7 天再看月份。
    """
    d = period_end - timedelta(days=7)
    start = fiscal_year_end % 12 + 1
    quarter = (d.month - start) % 12 // 3 + 1
    if fiscal_year_end == 12:
        return f"{d.year}Q{quarter}"
    year = d.year if d.month <= fiscal_year_end else d.year + 1
    return f"FY{year}Q{quarter}"
