"""[AT-10] Mac 实时取数（联网，只在 Mac 上手动跑：make live）。

INTC：价格、财报、一致预期、宏观四类齐全；0992：价格、披露易最近一份业绩公告、美元兑港元汇率齐全。
每个字段带来源；价格日期是各自市场最近一个收盘的交易日；和 stockanalysis 网页上的收盘价差异小于 1%。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from stockdesk.shared.calendar import last_closed_session

from conftest import ROOT

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def ws(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("live")
    shutil.copytree(ROOT / "config", path / "config")
    if (ROOT / ".env").exists():
        shutil.copy(ROOT / ".env", path / ".env")
    return path


def sd(ws: Path, *args: str) -> dict:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "STOCKDESK_DATA": str(ws / "data")}
    proc = subprocess.run([sys.executable, "-m", "stockdesk", *args, "--json"], cwd=ws, env=env,
                          capture_output=True, text=True, timeout=600)
    out = json.loads(proc.stdout)
    assert proc.returncode == 0, json.dumps(out, ensure_ascii=False, indent=1)[:3000]
    return out


def records(result: dict) -> list[dict]:
    facts, series = [], []
    for f in result["files"]:
        raw = json.loads(Path(f).read_text(encoding="utf-8"))
        (series.append(raw) if isinstance(raw, dict) else facts.extend(raw))
    return facts + series


def kinds_with_data(result: dict) -> set[str]:
    return {k for k, got in result["coverage"].items() if got}


def latest_bar(result: dict) -> list:
    bars = [r for r in records(result) if r.get("field") == "bars_daily"]
    assert bars, "没取到日线"
    return bars[0]["rows"][-1]


def check_sources(result: dict) -> None:
    for r in records(result):
        assert r["source_url"].startswith("https://"), r
        assert r["as_of"] and r["fetched_at"], r


def check_vs_stockanalysis(result: dict) -> None:
    sa = {r["period"]: r["value"] for r in records(result)
          if r.get("field") == "price_close" and "stockanalysis.com" in r["source_url"]}
    bars = next(r for r in records(result) if r.get("field") == "bars_daily")
    common = sorted(set(sa) & {row[0] for row in bars["rows"]})
    assert common, f"stockanalysis 和雅虎没有共同日期：{sorted(sa)[-3:]}"
    day = common[-1]
    close = next(row[4] for row in bars["rows"] if row[0] == day)
    assert abs(close / sa[day] - 1) < 0.01, (day, close, sa[day])


def test_doctor_on_mac(ws):
    prof = sd(ws, "doctor")
    assert prof["environment"] == "mac"
    assert prof["can_fetch"], prof["advice"]


def test_fetch_intc(ws):
    result = sd(ws, "fetch", "INTC")
    assert {"price", "fundamentals", "consensus", "macro"} <= kinds_with_data(result), result["failures"]
    check_sources(result)
    want = last_closed_session(datetime.now(UTC), "US").isoformat()
    assert latest_bar(result)[0] == want
    check_vs_stockanalysis(result)


def test_fetch_lenovo(ws):
    result = sd(ws, "fetch", "0992.HK")
    assert {"price", "filing", "fx"} <= kinds_with_data(result), result["failures"]
    check_sources(result)
    want = last_closed_session(datetime.now(UTC), "HK").isoformat()
    assert latest_bar(result)[0] == want
    filings = next(r for r in records(result) if r.get("field") == "filings")
    assert "hkexnews.hk" in filings["rows"][-1][3]
    check_vs_stockanalysis(result)
