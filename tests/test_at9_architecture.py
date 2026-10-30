"""[AT-9] 代码与架构图一致、内核不联网、不接券商。"""

from __future__ import annotations

import re
import shutil
import socket
import subprocess
import sys
import tomllib

import pytest

from conftest import ROOT

ALLOWED_DEPS = {
    "pydantic", "httpx", "edgartools", "yfinance", "akshare", "pandas", "jinja2",
    "pytest", "pytest-socket", "ruff",
}
BROKER_SDKS = {
    "ib_insync", "ib-insync", "ibapi", "alpaca-trade-api", "alpaca-py", "futu-api",
    "tigeropen", "longport", "robin-stocks", "schwab-py", "tda-api", "webull",
}


def test_imports_follow_the_diagram():
    proc = subprocess.run(
        [sys.executable, "design/tools/arch_check.py"], cwd=ROOT, capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="需要 Node 22 以上")
def test_blueprint_is_consistent():
    proc = subprocess.run(
        ["node", "design/tools/build.mjs", "--check"], cwd=ROOT, capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.filterwarnings("ignore:A test tried to use socket")
def test_kernel_tests_run_offline():
    with pytest.raises(Exception) as exc:
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("example.com", 443))
    assert "Socket" in type(exc.value).__name__ or "socket" in str(exc.value).lower()


def _dep_name(spec: str) -> str:
    return re.split(r"[<>=!~\[; ]", spec, maxsplit=1)[0].strip().lower()


def test_dependencies_are_allowlisted():
    meta = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    deps = [_dep_name(d) for d in meta.get("dependencies", [])]
    for group in meta.get("optional-dependencies", {}).values():
        deps += [_dep_name(d) for d in group]
    assert set(deps) <= ALLOWED_DEPS, set(deps) - ALLOWED_DEPS
    assert not set(deps) & BROKER_SDKS


def test_no_order_placement_code():
    pattern = re.compile(r"place_order|submit_order|create_order|broker", re.I)
    for path in (ROOT / "src").rglob("*.py"):
        assert not pattern.search(path.read_text(encoding="utf-8")), path
