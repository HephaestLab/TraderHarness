---
description: TraderHarness 发布分发手册：GitHub 元数据、Show HN、Reddit、X、知乎、掘金、V2EX、Product Hunt 发布稿与 awesome-list 投稿模板。
---

# 发布分发手册

本页是可复制的元数据与发布草稿。仅在公开仓库、安装包、数据集、文档站与容器链接全部上线后再执行外发。
所有稿件中的链接已就位：

- 仓库：<https://github.com/HephaestLab/TraderHarness>
- 文档站：<https://hephaestlab.github.io/TraderHarness/>
- 数据集：<https://huggingface.co/datasets/ANTICH/traderharness-ashare-5y>
- PyPI：<https://pypi.org/project/traderharness/>

## GitHub 仓库元数据（已配置）

**描述**

> Contamination-resistant A-share backtesting, evaluation, replay, and trajectory (SFT) export for autonomous LLM trading agents.

**Topics**

```text
llm-agents, autonomous-agents, quantitative-trading, algorithmic-trading,
backtesting, trading-bot, a-share, china-stocks, benchmark, deepseek,
multi-agent, agentic-ai, synthetic-data, sft, rlhf, financial-ai,
market-simulation, fastapi, react, python
```

社交预览图使用 `docs/assets/social-preview.png`（需在仓库 Settings 手动上传，上传前目视确认 GitHub 的裁切效果）。

## Show HN

**Title**

> Show HN: TraderHarness – contamination-resistant backtesting for autonomous trading agents

**Draft**

> Historical LLM trading evaluations are easy to leak: a model can recognize the date, company, or a full intraday
> price path. TraderHarness is an open-source A-share market environment that treats those as systems boundaries.
> It preloads five years of full-market data, progressively reveals 5-minute bars, anonymizes dates and companies,
> routes every fill through one matching path, and records full trajectories with fail-closed replay. It supports
> isolated agent comparisons and TradingAgents-style committees where only one executor can trade. A no-key replay
> and local FastAPI/React research console are included. I would especially value feedback on the masking threat
> model and trajectory format.

## Reddit r/algotrading

**Title**

> Open-source environment for auditing LLM trading agents on point-in-time A-share data

**Draft**

> I built TraderHarness to separate the agent architecture from the historical market contract. The environment
> owns the portfolio and simulated clock, masks future data at each tool boundary, reveals open/close 5-minute
> windows progressively, and exports complete model/tool/fill trajectories. Date and company identities can be
> deterministically anonymized to reduce memorized-answer contamination. It is research infrastructure rather than a
> strategy claim; I am looking for review of execution fairness, metrics, and data integrity.

## Reddit r/LocalLLaMA

**Title**

> TraderHarness: turn LLM trading runs into SFT training data (full-fidelity trajectories, fingerprinted replay)

**Draft**

> Every run in TraderHarness persists each LLM call with the complete message list, full tool schema, assistant
> content and reasoning, every tool call and its arguments, and phase metadata. `traderharness export sft` emits
> OpenAI-style JSONL gated by entity/date leakage checks, and replay cassettes reproduce runs deterministically
> with no API key. The bundled environment is a masked A-share market (five years of full-market daily + 5-minute
> data) with one controlled order path, so the generated trajectories come from a fair, auditable setting.
> Dataset: <https://huggingface.co/datasets/ANTICH/traderharness-ashare-5y>

## X / Twitter 线程（英文）

1/ Historical LLM trading evals are quietly broken: the model may recognize the date, the company, even the exact price path it's being tested on. We built TraderHarness to fix that at the environment level. 🧵

2/ TraderHarness preloads 5 years of full-market A-share data, then masks every outlet: point-in-time filtering, relative dates (D+0/D-1), deterministic company pseudonyms. 5-min bars are revealed progressively — no peeking, then picking a better earlier fill.

3/ Every order goes through one path: TradingBus.place_order(). Same clock, isolated portfolios — so multi-agent comparisons are fair, and replay cassettes reproduce runs bit-for-bit with zero API keys.

4/ Bonus: every run doubles as a data synthesizer. Full-fidelity trajectories → `traderharness export sft` → OpenAI-style JSONL, gated by leakage audits. Dataset: <https://huggingface.co/datasets/ANTICH/traderharness-ashare-5y>

