---
seo_title: Backtesting Multi-role LLM Trading Agents with Read-only Advisors
description: TraderHarness committee design keeps research and risk advisors read-only, gives one trader the order tool, and preserves deterministic replay and portfolio accountability.
lang: en
---

# Multi-role agent adapter

## Goal

Support TradingAgents-style committees without changing TraderHarness market, portfolio, matching, masking, or replay semantics. A committee is one evaluated agent with one portfolio. Specialist roles advise; only the executor may call `place_order`.

This differs from `traderharness compare`, where independent agents own separate portfolios and compete with each other.

## Model

```text
BacktestEngine (shared immutable market snapshot)
  └─ CommitteeAgent (one Portfolio + one TradingBus)
       ├─ fundamentals advisor ───┐
       ├─ technical advisor ──────┼─> phase memo
       ├─ news advisor ───────────┤
       ├─ bull researcher ────────┤
       ├─ bear researcher ────────┘
       └─ trader/executor -> AgentLoop -> TradingBus.place_order()
```

## Invariants

1. Advisors receive only masked, agent-visible messages.
2. Advisors never receive an order tool.
3. The executor uses the existing `ToolRegistry`; `TradingBus.place_order()` remains the only matching path.
4. Roles, phases, prompts, responses, models, and order are recorded for deterministic replay.
5. Every role shares one run-level `EntityMasker`.
6. Advisor failures remain visible in the memo and trajectory.

## Extension surface

```python
class Advisor(Protocol):
    role: str
    async def advise(self, messages: list[dict], phase: str) -> str: ...

class CommitteeCoordinator:
    async def build_memo(
        self,
        messages: list[dict],
        phase: str,
        sub_window: str | None,
    ) -> CommitteeMemo: ...
```

Advisors run concurrently with `asyncio.gather`; their labeled memo is injected before the first executor call for each `(day, phase, sub_window)`. The executor may accept or reject each recommendation.

## TradingAgents mapping

- market, news, and fundamental analysts become specialist advisors;
- bull and bear researchers become adversarial advisors;
- research and risk managers become synthesis advisors;
- Trader becomes the TraderHarness executor.

External portfolio and tool objects are not imported. The adapter keeps the reasoning topology while replacing execution with masked observations and the controlled order path.

## Configuration

```yaml
id: tradingagents-reference
name: TradingAgents Reference Committee
model: deepseek-chat
persona: ...
advisors:
  - role: fundamentals
    model: deepseek-chat
    prompt: ...
  - role: technical
    model: deepseek-chat
    prompt: ...
  - role: bull
    model: deepseek-chat
    prompt: ...
  - role: bear
    model: deepseek-chat
    prompt: ...
```

See the loadable [reference committee](https://github.com/HephaestLab/TraderHarness/blob/main/examples/tradingagents_committee.yaml).

## Acceptance criteria

- advisors never receive `place_order`;
- advisors are scheduled concurrently;
- exactly one executor can trade;
- replay reproduces the same memo and action sequence;
- real-data runs pass leakage audits;
- `compare` can rank committees and ordinary agents under identical data, capital, seed, and benchmark settings.
