"""[CLI] 把预检、取数、导入的结果打印成给人看的中文摘要。"""

from __future__ import annotations

from typing import Any

ENV_NAMES = {"cloud": "云端会话", "mac": "Mac", "other": "其他机器"}
KIND_NAMES = {"price": "价格", "fx": "汇率", "fundamentals": "财报数字", "consensus": "一致预期",
              "filing": "公告链接", "macro": "宏观"}


def print_doctor(prof: dict[str, Any]) -> None:
    print(f"环境：{ENV_NAMES.get(prof['environment'], prof['environment'])}（Python {prof['python']}，"
          f"检查于 {prof['checked_at']}）")
    for sid, s in prof["sources"].items():
        mark = "能用" if s["usable"] else ("缺包" if s["reachable"] else "连不上")
        extra = f"，缺 {', '.join(s['missing_packages'])}" if s["missing_packages"] else ""
        print(f"  {mark:<4} {sid:<14} {s['name']}（{s['detail']}{extra}）")
    print(f"SEC 联系方式：{'已设置' if prof['sec_contact'] == 'set' else '未设置'}")
    print(prof["advice"])


def print_fetch(result: dict[str, Any]) -> None:
    print(f"{result['ticker']} 取数完成（{ENV_NAMES.get(result['environment'], result['environment'])}，"
          f"最近收盘日 {result['as_of']}）")
    for kind, got in result["coverage"].items():
        name = KIND_NAMES.get(kind, kind)
        if got:
            for g in got:
                latest = f"，最新 {g['dates'][0]}" if g["dates"] else ""
                print(f"  {name:<6} {g['source']:<14} {len(g['fields'])} 个字段{latest}")
        else:
            print(f"  {name:<6} 没取到")
    for f in result["failures"]:
        print(f"  失败：{KIND_NAMES.get(f['kind'], f['kind'])} {f['source'] or ''} {f['error']}")
    print(f"快照目录：{result['snapshot_dir']}")
    if result["failures"]:
        print("缺的数据可以用 WebFetch 抓网页后 `sd import` 补上；先跑 `sd pack` 或 `sd zones` 看数据守门要不要。")


def print_import(result: dict[str, Any]) -> None:
    if result["gap_acks"] and not result["series"] and len(result["gap_acks"]) == result["facts"]:
        for g in result["gap_acks"]:
            print(f"已登记缺失：{g['field']}（{g['period']}）——{g['reason']}")
        return
    parts = [f"{result['facts']} 条数据"] if result["facts"] else []
    parts += [f"{s['field']} {s['rows']} 行（{s['from']} 至 {s['to']}）" for s in result["series"]]
    print(f"{result['ticker']} 导入 {'，'.join(parts)}：{', '.join(result['paths'])}")
