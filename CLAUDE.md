# 股票研究台：施工规则

本项目按一张架构图施工。图是唯一标准，文字规格和代码都必须与图一致。

## 先读这三样

1. `design/architecture.json`：架构图本身（模块、箭头、流程、不变量、验收、切片）。
2. `design/SPEC.md`：图的文字版，含接口、协议、验收标准。
3. `design/generated/review.html`：由前两者生成的审阅页，用户只看这一页。

## 不许擅自改图

- 新增或删除模块、箭头，修改代码目录，都算改图。需要改图时先停下，说明原因和影响，等用户确认。
- 用户确认后，同时修改 `design/architecture.json` 和 `design/SPEC.md`，再运行 `node design/tools/build.mjs`，让审阅页里能看到这次改动。
- 不要为了让检查通过去改检查规则或删测试。

## 只写图上允许的调用

- 每个模块只能放在图上写明的目录里（见 SPEC 中每个模块的"代码目录"）。
- 模块之间只能 import 图上画了"代码调用"箭头的方向，`make arch` 必须零违规。
- 公共代码只能放 `src/stockdesk/shared/`。反向通知用回调传入，不要反向 import。

## 按切片施工

切片定义见 SPEC 第 8 节，按顺序做，一次只做一个切片。每个切片都要从入口一路接到最底层，能跑起来；不要先把某一层做完整再做下一层。

1. 读该切片列出的验收场景，先写这些自动化测试，确认它们失败。
2. 只实现这个切片需要的部分，直到测试通过。图上其他模块保持空接口即可。
3. 运行 `make check`，必须全部通过。
4. 运行该切片的"演示"命令，确认输出符合预期。
5. 运行 `make arch-actual`，重建带"对比实际代码"的审阅页。
6. 汇报：演示命令的输出、完成了哪些验收、审阅页里还有哪些红色项、遇到的问题。不要只说"完成了"。
7. 停下，等用户确认后再开始下一个切片。

## 检查命令

SL-1 建立下面的 Makefile 目标：

```make
PY ?= .venv/bin/python
lint:        ; $(PY) -m ruff check src tests examples design/tools
test:        ; $(PY) -m pytest -q
arch:        ; $(PY) design/tools/arch_check.py
arch-actual: ; $(PY) design/tools/arch_check.py --json design/generated/actual-deps.json && node design/tools/build.mjs --actual design/generated/actual-deps.json
design:      ; node design/tools/build.mjs
design-check:; node design/tools/build.mjs --check
check: lint test arch design-check
```

## 技术约定

- Python 3.11 以上，类型标注齐全；测试用 pytest，关键路径不 mock 真实进程和文件。
- 入口 `src/stockdesk/__main__.py` 只能引用 [CLI] 的目录；`examples/` 是外部客户端，不能 import `stockdesk`。
- 设计工具 build.mjs 需要 Node 22 以上。
- 允许的依赖：pydantic（数据模型）、httpx（只在 `src/stockdesk/data/` 里用）、edgartools、yfinance（只在 Mac 上的 fetch 里用）、pandas、jinja2（报告）、pytest、pytest-socket（断网测试）、ruff。需要其他依赖时先问。
- 只有 `src/stockdesk/data/` 可以联网；其余模块的测试一律在断网下跑。
- 金额存美元原值，百分比存小数；每个数值字段都带 `source_url`、`as_of`、`fetched_at`。
- 已发布的报告里发现任何错误，都记进 `docs/BUGS-LOG.md`（现象、原因、修法），并补一个回放案例防止再犯（借鉴 UZI 的 BUGS-LOG 和回归测试）。
- 固定案例放 `tests/cases/<案例名>/`，数字取自 SEC 原文和本项目已发布的财报页，改动案例要在提交说明里写原因。
- 给用户看的错误信息说明出了什么事、下一步怎么做；错误码用英文常量。
- 不打印、不记录密钥。

## 不做的事

- 不接券商、不下单、不存账户凭据。
- 不输出综合评分，只输出带锚点的价位。
- 不做实时盯盘和日内交易。
- 第一版不做港股，不接付费数据源。
- 报告和提醒都要写“不构成投资建议”。
