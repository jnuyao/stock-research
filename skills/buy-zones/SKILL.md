---
name: buy-zones
description: 不在财报季时单独更新某只股票的三档买点：取最新价格和估值数据、确认 EPS 和 PE 假设、用 sd zones 算三档、存进观察清单。用户说“更新一下 XX 的买点”“XX 跌了现在能买吗”时用。
---

# 更新三档买点

价位只来自 `sd zones`，你不算任何价位。所有命令在仓库根目录运行，加 `--json` 读结果。

## 1. 网络预检：`sd doctor --json`

- Mac 上能直连：`sd fetch <代码> --kinds price,fx,consensus,macro --json`。
- 云端或连不上：用 WebFetch 抓最新收盘价（stockanalysis history 页，记下页面日期）、前瞻 PE（stockanalysis financials/ratios 页）、同行 PE（statistics 页）；港股加当日汇率。存成 JSON 后 `sd import <代码> <文件> --json`。格式和规则见 `skills/earnings-review/SKILL.md` 第 2 步。
- 算三档要近 260 个交易日的日线。云端抓不全时先看 `STOCKDESK_DATA` 里有没有 Mac 抓过的日线，没有就请用户在 Mac 上 `sd fetch <代码>`。

## 2. 确认假设

- 前瞻 EPS 和合理 PE 区间沿用上一份报告，除非这段时间有新的指引、预期大改或行业事件。改的话写一句理由。
- 最近一次财报日从上一份报告或公司公告里取。

## 3. 三档买点：`sd zones <代码> --eps <EPS> --pe <低-高> --earnings-date <财报日> --json`

- `STALE_PRICE`：重新取最新收盘价。`DATA_INCOMPLETE`：按缺口清单补抓；同行 PE 这类非关键字段补不到时用 `sd import <代码> --gap-ack 字段=原因` 登记。`FX_MISSING`：补当日汇率。
- 价位、仓位、右侧信号、失效位都以输出为准，不改数字。

## 4. 存进观察清单：`sd watch save <代码>`

切片 4 完成前这个命令会返回 `NOT_YET_BUILT`，跳过即可。

## 5. 回复用户

列出参考价和日期、三档区间和仓位、每档的锚点、右侧信号、失效位（周收盘），和上一版相比变了什么，最后写“不构成投资建议”。
