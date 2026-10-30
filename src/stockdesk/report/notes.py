"""读取 Claude 写的解读文件：开头是元数据（财报包指纹、四个视角），后面是 Markdown 正文。"""

from __future__ import annotations

from dataclasses import dataclass, field

LENSES = ("价值", "成长", "趋势", "宏观")
STANCES = ("看多", "看空", "中性")


@dataclass
class Notes:
    pack_hash: str | None
    lenses: dict[str, str] = field(default_factory=dict)
    body: str = ""
    body_offset: int = 0  # 正文在原文里的起始行号，报错时用


def parse_notes(text: str) -> Notes:
    lines = text.splitlines()
    meta: dict[str, str] = {}
    start = 0
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                start = i + 1
                break
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    lenses = {k.removeprefix("视角-"): v for k, v in meta.items() if k.startswith("视角-")}
    return Notes(meta.get("pack_hash"), lenses, "\n".join(lines[start:]).strip(), start)
