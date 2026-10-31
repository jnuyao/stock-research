"""[DATA] 导入 Claude 抓好的网页数据（云端取数的唯一入口）。

校验字段名、单位、日期格式和来源；有一行不对就整份拒绝，什么都不写，并逐行说明怎么改。
通过后写成和 fetch 一样格式的快照（via 记为 import）。
"""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from stockdesk.shared.errors import ErrorCode, StockdeskError
from stockdesk.shared.models import MONEY_UNITS, PER_SHARE_UNITS, RATIO_UNITS, Fact, Series

from .store import fact_record, iso, series_record, utc_now, write_snapshot

UNITS = MONEY_UNITS | PER_SHARE_UNITS | RATIO_UNITS | {"x", "text", "index", "HKD/USD", "USD/HKD", "count"}
FIELD_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[A-Za-z0-9_]+)*$")
PERIOD_RE = re.compile(r"^(\d{4}Q[1-4]|FY\d{4}Q[1-4]|FY\d{4}|\d{4}|\d{4}-\d{2}-\d{2})$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ABBREV = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
MONEY_FLOOR = 1e6      # 公司财报里的金额都在百万以上；更小的多半是写成了 16.5（意思是 16.5B）。股价除外
RATIO_CEILING = 5.0    # 比例超过 5（即 500%）多半是把 44.1% 写成了 44.1


def import_json(ticker: str, path: Path, root: Path, today: date | None = None) -> dict[str, Any]:
    """校验并导入一个 JSON 文件：事实列表、一段序列，或 {"facts": [...], "series": [...]}。"""
    ticker = ticker.upper()
    path = Path(path)
    if not path.exists():
        raise StockdeskError(ErrorCode.BAD_INPUT, f"找不到要导入的文件 {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise StockdeskError(ErrorCode.BAD_INPUT, f"{path.name} 不是合法的 JSON：{err}") from err
    today = today or date.today()

    if isinstance(raw, list):
        fact_rows, series_rows = raw, []
    elif isinstance(raw, dict) and ("facts" in raw or "series" in raw):
        fact_rows, series_rows = raw.get("facts", []), raw.get("series", [])
    elif isinstance(raw, dict):
        fact_rows, series_rows = [], [raw]
    else:
        raise StockdeskError(ErrorCode.BAD_INPUT, f"{path.name} 的格式不认识：要么是事实列表，要么是一段序列")

    problems: list[dict[str, Any]] = []
    facts = []
    for i, row in enumerate(fact_rows):
        msg = _check_fact(row, ticker, today) if isinstance(row, dict) else "每一行要是一个对象"
        if msg:
            problems.append({"row": i, "field": row.get("field") if isinstance(row, dict) else None, "message": msg})
        else:
            facts.append(_fact(row, ticker))
    series = []
    for i, row in enumerate(series_rows):
        msg = _check_series(row, ticker, today) if isinstance(row, dict) else "序列要是一个对象"
        if msg:
            problems.append({"series": i, "field": row.get("field") if isinstance(row, dict) else None,
                             "message": msg})
        else:
            series.append(Series.from_dict({**row, "ticker": ticker, "via": "import"}))
    if problems:
        first = problems[0]
        where = f"第 {first['row']} 行" if "row" in first else f"第 {first['series']} 段序列"
        raise StockdeskError(
            ErrorCode.BAD_INPUT,
            f"{path.name} 有 {len(problems)} 处不对，整份没有导入。{where}（{first['field']}）：{first['message']}",
            {"file": str(path), "problems": problems},
        )
    if not facts and not series:
        raise StockdeskError(ErrorCode.BAD_INPUT, f"{path.name} 里没有数据")
    return _write(ticker, root, facts, series, today)


def ack_gaps(ticker: str, specs: list[str], root: Path, as_of: str | None = None,
             today: date | None = None) -> dict[str, Any]:
    """登记确认缺失的字段：每条写成 字段[@期间]=原因，例如 peer_pe=同行 PE 这次没取到。"""
    ticker = ticker.upper()
    today = today or date.today()
    day = as_of or today.isoformat()
    now = iso(utc_now())
    facts = []
    for spec in specs:
        name, sep, reason = spec.partition("=")
        name, _, period = name.strip().partition("@")
        if not sep or not reason.strip() or not FIELD_RE.match(name):
            raise StockdeskError(
                ErrorCode.BAD_INPUT,
                f"--gap-ack 要写成 字段=原因 或 字段@期间=原因，例如 peer_pe=同行 PE 这次没取到；收到 {spec}",
            )
        period = period or day
        if not PERIOD_RE.match(period):
            raise StockdeskError(ErrorCode.BAD_INPUT,
                                 f"--gap-ack 里的期间 {period} 要写成 2026Q3、FY2027Q1 或 YYYY-MM-DD")
        facts.append(Fact(ticker, name, period, None, "text", "", day, now, "import", reason.strip()))
    return _write(ticker, root, facts, [], today, name="gap-ack")


def _write(ticker: str, root: Path, facts: list[Fact], series: list[Series], today: date,
           name: str = "import") -> dict[str, Any]:
    now = utc_now()
    day = today.isoformat()
    paths = []
    if facts:
        paths.append(write_snapshot(root, ticker, day, name, [fact_record(f) for f in facts], now))
    for s in series:
        paths.append(write_snapshot(root, ticker, day, f"{name}-{s.field}", series_record(s), now))
    return {
        "ticker": ticker,
        "path": str(paths[0]),
        "paths": [str(p) for p in paths],
        "facts": len(facts),
        "fields": sorted({f.field for f in facts}),
        "gap_acks": [{"field": f.field, "period": f.period, "reason": f.gap_ack} for f in facts if f.gap_ack],
        "series": [{"field": s.field, "rows": len(s.rows), "from": s.rows[0][0] if s.rows else None,
                    "to": s.rows[-1][0] if s.rows else None} for s in series],
    }


def _fact(row: dict[str, Any], ticker: str) -> Fact:
    d = {**row, "ticker": ticker, "via": "import"}
    if d.get("value") is not None:
        d["value"] = float(d["value"])
    return Fact.from_dict(d)


def _check_fact(row: dict[str, Any], ticker: str, today: date) -> str | None:
    if row.get("ticker") and str(row["ticker"]).upper() != ticker:
        return f"ticker 写的是 {row['ticker']}，和命令里的 {ticker} 不一致"
    name = row.get("field")
    if not isinstance(name, str) or not FIELD_RE.match(name):
        return f"field 写成 {name!r} 不对，要用小写英文字段名，例如 revenue、segment.DCAI.revenue"
    period = row.get("period")
    if not isinstance(period, str) or not PERIOD_RE.match(period):
        return f"period 写成 {period!r} 不对，要写 2026Q3、FY2027Q1 或 YYYY-MM-DD"
    unit = row.get("unit")
    if unit not in UNITS:
        return f"unit {unit!r} 不认识，可用：{', '.join(sorted(UNITS))}"
    value = row.get("value")
    if value is None:
        if not row.get("gap_ack"):
            return "value 为空时要写 gap_ack 说明为什么缺（或者用 sd import --gap-ack 登记）"
        return None
    msg = _check_value(value, unit, name)
    if msg:
        return msg
    url = row.get("source_url")
    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
        return "source_url 缺失：每个数字都要写来源网址"
    msg = _check_date(row.get("as_of"), "as_of", today)
    if msg:
        return msg
    return _check_fetched_at(row.get("fetched_at"))


def _check_value(value: Any, unit: str, name: str) -> str | None:
    if isinstance(value, str):
        m = re.fullmatch(r"\s*\$?(-?[\d,.]+)\s*([KMBT])\s*", value, re.I)
        if m:
            raw = float(m.group(1).replace(",", "")) * ABBREV[m.group(2).upper()]
            return f"金额要写原值、不缩写：{value} 要写成 {raw:.0f}"
        return f"value 要是数字，收到 {value!r}"
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        return f"value 要是数字，收到 {value!r}"
    if unit in MONEY_UNITS and not name.startswith("price") and 0 < abs(value) < MONEY_FLOOR:
        return f"金额要写原值、不缩写：{value} {unit} 看起来是缩写（例如 16.5B 要写成 16500000000）"
    if unit in RATIO_UNITS and abs(value) > RATIO_CEILING:
        return f"百分比要存小数：{value} 看起来是百分数（例如 44.1% 要写成 0.441）"
    return None


def _check_date(value: Any, name: str, today: date) -> str | None:
    if not isinstance(value, str) or not DATE_RE.match(value):
        return f"{name} 要写成 YYYY-MM-DD（页面上数据对应的日期），收到 {value!r}"
    try:
        day = date.fromisoformat(value)
    except ValueError:
        return f"{name} 不是有效日期：{value}"
    if day > today:
        return f"{name} {value} 晚于今天 {today}，日期写错了"
    return None


def _check_fetched_at(value: Any) -> str | None:
    if not isinstance(value, str):
        return "fetched_at 要写抓取时间，例如 2026-10-30T08:00:00Z"
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return f"fetched_at 要写成 2026-10-30T08:00:00Z 这样的时间，收到 {value!r}"
    return None


def _check_series(row: dict[str, Any], ticker: str, today: date) -> str | None:
    if row.get("ticker") and str(row["ticker"]).upper() != ticker:
        return f"ticker 写的是 {row['ticker']}，和命令里的 {ticker} 不一致"
    name = row.get("field")
    if not isinstance(name, str) or not FIELD_RE.match(name):
        return f"field 写成 {name!r} 不对"
    if row.get("unit") not in UNITS:
        return f"unit {row.get('unit')!r} 不认识，可用：{', '.join(sorted(UNITS))}"
    cols = row.get("columns")
    if not isinstance(cols, list) or not cols or cols[0] != "date":
        return "columns 第一列要是 date，例如 [\"date\", \"open\", \"high\", \"low\", \"close\", \"volume\"]"
    rows = row.get("rows")
    if not isinstance(rows, list) or not rows:
        return "rows 不能为空"
    seen = set()
    for r in rows:
        if not isinstance(r, list) or len(r) != len(cols):
            return f"每一行要有 {len(cols)} 个值（{', '.join(cols)}），这一行是 {r!r}"
        msg = _check_date(r[0], "日期", today)
        if msg:
            return msg
        if r[0] in seen:
            return f"日期 {r[0]} 出现了两次"
        seen.add(r[0])
        if row["unit"] != "text" and not all(isinstance(x, int | float) and not isinstance(x, bool) for x in r[1:]):
            return f"{r[0]} 这一行有非数字的值：{r!r}"
    url = row.get("source_url")
    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
        return "source_url 缺失：每段序列都要写来源网址"
    msg = _check_date(row.get("as_of"), "as_of", today)
    if msg:
        return msg
    return _check_fetched_at(row.get("fetched_at"))
