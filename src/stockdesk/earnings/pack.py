"""[EARN] 财报包：把一个季度整理成固定结构，只组装和计算，不写判断。

要哪些字段由公司档案决定（config/companies.toml）：例如 Alphabet 只报 GAAP EPS、不给指引，
港股的一致预期是非关键字段。档案没写的按默认处理。
"""

from __future__ import annotations

import re
from pathlib import Path

from stockdesk.qa import Dataset, Need, require
from stockdesk.shared.fields import label
from stockdesk.shared.models import CompanyProfile, EarningsPack, Fact, PackItem, Source

# 判定“高于 / 符合 / 低于预期”的阈值。改阈值等于改规则，要在报告里看得到。
THRESHOLDS = {
    "revenue_pct": 0.01,        # 实际营收相对预期 ±1% 以内算符合
    "eps_pct": 0.03,            # 实际 EPS 相对预期 ±3% 以内算符合
    "guide_revenue_pct": 0.02,  # 营收指引中值相对预期 ±2% 以内算符合
    "guide_eps_pct": 0.05,      # EPS 指引相对预期 ±5% 以内算符合
    "guide_gm_pt": 0.01,        # 毛利率指引相对预期 ±1 个百分点以内算符合
    "one_off_share": 0.10,      # 单项其他收益/损失超过当季营业利润的 10% 算一次性项目
}

CURRENT_OPTIONAL = [
    "revenue_yoy", "eps_gaap_yoy", "eps_nongaap_yoy", "op_margin_gaap", "op_margin_nongaap",
    "operating_cash_flow", "capex_gross", "fcf_adjusted", "fcf", "op_income", "pretax_income", "net_income",
    "other_income_net", "adj_net_income", "adj_net_income_yoy",
]
QUARTER_RE = re.compile(r"^(FY)?(\d{4})Q([1-4])$")


def next_quarter(quarter: str) -> str:
    m = QUARTER_RE.match(quarter)
    if not m:
        raise ValueError(f"季度写法应为 2026Q3 或 FY2027Q1，收到 {quarter}")
    prefix, year, q = m.group(1) or "", int(m.group(2)), int(m.group(3))
    return f"{prefix}{year + 1}Q1" if q == 4 else f"{prefix}{year}Q{q + 1}"


def _verdict(diff: float, tolerance: float) -> str:
    if diff > tolerance:
        return "高于预期"
    if diff < -tolerance:
        return "低于预期"
    return "符合预期"


class _Builder:
    def __init__(self, ds: Dataset, names: dict[str, str]):
        self.ds = ds
        self.names = names
        self.items: list[PackItem] = []
        self.by_key: dict[str, PackItem] = {}

    def _put(self, it: PackItem) -> PackItem:
        self.items.append(it)
        self.by_key[it.key] = it
        return it

    def add_fact(self, key: str, fact: Fact | None, period: str, unit: str = "", name: str | None = None) -> PackItem:
        lab = name or label(key, self.names)
        if fact is None or fact.value is None:
            return self._put(PackItem(key, lab, None, unit or (fact.unit if fact else ""), period,
                                      missing=True, gap_ack=fact.gap_ack if fact else None))
        return self._put(PackItem(key, lab, fact.value, fact.unit, period,
                                  sources=[Source(fact.source_url, fact.as_of)], note=fact.note))

    def add_if_present(self, key: str, fact: Fact | None, period: str) -> None:
        """可选字段：有数或登记了缺失原因才放进财报包，没有就不出现。"""
        if fact is not None and (fact.value is not None or fact.gap_ack):
            self.add_fact(key, fact, period)

    def derive(self, key: str, value: float | str, unit: str, period: str, inputs: list[str],
               name: str | None = None, note: str | None = None) -> PackItem:
        sources: list[Source] = []
        for k in inputs:
            for s in self.by_key[k].sources:
                if s not in sources:
                    sources.append(s)
        return self._put(PackItem(key, name or label(key, self.names), value, unit, period,
                                  sources=sources, derived_from=inputs, note=note))

    def has(self, key: str) -> bool:
        return key in self.by_key and not self.by_key[key].missing

    def v(self, key: str) -> float:
        return float(self.by_key[key].value)


