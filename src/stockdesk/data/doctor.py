"""[DATA] 网络预检：现在是云端还是 Mac，各来源连不连得上，缺不缺要装的包。

结果写进 data/network-profile.json，`sd fetch` 按它选来源。
云端的 Python 联网被拦，预检会明确提示改用 WebFetch 抓网页再 `sd import`。
"""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .sources import SourceDef
from .store import iso, utc_now

PROFILE_NAME = "network-profile.json"
PROFILE_MAX_AGE = timedelta(hours=6)
SEC_CONTACT_ENV = "STOCKDESK_SEC_CONTACT"
USER_AGENT = "stockdesk/0.1 (personal research tool; https://github.com/jnuyao/stock-research)"

ADVICE_BLOCKED = (
    "这台机器连不上行情和公告来源（云端的 Python 联网被拦）。请用 WebFetch 抓网页"
    "（stockanalysis、SEC 原文、披露易公告、公司 IR），按快照格式存成 JSON，再运行 `sd import <代码> <文件>`；"
    "补不到的非关键字段用 `sd import <代码> --gap-ack 字段=原因` 登记。"
)


def environment() -> str:
    if os.environ.get("CLAUDE_CODE_REMOTE") == "true":
        return "cloud"
    if sys.platform == "darwin":
        return "mac"
    return "other"


def sec_contact() -> str | None:
    """SEC 联系方式：先看环境变量，再看项目根目录的 .env（.env 不提交到仓库）。只放进请求头，不打印。"""
    value = os.environ.get(SEC_CONTACT_ENV, "").strip()
    if not value and Path(".env").exists():
        for line in Path(".env").read_text(encoding="utf-8").splitlines():
            key, sep, val = line.partition("=")
            if sep and key.strip().removeprefix("export ").strip() == SEC_CONTACT_ENV:
                value = val.strip().strip("'\"")
    return value or None


def probe(url: str, headers: dict[str, str] | None = None) -> tuple[bool, str]:
    """只看网络通不通：对方回了任何 HTTP 响应都算通（是否拒绝抓取，由取数时的结果说明）。"""
    try:
        import httpx

        resp = httpx.get(url, headers={"User-Agent": USER_AGENT, **(headers or {})}, timeout=8.0,
                         follow_redirects=True)
    except Exception as err:  # noqa: BLE001  任何连接问题都记为连不上，原因写进结果
        return False, f"{type(err).__name__}: {str(err)[:160]}"
    return True, f"HTTP {resp.status_code}"


def doctor(sources: list[SourceDef], root: Path, now: datetime | None = None) -> dict[str, Any]:
    now = now or utc_now()
    env = environment()
    contact = sec_contact()
    result: dict[str, dict[str, Any]] = {}
    for s in sources:
        missing = [m for m in s.needs if importlib.util.find_spec(m) is None]
        headers = {"User-Agent": f"stockdesk/0.1 {contact}"} if s.id == "sec" and contact else None
        ok, detail = probe(s.probe, headers)
        result[s.id] = {
            "name": s.name, "kinds": s.kinds, "markets": s.markets, "reachable": ok, "detail": detail,
            "missing_packages": missing, "usable": ok and not missing, "where": s.where,
        }
    can_fetch = any(r["usable"] and "price" in r["kinds"] for r in result.values())
    profile = {
        "environment": env,
        "checked_at": iso(now),
        "python": platform.python_version(),
        "sources": result,
        "can_fetch": can_fetch,
        "sec_contact": "set" if contact else "missing",
        "advice": _advice(env, result, can_fetch, contact),
    }
    path = Path(root) / PROFILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return profile


def load_network_profile(root: Path, now: datetime | None = None) -> dict[str, Any] | None:
    """读上次的预检结果；换了环境或超过 6 小时就当作没有，需要重新预检。"""
    path = Path(root) / PROFILE_NAME
    if not path.exists():
        return None
    try:
        prof = json.loads(path.read_text(encoding="utf-8"))
        checked = datetime.fromisoformat(prof["checked_at"].replace("Z", "+00:00"))
    except (ValueError, KeyError, json.JSONDecodeError):
        return None
    if prof.get("environment") != environment() or (now or utc_now()) - checked > PROFILE_MAX_AGE:
        return None
    return prof


def _advice(env: str, result: dict[str, dict[str, Any]], can_fetch: bool, contact: str | None) -> str:
    if not can_fetch:
        return ADVICE_BLOCKED
    lines = []
    ok = [sid for sid, r in result.items() if r["usable"]]
    down = [sid for sid, r in result.items() if not r["usable"]]
    lines.append(f"可以直连：{'、'.join(ok)}。用 `sd fetch <代码>` 取数。")
    for sid in down:
        r = result[sid]
        why = f"缺少 {', '.join(r['missing_packages'])}（pip install -e '.[mac]'）" if r["missing_packages"] \
            else "连不上"
        lines.append(f"{sid}：{why}；这部分数据改用 WebFetch 抓网页后 `sd import`。")
    if not contact:
        lines.append(f"SEC 要求请求头带联系方式：在环境变量 {SEC_CONTACT_ENV} 里写“姓名 邮箱”（不会打印或记录）。")
    if env == "cloud":
        lines.append("这是云端会话，直连结果可能随网络策略变化。")
    return "\n".join(lines)
