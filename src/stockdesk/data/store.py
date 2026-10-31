"""[DATA] 快照写入：data/snapshots/<代码>/<日期>/ 下的 JSON，只追加，不覆盖已有文件。"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from stockdesk.shared.models import Fact, Series

# 设了这个环境变量就把 data/ 放到别处（例如云端的项目共享文件夹，让不同会话共用快照）
DATA_ENV = "STOCKDESK_DATA"

FACT_KEYS = ["ticker", "field", "period", "value", "unit", "source_url", "as_of", "fetched_at", "via", "gap_ack",
             "note"]


def data_root() -> Path:
    return Path(os.environ.get(DATA_ENV) or "data").resolve()


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def fact_record(f: Fact) -> dict[str, Any]:
    return {k: getattr(f, k) for k in FACT_KEYS}


def series_record(s: Series) -> dict[str, Any]:
    return s.to_dict()


def write_snapshot(root: Path, ticker: str, day: str, name: str, payload: list | dict, now: datetime) -> Path:
    """写一个新文件；同名文件已存在时加序号，绝不覆盖。"""
    folder = Path(root) / "snapshots" / ticker.upper() / day
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"{now:%H%M%S}-{name}"
    text = _dump(payload)
    for n in range(1, 1000):
        path = folder / (f"{stem}.json" if n == 1 else f"{stem}-{n}.json")
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path
    raise RuntimeError(f"{folder} 里同名快照太多")


def append_log(root: Path, ticker: str, day: str, entry: dict[str, Any]) -> Path:
    """抓取日志（成功和失败的原因），按行追加；不是 .json，所以 [QA] 读快照时不会把它当数据。"""
    folder = Path(root) / "snapshots" / ticker.upper() / day
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "fetch-log.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def _dump(payload: list | dict) -> str:
    """和测试案例里的快照一样的排版：日线一行一天，其余缩进一格。"""
    if isinstance(payload, dict) and "rows" in payload:
        head = {k: v for k, v in payload.items() if k != "rows"}
        body = json.dumps(head, ensure_ascii=False, indent=1)[:-2]
        rows = ",\n".join("  " + json.dumps(r, ensure_ascii=False) for r in payload["rows"])
        return f'{body},\n "rows": [\n{rows}\n ]\n}}\n'
    return json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
