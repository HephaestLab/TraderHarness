---
description: TraderHarness 全保真轨迹采集与轨迹导出：完整消息、工具 schema、推理内容逐次落盘，导出 OpenAI 风格 SFT JSONL。
---

# 全保真轨迹与轨迹导出

TraderHarness 可以持久化每一次执行者 LLM 调用的完整掩码请求/响应对。它的用途是可复现研究与下游监督微调（SFT），并不代表每一条生成的决策都是高质量训练目标。

![逐笔复盘：K 线上下文、下单理由与执行证据](assets/trade-review.png)

*每一次决策都可回放审计：成交时 K 线、已记录的下单理由、工具调用参数与执行结果完整留档。*

## 采集轨迹

开启实体掩码运行回测：

```bash
traderharness run \
  --agent trend-breakout \
  --start 2024-03-04 \
  --end 2024-03-29 \
  --mask-entities
```

每个 `llm_exchange` 轨迹步骤包含：

- 发给执行者的完整消息列表；
- 该次调用可用的完整工具 schema；
- assistant 内容与可选的推理内容；
- 完整的工具调用与参数；
- 阶段与子窗口元数据。

兼容性的 `assistant` 与 `tool_call` 步骤也会保留。新生成的结果中 assistant 文本不再截断。

## 导出 OpenAI 风格 JSONL

```bash
traderharness export sft \
  ~/.traderharness/results/<run>_result.json \
  --output ./training.jsonl
```

每次 LLM 调用输出一行：

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

绝对交易日期不会进入导出元数据；Agent 可见日期保持相对形式（`D+0`、`D-1` 等）。

## 安全闸口

默认情况下，导出会：

1. 拒绝未开启实体掩码的运行；
2. 拒绝缺少全保真 `llm_exchange` 记录的旧轨迹；
3. 对输出运行实体/日期泄漏检测；
4. 只要仍有检出就以非零码退出。

`--allow-unmasked` 是面向私有研究的显式逃生门，这类输出不得作为抗污染训练数据发布。

## 筛选仍然必要

全保真意味着错误决策与好决策都会被保留。训练前请按结果、回撤、规则合规、工具错误与人工复核过滤轨迹，并确认所选模型供应商的条款允许将生成的推理与回复用于训练。
