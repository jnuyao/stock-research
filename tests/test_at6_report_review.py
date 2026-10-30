"""[AT-6] 出报告前自查：只有合规的解读能生成报告，其余四种各报对应的错误。"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import CASES

CASE = CASES / "intc-q3-2026"


def report(cli, notes: str, out: Path):
    return cli(
        "report", "INTC", "--quarter", "2026Q3", "--replay", "intc-q3-2026",
        "--notes", str(CASE / "notes" / notes), "--out", str(out), "--json",
    )


def test_compliant_notes_render(cli, tmp_path):
    res = report(cli, "ok.md", tmp_path)
    assert res.code == 0, res.stdout + res.stderr
    html_path = tmp_path / "INTC" / "2026Q3" / "report.html"
    assert html_path.exists()
    html = html_path.read_text(encoding="utf-8")
    assert "不构成投资建议" in html
    assert "数据截至" in html
    # 每个数字带来源：解读里的 $16.5B 被标注了来源
    assert 'data-source="https://www.intc.com/' in html
    assert (tmp_path / "INTC" / "2026Q3" / "pack.json").exists()


@pytest.mark.parametrize(
    ("notes", "code", "needle"),
    [
        ("unsourced.md", "UNSOURCED_NUMBER", "41%"),
        ("stale.md", "STALE_NOTES", "000000000000"),
        ("vague.md", "SELF_REVIEW_FAILED", "前景广阔"),
        ("no-contradiction.md", "SELF_REVIEW_FAILED", "矛盾"),
    ],
)
def test_bad_notes_are_refused(cli, tmp_path, notes, code, needle):
    res = report(cli, notes, tmp_path)
    assert res.code != 0
    out = res.json()
    assert out["error"]["code"] == code
    assert needle in res.stdout
    assert not (tmp_path / "INTC").exists(), "被拒绝的报告不能写进归档"
