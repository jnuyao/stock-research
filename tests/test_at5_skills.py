"""[AT-5] 技能文件：步骤写全、顺序对，只用命令行里真有的命令。

技能是 Markdown，不是代码。这里检查的是“按同样的步骤做事”能不能落到命令上；
技能跑出来的结果（报告页）由你看页面确认。
"""

from __future__ import annotations

import re

import pytest

from stockdesk.cli.main import build_parser

from conftest import ROOT

SKILLS = ROOT / "skills"

REQUIRED = {
    "earnings-review": [
        "sd doctor", "WebFetch", "sd import", "sd fetch", "sd pack", "pack_hash", "价值", "成长", "趋势", "宏观",
        "sd zones", "sd report", "sd watch save", "--gap-ack", "未取得电话会实录", "不构成投资建议",
    ],
    "buy-zones": ["sd doctor", "sd import", "sd fetch", "sd zones", "sd watch save", "不构成投资建议"],
}

# earnings-review 里这些步骤必须按这个顺序出现
ORDER = ["sd doctor", "sd pack", "pack_hash", "sd zones", "sd report"]


def read(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", sorted(REQUIRED))
def test_skill_has_front_matter(name):
    text = read(name)
    head = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert head, "开头要有 --- 包起来的 name 和 description"
    assert f"name: {name}" in head.group(1)
    assert re.search(r"^description: .{20,}", head.group(1), re.M)


@pytest.mark.parametrize("name", sorted(REQUIRED))
def test_skill_mentions_every_step(name):
    text = read(name)
    missing = [w for w in REQUIRED[name] if w not in text]
    assert not missing, f"{name} 缺这些步骤：{missing}"


def test_earnings_review_steps_in_order():
    text = read("earnings-review")
    positions = [text.index(w) for w in ORDER]
    assert positions == sorted(positions), dict(zip(ORDER, positions, strict=True))


@pytest.mark.parametrize("name", sorted(REQUIRED))
def test_skill_only_uses_real_commands(name):
    commands = set(build_parser()._subparsers._group_actions[0].choices)  # noqa: SLF001
    used = set(re.findall(r"\bsd ([a-z]+)", read(name)))
    assert used <= commands, used - commands


@pytest.mark.parametrize("name", sorted(REQUIRED))
def test_skill_does_not_compute_prices_itself(name):
    """技能只读和判断，价位交给 sd zones：不许出现让 Claude 自己乘出价位的写法。"""
    text = read(name)
    assert not re.search(r"(自己|手工|手动)(计算|算出?)(价位|买点|三档)", text)
