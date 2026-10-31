"""[DATA] 港交所披露易：找最近一份业绩公告（年度、中期、季度业绩）的链接。

港股的财报数字以业绩公告为准；公告是 PDF，数字由 Claude 读原文后 `sd import`（第一版不解析 PDF）。
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from typing import Any

from stockdesk.shared.models import Series

from .base import Context, Records, SourceError, http_get

BASE = "https://www1.hkexnews.hk"
PREFIX_URL = f"{BASE}/search/prefix.do"
SEARCH_URL = f"{BASE}/search/titleSearchServlet.do"
RESULTS_RE = re.compile(r"\[(Final|Interim|Quarterly) Results\]|業績|Results Announcement", re.I)


def parse_stock_id(text: str, code: str) -> int:
    """prefix.do 返回 callback({...}); 这样的 JSONP。"""
    m = re.search(r"\((\{.*\})\)", text, re.S)
    if not m:
        raise SourceError("披露易的代码查询返回格式变了")
    for s in json.loads(m.group(1)).get("stockInfo", []):
        if s.get("code") == code:
            return int(s["stockId"])
    raise SourceError(f"披露易没找到股票代码 {code}")


def parse_results(payload: dict[str, Any]) -> list[list[str]]:
    """标题检索结果里挑出业绩公告：[[日期, 类别, 标题, 链接]]，新的在前。"""
    items = payload.get("result") or "[]"
    items = json.loads(items) if isinstance(items, str) else items
    out = []
    for it in items:
        kind = it.get("LONG_TEXT", "")
        title = it.get("TITLE", "")
        if not (RESULTS_RE.search(kind) or RESULTS_RE.search(title)):
            continue
        day = datetime.strptime(it["DATE_TIME"][:10], "%d/%m/%Y").date().isoformat()
        out.append([day, kind.strip(), title.strip(), BASE + it["FILE_LINK"]])
    out.sort(key=lambda r: r[0], reverse=True)
    return out


def filings(ctx: Context) -> Records:
    code = ctx.ticker.split(".")[0].zfill(5)
    stock_id = parse_stock_id(
        http_get(PREFIX_URL, params={"callback": "callback", "lang": "EN", "type": "A", "name": code,
                                     "market": "SEHK"}).text, code)
    start = ctx.as_of - timedelta(days=200)
    payload = http_get(SEARCH_URL, params={
        "sortDir": 0, "sortByOptions": "DateTime", "category": 0, "market": "SEHK", "stockId": stock_id,
        "documentType": -1, "fromDate": f"{start:%Y%m%d}", "toDate": f"{ctx.as_of:%Y%m%d}", "title": "",
        "searchType": 0, "t1code": -2, "t2Gcode": -2, "t2code": -2, "rowRange": 200, "lang": "E",
    }).json()
    rows = [r for r in parse_results(payload) if r[0] <= ctx.as_of.isoformat()][:3]
    if not rows:
        raise SourceError(f"披露易近 200 天没有 {code} 的业绩公告")
    rows.sort(key=lambda r: r[0])
    return Records(series=[Series(ctx.ticker, "filings", "text", ["date", "form", "title", "url"], rows,
                                  f"{BASE}/search/titlesearch.xhtml", date.isoformat(ctx.as_of), ctx.fetched_at,
                                  "fetch", "披露易标题检索：业绩公告")])
