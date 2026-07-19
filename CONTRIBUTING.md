# Contributing to TraderHarness

Thank you for improving autonomous-agent evaluation infrastructure.

## Before opening a pull request

1. Open an issue for architectural changes or new data providers.
2. Add a failing test before changing engine, masking, sandbox, or order behavior.
3. Use real point-in-time market data for integration validation. Do not silently replace it with generated data or a reduced universe.
4. Preserve the core invariants: zero backtest-time I/O, strict historical visibility, one order path, deterministic execution, and environment-owned portfolios.

## What to contribute

[Extending TraderHarness](docs/extensions.md) has short contracts for the extension points we actively want help
with: data source adapters, tools, sandbox backends, evaluation metrics, broker adapters, and the frontend. Check
[the roadmap](docs/roadmap.md) first — it lists what already exists, what is in progress, and explicit non-goals,
so you do not spend effort on something that conflicts with the project's scope.

## Checks

```bash
.venv/Scripts/python -m pytest tests/ --no-header -q
.venv/Scripts/python -m ruff check traderharness scripts tests
cd webui
npm test
npm run build
npm run test:e2e
```

Explain which real-data runs were performed and which were not. Never include API keys, provider credentials, private datasets, or unmasked agent artifacts in a pull request.

By contributing, you agree that your contribution is licensed under Apache-2.0.
