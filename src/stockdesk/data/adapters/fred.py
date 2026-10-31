"""[DATA] FRED：10 年期美债收益率、VIX、高收益债信用利差（免费，不要密钥）。"""

from __future__ import annotations

import csv
import io
from datetime import timedelta

from .base import Context, Records, http_get

# FRED 序列 → (字段, 单位, 换算)
SERIES = {
    "DGS10": ("macro.us10y", "ratio", 0.01),         # 百分数 → 小数
    "VIXCLS": ("macro.vix", "index", 1.0),
    "BAMLH0A0HYM2": ("macro.hy_spread", "ratio", 0.01),
}


def csv_url(series_id: str) -> str:
    return f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"


def page_url(series_id: str) -> str:
    return f"https://fred.stlouisfed.org/series/{series_id}"


def parse_csv(text: str, as_of: str) -> tuple[str, float] | None:
    """返回 as_of 及以前最近一个有值的 (日期, 数值)；FRED 用 '.' 或空表示当天没有数。"""
    rows = list(csv.reader(io.StringIO(text)))
    best = None
    for r in rows[1:]:
        if len(r) < 2 or not r[1].strip() or r[1].strip() == ".":
            continue
        if r[0] <= as_of:
            best = (r[0], float(r[1]))
    return best


def macro(ctx: Context) -> Records:
    out = Records()
    start = (ctx.as_of - timedelta(days=30)).isoformat()
    for sid, (name, unit, scale) in SERIES.items():
        text = http_get(csv_url(sid), params={"cosd": start}).text
        got = parse_csv(text, ctx.as_of.isoformat())
        if got:
            day, value = got
            out.facts.append(ctx.fact(name, day, round(value * scale, 6), unit, page_url(sid), day,
                                      note=f"FRED {sid}"))
    return out
