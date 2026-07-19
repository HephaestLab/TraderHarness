---
name: Bug report
about: Report a defect in the engine, masking, tools, sandbox, data pipeline, or console
title: "[Bug] "
labels: bug
assignees: ""
---

## Summary

A short description of what went wrong.

## Affected area

- [ ] Engine / matching (`TradingBus.place_order()`, corporate actions, calendar)
- [ ] Masking (temporal, calendar, entity)
- [ ] Tools (`traderharness/tools/`)
- [ ] Sandbox (`execute_code`, `traderharness_api`)
- [ ] Data pipeline (providers, updates, integrity)
- [ ] Agents / committees / trajectory / replay
- [ ] Metrics / reports
- [ ] Local server / web console
- [ ] Docs / packaging

## Environment

- TraderHarness version (`traderharness --version`):
- OS:
- Python version:
- Install method (pip / source / Docker):

## Steps to reproduce

1.
2.
3.

## Expected behavior

## Actual behavior

Include the exact error message, traceback, or a minimal trajectory/result excerpt if relevant. Do not paste API
keys, licensed market data, or unmasked agent artifacts.

## Real-data validation

Was this reproduced against real point-in-time market data (not a reduced universe or synthetic substitute)? If
not, say so explicitly — see [`CONTRIBUTING.md`](../../CONTRIBUTING.md).

## Additional context

Logs, screenshots, or a link to a related run/replay artifact.
