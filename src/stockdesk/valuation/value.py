"""[VAL] 估值。只算数，不做判断；数据经 [QA] 取得。

EPS 的货币与股价货币不同（联想财报是美元、股价是港元）时，先按估值日汇率换算，
并在输出里写明汇率、日期和来源；取不到汇率就返回 FX_MISSING（INV-13）。
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from statistics import median
from typing import Any

from stockdesk.qa import Need, require
from stockdesk.shared.calendar import last_trading_day
from stockdesk.shared.errors import ErrorCode, StockdeskError

HISTORY_YEARS = 3
MIN_HISTORY_POINTS = 3


def _quantile(values: list[float], q: float) -> float:
    xs = sorted(values)
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def _fx(ds, pair: str, as_of: str, market: str) -> dict[str, Any]:
    """取估值日（as_of 当天或之前最近一个交易日）的汇率，不拿更早的汇率凑数。"""
    day = last_trading_day(date.fromisoformat(as_of), market).isoformat()
    cands = [f for (n, p), f in ds.facts.items()
             if n == f"fx.{pair}" and f.value is not None and day <= p <= as_of]
    if not cands:
        raise StockdeskError(
            ErrorCode.FX_MISSING,
            f"股价和 EPS 的货币不同，需要 {day} 的 {pair} 汇率，快照里没有；请补抓当日汇率",
            {"pair": pair, "as_of": as_of, "required": day},
        )
    f = max(cands, key=lambda x: x.period)
    return {"pair": pair, "rate": f.value, "date": f.period, "source_url": f.source_url, "note": f.note}


def value(
    ticker: str,
    as_of: str,
    eps_fwd: float,
    pe_range: tuple[float, float],
    root: Path,
    market: str = "US",
    price_currency: str = "USD",
    report_currency: str = "USD",
    eps_currency: str | None = None,
) -> dict[str, Any]:
    eps_currency = eps_currency or price_currency
    if eps_fwd <= 0:
        raise StockdeskError(ErrorCode.BAD_INPUT, "前瞻 EPS 必须是正数，亏损公司不适用市盈率法")
    pe_lo, pe_hi = pe_range
    if not 0 < pe_lo < pe_hi:
        raise StockdeskError(ErrorCode.BAD_INPUT, f"市盈率区间要写成 低-高，例如 38-45，收到 {pe_lo}-{pe_hi}")

    pair = f"{report_currency}{price_currency}"
    needs = [
        Need("pe_fwd", None),
        Need("peer_pe", None, critical=False, ack=True, prefix=True),
        Need(f"fx.{pair}", None, critical=False),
    ]
    ds = require(ticker, needs, root=root, as_of=as_of, market=market)

    fx = None
    if report_currency != price_currency or eps_currency != price_currency:
        fx = _fx(ds, pair, as_of, market)
    if eps_currency == price_currency:
        eps_p = eps_fwd
    elif fx and eps_currency == report_currency:
        eps_p = eps_fwd * fx["rate"]
    else:
        raise StockdeskError(ErrorCode.BAD_INPUT, f"EPS 货币 {eps_currency} 既不是股价货币也不是财报货币")

    start = (date.fromisoformat(as_of) - timedelta(days=365 * HISTORY_YEARS)).isoformat()
    points = sorted(
        ({"date": p, "pe": f.value, "source_url": f.source_url}
         for (n, p), f in ds.facts.items() if n == "pe_fwd" and f.value is not None and start <= p <= as_of),
        key=lambda x: x["date"],
    )
    if len(points) < MIN_HISTORY_POINTS:
        raise StockdeskError(
            ErrorCode.DATA_INCOMPLETE,
            f"近 3 年市盈率只有 {len(points)} 个点，至少要 {MIN_HISTORY_POINTS} 个",
            {"gaps": [{"field": "pe_fwd", "period": f"{start}~{as_of}", "label": "历史前瞻市盈率", "critical": True,
                       "where": "stockanalysis 的 financials/ratios 页（Forward PE 一行）",
                       "reason": f"只有 {len(points)} 个点"}]},
        )
    pes = [x["pe"] for x in points]
    hist = {
        "basis": "forward",
        "window": [start, as_of],
        "points": points,
        "count": len(pes),
        "min": min(pes),
        "p25": round(_quantile(pes, 0.25), 4),
        "median": round(median(pes), 4),
        "max": max(pes),
    }

    peer_facts = ds.by_prefix("peer_pe")
    peers = {
        "values": [{"name": f.field.removeprefix("peer_pe."), "pe": f.value, "as_of": f.as_of,
                    "source_url": f.source_url} for f in peer_facts],
        "missing": not peer_facts,
        "reason": ds.acks.get("peer_pe"),
    }
    peers["median"] = round(median(p["pe"] for p in peers["values"]), 4) if peer_facts else None

    return {
        "currency": price_currency,
        "eps_input": eps_fwd,
        "eps_currency": eps_currency,
        "eps_in_price_currency": eps_p,
        "pe_range": [pe_lo, pe_hi],
        "fair": {"low": eps_p * pe_lo, "mid": eps_p * (pe_lo + pe_hi) / 2, "high": eps_p * pe_hi},
        "history": hist,
        "crisis_price": eps_p * hist["min"],
        "peers": peers,
        "fx": fx,
    }
