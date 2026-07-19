# CLI and local API reference

## Core CLI

```text
traderharness run       Run one agent
traderharness compare   Run isolated agents against one market clock
traderharness demo      Replay the bundled masked run without an API key
traderharness ui        Start the local FastAPI and React console
traderharness audit     Scan artifacts for entity and calendar leakage
traderharness export    Convert trajectories to SFT JSONL
traderharness data      Download, update, and inspect datasets
```

Run `traderharness <command> --help` for the installed version's options.

## Agent protocol

Custom agents implement the public protocol in `traderharness.agents.protocol`. They receive environment-controlled
context for the pre-market, open-window, and close-window phases. Read-only advisors can be composed behind a single
executor; see [Multi-role committees](design/multi-role-agent.md).

## Local HTTP API

`traderharness ui` serves:

- `GET /api/status` — dataset, provider, and local security status;
- `GET/POST /api/agents` — agent-card collection;
- `GET/PUT/DELETE /api/agents/{id}` — one agent card;
- `POST /api/runs` — start a backtest;
- `GET/DELETE /api/runs/{id}` — inspect or cancel a run;
- `WS /api/runs/{id}/events` — reconnectable sequenced event journal;
- `GET /api/results` — persisted result summaries;
- `GET /api/results/{file}` — complete artifact;
- `GET /api/results/{file}/analysis` — normalized UI research dossier;
- `POST /api/demo` — start the bundled replay;
- `GET /api/health` — process health.

The HTTP API is local tooling, not an authenticated public service. Keep the default localhost binding.