5/ Open source (Apache-2.0), local-first, with a pixel-office research console. Repo: <https://github.com/HephaestLab/TraderHarness> — feedback on the masking threat model very welcome.

## 知乎（回答体，适配"如何评价 LLM 炒股/交易 Agent"类问题）

> 先说结论：目前大多数"LLM 交易"实验的评测结论是不可信的，因为模型很可能记得它被测试的那段历史。
>
> 一个通用大模型在 2024 年的 A 股上"回测"，它看到 600519 和 3 月的日期，就可能直接调用训练语料里的记忆——这不是交易能力，是背诵。行业里有 TradingAgents 这样的角色框架，但"把 Agent 放进历史里考试"这件事一直没有规范化的考场。
>
> 我们开源了 TraderHarness，把抗污染做成环境不变量：五年全市场真实数据预加载后，每个数据出口都过模拟时钟过滤（时点掩码）；日期变成 D+0/D-1 相对偏移；公司变成确定性伪身份（600519 → 公司-600731）；分钟线随窗口渐进揭示，决策时不可见的价格不可成交；所有订单只走一条 TradingBus 路径。
>
> 同时它也是一个数据合成器：每次模型调用的完整消息、工具 schema、推理过程全部落盘成轨迹，可指纹回放、可审计泄漏、可导出 SFT JSONL。数据集已发 Hugging Face。
>
> 仓库：<https://github.com/HephaestLab/TraderHarness>（Apache-2.0，本地运行，带免密回放和像素办公室研究台）。欢迎挑刺，尤其是掩码威胁模型。

## 掘金 / V2EX（分享体）

**标题**

> 开源 TraderHarness：给 LLM 交易 Agent 一个不容易偷看答案的 A 股回测环境

**正文**

> 大多数交易 Agent Demo 把注意力放在 prompt 和角色，却没有把历史时点、分钟级可见性、公司/日期记忆污染、
> 公平成交和完整证据链做成环境不变量。TraderHarness 用五年 A 股全市场真实数据，在每个数据出口执行时序遮罩，
> 对日期与公司做确定性匿名化，所有订单只走 TradingBus，并保存可 replay、可审计、可导出轨迹的完整记录。
> 同时支持独立账户的多 Agent 赛马，以及多个只读顾问 + 单一 Trader 的委员会。仓库带免 Key 回放和本地研究工作台。
>
> GitHub: <https://github.com/HephaestLab/TraderHarness>
> 文档: <https://hephaestlab.github.io/TraderHarness/>
> 数据集: <https://huggingface.co/datasets/ANTICH/traderharness-ashare-5y>

## Product Hunt

**Tagline（60 字符内）**

> Contamination-resistant backtesting for LLM trading agents

**Description（260 字符内）**

> TraderHarness is an open-source A-share market environment for evaluating LLM trading agents without data leakage: point-in-time masking, entity/date anonymization, progressive 5-minute execution, fingerprinted replay — plus full-fidelity trajectory export for SFT training data.

**First comment**

> Hi Product Hunt! I built TraderHarness after noticing that most LLM trading evaluations can be quietly invalidated by memorization — the model recognizes the dates and companies it's tested on. TraderHarness treats that as a systems boundary: masked egress, relative dates, deterministic pseudonyms, one order path, and auditable trajectories. It's local-first research infrastructure (Apache-2.0), not a trading bot. I'd love your feedback on the masking threat model and the trajectory format. Docs: <https://hephaestlab.github.io/TraderHarness/>

## awesome-list 投稿模板

每个列表一条小而实的 PR，链接到与列表范围匹配的文档页，不做绩效宣称：

- `awesome-llm-agents` →
  `| [TraderHarness](https://github.com/HephaestLab/TraderHarness) | Contamination-resistant A-share backtesting environment for LLM trading agents: point-in-time masking, entity/date anonymization, fingerprinted replay, trajectory export. |`
- `awesome-ai-agents` → 同上
- `awesome-quant` →
  `| [TraderHarness](https://github.com/HephaestLab/TraderHarness) | LLM-native A-share backtesting environment with strict point-in-time masking and deterministic replay. |`
- `awesome-systematic-trading` → 同上（链接到 [核心架构](architecture.md)）
- `awesome-financial-ai` →
  `| [TraderHarness](https://github.com/HephaestLab/TraderHarness) | Evaluate LLM trading agents on masked five-year A-share data; exports full-fidelity SFT trajectories. |`
