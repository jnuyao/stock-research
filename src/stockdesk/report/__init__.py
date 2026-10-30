"""[REPORT] 报告：先自查，再把财报包和 Claude 写的解读合成一页 HTML，最后归档。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from stockdesk.shared.models import EarningsPack

from .archive import report_dir, write_archive
from .notes import Notes, parse_notes
from .render import render_html, summary_line
from .review import Issue, check_names, raise_if_failed, self_review

__all__ = [
    "Issue", "Notes", "parse_notes", "render_report", "report_dir", "self_review", "summary_line",
]


def render_report(pack: EarningsPack, notes_text: str, out_root: Path, zones: dict | None = None,
                  generated_at: str | None = None) -> Path:
    """自查不过就抛 StockdeskError，什么都不写；通过才渲染并归档，返回 report.html 路径。"""
    notes = parse_notes(notes_text)
    raise_if_failed(self_review(pack, notes, zones))
    stamp = generated_at or datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    html = render_html(pack, notes, stamp, check_names(zones))
    return write_archive(out_root, pack, html, notes_text)
