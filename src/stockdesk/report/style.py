"""报告样式（与 GOOGL、INTC 财报页一致，含深色模式）。"""

CSS = """
/* 版式沿用 GOOGL、INTC 财报页：单栏阅读、财报对照表、KPI 卡片 */
:root{
  --bg:#f5f6f4; --surface:#ffffff; --fg:#1d2226; --muted:#5d666d; --line:#d9ddd8;
  --accent:#1a5c7a; --accent-soft:#e2edf2;
  --good:#2f7a46; --good-soft:#e3f1e7; --bad:#b0412e; --bad-soft:#f6e4df; --warn:#9a6a10; --warn-soft:#f5ecd6;
  --display:"Noto Serif SC","Songti SC",serif;
  --body:"Noto Sans SC","PingFang SC","Microsoft YaHei",system-ui,sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#14191c; --surface:#1b2226; --fg:#e4e8e6; --muted:#9aa5ab; --line:#2f393e;
  --accent:#6fb3d2; --accent-soft:#1d3440;
  --good:#6cc28a; --good-soft:#1c3324; --bad:#e58873; --bad-soft:#3a221d; --warn:#e0b558; --warn-soft:#352b17; color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#14191c; --surface:#1b2226; --fg:#e4e8e6; --muted:#9aa5ab; --line:#2f393e;
  --accent:#6fb3d2; --accent-soft:#1d3440;
  --good:#6cc28a; --good-soft:#1c3324; --bad:#e58873; --bad-soft:#3a221d; --warn:#e0b558; --warn-soft:#352b17; color-scheme:dark}
body{background:var(--bg);color:var(--fg);font-family:var(--body);font-size:15px;line-height:1.75}
.wrap{max-width:860px;margin:0 auto;padding-block:32px 64px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));display:flex;flex-direction:column;gap:36px}
h1,h2,h3{font-family:var(--display);text-wrap:balance;line-height:1.35;margin:0}
h1{font-size:30px;font-weight:800}
h2{font-size:21px;font-weight:800;padding-bottom:8px;border-bottom:2px solid var(--fg)}
h3{font-size:16px;font-weight:600;margin-top:4px}
p{margin:0}
section{display:flex;flex-direction:column;gap:14px;min-width:0}
.eyebrow{font-family:var(--mono);font-size:12px;letter-spacing:.08em;color:var(--muted);text-transform:uppercase}
.meta{color:var(--muted);font-size:13px}
.lead{font-size:17px;line-height:1.8}
.num{font-family:var(--mono);font-variant-numeric:tabular-nums}
.callout{background:var(--surface);border:1px solid var(--line);border-left:4px solid var(--accent);padding:16px 18px;display:flex;flex-direction:column;gap:8px}
.callout.warn{border-left-color:var(--warn)}
ul,ol{margin:0;padding-left:1.3em;display:flex;flex-direction:column;gap:6px}
.tbl{overflow-x:auto;border:1px solid var(--line);background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:14px;min-width:560px}
th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
th{font-weight:700;font-size:12px;color:var(--muted);letter-spacing:.04em;background:var(--bg)}
tr:last-child td{border-bottom:none}
td.r,th.r{text-align:right}
.pill{display:inline-block;font-size:12px;font-weight:700;padding:1px 8px;border-radius:3px;white-space:nowrap}
.pill.good{background:var(--good-soft);color:var(--good)}
.pill.bad{background:var(--bad-soft);color:var(--bad)}
.pill.warn{background:var(--warn-soft);color:var(--warn)}
.pill.info{background:var(--accent-soft);color:var(--accent)}
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;background:var(--line);border:1px solid var(--line)}
.kpi{background:var(--surface);padding:14px;display:flex;flex-direction:column;gap:2px;min-width:0}
.kpi .v{font-family:var(--mono);font-size:22px;font-weight:600}
.kpi .l{font-size:12px;color:var(--muted)}
.kpi .d{font-size:12px}
@media (max-width:620px){.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}}
.chart{background:var(--surface);border:1px solid var(--line);padding:12px;overflow-x:auto}
.chart svg{display:block;width:100%;min-width:520px;height:auto}
.src{font-size:13px;color:var(--muted)}
.src a{color:var(--accent)}
a{color:var(--accent)}
a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.good-t{color:var(--good)} .bad-t{color:var(--bad)} .warn-t{color:var(--warn)}
.n{border-bottom:1px dotted var(--muted);cursor:help}
.missing{color:var(--muted)}
.review{font-size:13px;color:var(--muted)}
.notes h3{margin-top:8px}
.tbl.narrow table{min-width:0}
td.num{white-space:nowrap}
.notes{display:flex;flex-direction:column;gap:12px}

"""
