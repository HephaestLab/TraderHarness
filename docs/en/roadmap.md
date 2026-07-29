---
seo_title: TraderHarness Roadmap — Agent Backtesting, Paper Trading, and Security Boundaries
description: Delivered capabilities, planned forward paper trading, possible broker adapters, sandbox hardening, and explicit non-goals for TraderHarness.
lang: en
---

# Roadmap

This page distinguishes delivered capability from planned work. It is not a date commitment.

## ✅ Delivered in v1.0

- Five years of full-market A-share data with atomic updates and integrity checks.
- Zero market-data I/O after preload and one `TradingBus.place_order()` path.
- Point-in-time masking across daily, intraday, news, announcements, fundamentals, and sandbox outlets.
- Relative dates and deterministic company pseudonyms that preserve board semantics.
- Pre-market, progressive open-window, and progressive close-window agent phases.
- Isolated multi-agent comparison and a reference read-only-advisor committee with one executor.
- Full-fidelity exchanges, fail-closed fingerprint replay, and trajectory export.
- Serialized-artifact leakage auditing.
- Local FastAPI/React console, non-root container, PyPI packaging, and CI.

See the [changelog](https://github.com/HephaestLab/TraderHarness/blob/main/CHANGELOG.md) for release-level details.

## 🚧 Next: forward paper trading

A simulated forward mode would reuse the current engine, masks, and tools while replacing full preload with a streaming feed. This feature is in design and **is not currently available**.

It must retain the same order path and risk checks, apply masking to every agent-facing outlet, and prevent tools or sandbox code from reading beyond the simulated clock.

## 📋 Planned: broker adapter {#live-broker-adapter}

A future adapter boundary may connect a research agent to a real brokerage API, after paper trading exists and a credential, authorization, and order-risk threat model matches the project’s [security policy](https://github.com/HephaestLab/TraderHarness/blob/main/SECURITY.md). There is no broker integration today.

## 📋 Planned: hardened sandbox {#hardened-sandbox}

The current sandbox protects one trusted researcher from accidentally reading canonical data or starting nested backtests. Future hardening may add resource isolation for third-party agent cards, narrower capability domains, and structured sandbox audit logs.

## ❌ Non-goals

- A public multi-tenant hosted service in the current security model.
- Market-impact modeling.
- A prescribed trading methodology.
- Agents interacting with each other or sharing fills in real time.

See [extensions](extensions.md) for contribution contracts.
