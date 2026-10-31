"""[DATA] SEC EDGAR：美股财报数字的标准来源（免费）。

- fundamentals：XBRL companyfacts 里最近几个季度的营收、GAAP EPS、毛利、营业利润、净利润（取自 10-Q/10-K）。
- filing：最近一份业绩 8-K（Item 2.02）的新闻稿附件 Ex-99.1，以及最近的 10-Q/10-K 链接，给 Claude 读原文。

SEC 要求请求头写联系方式：环境变量 STOCKDESK_SEC_CONTACT（“姓名 邮箱”），只放进请求头，不打印、不记录。
发财报当天 10-Q 还没出，新季度的数字要由 Claude 读 Ex-99.1 后 `sd import`。
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from stockdesk.shared.calendar import fiscal_quarter
from stockdesk.shared.models import Series

from .base import Context, Records, SourceError, http_get

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
QUARTERS = 6

# 字段 → 依次尝试的 us-gaap 标签（公司用的标签不同，取最新数据的那个）
CONCEPTS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"],
    "eps_gaap": ["EarningsPerShareDiluted"],
    "gross_profit": ["GrossProfit"],
    "op_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss"],
}
EX99_RE = re.compile(r"ex-?99[._-]?0?1|ex991|dex991", re.I)


def _headers(ctx: Context) -> dict[str, str]:
    if not ctx.sec_contact:
        raise SourceError("SEC 要求请求头带联系方式：请在环境变量 STOCKDESK_SEC_CONTACT 里写“姓名 邮箱”")
    return {"User-Agent": f"stockdesk/0.1 {ctx.sec_contact}"}


def find_cik(tickers: dict[str, dict[str, Any]], ticker: str) -> int:
    for row in tickers.values():
        if row.get("ticker", "").upper() == ticker.upper():
            return int(row["cik_str"])
    raise SourceError(f"SEC 的代码表里没有 {ticker}")


def filing_url(cik: int, accession: str, doc: str = "") -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{doc}"


def _quarterly(entries: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """只要 10-Q/10-K 里约一个季度长度（80–100 天）的数；同一期间以最后申报的为准。"""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for e in entries:
        if not e.get("start") or e.get("form") not in ("10-Q", "10-K", "10-Q/A", "10-K/A"):
            continue
        days = (date.fromisoformat(e["end"]) - date.fromisoformat(e["start"])).days
        if not 80 <= days <= 100:
            continue
        key = (e["start"], e["end"])
        if key not in out or e["filed"] > out[key]["filed"]:
            out[key] = e
    return out


def parse_companyfacts(data: dict[str, Any], cik: int, fiscal_year_end: int, as_of: date,
                       quarters: int = QUARTERS) -> list[tuple[str, str, float, str, str, str, str]]:
    """返回 [(字段, 季度, 数值, 单位, 来源网址, 季末日期, 说明)]，只含 as_of 以前申报的最近几个季度。"""
    gaap = data.get("facts", {}).get("us-gaap", {})
    picked: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
    for name, tags in CONCEPTS.items():
        best: dict[tuple[str, str], dict[str, Any]] = {}
        for tag in tags:
            units = gaap.get(tag, {}).get("units", {})
            entries = units.get("USD/shares" if name == "eps_gaap" else "USD", [])
            q = {k: v for k, v in _quarterly(entries).items() if v["filed"] <= as_of.isoformat()}
            if q and (not best or max(k[1] for k in q) > max(k[1] for k in best)):
                best = q
        picked[name] = best

    ends = sorted({k[1] for k in picked["revenue"]}, reverse=True)[:quarters]
    out = []
    for end in ends:
        label = fiscal_quarter(date.fromisoformat(end), fiscal_year_end)
        row = {name: next((e for (s, e_end), e in picked[name].items() if e_end == end), None) for name in picked}
        for name in ("revenue", "eps_gaap", "op_income", "net_income"):
            e = row[name]
            if e:
                unit = "USD/share" if name == "eps_gaap" else "USD"
                out.append((name, label, float(e["val"]), unit, filing_url(cik, e["accn"]), end,
                            f"SEC XBRL {e['form']}（{e['filed']} 申报）"))
        rev, gp = row["revenue"], row["gross_profit"]
        if rev and gp and rev["val"]:
            out.append(("gross_margin_gaap", label, round(gp["val"] / rev["val"], 6), "ratio",
                        filing_url(cik, gp["accn"]), end, "由 SEC XBRL 的毛利和营收计算"))
    return out


def parse_filings(sub: dict[str, Any], cik: int, as_of: date) -> dict[str, Any]:
    """从 submissions 里找最近一份业绩 8-K（Item 2.02）和最近的 10-Q/10-K。"""
    recent = sub.get("filings", {}).get("recent", {})
    rows = [dict(zip(recent.keys(), vals, strict=False)) for vals in zip(*recent.values(), strict=False)]
    rows = [r for r in rows if r.get("filingDate", "") <= as_of.isoformat()]
    rows.sort(key=lambda r: r["filingDate"], reverse=True)
    earnings = next((r for r in rows if r.get("form") == "8-K" and "2.02" in (r.get("items") or "")), None)
    periodic = next((r for r in rows if r.get("form") in ("10-Q", "10-K")), None)
    return {"earnings_8k": earnings, "periodic": periodic}


def pick_ex99(index: dict[str, Any]) -> str | None:
    names = [i["name"] for i in index.get("directory", {}).get("item", [])]
    hits = [n for n in names if EX99_RE.search(n) and n.lower().endswith((".htm", ".html"))]
    return hits[0] if hits else None


def _cik(ctx: Context) -> int:
    return find_cik(http_get(TICKERS_URL, headers=_headers(ctx)).json(), ctx.ticker)


def fundamentals(ctx: Context) -> Records:
    cik = _cik(ctx)
    data = http_get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json", headers=_headers(ctx)).json()
    rows = parse_companyfacts(data, cik, ctx.profile.fiscal_year_end, ctx.as_of)
    if not rows:
        raise SourceError(f"SEC XBRL 里没找到 {ctx.ticker} 的季度营收")
    return Records(facts=[ctx.fact(n, label, v, unit, url, end, note=note)
                          for n, label, v, unit, url, end, note in rows])


def filings(ctx: Context) -> Records:
    cik = _cik(ctx)
    sub = http_get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=_headers(ctx)).json()
    found = parse_filings(sub, cik, ctx.as_of)
    rows = []
    e8k = found["earnings_8k"]
    if e8k:
        index = http_get(filing_url(cik, e8k["accessionNumber"], "index.json"), headers=_headers(ctx)).json()
        doc = pick_ex99(index)
        url = filing_url(cik, e8k["accessionNumber"], doc or e8k["primaryDocument"])
        rows.append([e8k["filingDate"], "8-K 2.02", "业绩新闻稿 Ex-99.1" if doc else "业绩 8-K 正文", url])
    p = found["periodic"]
    if p:
        rows.append([p["filingDate"], p["form"], f"{p['form']}（截至 {p.get('reportDate', '')}）",
                     filing_url(cik, p["accessionNumber"], p["primaryDocument"])])
    if not rows:
        raise SourceError(f"SEC 里没找到 {ctx.ticker} 最近的业绩 8-K 或 10-Q")
    rows.sort(key=lambda r: r[0])
    return Records(series=[Series(ctx.ticker, "filings", "text", ["date", "form", "title", "url"], rows,
                                  f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}",
                                  ctx.as_of.isoformat(), ctx.fetched_at, "fetch", "SEC submissions")])
