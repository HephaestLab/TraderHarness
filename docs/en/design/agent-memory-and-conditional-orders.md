# Layered Agent Memory and Conditional Execution

TraderHarness separates research memory from executable state. Hypotheses and lessons are retrievable memories; positions, frozen plans, and conditional orders remain environment-owned hard state.

## Sources and adaptation

The design adapts ideas from [OpenClaw memory](https://github.com/openclaw/openclaw/blob/main/docs/concepts/memory.md), [Letta memory blocks](https://docs.letta.com/guides/core-concepts/memory/memory-blocks), [OpenHands context condensation](https://docs.openhands.dev/sdk/guides/context-condenser), and [LangGraph checkpoints](https://langchain-ai.github.io/langgraph/reference/checkpoints/). No framework code or remote embedding dependency is imported. The benchmark path uses append-only local JSONL plus deterministic lexical retrieval.

Memory has four layers: compact active durable records, recent daily journals, on-demand archive search, and environment runtime-state snapshots flushed before context condensation. Replacing a record appends a supersession event and preserves the old version for audit.

Conditional orders are created, updated, cancelled, and listed through Agent tools. The environment evaluates only subsequently revealed 5-minute bar closes. A matching condition calls `TradingBus.place_order()`, so T+1, price limits, lot size, cash, one-trade-per-security-per-day, and configured position constraints still apply. A price trigger is therefore not a fill guarantee; failed attempts remain active and are audited for later retry.

Structured first entries automatically install a full-position `price_lte` protective order at `original_structural_stop`, effective from the next A-share trading day. Protective stops may be raised but never lowered. Updates never scan already visible bars retroactively.

Results include `conditional_orders`, `conditional_order_events`, and `memory_events`; conditional fills also carry `conditional_order_id` and `execution_time` in the normal trade ledger.
