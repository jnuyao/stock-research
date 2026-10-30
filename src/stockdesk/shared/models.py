"""公共数据模型：快照里的一条事实、财报包里的一项，以及财报包本身。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

# 单位：USD 金额（原值，不缩写）、ratio 比例（小数）、USD/share 每股、pt 百分点差（小数）、text 文字
MONEY_UNITS = {"USD", "HKD"}
PER_SHARE_UNITS = {"USD/share", "HKD/share"}
RATIO_UNITS = {"ratio", "pt"}


@dataclass(frozen=True)
class Fact:
    """快照里的一条数据。value 为 None 表示确认缺失（必须写 gap_ack 原因）。"""

    ticker: str
    field: str
    period: str
    value: float | None
    unit: str
    source_url: str
    as_of: str
    fetched_at: str
    via: str = "fetch"
    gap_ack: str | None = None
    note: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Fact:
        known = {k: d.get(k) for k in cls.__dataclass_fields__}
        return cls(**known)


@dataclass(frozen=True)
class Source:
    url: str
    as_of: str


@dataclass
class PackItem:
    """财报包里的一项。derived_from 非空时表示由其他项计算得出，来源沿用输入项。"""

    key: str
    label: str
    value: float | str | None
    unit: str
    period: str
    sources: list[Source] = field(default_factory=list)
    derived_from: list[str] = field(default_factory=list)
    missing: bool = False
    gap_ack: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EarningsPack:
    ticker: str
    quarter: str
    next_quarter: str
    as_of: str
    market: str
    items: list[PackItem]

    def item(self, key: str) -> PackItem:
        for it in self.items:
            if it.key == key:
                return it
        raise KeyError(key)

    def has(self, key: str) -> bool:
        return any(it.key == key for it in self.items)

    @property
    def pack_hash(self) -> str:
        """财报包指纹：只看代码、季度和每一项的数值，数值变了指纹就变。"""
        core = {
            "ticker": self.ticker,
            "quarter": self.quarter,
            "items": sorted(
                [it.key, it.period, it.value if not isinstance(it.value, float) else round(it.value, 10)]
                for it in self.items
            ),
        }
        raw = json.dumps(core, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "quarter": self.quarter,
            "next_quarter": self.next_quarter,
            "as_of": self.as_of,
            "market": self.market,
            "pack_hash": self.pack_hash,
            "items": [it.to_dict() for it in self.items],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EarningsPack:
        items = [
            PackItem(**{**it, "sources": [Source(**s) for s in it.get("sources", [])]})
            for it in d["items"]
        ]
        return cls(d["ticker"], d["quarter"], d["next_quarter"], d["as_of"], d["market"], items)
