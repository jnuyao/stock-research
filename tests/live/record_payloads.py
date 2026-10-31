"""在 Mac 上录一份各来源的原始返回，存进 tests/cases/fetch-payloads/，给离线测试解析代码用。

用法（项目根目录）：.venv/bin/python tests/live/record_payloads.py
只保留解析要用到的部分（例如 SEC companyfacts 只留几个标签），文件不会太大。
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stockdesk.data.adapters import akshare_hk, fred, hkex, sec, stockanalysis, yahoo  # noqa: E402
from stockdesk.data.adapters.base import http_get  # noqa: E402
from stockdesk.data.doctor import sec_contact  # noqa: E402

OUT = ROOT / "tests" / "cases" / "fetch-payloads"


def save(name: str, payload) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print("saved", path.relative_to(ROOT), path.stat().st_size, "bytes")


def step(name, fn) -> None:
    try:
        fn()
    except Exception as err:  # noqa: BLE001
        print(f"FAILED {name}: {type(err).__name__}: {err}")


def stockanalysis_pages() -> None:
    import re

    for t in ("INTC", "0992.HK"):
        text = http_get(stockanalysis.page_url(t)).text
        body = re.search(r"<tbody[^>]*>.*?</tbody>", text, re.S)
        save(f"stockanalysis-{t}-history.html", f"<table>{body.group(0) if body else ''}</table>\n")


def sec_payloads() -> None:
    contact = sec_contact()
    if not contact:
        raise RuntimeError("没设置 STOCKDESK_SEC_CONTACT")
    h = {"User-Agent": f"stockdesk/0.1 {contact}"}
    tickers = http_get(sec.TICKERS_URL, headers=h).json()
    cik = sec.find_cik(tickers, "INTC")
    facts = http_get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json", headers=h).json()
    keep = {t for tags in sec.CONCEPTS.values() for t in tags}
    gaap = {k: v for k, v in facts["facts"]["us-gaap"].items() if k in keep}
    cutoff = (date.today() - timedelta(days=800)).isoformat()
    for v in gaap.values():
        for unit, entries in v["units"].items():
            v["units"][unit] = [e for e in entries if e.get("end", "") >= cutoff]
    save("sec-INTC-companyfacts.json", {"cik": cik, "entityName": facts.get("entityName"), "facts": {"us-gaap": gaap}})
    sub = http_get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=h).json()
    recent = {k: v[:60] for k, v in sub["filings"]["recent"].items()}
    save("sec-INTC-submissions.json", {"cik": cik, "filings": {"recent": recent}})
    found = sec.parse_filings({"filings": {"recent": recent}}, cik, date.today())
    if found["earnings_8k"]:
        acc = found["earnings_8k"]["accessionNumber"]
        save("sec-INTC-8k-index.json", http_get(sec.filing_url(cik, acc, "index.json"), headers=h).json())


def hkex_payloads() -> None:
    code = "00992"
    text = http_get(hkex.PREFIX_URL, params={"callback": "callback", "lang": "EN", "type": "A", "name": code,
                                             "market": "SEHK"}).text
    save("hkex-00992-prefix.txt", text)
    stock_id = hkex.parse_stock_id(text, code)
    today = date.today()
    payload = http_get(hkex.SEARCH_URL, params={
        "sortDir": 0, "sortByOptions": "DateTime", "category": 0, "market": "SEHK", "stockId": stock_id,
        "documentType": -1, "fromDate": f"{today - timedelta(days=200):%Y%m%d}", "toDate": f"{today:%Y%m%d}",
        "title": "", "searchType": 0, "t1code": -2, "t2Gcode": -2, "t2code": -2, "rowRange": 200, "lang": "E",
    }).json()
    save("hkex-00992-search.json", payload)


def fred_payloads() -> None:
    start = (date.today() - timedelta(days=30)).isoformat()
    for sid in fred.SERIES:
        save(f"fred-{sid}.csv", http_get(fred.csv_url(sid), params={"cosd": start}).text)


def yahoo_payloads() -> None:
    yf = yahoo._yf()  # noqa: SLF001
    for t in ("INTC", "0992.HK"):
        tk = yf.Ticker(t)
        hist = yahoo.history_records(tk.history(period="1mo", interval="1d", auto_adjust=False, actions=False))
        save(f"yahoo-{t}-history.json", hist)
        info = tk.info
        save(f"yahoo-{t}-info.json", {k: info.get(k) for k in (
            "currency", "financialCurrency", "postMarketPrice", "postMarketTime", "regularMarketPrice",
            "regularMarketTime", "forwardPE")})
        ee, re_ = tk.earnings_estimate, tk.revenue_estimate
        save(f"yahoo-{t}-estimates.json", {
            "eps": ee.to_dict("index") if ee is not None else {},
            "revenue": re_.to_dict("index") if re_ is not None else {},
            "calendar": tk.calendar,
        })
    for sym in ("HKD=X", "^VIX", "^TNX"):
        save(f"yahoo-{sym.replace('^', '').replace('=', '_')}-history.json",
             yahoo.history_records(yf.Ticker(sym).history(period="1mo", interval="1d")))


def akshare_payloads() -> None:
    ak = akshare_hk._ak()  # noqa: SLF001
    df = ak.stock_hk_daily(symbol="00992", adjust="")
    save("akshare-00992-daily.json", df.tail(30).to_dict("records"))


if __name__ == "__main__":
    print("recording at", datetime.now(UTC).isoformat())
    for name, fn in [("stockanalysis", stockanalysis_pages), ("sec", sec_payloads), ("hkex", hkex_payloads),
                     ("fred", fred_payloads), ("yahoo", yahoo_payloads), ("akshare", akshare_payloads)]:
        step(name, fn)
