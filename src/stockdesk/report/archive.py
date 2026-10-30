"""[ST-REPORT] 报告归档：reports/<代码>/<季度>/ 下的 report.html、pack.json 和所用解读。"""

from __future__ import annotations

import json
from pathlib import Path

from stockdesk.shared.models import EarningsPack


def report_dir(out_root: Path, pack: EarningsPack) -> Path:
    return Path(out_root) / pack.ticker / pack.quarter


def write_archive(out_root: Path, pack: EarningsPack, html: str, notes_text: str) -> Path:
    """只在自查通过后调用。返回 report.html 的路径。"""
    folder = report_dir(out_root, pack)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "pack.json").write_text(
        json.dumps(pack.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (folder / "notes.md").write_text(notes_text, encoding="utf-8")
    path = folder / "report.html"
    path.write_text(html, encoding="utf-8")
    return path
