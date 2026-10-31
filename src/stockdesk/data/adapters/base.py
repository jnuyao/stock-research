"""[DATA] 取数公共部分：一次调用的上下文、统一的失败类型、只试一次的 HTTP 请求。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from stockdesk.shared.models import CompanyProfile, Fact, Series

from ..store import iso

USER_AGENT = "stockdesk/0.1 (personal research tool; https://github.com/jnuyao/stock-research)"


class SourceError(Exception):
    """这个来源这次没取到。原因写进抓取日志，缺的字段交给 [QA] 判断能否继续。"""


@dataclass
class Records:
    facts: list[Fact] = field(default_factory=list)
    series: list[Series] = field(default_factory=list)


@dataclass
class Context:
    ticker: str
    profile: CompanyProfile
    now: datetime          # 带时区
    as_of: date            # 该市场最近一个已收盘的交易日
    sec_contact: str | None = None

    @property
    def fetched_at(self) -> str:
        return iso(self.now)

    def fact(self, field_name: str, period: str, value: float, unit: str, url: str, as_of: str,
             note: str | None = None) -> Fact:
        return Fact(self.ticker, field_name, period, float(value), unit, url, as_of, self.fetched_at, "fetch",
                    note=note)


def http_get(url: str, headers: dict[str, str] | None = None, params: dict[str, Any] | None = None,
             timeout: float = 30.0) -> Any:
    """只试一次；失败时抛 SourceError，说明对方返回了什么。"""
    import httpx

    try:
        resp = httpx.get(url, headers={"User-Agent": USER_AGENT, **(headers or {})}, params=params,
                         timeout=timeout, follow_redirects=True)
    except httpx.HTTPError as err:
        raise SourceError(f"连不上 {url}：{type(err).__name__}") from err
    if resp.status_code >= 400:
        raise SourceError(f"{url} 返回 HTTP {resp.status_code}")
    return resp
