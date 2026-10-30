"""测试公共工具：在仓库根目录用子进程跑 `python -m stockdesk`，返回退出码和输出。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "tests" / "cases"


@dataclass
class CliResult:
    code: int
    stdout: str
    stderr: str

    def json(self) -> dict:
        return json.loads(self.stdout)


def run_cli(*args: str, cwd: Path = ROOT) -> CliResult:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-m", "stockdesk", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return CliResult(proc.returncode, proc.stdout, proc.stderr)


@pytest.fixture
def cli():
    return run_cli


def make_variant(tmp_path: Path, base: str, name: str, mutate) -> Path:
    """把固定案例复制到临时目录做成变体，返回可以当作 cwd 的目录（含 config/）。

    mutate(case_dir) 直接改复制出来的文件。原案例不动。
    """
    shutil.copytree(ROOT / "config", tmp_path / "config", dirs_exist_ok=True)
    target = tmp_path / "tests" / "cases" / name
    shutil.copytree(CASES / base, target)
    mutate(target)
    return tmp_path


def edit_json(path: Path, fn) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(fn(data), ensure_ascii=False, indent=1), encoding="utf-8")


TOLERANCE = 0.05  # 与人工版本对照的允许偏差（AT-3、AT-12）
ACCEPTED_DRIFT = 0.005  # 认可过的偏差，规则结果再变动超过这个比例就要重新确认


def compare_with_manual(plan: dict, manual: dict) -> list[str]:
    """逐档对照人工版本，返回超出 5% 且没被你认可的差异（带原因）。"""
    accepted = {d["tier"]: d for d in manual.get("accepted_deviations", [])}
    ours = {t["name"]: t for t in plan["tiers"]}
    problems = []
    for name, (lo, hi) in manual["tiers"].items():
        t = ours.get(name)
        if t is None:
            problems.append(f"{name} 档：规则没有给出这一档（{plan.get('reserved', {}).get('reason', '')}）")
            continue
        dev = max(abs(t["low"] - lo) / lo, abs(t["high"] - hi) / hi)
        if dev <= TOLERANCE:
            continue
        ok = accepted.get(name)
        if ok is None:
            problems.append(
                f"{name} 档：规则 {t['low']:.2f}–{t['high']:.2f}，人工 {lo}–{hi}，偏差 {dev:.1%}；"
                f"规则锚点 {t['anchor']['label']} {t['anchor']['value']:.2f}"
            )
            continue
        # 认可的是当时规则给出的那个具体区间；规则结果再变，要重新确认
        rlo, rhi = ok["rule"]
        if max(abs(t["low"] - rlo) / rlo, abs(t["high"] - rhi) / rhi) > ACCEPTED_DRIFT:
            problems.append(
                f"{name} 档：认可过的规则结果是 {rlo}–{rhi}（{ok['date']}），现在变成 "
                f"{t['low']:.2f}–{t['high']:.2f}，需要重新确认"
            )
    inv = plan["invalidation"]["level"]
    dev = abs(inv - manual["invalidation"]) / manual["invalidation"]
    if dev > TOLERANCE and "invalidation" not in accepted:
        problems.append(
            f"失效位：规则 {inv:.2f}，人工 {manual['invalidation']}，偏差 {dev:.1%}；{plan['invalidation']['basis']}"
        )
    return problems
