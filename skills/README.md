# Claude 技能

这里是给 Claude 用的技能文件（Markdown，不是代码）。技能只负责“读和判断”，数字和价位都交给 `sd` 命令算。

| 技能 | 什么时候用 | 切片 |
|---|---|---|
| `earnings-review` | 公司发完财报后：取数 → 财报包 → 解读和假设 → 三档买点 → 报告页 | SL-3 |
| `buy-zones` | 不在财报季时单独更新某只股票的三档 | SL-3 |
| `earnings-preview` | 财报前 3 天出预案 | SL-4 |
| `weekly-check` | 每周五对照观察清单复盘 | SL-4 |

在 Claude Code 里用：把 `skills/<名字>/` 复制或链接到 `.claude/skills/<名字>/`，或者直接对 Claude 说“按 skills/earnings-review/SKILL.md 做 INTC”。
