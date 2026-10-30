# 股票研究台

给一个人用的美股和港股研究工作台：取数（带来源）→ 财报包 → Claude 写解读和假设 → 规则算三档买点和失效位 → 报告 → 观察清单 → 每周五复盘提醒。不构成投资建议。

当前进度：**蓝图 0.3，切片 1 完成**（INTC 财报包回放到报告，不联网）。下一步是切片 2（三档买点和数据守门）。

## 跑起来

需要 Python 3.11 以上；审阅页工具需要 Node 22 以上。

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
make check   # 代码检查、测试、架构检查、图文一致检查
make demo    # 用 INTC 2026Q3 固定案例跑 财报包 → 自查 → 报告，报告写到 reports/INTC/2026Q3/report.html
```

常用命令（都支持 `--json` 和 `--replay <案例>`）：

```bash
.venv/bin/sd pack INTC --quarter 2026Q3 --replay intc-q3-2026
.venv/bin/sd report INTC --quarter 2026Q3 --replay intc-q3-2026 --notes tests/cases/intc-q3-2026/notes/ok.md
```

在线审阅页：https://claude.ai/artifact/GVcTSjfggkxm3XiYe9Zf3b （私有，仅本人可见）。本地审阅：用浏览器打开 `design/generated/review.html`。

## 你只需要看一页

用浏览器打开 `design/generated/review.html`：

1. 图上每个方框右上角都应是绿色对勾；红色感叹号表示文字和图对不上。
2. 点方框，右侧显示 SPEC.md 里这个模块的原文。
3. 点上方编号核对流程经过哪些模块；点"切片"核对施工顺序。
4. 施工后打开"对比实际代码"：绿色是已按图实现，灰色虚线是还没实现，红色是图上没有的多余调用。

## 文件分工

| 文件 | 作用 |
|---|---|
| `design/architecture.json` | 架构图本身，唯一标准 |
| `design/SPEC.md` | 图的文字版，和图一起改 |
| `CLAUDE.md` | Claude Code 的施工规则 |
| `design/tools/` | 生成审阅页、检查一致性（来自 blueprint-kit，不用改） |
| `design/generated/` | 生成的产物，不要手工修改 |

让 Claude Code 开工时，在这个文件夹里启动它，说"按 CLAUDE.md 做 SL-1"即可。
