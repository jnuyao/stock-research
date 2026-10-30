"""[TECH] 技术位。只从日线算，不做判断；数据经 [QA] 取得。

“多次测试的支撑”按 SPEC 定义：近 250 个交易日里，日最低价落在同一 2% 区间内至少 3 次，
且每次之后 20 个交易日内反弹超过 5%。“一次”指一个局部低点（前后各 3 天里最低）。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from statistics import fmean
from typing import Any

from stockdesk.qa import BARS, Need, SeriesNeed, require
from stockdesk.shared.calendar import is_week_close, trading_days_between

MIN_ROWS = 260          # 200 日线 + 一年的支撑判断
WINDOW_52W = 252
SUPPORT_LOOKBACK = 250
SWING_WINDOW = 3
REBOUND_DAYS = 20
REBOUND_PCT = 0.05
BAND_PCT = 0.02
MIN_TOUCHES = 3
DRAWDOWNS = (0.35, 0.40, 0.45)


def _r(x: float) -> float:
    return round(x, 4)


def _supports(dates: list[str], highs: list[float], lows: list[float]) -> list[dict[str, Any]]:
    n = len(lows)
    swings = []
    for i in range(max(SWING_WINDOW, n - SUPPORT_LOOKBACK), n - SWING_WINDOW):
        if lows[i] != min(lows[i - SWING_WINDOW:i + SWING_WINDOW + 1]):
            continue
        after = highs[i + 1:i + 1 + REBOUND_DAYS]
        if after and max(after) >= lows[i] * (1 + REBOUND_PCT):
            swings.append((lows[i], dates[i]))
    swings.sort()
    out, used = [], set()
    for k, (low, _) in enumerate(swings):
        if k in used:
            continue
        group = [j for j in range(k, len(swings)) if j not in used and swings[j][0] <= low * (1 + BAND_PCT)]
        if len(group) >= MIN_TOUCHES:
            used.update(group)
            pts = sorted((swings[j][1], swings[j][0]) for j in group)
            out.append({"level": _r(fmean(p[1] for p in pts)), "touches": [p[0] for p in pts],
                        "lows": [p[1] for p in pts]})
        else:
            used.add(k)
    return sorted(out, key=lambda s: -s["level"])


def levels(ticker: str, as_of: str, root: Path, market: str = "US",
           earnings_date: str | None = None, earnings_timing: str = "after_close") -> dict[str, Any]:
    ds = require(ticker, [Need("price_after_hours", as_of, critical=False)], root=root, as_of=as_of,
                 market=market, series_needs=[SeriesNeed(BARS, MIN_ROWS)], check_price=True)
    bars = ds.series[BARS]
    dates = bars.column("date")
    highs = [float(x) for x in bars.column("high")]
    lows = [float(x) for x in bars.column("low")]
    closes = [float(x) for x in bars.column("close")]

    hi_i = max(range(len(highs) - WINDOW_52W, len(highs)), key=lambda i: highs[i])
    lo_i = min(range(len(lows) - WINDOW_52W, len(lows)), key=lambda i: lows[i])
    weekly = [{"date": d, "value": c} for d, c in zip(dates, closes, strict=True)
              if is_week_close(date.fromisoformat(d), market)]

    out: dict[str, Any] = {
        "currency": bars.unit,
        "source": {"url": bars.source_url, "as_of": bars.as_of, "fetched_at": bars.fetched_at},
        "last_close": {"date": dates[-1], "value": closes[-1]},
        "weekly_close": weekly[-1] if weekly else None,
        "weekly_closes": weekly[-52:],
        "ma50": _r(fmean(closes[-50:])),
        "ma200": _r(fmean(closes[-200:])),
        "high_52w": {"date": dates[hi_i], "value": highs[hi_i]},
        "low_52w": {"date": dates[lo_i], "value": lows[lo_i]},
        "drawdowns": {f"{d:.2f}": _r(highs[hi_i] * (1 - d)) for d in DRAWDOWNS},
        "supports": _supports(dates, highs, lows),
        "after_hours": None,
        "pre_earnings_close": None,
    }
    ah = ds.get("price_after_hours", as_of)
    if ah is not None and ah.value is not None:
        out["after_hours"] = {"date": as_of, "value": ah.value, "source_url": ah.source_url, "note": ah.note}
    if earnings_date and earnings_date <= dates[-1]:
        # 盘后发布：财报前收盘就是发布当天收盘；盘前发布：取前一个交易日
        idx = max(i for i, d in enumerate(dates) if d <= earnings_date)
        if earnings_timing == "before_open" and dates[idx] == earnings_date:
            idx -= 1
        out["pre_earnings_close"] = {"date": dates[idx], "value": closes[idx], "earnings_date": earnings_date,
                                     "timing": earnings_timing}
        out["trading_days_since_earnings"] = trading_days_between(
            date.fromisoformat(earnings_date), date.fromisoformat(as_of), market)
    return out
