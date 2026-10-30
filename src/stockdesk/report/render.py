"""把财报包和解读合成一页 HTML。每个数字都带来源：悬停可见字段、日期和网址。"""

from __future__ import annotations

from html import escape

from stockdesk.shared.fmt import money, show
from stockdesk.shared.models import EarningsPack, PackItem

from .notes import LENSES, Notes
from .numbers import find_numbers
from .style import CSS

DISCLAIMER = "不构成投资建议，价格与仓位请结合自身情况判断。"

VERDICT_CLASS = {"高于预期": "good", "符合预期": "info", "低于预期": "bad"}
STANCE_CLASS = {"看多": "good", "中性": "info", "看空": "bad"}


def _attrs(it: PackItem) -> str:
    """数字的来源属性：data-source 放第一个网址，title 列出全部来源。"""
    if not it.sources:
        return ""
    lines = [f"{it.label} · {it.period}"]
    if it.derived_from:
        lines.append("由 " + "、".join(it.derived_from) + " 计算")
    lines += [f"{s.as_of} · {s.url}" for s in it.sources]
    return f' data-source="{escape(it.sources[0].url)}" title="{escape(chr(10).join(lines))}"'


def _num(pack: EarningsPack, key: str) -> str:
    """表格里的一个数字。确认缺失的字段显示“—”并注明原因（自查第 7 条）。"""
    if not pack.has(key):
        return '<span class="missing" title="财报包里没有这一项">—</span>'
    it = pack.item(key)
    if it.missing or it.value is None:
        reason = it.gap_ack or "数据源里没有这一项"
        r = escape(reason)
        return f'<span class="missing" title="{r}">—</span><small class="missing">（{r}）</small>'
    return f'<span class="n"{_attrs(it)}>{escape(show(it.value, it.unit, key))}</span>'


def _pill(pack: EarningsPack, key: str) -> str:
    if not pack.has(key) or pack.item(key).missing:
        return "—"
    v = str(pack.item(key).value)
    return f'<span class="pill {VERDICT_CLASS.get(v, "info")}">{escape(v)}</span>'


def _range(pack: EarningsPack, low: str, high: str) -> str:
    return f"{_num(pack, low)}–{_num(pack, high)}"


def _tone(pack: EarningsPack, key: str) -> str:
    """同比、差异这类带正负的数字，涨用绿色、跌用红色。"""
    if not pack.has(key) or not isinstance(pack.item(key).value, (int, float)):
        return ""
    return "good-t" if float(pack.item(key).value) >= 0 else "bad-t"


def _inline(text: str, pack: EarningsPack) -> str:
    """转义一段正文，并给能找到出处的数字套上来源标注。"""
    out, pos = [], 0
    for f in find_numbers(text, pack.items):
        if f.item is None or f.start < pos:
            continue
        out.append(escape(text[pos:f.start]))
        out.append(f'<span class="n"{_attrs(f.item)}>{escape(text[f.start:f.end])}</span>')
        pos = f.end
    out.append(escape(text[pos:]))
    return "".join(out)


def _markdown(body: str, pack: EarningsPack) -> str:
    """只支持解读用到的三种写法：## 小标题、- 列表、空行分段。"""
    html: list[str] = []
    para: list[str] = []
    bullets: list[str] = []

    def flush() -> None:
        if para:
            html.append(f"<p>{_inline(' '.join(para), pack)}</p>")
            para.clear()
        if bullets:
            html.append("<ul>" + "".join(f"<li>{_inline(b, pack)}</li>" for b in bullets) + "</ul>")
            bullets.clear()

    for line in body.splitlines():
        s = line.strip()
        if not s:
            flush()
        elif s.startswith("## "):
            flush()
            html.append(f"<h3>{escape(s[3:])}</h3>")
        elif s.startswith("- "):
            if para:
                flush()
            bullets.append(s[2:])
        else:
            if bullets:
                flush()
            para.append(s)
    flush()
    return "\n".join(html)


