---
seo_title: Preventing Data Leakage and Historical Memorization in LLM Trading Backtests
description: How TraderHarness enforces point-in-time masking, relative dates, company pseudonyms, progressive intraday visibility, and artifact leakage audits.
lang: en
---

# Backtest LLM trading agents without data leakage

TraderHarness treats historical contamination as an environment boundary, not a promise in a prompt.

## Core controls

**Point-in-time masking:** every value exposed to an agent is filtered against the simulated clock. Daily bars end before the trading day, 5-minute bars stop at the current sub-window, and fundamentals must have been published by the current date.

**Date anonymization:** absolute calendar dates become offsets relative to the simulated present. Today is `D+0`; the previous calendar day is `D-1`. Intraday times remain visible.

**Entity masking:** real A-share codes and known aliases are mapped through a deterministic run-wide bijection to neutral identities. Codes are shuffled inside compatible board groups so historical price-limit rules still apply.

**Three-phase trading:** pre-market research cannot trade; 09:30–10:00 and 14:30–15:00 windows reveal 5-minute data progressively.

## Egress coverage {#egress-coverage}

Masking applies to:

- daily and intraday bars;
- screening, fundamentals, valuation, announcements, and policy news;
- portfolio and watchlist views;
- DataFrames returned inside the Python sandbox;
- model responses, reasoning fields, tool arguments, and committee memos;
- cross-day memory, saved trajectories, replay cassettes, comparisons, and exports.

Agent-visible pseudocodes are resolved internally before matching. The portfolio is rendered through the same forward mapping, so an agent never needs the real code.

![Date and entity masking](https://hephaestlab.github.io/TraderHarness/assets/dual-mask.svg)

## Artifact audit

```bash
traderharness audit result.json replay.jsonl export.parquet
```

The auditor checks known company aliases, six-digit A-share codes, absolute ISO and Chinese dates, and month-day forms. Passing this lexical contract does not prove that a model cannot infer a company from distinctive products, executives, financial patterns, or events. Public results should disclose masking configuration and seed and compare masked with unmasked runs when semantic re-identification matters.

## Execution leakage

Information masking is meaningless if a model can inspect a complete intraday window and then choose an earlier favorable fill. TraderHarness reveals one sub-window, requests a decision, and only then considers eligible prices. Every order passes through `TradingBus.place_order()`.
