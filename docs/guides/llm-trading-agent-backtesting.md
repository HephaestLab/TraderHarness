---
title: How to Backtest LLM Trading Agents Without Look-Ahead Bias
seo_title: How to Backtest LLM Trading Agents Without Look-Ahead Bias | TraderHarness
description: A practical framework for point-in-time data, fair execution, deterministic replay, contamination controls, and auditable trajectories in LLM trading-agent backtests.
author: HephaestLab
lang: en
schema_type: TechArticle
datePublished: 2026-07-29
dateModified: 2026-07-29
alternate_zh: https://hephaestlab.github.io/TraderHarness/guides/agent-stock-backtesting/
alternate_en: https://hephaestlab.github.io/TraderHarness/guides/llm-trading-agent-backtesting/
faq:
  - question: Can an LLM trading backtest be deterministic?
    answer: >-
      Fresh hosted-model generation is not guaranteed to be deterministic, but the full exchange can be recorded and replayed against canonical request fingerprints while matching, accounting, and metrics remain deterministic.
  - question: Does point-in-time data eliminate all backtest bias?
    answer: >-
      No. It addresses information timing, but universe construction, survivorship, costs, market impact, missing data, multiple testing, and model-selection bias still require explicit treatment.
  - question: Why mask company names as well as dates?
    answer: >-
      A recognizable ticker, company, product, or announcement can reveal a historical event even when the date is hidden. Entity masking reduces that memory channel while retaining the market rules needed for simulation.
  - question: Is TraderHarness a live trading bot?
    answer: >-
      No. TraderHarness is local research infrastructure for historical evaluation and trajectory generation; it does not route live orders or claim that historical performance predicts live returns.
---

# How to Backtest LLM Trading Agents Without Look-Ahead Bias

中文：[Agent 炒股如何回测？AI / LLM 股票交易 Agent 回测指南](agent-stock-backtesting.md)

An LLM trading-agent backtest is credible only when the agent sees exactly what would have been public at the simulated time, can trade only at prices revealed after its decision, and leaves enough evidence for the run to be reproduced and audited. A prompt that says “do not use future information” is not sufficient: the restriction must be enforced by the environment.

