"""[CLI] 把买点计划打印成给人看的中文摘要。"""

from __future__ import annotations

from typing import Any


def _p(x: float) -> str:
    return f"{x:,.2f}"


def _pe(x: float) -> str:
    return f"{x:.1f}"


def print_zones(plan: dict[str, Any]) -> None:
    ref, tech, val = plan["reference"], plan["tech"], plan["valuation"]
    cur = plan["currency"]
    print(f"{plan['ticker']} 三档买点（数据截至 {ref['close_date']}，单位 {cur}，规则版本 {plan['rules_version']}）")
    ref_text = f"参考价 {_p(ref['price'])}（{ref['basis']}"
    if ref["price"] != ref["close"]:
        ref_text += f"；收盘 {_p(ref['close'])}"
    print(ref_text + "）")
    print()
    for t in plan["tiers"]:
        chk = t["valuation_check"]
        verdict = "符合" if chk["ok"] else "高于"
        print(f"{t['name']} 档  {_p(t['low'])}–{_p(t['high'])}  仓位 {t['size']:.0%}")
        print(f"      锚点：{t['anchor']['label']} = {_p(t['anchor']['value'])}")
        print(f"      估值：隐含 {_pe(chk['implied_pe'])} 倍，{verdict}{chk['compare_to']} {_pe(chk['value'])} 倍")
        print(f"      条件：{t['condition']}")
    if "reserved" in plan:
        print(f"储备  仓位 {plan['reserved']['size']:.0%}：{plan['reserved']['reason']}")
    print(f"右侧  {plan['right_side']['condition']}")
    if "invalidation" in plan:
        inv = plan["invalidation"]
        print(f"失效位 {inv['condition']}（{inv['basis']}）")
    print()
    supports = "、".join(f"{_p(s['level'])}（{len(s['touches'])} 次）" for s in tech["supports"]) or "无"
    print(f"技术位：50 日线 {_p(tech['ma50'])}，200 日线 {_p(tech['ma200'])}，"
          f"52 周高点 {_p(tech['high_52w']['value'])}（{tech['high_52w']['date']}），支撑 {supports}")
    hist = val["history"]
    peers = val["peers"]
    peer_text = ("、".join(f"{p['name']} {_pe(p['pe'])} 倍" for p in peers["values"]) if not peers["missing"]
                 else f"缺失（{peers['reason']}）")
    pe_span = f"{_pe(hist['min'])}–{_pe(hist['max'])} 倍，中位 {_pe(hist['median'])} 倍"
    print(f"估值：近 3 年前瞻市盈率 {pe_span}；同行 {peer_text}")
    if val["fx"]:
        fx = val["fx"]
        print(f"汇率：{fx['pair']} {fx['rate']:g}（{fx['date']}，{fx['source_url']}）")
    for note in plan["notes"]:
        print(f"注：{note}")
    print(plan["disclaimer"])
