"""数据守门：分析内核读数据的唯一通道。

切片 1 实现：读快照、按字段清单查覆盖率、发现两个来源打架就拒绝。
切片 2 再加：价格时效（STALE_PRICE）、确认缺失的登记规则、港股差异。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from stockdesk.shared.errors import ErrorCode, StockdeskError
from stockdesk.shared.models import MONEY_UNITS, PER_SHARE_UNITS, Fact

# 同一字段两个来源的差异超过这些阈值，就算打架（与 SPEC 第 5 节一致）
PRICE_TOLERANCE = 0.01
FINANCIAL_TOLERANCE = 0.005

# 缺口清单里给出的补数建议
WHERE_TO_FIND = {
    "revenue": "公司新闻稿或 SEC 8-K 附件 Ex-99.1",
    "eps_gaap": "公司新闻稿或 SEC 8-K 附件 Ex-99.1",
    "eps_nongaap": "公司新闻稿的非 GAAP 调节表",
    "gross_margin_gaap": "公司新闻稿",
    "gross_margin_nongaap": "公司新闻稿的非 GAAP 调节表",
    "guide_revenue_low": "公司新闻稿的“Business Outlook”一节",
    "guide_revenue_high": "公司新闻稿的“Business Outlook”一节",
    "guide_gm_nongaap": "公司新闻稿的“Business Outlook”一节",
    "guide_eps_nongaap": "公司新闻稿的“Business Outlook”一节",
    "cons_revenue": "财报前的预期报道，或 stockanalysis 的 forecast 页",
    "cons_eps_nongaap": "财报前的预期报道，或 stockanalysis 的 forecast 页",
    "cons_gm_nongaap": "财报前的预期报道",
    "price_close": "stockanalysis 的 history 页",
}


@dataclass(frozen=True)
class Need:
    """调用方需要的一个字段。critical=True 时缺了就拒绝。"""

    field: str
    period: str
    critical: bool = True


@dataclass
class Dataset:
    ticker: str
    facts: dict[tuple[str, str], Fact] = field(default_factory=dict)
    missing: list[Need] = field(default_factory=list)

    def get(self, name: str, period: str) -> Fact | None:
        return self.facts.get((name, period))

    def by_prefix(self, prefix: str, period: str) -> list[Fact]:
        return sorted(
            (f for (n, p), f in self.facts.items() if n.startswith(prefix) and p == period),
            key=lambda f: f.field,
        )


def snapshot_dir(root: Path, ticker: str) -> Path:
    return Path(root) / "snapshots" / ticker.upper()


def load_facts(root: Path, ticker: str) -> list[Fact]:
    folder = snapshot_dir(root, ticker)
    files = sorted(folder.rglob("*.json")) if folder.exists() else []  # 支持按日期分子目录
    if not files:
        raise StockdeskError(
            ErrorCode.NO_SNAPSHOT,
            f"{ticker} 没有数据快照（找的是 {folder}）",
            {"ticker": ticker, "folder": str(folder)},
        )
    facts: list[Fact] = []
    for path in files:
        for raw in json.loads(path.read_text(encoding="utf-8")):
            fact = Fact.from_dict(raw)
            _check_provenance(fact, path)
            facts.append(fact)
    return facts


def _check_provenance(fact: Fact, path: Path) -> None:
    if fact.value is None and fact.gap_ack:
        return
    if not (fact.source_url and fact.as_of and fact.fetched_at):
        raise StockdeskError(
            ErrorCode.BAD_INPUT,
            f"{path.name} 里的 {fact.field} 缺来源网址或日期，不能使用",
            {"file": str(path), "field": fact.field},
        )


def _differs(a: Fact, b: Fact) -> bool:
    if a.value is None or b.value is None:
        return False
    if a.field.startswith("price"):
        tol = PRICE_TOLERANCE
    elif a.unit in MONEY_UNITS | PER_SHARE_UNITS:
        tol = FINANCIAL_TOLERANCE
    else:
        return abs(a.value - b.value) > 0.0005
    base = max(abs(a.value), abs(b.value)) or 1.0
    return abs(a.value - b.value) / base > tol


def require(ticker: str, needs: list[Need], root: Path, optional_prefixes: list[tuple[str, str]] = ()) -> Dataset:
    """按清单取数。关键字段缺失或来源打架时抛出 StockdeskError，不返回半成品。"""
    facts = load_facts(root, ticker)
    grouped: dict[tuple[str, str], list[Fact]] = {}
    for f in facts:
        grouped.setdefault((f.field, f.period), []).append(f)

    conflicts = []
    for key, group in grouped.items():
        for other in group[1:]:
            if _differs(group[0], other):
                conflicts.append({
                    "field": key[0], "period": key[1],
                    "values": [{"value": g.value, "source_url": g.source_url} for g in group],
                })
                break
    if conflicts:
        raise StockdeskError(
            ErrorCode.SOURCE_CONFLICT,
            "两个来源的数字对不上：" + "、".join(f"{c['field']}（{c['period']}）" for c in conflicts),
            {"conflicts": conflicts},
        )

    ds = Dataset(ticker=ticker.upper())
    gaps = []
    wanted = list(needs)
    for prefix, period in optional_prefixes:
        wanted += [Need(n, p, critical=False) for (n, p) in grouped if n.startswith(prefix) and p == period]
    for need in wanted:
        group = grouped.get((need.field, need.period))
        fact = group[0] if group else None
        if fact is None or fact.value is None:
            if need.critical:
                gaps.append({
                    "field": need.field, "period": need.period,
                    "where": WHERE_TO_FIND.get(need.field, "公司公告或财经网页"),
                })
            else:
                ds.missing.append(need)
                if fact is not None:
                    ds.facts[(need.field, need.period)] = fact
            continue
        ds.facts[(need.field, need.period)] = fact
    if gaps:
        raise StockdeskError(
            ErrorCode.DATA_INCOMPLETE,
            "关键字段缺失：" + "、".join(f"{g['field']}（{g['period']}）" for g in gaps),
            {"gaps": gaps},
        )
    return ds
