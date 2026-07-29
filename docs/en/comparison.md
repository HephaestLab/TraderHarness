---
seo_title: TraderHarness vs TradingAgents, StockBench, Qlib, and Traditional Backtesters
description: Compare agent orchestration, historical market simulation, contamination controls, execution, replay, and trajectory evidence across adjacent projects.
lang: en
---

# Comparison with adjacent projects

TraderHarness is environment and evidence infrastructure. It can host different agent architectures without prescribing an investment methodology.

| Project | Primary responsibility | Native decision unit | What integration still needs |
|---|---|---|---|
| **TraderHarness** | Historically valid market, execution, portfolio, evaluation, replay, trajectories | Autonomous agent, isolated comparison, or single-executor committee | An agent card or external framework |
| **TradingAgents** | Multi-role analysts, debate, risk, and trader workflow | Prescribed role graph | A strict benchmark market and order contract |
| **StockBench** | Standardized stock-reasoning benchmark tasks | Benchmark task or prediction | Persistent portfolio and autonomous tool loop |
| **Qlib** | Quant data, models, experiments, and strategies | ML model or code strategy | LLM-native tools and language-output contamination controls |
| **Backtrader / vn.py** | Strategy execution and trading infrastructure | Code strategy | Autonomous LLM research loop, masking, and trajectory contract |

## Independent agents versus a committee

`traderharness compare` is a race: every agent has its own cash, positions, memory, and portfolio. All agents share a market clock and are scored independently.

A committee is one competitor: read-only advisors may research, but exactly one trader owns the order tool and one portfolio. See [multi-role committees](design/multi-role-agent.md).

## Integrate your framework

An external LangGraph, TradingAgents, or custom orchestrator should implement the public agent protocol and return a final decision. Market reads and orders still pass through TraderHarness, inheriting the same clock, masks, progressive intraday visibility, and matching rules.
