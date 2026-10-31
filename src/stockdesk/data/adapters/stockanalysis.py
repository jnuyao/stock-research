"""[DATA] stockanalysis.com 历史价格页：第二来源，取最近几天的收盘价和雅虎日线互相核对。"""

from __future__ import annotations

import html
import re
from datetime import datetime

from stockdesk.shared.calendar import market_of

from .base import Context, Records, SourceError, http_get

KEEP_DAYS = 10


def page_url(ticker: str) -> str:
    if market_of(ticker) == "HK":
        return f"https://stockanalysis.com/quote/hkg/{ticker.split('.')[0].zfill(4)}/history/"
    return f"https://stockanalysis.com/stocks/{ticker.lower()}/history/"


def parse_history(text: str) -> list[tuple[str, float]]:
    """从页面的历史价格表里取 (日期, 收盘价)，新的在前。表头是 Date Open High Low Close ..."""
    body = re.search(r"<tbody[^>]*>(.*?)</tbody>", text, re.S)
    if not body:
        return []
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body.group(1), re.S):
        raw = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in raw]
        if len(cells) < 5:
            continue
        try:
            day = datetime.strptime(cells[0], "%b %d, %Y").date().isoformat()
            close = float(cells[4].replace(",", ""))
        except ValueError:
            continue
        out.append((day, close))
    return out


def price(ctx: Context) -> Records:
    url = page_url(ctx.ticker)
    rows = parse_history(http_get(url).text)
    rows = [(d, c) for d, c in rows if d <= ctx.as_of.isoformat()][:KEEP_DAYS]
    if not rows:
        raise SourceError(f"{url} 里没找到价格表（页面可能改版了）")
    unit = ctx.profile.price_currency
    return Records(facts=[ctx.fact("price_close", d, c, unit, url, d, note="stockanalysis 历史价格页")
                          for d, c in rows])
