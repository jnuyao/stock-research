"""[DATA] 各来源的取数代码。每个来源分两半：download_*（联网）和 parse_*（只处理已下载的内容，可离线测试）。"""

from . import akshare_hk, fred, hkex, sec, stockanalysis, yahoo
from .base import Context, Records, SourceError

# 来源 → 数据种类 → 取数函数
ADAPTERS = {
    "yahoo": {"price": yahoo.price, "fx": yahoo.fx, "consensus": yahoo.consensus, "macro": yahoo.macro},
    "stockanalysis": {"price": stockanalysis.price},
    "akshare": {"price": akshare_hk.price},
    "sec": {"fundamentals": sec.fundamentals, "filing": sec.filings},
    "hkex": {"filing": hkex.filings},
    "fred": {"macro": fred.macro},
}

__all__ = ["ADAPTERS", "Context", "Records", "SourceError"]
