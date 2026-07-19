# Extending TraderHarness

TraderHarness is designed to be extended without weakening its core invariants: zero backtest-time I/O, one order
path, strict point-in-time visibility, deterministic execution, and environment-owned portfolios (see
[Core architecture](architecture.md) and
[`AGENTS.md`](https://github.com/HephaestLab/TraderHarness/blob/main/AGENTS.md)). This page is a short contract
for the most common extension points. Open an issue before starting a large change; see
[`CONTRIBUTING.md`](https://github.com/HephaestLab/TraderHarness/blob/main/CONTRIBUTING.md).

## Data source adapters

A new market, or a new provider for the existing A-share dataset, should produce data that fits the canonical
schema described in [Data and licensing](data.md).

Contract:

- Implement a provider under `traderharness/data/providers/`; do not bypass `traderharness/data/datasets.py` or
  write directly into a running backtest's in-memory tables.
- Preserve point-in-time integrity: every record needs a stable natural key and, for anything not priced at the
  bar, a publication timestamp (`pub_date`-style column) that the masking layer can filter on.
- Add or extend a `data doctor` check (`scripts/data_doctor.py`) for the new table's required columns, date
  coverage, and duplicate-key invariants.
- Ship a small real-data fixture under `tests/fixtures/` and a loader test; do not substitute synthetic prices for
  acceptance validation (see the workspace rule on real data).

## Tools

Agent-facing tools live in `traderharness/tools/` and are registered through `traderharness/tools/registry.py`.

Contract:

- A tool handler receives the run's masked context; it must never reach past that context to read the canonical
  dataset or another agent's state.
- Every failure path returns a structured, actionable error that distinguishes "code does not exist" from "no
  data before this date" from "suspended" from "an ignored parameter" — a generic exception is not acceptable.
- New tools need JSON-schema argument validation, a unit test per failure mode, and an entry in the relevant agent
  card's `allowed_tools` list if a builtin agent should use it.
- Tools must not add a second order path. Trading stays behind `TradingBus.place_order()`.

## Sandbox backends

The `execute_code` tool and `traderharness_api` module are the sanctioned way for an agent to run arbitrary
analysis code against masked data (see [Preventing data leakage](contamination.md#egress-coverage)).

Contract:

- A sandbox backend must enforce the same path guard that blocks direct dataset reads (`sandbox/guard.py`) and the
  same wall-clock timeout.
- `traderharness_api` additions must resolve through the existing masked accessors; do not add a code path that
  returns an unmasked DataFrame or a real entity code.
- No sandbox backend may start a nested backtest or call back into the engine's order path.
- See [Roadmap](roadmap.md#planned-a-hardened-sandbox) for where sandbox isolation is headed; contributions that
  narrow the trusted surface are especially welcome.

## Evaluation metrics

Performance and behavioral metrics live in `traderharness/metrics/`.

Contract:

- A new metric is a pure function over an already-completed run's daily equity, trades, and decisions — it must
  not require re-running the backtest or touching provider APIs.
- Document the formula and its edge cases (empty trade history, single trading day, missing benchmark data) in the
  docstring, and add a report/JSON-export test.
- If the metric is agent-comparative (e.g., a ranking), it belongs in `traderharness/metrics/comparison.py`, not in
  the per-agent report.

## Broker adapters

There is no live broker adapter in v1.0; see [Roadmap](roadmap.md#planned-live-broker-adapter). Design
discussions and prototypes are welcome as issues, but a broker integration should not be wired into the backtest
`TradingBus` — historical simulation and live order routing are different trust boundaries and must stay
separated.

## Frontend (webui)

The research console is a local-only React app in `webui/`.

Contract:

- New views read from the existing REST/WebSocket API (`traderharness/server/app.py`); do not add client-side
  logic that re-derives masked data from raw fields.
- Keep Chinese-language labels consistent with `webui/src/locale.ts` rather than hardcoding literal strings in
  components.
- Add a Vitest unit test for new components and, for a new page or workflow, a Playwright scenario under
  `webui/tests/e2e` (or extend `webui/scripts/capture-demo.mjs` if it should also appear in the README GIF).

## Before opening a pull request

1. Add a failing test that demonstrates the new contract.
2. Implement without weakening any invariant in
   [`AGENTS.md`](https://github.com/HephaestLab/TraderHarness/blob/main/AGENTS.md#non-negotiable-invariants).
3. Run the focused suite, then the full suite (`pytest tests/ --no-header -q`, `ruff check`, and for
   engine/masking/tools/data/sandbox changes, a real replay or backtest with trace inspection).
4. State plainly which real-data runs were performed and which were not.
