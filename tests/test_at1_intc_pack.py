"""[AT-1] INTC Q3'26 财报包回放：数字对、指引判定对、每个字段带来源和日期；缺关键字段时拒绝。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from stockdesk.earnings import build_pack
from stockdesk.shared.errors import ErrorCode, StockdeskError

from conftest import CASES

CASE = CASES / "intc-q3-2026"


@pytest.fixture(scope="module")
def pack():
    return build_pack("INTC", "2026Q3", as_of="2026-10-29", root=CASE)


def item(pack, key):
    return pack.item(key)


def test_actuals_match_press_release(pack):
    assert item(pack, "revenue").value == pytest.approx(16.5e9)
    assert item(pack, "eps_nongaap").value == pytest.approx(0.52)
    assert item(pack, "eps_gaap").value == pytest.approx(0.60)
    assert item(pack, "gross_margin_nongaap").value == pytest.approx(0.441)


def test_actuals_vs_consensus(pack):
    assert item(pack, "cons_revenue").value == pytest.approx(16.47e9)
    assert item(pack, "cons_eps_nongaap").value == pytest.approx(0.40)
    assert item(pack, "verdict_revenue").value == "符合预期"
    assert item(pack, "verdict_eps").value == "高于预期"
    assert item(pack, "eps_surprise_pct").value == pytest.approx(0.30)


def test_guidance_all_below_consensus(pack):
    assert item(pack, "guide_revenue_low").value == pytest.approx(15.0e9)
    assert item(pack, "guide_revenue_high").value == pytest.approx(16.0e9)
    assert item(pack, "next_cons_revenue").value == pytest.approx(17.08e9)
    assert item(pack, "guide_eps_nongaap").value == pytest.approx(0.25)
    assert item(pack, "next_cons_eps_nongaap").value == pytest.approx(0.44)
    assert item(pack, "guide_gm_nongaap").value == pytest.approx(0.38)
    assert item(pack, "next_cons_gm_nongaap").value == pytest.approx(0.428)
    for key in ("verdict_guide_revenue", "verdict_guide_eps", "verdict_guide_gm"):
        assert item(pack, key).value == "低于预期", key


def test_gaap_and_nongaap_are_separate(pack):
    assert item(pack, "eps_gaap").value != item(pack, "eps_nongaap").value
    assert item(pack, "gross_margin_gaap").value == pytest.approx(0.430)


def test_every_item_has_source_and_date(pack):
    for it in pack.items:
        if it.missing:
            continue
        assert it.sources, f"{it.key} 没有来源"
        for src in it.sources:
            assert src.url.startswith("https://"), it.key
            assert len(src.as_of) == 10, it.key


def test_pack_hash_is_stable(pack):
    again = build_pack("INTC", "2026Q3", as_of="2026-10-29", root=CASE)
    assert pack.pack_hash == again.pack_hash
    assert len(pack.pack_hash) == 12


def test_missing_critical_field_is_refused(tmp_path: Path):
    case = tmp_path / "case"
    shutil.copytree(CASE, case)
    pr = case / "snapshots" / "INTC" / "2026-10-29-press-release.json"
    facts = [f for f in json.loads(pr.read_text()) if f["field"] != "guide_eps_nongaap"]
    pr.write_text(json.dumps(facts))
    with pytest.raises(StockdeskError) as exc:
        build_pack("INTC", "2026Q3", as_of="2026-10-29", root=case)
    assert exc.value.code == ErrorCode.DATA_INCOMPLETE
    missing = [g["field"] for g in exc.value.details["gaps"]]
    assert "guide_eps_nongaap" in missing


def test_cli_pack_replay_json(cli):
    res = cli("pack", "INTC", "--quarter", "2026Q3", "--replay", "intc-q3-2026", "--json")
    assert res.code == 0, res.stderr
    data = res.json()
    assert data["ticker"] == "INTC"
    keys = {it["key"]: it for it in data["items"]}
    assert keys["revenue"]["value"] == pytest.approx(16.5e9)
    assert keys["verdict_guide_revenue"]["value"] == "低于预期"
