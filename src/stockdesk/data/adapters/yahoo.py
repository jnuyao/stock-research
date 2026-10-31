"""[DATA] Yahoo Finance（yfinance）：日线、盘后价、汇率、一致预期、VIX 和 10 年期美债。只在 Mac 上用。

download 部分调用 yfinance；parse 部分只吃普通的列表和字典（录下来的数据可以离线测试）。
"""

from __future__ import annotations

import calendar as cal
from datetime import date, datetime
from typing import Any

from stockdesk.shared.calendar import MARKET_TZ, fiscal_quarter, session_closed

from .base import Context, Records, SourceError

BAR_COLUMNS = ["date", "open", "high", "low", "close", "volume"]


def _yf():
    try:
        import yfinance as yf
    except ImportError as err:
        raise SourceError("没装 yfinance：在 Mac 上运行 pip install -e '.[mac]'") from err
    return yf


def history_url(symbol: str) -> str:
    return f"https://finance.yahoo.com/quote/{symbol}/history/"


def history_records(df: Any) -> list[dict[str, Any]]:
    """yfinance 的 DataFrame → [{date, open, high, low, close, volume}]，日期按交易所当地时间。"""
    out = []
    for ts, r in df.iterrows():
        out.append({"date": ts.date().isoformat(), "open": r["Open"], "high": r["High"], "low": r["Low"],
                    "close": r["Close"], "volume": r["Volume"]})
    return out


def parse_bars(records: list[dict[str, Any]], now: datetime, market: str) -> list[list]:
    """只保留已经收盘的交易日（盘中抓到的当天那根还不是收盘价），去掉有空值的行。"""
    rows = []
    for r in records:
        day = date.fromisoformat(r["date"])
        vals = [r[c] for c in BAR_COLUMNS[1:]]
        if not session_closed(day, now, market) or any(v is None or v != v for v in vals):
            continue
        rows.append([r["date"], *(round(float(v), 4) for v in vals[:4]), int(vals[4])])
    return rows


def parse_after_hours(info: dict[str, Any], last_day: str) -> float | None:
    """盘后价只在它属于最后一个收盘日时才用。"""
    price, stamp = info.get("postMarketPrice"), info.get("postMarketTime")
    if not price or not stamp:
        return None
    day = datetime.fromtimestamp(int(stamp), MARKET_TZ["US"]).date().isoformat()
    return float(price) if day == last_day else None


def price(ctx: Context) -> Records:
    yf = _yf()
    sym = ctx.ticker
    t = yf.Ticker(sym)
    rows = parse_bars(history_records(t.history(period="2y", interval="1d", auto_adjust=False, actions=False)),
                      ctx.now, ctx.profile.market)
    if not rows:
        raise SourceError(f"yfinance 没返回 {sym} 的日线")
    from stockdesk.shared.models import Series

    url = history_url(sym)
    out = Records(series=[Series(ctx.ticker, "bars_daily", ctx.profile.price_currency, BAR_COLUMNS, rows, url,
                                 rows[-1][0], ctx.fetched_at, "fetch",
                                 f"yfinance {yf.__version__} history(auto_adjust=False)")])
    if ctx.profile.market == "US":
        try:
            ah = parse_after_hours(t.info, rows[-1][0])
        except Exception:  # noqa: BLE001  盘后价是可选的，取不到不影响日线
            ah = None
        if ah is not None:
            out.facts.append(ctx.fact("price_after_hours", rows[-1][0], ah, ctx.profile.price_currency,
                                      f"https://finance.yahoo.com/quote/{sym}/", rows[-1][0],
                                      note="yfinance postMarketPrice"))
    return out


def fx_symbol(base: str, quote: str) -> str:
    """USD→HKD 在雅虎是 HKD=X；其他货币对是 EURHKD=X 这种写法。"""
    return f"{quote}=X" if base == "USD" else f"{base}{quote}=X"


def parse_last_close(records: list[dict[str, Any]], as_of: date) -> tuple[str, float] | None:
    best = None
    for r in records:
        if r["date"] <= as_of.isoformat() and r["close"] == r["close"]:
            best = (r["date"], float(r["close"]))
    return best


def fx(ctx: Context) -> Records:
    base, quote = ctx.profile.report_currency, ctx.profile.price_currency
    if base == quote:
        return Records()
    sym = fx_symbol(base, quote)
    got = parse_last_close(history_records(_yf().Ticker(sym).history(period="1mo", interval="1d")), ctx.as_of)
    if not got:
        raise SourceError(f"yfinance 没返回 {sym} 的汇率")
    day, rate = got
    return Records(facts=[ctx.fact(f"fx.{base}{quote}", day, round(rate, 6), f"{quote}/{base}", history_url(sym),
                                   day, note="yfinance 收盘（日期按伦敦时间）")])