def _kpis(pack: EarningsPack) -> str:
    def card(label: str, value: str, detail: str) -> str:
        return (f'<div class="kpi"><span class="l">{label}</span><span class="v">{value}</span>'
                f'<span class="d">{detail}</span></div>')

    q, nq = pack.quarter, pack.next_quarter
    return '<div class="kpis">' + "".join([
        card(f"{q} 营收", _num(pack, "revenue"),
             f"同比 {_num(pack, 'revenue_yoy')} · 预期 {_num(pack, 'cons_revenue')}"),
        card("调整后 EPS", _num(pack, "eps_nongaap"),
             f"预期 {_num(pack, 'cons_eps_nongaap')} · GAAP {_num(pack, 'eps_gaap')}"),
        card(f"{nq} 营收指引", _range(pack, "guide_revenue_low", "guide_revenue_high"),
             f"预期 {_num(pack, 'next_cons_revenue')}"),
        card(f"{nq} 毛利率指引（非 GAAP）", _num(pack, "guide_gm_nongaap"),
             f"本季 {_num(pack, 'gross_margin_nongaap')} · 预期 {_num(pack, 'next_cons_gm_nongaap')}"),
    ]) + "</div>"


def _table(head: list[str], rows: list[list[str]], right_from: int = 1, narrow: bool = False) -> str:
    th_r, td_r = ' class="r"', ' class="r num"'
    th = "".join(f"<th{th_r if i >= right_from else ''}>{h}</th>" for i, h in enumerate(head))
    body = "".join(
        "<tr>" + "".join(f"<td{td_r if i >= right_from else ''}>{c}</td>" for i, c in enumerate(r)) + "</tr>"
        for r in rows
    )
    cls = "tbl narrow" if narrow else "tbl"  # 列少的表在手机上不横向滚动
    return f'<div class="{cls}"><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def _actual_vs_cons(pack: EarningsPack) -> str:
    rows = [
        ["营收", _num(pack, "revenue"), _num(pack, "revenue_yoy"), _num(pack, "cons_revenue"),
         _num(pack, "revenue_surprise_pct"), _pill(pack, "verdict_revenue")],
        ["调整后 EPS", _num(pack, "eps_nongaap"), _num(pack, "eps_nongaap_yoy"), _num(pack, "cons_eps_nongaap"),
         _num(pack, "eps_surprise_pct"), _pill(pack, "verdict_eps")],
        ["GAAP EPS", _num(pack, "eps_gaap"), _num(pack, "eps_gaap_yoy"), "—", "—", "—"],
        ["非 GAAP 毛利率", _num(pack, "gross_margin_nongaap"), "—", "—", "—", "—"],
        ["GAAP 毛利率", _num(pack, "gross_margin_gaap"), "—", "—", "—", "—"],
        ["非 GAAP 营业利润率", _num(pack, "op_margin_nongaap"), "—", "—", "—", "—"],
        ["GAAP 营业利润率", _num(pack, "op_margin_gaap"), "—", "—", "—", "—"],
    ]
    return _table(["项目", "实际", "同比", "一致预期", "相对预期", "判定"], rows)


def _segment_name(pack: EarningsPack, seg: str) -> str:
    for it in pack.items:
        if it.key.startswith(f"segment.{seg}."):
            return it.label.rsplit(" ", 1)[0]
    return seg


def _segments(pack: EarningsPack) -> str:
    segs = sorted({it.key.split(".")[1] for it in pack.items if it.key.startswith("segment.")})
    if not segs:
        return '<p class="missing">新闻稿没有分部门数据。</p>'
    rows = [[escape(_segment_name(pack, s)), _num(pack, f"segment.{s}.revenue"),
             f'<span class="{_tone(pack, f"segment.{s}.revenue_yoy")}">{_num(pack, f"segment.{s}.revenue_yoy")}</span>',
             f'<span class="{_tone(pack, f"segment.{s}.op_income")}">{_num(pack, f"segment.{s}.op_income")}</span>']
            for s in segs]
    return _table(["部门", "营收", "同比", "营业利润"], rows, narrow=True)


