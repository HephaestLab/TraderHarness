---
title: How to Backtest LLM Trading Agents
seo_title: How to Backtest LLM Trading Agents Without Look-Ahead Bias | TraderHarness
description: A practical guide to point-in-time data, model-memory contamination, fair execution, deterministic replay, and auditable LLM trading-agent evaluation.
author: HephaestLab
lang: en
schema_type: TechArticle
datePublished: 2026-07-29
dateModified: 2026-07-29
faq:
  - question: Can an LLM trading backtest be deterministic?
    answer: >-
      Fresh hosted-model generation is not guaranteed to be deterministic, but complete exchanges can be recorded and replayed against canonical request fingerprints while matching, accounting, and metrics remain deterministic.
  - question: Does point-in-time data eliminate all backtest bias?
    answer: >-
      No. It controls information timing, but survivorship, costs, market impact, missing data, multiple testing, model selection, and historical memorization still require explicit treatment.
  - question: Why mask company names as well as dates?
    answer: >-
      A ticker, company, product, or announcement can reveal a historical event even when its date is hidden. Entity masking reduces that memory channel while preserving market rules needed for simulation.
  - question: Is TraderHarness a live trading bot?
    answer: >-
      No. TraderHarness is local research infrastructure for historical evaluation and trajectory generation. It does not route live orders or claim that historical performance predicts future returns.
---

# How to backtest LLM trading agents without look-ahead bias

**Short answer:** place the agent inside a market environment that advances on a historical clock. The agent may read only information that was public at that moment and may research or trade only through controlled tools. The environment owns matching, accounting, and risk controls and records the complete path from model request to final fill.

[TraderHarness](https://github.com/HephaestLab/TraderHarness) implements that contract for China A-shares.

[Run the no-key replay](../quickstart.md){ .md-button .md-button--primary }
[Open the masked experiment](../masking-ab-showcase.md){ .md-button }

!!! warning "A backtest is not investment advice"
    Historical simulation cannot establish future profitability. TraderHarness does not connect to a live brokerage account, provide copy trading, or promise returns.

## The three leakage problems

### 1. Ordinary look-ahead bias

A decision at time *t* must not receive a closing price, filing, revised fundamental, or news item that became available after *t*. Calendar-date filtering alone is insufficient when sources have different publication timestamps and revision histories.

Every data outlet must enforce the simulated clock: daily bars end before the current day, intraday bars stop at the current sub-window, announcements and news satisfy publication-time constraints, and fundamentals are selected by publication date rather than reporting period alone.

### 2. Historical memorization by the model

A general-purpose LLM may recognize a famous company, date, crash, rally, or announcement from training data. It can then answer from memory even when the data pipeline is point-in-time correct.

TraderHarness can replace absolute dates with relative offsets such as `D+0` and map companies to deterministic neutral identities. This is a contamination control, not proof that semantic re-identification is impossible; public artifacts still need a leakage audit.

### 3. Non-reproducible model calls

Hosted models can change even at temperature zero. Saving only the final trade is therefore inadequate. A useful replay artifact retains messages, tool schemas, model response fields, tool calls, tool results, provider configuration, phase, and sub-window.

TraderHarness fingerprints each canonical request. Replay fails closed when a prompt, tool schema, visible input, or call sequence differs.

## A minimum credible evaluation contract

| Boundary | Minimum requirement | Evidence to retain |
|---|---|---|
| Market data | Filter every outlet by the simulated clock | Source time, simulated time, visible rows |
| Identity | Mask dates and entities when contamination matters | Policy, seed, leakage audit |
| Execution | Reveal fillable prices only after the decision | Order time, visible window, fill time and price |
| Portfolio | Give the agent a read-only view | Orders, fills, cash, positions, corporate actions |
| Model | Record the complete request/tool loop | Model ID, provider, request fingerprint |
| Comparison | Use one clock and isolated accounts | Configuration, seed, benchmark series |
| Publication | Audit every shared artifact | Code revision, data manifest, audit report |

The core rule is: **the same visible data and action sequence must produce the same environment result.** Fresh model generation can be recorded and fingerprint-replayed; matching, accounting, and metrics must remain deterministic.

## A practical workflow

1. Define an agent card with its model, persona, allowed tools, risk limits, and three trading phases.
2. Prepare unadjusted prices and publication-time-aware daily, intraday, announcement, news, and fundamental data.
3. Run masked and unmasked versions under the same clock, capital, tools, and execution rules.
4. Route every order through the environment’s single matching path.
5. Record the complete model/tool trajectory and replay it by request fingerprint.
6. Report behavior and risk, not just return.

```bash
pip install "traderharness[llm,data,ui]"
traderharness data download --full
traderharness demo
```

Record and audit a new run:

```bash
traderharness run \
  --agent trend-breakout \
  --start 2024-03-04 \
  --end 2024-03-29 \
  --mask-entities \
  --record-replay run.jsonl

traderharness audit result.json run.jsonl
```

## What results should report

- period return, CSI 300 relative return, maximum drawdown, and risk-adjusted metrics;
- orders, fills, rejections, inactive days, turnover, exposure, and concentration;
- date range, universe, capital, fees, execution rules, and masking configuration;
- model and provider, agent card, data version, code revision, and artifact audit;
- omitted effects such as market impact, live latency, and provider drift.

## Frequently asked questions

### Can an LLM trading backtest be deterministic?

Fresh generation usually cannot be guaranteed bit-for-bit, but its complete interaction can be recorded and replayed against request fingerprints. The market environment’s matching and accounting remain deterministic.

### Does point-in-time data eliminate all backtest bias?

No. It controls information timing, but not survivorship, costs, market impact, missing data, multiple testing, model selection, or historical memorization.

### Why mask company names as well as dates?

A ticker, product, executive, or distinctive announcement can identify a historical event. Entity masking reduces those cues while retaining the board and market metadata required for correct trading rules.

### Is TraderHarness a live trading bot?

No. It is local historical research infrastructure and does not route live orders.

## Next steps

- Follow the [quickstart](../quickstart.md).
- Read the [contamination controls](../contamination.md).
- Compare TraderHarness with [TradingAgents, StockBench, and Qlib](../comparison.md).
- Inspect the implementation and tests on [GitHub](https://github.com/HephaestLab/TraderHarness).
