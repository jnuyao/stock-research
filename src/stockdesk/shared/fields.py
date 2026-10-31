"""字段的中文名。财报包和报告都用这张表，保证同一个字段在各处叫法一致。"""

from __future__ import annotations

LABELS: dict[str, str] = {
    "revenue": "营收",
    "revenue_yoy": "营收同比",
    "gross_margin_gaap": "GAAP 毛利率",
    "gross_margin_nongaap": "非 GAAP 毛利率",
    "eps_gaap": "GAAP EPS",
    "eps_gaap_yoy": "GAAP EPS 同比",
    "eps_nongaap": "调整后 EPS",
    "eps_nongaap_yoy": "调整后 EPS 同比",
    "op_margin_gaap": "GAAP 营业利润率",
    "op_margin_nongaap": "非 GAAP 营业利润率",
    "operating_cash_flow": "经营现金流",
    "capex_gross": "资本开支",
    "fcf_adjusted": "调整后自由现金流",
    "cons_revenue": "营收一致预期",
    "cons_eps_nongaap": "调整后 EPS 一致预期",
    "revenue_surprise_pct": "营收超预期幅度",
    "eps_surprise": "EPS 超预期金额",
    "eps_surprise_pct": "EPS 超预期幅度",
    "verdict_revenue": "营收对比预期",
    "verdict_eps": "EPS 对比预期",
    "guide_revenue_low": "下季营收指引下限",
    "guide_revenue_high": "下季营收指引上限",
    "guide_revenue_mid": "下季营收指引中值",
    "guide_gm_gaap": "下季 GAAP 毛利率指引",
    "guide_gm_nongaap": "下季非 GAAP 毛利率指引",
    "guide_eps_gaap": "下季 GAAP EPS 指引",
    "guide_eps_nongaap": "下季调整后 EPS 指引",
    "next_cons_revenue": "下季营收一致预期",
    "next_cons_eps_nongaap": "下季 EPS 一致预期",
    "next_cons_gm_nongaap": "下季毛利率一致预期",
    "guide_revenue_vs_cons_pct": "营收指引中值相对预期",
    "guide_revenue_high_vs_cons_pct": "营收指引上限相对预期",
    "guide_eps_vs_cons": "EPS 指引相对预期（金额）",
    "guide_eps_vs_cons_pct": "EPS 指引相对预期",
    "guide_gm_vs_cons_pt": "毛利率指引相对预期",
    "gm_next_vs_current_pt": "毛利率指引相对本季",
    "verdict_guide_revenue": "营收指引对比预期",
    "verdict_guide_eps": "EPS 指引对比预期",
    "verdict_guide_gm": "毛利率指引对比预期",
    "one_off": "一次性项目",
    "price_close": "收盘价",
    "price_after_hours": "盘后价",
    "op_income": "营业利润",
    "pretax_income": "税前利润",
    "net_income": "净利润",
    "other_income_net": "其他收益（净）",
    "fcf": "自由现金流",
    "adj_net_income": "经调整净利润",
    "adj_net_income_yoy": "经调整净利润同比",
    "cons_eps_gaap": "GAAP EPS 一致预期",
    "next_cons_eps_gaap": "下季 GAAP EPS 一致预期",
    "op_income_ex_one_offs": "剔除一次性项目后的营业利润",
    "pretax_ex_one_offs": "剔除一次性项目后的税前利润",
    "eps_gaap_ex_one_offs": "剔除一次性项目后的 GAAP EPS",
    "one_off_total": "一次性项目合计",
    "bars_daily": "日线",
    "pe_fwd": "历史前瞻市盈率",
    "peer_pe": "同行市盈率",
    "fx.USDHKD": "美元兑港元汇率",
}

SEGMENT_METRICS: dict[str, str] = {
    "revenue": "营收",
    "revenue_yoy": "营收同比",
    "op_income": "营业利润",
}


def label(key: str, names: dict[str, str] | None = None) -> str:
    """字段的中文名。names 是公司档案里的部门和指标名（config/companies.toml）。"""
    names = names or {}
    if key.startswith("segment."):
        _, seg, metric = key.split(".", 2)
        return f"{names.get(seg, seg)} {SEGMENT_METRICS.get(metric, metric)}"
    if key.startswith(("kpi.", "one_off.", "peer_pe.")):
        head, name = key.split(".", 1)
        return names.get(name, name) if head == "kpi" else f"{LABELS.get(head, head)} {name}"
    if key.startswith("next_") and key not in LABELS:
        return "下季" + LABELS.get(key[5:], key[5:])
    return LABELS.get(key, key)
