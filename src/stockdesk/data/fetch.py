"""[DATA] 直连取数（Mac 上用）。按来源登记和网络预检选来源，每个来源只试一次。

同一类数据有两个来源都能连时都抓，交给 [QA] 交叉核对；失败的原因写进抓取日志，缺的字段交给 [QA] 判断能否继续。
一个能连的来源都没有时返回 SOURCE_BLOCKED，提示改用 WebFetch 抓网页再 `sd import`。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from stockdesk.shared.calendar import last_closed_session
from stockdesk.shared.errors import ErrorCode, StockdeskError
from stockdesk.shared.models import CompanyProfile

from .adapters import ADAPTERS, Context, Records
from .doctor import environment, sec_contact
from .sources import SourceDef
from .store import append_log, fact_record, iso, series_record, utc_now, write_snapshot

DEFAULT_KINDS = ["price", "fundamentals", "consensus", "filing", "macro"]


def fetch(ticker: str, profile: CompanyProfile, sources: list[SourceDef], network: dict[str, Any], root: Path,
          kinds: list[str] | None = None, now: datetime | None = None) -> dict[str, Any]:
    ticker = ticker.upper()
    now = now or utc_now()
    kinds = list(kinds or DEFAULT_KINDS)
    if profile.report_currency != profile.price_currency and "price" in kinds and "fx" not in kinds:
        kinds.insert(kinds.index("price") + 1, "fx")  # 货币不同时估值要用当日汇率
    status = network.get("sources", {})

    plan: dict[str, list[SourceDef]] = {}
    blocked: set[str] = set()
    for kind in kinds:
        cands = [s for s in sources if kind in s.kinds and profile.market in s.markets and s.id in ADAPTERS]
        plan[kind] = [s for s in cands if status.get(s.id, {}).get("usable")]
        blocked |= {s.id for s in cands if not status.get(s.id, {}).get("usable")}
    if not any(plan.values()):
        raise StockdeskError(
            ErrorCode.SOURCE_BLOCKED,
            f"{ticker}：这台机器（{network.get('environment', environment())}）连不上任何一个来源："
            f"{'、'.join(sorted(blocked))}",
            {"environment": network.get("environment"), "blocked": sorted(blocked),
             "checked_at": network.get("checked_at")},
        )

    as_of = last_closed_session(now, profile.market)
    ctx = Context(ticker, profile, now, as_of, sec_contact())
    day = now.date().isoformat()
    coverage: dict[str, list[dict[str, Any]]] = {k: [] for k in kinds}
    failures: list[dict[str, Any]] = []
    files: list[str] = []
    for kind in kinds:
        if not plan[kind]:
            failures.append({"kind": kind, "source": None,
                             "error": "没有能连的来源，改用 WebFetch 抓网页后 `sd import`"})
            continue
        for s in plan[kind]:
            try:
                got: Records = ADAPTERS[s.id][kind](ctx)
            except Exception as err:  # noqa: BLE001  任何失败都只记原因，不重试，不中断其他来源
                failures.append({"kind": kind, "source": s.id, "error": f"{type(err).__name__}: {str(err)[:300]}"})
                continue
            written = _write(root, ticker, day, f"{s.id}-{kind}", got, now)
            files += [str(p) for p in written]
            coverage[kind].append({
                "source": s.id,
                "fields": sorted({f.field for f in got.facts} | {x.field for x in got.series}),
                "dates": sorted({f.period for f in got.facts if f.field.startswith(("price", "fx", "macro"))}
                                | {x.rows[-1][0] for x in got.series if x.rows})[-1:],
            })
    result = {
        "ticker": ticker, "environment": network.get("environment"), "as_of": as_of.isoformat(),
        "fetched_at": iso(now), "snapshot_dir": str(Path(root) / "snapshots" / ticker / day),
        "files": files, "coverage": coverage, "failures": failures,
    }
    append_log(root, ticker, day, {k: result[k] for k in ("fetched_at", "as_of", "coverage", "failures")})
    return result


def _write(root: Path, ticker: str, day: str, name: str, got: Records, now: datetime) -> list[Path]:
    out = []
    if got.facts:
        out.append(write_snapshot(root, ticker, day, name, [fact_record(f) for f in got.facts], now))
    for s in got.series:
        out.append(write_snapshot(root, ticker, day, f"{name}-{s.field}", series_record(s), now))
    return out