def _quarter_end(year: int, month: int) -> date:
    return date(year, month, cal.monthrange(year, month)[1])


def estimate_periods(today: date, next_earnings: date | None, fiscal_year_end: int) -> dict[str, str]:
    """yfinance 的 0q（本季）和 +1q（下季）各对应哪个季度。

    0q 是还没发财报的最早一个季度：最近一个已结束的季度，如果它的财报还没发（下次财报日离季末不到 75 天）；
    否则是正在进行的季度。
    """
    ends = sorted(
        _quarter_end(y, m) for y in (today.year - 1, today.year, today.year + 1)
        for m in ((fiscal_year_end - 1 + 3 * k) % 12 + 1 for k in range(4))
    )
    last = max(e for e in ends if e <= today)
    nxt = min(e for e in ends if e > today)
    if next_earnings is not None:
        unreported = next_earnings > today and (next_earnings - last).days <= 75
    else:
        unreported = (today - last).days <= 30
    q0 = last if unreported else nxt
    q1 = min(e for e in ends if e > q0)
    return {"0q": fiscal_quarter(q0, fiscal_year_end), "+1q": fiscal_quarter(q1, fiscal_year_end)}


def parse_estimates(eps: dict[str, dict[str, Any]], revenue: dict[str, dict[str, Any]], periods: dict[str, str],
                    currency: str, eps_basis: str) -> list[tuple[str, str, float, str, str]]:
    """eps / revenue 是 DataFrame.to_dict('index')：{'0q': {'avg': ..., 'numberOfAnalysts': ...}, ...}。

    返回 [(字段, 季度, 数值, 单位, 说明)]。
    """
    out = []
    for key, label in periods.items():
        e, r = eps.get(key) or {}, revenue.get(key) or {}
        if e.get("avg") == e.get("avg") and e.get("avg") is not None:
            out.append((f"cons_eps_{eps_basis}", label, float(e["avg"]), f"{currency}/share",
                        f"yfinance 分析师均值（{key}，{int(e.get('numberOfAnalysts') or 0)} 位）"))
        if r.get("avg") == r.get("avg") and r.get("avg") is not None:
            out.append(("cons_revenue", label, float(r["avg"]), currency,
                        f"yfinance 分析师均值（{key}，{int(r.get('numberOfAnalysts') or 0)} 位）"))
    return out


def _next_earnings(cal_info: Any, today: date) -> date | None:
    days = (cal_info or {}).get("Earnings Date") or []
    future = [d for d in days if isinstance(d, date) and d >= today]
    return min(future) if future else None


def consensus(ctx: Context) -> Records:
    t = _yf().Ticker(ctx.ticker)
    eps_df, rev_df = t.earnings_estimate, t.revenue_estimate
    if eps_df is None or getattr(eps_df, "empty", True):
        raise SourceError(f"yfinance 没有 {ctx.ticker} 的一致预期")
    try:
        currency = t.info.get("financialCurrency") or ctx.profile.report_currency
    except Exception:  # noqa: BLE001
        currency = ctx.profile.report_currency
    today = ctx.now.astimezone(MARKET_TZ[ctx.profile.market]).date()
    nxt = _next_earnings(t.calendar, today)
    periods = estimate_periods(today, nxt, ctx.profile.fiscal_year_end)
    rows = parse_estimates(eps_df.to_dict("index"), rev_df.to_dict("index") if rev_df is not None else {},
                           periods, currency, ctx.profile.eps_basis)
    url = f"https://finance.yahoo.com/quote/{ctx.ticker}/analysis/"
    day = ctx.as_of.isoformat()
    tail = f"；下次财报 {nxt}" if nxt else ""
    return Records(facts=[ctx.fact(name, label, value, unit, url, day, note=note + tail)
                          for name, label, value, unit, note in rows])


MACRO = {"^VIX": ("macro.vix", "index", 1.0), "^TNX": ("macro.us10y", "ratio", 0.01)}


def macro(ctx: Context) -> Records:
    yf = _yf()
    out = Records()
    for sym, (name, unit, scale) in MACRO.items():
        rows = parse_bars(history_records(yf.Ticker(sym).history(period="1mo", interval="1d")), ctx.now, "US")
        if rows:
            day, close = rows[-1][0], rows[-1][4]
            out.facts.append(ctx.fact(name, day, round(close * scale, 6), unit, history_url(sym), day,
                                      note=f"yfinance {sym} 收盘"))
    return out
