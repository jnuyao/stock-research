"""[DATA] AKShare：港股日线（新浪），作为港股价格的第三来源。可选安装，只在 Mac 上用。"""

from __future__ import annotations

from datetime import date

from .base import Context, Records, SourceError

KEEP_DAYS = 10


def _ak():
    try:
        import akshare as ak
    except ImportError as err:
        raise SourceError("没装 akshare：需要时在 Mac 上运行 pip install -e '.[mac]'") from err
    return ak


def page_url(code: str) -> str:
    return f"https://stock.finance.sina.com.cn/hkstock/quotes/{code}.html"


def parse_daily(records: list[dict], as_of: date) -> list[tuple[str, float]]:
    """records 是 DataFrame.to_dict('records')：每行有 date 和 close。返回 as_of 及以前最近几天，新的在前。"""
    rows = []
    for r in records:
        d = r["date"]
        day = d.isoformat()[:10] if hasattr(d, "isoformat") else str(d)[:10]
        if day <= as_of.isoformat():
            rows.append((day, float(r["close"])))
    rows.sort(reverse=True)
    return rows[:KEEP_DAYS]


def price(ctx: Context) -> Records:
    code = ctx.ticker.split(".")[0].zfill(5)
    df = _ak().stock_hk_daily(symbol=code, adjust="")
    rows = parse_daily(df.to_dict("records"), ctx.as_of)
    if not rows:
        raise SourceError(f"AKShare 没返回 {code} 的日线")
    url = page_url(code)
    return Records(facts=[ctx.fact("price_close", d, c, ctx.profile.price_currency, url, d,
                                   note="AKShare stock_hk_daily（新浪）") for d, c in rows])
