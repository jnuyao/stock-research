---
name: earnings-review
description: 美股或港股公司发完财报后用：取数（云端 WebFetch 后 sd import，Mac 上 sd fetch）、组装财报包、读电话会写解读和 EPS/PE 假设、用规则算三档买点、出报告页。用户说“解读 INTC 财报”“联想发业绩了”时用。
---

# 财报解读

数字由 `sd` 算，判断由你写。你不算任何价位，价位只来自第 5 步的规则引擎。每个数字都要能追到来源网址。
所有命令在仓库根目录运行，加 `--json` 读结果。出错时看返回里的 `code`、`message` 和 `next_step`，照做。

## 0. 准备

- 确认代码和季度：美股写 `INTC`、季度 `2026Q3`；港股写 `0992.HK`、季度按财年写 `FY2027Q1`（见 `config/companies.toml` 的 `fiscal_year_end`）。
- 云端会话里如果有项目共享文件夹，先 `export STOCKDESK_DATA=/mnt/project-files/stockdesk-data`，这样导入的快照下次会话还在。

## 1. 网络预检：`sd doctor --json`

- `environment` 是 `mac` 且 `can_fetch` 为 true：运行 `sd fetch <代码> --json`，看 `coverage`（每类数据取到了什么）和 `failures`（哪里没取到）。缺的部分按第 2 步补。
- `environment` 是 `cloud`，或 `can_fetch` 为 false：全部按第 2 步，用 WebFetch 抓网页再 `sd import`。

## 2. 云端取数：WebFetch 抓网页 → 存成 JSON → `sd import`

按下表抓。每抓一页就记下三样：页面网址（`source_url`）、页面上数据对应的日期（`as_of`）、你抓取的时间（`fetched_at`）。拿不到就留空，交给数据守门判断，不要猜。

| 要什么 | 去哪里抓 |
|---|---|
| 营收、EPS（GAAP 和 non-GAAP）、毛利率、营业利润、分部门、一次性项目 | 美股：SEC 8-K 的新闻稿附件 Ex-99.1；港股：披露易业绩公告（PDF） |
| 下季指引 | 新闻稿的 Business Outlook 一节（港股大多没有） |
| 一致预期（本季和下季） | 财报前的预期报道，或 stockanalysis 的 forecast 页 |
| 最新收盘价 | stockanalysis 的 history 页；页面日期落后时，另找当天收盘的报道，日期照实写 |
| 近一年日线（算三档要 260 个交易日） | 云端抓不全：先看 `STOCKDESK_DATA` 里有没有 Mac 抓过的日线；没有就请用户在 Mac 上 `sd fetch <代码>`。云端只补最近几天的日线，导入后会和早先的日线按日期拼接 |
| 近 3 年前瞻 PE | stockanalysis 的 financials/ratios 页（Forward PE） |
| 同行前瞻 PE | 同行的 stockanalysis statistics 页 |
| 当日汇率（港股、财报和股价货币不同时） | Yahoo 的 HKD=X 页或香港金管局汇率页 |
| 电话会实录 | 公司 IR 或转载实录的网站 |

存成 JSON 时：

- 一条数据一行：`{"field": "revenue", "period": "2026Q3", "value": 16500000000, "unit": "USD", "source_url": "https://...", "as_of": "2026-09-27", "fetched_at": "2026-10-30T08:00:00Z"}`。
- 金额写原值，不缩写（16.5B 写成 16500000000）；百分比存小数（44.1% 写成 0.441）；每股写 `USD/share`。
- 日线写成一段序列：`{"field": "bars_daily", "unit": "USD", "columns": ["date","open","high","low","close","volume"], "rows": [["2026-10-30", ...]], "source_url": ..., "as_of": ..., "fetched_at": ...}`。
- 字段名照 `tests/cases/` 里的案例写（例如 `guide_revenue_low`、`cons_eps_nongaap`、`segment.DCAI.revenue`、`item.<名字>`、`fx.USDHKD`、`pe_fwd`、`peer_pe.AMD`）。

然后 `sd import <代码> <文件> --json`。返回 `BAD_INPUT` 时整份没写进去，按 `problems` 逐行改了再导入。

## 3. 财报包：`sd pack <代码> --quarter <季度> --json`

- `DATA_INCOMPLETE`：按 `gaps` 里每一项的 `where` 定点补抓，再 `sd import`。非关键字段确实补不到时，用 `sd import <代码> --gap-ack 字段@期间=原因` 登记；关键字段不能登记跳过。
- `SOURCE_CONFLICT`：打开两个来源的原文核对。在解读里把两个值都写出来，不悄悄挑一个。
- `STALE_PRICE`：重新取最新收盘价。
- 通过后记下 `pack_hash`，解读文件开头要写它。

## 4. 读电话会，写解读（Markdown 文件）

文件开头写元数据，格式和 `tests/cases/intc-q3-2026/notes/ok.md` 一样：

```
---
pack_hash: <第 3 步的 pack_hash>
视角-价值: 看多 / 看空 / 中性
视角-成长: ...
视角-趋势: ...
视角-宏观: ...
---
```

- 拿不到电话会实录时，改读公司 IR 的业绩演示材料和公告，正文第一句写“未取得电话会实录”。
- 正文写三件事：发生了什么、市场在担心什么、指引意味着什么。
- 过四个视角：价值（估值分位）、成长（营收和指引）、趋势（均线和支撑）、宏观（利率、VIX、信用利差）。每个视角只引用财报包里的数字；视角之间矛盾时单写一节“矛盾”，把矛盾本身写出来。
- 给出假设，各写一句理由：前瞻 EPS（例如“FY27 EPS 取 1.75，低于财报前一致预期 2.14，因为 Q4 毛利率指引 38%”）和合理 PE 区间。
- 不写空话（“值得关注”“有待观察”这类会被自查拒绝）。

## 5. 三档买点：`sd zones <代码> --eps <EPS> --pe <低-高> --earnings-date <财报日> --json`

- 港股财报是美元时加 `--eps-currency USD`，程序按当日汇率换算。
- 价位、仓位、右侧信号、失效位都以输出为准。觉得规则结果不合理时，在回复里说明理由，不改数字。

## 6. 报告：`sd report <代码> --quarter <季度> --notes <解读文件> --json`

- `STALE_NOTES`：解读依据的是旧财报包，按新的 `pack_hash` 重写。
- `UNSOURCED_NUMBER`、`SELF_REVIEW_FAILED`：按问题清单逐条改解读后重试。
- 通过后把 `reports/<代码>/<季度>/report.html` 发布成报告页，报告里要写“不构成投资建议”。

## 7. 存进观察清单：`sd watch save <代码>`

切片 4 完成前这个命令会返回 `NOT_YET_BUILT`，跳过即可。

## 8. 回复用户

先说结论，再给三档区间、仓位、右侧信号、失效位（周收盘）和“数据截至”日期，附报告页链接，最后写“不构成投资建议”。
