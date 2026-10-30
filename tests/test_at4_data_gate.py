"""[AT-4] 数据守门：价格过期、缺指引、两个来源打架都拒绝且不出价位；非关键字段可登记缺失，关键字段不行。"""

from __future__ import annotations

from conftest import edit_json, make_variant

BASE = "intc-q3-2026"
SNAP = ("snapshots", "INTC")
ZONES = ("--eps", "1.75", "--pe", "38-45", "--json")


def zones(cli, cwd, case):
    return cli("zones", "INTC", "--replay", case, *ZONES, cwd=cwd)


def pack(cli, cwd, case):
    return cli("pack", "INTC", "--quarter", "2026Q3", "--replay", case, "--json", cwd=cwd)


def assert_refused(res, code):
    assert res.code != 0, res.stdout
    out = res.json()
    assert out["error"]["code"] == code, out
    assert "tiers" not in out, "被拒绝时不能输出任何价位"
    return out["error"]


def test_stale_price_is_refused(cli, tmp_path):
    """价格停在 3 个交易日前（10-26），数据日期是 10-29。"""

    def stale(case):
        edit_json(case.joinpath(*SNAP, "2026-10-29-bars.json"),
                  lambda s: {**s, "as_of": "2026-10-26", "rows": [r for r in s["rows"] if r[0] <= "2026-10-26"]})
        for name in ("2026-10-29-price.json", "2026-10-29-after-hours.json"):
            case.joinpath(*SNAP, name).unlink()

    cwd = make_variant(tmp_path, BASE, "stale-price", stale)
    err = assert_refused(zones(cli, cwd, "stale-price"), "STALE_PRICE")
    assert "2026-10-26" in err["message"]


def test_missing_guidance_lists_the_gap(cli, tmp_path):
    def drop_guidance(case):
        edit_json(case.joinpath(*SNAP, "2026-10-29-press-release.json"),
                  lambda rows: [r for r in rows if not r["field"].startswith("guide_")])

    cwd = make_variant(tmp_path, BASE, "no-guidance", drop_guidance)
    err = assert_refused(pack(cli, cwd, "no-guidance"), "DATA_INCOMPLETE")
    gaps = err["details"]["gaps"]
    assert any("指引" in g["label"] and g["where"] for g in gaps), gaps
    assert {g["field"] for g in gaps} >= {"guide_revenue_low", "guide_eps_nongaap"}


def test_two_sources_disagree_on_close(cli, tmp_path):
    """MoneyCheck 收盘 92.07，日线里改成高 2%。"""

    def conflict(case):
        def bump(s):
            rows = [r[:4] + [round(r[4] * 1.02, 2)] + r[5:] if r[0] == "2026-10-29" else r for r in s["rows"]]
            return {**s, "rows": rows}

        edit_json(case.joinpath(*SNAP, "2026-10-29-bars.json"), bump)

    cwd = make_variant(tmp_path, BASE, "price-conflict", conflict)
    err = assert_refused(zones(cli, cwd, "price-conflict"), "SOURCE_CONFLICT")
    values = [v["value"] for c in err["details"]["conflicts"] for v in c["values"]]
    assert 92.07 in values and round(92.07 * 1.02, 2) in values


def test_peer_pe_gap_ack_passes_as_missing(cli, tmp_path):
    """同行 PE 没取到但已登记确认缺失：放行，输出里是缺失状态而不是 0。"""

    def ack(case):
        case.joinpath(*SNAP, "2026-10-30-peers.json").write_text(
            '[{"ticker": "INTC", "field": "peer_pe", "period": "2026-10-29", "value": null, "unit": "x",'
            ' "source_url": "", "as_of": "", "fetched_at": "", "gap_ack": "同行 PE 这次没取到"}]',
            encoding="utf-8",
        )

    cwd = make_variant(tmp_path, BASE, "peer-gap-ack", ack)
    res = zones(cli, cwd, "peer-gap-ack")
    assert res.code == 0, res.stdout + res.stderr
    peers = res.json()["valuation"]["peers"]
    assert peers["missing"] is True
    assert peers["values"] == []
    assert peers["reason"] == "同行 PE 这次没取到"


def test_peer_pe_missing_without_ack_is_a_gap(cli, tmp_path):
    def drop(case):
        case.joinpath(*SNAP, "2026-10-30-peers.json").unlink()

    cwd = make_variant(tmp_path, BASE, "peer-missing", drop)
    err = assert_refused(zones(cli, cwd, "peer-missing"), "DATA_INCOMPLETE")
    assert any(g["field"] == "peer_pe" and not g["critical"] for g in err["details"]["gaps"])


def test_critical_field_cannot_be_acked(cli, tmp_path):
    """缺下季指引还想登记跳过：拒绝，并说明这是关键字段。"""

    def ack_guidance(case):
        edit_json(case.joinpath(*SNAP, "2026-10-29-press-release.json"), lambda rows: [
            {**r, "value": None, "gap_ack": "没找到"} if r["field"] == "guide_eps_nongaap" else r for r in rows
        ])

    cwd = make_variant(tmp_path, BASE, "ack-guidance", ack_guidance)
    err = assert_refused(pack(cli, cwd, "ack-guidance"), "DATA_INCOMPLETE")
    gap = next(g for g in err["details"]["gaps"] if g["field"] == "guide_eps_nongaap")
    assert gap["critical"] is True
    assert "关键字段" in gap["reason"]