[TraderHarness](https://github.com/HephaestLab/TraderHarness) is an open-source Python environment built around that contract. It currently targets China A-shares and combines point-in-time data masking, date and entity anonymization, progressive 5-minute execution, fingerprinted replay, and full-fidelity trajectory export.

## The three leakage problems

### 1. Ordinary look-ahead bias

This is the familiar backtesting error: a decision made at time *t* receives a closing price, filing, revised fundamental, or news item that was not available until after *t*. Filtering rows by calendar date alone is not enough when different sources have publication timestamps and revision histories.

The environment should enforce the information boundary at every data outlet:

- daily bars must end before the simulated trading day;
- intraday bars must stop at the current sub-window;
- announcements and news must satisfy their publication-time constraints;
- fundamentals must be selected by publication date, not only by reporting period;
- portfolio state must be read-only to the agent.

### 2. Historical memorization by the model

A general-purpose LLM may recognize a famous company, date, crash, rally, or announcement from its training data. The model can then answer from memory even when the data pipeline itself is point-in-time correct.

Deterministic pseudonyms reduce these cues. TraderHarness can replace absolute dates with relative offsets such as `D+0` and map company names and stock codes to neutral identities while preserving market-rule metadata. This is a contamination control, not proof that semantic re-identification is impossible; serialized outputs still need a leakage audit.

### 3. Non-reproducible model calls

Even at temperature zero, a hosted model may change or return a different response. Saving only the final trade is therefore inadequate. A useful replay artifact must retain the complete messages, tool schemas, model response, reasoning fields made available by the provider, tool calls, tool results, and the phase of the simulated market.

TraderHarness fingerprints the canonical request behind each recorded response. Replay fails closed when a prompt, tool schema, visible input, or call sequence differs, rather than silently returning the wrong cached answer.

## A minimum credible evaluation contract

| Boundary | Requirement | Evidence to retain |
|---|---|---|
| Data | Point-in-time filtering at every agent-facing outlet | source timestamp, simulated clock, visible rows |
| Identity | Mask dates and entities when testing memorization risk | seed, mapping policy, post-run leakage audit |
| Execution | Reveal intraday data progressively and fill only after a decision | order time, visible window, fill time and price |
| Portfolio | Give the model a read-only view; let the environment own state | orders, fills, cash, positions, corporate actions |
| LLM | Record the full request/response/tool sequence | provider/model metadata and request fingerprint |
| Comparison | Isolate portfolios and keep the market clock identical | resolved configuration, seed, benchmark series |
| Publication | Audit artifacts before sharing | audit report, dataset manifest, code version |

The key principle is simple: the same visible market data and action sequence should produce the same environment result. Model generation can be recorded once and replayed; market accounting and matching must remain deterministic.

## A practical TraderHarness workflow

Install the package and canonical dataset, then run the bundled masked replay:

```bash
pip install "traderharness[llm,data,ui]"
traderharness data download --full
traderharness demo
```

The demo does not call an LLM provider, but it does evaluate the recorded trajectory against the local canonical market data. The full dataset is downloaded separately and verified against its release manifest.

To record a new run:

```bash
traderharness run \
  --agent trend-breakout \
  --start 2024-03-04 \
  --end 2024-03-29 \
  --mask-entities \
  --record-replay run.jsonl
```

Before publishing a result or converting it into training data:

```bash
traderharness audit result.json run.jsonl
traderharness export sft result.json --output training.jsonl
```

For multiple independent agents, `traderharness compare` gives each agent an isolated portfolio. For a TradingAgents-style committee, advisors remain read-only and exactly one executor receives trading tools. These are different evaluation contracts and should not be reported as if they were interchangeable.

## What a backtest result should report

Return and Sharpe ratio are not enough. A reproducible LLM-agent result should also state:

- the exact date range, universe, benchmark, initial capital, fees, and execution rules;
- the model and provider configuration, agent card, tool schemas, and masking seed;
- whether calls were live, recorded, or replayed;
- the number of decisions, orders, fills, rejected orders, and no-trade days;
- maximum drawdown, turnover, exposure, concentration, and behavior diagnostics;
- the artifact audit result and code/data versions;
- important omissions such as market impact, live latency, or survivorship treatment.

This makes the claim inspectable. It also separates “the model produced an interesting behavior under a controlled historical environment” from “this strategy is safe or profitable in live trading.” The latter does not follow from a historical simulation.

## Frequently asked questions

### Can an LLM trading backtest be deterministic?

The historical environment, matching, accounting, and replay can be deterministic. A fresh hosted-model call generally cannot be guaranteed deterministic, so record the full exchange and use fingerprint-validated replay for exact reproduction.

### Does point-in-time data eliminate all backtest bias?

No. It addresses information timing, but universe construction, survivorship, transaction costs, market impact, missing data, multiple testing, and model-selection bias still require explicit treatment and disclosure.

### Why mask company names as well as dates?

Date masking hides the calendar period, but a recognizable ticker, company, product, or announcement can still reveal the event. Entity masking reduces that second channel while retaining the trading rules the simulator needs.

### Is TraderHarness a live trading bot?

No. It is local research infrastructure for historical evaluation and trajectory generation. It does not route live orders and does not claim that historical performance predicts live returns.

## Next steps

- Follow the [quickstart](../quickstart.md) for installation and the local research console.
- Read the [contamination model](../contamination.md) for precise data-egress rules.
- Review the [architecture invariants](../architecture.md) before adding an agent or tool.
- Inspect the [comparison matrix](../comparison.md) to decide whether you need an agent framework, a market environment, or both.
- Use the [GitHub repository](https://github.com/HephaestLab/TraderHarness) for source code, issues, and releases.
