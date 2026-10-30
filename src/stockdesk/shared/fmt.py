"""数字格式化：报告和命令行摘要共用，保证同一个数字在各处写法一致。"""

from __future__ import annotations

from .models import MONEY_UNITS, PER_SHARE_UNITS


def money(value: float, unit: str = "USD") -> str:
    sign = "−" if value < 0 else ""
    v = abs(value)
    prefix = "$" if unit == "USD" else "HK$"
    if v >= 1e9:
        return f"{sign}{prefix}{_trim(v / 1e9, 2)}B"
    if v >= 1e6:
        return f"{sign}{prefix}{v / 1e6:.0f}M"
    return f"{sign}{prefix}{v:,.2f}"


def _trim(x: float, places: int) -> str:
    return f"{x:.{places}f}".rstrip("0").rstrip(".")


def ratio(value: float, signed: bool = False) -> str:
    pct = value * 100
    text = f"{abs(pct):.1f}%"
    if signed:
        return ("+" if pct >= 0 else "−") + text
    return ("−" if pct < 0 else "") + text


def points(value: float) -> str:
    pt = value * 100
    return ("+" if pt >= 0 else "−") + f"{abs(pt):.1f} 个百分点"


def show(value: float | str | None, unit: str, key: str = "") -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        return value
    if unit in MONEY_UNITS:
        return money(value, unit)
    if unit in PER_SHARE_UNITS:
        prefix = "$" if unit.startswith("USD") else "HK$"
        return ("−" if value < 0 else "") + f"{prefix}{abs(value):.2f}"
    if unit == "pt":
        return points(value)
    if unit == "ratio":
        return ratio(value, signed=key.endswith(("_yoy", "_pct")))
    return f"{value:g}"
