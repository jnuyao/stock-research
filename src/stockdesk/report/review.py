"""出报告前的机械自查（借鉴 UZI-Skill 的 self_review）。有一条严重问题就拒绝生成报告。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

from stockdesk.shared.calendar import last_trading_day
from stockdesk.shared.errors import ErrorCode, StockdeskError
from stockdesk.shared.models import EarningsPack

from .notes import LENSES, STANCES, Notes
from .numbers import find_numbers

BANNED_PHRASES = ("基本面良好", "前景广阔", "值得关注")


def check_names(zones: dict | None) -> list[str]:
    """本次实际跑过的自查项，写进报告末尾。"""
    names = ["正文数字都有出处", "解读对应当前财报包"]
    if zones:
        names.append("三档价格与仓位")
    return names + ["数据截至最近交易日", "没有空话", "四个视角齐全、矛盾已写明", "缺失字段注明原因"]


@dataclass
class Issue:
    check: str
    message: str
    evidence: str
    fix: str


def self_review(pack: EarningsPack, notes: Notes, zones: dict | None = None) -> list[Issue]:
    issues: list[Issue] = []

    # 2. 解读必须对应当前这份财报包
    if notes.pack_hash != pack.pack_hash:
        issues.append(Issue(
            "STALE_NOTES", "解读依据的不是当前这份财报包",
            f"解读写的是 {notes.pack_hash}，当前财报包是 {pack.pack_hash}",
            "按当前财报包重写解读，并更新开头的 pack_hash。",
        ))

    # 1. 正文里的数字都要有出处
    for f in find_numbers(notes.body, pack.items):
        if f.item is None:
            issues.append(Issue(
                "UNSOURCED_NUMBER", f"“{f.text}”在财报包里找不到出处", f.text,
                "删掉这个数字，或先把它补进数据再写。",
            ))

    # 3. 三档买点（切片 2 起才有）
    if zones:
        price = pack.item("price_close").value
        tiers = [t["high"] for t in zones.get("tiers", [])]
        if any(h >= price for h in tiers) or tiers != sorted(tiers, reverse=True):
            issues.append(Issue("ZONES", "三档价格必须低于最新收盘且逐档递减", str(tiers), "重新运行 sd zones。"))
        if abs(sum(t["size"] for t in zones.get("tiers", [])) - 1) > 1e-6:
            issues.append(Issue("ZONES", "三档仓位合计不是 100%", "", "重新运行 sd zones。"))

    # 4. 数据截至最近一个交易日
    price = pack.item("price_close") if pack.has("price_close") else None
    expected = last_trading_day(date.fromisoformat(pack.as_of), pack.market).isoformat()
    if price is None or price.missing:
        issues.append(Issue("DATA_DATE", "缺收盘价，写不出“数据截至”", pack.as_of, "补抓最近一个交易日的收盘价。"))
    elif price.period != expected:
        issues.append(Issue(
            "DATA_DATE", "收盘价不是最近一个交易日的", f"收盘价日期 {price.period}，应为 {expected}",
            "重新取价格。",
        ))

    # 5. 不准用空话
    for phrase in BANNED_PHRASES:
        if phrase in notes.body:
            issues.append(Issue(
                "VAGUE", f"出现空话“{phrase}”", phrase, "换成具体的数字或判断，例如哪项指标、比预期高多少。",
            ))

    # 6. 四个视角都要写，估值和趋势相反时要写出矛盾
    for lens in LENSES:
        if notes.lenses.get(lens) not in STANCES:
            issues.append(Issue(
                "LENSES", f"缺少“{lens}”视角的结论", str(notes.lenses),
                f"在开头写 视角-{lens}: 看多 / 看空 / 中性。",
            ))
    if {notes.lenses.get("价值"), notes.lenses.get("趋势")} == {"看多", "看空"}:
        if "## 矛盾" not in notes.body:
            issues.append(Issue(
                "CONTRADICTION", "估值视角和趋势视角结论相反，但正文没有“矛盾”一段",
                f"价值：{notes.lenses.get('价值')}，趋势：{notes.lenses.get('趋势')}",
                "加一段“## 矛盾”，写清两者冲突在哪、怎么处理。",
            ))
    return issues


def raise_if_failed(issues: list[Issue]) -> None:
    if not issues:
        return
    checks = {i.check for i in issues}
    if "STALE_NOTES" in checks:
        code = ErrorCode.STALE_NOTES
    elif "UNSOURCED_NUMBER" in checks:
        code = ErrorCode.UNSOURCED_NUMBER
    else:
        code = ErrorCode.SELF_REVIEW_FAILED
    summary = "；".join(i.message for i in issues[:5])
    raise StockdeskError(code, f"出报告前自查没通过：{summary}", {"issues": [asdict(i) for i in issues]})
