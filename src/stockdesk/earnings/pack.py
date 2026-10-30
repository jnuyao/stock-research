"""[EARN] 财报包：把一个季度整理成固定结构，只组装和计算，不写判断。"""

from __future__ import annotations

from pathlib import Path

from stockdesk.qa import Dataset, Need, require
from stockdesk.shared.fields import label
from stockdesk.shared.models import EarningsPack, Fact, PackItem, Source

# 判定“高于 / 符合 / 低于预期”的阈值。改阈值等于改规则，要在报告里看得到。
THRESHOLDS = {
    "revenue_pct": 0.01,        # 实际营收相对预期 ±1% 以内算符合
    "eps_pct": 0.03,            # 实际 EPS 相对预期 ±3% 以内算符合
    "guide_revenue_pct": 0.02,  # 营收指引中值相对预期 ±2% 以内算符合
    "guide_eps_pct": 0.05,      # EPS 指引相对预期 ±5% 以内算符合
    "guide_gm_pt": 0.01,        # 毛利率指引相对预期 ±1 个百分点以内算符合
}

CURRENT_CRITICAL = ["revenue", "eps_gaap", "eps_nongaap", "gross_margin_gaap", "gross_margin_nongaap",
                    "cons_revenue", "cons_eps_nongaap"]
CURRENT_OPTIONAL = ["revenue_yoy", "eps_gaap_yoy", "eps_nongaap_yoy", "op_margin_gaap", "op_margin_nongaap",
                    "operating_cash_flow", "capex_gross", "fcf_adjusted"]
NEXT_CRITICAL = ["guide_revenue_low", "guide_revenue_high", "guide_eps_nongaap", "guide_gm_nongaap",
                 "cons_revenue", "cons_eps_nongaap", "cons_gm_nongaap"]
NEXT_OPTIONAL = ["guide_gm_gaap", "guide_eps_gaap"]


def next_quarter(quarter: str) -> str:
    year, q = int(quarter[:4]), int(quarter[-1])
    return f"{year + 1}Q1" if q == 4 else f"{year}Q{q + 1}"


def _verdict(diff: float, tolerance: float) -> str:
    if diff > tolerance:
        return "高于预期"
    if diff < -tolerance:
        return "低于预期"
    return "符合预期"


class _Builder:
    def __init__(self, ds: Dataset):
        self.ds = ds
        self.items: list[PackItem] = []
        self.by_key: dict[str, PackItem] = {}

    def add_fact(self, key: str, fact: Fact | None, period: str, unit: str = "") -> PackItem:
        if fact is None or fact.value is None:
            it = PackItem(key, label(key), None, unit or (fact.unit if fact else ""), period,
                          missing=True, gap_ack=fact.gap_ack if fact else None)
        else:
            it = PackItem(key, label(key), fact.value, fact.unit, period,
                          sources=[Source(fact.source_url, fact.as_of)])
        self.items.append(it)
        self.by_key[key] = it
        return it

    def derive(self, key: str, value: float | str, unit: str, period: str, inputs: list[str]) -> PackItem:
        sources: list[Source] = []
        for k in inputs:
            for s in self.by_key[k].sources:
                if s not in sources:
                    sources.append(s)
        it = PackItem(key, label(key), value, unit, period, sources=sources, derived_from=inputs)
        self.items.append(it)
        self.by_key[key] = it
        return it

    def v(self, key: str) -> float:
        return float(self.by_key[key].value)


