---
seo_title: TraderHarness Daily Paper Trading for LLM Agents
description: Run a selected LLM trading Agent each market day with rate-limited one-minute quotes, A-share execution rules, conditional orders, safe stop, and downloadable full trajectories.
lang: en
---

# Daily paper trading

TraderHarness paper sessions reuse the same `ToolAgent`, phase protocol, conditional orders, and
`TradingBus.place_order()` execution path as backtests. Pre-market research, the two open windows,
the two close windows, tool corrections, and Agent memory therefore remain auditable.

## Clock modes

- **Live one-minute** is for today or a future exchange session. From market open, TraderHarness
  polls only the small attention set formed by positions, watchlist entries, and active conditional
  orders. It pauses during the lunch break. Each Agent window receives only five-minute bars that
  were complete at that point in time.
- **Accelerated acceptance** advances the four decision windows immediately. Recent sessions prefer
  the public one-minute snapshot; when unavailable, the UI explicitly reports a fallback to the local
  canonical five-minute dataset. This is a development acceptance mode, not a live quote claim.

The default attention set is eight securities at a 60-second interval, or roughly 0.13 requests per
second. Even the allowed maximum of 20 securities every 15 seconds is roughly 1.33 requests per
second, below the default Eastmoney cooperative budget of 2.5 requests per second. If Eastmoney
disconnects, it enters a five-minute cooldown and Sina fetches only the missing symbols under its own
two-request-per-second budget; the two sources are not redundantly hammered. Each provider still uses
a shared minimum interval, `Retry-After`, exponential backoff, and 403/429 circuit breaking.
TraderHarness does not rotate proxies to bypass an upstream limit.

## Use

Start the local console and open `/paper`:

1. select an Agent, session date, clock mode, and virtual capital;
2. start the daily paper session;
3. inspect account equity, positions, fills, tool/phase trajectory, and model messages;
4. use **Safe stop** to cancel cooperatively.

State is stored at `~/.traderharness/paper/<session-id>/state.json`; ordered UI events are appended to
`events.jsonl`, while full model requests/responses and tool arguments/results are written to
`trajectory.jsonl`. Both journals can be downloaded from the paper page. A service restart marks an
interrupted session as failed instead of pretending that it continued, while preserving the audit
journal. Cooperative safe-stop also drops any order tool returned by an in-flight model request after
cancellation and closes the session as `cancelled`.

## Quote-integrity rules

- Missing one-minute quotes for a held security stop execution; stale prices are never substituted.
- Missing non-held watchlist quotes produce a visible degraded state while verified symbols continue.
- One-minute observations only form completed five-minute decision windows. A-share limits, board
  lots, T+1, fees, and the single execution path remain in force.
- Broad-market research continues to use local point-in-time-safe daily, announcement, news,
  fundamental, and valuation data; the system never scans the entire market every minute.

!!! warning "Research only"
    Paper sessions use virtual capital for Agent evaluation and software research. They are not a live
    brokerage connection and do not constitute investment advice. Public displays should disclose
    quote latency, simulated fills, fees, and failures.
