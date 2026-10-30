"""[CLI] 命令行 sd：解析参数，调用对应模块。

加 --json 时只输出 JSON（给 Claude 技能读）；不加时输出简短中文摘要（给人看）。
加 --replay <案例> 时只读 tests/cases/<案例>/ 里的固定快照，不联网。
出错时打印错误码、原因和下一步，退出码为 1。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from stockdesk.earnings import build_pack
from stockdesk.report import parse_notes, render_report, self_review, summary_line
from stockdesk.shared.calendar import last_trading_day
from stockdesk.shared.errors import ErrorCode, StockdeskError
from stockdesk.shared.fmt import show
from stockdesk.shared.models import EarningsPack

CASES_DIR = Path("tests/cases")
DATA_DIR = Path("data")
REPORTS_DIR = Path("reports")

# 后面切片才实现的命令：先占位，调用时明确告诉用户还没做
LATER = {
    "doctor": "SL-3", "fetch": "SL-3", "import": "SL-3", "preview": "SL-4",
    "zones": "SL-2", "watch": "SL-4", "check": "SL-4",
}


@dataclass
class Source:
    """这次运行从哪里读数据：回放案例或本机 data/ 目录。"""

    root: Path
    as_of: str
    market: str
    case: dict[str, Any]


def _resolve(replay: str | None, as_of: str | None, ticker: str) -> Source:
    if replay:
        root = CASES_DIR / replay
        case_file = root / "case.json"
        if not case_file.exists():
            known = sorted(p.name for p in CASES_DIR.glob("*") if (p / "case.json").exists())
            raise StockdeskError(
                ErrorCode.BAD_INPUT, f"找不到回放案例 {replay}（找的是 {case_file}）",
                {"known_cases": known},
            )
        case = json.loads(case_file.read_text(encoding="utf-8"))
        return Source(root, as_of or case["as_of"], case.get("market", "US"), case)
    market = "HK" if ticker.upper().endswith(".HK") else "US"
    day = as_of or last_trading_day(date.today(), market).isoformat()
    return Source(DATA_DIR, day, market, {})


def _pack(args: argparse.Namespace) -> EarningsPack:
    src = _resolve(args.replay, args.as_of, args.ticker)
    return build_pack(args.ticker, args.quarter, src.as_of, root=src.root, market=src.market)


def _print_pack(pack: EarningsPack) -> None:
    print(summary_line(pack))
    print(f"财报包指纹 pack_hash：{pack.pack_hash}（写解读时填在开头）")
    for it in pack.items:
        value = "—（" + (it.gap_ack or "缺失") + "）" if it.missing else show(it.value, it.unit, it.key)
        print(f"  {it.label:<16} {it.period:<10} {value}")


def cmd_pack(args: argparse.Namespace) -> dict[str, Any]:
    pack = _pack(args)
    if not args.json:
        _print_pack(pack)
    return pack.to_dict()


def cmd_report(args: argparse.Namespace) -> dict[str, Any]:
    pack = _pack(args)
    notes_path = Path(args.notes)
    if not notes_path.exists():
        raise StockdeskError(ErrorCode.BAD_INPUT, f"找不到解读文件 {notes_path}")
    path = render_report(pack, notes_path.read_text(encoding="utf-8"), Path(args.out))
    if not args.json:
        print(summary_line(pack))
        print(f"报告已生成：{path}")
    return {"report": str(path), "pack": str(path.with_name("pack.json")), "pack_hash": pack.pack_hash}


def cmd_demo(args: argparse.Namespace) -> dict[str, Any]:
    """用固定案例跑完 pack → 自查 → report，并演示几种会被拒绝的解读。"""
    src = _resolve(args.case, None, "")
    case = src.case
    pack = build_pack(case["ticker"], case["quarter"], src.as_of, root=src.root, market=src.market)
    notes_file = src.root / case.get("notes", "notes/ok.md")
    path = render_report(pack, notes_file.read_text(encoding="utf-8"), Path(args.out))

    refused = []
    for other in sorted(notes_file.parent.glob("*.md")):
        if other == notes_file:
            continue
        issues = self_review(pack, parse_notes(other.read_text(encoding="utf-8")))
        refused.append({"notes": other.name, "issues": [i.message for i in issues]})

    if not args.json:
        print(f"案例 {args.case}：{case.get('description', '')}")
        print(f"① 财报包：{len(pack.items)} 项，指纹 {pack.pack_hash}")
        print(f"   {summary_line(pack)}")
        print(f"② 自查通过，报告已生成：{path}")
        print("③ 同一份财报包，换成有问题的解读会被拒绝：")
        for r in refused:
            print(f"   {r['notes']:<22} {'；'.join(r['issues']) or '（没被拒绝，检查规则有漏洞）'}")
    return {"report": str(path), "pack_hash": pack.pack_hash, "items": len(pack.items), "refused": refused}


def cmd_later(args: argparse.Namespace) -> dict[str, Any]:
    raise StockdeskError(
        ErrorCode.NOT_YET_BUILT, f"sd {args.command} 属于切片 {LATER[args.command]}，还没实现",
        {"command": args.command, "slice": LATER[args.command]},
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sd", description="股票研究台：财报解读与分档买点（不构成投资建议）")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--json", action="store_true", help="只输出 JSON")
        sp.add_argument("--replay", metavar="案例", help="只读 tests/cases/<案例>/ 的固定快照")
        sp.add_argument("--as-of", dest="as_of", metavar="YYYY-MM-DD", help="数据日期，默认最近一个交易日")

    sp = sub.add_parser("pack", help="组装财报包")
    sp.add_argument("ticker")
    sp.add_argument("--quarter", required=True, metavar="2026Q3")
    common(sp)
    sp.set_defaults(func=cmd_pack)

    sp = sub.add_parser("report", help="自查后合成 HTML 报告")
    sp.add_argument("ticker")
    sp.add_argument("--quarter", required=True, metavar="2026Q3")
    sp.add_argument("--notes", required=True, help="Claude 写的解读（Markdown）")
    sp.add_argument("--out", default=str(REPORTS_DIR), help="报告归档目录，默认 reports/")
    common(sp)
    sp.set_defaults(func=cmd_report)

    sp = sub.add_parser("demo", help="用固定案例跑完 pack → report")
    sp.add_argument("case")
    sp.add_argument("--out", default=str(REPORTS_DIR))
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_demo)

    for name, slice_id in LATER.items():
        sp = sub.add_parser(name, help=f"（切片 {slice_id} 实现）")
        sp.add_argument("rest", nargs="*")
        sp.add_argument("--json", action="store_true")
        sp.set_defaults(func=cmd_later)
    return p


def _print_error(err: StockdeskError) -> None:
    d = err.to_dict()
    print(f"出错了 [{d['code']}]：{d['message']}", file=sys.stderr)
    for gap in d["details"].get("gaps", []):
        print(f"  缺 {gap['field']}（{gap['period']}）：去 {gap['where']} 找", file=sys.stderr)
    for issue in d["details"].get("issues", []):
        print(f"  - {issue['message']}（{issue['evidence']}）→ {issue['fix']}", file=sys.stderr)
    print(f"下一步：{d['next_step']}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = args.func(args)
    except StockdeskError as err:
        if args.json:
            print(json.dumps({"error": err.to_dict()}, ensure_ascii=False, indent=2))
        else:
            _print_error(err)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
