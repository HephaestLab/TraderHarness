---
seo_title: Extending TraderHarness — Data Providers, Agent Tools, and Metrics
description: Contracts for adding providers, tools, sandbox capabilities, metrics, and frontend views without weakening point-in-time safety, the single order path, or deterministic execution.
lang: en
---

# Extending TraderHarness

Extensions must preserve zero backtest-time I/O, one order path, strict point-in-time visibility, deterministic execution, and environment-owned portfolios. Review the [architecture](architecture.md), [`AGENTS.md`](https://github.com/HephaestLab/TraderHarness/blob/main/AGENTS.md), and [`CONTRIBUTING.md`](https://github.com/HephaestLab/TraderHarness/blob/main/CONTRIBUTING.md) before a large change.

## Data providers

- Implement providers under `traderharness/data/providers/`; do not bypass `traderharness/data/datasets.py` or mutate tables used by a running backtest.
- Give every record a stable natural key and every non-price record a publication timestamp that masking can enforce.
- Extend data-doctor checks for required columns, date coverage, and duplicates.
- Add a small real-data fixture and loader tests. Do not substitute synthetic prices in acceptance runs.

## Agent tools

- Tool handlers receive the run’s masking context and may not read the canonical dataset or another agent’s state.
- Return structured, actionable errors for invalid symbols, unavailable dates, suspensions, and ignored parameters.
- Add JSON-schema validation and tests for each failure mode.
- Never create a second order path. Trading always uses `TradingBus.place_order()`.

## Sandbox backends

- Apply the existing path guard and wall-clock timeout.
- Resolve new `traderharness_api` capabilities through masked accessors.
- Never return unmasked frames or real entity codes.
- Never start nested backtests or call the engine’s order path.

## Metrics

Metrics under `traderharness/metrics/` are pure functions over completed daily equity, fills, and decisions. Document formulas and edge cases and add report/JSON tests. Cross-agent rankings belong in `metrics/comparison.py`.

## Broker adapters

The current release has no live broker adapter. Historical matching and live authorization are separate trust boundaries and must not share `TradingBus`.

## Frontend

The React console reads existing REST/WebSocket APIs and must not reconstruct unmasked fields client-side. New components need Vitest coverage; new flows need browser E2E coverage.

## Before a pull request

1. Add the smallest failing contract test.
2. Implement without weakening repository invariants.
3. Run focused tests, then the full suite and lint checks.
4. For engine, masking, tools, data, or sandbox changes, run a real replay/backtest and inspect the trajectory.
5. State exactly which real-data checks were and were not performed.
