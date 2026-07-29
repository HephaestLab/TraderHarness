---
seo_title: TraderHarness FAQ — LLM Agent Backtesting, Leakage, and Replay
description: Answers about historical memorization, point-in-time data, no-key replay, independent agents versus committees, A-share data, paper trading, and local security.
lang: en
---

# Frequently asked questions

## Why test a new LLM on history it may have seen?

A knowledge cutoff is not an information barrier. TraderHarness removes absolute dates and company identities at agent-facing boundaries, reveals intraday bars progressively, and audits serialized artifacts. Famous events may still be inferred semantically, so serious work should disclose masks and include masked/unmasked controls when appropriate.

## Does entity masking change market rules?

No. Real codes are shuffled within compatible A-share board groups. A pseudocode preserves the historical board’s price-limit behavior, while matching uses the internally resolved real symbol.

## Is the full dataset synthetic?

No. Acceptance runs and public artifacts use historical full-market data. The no-key demo replays a real masked run rather than substituting generated prices.

## Does `compare` use one shared portfolio?

No. Every compared agent has an isolated portfolio. A TradingAgents-style committee instead has read-only advisors, one executor, and one portfolio.

## Can replay silently call a model provider?

No. Requests are fingerprinted. A mismatch or exhausted cassette fails closed.

## Can I expose the console as a hosted service?

Not safely in its current form. Agent-authored Python can execute behind the local HTTP server. The sandbox protects backtest integrity, not a hostile multi-tenant deployment. Keep it on localhost.

## Does a profitable backtest mean the strategy is deployable?

No. TraderHarness does not model market impact, and historical performance does not guarantee future returns. It is research infrastructure, not a broker or investment advisor.

## Is `traderharness demo` paper trading?

No. `demo` replays a recorded masked historical run without network calls. Forward paper trading over streaming data is planned but does not exist today.
