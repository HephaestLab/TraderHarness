# Agent guide for TraderHarness

This file is the public operating guide for coding agents working in this repository.

## Project map

- `traderharness/core/`: clock, engine, portfolio, matching, masking, events, and run results
- `traderharness/agents/`: agent protocol, three-phase LLM loop, cards, memory, replay clients, and committees
- `traderharness/tools/`: the agent-facing market, analysis, portfolio, trading, watchlist, news, and sandbox tools
- `traderharness/data/`: canonical loaders, release manifests, providers, updates, and entity templates
- `traderharness/trajectory/`: full-fidelity collection, deterministic replay, and SFT conversion
- `traderharness/metrics/`: performance, benchmark, behavior, comparison, and reports
- `traderharness/server/`: local FastAPI REST/WebSocket application
- `webui/`: React research console
- `tests/`: unit and real-data integration tests

The Python import package and CLI name are both `traderharness`. The default local state directory is
`~/.traderharness`, overridable with `TRADERHARNESS_HOME`.

## Non-negotiable invariants

1. Market data is preloaded. Backtest-time data access must remain in-memory.
2. `TradingBus.place_order()` is the only matching and order path.
3. Daily, intraday, news, announcement, and fundamental egress must remain point-in-time safe.
4. Agent-facing calendar dates and entities must pass through the configured masks.
5. Agents receive read-only portfolio views; the environment owns portfolio state.
6. The same visible data and action sequence must produce the same environment result.
   Sandbox code runs in-process, so entry points (CLI group, pytest conftest) pin `PYTHONHASHSEED`
   via `traderharness._hashseed.ensure_fixed_hash_seed()` — otherwise `set` iteration order leaks
   into tool output and breaks cassette fingerprints across processes.
7. Historical fills and corporate actions use unadjusted prices.
8. Sandbox code may analyze visible data, but must not read the canonical dataset directly or start nested backtests.
9. Independent multi-agent compare runs agents **sequentially within each trading day** (still isolated portfolios).
   Concurrent `on_day` scheduling previously raced on shared in-memory market frames and broke fingerprinted replay.

Do not add a shortcut around these boundaries, including for examples or UI endpoints.

## Development workflow

Use Python 3.10–3.12. On Windows:

```powershell
.venv\Scripts\python.exe -m pip install -e ".[all]"
.venv\Scripts\python.exe -m pytest tests\unit\path\to\test_file.py --no-header -q
.venv\Scripts\python.exe -m ruff check traderharness tests
```

For a new feature or bug fix:

1. Add the smallest test that demonstrates the required contract.
2. Run it and confirm the expected failure.
3. Implement the change without weakening an invariant.
4. Run the focused suite, then `tests/`.
5. For engine, masking, tools, data, or sandbox changes, run a real replay/backtest and inspect the trajectory.

Frontend checks:

```bash
cd webui
npm ci
npm test
npm run build
npm run test:e2e
```

## Adding an agent

Agent cards live in `~/.traderharness/agents/<id>.json`. Implementations must follow the public protocol in
`traderharness/agents/protocol.py` and participate in all three phases:

1. pre-market research, where orders are disabled;
2. the progressively revealed open window;
3. the progressively revealed close window.

For a multi-role system, advisors must remain read-only and only one executor may receive trading tools. See
`docs/design/multi-role-agent.md`.

## Data and artifacts

The canonical production dataset is:

```text
~/.traderharness/dataset/
├── daily.parquet
├── 5min_clean/
├── announcements.parquet
├── news_cls.parquet
├── fundamentals.parquet
├── valuation.parquet
├── dividends.parquet
├── index_300.parquet
└── metadata.json
```

Do not silently substitute synthetic prices or a reduced universe for a real-data acceptance run. Replay is the
approved deterministic no-network path.

Before sharing a result, replay cassette, comparison, or SFT export, run:

```bash
traderharness audit <artifact>
```

## Local server security

The Web UI is a local research tool. The Python sandbox protects backtest integrity, not a hostile multi-tenant
server. Keep it bound to localhost and never expose it directly to the public internet.
