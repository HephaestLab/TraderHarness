---
seo_title: TraderHarness CLI and Local API Reference
description: Commands and localhost APIs for data installation, agent backtests, comparison, replay, auditing, trajectory export, REST endpoints, and WebSocket events.
lang: en
---

# CLI and local API

## Core commands

```text
traderharness run       Run one agent
traderharness compare   Run isolated agents under one market clock
traderharness demo      Replay the bundled masked run without an API key
traderharness ui        Start the local FastAPI + React console
traderharness audit     Scan artifacts for entity and calendar leakage
traderharness export    Convert trajectories to optional SFT JSONL
traderharness data      Download, update, and inspect the dataset
```

Use `traderharness <command> --help` for the authoritative options.

## Agent protocol

Custom agents implement the public protocol in `traderharness.agents.protocol`. The environment supplies controlled contexts for pre-market research, the progressive open window, and the progressive close window. Read-only advisors can be composed behind one executor; see [multi-role committees](design/multi-role-agent.md).

## Local HTTP API

`traderharness ui` exposes:

- `GET /api/status` — dataset, provider, and local security status;
- `GET/POST /api/agents` — agent card collection;
- `GET/PUT/DELETE /api/agents/{id}` — one agent card;
- `POST /api/runs` — start a backtest;
- `GET/DELETE /api/runs/{id}` — inspect or cancel a run;
- `WS /api/runs/{id}/events` — reconnectable ordered event stream;
- `GET /api/results` — persisted result summaries;
- `GET /api/results/{file}` — complete artifact;
- `GET /api/results/{file}/analysis` — normalized research dossier;
- `POST /api/demo` — start the bundled replay;
- `GET /api/health` — process health.

The HTTP API is a local research tool, not an authenticated public service. Keep its default localhost binding.
