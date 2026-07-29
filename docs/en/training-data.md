---
seo_title: LLM Trading Agent Trajectories for Replay, RL, and Evaluation
description: Capture complete messages, tool schemas, reasoning fields, actions, fills, and phase metadata for auditable replay, reinforcement learning, behavior analysis, and optional SFT export.
lang: en
---

# Full-fidelity trajectories for RL and evaluation

TraderHarness persists every executor LLM exchange as a complete masked request/response pair. These trajectories support reproducible research, reinforcement learning, behavior analysis, and evaluation. An optional converter emits OpenAI-style SFT JSONL, but recorded decisions are not automatically high-quality training targets.

![Auditable trade review](https://hephaestlab.github.io/TraderHarness/assets/trade-review.png)

## Capture a trajectory

```bash
traderharness run \
  --agent trend-breakout \
  --start 2024-03-04 \
  --end 2024-03-29 \
  --mask-entities
```

Every `llm_exchange` step contains:

- the complete message list sent to the executor;
- the complete tool schema available for that call;
- assistant content and provider-exposed reasoning fields;
- every tool call and argument;
- phase and sub-window metadata.

Assistant text is not truncated in newly generated results. Compatibility `assistant` and `tool_call` steps remain available.

## Optional SFT conversion

```bash
traderharness export sft \
  ~/.traderharness/results/<run>_result.json \
  --output ./training.jsonl
```

Each call becomes one JSONL row containing `messages`, `tools`, and metadata such as agent, phase, sub-window, day index, and call index. Absolute trading dates do not enter export metadata; agent-visible dates remain relative.

## Safety gates

By default, export:

1. rejects runs without entity masking;
2. rejects legacy trajectories without full-fidelity exchanges;
3. scans output for entity and date leakage;
4. exits non-zero while any finding remains.

`--allow-unmasked` is an explicit escape hatch for private research. Such output must not be published as contamination-resistant training data.

## Selection is still required

Full fidelity preserves bad decisions as well as good ones. Before training, filter by outcomes, drawdown, rule compliance, tool failures, and human review. Confirm that provider terms allow generated reasoning and responses to be used for training.
