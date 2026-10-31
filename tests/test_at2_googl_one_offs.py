"""[AT-2] GOOGL Q3'26：GAAP EPS 与预期并列，股权投资损失标为一次性项目，给出剔除后的数字。"""

from __future__ import annotations

import pytest

from conftest import edit_json, make_variant

ARGS = ("pack", "GOOGL", "--quarter", "2026Q3", "--replay", "googl-q3-2026", "--json")


def items(res) -> dict:
    assert res.code == 0, res.stdout + res.stderr
    return {it["key"]: it for it in res.json()["items"]}


@pytest.fixture(scope="module")
def pack():
    from conftest import run_cli

    return items(run_cli(*ARGS))


def test_gaap_eps_sits_next_to_consensus(pack):
    assert pack["eps_gaap"]["value"] == pytest.approx(2.12)
    assert pack["cons_eps_gaap"]["value"] == pytest.approx(3.02)
    assert pack["verdict_eps"]["value"] == "低于预期"
    assert "eps_nongaap" not in pack, "Alphabet 不报非 GAAP EPS，不能凭空出现"


def test_equity_loss_is_flagged_as_one_off(pack):
    one_offs = [it for k, it in pack.items() if k.startswith("one_off.")]
    assert len(one_offs) == 1
    loss = one_offs[0]
    assert loss["value"] == pytest.approx(-8.7e9, abs=0.05e9)
    assert "SpaceX" in loss["label"]
    assert loss["sources"][0]["url"].startswith("https://s206.q4cdn.com/")
    # 剔除后：营业利润不受影响（该项在营业利润之下），税前利润和 EPS 加回
    assert pack["op_income_ex_one_offs"]["value"] == pytest.approx(40.576e9)
    assert pack["pretax_ex_one_offs"]["value"] == pytest.approx(32.355e9 + 8.664e9)
    assert pack["eps_gaap_ex_one_offs"]["value"] == pytest.approx(2.67)


def test_cloud_and_backlog(pack):
    assert pack["segment.CLOUD.revenue"]["value"] == pytest.approx(30.7e9, abs=0.05e9)
    assert pack["kpi.cloud_backlog"]["value"] == pytest.approx(561e9)
    assert "investing.com" in pack["kpi.cloud_backlog"]["sources"][0]["url"]


def test_no_guidance_is_not_a_gap(pack):
    """Alphabet 不给季度指引：按公司档案不要求指引，不报 DATA_INCOMPLETE。"""
    assert not any(k.startswith("guide_") for k in pack)


def test_small_items_are_not_one_offs(cli, tmp_path):
    """低于当季营业利润 10% 的其他收益不算一次性项目。"""

    def shrink(case):
        path = case / "snapshots" / "GOOGL" / "2026-10-28-press-release.json"
        edit_json(path, lambda rows: [
            {**r, "value": -3e9} if r["field"] == "item.equity_securities" else r for r in rows
        ])

    cwd = make_variant(tmp_path, "googl-q3-2026", "googl-small-item", shrink)
    res = cli("pack", "GOOGL", "--quarter", "2026Q3", "--replay", "googl-small-item", "--json", cwd=cwd)
    got = items(res)
    assert not any(k.startswith("one_off.") for k in got)
