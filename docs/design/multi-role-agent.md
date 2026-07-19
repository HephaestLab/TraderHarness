# Multi-role Agent Adapter

## Goal

Support TradingAgents-style committees without changing TraderHarness's market,
portfolio, matching, masking, or replay semantics. A committee is one evaluated
agent with one portfolio. Specialist roles advise; one executor alone may call
`place_order`.

This is distinct from `traderharness compare`, where independent agents receive
separate portfolios and are ranked against each other.

## Model

```text
BacktestEngine (shared immutable market snapshot)
  └─ CommitteeAgent (one Portfolio + one TradingBus)
       ├─ fundamentals advisor ─┐
       ├─ technical advisor ───┼─> phase memo
       ├─ news advisor ────────┤
       ├─ bull researcher ─────┤
       ├─ bear researcher ─────┘
       └─ trader/executor -> existing AgentLoop -> TradingBus.place_order()
```

Independent committees remain parallelizable by the engine:

```text
Committee A + Portfolio A ─┐
Committee B + Portfolio B ─┼─ asyncio.gather per trading day
Single Agent + Portfolio C ─┘
```

## Invariants

1. Advisors only receive already-masked Agent-visible messages.
2. Advisors have no order tool. Read-only tool access is a later extension.
3. The executor uses the existing `ToolRegistry`; `TradingBus.place_order()` is
   still the only matching path.
4. Committee calls are deterministic for replay: role, phase, prompt, response,
   model, and ordering are trajectory records.
5. One run-scoped `EntityMasker` is shared by every advisor and executor.
6. Advisor failures are explicit in the memo and trace; no silent fallback.

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

`AgentLoop._run_phase()` requests one memo before the first executor call for
each `(day, phase, sub_window)`. Advisors run concurrently with
`asyncio.gather`; their output is inserted as a tagged system message. The
executor can accept or reject every recommendation.

## TradingAgents adapter

The adapter maps external graph nodes to `Advisor` implementations:

- Market/News/Fundamentals analysts -> specialist advisors
- Bull/Bear researchers -> adversarial advisors
- Research manager/Risk manager -> synthesis advisors
- Trader -> TraderHarness executor

External tools and portfolio objects are not imported. They are replaced by
TraderHarness's masked observations and single portfolio/order path. This keeps
external reasoning topology while preserving backtest fairness.

## Configuration

The loader (`PromptAgent`) detects a committee from a top-level `advisors:` list — there is no nested `committee:`
or `executor:` block. `id`, `name`, and the executor's own `model`/`persona` sit at the top level, exactly like a
single-agent card:

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

See [`examples/tradingagents_committee.yaml`](https://github.com/HephaestLab/TraderHarness/blob/main/examples/tradingagents_committee.yaml)
for the full, loadable reference committee.

## Acceptance criteria

- Unit test proves advisors never receive `place_order`.
- Unit test proves all advisors are scheduled concurrently.
- Integration test proves exactly one executor can place orders.
- Replay reproduces the same memo and executor action sequence.
- Real one-day, three-day, and one-month runs pass leakage audit.
- `compare` can rank a committee against ordinary agents under identical data,
  cash, masking seed, and benchmark.

## Deferred

- Advisor-specific read-only tool budgets.
- Arbitrary cyclic graphs and inter-agent message buses.
- Shared portfolio controlled by multiple executors (intentionally excluded;
  it would make order ownership and replay ambiguous).
