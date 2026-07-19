# TraderHarness

<p align="center">
  <strong>面向自主交易 Agent 的执行与证据环境——不是又一个策略库。</strong><br>
  真实 A 股全市场数据 · 严格时序遮罩 · 可复现完整轨迹
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="https://github.com/HephaestLab/TraderHarness/actions/workflows/ci.yml">CI</a> ·
  <a href="https://pypi.org/project/traderharness/">PyPI</a> ·
  <a href="CHANGELOG.md">Research Beta</a> ·
  Apache-2.0
</p>

<p align="center">
  <img src="docs/assets/traderharness-demo.gif" alt="TraderHarness 流式历史回放控制台" width="920">
</p>

<p align="center"><sub>该 GIF 由本地研究控制台截图生成（<code>webui/scripts/capture-demo.mjs</code>）。UI 有变化时执行 <code>npm run capture:demo</code> 重新生成；将随 v1.0 验收跑一并更新。</sub></p>

TraderHarness 是 LLM 交易 Agent 的执行环境和评测框架，不是又一个策略库。模型获得一个严格对齐历史时点的市场、研究工具和账户，可以自主检索、写分析代码、修正判断，并通过唯一受控入口下单——环境里没有实盘市场，也没有券商接口。

首个生产数据集覆盖五年 A 股全市场：日线、5 分钟线、公告、政策快讯、基本面、估值、分红以及沪深 300 基准。

## 为什么不是普通 Agent Demo

| 能力 | 常见 Demo | TraderHarness |
|---|---:|---:|
| 基本面与新闻时点对齐 | 局部 | 每个数据出口强制执行 |
| 日期与公司匿名化 | 无 | 确定性实体/日期遮罩 |
| 盘中公平成交 | 常用收盘价 | 5 分钟可见性 + 分钟级撮合 |
| LLM 结果复现 | 仅日志 | 请求指纹校验的 replay |
| 训练轨迹 | 经常截断 | 请求、推理、工具、结果全保真 |
| 多 Agent | 共享聊天模拟 | 隔离组合对比 + 单执行者委员会 |
| 回测期间数据 I/O | 常见 | 启动预载后零 I/O |
| 历史回放 | 临时脚本拼接 | 流式、按阶段渐进披露的历史回放——绝非实时行情 |

TraderHarness 负责历史环境、信息边界、公平撮合和证据产物，不限定交易方法论。与 TradingAgents、StockBench、Qlib 等项目的完整边界对比见[项目对比](docs/comparison.md)。

## 四智能体展示阵容

TraderHarness 在 `traderharness/agents/builtin/` 下内置四个人设清晰、互不重复的参考 Agent 卡片：

| Agent id | 风格 | 风险画像 | 持仓周期 |
|---|---|---|---|
| `trend-breakout` | 量价突破、相对强度、成交量确认、机械止损 | 进取 | 3–10 个交易日 |
| `quality-compounder` | 盈利质量、资产负债表与估值纪律，低换手 | 保守 | 20–60 个交易日 |
| `event-hawk` | 公告/政策/新闻催化，重视时间戳与来源核验 | 进取 | 1–5 个交易日 |
| `quant-researcher` | 沙箱内可复现的横截面因子检验 | 均衡 | 2–20 个交易日 |

验收参考跑是这四个 Agent 在 **2024-03-04 → 2024-03-29** 区间的正面对比，执行模型为 `deepseek-v4-pro` 的 thinking（深度推理）模式，全程开启实体遮罩：

```powershell
$env:DEEPSEEK_API_KEY="..."
traderharness compare `
  --agent trend-breakout `
  --agent quality-compounder `
  --agent event-hawk `
  --agent quant-researcher `
  --start 2024-03-04 `
  --end 2024-03-29 `
  --mask-entities `
  --entity-mask-seed 42 `
  --record-replay showcase_mar2024 `
  --output showcase_mar2024/comparison.html
```

