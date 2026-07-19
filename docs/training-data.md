# Full-fidelity trajectory and SFT export

TraderHarness can persist the exact masked request/response pair for every
executor LLM call. This is intended for reproducible research and downstream
supervised fine-tuning (SFT), not as a claim that every generated decision is a
high-quality training target.

## Capture a trajectory

Run backtests with entity masking enabled:

```bash
traderharness run \
  --agent trend-breakout \
  --start 2024-03-04 \
  --end 2024-03-29 \
  --mask-entities
```

Each `llm_exchange` trajectory step contains:

- the complete message list sent to the executor;
- the complete tool schema available for that call;
- assistant content and optional reasoning content;
- complete tool calls and arguments;
- phase and sub-window metadata.

The compatibility `assistant` and `tool_call` steps are also retained. Assistant
text is no longer truncated in newly generated results.

## Export OpenAI-style JSONL

```bash
traderharness export sft \
  ~/.traderharness/results/<run>_result.json \
  --output ./training.jsonl
```

One line is emitted per LLM call:

```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "...", "tool_calls": []}
  ],
  "tools": [],
  "metadata": {
    "agent_id": "trend-breakout",
    "phase": "pre_market",
    "sub_window": null,
    "day_index": 1,
    "call_index": 1
  }
}
```

Absolute trading dates are not copied into export metadata. Agent-visible dates
remain relative (`D+0`, `D-1`, and so on).

## Safety gates

By default, export:

1. rejects runs that were not created with entity masking;
2. rejects legacy trajectories without full-fidelity `llm_exchange` records;
3. runs the entity/date leakage detector over the output;
4. exits non-zero if any finding remains.

`--allow-unmasked` is an explicit escape hatch for private research. Such
output must not be published as contamination-resistant training data.

## Curation remains necessary

Full fidelity preserves mistakes as well as good decisions. Before training,
filter trajectories using outcome, drawdown, rule compliance, tool errors, and
human review. Also verify that the selected model provider's terms permit use
of generated reasoning and responses for training.
