"""[ZONES] 买点规则。本模块不读写文件：价位来自 [TECH] 和 [VAL]，规则由调用方传入（config/rules.toml）。

每一档的做法：
1. 列出该档允许的候选锚点（规则里的 anchors），每个锚点都是 [TECH] 或 [VAL] 输出里的一个具体数值；
2. 只看低于上限的：A 档上限是参考价再低 first_gap，之后每档上限是上一档下沿（保证不重叠）；
3. 取其中最高的一个（“取规则允许的最近一个”），价格区间 = 锚点上下 band；
4. 找不到锚点的档位不硬凑，仓位留作储备，写明原因。
参考价 = 最新收盘和盘后价里较低的一个：财报跳空后，买点必须在实际成交价下方。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from stockdesk.technicals import levels
from stockdesk.valuation import value

DISCLAIMER = "不构成投资建议，价格与仓位请结合自身情况判断。"
CHECK_NAMES = {"median": "近 3 年市盈率中位", "p25": "近 3 年市盈率 25% 分位", "min": "近 3 年最低市盈率"}


def _candidates(tech: dict, val: dict) -> dict[str, list[dict[str, Any]]]:
    pe_lo, pe_hi = val["pe_range"]
    eps = val["eps_in_price_currency"]
    out: dict[str, list[dict[str, Any]]] = {
        "support": [{"value": s["level"], "module": "TECH",
                     "label": f"多次测试的支撑（{len(s['touches'])} 次：{'、'.join(s['touches'])}）"}
                    for s in tech["supports"]],
        "ma50": [{"value": tech["ma50"], "module": "TECH", "label": "50 日线"}],
        "ma200": [{"value": tech["ma200"], "module": "TECH", "label": "200 日线"}],
        "fair_high": [{"value": val["fair"]["high"], "module": "VAL",
                       "label": f"估值区间上沿（EPS {eps:.4g} × {pe_hi:g} 倍）"}],
        "fair_mid": [{"value": val["fair"]["mid"], "module": "VAL",
                      "label": f"估值区间中值（EPS {eps:.4g} × {(pe_lo + pe_hi) / 2:g} 倍）"}],
        "fair_low": [{"value": val["fair"]["low"], "module": "VAL",
                      "label": f"估值区间下沿（EPS {eps:.4g} × {pe_lo:g} 倍）"}],
        "pe_floor": [{"value": val["crisis_price"], "module": "VAL",
                      "label": f"危机估值（EPS {eps:.4g} × 近 3 年最低市盈率 {val['history']['min']:g} 倍）"}],
    }
    for k, v in tech["drawdowns"].items():
        high = tech["high_52w"]["value"]
        out[f"drawdown_{k}"] = [{"value": v, "module": "TECH", "label": f"52 周高点 {high:g} 回撤 {float(k):.0%}"}]
    return out


def _check(anchor: float, val: dict, kind: str) -> dict[str, Any]:
    implied = anchor / val["eps_in_price_currency"]
    target = val["history"][kind]
    return {"implied_pe": round(implied, 2), "compare_to": CHECK_NAMES[kind], "value": target,
            "ok": implied <= target * 1.0001}


def compute_zones(
    ticker: str,
    as_of: str,
    eps_fwd: float,
    pe_range: tuple[float, float],
    rules: dict[str, Any],
    root: Path,
    market: str = "US",
    price_currency: str = "USD",
    report_currency: str = "USD",
    eps_currency: str | None = None,
    earnings: dict[str, str] | None = None,
) -> dict[str, Any]:
    earnings = earnings or {}
    tech = levels(ticker, as_of, root, market, earnings.get("date"), earnings.get("timing", "after_close"))
    val = value(ticker, as_of, eps_fwd, pe_range, root, market, price_currency, report_currency, eps_currency)

    close = tech["last_close"]["value"]
    ah = tech["after_hours"]
    ref = min(close, ah["value"]) if ah else close
    reference = {
        "price": ref, "close": close, "close_date": tech["last_close"]["date"],
        "after_hours": ah["value"] if ah else None,
        "basis": "盘后价，低于收盘" if ah and ah["value"] < close else "最新收盘",
    }

    band, depth_floor = rules["band"], ref * (1 - rules["max_depth"])
    high_52w = tech["high_52w"]["value"]
    near_high = close >= high_52w * (1 - rules["near_high"])
    sizes = rules["near_high_sizes"] if near_high else {k: v["size"] for k, v in rules["tiers"].items()}

    cands = _candidates(tech, val)
    recent = tech.get("trading_days_since_earnings", 999) <= rules["recent_earnings_days"]
    tiers, reserved, notes, empty = [], 0.0, [], []
    ceiling = ref * (1 - rules["first_gap"])
    for name in ("A", "B", "C"):
        spec = rules["tiers"][name]
        pool = [c for key in spec["anchors"] for c in cands.get(key, [])
                if depth_floor <= c["value"] <= ceiling]
        if not pool:
            reserved += sizes[name]
            empty.append(name)
            continue
        anchor = max(pool, key=lambda c: c["value"])
        low, high = anchor["value"] * (1 - band), anchor["value"] * (1 + band)
        tiers.append({
            "name": name, "low": round(low, 2), "high": round(high, 2), "size": sizes[name],
            "anchor": anchor, "condition": spec.get("condition_after_earnings", spec["condition"]) if recent
            else spec["condition"],
            "valuation_check": _check(anchor["value"], val, spec["check"]),
        })
        ceiling = round(low, 2) / (1 + band)  # 下一档的上沿不能碰到这一档的下沿

    if tech["pre_earnings_close"] and recent:
        pre = tech["pre_earnings_close"]
        right = {"value": pre["value"], "module": "TECH", "label": f"财报前收盘价 {pre['date']}"}
    else:
        right = {"value": tech["ma50"], "module": "TECH", "label": "50 日线"}

    plan: dict[str, Any] = {
        "ticker": ticker.upper(), "as_of": as_of, "market": market, "currency": price_currency,
        "rules_version": rules["version"], "reference": reference, "tiers": tiers,
        "right_side": {"level": right["value"], "anchor": right,
                       "condition": f"周收盘重新站上 {right['value']:.2f}（{right['label']}）时，补回未买的部分"},
        "near_high": near_high, "notes": notes, "tech": tech, "valuation": val, "disclaimer": DISCLAIMER,
    }
    if reserved:
        plan["reserved"] = {
            "size": round(reserved, 4), "tiers": empty,
            "reason": f"{'、'.join(empty)} 档在参考价 {ref:g} 下方 {rules['max_depth']:.0%} 以内找不到规则允许的锚点，"
                      "这部分仓位留到下次财报或右侧信号再用",
        }
    if near_high:
        notes.append(f"离 52 周高点 {high_52w:g} 不到 {rules['near_high']:.0%}，用 2-3-5 分配，并留一半作恐慌储备")
    if tiers:
        lowest = tiers[-1]
        level = round(lowest["low"] * (1 - rules["invalidation_gap"]), 2)
        plan["invalidation"] = {
            "level": level,
            "basis": f"最低一档（{lowest['name']} 档）下沿 {lowest['low']:.2f} 再低 {rules['invalidation_gap']:.0%}",
            "condition": f"周收盘跌破 {level:.2f}：停止加仓、复盘投资逻辑",
        }
    return plan
