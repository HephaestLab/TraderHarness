## Summary

What does this change do, and why?

## Related issue

Closes #

## Type of change

- [ ] Bug fix
- [ ] New feature / extension (data adapter, tool, sandbox backend, metric, broker adapter, frontend)
- [ ] Documentation
- [ ] Refactor / chore

## Invariants checklist

If this touches the engine, masking, tools, sandbox, data pipeline, or order path, confirm each still holds (see
[`AGENTS.md`](../AGENTS.md#non-negotiable-invariants)):

- [ ] Market data access remains in-memory during a backtest (no new I/O path)
- [ ] `TradingBus.place_order()` remains the only order/matching path
- [ ] Point-in-time visibility is unchanged or made stricter, not looser
- [ ] Agent-facing calendar/entity masking still applies to any new egress
- [ ] Agents still receive read-only portfolio views
- [ ] The environment is still deterministic for the same inputs
- [ ] Not applicable to this change

## Tests

- [ ] Added a failing test before implementing the fix/feature
- [ ] `pytest tests/ --no-header -q` passes locally
- [ ] `ruff check traderharness scripts tests` passes locally
- [ ] For engine/masking/tools/data/sandbox changes: ran a real replay or backtest and inspected the trajectory
- [ ] `webui` changes: `npm test`, `npm run build`, and `npm run test:e2e` pass

## Real-data validation

State which real-data runs were performed and which were not. Do not silently substitute synthetic data or a
reduced universe for acceptance validation.

## Notes for reviewers

Anything else reviewers should know (breaking changes, follow-ups, things intentionally left out).