def _needs(profile: CompanyProfile, quarter: str, nq: str, as_of: str) -> list[Need]:
    nongaap = profile.eps_basis == "nongaap"
    eps_key = "eps_nongaap" if nongaap else "eps_gaap"
    cons = dict(critical=profile.consensus_critical, ack=not profile.consensus_critical)
    needs = [Need("revenue", quarter), Need("eps_gaap", quarter)]
    if nongaap:
        needs.append(Need("eps_nongaap", quarter))
    if profile.gross_margin:
        needs.append(Need("gross_margin_gaap", quarter))
        if nongaap:
            needs.append(Need("gross_margin_nongaap", quarter))
    needs += [Need("cons_revenue", quarter, **cons), Need(f"cons_{eps_key}", quarter, **cons)]
    needs += [Need(f, quarter, critical=False) for f in CURRENT_OPTIONAL]
    if profile.guidance:
        needs += [Need(f, nq) for f in ("guide_revenue_low", "guide_revenue_high", f"guide_{eps_key}")]
        needs += [Need("cons_revenue", nq, **cons), Need(f"cons_{eps_key}", nq, **cons)]
        if nongaap:
            needs += [Need("guide_gm_nongaap", nq), Need("cons_gm_nongaap", nq, **cons)]
        needs += [Need(f, nq, critical=False) for f in ("guide_gm_gaap", "guide_eps_gaap")]
    needs.append(Need("price_close", as_of, critical=False))
    return needs


def build_pack(ticker: str, quarter: str, as_of: str, root: Path, market: str | None = None,
               profile: CompanyProfile | None = None) -> EarningsPack:
    ticker = ticker.upper()
    profile = profile or CompanyProfile.default(ticker)
    market = market or profile.market
    nq = next_quarter(quarter)
    nongaap = profile.eps_basis == "nongaap"
    eps_key = "eps_nongaap" if nongaap else "eps_gaap"
    ds = require(ticker, _needs(profile, quarter, nq, as_of), root=root, as_of=as_of, market=market,
                 optional_prefixes=[("segment.", quarter), ("kpi.", quarter), ("item.", quarter)])
    b = _Builder(ds, {**profile.segments, **profile.kpis})

    # 本季实际与预期
    core = ["revenue", "eps_gaap"] + (["eps_nongaap"] if nongaap else [])
    if profile.gross_margin:
        core += ["gross_margin_gaap"] + (["gross_margin_nongaap"] if nongaap else [])
    for f in core:
        b.add_fact(f, ds.get(f, quarter), quarter)
    for f in ("cons_revenue", f"cons_{eps_key}"):
        b.add_fact(f, ds.get(f, quarter), quarter)
    for f in CURRENT_OPTIONAL:
        b.add_if_present(f, ds.get(f, quarter), quarter)
    for prefix in ("segment.", "kpi."):
        for fact in ds.by_prefix(prefix, quarter):
            b.add_fact(fact.field, fact, quarter)

    # 下季指引与预期
    if profile.guidance:
        gm = ["guide_gm_gaap", "guide_gm_nongaap"] if nongaap else []
        for f in ["guide_revenue_low", "guide_revenue_high", *gm, "guide_eps_gaap", "guide_eps_nongaap"]:
            if f in ("guide_gm_gaap", "guide_eps_gaap") or (f == "guide_eps_nongaap" and not nongaap):
                b.add_if_present(f, ds.get(f, nq), nq)
            else:
                b.add_fact(f, ds.get(f, nq), nq)
        for f in ["cons_revenue", f"cons_{eps_key}"] + (["cons_gm_nongaap"] if nongaap else []):
            b.add_fact(f"next_{f}", ds.get(f, nq), nq)
    b.add_fact("price_close", ds.get("price_close", as_of), as_of, unit=profile.price_currency)

    _surprise(b, quarter, eps_key)
    if profile.guidance:
        _guidance(b, nq, eps_key, nongaap)
    _one_offs(b, ds, quarter)
    return EarningsPack(ticker, quarter, nq, as_of, market, b.items)


def _surprise(b: _Builder, quarter: str, eps_key: str) -> None:
    cons_eps = f"cons_{eps_key}"
    if b.has("cons_revenue"):
        rev_pct = b.v("revenue") / b.v("cons_revenue") - 1
        b.derive("revenue_surprise_pct", rev_pct, "ratio", quarter, ["revenue", "cons_revenue"])
    if b.has(cons_eps):
        b.derive("eps_surprise", b.v(eps_key) - b.v(cons_eps), b.by_key[eps_key].unit, quarter, [eps_key, cons_eps])
        eps_pct = b.v(eps_key) / b.v(cons_eps) - 1
        b.derive("eps_surprise_pct", eps_pct, "ratio", quarter, [eps_key, cons_eps])
    if b.has("cons_revenue"):
        b.derive("verdict_revenue", _verdict(rev_pct, THRESHOLDS["revenue_pct"]), "text", quarter,
                 ["revenue", "cons_revenue"])
    if b.has(cons_eps):
        b.derive("verdict_eps", _verdict(eps_pct, THRESHOLDS["eps_pct"]), "text", quarter, [eps_key, cons_eps])


