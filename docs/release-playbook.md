# 发布分发手册

本页是可复制的元数据与发布草稿。仅在公开仓库、安装包、数据集、文档站与容器链接全部上线后再执行外发。

## GitHub 仓库元数据

**描述**

> Contamination-resistant A-share backtesting, evaluation, replay, and SFT trajectories for autonomous LLM trading agents.

**Topics**

```text
llm-agents, autonomous-agents, quantitative-trading, algorithmic-trading,
backtesting, trading-bot, a-share, china-stocks, benchmark, deepseek,
multi-agent, agentic-ai, synthetic-data, sft, rlhf, financial-ai,
market-simulation, fastapi, react, python
```

社交预览图使用 `docs/assets/social-preview.png`，上传前请目视确认 GitHub 的裁切效果。

## Show HN

**标题**

> Show HN: TraderHarness – contamination-resistant backtesting for autonomous trading agents

**草稿**

> Historical LLM trading evaluations are easy to leak: a model can recognize the date, company, or a full intraday
> price path. TraderHarness is an open-source A-share market environment that treats those as systems boundaries.
> It preloads five years of full-market data, progressively reveals 5-minute bars, anonymizes dates and companies,
> routes every fill through one matching path, and records full trajectories with fail-closed replay. It supports
> isolated agent comparisons and TradingAgents-style committees where only one executor can trade. A no-key replay
> and local FastAPI/React research console are included. I would especially value feedback on the masking threat
> model and trajectory format.

## Reddit r/algotrading

**标题**

> Open-source environment for auditing LLM trading agents on point-in-time A-share data

**草稿**

> I built TraderHarness to separate the agent architecture from the historical market contract. The environment
> owns the portfolio and simulated clock, masks future data at each tool boundary, reveals open/close 5-minute
> windows progressively, and exports complete model/tool/fill trajectories. Date and company identities can be
> deterministically anonymized to reduce memorized-answer contamination. It is research infrastructure rather than a
> strategy claim; I am looking for review of execution fairness, metrics, and data integrity.

## 中文发布草稿

**标题**

> 开源 TraderHarness：给 LLM 交易 Agent 一个不容易偷看答案的 A 股回测环境

**草稿**

> 大多数交易 Agent Demo 把注意力放在 prompt 和角色，却没有把历史时点、分钟级可见性、公司/日期记忆污染、
> 公平成交和完整证据链做成环境不变量。TraderHarness 用五年 A 股全市场真实数据，在每个数据出口执行时序遮罩，
> 对日期与公司做确定性匿名化，所有订单只走 TradingBus，并保存可 replay、可审计、可导出轨迹的完整记录。
> 同时支持独立账户的多 Agent 赛马，以及多个只读顾问 + 单一 Trader 的委员会。仓库带免 Key 回放和本地研究工作台。

## 相关精选列表

为以下列表准备小而实的 PR：

- `awesome-llm-agents`
- `awesome-ai-agents`
- `awesome-quant`
- `awesome-systematic-trading`
- `awesome-financial-ai`

每次投稿都应链接与列表范围匹配的文档页，并避免绩效类表述。
