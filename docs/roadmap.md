# Roadmap

This page tracks what TraderHarness actually ships versus what is planned. It exists so integrators can make
build-or-wait decisions without guessing from issue threads. Nothing below is a date commitment.

## ✅ Delivered in v1.0

- Five-year full-market A-share dataset (daily, 5-minute, announcements, policy news, fundamentals, valuation,
  dividends, CSI 300) with atomic incremental updates and integrity checks.
- Zero backtest-time market-data I/O after preload; a single order path through `TradingBus.place_order()`.
- Strict point-in-time masking across daily, intraday, news, announcement, fundamental, and sandbox egress.
- Deterministic calendar (`D+0`, `D-1`, …) and company-entity anonymization with board-semantics preservation.
- The three-phase pre-market / open-window / close-window agent loop with progressive intraday visibility.
- Independent multi-agent comparison (`traderharness compare`) and a single-executor, multi-role committee
  reference implementation (advisors are read-only; one Trader holds the order tool).
- Full-fidelity LLM exchange trajectories, fail-closed fingerprinted replay, and OpenAI-style SFT export.
- Serialized-artifact leakage auditing (`traderharness audit`).
- A local FastAPI + React research console, an unprivileged Docker image, PyPI packaging, and CI.

See [`CHANGELOG.md`](https://github.com/HephaestLab/TraderHarness/blob/main/CHANGELOG.md) for the itemized release
notes.

## 🚧 Next: paper trading

A simulated live-forward mode that reuses the existing engine, masking, and tool contract against a streaming
(rather than fully preloaded) market feed, so an agent card can be evaluated forward-in-time without code changes.
This is in design; it is **not available today** and nothing in this repository should be read as a claim
otherwise.

Constraints carried over from the backtest engine:

- the same `TradingBus.place_order()` path and risk checks;
- the same masking contract for any agent-facing egress;
- no shortcut that lets the sandbox or a tool observe data ahead of the simulated clock.

## 📋 Planned: live broker adapter

An adapter boundary so a paper-trading or research agent can be pointed at a real brokerage API. This depends on
paper trading landing first, and on a threat model for credentials and order authorization that matches the rest
of the project's security posture (see
[`SECURITY.md`](https://github.com/HephaestLab/TraderHarness/blob/main/SECURITY.md)). No broker integration
exists today.

## 📋 Planned: a hardened sandbox

The current Python sandbox (`execute_code` + `traderharness_api`) is scoped to keep a single trusted researcher
from accidentally reading the canonical dataset or starting a nested backtest — see
[Local server security](https://github.com/HephaestLab/TraderHarness/blob/main/AGENTS.md#local-server-security).
Hardening planned for a future release:

- resource and wall-clock isolation suitable for running untrusted or third-party agent cards;
- a narrower default `traderharness_api` surface with per-tool capability scoping;
- structured sandbox audit logs alongside the existing trajectory records.

## ❌ Non-goals

- **A public leaderboard or hosted multi-tenant service.** TraderHarness is local research infrastructure; see
  [Local server security](https://github.com/HephaestLab/TraderHarness/blob/main/AGENTS.md#local-server-security).
- **Market-impact modeling.** Historical fills use unadjusted prices and do not simulate how an agent's own orders
  would move the market.
- **Prescribing a trading methodology.** The environment stays agent-architecture-agnostic; see
  [Project comparison](comparison.md).
- **Real-time multi-agent interaction where agents affect each other's fills.** Every agent (or committee) trades
  against the same historical clock in its own isolated portfolio.

## How to help

Roadmap items above are the areas most likely to be accepted quickly. See
[Extending TraderHarness](extensions.md) for contribution contracts and
[`CONTRIBUTING.md`](https://github.com/HephaestLab/TraderHarness/blob/main/CONTRIBUTING.md) for the process.