def _guidance(pack: EarningsPack) -> str:
    rows = [
        ["营收",
         _range(pack, "guide_revenue_low", "guide_revenue_high")
         + f"<br><small>中值 {_num(pack, 'guide_revenue_mid')}</small>",
         _num(pack, "next_cons_revenue"), _num(pack, "guide_revenue_vs_cons_pct"),
         _pill(pack, "verdict_guide_revenue")],
        ["调整后 EPS", _num(pack, "guide_eps_nongaap"), _num(pack, "next_cons_eps_nongaap"),
         _num(pack, "guide_eps_vs_cons_pct"), _pill(pack, "verdict_guide_eps")],
        ["非 GAAP 毛利率", _num(pack, "guide_gm_nongaap"), _num(pack, "next_cons_gm_nongaap"),
         _num(pack, "guide_gm_vs_cons_pt"), _pill(pack, "verdict_guide_gm")],
        ["GAAP EPS", _num(pack, "guide_eps_gaap"), "—", "—", "—"],
        ["GAAP 毛利率", _num(pack, "guide_gm_gaap"), "—", "—", "—"],
    ]
    return _table(["项目", "公司指引", "一致预期", "相对预期", "判定"], rows)


def _cash(pack: EarningsPack) -> str:
    rows = [
        ["经营现金流", _num(pack, "operating_cash_flow")],
        ["资本开支（总额）", _num(pack, "capex_gross")],
        ["调整后自由现金流", _num(pack, "fcf_adjusted")],
    ]
    return _table(["项目", pack.quarter], rows, narrow=True)


def _lenses(notes: Notes) -> str:
    cells = []
    for lens in LENSES:
        stance = notes.lenses.get(lens, "—")
        cells.append(f'<span class="pill {STANCE_CLASS.get(stance, "info")}">{lens}：{escape(stance)}</span>')
    return '<p class="lenses">' + " ".join(cells) + "</p>"


def _sources(pack: EarningsPack) -> str:
    seen: dict[str, str] = {}
    for it in pack.items:
        for s in it.sources:
            seen.setdefault(s.url, s.as_of)
    lis = "".join(f'<li><a href="{escape(u)}">{escape(u)}</a>（数据日期 {escape(d)}）</li>'
                  for u, d in seen.items())
    return f'<ul class="src">{lis}</ul>'


def render_html(pack: EarningsPack, notes: Notes, generated_at: str, passed: list[str]) -> str:
    price = pack.item("price_close") if pack.has("price_close") else None
    data_date = price.period if price else pack.as_of
    price_text = f"，收盘价 {_num(pack, 'price_close')}" if price and not price.missing else ""
    title = f"{pack.ticker} {pack.quarter} 财报解读"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header style="display:flex;flex-direction:column;gap:10px">
  <div class="eyebrow">{escape(pack.ticker)} · {escape(pack.quarter)} 财报 · {escape(pack.market)}</div>
  <h1>{escape(title)}</h1>
  <p class="meta">数据截至 {escape(data_date)}{price_text}。{DISCLAIMER}</p>
</header>

<section>
  <h2>关键数字</h2>
  {_kpis(pack)}
</section>

<section>
  <h2>一、本季实际 vs 预期</h2>
  {_actual_vs_cons(pack)}
</section>

<section>
  <h2>二、分部门</h2>
  {_segments(pack)}
</section>

<section>
  <h2>三、下季指引 vs 预期</h2>
  {_guidance(pack)}
</section>

<section>
  <h2>四、现金与资本</h2>
  {_cash(pack)}
</section>

<section class="notes">
  <h2>五、解读</h2>
  {_lenses(notes)}
  {_markdown(notes.body, pack)}
</section>

<section>
  <h2>来源</h2>
  <p class="src">表格和正文里带虚线的数字，悬停可见字段、数据日期和来源网址。</p>
  {_sources(pack)}
  <p class="review">出报告前自查通过：{escape("、".join(passed))}<br>
    财报包指纹 {pack.pack_hash} · 生成于 {escape(generated_at)}</p>
  <p class="meta">{DISCLAIMER}</p>
</section>
</div>
</body>
</html>
"""


def summary_line(pack: EarningsPack) -> str:
    """命令行里给人看的一行摘要。"""
    rev = pack.item("revenue")
    head = f"{pack.ticker} {pack.quarter} 营收 {money(float(rev.value), rev.unit)}"
    names = {"verdict_revenue": "营收", "verdict_eps": "EPS", "verdict_guide_revenue": "营收指引",
             "verdict_guide_eps": "EPS 指引", "verdict_guide_gm": "毛利率指引"}
    parts = [f"{name}{' ' if name[-1].isascii() else ''}{pack.item(key).value}"
             for key, name in names.items() if pack.has(key)]
    return f"{head}：" + "，".join(parts)
