"""[AT-3] INTC 三档买点回放：三档、右侧、失效位；锚点可追溯；与人工版本对照。"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from stockdesk.shared.calendar import is_trading_day

from conftest import CASES, compare_with_manual, run_cli

CASE = CASES / "intc-q3-2026"
ARGS = ("zones", "INTC", "--replay", "intc-q3-2026", "--eps", "1.75", "--pe", "38-45", "--json")


@pytest.fixture(scope="module")
def plan():
    res = run_cli(*ARGS)
    assert res.code == 0, res.stdout + res.stderr
    return res.json()


def numbers(obj) -> list[float]:
    """把 TECH / VAL 输出里的所有数值摊平，用来核对锚点。"""
    if isinstance(obj, bool):
        return []
    if isinstance(obj, (int, float)):
        return [float(obj)]
    if isinstance(obj, dict):
        return [x for v in obj.values() for x in numbers(v)]
    if isinstance(obj, list):
        return [x for v in obj for x in numbers(v)]
    return []


def test_three_tiers_strictly_below_price(plan):
    tiers = plan["tiers"]
    assert [t["name"] for t in tiers] == ["A", "B", "C"]
    last_close = plan["reference"]["close"]
    assert last_close == pytest.approx(92.07)
    for upper, lower in zip(tiers, tiers[1:], strict=False):
        assert upper["low"] > lower["high"], "三档必须严格递减、不重叠"
    for t in tiers:
        assert t["low"] < t["high"] < last_close
    total = sum(t["size"] for t in tiers) + plan.get("reserved", {}).get("size", 0)
    assert total == pytest.approx(1.0)


def test_right_side_and_invalidation(plan):
    assert plan["right_side"]["level"] == pytest.approx(92.07), "右侧：周收盘站回财报前收盘价"
    assert plan["invalidation"]["level"] < plan["tiers"][-1]["low"]
    assert "周收盘" in plan["invalidation"]["condition"]


def test_every_anchor_comes_from_tech_or_valuation(plan):
    pool = {"TECH": numbers(plan["tech"]), "VAL": numbers(plan["valuation"])}
    for t in plan["tiers"] + [plan["right_side"]]:
        anchor = t["anchor"]
        assert anchor["module"] in pool
        assert any(abs(anchor["value"] - x) < 1e-9 for x in pool[anchor["module"]]), anchor


def test_tech_levels_from_daily_bars(plan):
    tech = plan["tech"]
    assert tech["last_close"]["date"] == "2026-10-29"
    assert tech["ma50"] > tech["ma200"] > 0
    assert tech["high_52w"]["value"] == pytest.approx(142.35)
    assert tech["drawdowns"]["0.45"] == pytest.approx(142.35 * 0.55, rel=1e-6)
    for s in tech["supports"]:
        assert len(s["touches"]) >= 3, "多次测试的支撑：至少 3 次"


def test_close_to_manual_version(plan):
    manual = json.loads((CASE / "manual-zones.json").read_text(encoding="utf-8"))
    problems = compare_with_manual(plan, manual)
    for p in problems:
        print("差异：", p)
    assert not problems, "与人工版本偏差超过 5%，需要你判断：\n" + "\n".join(problems)


def test_us_calendar_matches_bars():
    """美股日历与日线一致：有日线的日子都是交易日，没日线的工作日都是休市日。"""
    rows = json.loads((CASE / "snapshots" / "INTC" / "2026-10-29-bars.json").read_text())["rows"]
    have = {r[0] for r in rows}
    day, end = date.fromisoformat(rows[0][0]), date.fromisoformat(rows[-1][0])
    while day <= end:
        if day.weekday() < 5:
            assert is_trading_day(day, "US") == (day.isoformat() in have), day
        day += timedelta(days=1)


def test_human_output_reads_well():
    res = run_cli(*ARGS[:-1])
    assert res.code == 0, res.stderr
    assert "不构成投资建议" in res.stdout
    for word in ("A 档", "B 档", "C 档", "右侧", "失效位"):
        assert word in res.stdout

