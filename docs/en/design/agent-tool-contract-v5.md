seo_title: TraderHarness Agent Tool Schemas, Error Repair, and Phase Contract v5
description: Strict inputs, uniform errors, in-phase self-repair, sandbox timeouts, and legacy replay compatibility for all 30 TraderHarness Agent tools.
lang: en
---

# Agent Tool Contract v5

This design governs all 30 Agent-facing tools in TraderHarness. It makes input requirements visible before a call,
keeps repairable failures inside the same market phase, and makes behavior auditable through schemas, trajectories,
and deterministic replay.

## Contract boundary

- v5 is the default for new runs. v1–v4 keep their historical descriptions, schemas, message ordering, and
  serialization so existing cassettes remain replayable.
- Every v5 input object uses `additionalProperties: false`; every field has a description plus applicable enums,
  ranges, defaults, and conditional requirements.
- Every tool description includes a valid `arguments` example, a success-result summary, and the common error contract.
- Local validation runs before entity unmasking and before the handler. Invalid calls cannot reach tool logic or matching.
- DeepSeek-compatible gateways do not consistently expose provider-side strict mode, so v5 performs deterministic local
  schema validation without changing the configured API provider.

Successful results include `success: true`. Failures use this envelope:

```json
{
  "success": false,
  "error": "specific human- and model-readable error",
  "error_code": "stable_machine_code",
  "retryable": true,
  "correction": {
    "tool": "tool_name",
    "instruction": "how to repair this call in the same phase",
    "valid_arguments_example": {},
    "received_arguments": {}
  }
}
```

A `retryable: true` failure remains pending inside the phase. The Agent must make that tool succeed or explicitly list
the code in `abandon_error_codes` on `complete_phase` / `finish_day` and explain the abandonment. Completion tools are
validated like every other tool. The close fallback exposes up to three repair attempts and records a
`_finish_day_protocol_failure` instead of silently swallowing failure.

## Tool inventory

| Group | Tools | v5 contract focus |
|---|---|---|
| Market | `get_kline`, `get_stock_price`, `get_stock_info`, `get_market_overview` | Strict D-1 daily history; current revealed five-minute price during windows; source and as-of metadata |
| Narrative | `get_narrative_market_overview`, `get_narrative_sector_summary`, `get_narrative_news` | Point-in-time evidence IDs, breadth, leadership comparison, explicit non-retryable daily budgets |
| Screening | `screen_stocks`, `screen_behavioral_cycle`, `get_sector_summary` | Bounded result counts, valid ranges, deterministic point-in-time features |
| Fundamentals | `get_fundamentals`, `get_business_segments`, `get_valuation` | Explicit units; segment revenue is `revenue_100m_cny` |
| Text | `get_announcements`, `get_announcement_evidence`, `get_news` | Time, title, type/content, literal keyword matching, auditable evidence IDs |
| Portfolio | `get_portfolio`, `get_position` | Position plans, sellable quantity, P&L, phase-aware valuation sources |
| Execution | `place_order`, `manage_conditional_order`, `list_conditional_orders` | Context-dependent plan/card requirements, per-operation conditional fields, relative expiry, unchanged single matching path |
| Watchlist | `add_watchlist`, `remove_watchlist`, `get_watchlist` | Full visible aliases, reasons, TTL, phase-aware prices |
| Memory | `remember`, `search_memory`, `get_memory` | Stable IDs, typed search, limits, conflict candidates, and supersession retry arguments |
| Sandbox | `execute_code` | Code bounds, terminated timeouts, tracebacks, retry budget, allowlist-gated data APIs |
| Control | `complete_phase`, `finish_day` | Explicit clock advancement only after successful validation and resolved retryable errors |

Stock-code fields require the complete visible code. With entity masking enabled, a code such as `SHM-000360` must
retain its board prefix. An ambiguous six-digit suffix returns `candidate_aliases` and complete
`retry_argument_choices` instead of asking the model to guess.

## Large results and sandbox behavior

v5 no longer truncates raw JSON at 3,000 characters. It progressively compacts arrays and long strings while preserving
valid JSON and adds `_truncation`, the original length, and a query-narrowing instruction. v1–v4 retain the historical
serializer for replay compatibility.

The sandbox remains an in-process analysis surface over masked, read-only market views. v5 installs a Python-bytecode
deadline trace, verifies that a timed-out worker exits, and returns `sandbox_timeout`. Data APIs also honor the Agent-card
allowlist: market-wide daily data requires `get_kline`; behavioral features require `screen_behavioral_cycle` or
`get_kline`. Canonical dataset access and nested backtests remain prohibited.

## Audit coverage

Executable contract tests enumerate all 30 tools and verify catalog parity, input/output contracts, field documentation,
and examples. They also cover handler bypass on invalid input, normalized legacy errors, valid-JSON result compaction,
completion blocking and repair, real infinite-loop termination, and request-identical replay of the bundled v2 real-data
cassette.

```powershell
.venv\Scripts\python.exe -m ruff check traderharness tests
.venv\Scripts\python.exe -m pytest tests --no-header -q
traderharness audit <artifact>
```
