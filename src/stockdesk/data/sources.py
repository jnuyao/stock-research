"""[DATA] 来源登记（config/sources.toml）。"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from stockdesk.shared.errors import ErrorCode, StockdeskError


@dataclass(frozen=True)
class SourceDef:
    id: str
    name: str
    probe: str
    kinds: list[str]
    markets: list[str]
    priority: int = 9
    needs: list[str] = field(default_factory=list)
    where: str = ""


def load_sources(path: Path) -> list[SourceDef]:
    path = Path(path)
    if not path.exists():
        raise StockdeskError(ErrorCode.BAD_INPUT, f"找不到来源登记 {path}（要在项目根目录运行 sd）")
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    out = []
    for sid, d in raw.items():
        known = {k: v for k, v in d.items() if k in SourceDef.__dataclass_fields__}
        out.append(SourceDef(id=sid, **known))
    return sorted(out, key=lambda s: (s.priority, s.id))