`--record-replay` 会保存一份带指纹校验的 cassette，可以在没有 API Key 的情况下确定性重放、审计和分享。参考[快速开始](#快速开始)和[训练数据](docs/training-data.md)。

**验收结果**（2024-03-04 → 2024-03-29，实体遮罩 seed `42`，`deepseek-v4-pro` thinking high）。
按夏普排序；该跑已通过 `traderharness audit`（零发现），可用 `--replay showcase_mar2024` 无 Key 复现：

| Agent | 累计收益 | 年化收益 | 夏普比率 | 最大回撤 | 胜率 | 成交次数 |
|---|---:|---:|---:|---:|---:|---:|
| `quality-compounder` | +0.52% | +7.92% | 1.09 | 0.76% | 33% | 9 |
| `trend-breakout` | +0.09% | +1.32% | −0.20 | 1.07% | 38% | 16 |
| `event-hawk` | −0.70% | −9.74% | −3.22 | 0.93% | 0% | 5 |
| `quant-researcher` | −1.33% | −17.75% | −4.19 | 1.73% | 40% | 19 |
| 沪深 300（基准） | −0.10% | — | — | — | — | — |

## 证据链

上面的每一句话都应该能被核实，而不是靠信任。每次完整的运行都会保存每一次 LLM 调用的：完整消息列表、完整工具 schema、模型回答与推理内容、每一次工具调用及其参数、以及阶段/子窗口元数据——参见[训练数据](docs/training-data.md)。研究控制台会把同一份证据渲染成逐笔复盘档案：成交时刻的 5 分钟 K 线、Agent 当时的推理陈述，以及产生这笔成交的具体工具调用。

<p align="center">
  <img src="docs/assets/results-workbench.png" alt="TraderHarness 回测结果研究工作台：基准、回撤、K 线、成交与决策证据" width="920">
</p>

```bash
traderharness audit result.json replay.jsonl
traderharness export sft result.json --output training.jsonl
```

## 双重遮罩

数据泄漏是系统问题，不能只靠 prompt 约束。

- **时序遮罩**：日线严格满足 `date < current_date`；分钟线只暴露已发生子窗口；基本面严格满足 `pub_date <= current_date`。
- **日历遮罩**：Agent 看到的日历日期变为 `D-1`、`D+0` 等相对偏移。
- **实体遮罩**：股票代码和公司别名映射为确定性中性实体，同时保留创业板/科创板等交易规则（如 20% 涨跌停）。
- **输出清洗**：模型回答、推理、工具参数、委员会备忘、轨迹和 replay 全部经过同一套遮罩。
- **泄漏审计**：发布或导出 SFT 前，可对 JSON、JSONL、Parquet 进行扫描。

<p align="center">
  <img src="docs/assets/dual-mask.svg" alt="历史公告经过日期与实体双重遮罩后的 Agent 视图" width="920">
</p>

v1.0 发布验收已对完整的一月 DeepSeek 轨迹做序列化后出口审计，未检出真实公司别名或绝对日历日期。这里指自动化出口审计结果，不代表语义再识别风险为零——参见[抗污染机制](docs/contamination.md)。

## 快速开始

支持 Python 3.10–3.12。

```bash
pip install "traderharness[llm,data,ui]"
traderharness data download --full
traderharness demo
```

`traderharness demo` 使用真实市场数据回放一段已经遮罩的单日轨迹，不需要 API Key。这是对真实本机行情的**流式历史回放**，按阶段渐进披露——不是实时行情，也不会用模拟价格替代真实数据。

启动本地研究控制台：

```bash
traderharness ui
# 打开 http://127.0.0.1:8000
```

运行真实模型回测：

```powershell
$env:DEEPSEEK_API_KEY="..."
traderharness run `
  --agent trend-breakout `
  --start 2024-03-04 `
  --end 2024-03-29 `
  --mask-entities `
  --record-replay run.jsonl
```

也可以用容器启动：

```bash
docker compose up --build
```

Compose 会把本机 `~/.traderharness` 挂载到 `/data`，不会把完整数据集烘焙进镜像。打开 `http://127.0.0.1:8000`，内置回放不需要 API Key。

### 每个交易日

每个交易日分三个有边界的阶段：

1. **盘前研究**：账户、昨日市场宽度、板块、自选股、公告和政策；禁止下单。
2. **开盘窗口**：09:30–10:00 的 5 分钟线按子窗口逐步可见；允许下单。
3. **尾盘窗口**：14:30–15:00 的数据逐步可见；允许下单并结束当天。

Agent 可查询历史 K 线、基本面、估值、公告和新闻，进行全市场筛选，在沙箱里自由使用 `numpy/pandas/scipy`，并查看只读账户。所有成交都必须经过 `TradingBus.place_order()`。

## 独立赛马 vs 单执行者委员会

`compare` 和委员会是建立在同一个遮罩市场和同一条下单路径上的两种不同产品。

### 独立组合对比

`compare` 让每个 Agent 拥有独立账户，在相同市场时钟和初始资金下并行运行，再按收益、风险和行为指标排名。[四智能体展示阵容](#四智能体展示阵容)就是用这个命令跑的。

```bash
traderharness compare \
  --agent trend-breakout \
  --agent quality-compounder \
  --start 2024-03-04 \
  --end 2024-03-29 \
  --mask-entities \
  --output comparison
```

### TradingAgents 风格委员会

委员会是“一个交易 Agent + 多个只读顾问 + 一个 Trader 执行者”。顾问并发研究，但只有 Trader 能获得下单工具，保证一个账户只有一条可追责的订单路径。

```yaml
id: research-committee
name: Research Committee
model: deepseek-v4-pro
persona: |
  你是委员会的唯一交易执行者。顾问意见只是证据输入；你必须独立核验，
  遵守仓位与交易窗口约束，并且只有你可以调用 place_order。
advisors:
  - role: fundamentals
    model: deepseek-v4-pro
    prompt: 关注盈利质量、估值、资产负债表和公告中的基本面变化。
  - role: technicals
    model: deepseek-v4-pro
    prompt: 关注趋势、量价、波动、支撑阻力和信号失效条件。
  - role: risk
    model: deepseek-v4-pro
    prompt: 从组合暴露、仓位集中、成交约束和尾部风险提出否决意见。
```

这份示例严格对应加载器真实的顶层 `advisors:` schema，没有嵌套的 `committee:` 结构，也没有虚构字段。完整六角色参考见 [`examples/tradingagents_committee.yaml`](examples/tradingagents_committee.yaml) 和[设计文档](docs/design/multi-role-agent.md)。

## 数据与架构

<p align="center">
  <img src="docs/assets/architecture.svg" alt="TraderHarness 数据、引擎、Agent、轨迹和评估架构" width="920">
</p>

核心不变量：回测期间零 I/O、单一下单路径（`TradingBus.place_order()`）、环境确定性、Agent 不持有 Portfolio、使用不复权真实价格。

全量数据下载会校验文件大小和 SHA-256，再原子安装到：

```text
~/.traderharness/dataset/
├── daily.parquet
├── 5min_clean/
├── announcements.parquet
├── news_cls.parquet
├── fundamentals.parquet
├── valuation.parquet
├── dividends.parquet
├── index_300.parquet
└── metadata.json
```

增量更新幂等：

```bash
traderharness data update
```

公开新闻数据保留模板化标题，去除有版权的正文。数据再分发和商业使用前请确认上游许可。详见[数据与许可](docs/data.md)和[核心架构](docs/architecture.md)。

## 面向 AI 的入口

TraderHarness 提供机器可读的操作指南，让编程助手不用猜测上面这些不变量：

- [`llms.txt`](llms.txt) —— 官方文档的精简索引。
- [`llms-full.txt`](llms-full.txt) —— 同一份文档集合合并成一个文件，由 `scripts/build_llms_full.py` 生成。
- [`AGENTS.md`](AGENTS.md) —— 公开操作指南：项目地图、不可协商的不变量与工作流程。

推荐先给 Cursor、Claude Code 等工具以下指令：

```text
先阅读 AGENTS.md 和 docs/architecture.md。新增 Agent 时不得绕过
TradingBus、时点遮罩和单一下单路径；先写失败测试，再运行相关测试和 replay demo。
```

## 和我们一起建设

TraderHarness 最值得扩展的几个接缝是：数据源适配器、工具、沙箱后端、评测指标、实盘 Broker adapter，以及研究控制台前端。每一个都在[扩展指南](docs/extensions.md)里有简短契约；流程和必跑检查见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。

```bash
.venv\Scripts\python.exe -m pip install -e ".[all]"
.venv\Scripts\python.exe -m pytest tests/ --no-header -q
.venv\Scripts\python.exe -m ruff check traderharness
cd webui
npm ci
npm test
npm run build
npm run test:e2e
```

## 路线图

完整版本（含明确的非目标）见 [`docs/roadmap.md`](docs/roadmap.md)：

| 状态 | 事项 |
|---|---|
| ✅ v1.0 已交付 | 回测引擎、遮罩、replay/SFT、多 Agent 对比、委员会、研究控制台 |
| 🚧 下一阶段 | 模拟盘（Paper Trading，复用同一引擎和遮罩契约的前向仿真模式） |
| 📋 规划中 | 实盘 Broker adapter |
| 📋 规划中 | 面向不可信/第三方 Agent 卡片的强化沙盒 |
| ❌ 非目标 | 公开排行榜、多租户托管服务、市场冲击建模 |

## 边界与限制

- 目前维护的生产数据集覆盖中国 A 股；欢迎为其他市场提供适配器。
- 目前没有模拟盘或实盘接口，参见[路线图](docs/roadmap.md)。历史仿真不模拟市场冲击，也不保证实盘表现。
- 部分上游字段的再分发可能受供应商条款限制。
- TraderHarness 是研究基础设施，不是投资建议，也不是券商系统。

## 引用

如果 TraderHarness 对你的研究有帮助，请引用：

```bibtex
@software{traderharness2026,
  title  = {TraderHarness: A Contamination-Resistant Environment for Autonomous Trading Agents},
  author = {{HephaestLab}},
  year   = {2026},
  url    = {https://github.com/HephaestLab/TraderHarness},
  version = {1.0.0}
}
```

机器可读记录见 [`CITATION.cff`](CITATION.cff)。

Apache-2.0 © HephaestLab.
