"""在解读正文里找数字，并到财报包里找它的出处。

只检查“像财务数字”的写法：带单位（%、个百分点、B、M、亿、万）、带小数点、或带 $。
“2 个交易日”“Q3”“14A”这类不带单位的整数不检查。
比对时按写出来的精度留余量：写 16.5B 就允许 ±0.05B，写 9% 就允许 ±0.5 个百分点。
正负号通常用文字表达（“低于”“下降”），所以比较绝对值。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from stockdesk.shared.models import MONEY_UNITS, PER_SHARE_UNITS, RATIO_UNITS, PackItem

NUMBER_RE = re.compile(
    r"(?<![\w.])(?P<prefix>HK\$|\$)?\s?"
    r"(?P<a>\d+(?:\.\d+)?)"
    r"(?:\s?[–—~\-至到]\s?(?P<b>\d+(?:\.\d+)?))?"
    r"\s?(?P<unit>%|个百分点|pt|B|M|亿|万)?"
    r"(?![A-Za-z0-9.])"
)

SCALE = {"B": 1e9, "M": 1e6, "亿": 1e8, "万": 1e4}
PERCENT_UNITS = {"%", "个百分点", "pt"}


@dataclass
class Found:
    text: str
    start: int
    end: int
    item: PackItem | None


def _decimals(s: str) -> int:
    return len(s.split(".")[1]) if "." in s else 0


def _match(raw: str, unit: str | None, items: list[PackItem]) -> PackItem | None:
    x = float(raw)
    step = 0.5 * 10 ** (-_decimals(raw)) + 1e-12
    numeric = [it for it in items if isinstance(it.value, (int, float)) and not it.missing and it.sources]
    if unit in PERCENT_UNITS:
        cands = [it for it in numeric if it.unit in RATIO_UNITS]
        return next((it for it in cands if abs(abs(it.value) * 100 - x) <= step), None)
    if unit in SCALE:
        scale = SCALE[unit]
        cands = [it for it in numeric if it.unit in MONEY_UNITS]
        return next((it for it in cands if abs(abs(it.value) / scale - x) <= step), None)
    cands = [it for it in numeric if it.unit in PER_SHARE_UNITS | MONEY_UNITS]
    return next((it for it in cands if abs(abs(it.value) - x) <= step), None)


def find_numbers(text: str, items: list[PackItem]) -> list[Found]:
    found: list[Found] = []
    for m in NUMBER_RE.finditer(text):
        unit, prefix = m.group("unit"), m.group("prefix")
        a, b = m.group("a"), m.group("b")
        checkable = unit or prefix or "." in a or (b is not None and "." in b)
        if not checkable:
            continue
        parts = [("a", a)] + ([("b", b)] if b is not None else [])
        for i, (name, raw) in enumerate(parts):
            start, end = m.span(name)
            if i == 0 and prefix:
                start = m.start("prefix")
            if i == len(parts) - 1:
                end = m.end()  # 最后一个数字带上单位
            found.append(Found(text[start:end].strip(), start, end, _match(raw, unit, items)))
    return found
