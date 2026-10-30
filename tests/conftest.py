"""测试公共工具：在仓库根目录用子进程跑 `python -m stockdesk`，返回退出码和输出。"""

from __future__ import annotations

import json
import os
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