def _guidance(b: _Builder, nq: str, eps_key: str, nongaap: bool) -> None:
    g_eps, c_eps = f"guide_{eps_key}", f"next_cons_{eps_key}"
    mid = (b.v("guide_revenue_low") + b.v("guide_revenue_high")) / 2
    b.derive("guide_revenue_mid", mid, b.by_key["guide_revenue_low"].unit, nq,
             ["guide_revenue_low", "guide_revenue_high"])
    if b.has("next_cons_revenue"):
        g_rev = mid / b.v("next_cons_revenue") - 1
        b.derive("guide_revenue_vs_cons_pct", g_rev, "ratio", nq, ["guide_revenue_mid", "next_cons_revenue"])
        b.derive("guide_revenue_high_vs_cons_pct", b.v("guide_revenue_high") / b.v("next_cons_revenue") - 1,
                 "ratio", nq, ["guide_revenue_high", "next_cons_revenue"])
    if b.has(c_eps):
        b.derive("guide_eps_vs_cons", b.v(g_eps) - b.v(c_eps), b.by_key[g_eps].unit, nq, [g_eps, c_eps])
        g_epsp = b.v(g_eps) / b.v(c_eps) - 1
        b.derive("guide_eps_vs_cons_pct", g_epsp, "ratio", nq, [g_eps, c_eps])
    if nongaap and b.has("next_cons_gm_nongaap"):
        g_gm = b.v("guide_gm_nongaap") - b.v("next_cons_gm_nongaap")
        b.derive("guide_gm_vs_cons_pt", g_gm, "pt", nq, ["guide_gm_nongaap", "next_cons_gm_nongaap"])
    if nongaap:
        b.derive("gm_next_vs_current_pt", b.v("guide_gm_nongaap") - b.v("gross_margin_nongaap"), "pt", nq,
                 ["guide_gm_nongaap", "gross_margin_nongaap"])
    if b.has("next_cons_revenue"):
        b.derive("verdict_guide_revenue", _verdict(g_rev, THRESHOLDS["guide_revenue_pct"]), "text", nq,
                 ["guide_revenue_mid", "next_cons_revenue"])
    if b.has(c_eps):
        b.derive("verdict_guide_eps", _verdict(g_epsp, THRESHOLDS["guide_eps_pct"]), "text", nq, [g_eps, c_eps])
    if nongaap and b.has("next_cons_gm_nongaap"):
        b.derive("verdict_guide_gm", _verdict(g_gm, THRESHOLDS["guide_gm_pt"]), "text", nq,
                 ["guide_gm_nongaap", "next_cons_gm_nongaap"])


def _one_offs(b: _Builder, ds: Dataset, quarter: str) -> None:
    """新闻稿列出的其他收益/损失，单项超过当季营业利润 10% 的标为一次性项目，并给出剔除后的数字。"""
    if not b.has("op_income"):
        return
    limit = abs(b.v("op_income")) * THRESHOLDS["one_off_share"]
    flagged = []
    for fact in ds.by_prefix("item.", quarter):
        slug = fact.field.removeprefix("item.")
        if "." in slug or abs(fact.value) <= limit:
            continue
        key = f"one_off.{slug}"
        b.add_fact(key, fact, quarter, name=fact.note or slug)
        flagged.append((key, ds.get(f"item.{slug}.eps_impact", quarter)))
    if not flagged:
        return
    keys = [k for k, _ in flagged]
    total = sum(b.v(k) for k in keys)
    b.derive("one_off_total", total, b.by_key[keys[0]].unit, quarter, keys)
    b.derive("op_income_ex_one_offs", b.v("op_income"), b.by_key["op_income"].unit, quarter, ["op_income", *keys],
             note="这些项目记在营业利润之下（其他收益），营业利润本身不受影响")
    if b.has("pretax_income"):
        b.derive("pretax_ex_one_offs", b.v("pretax_income") - total, b.by_key["pretax_income"].unit, quarter,
                 ["pretax_income", *keys])
    impacts = [f for _, f in flagged]
    if b.has("eps_gaap") and all(f is not None and f.value is not None for f in impacts):
        for key, f in flagged:
            slug = key.removeprefix("one_off.")
            b.add_fact(f"one_off_eps.{slug}", f, quarter, name=f"{b.by_key[key].label}对 EPS 的影响")
        eps = b.v("eps_gaap") - sum(f.value for f in impacts)
        b.derive("eps_gaap_ex_one_offs", round(eps, 4), b.by_key["eps_gaap"].unit, quarter,
                 ["eps_gaap", *[f"one_off_eps.{k.removeprefix('one_off.')}" for k in keys]],
                 note="按新闻稿给出的每股影响加回")
