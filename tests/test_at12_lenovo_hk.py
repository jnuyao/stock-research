"""[AT-12] 联想 0992 港股回放：美元财报配港元股价要换汇率，按香港交易日历取周收盘。"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from stockdesk.shared.calendar import is_trading_day

from conftest import CASES, compare_with_manual, edit_json, make_variant, run_cli

CASE_NAME = "lenovo-2026-10-29"
CASE = CASES / CASE_NAME
TICKER = "0992.HK"


@pytest.fixture(scope="module")
def pack():
    res = run_cli("pack", TICKER, "--quarter", "FY2027Q1", "--replay", CASE_NAME, "--json")
    assert res.code == 0, res.stdout + res.stderr
    return {it["key"]: it for it in res.json()["items"]}


@pytest.fixture(scope="module")
def plan():
    res = run_cli("zones", TICKER, "--replay", CASE_NAME, "--eps", "2.7", "--pe", "8-11", "--json")
    assert res.code == 0, res.stdout + res.stderr
    return res.json()


def test_results_from_hkex(pack):
    assert pack["revenue"]["value"] == pytest.approx(26.9e9, abs=0.05e9)
    assert pack["revenue_yoy"]["value"] == pytest.approx(0.43, abs=0.005)
    assert pack["adj_net_income"]["value"] == pytest.approx(1.075e9, abs=0.001e9)
    for key in ("revenue", "adj_net_income", "eps_gaap", "gross_margin_gaap"):
        assert "hkexnews.hk" in pack[key]["sources"][0]["url"], key


def test_no_guidance_is_fine_for_hk(pack):
    assert not any(k.startswith("guide_") for k in pack)
    assert pack["cons_revenue"]["missing"] is True
    assert pack["cons_revenue"]["gap_ack"]


def test_price_in_hkd(pack):
    assert pack["price_close"]["value"] == pytest.approx(23.78)
    assert pack["price_close"]["unit"] == "HKD"


def test_valuation_states_fx(plan):
    fx = plan["valuation"]["fx"]
    assert fx["pair"] == "USDHKD"
    assert fx["rate"] == pytest.approx(7.8444)
    assert fx["date"] == "2026-10-28"
    assert fx["source_url"].startswith("https://")


def test_eps_in_usd_is_converted():
    res = run_cli("zones", TICKER, "--replay", CASE_NAME, "--eps", "0.3442", "--eps-currency", "USD",
                  "--pe", "8-11", "--json")
    assert res.code == 0, res.stdout + res.stderr
    val = res.json()["valuation"]
    assert val["eps_in_price_currency"] == pytest.approx(0.3442 * 7.8444, rel=1e-9)
    assert val["fair"]["low"] == pytest.approx(0.3442 * 7.8444 * 8, rel=1e-9)


def test_fx_missing_is_refused(cli, tmp_path):
    cwd = make_variant(tmp_path, CASE_NAME, "lenovo-no-fx",
                       lambda case: case.joinpath("snapshots", TICKER, "2026-10-28-fx.json").unlink())
    res = cli("zones", TICKER, "--replay", "lenovo-no-fx", "--eps", "2.7", "--pe", "8-11", "--json", cwd=cwd)
    assert res.code != 0
    assert res.json()["error"]["code"] == "FX_MISSING"


def test_old_fx_is_refused(cli, tmp_path):
    """INV-13 要的是当日汇率：拿前一天的汇率凑数也要拒绝。"""
    def older(case):
        def shift(facts):
            for f in facts:
                f["period"] = f["as_of"] = "2026-10-27"
            return facts
        edit_json(case / "snapshots" / TICKER / "2026-10-28-fx.json", shift)

    cwd = make_variant(tmp_path, CASE_NAME, "lenovo-old-fx", older)
    res = cli("zones", TICKER, "--replay", "lenovo-old-fx", "--eps", "2.7", "--pe", "8-11", "--json", cwd=cwd)
    assert res.code != 0
    err = res.json()["error"]
    assert err["code"] == "FX_MISSING"
    assert "2026-10-28" in err["message"]


def test_ma200_near_19_1(plan):
    assert plan["tech"]["ma200"] == pytest.approx(19.1, rel=0.05)


def test_weekly_close_uses_hk_calendar(plan):
    weeks = {w["date"] for w in plan["tech"]["weekly_closes"]}
    assert "2026-06-18" in weeks, "6 月 19 日端午节休市，那周的周收盘是周四"
    assert "2026-04-02" in weeks, "4 月 3 日耶稣受难节休市，那周的周收盘是周四"
    assert "2026-06-19" not in weeks


def test_close_to_manual_version(plan):
    manual = json.loads((CASE / "manual-zones.json").read_text(encoding="utf-8"))
    problems = compare_with_manual(plan, manual)
    for p in problems:
        print("差异：", p)
    assert not problems, "与人工版本偏差超过 5%，需要你判断：\n" + "\n".join(problems)


def test_tiers_below_price_and_sizes_add_up(plan):
    close = plan["reference"]["close"]
    tiers = plan["tiers"]
    for t in tiers:
        assert t["high"] < close
    for upper, lower in zip(tiers, tiers[1:], strict=False):
        assert upper["low"] > lower["high"]
    total = sum(t["size"] for t in tiers) + plan.get("reserved", {}).get("size", 0)
    assert total == pytest.approx(1.0)


def test_hk_calendar_matches_bars():
    rows = json.loads((CASE / "snapshots" / TICKER / "2026-10-28-bars.json").read_text())["rows"]
    have = {r[0] for r in rows}
    day, end = date.fromisoformat(rows[0][0]), date.fromisoformat(rows[-1][0])
    while day <= end:
        if day.weekday() < 5:
            assert is_trading_day(day, "HK") == (day.isoformat() in have), day
        day += timedelta(days=1)
