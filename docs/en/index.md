---
seo_title: TraderHarness — Auditable Backtesting for LLM Trading Agents
description: Open-source infrastructure for leakage-resistant LLM trading-agent backtests on China A-shares, with point-in-time data, masked identities, deterministic replay, and auditable trajectories.
lang: en
---

# A fair historical market for LLM trading agents

LLM trading agents can appear successful for the wrong reason: the model may recognize a company, a date, or an entire historical price path from its training data. Ordinary look-ahead checks do not control that memory channel.

**TraderHarness is an open-source market environment for testing what an agent can do with only the evidence available at the simulated time.** It combines point-in-time data, deterministic date and entity masking, progressive 5-minute execution, one controlled order path, fingerprinted replay, and full-fidelity trajectories for reinforcement learning, behavior analysis, and evaluation.

[Run the no-key demo](quickstart.md){ .md-button .md-button--primary }
[See the masked experiment](masking-ab-showcase.md){ .md-button }
[Read the evaluation guide](guides/agent-stock-backtesting.md){ .md-button }

![TraderHarness local research console](https://hephaestlab.github.io/TraderHarness/assets/traderharness-demo.gif)

## Why another backtesting environment?

A prompt that says “do not use future information” is not an enforcement boundary. A credible evaluation must control what every tool returns, which prices may fill an order, who owns portfolio state, and whether the complete model/tool sequence can be replayed.

TraderHarness makes those requirements environment invariants:

- daily, intraday, announcement, news, and fundamental data are filtered by the simulated clock;
- dates become relative offsets such as `D+0`, while companies receive deterministic pseudonyms;
- 5-minute bars are revealed progressively before each decision and fill;
- every order goes through `TradingBus.place_order()`;
- agents receive read-only portfolio views;
- recorded model exchanges are matched by canonical request fingerprints and fail closed;
- serialized results, replay cassettes, and trajectory exports can be scanned with `traderharness audit`.

## Start in three commands

```bash
pip install "traderharness[llm,data,ui]"
traderharness data download --full
traderharness demo
```

The demo replays a recorded masked LLM trajectory without an API key, while the local engine re-executes matching, accounting, and metrics against canonical market data.

## What is included?

- Five years of full-market China A-share daily and 5-minute data.
- Announcements, policy news, fundamentals, valuation, dividends, and a CSI 300 benchmark.
- Single-agent runs, isolated multi-agent comparisons, and read-only-advisor committees with one executor.
- A local FastAPI/React research console for live progress, trade review, and cross-run comparison.
- Auditable trajectories that preserve full messages, tool schemas, tool calls, tool results, and phase metadata.

## Research boundary

TraderHarness is historical research infrastructure. It does not connect to a broker, provide copy trading, promise returns, or turn a backtest into investment advice. Historical results remain sensitive to costs, market impact, sampling, model drift, and data quality.

[GitHub repository](https://github.com/HephaestLab/TraderHarness) · [A-share dataset](https://huggingface.co/datasets/ANTICH/traderharness-ashare-5y) · [PyPI](https://pypi.org/project/traderharness/)
