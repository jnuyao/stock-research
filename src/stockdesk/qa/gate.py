"""数据守门：分析内核读数据的唯一通道。

按调用方给的字段清单取数，检查四件事，任何一件不过就拒绝，不返回半成品：
1. 有没有快照（NO_SNAPSHOT）
2. 两个来源是否打架（SOURCE_CONFLICT，会列出两个值）
3. 价格是否过期（STALE_PRICE，按各自市场的交易日历判断）
4. 字段是否齐全（DATA_INCOMPLETE，附缺口清单和建议来源）

字段分三级：关键（缺了就拒绝，不能登记跳过）、需登记（缺了要用 gap_ack 写明原因才放行）、可选（有就用）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from stockdesk.shared.calendar import last_trading_day, previous_trading_day
from stockdesk.shared.errors import ErrorCode, StockdeskError
from stockdesk.shared.fields import label
from stockdesk.shared.models import MONEY_UNITS, PER_SHARE_UNITS, Fact, Series

# 同一字段两个来源的差异超过这些阈值，就算打架（与 SPEC 第 5 节一致）
PRICE_TOLERANCE = 0.01
FINANCIAL_TOLERANCE = 0.005
RATIO_TOLERANCE = 0.0005

BARS = "bars_daily"

# 缺口清单里给出的补数建议
WHERE_TO_FIND = {
    "revenue": "公司新闻稿或 SEC 8-K 附件 Ex-99.1；港股看披露易业绩公告",
    "eps_gaap": "公司新闻稿或 SEC 8-K 附件 Ex-99.1；港股看披露易业绩公告",
    "eps_nongaap": "公司新闻稿的非 GAAP 调节表",
    "gross_margin_gaap": "公司新闻稿；港股看披露易业绩公告",
    "gross_margin_nongaap": "公司新闻稿的非 GAAP 调节表",
    "guide_revenue_low": "公司新闻稿的“Business Outlook”一节",
    "guide_revenue_high": "公司新闻稿的“Business Outlook”一节",
    "guide_gm_nongaap": "公司新闻稿的“Business Outlook”一节",
    "guide_eps_nongaap": "公司新闻稿的“Business Outlook”一节",
    "cons_revenue": "财报前的预期报道，或 stockanalysis 的 forecast 页",
    "cons_eps_nongaap": "财报前的预期报道，或 stockanalysis 的 forecast 页",
    "cons_eps_gaap": "财报前的预期报道，或 stockanalysis 的 forecast 页",
    "cons_gm_nongaap": "财报前的预期报道",
    "price_close": "stockanalysis 的 history 页",
    BARS: "Mac 上 `sd fetch`（yfinance），或 stockanalysis 的 history 页",
    "pe_fwd": "stockanalysis 的 financials/ratios 页（Forward PE 一行）",
    "peer_pe": "同行的 stockanalysis statistics 页（Forward PE）",
    "fx.USDHKD": "Yahoo Finance 的 USDHKD=X，或香港金管局汇率页",
}


@dataclass(frozen=True)
class Need:
    """调用方需要的一个字段。

    critical：缺了就拒绝，不能登记跳过。
    ack：非关键，但缺了必须有 gap_ack 登记原因才放行。
    两者都为 False：可选，有就用。
    period 为 None 表示任意期间；prefix 为 True 表示字段名以 field 开头的都算（如 peer_pe.AMD）。
    """

    field: str
    period: str | None = None
    critical: bool = True
    ack: bool = False
    prefix: bool = False


@dataclass(frozen=True)
class SeriesNeed:
    """需要一段序列（例如日线），至少 min_rows 行，截至 as_of。"""

    field: str
    min_rows: int = 1


@dataclass
class Dataset:
    ticker: str
    facts: dict[tuple[str, str], Fact] = field(default_factory=dict)
    series: dict[str, Series] = field(default_factory=dict)
    missing: list[Need] = field(default_factory=list)
    acks: dict[str, str] = field(default_factory=dict)  # 字段 → 登记的缺失原因

    def get(self, name: str, period: str) -> Fact | None:
        return self.facts.get((name, period))

    def by_prefix(self, prefix: str, period: str | None = None) -> list[Fact]:
        return sorted(
            (f for (n, p), f in self.facts.items()
             if n.startswith(prefix) and (period is None or p == period) and f.value is not None),
            key=lambda f: (f.field, f.period),
        )


def snapshot_dir(root: Path, ticker: str) -> Path:
    return Path(root) / "snapshots" / ticker.upper()


def load_snapshots(root: Path, ticker: str) -> tuple[list[Fact], dict[str, Series]]:
    folder = snapshot_dir(root, ticker)
    files = sorted(folder.rglob("*.json")) if folder.exists() else []  # 支持按日期分子目录
    if not files:
        raise StockdeskError(
            ErrorCode.NO_SNAPSHOT,
            f"{ticker} 没有数据快照（找的是 {folder}）",
            {"ticker": ticker, "folder": str(folder)},
        )
    facts: list[Fact] = []
    parts: dict[str, list[Series]] = {}
    for path in files:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):  # 一段序列
            s = Series.from_dict(raw)
            _check_source(s.field, s.source_url, s.as_of, s.fetched_at, path)
            parts.setdefault(s.field, []).append(s)
            continue
        for item in raw:
            fact = Fact.from_dict(item)
            if not (fact.value is None and fact.gap_ack):
                _check_source(fact.field, fact.source_url, fact.as_of, fact.fetched_at, path)
            facts.append(fact)
    series: dict[str, Series] = {}
    for name, group in parts.items():  # 多份同名序列按日期拼接，每一行保留自己的来源
        try:
            series[name] = Series.merge(group)
        except ValueError as err:
            raise StockdeskError(ErrorCode.BAD_INPUT, f"{ticker}：{err}", {"field": name}) from err
    return facts, series


def load_facts(root: Path, ticker: str) -> list[Fact]:
    return load_snapshots(root, ticker)[0]


def _check_source(name: str, url: str, as_of: str, fetched_at: str, path: Path) -> None:
    if not (url and as_of and fetched_at):
        raise StockdeskError(
            ErrorCode.BAD_INPUT,
            f"{path.name} 里的 {name} 缺来源网址或日期，不能使用",
            {"file": str(path), "field": name},
        )


def _differs(a: Fact, b: Fact) -> bool:
    if a.value is None or b.value is None:
        return False
    if a.field.startswith("price") or a.unit == "index":
        tol = PRICE_TOLERANCE
    elif a.unit in MONEY_UNITS | PER_SHARE_UNITS:
        tol = FINANCIAL_TOLERANCE
    else:
        return abs(a.value - b.value) > RATIO_TOLERANCE
    base = max(abs(a.value), abs(b.value)) or 1.0
    return abs(a.value - b.value) / base > tol


def _bar_facts(ticker: str, bars: Series) -> list[Fact]:
    """把日线收盘转成 price_close 事实，用来和网页上的收盘价互相核对。"""
    i_close = bars.columns.index("close")
    return [
        Fact(ticker, "price_close", r[0], float(r[i_close]), bars.unit, bars.source_at(i), r[0],
             bars.fetched_at, bars.via, note="取自日线")
        for i, r in enumerate(bars.rows)
    ]


def _conflicts(grouped: dict[tuple[str, str], list[Fact]]) -> list[dict]:
    out = []
    for (name, period), group in grouped.items():
        if any(_differs(group[0], other) for other in group[1:]):
            out.append({
                "field": name, "period": period, "label": label(name),
                "values": [{"value": g.value, "source_url": g.source_url} for g in group],
            })
    return out


def _check_fresh(ticker: str, as_of: str, market: str, price_dates: list[str]) -> None:
    """最新价格不能早于上一个交易日收盘。"""
    need = previous_trading_day(last_trading_day(date.fromisoformat(as_of), market), market).isoformat()
    latest = max(price_dates) if price_dates else None
    if latest is None or latest < need:
        raise StockdeskError(
            ErrorCode.STALE_PRICE,
            f"{ticker} 最新价格停在 {latest or '（没有）'}，数据日期 {as_of} 要求至少到 {need}（{market} 交易日历）",
            {"latest": latest, "required": need, "as_of": as_of, "market": market},
        )


def _gap(need: Need, period: str | None, reason: str) -> dict:
    return {
        "field": need.field, "period": period, "label": label(need.field), "critical": need.critical,
        "where": WHERE_TO_FIND.get(need.field, "公司公告或财经网页"), "reason": reason,
    }


def require(
    ticker: str,
    needs: list[Need],
    root: Path,
    optional_prefixes: list[tuple[str, str]] = (),
    as_of: str | None = None,
    market: str = "US",
    series_needs: list[SeriesNeed] = (),
    check_price: bool = False,
) -> Dataset:
    """按清单取数。有任何问题就抛 StockdeskError，不返回半成品。

    as_of 给出时，序列只保留 as_of 及以前的行（回放不偷看未来）。
    check_price 为 True 时检查价格时效，并让日线和网页收盘价互相核对。
    """
    ticker = ticker.upper()
    facts, series = load_snapshots(root, ticker)
    if as_of:
        series = {k: s.until(as_of) for k, s in series.items()}

    grouped: dict[tuple[str, str], list[Fact]] = {}
    for f in facts:
        grouped.setdefault((f.field, f.period), []).append(f)
    if BARS in series:
        for f in _bar_facts(ticker, series[BARS]):
            grouped.setdefault((f.field, f.period), []).append(f)

    conflicts = _conflicts(grouped)
    if conflicts:
        raise StockdeskError(
            ErrorCode.SOURCE_CONFLICT,
            "两个来源的数字对不上：" + "、".join(f"{c['label']}（{c['period']}）" for c in conflicts),
            {"conflicts": conflicts},
        )

    if check_price and as_of:
        dates = [p for (n, p), g in grouped.items() if n == "price_close" and p <= as_of and g[0].value is not None]
        _check_fresh(ticker, as_of, market, dates)

    ds = Dataset(ticker=ticker, series=series)
    gaps: list[dict] = []
    wanted = list(needs)
    for prefix, period in optional_prefixes:
        wanted += [Need(n, p, critical=False) for (n, p) in grouped if n.startswith(prefix) and p == period]

    for need in wanted:
        matches = [
            g for (n, p), g in grouped.items()
            if (n == need.field or (need.prefix and n.startswith(need.field + ".")))
            and (need.period is None or p == need.period)
        ]
        present = [g[0] for g in matches if g[0].value is not None]
        acked = [g[0] for g in matches if g[0].value is None and g[0].gap_ack]
        for f in present:
            ds.facts[(f.field, f.period)] = f
        if present:
            continue
        if need.critical:
            reason = (f"这是关键字段，不能登记缺失（登记的原因：{acked[0].gap_ack}）" if acked
                      else "关键字段缺失")
            gaps.append(_gap(need, need.period, reason))
        elif acked:
            ds.missing.append(need)
            ds.acks[need.field] = acked[0].gap_ack
            for f in acked:
                ds.facts[(f.field, f.period)] = f
        elif need.ack:
            gaps.append(_gap(need, need.period, "非关键字段缺失：补不到时用 `sd import --gap-ack` 登记原因"))
        else:
            ds.missing.append(need)

    for sn in series_needs:
        s = series.get(sn.field)
        n = len(s.rows) if s else 0
        if n < sn.min_rows:
            gaps.append(_gap(Need(sn.field), as_of, f"需要至少 {sn.min_rows} 行，现在只有 {n} 行"))

    if gaps:
        names = "、".join(f"{g['label']}（{g['period'] or '任意期间'}）" for g in gaps)
        raise StockdeskError(ErrorCode.DATA_INCOMPLETE, f"字段缺失：{names}", {"gaps": gaps})
    return ds