def build_pack(ticker: str, quarter: str, as_of: str, root: Path, market: str = "US") -> EarningsPack:
    ticker = ticker.upper()
    nq = next_quarter(quarter)
    needs = (
        [Need(f, quarter) for f in CURRENT_CRITICAL]
        + [Need(f, quarter, critical=False) for f in CURRENT_OPTIONAL]
        + [Need(f, nq) for f in NEXT_CRITICAL]
        + [Need(f, nq, critical=False) for f in NEXT_OPTIONAL]
        + [Need("price_close", as_of, critical=False)]
    )
    ds = require(ticker, needs, root=root, optional_prefixes=[("segment.", quarter)])
    b = _Builder(ds)

    for f in CURRENT_CRITICAL + CURRENT_OPTIONAL:
        b.add_fact(f, ds.get(f, quarter), quarter)
    for seg in ds.by_prefix("segment.", quarter):
        b.add_fact(seg.field, seg, quarter)
    for f in ["guide_revenue_low", "guide_revenue_high", "guide_gm_gaap", "guide_gm_nongaap",
              "guide_eps_gaap", "guide_eps_nongaap"]:
        b.add_fact(f, ds.get(f, nq), nq)
    for f in ["cons_revenue", "cons_eps_nongaap", "cons_gm_nongaap"]:
        b.add_fact(f"next_{f}", ds.get(f, nq), nq)
    b.add_fact("price_close", ds.get("price_close", as_of), as_of, unit="USD")

    # 本季：实际 vs 预期
    rev_pct = b.v("revenue") / b.v("cons_revenue") - 1
    b.derive("revenue_surprise_pct", rev_pct, "ratio", quarter, ["revenue", "cons_revenue"])
    b.derive("eps_surprise", b.v("eps_nongaap") - b.v("cons_eps_nongaap"), b.by_key["eps_nongaap"].unit,
             quarter, ["eps_nongaap", "cons_eps_nongaap"])
    eps_pct = b.v("eps_nongaap") / b.v("cons_eps_nongaap") - 1
    b.derive("eps_surprise_pct", eps_pct, "ratio", quarter, ["eps_nongaap", "cons_eps_nongaap"])
    b.derive("verdict_revenue", _verdict(rev_pct, THRESHOLDS["revenue_pct"]), "text", quarter,
             ["revenue", "cons_revenue"])
    b.derive("verdict_eps", _verdict(eps_pct, THRESHOLDS["eps_pct"]), "text", quarter,
             ["eps_nongaap", "cons_eps_nongaap"])

    # 下季：指引 vs 预期
    mid = (b.v("guide_revenue_low") + b.v("guide_revenue_high")) / 2
    b.derive("guide_revenue_mid", mid, b.by_key["guide_revenue_low"].unit, nq,
             ["guide_revenue_low", "guide_revenue_high"])
    g_rev = mid / b.v("next_cons_revenue") - 1
    b.derive("guide_revenue_vs_cons_pct", g_rev, "ratio", nq, ["guide_revenue_mid", "next_cons_revenue"])
    b.derive("guide_revenue_high_vs_cons_pct", b.v("guide_revenue_high") / b.v("next_cons_revenue") - 1,
             "ratio", nq, ["guide_revenue_high", "next_cons_revenue"])
    b.derive("guide_eps_vs_cons", b.v("guide_eps_nongaap") - b.v("next_cons_eps_nongaap"),
             b.by_key["guide_eps_nongaap"].unit, nq, ["guide_eps_nongaap", "next_cons_eps_nongaap"])
    g_eps = b.v("guide_eps_nongaap") / b.v("next_cons_eps_nongaap") - 1
    b.derive("guide_eps_vs_cons_pct", g_eps, "ratio", nq, ["guide_eps_nongaap", "next_cons_eps_nongaap"])
    g_gm = b.v("guide_gm_nongaap") - b.v("next_cons_gm_nongaap")
    b.derive("guide_gm_vs_cons_pt", g_gm, "pt", nq, ["guide_gm_nongaap", "next_cons_gm_nongaap"])
    b.derive("gm_next_vs_current_pt", b.v("guide_gm_nongaap") - b.v("gross_margin_nongaap"), "pt", nq,
             ["guide_gm_nongaap", "gross_margin_nongaap"])
    b.derive("verdict_guide_revenue", _verdict(g_rev, THRESHOLDS["guide_revenue_pct"]), "text", nq,
             ["guide_revenue_mid", "next_cons_revenue"])
    b.derive("verdict_guide_eps", _verdict(g_eps, THRESHOLDS["guide_eps_pct"]), "text", nq,
             ["guide_eps_nongaap", "next_cons_eps_nongaap"])
    b.derive("verdict_guide_gm", _verdict(g_gm, THRESHOLDS["guide_gm_pt"]), "text", nq,
             ["guide_gm_nongaap", "next_cons_gm_nongaap"])

    return EarningsPack(ticker, quarter, nq, as_of, market, b.items)
