---
seo_title: TraderHarness Daily Paper Trading for LLM Agents
description: Run a selected LLM trading Agent each market day with rate-limited one-minute quotes, A-share execution rules, conditional orders, safe stop, and downloadable full trajectories.
lang: en
---

# Daily paper trading

TraderHarness paper sessions reuse the same `ToolAgent`, phase protocol, conditional orders, and
`TradingBus.place_order()` execution path as backtests. Pre-market research, the two open windows,
the two close windows, tool corrections, and Agent memory therefore remain auditable.

## Multi-Agent arena

A paper session can host one to four Agents. Every Agent has isolated cash, positions, conditional
orders, fills, equity, and error state while sharing the same session date, initial capital, market
cutoffs, matching rules, and fee model. The arena overlays their equity curves and live ranking; an
Agent selector focuses positions, fills, model decisions, and the complete work trace.

Agents execute sequentially within a trading day to preserve deterministic results and avoid races on
shared in-memory market frames. Each isolated portfolio still receives only the snapshot visible at
the relevant cutoff. This is a fair strategy/Agent comparison, not a concurrent latency benchmark.

## Minute market and news broadcast

The arena turns attention-set quotes into a compact market pulse with last price, intraday change,
and recent minute-volume ratio. Material price or volume moves receive higher visual priority. Its
news desk presents point-in-time-safe items that matter to the current work:

- announcements related to positions, watchlists, or active conditional orders;
- high-impact policy flashes from major Chinese financial and government authorities;
- provider-classified high-priority market flashes.

The live flash adapter fetches at most one page per polling interval and inherits the data pipeline's
rate gate, backoff, and circuit breaker. Broadcast items are deduplicated for presentation; Agents
continue to access the complete point-in-time-safe stores through their normal tools.

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

1. select one to four Agents, session date, clock mode, and virtual capital per account;
2. start the daily paper session;
3. compare equity and ranking, then inspect important broadcasts, positions, fills, tool/phase
   trajectory, and model messages;
4. use **Safe stop** to cancel cooperatively.

State is stored at `~/.traderharness/paper/<session-id>/state.json`; ordered UI events are appended to
`events.jsonl`, while full model requests/responses and tool arguments/results are written to
`trajectory.jsonl`. Both journals can be downloaded from the paper page. A service restart marks an
interrupted session as failed instead of pretending that it continued, while preserving the audit
journal. Cooperative safe-stop also drops any order tool returned by an in-flight model request after
cancellation and closes the session as `cancelled`.

The audit workbench parses tool arguments and bounded result previews into readable fields. Python
submitted through tools such as `execute_code` is rendered with line numbers, its own scrolling area,
and a copy action instead of an escaped JSON string. The Results page reuses the same structured
renderer, so backtest and paper-session traces have a consistent reading model.

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
